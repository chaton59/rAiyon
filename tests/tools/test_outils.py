"""Les cinq outils : ce qu'ils lisent, ce qu'ils rendent, ce qu'ils refusent de rendre.

Aucun de ces tests ne charge `Settings` : la tolérance est injectée, l'état est pur et le
dépôt est en mémoire. C'est la porte de sortie de l'étape — la couche outils est testable
sans base, sans conteneur et sans clé API — et elle tient par construction, pas par
discipline.
"""

from decimal import Decimal

import pytest

from outils_de_test import TOLERANCE, critere, ecrans, etat_avec
from produits_de_test import fabriquer
from raiyon.matching.criteres import Importance, Operateur, Optimisation
from raiyon.matching.depot import Fourchette
from raiyon.matching.relachement import Motif
from raiyon.tools.erreurs import CodeRefus, OutilRefuse
from raiyon.tools.etat import EtatSession
from raiyon.tools.outils import (
    ArgumentsCritere,
    ArgumentsEnregistrement,
    ArgumentsPrecision,
    ArgumentsSondage,
    demander_precision,
    en_tool_result,
    enregistrer_criteres,
    question_suivante,
    rechercher_produits,
    sonder_catalogue,
)

# --------------------------------------------------------------------------- #
# enregistrer_criteres — la seule porte
# --------------------------------------------------------------------------- #


def test_lenregistrement_rend_letat_et_ce_qui_a_ete_pose():
    resultat = enregistrer_criteres(
        EtatSession(),
        ArgumentsEnregistrement(
            categorie="monitor",
            criteres=(
                ArgumentsCritere(
                    champ="refresh_rate",
                    operateur=Operateur.AU_MOINS,
                    valeur="144",
                    importance=Importance.BLOQUANT,
                ),
            ),
            budget_usd="400",
        ),
        tour_client=1,
    )
    assert resultat.categorie == "monitor"
    assert resultat.budget_usd == Decimal("400")
    assert [c.champ for c in resultat.criteres] == ["refresh_rate"]
    assert resultat.mouvements_refuses == ()
    assert resultat.terminal is False


def test_le_retrait_du_budget_se_demande_explicitement():
    """« Je n'ai pas de plafond » est un geste, pas une absence d'argument."""
    etat = etat_avec("monitor", budget="400")
    resultat = enregistrer_criteres(
        etat,
        ArgumentsEnregistrement(categorie="monitor", retirer_le_budget=True),
        tour_client=2,
    )
    assert resultat.budget_usd is None


def test_un_argument_invente_par_le_modele_est_une_erreur_pas_un_oubli():
    with pytest.raises(ValueError):
        ArgumentsEnregistrement(categorie="monitor", max_price="400")


# --------------------------------------------------------------------------- #
# sonder_catalogue — des agrégats, et aucun produit
# --------------------------------------------------------------------------- #


def test_le_sondage_rend_deux_comptes_separes(depot):
    """Sinon « il te reste 12 modèles » désignerait des produits que le client ne peut
    pas acheter (§3.10)."""
    depot.produits = ecrans(5)
    depot.hors_budget = ecrans(2)
    etat = etat_avec("monitor", budget="400")

    sondage = sonder_catalogue(etat, depot, tolerance=TOLERANCE)
    assert sondage.dans_le_budget == 5
    assert sondage.dans_la_zone_de_tolerance == 2


def test_le_sondage_applique_le_budget(depot):
    depot.produits = ecrans(3)
    etat = etat_avec("monitor", budget="250")
    sonder_catalogue(etat, depot, tolerance=TOLERANCE)
    assert Fourchette(max_inclus=Decimal("250")) in depot.fourchettes


def test_sans_budget_la_zone_de_tolerance_est_vide_et_aucune_bande_nest_demandee(depot):
    depot.produits = ecrans(3)
    sondage = sonder_catalogue(etat_avec("monitor"), depot, tolerance=TOLERANCE)
    assert sondage.dans_la_zone_de_tolerance == 0
    assert all(f.min_exclu is None for f in depot.fourchettes)


def test_le_sondage_ordonne_les_valeurs_et_declare_la_troncature(depot):
    depot.produits = [
        fabriquer("video-card", numero, "500", chipset=f"Chipset {numero:02d}")
        for numero in range(1, 21)
    ] + [fabriquer("video-card", 99, "500", chipset="Chipset 01")]
    sondage = sonder_catalogue(
        etat_avec("video-card"), depot, ArgumentsSondage(champs=("chipset",)), tolerance=TOLERANCE
    )
    (distribution,) = sondage.champs
    assert distribution.valeurs[0].valeur == "Chipset 01"
    assert distribution.total_distinct == 20
    assert distribution.tronque is True
    assert len(distribution.valeurs) == 15


def test_la_troncature_est_declaree_meme_quand_il_ny_a_rien_a_tronquer(depot):
    depot.produits = ecrans(3)
    sondage = sonder_catalogue(
        etat_avec("monitor"), depot, ArgumentsSondage(champs=("panel_type",)), tolerance=TOLERANCE
    )
    (distribution,) = sondage.champs
    assert distribution.tronque is False
    assert distribution.total_distinct == 1


def test_le_sondage_decrit_tous_les_champs_utilisables_par_defaut(depot):
    depot.produits = ecrans(3)
    sondage = sonder_catalogue(etat_avec("monitor"), depot, tolerance=TOLERANCE)
    assert {distribution.champ for distribution in sondage.champs} >= {
        "refresh_rate",
        "panel_type",
        "marque",
    }


def test_le_sondage_respecte_lordre_des_champs_demandes(depot):
    depot.produits = ecrans(3)
    sondage = sonder_catalogue(
        etat_avec("monitor"),
        depot,
        ArgumentsSondage(champs=("panel_type", "refresh_rate", "panel_type")),
        tolerance=TOLERANCE,
    )
    assert [distribution.champ for distribution in sondage.champs] == [
        "panel_type",
        "refresh_rate",
    ]


def test_le_sondage_transporte_les_ecartes_faute_de_donnee(depot):
    """Ce que le filtre a écarté sans le dire est une information sur le catalogue."""
    depot.produits = ecrans(3)
    depot.ecartes = {"refresh_rate": 6}
    sondage = sonder_catalogue(etat_avec("monitor"), depot, tolerance=TOLERANCE)
    assert sondage.ecartes_faute_de_donnee == {"refresh_rate": 6}


# --------------------------------------------------------------------------- #
# question_suivante
# --------------------------------------------------------------------------- #


def test_la_question_ne_rend_aucune_phrase(depot):
    """Le français est du vocabulaire, pas des phrases (arbitrage I de l'étape 6)."""
    depot.produits = [
        *ecrans(3, panel_type="IPS"),
        *[fabriquer("monitor", 10 + n, "200", panel_type="VA") for n in range(3)],
    ]
    resultat = question_suivante(etat_avec("monitor", budget="400"), depot, tolerance=TOLERANCE)
    assert resultat.champ is not None
    assert resultat.champ.libelle_fr == "type de dalle"
    assert {v.valeur for v in resultat.champ.distribution.valeurs} == {"IPS", "VA"}
    assert "?" not in str(en_tool_result(resultat))


def test_la_question_ecarte_les_champs_deja_dits(depot):
    """§3.7 parle du champ **manquant** : redemander ce que le client vient de dire est
    l'interrogatoire que §3.9 cherche à éviter."""
    depot.produits = [
        *ecrans(3, panel_type="IPS"),
        *[fabriquer("monitor", 10 + n, "200", panel_type="VA") for n in range(3)],
    ]
    etat = etat_avec("monitor", critere("panel_type", Operateur.EGAL, "IPS"), budget="400")
    resultat = question_suivante(etat, depot, tolerance=TOLERANCE)
    assert resultat.champ is None or resultat.champ.champ != "panel_type"


def test_le_budget_inconnu_est_rendu_en_tete_dans_un_champ_typé_distinct(depot):
    """`prix_usd` est un champ dédié : le déguiser en attribut à demander rouvrirait le
    second chemin vers le budget que §3.10 ferme."""
    depot.produits = ecrans(3)
    resultat = question_suivante(etat_avec("monitor"), depot, tolerance=TOLERANCE)
    assert resultat.budget is not None
    assert resultat.budget.fourchette_prix is not None
    assert resultat.budget.fourchette_prix.plus_bas == Decimal("110")
    assert resultat.budget.fourchette_prix.plus_haut == Decimal("130")


def test_le_budget_connu_ne_fait_pas_de_cas_special(depot):
    depot.produits = ecrans(3)
    resultat = question_suivante(etat_avec("monitor", budget="400"), depot, tolerance=TOLERANCE)
    assert resultat.budget is None


def test_aucun_champ_discriminant_est_une_reponse(depot):
    depot.produits = ecrans(3)
    resultat = question_suivante(etat_avec("monitor", budget="400"), depot, tolerance=TOLERANCE)
    assert resultat.champ is None
    assert resultat.candidats == 3


# --------------------------------------------------------------------------- #
# rechercher_produits
# --------------------------------------------------------------------------- #


def test_la_recherche_rend_le_produit_entier_et_sa_trace(depot):
    """Arbitrage J : toutes les specs, pas seulement les champs cités par la trace."""
    depot.produits = ecrans(2)
    resultat = rechercher_produits(
        etat_avec("monitor", critere("refresh_rate", Operateur.AU_MOINS, "144"), budget="400"),
        depot,
        tour_client=1,
        tolerance=TOLERANCE,
    )
    charge = en_tool_result(resultat)
    assert charge["candidats_trouves"] == 2
    produit = charge["produits"][0]
    assert {"id", "nom", "marque", "prix_usd", "specs"} <= set(produit)
    assert "panel_type" in produit["specs"]
    assert charge["traces"][0]["produit_id"] == produit["id"]


def test_la_recherche_separe_les_produits_hors_budget(depot):
    depot.produits = []
    depot.hors_budget = [fabriquer("monitor", 9, "420.00")]
    resultat = rechercher_produits(
        etat_avec("monitor", budget="400"), depot, tour_client=1, tolerance=TOLERANCE
    )
    charge = en_tool_result(resultat)
    assert charge["produits"] == []
    assert charge["au_dessus_du_budget"][0]["ecart_usd"] == "20.00"


def test_deux_recherches_sur_la_meme_categorie_dans_un_tour_passent(depot):
    depot.produits = ecrans(2)
    etat = etat_avec("monitor", budget="400")
    etat = rechercher_produits(etat, depot, tour_client=1, tolerance=TOLERANCE).etat
    rechercher_produits(etat, depot, tour_client=1, tolerance=TOLERANCE)


def test_la_garde_de_recherche_ne_survit_pas_au_tour(depot):
    depot.produits = ecrans(2)
    etat = etat_avec("monitor", budget="400")
    etat = rechercher_produits(etat, depot, tour_client=1, tolerance=TOLERANCE).etat
    etat = enregistrer_criteres(etat, ArgumentsEnregistrement(categorie="cpu"), tour_client=2).etat
    rechercher_produits(etat, depot, tour_client=2, tolerance=TOLERANCE)


def test_le_zero_resultat_porte_son_diagnostic(depot):
    """Le critère nº6 traverse la couche outils sans être reformulé."""
    depot.produits = []
    depot.releves.rouvre_si_retire["refresh_rate"] = 12
    etat = etat_avec(
        "monitor", critere("refresh_rate", Operateur.AU_MOINS, "240", Importance.BLOQUANT)
    )
    charge = en_tool_result(rechercher_produits(etat, depot, tour_client=1, tolerance=TOLERANCE))
    assert charge["diagnostic"]["motif"] == Motif.CRITERE_TROP_STRICT.value
    assert charge["diagnostic"]["propositions"][0]["champ"] == "refresh_rate"


# --------------------------------------------------------------------------- #
# demander_precision — terminal
# --------------------------------------------------------------------------- #


def test_la_demande_de_precision_est_terminale():
    resultat = demander_precision(
        etat_avec("monitor"), ArgumentsPrecision(question="Tu joues à quoi ?")
    )
    assert resultat.terminal is True
    assert en_tool_result(resultat) == {
        "ok": True,
        "terminal": True,
        "question": "Tu joues à quoi ?",
        "champ_vise": None,
    }


def test_la_demande_de_precision_peut_viser_le_budget():
    """`prix_usd` n'est pas un critère, mais c'est bien une question à poser."""
    resultat = demander_precision(
        etat_avec("monitor"),
        ArgumentsPrecision(question="Quel budget ?", champ_vise="prix_usd"),
    )
    assert resultat.champ_vise == "prix_usd"


def test_une_question_vide_est_refusee():
    with pytest.raises(ValueError):
        ArgumentsPrecision(question="")


def test_les_autres_outils_ne_sont_pas_terminaux(depot):
    depot.produits = ecrans(2)
    etat = etat_avec("monitor", budget="400")
    for resultat in (
        sonder_catalogue(etat, depot, tolerance=TOLERANCE),
        question_suivante(etat, depot, tolerance=TOLERANCE),
        rechercher_produits(etat, depot, tour_client=1, tolerance=TOLERANCE),
    ):
        assert resultat.terminal is False


# --------------------------------------------------------------------------- #
# La sérialisation
# --------------------------------------------------------------------------- #


def test_letat_de_session_nest_jamais_serialise(depot):
    """Envoyer au modèle l'objet même qui le contraint serait l'inviter à négocier."""
    depot.produits = ecrans(2)
    etat = etat_avec("monitor", budget="400")
    charges = [
        en_tool_result(
            enregistrer_criteres(etat, ArgumentsEnregistrement(categorie="monitor"), tour_client=2)
        ),
        en_tool_result(sonder_catalogue(etat, depot, tolerance=TOLERANCE)),
        en_tool_result(question_suivante(etat, depot, tolerance=TOLERANCE)),
        en_tool_result(rechercher_produits(etat, depot, tour_client=2, tolerance=TOLERANCE)),
    ]
    for charge in charges:
        assert "etat" not in str(charge)
        assert "tour_du_dernier_desserrage" not in str(charge)


def test_tout_resultat_se_serialise_en_json(depot):
    import json

    depot.produits = ecrans(2)
    etat = etat_avec("monitor", budget="400")
    json.dumps(en_tool_result(sonder_catalogue(etat, depot, tolerance=TOLERANCE)))
    json.dumps(en_tool_result(question_suivante(etat, depot, tolerance=TOLERANCE)))
    json.dumps(en_tool_result(rechercher_produits(etat, depot, tour_client=1, tolerance=TOLERANCE)))


def test_les_decimaux_partent_en_chaines():
    """Comme partout ailleurs dans le projet : un flottant JSON perdrait des décimales
    sur un prix, et le validateur de l'étape 9 compare des caractères."""
    resultat = enregistrer_criteres(
        EtatSession(),
        ArgumentsEnregistrement(
            categorie="monitor",
            criteres=(
                ArgumentsCritere(champ="refresh_rate", operateur=Operateur.AU_MOINS, valeur="144"),
            ),
            budget_usd="399.99",
        ),
        tour_client=1,
    )
    charge = en_tool_result(resultat)
    assert charge["budget_usd"] == "399.99"
    assert charge["criteres"][0]["valeur"] == "144"


def test_un_refus_se_serialise_comme_un_resultat():
    """Un refus fait partie du dialogue : le modèle lit, corrige, rappelle."""
    erreur = OutilRefuse(CodeRefus.CATEGORIE_ABSENTE, "message pédagogique")
    assert en_tool_result(erreur) == {
        "ok": False,
        "erreur": "categorie_absente",
        "message": "message pédagogique",
    }


def test_loptimisation_traverse_jusquau_resultat():
    resultat = enregistrer_criteres(
        EtatSession(),
        ArgumentsEnregistrement(categorie="monitor", optimisation=Optimisation.MOINS_CHER),
        tour_client=1,
    )
    assert en_tool_result(resultat)["optimisation"] == "moins_cher"
