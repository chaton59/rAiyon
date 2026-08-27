# rAiyon — Assistant conseil produit en temps réel

Document de cadrage. Il consigne les décisions d'architecture, **les alternatives
écartées et pourquoi**. Il fait foi : toute décision qui le contredit doit être
discutée et amender ce fichier.

Statut : cadrage validé. Étape suivante — exploration du dataset.
Dernière révision : 2026-08-27.

---

## 1. Le problème

Un client arrive sur une page web sans savoir précisément ce qu'il veut. Il
décrit un besoin en langage naturel, souvent flou et incomplet. L'assistant doit
dialoguer avec lui, comprendre son besoin et son budget, puis recommander 1 à 3
produits réels du catalogue, classés, avec le « pourquoi » de chacun.

Domaine retenu : équipements électriques et électroniques.

### Le mode d'échec à éviter

Un LLM branché seul sur une base produits invente. Il invente des références,
des prix, des caractéristiques, et surtout des *justifications* — un produit
réel recommandé pour une raison fausse est aussi grave qu'un produit inventé.

Tout ce document découle de cette contrainte.

---

## 2. Contrainte d'architecture non négociable

> **Le LLM ne produit jamais un fait. Il produit du langage à propos de faits
> que le code lui a fournis.**

En pratique :

- Les produits, prix, stocks et caractéristiques viennent **exclusivement** de
  requêtes SQL exécutées par du code Python.
- Le LLM ne transcrit jamais un chiffre : les prix sont des `Decimal` typés que
  **le code formate**, et qui sont validés en sortie.
- Le « pourquoi » d'une recommandation vient de la **trace d'explication** que
  le moteur de matching produit, pas de l'inférence du LLM.
- Un validateur programmatique vérifie chaque réponse avant qu'elle atteigne le
  client.

---

## 3. Décisions d'architecture

### 3.1 — Catalogue : 5 à 6 catégories, ~30 produits chacune

**Retenu.** Un périmètre de 150 à 200 produits sur 5-6 catégories.

**Condition attachée à ce choix :** chaque catégorie doit disposer d'au moins
**6 attributs discriminants** (au-delà du prix et de la marque). Sans cela, le
moteur n'a rien pour départager et toute recommandation devient triviale. Cette
condition est vérifiée à l'étape d'exploration du dataset, avant écriture du
pipeline.

**Alternative écartée — 1 à 2 catégories profondes.** Matching plus riche et
schéma plus simple, mais ne démontre pas que l'architecture absorbe
l'hétérogénéité des attributs, qui est le vrai problème de modélisation ici.

**Alternative écartée — catalogue large (10+ catégories, 500+ produits).**
L'effort part dans la production de données au lieu du raisonnement, qui est le
sujet du projet.

### 3.2 — PostgreSQL, via docker-compose

**Retenu.** Postgres avec SQLAlchemy et migrations Alembic.

Raisons : les attributs produits sont hétérogènes entre catégories, et Postgres
indexe le **JSONB** — on peut donc filtrer efficacement sur des specs variables
sans multiplier les colonnes NULL. Il ouvre aussi la porte à `pg_trgm` et
`pgvector` sans changer de moteur.

**Alternative écartée — SQLite.** Zéro installation et fichier versionnable avec
le repo : nettement plus agréable pour qui clone le projet. Mais l'indexation
JSON y est faible, ce qui aurait poussé vers un schéma en colonnes fixes ou en
EAV, tous deux moins bons ici.

**Conséquence assumée :** Docker devient un prérequis de la démo. Atténuation :
un `docker-compose up` unique, et un jeu de données seedé automatiquement.

### 3.3 — Modélisation des attributs : colonnes communes + JSONB

Colonnes typées et indexées pour ce qui est commun à tout produit — `id`, `nom`,
`marque`, `catégorie`, `prix`, `stock`, `description`. Un champ `specs` en JSONB
pour ce qui est propre à la catégorie.

**Alternative écartée — colonnes fixes pour tout.** SQL le plus simple et le plus
rapide, mais chaque nouvelle catégorie devient une migration, et la table se
remplit de NULL.

**Alternative écartée — EAV (table clé/valeur).** Flexibilité maximale, mais les
requêtes deviennent des cascades de JOIN et on perd tout typage.

### 3.4 — Données : dataset public réel + passe de normalisation LLM

**Retenu.** Un dataset public sert de colonne vertébrale (noms, marques, prix,
descriptions authentiques). Un script one-shot appelle un LLM pour extraire et
normaliser les caractéristiques techniques vers le schéma retenu. Le résultat est
**figé dans un seed versionné** : le pipeline n'est pas rejoué à chaque
installation.

Candidats à évaluer :
- [Datafiniti — Electronic Products & Pricing](https://www.kaggle.com/datasets/datafiniti/electronic-products-prices)
  (15 000 produits, mais aucune spec technique)
- [McAuley-Lab/Amazon-Reviews-2023](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023)
  (métadonnées riches, champ `details` semi-structuré, très bruité)
- [iarbel/amazon-product-data-filter](https://huggingface.co/datasets/iarbel/amazon-product-data-filter)
  (données techniques en tuples clé/valeur)

Le script de normalisation est lui-même une démonstration de sortie structurée
LLM, et fait partie des livrables.

**Alternative écartée — catalogue entièrement généré.** Beaucoup plus rapide, et
permet de placer volontairement les cas limites nécessaires aux tests. Mais des
prix inventés affaiblissent un projet dont l'argument central est précisément de
ne rien inventer.

**Conséquence assumée :** une étape de data engineering qui n'est pas le cœur du
sujet, et des surprises garanties au nettoyage. Ce qui reste dérivé plutôt que
réel sera **explicitement documenté** dans le README.

### 3.5 — Recherche vectorielle : hors périmètre du produit livrable

**Retenu.** Le moteur est 100 % SQL. La recherche hybride est documentée comme
extension possible une fois le produit complet et évalué.

Raison de fond : **un vecteur ne sait pas compter.** Les descriptions d'une
perceuse à 420 € et d'une perceuse à 89 € produisent des embeddings quasi
identiques. Une recherche vectorielle sur « perceuse à moins de 150 € » remonte
volontiers la première. Le respect du budget serait cassé au niveau de la
récupération, avant même que le LLM parle.

Second motif : un RAG rend des **morceaux de texte**, que le LLM doit relire pour
en extraire un prix. Chaque relecture est une occasion d'halluciner. SQL rend des
lignes typées.

**Extension prévue.** Les vecteurs ont une place légitime — pas comme moyen de
récupérer, comme **signal de score** après le filtrage dur :

```
1. SQL WHERE      filtres durs (budget, catégorie, contraintes)
2. score_specs    attributs structurés pondérés                  0-1
3. score_usage    similarité entre besoin exprimé et description 0-1
4. classement     0.75 × score_specs + 0.25 × score_usage
```

Règle stricte si cette extension est implémentée : **le vecteur peut départager,
jamais justifier.** Un score cosinus n'est pas une raison présentable à un client.

### 3.6 — Orchestration : agent avec outils, invariants dans la couche outils

**Retenu.** Le LLM conduit la conversation. Il dispose d'outils et décide quand
les appeler. Aucune machine à états ne pilote le tour de parole.

Le raisonnement qui rend ce choix sûr : **les garanties ne vivent pas dans
l'orchestration, elles vivent dans les outils.** Un agent n'est incontrôlable que
si on lui donne des outils qui le laissent l'être.

```python
def search_products(criteria_du_llm, session):
    # Le LLM peut demander max_price=250 alors que le client a dit 200.
    # Le code arbitre : la session fait foi.
    c = clamp(criteria_du_llm, session.validated_criteria)
    return {
        "produits":            sql_search(c, max_price=session.budget),
        "au_dessus_du_budget": sql_search(c, min_price=session.budget,
                                             max_price=session.budget * 1.15),
    }
```

Les deux ensembles sont **structurellement séparés**. Le LLM ne peut pas
présenter un produit hors budget comme étant dedans, quelle que soit sa sortie.

**Alternative écartée — machine à états explicite.** Le code décide à chaque tour
d'extraire, relancer ou recommander. `decide_next_action()` devient une fonction
pure, testable en 0,2 seconde et sans appel API, et les critères d'acceptation
sont garantis par construction. C'était le choix prudent.

Motif du rejet : la machine à états répond mal aux virages hors-script, qui sont
la norme dans une conversation de vente réelle — « compare plutôt la 1 et la 3 »,
« et pour ma sœur qui est gauchère ? », « il me faut aussi une ponceuse, 300 €
pour les deux ». Chacun demande un état prévu à l'avance. L'agent les encaisse
naturellement.

**Alternative écartée — hybride (états + sondage anticipé du catalogue).**
Compromis raisonnable, rejeté pour la même raison : la boucle de dialogue restait
rigide là où on veut de la fluidité.

**Ce que ce choix coûte, explicitement.** La testabilité par tests unitaires
rapides disparaît en grande partie : il n'y a plus de fonction de décision pure à
assertionner. Le comportement se valide par **éval** — des scénarios, des taux,
des métriques — ce qui est plus lent, plus cher et plus inconfortable. C'est le
prix assumé, et c'est ce qui rend le harnais d'éval non optionnel.

Coûts secondaires : 2 à 4 appels API par tour au lieu de 2 (latence atténuée par
le streaming), et un garde-fou `max_iterations` contre l'emballement.

### 3.7 — Les outils exposés à l'agent

| Outil | Rend | Rôle |
|---|---|---|
| `probe_catalog(criteria)` | **Agrégats seuls** : nombre de résultats, fourchette de prix, valeurs distinctes par attribut | Permet à l'agent de sonder sans récupérer de produits — « il me reste 12 modèles entre 90 et 340 € » |
| `suggest_next_question()` | Le champ manquant le plus discriminant sur le sous-catalogue courant | Expose le calcul de gain d'information ; l'agent reste libre de s'en servir |
| `search_products(criteria)` | Produits réels, `produits` et `au_dessus_du_budget` séparés, avec trace d'explication | Seule source de produits |
| `ask_clarification(preamble, question, champ)` | — | Poser une question est un acte tracé, donc mesurable en éval |

`probe_catalog` ne rend jamais de produit. C'est ce qui permet à l'agent d'être
fluide pendant la collecte sans court-circuiter le chemin de recommandation, qui
reste unique et instrumenté.

### 3.8 — La relance : gain d'information, pas ordre codé

**Retenu.** `suggest_next_question()` interroge le sous-catalogue courant et rend
le champ dont la connaissance découperait le mieux l'espace restant.

Bénéfice concret : si tous les produits restants sont sans fil, l'outil ne
proposera jamais de demander « fil ou sans fil ? ». C'est ce qui sépare un bot
qui paraît intelligent d'un questionnaire.

**Alternative écartée — liste de priorité codée par catégorie.** 20 lignes,
totalement prévisible, mais pose régulièrement des questions sans valeur
discriminante.

### 3.9 — Le nombre de questions : métrique, pas plafond

La spec initiale imposait « pas plus de 3 questions avant une première
proposition ». **Cette contrainte est levée en tant que plafond dur**, et
remplacée par :

- une **règle de dialogue** dans le prompt système : *ne jamais demander sans
  donner quelque chose en retour*. Montrer des pistes provisoires, puis affiner ;
- une **métrique d'éval** : « questions avant première recommandation », suivie
  sur chaque scénario. Une dérive de 2 à 6 après un changement de prompt se voit
  immédiatement ;
- un **garde-fou anti-boucle** à 8 itérations, qui est une protection technique
  et non une règle d'expérience.

Motif : le plafond protégeait contre un mode d'échec réel — l'interrogatoire —
mais un seuil à 3 est arbitraire. Si le client est engagé et affine son besoin,
la 4ᵉ question est exactement ce qu'il attend. Le bon indicateur est le **délai
avant première valeur**, pas le compte de questions.

### 3.10 — Budget : contrainte dure avec zone de tolérance séparée

Le budget déclaré est un filtre dur. Une tolérance paramétrable (défaut : +15 %)
définit une zone où les produits sont récupérés **dans un champ distinct**,
taggés avec l'écart exact.

Le moteur ne décide pas de les proposer : il les rend disponibles. L'agent peut
les mentionner, mais jamais mélangés au classement principal, et le validateur
vérifie que tout produit hors budget cité est bien présenté comme tel.

### 3.11 — Anti-hallucination : validateur programmatique

Trois niveaux, cumulés :

1. **Prompt** — « tu ne cites que les produits fournis, par leur ID ». Nécessaire,
   jamais suffisant.
2. **Validateur post-génération** — la réponse est parsée, tous les IDs, prix et
   valeurs chiffrées sont extraits et vérifiés contre le contexte réellement
   fourni. Écart → une régénération, puis repli.
3. **Repli sur template** — le code rédige la recommandation, le LLM n'assure que
   la transition. Texte plus sec, risque nul.

C'est le niveau 2 qui transforme « zéro hallucination » d'une intention en un
test qui passe ou échoue.

### 3.12 — API : FastAPI, SSE, événements typés

**SSE plutôt que WebSocket** : le flux est unidirectionnel serveur→client, SSE est
natif en HTTP et se teste en `curl`.

**Événements typés plutôt que texte brut** :

```
criteria_updated   { budget: 200, catégorie: "perceuse", sans_fil: true }
catalog_probe      { count: 12, price_range: [90, 340] }
products_found     [ { id, nom, prix, score, explication }, ... ]
text_delta         "…"
```

L'interface peut alors afficher un panneau « voici ce que j'ai compris de ton
besoin » qui rend l'architecture visible à l'écran. C'est le meilleur rapport
effet/effort du projet.

**Sessions persistées en table Postgres**, pas dans un dict en mémoire : survit au
redémarrage, autorise le multi-worker, coûte une trentaine de lignes.

### 3.13 — Modèles

| Usage | Modèle | Raison |
|---|---|---|
| Boucle agent (dialogue + tool use) | Sonnet | Porte toute la qualité perçue et le raisonnement sur les outils |
| Normalisation du dataset | Haiku | Tâche fermée, à sortie structurée, sur des milliers de lignes |
| Client simulé dans les évals | Haiku | Génération de tours de parole, coût dominant en volume |

Modèles configurables par variable d'environnement. Prompt caching activé sur le
prompt système, qui est long et stable.

**Note.** L'architecture agent a rendu caduque la séparation « Haiku pour
l'extraction / Sonnet pour la rédaction » envisagée initialement : il n'y a plus
d'appel d'extraction distinct. Les critères sont désormais **dérivés des
arguments** que l'agent passe à ses outils, fusionnés et validés par le code dans
`session.validated_criteria`.

### 3.14 — Prompts versionnés

Les prompts système vivent dans `prompts/`, en fichiers markdown numérotés
(`systeme.v1.md`, `recommandation.v1.md`), chargés au runtime. La version en
vigueur est loguée à chaque appel.

Sans cela, impossible de comparer deux formulations sur la même suite de
scénarios — ce qui est le cœur du travail sur le dialogue.

### 3.15 — Stratégie de test

| Cible | Approche |
|---|---|
| Moteur de matching | pytest pur, catalogue fixture, **zéro appel API** |
| Invariants des outils | Assertions dures : clamp budget, séparation hors-budget, forme des agrégats |
| Validateur | Fixtures de sorties LLM piégeuses (prix modifié, ID inexistant, produit inventé) |
| Scénarios bout en bout | **Cassettes enregistrées** : le premier run appelle l'API, les suivants rejouent depuis le disque. CI gratuite et déterministe |
| Dialogue réel | 2-3 scénarios avec **client simulé par LLM**, lancés à la main, hors CI |

**Alternative écartée — mocks écrits à la main.** Aucun appel API, mais on teste
ses propres suppositions sur ce que le LLM répond, pas la réalité.

**Alternative écartée — appels réels marqués et exclus par défaut.** Teste la
vérité, mais rien ne l'exécute automatiquement : les régressions passent.

**Servitude des cassettes :** il faut les régénérer à chaque changement de prompt.
C'est une discipline à tenir, pas un détail.

---

## 4. Critères d'acceptation

Mesurés par le harnais d'éval, publiés en tableau dans le README.

| # | Critère | Seuil | Mesure |
|---|---|---|---|
| 1 | Aucun produit, prix ou spec inventé | **0**, strict | Validateur, sur tous les scénarios |
| 2 | Budget jamais dépassé sans présentation explicite | **0** violation | Assertion sur les produits cités hors `au_dessus_du_budget` |
| 3 | Délai avant première valeur | ≤ 2 questions médian | Métrique d'éval, suivie dans le temps |
| 4 | Pertinence : le produit attendu est dans le top 3 | ≥ 80 % | Scénarios à réponse de référence |
| 5 | Moteur de matching testable sans API | binaire | La suite `tests/matching/` tourne hors ligne |
| 6 | Cas zéro résultat traité proprement | binaire | Scénario dédié : dire pourquoi + proposer l'assouplissement du critère le plus coûteux |

Les critères 1, 2, 5 et 6 sont binaires et bloquants. Les 3 et 4 sont des
métriques de qualité que l'on suit et que l'on cherche à améliorer.

---

## 5. Plan d'exécution

Chaque étape se termine par une **porte de sortie** : une vérification concrète.
Tant qu'elle n'est pas franchie, on ne passe pas à la suivante — c'est ce qui
évite de construire trois couches sur une fondation fausse.

### Étape 1 — Cadrage ✅

Ce document.

**Porte de sortie :** les décisions sont écrites avec leurs alternatives écartées.

---

### Étape 2 — Socle du dépôt

Structure de projet, `pyproject.toml`, `.env.example`, `docker-compose.yml` avec
Postgres, `ruff` et `pytest` configurés, un test bidon qui passe.

**Porte de sortie :** `docker-compose up` démarre Postgres, `pytest` tourne vert
sur un dépôt vide.

Cette étape paraît accessoire. Elle évite de bricoler la configuration au milieu
d'un travail de fond, ce qui est là qu'on introduit des clés en dur.

---

### Étape 3 — Exploration du dataset et schéma d'attributs

**C'est l'étape la plus risquée du projet.** Tout ce qui suit en dépend.

1. Télécharger et inspecter les trois datasets candidats.
2. Mesurer, pour chaque catégorie candidate : nombre de produits exploitables,
   taux de remplissage des attributs, cohérence des clés.
3. Retenir 5-6 catégories et écrire pour chacune son **schéma d'attributs** :
   nom du champ, type, unité, plage de valeurs, rôle dans le matching
   (filtre dur / critère de score / affichage seul).
4. Faire valider ce schéma avant d'écrire la moindre ligne de pipeline.

**Porte de sortie :** un fichier `catalogue/schema_attributs.md` où chaque
catégorie retenue expose **au moins 6 attributs discriminants** documentés, et
un échantillon de 20 produits réels montrant que ces attributs sont réellement
remplissables.

**Si la porte ne s'ouvre pas :** réduire à 3 catégories, ou basculer sur des
specs complétées par génération — documenté honnêtement dans le README.

---

### Étape 4 — Schéma SQL et migrations

Modèles SQLAlchemy (`products`, `sessions`, `conversation_turns`), migration
Alembic initiale, index sur `catégorie`, `prix`, et index GIN sur `specs`.

Modèles Pydantic miroirs pour la validation à l'insertion : rien n'entre en base
sans avoir été typé et validé.

**Porte de sortie :** la migration s'applique sur une base vide, un test insère
et relit un produit, et un produit malformé est rejeté par Pydantic.

---

### Étape 5 — Pipeline de normalisation des données

Script one-shot : lecture du dataset brut → filtrage sur les catégories retenues
→ appel LLM (Haiku, sortie structurée) pour extraire les attributs vers le schéma
→ validation Pydantic → écriture d'un **seed versionné** (JSON ou SQL).

Le seed est committé. Le pipeline n'est pas rejoué à l'installation.

Prévoir dès maintenant, dans le seed, les **cas limites** dont les tests auront
besoin : un produit juste au-dessus d'un budget rond, une combinaison de critères
sans aucun résultat, deux produits quasi identiques à départager.

**Porte de sortie :** `make seed` remplit la base avec 150-200 produits validés ;
un rapport imprime le taux de remplissage par attribut et par catégorie ; aucun
produit en base n'a un attribut hors de sa plage déclarée.

---

### Étape 6 — Moteur de matching

Le cœur du projet, et la seule partie entièrement déterministe.

1. **Filtres durs** → SQL `WHERE` : catégorie, budget, contraintes bloquantes.
2. **Scoring** → Python sur les résultats : chaque critère souple produit un
   sous-score 0-1, pondéré par l'importance déclarée.
3. **Trace d'explication** → pour chaque produit retenu, la liste
   `{critère: matché | partiel | raté, écart}`. C'est cette trace, pas le LLM,
   qui portera le « pourquoi » affiché au client.
4. **Séparation budget** → `produits` et `au_dessus_du_budget` en deux ensembles
   distincts, avec l'écart exact.
5. **Cas zéro résultat** → identifier le critère le plus coûteux (celui dont le
   relâchement ouvrirait le plus de produits) et le rendre dans la réponse.

**Porte de sortie :** la suite `tests/matching/` couvre filtre dur, scoring,
classement, zone de tolérance budget, zéro résultat et suggestion
d'assouplissement — et tourne **sans aucune clé API**, en moins de deux secondes.

C'est le critère d'acceptation nº5, franchi ici.

---

### Étape 7 — Couche outils et invariants

Les quatre outils du §3.7, chacun comme une fonction Python testable, avec leur
schéma JSON d'entrée.

C'est ici que vivent les garanties :

- `search_products` **clampe** les critères du LLM contre `session.validated_criteria` ;
- `probe_catalog` ne peut structurellement pas rendre de produit ;
- les critères de session sont dérivés des arguments d'appel et fusionnés par le
  code, avec gestion explicite des contradictions et des retraits.

**Porte de sortie :** des tests qui appellent les outils avec des arguments
**hostiles** — budget élargi, catégorie inexistante, critères contradictoires —
et vérifient qu'aucun ne franchit l'invariant. Toujours zéro appel API.

C'est le critère nº2 franchi au niveau structurel, avant même qu'un LLM existe
dans le projet.

---

### Étape 8 — Boucle agent et prompt système v1

Boucle de tool use : appel, exécution des outils, réinjection, jusqu'à réponse
texte ou `max_iterations`. Prompt système en fichier versionné. Journalisation
structurée de chaque tour — message, appels d'outils, arguments, résultats,
sortie.

La règle de dialogue centrale du prompt : *ne jamais demander sans donner
quelque chose en retour.*

**Porte de sortie :** une conversation manuelle en console, de bout en bout, qui
aboutit à une recommandation de produits réels. Pas encore de qualité garantie —
juste la preuve que la boucle tourne et que les logs sont lisibles.

---

### Étape 9 — Validateur anti-hallucination

Parsing de chaque sortie texte : extraction des IDs produits, des prix, des
valeurs chiffrées. Vérification contre le contexte réellement fourni à l'appel.
Écart → une régénération avec le grief en message ; second échec → repli sur
template.

**Porte de sortie :** des fixtures de sorties LLM **délibérément piégeuses** —
prix modifié de 10 €, ID inexistant, produit entièrement inventé, spec
transformée — toutes détectées. Et le repli template produit une réponse
correcte, même si sèche.

C'est le critère nº1 franchi au niveau du mécanisme.

---

### Étape 10 — API et streaming

FastAPI, endpoint de chat en SSE, événements typés du §3.12, persistance de
session en Postgres, configuration entièrement par variables d'environnement.

**Porte de sortie :** une conversation complète menée en `curl`, avec les
événements typés visibles dans le flux ; le serveur redémarré en cours de
conversation, qui reprend la session sans rien perdre.

---

### Étape 11 — Interface web

Chat, panneau latéral « ce que j'ai compris » alimenté par `criteria_updated`,
cartes produits alimentées par `products_found`, indicateur d'activité sur
`catalog_probe`.

**Porte de sortie :** une conversation complète dans le navigateur, où l'on voit
les critères se remplir au fil du dialogue.

C'est le moment où le projet devient démontrable. C'est aussi, en portfolio, ce
qui fait le plus d'effet pour le moins d'effort : le panneau latéral rend
l'architecture visible.

---

### Étape 12 — Harnais d'éval

1. Enregistrement en cassettes (hash du prompt stocké dedans : le test échoue si
   le prompt a changé sans régénération).
2. 8 à 10 scénarios écrits, dont obligatoirement : budget serré, budget absent,
   besoin très flou, besoin sur-spécifié sans solution, changement d'avis en
   cours de route, demande de comparaison entre deux propositions, catégorie hors
   catalogue, et le cas zéro résultat.
3. Métriques calculées automatiquement : hallucinations, violations budget,
   questions avant première recommandation, présence du produit attendu en top 3.
4. 2-3 scénarios avec client simulé par Haiku, lancés à la main.

**Porte de sortie :** un tableau de métriques généré par commande, où les
critères 1, 2 et 6 sont à zéro violation.

---

### Étape 13 — Itération sur les prompts

C'est ici que le produit devient bon, et c'est l'étape qu'on est tenté de sauter.

Le harnais existe désormais : chaque modification de prompt se mesure. Faire
varier le prompt système, comparer les tableaux, versionner ce qui gagne. Viser
en priorité la métrique nº3 — le délai avant première valeur — qui est ce que
ressent un vrai utilisateur.

**Porte de sortie :** au moins deux versions de prompt comparées chiffres en
main, et la trace de cette comparaison conservée dans le dépôt.

---

### Étape 14 — README et finition

Installation, lancement, exemples d'usage, tableau de métriques, schéma
d'architecture, et une section honnête sur ce qui est réel et ce qui est dérivé
dans le catalogue.

**Porte de sortie :** un `git clone` suivi de la procédure du README, sur une
machine vierge, aboutit à une conversation fonctionnelle.

C'est la seule vérification qui compte pour un portfolio.

---

### Étape 15 — Extensions, si l'envie est là

- Recherche hybride avec `pgvector`, en respectant la règle « départager, jamais
  justifier ».
- Variante machine à états, comparée à l'agent sur les mêmes scénarios et le même
  tableau de métriques. Ce serait le contenu le plus intéressant du projet.

---

## 6. Ordre non négociable

**Moteur de matching → couche outils → boucle agent.**

Le moteur définit la forme des critères, qui définit la signature des outils, qui
définit ce que l'agent peut faire. Prendre l'ordre inverse produit une couche LLM
qui extrait des critères que le moteur ne sait pas consommer — et il faut tout
réécrire.

De même : **le validateur avant l'API, l'API avant le front, le harnais d'éval
avant l'itération sur les prompts.** Sans harnais, régler un prompt revient à
juger à l'oreille sur trois conversations, et à faire régresser ce qui marchait.

---

## 7. Risques identifiés

| Risque | Gravité | Atténuation |
|---|---|---|
| **Le dataset n'a pas d'attributs exploitables sur 5-6 catégories** | Élevée — tout le projet en dépend | Porte de sortie explicite à l'étape 3, avant tout code de pipeline. Repli : 3 catégories, ou specs complétées et documentées |
| **L'agent dérive vers l'interrogatoire ou la recommandation prématurée** | Moyenne — c'est la qualité perçue | Règle « donner avant de demander » dans le prompt, métrique suivie, itération outillée à l'étape 13 |
| **Les cassettes deviennent obsolètes silencieusement** | Moyenne — les tests passent à côté de la réalité | Hash du prompt stocké dans la cassette ; le test échoue si le prompt a changé |
| **Le nettoyage du dataset déborde** | Moyenne — dérive du projet | Geler le périmètre à ce qui est propre plutôt que poursuivre l'exhaustivité |
| **Latence perçue de la boucle multi-outils** | Faible | Streaming des événements typés dès le premier appel d'outil |

---

## 8. Hors périmètre

Paiement, compte utilisateur, multilingue, gestion de panier, historique
inter-sessions.
