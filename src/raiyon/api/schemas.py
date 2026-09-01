"""Ce qui entre et ce qui sort en JSON ordinaire — le fil SSE a son propre module.

### Une seule structure entre, et elle est étroite

`MessageEntrant` est le seul corps de requête du projet. Son `extra="forbid"` transforme
une faute de frappe du front en **422** plutôt qu'en message vide envoyé au modèle : c'est
la même décision que `_Arguments` dans `raiyon.tools.outils`, pour la même raison — un
champ inventé est une erreur, pas un oubli.

`max_length` n'était demandé nulle part et il est là quand même : Starlette ne borne pas
la taille d'un corps de requête, et rien d'autre sur le chemin ne le ferait. Sans lui, un
message de plusieurs mégaoctets serait persisté en base **puis** envoyé à l'API. La borne
est large (aucun message de client réel ne l'approche) et son seul rôle est d'exister.

### Les critères ne sont pas re-typés ici, et c'est délibéré

`EtatExpose.criteres` est une liste de dictionnaires, pas une liste de modèles Pydantic.
Leur forme est nommée **une seule fois**, dans `serialisation.criteres_serialises()`,
parce que la même structure voyage sur le fil SSE dans `criteria_updated`. La retyper ici
donnerait deux déclarations de la même chose, donc deux occasions de diverger — et le
front devrait alors savoir laquelle des deux il lit.

C'est le raisonnement d'`en_tool_result()` : « le seul endroit où une clé porte un nom ».
"""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

LONGUEUR_MAX_MESSAGE = 4000
"""Caractères. Une borne de sécurité, pas une règle de produit — voir la docstring."""


class MessageEntrant(BaseModel):
    """Le message du client. **Le seul corps de requête du projet.**"""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=LONGUEUR_MAX_MESSAGE)


class SessionCreee(BaseModel):
    """La réponse de `POST /sessions`. L'UUID est généré côté application (`uuid4`)."""

    id: uuid.UUID


class ErreurExposee(BaseModel):
    """Un échec porteur d'un `CodeErreur`, **à plat** — la même forme que l'événement
    `error` du fil.

    Elle n'existe que pour être la même des deux côtés de la ligne de partage de
    l'arbitrage E : avant le premier octet, c'est le corps d'un **409** ; après, c'est la
    charge utile d'un `error`. `HTTPException` emballe son `detail`, donc sans elle le
    front porterait **deux** lecteurs d'erreur pour un seul vocabulaire — et la promesse
    écrite dans la docstring de `CodeErreur` serait fausse.

    Le 404 et le 422 gardent la forme de FastAPI : ils ne portent pas de `CodeErreur`.
    """

    code: str
    message: str


class EtatExpose(BaseModel):
    """Ce que le code a compris du besoin, lu par `depuis_jsonb()` et **pas reconstruit**.

    `libelle_categorie` accompagne `categorie` pour la même raison que sur le fil : le
    front ne doit pas avoir de table de traduction à lui (arbitrage H).
    """

    categorie: str | None
    libelle_categorie: str | None
    criteres: list[dict[str, Any]]
    budget_usd: str | None
    """Chaîne, comme partout : un flottant JSON perdrait des décimales sur un montant."""

    optimisation: str
    libelle_optimisation: str
    """Le français du jeton, pour la même raison que `libelle_categorie` : le front ne
    doit pas avoir de table de traduction à lui (arbitrage H). Les deux voyagent
    ensemble — le jeton se compare, le libellé s'affiche."""


class ParoleExposee(BaseModel):
    """Un tour de parole affichable. `interlocuteur` vaut `client` ou `assistant`."""

    interlocuteur: str
    texte: str


class SessionExposee(BaseModel):
    """L'état et la prose — les deux seules choses que `GET /sessions/{id}` rend.

    Pas d'événements : les reconstruire depuis les `tool_result` demanderait un second
    lecteur du protocole, donc une seconde vérité (arbitrage J).
    """

    id: uuid.UUID
    statut: str
    etat: EtatExpose
    prose: list[ParoleExposee]


class PromptExpose(BaseModel):
    """La version du prompt système et son empreinte — §3.14, rendues à l'extérieur.

    C'est ce qui permet de dire, depuis une autre machine, **quelle** rédaction tourne :
    l'étape 12 stocke la même empreinte dans ses cassettes.
    """

    version: str
    empreinte: str


class Sante(BaseModel):
    """`GET /health` : les trois choses qu'il faut savoir avant de tenir la démonstration.

    `strict` est une **mesure**, pas un réglage : le mode retenu par le client au premier
    appel (arbitrage 11 de l'étape 8). Le lire ici évite d'avoir à fouiller les logs.
    """

    base: bool
    prompt: PromptExpose
    strict: bool
