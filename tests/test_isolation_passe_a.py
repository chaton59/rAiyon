"""Aucun module du catalogue ne charge le SDK Anthropic — arbitrage B de l'étape 5.

**Pourquoi ce test existe, et pourquoi il s'est durci.** À l'origine, il gardait la
séparation entre une passe A déterministe et une passe B qui appelait un modèle : il
suffisait d'un `from raiyon.catalogue.traduction import ...` ajouté « pour réutiliser
une fonction » pour que la frontière cède. La passe B a été supprimée (§3.4ter), et la
garantie est devenue plus forte que la frontière qu'elle protégeait : **plus aucun
octet du catalogue ne vient d'un modèle**, donc plus aucun module de
`raiyon.catalogue` n'a de raison de connaître le SDK.

Le test ne cite donc plus une liste de modules écrite à la main — elle aurait vieilli
au premier fichier ajouté. Il **découvre** les modules du paquet et les vérifie tous.

Le sous-processus est indispensable : `pytest` importe le SDK ailleurs dans la suite,
donc regarder `sys.modules` dans le processus courant ne prouverait rien.
"""

import importlib
import importlib.util
from pathlib import Path

import pytest

from isolation_sdk import modules_anthropic_charges_par, modules_du_paquet

PAQUET = "raiyon.catalogue"
REPERTOIRE = Path(__file__).resolve().parents[1] / "src" / "raiyon" / "catalogue"

# Le mécanisme — découverte sur le disque, interpréteur neuf, contre-épreuve — a
# déménagé dans `tests/isolation_sdk.py` à l'étape 7, quand `raiyon.tools` a eu besoin
# de la même garantie. Le recopier aurait donné deux versions d'une même vérification,
# et celle qu'on ne modifie plus finit par ne plus vérifier grand-chose.


@pytest.mark.parametrize("module", modules_du_paquet(PAQUET))
def test_aucun_module_du_catalogue_ne_charge_le_sdk_anthropic(module: str):
    """`make seed-build` et `make seed` ne font aucun appel API — ni même un import."""
    assert modules_anthropic_charges_par(module) == []


def test_le_catalogue_nexpose_plus_rien_qui_sappelle_traduction():
    """La passe B n'a pas été neutralisée, elle a été retirée (§3.4ter).

    Un module laissé en place « au cas où » aurait gardé vivante une décision
    renversée, et le prochain lecteur y aurait vu une intention.
    """
    assert importlib.util.find_spec(f"{PAQUET}.traduction") is None
    assert not [chemin for chemin in REPERTOIRE.glob("*.py") if "traduction" in chemin.stem]

    paquet = importlib.import_module(PAQUET)
    assert not [nom for nom in dir(paquet) if "traduction" in nom.lower()]


def test_le_sdk_est_bien_installe():
    """Contre-épreuve : sans elle, les tests ci-dessus passeraient sur un SDK absent."""
    assert modules_anthropic_charges_par("anthropic") != []
