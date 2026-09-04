"""La seconde orchestration, jouée avec le faux client de l'étape 8. **Sans base, sans clé.**

Le décor est celui de `tests/agent/` — `FauxClient`, `DepotEnMemoire`, les vraies
définitions d'outils — et pour la même raison : ces tests ne mesurent pas ce que le modèle
répond, ils mesurent **ce que l'orchestrateur fait d'une réponse donnée**. Enchaînement,
réenchaînement de l'état, terminalité, appairage des `tool_result`, borne de décisions.

⚠️ **Ce que ces tests ne disent pas** est le même que pour `tests/agent/` : la conduite du
dialogue de la machine se teste dans `test_conduite.py`, sur `decider()`, et la qualité de
la prose ne se teste que par éval. Ici, c'est de la mécanique.

### Le second tour est un test, pas une vérification annexe

`test_lhistorique_dune_machine_se_rejoue_au_tour_suivant` est le test le plus important du
module : il rejoue les blocs persistés par un premier tour comme `historique` d'un second.
C'est le **piège technique nº1 de l'étape 8** — un `tool_use` sans son `tool_result` ne
casse pas le tour courant, il casse le suivant — et chez la machine, la question se pose
différemment puisque c'est le code qui appelle les outils.
"""

from typing import Any

import pytest
from faux_client import FauxClient, appel_outil, message, texte, verifier_appairage
from scenarios import ECRAN_144, SYSTEME

from outils_de_test import TOLERANCE, DepotEnMemoire, ecrans
from raiyon.agent.evenements import (
    CriteresMisAJour,
    ProduitsTrouves,
    QuestionPosee,
    QuestionSuggeree,
    Repli,
    Sondage,
    Texte,
    TexteRejete,
)
from raiyon.agent.evenements import (
    MotifDeRepli as Motif,
)
from raiyon.api.prose import Interlocuteur, prose_de
from raiyon.machine.orchestrateur import (
    CONSIGNE_DE_QUESTION,
    CONSIGNE_DE_REDACTION,
    CONSIGNE_DE_RELANCE,
    repondre_machine,
)
from raiyon.tools.etat import EtatSession
from raiyon.tools.repartiteur import ContexteOutils
from raiyon.tools.schema_outils import (
    NOM_ENREGISTRER,
    NOM_PRECISION,
    NOM_QUESTION,
    NOM_RECHERCHER,
    NOM_SONDER,
    schema_des_outils,
)

SANS_BUDGET: dict[str, Any] = {
    "categorie": "monitor",
    "criteres": [
        {"champ": "refresh_rate", "operateur": "au_moins", "valeur": "144", "importance": "souhait"}
    ],
}
"""Le même enregistrement qu'`ECRAN_144`, **moins le budget** : c'est ce qui envoie la
machine sur le chemin de la question (§3.10, `Attente.AUCUNE_RECHERCHE_SANS_BUDGET`)."""

EXTRACTION = message(appel_outil(NOM_ENREGISTRER, ECRAN_144))
EXTRACTION_SANS_BUDGET = message(appel_outil(NOM_ENREGISTRER, SANS_BUDGET))
REDACTION = message(texte("Voici ce que je vous propose."))


@pytest.fixture
def depot() -> DepotEnMemoire:
    depot = DepotEnMemoire()
    depot.produits = ecrans(3, refresh_rate=165)
    return depot


@pytest.fixture
def contexte(depot: DepotEnMemoire) -> ContexteOutils:
    return ContexteOutils(depot=depot, tour_client=1, tolerance=TOLERANCE)


@pytest.fixture
def outils() -> tuple[dict[str, Any], ...]:
    """Les vraies définitions. La machine en extrait le seul outil qu'elle expose."""
    return schema_des_outils()


def jouer(
    client: FauxClient,
    contexte: ContexteOutils,
    outils,
    *,
    etat: EtatSession | None = None,
    historique=(),
    max_iterations: int = 8,
    max_regenerations: int = 1,
    message_client: str = "Bonjour",
):
    """Consomme le générateur en entier et rend `(événements, issue)`."""
    generateur = repondre_machine(
        client=client,
        systeme=SYSTEME,
        outils=outils,
        historique=list(historique),
        message_client=message_client,
        etat=etat if etat is not None else EtatSession(),
        contexte=contexte,
        max_iterations=max_iterations,
        max_regenerations=max_regenerations,
    )
    evenements = []
    while True:
        try:
            evenements.append(next(generateur))
        except StopIteration as arret:
            return evenements, arret.value


def types(evenements) -> list[str]:
    return [type(evenement).__name__ for evenement in evenements]


def blocs_de(issue) -> list[dict[str, Any]]:
    return [bloc for tour in issue.tours for bloc in tour.blocs]


# --------------------------------------------------------------------------- #
# L'enchaînement nominal
# --------------------------------------------------------------------------- #


def test_un_tour_nominal_fait_deux_appels_modele_et_trois_outils(contexte, outils):
    """La forme d'un tour : extraction, puis le code, puis la rédaction.

    Les trois outils sont ceux que `decider()` enchaîne quand le budget est connu —
    recherche, puis sondage (la garde de contexte), puis rédaction. Aucun n'a coûté d'appel
    modèle : c'est le plancher de 2,00 appel par tour.
    """
    client = FauxClient([EXTRACTION, REDACTION])

    evenements, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 2
    assert issue.iterations == 2
    assert issue.outils_appeles == (NOM_ENREGISTRER, NOM_RECHERCHER, NOM_SONDER)
    assert types(evenements) == ["CriteresMisAJour", "ProduitsTrouves", "Sondage", "Texte"]
    verifier_appairage(issue.tours)


def test_les_deux_appels_du_tour_partagent_le_meme_prefixe(contexte, outils):
    """Même `systeme`, même schéma d'outils : le second appel lit le préfixe mis en cache
    (§3.13, arbitrage 7). C'est ce que le faux client journalise, et c'est gratuit ici —
    la machine n'expose qu'un outil, et le même aux deux appels."""
    client = FauxClient([EXTRACTION, REDACTION])

    jouer(client, contexte, outils)

    premier, second = client.appels
    assert premier.systeme == second.systeme
    assert premier.outils == second.outils
    assert [outil["name"] for outil in premier.outils] == [NOM_ENREGISTRER]


def test_letat_se_reenchaine_entre_deux_actions_du_meme_tour(contexte, outils):
    """⚠️ **C'est ce qu'aucune cassette ne teste** : le sondage doit voir l'état que la
    recherche a laissé, sinon la garde « un tour, une catégorie » ne se déclenche jamais
    (arbitrage E de l'étape 7). Ici, `recherche_du_tour` doit être posé sur l'état final."""
    client = FauxClient([EXTRACTION, REDACTION])

    _, issue = jouer(client, contexte, outils)

    assert issue.etat.recherche_du_tour is not None
    assert issue.etat.recherche_du_tour.categorie == "monitor"
    assert issue.etat.recherche_du_tour.tour_client == contexte.tour_client


def test_le_chemin_sans_budget_finit_sur_une_question(contexte, outils):
    """Sonder, suggérer, demander — et jamais chercher. Les quatre événements sont ceux que
    `Attente.AUCUNE_RECHERCHE_SANS_BUDGET` et `Attente.QUESTION_POSEE` lisent."""
    client = FauxClient([EXTRACTION_SANS_BUDGET, message(texte("Quel est votre budget ?"))])

    evenements, issue = jouer(client, contexte, outils)

    assert types(evenements) == ["CriteresMisAJour", "Sondage", "QuestionSuggeree", "QuestionPosee"]
    assert issue.outils_appeles == (NOM_ENREGISTRER, NOM_SONDER, NOM_QUESTION)
    assert not any(isinstance(evenement, ProduitsTrouves) for evenement in evenements)
    posee = evenements[-1]
    assert isinstance(posee, QuestionPosee)
    assert posee.question == "Quel est votre budget ?"
    assert posee.champ_vise is None, "le budget n'est pas un attribut du catalogue (§3.10)"


def test_la_consigne_de_question_nomme_lobjet_et_pas_la_phrase(contexte, outils):
    """La frontière du jalon 1 appliquée à l'invite : le code dit **de quoi** on parle, le
    modèle écrit les mots. Une consigne qui dicterait la question ferait de la relance un
    gabarit — l'option que l'arbitrage de l'étape a écartée."""
    client = FauxClient([EXTRACTION_SANS_BUDGET, message(texte("Quel est votre budget ?"))])

    jouer(client, contexte, outils)

    consigne = client.appels[-1].messages[-1]["content"][0]["text"]
    assert consigne.startswith(CONSIGNE_DE_QUESTION.split("{", 1)[0])
    assert "budget" in consigne


# --------------------------------------------------------------------------- #
# Ce qui est persisté, et ce qui ne l'est pas
# --------------------------------------------------------------------------- #


def test_le_texte_de_lextraction_est_jete(contexte, outils):
    """⚠️ Point B : il n'est **ni émis, ni validé, ni persisté**. Le seul texte qui part au
    client vient de l'appel nº2.

    Le persister le ferait réapparaître au rechargement — `prose.py` rend tout bloc `text`
    d'un message assistant non refusé —, c'est-à-dire la brèche de §2 que le correctif de
    l'étape 11 a fermée pour les textes refusés.
    """
    bavard = message(texte("Je note vos critères."), appel_outil(NOM_ENREGISTRER, ECRAN_144))
    client = FauxClient([bavard, REDACTION])

    evenements, issue = jouer(client, contexte, outils)

    assert "Je note vos critères." not in str(blocs_de(issue))
    assert [evenement for evenement in evenements if isinstance(evenement, Texte)] == [
        Texte("Voici ce que je vous propose.")
    ]


def test_un_outil_appele_a_la_redaction_est_jete_sans_etre_execute(contexte, outils):
    """Deux raisons, et une seule suffirait : un `tool_use` persisté sans son `tool_result`
    rend l'historique irrecevable au tour suivant, et un `ask_clarification` émis là verrait
    sa question rendue comme de la prose par `prose.py` sans jamais avoir atteint le client.
    """
    deviante = message(
        texte("Voici ce que je vous propose."),
        appel_outil(NOM_PRECISION, {"question": "Une phrase que le client n'a jamais lue ?"}),
    )
    client = FauxClient([EXTRACTION, deviante])

    evenements, issue = jouer(client, contexte, outils)

    assert NOM_PRECISION not in issue.outils_appeles
    assert "jamais lue" not in str(blocs_de(issue))
    assert types(evenements)[-1] == "Texte"
    verifier_appairage(issue.tours)


def test_la_consigne_nest_jamais_persistee(contexte, outils):
    """⚠️ Persistée, `prose.py` la rendrait **comme une parole du client** : c'est un bloc
    `text` de rôle `user` sans `tool_result`, exactement la forme d'un message client.

    La reconnaître demanderait une seconde règle dans `prose.py`, ce que sa docstring
    refuse en toutes lettres — elle deviendrait heuristique.
    """
    client = FauxClient([EXTRACTION, REDACTION])

    _, issue = jouer(client, contexte, outils)

    persiste = str(blocs_de(issue))
    assert CONSIGNE_DE_REDACTION not in persiste
    assert "N'appelez aucun outil" not in persiste


def test_la_prose_relue_ne_montre_que_ce_que_le_client_a_lu(contexte, outils):
    """Le contrôle par le vrai lecteur, pas par une inspection de blocs. `prose_de()` est
    ce que `GET /sessions/{id}` sert au rechargement."""
    bavard = message(texte("Je note vos critères."), appel_outil(NOM_ENREGISTRER, ECRAN_144))
    client = FauxClient([bavard, REDACTION])

    _, issue = jouer(client, contexte, outils)
    historique = [{"role": tour.role, "content": tour.blocs} for tour in issue.tours]

    paroles = prose_de(historique)

    assert len(paroles) == 1, f"un seul tour de parole doit être relu, obtenu {paroles}"
    assert paroles[0].interlocuteur is Interlocuteur.ASSISTANT
    assert paroles[0].texte == "Voici ce que je vous propose."


# --------------------------------------------------------------------------- #
# Le tour suivant — le piège technique nº1
# --------------------------------------------------------------------------- #


def test_lhistorique_dune_machine_se_rejoue_au_tour_suivant(contexte, outils, depot):
    """⚠️ **Le test le plus important du module.** Un `tool_use` sans son `tool_result` ne
    casse pas le tour courant : il casse le suivant, et le message d'erreur parle d'un
    identifiant de bloc.

    Chez la machine, la question se pose différemment — c'est le code qui appelle les
    outils —, mais l'historique persisté doit rester relisible : les deux orchestrations
    écrivent dans la même table, et une session peut être reprise par l'autre.
    """
    premier = FauxClient([EXTRACTION, REDACTION])
    _, issue1 = jouer(premier, contexte, outils)
    historique = [{"role": tour.role, "content": tour.blocs} for tour in issue1.tours]

    second = FauxClient([message(appel_outil(NOM_ENREGISTRER, ECRAN_144)), REDACTION])
    _, issue2 = jouer(
        second,
        ContexteOutils(depot=depot, tour_client=3, tolerance=TOLERANCE),
        outils,
        etat=issue1.etat,
        historique=historique,
        message_client="Et en 27 pouces ?",
    )

    verifier_appairage(
        [*issue1.tours, *issue2.tours],
    )
    envoye = second.appels[0].messages
    assert envoye[: len(historique)] == historique, "l'historique part tel quel au modèle"


def test_les_identifiants_doutils_du_code_sont_uniques_dans_la_session(contexte, outils, depot):
    """Ils sont dérivés du tour client et du rang : deux tours différents ne peuvent pas
    produire le même. L'API exige l'unicité dans une requête, et une requête porte toute la
    conversation."""
    premier = FauxClient([EXTRACTION, REDACTION])
    _, issue1 = jouer(premier, contexte, outils)

    second = FauxClient([EXTRACTION, REDACTION])
    _, issue2 = jouer(
        second,
        ContexteOutils(depot=depot, tour_client=3, tolerance=TOLERANCE),
        outils,
        etat=issue1.etat,
        historique=[{"role": tour.role, "content": tour.blocs} for tour in issue1.tours],
    )

    # ⚠️ Seuls les identifiants **que la machine fabrique** sont en jeu. Ceux des `tool_use`
    # du modèle viennent du modèle — et le faux client, lui, en rend un fixe (`tu_<nom>`),
    # ce qui produirait un faux échec en disant quelque chose du décor, pas du code.
    identifiants = [
        bloc["id"]
        for bloc in [*blocs_de(issue1), *blocs_de(issue2)]
        if bloc.get("type") == "tool_use" and str(bloc["id"]).startswith("mach")
    ]
    assert len(identifiants) == 4
    assert len(identifiants) == len(set(identifiants))


# --------------------------------------------------------------------------- #
# L'extraction sans outil
# --------------------------------------------------------------------------- #


def test_un_tour_dextraction_sans_outil_est_le_chemin_normal(contexte, outils):
    """Point B : c'est un tour qui n'apporte aucun critère nouveau, pas un incident.

    L'état passe inchangé à `decider()`. Sans catégorie courante, il n'y a pas de
    sous-catalogue : la machine rédige directement, ce qui est exactement le cas
    `hors_catalogue`.
    """
    client = FauxClient([message(texte("Je n'ai pas de critère à noter.")), REDACTION])

    evenements, issue = jouer(client, contexte, outils)

    assert issue.outils_appeles == ()
    assert issue.etat == EtatSession()
    assert types(evenements) == ["Texte"]


def test_sans_outil_dextraction_dans_le_schema_lerreur_est_nommee_avant_tout_appel(contexte):
    """Un `tools` vide avec des `tool_use` dans `messages` est une erreur de l'API. La
    nommer ici vaut mieux que de la lire dans un 400, et surtout : avant l'appel payé."""
    client = FauxClient([EXTRACTION, REDACTION])

    with pytest.raises(ValueError, match=NOM_ENREGISTRER):
        jouer(client, contexte, [])

    assert client.nombre_dappels == 0


# --------------------------------------------------------------------------- #
# Validation, régénération, replis
# --------------------------------------------------------------------------- #


FAUTIF = message(texte("Le MSI G274 est à 189,99 dollars."))
"""Un prix qu'aucun `tool_result` n'a fourni : la règle des montants du validateur mord."""


def test_un_texte_refuse_est_regenere_une_fois(contexte, outils):
    """Le budget de régénération est celui du tour, comme chez l'agent, et il porte sur
    l'appel nº2 : un troisième appel modèle, donc un tour au-dessus du plancher de 2,00."""
    client = FauxClient([EXTRACTION, FAUTIF, REDACTION])

    evenements, issue = jouer(client, contexte, outils)

    assert types(evenements)[-2:] == ["TexteRejete", "Texte"]
    assert client.nombre_dappels == 3
    assert issue.iterations == 3


def test_un_second_refus_se_replie_sur_template(contexte, outils):
    """§3.11 niveau 3 : le code rédige, le modèle n'assure plus rien."""
    client = FauxClient([EXTRACTION, FAUTIF])

    evenements, issue = jouer(client, contexte, outils)

    replis = [evenement for evenement in evenements if isinstance(evenement, Repli)]
    assert len(replis) == 1
    assert replis[0].motif is Motif.VALIDATION
    assert [evenement for evenement in evenements if isinstance(evenement, Texte)] == []
    verifier_appairage(issue.tours)


def test_un_texte_refuse_est_toujours_suivi_dune_reprise(contexte, outils):
    """⚠️ **L'invariant dont `prose.py` dépend**, et c'est son oubli sur les chemins de
    budget épuisé qui a coûté le correctif de l'étape 11 : *un message assistant refusé est
    toujours suivi d'un message portant une reprise.*

    Le contrôle passe par `prose_de()`, le vrai lecteur : le texte refusé ne doit pas
    revenir par la porte du rechargement.
    """
    client = FauxClient([EXTRACTION, FAUTIF])

    _, issue = jouer(client, contexte, outils)
    historique = [{"role": tour.role, "content": tour.blocs} for tour in issue.tours]

    assert "189,99" not in str(prose_de(historique))
    assert prose_de(historique) == ()


def test_une_reponse_sans_texte_se_replie_et_le_dit(contexte, outils):
    """Un message qui ne porte que des blocs `thinking` — observé en conversation réelle au
    correctif de l'étape 12. Le client recevait `done` et rien d'autre ; ici il reçoit une
    phrase écrite en Python, et le motif se compte."""
    pensif = message({"type": "thinking", "thinking": "…", "signature": "sig"}, fin="end_turn")
    client = FauxClient([EXTRACTION, pensif])

    evenements, issue = jouer(client, contexte, outils)

    replis = [evenement for evenement in evenements if isinstance(evenement, Repli)]
    assert [replis[0].motif] == [Motif.REPONSE_VIDE]
    assert issue.tours[-1].blocs[-1]["type"] == "thinking", (
        "un bloc `thinking` seul reste persisté : le jeter laisserait un message vide"
    )


# --------------------------------------------------------------------------- #
# La borne de décisions
# --------------------------------------------------------------------------- #


def test_la_borne_de_decisions_echoue_bruyamment(contexte, outils):
    """Le graphe est fini — trois décisions au plus —, donc la borne ne devrait jamais
    mordre. C'est exactement pour cela qu'elle existe : échouer bruyamment plutôt que
    tourner. Un `max_iterations` à 1 la force."""
    client = FauxClient([EXTRACTION, REDACTION])

    evenements, issue = jouer(client, contexte, outils, max_iterations=1)

    replis = [evenement for evenement in evenements if isinstance(evenement, Repli)]
    assert [replis[0].motif] == [Motif.MAX_ITERATIONS]
    assert client.nombre_dappels == 1, "la rédaction n'a pas lieu : le tour est clos"
    verifier_appairage(issue.tours)


# --------------------------------------------------------------------------- #
# Les événements du contrat
# --------------------------------------------------------------------------- #


def test_les_types_devenements_sont_ceux_de_lagent(contexte, outils):
    """`raiyon/eval/metriques.py` lit **les seuls événements**. Un type que la machine
    n'émettrait pas ferait échouer des scénarios pour une raison qui n'est pas la conduite,
    et ce serait le signe que la comparaison ne porte plus sur les mêmes mesures."""
    nominal, _ = jouer(FauxClient([EXTRACTION, REDACTION]), contexte, outils)
    question, _ = jouer(
        FauxClient([EXTRACTION_SANS_BUDGET, message(texte("Votre budget ?"))]), contexte, outils
    )
    rejet, _ = jouer(FauxClient([EXTRACTION, FAUTIF]), contexte, outils)

    emis = {type(evenement) for evenement in [*nominal, *question, *rejet]}
    assert emis == {
        CriteresMisAJour,
        ProduitsTrouves,
        Sondage,
        QuestionSuggeree,
        QuestionPosee,
        Texte,
        TexteRejete,
        Repli,
    }


# --------------------------------------------------------------------------- #
# La garde d'extraction — étape 21
# --------------------------------------------------------------------------- #

MUET: dict[str, Any] = {"categorie": "monitor", "budget_usd": "400"}
"""Le tirage fautif de l'étape 20, réduit à ses arguments : une catégorie, un budget, et
**aucun critère** pour un client qui en avait énoncé. C'est le seul déclencheur de la
garde."""

EXTRACTION_MUETTE = message(appel_outil(NOM_ENREGISTRER, MUET, id="tu_muet"))
EXTRACTION_RELANCEE = message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_relance"))


def test_la_garde_relance_lextraction_sur_une_categorie_sans_critere(contexte, outils):
    """Le cas de l'étape 20 : catégorie et budget enregistrés, critères perdus.

    Trois appels au lieu de deux, et le critère que la relance rapporte est bien dans
    l'état final — c'est le seul résultat qui compte, le compte d'appels n'étant que son
    prix.
    """
    client = FauxClient([EXTRACTION_MUETTE, EXTRACTION_RELANCEE, REDACTION])

    _, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 3
    assert issue.iterations == 3
    assert [critere.champ for critere in issue.etat.criteres_de("monitor")] == ["refresh_rate"]
    verifier_appairage(issue.tours)


def test_la_garde_garde_ce_que_lextraction_muette_avait_bien_lu(contexte, outils):
    """⚠️ Le premier `record_criteria` est **exécuté avant** la relance, pas jeté.

    Dans le tirage de l'étape 20, le budget est le seul fait que l'extraction ait
    correctement lu ; le jeter pour recommencer proprement coûterait plus que le défaut. La
    relance **complète**, elle n'annule pas.
    """
    sans_budget = {"categorie": "monitor", "criteres": SANS_BUDGET["criteres"]}
    client = FauxClient(
        [
            EXTRACTION_MUETTE,
            message(appel_outil(NOM_ENREGISTRER, sans_budget, id="tu_r")),
            REDACTION,
        ]
    )

    _, issue = jouer(client, contexte, outils)

    assert issue.etat.budget_usd is not None, "le budget de l'appel muet a survécu à la relance"
    assert [critere.champ for critere in issue.etat.criteres_de("monitor")] == ["refresh_rate"]


def test_la_garde_ne_tire_pas_sur_un_tour_qui_napporte_legitimement_aucun_critere(contexte, outils):
    """« Compare plutôt la 1 et la 3 » : le modèle n'appelle aucun outil, donc ne pose
    aucune catégorie, donc la garde ne voit rien. C'est le chemin normal de la docstring du
    module, et il reste à deux appels."""
    client = FauxClient([message(texte("Rien à noter ici.")), REDACTION])

    _, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 2
    assert issue.iterations == 2


def test_la_garde_ne_tire_pas_quand_un_second_appel_parallele_porte_les_criteres(contexte, outils):
    """⚠️ Le verdict porte sur la **réponse entière**, pas sur chaque appel.

    Le modèle sépare parfois le budget des critères en deux `record_criteria` parallèles —
    `budget_serre.2`, `desserrage_refuse.1` et `.3`, `question_de_domaine.3` dans les
    cassettes. Juger appel par appel ferait tirer la garde sur quatre tours qui ont
    parfaitement extrait.
    """
    parallele = message(
        appel_outil(NOM_ENREGISTRER, MUET, id="tu_budget"),
        appel_outil(NOM_ENREGISTRER, SANS_BUDGET, id="tu_criteres"),
    )
    client = FauxClient([parallele, REDACTION])

    _, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 2
    verifier_appairage(issue.tours)


def test_la_garde_ne_tire_pas_sur_un_retrait_de_critere(contexte, outils):
    """Retirer un critère est une opération **sur les critères** : le tour a apporté
    quelque chose, même si `criteres` est vide."""
    retrait = {
        "categorie": "monitor",
        "retraits": [{"champ": "refresh_rate", "operateur": "au_moins"}],
    }
    depart = EtatSession()
    _, issue_depart = jouer(FauxClient([EXTRACTION, REDACTION]), contexte, outils, etat=depart)

    client = FauxClient([message(appel_outil(NOM_ENREGISTRER, retrait, id="tu_ret")), REDACTION])
    _, issue = jouer(client, contexte, outils, etat=issue_depart.etat)

    assert client.nombre_dappels == 2
    assert issue.etat.criteres_de("monitor") == ()


def test_la_garde_ne_tire_quune_fois(contexte, outils):
    """Un garde-fou, pas une boucle. Deux extractions muettes de suite donnent **trois**
    appels, jamais quatre : le troisième est la rédaction."""
    client = FauxClient([EXTRACTION_MUETTE, EXTRACTION_MUETTE, REDACTION])

    evenements, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 3
    assert types(evenements)[-1] == "Texte"
    verifier_appairage(issue.tours)


def test_le_tour_se_termine_normalement_si_la_relance_ne_rapporte_rien(contexte, outils):
    """« Si la relance rend encore zéro critère, on continue avec ce qu'on a. » Le défaut
    est alors du modèle et non de l'orchestration, et on ne paie pas un troisième appel
    pour le constater."""
    client = FauxClient([EXTRACTION_MUETTE, message(texte("Rien de plus à noter.")), REDACTION])

    evenements, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 3
    assert types(evenements)[-1] == "Texte"
    assert issue.etat.criteres_de("monitor") == ()
    verifier_appairage(issue.tours)


def test_la_consigne_de_relance_nest_jamais_persistee(contexte, outils):
    """Même statut que les deux autres consignes : persistée, `prose.py` la rendrait
    **comme une parole du client**. Le contrôle passe par le vrai lecteur."""
    client = FauxClient([EXTRACTION_MUETTE, EXTRACTION_RELANCEE, REDACTION])

    _, issue = jouer(client, contexte, outils)
    historique = [{"role": tour.role, "content": tour.blocs} for tour in issue.tours]

    assert CONSIGNE_DE_RELANCE not in str(blocs_de(issue))
    assert [parole.texte for parole in prose_de(historique)] == ["Voici ce que je vous propose."]


def test_la_relance_lit_le_resultat_de_lextraction_muette(contexte, outils):
    """La consigne vient **après** le `tool_result` du premier enregistrement : ce que le
    modèle relit n'est pas seulement son appel, c'est le `"criteres": []` que la couche
    outils lui a renvoyé."""
    client = FauxClient([EXTRACTION_MUETTE, EXTRACTION_RELANCEE, REDACTION])

    jouer(client, contexte, outils)

    envoyes = client.appels[1].messages
    assert envoyes[-1]["content"][0]["text"] == CONSIGNE_DE_RELANCE
    assert envoyes[-2]["content"][0]["type"] == "tool_result"
    assert '"criteres": []' in envoyes[-2]["content"][0]["content"]


def test_lhistorique_dun_tour_ou_la_garde_a_tire_se_rejoue_au_tour_suivant(contexte, outils, depot):
    """Le piège technique nº1, appliqué au tour à deux extractions : deux paires
    `tool_use`/`tool_result` de plus dans le même message persisté, et l'API doit toujours
    accepter l'historique au tour suivant."""
    premier = FauxClient([EXTRACTION_MUETTE, EXTRACTION_RELANCEE, REDACTION])
    _, issue1 = jouer(premier, contexte, outils)
    historique = [{"role": tour.role, "content": tour.blocs} for tour in issue1.tours]

    second = FauxClient([EXTRACTION, REDACTION])
    _, issue2 = jouer(
        second,
        ContexteOutils(depot=depot, tour_client=3, tolerance=TOLERANCE),
        outils,
        etat=issue1.etat,
        historique=historique,
        message_client="Et en 27 pouces ?",
    )

    verifier_appairage([*issue1.tours, *issue2.tours])
    assert second.appels[0].messages[: len(historique)] == historique
