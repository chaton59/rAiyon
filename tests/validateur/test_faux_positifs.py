"""Six sorties **légitimes**, qui doivent passer sans un seul grief. Aussi important.

C'est un validateur qui crie sur du français correct qui tue le mécanisme, pas un qui en
laisse passer. Un grief coûte un appel API et affiche au client une réponse plus sèche :
un faux positif se paie donc deux fois, en argent et en qualité perçue.

Chaque cas ci-dessous est un comportement que le prompt système **réclame** : citer un
produit d'un tour précédent, annoncer une fourchette, écrire un prix à la française.
S'il ne passait pas, ce serait le validateur qu'il faudrait corriger, pas le modèle.
"""

import pytest
from contexte_de_test import contexte_apres_sondage, contexte_complet

from raiyon.validateur.validateur import valider


@pytest.fixture
def contexte():
    return contexte_complet()


def sans_grief(texte, contexte) -> bool:
    verdict = valider(texte, contexte)
    assert verdict.valide, f"griefs inattendus : {[g.en_ligne() for g in verdict.griefs]}"
    return True


def test_une_recommandation_de_trois_produits_exacte_passe(contexte):
    """Le cas nominal, tel que la section 11 du prompt système le demande.

    Noms verbatim, `id`, prix chiffre pour chiffre, specs du catalogue, et le produit
    hors budget présenté avec son écart exact. Si celui-ci échoue, rien ne marche.
    """
    texte = (
        "Voici trois écrans qui tiennent dans vos 400 dollars.\n"
        "1) Samsung Odyssey G50A — monitor-0000000001 — 249.99 $\n"
        "   Un 27 pouces à 144 Hz, dalle IPS.\n"
        "2) AOC 24G2SP — monitor-0000000003 — 189.99 $\n"
        "   Plus petit, 24 pouces, toujours 144 Hz.\n"
        "3) Dell S2721DGF — monitor-0000000002 — 329.99 $\n"
        "Et juste au-dessus : le LG 27GP850-B à 417.14 $, soit 17.14 $ de plus.\n"
    )

    assert sans_grief(texte, contexte)


def test_un_produit_du_tour_trois_cite_au_tour_six_passe(contexte):
    """**Le contexte est cumulatif sur la session, pas sur le tour** (arbitrage B).

    « Je prends le premier » arrive six messages après la recherche. Un contexte remis à
    zéro à chaque tour rejetterait la moitié des conversations réelles — et le modèle
    serait puni pour avoir de la mémoire.
    """
    texte = "Alors je pars sur le Samsung Odyssey G50A, à 249,99 $. Bon choix."

    assert sans_grief(texte, contexte)


def test_une_fourchette_de_sondage_sans_produit_nomme_passe():
    """« entre 108 $ et 400 $ » après un sondage : bornes exactes, aucun produit nommé.

    C'est la section 4 du prompt système appliquée correctement — une fourchette décrit
    un ensemble — et c'est le **pendant exact** du piège nº6 : les mêmes chiffres,
    acceptés parce qu'ils ne sont attribués à personne.
    """
    texte = "Je vous propose trois modèles entre 108 $ et 400 $, tous à 144 Hz au moins."

    assert sans_grief(texte, contexte_apres_sondage())


def test_une_phrase_sans_aucun_chiffre_passe(contexte):
    """Rien à vérifier n'est pas une raison de lever : le validateur ne s'invente pas de griefs."""
    texte = "Dites-moi plutôt si c'est pour jouer ou pour de la bureautique."

    assert sans_grief(texte, contexte)


def test_un_entier_nu_passe(contexte):
    """**L'exemption assumée du §7**, et elle est délibérée.

    Sans elle, « je vous propose trois modèles » lèverait un grief. La conséquence est
    réelle et écrite : « 32 candidats » pourrait être faux sans que rien ne le voie.
    """
    texte = "Je vous propose trois modèles, sur 32 candidats."

    assert sans_grief(texte, contexte)


def test_un_prix_ecrit_a_la_francaise_passe(contexte):
    """`417,14 $` quand le `tool_result` porte `"417.14"`.

    Le modèle écrit en français, `en_tool_result()` sérialise en anglais : la
    normalisation tient les deux séparateurs, sans quoi le validateur crierait sur
    **toutes** les réponses correctes du produit.
    """
    texte = "Le LG 27GP850-B est à 417,14 $, soit 17,14 $ au-dessus de votre budget."

    assert sans_grief(texte, contexte)
