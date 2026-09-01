# Prompt Claude Code — Étape 12 : harnais d'éval, cassettes et client simulé

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`, au commit `5cf0085`. Les étapes 1 à 11 sont
franchies : catalogue en base, moteur déterministe, couche outils, boucle d'agent,
validateur anti-hallucination, API SSE, interface web. 720 tests purs en 6,0 s, 84
d'intégration, `mypy --strict` et `ruff` propres.

**Le §7 porte une ligne notée Élevée, et c'est la seule qui reste ouverte à ce niveau :**
*« Le prompt v1 n'est mesuré par rien avant l'étape 12. »* Les règles de conduite du
dialogue — donner avant de demander, une fourchette n'est jamais un prix, dire le refus
plutôt que le contourner — sont des **atténuations déclarées, pas vérifiées**. Une
observation en conversation manuelle n'est pas une mesure.

Tu vas réaliser **l'étape 12 et rien d'autre**. Elle ne change aucun prompt : régler une
formulation appartient à l'étape 13, et le faire maintenant rendrait incomparable ce que
le harnais mesure.

## Avant d'écrire quoi que ce soit

Lis, dans cet ordre :

1. `PROJET.md` — §3.9, §3.13, §3.14, §3.15, §3.17, §4 (les six critères), §5 étapes 8, 9,
   12 et 13, §7 en entier, §8.
2. `src/raiyon/agent/client.py` — le `Protocol` `ClientLLM` et `ReponseLLM`. **C'est la
   couture où la cassette se branche**, et sa docstring dit déjà pourquoi elle existe.
3. `tests/agent/faux_client.py` — le rejeu par index existe déjà, en plus court. Lis ce
   qu'il fait et ce qu'il ne fait pas.
4. `src/raiyon/agent/session.py` et `boucle.py` — ce que `tour()` rend, et l'`IssueDuTour`.
5. `src/raiyon/agent/evenements.py` — les huit événements. **Toutes les métriques se
   calculent depuis eux**, jamais depuis le texte.
6. `src/raiyon/api/serialisation.py` — le précédent de la traduction pure, et
   `assert_never`.
7. `src/raiyon/agent/prompts.py` — `charger()`, `empreinte()`, `prompt_systeme()`.

### Constats de lecture déjà faits — ne les redécouvre pas

1. **`ClientLLM` est un `Protocol`, et c'est tout ce dont la cassette a besoin.** Ni
   `boucle.py` ni `session.py` ne bougent de l'étape : tu remplaces le producteur de
   réponses, exactement comme `tests/integration/test_api.py` le fait déjà.
2. **`session.tour()` est un générateur qui rend une `IssueDuTour`.** Un exécuteur de
   scénario le consomme **en entier** — sinon rien n'est persisté — et collecte les
   événements au passage. La console et l'API le font déjà ; c'est le troisième
   consommateur, pas une quatrième mécanique.
3. **La température n'est pas fixée** (étape 8, arbitrage 12), et on ne la fixe pas ici.
   Une cassette est donc **un tirage**, pas une espérance. C'est l'arbitrage D ci-dessous.
4. `prompts.empreinte()` rend les douze premiers caractères d'un sha256. Tu t'en sers pour
   le prompt **et** pour le schéma d'outils.
5. Le marqueur `llm` existe déjà dans `pyproject.toml` et est désélectionné par défaut.
   **Tu n'ajoutes aucun marqueur.**

---

## Le piège central de l'étape, et il faut le traiter avant d'écrire une ligne

> **Les critères nº1 et nº2 sont garantis par construction depuis l'étape 9. Un tableau
> qui les affiche à zéro ne prouve rien.**

Le validateur refuse le texte fautif, régénère une fois, puis se replie sur un template
écrit en Python. Le texte **livré** ne peut donc pas contenir d'hallucination : mesurer
zéro, c'est mesurer le mécanisme contre lui-même.

Ce n'est pas une raison de ne pas le mesurer — c'est une raison de mesurer **trois couches
et de les publier ensemble** :

| Couche | Ce qu'elle dit | Ce qu'on en fait |
|---|---|---|
| **Ce qui est livré** | 0 grief, 0 violation budget | Critères nº1 et nº2. Une valeur non nulle signifie que **le validateur a un trou**, pas que le modèle a menti — c'est là toute l'information |
| **Ce que le modèle a tenté** | taux de rejet, par origine et par code de grief | C'est ce qui **bouge**, et c'est ce que l'étape 13 corrige dans le prompt |
| **Ce qui a fini en repli** | taux de repli, par motif | Un repli est une **réponse dégradée livrée au client**. Un tour replié est une défaillance produit, critère nº1 vert ou pas |

**Écris cette phrase dans le rapport lui-même** : *un tableau où le critère nº1 vaut 0 et
le taux de repli vaut 30 % décrit un produit qui échoue.* Sans elle, quelqu'un lira la
première ligne et s'arrêtera là — toi le premier, dans six mois.

---

## Arbitrages déjà rendus — applique-les, ne les rediscute pas

### A. Une cassette n'enregistre que les réponses du modèle

**Rien d'autre.** Les `tool_result` sont **recalculés** à chaque rejeu par le vrai moteur,
la vraie couche outils et le vrai validateur, sur le seed committé.

C'est ce qui fait que l'éval mesure la **pile entière** : un changement de scoring, une
borne recalibrée, une règle du validateur qui se resserre — tout cela se voit dans les
métriques au rejeu suivant, sans rien réenregistrer.

*Alternative écartée — enregistrer aussi les `tool_result`.* Le rejeu serait entièrement
hors ligne, donc intégrable à `make check`. Écartée parce qu'elle **fige le moteur** : un
scoring cassé rejouerait ses anciens résultats et la suite resterait verte. On testerait la
conduite du dialogue contre un passé figé, pas le produit.

**Conséquence assumée** : le rejeu exige Postgres et le seed. `make check` reste inchangé.

### B. Rejeu par index, avec assertion d'empreinte

La cassette est une liste ordonnée de prises ; on rend la n-ième, comme `FauxClient`. Mais
**on vérifie que l'empreinte de la requête reçue correspond à celle enregistrée** —
système + outils + messages, sérialisés de façon stable.

Un écart fait **échouer le scénario en nommant le tour où la conversation a divergé**, avec
un diff lisible entre l'attendu et le reçu.

*Alternative écartée — un dictionnaire indexé par empreinte.* Robuste à un
réordonnancement, mais le message d'échec parle d'un hash absent au lieu d'un tour, et une
cassette lue hors ordre ne se relit pas à la main.

*Alternative écartée — l'index seul*, comme `FauxClient`. Une divergence **désynchronise en
silence** : le modèle reçoit la réponse du tour suivant, la conversation part ailleurs, et
les métriques décrivent une conversation qui n'a jamais eu lieu. C'est le mode d'échec le
plus coûteux d'un harnais d'éval, parce qu'il produit des chiffres au lieu d'une erreur.

### C. La cassette porte les empreintes qui la périment

Un en-tête, à côté des prises :

* la version du prompt système et son **empreinte** ;
* l'**empreinte du schéma d'outils** — il fait partie du préfixe mis en cache et
  détermine ce que le modèle peut faire ; un outil dont la description change rend la
  cassette aussi périmée qu'un prompt modifié ;
* le **modèle** et la date d'enregistrement.

Au rejeu, une empreinte qui ne correspond plus **échoue en disant de régénérer**, avec la
commande à taper. C'est le point 1 du §5 étape 12, et c'est la servitude que §3.15 annonce
déjà : *« il faut les régénérer à chaque changement de prompt. C'est une discipline à
tenir, pas un détail. »* Ici, ce n'est plus une discipline — c'est une erreur.

### D. Trois prises sur trois scénarios, une ailleurs

La température n'est pas fixée : une cassette est un tirage. Un tirage par scénario, **sauf
sur trois** — budget serré, besoin très flou, zéro résultat — où l'on enregistre **trois
prises**.

On obtient un ordre de grandeur de la dispersion sur les métriques nº3 et nº4, donc de quoi
savoir, à l'étape 13, si un écart entre deux prompts est un signal ou du bruit. Le rapport
publie alors une **fourchette** sur ces trois-là, pas une valeur.

⚠️ **Trois prises ne sont pas un intervalle de confiance**, et le rapport ne doit pas
prétendre le contraire. C'est un ordre de grandeur, et c'est déjà infiniment mieux que le
plancher de bruit inconnu qu'on aurait sinon.

### E. Les métriques se calculent depuis les **événements**, jamais depuis le texte

Un scénario collecte la suite d'`Evenement` que `tour()` a rendue. Toute mesure s'en
déduit : `QuestionPosee` compte les questions, `ProduitsTrouves` porte les produits et le
diagnostic, `TexteRejete` porte l'origine et les codes, `Repli` porte son motif.

**Aucune métrique ne relit la prose du modèle avec une expression régulière.** Ce serait un
second validateur, plus faible que le premier, et il finirait par diverger de lui.

### F. La réponse de référence du critère nº4 est choisie **à la main**, et justifiée

Le critère nº4 — « le produit attendu est dans le top 3 » — a besoin d'un attendu. **Il ne
doit pas venir du moteur** : le déterminer en lançant le moteur reviendrait à tester le
moteur contre lui-même, et la métrique vaudrait 100 % par construction.

Chaque scénario concerné porte donc un identifiant de produit **choisi en lisant le
catalogue**, accompagné d'une phrase qui dit pourquoi c'est le bon choix pour ce besoin.
Écris cette phrase dans le scénario, pas dans un commentaire : c'est elle qu'on relira le
jour où la métrique chutera, et sans elle on ne saura pas si c'est le moteur qui a régressé
ou l'attendu qui était mauvais.

⚠️ Un scénario dont tu n'arrives pas à justifier l'attendu **ne porte pas d'attendu**. La
métrique nº4 se calcule sur les scénarios qui en ont un, et le rapport dit combien.

### G. Les tours du client scripté sont des **énoncés de besoin**, pas des réponses

Un client scripté ne réagit pas : le message du tour 3 est écrit d'avance et peut tomber à
côté de ce que l'assistant vient de demander. Écris donc chaque tour pour qu'il se suffise
— « en fait je peux monter à 500 » plutôt que « oui, IPS » — de sorte qu'il reste sensé
quelle que soit la question posée.

Le réalisme conversationnel est le rôle du **client simulé** (arbitrage H), pas des
scénarios déterministes. Les deux mesurent des choses différentes, et confondre les deux
donne des scénarios fragiles qui cassent au premier changement de prompt.

### H. Le client simulé ne voit que ce qu'un client voit

Le client joué par Haiku reçoit **la prose livrée** — `Texte`, `QuestionPosee`, `Repli` —
et les produits de `ProduitsTrouves`. Il ne voit **jamais** les `tool_result`, ni
l'`EtatSession`, ni les critères enregistrés, ni un `TexteRejete`.

Sans cette cloison, il devient un oracle : il « sait » ce que l'assistant a compris, et
il répond à côté de ce qu'un vrai client aurait compris. La mesure serait alors flatteuse
et fausse.

Son prompt vit dans `prompts/client_simule.v1.md`, versionné comme les autres (§3.14).

---

## Ce que tu livres, fichier par fichier

```
src/raiyon/eval/
    cassette.py       # format, en-tête, empreintes, lecture/écriture — PUR
    client.py         # ClientCassette (rejeu) et ClientEnregistreur (enveloppe)
    scenario.py       # Scenario, Attendu, la liste des scénarios — PUR
    metriques.py      # suite d'Evenement -> Mesures — PUR
    rapport.py        # Mesures -> tableau markdown — PUR
    executeur.py      # joue un scénario contre session.tour(), collecte
    client_simule.py  # le client joué par Haiku, cloisonné (arbitrage H)
scripts/eval.py       # make eval | make eval-enregistrer | make eval-live
prompts/
    client_simule.v1.md
evals/cassettes/*.json
docs/eval/rapport.md  # la sortie de `make eval`, committée
tests/eval/
    test_cassette.py test_metriques.py test_rapport.py test_scenarios.py
```

`cassette.py`, `scenario.py`, `metriques.py` et `rapport.py` **n'importent ni `anthropic`
ni SQLAlchemy**. Étends le test d'isolation par découverte sur disque à ces quatre
modules — même geste qu'aux étapes 9 et 10.

`Makefile` :

* `make eval` — rejoue les cassettes, calcule, écrit `docs/eval/rapport.md`, l'affiche, et
  **sort en code non nul si un critère binaire est violé**. Base requise, clé non requise.
* `make eval-enregistrer` — enregistre ou réenregistre les cassettes. Consomme la clé et
  des jetons. Accepte un nom de scénario en argument pour n'en refaire qu'un.
* `make eval-live` — 2 à 3 conversations avec le client simulé. Clé requise, hors CI, et
  **rien n'est enregistré en cassette** : ces conversations ne sont pas reproductibles par
  construction.

---

## Les scénarios

Dix, dont les huit qu'exige le §5 étape 12 :

1. **budget serré** — le bon produit existe, mais juste sous la limite.
2. **budget absent** — l'agent doit le demander avant de chercher (`BesoinDeBudget`).
3. **besoin très flou** — « je veux un bon écran ». Mesure le délai avant première valeur.
4. **besoin sur-spécifié sans solution** — diagnostic `critere_trop_strict`.
5. **changement d'avis en cours de route** — un critère desserré, jeton consommé.
6. **demande de comparaison entre deux propositions** — l'agent doit répondre sans
   réinventer les produits ; c'est un piège à hallucination.
7. **catégorie hors catalogue** — « une perceuse ». L'agent doit dire qu'il ne sait pas
   faire, pas improviser.
8. **zéro résultat par budget trop bas** — diagnostic `budget_trop_bas`, distinct du nº4
   par son motif.

Et deux que j'ajoute, parce qu'ils visent des invariants que **seuls des tests unitaires
touchent aujourd'hui** :

9. **desserrage refusé par le jeton de parole** (§3.17) — le client demande trois
   desserrages en un tour ; un seul passe, et l'agent doit **le dire** au lieu de laisser
   croire qu'il a été entendu. Vérifie `mouvements_refuses` non vide, et que la prose
   livrée n'affirme pas le contraire.
10. **changement de catégorie qui efface le budget** (étape 7, arbitrage D ; §7, « une
    porte tarifée plutôt qu'une seconde source de vérité ») — l'agent doit redemander le
    budget, et non le reporter en silence.

Chaque scénario porte : un nom, ses tours client, ses attentes binaires, et — quand il est
justifiable (arbitrage F) — sa réponse de référence avec sa phrase.

---

## Les métriques

| # | Métrique | D'où elle se calcule | Seuil |
|---|---|---|---|
| 1 | Hallucinations **livrées** | griefs dans le texte émis — 0 par construction | **0**, bloquant |
| 2 | Violations budget **livrées** | produit cité hors `au_dessus_du_budget` | **0**, bloquant |
| 6 | Zéro résultat traité | `ProduitsTrouves.diagnostic` non nul **et** propositions présentes | binaire, bloquant |
| 3 | Questions avant première valeur | `QuestionPosee` avant le premier `ProduitsTrouves` non vide | médiane ≤ 2 |
| 4 | Produit attendu en top 3 | `ProduitsTrouves.produits`, sur les scénarios à attendu | ≥ 80 % |
| — | **Taux de rejet** | `TexteRejete`, par origine et par code | publié, pas de seuil |
| — | **Taux de repli** | `Repli`, par motif | publié, pas de seuil |
| — | **Itérations par tour** | `IssueDuTour.iterations` | publié |

Les trois dernières lignes n'ont pas de seuil **et sont les plus intéressantes** : ce sont
elles qui bougent quand un prompt change, et elles que l'étape 13 cherchera à faire
descendre.

---

## Tests attendus — `tests/eval/`, purs

1. **Une cassette fait un aller-retour** : écrite, relue, identique. `Decimal` compris s'il
   y en a.
2. **Une empreinte de prompt qui ne correspond plus fait échouer le rejeu**, avec un
   message qui nomme la cassette et la commande à taper.
3. **Une empreinte de schéma d'outils modifiée fait échouer aussi** — c'est le cas que la
   formulation « hash du prompt » du §5 laissait échapper.
4. **Une divergence de requête au tour n échoue en nommant n**, et pas en rendant la
   mauvaise réponse. Fabrique-la : une cassette de trois prises, un `tool_result` modifié
   au deuxième tour.
5. **Les métriques se calculent sur des suites d'événements construites à la main** — pas
   sur une conversation réelle. Une suite avec deux `QuestionPosee` puis un
   `ProduitsTrouves` rend 2 ; une suite qui commence par `ProduitsTrouves` rend 0.
6. **Un `Repli(motif=VALIDATION)` compte comme repli et non comme réponse** — le tour est
   servi, mais dégradé.
7. **Le rapport rend un tableau markdown stable** : même entrée, même sortie, octet pour
   octet. Sans quoi `docs/eval/rapport.md` produirait un diff à chaque exécution.
8. **Un scénario sans attendu n'entre pas dans le calcul du nº4**, et le rapport dit sur
   combien de scénarios il porte.

Et un test d'intégration mince, sous le marqueur `integration` : **un** scénario rejoué de
bout en bout, pour que le harnais ne pourrisse pas silencieusement entre deux `make eval`.

---

## Porte de sortie

- `make check` vert — **sans base, sans conteneur, sans clé**. Le ratio pur/intégration ne
  se dégrade pas.
- `make test-int` vert.
- `make eval` produit `docs/eval/rapport.md`, **avec les critères 1, 2 et 6 à zéro
  violation**, et sort en code 0. Colle-moi le tableau.
- Les dix cassettes sont enregistrées et committées.
- **`make eval-live` mené une fois**, sur deux ou trois personas. Colle-moi une
  transcription, et dis-moi ce qu'elle montre que les scénarios scriptés ne montraient pas.
- **Neutralise une règle du validateur et relance `make eval`** : le critère nº1 doit
  cesser d'être à zéro. C'est la ligne de porte de sortie qu'on s'est donnée au correctif de
  l'étape 11 — un harnais qui ne casse pas quand on casse ce qu'il mesure ne mesure rien.
  Rétablis la règle, et dis-moi ce qui est tombé.

---

## Documentation — dans le même commit

1. `PROJET.md` §5 étape 12 en ✅, arbitrages A à H avec leurs alternatives écartées, et
   « ce que l'étape a appris ».
2. **§7 — la ligne « Le prompt v1 n'est mesuré par rien avant l'étape 12 » passe de
   Élevée à éteinte**, barrée et non effacée, avec ce que le harnais mesure réellement.
3. **§7, deux lignes nouvelles** :
   * une cassette est **un tirage**, pas une espérance ; trois prises sur trois scénarios
     donnent un ordre de grandeur, pas un intervalle de confiance ;
   * la réponse de référence du critère nº4 est **choisie à la main** ; sa qualité n'est
     vérifiée par rien, et une métrique qui chute peut accuser le moteur à tort.
4. **§3.15** : la ligne « servitude des cassettes » cesse d'être une discipline — l'écart
   d'empreinte est désormais une erreur. Amende-la.
5. `README.md` : le tableau des critères d'acceptation, **rempli** — c'est ce que §4
   promet depuis l'étape 1 (« mesurés par le harnais d'éval, publiés en tableau dans le
   README ») et que rien n'avait encore tenu.
6. Dans `docs/eval/rapport.md` lui-même : la phrase sur les trois couches. Le rapport doit
   se défendre tout seul contre une lecture qui s'arrêterait à la première ligne.

---

## Méthode

Un jalon à la fois.

1. **Les modules purs d'abord** — `cassette.py`, `metriques.py`, `rapport.py`, et leurs
   tests, sur des suites d'événements fabriquées à la main. **Aucun appel API.** Montre-moi
   un rapport calculé sur des données inventées avant qu'une seule cassette existe : si le
   tableau ne dit rien d'utile sur des données fausses, il ne dira rien sur des vraies.
2. **`executeur.py` + `client.py`**, et **un** scénario enregistré. Montre-moi la cassette,
   sa taille, et le rapport à un scénario.
3. **Les neuf autres scénarios**, enregistrés. Montre-moi le tableau complet.
4. **Le client simulé**, et une conversation.
5. **La neutralisation d'une règle**, la documentation.

Expose l'alternative avant de trancher ce que je n'ai pas tranché, et dis-moi explicitement
quand un choix est risqué ou fragile. **Ne commence pas l'étape 13** : aucun prompt ne
change dans ce commit, pas même d'un mot.
