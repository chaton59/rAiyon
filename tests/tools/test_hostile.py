"""Les portes fermées, une par une — **par la surface que le modèle voit réellement**.

Chaque test est nommé d'après ce qu'il empêche, pas d'après ce qu'il appelle, et passe
par les fonctions d'outil plutôt que par la fusion : c'est là que le modèle frappera.

C'est la porte de sortie de l'étape 7, et elle a changé de nature en cours de route.
L'énoncé initial disait : « des tests qui appellent les outils avec des arguments
hostiles — budget élargi, catégorie inexistante, critères contradictoires — et vérifient
qu'aucun ne franchit l'invariant ». Depuis l'arbitrage C, **les outils de recherche ne
prennent aucun critère** : la question n'est plus « l'argument hostile est-il arrêté ? »
mais « existe-t-il un argument par lequel passer ? ». Les deux formes sont ici — le refus
pour ce qui entre par `record_criteria`, et l'inspection de signature pour ce qui
n'entre nulle part.

⚠️ **Ce que ces tests ne prouvent pas**, et qui est au §7 : le jeton borne le nombre
d'assouplissements par parole du client, il ne vérifie pas que le client parlait **de ce
critère-là**. Un desserrage par tour au lieu de zéro contrôle est un progrès, pas une
garantie.
"""

import inspect
from dataclasses import fields
from decimal import Decimal
from typing import get_type_hints

import pytest

from outils_de_test import TOLERANCE, critere, ecrans, etat_avec
from raiyon.matching.criteres import Importance, Operateur
from raiyon.matching.relachement import Motif
from raiyon.tools.erreurs import CodeRefus, OutilRefuse
from raiyon.tools.etat import EtatSession, fusionner
from raiyon.tools.outils import (
    ArgumentsCritere,
    ArgumentsEnregistrement,
    ArgumentsPrecision,
    ArgumentsSondage,
    ResultatSondage,
    demander_precision,
    en_tool_result,
    enregistrer_criteres,
    question_suivante,
    rechercher_produits,
    sonder_catalogue,
)


def poser(
    etat: EtatSession,
    tour: int,
    categorie: str = "monitor",
    *criteres: ArgumentsCritere,
    **arguments: object,
):
    """Un appel de `record_criteria`, tel que le modèle l'émettrait."""
    return enregistrer_criteres(
        etat,
        ArgumentsEnregistrement(categorie=categorie, criteres=criteres, **arguments),
        tour_client=tour,
    )


def entrant(champ, operateur=Operateur.AU_MOINS, valeur="144", importance=Importance.SOUHAIT):
    return ArgumentsCritere(champ=champ, operateur=operateur, valeur=valeur, importance=importance)


# --------------------------------------------------------------------------- #
# 1. Le budget ne s'élargit pas en cours de tour — et il n'a qu'une porte
# --------------------------------------------------------------------------- #


def test_le_budget_ne_selargit_pas_deux_fois_dans_le_meme_message():
    """Le premier relèvement prend le jeton, le second est refusé et le budget tient."""
    etat = etat_avec("monitor", budget="300")
    etat = poser(etat, 2, "monitor", budget_usd="350").etat
    assert etat.budget_usd == Decimal("350.00")

    resultat = poser(etat, 2, "monitor", budget_usd="900")
    assert resultat.budget_usd == Decimal("350.00")
    assert [refus.champ for refus in resultat.mouvements_refuses] == ["prix_usd"]


def test_il_nexiste_aucun_autre_chemin_vers_le_budget_que_lenregistrement():
    """Arbitrage C, constaté sur les signatures : les quatre autres outils lisent l'état.

    Une garde qu'on écrit doit être testée et n'être jamais oubliée sur un futur outil ;
    un argument qui n'existe pas n'a rien à oublier.
    """
    interdits = {"budget_usd", "budget", "criteres", "categorie", "max_price"}
    for outil in (sonder_catalogue, question_suivante, rechercher_produits, demander_precision):
        assert interdits.isdisjoint(inspect.signature(outil).parameters)
    for arguments in (ArgumentsSondage, ArgumentsPrecision):
        assert interdits.isdisjoint(arguments.model_fields)


# --------------------------------------------------------------------------- #
# 2 à 6. Ce que le registre refuse
# --------------------------------------------------------------------------- #


def test_une_categorie_inexistante_nentre_pas():
    """Deux lignes de défense : le schéma d'entrée, puis la fusion."""
    with pytest.raises(ValueError):
        ArgumentsEnregistrement(categorie="perceuse")

    with pytest.raises(OutilRefuse) as refus:
        fusionner(EtatSession(), tour_client=1, categorie="perceuse")
    assert refus.value.code is CodeRefus.CATEGORIE_INCONNUE


def test_un_champ_dune_autre_categorie_nentre_pas():
    """Un écran n'a pas de socket, un processeur n'a pas de dalle."""
    with pytest.raises(OutilRefuse) as refus:
        poser(EtatSession(), 1, "cpu", entrant("screen_size", valeur="27"))
    assert refus.value.code is CodeRefus.CRITERE_INVALIDE
    assert "champs connus" in refus.value.message


@pytest.mark.parametrize("champ", ["color", "nom", "id"])
def test_un_champ_daffichage_ne_se_pose_pas_en_critere(champ):
    """Ils sont montrés au client ; ils ne filtrent ni ne scorent (§ schéma d'attributs).

    Le registre les porte **avec leur rôle** plutôt que de les omettre : c'est ce qui
    permet de le prouver ici, au lieu de constater qu'on les a oubliés.
    """
    with pytest.raises(OutilRefuse) as refus:
        poser(EtatSession(), 1, "memory", entrant(champ, Operateur.EGAL, "Black"))
    assert refus.value.code is CodeRefus.CRITERE_INVALIDE


@pytest.mark.parametrize("champ", ["prix_usd", "categorie", "disponible"])
def test_un_champ_a_champ_dedie_ne_se_pose_pas_en_critere(champ):
    """Deux chemins vers une même contrainte finissent par diverger (§3.10)."""
    with pytest.raises(OutilRefuse) as refus:
        poser(EtatSession(), 1, "monitor", entrant(champ, Operateur.EGAL, "300"))
    assert refus.value.code is CodeRefus.CRITERE_INVALIDE
    assert "budget" in refus.value.message or "imposé" in refus.value.message


def test_un_attribut_de_score_ne_se_promeut_pas_en_bloquant():
    """Poser `boost_clock` en bloquant exclurait le tiers de processeurs qui ne le
    déclarent pas : un comblement d'absence par la porte de derrière (§3.4quater)."""
    with pytest.raises(OutilRefuse) as refus:
        poser(
            EtatSession(),
            1,
            "cpu",
            entrant("boost_clock", Operateur.AU_MOINS, "5.0", Importance.BLOQUANT),
        )
    assert refus.value.code is CodeRefus.CRITERE_INVALIDE
    assert "Repasser en 'important'" in refus.value.message


# --------------------------------------------------------------------------- #
# 7 à 9. Les trois formes d'assouplissement, et le jeton qui les borne
# --------------------------------------------------------------------------- #


def test_un_bloquant_ne_retombe_pas_en_souhait_sans_nouvelle_parole():
    """L'importance est collante : la baisser est un assouplissement comme un autre.

    Le jeton du tour est ici déjà pris par un premier assouplissement ; la rétrogradation
    est donc refusée et le critère reste bloquant. Sans cette règle, le zéro résultat
    devient une incitation à assouplir en douce — l'agent essaierait jusqu'à trouver
    quelque chose à montrer, ce que §3.6 cherche précisément à empêcher.
    """
    etat = etat_avec(
        "monitor",
        critere("refresh_rate", Operateur.AU_MOINS, "144", Importance.BLOQUANT),
        critere("screen_size", Operateur.AU_MOINS, "27", Importance.BLOQUANT),
    )
    etat = poser(etat, 2, "monitor", entrant("screen_size", valeur="24")).etat

    resultat = poser(
        etat,
        2,
        "monitor",
        entrant("refresh_rate", Operateur.AU_MOINS, "144", Importance.SOUHAIT),
    )
    pose = resultat.etat.par_cle("monitor")[("refresh_rate", Operateur.AU_MOINS)]
    assert pose.importance is Importance.BLOQUANT
    assert [refus.champ for refus in resultat.mouvements_refuses] == ["refresh_rate"]


def test_un_seuil_ne_recule_pas_deux_fois_apres_un_zero_resultat():
    """**Le test le plus important de l'étape.**

    L'étape 6 ne surveillait que l'importance. C'était insuffisant : après un zéro
    résultat, passer `au_moins 144` à `au_moins 120` obtient exactement ce que la
    rétrogradation obtenait, sans toucher à l'importance — et retirer le critère fait
    pire. Deux assertions, et la première porte autant que la seconde :

    1. reculer un seuil **est** un desserrage : le mouvement consomme le jeton du tour ;
    2. le suivant, dans le même message, est refusé, et le seuil tient.
    """
    etat = etat_avec(
        "monitor", critere("refresh_rate", Operateur.AU_MOINS, "144", Importance.BLOQUANT)
    )
    premier = poser(
        etat, 2, "monitor", entrant("refresh_rate", Operateur.AU_MOINS, "120", Importance.BLOQUANT)
    )
    assert premier.etat.tour_du_dernier_desserrage == 2
    assert premier.criteres[0].valeur == Decimal("120")

    second = poser(
        premier.etat,
        2,
        "monitor",
        entrant("refresh_rate", Operateur.AU_MOINS, "100", Importance.BLOQUANT),
    )
    assert second.criteres[0].valeur == Decimal("120")
    assert [refus.champ for refus in second.mouvements_refuses] == ["refresh_rate"]


def test_un_critere_bloquant_ne_se_retire_pas_deux_fois_dans_le_meme_message():
    """Retirer est la forme la plus franche du desserrage, et elle passe par le jeton."""
    etat = etat_avec(
        "monitor",
        critere("refresh_rate", Operateur.AU_MOINS, "144", Importance.BLOQUANT),
        critere("aspect_ratio", Operateur.EGAL, "16:9", Importance.BLOQUANT),
    )
    etat = poser(
        etat, 2, "monitor", retraits=({"champ": "aspect_ratio", "operateur": "egal"},)
    ).etat

    resultat = poser(
        etat, 2, "monitor", retraits=({"champ": "refresh_rate", "operateur": "au_moins"},)
    )
    assert [c.champ for c in resultat.criteres] == ["refresh_rate"]
    assert [refus.champ for refus in resultat.mouvements_refuses] == ["refresh_rate"]


# --------------------------------------------------------------------------- #
# 10. Un tour, une catégorie
# --------------------------------------------------------------------------- #


def test_deux_categories_ne_se_cherchent_pas_dans_le_meme_message(depot):
    """Le moteur garantit qu'un **appel** rend une seule catégorie ; il ne garantit rien
    sur un **tour**. Sans cette garde, l'agent servirait la « config gaming » que §8 met
    hors périmètre, et le critère nº2 cesserait d'être vérifiable produit par produit."""
    depot.produits = ecrans(3)
    etat = etat_avec("monitor")
    etat = rechercher_produits(etat, depot, tour_client=1, tolerance=TOLERANCE).etat
    etat = poser(etat, 1, "cpu").etat

    with pytest.raises(OutilRefuse) as refus:
        rechercher_produits(etat, depot, tour_client=1, tolerance=TOLERANCE)
    assert refus.value.code is CodeRefus.DEUX_CATEGORIES_DANS_UN_TOUR
    assert "un composant à la fois" in refus.value.message


# --------------------------------------------------------------------------- #
# 11. Une contradiction est une réponse, pas un bug
# --------------------------------------------------------------------------- #


def test_deux_criteres_contradictoires_donnent_zero_resultat_et_un_diagnostic(depot):
    """« Au moins 200 Hz et au plus 100 Hz » ne lève pas : le catalogue répond, et le
    moteur dit pourquoi il ne répond rien. Lever ici priverait le client de l'explication
    à laquelle le critère nº6 lui donne droit."""
    depot.produits = []
    depot.releves.rouvre_si_retire["refresh_rate"] = 12

    etat = etat_avec(
        "monitor",
        critere("refresh_rate", Operateur.AU_MOINS, "200", Importance.BLOQUANT),
        critere("refresh_rate", Operateur.AU_PLUS, "100", Importance.BLOQUANT),
    )
    charge = en_tool_result(rechercher_produits(etat, depot, tour_client=1, tolerance=TOLERANCE))
    assert charge["produits"] == []
    assert charge["diagnostic"]["motif"] == Motif.CRITERE_TROP_STRICT.value
    assert {p["champ"] for p in charge["diagnostic"]["propositions"]} == {"refresh_rate"}


# --------------------------------------------------------------------------- #
# 12 à 14. Ce qui ne se convertit pas, et ce qui se contredit
# --------------------------------------------------------------------------- #


def test_un_operateur_incompatible_avec_le_genre_nentre_pas():
    """Une interface ne se compare pas : elle se branche ou non (arbitrage L)."""
    with pytest.raises(OutilRefuse) as refus:
        poser(
            EtatSession(),
            1,
            "internal-hard-drive",
            entrant("interface", Operateur.AU_MOINS, "M.2 PCIe 4.0 X4"),
        )
    assert refus.value.code is CodeRefus.CRITERE_INVALIDE
    assert "admis" in refus.value.message


@pytest.mark.parametrize(
    ("categorie", "champ", "operateur", "valeur"),
    [
        ("monitor", "refresh_rate", Operateur.AU_MOINS, "beaucoup"),
        ("headphones", "wireless", Operateur.EGAL, "peut-être"),
    ],
)
def test_une_valeur_illisible_nentre_pas(categorie, champ, operateur, valeur):
    """`valeur` est toujours une chaîne dans le schéma (arbitrage F) : la convertir est
    donc un acte, et il peut échouer. Le message dit ce qu'il fallait écrire."""
    with pytest.raises(OutilRefuse) as refus:
        poser(EtatSession(), 1, categorie, entrant(champ, operateur, valeur))
    assert refus.value.code is CodeRefus.VALEUR_ILLISIBLE
    assert valeur in refus.value.message


def test_deux_criteres_sur_la_meme_cle_ne_passent_pas():
    """Le second annulerait le premier, ou le compterait deux fois au score."""
    with pytest.raises(OutilRefuse) as refus:
        poser(
            EtatSession(),
            1,
            "monitor",
            entrant("refresh_rate", Operateur.AU_MOINS, "144"),
            entrant("refresh_rate", Operateur.AU_MOINS, "120"),
        )
    assert refus.value.code is CodeRefus.CRITERE_INVALIDE
    assert "intervalle" in refus.value.message


def test_les_deux_bornes_dun_intervalle_ne_sont_pas_un_doublon():
    """Contre-épreuve : la clé est `(champ, opérateur)`, pas le champ seul — sinon
    « entre 24 et 27 pouces » serait indicible."""
    resultat = poser(
        EtatSession(),
        1,
        "monitor",
        entrant("screen_size", Operateur.AU_MOINS, "24"),
        entrant("screen_size", Operateur.AU_PLUS, "27"),
    )
    assert len(resultat.criteres) == 2


# --------------------------------------------------------------------------- #
# 15. Le sondage ne peut pas rendre de produit
# --------------------------------------------------------------------------- #


def test_le_sondage_ne_peut_structurellement_pas_rendre_de_produit():
    """Constaté **sur le type de retour**, pas sur une exécution : une exécution ne
    prouve que le jeu de données qu'on lui a donné.

    Aucun champ de `ResultatSondage` ne porte d'identifiant, de nom, ni de ligne de
    catalogue. C'est ce qui permet à l'agent d'être fluide pendant la collecte sans
    court-circuiter le chemin de recommandation, qui reste unique et instrumenté.
    """
    annotations = get_type_hints(ResultatSondage)
    for champ in fields(ResultatSondage):
        if champ.name == "etat":
            continue
        assert "Produit" not in str(annotations[champ.name])
        assert not {"id", "nom", "produit", "produits"} & set(str(annotations[champ.name]).split())


def test_un_sondage_execute_ne_laisse_filtrer_aucun_identifiant(depot):
    """Ceinture et bretelles : le type l'interdit, la sérialisation le confirme."""
    depot.produits = ecrans(3)
    charge = str(en_tool_result(sonder_catalogue(etat_avec("monitor"), depot, tolerance=TOLERANCE)))
    for produit in depot.produits:
        assert produit.id not in charge
        assert produit.nom not in charge


# --------------------------------------------------------------------------- #
# 16. La règle borne l'essai-erreur, elle ne gèle pas la conversation
# --------------------------------------------------------------------------- #


def test_deux_assouplissements_dans_deux_messages_passent_tous_les_deux():
    """Un jeton par parole du client : le client qui change deux fois d'avis en deux
    messages obtient deux fois gain de cause. Une règle qui gèlerait la conversation
    serait pire que le mal qu'elle soigne."""
    etat = etat_avec(
        "monitor", critere("refresh_rate", Operateur.AU_MOINS, "144", Importance.BLOQUANT)
    )
    etat = poser(
        etat, 2, "monitor", entrant("refresh_rate", Operateur.AU_MOINS, "120", Importance.BLOQUANT)
    ).etat
    resultat = poser(
        etat, 3, "monitor", entrant("refresh_rate", Operateur.AU_MOINS, "100", Importance.BLOQUANT)
    )
    assert resultat.mouvements_refuses == ()
    assert resultat.criteres[0].valeur == Decimal("100")
    assert resultat.etat.tour_du_dernier_desserrage == 3


# --------------------------------------------------------------------------- #
# 17. Deux gestes contradictoires sur le budget
# --------------------------------------------------------------------------- #


def test_poser_et_retirer_le_budget_dans_le_meme_appel_ne_passe_pas():
    """Choisir lequel des deux gestes appliquer serait deviner ce que le client a dit.

    Le refus est **dur** : c'est une erreur d'argument que le modèle doit corriger, pas
    un mouvement à écarter en silence.
    """
    with pytest.raises(OutilRefuse) as refus:
        enregistrer_criteres(
            EtatSession(),
            ArgumentsEnregistrement(categorie="monitor", budget_usd="400", retirer_le_budget=True),
            tour_client=1,
        )
    assert refus.value.code is CodeRefus.VALEUR_ILLISIBLE
    assert "choisir" in refus.value.message
