"""Les modules purs de `raiyon.eval` ne chargent ni le SDK Anthropic, ni FastAPI.

**Cinquième paquet à porter cette garantie**, après `raiyon.catalogue`, `raiyon.tools`,
`raiyon.validateur` et `raiyon.api` — et le second, après l'API, où elle ne peut pas
porter sur le paquet entier : `client_simule.py` appelle Haiku, c'est sa raison d'être, et
`executeur.py` a besoin d'une `Session` SQLAlchemy.

Le dispositif est celui de `test_isolation_api.py`, et il garde la propriété qui compte :
la **découverte sur disque** interdit qu'un module nouveau échappe au classement. Un
`metriques_v2.py` ajouté demain fera échouer `test_le_classement_couvre_tous_les_modules`
tant que personne n'aura dit s'il est pur — c'est-à-dire tant que personne n'aura pris la
décision.

### Ce que la garantie achète ici, et c'est concret

**`make eval` tourne sans clé API.** Rejouer une cassette ne demande que le fichier et le
`Protocol` `ClientLLM` : c'est `eval/client.py` qui le rend vrai, et c'est pour cela qu'il
figure dans `MODULES_PURS` bien que le §5 n'ait nommé que les quatre autres. Un import de
`raiyon.agent.client_anthropic` glissé là — pour « réutiliser le repli `strict` », par
exemple — ferait réclamer une clé à une commande qui n'appelle rien, et le défaut ne se
verrait qu'en CI.

⚠️ **La garantie porte sur `anthropic`, `fastapi` et `starlette`, pas sur SQLAlchemy**, et
c'est la troisième fois que le dépôt l'écrit — après `raiyon.validateur` à l'étape 9 et
`raiyon.api` à l'étape 10. La raison est structurelle : `metriques.py` est typé sur
`Evenement`, donc sur `ResultatMatching`, donc sur `matching.depot`, donc sur
`sqlalchemy`. La renoncer serait renoncer à l'arbitrage E — les métriques se calculent
depuis les événements typés — et la remplacer par des chaînes de caractères pour gagner
un import serait un mauvais échange.

La propriété qui compte n'est pas « rien n'importe SQLAlchemy » mais **« rien ne se
connecte »**, et c'est ce que le temps d'exécution de `tests/eval/` constate à chaque
`make check`.
"""

import pytest

from isolation_sdk import modules_charges_par, modules_du_paquet

PAQUET = "raiyon.eval"

MODULES_PURS = (
    "raiyon.eval.cassette",
    "raiyon.eval.scenario",
    "raiyon.eval.metriques",
    "raiyon.eval.rapport",
    "raiyon.eval.client",
)
"""Les quatre du §5, plus `client` — voir la docstring : c'est lui qui fait que `make eval`
n'a pas besoin de clé."""

MODULES_SDK = ("raiyon.eval.client_simule",)
"""Il *doit* importer `anthropic` : il joue le client par Haiku. L'y autoriser
explicitement est une décision, pas un oubli."""

MODULES_BASE = ("raiyon.eval.executeur",)
"""SQLAlchemy, et rien d'autre : il consomme `session.tour()`, ce qui exige une `Session`
et le seed en base (arbitrage A)."""

MODULES_LIBRES = ("raiyon.eval",)
"""Le paquet lui-même, qui ne porte qu'une docstring."""

INTERDITS = frozenset({"anthropic", "fastapi", "starlette"})


@pytest.mark.parametrize("module", MODULES_PURS)
def test_les_modules_purs_ne_chargent_ni_le_sdk_ni_le_serveur(module: str):
    """La propriété de l'étape : mesurer et rejouer se font sans rien démarrer."""
    assert modules_charges_par(module, INTERDITS) == []


@pytest.mark.parametrize("module", MODULES_BASE)
def test_lexecuteur_non_plus_ne_charge_pas_le_sdk(module: str):
    """Il a besoin de la base, pas du modèle : le producteur de réponses lui est **passé**.

    C'est ce qui permet de lui donner un `ClientCassette` au rejeu et un
    `ClientEnregistreur` à l'enregistrement sans qu'une ligne ne bouge — le même geste que
    `dependency_overrides` à l'étape 10.
    """
    assert modules_charges_par(module, INTERDITS) == []


def test_le_classement_couvre_tous_les_modules_du_paquet():
    """Il ne vérifie aucun import : il vérifie qu'aucun module n'a échappé à la question
    « celui-là, est-il pur ? ». Un module ajouté sans réponse fait échouer la suite."""
    classes = set(MODULES_PURS) | set(MODULES_SDK) | set(MODULES_BASE) | set(MODULES_LIBRES)
    trouves = set(modules_du_paquet(PAQUET))
    assert trouves == classes, (
        "un module de raiyon.eval n'est pas classé — dire s'il est pur (donc testé "
        f"ici) ou non : {sorted(trouves ^ classes)}"
    )


def test_le_client_simule_charge_bien_le_sdk():
    """Contre-épreuve. Sans elle, tout passerait sur un `INTERDITS` mal orthographié —
    qui est le mode d'échec réel de ce dispositif."""
    assert modules_charges_par("raiyon.eval.client_simule", INTERDITS) != []
