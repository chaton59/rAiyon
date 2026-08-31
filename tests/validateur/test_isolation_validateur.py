"""Aucun module de `raiyon.validateur` ne charge le SDK Anthropic.

**Troisième paquet à porter cette garantie**, après `raiyon.catalogue` et `raiyon.tools`,
et celui pour lequel la tentation est la plus forte : le validateur relit ce que le
modèle a écrit, il vit à trois lignes de la boucle, et l'import « pour réutiliser un
type » ne coûte rien à écrire.

Ce que le test achète : la couche qui porte le critère d'acceptation nº1 se teste
**sans clé API**, et c'est vrai par vérification et non par discipline. Le mécanisme est
celui d'`isolation_sdk.py` — découverte des modules sur le disque, interpréteur neuf,
contre-épreuve — et c'est précisément parce qu'il découvre les modules qu'il couvrira le
module ajouté demain.

⚠️ **À dire précisément : la garantie porte sur `anthropic`, pas sur SQLAlchemy.**
`repli.py` est typé sur `ResultatMatching`, donc il importe `raiyon.matching.moteur`,
donc `depot.py`, donc `sqlalchemy` — exactement comme `raiyon.tools` depuis l'étape 7.
La propriété qui compte n'est pas « rien n'importe SQLAlchemy » mais « rien ne se
connecte » : la suite entière de `tests/validateur/` tourne sans conteneur, ce que
`make check` constate à chaque exécution.
"""

import pytest

from isolation_sdk import modules_anthropic_charges_par, modules_du_paquet

PAQUET = "raiyon.validateur"


@pytest.mark.parametrize("module", modules_du_paquet(PAQUET))
def test_aucun_module_du_validateur_ne_charge_le_sdk_anthropic(module: str):
    assert modules_anthropic_charges_par(module) == []
