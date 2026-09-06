"""`max_tokens` et `refusal` : nommés et comptés, sur les deux orchestrations.

⚠️ **Le cas qui a motivé ces tests est le troisième**, celui où la génération est coupée
alors que le message porte des appels d'outils. Le contrôle vivait sous `if not
message.appels` : un message coupé qui appelait des outils ne l'atteignait jamais. C'est
exactement ce qui est arrivé au premier tir réel de l'étape 23 — trois `tool_use`, dont un
`ask_clarification` à `{}`, et un `stop_reason` que personne n'a vu.

**Aucun de ces tests n'assertent un changement de comportement**, et c'est délibéré : les
deux `stop_reason` restent opaques pour l'orchestration. On constate donc *aussi* que
l'issue est identique à celle d'une fin normale.

Purs : ni base, ni conteneur, ni clé API.
"""

import pytest
import structlog
from faux_client import FauxClient, appel_outil, message, texte
from scenarios import ECRAN_144, SYSTEME, etat_ecran

from raiyon.agent.boucle import repondre
from raiyon.agent.client import ReponseLLM
from raiyon.machine.orchestrateur import repondre_machine
from raiyon.orchestration.contrat import FINS_INTERROMPUES

FINS = pytest.mark.parametrize("fin", sorted(FINS_INTERROMPUES), ids=sorted(FINS_INTERROMPUES))


def _jouer(client, orchestration, contexte, outils, etat):
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


def _alertes(journal, evenement):
    return [ligne for ligne in journal if ligne["event"] == evenement]


@FINS
def test_la_boucle_signale_une_generation_interrompue(fin, contexte, outils):
    """Un message texte-seul coupé : le cas que l'étape 8 surveillait déjà, pour `max_tokens`."""
    client = FauxClient(reponses=[ReponseLLM(blocs=[texte("Voici trois écr")], fin=fin)])

    with structlog.testing.capture_logs() as journal:
        _jouer(client, repondre, contexte, outils, etat_ecran())

    (alerte,) = _alertes(journal, "boucle.generation_interrompue")
    assert alerte["log_level"] == "warning"
    assert alerte["fin"] == fin
    assert alerte["cause"] == FINS_INTERROMPUES[fin]


@FINS
def test_la_boucle_signale_meme_quand_le_message_porte_des_appels_doutils(fin, contexte, outils):
    """⚠️ **Le défaut corrigé : c'est par là que `refusal` est passé sans être vu.**

    Le message coupé de l'étape 23 portait trois `tool_use`. Sous l'ancien placement — dans
    la branche `if not message.appels` — il n'atteignait jamais le contrôle, et le tour se
    déroulait sans qu'une ligne le mentionne.
    """
    client = FauxClient(
        reponses=[
            ReponseLLM(
                blocs=[
                    appel_outil("record_criteria", ECRAN_144, id="tu_1"),
                    # L'appel coupé dans ses arguments, tel qu'observé : `{}` là où le
                    # schéma exige `question`.
                    appel_outil("ask_clarification", {}, id="tu_2"),
                ],
                fin=fin,
            ),
            message(texte("Voici trois écrans.")),
        ]
    )

    with structlog.testing.capture_logs() as journal:
        _jouer(client, repondre, contexte, outils, etat_ecran())

    (alerte,) = _alertes(journal, "boucle.generation_interrompue")
    assert alerte["outils_du_message"] == ["record_criteria", "ask_clarification"]


def test_une_fin_normale_ne_signale_rien(contexte, outils):
    """`end_turn` et `tool_use` sont le régime nominal : ils ne doivent produire aucun bruit."""
    client = FauxClient(
        reponses=[
            message(appel_outil("record_criteria", ECRAN_144, id="tu_1")),
            message(texte("Voici trois écrans.")),
        ]
    )

    with structlog.testing.capture_logs() as journal:
        _jouer(client, repondre, contexte, outils, etat_ecran())

    assert _alertes(journal, "boucle.generation_interrompue") == []


@FINS
def test_le_signal_ne_change_pas_ce_que_la_boucle_produit(fin, contexte, outils):
    """**Nommé et compté, rien de plus.** Les deux `stop_reason` restent opaques.

    Replier sur `refusal` serait changer le comportement sur la foi d'une occurrence ; la
    colonne `stop_reason` d'`appels_modele` dira d'abord à quelle fréquence il arrive.
    """
    coupe = FauxClient(reponses=[ReponseLLM(blocs=[texte("Voici trois écrans.")], fin=fin)])
    normal = FauxClient(reponses=[message(texte("Voici trois écrans."))])

    avec, issue_avec = _jouer(coupe, repondre, contexte, outils, etat_ecran())
    sans, issue_sans = _jouer(normal, repondre, contexte, outils, etat_ecran())

    assert avec == sans
    assert issue_avec == issue_sans


@FINS
def test_la_machine_signale_son_extraction_interrompue(fin, contexte, outils):
    """⚠️ **La machine ne surveillait ni l'un ni l'autre.**

    C'est le tour le plus coûteux à laisser silencieux des deux : une extraction coupée au
    milieu de ses arguments produit un état amputé, donc une recommandation fondée sur des
    critères que le client n'a pas vus disparaître.
    """
    client = FauxClient(
        reponses=[
            ReponseLLM(blocs=[appel_outil("record_criteria", ECRAN_144, id="tu_1")], fin=fin),
            message(texte("Voici trois écrans.")),
        ]
    )

    with structlog.testing.capture_logs() as journal:
        _jouer(client, repondre_machine, contexte, outils, etat_ecran())

    alertes = _alertes(journal, "machine.generation_interrompue")
    assert [alerte["phase"] for alerte in alertes][:1] == ["extraction"]
    assert alertes[0]["fin"] == fin
