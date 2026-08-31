"""`ask_clarification` clôt le tour. Trois cas résiduels, et ce qui part au client.

L'outil est terminal depuis l'étape 7 : il rend `{ok, terminal}` et la boucle renvoie sa
question au client. La version initiale de §3.7 forçait un aller-retour API de plus et
invitait le modèle à appeler l'outil **puis** à réécrire la question en texte — la
question était alors posée deux fois.

Ce fichier vérifie donc trois choses, et la première est un coût :

1. **aucun second appel API** — c'est ce que « terminal » veut dire, et ça se compte ;
2. **ce qui part au client est le texte précédent, puis la question** — le « donner avant
   de demander » de §3.9 n'a plus d'autre endroit où vivre depuis que `preamble` a été
   supprimé (arbitrage 5) ;
3. **chaque `tool_use` a quand même son `tool_result`** — y compris ceux dont le résultat
   est perdu. C'est le piège technique nº1 : sans eux, c'est le tour **suivant** qui
   partira sur un historique que l'API refuse.
"""

import structlog
from faux_client import FauxClient, appel_outil, message, texte, verifier_appairage
from scenarios import ECRAN_144, etat_ecran, jouer

from raiyon.agent.evenements import CriteresMisAJour, QuestionPosee, Texte
from raiyon.tools.schema_outils import NOM_ENREGISTRER, NOM_PRECISION, NOM_RECHERCHER

QUESTION = "C'est pour jouer, pour du montage, ou pour de la bureautique ?"


def test_ask_clarification_arrete_la_boucle_sans_second_appel_api(contexte, outils):
    """La propriété qui se compte : un tour clos est un appel API économisé."""
    client = FauxClient(
        [
            message(appel_outil(NOM_PRECISION, {"question": QUESTION}, id="tu_1")),
            message(texte("Ce message ne doit jamais être demandé.")),
        ]
    )

    evenements, issue = jouer(client, contexte, outils, etat=etat_ecran())

    assert client.nombre_dappels == 1
    assert evenements == [QuestionPosee(question=QUESTION, champ_vise=None)]
    assert issue.iterations == 1


def test_ce_qui_part_au_client_est_le_texte_puis_la_question(contexte, outils):
    """« Donner avant de demander » (§3.9) vit dans le message, plus dans un argument.

    L'ordre des événements **est** ce que le client lit : les blocs `text` du message
    assistant, puis la question. Un `Texte` émis après la `QuestionPosee` ferait lire la
    question avant la piste qu'elle affine.
    """
    piste = "Sur cette gamme je pars plutôt sur du 27 pouces en 144 Hz."
    client = FauxClient(
        [message(texte(piste), appel_outil(NOM_PRECISION, {"question": QUESTION}, id="tu_1"))]
    )

    evenements, _ = jouer(client, contexte, outils, etat=etat_ecran())

    assert evenements == [Texte(piste), QuestionPosee(question=QUESTION, champ_vise=None)]


def test_ask_clarification_accompagne_dun_autre_outil_les_deux_sexecutent(contexte, outils):
    """Le prompt système dit de ne pas le faire. Quand il le fait quand même :
    tous s'exécutent, tous ont leur `tool_result`, la question gagne."""
    client = FauxClient(
        [
            message(
                appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1"),
                appel_outil(NOM_PRECISION, {"question": QUESTION}, id="tu_2"),
                appel_outil(NOM_RECHERCHER, id="tu_3"),
            )
        ]
    )

    evenements, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 1
    resultats = issue.tours[1].blocs
    assert [bloc["tool_use_id"] for bloc in resultats] == ["tu_1", "tu_2", "tu_3"]
    assert all(bloc["is_error"] is False for bloc in resultats)

    # La recherche a bien eu lieu — son `tool_result` est dans l'historique — mais son
    # résultat **ne part pas au client** : le tour est clos, l'assistant ne commentera
    # jamais ces produits, et les afficher serait une recommandation sans son « pourquoi ».
    #
    # L'enregistrement, lui, a été émis : il précède la question dans le message. C'est
    # l'asymétrie assumée de l'arbitrage 5 — on n'annule pas un événement déjà parti,
    # et toute règle qui n'en dépendrait pas exigerait de bufferiser le message entier.
    assert [type(evenement) for evenement in evenements] == [CriteresMisAJour, QuestionPosee]
    verifier_appairage(issue.tours)


def test_deux_ask_clarification_la_premiere_gagne_et_un_warning_est_logue(contexte, outils):
    """La seconde s'exécute quand même : elle a besoin de son `tool_result`."""
    seconde = "Vous avez une préférence de marque ?"
    client = FauxClient(
        [
            message(
                appel_outil(NOM_PRECISION, {"question": QUESTION}, id="tu_1"),
                appel_outil(NOM_PRECISION, {"question": seconde}, id="tu_2"),
            )
        ]
    )

    with structlog.testing.capture_logs() as journal:
        evenements, issue = jouer(client, contexte, outils, etat=etat_ecran())

    assert evenements == [QuestionPosee(question=QUESTION, champ_vise=None)]
    assert [bloc["tool_use_id"] for bloc in issue.tours[1].blocs] == ["tu_1", "tu_2"]

    alerte = [
        ligne
        for ligne in journal
        if ligne["event"] == "boucle.seconde_demande_de_precision_ignoree"
    ]
    assert len(alerte) == 1
    assert alerte[0]["log_level"] == "warning"
    assert alerte[0]["question"] == seconde


def test_le_champ_vise_remonte_dans_levenement(contexte, outils):
    """`champ_vise` sert la mesure du dialogue (métrique nº3), pas la recherche."""
    client = FauxClient(
        [
            message(
                appel_outil(
                    NOM_PRECISION,
                    {"question": QUESTION, "champ_vise": "panel_type"},
                    id="tu_1",
                )
            )
        ]
    )

    evenements, _ = jouer(client, contexte, outils, etat=etat_ecran())

    assert evenements == [QuestionPosee(question=QUESTION, champ_vise="panel_type")]


def test_une_question_vide_est_refusee_et_la_boucle_continue(contexte, outils):
    """`question` porte `min_length=1` : un outil terminal appelé à vide clorait le tour
    sur un silence."""
    client = FauxClient(
        [
            message(appel_outil(NOM_PRECISION, {"question": ""}, id="tu_1")),
            message(texte("Pardon — que cherchez-vous exactement ?")),
        ]
    )

    evenements, issue = jouer(client, contexte, outils, etat=etat_ecran())

    assert client.nombre_dappels == 2
    assert issue.tours[1].blocs[0]["is_error"] is True
    assert evenements == [Texte("Pardon — que cherchez-vous exactement ?")]
