"""Fixtures de la boucle. **Aucune n'a besoin de clé API, de base ni de `.env`.**

C'est la propriété que la porte de sortie de l'étape 8 demande : `make check` tourne
sans conteneur et sans clé, et la suite de `tests/agent/` en fait partie.

Ce fichier ne porte **que** des fixtures. Les helpers importables sont dans
`scenarios.py` : deux `conftest.py` se chargeraient sous le même nom de module et
`pytest tests/agent tests/tools` échouerait à l'import selon l'ordre de collecte.
"""

import pytest

from outils_de_test import TOLERANCE, DepotEnMemoire, ecrans
from raiyon.tools.repartiteur import ContexteOutils
from raiyon.tools.schema_outils import schema_des_outils


@pytest.fixture
def depot() -> DepotEnMemoire:
    """Trois écrans à 165 Hz : de quoi faire remonter des produits sans dépendre du seed."""
    depot = DepotEnMemoire()
    depot.produits = ecrans(3, refresh_rate=165)
    return depot


@pytest.fixture
def contexte(depot: DepotEnMemoire) -> ContexteOutils:
    return ContexteOutils(depot=depot, tour_client=1, tolerance=TOLERANCE)


@pytest.fixture
def outils() -> tuple[dict, ...]:
    """Les vraies définitions. Un schéma de test se serait mis à mentir sur le catalogue."""
    return schema_des_outils()
