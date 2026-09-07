"""Les deux points de coupe du cache de prompt (arbitrage 7, renversé le 2026-09-07).

Le premier point de coupe est constaté ailleurs — `test_boucle.py` vérifie que le
`systeme` et les `outils` d'un même tour sont identiques d'un appel à l'autre. Ce
fichier-ci porte sur le second, celui qui se déplace, et sur la seule propriété qui peut le
transformer en panne : **il ne doit rien modifier de ce qu'on lui donne.**

⚠️ **Pourquoi cette propriété et pas une autre.** Les blocs passés à `repondre()` sont ceux
que `session.tour()` va persister dans `tours_conversation`, et que `historique_de()`
rejouera au tour suivant. Un `cache_control` écrit en place y resterait : il reviendrait
dans l'historique, un nouveau serait posé par-dessus, et **le cinquième tour dépasserait la
limite de quatre points de coupe de l'API**. Le défaut ne se verrait pas au premier tour,
ni au deuxième — il se verrait en production, au cinquième, sous la forme d'un 400.

Le test qui compte est donc `test_les_messages_recus_ne_sont_pas_modifies`, et les autres
sont là pour qu'il ne passe pas par accident.
"""

import pytest

from raiyon.agent.client_anthropic import (
    BLOCS_SANS_CACHE_CONTROL,
    CACHE_EPHEMERE,
    avec_point_de_coupe,
)

# --------------------------------------------------------------------------- #
# Fabriques — les mêmes formes que celles qu'empile `boucle.repondre`
# --------------------------------------------------------------------------- #


def texte(contenu="Bonjour."):
    return {"type": "text", "text": contenu}


def resultat(identifiant="tu_1", contenu="{}"):
    return {"type": "tool_result", "tool_use_id": identifiant, "content": contenu}


def raisonnement(signature="sig"):
    return {"type": "thinking", "thinking": "", "signature": signature}


def client(*blocs):
    return {"role": "user", "content": list(blocs)}


def assistant(*blocs):
    return {"role": "assistant", "content": list(blocs)}


def coupes(messages):
    """Les (rang du message, rang du bloc) qui portent un `cache_control`."""
    return [
        (i, j)
        for i, message in enumerate(messages)
        for j, bloc in enumerate(message["content"])
        if "cache_control" in bloc
    ]


# --------------------------------------------------------------------------- #
# 1 — Où la coupe se pose
# --------------------------------------------------------------------------- #


def test_la_coupe_est_sur_le_dernier_bloc_du_dernier_message():
    messages = [
        client(texte("je cherche un écran")),
        assistant(texte("Voici.")),
        client(resultat()),
    ]

    marques = avec_point_de_coupe(messages)

    assert coupes(marques) == [(2, 0)]
    assert marques[2]["content"][0]["cache_control"] == CACHE_EPHEMERE


def test_la_coupe_est_sur_le_dernier_bloc_quand_le_message_en_porte_plusieurs():
    """Le message de reprise : les `tool_result` d'abord, le grief ensuite."""
    messages = [client(resultat("tu_1"), resultat("tu_2"), texte("Ta réponse a été refusée."))]

    marques = avec_point_de_coupe(messages)

    assert coupes(marques) == [(0, 2)]


def test_il_ny_a_jamais_quune_seule_coupe_dans_les_messages():
    """La seconde moitié de la garantie : la coupe système est posée à part, et les deux
    ensemble doivent rester sous la limite de quatre de l'API."""
    messages = [client(texte()), assistant(texte("a")), client(resultat()), assistant(texte("b"))]

    assert len(coupes(avec_point_de_coupe(messages))) == 1


# --------------------------------------------------------------------------- #
# 2 — ⭐ Ce que la fonction ne fait pas : modifier ce qu'on lui donne
# --------------------------------------------------------------------------- #


def test_les_messages_recus_ne_sont_pas_modifies():
    """🔴 **Le test de ce fichier.** Voir la docstring du module : muter en place ferait
    persister le marqueur, donc revenir dans l'historique, donc un 400 au cinquième tour."""
    bloc = resultat()
    messages = [client(texte("je cherche un écran")), client(bloc)]

    avec_point_de_coupe(messages)

    assert "cache_control" not in bloc
    assert coupes(messages) == []
    assert messages == [
        {"role": "user", "content": [{"type": "text", "text": "je cherche un écran"}]},
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": "{}"}],
        },
    ]


def test_deux_appels_de_suite_ne_cumulent_pas_les_marqueurs():
    """La contre-épreuve du précédent, dans la forme où le défaut se produirait vraiment :
    la boucle rappelle `repondre()` sur la **même** liste, allongée."""
    messages = [client(texte("je cherche un écran"))]

    premier = avec_point_de_coupe(messages)
    messages.append(assistant(texte("Voici.")))
    messages.append(client(resultat()))
    second = avec_point_de_coupe(messages)

    assert coupes(premier) == [(0, 0)]
    assert coupes(second) == [(2, 0)]
    assert coupes(messages) == []


def test_le_prefixe_nest_pas_recopie():
    """Le coût est constant : seuls la liste, le dernier message, sa liste de blocs et le
    bloc marqué sont neufs. Sans quoi la fonction recopierait tout l'historique à chaque
    appel — c'est-à-dire la chose même que le cache existe pour éviter."""
    messages = [client(texte("un")), client(texte("deux")), client(resultat())]

    marques = avec_point_de_coupe(messages)

    assert marques[0] is messages[0]
    assert marques[1] is messages[1]
    assert marques[2] is not messages[2]
    assert marques[2]["content"][0] is not messages[2]["content"][0]


# --------------------------------------------------------------------------- #
# 3 — Les blocs qui n'acceptent pas `cache_control`
# --------------------------------------------------------------------------- #


def test_la_coupe_remonte_au_dessus_dun_bloc_thinking():
    """Un `thinking` en dernier ne peut pas porter la coupe. On remonte : la queue sort du
    cache — le comportement d'aujourd'hui sur ces quelques jetons — au lieu d'un 400."""
    messages = [assistant(texte("Voici."), raisonnement())]

    marques = avec_point_de_coupe(messages)

    assert coupes(marques) == [(0, 0)]


def test_aucune_coupe_quand_aucun_bloc_ne_laccepte():
    messages = [assistant(raisonnement("a"), raisonnement("b"))]

    marques = avec_point_de_coupe(messages)

    assert coupes(marques) == []
    assert marques == messages


@pytest.mark.parametrize(
    "messages",
    [
        pytest.param([], id="aucun message"),
        pytest.param([client()], id="contenu vide"),
        pytest.param([{"role": "user", "content": "du texte nu"}], id="contenu non découpé"),
    ],
)
def test_les_formes_degenerees_passent_sans_lever(messages):
    """Ne pas poser de coupe coûte un gain ; lever coûterait le tour."""
    assert coupes(avec_point_de_coupe(messages)) == []


# --------------------------------------------------------------------------- #
# 4 — ⭐ Le relevé est lu sur le paquet installé, pas recopié
# --------------------------------------------------------------------------- #


def test_les_blocs_refuses_sont_ceux_que_le_sdk_refuse():
    """`BLOCS_SANS_CACHE_CONTROL` est une **mesure**, et ce test est son lecteur.

    Le dépôt a neuf précédents de capacité supposée sans être mesurée (§9.1). Celui-ci est
    vérifié contre les `TypedDict` du paquet installé plutôt qu'affirmé en commentaire : le
    jour où le SDK ajoute `cache_control` à `ThinkingBlockParam`, ce test rougit et
    l'ensemble se resserre au lieu de rester faux en silence.
    """
    from anthropic.types import (
        RedactedThinkingBlockParam,
        TextBlockParam,
        ThinkingBlockParam,
        ToolResultBlockParam,
        ToolUseBlockParam,
    )

    accepte = {
        type_.__name__: "cache_control" in type_.__annotations__
        for type_ in (
            TextBlockParam,
            ToolUseBlockParam,
            ToolResultBlockParam,
            ThinkingBlockParam,
            RedactedThinkingBlockParam,
        )
    }

    assert accepte == {
        "TextBlockParam": True,
        "ToolUseBlockParam": True,
        "ToolResultBlockParam": True,
        "ThinkingBlockParam": False,
        "RedactedThinkingBlockParam": False,
    }
    assert set(BLOCS_SANS_CACHE_CONTROL) == {"thinking", "redacted_thinking"}


# --------------------------------------------------------------------------- #
# 5 — Le câblage : la coupe part réellement dans la requête
# --------------------------------------------------------------------------- #


def test_la_requete_porte_les_deux_points_de_coupe(monkeypatch):
    """La fonction pure peut être juste et n'être appelée par personne. Ce test constate
    que `_appeler` la traverse, et que la coupe système est toujours là."""
    import anthropic

    from raiyon.agent.client_anthropic import ClientAnthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "factice-points-de-coupe")
    envoye = {}

    class FausseCreation:
        def create(self, **kwargs):
            envoye.update(kwargs)
            return anthropic.types.Message(
                id="msg_1",
                model="claude-sonnet-5",
                role="assistant",
                type="message",
                content=[{"type": "text", "text": "Voici."}],
                stop_reason="end_turn",
                usage={"input_tokens": 12, "output_tokens": 3},
            )

    client_llm = ClientAnthropic()
    monkeypatch.setattr(client_llm, "_client", type("Faux", (), {"messages": FausseCreation()})())

    messages = [client(texte("je cherche un écran"))]
    client_llm.repondre(systeme="SYSTÈME", outils=[], messages=messages)

    assert envoye["system"][0]["cache_control"] == CACHE_EPHEMERE
    assert envoye["messages"][0]["content"][0]["cache_control"] == CACHE_EPHEMERE
    assert coupes(messages) == [], "l'objet de l'appelant est ressorti marqué"
