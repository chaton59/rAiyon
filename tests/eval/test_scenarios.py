"""Les dix scénarios : ce que le §5 étape 12 exige, et ce que l'arbitrage F impose.

Ces tests ne mesurent rien — ils vérifient que la **définition** des scénarios tient ses
promesses. Un attendu sans justification passerait toutes les autres suites au vert et
rendrait la métrique nº4 inexploitable le jour où elle chuterait.
"""

import pytest

from raiyon.catalogue.pipeline import FICHIER_SEED, lire_seed
from raiyon.eval.metriques import Attente
from raiyon.eval.scenario import (
    PAR_NOM,
    SCENARIOS,
    ScenarioInconnu,
    par_nom,
    prises_attendues,
)
from raiyon.matching.relachement import Motif

EXIGES_PAR_LE_PLAN = {
    "budget_serre",
    "budget_absent",
    "besoin_flou",
    "sur_specifie",
    "changement_davis",
    "comparaison",
    "hors_catalogue",
    "zero_budget_trop_bas",
}
"""Les huit du §5 étape 12. Les deux autres visent des invariants que seuls des tests
unitaires touchent aujourd'hui : le jeton de parole et le budget effacé."""

A_TROIS_PRISES = {"budget_serre", "besoin_flou", "zero_budget_trop_bas"}
"""Arbitrage D : les trois sur lesquels on veut un ordre de grandeur de la dispersion."""


def test_les_huit_scenarios_du_plan_sont_tous_la():
    assert set(PAR_NOM) >= EXIGES_PAR_LE_PLAN


def test_il_y_a_bien_dix_scenarios():
    assert len(SCENARIOS) == 10


def test_les_noms_sont_uniques():
    """Deux scénarios de même nom écriraient dans la même cassette, et l'un des deux
    mesurerait la conversation de l'autre."""
    noms = [scenario.nom for scenario in SCENARIOS]
    assert len(set(noms)) == len(noms)


def test_seuls_trois_scenarios_portent_trois_prises():
    """Une cassette est un **tirage** ; trois prises coûtent trois fois le budget de
    jetons, et on ne les paie que là où la dispersion nous intéresse (arbitrage D)."""
    multiples = {scenario.nom for scenario in SCENARIOS if scenario.prises > 1}
    assert multiples == A_TROIS_PRISES
    assert all(PAR_NOM[nom].prises == 3 for nom in A_TROIS_PRISES)
    assert prises_attendues() == 16


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.nom)
def test_chaque_scenario_a_au_moins_deux_tours_client(scenario):
    """Un scénario d'un seul tour ne mesure pas un dialogue, il mesure un prompt."""
    assert len(scenario.tours) >= 2
    assert all(tour.strip() for tour in scenario.tours)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.nom)
def test_chaque_scenario_dit_ce_quil_cherche_a_mettre_en_defaut(scenario):
    assert len(scenario.intention) > 20


@pytest.mark.parametrize(
    "scenario",
    [scenario for scenario in SCENARIOS if scenario.attendu is not None],
    ids=lambda scenario: scenario.nom,
)
def test_tout_attendu_porte_sa_justification(scenario):
    """**Arbitrage F.** C'est cette phrase qu'on relira le jour où la métrique nº4
    chutera, et sans elle on ne saura pas si c'est le moteur qui a régressé ou l'attendu
    qui était mauvais. Une phrase courte serait une phrase absente."""
    attendu = scenario.attendu
    assert attendu is not None
    assert attendu.produit_id.startswith(("monitor-", "cpu-", "memory-", "video-card-"))
    assert len(attendu.justification) > 200, "une justification tient en plusieurs phrases"


@pytest.mark.parametrize(
    "scenario",
    [scenario for scenario in SCENARIOS if scenario.attendu is not None],
    ids=lambda scenario: scenario.nom,
)
def test_tout_attendu_designe_un_produit_du_seed_committe(scenario):
    """Un attendu qui pointerait vers un identifiant inexistant ferait échouer la métrique
    nº4 pour toujours, sans qu'aucun message ne dise pourquoi. Le seed est committé : la
    vérification est **pure**, et elle tourne dans `make check`."""
    if not FICHIER_SEED.is_file():
        pytest.skip(f"{FICHIER_SEED} est absent — lancer `make seed-build`.")
    identifiants = {produit.id for produit in lire_seed(FICHIER_SEED)}
    attendu = scenario.attendu
    assert attendu is not None
    assert attendu.produit_id in identifiants, (
        f"{scenario.nom} attend {attendu.produit_id}, absent du seed committé — "
        "la métrique nº4 vaudrait 0 sans que rien ne dise pourquoi."
    )


def test_les_scenarios_sans_attendu_sont_une_decision_pas_un_oubli():
    """Six prises sur seize portent un attendu. Les autres mesurent autre chose — une
    non-hallucination, un diagnostic, un refus — et leur en donner un par symétrie
    fabriquerait une métrique nº4 flatteuse."""
    sans = {scenario.nom for scenario in SCENARIOS if scenario.attendu is None}
    assert sans == {
        "besoin_flou",
        "sur_specifie",
        "hors_catalogue",
        "zero_budget_trop_bas",
        "desserrage_refuse",
        "categorie_efface_budget",
    }
    avec = sum(scenario.prises for scenario in SCENARIOS if scenario.attendu is not None)
    assert avec == 6


def test_les_deux_scenarios_de_budget_portent_linvariant_et_non_le_nom_de_loutil():
    """Ce que la première exécution du harnais a appris, figé en test.

    Le §5 nommait `BesoinDeBudget`. Écrite ainsi, l'attente a échoué sur deux scénarios où
    l'agent s'était pourtant bien conduit : il sonde le catalogue puis pose la question en
    texte, sans passer par `suggest_next_question`. L'exigence porte donc sur l'invariant —
    **aucune recherche sans budget connu** — et le passage par l'outil reste une
    observation publiée sans seuil.
    """
    for nom in ("budget_absent", "categorie_efface_budget"):
        assert Attente.AUCUNE_RECHERCHE_SANS_BUDGET in PAR_NOM[nom].attentes
        assert Attente.BESOIN_DE_BUDGET not in PAR_NOM[nom].attentes


def test_aucun_scenario_nexige_un_appel_doutil_particulier():
    """Une attente qui nomme un outil mesure le chemin, pas le résultat — et le prompt
    système dit explicitement que `suggest_next_question` **est une suggestion** (§3.8)."""
    exigees = {attente for scenario in SCENARIOS for attente in scenario.attentes}
    assert Attente.BESOIN_DE_BUDGET not in exigees


def test_les_deux_diagnostics_attendus_sont_distincts():
    """Le §5 exige que le zéro résultat par budget soit **distinct par son motif** du
    besoin sur-spécifié. Deux scénarios, deux motifs."""
    attendus = {
        scenario.nom: scenario.diagnostic_attendu
        for scenario in SCENARIOS
        if scenario.diagnostic_attendu is not None
    }
    assert attendus == {
        "sur_specifie": Motif.CRITERE_TROP_STRICT,
        "zero_budget_trop_bas": Motif.BUDGET_TROP_BAS,
    }


def test_un_nom_de_fichier_de_cassette_porte_le_scenario_et_la_prise():
    assert PAR_NOM["budget_serre"].fichier(2) == "budget_serre.2.json"


def test_un_scenario_inconnu_liste_les_noms_valides():
    with pytest.raises(ScenarioInconnu) as erreur:
        par_nom("budget-serre")
    assert "budget_serre" in str(erreur.value)
    assert "categorie_efface_budget" in str(erreur.value)
