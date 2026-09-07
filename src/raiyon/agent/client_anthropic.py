"""L'implémentation SDK du `ClientLLM`. **Le seul module du projet qui importe `anthropic`.**

Deux tests le vérifient sur le disque plutôt que sur la discipline — `raiyon.catalogue`
et `raiyon.tools` sont balayés module par module, dans un interpréteur neuf. La frontière
n'a donc pas besoin d'être rappelée en revue.

---

### Le cache de prompt : deux points de coupe, le second mobile (arbitrage 7, renversé)

```python
system = [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]
messages = avec_point_de_coupe(messages)  # marque le dernier bloc du dernier message
```

Le premier point de coupe ne bouge pas : il couvre `tools` + `system`, soit **13 078
jetons mesurés le 2026-09-07**, les six définitions d'outils comprises. Le second est posé
sur le **dernier bloc du dernier message**, donc à la fin de l'historique, et il se déplace
à chaque appel.

⚠️ **La phrase qui suit a été vraie, puis a cessé de l'être sans que rien ne le dise. Elle
est barrée plutôt qu'effacée** (§9.3, « une affirmation réfutée doit être corrigée au point
de décision ») :

> ~~« Un second point de coupe n'aurait rien à protéger de plus. »~~ — écrite à l'étape 23,
> **réfutée le 2026-09-07** sur la session `b19bd39a`.

Il aurait protégé **185 873 jetons**, soit **0,3250 $ sur 0,6018** — plus de la moitié de
la facture de la session, et 65 % de sa part d'entrée.

**Elle a cessé d'être vraie entre le tour 2 et le tour 3.** À trois appels, l'historique
pesait moins que le préfixe système et la phrase décrivait exactement le dépôt. L'entrée
cumulée d'un tour client vaut 3 746 jetons au tour 1, 11 368 au tour 2 — tous deux **sous**
les 13 078 du préfixe — et 14 746 au tour 3, **au-dessus**. Elle n'a pas été relue parce que
rien dans le dépôt ne disait **à quelle échelle** elle avait été vérifiée, et parce qu'il n'y
avait rien à y relire : elle était juste.

Ce que la session a mesuré, sur 10 tours client et 24 appels persistés :

| | jetons | $ |
|---|---:|---:|
| entrée hors cache | 205 088 | 0,4102 |
| cache écrit | 13 078 | 0,0327 |
| cache lu | 300 794 (= 13 078 fois 23, **constant**) | 0,0602 |
| sortie | 9 876 | 0,0988 |
| **total** | | **0,6018** |

`cache_lu` rigoureusement constant est la signature du défaut : le préfixe protégé ne
grossit jamais, donc chaque tour renvoie tout l'historique au tarif plein et le cumul croît
en carré du nombre d'appels — l'entrée d'un appel monte de 767 jetons en moyenne (R² = 0,95
sur les 24), le cumul suit `i²` à R² = 0,997.

### Pourquoi c'est décidable sans mesurer d'abord la frontière entre deux tours

Trois scénarios simulés sur les chiffres ci-dessus :

| | entrée facturée | coût | |
|---|---:|---:|---|
| aujourd'hui | 218 166 | 0,6018 $ | — |
| le préfixe tient **aussi** entre les tours | 32 293 | 0,2768 $ | **-54,0 %** |
| il ne tient qu'**à l'intérieur** d'un tour | 116 903 | 0,4714 $ | **-21,7 %** |
| il ne tient **jamais** | 218 166 | 0,7043 $ | +17,0 % |

Le troisième cas est le pire réaliste, et **c'est encore un gain**. Le quatrième — le seul
qui coûte, exactement 25 % de l'entrée d'aujourd'hui, l'écart entre le facteur d'écriture
1,25 et l'entrée nue — exige que le préfixe ne soit **jamais** réutilisé, ce que la boucle
rend inatteignable : `ajouter_les_resultats` et `empiler_la_reprise` ne font
qu'`append`, rien n'est jamais réécrit, **y compris un message assistant refusé**.
L'historique est append-only par construction, pas par discipline. Le seuil de rentabilité
est à 24 % d'appels qui touchent ; l'intérieur d'un tour en garantit plus à lui seul.

⚠️ **L'inconnue restante ne bloque pas, et c'est le point à retenir.** `historique_de()`
reconstruit l'historique depuis le JSONB de `tours_conversation`, et Postgres ne conserve ni
l'ordre des clés ni les doublons ; que le préfixe reconstruit se tokenise à l'identique de
ce qui avait été envoyé en mémoire n'est **pas mesuré**. Mais cette inconnue décide entre
**-22 % et -54 %**, c'est-à-dire entre deux gains. Elle ne change pas la décision, donc on
ne la paie pas avant.

**Elle se mesurera après, gratuitement, et le lecteur existe déjà** : `appels_modele.cache_lu`.
S'il grossit d'un tour au suivant, la frontière tient ; s'il retombe à 13 078 au premier
appel de chaque tour, elle ne tient pas et on est dans le scénario à -21,7 %. Aucune
campagne, aucun appel de plus — c'est la colonne que l'étape 23 écrivait déjà.

### Ce que les deux coupes interdisent

⚠️ **Le préfixe système reste identique octet pour octet, et c'est toujours une règle de
conception.** Ni la date, ni l'état de session, ni le numéro de tour, ni la catégorie
courante ne vont dans le prompt système ; l'état ne vit que dans les `tool_result`. Un test
de `tests/agent/` constate que deux appels d'un même tour reçoivent un `systeme` et des
`outils` identiques.

🔴 **Et la seconde coupe en ajoute une, qui n'existait pas : `avec_point_de_coupe()` ne
modifie jamais les messages qu'on lui donne.** Elle recopie la liste, le dernier message,
sa liste de blocs et le seul bloc qu'elle marque — le reste est partagé. Muter en place
écrirait le `cache_control` dans `tours_conversation.blocs`, donc dans ce que
`historique_de()` rejoue : le marqueur reviendrait dans l'historique au tour suivant, un
nouveau serait posé par-dessus, et **le cinquième tour dépasserait la limite de quatre
points de coupe de l'API**. Un test constate que l'objet passé ressort intact.

**Quels blocs acceptent `cache_control` : mesuré sur le paquet installé, pas supposé.**
`text`, `tool_use` et `tool_result` le portent ; `thinking` et `redacted_thinking` **ne le
portent pas** — leurs `TypedDict` du SDK n'ont pas le champ. La boucle ne termine jamais
`messages` par un message assistant (voir l'alternative écartée de `boucle.repondre`), donc
le dernier bloc est toujours un `text` ou un `tool_result` ; `avec_point_de_coupe()` remonte
tout de même jusqu'au dernier bloc marquable plutôt que de supposer cette invariante tenue
par un autre module. Ne pas poser de coupe coûte un gain ; en poser une au mauvais endroit
coûte un 400.

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

### Le raisonnement : adaptatif, résumé, borné par `max_tokens` (étape 23)

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
  l'API**, jamais la trace brute du modèle — le dashboard de l'étape 23 l'écrit à l'écran,
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
from anthropic.types import (
    CacheControlEphemeralParam,
    MessageParam,
    ThinkingConfigParam,
    ToolParam,
)

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

CACHE_EPHEMERE: CacheControlEphemeralParam = {"type": "ephemeral"}
"""Le marqueur des **deux** points de coupe. Écrit une fois : deux littéraux identiques
posés à deux endroits sont le motif que ce dépôt a déjà payé trois fois."""

BLOCS_SANS_CACHE_CONTROL = frozenset({"thinking", "redacted_thinking"})
"""Les types de bloc qui **n'acceptent pas** `cache_control`. **Relevé le 2026-09-07 sur le
paquet installé**, pas supposé : `ThinkingBlockParam` et `RedactedThinkingBlockParam` n'ont
pas le champ, là où `TextBlockParam`, `ToolUseBlockParam` et `ToolResultBlockParam` l'ont.

Aucun chemin du dépôt ne devrait terminer `messages` sur l'un des deux — la boucle ne
laisse jamais un message assistant en dernier. C'est justement pourquoi l'ensemble est
écrit ici plutôt que supposé ailleurs : la garantie appartient à `boucle.py`, la
conséquence d'un 400 appartient à ce module."""


def avec_point_de_coupe(messages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les mêmes messages, le dernier bloc marquable du dernier message portant le cache.

    ⚠️ **Rien n'est modifié en place, et c'est la propriété qui compte.** Les blocs qu'on
    reçoit sont ceux que `session.tour()` va persister dans `tours_conversation` et que
    `historique_de()` rejouera : y écrire un `cache_control` le ferait revenir dans
    l'historique au tour suivant, un nouveau serait posé par-dessus, et le cinquième tour
    dépasserait la limite de quatre points de coupe de l'API. La liste, le dernier message,
    sa liste de blocs et le seul bloc marqué sont recopiés ; tout le reste est partagé, donc
    le coût est constant quelle que soit la longueur de la conversation.

    Une liste vide, un contenu qui n'est pas une liste de blocs, ou un dernier message
    entièrement fait de blocs non marquables : on rend les messages tels quels. **Ne pas
    poser de coupe coûte un gain ; en poser une au mauvais endroit coûte un 400.**
    """
    if not messages:
        return []
    dernier = messages[-1]
    blocs = dernier.get("content")
    if not isinstance(blocs, list) or not blocs:
        return list(messages)
    rang = _dernier_bloc_marquable(blocs)
    if rang is None:
        logueur.warning(
            "client_anthropic.point_de_coupe_sans_place",
            types=[bloc.get("type") for bloc in blocs],
            consequence="aucune coupe sur l'historique — l'appel part sans, et il est valide",
        )
        return list(messages)
    marque = {**blocs[rang], "cache_control": CACHE_EPHEMERE}
    return [
        *messages[:-1],
        {**dernier, "content": [*blocs[:rang], marque, *blocs[rang + 1 :]]},
    ]


def _dernier_bloc_marquable(blocs: list[dict[str, Any]]) -> int | None:
    """Le rang du dernier bloc qui accepte `cache_control`, ou `None` s'il n'y en a pas.

    On remonte au lieu de s'arrêter au dernier bloc : une coupe posée un cran plus tôt
    laisse la queue hors du cache — c'est-à-dire le comportement d'aujourd'hui sur ces
    quelques jetons — là où une coupe posée sur un `thinking` ferait échouer l'appel.
    """
    for rang in range(len(blocs) - 1, -1, -1):
        if blocs[rang].get("type") not in BLOCS_SANS_CACHE_CONTROL:
            return rang
    return None


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

    # Trois lectures publiques, ajoutées à l'étape 23 pour `ClientJournalisant`. Elles
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
            # Le point de coupe **fixe**. Le préfixe couvert est `tools` + `system` :
            # les six définitions d'outils sont dedans, 13 078 jetons au 2026-09-07.
            system=[{"type": "text", "text": systeme, "cache_control": CACHE_EPHEMERE}],
            tools=cast(list[ToolParam], definitions),
            # Le point de coupe **mobile**, à la fin de l'historique. `messages` ressort
            # intact : voir `avec_point_de_coupe`, dont c'est la raison d'être.
            messages=cast(list[MessageParam], avec_point_de_coupe(messages)),
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
