# Prompt Claude Code — Étape 8 : boucle agent et prompt système v1

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`. Les étapes 1 à 7 sont franchies : le catalogue est
en base (1 026 produits, seed committé et déterministe), le moteur de matching est
calibré et testé, et la couche outils porte les invariants — 474 tests purs en 2,8 s,
62 d'intégration, 20 portes hostiles. **Il n'existe aujourd'hui aucun appel LLM nulle
part dans le projet.** L'étape 8 est la première qui consommera une clé API.

Tu vas réaliser **l'étape 8 et rien d'autre**.

## Avant d'écrire quoi que ce soit

Lis, dans cet ordre :

1. `PROJET.md` — §2, §3.6 (et son amendement), §3.7 (et son amendement), §3.9, §3.10,
   §3.11, §3.12, §3.13, §3.14, §3.15, §3.17, §4, §5 étapes 7 et 8, §6, §7, §8.
2. `src/raiyon/tools/` en entier — `outils.py` et `schema_outils.py` d'abord : **ta
   boucle en sera la seule cliente**. Puis `etat.py` et `erreurs.py`.
3. `src/raiyon/config.py`, `src/raiyon/db/models.py`, `src/raiyon/db/engine.py`,
   `src/raiyon/catalogue/schemas.py` (pour `LIBELLES_CATEGORIE`), `Makefile`,
   `tests/test_isolation_passe_a.py`.

### Sept constats de lecture déjà faits, que tu n'as pas à redécouvrir

1. **`EtatSession` est immuable et chaque outil rend un `etat`** — y compris
   `rechercher_produits`, qui y pose `recherche_du_tour`. Si la boucle ne réenchaîne
   pas l'état d'un `tool_use` au suivant **à l'intérieur d'un même message assistant**,
   la garde « un tour, une catégorie » (arbitrage E de l'étape 7) ne se déclenche
   jamais. C'est une exigence de correction, pas de style.
2. **`en_tool_result()` retire le champ `etat`** de toute charge utile : l'état de
   session ne part jamais au modèle. Tu ne le contournes pas.
3. **`recherche_du_tour` n'est pas persistée** (docstring de `etat.py`). Elle ne vit que
   dans le tour, ce qui tombe juste : chaque tour client repart d'un état relu par
   `depuis_jsonb()`, donc à `None`.
4. **`tour_du_dernier_desserrage`, lui, est persisté** par `en_jsonb()`. Le jeton de
   parole ne survit donc à un redémarrage que si le numéro de tour est lui aussi
   persistant — voir l'arbitrage 9.
5. **Les noms d'outils sont des constantes** : `NOM_ENREGISTRER`, `NOM_SONDER`,
   `NOM_QUESTION`, `NOM_RECHERCHER`, `NOM_PRECISION` dans `schema_outils.py`. Tu ne
   réécris jamais `"record_criteria"` en littéral.
6. **Les modèles Pydantic d'arguments existent déjà** (`ArgumentsEnregistrement`,
   `ArgumentsSondage`, `ArgumentsPrecision`), en `extra="forbid"`. Tu les utilises pour
   parser le `input` brut du modèle ; tu n'en écris pas de nouveaux.
7. **`rechercher()` appelle `get_settings()`** pour la tolérance. Les outils propagent
   un paramètre `tolerance` injectable — c'est par lui que les tests purs se passent de
   `.env`.

## Périmètre — ce que tu livres

- **A.** L'accès à la clé API, corrigé (arbitrage 10).
- **B.** Le répartiteur d'outils, **pur**, dans `raiyon.tools`.
- **C.** Le client LLM : un `Protocol` et son implémentation SDK.
- **D.** La boucle d'agent, qui rend des **événements typés**.
- **E.** La persistance de session et de tours.
- **F.** Le prompt système `prompts/systeme.v1.md` et son chargeur.
- **G.** La console (`make chat`) et le contrôle de schéma (`make fumee`).
- **H.** Les tests, et la mise à jour de `PROJET.md`.

**Hors périmètre, à ne pas commencer :** le validateur anti-hallucination (étape 9),
l'API FastAPI et le SSE HTTP (étape 10), le front (étape 11), le harnais d'éval et les
cassettes (étape 12), l'itération sur les prompts (étape 13).

**Tu ne modifies pas** `src/raiyon/matching/`, ni `src/raiyon/catalogue/`, ni
`db/models.py`, ni les migrations. **Tu ne modifies pas non plus les descriptions
d'outils de `schema_outils.py`** — voir l'arbitrage 6. Les seuls fichiers existants que
tu touches sont `config.py` (arbitrage 10), `Makefile`, `PROJET.md` et `README.md`.

---

## Arbitrages déjà rendus — applique-les, ne les rediscute pas

Chacun a été pesé contre son alternative. Tu recopies la décision **et** l'alternative
écartée dans la docstring du module concerné, comme le fait déjà `matching/` et
`tools/`.

### 1. La boucle rend des événements typés, mais n'appelle pas `messages.stream()`

Tu utilises `client.messages.create()`. La boucle est un **générateur d'événements** :

```python
def repondre(...) -> Iterator[Evenement]
```

avec `Evenement` = `CriteresMisAJour | Sondage | QuestionSuggeree | ProduitsTrouves |
QuestionPosee | Texte | Repli`. La console consomme l'itérateur.

*Alternative écartée — streamer dès maintenant.* La console serait plus vivante, mais
on paie l'accumulation des deltas de `tool_use` en JSON partiel dans l'étape qui fait
déjà le premier appel API du projet.

*Alternative écartée — des retours simples, les événements à l'étape 10.* Une
abstraction de moins ; mais l'étape 10 réécrirait alors la boucle au lieu d'en remplacer
le producteur, ce que §6 dit d'éviter. **L'étape 10 doit pouvoir remplacer
`messages.create()` par `messages.stream()` sans que le consommateur bouge.**

### 2. Un `Protocol` de client LLM, comme `DepotProduits`

```python
class ClientLLM(Protocol):
    def repondre(
        self, *, systeme: str, outils: Sequence[dict[str, Any]], messages: list[dict[str, Any]]
    ) -> ReponseLLM: ...
```

`ReponseLLM` est une dataclass : `blocs: list[dict[str, Any]]` (les blocs de contenu
bruts, sérialisables tels quels en JSONB) et `fin: str` (le `stop_reason`).

L'implémentation SDK vit dans `agent/client_anthropic.py` ; **elle est le seul module du
projet qui importe `anthropic`.** Un faux scripté vit dans `tests/agent/faux_client.py`.

*Alternative écartée — ne tester la boucle que par cassettes à l'étape 12.* Elle teste
la vérité, mais rien avant l'étape 12, et un défaut de réenchaînement d'état ne se voit
pas dans une cassette : la cassette rejoue les réponses du modèle, pas notre gestion de
l'état.

⚠️ **Tension à écrire dans `PROJET.md`, sinon un relecteur y verra un reniement.** §3.15
écarte les « mocks écrits à la main » au motif qu'on teste ses propres suppositions sur
ce que le LLM répond. La nuance est que le faux client ne teste pas *ce que le modèle
répond* — il teste *ce que la boucle fait d'une réponse donnée* : enchaînement, état,
terminalité, appairage des `tool_result`. C'est légitime, et ça ne remplace pas les
cassettes de l'étape 12.

### 3. Le répartiteur vit dans `raiyon.tools`, pas dans `raiyon.agent`

Écris `src/raiyon/tools/repartiteur.py` :

```python
@dataclass(frozen=True, slots=True)
class ContexteOutils:
    depot: DepotProduits
    tour_client: int
    tolerance: Decimal | None = None

def executer(
    nom: str, entree: Mapping[str, Any], etat: EtatSession, contexte: ContexteOutils
) -> tuple[EtatSession, ResultatOutil | OutilRefuse]: ...
```

Elle parse les arguments avec les modèles Pydantic existants, appelle l'outil, et rend
le **nouvel état** avec le résultat. Sur `OutilRefuse` comme sur `ValidationError`, elle
rend l'état **inchangé** et un `OutilRefuse`. Pour un nom d'outil inconnu, ajoute
`OUTIL_INCONNU = "outil_inconnu"` à `CodeRefus` : la convention du module est « un code
par geste », et corriger un nom d'outil n'est pas corriger un champ.

La conversion `ValidationError` → `OutilRefuse` porte le code `VALEUR_ILLISIBLE` et
recopie le message de Pydantic tel quel : il nomme le champ fautif, ce qu'une
reformulation perdrait.

*Alternative écartée — le répartiteur dans `agent/`.* La couche outils resterait « cinq
fonctions » ; mais `record_criteria` s'écrirait alors dans deux modules de deux couches,
et c'est exactement le motif que `en_tool_result()` refuse — **un seul endroit où un nom
du protocole est écrit.**

⚠️ **Le test d'isolation SDK doit rester vert** : `repartiteur.py` n'importe rien
d'`anthropic`, et le test qui balaie les modules de `raiyon.tools` sur le disque le
prendra automatiquement en compte. Vérifie-le.

### 4. Blocs multiples dans un message assistant : tout exécuter, séquentiellement

- Chaque `tool_use` s'exécute **sur l'état rendu par le précédent**.
- Un `OutilRefuse` ne fait pas tomber les suivants : ils repartent de l'état d'avant.
- **Chaque `tool_use` reçoit exactement un `tool_result`, dans le même ordre**, sans
  aucune exception — y compris quand le tour est clos par `ask_clarification`, y compris
  quand `max_iterations` est atteint.

Ce dernier point n'est pas un choix : l'API refuse un historique où un `tool_use` n'a
pas son `tool_result` appairé. Si tu clos le tour sans écrire les `tool_result` dans
`tours_conversation`, **le tour client suivant partira sur un historique invalide**.
C'est le piège technique nº1 de cette étape ; écris-le en commentaire à l'endroit qui
compte.

Un `OutilRefuse` part dans un `tool_result` marqué `"is_error": true`. Le contenu est
`json.dumps(en_tool_result(...), ensure_ascii=False)`.

### 5. `ask_clarification` terminal : le texte qui précède est le préambule

§3.7 avait un argument `preamble` ; l'étape 7 l'a supprimé. Le « donner avant de
demander » de §3.9 doit donc vivre quelque part, et cet endroit est le message lui-même.

**Ce qui part au client est la concaténation des blocs `text` du message assistant, puis
`question`.** Le prompt système le dit : « écris ta piste en texte, puis pose la question
par l'outil ».

*Alternative écartée — jeter le texte et n'envoyer que `question`.* La règle serait plus
simple et l'outil vraiment terminal ; mais elle supprime mécaniquement le comportement
que §3.9 réclame, et le modèle n'a plus aucun endroit où donner quelque chose en retour.

Cas résiduels, tranchés :

- **Deux `ask_clarification` dans un même message** : la première gagne. La seconde
  s'exécute quand même (elle a besoin de son `tool_result`) et son résultat est ignoré.
  Log `WARNING`.
- **`ask_clarification` avec un autre outil dans le même message** : tous s'exécutent,
  tous ont leur `tool_result`, la question part au client et les autres résultats sont
  perdus. Le prompt système dit de ne pas le faire.
- **Aucun `tool_use`, que du texte** (`stop_reason == "end_turn"`) : c'est la fin normale
  du tour.

### 6. On ne touche pas aux descriptions d'outils, et la duplication est tolérée en v1

`DESCRIPTION_SONDER` et `DESCRIPTION_PRECISION` portent déjà des règles de dialogue
(« une fourchette de prix n'est jamais le prix d'un produit », « ne jamais demander sans
donner quelque chose »). Le prompt système v1 les redit.

**Tolérée en v1, à résorber à l'étape 13.** Raison : toucher `schema_outils.py` invalide
le cache de prompt, rouvre une couche qu'on vient de fermer et de tester, et on ne sait
pas encore **laquelle des deux formulations porte l'effet** — c'est précisément ce que le
harnais d'éval saura dire.

*Alternative écartée — répartir maintenant : le contrat d'appel dans la description, la
conduite dans le prompt.* C'est la bonne cible, et elle suit le raisonnement de
`erreurs.py` (deux rédactions d'une même règle finissent par en dire deux choses). Elle
est reportée, pas abandonnée : écris-le au §5 étape 13 de `PROJET.md`.

### 7. Cache de prompt activé, et ce qu'il interdit

Un seul point de coupe, **sur le bloc système** :

```python
system=[{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]
```

Le préfixe mis en cache est `tools` + `system` : une coupe sur le système couvre donc
aussi les cinq définitions d'outils, qui sont la partie la plus lourde et la plus stable.

La contrainte que ça crée est ce qui compte : le préfixe doit être **identique octet
pour octet** d'un appel à l'autre. Donc **ni la date, ni l'état de session, ni le numéro
de tour, ni la catégorie courante ne vont dans le prompt système.** L'état ne vit que
dans les `tool_result`. C'est une règle de conception du prompt v1, pas une optimisation.

Un test le vérifie : deux appels du même tour reçoivent un `systeme` et des `outils`
identiques.

### 8. `max_iterations` atteint : un message de repli écrit en Python

Log `WARNING` avec le compte d'itérations et les noms d'outils appelés, puis un
événement `Repli` portant une phrase constante — du type « je m'y perds un peu, tu peux
me redire ce que tu cherches ? ». Le tour est clos.

*Alternative écartée — un dernier appel sans outils pour forcer une réponse texte.* Plus
élégant, et c'est ce que l'étape 9 rendra sûr. Écartée ici : après 8 itérations, le
modèle a précisément tourné en rond, et **rien ne valide encore sa sortie** — ce serait
le texte le moins fiable de toute la conversation qu'on enverrait au client.

### 9. Persistance en base dès maintenant, et `tour_client` est le numéro du tour

*Cet arbitrage se tranche seul, et il faut le dire :* la console a **de toute façon**
besoin de Postgres, puisque `search_products` interroge le dépôt. L'argument « garder la
console utilisable sans conteneur » est faux.

Donc : `sessions` et `tours_conversation` sont écrits dès l'étape 8, et
`en_jsonb()` / `depuis_jsonb()` sont exercés sur un aller-retour réel — sinon l'étape 10
découvrirait le défaut avec le streaming par-dessus.

**`tour_client` est le `numero` de la ligne `tours_conversation` du message client.**
C'est un entier croissant, unique par session, stable au redémarrage, jamais réutilisé —
tout ce dont le jeton de parole a besoin. Ne compte **pas** les lignes de rôle `user` :
les `tool_result` en portent aussi (voir le commentaire de `models.py`), et un compteur
en mémoire rendrait le jeton contournable par redémarrage.

Chaque tour client :

1. relit la session, construit l'état par
   `depuis_jsonb(session.criteres_valides, budget_usd=session.budget_usd)` ;
2. relit les tours pour reconstruire `messages` (les `blocs` bruts, dans l'ordre du
   `numero`) ;
3. tourne la boucle ;
4. écrit **tous** les tours produits (assistant, `tool_result`, assistant…) puis
   `session.criteres_valides = etat.en_jsonb()` et `session.budget_usd = etat.budget_usd` ;
5. commit unique, en fin de tour.

Le générateur écrit en base **à la fin**, donc la console doit le consommer entièrement.
Écris-le dans la docstring.

### 10. `ANTHROPIC_API_KEY` devient optionnelle, avec un accesseur qui lève

C'est l'arbitrage laissé en suspens à l'étape 5, et le moment prévu pour le trancher.

Dans `config.py` :

```python
anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")

def cle_api() -> str:
    """La clé, ou une ConfigurationError qui dit quoi faire. Seul site de déballage."""
```

*Alternative écartée — statu quo, obligatoire au démarrage.* Simple, et un projet
portfolio a de toute façon une clé ; mais `make seed` et `make calibrer` sont du code
**déterministe depuis §3.4ter** et exiger une clé pour eux est un mensonge sur la
dépendance — celui-là même que la suppression de la passe LLM de l'étape 5 a fait
disparaître.

*Alternative écartée — `SecretStr | None` déballé partout.* Elle répand des `| None`
dans chaque site d'usage. L'accesseur en concentre un seul.

Le principe du dépôt reste « échouer tôt » : il échoue tôt **sur ce qui est réellement
requis**. Mets à jour `.env.example` et le test de `tests/test_config.py` qui attend
aujourd'hui une `ValidationError` sur clé absente.

### 11. Le premier appel API du projet valide `strict: true`, avant la boucle

Le repli `schema_des_outils(strict=False)` existe depuis l'étape 7 mais n'a **jamais été
exercé contre l'API réelle**, et le sous-ensemble de JSON Schema admis sous ce drapeau
n'est écrit nulle part dans le paquet installé.

Livre `make fumee` : un appel jetable qui envoie les cinq définitions avec un message
trivial, et loggue le mode retenu. Dans le client SDK, le repli est automatique et
mémorisé : sur un `BadRequestError` au premier appel, réessaie **une fois** en
`strict=False`, log `WARNING` avec le message de l'API, et garde ce mode pour la suite
du processus.

C'est le point le plus fragile de l'étape. Le dépôt a trois précédents — `smt` à l'étape
3, `temperature=0` et `nom_fr` à l'étape 5 — où une capacité supposée disponible n'avait
pas été mesurée. **Fais tourner `make fumee` avant d'écrire la boucle**, et dis-moi ce
qu'il rend.

### 12. Quatre réglages, tranchés au plus simple

- **Pas de thinking étendu en v1.** Avec le tool use, les blocs `thinking` doivent être
  réinjectés verbatim et persistés, ce qui alourdit l'historique pour un raisonnement
  qui tient en deux lignes. À rouvrir à l'étape 13 si la métrique nº4 plafonne.
- **On ne fixe pas `temperature`.** Le défaut du modèle. Le dépôt s'est déjà fait
  prendre à supposer que `temperature=0` donnait du déterminisme ; on ne le suppose plus
  et on ne le revendique nulle part.
- **`max_tokens = 2048`.** Une recommandation de trois produits avec son pourquoi tient
  largement dedans.
- **Le faux client reste dans `tests/`.** Pas de mode démo hors ligne : ce serait une
  seconde façon de faire tourner le produit, à maintenir, pour un gain qui appartient à
  l'étape 12.

---

## Ce que tu livres, fichier par fichier

```
src/raiyon/tools/
    repartiteur.py         # nom d'outil → fonction, pur, aucun import anthropic
    erreurs.py             # + CodeRefus.OUTIL_INCONNU
src/raiyon/agent/
    client.py              # Protocol ClientLLM, dataclass ReponseLLM
    client_anthropic.py    # SEUL module qui importe anthropic ; repli strict
    evenements.py          # les événements typés, dataclasses frozen
    prompts.py             # chargement des prompts versionnés + empreinte sha256
    boucle.py              # repondre() : générateur d'événements
    session.py             # lecture/écriture de sessions et tours_conversation
src/raiyon/config.py       # anthropic_api_key optionnelle + cle_api()
prompts/
    systeme.v1.md
scripts/
    console.py             # make chat
    fumee.py               # make fumee
tests/agent/
    faux_client.py  test_boucle.py  test_terminal.py  test_prompts.py
tests/integration/
    test_session_persistee.py       # marqueur `integration`
```

`agent/prompts.py` expose `charger(nom: str) -> str` et `empreinte(texte) -> str`
(sha256 tronqué à 12). La version **et** l'empreinte sont loguées à chaque appel :
l'étape 12 en a besoin pour détecter une cassette obsolète (§7), et ça coûte trois
lignes maintenant.

### La console

`make chat` : lecture de stdin ligne à ligne, une session créée au démarrage (son UUID
affiché), `Ctrl-D` pour sortir. Deux niveaux d'affichage :

- **par défaut** — le dialogue, plus une ligne compacte par événement non textuel :
  `[critères] écran · 144 Hz bloquant · budget 400 $`, `[sondage] 32 candidats,
  180–395 $`, `[produits] 3 trouvés`. C'est le panneau « voici ce que j'ai compris » de
  §3.12 en version terminal, et c'est ce qui rend l'architecture visible ;
- **`--trace`** — en plus, les arguments d'appel et les `tool_result` bruts.

---

## Le prompt système v1 — contenu obligatoire

Court et sectionné, pas exhaustif. Onze sections numérotées, une idée chacune, pour que
l'étape 13 puisse en déplacer **une** et mesurer. Écrire un prompt v1 maximal
laisserait les métriques nº3 et nº4 sans marge de progression et rendrait chaque
changement ultérieur non attribuable.

Il doit contenir, et rien de superflu autour :

1. **Le rôle** — vendeur conseil en composants et périphériques PC, en français,
   vouvoiement, phrases courtes, aucun emoji.
2. **La règle absolue** — tu ne cites que les produits rendus par `search_products`, par
   leur nom exact et leur `id`. Aucun prix, aucune caractéristique qui ne vienne d'un
   `tool_result`. Si tu ne l'as pas sous les yeux, tu cherches, ou tu dis que tu ne sais
   pas.
3. **Les noms de produits sont en anglais et se citent verbatim** — jamais traduits,
   jamais réécrits, pas même l'espace ou la casse : c'est un identifiant que le client
   va retaper dans un moteur de recherche. Les **catégories**, elles, se disent en
   français (« écran », « carte graphique »). C'est la contrainte de §3.4ter, et c'est
   ce qui rendra le validateur de l'étape 9 vérifiable au caractère près.
4. **Une fourchette de sondage n'est jamais le prix d'un produit.** Elle décrit un
   ensemble. Citer un prix exige d'avoir le produit sous les yeux. *(Atténuation du
   risque « `probe_catalog` est un oracle à prix », §7.)*
5. **Donner avant de demander.** Montrer des pistes provisoires, puis affiner.
   `ask_clarification` seulement quand il n'y a vraiment rien à donner en retour — et
   alors, écrire d'abord en texte ce qu'on a compris, puis poser la question par
   l'outil, une seule fois.
6. **`suggest_next_question` est une suggestion, pas un ordre.** Le champ de plus fort
   gain d'information n'est pas toujours la meilleure question de vente : si l'outil
   rend `marque`, préfère presque toujours l'usage — « c'est pour jouer, pour du
   montage, pour du bureautique ? » — qui fait avancer plusieurs critères à la fois.
   *(Atténuation du risque « le champ le plus discriminant n'est pas toujours la
   meilleure question », §7.)*
7. **Le budget est une contrainte dure.** Un produit d'`au_dessus_du_budget` ne se cite
   jamais sans dire qu'il dépasse, et de combien exactement.
8. **Un composant à la fois.** « Monte-moi une config gaming » se séquence : annonce-le,
   commence par une catégorie, termine-la, puis propose la suivante au message suivant.
9. **Enregistre ce que le client a dit, pas ce qui arrangerait la recherche.** Assouplir
   coûte une parole du client. Quand `record_criteria` refuse un mouvement, dis-le au
   client (« je garde 144 Hz tant que tu ne me dis pas le contraire ») au lieu de
   réessayer autrement. *(Atténuation du risque « le jeton ne vérifie pas de quel critère
   le client parlait », §7 : la seule parade côté prompt est de rendre le refus visible
   plutôt que contournable.)*
10. **Zéro résultat** — dis pourquoi, avec le diagnostic rendu par l'outil, puis propose
    l'assouplissement que le moteur a calculé comme le plus rentable. N'assouplis jamais
    de toi-même : c'est au client de trancher.
11. **La recommandation** — un à trois produits, classés, chacun avec son « pourquoi »
    tiré de la trace. Ce qui ne satisfait pas un critère se dit aussi.

---

## Tests attendus — purs, sans clé et sans base

`tests/agent/`, avec le faux client scripté. Chacun nommé d'après ce qu'il empêche :

1. Un message sans outil → un événement `Texte`, aucun appel d'outil, un seul appel API.
2. `record_criteria` → `search_products` → texte : l'état s'enchaîne, les produits
   remontent.
3. **Deux `tool_use` dans un même message assistant**, le second dépendant de l'état posé
   par le premier → le réenchaînement est prouvé.
4. **Deux `search_products` sur deux catégories dans le même message** → le second reçoit
   un `tool_result` en erreur, code `deux_categories_dans_un_tour`. C'est le test le plus
   important de l'étape : il échoue si l'état n'est pas réenchaîné.
5. `ask_clarification` → la boucle s'arrête, **aucun second appel API**, et ce qui part
   au client est le texte précédent puis la question.
6. `ask_clarification` accompagné d'un autre outil → les deux exécutés, deux
   `tool_result`, la question gagne.
7. Deux `ask_clarification` → la première gagne, `WARNING` logué.
8. Arguments invalides (propriété inventée, `"beaucoup"` sur un numérique) →
   `tool_result` en erreur, **la boucle continue**.
9. Nom d'outil inconnu → `tool_result` en erreur, code `outil_inconnu`.
10. Le modèle boucle indéfiniment → `max_iterations` atteint, événement `Repli`,
    `WARNING`, aucun appel supplémentaire.
11. **Assertion générique, appliquée à tous les scénarios** : chaque `tool_use` a
    exactement un `tool_result`, avec le même `tool_use_id`, dans le même ordre.
12. Le préfixe (`systeme` + `outils`) est identique entre deux appels du même tour — la
    garantie du cache.
13. Le test d'isolation SDK reste vert : aucun module de `raiyon.tools` ne charge
    `anthropic`, `repartiteur.py` compris.

`tests/integration/test_session_persistee.py` (marqueur `integration`) : un tour écrit,
relu, et l'état reconstruit à l'identique — critères, budget,
`tour_du_dernier_desserrage`.

---

## Porte de sortie

1. `make fumee` vert, et **tu me dis quel mode a été retenu** (`strict: true` ou le
   repli). À faire **avant** d'écrire la boucle.
2. `make check` vert — lint, `mypy --strict`, suite pure — **sans base, sans conteneur
   et sans clé API**. La suite de `tests/agent/` en fait partie.
3. `make test-int` vert.
4. **Une conversation manuelle en console, de bout en bout, qui aboutit à une
   recommandation de produits réels.** Colle-m'en la transcription, avec le `--trace`
   sur au moins un tour.
5. Un redémarrage de la console sur la même session retrouve les critères — la preuve
   que `depuis_jsonb` fait un aller-retour réel.

Pas encore de qualité garantie : juste la preuve que la boucle tourne et que les logs
sont lisibles.

---

## Documentation — dans le même commit

1. `PROJET.md` §5 étape 8 passe en ✅, avec les douze arbitrages ci-dessus, chacun avec
   son alternative écartée, dans le style des dix arbitrages de l'étape 7.
2. **Amendement du §3.13** : le point de coupe du cache est sur le bloc système, et la
   conséquence de conception — **le prompt système ne contient jamais rien de dynamique**
   — est écrite là, pas seulement dans le code.
3. **Amendement du §5 étape 2** : `ANTHROPIC_API_KEY` n'est plus obligatoire au
   démarrage. Écris pourquoi la décision initiale était raisonnable et ce qui l'a
   renversée (§3.4ter a supprimé le seul appel LLM du chemin de données). Ne réécris pas
   l'histoire.
4. **Trois lignes au §7 (risques)** :
   - le prompt v1 n'est mesuré par rien avant l'étape 12 — les sections 4, 6 et 9 sont
     des atténuations **déclarées**, pas vérifiées ;
   - le faux client teste la boucle, pas le modèle : un défaut de conduite du dialogue
     passe entièrement à travers `make check` ;
   - le texte sortant n'est validé par rien jusqu'à l'étape 9 — c'est le seul moment du
     projet où le §2 repose uniquement sur le prompt, et c'est pour ça que l'étape 9 est
     la suivante et pas l'étape 10.
5. Une section « ce que l'étape a appris, et qui n'était pas prévu ». En particulier ce
   que `make fumee` aura révélé sur `strict`.
6. `README.md` : une section « lancer une conversation » (`make up`, `make migrate`,
   `make seed`, `make chat`), et la mention que la clé n'est requise que pour `make chat`
   et `make fumee`.

---

## Méthode

Un jalon à la fois.

1. **`make fumee` d'abord** — avant toute autre ligne. Montre-moi ce que l'API dit de
   `strict: true` sur une `enum` de 36 entrées.
2. Puis **A + B + C** (clé, répartiteur, client). Montre-moi le répartiteur et ses tests
   avant d'écrire la boucle : c'est la pièce dont une erreur se propage partout.
3. Puis **D + E** (boucle et persistance).
4. Puis **F + G** (prompt v1 et console), et la conversation de bout en bout.

À chaque décision structurante que je n'ai pas tranchée ci-dessus, expose l'alternative
et le compromis **avant** de trancher, et dis-moi explicitement quand un choix est
risqué ou fragile.

Ne commence pas l'étape 9. Aucun validateur, aucun parsing de sortie texte, aucune
régénération. Aucune route FastAPI.
