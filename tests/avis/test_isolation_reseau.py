"""🔴 **Aucun module de `raiyon.avis` ne charge un client HTTP.** Le test de la décision.

### Ce qu'il garde, et pourquoi c'est une décision et non une précaution

L'étape 26 a tranché : **les mesures ne sortent jamais sur le réseau.** Les campagnes
d'éval lisent un cache pré-chargé de contenus fabriqués. Deux raisons, et elles sont
indépendantes — perdre l'une laisse l'autre debout :

1. `make eval` tourne aujourd'hui sans clé API et sans réseau. Un outil qui appellerait un
   fournisseur au rejeu dépenserait du crédit **et** rendrait un `tool_result` différent
   de celui de l'enregistrement, donc une cassette qui ne rejoue plus la même conversation.
2. Le §3(b) des conditions Brave interdit d'employer des résultats de recherche pour
   *« evaluate […] or benchmark »* un modèle. Une campagne qui interroge Brave pour
   comparer deux prompts est exactement cela.

### Pourquoi ce test-là, et ce qu'il ne prouve pas

Il constate qu'aucun module du paquet ne **charge** un client HTTP. C'est une preuve
d'import, pas une preuve d'exécution : elle ne dit rien de ce qu'une campagne fait à
l'exécution, et elle ne le prétend pas. Sa force est ailleurs — **elle échoue le jour où
quelqu'un écrit le fournisseur au mauvais endroit**, c'est-à-dire au moment où la décision
se perd, et pas trois semaines plus tard sur une facture.

⚠️ **Il porte sur le paquet entier parce qu'aujourd'hui aucun fournisseur n'existe.** Le
jour où l'un entre, il aura son module à lui, ce module sera classé ici comme
`raiyon.api.app` l'est pour FastAPI, et la garantie deviendra « tout le paquet sauf lui » —
la même forme que `test_isolation_api`. Ne pas anticiper ce classement est volontaire : un
classement écrit pour un module qui n'existe pas décrit une architecture imaginaire.

La contre-épreuve est en bas. Sans elle, tout passerait sur une machine où `httpx` n'est
pas installé, ce qui est le mode d'échec réel de ce genre de test.
"""

import importlib.util

import pytest

from isolation_sdk import modules_charges_par, modules_du_paquet

PAQUET = "raiyon.avis"

CLIENTS_HTTP = frozenset({"httpx", "requests", "urllib3", "aiohttp", "http"})
"""Les paquets par lesquels une sortie réseau passerait.

`http` — le module de la bibliothèque standard — est dans la liste : `http.client` est le
chemin le plus court pour sortir sans dépendance, donc celui qu'on prendrait sans y penser.
`urllib3` y est parce que `requests` et `httpx` s'appuient dessus et qu'on peut l'appeler
seul."""


@pytest.mark.parametrize("module", modules_du_paquet(PAQUET))
def test_aucun_module_du_paquet_ne_charge_un_client_http(module: str):
    """La décision de l'étape 26, rendue exécutable.

    Le message de pytest nomme le module coupable et le client chargé : c'est ce que
    `modules_charges_par` achète en rendant une liste plutôt qu'un booléen.
    """
    assert modules_charges_par(module, CLIENTS_HTTP) == [], (
        f"{module} charge un client HTTP. Les mesures ne sortent jamais sur le réseau — "
        "voir la docstring de ce fichier pour les deux raisons."
    )


def test_le_chargement_du_seed_ne_charge_pas_de_client_http():
    """Le chemin de `make seed` en entier, puisque c'est lui qui remplit le cache.

    `raiyon.avis.chargement` est déjà couvert par le test paramétré ci-dessus ; celui-ci
    prend le module qui l'appelle, où la régression serait tout aussi silencieuse.
    """
    assert modules_charges_par("raiyon.catalogue.chargement", CLIENTS_HTTP) == []


def test_contre_epreuve_le_dispositif_sait_voir_un_client_http():
    """Sans elle, les tests du dessus passeraient sur une machine sans client HTTP installé.

    On importe un module de la bibliothèque standard qui tire `http` — donc toujours
    présent, quel que soit l'état des dépendances du projet.
    """
    assert modules_charges_par("http.client", CLIENTS_HTTP) != []


def test_le_client_http_est_bien_installe_donc_la_garantie_porte_sur_les_imports():
    """⚠️ **Ce qu'on aurait voulu affirmer, et qui est faux — vérifié plutôt que supposé.**

    L'idée qui vient d'abord est plus forte que celle qui est implémentée : « httpx n'est
    pas une dépendance de ce projet, donc aucune sortie réseau n'est possible du tout ».
    Elle est **fausse**, et la mesure le dit — `httpx` est installé, tiré par le SDK
    Anthropic dont il est une dépendance transitive. Trois lignes suffiraient à sortir sur
    le réseau depuis n'importe quel module.

    La garantie de ce fichier est donc bien celle qu'elle annonce, et pas plus : **aucun
    module de `raiyon.avis` n'importe de client HTTP.** Ce test est là pour que la phrase
    plus forte ne se réinstalle pas dans la tête d'un relecteur — si un jour `httpx`
    disparaît de l'arbre de dépendances, il tombe, et c'est le bon moment pour resserrer.
    """
    assert importlib.util.find_spec("httpx") is not None, (
        "httpx a disparu des dépendances — la garantie peut devenir « aucune sortie "
        "réseau n'est possible » au lieu de « aucun import ». Relire ce fichier."
    )
