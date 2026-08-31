"""Les agrégats de l'étape 7, sur les 1 026 produits du seed committé. Marqueur `integration`.

Ce que la part pure ne peut pas vérifier : que le `GROUP BY` compte bien ce que le
registre annonce, que la couverture mesurée est celle du rapport de seed, et que les
nombres qu'un client lira — « il te reste 32 modèles », « entre 108 et 400 $ » — sortent
de la base et non d'une fixture. Les valeurs citées en dur sont celles du seed : si elles
changent, un test casse, et c'est le comportement voulu.

Aucun appel LLM, aucune clé API.
"""

from decimal import Decimal

import pytest

from raiyon.matching.attributs import ATTRIBUTS
from raiyon.matching.criteres import Critere, Importance, Operateur, RequeteMatching
from raiyon.matching.depot import Fourchette
from raiyon.matching.sondage import ordonner, resumer
from raiyon.tools.etat import CritereTexte, DemandeBudget, EtatSession, fusionner
from raiyon.tools.outils import ArgumentsSondage, question_suivante, sonder_catalogue

pytestmark = pytest.mark.integration

TOUT = Fourchette()
TOLERANCE = Decimal("0.15")


def requete(categorie="monitor", budget=None, *criteres) -> RequeteMatching:
    return RequeteMatching(categorie=categorie, budget_usd=budget, criteres=criteres)


# --------------------------------------------------------------------------- #
# Comptages et bornes — le même prédicat que les candidats
# --------------------------------------------------------------------------- #


def test_le_comptage_est_celui_des_candidats(depot_catalogue):
    """« Il te reste 12 modèles » et « voici les trois meilleurs » ne peuvent pas parler
    de deux ensembles différents : c'est le même prédicat, sans la projection."""
    demande = requete("monitor")
    assert depot_catalogue.compter(demande, TOUT) == len(depot_catalogue.candidats(demande, TOUT))


def test_le_comptage_applique_le_budget(depot_catalogue):
    demande = requete("monitor")
    dans_le_budget = depot_catalogue.compter(demande, Fourchette(max_inclus=Decimal("200")))
    assert 0 < dans_le_budget < depot_catalogue.compter(demande, TOUT)


def test_les_bornes_de_prix_sont_celles_des_candidats(depot_catalogue):
    demande = requete("monitor")
    bornes = depot_catalogue.bornes_de_prix(demande, TOUT)
    prix = [produit.prix_usd for produit in depot_catalogue.candidats(demande, TOUT)]
    assert bornes is not None
    assert (bornes.plus_bas, bornes.plus_haut) == (min(prix), max(prix))


def test_un_sous_catalogue_vide_na_pas_de_fourchette(depot_catalogue):
    """`None` est une information : une fourchette de zéro produit n'existe pas."""
    impossible = requete(
        "monitor",
        None,
        Critere(
            champ="refresh_rate",
            operateur=Operateur.AU_MOINS,
            valeur=Decimal("9999"),
            importance=Importance.BLOQUANT,
        ),
    )
    assert depot_catalogue.compter(impossible, TOUT) == 0
    assert depot_catalogue.bornes_de_prix(impossible, TOUT) is None


# --------------------------------------------------------------------------- #
# Distributions et couverture
# --------------------------------------------------------------------------- #


def test_la_distribution_compte_tous_les_produits_renseignes(depot_catalogue):
    demande = requete("monitor")
    (comptages,) = depot_catalogue.distributions(demande, TOUT, ["panel_type"]).values()
    assert comptages.total == depot_catalogue.compter(demande, TOUT)
    assert comptages.renseignes == sum(nombre for _, nombre in comptages.effectifs)
    assert comptages.renseignes <= comptages.total


def test_la_couverture_mesuree_est_celle_du_registre(depot_catalogue):
    """`rpm` est à 33,9 % sur le seed, et ces 33,9 % **sont** la part de HDD.

    La couverture n'est donc pas une lacune de données : c'est ce que la pondération de
    l'arbitrage H doit voir pour ne pas proposer de demander une vitesse de rotation à un
    client dont les deux tiers des candidats sont des SSD.
    """
    demande = requete("internal-hard-drive")
    comptages = depot_catalogue.distributions(demande, TOUT, ["rpm", "type"])
    rpm = comptages["rpm"]
    taux = Decimal(rpm.renseignes) / Decimal(rpm.total)
    assert abs(taux - ATTRIBUTS["internal-hard-drive"]["rpm"].taux_remplissage) < Decimal("0.01")

    hdd = dict(comptages["type"].effectifs).get("HDD", 0)
    assert rpm.renseignes == hdd


def test_un_champ_a_100_pour_cent_est_renseigne_partout(depot_catalogue):
    demande = requete("cpu")
    (comptages,) = depot_catalogue.distributions(demande, TOUT, ["microarchitecture"]).values()
    assert comptages.renseignes == comptages.total


def test_les_valeurs_dune_colonne_commune_remontent_aussi(depot_catalogue):
    """`marque` ne vit pas dans le JSONB : le prédicat doit lire la colonne.

    C'est le mode d'échec le plus désagréable de l'étape 6 — un `dans_les_specs` oublié
    rendait zéro produit **sans lever**. Le sondage a le même point faible, en pire : il
    afficherait « aucune marque disponible ».
    """
    (comptages,) = depot_catalogue.distributions(requete("cpu"), TOUT, ["marque"]).values()
    assert comptages.renseignes == comptages.total
    assert "Intel" in dict(comptages.effectifs)
    assert "AMD" in dict(comptages.effectifs)


def test_la_distribution_respecte_les_criteres_de_la_requete(depot_catalogue):
    """Le sous-catalogue courant, pas le catalogue entier."""
    sans_critere = depot_catalogue.distributions(requete("monitor"), TOUT, ["panel_type"])
    filtre = depot_catalogue.distributions(
        requete(
            "monitor",
            None,
            Critere(
                champ="refresh_rate",
                operateur=Operateur.AU_MOINS,
                valeur=Decimal("144"),
                importance=Importance.BLOQUANT,
            ),
        ),
        TOUT,
        ["panel_type"],
    )
    assert filtre["panel_type"].total < sans_critere["panel_type"].total


def test_lordre_ne_depend_pas_de_postgres(depot_catalogue):
    """Le tri est fait en Python, une fois : la collation de la base n'entre pas dans ce
    qu'un client lira."""
    (comptages,) = depot_catalogue.distributions(requete("monitor"), TOUT, ["panel_type"]).values()
    valeurs = ordonner(comptages, ATTRIBUTS["monitor"]["panel_type"])
    effectifs = [valeur.effectif for valeur in valeurs]
    assert effectifs == sorted(effectifs, reverse=True)


def test_les_241_chipsets_sont_tronques_et_ca_se_dit(depot_catalogue):
    """241 valeurs ne rentrent pas. Sans `total_distinct` et `tronque`, l'agent écrirait
    « les chipsets disponibles sont… » et ce serait faux par omission."""
    (comptages,) = depot_catalogue.distributions(requete("video-card"), TOUT, ["chipset"]).values()
    resume = resumer(comptages, ATTRIBUTS["video-card"]["chipset"])
    assert resume.total_distinct > 15
    assert resume.tronque is True
    assert len(resume.valeurs) == 15


# --------------------------------------------------------------------------- #
# Les outils, sur le catalogue réel
# --------------------------------------------------------------------------- #


def etat_ecran_144hz() -> EtatSession:
    return fusionner(
        EtatSession(),
        tour_client=1,
        categorie="monitor",
        ajouts=[CritereTexte("refresh_rate", Operateur.AU_MOINS, "144", Importance.BLOQUANT)],
        budget=DemandeBudget("400"),
    ).etat


def test_un_sondage_reel_rend_des_nombres_du_catalogue(depot_catalogue):
    """Les valeurs sont celles du seed committé : elles changent si le catalogue change."""
    sondage = sonder_catalogue(
        etat_ecran_144hz(),
        depot_catalogue,
        ArgumentsSondage(champs=("panel_type",)),
        tolerance=TOLERANCE,
    )
    assert sondage.dans_le_budget == 32
    assert sondage.dans_la_zone_de_tolerance == 4
    assert sondage.fourchette_prix is not None
    assert sondage.fourchette_prix.plus_bas == Decimal("108.00")
    assert sondage.fourchette_prix.plus_haut == Decimal("399.99")

    (dalles,) = sondage.champs
    assert {valeur.valeur for valeur in dalles.valeurs} == {"VA", "IPS", "TN"}
    assert dalles.total == 32


def test_un_sondage_reel_declare_ce_que_le_filtre_a_ecarte_faute_de_donnee(depot_catalogue):
    """« Aucun écran ne fait 144 Hz » n'est pas « six écrans ne déclarent pas leur
    fréquence » — et le sondage est l'endroit où l'agent décide de ce qu'il affirme."""
    sondage = sonder_catalogue(etat_ecran_144hz(), depot_catalogue, tolerance=TOLERANCE)
    assert sondage.ecartes_faute_de_donnee == {"refresh_rate": 6}


def test_la_question_suivante_rend_le_budget_en_tete_quand_il_manque(depot_catalogue):
    etat = fusionner(
        EtatSession(),
        tour_client=1,
        categorie="video-card",
        ajouts=[CritereTexte("chipset", Operateur.EGAL, "GeForce RTX 4070", Importance.BLOQUANT)],
    ).etat
    resultat = question_suivante(etat, depot_catalogue, tolerance=TOLERANCE)

    assert resultat.budget is not None
    assert resultat.budget.fourchette_prix is not None
    assert resultat.budget.fourchette_prix.plus_bas == Decimal("579.00")
    assert resultat.candidats == 3


def test_la_question_suivante_rend_un_champ_reellement_discriminant(depot_catalogue):
    resultat = question_suivante(etat_ecran_144hz(), depot_catalogue, tolerance=TOLERANCE)
    assert resultat.champ is not None
    assert resultat.champ.score > 0
    assert resultat.champ.distribution.total == 32
    # Le champ proposé n'est jamais un champ que le client a déjà renseigné.
    assert resultat.champ.champ != "refresh_rate"
