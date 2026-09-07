"""`systeme.v4` est `systeme.v3` **moins la 8 bis**, et c'est vérifié section par section.

C'est le même geste que `tests/machine/test_prompt_derive.py`, appliqué à une autre
relation : là-bas une **soustraction** (la machine reprend au prompt ce que le code
décide), ici une **substitution unique** (une seule section est réécrite).

### La propriété, et ce qu'elle achète

> Toute section de `systeme.v4.md` autre que la 8 bis est identique à celle de
> `systeme.v3.md`, **au caractère près**, et les deux fichiers portent exactement les
> mêmes titres de section.

Elle achète l'**attribution**. La campagne qui comparera v3 et v4 mesurera une différence
de comportement ; sans cette garantie, rien ne permettrait de l'imputer à la 8 bis plutôt
qu'à une virgule déplacée ailleurs pendant la copie. C'est la condition que l'étape 13 pose
à toute comparaison de prompts — « déplacer **une** section et mesurer l'effet » — et une
condition qu'on croit tenir n'en est pas une.

⚠️ **Le test ne juge pas la rédaction de la 8 bis**, et il ne le peut pas : elle est
justement ce qui change. Il borne le reste, ce qui est exactement ce dont la mesure a
besoin.

### ⚠️ Ce module ne compte pas dans la mesure nº8

Il ne vérifie aucune règle de conduite du dialogue : il vérifie une relation entre deux
fichiers. Aucune de ses fonctions ne porte de ligne `Règle — `, et c'est ce qui les exclut
du compte de `test_mesure_8.py`.
"""

import re

import pytest

from raiyon.agent.prompts import charger

SOURCE = "systeme.v3"
DERIVE = "systeme.v4"

SECTION_REECRITE = "## 8 bis. Les avis du web : des opinions, jamais des faits"
"""La seule section que v4 réécrit. **Son titre est inchangé**, et c'est voulu : un titre
qui bouge en même temps que le corps rendrait le `diff` illisible pour rien."""

MOTIF_DE_SECTION = re.compile(r"^(## .*)$", re.MULTILINE)


def sections(nom: str) -> dict[str, str]:
    """Les sections d'un prompt, `titre -> corps`. Le préambule n'en est pas une.

    Le découpage se fait sur le titre de niveau 2, qui est la granularité de l'étape 13 :
    c'est l'unité qu'une campagne déplace, donc l'unité qu'un test d'attribution doit voir.
    """
    morceaux = MOTIF_DE_SECTION.split(charger(nom))
    trouvees: dict[str, str] = {}
    titre: str | None = None
    for morceau in morceaux:
        if morceau.startswith("## "):
            titre = morceau.strip()
            trouvees[titre] = ""
        elif titre is not None:
            trouvees[titre] += morceau
    return trouvees


def test_les_deux_versions_portent_les_memes_sections():
    """Aucune section ajoutée, aucune retirée. **Le préalable de toute comparaison.**"""
    assert sections(SOURCE).keys() == sections(DERIVE).keys()


def test_la_section_reecrite_existe_dans_les_deux():
    """Sinon les deux tests suivants passeraient sur un fichier qui ne dit plus rien."""
    assert SECTION_REECRITE in sections(SOURCE)
    assert SECTION_REECRITE in sections(DERIVE)


@pytest.mark.parametrize("titre", [t for t in sections(SOURCE) if t != SECTION_REECRITE])
def test_toute_section_autre_que_la_8_bis_est_identique_au_caractere_pres(titre):
    """Paramétré par section : un échec **nomme** celle qui a bougé.

    Un `assert` global sur les treize dirait « quelque chose a changé » et laisserait
    chercher quoi — or c'est précisément le travail que ce module existe pour éviter.
    """
    assert sections(SOURCE)[titre] == sections(DERIVE)[titre]


def test_la_8_bis_a_bien_change():
    """**Le test qui sait rougir.**

    Sans lui, une copie conforme de v3 en `systeme.v4.md` passerait les trois autres avec
    un vert franc, et la campagne comparerait un prompt avec lui-même. C'est le §9.3 du
    journal — « un test vert n'est pas une mesure tant qu'on n'a pas vérifié qu'il savait
    rougir » — écrit dans le sens positif : on constate aussi ce qui **doit** différer.
    """
    assert sections(SOURCE)[SECTION_REECRITE] != sections(DERIVE)[SECTION_REECRITE]
