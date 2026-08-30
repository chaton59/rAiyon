"""Le prix : deux intentions distinctes, un plafond de poids, et rien par défaut.

C'est le fichier qui garde l'arbitrage H. Le moins cher et le mieux placé ne sont pas
le même produit ; si un jour ces deux classements se confondent, c'est ici que ça se
verra.
"""

from decimal import Decimal

from conftest import fabriquer
from raiyon.matching.criteres import (
    POIDS_PAR_IMPORTANCE,
    Critere,
    Importance,
    Operateur,
    Optimisation,
    RequeteMatching,
)
from raiyon.matching.score import PLAFOND_POIDS_PRIX, classer, evaluer_lot

FAIBLE = fabriquer("video-card", 1, "200", memory=Decimal("4"), core_clock=775, boost_clock=1335)
PUISSANTE = fabriquer(
    "video-card", 2, "500", memory=Decimal("24"), core_clock=2410, boost_clock=2970
)


def classement(optimisation, criteres=(), produits=(FAIBLE, PUISSANTE)):
    requete = RequeteMatching(categorie="video-card", criteres=criteres, optimisation=optimisation)
    return [evaluation.produit.id for evaluation in classer(evaluer_lot(produits, requete))]


def test_le_plafond_du_poids_du_prix_est_sous_le_plus_faible_critere_technique():
    """La règle dure de l'arbitrage H, énoncée comme une propriété et non un nombre.

    Tant que cette inégalité tient, un produit qui rate complètement un critère
    technique énoncé ne peut pas repasser devant par le prix seul.
    """
    assert min(POIDS_PAR_IMPORTANCE.values()) > PLAFOND_POIDS_PRIX


def test_moins_cher_et_rapport_qualite_prix_ne_classent_pas_pareil():
    """Deux demandes, deux réponses. C'est le test qui garde l'arbitrage H."""
    assert classement(Optimisation.MOINS_CHER)[0] == FAIBLE.id
    assert classement(Optimisation.RAPPORT_QUALITE_PRIX)[0] == PUISSANTE.id


def test_le_prix_ne_renverse_pas_un_critere_technique_enonce():
    """« Je veux 12 Go de VRAM et pas trop cher » ne finit pas sur une carte à 1 Go."""
    criteres = (
        Critere(
            champ="memory",
            operateur=Operateur.AU_MOINS,
            valeur=12,
            importance=Importance.SOUHAIT,
        ),
    )
    minuscule = fabriquer("video-card", 3, "108.99", memory=Decimal("1"))
    genereuse = fabriquer("video-card", 4, "2590", memory=Decimal("24"))

    ordre = classement(Optimisation.MOINS_CHER, criteres, (minuscule, genereuse))
    assert ordre == [genereuse.id, minuscule.id]


def test_sans_demande_explicite_le_prix_ne_marque_rien():
    """Le prix borne et départage ; il ne pondère pas. C'est le défaut, et c'est G2."""
    evaluations = evaluer_lot((FAIBLE, PUISSANTE), RequeteMatching(categorie="video-card"))
    for evaluation in evaluations:
        assert evaluation.score == 0
        assert not evaluation.avec_ligne_de_prix
        assert all(ligne.champ != "prix_usd" for ligne in evaluation.lignes)


def test_a_egalite_le_departage_se_fait_sur_le_prix():
    """Même score, même nombre de critères évalués : le moins cher passe devant."""
    ordre = classement(Optimisation.AUCUNE)
    assert ordre == [FAIBLE.id, PUISSANTE.id]


def test_le_rapport_qualite_prix_utilise_price_per_gb_quand_la_source_le_donne():
    """Sur `memory` et `internal-hard-drive`, le rapport naturel existe déjà.

    L'étape 5 l'a recalculé sur le prix retenu ; il est utilisable tel quel, et la
    trace nomme le champ dont le sous-score est sorti.
    """
    cher = fabriquer("memory", 1, "300", price_per_gb=Decimal("13.375"))
    economique = fabriquer("memory", 2, "300", price_per_gb=Decimal("2.170"))
    requete = RequeteMatching(categorie="memory", optimisation=Optimisation.RAPPORT_QUALITE_PRIX)

    evaluations = {e.produit.id: e for e in evaluer_lot((cher, economique), requete)}
    assert evaluations[economique.id].lignes[-1].champ == "price_per_gb"
    assert evaluations[economique.id].score == 1
    assert evaluations[cher.id].score == 0


def test_le_ratio_calcule_est_ramene_par_un_plafond_constant():
    """Jamais par le maximum du lot : sinon le meilleur rapport cesse d'être reproductible.

    Le même produit, comparé à un lot différent, garde exactement le même sous-score.
    """
    requete = RequeteMatching(
        categorie="video-card", optimisation=Optimisation.RAPPORT_QUALITE_PRIX
    )
    seule = evaluer_lot((PUISSANTE,), requete)[0]
    entouree = {
        e.produit.id: e
        for e in evaluer_lot((PUISSANTE, FAIBLE, fabriquer("video-card", 9, "62.99")), requete)
    }
    assert seule.score == entouree[PUISSANTE.id].score
    assert 0 < seule.score <= 1
