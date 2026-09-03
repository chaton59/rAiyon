"""Le contexte fourni et les cinq règles, prises une par une.

`test_pieges.py` et `test_faux_positifs.py` jugent le validateur sur des sorties
entières ; ce fichier vérifie la **mécanique** qui les rend possibles — et d'abord la
seule chose qui compte vraiment : que le contexte range les faits par provenance.
"""

import json

import pytest
from contexte_de_test import (
    AOPEN,
    ASUS,
    GIGABYTE,
    LG,
    SAMSUNG,
    charge_recherche,
    contexte_a_deux_hors_budget,
    contexte_apres_sondage,
    contexte_complet,
    messages_du_scenario,
)

from raiyon.validateur.contexte import CONTEXTE_VIDE, contexte_des_messages, contexte_des_resultats
from raiyon.validateur.regles import (
    CodeGrief,
    produits_nommes,
    regle_ecart_au_budget,
    regle_identifiants,
    regle_montants,
    regle_noms_verbatim,
    regle_valeurs_unitaires,
)
from raiyon.validateur.validateur import valider


@pytest.fixture
def contexte():
    return contexte_complet()


# --------------------------------------------------------------------------- #
# Le contexte fourni — la provenance, et rien d'autre
# --------------------------------------------------------------------------- #


def test_le_prix_dun_produit_et_une_borne_de_sondage_ne_sont_pas_rangés_ensemble(contexte):
    """**L'arbitrage B, constaté sur la structure et pas sur un comportement.**

    108,00 est la borne basse du sondage : elle est dans `agregats` et dans aucun `prix`.
    249,99 est le prix du Samsung : il est dans `prix` et dans aucun agrégat. Les deux
    sont des faits fournis, et ils ne disent pas la même chose.
    """
    assert AOPEN.prix_usd in contexte.agregats
    assert AOPEN.prix_usd not in contexte.prix.values()
    assert SAMSUNG.prix_usd in contexte.prix.values()
    assert SAMSUNG.prix_usd not in contexte.agregats


def test_les_valeurs_dune_distribution_nentrent_pas_dans_les_valeurs_de_specs(contexte):
    """165 Hz est dans la distribution du sondage et sur aucun produit fourni.

    C'est la ligne de `contexte.py` qu'il ne faut pas « simplifier » : verser les valeurs
    d'une distribution dans les specs rendrait le piège nº9 indétectable, et
    transformerait « 12 écrans sont à 165 Hz » en « celui-ci est à 165 Hz ».
    """
    assert "165" not in contexte.valeurs_de_specs
    assert GIGABYTE.id not in contexte.produits


def test_un_produit_hors_budget_est_citable_et_porte_son_ecart(contexte):
    """Il est **dans** `produits` — son nom et son `id` sont vrais — et dans `hors_budget`.

    C'est `hors_budget` qui porte la contrainte de présentation (§3.10), pas l'absence
    d'entrée : un produit de la zone de tolérance existe, il ne se cite simplement pas
    sans son écart.
    """
    assert LG.id in contexte.produits
    assert contexte.hors_budget[LG.id] == LG.prix_usd - 400


def test_le_contexte_est_cumulatif_sur_la_session():
    """Sondage puis recherche : le contexte du sondage seul ne porte aucun produit."""
    apres_sondage = contexte_apres_sondage()

    assert not apres_sondage.produits
    assert apres_sondage.agregats
    assert contexte_complet().produits


def test_le_contexte_se_lit_aussi_sur_les_messages_au_format_api():
    """C'est la forme que la boucle a sous la main : des blocs, pas des dataclasses."""
    depuis_les_messages = contexte_des_messages(messages_du_scenario())

    assert sorted(depuis_les_messages.produits) == sorted(contexte_complet().produits)


def test_un_tool_result_en_erreur_ne_fournit_aucun_fait():
    """Un refus est un échange avec le modèle (`erreurs.py`), pas une source de faits."""
    bloc = {
        "type": "tool_result",
        "tool_use_id": "tu_1",
        "content": json.dumps(charge_recherche(), ensure_ascii=False),
        "is_error": True,
    }

    assert contexte_des_messages([{"role": "user", "content": [bloc]}]) == CONTEXTE_VIDE


def test_un_tool_result_illisible_ne_fait_pas_lever():
    """Il ne fournit rien — donc le texte est jugé plus sévèrement, jamais plus laxement."""
    bloc = {"type": "tool_result", "tool_use_id": "tu_1", "content": "{ pas du json"}

    assert contexte_des_messages([{"role": "user", "content": [bloc]}]).vide


def test_un_produit_refuse_par_le_schema_nentre_pas_dans_le_contexte():
    """La porte de `catalogue/schemas.py`, prise dans l'autre sens.

    Un `tool_result` corrompu ne doit pas rendre citable un produit que la base
    n'aurait jamais accepté — sans quoi le validateur garantirait moins que
    l'insertion.
    """
    charge = {"ok": True, "produits": [{"id": "monitor-01", "nom": "Faux"}]}

    assert contexte_des_resultats([charge]).vide


# --------------------------------------------------------------------------- #
# Les règles, une par une
# --------------------------------------------------------------------------- #


def test_regle_1_accepte_un_identifiant_fourni_et_refuse_les_autres(contexte):
    assert regle_identifiants(f"Le {SAMSUNG.id} convient.", contexte) == ()
    assert regle_identifiants("Le monitor-0123456789 convient.", contexte)


def test_regle_2_distingue_la_phrase_qui_nomme_un_produit_de_celle_qui_nen_nomme_aucun(contexte):
    """La même valeur, deux verdicts : c'est toute la règle.

    108 $ dans une phrase sans produit est une borne de sondage — vraie. La même valeur
    accolée au Samsung est une affirmation sur ce produit — fausse.
    """
    assert regle_montants("Il y a des écrans dès 108 $.", contexte) == ()
    assert regle_montants(f"Le {SAMSUNG.nom} est à 108 $.", contexte)


def test_regle_2_rejette_un_montant_qui_nest_ni_prix_ni_agregat(contexte):
    griefs = regle_montants("Comptez 279,99 $ pour ce genre de dalle.", contexte)

    assert [grief.code for grief in griefs] == [CodeGrief.MONTANT_NON_FOURNI]


def test_regle_3_accepte_le_verbatim_et_refuse_la_reecriture(contexte):
    assert regle_noms_verbatim(f"Le {SAMSUNG.nom} est parfait.", contexte) == ()
    assert regle_noms_verbatim("Le Samsung Odyssée G50A est parfait.", contexte)


def test_regle_3_ne_confond_pas_deux_produits_de_la_meme_marque(contexte):
    """Le retrait préalable des noms verbatim est ce qui rend la règle vivable.

    Sans lui, citer correctement un produit laisserait sa marque dans le texte, et
    chaque autre produit de cette marque serait accusé d'avoir été réécrit.
    """
    texte = "Entre le Dell S2721DGF et le Samsung Odyssey G50A, je prends le second."

    assert regle_noms_verbatim(texte, contexte) == ()


def test_regle_4_ne_mord_que_sur_les_produits_de_la_zone_de_tolerance(contexte):
    assert regle_ecart_au_budget(f"Le {SAMSUNG.nom} à 249.99 $.", contexte) == ()
    assert regle_ecart_au_budget(f"Le {LG.nom} à 417.14 $.", contexte)


# --------------------------------------------------------------------------- #
# Les règles 2 et 4 ensemble — le défaut de l'étape 18
#
# Deux règles pouvaient être **conjointement insatisfaisables**. La règle 4 réclamait
# l'écart dans la phrase qui nomme le produit ; la règle 2, dans une phrase sans produit,
# ne connaissait pas les écarts et refusait le chiffre. Dès que le nom et l'écart
# tombaient dans deux phrases — ce que la section 14 du prompt *encourage*, un produit par
# ligne —, le message était refusé quoi que le modèle écrive. Trouvé en conversation
# réelle, sur une comparaison de deux produits au-dessus du budget.
#
# Les trois tests ci-dessous bornent le desserrage : le cas de terrain passe, le critère
# nº2 tient, et la vérification reste par identifiant.
# --------------------------------------------------------------------------- #


def test_le_nom_et_lecart_dans_deux_phrases_ne_levent_aucun_grief(contexte):
    """**Le cas de terrain, reproduit tel quel.** C'est ce qui bloquait le produit.

    Avant l'étape 18 : `ecart_non_dit` sur la première phrase (« dis de combien il
    dépasse — 17.14 $ ») **et** `montant_non_fourni` sur la seconde (« aucun outil n'a
    rendu ce montant »). Le texte était refusé deux fois, puis replié.
    """
    texte = f"Le {LG.nom} est à 417,14 $.\nIl dépasse votre budget de 17,14 $."

    assert valider(texte, contexte).griefs == ()


def test_un_produit_hors_budget_sans_son_ecart_nulle_part_reste_refuse(contexte):
    """**Le critère nº2 tient.** Le desserrage n'est pas une exemption.

    Le produit est nommé sur deux phrases, l'écart n'est écrit dans aucune : la règle 4
    lève son grief, attaché à la **première** phrase qui nomme le produit.
    """
    texte = f"Le {LG.nom} est à 417,14 $.\nIl est très bien équipé pour ce prix."

    griefs = regle_ecart_au_budget(texte, contexte)
    assert [grief.code for grief in griefs] == [CodeGrief.ECART_NON_DIT]
    assert griefs[0].extrait == f"Le {LG.nom} est à 417,14 $"


def test_lecart_dun_produit_ne_couvre_pas_celui_dun_autre():
    """**Le piège de la contamination**, et c'est lui qui borne le desserrage.

    Élargir la recherche de l'écart à tout le message ne doit pas rendre les écarts
    interchangeables : citer 17,14 $ pour le LG ne dit rien de l'Asus, qui dépasse de
    29,99 $. La vérification reste **par identifiant** — sans cela, un seul écart
    quelque part dans un message satisferait tous les produits hors budget qu'il nomme.
    """
    contexte = contexte_a_deux_hors_budget()
    texte = (
        f"Le {LG.nom} est à 417,14 $, soit 17,14 $ de plus que votre budget.\n"
        f"Le {ASUS.nom} est à 429,99 $."
    )

    griefs = regle_ecart_au_budget(texte, contexte)
    assert [grief.code for grief in griefs] == [CodeGrief.ECART_NON_DIT]
    assert ASUS.nom in griefs[0].correction
    assert "29.99 $" in griefs[0].correction


def test_regle_5_range_les_valeurs_par_provenance_comme_la_regle_2(contexte):
    """**La même valeur, deux verdicts, selon que la phrase nomme un produit.**

    165 Hz existe dans la distribution du sondage et sur aucun produit fourni. Dire « il
    y a des écrans à 165 Hz » est donc vrai — c'est ce que `probe_catalog` existe pour
    faire dire — et « le Samsung est à 165 Hz » est faux. C'est exactement la structure
    de la règle 2 sur les bornes de prix, appliquée aux caractéristiques.

    180 Hz, lui, n'est nulle part : ni spec, ni distribution, ni agrégat.
    """
    assert regle_valeurs_unitaires("Un 27 pouces à 144 Hz.", contexte) == ()
    assert regle_valeurs_unitaires("Il y a des écrans à 165 Hz.", contexte) == ()
    assert regle_valeurs_unitaires(f"Le {SAMSUNG.nom} monte à 165 Hz.", contexte)
    assert regle_valeurs_unitaires("Il y a des écrans à 180 Hz.", contexte)


# --------------------------------------------------------------------------- #
# `produits_nommes` — le partage entre les règles 2 et 4
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "phrase",
    [
        "Je conseille le monitor-0000000001.",
        "Je conseille le Samsung Odyssey G50A.",
        "Je conseille l'Odyssée de Samsung.",
    ],
)
def test_une_phrase_nomme_un_produit_par_son_id_son_nom_ou_sa_contrefacon(phrase, contexte):
    """Les trois désignations comptent : sans la troisième, franciser un nom suffirait
    à sortir un prix faux du champ de la règle 2."""
    assert SAMSUNG.id in produits_nommes(phrase, contexte)


def test_toutes_les_regles_sexecutent_meme_apres_un_premier_grief(contexte):
    """Le budget de régénération est de **une** : un message de reprise qui ne
    signalerait que la première faute ferait payer une régénération par faute."""
    texte = "Le monitor-00000000ff est à 279,99 $ et monte à 180 Hz."

    codes = {grief.code for grief in valider(texte, contexte).griefs}

    assert codes == {
        CodeGrief.ID_INCONNU,
        CodeGrief.MONTANT_NON_FOURNI,
        CodeGrief.VALEUR_NON_FOURNIE,
    }
