"""Les onze scénarios : ce que le §5 étape 12 exige, et ce que l'arbitrage F impose.

Ces tests ne mesurent rien — ils vérifient que la **définition** des scénarios tient ses
promesses. Un attendu sans justification passerait toutes les autres suites au vert et
rendrait la métrique nº4 inexploitable le jour où elle chuterait.
"""

import inspect

import pytest

from raiyon.catalogue.pipeline import FICHIER_SEED, lire_seed
from raiyon.eval import metriques
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

A_SIX_PRISES = {"question_de_domaine"}
"""Le seul scénario où le nombre de prises achète du **qualitatif** (étape 13, jalon 0).

Trois tours, donc un surcoût marginal, et six proses de domaine à relire au lieu de trois.
Partout ailleurs, une prise de plus n'achète que de la statistique."""

A_TROIS_PRISES = {
    "budget_serre",
    "besoin_flou",
    "zero_budget_trop_bas",
    "question_de_domaine",
}
"""Arbitrage D : ceux sur lesquels un tirage unique ne dit rien.

Les trois premiers portent la dispersion des métriques nº3 et nº4. Le quatrième est venu
au correctif de l'étape 12, et pour une **autre** raison : il mesure un événement rare —
un repli sur une question de domaine — et la première prise n'en a produit aucun. Le
modèle avait répondu sans citer un seul chiffre, donc aucune des cinq règles n'a tiré.

⚠️ **Trois prises ne rendent pas ce scénario déterministe**, et ce n'est pas ce qu'on leur
demande : elles disent si le repli est fréquent ou exceptionnel. Réenregistrer jusqu'à
obtenir le repli qu'on attendait serait exactement la faute que ce dépôt cherche à ne plus
commettre."""


def test_les_huit_scenarios_du_plan_sont_tous_la():
    assert set(PAR_NOM) >= EXIGES_PAR_LE_PLAN


def test_il_y_a_bien_douze_scenarios():
    """Dix à l'étape 12, `question_de_domaine` au correctif, `avis_du_web` à l'étape 33.

    ⚠️ **Le douzième ne cherche à mettre en défaut aucune conduite**, et c'est le seul dans
    ce cas : il existe pour qu'un appel à `search_reviews` — donc un encadrement scellé —
    traverse le harnais à chaque campagne. Il n'y était pas parce qu'il ne **pouvait** pas y
    être : le sceau entrait dans l'empreinte de requête et rendait la prise irrejouable.
    """
    assert len(SCENARIOS) == 12
    assert "question_de_domaine" in PAR_NOM
    assert "avis_du_web" in PAR_NOM


def test_les_noms_sont_uniques():
    """Deux scénarios de même nom écriraient dans la même cassette, et l'un des deux
    mesurerait la conversation de l'autre."""
    noms = [scenario.nom for scenario in SCENARIOS]
    assert len(set(noms)) == len(noms)


def test_chaque_scenario_porte_au_moins_trois_prises():
    """**Trois partout depuis l'étape 13**, et l'arbitrage D a été révisé pour cela.

    L'étape 12 ne payait trois prises que là où la dispersion l'intéressait, un tirage
    ailleurs. Ses chiffres ont montré que ça ne suffit pas à comparer deux prompts : là où
    la dispersion a été mesurée, elle vaut la **totalité** de l'effet qu'on espère — 0, 0, 2
    rejets sur `besoin_flou`, 2, 0, 0 sur `budget_serre`. Sur un scénario à une prise, un
    écart v1 → v2 est indistinguable du tirage.

    ⚠️ **Ce test interdit de couper les prises pour tenir un budget.** Si la campagne coûte
    trop cher, ce qui se coupe est le nombre de **scénarios**, en l'écrivant dans le
    rapport — et on perd alors la détection d'un effet inattendu ailleurs, qui est le
    risque principal d'un changement de prompt.
    """
    assert all(scenario.prises >= 3 for scenario in SCENARIOS)
    assert {scenario.nom for scenario in SCENARIOS if scenario.prises > 3} == A_SIX_PRISES
    assert all(PAR_NOM[nom].prises == 6 for nom in A_SIX_PRISES)
    assert prises_attendues() == 39, "36 jusqu'à l'étape 32, +3 pour `avis_du_web`"


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
        "question_de_domaine",
        "besoin_flou",
        "sur_specifie",
        "hors_catalogue",
        "zero_budget_trop_bas",
        "desserrage_refuse",
        "categorie_efface_budget",
        # `avis_du_web` mesure qu'un encadrement traverse le harnais, pas quel produit
        # arrive en tête : un attendu y ferait porter la métrique nº4 sur un scénario qui
        # ne classe rien.
        "avis_du_web",
    }
    avec = sum(scenario.prises for scenario in SCENARIOS if scenario.attendu is not None)
    assert avec == 12, "quatre scénarios à attendu, trois prises chacun depuis l'étape 13"


def test_les_deux_scenarios_de_budget_portent_linvariant_et_non_le_nom_de_loutil():
    """Ce que la première exécution du harnais a appris, figé en test.

    Le §5 nommait `BesoinDeBudget`. Écrite ainsi, l'attente a échoué sur deux scénarios où
    l'agent s'était pourtant bien conduit : il sonde le catalogue puis pose la question en
    texte, sans passer par `suggest_next_question`. L'exigence porte donc sur l'invariant,
    et le passage par l'outil reste une observation publiée sans seuil.

    ⚠️ **Les deux scénarios ne portent plus le même invariant depuis l'étape 32**, et c'est
    l'objet de la moitié basse de ce test. La leçon d'origine, elle, ne bouge pas : ni l'un
    ni l'autre n'exige un outil.
    """
    for nom in ("budget_absent", "categorie_efface_budget"):
        assert Attente.BESOIN_DE_BUDGET not in PAR_NOM[nom].attentes


def test_un_budget_efface_et_un_budget_jamais_donne_nexigent_pas_la_meme_chose():
    """La séparation de l'étape 32, et **la raison** qui la rend défendable.

    **« Jamais eu de budget » et « en avait un, effacé » sont deux états différents, et seul
    le second porte un risque : celui d'une valeur périmée reportée en silence** sur la
    catégorie suivante — la seconde source de vérité que §3.10 ferme. `categorie_efface_budget`
    garde donc `AUCUNE_RECHERCHE_SANS_BUDGET` ; `budget_absent` passe à
    `BUDGET_DEMANDE_EN_LIVRANT`, parce qu'un budget jamais donné n'a rien à reporter et que
    §6 de `systeme.v3` demande de montrer d'abord.

    ⚠️ **Harmoniser les deux serait du rangement qui détruit de l'information.** Deux
    scénarios qui portent la même attente se lisent plus vite ; ils cesseraient de dire que
    les deux situations n'appellent pas la même garantie. Ce test existe pour que ce
    rangement-là échoue, parce que la seule autre trace de la distinction serait un
    commentaire que la relecture ne visite pas.
    """
    assert Attente.AUCUNE_RECHERCHE_SANS_BUDGET in PAR_NOM["categorie_efface_budget"].attentes
    assert Attente.BUDGET_DEMANDE_EN_LIVRANT not in PAR_NOM["categorie_efface_budget"].attentes

    assert Attente.BUDGET_DEMANDE_EN_LIVRANT in PAR_NOM["budget_absent"].attentes
    assert Attente.AUCUNE_RECHERCHE_SANS_BUDGET not in PAR_NOM["budget_absent"].attentes


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
    assert "question_de_domaine" in str(erreur.value)


# --------------------------------------------------------------------------- #
# L'index des attentes est un test de ce qu'il indexe (étape 32)
# --------------------------------------------------------------------------- #

ATTENTES_PUBLIEES_SANS_SEUIL = {
    Attente.BESOIN_DE_BUDGET: (
        "publiée comme observation dans le rapport, jamais exigée : elle mesure quel outil "
        "l'agent a choisi, ce que la première exécution du harnais a appris à ne pas faire"
    ),
}

ATTENTES_CALCULEES_SANS_LECTEUR: dict[Attente, str] = {}
"""Vide, et **c'est une case, pas un oubli** (étape 32).

`QUESTION_POSEE` l'a occupée le temps d'un jalon : calculée par les deux lecteurs, lue par
personne — aucun scénario ne la portait, aucun rapport ne la publiait. Elle a été
**retirée**, pas tolérée : une valeur produite et jamais lue finit par être interprétée un
jour par quelqu'un qui suppose qu'elle sert. Voir §9 — c'est `SEPARATEUR_DE_BLOCS` en
version calcul.

La case reste ouverte pour que le prochain cas ait un endroit où être écrit **avec sa
raison**, plutôt que d'être glissé dans un scénario pour faire passer le test.
"""


def test_chaque_attente_est_exigee_publiee_ou_declaree_inutilisee():
    """**La version exécutable de « un index est un test de ce qu'il indexe ».**

    Une attente qu'aucun scénario ne porte ne peut échouer nulle part : elle ne coûte rien,
    ne dit rien, et rien ne la dénonce. C'est la forme silencieuse du défaut de l'étape 32,
    où un champ n'avait qu'un lecteur cher — ici, il n'en aurait aucun.

    Les trois cases sont exclusives, et une attente neuve n'en occupe aucune : ce test
    échoue alors, et **c'est en le faisant passer qu'on est forcé de dire à quoi elle
    sert**. C'est le seul moment où quelqu'un y pensera.
    """
    portees = {attente for scenario in SCENARIOS for attente in scenario.attentes}
    declarees = set(ATTENTES_PUBLIEES_SANS_SEUIL) | set(ATTENTES_CALCULEES_SANS_LECTEUR)

    sans_case = set(Attente) - portees - declarees
    assert not sans_case, (
        "attente(s) que rien n'exige et que rien ne déclare : "
        f"{sorted(a.value for a in sans_case)}. "
        "L'ajouter à un scénario, ou la déclarer dans ATTENTES_PUBLIEES_SANS_SEUIL / "
        "ATTENTES_CALCULEES_SANS_LECTEUR avec sa raison."
    )
    # Une déclaration périmée est aussi trompeuse qu'une absence : si un scénario finit par
    # porter l'attente, la case « personne ne la lit » ment.
    doublons = portees & declarees
    assert not doublons, (
        f"déclarée inutilisée mais portée par un scénario : {sorted(a.value for a in doublons)}"
    )


def test_les_deux_lecteurs_dattentes_couvrent_le_meme_vocabulaire():
    """Aucune attente n'est calculable d'un côté seulement.

    L'accord des deux lecteurs est vérifié sur des conversations réelles
    (`tests/integration/test_eval.py`), mais un tel test ne lie que les chemins que ses
    scénarios empruntent — la contre-épreuve de l'étape 32 l'a montré en cassant une branche
    sans faire échouer quoi que ce soit. Ce contrôle-ci est statique et exhaustif : il lit
    le corps des deux fonctions et exige que chaque membre y figure.

    Grossier exprès. Il ne prouve pas que les deux lectures **coïncident** — c'est le rôle
    de l'autre —, seulement qu'aucune n'a été oubliée, ce qui est précisément l'erreur qu'un
    ajout à l'énumération provoque.
    """
    lecteurs = {
        "harnais": inspect.getsource(metriques._attentes_tenues),
        "journal": inspect.getsource(metriques.attentes_du_journal),
    }
    manquantes = {
        nom: sorted(a.name for a in Attente if f"Attente.{a.name}" not in source)
        for nom, source in lecteurs.items()
    }
    assert not any(manquantes.values()), f"attente(s) absente(s) d'un lecteur : {manquantes}"
