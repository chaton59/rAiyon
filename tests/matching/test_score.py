"""Sous-scores, bornes, winsorisation, renormalisation. Tout est pur, rien n'est mocké.

Les bornes utilisées sont celles du registre, calibrées sur le seed committé : ces
tests exercent donc les vraies constantes, pas des valeurs de laboratoire.
"""

from decimal import Decimal

import pytest

from conftest import fabriquer
from raiyon.matching.attributs import ATTRIBUTS
from raiyon.matching.criteres import Critere, Importance, Operateur, resoudre_critere
from raiyon.matching.score import (
    PLANCHER_SATISFAISANT,
    agreger,
    evaluer_critere,
    normaliser,
)
from raiyon.matching.trace import Statut


def resolu(categorie, champ, operateur, valeur, importance=Importance.IMPORTANT):
    return resoudre_critere(
        categorie,
        Critere(champ=champ, operateur=operateur, valeur=valeur, importance=importance),
    )


def test_la_borne_basse_vaut_zero_et_la_borne_haute_vaut_un():
    assert normaliser(Decimal("60"), Decimal("60"), Decimal("240")) == 0
    assert normaliser(Decimal("240"), Decimal("60"), Decimal("240")) == 1
    assert normaliser(Decimal("150"), Decimal("60"), Decimal("240")) == Decimal("0.5")


def test_au_dela_des_bornes_le_sous_score_est_borne():
    """C'est la winsorisation : au-delà, on ne gagne plus de points."""
    assert normaliser(Decimal("600"), Decimal("60"), Decimal("240")) == 1
    assert normaliser(Decimal("30"), Decimal("60"), Decimal("240")) == 0


def sous_score(categorie, champ, operateur, seuil, valeur):
    """Sous-score d'une valeur pour un critère donné, sans passer par un produit entier."""
    return evaluer_critere(
        fabriquer(categorie, 1, "200", **{champ: valeur}),
        resolu(categorie, champ, operateur, seuil, Importance.SOUHAIT),
    ).sous_score


def test_un_critere_au_plus_inverse_le_sens():
    """« Au plus 65 W » : plus le TDP est bas, meilleur est le sous-score."""
    frugal = fabriquer("cpu", 1, "200", tdp=35)
    gourmand = fabriquer("cpu", 2, "200", tdp=165)
    critere = resolu("cpu", "tdp", Operateur.AU_PLUS, 65, Importance.SOUHAIT)

    assert evaluer_critere(frugal, critere).sous_score == 1
    assert evaluer_critere(gourmand, critere).sous_score == 0


def test_un_plafond_classe_le_plus_grand_qui_rentre_en_tete():
    """Le test qui manquait, et le défaut qu'il garde.

    `screen_size` est calibré `[21,5 ; 34]` et son `sens` est « plus haut vaut mieux ».
    Sur « un écran d'au plus 24 pouces », faire décider la direction par l'opérateur
    seul mettait le **21,5″ en tête** (1,00 contre 0,80 au 24″). Le client qui pose un
    plafond veut le plus grand qui rentre, pas le plus petit qui existe.

    C'est la seule des quatre configurations où l'opérateur et le `sens` divergent, donc
    la seule qui révèle le problème — et `cpu.tdp`, sur lequel portait le test
    précédent, ne pouvait pas le voir : son `sens` dit déjà la même chose que
    l'opérateur.
    """
    juste = sous_score("monitor", "screen_size", Operateur.AU_PLUS, 24, Decimal("24"))
    petit = sous_score("monitor", "screen_size", Operateur.AU_PLUS, 24, Decimal("21.5"))

    assert juste > petit
    assert juste == 1
    assert petit == Decimal("0.5")


@pytest.mark.parametrize(
    ("categorie", "champ", "operateur", "seuil", "gagnant", "perdant"),
    [
        ("monitor", "refresh_rate", Operateur.AU_MOINS, 144, 240, 144),
        ("monitor", "screen_size", Operateur.AU_PLUS, 24, Decimal("24"), Decimal("21.5")),
        ("cpu", "tdp", Operateur.AU_PLUS, 65, 35, 65),
        ("memory", "price_per_gb", Operateur.AU_PLUS, 5, Decimal("0.05"), Decimal("4.90")),
    ],
)
def test_les_quatre_configurations_de_direction(
    categorie, champ, operateur, seuil, gagnant, perdant
):
    """Les quatre lignes du tableau de `sous_score_numerique`, en assertions d'ordre.

    Deux valeurs qui **satisfont toutes les deux** le critère : c'est le `sens` du
    registre, et lui seul, qui les départage.
    """
    assert sous_score(categorie, champ, operateur, seuil, gagnant) > sous_score(
        categorie, champ, operateur, seuil, perdant
    )


@pytest.mark.parametrize(
    ("categorie", "champ", "operateur", "seuil", "satisfaisantes", "ratees"),
    [
        ("monitor", "refresh_rate", Operateur.AU_MOINS, 144, (144, 165, 240), (60, 120, 143)),
        ("cpu", "tdp", Operateur.AU_PLUS, 65, (35, 50, 65), (66, 105, 165)),
    ],
)
def test_une_valeur_ratee_marque_toujours_moins_quune_valeur_satisfaisante(
    categorie, champ, operateur, seuil, satisfaisantes, ratees
):
    """La frontière est **stricte** dans les deux sens, et elle passe à 0,5.

    Sans cette garantie, un produit qui rate le critère de peu pourrait devancer un
    produit qui le satisfait tout juste — ce qui rendrait le sous-score illisible sans
    consulter le statut à côté.
    """
    scores_ok = [sous_score(categorie, champ, operateur, seuil, v) for v in satisfaisantes]
    scores_ko = [sous_score(categorie, champ, operateur, seuil, v) for v in ratees]

    assert min(scores_ok) >= PLANCHER_SATISFAISANT
    assert max(scores_ko) < PLANCHER_SATISFAISANT


def test_un_seuil_au_dela_de_la_borne_haute_ne_casse_pas_la_regle():
    """« Au moins 500 Hz » sur des bornes `[60, 240]` : la région satisfaisante est vide.

    Rien à ordonner, donc rien à diviser : la fonction ne lève pas et reste dans
    `[0, 1]`. Un écran qui atteindrait 500 Hz est pleinement satisfaisant, faute
    d'échelle pour dire qu'il l'est plus ou moins.
    """
    assert sous_score("monitor", "refresh_rate", Operateur.AU_MOINS, 500, 600) == 1
    rate = sous_score("monitor", "refresh_rate", Operateur.AU_MOINS, 500, 240)
    assert 0 <= rate < PLANCHER_SATISFAISANT


def test_un_seuil_en_deca_de_la_borne_basse_ne_casse_pas_la_regle():
    """« Au plus 10 pouces » sur `[21,5 ; 34]` : la région rejetée couvre tout le catalogue."""
    assert sous_score("monitor", "screen_size", Operateur.AU_PLUS, 10, Decimal("9")) == 1
    rate = sous_score("monitor", "screen_size", Operateur.AU_PLUS, 10, Decimal("27"))
    assert 0 <= rate < PLANCHER_SATISFAISANT


def test_un_seuil_sous_toute_lechelle_met_les_ratees_au_plancher():
    """« Au moins 30 Hz » sur `[60, 240]` : ce qui rate est hors échelle, pas un peu moins bon."""
    assert sous_score("monitor", "refresh_rate", Operateur.AU_MOINS, 30, 20) == 0


def test_un_critere_egal_score_la_proximite():
    """« Exactement 1 To » ne doit pas classer le 16 To en tête."""
    critere = resolu("internal-hard-drive", "capacity", Operateur.EGAL, 1000, Importance.SOUHAIT)
    juste = evaluer_critere(fabriquer("internal-hard-drive", 1, "90", capacity=1000), critere)
    enorme = evaluer_critere(fabriquer("internal-hard-drive", 2, "900", capacity=16000), critere)

    assert juste.sous_score == 1
    assert juste.statut is Statut.MATCHE
    # 15 000 Go d'écart sur une amplitude de bornes de 15 880 : il reste des miettes,
    # et c'est bien ainsi — un `au_moins` aurait mis ce disque en tête du classement.
    assert enorme.sous_score < Decimal("0.1")
    assert enorme.statut is Statut.PARTIEL


def test_la_winsorisation_ecrase_la_queue_lourde_de_price_per_gb():
    """497,5 USD/GB est une valeur réelle du catalogue ; la borne haute vaut 13,375.

    Sans plafonnement, ce seul produit tasserait tous les autres dans un mouchoir de
    poche — et c'est exactement ce que `schema_attributs.md` demandait de borner.
    """
    attribut = ATTRIBUTS["memory"]["price_per_gb"]
    assert attribut.borne_haute == Decimal("13.375")

    aberrant = fabriquer("memory", 1, "500", price_per_gb=Decimal("497.500"))
    correct = fabriquer("memory", 2, "100", price_per_gb=Decimal("2.170"))
    critere = resolu("memory", "price_per_gb", Operateur.AU_PLUS, Decimal("5"))

    assert evaluer_critere(aberrant, critere).sous_score == 0
    assert evaluer_critere(correct, critere).sous_score == 1


def test_une_valeur_absente_rend_le_critere_indisponible():
    """Ni 0 (qui punirait l'absence), ni 0,5 (qui inventerait une médiane)."""
    ligne = evaluer_critere(
        fabriquer("cpu", 1, "200", boost_clock=None),
        resolu("cpu", "boost_clock", Operateur.AU_MOINS, Decimal("5")),
    )
    assert ligne.statut is Statut.INDISPONIBLE
    assert ligne.sous_score is None
    assert ligne.poids is None


def test_les_poids_sont_renormalises_sur_les_criteres_disponibles():
    """Le critère indisponible sort du numérateur **et** du dénominateur (arbitrage F)."""
    produit = fabriquer("cpu", 1, "200", boost_clock=None, core_clock=Decimal("4.1"))
    lignes = (
        evaluer_critere(produit, resolu("cpu", "boost_clock", Operateur.AU_MOINS, Decimal("5"))),
        evaluer_critere(produit, resolu("cpu", "core_clock", Operateur.AU_MOINS, Decimal("3"))),
    )
    disponibles = [ligne for ligne in lignes if ligne.sous_score is not None]

    assert sum(ligne.poids for ligne in disponibles) == Decimal("2")
    # Le score vaut le sous-score restant, entier : les poids ont bien été renormalisés
    # et non pas divisés par le total initial de 4.
    assert agreger(lignes) == disponibles[0].sous_score == 1


def test_sans_aucun_critere_scorable_le_score_vaut_zero():
    """Ce n'est pas un échec : c'est le cas nominal quand tout est en filtre dur."""
    assert agreger(()) == 0


def test_un_statut_partiel_est_entre_le_matche_et_le_rate():
    """La valeur ne satisfait pas la demande, mais n'est pas au plancher."""
    ligne = evaluer_critere(
        fabriquer("monitor", 1, "300", refresh_rate=120),
        resolu("monitor", "refresh_rate", Operateur.AU_MOINS, 144, Importance.SOUHAIT),
    )
    assert ligne.statut is Statut.PARTIEL
    assert 0 < ligne.sous_score < 1
    assert ligne.ecart == Decimal("-24")


def test_une_enumeration_scoree_ne_connait_que_zero_ou_un():
    """Égalité stricte : « IPS » ne ressemble pas un peu à « VA »."""
    critere = resolu("monitor", "panel_type", Operateur.EGAL, "IPS")
    assert evaluer_critere(fabriquer("monitor", 1, "300"), critere).sous_score == 1
    assert evaluer_critere(fabriquer("monitor", 2, "300", panel_type="VA"), critere).sous_score == 0


@pytest.mark.parametrize("valeur", [Decimal("21.5"), Decimal("34")])
def test_le_sous_score_ne_depend_pas_des_autres_produits(valeur):
    """Arbitrage G : bornes absolues. Le lot n'entre pas dans le calcul.

    Le même produit, seul ou entouré, rend le même sous-score — sans quoi deux
    conversations le classeraient différemment.
    """
    critere = resolu("monitor", "screen_size", Operateur.AU_MOINS, 24, Importance.SOUHAIT)
    produit = fabriquer("monitor", 1, "300", screen_size=valeur)
    attendu = evaluer_critere(produit, critere).sous_score

    for autre in (Decimal("14"), Decimal("65")):
        fabriquer("monitor", 2, "300", screen_size=autre)
        assert evaluer_critere(produit, critere).sous_score == attendu
