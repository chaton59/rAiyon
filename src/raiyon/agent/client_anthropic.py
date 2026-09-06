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

### Le raisonnement : adaptatif, résumé, borné par `max_tokens` (étape 17)

```python
thinking = {"type": "adaptive", "display": "summarized"}
```

⚠️ **Cette section disait exactement l'inverse, et c'est le quatrième précédent de
capacité supposée sans être mesurée — le premier à être inversé.** Elle annonçait « pas
de thinking étendu en v1 » (arbitrage 12), au motif que les blocs `thinking` alourdiraient
l'historique. La phrase était fausse **dès le premier appel du projet**, et pour une
raison qu'aucune relecture ne pouvait attraper : sur `claude-sonnet-5`, le raisonnement
adaptatif est **actif par défaut**, et le défaut de `display` est `omitted`. L'API
renvoyait donc des blocs `{"thinking": "", "signature": "…"}` — du raisonnement réel,
facturé sur `max_tokens`, réinjecté dans l'historique, et **vide à la lecture**.

Les 160 blocs `thinking` de `evals/cassettes/` en portent la preuve : tous signés, tous
sans une lettre de texte. Le dépôt payait le raisonnement, le transportait, et croyait
l'avoir désactivé.

Les trois précédents étaient des capacités **absentes** qu'on avait crues présentes —
`smt` à l'étape 3, `temperature=0` à l'étape 5, `nom_fr` à l'étape 5. Celui-ci est
l'inverse : une capacité **présente** qu'on avait crue absente. La leçon ne change pas de
camp — ce qui n'est pas mesuré n'est pas connu — mais elle vaut désormais dans les deux
sens, et un commentaire qui dit « on n'utilise pas X » est une affirmation à vérifier au
même titre qu'un « X marche ».

**Ce qui est vrai, et mesuré le 2026-09-04 :**

* `{"type": "enabled", "budget_tokens": N}` est **refusé** par ce modèle — HTTP 400,
  *« "thinking.type.enabled" is not supported for this model. Use "thinking.type.adaptive"
  and "output_config.effort" to control thinking behavior. »* Le budget de jetons de
  raisonnement n'existe plus comme paramètre ; la borne dure qui reste est `MAX_TOKENS`.
* `display: "summarized"` est ce qui rend le texte non vide. C'est un **résumé produit par
  l'API**, jamais la trace brute du modèle — le dashboard de l'étape 17 l'écrit à l'écran,
  et ce module ne prétend pas le contraire.
* `output_config.effort` n'est **pas** fixé : son défaut est `high`, et trois mesures à
  `low` / `medium` / `high` sur le même message ont rendu 165, 280 et 187 jetons de
  sortie — soit du bruit, sur cette charge. Le fixer serait remplacer un pari non mesuré
  par un autre. C'est le levier à ouvrir si la métrique nº4 bouge, et pas avant.

### On ne fixe pas non plus `temperature` (arbitrage 12, celui-là tient)

Le défaut du modèle. Le dépôt s'est déjà fait prendre à supposer que `temperature=0`
donnait du déterminisme ; on ne le suppose plus, et on ne le revendique nulle part.
"""

from collections.abc import Sequence
from typing import Any, Literal, cast

import anthropic
import structlog
from anthropic.types import MessageParam, ThinkingConfigParam, ToolParam

from raiyon.agent.client import EFFORT_NON_FIXE, MAX_TOKENS, ReponseLLM, Usage
from raiyon.config import cle_api, get_settings

logueur = structlog.get_logger(__name__)

DISPLAY: Literal["summarized"] = "summarized"
"""Le mode d'affichage du raisonnement, **et le maximum que l'API accorde**.

Nommé à part parce que deux endroits le lisent : la requête ci-dessous, et la propriété
`display` que l'observation écrit dans `appels_modele`. Une valeur écrite deux fois est le
motif que ce dépôt a déjà payé trois fois."""

THINKING: ThinkingConfigParam = {"type": "adaptive", "display": DISPLAY}
"""Le raisonnement demandé à chaque appel. **`display` est le seul champ qui change quelque
chose** — l'adaptatif tournait déjà, en silence. Voir la docstring du module."""


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

        self.dernier_usage: Usage | None = None
        """Ce que le **dernier** appel a consommé, ou `None` avant le premier.

        Public et mutable, contrairement au reste de cet objet : c'est une sortie
        d'observation, pas un réglage. Lue par `ClientEnregistreur` via `getattr`, donc
        sans que le `Protocol` `ClientLLM` en entende parler."""

    @property
    def strict(self) -> bool:
        """Le mode retenu. `make fumee` et les logs de la boucle l'affichent."""
        return not self._replie

    # Trois lectures publiques, ajoutées à l'étape 17 pour `ClientJournalisant`. Elles
    # décrivent **la requête qui part**, et c'est ce qui les rend légitimes : le décorateur
    # ne les devine pas, il les lit sur celui qui les envoie. Hors du `Protocol` — la
    # boucle n'en a que faire, et un client de cassette n'a rien à en dire.

    @property
    def modele(self) -> str:
        """L'identifiant de modèle réellement envoyé, défaut de configuration résolu."""
        return self._modele

    @property
    def effort(self) -> str:
        """`defaut` tant que `output_config.effort` n'est pas fixé — et il ne l'est pas.

        ⚠️ **Ce n'est pas un réglage déguisé.** Trois tirages `low`/`medium`/`high` sur un
        même message ont rendu 165, 280 et 187 jetons de sortie : du bruit. Fixer sur cette
        base referait la faute que la docstring du module vient de consigner. La colonne
        `appels_modele.effort` existe pour rendre la question décidable sur du trafic réel,
        et cette propriété est ce qui la remplit honnêtement en attendant."""
        return EFFORT_NON_FIXE

    @property
    def display(self) -> str:
        """`summarized` — et c'est le maximum que l'API accorde. **Mesuré.**

        Une valeur inventée rend un 400 qui énumère la liste close :
        `thinking.adaptive.display: Input should be 'summarized', 'omitted'`. Il n'existe
        donc pas de mode plus bavard à demander, et le résumé de 130 à 175 caractères qu'on
        observe est le plafond du modèle, pas un réglage à pousser."""
        return DISPLAY

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
            # ⚠️ **Explicite parce qu'il était déjà actif**, pas pour l'activer : voir la
            # docstring du module. Le seul effet réel de cette ligne est `display`, qui
            # fait arriver un résumé lisible là où le texte revenait vide.
            thinking=THINKING,
            # Le **seul** point de coupe du cache. Le préfixe couvert est
            # `tools` + `system` : les cinq définitions d'outils sont dedans.
            system=[{"type": "text", "text": systeme, "cache_control": {"type": "ephemeral"}}],
            tools=cast(list[ToolParam], definitions),
            messages=cast(list[MessageParam], messages),
        )
        self._mode_etabli = True

        usage = message.usage
        # Posé sur le client, **jamais dans `ReponseLLM`** : la boucle n'a que faire du
        # coût, et l'y mettre obligerait le faux client, le client de cassette et les
        # surcharges de l'API à fabriquer une valeur qu'aucun d'eux ne possède. Seul
        # l'enregistreur de cassettes le lit, par `getattr`. Voir `Usage`.
        self.dernier_usage = Usage(
            appels=1,
            jetons_entree=usage.input_tokens,
            jetons_sortie=usage.output_tokens,
            cache_ecrit=usage.cache_creation_input_tokens or 0,
            cache_lu=usage.cache_read_input_tokens or 0,
        )
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
