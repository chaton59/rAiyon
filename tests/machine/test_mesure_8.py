"""La mesure nº8 : le compte de tests de conduite du dialogue, et il ne dérive pas.

**Un chiffre publié dans trois fichiers finit par n'être corrigé que dans un.** Le dépôt a
déjà payé ce motif deux fois — `erreurs.py`, puis `SYSTEME_PAR_DEFAUT` contre
`Settings.prompt_systeme`, où il annonçait `systeme.v2` et servait `systeme.v1` — et
`test_env_example.py` existe pour la même raison. Ces tests-ci sont la troisième
application du même remède : le nombre est **dérivé de la suite**, et les documents qui le
publient sont relus contre lui.

Ajouter un test de conduite sans mettre les documents à jour fait donc échouer `make
check`, en disant le nombre attendu.

⚠️ **Ce module ne compte pas dans la mesure nº8.** Il ne vérifie aucune règle de conduite :
il vérifie un chiffre. Aucune de ses fonctions ne porte de ligne `Règle — `, et c'est ce
qui les exclut du compte.
"""

import re
from pathlib import Path

import pytest
import test_conduite

from raiyon.machine.decision import RESERVE_MESURE_8

RACINE = Path(__file__).resolve().parents[2]
"""Résolu depuis ce fichier, jamais depuis le `cwd` : un test qui ne trouve sa cible que
lancé du bon répertoire finit par être ignoré en silence."""

MARQUEUR = "Règle — "
"""Le préfixe qui fait d'un test un test de **conduite**. Voir la docstring de
`test_conduite.py` : un test écrit depuis l'implémentation plutôt que depuis une règle
vérifie une tautologie, et il gonflerait le chiffre sans rien prouver."""

PUBLICATION = re.compile(r"\*\*(\d+) tests de conduite du dialogue\*\*")
"""La forme sous laquelle les documents publient le nombre. Elle est cherchée, pas
supposée : un document qui ne le publie plus fait échouer le test qui le lit."""

DOCUMENTS = ("PROJET.md", "README.md")
"""Les deux fichiers où le chiffre paraît. `docs/prompts/etape-15.md` porte la
spécification du jalon 3, pas la mesure."""

EXTRAIT_DE_RESERVE = "pas que la conduite est bonne"
"""Un fragment de `RESERVE_MESURE_8`, suffisant pour constater que la réserve **voyage
avec le chiffre**. La chercher en entier ferait échouer le test sur un retour à la ligne
placé autrement, ce qui n'est pas ce qu'on protège."""


def conduites() -> list[str]:
    """Les tests de `test_conduite.py` qui portent une référence de règle."""
    return sorted(
        nom
        for nom, objet in vars(test_conduite).items()
        if nom.startswith("test_") and callable(objet) and MARQUEUR in (objet.__doc__ or "")
    )


def fonctions_de_test() -> list[str]:
    return sorted(
        nom
        for nom, objet in vars(test_conduite).items()
        if nom.startswith("test_") and callable(objet)
    )


def test_chaque_test_de_conduite_nomme_la_regle_quil_verifie():
    """Sans référence, un test n'est pas un test de conduite : il peut avoir été écrit en
    lisant l'implémentation, auquel cas il vérifie que le code fait ce que le code fait.

    C'est la circularité qui a fait refuser, à l'étape 12, d'ajouter des scénarios d'éval
    écrits depuis §3.6. Le marqueur est le seul garde-fou possible ici — il ne prouve pas
    que la règle citée est la bonne, il garantit qu'il y en a une à relire.
    """
    sans_reference = sorted(set(fonctions_de_test()) - set(conduites()))

    assert sans_reference == [], (
        "ces tests de `test_conduite.py` ne citent aucune règle — leur ajouter une ligne "
        f"« {MARQUEUR}… », ou les déplacer hors de ce module : {sans_reference}"
    )


@pytest.mark.parametrize("document", DOCUMENTS)
def test_le_nombre_publie_est_celui_que_la_suite_compte(document: str):
    """Le chiffre des documents est relu contre la suite, jamais l'inverse."""
    texte = (RACINE / document).read_text(encoding="utf-8")
    publies = {int(nombre) for nombre in PUBLICATION.findall(texte)}
    compte = len(conduites())

    assert publies, f"{document} ne publie plus la mesure nº8 sous la forme attendue."
    assert publies == {compte}, (
        f"{document} annonce {sorted(publies)} test(s) de conduite, la suite en compte "
        f"{compte}. Mettre le document à jour — le chiffre se dérive, il ne se rédige pas."
    )


@pytest.mark.parametrize("document", DOCUMENTS)
def test_la_reserve_voyage_avec_le_chiffre(document: str):
    """⚠️ **Sans elle, « N contre 0 » est un double standard**, et c'est la seule façon de
    rater une mesure par ailleurs imparable.

    L'étape 13 se l'est reproché sur la métrique nº3 : publier l'écart qui arrange sans
    l'étendue qui le relativise. La réserve dit ce que ces N tests ne prouvent pas — que la
    conduite soit **bonne** —, et elle doit être là où le chiffre est lu, pas dans un
    fichier annexe qu'on ne rouvre pas.
    """
    texte = (RACINE / document).read_text(encoding="utf-8")

    assert EXTRAIT_DE_RESERVE in texte, (
        f"{document} publie la mesure nº8 sans sa réserve. Elle est écrite une seule fois, "
        "dans `raiyon.machine.decision.RESERVE_MESURE_8`."
    )


def test_la_reserve_du_code_et_celle_des_documents_disent_la_meme_chose():
    """La constante est la source ; les documents la citent. Si elle est reformulée sans
    que les documents suivent, ce test le dit — c'est le motif d'`.env.example`."""
    assert EXTRAIT_DE_RESERVE in RESERVE_MESURE_8
