"""Le contrat d'appel au modèle : un `Protocol`, et la forme de sa réponse.

### Un `Protocol`, comme `DepotProduits` (arbitrage 2 de l'étape 8)

La dépendance va dans le bon sens : la boucle ne connaît pas le SDK, et un faux client
scripté est possible sans que rien de la boucle ne bouge. C'est exactement le motif que
`matching/depot.py` emploie pour la source de produits, et il vaut ici pour la même
raison — la pièce coûteuse et non déterministe est derrière une frontière nommée.

*Alternative écartée — ne tester la boucle que par cassettes à l'étape 12.* Elle teste la
vérité, mais rien avant l'étape 12, et surtout **un défaut de réenchaînement d'état ne se
voit pas dans une cassette** : la cassette rejoue les réponses du modèle, pas notre
gestion de l'état entre deux `tool_use`.

⚠️ **Tension avec §3.15, à ne pas laisser passer pour un reniement.** §3.15 écarte les
« mocks écrits à la main » au motif qu'on y teste ses propres suppositions sur ce que le
LLM répond. La nuance est que le faux client de `tests/agent/` ne teste pas *ce que le
modèle répond* — il teste *ce que la boucle fait d'une réponse donnée* : enchaînement,
état, terminalité, appairage des `tool_result`. C'est légitime, et **ça ne remplace pas**
les cassettes de l'étape 12, qui restent au plan.

### `blocs` est du dictionnaire brut, pas un type du SDK

`ReponseLLM.blocs` porte les blocs de contenu tels quels, sérialisables en JSONB sans
conversion : c'est ce que `tours_conversation.blocs` stocke, et ce que l'historique
réinjecte au tour suivant. Un type du SDK obligerait à convertir deux fois et ferait
entrer `anthropic` dans la signature de la boucle.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

MAX_TOKENS = 2048
"""Arbitrage 12 : une recommandation de trois produits avec son pourquoi tient largement
dedans, et un plafond bas borne le coût d'une itération qui part en boucle."""


@dataclass(frozen=True, slots=True)
class ReponseLLM:
    """Un tour de parole du modèle : ses blocs de contenu, et pourquoi il s'est arrêté."""

    blocs: list[dict[str, Any]]
    """Les blocs bruts (`text`, `tool_use`), sérialisables tels quels en JSONB."""

    fin: str
    """Le `stop_reason` de l'API : `end_turn`, `tool_use`, `max_tokens`, `stop_sequence`."""


@dataclass(frozen=True, slots=True)
class Usage:
    """Ce qu'un appel a consommé. **Hors du `Protocol`, et hors de `ReponseLLM`.**

    ### Pourquoi elle n'entre pas dans `ReponseLLM` (étape 13, jalon 1)

    `ReponseLLM` est ce que la **boucle** reçoit, et la boucle n'a que faire du coût : y
    ajouter un champ obligerait le faux client de l'étape 8, le client de cassette et les
    surcharges de l'API à le fabriquer, pour une information qu'aucun d'eux ne possède ni
    n'utilise. C'est la raison qui a fait écarter la capture de l'identifiant de modèle
    résolu au jalon 0, et elle vaut toujours.

    Elle vit donc **à côté** : `ClientAnthropic` pose son dernier `Usage` sur lui-même, et
    seul l'enregistreur de cassettes le lit — par `getattr`, sur un client qui peut ne pas
    en avoir. Le rejeu n'en a jamais, et c'est correct : une cassette rejouée ne consomme
    rien.

    ### Ce qu'elle sert, et ce n'est pas de la curiosité

    La campagne v1 de l'étape 13 s'est arrêtée au milieu — crédits épuisés — et **personne
    ne pouvait dire ce qu'elle avait consommé**. Les jetons étaient dans les logs, ligne
    par ligne, sans cumul et sans rien qui les rattache à une prise. Une campagne coûte
    deux cents appels : savoir où on en est pendant qu'elle tourne n'est pas un confort.
    """

    appels: int
    jetons_entree: int
    jetons_sortie: int
    cache_ecrit: int
    cache_lu: int
    """Les deux compteurs de cache sont l'unique façon de constater que l'arbitrage 7
    produit son effet. Une campagne dont `cache_lu` s'effondre a repayé son préfixe, ce
    qui arrive quand on enregistre par petits bouts espacés."""

    def __add__(self, autre: "Usage") -> "Usage":
        """Le cumul d'une campagne. `sum()` n'est pas utilisé : il partirait de `0`."""
        return Usage(
            appels=self.appels + autre.appels,
            jetons_entree=self.jetons_entree + autre.jetons_entree,
            jetons_sortie=self.jetons_sortie + autre.jetons_sortie,
            cache_ecrit=self.cache_ecrit + autre.cache_ecrit,
            cache_lu=self.cache_lu + autre.cache_lu,
        )

    def en_ligne(self) -> str:
        """Une ligne lisible en cours de campagne. Pas un format de fichier."""
        return (
            f"{self.appels} appel(s) · {self.jetons_entree} jetons entrants "
            f"({self.cache_lu} lus du cache, {self.cache_ecrit} écrits) · "
            f"{self.jetons_sortie} sortants"
        )


USAGE_NUL = Usage(appels=0, jetons_entree=0, jetons_sortie=0, cache_ecrit=0, cache_lu=0)
"""Le neutre du cumul. Nommé plutôt que reconstruit à chaque campagne."""


class ClientLLM(Protocol):
    """Ce que la boucle attend d'un modèle. Rien de plus, et surtout rien du SDK.

    ⚠️ ~~**La signature est ce qui rend l'étape 10 possible sans réécrire la boucle**
    (arbitrage 1) : remplacer `messages.create()` par `messages.stream()` change
    l'implémentation de cette méthode, pas son contrat.~~

    **Troisième copie de la promesse renversée, barrée avec les deux autres** (voir
    `evenements.py` et `boucle.py`). L'étape 10 n'a pas remplacé `messages.create()` : elle
    n'en a pas eu l'usage, faute de consommateur de delta. Ce que la signature a réellement
    acheté est ailleurs, et c'est réel — `dependency_overrides` remplace ce `Protocol` par
    le faux client de l'étape 8, et `tests/integration/test_api.py` teste ainsi les
    endpoints, le verrou et le générateur SSE **sans consommer un seul jeton**.
    """

    def repondre(
        self,
        *,
        systeme: str,
        outils: Sequence[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> ReponseLLM: ...
