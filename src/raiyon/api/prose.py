"""La prose échangée, relue depuis les blocs persistés. **Module pur.**

### `GET /sessions/{id}` relit la prose, jamais les événements (arbitrage J)

Les `blocs` de `tours_conversation` ne sont **pas** une projection d'événements.
Reconstruire `criteria_updated` ou `products_found` depuis les `tool_result` demanderait un
**second lecteur du protocole**, donc une seconde vérité qui divergerait de la première au
premier changement de clé.

L'endpoint rend donc deux choses, et aucune n'est reconstruite :

* l'**état**, lu par `etat_de()` — c'est-à-dire par `depuis_jsonb()`, le lecteur qui
  existe déjà ;
* la **prose**, extraite ici : les blocs `text`, et l'argument `question` des `tool_use`
  nommés `ask_clarification`.

### Trois blocs de texte sur quatre partent au client ; le quatrième non

C'est le seul point de conception du module, et il ne se devine pas en lisant la table
`tours_conversation` : **tous les blocs `text` ne sont pas de la prose de dialogue.**

| Ce qu'on lit | Rôle | Va au client ? |
|---|---|---|
| le message du client | `user` | oui |
| le texte d'un message assistant | `assistant` | oui |
| la question d'`ask_clarification` | `assistant` (`tool_use`) | oui |
| le **message de reprise** de l'étape 9 | `user` | **non** |

Le message de reprise est un bloc `text` de rôle `user`, écrit **pour le modèle** par
`prompts/grief.v1.md`, et il dit lui-même « le client ne le voit pas ». Le rendre dans
l'historique afficherait à l'écran la mécanique interne d'un rejet, à la place et sous
l'identité du client. Deux formes existent, et elles se reconnaissent différemment :

1. **avec des `tool_result`** — le message fautif portait des `tool_use`, et le grief les
   suit dans le même bloc `user` (arbitrage D de l'étape 9). La présence d'un
   `tool_result` suffit alors à écarter tout le message ;
2. **seul** — le message fautif ne portait que du texte. Le bloc est alors indiscernable
   d'un message client **par sa forme**, et c'est son contenu qui le désigne.

Le second cas se reconnaît sur le **gabarit chargé**, jamais sur une phrase recopiée ici :
le message de reprise est le gabarit avec sa marque remplacée, donc il commence
exactement par le préfixe du gabarit. La reconnaissance est donc **dérivée**, comme le
français du fil (arbitrage H), et non heuristique.

⚠️ **Limite connue, et elle est datée.** La comparaison porte sur le gabarit *en vigueur*.
Une conversation persistée sous `grief.v1` puis relue après un `grief.v2` de l'étape 13
réafficherait ses anciens messages de reprise. Le correctif, s'il devient nécessaire,
tient en une ligne — comparer aux préfixes de **tous** les gabarits présents dans
`prompts/` — et il n'est pas pris maintenant parce qu'aucun `grief.v2` n'existe.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from raiyon.agent.prompts import GRIEF_V1, MARQUE_DES_GRIEFS, charger
from raiyon.tools.schema_outils import NOM_PRECISION

ROLE_API_CLIENT = "user"
"""⚠️ Les `tool_result` portent ce rôle aussi : il n'existe pas de rôle « outil » dans
l'API Anthropic. C'est exactement ce qui rend la lecture ci-dessous non triviale."""


class Interlocuteur(StrEnum):
    """Qui parle, **dans le vocabulaire du produit** et non dans celui du protocole.

    `user` désigne côté API aussi bien le client que les résultats d'outils ; le fil, lui,
    n'a que deux interlocuteurs et ils sont tous les deux humainement identifiables.
    """

    CLIENT = "client"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class Parole:
    """Un tour de parole affichable. Ni bloc, ni rôle d'API, ni numéro de tour."""

    interlocuteur: Interlocuteur
    texte: str


def prose_de(historique: Sequence[Mapping[str, Any]]) -> tuple[Parole, ...]:
    """La conversation telle qu'elle s'est dite, dans l'ordre, et **rien d'autre**.

    `historique` est ce que rend `session.historique_de()` : des messages `{role, content}`
    dans l'ordre des numéros de tour. Aucun fait n'est reconstruit — les critères, les
    sondages et les produits ne repassent pas par ici (arbitrage J).
    """
    paroles: list[Parole] = []
    for message in historique:
        du_client = message.get("role") == ROLE_API_CLIENT
        blocs: Sequence[Mapping[str, Any]] = message.get("content") or ()
        if du_client and any(bloc.get("type") == "tool_result" for bloc in blocs):
            # Des `tool_result`, et éventuellement le message de reprise qui les suit.
            # Rien de ce bloc n'a été dit par qui que ce soit.
            continue
        for bloc in blocs:
            parole = _parole_du_bloc(bloc, du_client=du_client)
            if parole is not None:
                paroles.append(parole)
    return tuple(paroles)


def _parole_du_bloc(bloc: Mapping[str, Any], *, du_client: bool) -> Parole | None:
    """La parole que porte un bloc, ou `None` s'il n'en porte pas.

    Les `tool_use` autres qu'`ask_clarification` n'en portent aucune : leurs arguments
    sont des critères et des champs, pas des phrases. C'est la frontière de §3.4ter — le
    modèle met en mots, le code fournit les faits — appliquée à la relecture.
    """
    genre = bloc.get("type")
    if genre == "text":
        texte = str(bloc.get("text", "")).strip()
        if not texte or (du_client and _est_un_message_de_reprise(texte)):
            return None
        return Parole(Interlocuteur.CLIENT if du_client else Interlocuteur.ASSISTANT, texte)
    if genre == "tool_use" and bloc.get("name") == NOM_PRECISION:
        question = str((bloc.get("input") or {}).get("question", "")).strip()
        # La question part au client **verbatim** : c'est de la prose, au même titre qu'un
        # bloc `text`, et c'est ce qui l'a fait entrer au validateur à l'étape 9.
        return Parole(Interlocuteur.ASSISTANT, question) if question else None
    return None


def prefixe_de_reprise() -> str:
    """Ce par quoi commence tout message de reprise : le gabarit **avant** sa marque.

    Dérivé du fichier, jamais recopié. `message_de_grief()` construit son texte en
    remplaçant `MARQUE_DES_GRIEFS` dans ce même gabarit : le préfixe est donc exact au
    caractère près, et il le reste si l'étape 13 réécrit le corps du message.
    """
    return charger(GRIEF_V1).split(MARQUE_DES_GRIEFS, 1)[0].strip()


def _est_un_message_de_reprise(texte: str) -> bool:
    """Un gabarit sans préfixe ne reconnaîtrait plus rien — mieux vaut ne rien filtrer.

    Le cas ne peut se produire qu'en mettant la marque en toute première ligne du fichier.
    Rendre `False` affiche alors un message de reprise au client, ce qui est laid ;
    rendre `True` sur un préfixe vide masquerait **tous** les messages du client, ce qui
    est une conversation vide. Le mauvais choix est le moins mauvais des deux.
    """
    prefixe = prefixe_de_reprise()
    return bool(prefixe) and texte.startswith(prefixe)
