"""Les modules purs de `raiyon.api` ne chargent ni le SDK Anthropic, ni FastAPI.

**Quatrième paquet à porter cette garantie**, après `raiyon.catalogue`, `raiyon.tools` et
`raiyon.validateur` — et le premier où elle ne peut pas porter sur le paquet entier :
`app.py` importe FastAPI, c'est sa raison d'être, et il construit le client Anthropic au
démarrage.

Le dispositif change donc de forme, et **il ne perd pas la propriété qui compte**. La
découverte sur disque reste : elle sert ici à interdire qu'un module nouveau échappe au
classement. Un `serialisation_v2.py` ajouté demain fera échouer
`test_le_classement_couvre_tous_les_modules_du_paquet` tant que personne n'aura dit s'il
est pur — c'est-à-dire tant que personne n'aura pris la décision. Une liste écrite sans ce
garde-fou aurait simplement ignoré le nouveau venu, en silence.

### Ce que la garantie achète

`serialisation.py` porte le contrat de fil, `prose.py` la relecture de la prose. Les deux
sont testés en entier dans `make check`, **sans serveur, sans base et sans clé API** — 40
tests en moins d'une seconde. C'est ce qui permet d'arrêter le contrat avant d'écrire une
route, ce que la méthode de l'étape demandait, et c'est ce qui fera que l'étape 11 pourra
le relire sans rien démarrer.

⚠️ **La garantie porte sur `anthropic` et `fastapi`, pas sur SQLAlchemy.** Les événements
du domaine sont typés sur `ResultatMatching`, donc sur `matching.depot`, donc sur
`sqlalchemy` — exactement comme `raiyon.tools` depuis l'étape 7 et `raiyon.validateur`
depuis l'étape 9. La propriété n'est pas « rien n'importe SQLAlchemy » mais **« rien ne se
connecte »**, et c'est ce que le temps d'exécution de `make check` constate.
"""

import pytest

from isolation_sdk import modules_charges_par, modules_du_paquet

PAQUET = "raiyon.api"

MODULES_PURS = ("raiyon.api.serialisation", "raiyon.api.prose")
"""Traduisent, ne parlent à personne. C'est sur eux que porte la garantie."""

MODULES_SERVEUR = ("raiyon.api.app",)
"""Ils *doivent* importer FastAPI. Les y autoriser explicitement est une décision, pas un
oubli — et le test de couverture ci-dessous empêche qu'elle en devienne un."""

MODULES_BASE = ("raiyon.api.verrou",)
"""SQLAlchemy, et rien d'autre : le verrou est une phrase de SQL, pas une route."""

MODULES_LIBRES = ("raiyon.api", "raiyon.api.schemas")
"""Le paquet lui-même (vide) et les modèles Pydantic d'entrée/sortie. Rien à garantir :
ils n'importent déjà que Pydantic, et aucun invariant ne repose là-dessus."""

INTERDITS = frozenset({"anthropic", "fastapi", "starlette"})
"""`starlette` autant que `fastapi` : `Response` et `StreamingResponse` s'importent des
deux, et n'interdire que le second laisserait la porte ouverte."""


@pytest.mark.parametrize("module", MODULES_PURS)
def test_les_modules_purs_ne_chargent_ni_le_sdk_ni_le_serveur(module: str):
    """La propriété de l'étape : le contrat de fil se relit sans rien démarrer."""
    assert modules_charges_par(module, INTERDITS) == []


def test_le_classement_couvre_tous_les_modules_du_paquet():
    """**C'est ce test qui remplace la découverte sur disque, et il fait le même travail.**

    Il ne vérifie aucun import : il vérifie qu'aucun module n'a échappé à la question
    « celui-là, est-il pur ? ». Un module ajouté sans réponse fait échouer la suite, avec
    son nom dans le message.
    """
    classes = set(MODULES_PURS) | set(MODULES_SERVEUR) | set(MODULES_BASE) | set(MODULES_LIBRES)

    trouves = set(modules_du_paquet(PAQUET))

    assert trouves == classes, (
        "un module de raiyon.api n'est pas classé — dire s'il est pur (donc testé "
        f"ici) ou non : {sorted(trouves ^ classes)}"
    )


def test_le_serveur_charge_bien_fastapi():
    """Contre-épreuve. Sans elle, le test du dessus passerait sur un FastAPI absent — ou
    sur un `INTERDITS` mal orthographié, ce qui est le mode d'échec réel."""
    assert modules_charges_par("raiyon.api.app", INTERDITS) != []
