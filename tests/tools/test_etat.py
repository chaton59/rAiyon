"""L'état de session : indexation par catégorie, forme JSONB, requête vers le moteur."""

from decimal import Decimal

import pytest

from outils_de_test import critere, etat_avec
from raiyon.matching.attributs import ATTRIBUTS
from raiyon.matching.criteres import Importance, Operateur, Optimisation
from raiyon.tools.erreurs import CodeRefus, OutilRefuse
from raiyon.tools.etat import (
    CritereTexte,
    DemandeBudget,
    EtatSession,
    depuis_jsonb,
    fusionner,
    valeur_depuis_texte,
    valeur_en_texte,
)


def test_un_critere_entre_typé_depuis_du_texte():
    """`"144"` devient un `Decimal`, parce que le registre dit que c'est un nombre."""
    etat = etat_avec("monitor", critere("refresh_rate", Operateur.AU_MOINS, "144"))
    (pose,) = etat.criteres_de("monitor")
    assert pose.valeur == Decimal("144")
    assert isinstance(pose.valeur, Decimal)


def test_un_booleen_entre_depuis_true_ou_false():
    etat = etat_avec("headphones", critere("wireless", Operateur.EGAL, "true"))
    (pose,) = etat.criteres_de("headphones")
    assert pose.valeur is True


def test_les_deux_bornes_dun_intervalle_cohabitent_sur_le_meme_champ():
    """La clé de fusion est `(champ, opérateur)`, jamais le champ seul."""
    etat = etat_avec(
        "monitor",
        critere("screen_size", Operateur.AU_MOINS, "24"),
        critere("screen_size", Operateur.AU_PLUS, "27"),
    )
    assert len(etat.criteres_de("monitor")) == 2


def test_letat_est_indexe_par_categorie_et_le_client_retrouve_ce_quil_a_dit():
    """Revenir à l'écran rend ses critères ; cela ne crée aucun panier (arbitrage D)."""
    etat = etat_avec("monitor", critere("refresh_rate"))
    etat = fusionner(
        etat, tour_client=2, categorie="video-card", ajouts=[critere("memory", valeur="12")]
    ).etat
    etat = fusionner(etat, tour_client=3, categorie="monitor").etat

    assert etat.categorie_courante == "monitor"
    assert [c.champ for c in etat.criteres_de("monitor")] == ["refresh_rate"]
    assert [c.champ for c in etat.criteres_de("video-card")] == ["memory"]


def test_le_changement_de_categorie_remet_le_budget_a_none():
    """« 300 $ pour l'écran » ne doit pas s'appliquer au SSD (arbitrage D)."""
    etat = etat_avec("monitor", budget="300")
    assert etat.budget_usd == Decimal("300")

    etat = fusionner(etat, tour_client=2, categorie="internal-hard-drive").etat
    assert etat.budget_usd is None


def test_le_changement_de_categorie_consomme_le_jeton_sil_efface_un_budget():
    """C'est la ligne « budget qui passe à None » de l'arbitrage B, sans exemption.

    Sans elle, le trou était inter-tours — donc invisible pour une borne posée par
    tour : partir sur `cpu` au tour 5, revenir sur `monitor` au tour 6, et chercher sans
    plafond.
    """
    etat = etat_avec("monitor", budget="300")
    fusion = fusionner(etat, tour_client=2, categorie="cpu")
    assert fusion.etat.budget_usd is None
    assert fusion.etat.tour_du_dernier_desserrage == 2


def test_le_changement_de_categorie_sans_budget_est_gratuit():
    """Sans budget en vigueur, un aller-retour n'efface rien : il n'y a rien à tarifer."""
    etat = etat_avec("monitor")
    fusion = fusionner(etat, tour_client=2, categorie="cpu")
    assert fusion.etat.tour_du_dernier_desserrage is None


def test_changer_de_categorie_et_poser_un_budget_passe_en_un_seul_appel():
    """« Maintenant un SSD, 100 $ » : le changement paie, le budget posé depuis None
    est un resserrage, donc libre."""
    etat = etat_avec("monitor", budget="300")
    fusion = fusionner(
        etat,
        tour_client=2,
        categorie="internal-hard-drive",
        budget=DemandeBudget("100"),
        ajouts=[critere("capacity", Operateur.AU_MOINS, "1000")],
    )
    assert fusion.refuses == ()
    assert fusion.etat.budget_usd == Decimal("100")
    assert fusion.etat.categorie_courante == "internal-hard-drive"


def test_changer_de_categorie_sans_jeton_echoue_plutot_que_de_sappliquer_a_moitie():
    """Il n'y a pas de demi-changement de sujet."""
    etat = etat_avec("monitor", critere("refresh_rate", Operateur.AU_MOINS, "144"), budget="300")
    etat = fusionner(
        etat,
        tour_client=2,
        categorie="monitor",
        ajouts=[critere("refresh_rate", Operateur.AU_MOINS, "120")],
    ).etat

    with pytest.raises(OutilRefuse) as refus:
        fusionner(etat, tour_client=2, categorie="cpu")
    assert refus.value.code is CodeRefus.CHANGEMENT_DE_CATEGORIE_SANS_JETON


def test_laller_retour_de_categorie_coute_un_jeton_par_effacement():
    """Deux tours, deux jetons : la règle tarife l'aller-retour au lieu de l'offrir."""
    etat = etat_avec("monitor", budget="300")
    etat = fusionner(etat, tour_client=2, categorie="cpu").etat
    fusion = fusionner(etat, tour_client=3, categorie="monitor")
    assert fusion.etat.categorie_courante == "monitor"
    # Le retour ne coûte rien : il n'y avait plus de budget à effacer. C'est la limite
    # écrite au §7 — la règle tarife le premier effacement, elle ne le rend pas
    # impossible.
    assert fusion.etat.tour_du_dernier_desserrage == 2


def test_redire_a_lidentique_ne_produit_aucun_mouvement():
    """Un modèle qui récapitule l'état à chaque tour ne se punit pas lui-même."""
    etat = etat_avec("monitor", critere("refresh_rate", Operateur.AU_MOINS, "144"))
    fusion = fusionner(
        etat,
        tour_client=2,
        categorie="monitor",
        ajouts=[critere("refresh_rate", Operateur.AU_MOINS, "144")],
    )
    assert fusion.appliques == ()
    assert fusion.refuses == ()
    assert fusion.etat.tour_du_dernier_desserrage is None


def test_retirer_un_critere_absent_est_un_non_evenement():
    etat = etat_avec("monitor")
    fusion = fusionner(
        etat,
        tour_client=2,
        categorie="monitor",
        retraits=[("refresh_rate", Operateur.AU_MOINS)],
    )
    assert fusion.appliques == ()
    assert fusion.etat.tour_du_dernier_desserrage is None


def test_un_critere_reecrit_garde_sa_place_dans_la_liste():
    """Sinon un simple changement d'importance ferait défiler l'ordre de l'état persisté."""
    etat = etat_avec(
        "monitor",
        critere("refresh_rate", Operateur.AU_MOINS, "144"),
        critere("screen_size", Operateur.AU_MOINS, "27"),
    )
    etat = fusionner(
        etat,
        tour_client=2,
        categorie="monitor",
        ajouts=[critere("refresh_rate", Operateur.AU_MOINS, "144", Importance.BLOQUANT)],
    ).etat
    assert [c.champ for c in etat.criteres_de("monitor")] == ["refresh_rate", "screen_size"]


def test_changer_doptimisation_est_libre():
    """Elle ne touche pas l'ensemble des candidats, seulement son ordre.

    Elle ne peut donc pas transformer un zéro résultat en résultat — le seul mode
    d'échec que le jeton vise. Elle change bien **quels** produits sont montrés, la
    limite étant de trois.
    """
    etat = etat_avec("monitor")
    fusion = fusionner(
        etat, tour_client=2, categorie="monitor", optimisation=Optimisation.MOINS_CHER
    )
    assert fusion.etat.optimisation is Optimisation.MOINS_CHER
    assert fusion.etat.tour_du_dernier_desserrage is None


# --------------------------------------------------------------------------- #
# La forme JSONB — arrêtée maintenant pour qu'aucune migration ne soit nécessaire
# --------------------------------------------------------------------------- #


def test_la_forme_jsonb_est_celle_de_larbitrage_d():
    etat = etat_avec(
        "monitor",
        critere("refresh_rate", Operateur.AU_MOINS, "144", Importance.BLOQUANT),
        budget="400",
    )
    etat = fusionner(etat, tour_client=2, categorie="video-card").etat

    assert etat.en_jsonb() == {
        "categorie_courante": "video-card",
        "criteres": {
            "monitor": [
                {
                    "champ": "refresh_rate",
                    "operateur": "au_moins",
                    "valeur": "144",
                    "importance": "bloquant",
                }
            ],
            "video-card": [],
        },
        "optimisation": "aucune",
        # Le passage à `video-card` a effacé le budget de 400 USD : c'est un
        # desserrage, et il a donc consommé le jeton du tour 2.
        "tour_du_dernier_desserrage": 2,
    }


def test_le_budget_nest_pas_dans_le_jsonb():
    """Il garde sa colonne : deux copies d'une même contrainte divergent (§3.10)."""
    etat = etat_avec("monitor", budget="400")
    assert "budget" not in str(etat.en_jsonb())


def test_laller_retour_jsonb_redonne_le_meme_etat():
    """La persistance de l'étape 10 ne doit rien perdre de ce que le client a dit."""
    etat = etat_avec(
        "monitor",
        critere("refresh_rate", Operateur.AU_MOINS, "144", Importance.BLOQUANT),
        critere("panel_type", Operateur.EGAL, "IPS", Importance.IMPORTANT),
        budget="400",
    )
    relu = depuis_jsonb(etat.en_jsonb(), budget_usd=etat.budget_usd)

    assert relu.categorie_courante == etat.categorie_courante
    assert relu.criteres_de("monitor") == etat.criteres_de("monitor")
    assert relu.budget_usd == Decimal("400")
    assert relu.en_jsonb() == etat.en_jsonb()


def test_le_jsonb_relu_est_revalide():
    """Une ligne corrompue s'arrête ici, pas trois couches plus loin dans une requête."""
    with pytest.raises(ValueError):
        depuis_jsonb({"categorie_courante": "perceuse", "criteres": {}})


def test_le_jsonb_relu_refuse_un_champ_inconnu():
    corrompu = {
        "categorie_courante": "monitor",
        "criteres": {"monitor": [{"champ": "inexistant", "operateur": "egal", "valeur": "x"}]},
    }
    with pytest.raises(OutilRefuse):
        depuis_jsonb(corrompu)


def test_letat_vide_se_serialise_sans_perdre_la_forme():
    assert depuis_jsonb(EtatSession().en_jsonb()).en_jsonb() == EtatSession().en_jsonb()


# --------------------------------------------------------------------------- #
# La conversion texte ↔ valeur
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("champ", "texte", "attendu"),
    [
        ("refresh_rate", "144", Decimal("144")),
        ("screen_size", "27.5", Decimal("27.5")),
        ("panel_type", "IPS", "IPS"),
    ],
)
def test_valeur_depuis_texte(champ, texte, attendu):
    assert valeur_depuis_texte(ATTRIBUTS["monitor"][champ], texte) == attendu


@pytest.mark.parametrize("texte", ["beaucoup", "", "NaN", "Infinity"])
def test_une_valeur_numerique_illisible_est_refusee(texte):
    """`Decimal` accepte « NaN » et « Infinity » : les laisser passer empoisonnerait
    toutes les comparaisons en aval, silencieusement."""
    with pytest.raises(OutilRefuse) as refus:
        valeur_depuis_texte(ATTRIBUTS["monitor"]["refresh_rate"], texte)
    assert refus.value.code is CodeRefus.VALEUR_ILLISIBLE


def test_valeur_en_texte_est_linverse_de_valeur_depuis_texte():
    attribut = ATTRIBUTS["headphones"]["wireless"]
    assert valeur_en_texte(valeur_depuis_texte(attribut, "true")) == "true"
    assert valeur_en_texte(valeur_depuis_texte(attribut, "false")) == "false"


# --------------------------------------------------------------------------- #
# La requête vers le moteur — le seul chemin
# --------------------------------------------------------------------------- #


def test_la_requete_reprend_letat_et_rien_dautre():
    etat = etat_avec(
        "monitor",
        critere("refresh_rate", Operateur.AU_MOINS, "144", Importance.BLOQUANT),
        budget="400",
    )
    requete = etat.requete()
    assert requete.categorie == "monitor"
    assert requete.budget_usd == Decimal("400")
    assert [c.champ for c in requete.criteres] == ["refresh_rate"]


def test_une_requete_sans_categorie_courante_est_impossible():
    with pytest.raises(ValueError):
        EtatSession().requete()


def test_le_budget_nentre_jamais_dans_les_criteres():
    """`prix_usd` est un champ dédié : le critère de budget de `desserre()` ne fuit pas."""
    etat = etat_avec("monitor", budget="400")
    assert all(c.champ != "prix_usd" for c in etat.criteres_de("monitor"))
    assert "prix_usd" not in str(etat.en_jsonb())


def test_une_categorie_inconnue_est_refusee():
    with pytest.raises(OutilRefuse) as refus:
        fusionner(EtatSession(), tour_client=1, categorie="perceuse", ajouts=[])
    assert refus.value.code is CodeRefus.CATEGORIE_INCONNUE


def test_le_budget_veut_deux_decimales_au_plus():
    with pytest.raises(OutilRefuse) as refus:
        fusionner(
            EtatSession(),
            tour_client=1,
            categorie="monitor",
            budget=DemandeBudget("199.999"),
        )
    assert refus.value.code is CodeRefus.VALEUR_ILLISIBLE


def test_un_budget_negatif_est_refuse():
    with pytest.raises(OutilRefuse):
        fusionner(EtatSession(), tour_client=1, categorie="monitor", budget=DemandeBudget("-10"))


def test_critere_texte_expose_sa_cle():
    entrant = CritereTexte(champ="refresh_rate", operateur=Operateur.AU_MOINS, valeur="144")
    assert entrant.cle == ("refresh_rate", Operateur.AU_MOINS)
