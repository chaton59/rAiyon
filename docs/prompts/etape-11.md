# Prompt Claude Code — Étape 11 : interface web

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`. Les étapes 1 à 10 sont franchies : catalogue en base,
moteur déterministe, couche outils, boucle d'agent, validateur anti-hallucination, et
depuis l'étape 10 une API FastAPI qui streame dix événements typés en SSE. 677 tests purs
en 5,2 s, 84 d'intégration, `mypy --strict` et `ruff` propres.

**Le produit se mène aujourd'hui entièrement en `curl`.** `web/index.html` est une page de
remplacement qui dit que l'interface arrive.

Tu vas réaliser **l'étape 11 et rien d'autre**. C'est le moment où le projet devient
démontrable : le panneau latéral rend l'architecture visible, et c'est le meilleur rapport
effet/effort du plan.

## Avant d'écrire quoi que ce soit

Lis, dans cet ordre :

1. `README.md` — la section « L'API et son fil d'événements ». **C'est ta spécification**,
   et elle est à jour.
2. `src/raiyon/api/serialisation.py` en entier — la forme exacte de chaque charge utile.
   Aucune clé ne s'invente : elles sont toutes là.
3. `src/raiyon/api/app.py` — les routes, l'ordre de résolution, le montage `StaticFiles`.
4. `src/raiyon/api/schemas.py` — ce que rend `GET /sessions/{id}`.
5. `scripts/console.py` — **le consommateur de référence.** Il traite les huit événements
   du domaine et il montre lesquels méritent une ligne compacte et lesquels appartiennent
   à `--trace`. Le mode « coulisses » du navigateur est son jumeau.
6. `PROJET.md` — §3.12, §5 étapes 9, 10 et 11, §7 (les trois lignes ajoutées par l'étape
   10), §8.

### Constats de lecture déjà faits — ne les redécouvre pas

1. **Les événements d'outils arrivent au fil de l'eau ; la prose arrive d'un bloc et en
   retard.** C'est l'arbitrage A de l'étape 9, et ce n'est pas un défaut à masquer :
   pendant que le validateur relit la réponse, le panneau et les cartes sont déjà remplis.
   **L'interface doit rendre cette attente lisible**, pas la cacher — c'est la
   démonstration elle-même.
2. **Le français vient du fil, jamais du JavaScript.** Chaque champ voyage avec son
   `libelle_fr` et son `unite`, et `criteria_updated` porte `libelle_categorie`. Une seule
   table de traduction dans le front rendrait fausse la règle §3.4ter au moment précis où
   elle devient visible.
3. **Tout montant est une chaîne** (`"129.99"`). Ne la convertis jamais en `Number` :
   `parseFloat` puis `toFixed(2)` réintroduirait une approximation dans le seul projet qui
   compare des prix au caractère près. Affiche la chaîne, ajoute le symbole.
4. `done` est émis **après** que le tour a été persisté — la boucle `for` du générateur
   épuise `session.tour()`, qui commite avant de rendre la main. `done` signifie donc
   « enregistré », pas seulement « fini ». C'est ce qui autorise le front à réactiver la
   saisie sans réserve.
5. `fourchette_prix` et `champ` valent parfois `null`, et **c'est une information** : le
   sous-catalogue est vide, ou plus rien ne discrimine. Ne les traite pas comme des zéros.
6. `mouvements_refuses` porte ce qui **n'a pas** été appliqué. C'est ce qui permet
   d'afficher « je garde 144 Hz » plutôt que de laisser le client croire qu'il a été
   entendu (§3.17).

---

## Jalon 0 — le reliquat de l'étape 10, avant de toucher au front

Deux points laissés ouverts, à fermer d'abord parce que le front s'appuie dessus dès sa
première ligne.

**1. Aplatir le corps du 409.** `HTTPException` emballe son `detail`, donc le 409 rend
`{"detail": {"code", "message"}}` quand l'événement `error` rend `{"code", "message"}` à
plat. La docstring de `CodeErreur` promet que « le front affiche le même message quel que
soit le chemin par lequel l'échec lui arrive » — aujourd'hui elle est fausse, et c'est le
front qui paierait la promesse en portant deux lecteurs d'erreur.

Un `exception_handler` qui rend la charge utile à plat sur les erreurs de l'API. Le 404 et
le 422 gardent leur forme FastAPI : ils ne portent pas de `CodeErreur`, et les uniformiser
demanderait de leur en inventer un.

**2. Documenter le résidu du verrou au §7.** Le verrou est pris dans l'endpoint ; le
`try/finally` qui le relâche vit dans le générateur. Or `_flux(...)` **construit** le
générateur sans l'exécuter : tant que Starlette n'a pas appelé le premier `next()`, le
`finally` n'existe pas. Si l'itération ne commence jamais — client déjà parti quand
`http.response.start` est envoyé —, la `Session` reste ouverte, transaction non validée,
**verrou tenu jusqu'au ramasse-miettes**. Symptôme visible : un 409 « un tour est déjà en
cours » sur une session où rien ne tourne, au renvoi d'une requête qui avait lâché.

**On ne le corrige pas**, et il faut écrire pourquoi : la parade est d'amorcer le
générateur dans l'endpoint pour entrer dans le `try` avant de rendre, ce qui oblige à
rechaîner la première trame et complique le seul endroit du code qui doit rester lisible.
Le défaut s'auto-guérit au GC, sa fenêtre est étroite, et sa conséquence est un 409
qu'un renvoi résout. Ligne au §7, avec la parade nommée et son coût.

---

## Arbitrages déjà rendus — applique-les, ne les rediscute pas

### A. Vanilla, modules ES, aucun build

Du JavaScript natif en `<script type="module">`, servi tel quel par `StaticFiles`. **Pas
de `package.json`, pas de `node_modules`, pas d'étape de compilation, pas de second
serveur.** `make api` reste la seule commande, et l'arbitrage L de l'étape 10 — un
processus, donc aucun CORS — tient sans effort.

*Alternative écartée — Vite + React.* Un point de plus sur un CV, et un coût réel : un
build à lancer avant `make api`, un serveur de développement séparé qui **rouvre le CORS
que l'étape 10 venait de fermer**, et un dépôt bilingue. L'étape 11 est la plus courte du
plan ; ce choix en aurait fait la plus longue.

*Alternative écartée — Preact + htm vendorés.* Le rendu déclaratif sans build. Écartée
pour deux dépendances JavaScript à justifier dans un projet qui n'en a aucune.

**Conséquence à assumer, pas à contourner** : le rendu s'écrit à la main. Interdis-toi la
tentation d'écrire un micro-framework — un rendu par événement, ciblé, suffit largement à
cette page.

### B. La sécurité du rendu : `textContent`, jamais `innerHTML`

> **On ne fait pas confiance au modèle pour les faits ; on ne lui fait pas davantage
> confiance pour le HTML.**

Toute chaîne venue du fil — prose, question, nom de produit, extrait de grief, message de
repli — entre dans le DOM par `textContent` ou `createTextNode`. **Aucun `innerHTML` sur
une valeur du fil**, aucune exception, y compris pour un nom de produit qui « ne peut pas »
contenir de balise.

Le modèle produit du markdown (`**gras**`, listes numérotées). Tu en interprètes **deux
formes et pas une de plus** — le gras `**…**` et les sauts de ligne — et tu les construis
en **nœuds DOM**, jamais en chaîne de HTML assemblée puis injectée. Une trentaine de
lignes, testables, et qui ne peuvent structurellement pas ouvrir d'injection.

Le reste du markdown s'affiche tel quel. **C'est le prompt qu'il faudra corriger à
l'étape 13, pas le front qu'il faut armer d'un parseur** — écris-le au §7 plutôt que de
laisser un futur toi ajouter une dépendance markdown.

### C. Les cartes produits vivent dans le fil du chat, pas dans le panneau

`products_found` arrive **avant** la prose qui le commente. Poser les cartes dans le flux
de conversation, à l'endroit où elles arrivent, rend visible l'ordre réel : le code a
trouvé, puis le modèle a écrit à propos de ce qu'on lui a donné. C'est §2 rendu observable
sans une ligne d'explication.

*Alternative écartée — les cartes dans le panneau latéral.* Le panneau resterait le seul
endroit « technique » et le chat le seul endroit « produit ». Écartée parce qu'elle casse
la chronologie, qui est précisément ce qu'on veut montrer.

Le panneau porte donc **ce que le code a compris** (`criteria_updated`) et l'activité
(`catalog_probe`, `suggested_question`), pas les résultats.

### D. L'attente est affichée, pas masquée

Entre le dernier événement d'outil et le `message`, le validateur relit la réponse. Le
front dit ce qui se passe — « vérification de la réponse… » — plutôt que d'afficher un
sablier générique. C'est la seule chose qui bouge à ce moment-là, et c'est ce que
l'arbitrage A de l'étape 9 a acheté.

⚠️ N'invente pas d'étapes que le fil ne dit pas. L'indicateur reflète **le dernier
événement reçu**, et rien d'autre : après `catalog_probe`, « lecture du catalogue » ;
après `products_found`, « vérification de la réponse » ; au démarrage du tour, « … ».

### E. Le mode « coulisses », interrupteur dans le panneau

Fermé : l'interface d'un produit. Le client voit le chat, le panneau des critères, les
cartes. `text_rejected`, `suggested_question` et le détail des distributions **n'y sont
pas** — un client n'a rien à faire des reprises internes.

Ouvert : chaque `text_rejected` s'affiche dans le fil, avec son origine, sa tentative et
ses griefs (code, extrait, correction) ; `catalog_probe` déplie ses distributions ;
`suggested_question` montre le champ de plus fort gain. **C'est le `--trace` de la console
porté au navigateur**, et c'est la démonstration qu'on montre en entretien.

L'état de l'interrupteur ne se persiste pas : une page rechargée repart en mode produit.
C'est celui qu'un visiteur doit voir en premier.

⚠️ **Les événements masqués sont reçus et conservés**, pas jetés : basculer l'interrupteur
au milieu d'une conversation affiche ce qui s'est déjà passé. Un mode qui ne montrerait que
la suite obligerait à refaire la conversation pour voir le rejet qu'on vient de rater.

### F. L'identifiant de session vit dans le fragment d'URL

`#<uuid>`. Un rechargement retrouve la conversation, l'URL se copie et se recolle, et
l'identifiant est **visible** — ce qui est un atout de démonstration, pas un détail.

*Alternative écartée — `localStorage`.* Invisible, non partageable, et elle rend la
seconde conversation impossible sans vider le stockage.

Au chargement : fragment présent → `GET /sessions/{id}` pour réhydrater ; absent → aucun
appel, la session est créée au premier message envoyé.

⚠️ **Un `GET` sur une session inconnue rend 404** (fragment périmé, base réinitialisée). Le
front repart alors sur une conversation neuve **en le disant**, et n'affiche pas une page
vide dont personne ne comprendrait la cause.

### G. Ce que la réhydratation perd, et qui doit se voir

`GET /sessions/{id}` rend l'état et la prose, **jamais les événements** (arbitrage J de
l'étape 10). Une conversation rechargée n'a donc ni cartes produits, ni panneau
d'activité : seulement les critères et les paroles.

Et elle perd davantage — **les messages de repli ne sont pas persistés** (§7). Un tour
clos par un `fallback` réapparaît après un F5 **sans sa réponse**.

L'interface ne fait pas semblant : la conversation réhydratée est marquée comme telle
(« conversation reprise — les résultats détaillés ne sont pas rejoués »). Inventer une
carte produit à partir de rien serait exactement ce que ce projet interdit au modèle.

### H. La saisie est verrouillée pendant un tour

Un seul tour à la fois par session (arbitrage D de l'étape 10). Le champ et le bouton sont
désactivés dès l'envoi, réactivés sur `done`, sur `error`, ou sur un échec réseau.

Le 409 reste traité : il arrive quand **deux onglets** partagent la même URL, ce que le
verrouillage local ne peut pas empêcher. Message humain, saisie réactivée.

### I. Rien n'est testé en JavaScript, et le contrat l'est en Python

Aucune dépendance nouvelle, aucun `node_modules`, `make check` inchangé — voir la section
« Tests attendus », qui dit exactement ce que cela couvre et ce que cela ne couvre pas.

---

## Les pièges techniques de l'étape

Quatre, et les deux premiers sont ceux qui se voient en démonstration et pas en relecture.

**1. `TextDecoder` doit décoder en flux.** `new TextDecoder("utf-8")` sans
`{ stream: true }` à chaque `decode()` casse tout caractère multi-octets coupé entre deux
morceaux réseau. La prose est en français : les accents sont partout, et le défaut produit
un `�` au milieu d'un mot, de façon intermittente. **Passe `{ stream: true }`**, toujours.

**2. Le tampon garde sa queue.** Les morceaux d'un `ReadableStream` ne s'alignent pas sur
les trames. Le parseur accumule, découpe sur `\n\n`, traite les segments complets et
**conserve le dernier morceau incomplet** pour le tour suivant. C'est l'erreur classique
du SSE écrit à la main, et son symptôme est un événement perdu de temps en temps — donc
une carte produit qui manque une fois sur dix.

**3. Le parseur implémente le cadrage du projet, pas la spécification SSE.** Notre
producteur émet exactement `event:` puis un `data:` unique puis une ligne vide. N'écris
pas un parseur générique multi-`data:` : il serait plus long, non exercé, et faussement
rassurant. **Écris-le dans la docstring de la fonction** — c'est ce qui rend la limite
vérifiable le jour où le producteur changerait.

**4. Le défilement automatique n'est pas inconditionnel.** On ne défile que si l'on était
déjà en bas. Sinon, relire une réponse pendant que la suivante arrive devient impossible.

---

## Ce que tu livres, fichier par fichier

```
web/
    index.html      # la structure, deux colonnes, aucun script en ligne
    style.css       # tout le style ; aucune classe inventée par le JS qui n'existe pas ici
    flux.js         # fetch + ReadableStream -> événements typés — LE module à isoler
    etat.js         # le réducteur : un événement, un état ; aucune manipulation du DOM
    rendu.js        # état -> DOM, textContent uniquement (arbitrage B)
    app.js          # câblage : saisie, fragment d'URL, verrouillage, coulisses
tests/api/
    test_cadrage_sse.py   # le contrat du producteur, purs
```

`flux.js` et `etat.js` ne touchent **jamais** au DOM ; `rendu.js` ne parle **jamais** au
réseau. C'est la même séparation que `serialisation.py` / `app.py` côté serveur, et elle
sert la même chose : ce qui peut casser en silence vit dans un module qu'on peut lire seul.

Mets à jour :

* `README.md` — une section « L'interface » : ce que montre le panneau, ce que montre le
  mode coulisses, ce que la réhydratation ne rejoue pas.
* `PROJET.md` — §5 étape 11 en ✅, arbitrages A à I, et la section « ce que l'étape a
  appris ».

---

## Tests attendus

### `tests/api/test_cadrage_sse.py` — purs, avec le faux client de l'étape 8

**Ce qu'ils testent : le producteur.** Le front s'appuie sur trois propriétés du flux, et
ce sont les trois qui peuvent se dégrader en silence côté serveur :

1. **Une trame est une ligne `event:`, une ligne `data:`, une ligne vide.** Sur tous les
   types d'événements, sans exception.
2. **Aucun `data:` ne contient de saut de ligne brut**, y compris pour une prose
   multi-lignes et pour un extrait de grief. C'est ce qui autorise le découpage sur
   `\n\n`.
3. **Le flux se recompose sous un découpage arbitraire.** Rejoue un tour complet en
   coupant les octets à 1, 7, 64 et 4096, réassemble avec l'algorithme exact du parseur —
   accumuler, découper, garder la queue — et vérifie qu'on retrouve la même suite
   d'événements. **Écris cet algorithme une fois, dans le test, et dis en commentaire
   qu'il est la spécification que `flux.js` transcrit.**
4. **L'ordre d'un tour** : les événements d'outils précèdent `message`, et `done` est
   dernier.

### ⚠️ Ce que ces tests ne couvrent pas, et qui va au §7

Ils prouvent que **le serveur émet** des trames bien formées et recomposables. Ils ne
prouvent **pas** que `flux.js` les recompose correctement : un parseur qui oublierait sa
queue passerait toute cette suite au vert.

Écris-le en toutes lettres au §7 : *le parseur SSE et le réducteur du front sont le seul
code du projet que rien ne vérifie automatiquement ; l'atténuation est la concentration —
la logique tient dans deux modules nommés, sans DOM, dont l'un transcrit un algorithme
écrit et testé en Python.* C'est une atténuation, pas une preuve, et le dire ainsi vaut
mieux qu'un test Playwright qui donnerait l'illusion de la couverture pour le prix d'une
suite qui cesse de tourner « sans base, sans conteneur, sans clé ».

*Alternative écartée — Playwright de bout en bout.* La porte de sortie, littéralement
automatisée. Écartée pour une dépendance, des navigateurs à installer, un serveur à lancer
en test, et surtout parce que `make check` perdrait la propriété qui fait sa valeur.

---

## Porte de sortie

- `make check` vert — **sans base, sans conteneur, sans clé**. Le ratio pur/intégration ne
  se dégrade pas.
- `make test-int` vert.
- **Une conversation complète dans le navigateur**, où l'on voit les critères se remplir au
  fil du dialogue. Décris-moi ce qui s'affiche à chaque tour ; capture d'écran si tu peux.
- **Le cas zéro résultat rendu lisible** : un `diagnostic` affiché avec ses propositions
  de relâchement — c'est le critère d'acceptation nº6, et c'est la première fois qu'il se
  voit.
- **Un rejet du validateur observé en mode coulisses**, avec ses griefs. Provoque-le si la
  conversation ne le donne pas spontanément.
- **F5 en cours de conversation** : la session revient par son fragment d'URL, l'état et la
  prose sont là, et l'interface dit ce qu'elle ne rejoue pas.
- **Deux onglets sur la même URL** : le second reçoit un 409 dit en français, saisie
  réactivée.

---

## Documentation — dans le même commit

1. `PROJET.md` §5 étape 11 en ✅, arbitrages A à I avec leurs alternatives écartées, et
   « ce que l'étape a appris, et qui n'était pas prévu ».
2. **§7, deux lignes nouvelles** : le parseur et le réducteur du front ne sont vérifiés par
   rien (avec l'atténuation par concentration) ; la prose du modèle contient du markdown
   dont le front n'interprète que deux formes — **c'est le prompt qu'on corrigera à
   l'étape 13**, pas le front qu'on armera d'un parseur.
3. **§7, la ligne du jalon 0** : le verrou tenu jusqu'au GC quand le générateur n'est jamais
   démarré, avec la parade nommée et la raison de ne pas la prendre.
4. `README.md` — la section « L'interface ».
5. Le §3.12 disait « l'interface peut alors afficher un panneau *voici ce que j'ai compris
   de ton besoin* — c'est le meilleur rapport effet/effort du projet ». **Dis si c'était
   vrai**, et ce que ça a réellement coûté en lignes.

---

## Méthode

Un jalon à la fois.

0. **Le reliquat de l'étape 10** — le 409 aplati, la ligne de §7. Montre-moi le diff avant
   de continuer.
1. **`flux.js` + `test_cadrage_sse.py`** — le parseur et le contrat qu'il transcrit, sans
   une ligne de DOM. Montre-moi les événements arriver dans la console du navigateur avant
   d'écrire quoi que ce soit de visuel. Si le flux est faux, tout ce qui se branche dessus
   est à refaire.
2. **`etat.js` + `rendu.js`** — le chat, le panneau, les cartes. Mode produit uniquement.
3. **Le mode coulisses, le fragment d'URL, la réhydratation, le verrouillage de saisie.**
4. **La conversation de bout en bout**, et la documentation.

Expose l'alternative avant de trancher ce que je n'ai pas tranché, et dis-moi explicitement
quand un choix est risqué ou fragile. **Ne commence pas l'étape 12** : aucun harnais
d'éval, aucune cassette, aucun client simulé.
