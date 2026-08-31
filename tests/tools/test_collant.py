"""La règle de collant, ligne à ligne — et le jeton de parole qui la borne.

Deux moitiés, et c'est volontaire :

* **`desserre()`** se teste sans état ni tour : c'est une fonction de trois arguments,
  et le tableau de l'arbitrage B se relit ici presque tel quel ;
* **le jeton** se teste sur des tours injectés à la main. La couche outils n'a aucune
  horloge : le numéro de tour vient de l'appelant, donc d'un entier dans un test.
"""

from decimal import Decimal

import pytest

from outils_de_test import critere, etat_avec
from raiyon.matching.attributs import ATTRIBUTS
from raiyon.matching.criteres import Critere, Importance, Operateur
from raiyon.tools.etat import DemandeBudget, desserre, fusionner

ECRAN = ATTRIBUTS["monitor"]
CASQUE = ATTRIBUTS["headphones"]


def pose(champ: str, operateur: Operateur, valeur: object, importance=Importance.SOUHAIT):
    """Un `Critere` déjà typé, tel qu'il vit dans l'état."""
    return Critere(champ=champ, operateur=operateur, valeur=valeur, importance=importance)


# --------------------------------------------------------------------------- #
# Le tableau de l'arbitrage B
# --------------------------------------------------------------------------- #


def test_ajouter_un_critere_sur_une_cle_libre_resserre():
    apres = pose("refresh_rate", Operateur.AU_MOINS, Decimal("144"))
    assert desserre(None, apres, ECRAN["refresh_rate"]) is False


def test_retirer_un_critere_desserre():
    avant = pose("refresh_rate", Operateur.AU_MOINS, Decimal("144"))
    assert desserre(avant, None, ECRAN["refresh_rate"]) is True


@pytest.mark.parametrize(
    ("avant", "apres", "attendu"),
    [
        (Importance.BLOQUANT, Importance.IMPORTANT, True),
        (Importance.BLOQUANT, Importance.SOUHAIT, True),
        (Importance.IMPORTANT, Importance.SOUHAIT, True),
        (Importance.SOUHAIT, Importance.IMPORTANT, False),
        (Importance.IMPORTANT, Importance.BLOQUANT, False),
        (Importance.BLOQUANT, Importance.BLOQUANT, False),
    ],
)
def test_le_sens_du_mouvement_dimportance(avant, apres, attendu):
    """`bloquant` > `important` > `souhait` : descendre desserre, monter est libre."""
    verdict = desserre(
        pose("refresh_rate", Operateur.AU_MOINS, Decimal("144"), avant),
        pose("refresh_rate", Operateur.AU_MOINS, Decimal("144"), apres),
        ECRAN["refresh_rate"],
    )
    assert verdict is attendu


@pytest.mark.parametrize(
    ("operateur", "avant", "apres", "attendu"),
    [
        (Operateur.AU_MOINS, "144", "120", True),
        (Operateur.AU_MOINS, "144", "165", False),
        (Operateur.AU_MOINS, "144", "144", False),
        (Operateur.AU_PLUS, "27", "32", True),
        (Operateur.AU_PLUS, "27", "24", False),
    ],
)
def test_le_sens_du_mouvement_de_valeur(operateur, avant, apres, attendu):
    """Un seuil qui recule est un desserrage, même à importance inchangée.

    C'est ce que l'étape 6 ne couvrait pas : passer `au_moins 144` à `au_moins 120`
    obtient exactement ce que la rétrogradation obtenait, sans toucher à l'importance.
    """
    champ = "refresh_rate" if operateur is Operateur.AU_MOINS else "screen_size"
    verdict = desserre(
        pose(champ, operateur, Decimal(avant)),
        pose(champ, operateur, Decimal(apres)),
        ECRAN[champ],
    )
    assert verdict is attendu


def test_egal_desserre_des_que_la_valeur_change():
    """On ne peut pas savoir sans le catalogue si l'autre valeur est plus rare."""
    assert (
        desserre(
            pose("panel_type", Operateur.EGAL, "IPS"),
            pose("panel_type", Operateur.EGAL, "VA"),
            ECRAN["panel_type"],
        )
        is True
    )


def test_un_booleen_qui_bascule_desserre():
    assert (
        desserre(
            pose("wireless", Operateur.EGAL, True),
            pose("wireless", Operateur.EGAL, False),
            CASQUE["wireless"],
        )
        is True
    )


def test_changer_doperateur_sur_le_meme_champ_desserre():
    """Traité comme retrait + ajout : « au moins 144 » puis « au plus 240 » laisse
    remonter tous les 60 Hz."""
    assert (
        desserre(
            pose("refresh_rate", Operateur.AU_MOINS, Decimal("144")),
            pose("refresh_rate", Operateur.AU_PLUS, Decimal("240")),
            ECRAN["refresh_rate"],
        )
        is True
    )


def test_le_verdict_est_un_ou_pas_un_et():
    """Desserrer par la valeur en resserrant par l'importance consomme quand même.

    La question posée est « **peut**-il faire remonter un produit ? », pas « le fait-il
    à coup sûr ? ». Le sens conservateur est le seul qui ne s'ouvre pas à une
    combinaison.
    """
    assert (
        desserre(
            pose("refresh_rate", Operateur.AU_MOINS, Decimal("144"), Importance.SOUHAIT),
            pose("refresh_rate", Operateur.AU_MOINS, Decimal("120"), Importance.BLOQUANT),
            ECRAN["refresh_rate"],
        )
        is True
    )


def test_le_non_mouvement_ne_desserre_pas():
    assert desserre(None, None, ECRAN["refresh_rate"]) is False


# --------------------------------------------------------------------------- #
# Le budget, par les mêmes lignes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("avant", "apres", "attendu"),
    [("300", "400", True), ("300", None, True), ("300", "200", False), (None, "300", False)],
)
def test_le_budget_suit_les_lignes_du_tableau(avant, apres, attendu):
    """Aucune règle propre au budget n'est écrite : il est présenté comme un `au_plus`."""
    etat = etat_avec("monitor", budget=avant)
    fusion = fusionner(etat, tour_client=2, categorie="monitor", budget=DemandeBudget(apres))
    consomme = fusion.etat.tour_du_dernier_desserrage == 2
    assert consomme is attendu
    if attendu:
        assert fusion.etat.budget_usd == (None if apres is None else Decimal(apres))


def test_un_budget_reecrit_a_lidentique_ne_bouge_pas():
    etat = etat_avec("monitor", budget="300")
    fusion = fusionner(etat, tour_client=2, categorie="monitor", budget=DemandeBudget("300.00"))
    assert fusion.appliques == ()
    assert fusion.etat.tour_du_dernier_desserrage is None


# --------------------------------------------------------------------------- #
# Le jeton de parole
# --------------------------------------------------------------------------- #


def test_un_desserrage_passe_et_consomme_le_jeton():
    etat = etat_avec("monitor", critere("refresh_rate", Operateur.AU_MOINS, "144"))
    fusion = fusionner(
        etat,
        tour_client=2,
        categorie="monitor",
        ajouts=[critere("refresh_rate", Operateur.AU_MOINS, "120")],
    )
    assert fusion.refuses == ()
    assert fusion.etat.tour_du_dernier_desserrage == 2
    assert fusion.etat.criteres_de("monitor")[0].valeur == Decimal("120")


def test_le_second_desserrage_du_meme_tour_est_refuse_et_le_reste_sapplique():
    """Un refus de jeton n'est pas une erreur : l'outil réussit et le dit."""
    etat = etat_avec(
        "monitor",
        critere("refresh_rate", Operateur.AU_MOINS, "144"),
        critere("screen_size", Operateur.AU_MOINS, "27"),
    )
    fusion = fusionner(
        etat,
        tour_client=2,
        categorie="monitor",
        ajouts=[
            critere("refresh_rate", Operateur.AU_MOINS, "120"),
            critere("screen_size", Operateur.AU_MOINS, "24"),
            critere("panel_type", Operateur.EGAL, "IPS"),
        ],
    )

    assert [m.champ for m in fusion.appliques] == ["refresh_rate", "panel_type"]
    assert [(r.champ, r.operateur) for r in fusion.refuses] == [("screen_size", Operateur.AU_MOINS)]
    assert fusion.etat.par_cle("monitor")[("screen_size", Operateur.AU_MOINS)].valeur == Decimal(
        "27"
    )
    assert "un seul assouplissement par message" in fusion.refuses[0].motif


# Le cas « deux desserrages dans deux tours différents passent tous les deux » est en
# tête des cas hostiles (`test_hostile.py`), exercé par la surface que le modèle voit :
# c'est là qu'il se lit avec les seize autres portes.


def test_le_jeton_deja_pris_par_un_appel_precedent_du_meme_tour_refuse_le_suivant():
    """Deux appels d'outil dans un même tour partagent le même jeton."""
    etat = etat_avec("monitor", critere("refresh_rate", Operateur.AU_MOINS, "144"))
    etat = fusionner(
        etat,
        tour_client=2,
        categorie="monitor",
        ajouts=[critere("refresh_rate", Operateur.AU_MOINS, "120")],
    ).etat
    fusion = fusionner(
        etat,
        tour_client=2,
        categorie="monitor",
        retraits=[("refresh_rate", Operateur.AU_MOINS)],
    )
    assert fusion.appliques == ()
    assert len(fusion.refuses) == 1
    assert fusion.etat.criteres_de("monitor")[0].valeur == Decimal("120")


def test_les_resserrages_ne_consomment_rien_et_passent_tous():
    etat = etat_avec("monitor", critere("refresh_rate", Operateur.AU_MOINS, "144"))
    fusion = fusionner(
        etat,
        tour_client=2,
        categorie="monitor",
        ajouts=[
            critere("refresh_rate", Operateur.AU_MOINS, "165"),
            critere("screen_size", Operateur.AU_MOINS, "27"),
            critere("panel_type", Operateur.EGAL, "IPS"),
        ],
        budget=DemandeBudget("250"),
    )
    assert fusion.refuses == ()
    assert len(fusion.appliques) == 4
    assert fusion.etat.tour_du_dernier_desserrage is None


def test_lordre_donne_par_le_modele_decide_qui_obtient_le_jeton():
    """Documenté et assumé : c'est ce que le client vient de dire qui prime, pas l'alphabet."""
    etat = etat_avec(
        "monitor",
        critere("refresh_rate", Operateur.AU_MOINS, "144"),
        critere("screen_size", Operateur.AU_MOINS, "27"),
    )
    fusion = fusionner(
        etat,
        tour_client=2,
        categorie="monitor",
        ajouts=[
            critere("screen_size", Operateur.AU_MOINS, "24"),
            critere("refresh_rate", Operateur.AU_MOINS, "120"),
        ],
    )
    assert [m.champ for m in fusion.appliques] == ["screen_size"]
    assert [r.champ for r in fusion.refuses] == ["refresh_rate"]
