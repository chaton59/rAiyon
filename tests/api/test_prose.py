"""La relecture de la prose : ce qui a été dit, et **rien d'autre**. Tests purs.

Deux propriétés se jouent ici, et la seconde ne se devine pas en lisant la table :

1. aucun **fait** n'est reconstruit depuis les `tool_result` — c'est l'arbitrage J, et
   c'est ce qui évite un second lecteur du protocole ;
2. le **message de reprise** de l'étape 9 est un bloc `text` de rôle `user` écrit pour le
   modèle. Le rendre afficherait la mécanique interne d'un rejet sous l'identité du
   client.
"""

import json

from faux_client import appel_outil, texte

from raiyon.agent.prompts import message_de_grief
from raiyon.api.prose import Interlocuteur, Parole, prose_de
from raiyon.tools.schema_outils import NOM_PRECISION, NOM_RECHERCHER

QUESTION = "Tu joues plutôt en compétitif ou en solo ?"


def _client(contenu: str) -> dict:
    return {"role": "user", "content": [texte(contenu)]}


def _assistant(*blocs: dict) -> dict:
    return {"role": "assistant", "content": list(blocs)}


def _resultats(*identifiants: str) -> dict:
    """Le bloc `user` que la boucle pose après un message à `tool_use`."""
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": identifiant,
                "content": json.dumps({"ok": True}),
                "is_error": False,
            }
            for identifiant in identifiants
        ],
    }


def test_un_historique_complet_rend_la_prose_dans_lordre_et_rien_dautre():
    """Le cas nominal : du texte, une question posée par outil, un outil muet.

    `search_products` ne dit rien — ses arguments sont des critères, pas des phrases —
    et son `tool_result` non plus : c'est un fait, et les faits passent par l'état, pas
    par la prose (arbitrage J).
    """
    historique = [
        _client("Je cherche un écran 144 Hz à 400 $ max"),
        _assistant(
            texte("Bonne base. Je regarde ce que le catalogue a."),
            appel_outil(NOM_RECHERCHER, id="tu_1"),
        ),
        _resultats("tu_1"),
        _assistant(
            texte("Il me reste une chose à savoir."),
            appel_outil(NOM_PRECISION, {"question": QUESTION}, id="tu_2"),
        ),
        _resultats("tu_2"),
    ]

    assert prose_de(historique) == (
        Parole(Interlocuteur.CLIENT, "Je cherche un écran 144 Hz à 400 $ max"),
        Parole(Interlocuteur.ASSISTANT, "Bonne base. Je regarde ce que le catalogue a."),
        Parole(Interlocuteur.ASSISTANT, "Il me reste une chose à savoir."),
        Parole(Interlocuteur.ASSISTANT, QUESTION),
    )


def test_la_question_dask_clarification_est_de_la_prose():
    """Elle n'est pas un bloc `text` : c'est un argument d'outil qui part au client
    **verbatim**. C'est ce qui l'a fait entrer au validateur à l'étape 9, et c'est la
    même raison qui la fait entrer ici."""
    historique = [_assistant(appel_outil(NOM_PRECISION, {"question": QUESTION}, id="tu_1"))]

    assert prose_de(historique) == (Parole(Interlocuteur.ASSISTANT, QUESTION),)


def test_les_autres_appels_doutil_ne_disent_rien():
    """Les arguments de `record_criteria` sont des critères. Les rendre en prose
    inventerait une phrase que personne n'a écrite."""
    historique = [
        _assistant(
            appel_outil(
                "record_criteria",
                {"categorie": "monitor", "budget_usd": "400"},
                id="tu_1",
            )
        ),
        _resultats("tu_1"),
    ]

    assert prose_de(historique) == ()


def test_les_tool_result_ne_sont_jamais_de_la_prose_malgre_leur_role_user():
    """⚠️ Les `tool_result` portent le rôle `user` : il n'existe pas de rôle « outil »."""
    historique = [_resultats("tu_1", "tu_2")]

    assert prose_de(historique) == ()


# --------------------------------------------------------------------------- #
# Le message de reprise de l'étape 9 — les deux formes
# --------------------------------------------------------------------------- #


def test_le_message_de_reprise_seul_nest_pas_rendu_comme_une_parole_du_client():
    """La forme la plus piégeuse : le message fautif ne portait que du texte, donc la
    reprise est un bloc `user` **indiscernable d'un message client par sa forme**.

    Sans ce filtre, une conversation rechargée afficherait « # Reprise — votre dernier
    message affirme des faits… » comme si le client l'avait tapé.
    """
    reprise = message_de_grief(("- **id_inconnu** — « monitor-0000000000 » : citer un id",))
    historique = [
        _client("montre-moi"),
        _assistant(texte("Je vous propose le monitor-0000000000 à 108 $.")),
        {"role": "user", "content": [texte(reprise)]},
        _assistant(texte("Voici trois écrans du catalogue.")),
    ]

    assert prose_de(historique) == (
        Parole(Interlocuteur.CLIENT, "montre-moi"),
        Parole(Interlocuteur.ASSISTANT, "Je vous propose le monitor-0000000000 à 108 $."),
        Parole(Interlocuteur.ASSISTANT, "Voici trois écrans du catalogue."),
    )


def test_le_message_de_reprise_qui_suit_des_tool_result_nest_pas_rendu_non_plus():
    """L'autre forme : le grief part dans le **même** bloc `user` que les `tool_result`,
    après eux (arbitrage D de l'étape 9). La présence d'un `tool_result` suffit alors."""
    reprise = message_de_grief(("- **montant_non_fourni** — « 42 $ » : citer un prix fourni",))
    historique = [
        _assistant(texte("Le monitor-1 est à 42 $."), appel_outil(NOM_RECHERCHER, id="tu_1")),
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_1",
                    "content": "{}",
                    "is_error": False,
                },
                texte(reprise),
            ],
        },
    ]

    assert prose_de(historique) == (Parole(Interlocuteur.ASSISTANT, "Le monitor-1 est à 42 $."),)


def test_le_texte_refuse_reste_dans_la_prose_parce_quil_reste_dans_lhistorique():
    """**À dire plutôt qu'à masquer.** Le message fautif n'est pas retiré de
    l'historique — le retirer casserait l'appairage des `tool_result` et rendrait le
    grief incompréhensible (étape 9). Il est donc relu, comme le modèle le relit.

    Ce n'est pas un défaut de cet endpoint : c'est la conséquence visible d'une décision
    de la boucle. Ce qui **n'est jamais parti au client** est le texte de la reprise ; le
    texte refusé, lui, a bien été écrit par l'assistant.
    """
    reprise = message_de_grief(("- **id_inconnu** — « x » : citer un id fourni",))
    historique = [
        _assistant(texte("Une affirmation fausse.")),
        {"role": "user", "content": [texte(reprise)]},
    ]

    assert prose_de(historique) == (Parole(Interlocuteur.ASSISTANT, "Une affirmation fausse."),)


# --------------------------------------------------------------------------- #
# Les formes dégénérées
# --------------------------------------------------------------------------- #


def test_un_historique_vide_rend_une_prose_vide():
    assert prose_de([]) == ()


def test_un_bloc_de_texte_vide_ne_produit_pas_de_parole():
    """Un message assistant qui n'a que des `tool_use` porte parfois un bloc `text` vide.
    Une bulle vide à l'écran n'est pas une parole."""
    historique = [_assistant(texte("   "), appel_outil(NOM_RECHERCHER, id="tu_1"))]

    assert prose_de(historique) == ()


def test_un_bloc_inconnu_est_ignore_plutot_que_de_faire_lever():
    """Même règle que `_depouiller()` dans la boucle : un bloc d'un type qu'on ne connaît
    pas ne doit pas rendre une conversation illisible."""
    historique = [{"role": "assistant", "content": [{"type": "thinking", "thinking": "…"}]}]

    assert prose_de(historique) == ()


def test_aucun_fait_ne_remonte_depuis_les_tool_result():
    """**Arbitrage J en assertion négative.** Le prix rendu par un outil est dans le
    `tool_result` ; il n'a rien à faire dans la prose, et le reconstruire demanderait un
    second lecteur du protocole."""
    historique = [
        _assistant(appel_outil(NOM_RECHERCHER, id="tu_1")),
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_1",
                    "content": json.dumps(
                        {"produits": [{"id": "monitor-1", "prix_usd": "329.99"}]}
                    ),
                    "is_error": False,
                }
            ],
        },
    ]

    paroles = prose_de(historique)

    assert paroles == ()
    assert all("329.99" not in parole.texte for parole in paroles)
