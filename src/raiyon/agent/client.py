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
