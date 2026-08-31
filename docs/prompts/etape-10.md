# Prompt Claude Code — Étape 10 : API FastAPI et streaming SSE

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`. Les étapes 1 à 9 sont franchies : catalogue en base,
moteur de matching calibré, couche outils portant les invariants, boucle d'agent, et
depuis l'étape 9 un validateur programmatique qui bufferise, relit et refuse la prose
avant qu'elle parte. 624 tests purs en 4,4 s, 67 d'intégration, `mypy --strict` et `ruff`
propres.

**La pile est complète jusqu'au texte validé, et il n'existe aucune route HTTP dans tout
le dépôt.** `src/raiyon/api/__init__.py` est vide depuis l'étape 2. Le seul consommateur
d'événements est `scripts/console.py`.

Tu vas réaliser **l'étape 10 et rien d'autre** : l'API en fait un **second
consommateur**, pas une réécriture de la boucle.

## Avant d'écrire quoi que ce soit

Lis, dans cet ordre :

1. `PROJET.md` — §3.11, §3.12, §3.14, §3.16, §4, §5 étapes 7, 8, 9 et 10 (dont
   l'avertissement sur la persistance en milieu de tour), §6, §7, §8.
2. `src/raiyon/agent/evenements.py` en entier — c'est **le contrat que tu sérialises**.
3. `src/raiyon/agent/boucle.py` (au moins `repondre()`, `IssueDuTour`) et
   `src/raiyon/agent/session.py` en entier.
4. `scripts/console.py` — **c'est le consommateur dont tu écris le jumeau.** Il montre
   quels champs sont réellement affichables et par quel chemin le français est dérivé du
   registre. Tu ne le modifies pas.
5. `src/raiyon/db/models.py`, `src/raiyon/db/engine.py`, `src/raiyon/config.py`.
6. `src/raiyon/tools/outils.py` — `en_tool_result()` pour la convention de
   sérialisation des `Decimal`.
7. `src/raiyon/matching/attributs.py` (`ATTRIBUTS`) et
   `src/raiyon/catalogue/schemas.py` (`LIBELLES_CATEGORIE`).

### Constats de lecture déjà faits — ne les redécouvre pas

1. **`messages.stream()` est sans objet, et définitivement.** Un bloc `tool_use` doit être
   complet avant `executer()`, et depuis l'arbitrage A de l'étape 9 le texte est
   inutilisable avant d'être entier. Il ne reste aucun consommateur de delta dans la
   boucle. **Tu ne touches pas à `client_anthropic.py`.** L'étape 10 ne streame que
   serveur → navigateur.
2. **Une promesse écrite est à barrer, pas à tenir.** `evenements.py` et `boucle.py`
   disent que « l'étape 10 doit pouvoir remplacer `messages.create()` par
   `messages.stream()` sans que le consommateur bouge ». C'est faux depuis l'étape 9 et
   ça le reste. Réécris ces passages en disant qu'ils ont été renversés et pourquoi ; ne
   les efface pas.
3. **`db/engine.py` contient une phrase fausse à corriger** : « L'API FastAPI de l'étape
   10 enveloppera ses appels base dans `asyncio.to_thread` ». L'arbitrage A ci-dessous
   dit l'inverse. Amende la docstring, en gardant l'argument (le moteur reste synchrone
   pour que le critère nº5 tienne) et en corrigeant le mécanisme.
4. `session.tour()` est un **générateur qui n'écrit qu'à la fin** : un consommateur qui
   abandonne l'itération ne persiste rien. Toute la sémantique d'erreur de cette étape en
   découle.
5. `EtatSession` porte des **gardes de tour non persistées** (`recherche_du_tour`,
   `tour_du_changement_de_categorie`). Le §5 étape 10 avertit : si l'API persistait
   l'état **au milieu** d'un tour, elles devraient rejoindre le JSONB. **Tu ne persistes
   rien au milieu d'un tour**, donc elles n'y vont pas. Écris-le.
6. `ClientAnthropic` **mémorise son mode `strict`** sur l'instance, mesuré au premier
   appel. Une instance par requête reperdrait cette mesure et paierait un aller-retour de
   plus à chaque premier échec.
7. `en_tool_result()` sérialise tous les `Decimal` **en chaînes** (`"108.00"`). Le fil
   fait pareil, partout, sans exception.

## Périmètre — ce que tu livres

- **A.** Un module de sérialisation **pur** : `Evenement` → trame SSE.
- **B.** L'application FastAPI, sa durée de vie, ses quatre routes.
- **C.** Le générateur SSE : verrou, session base, drainage, événements d'API.
- **D.** Le service des fichiers statiques et la cible `make api`.
- **E.** Les tests : sérialisation purs, endpoints en `integration`.
- **F.** `PROJET.md`, `README.md`, et les docstrings à amender.

**Hors périmètre :** l'interface web (étape 11 — tu crées le répertoire statique et son
point de montage, pas la page), le harnais d'éval et les cassettes (étape 12), toute
itération sur les prompts (étape 13). **Tu ne modifies pas** `matching/`, `catalogue/`,
`tools/`, `validateur/`, `db/models.py`, ni aucune migration. **Tu ne modifies pas la
logique de `agent/`** — seulement les docstrings nommées au constat 2.

---

## Arbitrages déjà rendus — applique-les, ne les rediscute pas

### A. Pile synchrone de bout en bout

Le générateur passé à `StreamingResponse` est **synchrone** ; Starlette l'enveloppe dans
`iterate_in_threadpool`. Toute la pile métier reste synchrone, ce qui est la condition du
critère nº5.

Précision qui compte : **ce n'est pas l'endpoint qui doit être `def`.** L'endpoint peut
rester `async def` et rendre un `StreamingResponse` construit sur un générateur sync — le
tour n'a pas lieu dans le corps de l'endpoint, mais après son retour.

*Alternative écartée — un engine asyncio.* Il imposerait `async def` jusque dans
`tests/matching/`, donc ferait tomber le critère nº5. Non négociable.

### B. POST rendant du `text/event-stream`

`EventSource` ne sait faire que du GET, et mettre le message client en query string est
exclu — longueur, encodage, journalisation.

*Alternative écartée — POST qui ouvre un tour, puis GET `/events` en `EventSource`.* Deux
requêtes, une course entre les deux, et un état serveur à porter entre elles pour rien.

**Coût à écrire dans PROJET.md** : le front de l'étape 11 devra parser le SSE à la main
sur `fetch` + `ReadableStream`, là où `EventSource` l'aurait fait seul.

### C. Aucun heartbeat, et c'est assumé

Un générateur synchrone bloqué dans `messages.create()` ne peut rien intercaler : ni
`: ping`, ni détection de déconnexion. On ne fait **rien**.

Le silence réel est celui d'un tour sans appel d'outil — les événements d'outils arrivent
au fil de l'eau et tiennent la connexion vivante le reste du temps. En démo locale et en
`curl`, aucun effet. **À rouvrir le jour d'un déploiement derrière un proxy** qui coupe à
60 s d'inactivité ; la parade serait un endpoint `async` drainant le générateur sync par
une `queue.Queue`, soit une quarantaine de lignes de plomberie thread↔asyncio. Écris la
condition de bascule, pas le code.

### D. Un tour à la fois par session, verrouillé en base

**Le verrou en mémoire est interdit par une décision déjà écrite** : §3.12 justifie la
persistance des sessions par « autorise le multi-worker ». Un `dict` de verrous par
processus rendrait cette phrase fausse dès `uvicorn --workers 2`.

Le verrou est un **advisory lock Postgres à portée de transaction**
(`pg_try_advisory_xact_lock`), pris sur la **même `Session` SQLAlchemy** que celle qui
servira le tour, **avant** d'appeler `session.tour()`. `tour()` commite exactement une
fois, en fin de tour : la portée du verrou coïncide donc au caractère près avec la portée
du tour, et il n'y a aucune libération à oublier.

⚠️ Un verrou pris sur une autre connexion que celle qui écrit ne sert à rien. Vérifie-le
par un test, pas par relecture.

Refus du verrou → **409 avant le premier octet** (voir E).

*Alternative écartée — `SELECT … FOR UPDATE NOWAIT` sur la ligne de session.* Même effet,
mais verrouille une ligne qu'on écrit de toute façon, et le message d'erreur parle de la
ligne, pas du tour.

### E. Avant le premier octet, un code HTTP ; après, un événement typé

C'est la ligne de partage de toute la gestion d'erreur.

**Avant** — session inconnue → `404`. Corps de requête invalide → `422` (Pydantic).
Verrou déjà pris → `409`. Ces trois cas sont décidés **avant** d'ouvrir le flux, donc
avant que `StreamingResponse` ne commence.

**Après** — il n'existe plus de code HTTP à changer. Toute exception qui survient pendant
le tour devient un événement `error` typé, suivi de la fermeture du flux.

⚠️ **Le message d'un `error` est écrit pour le client, en français, et ne contient jamais
le `str()` de l'exception.** Une trace SQLAlchemy sur une page web est une fuite. Le
détail part en `logueur.exception`, avec l'identifiant de session.

### F. `error` et `done` n'entrent pas dans l'union `Evenement`

L'union de `agent/evenements.py` décrit **le domaine**. « La base a coupé » n'est pas un
fait du dialogue, et l'y ajouter obligerait la console à traiter un cas qui ne peut pas
lui arriver. Ces deux événements vivent dans le vocabulaire de l'API, et **sont produits
par le générateur SSE, jamais par la boucle.**

`done` est terminal et obligatoire : sans lui, le front ne distingue pas « tour terminé »
de « connexion tombée ». La fermeture du flux seule ne les sépare pas.

### G. Ce que le fil porte, et ce qu'il ne porte pas

**`text_rejected` part au client. La trace d'explication ne part pas.**

Ligne de partage : **ce qui prouve un invariant sort, ce qui explique un classement
reste.** `TexteRejete` est petit (codes de grief + extrait) et c'est la seule preuve
visible à l'écran que §2 est tenu par du code et non par un prompt — c'est le meilleur
rapport effet/effort de l'étape 11. `ResultatMatching.traces` est du volume et du
débogage de moteur : `products_found` est réduit aux champs affichables.

Restent hors du fil, pour la même raison : `ResultatMatching.ecartes_faute_de_donnee`,
`Repli.iterations`, `Repli.outils_appeles`, et tout `EtatSession` (règle déjà posée par
`evenements.py`, et elle vaut ici aussi).

Si l'étape 11 réclamait la trace, elle passerait par un endpoint dédié — pas par un
élargissement de `products_found`.

### H. Le français du fil est **dérivé du registre**, jamais inventé par le front

`Critere` ne porte ni libellé ni unité ; `ProduitEnBase.specs` est en anglais. La console
résout les deux par `ATTRIBUTS[categorie][champ]` (arbitrage I de l'étape 6). **Le
sérialiseur fait exactement le même geste**, et le fil porte `libelle_fr` et `unite` à
côté de chaque champ.

Sans cela, l'étape 11 coderait du français en dur dans du JavaScript, et §3.4ter cesserait
d'être vrai de bout en bout au moment précis où il devient visible.

### I. Une déconnexion tue le tour, exactement comme un redémarrage

**C'est une correction : la note d'arbitrage disait le contraire, et elle avait tort.**

Sur une déconnexion, Starlette cesse d'itérer et le générateur reçoit un `GeneratorExit`
au `yield` en cours. `session.tour()` ne va donc jamais jusqu'à son `commit()` : **rien
n'est persisté, pas même le message du client.** L'appel API à Anthropic est payé et
perdu.

On ne cherche pas à l'éviter — l'éviter demanderait le drainage par file d'attente que
l'arbitrage C écarte. On le **rend propre** : un `finally` qui `rollback()` et `close()`
la `Session`, sans quoi la connexion revient au pool en transaction avortée et fait
échouer la requête suivante avec une erreur qui ne désigne pas la vraie cause.

C'est la même sémantique que le redémarrage en milieu de tour, et c'est cohérent :
l'atomicité de `session.py` dit que « sans rien perdre » signifie **« sans rien écrire de
faux »**. Un tour est entier ou n'a pas eu lieu.

### J. `GET /sessions/{id}` relit la prose, jamais les événements

Les `blocs` ne sont pas une projection d'événements. Reconstruire `criteria_updated` ou
`products_found` depuis les `tool_result` demanderait un **second lecteur du protocole**,
donc une seconde vérité qui divergerait du premier.

L'endpoint rend :

* l'**état**, lu par `etat_de(conversation)` — c'est-à-dire par `depuis_jsonb()`, le
  lecteur qui existe déjà ;
* la **prose échangée**, extraite des `blocs` : les blocs `text`, et l'argument `question`
  des `tool_use` nommés `ask_clarification`. Une quinzaine de lignes, un seul but,
  aucune reconstruction de fait.

⚠️ **Limite connue, à écrire au §7 et non à découvrir à l'étape 11 : les messages de repli
ne sont pas persistés.** `Repli` est émis par la boucle mais n'entre pas dans
`IssueDuTour.tours` — c'est du texte écrit en Python, que le modèle n'a jamais produit.
Une conversation rechargée après un F5 perd donc les tours clos par un repli. Le correctif
serait de persister ce message comme un tour assistant, ce qui l'injecterait dans
l'historique relu et changerait ce que le modèle voit au tour suivant : c'est une décision
de l'étape 11 si elle en a besoin, pas un effet de bord à prendre ici.

### K. Aucune nouvelle variable d'environnement

Hôte et port sont des arguments `uvicorn` dans le `Makefile`. Le front étant servi par
FastAPI (arbitrage L), **il n'y a aucun CORS à configurer** — et donc rien à rendre
configurable. `config.py` ne bouge pas.

### L. Le front est servi par le même processus

`StaticFiles` monté sur `/`, sur un répertoire `web/` que tu crées avec un `index.html`
minimal disant que l'étape 11 n'est pas faite. Un processus, une commande, pas de CORS,
pas de second serveur de dev à lancer pour la porte de sortie.

⚠️ **Le montage `/` doit venir après les routes**, sinon il les avale.

---

## Le contrat de fil — arrête-le d'abord, code ensuite

Encadrement SSE, sans variante :

```
event: <nom>\n
data: <JSON sur une seule ligne>\n
\n
```

Le JSON est produit par `json.dumps(..., ensure_ascii=False)` : les sauts de ligne de la
prose du modèle y sont échappés en `\n`, donc une trame reste une ligne. **Vérifie-le par
un test sur un texte multi-lignes** — c'est le défaut classique du SSE écrit à la main,
et il coupe le flux au milieu d'un message.

En-têtes : `text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.

### Les dix événements

| Événement Python | `event:` | `data:` |
|---|---|---|
| `CriteresMisAJour` | `criteria_updated` | `categorie`, `libelle_categorie`, `criteres[]`, `budget_usd`, `optimisation`, `mouvements_refuses[]` |
| `Sondage` | `catalog_probe` | `categorie`, `dans_le_budget`, `dans_la_zone_de_tolerance`, `fourchette_prix`, `champs[]` |
| `QuestionSuggeree` | `suggested_question` | `categorie`, `candidats`, `budget`, `champ` |
| `ProduitsTrouves` | `products_found` | `categorie`, `candidats_trouves`, `produits[]`, `au_dessus_du_budget[]`, `diagnostic` |
| `QuestionPosee` | `question` | `question`, `champ_vise` |
| `Texte` | `message` | `texte` |
| `TexteRejete` | `text_rejected` | `origine`, `tentative`, `griefs[]` |
| `Repli` | `fallback` | `message`, `motif` |
| — (API) | `error` | `code`, `message` |
| — (API) | `done` | `{}` |

Détails qui ne se devinent pas :

* `criteres[]` : `{champ, libelle_fr, unite, operateur, valeur, importance}` — `valeur`
  par `valeur_en_texte()`, `libelle_fr` et `unite` par `ATTRIBUTS` (arbitrage H).
* `fourchette_prix` : `{plus_bas, plus_haut}` ou `null`. **`null` est une information**
  (sous-catalogue vide), pas un zéro — c'est écrit dans `BornesPrix`.
* `champs[]` d'un sondage : la `Distribution` entière (`valeurs`, `total_distinct`,
  `tronque`, `renseignes`, `total`). Ce n'est pas la trace : c'est ce qui permet au
  panneau de dire ce que le catalogue contient.
* `produits[]` : `{id, nom, marque, prix_usd, disponible, specs[]}` où `specs[]` est une
  liste `{champ, libelle_fr, unite, valeur}` dérivée du registre (arbitrage H), **pas** le
  JSONB brut. Les champs de rôle `affichage` y sont, les inconnus du registre sont
  ignorés.
* `au_dessus_du_budget[]` : `{produit, ecart_usd}`.
* `diagnostic` : `{motif, propositions[]}` ou `null` ; chaque proposition porte `champ`,
  `libelle_fr`, `unite`, `valeur_atteignable`, `produits_rouverts`, `motif`,
  `dernier_recours`.
* `griefs[]` : `{code, extrait, correction}`.
* `error.code` : un `StrEnum` fermé (`tour_en_cours`, `interne`), jamais du texte libre.
* **Tout `Decimal` est une chaîne.** Tout `StrEnum` est sa `.value`.

### L'exhaustivité est vérifiée par mypy, pas par relecture

La branche finale de la fonction de sérialisation appelle `typing.assert_never`. Un
neuvième événement ajouté à l'union en étape 12 ou 13 fera alors **échouer `make
typecheck`** au lieu d'être silencieusement absent du fil. C'est le point de conception
qui justifie que ce module existe séparément.

---

## Les routes

```
POST /sessions                    -> 201 {"id": "<uuid>"}
POST /sessions/{id}/messages      -> 200 text/event-stream   (404 | 409 | 422)
GET  /sessions/{id}               -> 200 {état + prose}      (404)
GET  /health                      -> 200 {base, prompt, strict}
GET  /                            -> StaticFiles("web")
```

`/health` : base joignable (`SELECT 1`), signature du prompt système, mode `strict`
retenu par le client. C'est ce qui rend la porte de sortie exécutable par quelqu'un
d'autre que toi.

---

## Les pièges techniques de l'étape

Ils sont au nombre de quatre, et aucun ne se voit en test unitaire.

**1. La `Session` SQLAlchemy s'ouvre dans le corps du générateur.** Le générateur
s'exécute **après** que l'endpoint a rendu : une session obtenue par `Depends` avec
`yield` est fermée, ou en cours de fermeture, quand la boucle tourne. Le symptôme est un
`DetachedInstanceError` au troisième tour, pas au premier.

Corollaire : le `404` de session inconnue et le `409` de verrou pris se décident **avant**
d'ouvrir le flux, donc sur une **autre** session base, courte, ouverte dans l'endpoint.
Le verrou, lui, est repris dans la session du générateur (arbitrage D) — un verrou pris
puis relâché par le commit de la vérification ne verrouillerait rien.

**2. Le générateur se consomme en entier, ou il ne persiste rien.** Même règle que la
console. N'écris jamais de `break`, et n'insère jamais de `return` conditionnel dans la
boucle d'émission.

**3. Le `finally` est obligatoire** — `rollback()` puis `close()`. Voir l'arbitrage I.

**4. Le client Anthropic, le prompt système et le schéma d'outils sont construits une
fois, au démarrage** (`lifespan`), et partagés. Une instance par requête reperdrait la
mesure du mode `strict` (constat 6) et rechargerait le prompt à chaque message. Si
`cle_api()` lève, **le processus refuse de démarrer** avec le message qui dit quoi faire :
c'est le principe « échouer tôt sur ce qui est réellement requis » du §3.13, et pour un
serveur le premier moment réel est le démarrage.

---

## Ce que tu livres, fichier par fichier

```
src/raiyon/api/
    __init__.py
    serialisation.py   # Evenement -> (nom, données) ; formatage SSE — PUR
    schemas.py         # corps de requête et réponses JSON (Pydantic)
    verrou.py          # pg_try_advisory_xact_lock sur l'UUID de session
    prose.py           # relecture des blocs pour GET /sessions/{id} — PUR
    app.py             # application, lifespan, les cinq routes, le générateur SSE
web/
    index.html         # placeholder de l'étape 11
tests/api/
    test_serialisation.py   # purs
    test_prose.py           # purs
tests/integration/
    test_api.py             # endpoints, base réelle, faux client LLM
```

`serialisation.py` et `prose.py` **n'importent ni FastAPI, ni SQLAlchemy, ni
`anthropic`.** Étends le test d'isolation par découverte sur disque à `raiyon.api` pour
les modules purs — même geste qu'à l'étape 9 pour `raiyon.validateur`.

Ajoute aussi :

* `Makefile` : cible `api` (`uv run uvicorn raiyon.api.app:app --reload`), documentée
  comme `chat` l'est — base + seed + clé requis.
* `README.md` : la section API, la table des événements, un exemple `curl` complet.

---

## Tests attendus

### Purs — `tests/api/`

1. Les huit événements du domaine, chacun sérialisé, champ par champ.
2. **Un `Texte` multi-lignes produit une trame d'une seule ligne** — le piège du SSE.
3. Les `Decimal` sortent en chaînes, jamais en nombres JSON.
4. `fourchette_prix=None` sort en `null`, et n'est pas omis.
5. `products_found` **ne contient pas** `traces` — assertion négative explicite, nommée
   d'après l'arbitrage G.
6. `libelle_fr` et `unite` viennent bien du registre : un critère sur un champ à unité
   sort avec son unité, sans qu'aucun français soit écrit en dur dans le sérialiseur.
7. `assert_never` : un test qui documente que l'union est exhaustive (ou, plus simple, un
   commentaire renvoyant à `make typecheck` — mais alors dis-le).
8. `prose.py` : un historique contenant `text`, `tool_use ask_clarification`,
   `tool_use search_products` et `tool_result` rend exactement les textes et la question,
   dans l'ordre, et **rien d'autre**.

### Intégration — `tests/integration/test_api.py`

Base réelle, `ClientLLM` remplacé par `faux_client.py` via `dependency_overrides`.

1. `POST /sessions` rend un UUID, et la ligne existe en base.
2. Un tour complet : la suite d'événements attendue arrive dans l'ordre, et se termine
   par `done`.
3. Session inconnue → `404`, **et aucun octet de flux**.
4. Corps vide → `422`.
5. **Deux tours concurrents sur la même session** : le second reçoit `409`. C'est le test
   qui vérifie que le verrou est pris sur la bonne connexion (arbitrage D).
6. Deux tours **séquentiels** passent tous les deux — le verrou est bien relâché par le
   commit.
7. Une exception levée pendant le tour → un événement `error`, puis fermeture ; **le
   message d'exception n'apparaît pas dans le flux**.
8. `GET /sessions/{id}` après deux tours rend l'état et la prose, dans l'ordre.
9. `GET /health` rend 200 avec la base joignable.

---

## Porte de sortie

- `make check` vert — lint, `mypy --strict`, suite pure, **sans base, sans conteneur, sans
  clé**. Le ratio pur/intégration ne se dégrade pas.
- `make test-int` vert.
- **Une conversation complète menée en `curl`**, avec les événements typés visibles dans
  le flux. Colle-m'en la transcription.
- **Le serveur redémarré en cours de conversation**, qui reprend la session sans rien
  perdre — c'est-à-dire : redémarré **entre deux tours**, la session reprise par son UUID,
  l'état et la prose intacts. Colle-m'en la transcription aussi.
- `GET /health` répond avant et après.

---

## Documentation — dans le même commit

1. `PROJET.md` §5 étape 10 en ✅, avec les arbitrages A à L et leurs alternatives
   écartées, plus une section « ce que l'étape a appris, et qui n'était pas prévu ».
2. **Amendement du §3.12** : `text_delta` était déjà mort à l'étape 9 ; l'étape 10 fixe
   les noms de fil, ce que le fil porte (`text_rejected`) et ce qu'il ne porte pas (la
   trace), et pourquoi le français y est dérivé du registre.
3. **Amendement du §5 étape 8** : la promesse « remplacer le producteur sans que le
   consommateur bouge » est barrée. `messages.stream()` n'a plus de consommateur.
4. **Amendement du §5 étape 10** : la condition de bascule sur les gardes de tour est
   **restée fermée** — rien n'est persisté au milieu d'un tour, les gardes ne rejoignent
   pas le JSONB.
5. **§7, trois lignes nouvelles** :
   * une déconnexion client, comme un redémarrage en milieu de tour, perd le tour en
     entier et l'appel API avec — atomicité assumée, pas de reprise de flux ;
   * les messages de repli ne sont pas persistés, donc une conversation rechargée les perd
     (arbitrage J) ;
   * aucun heartbeat : à rouvrir derrière un proxy, avec la parade nommée (arbitrage C).
6. `README.md` : `make api`, la table des événements, un `curl` complet, et la mention que
   les prix sont figés à juillet 2025 reste où elle est.

---

## Méthode

Un jalon à la fois, et **le contrat de fil avant tout le reste**.

1. **A** — `serialisation.py`, `prose.py`, et leurs tests purs. Montre-moi une trame de
   chaque type **avant** d'écrire la moindre route : si le contrat est faux, tout ce qui
   se branche dessus est à refaire, et l'étape 11 le paie deux fois.
2. **B + C** — l'application, les routes, le verrou, le générateur. Montre-moi le tour
   complet en `curl`.
3. **D + E + F** — statiques, `make api`, tests d'intégration, documentation.

Expose l'alternative avant de trancher ce que je n'ai pas tranché, et dis-moi
explicitement quand un choix est risqué ou fragile. **Ne commence pas l'étape 11** :
aucune interface au-delà du placeholder, aucun JavaScript de dialogue.
