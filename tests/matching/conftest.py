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
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from base_de_test import preparer_base, supprimer_base
from raiyon.catalogue.chargement import charger_en_base
from raiyon.catalogue.pipeline import FICHIER_SEED, lire_seed
from raiyon.catalogue.schemas import Categorie, ProduitEnBase
from raiyon.matching.criteres import RequeteMatching
from raiyon.matching.depot import DepotSql, Fourchette, RelevesDeRelachement

NOM_BASE_MATCHING = "raiyon_test_matching"

# --------------------------------------------------------------------------- #
# Part pure : produits inventés et dépôt factice
# --------------------------------------------------------------------------- #

DEFAUTS: dict[Categorie, dict[str, Any]] = {
    "monitor": {
        "screen_size": Decimal("27"),
        "largeur_px": 2560,
        "hauteur_px": 1440,
        "aspect_ratio": "16:9",
        "panel_type": "IPS",
        "refresh_rate": 144,
        "response_time": Decimal("1"),
    },
    "internal-hard-drive": {
        "capacity": 1000,
        "form_factor": "M.2-2280",
        "interface": "M.2 PCIe 4.0 X4",
        "type": "SSD",
        "rpm": None,
        "price_per_gb": Decimal("0.100"),
        "cache": 1024,
    },
    "memory": {
        "ddr_generation": 5,
        "frequence_mhz": 6000,
        "nb_modules": 2,
        "taille_module_gb": 16,
        "capacite_totale_gb": 32,
        "cas_latency": 30,
        "first_word_latency": Decimal("10"),
        "price_per_gb": Decimal("4"),
        "color": "Black",
    },
    "headphones": {
        "type": "Circumaural",
        "microphone": True,
        "wireless": False,
        "enclosure_type": "Closed",
        "freq_min_hz": 20,
        "freq_max_khz": Decimal("20"),
        "color": "Black",
    },
    "video-card": {
        "chipset": "GeForce RTX 4070",
        "memory": Decimal("12"),
        "length": 300,
        "core_clock": 1920,
        "boost_clock": 2475,
        "color": "Black",
    },
    "cpu": {
        "core_count": 8,
        "core_clock": Decimal("3.8"),
        "tdp": 65,
        "microarchitecture": "Zen 4",
        "boost_clock": Decimal("5.0"),
        "graphics": None,
    },
}
"""Un produit « moyen » par catégorie. Les tests ne redisent que ce qu'ils changent,
ce qui fait qu'une assertion se lit sans dérouler la fixture."""


def fabriquer(
    categorie: Categorie,
    numero: int,
    prix: str,
    marque: str = "Acme",
    **specs: Any,
) -> ProduitEnBase:
    """Un produit inventé, valide au sens de `ProduitEnBase`.

    L'identifiant respecte `MOTIF_ID` (`{categorie}-{10 hexadécimaux}`) : un produit de
    test qui ne passerait pas la validation du schéma ne prouverait rien du moteur.
    """
    return ProduitEnBase(
        id=f"{categorie}-{numero:010x}",
        nom=f"{marque} modele {numero}",
        marque=marque,
        categorie=categorie,
        prix_usd=Decimal(prix),
        disponible=True,
        specs={**DEFAUTS[categorie], **specs},  # type: ignore[arg-type]
    )


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
