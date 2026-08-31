"""L'implémentation SDK du `ClientLLM`. **Le seul module du projet qui importe `anthropic`.**

Deux tests le vérifient sur le disque plutôt que sur la discipline — `raiyon.catalogue`
et `raiyon.tools` sont balayés module par module, dans un interpréteur neuf. La frontière
n'a donc pas besoin d'être rappelée en revue.

---

### Le cache de prompt : un seul point de coupe, sur le bloc système (arbitrage 7)

```python
system = [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]
```

Le préfixe mis en cache est `tools` + `system`. Une coupe posée sur le système couvre
donc **aussi** les cinq définitions d'outils, qui sont la partie la plus lourde et la
plus stable de la requête. Un second point de coupe n'aurait rien à protéger de plus.

⚠️ **Ce que ça interdit, et c'est une règle de conception, pas une optimisation :** le
préfixe doit être identique **octet pour octet** d'un appel à l'autre. Ni la date, ni
l'état de session, ni le numéro de tour, ni la catégorie courante ne vont dans le prompt
système. L'état ne vit que dans les `tool_result`. Un test de `tests/agent/` constate que
deux appels d'un même tour reçoivent un `systeme` et des `outils` identiques.

### Le repli `strict=False` : automatique, mémorisé, et logué (arbitrage 11)

`schema_des_outils(strict=False)` existe depuis l'étape 7 mais n'avait **jamais été
exercé contre l'API réelle**, et le sous-ensemble de JSON Schema admis sous ce drapeau
n'est écrit nulle part dans le paquet installé. Le dépôt a trois précédents — `smt` à
l'étape 3, `temperature=0` et `nom_fr` à l'étape 5 — où une capacité supposée disponible
n'avait pas été mesurée.

Donc : sur un `BadRequestError` **tant que le mode n'est pas établi**, on réessaie une
fois en retirant `strict`, on loggue en `WARNING` le message de l'API, et on garde ce
mode pour la suite du processus. Une fois le mode établi, un `BadRequestError` remonte —
il ne parle plus du schéma mais de l'historique, et le masquer par un second essai ferait
payer deux appels pour une erreur qui ne va pas se résoudre.

`make fumee` exerce ce chemin sans la boucle, et dit quel mode a été retenu.

### Deux réglages tranchés au plus simple (arbitrage 12)

* **Pas de thinking étendu en v1.** Avec le tool use, les blocs `thinking` doivent être
  réinjectés verbatim et persistés ; ça alourdit l'historique pour un raisonnement qui
  tient en deux lignes. À rouvrir à l'étape 13 si la métrique nº4 plafonne.
* **On ne fixe pas `temperature`.** Le défaut du modèle. Le dépôt s'est déjà fait prendre
  à supposer que `temperature=0` donnait du déterminisme ; on ne le suppose plus, et on
  ne le revendique nulle part.
"""

from collections.abc import Sequence
from typing import Any, cast

import anthropic
import structlog
from anthropic.types import MessageParam, ToolParam

from raiyon.agent.client import MAX_TOKENS, ReponseLLM
from raiyon.config import cle_api, get_settings

logueur = structlog.get_logger(__name__)


def sans_strict(outils: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les mêmes définitions, drapeau `strict` retiré. Le repli de l'arbitrage 11.

    Retirer la clé plutôt que la poser à `False` : `strict` absent est le comportement
    historique de l'API, et un `False` explicite suppose que le champ est accepté partout
    où il pourrait ne pas l'être. C'est la supposition qu'on cherche justement à ne plus
    faire.
    """
    return [{cle: valeur for cle, valeur in outil.items() if cle != "strict"} for outil in outils]


class ClientAnthropic:
    """Le `ClientLLM` réel. Une instance par processus, et elle mémorise son mode.

    Le mode `strict` n'est pas un réglage : c'est une **mesure**, faite au premier appel
    et conservée. La consigner sur l'instance plutôt que dans la configuration évite de
    demander à l'utilisateur de deviner ce que l'API accepte.
    """

    def __init__(self, *, modele: str | None = None, max_tokens: int = MAX_TOKENS) -> None:
        self._client = anthropic.Anthropic(api_key=cle_api())
        self._modele = modele if modele is not None else get_settings().model_agent
        self._max_tokens = max_tokens
        self._replie = False
        """Vrai une fois le repli constaté. Vaut pour la durée du processus."""

        self._mode_etabli = False
        """Vrai dès qu'un appel a abouti. Après quoi un `BadRequestError` remonte."""

    @property
    def strict(self) -> bool:
        """Le mode retenu. `make fumee` et les logs de la boucle l'affichent."""
        return not self._replie

    def repondre(
        self,
        *,
        systeme: str,
        outils: Sequence[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> ReponseLLM:
        """Un appel, et au plus un second si l'API refuse `strict` avant tout succès."""
        try:
            return self._appeler(systeme, outils, messages)
        except anthropic.BadRequestError as erreur:
            if self._replie or self._mode_etabli:
                raise
            logueur.warning(
                "client_anthropic.strict_refuse",
                message=str(erreur),
                consequence="repli sur des définitions d'outils sans le drapeau strict",
            )
            self._replie = True
            return self._appeler(systeme, outils, messages)

    def _appeler(
        self,
        systeme: str,
        outils: Sequence[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> ReponseLLM:
        definitions = sans_strict(outils) if self._replie else list(outils)
        message = self._client.messages.create(
            model=self._modele,
            max_tokens=self._max_tokens,
            # Le **seul** point de coupe du cache. Le préfixe couvert est
            # `tools` + `system` : les cinq définitions d'outils sont dedans.
            system=[{"type": "text", "text": systeme, "cache_control": {"type": "ephemeral"}}],
            tools=cast(list[ToolParam], definitions),
            messages=cast(list[MessageParam], messages),
        )
        self._mode_etabli = True

        usage = message.usage
        logueur.info(
            "client_anthropic.reponse",
            modele=self._modele,
            strict=self.strict,
            fin=message.stop_reason,
            jetons_entree=usage.input_tokens,
            jetons_sortie=usage.output_tokens,
            # Les deux compteurs de cache sont l'unique façon de constater que
            # l'arbitrage 7 produit son effet ; sans eux, « le cache est activé » reste
            # une affirmation de code.
            cache_ecrit=usage.cache_creation_input_tokens,
            cache_lu=usage.cache_read_input_tokens,
        )
        return ReponseLLM(
            blocs=[bloc.model_dump(mode="json", exclude_none=True) for bloc in message.content],
            fin=message.stop_reason or "end_turn",
        )
