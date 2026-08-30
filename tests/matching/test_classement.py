"""L'ordre est total et déterministe (arbitrage M).

`(score décroissant, critères évalués décroissant, prix croissant, id croissant)`.
Aucun ex æquo ne subsiste, donc aucun classement ne dépend de l'ordre dans lequel
Postgres a rendu ses lignes — et un test peut asserter une liste exacte.
"""

from decimal import Decimal

from conftest import fabriquer
from raiyon.matching.criteres import Critere, Importance, Operateur, RequeteMatching
from raiyon.matching.score import classer, evaluer_lot


def requete(*criteres):
    return RequeteMatching(categorie="cpu", criteres=criteres)


def critere(champ, operateur, valeur, importance=Importance.IMPORTANT):
    return Critere(champ=champ, operateur=operateur, valeur=valeur, importance=importance)


def test_lordre_est_total_meme_sur_des_produits_indiscernables():
    """Deux produits identiques jusqu'au prix se départagent sur l'identifiant."""
    jumeaux = [fabriquer("cpu", numero, "200") for numero in (3, 1, 2)]
    ordre = [e.produit.id for e in classer(evaluer_lot(jumeaux, requete()))]
    assert ordre == sorted(ordre)


def test_le_classement_ne_depend_pas_de_lordre_dentree():
    """Le même lot, mélangé, rend la même liste."""
    lot = [fabriquer("cpu", n, prix) for n, prix in enumerate(("300", "100", "200"), start=1)]
    ordre = [e.produit.id for e in classer(evaluer_lot(lot, requete()))]
    inverse = [e.produit.id for e in classer(evaluer_lot(lot[::-1], requete()))]
    assert ordre == inverse


def test_a_score_egal_le_produit_a_plus_de_criteres_evalues_passe_devant():
    """Le garde-fou de l'arbitrage F, et il est exercé contre le prix.

    Le produit incomplet est **moins cher** : sans ce terme de tri, il gagnerait par le
    départage, et l'absence de donnée deviendrait un avantage.
    """
    incomplet = fabriquer("cpu", 1, "100", boost_clock=None, core_clock=Decimal("4.1"))
    complet = fabriquer("cpu", 2, "300", boost_clock=Decimal("5.6"), core_clock=Decimal("4.1"))

    demande = requete(
        critere("boost_clock", Operateur.AU_MOINS, Decimal("5")),
        critere("core_clock", Operateur.AU_MOINS, Decimal("3")),
    )
    evaluations = {e.produit.id: e for e in evaluer_lot((incomplet, complet), demande)}
    assert evaluations[incomplet.id].score == evaluations[complet.id].score == 1
    assert evaluations[incomplet.id].criteres_evalues == 1
    assert evaluations[complet.id].criteres_evalues == 2

    ordre = [e.produit.id for e in classer(evaluations.values())]
    assert ordre == [complet.id, incomplet.id]


def test_un_meilleur_score_prime_sur_tout_le_reste():
    """Le score d'abord : le reste ne sert qu'à départager."""
    bon = fabriquer("cpu", 1, "2699.99", core_clock=Decimal("4.1"))
    mauvais = fabriquer("cpu", 2, "25", core_clock=Decimal("2.1"))
    demande = requete(critere("core_clock", Operateur.AU_MOINS, Decimal("4")))
    ordre = [e.produit.id for e in classer(evaluer_lot((mauvais, bon), demande))]
    assert ordre == [bon.id, mauvais.id]
