"""Fixtures de la couche outils. Les helpers **importables** sont dans
`tests/outils_de_test.py` : ce fichier ne porte que ce que pytest résout tout seul.
"""

import pytest

from outils_de_test import DepotEnMemoire, critere, etat_avec
from raiyon.matching.criteres import Importance, Operateur
from raiyon.tools.etat import EtatSession


@pytest.fixture
def depot() -> DepotEnMemoire:
    """Un dépôt vide : chaque test y met ce dont il a besoin, et rien d'autre."""
    return DepotEnMemoire()


@pytest.fixture
def etat_ecran() -> EtatSession:
    """Un client qui a demandé un écran 144 Hz bloquant, avec 400 USD de budget."""
    return etat_avec(
        "monitor",
        critere("refresh_rate", Operateur.AU_MOINS, "144", Importance.BLOQUANT),
        budget="400",
    )
