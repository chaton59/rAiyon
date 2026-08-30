"""L'orchestration, sur un dépôt factice. Toujours aucune base, toujours aucune clé.

Ce que ces tests gardent n'est pas le SQL — il a ses propres tests, marqués
`integration` — mais la **forme du résultat** : ce qui est séparé de quoi, ce qui est
toujours présent, ce qui n'est renseigné que dans un cas.
"""

from decimal import Decimal

import pytest

from conftest import DepotFactice, fabriquer
from raiyon.matching.criteres import (
    Critere,
    Importance,
    Operateur,
    Optimisation,
    RequeteMatching,
)
from raiyon.matching.depot import RelevesDeRelachement
from raiyon.matching.moteur import (
    LIMITE_AU_DESSUS_DU_BUDGET,
    LIMITE_PRODUITS,
    CategorieIncoherente,
    rechercher,
    tolerance_budget,
)
from raiyon.matching.relachement import Motif

TOLERANCE = Decimal("0.15")


def requete(**kwargs):
    return RequeteMatching(categorie="monitor", **kwargs)


def ecrans(nombre, prix="300"):
    return [fabriquer("monitor", numero, prix) for numero in range(1, nombre + 1)]


def test_au_plus_trois_produits_sont_rendus():
    """1 à 3 recommandations : au-delà ce n'est plus un conseil, c'est une liste."""
    depot = DepotFactice(produits=ecrans(8))
    resultat = rechercher(depot, requete(), tolerance=TOLERANCE)

    assert len(resultat.produits) == LIMITE_PRODUITS
    assert resultat.candidats_trouves == 8
    assert len(resultat.traces) == len(resultat.produits)


def test_chaque_trace_correspond_au_produit_de_meme_rang():
    depot = DepotFactice(produits=ecrans(5))
    resultat = rechercher(depot, requete(), tolerance=TOLERANCE)

    for rang, (produit, trace) in enumerate(
        zip(resultat.produits, resultat.traces, strict=True), start=1
    ):
        assert trace.produit_id == produit.id
        assert trace.rang == rang


def test_les_deux_ensembles_de_budget_sont_structurellement_separes():
    """§3.10 : le LLM ne peut pas présenter un hors-budget comme étant dedans.

    Il ne les reçoit pas dans le même champ ; aucune consigne de prompt n'est
    nécessaire pour l'en empêcher.
    """
    dedans = fabriquer("monitor", 1, "290")
    dehors = fabriquer("monitor", 2, "308")
    depot = DepotFactice(produits=[dedans], hors_budget=[dehors])

    resultat = rechercher(depot, requete(budget_usd=Decimal("300")), tolerance=TOLERANCE)

    assert [produit.id for produit in resultat.produits] == [dedans.id]
    assert [hors.produit.id for hors in resultat.au_dessus_du_budget] == [dehors.id]
    assert resultat.au_dessus_du_budget[0].ecart_usd == Decimal("8.00")


def test_la_zone_de_tolerance_est_bornee_par_la_configuration():
    """`]budget, budget x 1,15]`, bornes calculées en décimal exact."""
    depot = DepotFactice(produits=ecrans(1))
    rechercher(depot, requete(budget_usd=Decimal("300")), tolerance=TOLERANCE)

    zone = [f for f in depot.fourchettes if f.min_exclu is not None]
    assert len(zone) == 1
    assert zone[0].min_exclu == Decimal("300")
    assert zone[0].max_inclus == Decimal("345.00")


def test_la_zone_de_tolerance_rend_au_plus_deux_produits():
    depot = DepotFactice(produits=ecrans(1), hors_budget=ecrans(5, prix="310"))
    resultat = rechercher(depot, requete(budget_usd=Decimal("300")), tolerance=TOLERANCE)
    assert len(resultat.au_dessus_du_budget) == LIMITE_AU_DESSUS_DU_BUDGET


def test_sans_budget_la_zone_de_tolerance_est_vide_et_non_interrogee():
    depot = DepotFactice(produits=ecrans(2), hors_budget=ecrans(2, prix="900"))
    resultat = rechercher(depot, requete(), tolerance=TOLERANCE)

    assert resultat.au_dessus_du_budget == ()
    assert all(fourchette.min_exclu is None for fourchette in depot.fourchettes)


def test_les_ecartes_faute_de_donnee_sont_toujours_presents():
    """Champ toujours là, vide quand il n'y a rien à dire."""
    resultat = rechercher(DepotFactice(produits=ecrans(2)), requete(), tolerance=TOLERANCE)
    assert resultat.ecartes_faute_de_donnee == {}


def test_le_diagnostic_nest_renseigne_que_sur_un_zero_resultat():
    depot = DepotFactice(produits=ecrans(2))
    assert rechercher(depot, requete(), tolerance=TOLERANCE).diagnostic is None
    assert depot.appels_de_comptage == 0


def test_un_zero_resultat_declenche_le_diagnostic():
    depot = DepotFactice(
        produits=[],
        ecartes={"refresh_rate": 7},
        releves=RelevesDeRelachement(rouvre_si_retire={"refresh_rate": 7}),
    )
    resultat = rechercher(
        depot,
        requete(
            criteres=(
                Critere(
                    champ="refresh_rate",
                    operateur=Operateur.AU_MOINS,
                    valeur=144,
                    importance=Importance.BLOQUANT,
                ),
            )
        ),
        tolerance=TOLERANCE,
    )

    assert resultat.produits == ()
    assert resultat.diagnostic is not None
    assert resultat.diagnostic.motif is Motif.DONNEE_ABSENTE
    assert resultat.ecartes_faute_de_donnee == {"refresh_rate": 7}
    assert depot.appels_de_comptage == 1


def test_il_ny_a_pas_de_score_plancher():
    """Un mauvais score reste une réponse : un plancher recréerait un zéro silencieux."""
    depot = DepotFactice(produits=ecrans(1))
    resultat = rechercher(
        depot,
        requete(
            criteres=(
                Critere(
                    champ="panel_type",
                    operateur=Operateur.EGAL,
                    valeur="TN",
                    importance=Importance.IMPORTANT,
                ),
            )
        ),
        tolerance=TOLERANCE,
    )
    assert len(resultat.produits) == 1
    assert resultat.traces[0].score == 0


def test_un_produit_dune_autre_categorie_fait_lever():
    """Un tour, une catégorie (arbitrage K). L'invariant se vérifie, il ne se suppose pas."""
    depot = DepotFactice(produits=[fabriquer("cpu", 1, "200")])
    with pytest.raises(CategorieIncoherente):
        rechercher(depot, requete(), tolerance=TOLERANCE)


def test_la_tolerance_par_defaut_vient_de_la_configuration(monkeypatch):
    """Et elle est convertie en `Decimal` par `str`, jamais par `Decimal(float)`."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0123456789")
    assert tolerance_budget() == Decimal("0.15")
    assert str(tolerance_budget()) == "0.15"


def test_toute_position_gagnee_par_le_prix_apparait_dans_la_trace():
    """Le prix compte deux fois — le budget borne, le score ordonne — donc ça s'écrit.

    L'écran bon marché est techniquement moins bon ; il passe devant grâce au
    sous-score de prix, et la trace dit **de combien de places**.
    """
    cher = fabriquer("monitor", 1, "1299.99", refresh_rate=240)
    economique = fabriquer("monitor", 2, "108", refresh_rate=228)
    depot = DepotFactice(produits=[cher, economique])

    resultat = rechercher(
        depot,
        requete(
            criteres=(
                Critere(
                    champ="refresh_rate",
                    operateur=Operateur.AU_MOINS,
                    valeur=144,
                    importance=Importance.SOUHAIT,
                ),
            ),
            optimisation=Optimisation.MOINS_CHER,
        ),
        tolerance=TOLERANCE,
    )

    traces = {trace.produit_id: trace for trace in resultat.traces}
    assert [produit.id for produit in resultat.produits] == [economique.id, cher.id]
    assert traces[economique.id].positions_gagnees_par_le_prix == 1
    assert traces[cher.id].positions_gagnees_par_le_prix == -1
    # Sans le sous-score de prix, l'ordre technique serait l'inverse.
    assert traces[cher.id].rang_sans_le_prix == 1
