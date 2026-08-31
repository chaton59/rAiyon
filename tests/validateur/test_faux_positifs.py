"""Onze sorties **légitimes**, qui doivent passer sans un seul grief. Aussi important.

C'est un validateur qui crie sur du français correct qui tue le mécanisme, pas un qui en
laisse passer. Un grief coûte un appel API et affiche au client une réponse plus sèche :
un faux positif se paie donc deux fois, en argent et en qualité perçue.

Chaque cas ci-dessous est un comportement que le prompt système **réclame** : citer un
produit d'un tour précédent, annoncer une fourchette, écrire un prix à la française.
S'il ne passait pas, ce serait le validateur qu'il faudrait corriger, pas le modèle.
"""

import pytest
from contexte_de_test import SCEPTRE, contexte_apres_sondage, contexte_complet

from raiyon.validateur.validateur import valider


@pytest.fixture
def contexte():
    return contexte_complet()


@pytest.fixture
def contexte_du_sondage():
    return contexte_apres_sondage()


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
        "2) Sceptre C248W-1920RN — monitor-0000000007 — 189.99 $\n"
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


# --------------------------------------------------------------------------- #
# 7 à 9 — ce que le correctif de l'étape 9 devait rendre possible
# --------------------------------------------------------------------------- #


def test_une_question_qui_nomme_un_produit_reel_avec_son_prix_exact_passe(contexte):
    """Valider les questions ne doit pas rendre les questions impossibles.

    C'est la contrepartie du piège nº10 : le même chemin, la même règle, et une
    formulation correcte qui doit passer. Sans ce test, un validateur trop strict sur les
    questions se paierait sur **chaque tour** d'une conversation, pas seulement sur les
    recommandations.
    """
    question = (
        "Le Samsung Odyssey G50A à 249,99 $ vous irait, "
        "ou vous préférez que je regarde plus grand ?"
    )

    assert sans_grief(question, contexte)


def test_le_budget_du_client_est_admis_dans_une_phrase_qui_nomme_un_produit(contexte):
    """**Le correctif nº2**, et il ferme un faux positif que le rapport de l'étape signalait.

    « Le X à 249,99 $ rentre dans vos 400 $ » est la formulation naturelle d'un vendeur,
    et elle le devient d'autant plus depuis que les questions sont validées. Le budget
    n'est pas un fait du catalogue : c'est une **parole du client**, entrée par
    `record_criteria` et rendue dans son `tool_result`.

    ⚠️ Le pendant est le piège nº6, qui doit continuer d'échouer : une borne de sondage
    n'est pas un montant attribuable, et elle reste interdite ici.
    """
    texte = "Le Samsung Odyssey G50A à 249,99 $ rentre dans vos 400 $."

    assert sans_grief(texte, contexte)


def test_un_intervalle_aux_deux_bornes_exactes_passe(contexte_du_sondage):
    """La propagation d'unité doit **valider** autant qu'elle refuse.

    Le piège nº12 attrape « entre 65 et 400 dollars » quand la borne vaut 64,98. Un test
    qui ne montrerait que le refus laisserait passer une propagation qui casse les cas
    justes — et 108 comme 400 sont ici des agrégats fournis, exacts tous les deux.
    """
    texte = "Je vous propose trois modèles entre 108 et 400 dollars."

    assert sans_grief(texte, contexte_du_sondage)


def test_un_nom_de_produit_qui_contient_une_unite_passe(contexte):
    """**Trouvé en conversation réelle, et il coûtait un repli sur une réponse juste.**

    Le catalogue contient `Sceptre C248W-1920RN`. Cité verbatim comme §3.4ter l'exige,
    « 248W » se lit 248 watts, et la règle 5 refusait une recommandation exacte. Un nom
    est un **identifiant**, pas une affirmation de caractéristique : il sort du texte
    avant lecture des unités.
    """
    texte = f"Le {SCEPTRE.nom} — {SCEPTRE.id} — {SCEPTRE.prix_usd} $ est le plus abordable."

    assert sans_grief(texte, contexte)


def test_decrire_le_catalogue_apres_un_sondage_passe(contexte_du_sondage):
    """**Trouvé en conversation réelle, et il a coûté deux replis sur des messages exacts.**

    « les fréquences vont de 144 à 165 Hz » est vrai : les deux valeurs sont dans la
    distribution rendue par `probe_catalog`, et dire ce que contient le sous-catalogue
    est précisément ce pour quoi cet outil existe (§3.7). Le validateur les refusait
    parce qu'elles ne sont attribuables à aucun produit — ce qui est vrai, et sans
    rapport avec une phrase qui n'en nomme aucun.

    La règle 5 range donc les valeurs par provenance, comme la règle 2 le fait des prix.
    Le pendant est le piège nº9, qui doit continuer d'échouer.
    """
    texte = "Sur cette gamme, les fréquences vont de 144 à 165 Hz."

    assert sans_grief(texte, contexte_du_sondage)
