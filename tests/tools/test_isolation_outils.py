"""Aucun module de `raiyon.tools` ne charge le SDK Anthropic.

**Ce n'est pas la même garantie que pour le catalogue, et elle vaut pour une autre
raison.** Le catalogue ne charge pas le SDK parce qu'aucun octet du catalogue ne vient
d'un modèle (§3.4ter). La couche outils, elle, sera appelée depuis la boucle d'agent : le
SDK sera juste à côté, et l'import « pour réutiliser un type » est à une ligne.

Ce que ce test achète : la couche où vivent tous les invariants du produit se teste
**sans clé API**, et c'est vrai par vérification et non par discipline. C'est la
condition qui rend la porte de sortie de l'étape 7 — le critère nº2 franchi avant qu'un
LLM existe dans le projet — autre chose qu'une intention.
"""

import pytest

from isolation_sdk import modules_anthropic_charges_par, modules_du_paquet

PAQUET = "raiyon.tools"


@pytest.mark.parametrize("module", modules_du_paquet(PAQUET))
def test_aucun_module_des_outils_ne_charge_le_sdk_anthropic(module: str):
    assert modules_anthropic_charges_par(module) == []


def test_le_sdk_est_bien_installe():
    """Contre-épreuve : sans elle, le test ci-dessus passerait sur un SDK absent."""
    assert modules_anthropic_charges_par("anthropic") != []
