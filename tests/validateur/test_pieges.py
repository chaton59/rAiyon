"""Douze sorties LLM **délibérément piégeuses**, toutes détectées. La porte de sortie.

Chaque test est nommé d'après **ce qu'il empêche**, pas d'après ce qu'il exerce. Le
décor est celui de `contexte_de_test.py` : une conversation d'écrans où le sondage a vu
plus large que la recherche, ce qui est le cas réel et non un montage.

Le plus important du fichier est `test_la_borne_dun_sondage_attribuee_a_un_produit...` :
**il échoue si le contexte a été aplati.** Un validateur qui vérifierait « tout nombre
cité apparaît quelque part dans un `tool_result` » laisserait passer un prix de sondage
collé à un modèle nommé — c'est l'oracle à prix du §7, et c'est la raison d'être de la
provenance (arbitrage B).
"""

import pytest
from contexte_de_test import contexte_complet

from raiyon.validateur.validateur import CodeGrief, valider


@pytest.fixture
def contexte():
    return contexte_complet()


def codes(texte, contexte) -> set[CodeGrief]:
    return {grief.code for grief in valider(texte, contexte).griefs}


# --------------------------------------------------------------------------- #
# 1 à 3 — le produit et son prix
# --------------------------------------------------------------------------- #


def test_un_prix_modifie_de_dix_dollars_est_detecte(contexte):
    """Le Samsung est à 249,99 $ ; 259,99 $ est plausible, et faux."""
    texte = "Le Samsung Odyssey G50A est à 259,99 $, c'est une très bonne affaire."

    assert CodeGrief.PRIX_ETRANGER_AU_PRODUIT in codes(texte, contexte)


def test_un_identifiant_inexistant_au_bon_format_est_detecte(contexte):
    """Le format ne prouve rien : seule l'appartenance au contexte fourni compte."""
    texte = "Je vous conseille le monitor-00000000ff."

    assert CodeGrief.ID_INCONNU in codes(texte, contexte)


def test_un_produit_entierement_invente_est_detecte_par_son_prix(contexte):
    """Nom plausible, prix plausible — et aucun outil ne l'a jamais rendu.

    ⚠️ **C'est le prix qui trahit, pas le nom.** Le validateur ne sait pas qu'« Acer
    Nitro XV272U » est un nom de produit : il constate qu'aucun montant fourni ne vaut
    279,99 $. La limite est réelle et elle est au §7 — un produit inventé dont le prix
    serait une borne de sondage, dans une phrase qui ne nomme aucun produit **connu**,
    passerait.
    """
    texte = "L'Acer Nitro XV272U est à 279,99 $ et fait très bien l'affaire."

    assert CodeGrief.MONTANT_NON_FOURNI in codes(texte, contexte)


# --------------------------------------------------------------------------- #
# 4 et 5 — la spec et le nom
# --------------------------------------------------------------------------- #


def test_une_spec_transformee_est_detectee(contexte):
    """180 Hz annoncés sur un écran qui en porte 144, et qu'aucun outil n'a rendus."""
    texte = "Le Dell S2721DGF monte à 180 Hz."

    assert CodeGrief.VALEUR_NON_FOURNIE in codes(texte, contexte)


def test_un_nom_francise_est_detecte(contexte):
    """« l'Odyssée de Samsung » pour `Samsung Odyssey G50A` (§3.4ter).

    Le nom est un identifiant que le client va retaper dans un moteur de recherche :
    le traduire le rend inutilisable, même quand tout le reste de la phrase est exact.
    """
    texte = "L'Odyssée de Samsung reste mon premier choix."

    assert CodeGrief.NOM_REECRIT in codes(texte, contexte)


# --------------------------------------------------------------------------- #
# 6 — le test le plus important de l'étape
# --------------------------------------------------------------------------- #


def test_la_borne_dun_sondage_attribuee_a_un_produit_est_detectee(contexte):
    """**Il échoue si le contexte a été aplati.**

    108,00 $ est la borne basse rendue par `probe_catalog` : c'est un fait *fourni*, mais
    il décrit un **ensemble** et n'est le prix d'aucun produit. Collé à un modèle nommé,
    il devient une affirmation que le code n'a jamais produite — l'oracle à prix du §7.

    Un ensemble plat de « tous les nombres fournis » contiendrait 108,00 et accepterait
    cette phrase. C'est pour cette seule raison que `ContexteFourni` sépare `prix` et
    `agregats`.
    """
    texte = "Le Samsung Odyssey G50A est à 108 $."

    griefs = valider(texte, contexte).griefs
    assert [grief.code for grief in griefs] == [CodeGrief.PRIX_ETRANGER_AU_PRODUIT]
    assert "fourchette de sondage" in griefs[0].correction


# --------------------------------------------------------------------------- #
# 7 et 8 — le budget, et le critère d'acceptation nº2
# --------------------------------------------------------------------------- #


def test_un_produit_hors_budget_cite_sans_son_ecart_est_detecte(contexte):
    """Critère nº2 : « budget jamais dépassé sans présentation explicite ».

    Le moteur garantit que le modèle a reçu `produits` et `au_dessus_du_budget`
    séparés ; cette règle garantit qu'il ne les a pas recollés en écrivant.
    """
    texte = "Je peux aussi vous montrer le LG 27GP850-B, à 417,14 $."

    assert CodeGrief.ECART_NON_DIT in codes(texte, contexte)


def test_un_ecart_faux_sur_un_produit_hors_budget_est_detecte(contexte):
    """« 15 $ de plus » au lieu de 17,14 : deux griefs, et les deux sont mérités.

    Le montant n'appartient pas au produit (règle 2) **et** l'écart exact n'a pas été
    dit (règle 4). Dire « il dépasse un peu » avec un chiffre faux est pire que ne rien
    dire : le client croit tenir un fait.
    """
    texte = "Le LG 27GP850-B est à 417,14 $, soit 15 $ de plus que votre budget."

    assert codes(texte, contexte) == {
        CodeGrief.PRIX_ETRANGER_AU_PRODUIT,
        CodeGrief.ECART_NON_DIT,
    }


# --------------------------------------------------------------------------- #
# 9 — la spec déduite d'un sondage
# --------------------------------------------------------------------------- #


def test_une_spec_lue_dans_la_distribution_dun_sondage_est_detectee(contexte):
    """165 Hz existe dans la distribution du sondage, sur **aucun** produit fourni.

    C'est la variante fine du piège nº4, et elle échoue si les valeurs des distributions
    ont été versées dans `valeurs_de_specs`. « 12 écrans sont à 165 Hz » est vrai ;
    « celui-ci est à 165 Hz » ne l'est pas, et la différence est une différence de
    provenance, pas de valeur.
    """
    texte = "Le Samsung Odyssey G50A monte à 165 Hz."

    assert CodeGrief.VALEUR_NON_FOURNIE in codes(texte, contexte)


# --------------------------------------------------------------------------- #
# 10 et 11 — dans une question, pas dans une recommandation (correctif)
# --------------------------------------------------------------------------- #


def test_un_prix_invente_dans_une_question_est_detecte(contexte):
    """**Le chemin le plus fréquent d'une conversation, et il n'était pas couvert.**

    La question d'`ask_clarification` est un argument d'outil, pas un bloc `text` : elle
    partait au client sans passer par le validateur. Une conversation contient beaucoup
    plus de questions que de recommandations — c'était le critère nº1 percé là où il
    servait le plus.

    Le texte de la question passe par les **mêmes** cinq règles : rien à écrire de neuf,
    ce test le constate.
    """
    question = "Le Samsung Odyssey G50A à 199 $ vous conviendrait, ou vous voulez plus grand ?"

    assert CodeGrief.PRIX_ETRANGER_AU_PRODUIT in codes(question, contexte)


def test_un_produit_invente_dans_une_question_est_detecte(contexte):
    """Même faute que le piège nº3, sur l'autre chemin de sortie."""
    question = "Plutôt l'Acer Nitro XV272U à 279,99 $, ou quelque chose de plus grand ?"

    assert CodeGrief.MONTANT_NON_FOURNI in codes(question, contexte)


# --------------------------------------------------------------------------- #
# 12 — le cas de terrain
# --------------------------------------------------------------------------- #


def test_une_borne_basse_arrondie_dans_un_intervalle_est_detectee(contexte):
    """**Reproduction du cas observé en conversation réelle à l'étape 9.**

    Le modèle a écrit « entre 65 et 400 dollars » quand la borne fournie valait 64,98 $.
    « 400 dollars » était vérifié, « 65 » non : entier nu, exempté. Or 65 est un
    **arrondi**, c'est-à-dire une affirmation approximative sur le catalogue — exactement
    ce que l'étape 7 avait refusé de faire produire à `probe_catalog` en écartant les
    paliers arrondis. Le validateur laissait passer ce qu'un arbitrage avait refusé de
    fabriquer.

    Depuis le correctif, la borne basse hérite de l'unité de la borne haute et cesse
    d'être un entier nu. L'exemption générale, elle, reste — voir
    `test_faux_positifs.test_un_entier_nu_passe`.
    """
    texte = "Je vous propose trois modèles entre 65 et 400 dollars."

    assert CodeGrief.MONTANT_NON_FOURNI in codes(texte, contexte)


def test_les_douze_pieges_sont_tous_couverts():
    """Garde de complétude : la porte de sortie en demande douze, ce fichier en tient douze."""
    pieges = [nom for nom in globals() if nom.startswith("test_") and "couverts" not in nom]

    assert len(pieges) == 12
