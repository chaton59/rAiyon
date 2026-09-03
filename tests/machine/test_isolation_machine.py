"""`raiyon.machine` ne charge ni le SDK, ni le serveur, ni la boucle d'agent.

**Sixième paquet à porter la garantie**, après `raiyon.catalogue`, `raiyon.tools`,
`raiyon.validateur`, `raiyon.api` et `raiyon.eval` — et le premier à en porter une de plus.

### Ce que la garantie achète ici, et c'est la mesure nº8

`decider()` est pure : elle ne voit que l'état et le dernier résultat d'outil, jamais de
prose. Les tests de conduite du dialogue tournent donc **dans `make check`, sans clé, sans
base, sans conteneur, en millisecondes**. C'est ce que §3.6 disait perdu avec l'agent — « il
n'y a plus de fonction de décision pure à assertionner » — et c'est ce que ce paquet rend
de nouveau vrai.

### La garantie supplémentaire : `raiyon.agent`

Les cinq paquets précédents interdisent `anthropic`, `fastapi` et `starlette`. Celui-ci
interdit en plus **`raiyon.agent`**, et la raison n'est pas l'hygiène : la boucle d'agent
est l'orchestration que la machine met en concurrence. Un import — même « juste pour
réutiliser un type d'événement » — ferait dépendre la décision de ce qu'elle est censée
remplacer, et la campagne de l'étape 15 comparerait deux choses dont l'une contient
l'autre.

Le mécanisme d'origine ne sait pas exprimer cette garantie : il découpe sur le premier
segment du nom, ce qui donnerait `raiyon` — chargé par tout le monde. D'où
`modules_charges_sous()`, qui compare des **préfixes pointés**.

⚠️ **Elle ne porte pas sur `raiyon.db`, et c'est la sixième fois que le dépôt l'écrit.**
`decision.py` est typé sur `EtatSession` et `ResultatOutil`, donc sur `raiyon.matching`,
donc sur `raiyon.db.models`. La propriété qui compte n'est pas « rien n'importe la base »
mais **« rien ne se connecte »** — le temps d'exécution de `tests/machine/` le constate à
chaque `make check`.
"""

import pytest

from isolation_sdk import modules_charges_par, modules_charges_sous, modules_du_paquet

PAQUET = "raiyon.machine"

MODULES_PURS = ("raiyon.machine.decision",)
"""La fonction de décision. Ni SDK, ni serveur, ni boucle d'agent."""

MODULES_LIBRES = ("raiyon.machine",)
"""Le paquet lui-même, qui ne porte qu'une docstring."""

INTERDITS = frozenset({"anthropic", "fastapi", "starlette"})

INTERDITS_INTERNES = frozenset({"raiyon.agent"})
"""L'orchestration que la machine met en concurrence. Voir la docstring du module."""


@pytest.mark.parametrize("module", MODULES_PURS)
def test_les_modules_purs_ne_chargent_ni_le_sdk_ni_le_serveur(module: str):
    """La propriété de l'étape : la décision se teste sans rien démarrer."""
    assert modules_charges_par(module, INTERDITS) == []


@pytest.mark.parametrize("module", MODULES_PURS)
def test_la_decision_ignore_la_boucle_dagent(module: str):
    """La garantie propre à ce paquet : comparer deux orchestrations suppose qu'aucune des
    deux ne contienne l'autre."""
    assert modules_charges_sous(module, INTERDITS_INTERNES) == []


def test_le_classement_couvre_tous_les_modules_du_paquet():
    """Il ne vérifie aucun import : il vérifie qu'aucun module n'a échappé à la question
    « celui-là, est-il pur ? ». Un module ajouté sans réponse fait échouer la suite, avec
    son nom dans le message — vérifié en ajoutant un module vide, puis retiré."""
    classes = set(MODULES_PURS) | set(MODULES_LIBRES)
    trouves = set(modules_du_paquet(PAQUET))
    assert trouves == classes, (
        "un module de raiyon.machine n'est pas classé — dire s'il est pur (donc testé "
        f"ici) ou non : {sorted(trouves ^ classes)}"
    )


def test_la_boucle_dagent_charge_bien_ce_quon_lui_interdit_ici():
    """Contre-épreuve. Sans elle, le test du dessus passerait sur un `INTERDITS_INTERNES`
    mal orthographié — qui est le mode d'échec réel de ce dispositif."""
    assert modules_charges_sous("raiyon.agent.boucle", INTERDITS_INTERNES) != []
