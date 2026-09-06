"""⚠️ **La propriété que l'étape 17 doit tenir : observer un tour ne change pas ce tour.**

C'est la seule chose qu'un décorateur de `ClientLLM` peut casser, et elle ne se voit pas en
lisant le code — il faut jouer les mêmes scénarios des deux façons et comparer.

Les scénarios sont joués **sur les deux orchestrations**, avec le même client scripté. Le
fondement de l'étape 15 est que le harnais puisse mettre les deux à la même place ; un
décorateur qui serait transparent pour l'une et pas pour l'autre ruinerait la comparaison
sans qu'aucun test de l'une ou de l'autre ne bouge.

Purs : ni base, ni conteneur, ni clé API.
"""

import pytest
from faux_client import FauxClient, appel_outil, message, texte
from scenarios import ECRAN_144, SYSTEME, etat_ecran

from raiyon.agent.boucle import repondre
from raiyon.machine.orchestrateur import repondre_machine
from raiyon.observation import ClientJournalisant
from raiyon.tools.etat import EtatSession

ORCHESTRATIONS = pytest.mark.parametrize(
    "orchestration", [repondre, repondre_machine], ids=["agent", "machine"]
)


def _scenario_recommandation() -> list:
    """Critères, recherche, puis la phrase. Le chemin nominal, en trois messages."""
    return [
        message(appel_outil("record_criteria", ECRAN_144)),
        message(appel_outil("search_products", {"categorie": "monitor"})),
        message(texte("Voici trois écrans à 165 Hz sous 400 $.")),
    ]


def _scenario_question() -> list:
    """`ask_clarification` : le tour est clos par l'outil, pas par du texte."""
    return [
        message(appel_outil("record_criteria", {"categorie": "monitor"})),
        message(
            appel_outil(
                "ask_clarification",
                {"question": "Quelle taille d'écran vous conviendrait ?", "champ_vise": "size"},
            )
        ),
    ]


def _scenario_bouclage() -> list:
    """Le même appel, indéfiniment : la garde d'itérations et le repli."""
    return [message(appel_outil("record_criteria", {"categorie": "monitor"}))]


SCENARIOS = pytest.mark.parametrize(
    ("fabrique", "etat_initial"),
    [
        (_scenario_recommandation, etat_ecran),
        (_scenario_question, EtatSession),
        (_scenario_bouclage, EtatSession),
    ],
    ids=["recommandation", "question", "bouclage"],
)


def _jouer(client, orchestration, contexte, outils, etat):
    """Consomme le générateur en entier et rend `(événements, issue)`."""
    generateur = orchestration(
        client=client,
        systeme=SYSTEME,
        outils=outils,
        historique=[],
        message_client="Bonjour",
        etat=etat,
        contexte=contexte,
        max_iterations=8,
        max_regenerations=1,
    )
    evenements = []
    while True:
        try:
            evenements.append(next(generateur))
        except StopIteration as arret:
            return evenements, arret.value


@ORCHESTRATIONS
@SCENARIOS
def test_le_decorateur_ne_change_rien_a_ce_que_lorchestration_produit(
    orchestration, fabrique, etat_initial, contexte, outils
):
    """Mêmes événements, même issue, avec et sans l'enveloppe d'observation.

    La comparaison porte sur les **événements** et sur l'`IssueDuTour` entière — état final,
    tours à persister, compte d'itérations, outils appelés. C'est tout ce que la persistance
    consomme : si ces deux-là sont identiques, la base reçoit la même chose.
    """
    nu = FauxClient(reponses=fabrique())
    enveloppe = ClientJournalisant(reel=FauxClient(reponses=fabrique()))

    sans, issue_sans = _jouer(nu, orchestration, contexte, outils, etat_initial())
    avec, issue_avec = _jouer(enveloppe, orchestration, contexte, outils, etat_initial())

    assert avec == sans
    assert issue_avec == issue_sans


@ORCHESTRATIONS
@SCENARIOS
def test_les_requetes_recues_par_le_client_sont_identiques(
    orchestration, fabrique, etat_initial, contexte, outils
):
    """⚠️ **Le décorateur ne doit pas non plus modifier ce qui part vers le modèle.**

    L'assertion précédente porte sur ce qui sort ; celle-ci porte sur ce qui entre. Un
    décorateur qui recopierait `messages` au lieu de le passer — ou qui toucherait au
    `systeme` pour calculer son empreinte — ferait diverger le préfixe mis en cache sans
    changer une seule issue, et l'arbitrage 7 tomberait en silence.
    """
    nu = FauxClient(reponses=fabrique())
    interne = FauxClient(reponses=fabrique())

    _jouer(nu, orchestration, contexte, outils, etat_initial())
    _jouer(ClientJournalisant(reel=interne), orchestration, contexte, outils, etat_initial())

    assert interne.appels == nu.appels


@ORCHESTRATIONS
def test_un_appel_est_journalise_par_appel_reellement_emis(orchestration, contexte, outils):
    """Le compte des lignes suit le compte des appels, quelle que soit l'orchestration."""
    interne = FauxClient(reponses=_scenario_recommandation())
    journalisant = ClientJournalisant(reel=interne)

    _jouer(journalisant, orchestration, contexte, outils, etat_ecran())

    appels = journalisant.drainer()
    assert len(appels) == interne.nombre_dappels
    assert [appel.iteration for appel in appels] == list(range(1, len(appels) + 1))


def test_le_repli_de_bouclage_est_journalise_avec_ses_huit_appels(contexte, outils):
    """Un tour qui part en boucle est **le** tour qu'on veut voir au tableau de bord.

    Huit appels payés pour une phrase écrite en Python : c'est le cas que la garde
    d'itérations borne, et celui dont le coût était jusqu'ici invisible.

    ⚠️ **Ce test-là ne porte que sur la boucle d'agent, et c'est délibéré.** La machine
    n'a pas de garde d'itérations à huit : sur le même script elle clôt après deux appels,
    par son propre chemin de réponse vide. Le paramétrer sur les deux orchestrations
    reviendrait à affirmer d'elle une propriété qui appartient à l'autre — les tests
    au-dessus disent ce qui vaut pour les deux, celui-ci dit ce qui vaut pour une.
    """
    journalisant = ClientJournalisant(reel=FauxClient(reponses=_scenario_bouclage()))

    evenements, _ = _jouer(journalisant, repondre, contexte, outils, EtatSession())

    assert len(journalisant.drainer()) == 8
    assert any(type(evenement).__name__ == "Repli" for evenement in evenements)
