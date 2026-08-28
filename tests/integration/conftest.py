"""Base de test jetable pour les tests d'intégration.

**Décision : une base dédiée `raiyon_test` sur le Postgres de `docker-compose`**, et
non `testcontainers`. Le conteneur est déjà là — `make up` le démarre — et le faire
démarrer une seconde fois par la suite de tests ajouterait une dépendance et une
dizaine de secondes par exécution pour la même garantie. La contrepartie est
assumée : ces tests ont besoin d'un Postgres joignable, ils portent donc le marqueur
`integration` et restent hors de `make check`.

**Conflit avec `isolated_env`, et sa résolution.** La fixture `isolated_env` de
`tests/conftest.py` est `autouse` : elle retire les variables `RAIYON_*` et déplace
le répertoire courant vers un dossier temporaire, ce qui rend `.env` introuvable.
C'est exactement ce qu'on veut pour les tests unitaires de configuration, et
exactement ce qui empêcherait de trouver la base ici. L'URL est donc lue **à
l'import de ce fichier**, avant qu'aucune fixture n'ait pu s'exécuter, et conservée
dans une constante de module. Réinjecter la variable après coup aurait marché aussi,
mais aurait fait dépendre ces tests de l'ordre d'exécution des fixtures.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from raiyon.config import Settings

RACINE = Path(__file__).resolve().parents[2]
NOM_BASE_DE_TEST = "raiyon_test"
# Base distincte pour l'aller-retour des migrations : ce test détruit le schéma,
# il ne peut donc pas partager la base des autres.
NOM_BASE_MIGRATIONS = "raiyon_test_migrations"

# Base de maintenance : on ne peut ni créer ni supprimer une base depuis
# elle-même, il faut être connecté ailleurs. `postgres` existe toujours.
BASE_DE_MAINTENANCE = "postgres"


def _url_configuree() -> URL:
    """Lit l'URL du projet à l'import, `.env` compris.

    La clé API est remplacée par une valeur factice : c'est le seul champ obligatoire
    de `Settings`, il n'a rien à voir avec la base, et l'exiger ferait échouer ces
    tests sur une machine qui n'a pas de clé — en CI, par exemple, où le job doit
    passer sur un fork.
    """
    settings = Settings(
        _env_file=RACINE / ".env",
        anthropic_api_key=SecretStr("factice-tests-integration"),
    )
    return make_url(str(settings.database_url))


URL_CONFIGUREE = _url_configuree()
URL_MAINTENANCE = URL_CONFIGUREE.set(database=BASE_DE_MAINTENANCE)
URL_BASE_DE_TEST = URL_CONFIGUREE.set(database=NOM_BASE_DE_TEST)

MESSAGE_SANS_POSTGRES = (
    f"Postgres injoignable sur {URL_CONFIGUREE.render_as_string(hide_password=True)} - "
    "lancer `make up`, puis relancer `make test-int`."
)


def _moteur_de_maintenance() -> Engine:
    """Moteur en AUTOCOMMIT : `CREATE DATABASE` ne peut pas tourner en transaction."""
    return create_engine(URL_MAINTENANCE, isolation_level="AUTOCOMMIT")


def creer_base_vierge(nom: str) -> None:
    """(Re)crée une base vide. Skip explicite si Postgres n'est pas là."""
    moteur = _moteur_de_maintenance()
    try:
        with moteur.connect() as connexion:
            # Les sessions ouvertes sur la base empêchent sa suppression ; sans ce
            # `WITH (FORCE)`, une exécution interrompue au débogueur bloque toutes
            # les suivantes avec une erreur qui ne dit pas pourquoi.
            connexion.execute(text(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)'))
            connexion.execute(text(f'CREATE DATABASE "{nom}"'))
    except OperationalError as erreur:
        pytest.skip(f"{MESSAGE_SANS_POSTGRES}\n({erreur.__class__.__name__})")
    finally:
        moteur.dispose()


def supprimer_base(nom: str) -> None:
    """Supprime la base de test. Aucune donnée n'y survit d'une exécution à l'autre."""
    moteur = _moteur_de_maintenance()
    try:
        with moteur.connect() as connexion:
            connexion.execute(text(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)'))
    except OperationalError:
        # Le nettoyage ne doit pas masquer l'échec d'un test par une erreur de
        # démontage : si Postgres a disparu en cours de route, on l'a déjà vu.
        pass
    finally:
        moteur.dispose()


def config_alembic(url: URL) -> Config:
    """Configuration Alembic visant explicitement `url`.

    `env.py` privilégie l'URL passée ici sur celle de la configuration du projet :
    c'est ce qui permet de migrer une base jetable sans jamais toucher `raiyon`.
    """
    config = Config(str(RACINE / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    return config


@pytest.fixture(scope="session")
def base_de_test() -> Iterator[URL]:
    """Crée `raiyon_test`, y applique les migrations, la supprime à la fin."""
    creer_base_vierge(NOM_BASE_DE_TEST)
    command.upgrade(config_alembic(URL_BASE_DE_TEST), "head")
    yield URL_BASE_DE_TEST
    supprimer_base(NOM_BASE_DE_TEST)


@pytest.fixture(scope="session")
def moteur(base_de_test: URL) -> Iterator[Engine]:
    """Moteur branché sur la base de test, partagé par toute la session."""
    moteur = create_engine(base_de_test, pool_pre_ping=True)
    yield moteur
    moteur.dispose()


@pytest.fixture
def session(moteur: Engine) -> Iterator[Session]:
    """Une session dans une transaction annulée à la fin du test.

    Chaque test repart donc d'une base vide sans qu'on ait à la recréer ni à la
    tronquer : le `rollback` final défait tout, y compris ce qu'un `commit()` du test
    a validé — la session rejoint la transaction externe par un point de sauvegarde.
    """
    connexion = moteur.connect()
    transaction = connexion.begin()
    session = Session(bind=connexion, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        # Un `IntegrityError` levé au commit termine lui-même la transaction externe.
        # Rappeler `rollback()` dans ce cas ne casse rien mais lève un avertissement
        # SQLAlchemy qui, répété, finit par masquer les vrais.
        if transaction.is_active:
            transaction.rollback()
        connexion.close()


@pytest.fixture
def base_jetable() -> Iterator[tuple[URL, Config]]:
    """Une base vide et sa configuration Alembic, supprimée quoi qu'il arrive.

    Sert au test d'aller-retour des migrations, qui ne peut pas travailler sur la
    base partagée : il la viderait pour tous les autres.
    """
    creer_base_vierge(NOM_BASE_MIGRATIONS)
    url = URL_CONFIGUREE.set(database=NOM_BASE_MIGRATIONS)
    try:
        yield url, config_alembic(url)
    finally:
        supprimer_base(NOM_BASE_MIGRATIONS)
