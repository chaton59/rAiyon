"""`systeme.machine.v1` est une **soustraction pure** de `systeme.v2`, et c'est vérifié.

La règle de dérivation tient en une phrase : *une section qui dit **qui parle quand** part
dans le code ; une section qui dit **ce qui peut être écrit** reste au prompt.* Elle est
écrite, avec son verdict section par section, dans `docs/prompts/etape-15.md`.

Ce module la transforme en garantie. **Sans lui, « le diff est la spécification » serait
une intention** — et une intention qui se périme à la première retouche.

### La propriété, et pourquoi c'est une sous-séquence et non une inclusion

> Chaque ligne de `systeme.machine.v1.md` apparaît dans `systeme.v2.md`, **dans le même
> ordre**.

L'ordre est ce qui interdit de réarranger. Une inclusion d'ensemble laisserait déplacer §13
avant §4 sans que rien ne le dise, et le `diff` cesserait d'être lisible comme une liste de
suppressions.

**Aucune liste d'exceptions, aucune ligne autorisée en plus.** C'est ce qui fait qu'un
lecteur peut taper `diff prompts/systeme.v2.md prompts/systeme.machine.v1.md` et obtenir la
réponse **exhaustive** à « qu'est-ce que l'orchestration a repris au modèle ? », sans avoir
à croire un commentaire.

### ⚠️ Ce module ne compte pas dans la mesure nº8

Il ne vérifie aucune règle de conduite du dialogue : il vérifie une relation entre deux
fichiers. Aucune de ses fonctions ne porte de ligne `Règle — `, et c'est ce qui les exclut
du compte de `test_mesure_8.py`.
"""

import pytest

from raiyon.agent.prompts import charger

SOURCE = "systeme.v2"
DERIVE = "systeme.machine.v1"

RETIREES = (5, 6, 8)
"""Les sections que `decider()` a reprises — voir `docs/prompts/etape-15.md`."""

CONSERVEES = (1, 2, 3, 4, 7, 9, 10, 11, 12, 13, 14)
"""Les autres, **avec leurs numéros d'origine**. Les trous sont le message."""


def lignes(nom: str) -> list[str]:
    return charger(nom).splitlines()


def premiere_ligne_hors_sequence(derive: list[str], source: list[str]) -> str | None:
    """La première ligne du dérivé que la source n'offre pas dans l'ordre, ou `None`.

    Un balayage à deux curseurs : c'est la définition même d'une sous-séquence, et il rend
    la ligne fautive plutôt qu'un booléen — un test qui dit « ce n'est pas une
    sous-séquence » sans dire où oblige à refaire le travail à la main.
    """
    curseur = 0
    for ligne in derive:
        while curseur < len(source) and source[curseur] != ligne:
            curseur += 1
        if curseur == len(source):
            return ligne
        curseur += 1
    return None


def test_le_derive_est_une_sous_sequence_de_la_source():
    """**La garantie du jalon.** Une ligne ajoutée, modifiée ou déplacée la casse.

    Elle est plus forte que « le diff ne montre que des suppressions » : elle vaut encore
    quand `diff` choisit un autre alignement, parce qu'elle ne parle pas de hunks mais de
    l'ordre des lignes elles-mêmes.
    """
    fautive = premiere_ligne_hors_sequence(lignes(DERIVE), lignes(SOURCE))

    assert fautive is None, (
        f"{DERIVE}.md n'est plus une soustraction de {SOURCE}.md — première ligne qui ne "
        f"s'y retrouve pas dans l'ordre : {fautive!r}"
    )


def test_le_derive_est_strictement_plus_court():
    """Une soustraction qui ne retire rien serait une copie, et le fichier n'aurait pas
    lieu d'exister — la machine tournerait sur `systeme.v2`, comme au jalon 2."""
    assert len(lignes(DERIVE)) < len(lignes(SOURCE))


@pytest.mark.parametrize("numero", CONSERVEES)
def test_les_sections_conservees_gardent_leur_numero_dorigine(numero: int):
    """⚠️ **Le trou est le message.** Une renumérotation donnerait deux prompts dont les
    sections 2 se ressemblent sans être les mêmes, et « la section 6 disait… » deviendrait
    ambigu entre les deux orchestrations pour toujours."""
    assert f"\n## {numero}." in charger(DERIVE)


@pytest.mark.parametrize("numero", RETIREES)
def test_les_sections_de_conduite_ont_disparu(numero: int):
    """Elles sont dans `decider()`, et le prompt ne doit plus les redire : deux rédactions
    d'une même règle finissent par en dire deux choses."""
    assert f"\n## {numero}." not in charger(DERIVE)
    assert f"\n## {numero}." in charger(SOURCE), "la section a disparu de la source aussi"


def test_les_deux_outils_que_la_machine_nexpose_pas_ont_disparu_avec_elles():
    """Conséquence non recherchée de la soustraction, et bienvenue : `ask_clarification` et
    `suggest_next_question` n'étaient nommés **que** dans §5 et §6.

    La machine n'expose ni l'un ni l'autre — `decider()` décide de la question, le modèle
    l'écrit —, et un prompt qui les nommerait inviterait à appeler des outils absents. Ce
    n'est pas ce qui a décidé du retrait de §5 et §6 ; c'est ce que le retrait donne en
    plus, et le constater ici l'empêche d'être défait par inadvertance.
    """
    texte = charger(DERIVE)

    assert "ask_clarification" not in texte
    assert "suggest_next_question" not in texte
    assert "record_criteria" in texte, "l'extraction, elle, l'expose"
    assert "search_products" in texte and "probe_catalog" in texte


def test_aucune_section_conservee_ne_renvoie_a_une_section_retiree():
    """La règle « une suppression qui laisse une référence pendante annule la suppression »
    ne s'est pas déclenchée, et c'est une **propriété du texte**, pas une chance.

    `systeme.v2.md` ne porte que deux renvois internes — « la section 2 » dans §12 et
    « la section 12 » dans §13 — et les deux visent des sections conservées.
    """
    texte = charger(DERIVE)

    for numero in RETIREES:
        assert f"la section {numero}" not in texte
        assert f"section {numero} " not in texte.replace(f"## {numero}. ", "")


def test_le_derive_compte_onze_sections_et_sa_premiere_ligne_le_dit_par_accident():
    """⚠️ **Un accident, pas une intention, et il faut l'écrire comme tel.**

    La troisième ligne de `systeme.v2.md` annonce « Onze sections » : elle date de v1, v2
    en compte quatorze, et personne ne l'a corrigée. La soustraction pure la recopie telle
    quelle — et comme elle retire exactement trois sections, **elle redevient exacte pour la
    machine**, tout en restant fausse pour l'agent.

    La corriger dans `systeme.v2.md` coûterait la campagne v2 entière : 36 cassettes portent
    son `prompt_empreinte`, et un seul caractère les périme toutes. Une coquille vaut zéro,
    191 appels valent le prix qu'ils ont coûté.
    """
    texte = charger(DERIVE)

    assert texte.count("\n## ") == 11 == len(CONSERVEES)
    assert "Onze sections" in texte
    assert charger(SOURCE).count("\n## ") == 14, (
        "si la source cesse d'en compter quatorze, l'accident n'en est plus un"
    )
