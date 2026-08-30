"""Base de test jetable pour les tests d'intégration de l'étape 4.

La plomberie — création, migration, URL, message d'absence de Postgres — vit dans
`tests/base_de_test.py` depuis l'étape 6 : `tests/matching/` en a besoin aussi, et un
conftest ne s'importe pas depuis un autre. Les décisions qui la gouvernent sont
documentées là-bas ; ne restent ici que les fixtures propres à ce répertoire.
"""

from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from base_de_test import (
    config_alembic,
    creer_base_vierge,
    preparer_base,
    supprimer_base,
    url_de,
)

NOM_BASE_DE_TEST = "raiyon_test"
# Base distincte pour l'aller-retour des migrations : ce test détruit le schéma,
# il ne peut donc pas partager la base des autres.
NOM_BASE_MIGRATIONS = "raiyon_test_migrations"


@pytest.fixture(scope="session")
def base_de_test() -> Iterator[URL]:
    """Crée `raiyon_test`, y applique les migrations, la supprime à la fin."""
    yield preparer_base(NOM_BASE_DE_TEST)
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
    url = url_de(NOM_BASE_MIGRATIONS)
    try:
        yield url, config_alembic(url)
    finally:
        supprimer_base(NOM_BASE_MIGRATIONS)
