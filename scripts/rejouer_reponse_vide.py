"""Rejoue l'historique **exact** d'une session contre l'API réelle, et mesure.

Le chemin `boucle.reponse_vide` s'est déclenché en conversation réelle (session
`0fdcf1d5…`, tours 10 et 14) : un message assistant ne portant qu'un bloc `thinking`.
Le commentaire de `client_anthropic.py` annonce « pas de thinking étendu en v1» ; la
base dit le contraire. Ce script ne suppose rien — il appelle.

Trois questions, trois variantes, toutes sur le **même** historique relu en base, avec
le **même** `systeme` et les **mêmes** `outils` que le serveur :

* `A_verbatim`  — l'historique tel quel, blocs `thinking` signés réinjectés.
  Répond à : *l'API accepte-t-elle un bloc `thinking` signé sans thinking demandé ?*
* `B_sans_thinking` — les mêmes messages, blocs `thinking` retirés.
  Répond à : *le filtrage est-il seulement possible, et change-t-il l'issue ?*
* `C_max_tokens_8192` — variante A, plafond quadruplé.
  Répond à : *le message vide est-il une troncature ou une réponse complète ?*

Usage :
    uv run python scripts/rejouer_reponse_vide.py [session_uuid] [--jusqu-au N]

`--jusqu-au N` coupe l'historique **avant** le tour N : `--jusqu-au 14` rejoue donc
l'appel qui a produit le tour 14. Défaut : le dernier tour assistant vide trouvé.
"""

from __future__ import annotations

import argparse
import json
import uuid
from collections.abc import Sequence
from typing import Any, cast

import anthropic
from anthropic.types import MessageParam, ToolParam
from sqlalchemy import select

from raiyon.agent.prompts import prompt_systeme
from raiyon.config import cle_api, get_settings
from raiyon.db.engine import session_scope
from raiyon.db.models import TourConversation
from raiyon.tools.schema_outils import schema_des_outils

SESSION_PAR_DEFAUT = "0fdcf1d5-a279-4068-b754-6774d20722f6"


def historique_brut(identifiant: uuid.UUID) -> list[tuple[int, str, list[dict[str, Any]]]]:
    """Les tours de la session, numéro compris — `historique_de()` le perd."""
    with session_scope() as base:
        lignes = base.scalars(
            select(TourConversation)
            .where(TourConversation.session_id == identifiant)
            .order_by(TourConversation.numero)
        ).all()
        return [(ligne.numero, ligne.role, list(ligne.blocs)) for ligne in lignes]


def premier_tour_vide(tours: Sequence[tuple[int, str, list[dict[str, Any]]]]) -> int | None:
    """Le dernier tour assistant sans `text` ni `tool_use`. C'est celui qu'on rejoue."""
    vides = [
        numero
        for numero, role, blocs in tours
        if role == "assistant"
        and not any(bloc.get("type") in {"text", "tool_use"} for bloc in blocs)
    ]
    return vides[-1] if vides else None


def sans_thinking(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les mêmes messages, blocs `thinking` retirés — et les messages devenus vides aussi.

    Retirer un bloc peut vider un message ; l'API refuse un `content` vide. Le message
    disparaît alors, ce qui est précisément le coût que la variante mesure.
    """
    filtres = []
    for message in messages:
        blocs = [bloc for bloc in message["content"] if bloc.get("type") != "thinking"]
        if blocs:
            filtres.append({"role": message["role"], "content": blocs})
    return filtres


def appeler(
    client: anthropic.Anthropic,
    *,
    etiquette: str,
    systeme: str,
    outils: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    max_tokens: int,
    **surcharges: object,
) -> None:
    """Un appel, et ce qu'il rend — ou l'erreur, qui est une mesure aussi.

    `surcharges` part tel quel dans `messages.create()` : c'est ce qui permet de mesurer
    `thinking=` et `output_config=` sans écrire une seconde fonction d'appel qui
    divergerait de celle-ci.
    """
    print(f"\n{'=' * 72}\n{etiquette}")
    print(f"  messages={len(messages)}  max_tokens={max_tokens}  surcharges={surcharges}")
    types_envoyes = sorted(
        {bloc.get("type") for message in messages for bloc in message["content"]}
    )
    print(f"  types envoyés : {types_envoyes}")
    try:
        reponse = client.messages.create(
            model=get_settings().model_agent,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": systeme, "cache_control": {"type": "ephemeral"}}],
            # Les mêmes `cast` que `ClientAnthropic._appeler` : mêmes types entrants,
            # même appel.
            tools=cast(list[ToolParam], outils),
            messages=cast(list[MessageParam], messages),
            # `cast` parce que `messages.create` est surchargée : mypy ne peut pas
            # résoudre une surcharge sur un `**kwargs` typé. Ce script mesure des
            # paramètres que le dépôt ne passe pas encore ; les nommer un par un ici
            # fixerait d'avance la liste de ce qu'on a le droit de mesurer.
            **cast(dict[str, Any], surcharges),
        )
    except anthropic.APIStatusError as erreur:
        print(f"  ❌ {erreur.__class__.__name__} {erreur.status_code}")
        print(f"     {erreur.message}")
        return

    blocs = [bloc.model_dump(mode="json", exclude_none=True) for bloc in reponse.content]
    print(f"  ✅ fin={reponse.stop_reason!r}")
    print(f"     types_de_blocs={sorted({bloc['type'] for bloc in blocs})}")
    print(
        f"     jetons  entrée={reponse.usage.input_tokens}"
        f"  sortie={reponse.usage.output_tokens}"
        f"  cache_lu={reponse.usage.cache_read_input_tokens}"
    )
    for bloc in blocs:
        if bloc["type"] == "thinking":
            print(
                f"     thinking : len(thinking)={len(bloc.get('thinking', ''))}"
                f"  len(signature)={len(bloc.get('signature', ''))}"
            )
        elif bloc["type"] == "text":
            apercu = bloc["text"][:160].replace("\n", " ")
            print(f"     text ({len(bloc['text'])} car.) : {apercu}…")
        elif bloc["type"] == "tool_use":
            print(f"     tool_use : {bloc['name']} {json.dumps(bloc['input'])[:120]}")
        else:
            print(f"     {bloc['type']} : {sorted(bloc)}")


def main() -> None:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("session", nargs="?", default=SESSION_PAR_DEFAUT)
    analyseur.add_argument("--jusqu-au", type=int, default=None, dest="jusqu_au")
    arguments = analyseur.parse_args()

    identifiant = uuid.UUID(arguments.session)
    tours = historique_brut(identifiant)
    print(f"session {identifiant} — {len(tours)} tours en base")
    for numero, role, blocs in tours:
        types = ",".join(str(bloc.get("type")) for bloc in blocs)
        print(f"  {numero:>3} {role:<9} [{types}]")

    cible = arguments.jusqu_au or premier_tour_vide(tours)
    if cible is None:
        raise SystemExit("aucun tour assistant vide dans cette session")
    print(f"\nrejoue l'appel qui a produit le tour {cible} (historique coupé avant)")

    messages = [{"role": role, "content": blocs} for numero, role, blocs in tours if numero < cible]
    systeme = prompt_systeme()
    outils = list(schema_des_outils())
    client = anthropic.Anthropic(api_key=cle_api())

    print(f"prompt système : {systeme.version} ({systeme.empreinte})")
    print(f"outils : {[outil['name'] for outil in outils]}")

    appeler(
        client,
        etiquette="A_verbatim — thinking signés réinjectés, max_tokens du dépôt",
        systeme=systeme.texte,
        outils=outils,
        messages=messages,
        max_tokens=2048,
    )
    appeler(
        client,
        etiquette="B_sans_thinking — mêmes messages, blocs thinking retirés",
        systeme=systeme.texte,
        outils=outils,
        messages=sans_thinking(messages),
        max_tokens=2048,
    )
    appeler(
        client,
        etiquette="C_max_tokens_8192 — variante A, plafond quadruplé",
        systeme=systeme.texte,
        outils=outils,
        messages=messages,
        max_tokens=8192,
    )
    # D et E mesurent la cause plutôt que le symptôme. Le dépôt croit ne pas avoir
    # demandé de thinking (docstring de `client_anthropic.py`, arbitrage 12) ; sur
    # `claude-sonnet-5`, **ne pas passer `thinking` vaut `{"type": "adaptive"}`**. Les
    # blocs `thinking` vides à grosse signature de la base en sont la trace, et les
    # jetons de raisonnement se paient et comptent dans `max_tokens`.
    appeler(
        client,
        etiquette="D_thinking_disabled — le paramètre que le dépôt croyait par défaut",
        systeme=systeme.texte,
        outils=outils,
        messages=messages,
        max_tokens=2048,
        thinking={"type": "disabled"},
    )
    appeler(
        client,
        etiquette="E_effort_low — thinking gardé, profondeur bornée",
        systeme=systeme.texte,
        outils=outils,
        messages=messages,
        max_tokens=2048,
        output_config={"effort": "low"},
    )


if __name__ == "__main__":
    main()
