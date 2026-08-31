"""Fixtures du moteur de matching, et la frontière de l'arbitrage A rendue visible.

Ce fichier porte les deux moitiés de la suite :

* **la part pure** — une douzaine de produits inventés, un dépôt factice, aucune base.
  Ces produits vivent dans `tests/`, **jamais dans `data/`** : fabriquer un produit
  pour faire passer un test le ferait entrer dans le catalogue, c'est-à-dire dans ce
  que le LLM aura le droit de citer, et §2 l'interdit.
* **la part `integration`** — une base dédiée `raiyon_test_matching`, migrée et
  **seedée une seule fois** (portée `session`). Sans cette portée, on mesurerait le
  coût des migrations et non celui du moteur, et la porte de sortie « moins de deux
  secondes » échouerait pour une raison qui n'a rien à voir avec elle.

La base de matching est distincte de `raiyon_test` : les tests de l'étape 4 supposent
une table vide au début de chaque test, un catalogue chargé les ferait tomber.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from base_de_test import preparer_base, supprimer_base
from produits_de_test import DEFAUTS, fabriquer
from raiyon.catalogue.chargement import charger_en_base
from raiyon.catalogue.pipeline import FICHIER_SEED, lire_seed
from raiyon.catalogue.schemas import ProduitEnBase
from raiyon.matching.criteres import RequeteMatching
from raiyon.matching.depot import DepotSql, Fourchette, RelevesDeRelachement

NOM_BASE_MATCHING = "raiyon_test_matching"

# --------------------------------------------------------------------------- #
# Part pure : produits inventés et dépôt factice
# --------------------------------------------------------------------------- #

# `DEFAUTS` et `fabriquer()` ont déménagé dans `tests/produits_de_test.py` à l'étape 7 :
# la suite des outils en a besoin elle aussi, et un conftest ne s'importe pas depuis un
# autre. Ils restent visibles ici sous leurs noms d'origine, pour que les tests de
# l'étape 6 continuent de les prendre par `from conftest import fabriquer`.


@dataclass
class DepotFactice:
    """Un dépôt qui rend ce qu'on lui a mis dedans, et compte ce qu'on lui a dicté.

    C'est ce que permet le protocole `DepotProduits` : la moitié Python du moteur se
    teste avec des **comptages injectés à la main**, sans base, sans SQL et sans que le
    test ait à construire une situation qui produirait ces comptages.
    """

    produits: list[ProduitEnBase] = field(default_factory=list)
    hors_budget: list[ProduitEnBase] = field(default_factory=list)
    ecartes: dict[str, int] = field(default_factory=dict)
    releves: RelevesDeRelachement = field(default_factory=RelevesDeRelachement)
    appels_de_comptage: int = 0
    fourchettes: list[Fourchette] = field(default_factory=list)

    def candidats(self, requete: RequeteMatching, fourchette: Fourchette) -> list[ProduitEnBase]:
        # La fourchette distingue les deux appels du moteur : bornée à gauche, c'est la
        # zone de tolérance ; sinon, le classement principal.
        self.fourchettes.append(fourchette)
        return list(self.hors_budget if fourchette.min_exclu is not None else self.produits)

    def ecartes_faute_de_donnee(
        self, requete: RequeteMatching, fourchette: Fourchette
    ) -> dict[str, int]:
        return dict(self.ecartes)

    def releves_de_relachement(
        self, requete: RequeteMatching, fourchette: Fourchette
    ) -> RelevesDeRelachement:
        self.appels_de_comptage += 1
        return self.releves


# --------------------------------------------------------------------------- #
# Part integration : le catalogue réel, chargé une fois
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def moteur_catalogue() -> Iterator[Engine]:
    """Base migrée et **seedée une seule fois** pour toute la session de tests."""
    if not FICHIER_SEED.is_file():
        pytest.skip(f"{FICHIER_SEED} est absent — lancer `make seed-build`.")

    url = preparer_base(NOM_BASE_MATCHING)
    moteur = create_engine(url, pool_pre_ping=True)
    with Session(moteur) as session:
        charger_en_base(session, lire_seed(FICHIER_SEED))
        session.commit()
    yield moteur
    moteur.dispose()
    supprimer_base(NOM_BASE_MATCHING)


@pytest.fixture
def session_catalogue(moteur_catalogue: Engine) -> Iterator[Session]:
    """Session en lecture sur le catalogue seedé, annulée à la fin par précaution."""
    connexion = moteur_catalogue.connect()
    transaction = connexion.begin()
    session = Session(bind=connexion, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connexion.close()


@pytest.fixture
def depot(session_catalogue: Session) -> DepotSql:
    """Le dépôt Postgres branché sur le catalogue complet."""
    return DepotSql(session_catalogue)


__all__ = ["DEFAUTS", "DepotFactice", "fabriquer"]
