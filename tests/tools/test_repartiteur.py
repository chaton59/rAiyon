"""Le répartiteur : parse, appelle, rend le nouvel état — et ne lève jamais.

C'est la pièce dont une erreur se propage partout : la boucle de l'étape 8 est sa seule
cliente, et elle ne sait rien faire d'autre que ce que le répartiteur lui rend. Ces
tests portent donc sur trois propriétés et rien d'autre :

1. les cinq noms du protocole atteignent les cinq fonctions, et **seulement** elles ;
2. l'état sort toujours, nouveau sur un succès, **inchangé** sur un refus ;
3. rien ne remonte en exception — un refus est une valeur.
"""

from decimal import Decimal

import pytest

from outils_de_test import TOLERANCE, DepotEnMemoire, critere, ecrans, etat_avec
from raiyon.matching.criteres import Importance, Operateur
from raiyon.tools.erreurs import CodeRefus, OutilRefuse
from raiyon.tools.etat import EtatSession
from raiyon.tools.outils import (
    ResultatEnregistrement,
    ResultatPrecision,
    ResultatQuestion,
    ResultatRecherche,
    ResultatSondage,
)
from raiyon.tools.repartiteur import NOMS, ContexteOutils, executer
from raiyon.tools.schema_outils import (
    NOM_ENREGISTRER,
    NOM_PRECISION,
    NOM_QUESTION,
    NOM_RECHERCHER,
    NOM_SONDER,
    schema_des_outils,
)


@pytest.fixture
def contexte(depot: DepotEnMemoire) -> ContexteOutils:
    """Tolérance injectée : aucun test de ce fichier ne lit `.env`."""
    return ContexteOutils(depot=depot, tour_client=1, tolerance=TOLERANCE)


ENREGISTREMENT_ECRAN = {
    "categorie": "monitor",
    "criteres": [
        {
            "champ": "refresh_rate",
            "operateur": "au_moins",
            "valeur": "144",
            "importance": "bloquant",
        }
    ],
    "budget_usd": "400",
}


# --------------------------------------------------------------------------- #
# Les cinq noms atteignent les cinq fonctions
# --------------------------------------------------------------------------- #


def test_les_noms_du_repartiteur_sont_ceux_du_schema():
    """Une divergence rendrait un outil annoncé au modèle et injoignable, ou l'inverse.

    C'est la seule assertion du fichier qui ne teste pas un comportement mais une
    correspondance ; elle vaut parce que les deux listes sont écrites dans deux modules,
    et que le schéma est ce que le modèle lit.
    """
    assert set(NOMS) == {outil["name"] for outil in schema_des_outils()}


def test_enregistrer_rend_un_etat_neuf_qui_porte_les_criteres(contexte):
    etat, resultat = executer(NOM_ENREGISTRER, ENREGISTREMENT_ECRAN, EtatSession(), contexte)

    assert isinstance(resultat, ResultatEnregistrement)
    assert etat.categorie_courante == "monitor"
    assert etat.budget_usd == Decimal("400")
    assert [critere.champ for critere in etat.criteres_de("monitor")] == ["refresh_rate"]


def test_sonder_rend_des_agregats_et_un_etat_inchange(contexte, depot, etat_ecran):
    depot.produits = ecrans(3, refresh_rate=165)

    etat, resultat = executer(NOM_SONDER, {"champs": ["refresh_rate"]}, etat_ecran, contexte)

    assert isinstance(resultat, ResultatSondage)
    assert resultat.dans_le_budget == 3
    assert etat == etat_ecran


def test_question_suivante_ne_prend_rien_et_repond(contexte, depot, etat_ecran):
    depot.produits = ecrans(3, refresh_rate=165)

    etat, resultat = executer(NOM_QUESTION, {}, etat_ecran, contexte)

    assert isinstance(resultat, ResultatQuestion)
    assert etat == etat_ecran


def test_rechercher_pose_la_garde_de_tour_dans_letat_rendu(contexte, depot, etat_ecran):
    """C'est **la** propriété dont dépend l'arbitrage E, et elle est ici, pas plus loin.

    Si le répartiteur rendait l'état reçu au lieu de celui du résultat, la garde « un
    tour, une catégorie » ne s'armerait jamais et le test nº4 de la boucle échouerait
    sans qu'on sache où regarder.
    """
    depot.produits = ecrans(2, refresh_rate=165)

    etat, resultat = executer(NOM_RECHERCHER, {}, etat_ecran, contexte)

    assert isinstance(resultat, ResultatRecherche)
    assert etat.recherche_du_tour is not None
    assert etat.recherche_du_tour.categorie == "monitor"
    assert etat.recherche_du_tour.tour_client == 1


def test_demander_precision_est_terminal(contexte, etat_ecran):
    _, resultat = executer(NOM_PRECISION, {"question": "Plutôt IPS ou VA ?"}, etat_ecran, contexte)

    assert isinstance(resultat, ResultatPrecision)
    assert resultat.terminal is True
    assert resultat.question == "Plutôt IPS ou VA ?"


# --------------------------------------------------------------------------- #
# Les refus sont des valeurs, jamais des exceptions
# --------------------------------------------------------------------------- #


def test_outil_inconnu_rend_un_refus_code_outil_inconnu(contexte, etat_ecran):
    """Le mode `strict` de l'API garantit les noms d'outils ; le repli le retire."""
    etat, resultat = executer("search_the_web", {}, etat_ecran, contexte)

    assert isinstance(resultat, OutilRefuse)
    assert resultat.code is CodeRefus.OUTIL_INCONNU
    assert etat == etat_ecran
    # Le message dit quoi faire : il liste les outils qui existent.
    for nom in NOMS:
        assert nom in resultat.message


def test_propriete_inventee_rend_un_refus_qui_nomme_le_champ(contexte):
    """`extra="forbid"` : un argument inventé est une erreur, pas un oubli."""
    etat, resultat = executer(
        NOM_ENREGISTRER, {**ENREGISTREMENT_ECRAN, "urgence": "haute"}, EtatSession(), contexte
    )

    assert isinstance(resultat, OutilRefuse)
    assert resultat.code is CodeRefus.VALEUR_ILLISIBLE
    # Le message de Pydantic part verbatim : il nomme le champ fautif, ce qu'une
    # reformulation perdrait.
    assert "urgence" in resultat.message
    assert etat == EtatSession()


def test_valeur_non_numerique_sur_un_champ_numerique_est_refusee(contexte):
    """« beaucoup » n'est rien : `valeur` est toujours une chaîne, pas n'importe laquelle."""
    entree = {
        "categorie": "monitor",
        "criteres": [
            {
                "champ": "refresh_rate",
                "operateur": "au_moins",
                "valeur": "beaucoup",
                "importance": "bloquant",
            }
        ],
    }

    etat, resultat = executer(NOM_ENREGISTRER, entree, EtatSession(), contexte)

    assert isinstance(resultat, OutilRefuse)
    assert etat == EtatSession()


def test_un_invariant_viole_rend_un_refus_sans_toucher_a_letat(contexte, depot, etat_ecran):
    """Deux catégories dans un tour : le refus vient de l'outil, pas de Pydantic."""
    depot.produits = ecrans(2, refresh_rate=165)
    etat, _ = executer(NOM_RECHERCHER, {}, etat_ecran, contexte)
    etat, _ = executer(
        NOM_ENREGISTRER, {"categorie": "cpu", "criteres": []}, etat, ContexteOutils(depot, 2)
    )

    apres, resultat = executer(NOM_RECHERCHER, {}, etat, ContexteOutils(depot, 1, TOLERANCE))

    assert isinstance(resultat, OutilRefuse)
    assert resultat.code is CodeRefus.DEUX_CATEGORIES_DANS_UN_TOUR
    assert apres == etat


def test_sans_categorie_le_sondage_refuse_plutot_que_de_lever(contexte):
    etat, resultat = executer(NOM_SONDER, {}, EtatSession(), contexte)

    assert isinstance(resultat, OutilRefuse)
    assert resultat.code is CodeRefus.CATEGORIE_ABSENTE
    assert etat == EtatSession()


@pytest.mark.parametrize("nom", [NOM_QUESTION, NOM_RECHERCHER])
def test_un_argument_sur_un_outil_qui_nen_prend_pas_est_refuse(contexte, depot, etat_ecran, nom):
    """Ignorer l'argument serait pire que le refuser, et c'est le point.

    Un modèle qui passe des critères à `search_products` et reçoit un résultat croirait
    qu'ils ont filtré la recherche : il décrirait ensuite les produits comme satisfaisant
    des contraintes jamais appliquées. Le refus lui dit où les critères entrent.
    """
    depot.produits = ecrans(2, refresh_rate=165)

    etat, resultat = executer(nom, {"criteres": [{"champ": "refresh_rate"}]}, etat_ecran, contexte)

    assert isinstance(resultat, OutilRefuse)
    assert NOM_ENREGISTRER in resultat.message
    assert etat == etat_ecran


# --------------------------------------------------------------------------- #
# Le jeton de parole traverse le répartiteur sans être réinventé
# --------------------------------------------------------------------------- #


def test_le_tour_client_du_contexte_porte_le_jeton_de_parole(depot):
    """Deux desserrages dans le même tour : le second est refusé, et par `fusionner()`.

    Le répartiteur ne compte rien — il transmet `contexte.tour_client`. Ce test le
    constate en changeant le contexte plutôt qu'en appelant deux fois : c'est la seule
    façon de vérifier que le numéro vient bien de l'extérieur.
    """
    contexte = ContexteOutils(depot=depot, tour_client=7, tolerance=TOLERANCE)
    etat = etat_avec(
        "monitor",
        critere("refresh_rate", Operateur.AU_MOINS, "144", Importance.BLOQUANT),
        budget="400",
        tour_client=7,
    )

    # Premier desserrage du tour 7 : le budget monte. Accepté, jeton consommé.
    etat, premier = executer(
        NOM_ENREGISTRER, {"categorie": "monitor", "budget_usd": "600"}, etat, contexte
    )
    assert isinstance(premier, ResultatEnregistrement)
    assert premier.mouvements_refuses == ()
    assert etat.budget_usd == Decimal("600")

    # Second desserrage du **même** tour : refusé, et le critère reste en place.
    etat, second = executer(
        NOM_ENREGISTRER,
        {
            "categorie": "monitor",
            "criteres": [
                {
                    "champ": "refresh_rate",
                    "operateur": "au_moins",
                    "valeur": "120",
                    "importance": "bloquant",
                }
            ],
        },
        etat,
        contexte,
    )
    assert isinstance(second, ResultatEnregistrement)
    assert second.mouvements_refuses != ()
    assert etat.criteres_de("monitor")[0].valeur == Decimal("144")
