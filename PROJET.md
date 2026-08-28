# rAiyon — Assistant conseil produit en temps réel

Document de cadrage. Il consigne les décisions d'architecture, **les alternatives
écartées et pourquoi**. Il fait foi : toute décision qui le contredit doit être
discutée et amender ce fichier.

Statut : étapes 1 à 5 franchies. Source, domaine et 6 catégories arrêtés
(3.4, 3.4bis), schéma d'attributs écrit et validé, schéma SQL migré et testé,
catalogue de 1 026 produits normalisé, committé et chargé en base.
✅ La passe LLM du catalogue a été **supprimée après mesure** (§3.4ter, réécrite) :
le catalogue reste en anglais, le français se produit dans la réponse à l'étape 8.
Aucun octet de la base ne vient d'un modèle, et aucune clé API n'est nécessaire
avant l'étape 8.
Étape suivante — 6, moteur de matching.
Dernière révision : 2026-08-28.

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

### 3.1 — Catalogue : 6 catégories, ~150-200 produits chacune

**Retenu.** Un périmètre d'environ **1 000 produits sur 6 catégories**.

**Condition attachée à ce choix :** chaque catégorie doit disposer d'au moins
**5 attributs discriminants** renseignés à **≥ 80 %** (au-delà du prix). Sans
cela, le moteur n'a rien pour départager et toute recommandation devient
triviale. Condition vérifiée à l'étape 3, avant écriture du pipeline. Le décompte
obéit à la règle 3.4quater.

**Volume révisé à la hausse après l'étape 3.** Le cadrage initial prévoyait ~30
produits par catégorie. À ce volume, un filtre dur réaliste — « SSD M.2 de 2 To
sous 150 $ » — renvoie zéro résultat la plupart du temps : le cas d'échec
deviendrait le cas courant au lieu d'être un cas limite, et le classement n'aurait
presque jamais de quoi s'exercer.

**Objection à cette révision, et sa réponse.** Un catalogue de 30 produits par
catégorie se relit intégralement à l'œil, ce qui rassure sur le critère nº1.
Mais la vérification anti-hallucination ne repose pas sur une relecture humaine :
elle repose sur le **validateur programmatique** du §3.11, qui compare les IDs et
les valeurs citées au contexte réellement fourni. Ce mécanisme est indifférent à
la taille du catalogue. La relisibilité n'était donc pas une garantie, seulement
un confort.

**Alternative écartée — 1 à 2 catégories profondes.** Matching plus riche et
schéma plus simple, mais ne démontre pas que l'architecture absorbe
l'hétérogénéité des attributs, qui est le vrai problème de modélisation ici.

**Alternative écartée — charger les 9 687 produits à prix.** Aucun biais
d'échantillonnage à justifier, mais un seed committé nettement plus lourd, et
surtout les cas limites nécessaires aux tests (produit juste au-dessus d'un
budget rond, deux produits quasi identiques) ne seraient plus **placés** : il
faudrait les trouver.

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

### 3.3bis — Indexation des `specs` : un GIN, et un balayage séquentiel assumé

**Retenu.** Un seul index, GIN `jsonb_path_ops`, sur la colonne `specs`. Aucun
index d'expression.

**Ce que cet index fait :** il sert l'égalité et la containment (`specs @> '…'`).
**Ce qu'il ne fait pas, et il faut le dire :** il ne sert **pas** les comparaisons
de plage, qui sont pourtant la forme la plus fréquente des filtres durs du domaine
— « au moins 2 To », « 144 Hz minimum », « 12 Go de VRAM ». `(specs->>'capacity')::int
>= 2000` provoque un **balayage séquentiel** de la table.

**Pourquoi c'est acceptable ici :** à ~1 000 produits (3.1), un balayage séquentiel
coûte quelques millisecondes, soit trois ordres de grandeur sous la latence du
moindre appel LLM. Le coût est réel mais invisible.

**Ce que ce choix ne démontre pas.** La justification de Postgres en 3.2 invoquait
l'indexation du JSONB. Sur les filtres de plage, ce schéma ne la démontre pas : il
tient par la petite taille du catalogue, pas par l'index. C'est une limite du
livrable, pas un détail d'implémentation, et elle est écrite en commentaire dans la
migration pour qu'on ne la redécouvre pas au mauvais moment.

**Alternative écartée — index d'expression B-tree sur chaque champ numérique
filtré** (`((specs->>'capacity')::int)`). C'est l'échappatoire connue si le volume
changeait d'ordre de grandeur. Écartée maintenant parce qu'elle demande un index par
champ **et** par catégorie — une vingtaine d'index pour une table de 1 000 lignes,
qu'il faudrait maintenir en cohérence avec `schema_attributs.md` à chaque évolution.
Optimiser avant d'avoir mesuré un problème coûterait plus qu'il ne rapporterait.

**Alternative écartée — promouvoir les champs de plage en colonnes typées.** Elle
supprimerait le problème, mais ramènerait la table de colonnes fixes que 3.3 a
écartée, avec ses NULL et sa migration par catégorie.

### 3.4 — Données : `docyx/pc-part-dataset`, déjà structuré

**Retenu.** [`docyx/pc-part-dataset`](https://github.com/docyx/pc-part-dataset) —
66 778 produits, licence MIT, JSON/JSONL/CSV versionnés dans le dépôt, snapshot
de juillet 2025, scrapé de PCPartPicker. Chaque produit porte un `price` en USD.

Ce qui décide : **les attributs sont déjà typés, nommés et unitaires**
(`refresh_rate` en Hz, `response_time` en ms, `capacity` en GB,
`frequency_response` en `[min, max]` kHz, `tdp` en W). Le
[schéma complet](https://github.com/docyx/pc-part-dataset/blob/main/API.md) est
publié et lisible avant tout téléchargement. Il n'y a pas d'extraction
d'attributs à faire : il y a une normalisation déterministe à écrire.

**Alternatives écartées — les trois candidats Amazon**
([Datafiniti](https://www.kaggle.com/datasets/datafiniti/electronic-products-prices),
[Amazon-Reviews-2023](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023),
[iarbel/amazon-product-data-filter](https://huggingface.co/datasets/iarbel/amazon-product-data-filter)).
Toutes trois échouent pour la même raison, celle qui était déjà identifiée en
3.4bis : les « specs » y sont du texte marketing en champ libre. Le pipeline LLM
n'y aurait pas *normalisé* une structure, il l'aurait **créée** — donc inventée.
Incompatible avec l'invariant central du projet.

**Alternative écartée — [Open Icecat](https://icecat.com/structured-data-content-users/).**
18 M de fiches, specs validées par les marques, 70+ langues dont le français :
la meilleure qualité de données en absolu, et elle réglait le problème de
traduction. Écartée sur un point unique et rédhibitoire — **Icecat ne porte pas
de prix** (c'est de la syndication de contenu, les prix viennent des revendeurs).
Un moteur à contrainte budgétaire sans prix n'existe pas.

**Alternatives écartées, plus brièvement.**
[Best Buy open-data-set](https://github.com/BestBuyAPIs/open-data-set) (~50 k
produits avec prix, mais quasi aucun attribut technique) ;
[Amazon Berkeley Objects](https://registry.opendata.aws/amazon-berkeley-objects/)
(18 attributs, mais génériques — couleur, matériau, dimensions — donc non
discriminants) ; les scrapes GSMArena (attributs excellents, mais mono-catégorie).

**Alternative écartée — catalogue entièrement généré.** Beaucoup plus rapide, et
permet de placer volontairement les cas limites nécessaires aux tests. Mais des
prix inventés affaiblissent un projet dont l'argument central est précisément de
ne rien inventer.

**Conséquences assumées, à documenter dans le README :**

1. Le dépôt est MIT, mais les données sous-jacentes sont **scrapées de
   PCPartPicker**. Acceptable pour un projet de portfolio, à condition de le dire.
2. Les prix sont en **USD et figés à juillet 2025**. Le catalogue est un snapshot,
   pas un flux.
3. Il n'y a **ni description produit, ni disponibilité**. La disponibilité sort du
   modèle : aucune source ne la porte, on ne l'invente pas. L'absence de
   description est en réalité favorable — la justification devra se construire sur
   les attributs, jamais sur de la copie marketing.
4. Certains champs sont des unions hétérogènes (`number | [number, number]`,
   booléens, chaînes). La normalisation est réelle, mais **déterministe et
   testable** : aucun LLM n'y intervient.

### 3.4bis — Domaine retenu : composants et périphériques PC

Le choix du dataset entraîne le domaine. On passe d'« électronique grand public »
à **composants PC** : le scénario de conseil devient « aide-moi à choisir un
écran / un SSD / une carte graphique ». C'est un domaine que le porteur du projet
maîtrise, ce qui rend la relecture des recommandations possible — critère décisif
sur un projet dont la qualité perçue dépend de la pertinence du conseil.

**Six catégories retenues**, arrêtées après mesure du remplissage réel à
l'étape 3 (et non plus d'après la documentation de la source) :

| Catégorie | Produits à prix | Attributs discriminants ≥ 80 % |
| --- | --- | --- |
| `memory` | 2 907 | 6 |
| `internal-hard-drive` | 2 103 | 6 |
| `monitor` | 1 367 | 6 |
| `video-card` | 1 275 | 6 |
| `keyboard` | 824 | 4 → **retirée** |
| `headphones` | 664 | 6 |
| `cpu` | 547 | 5 |

**Le seuil avait déjà été abaissé de 6 à 5 avant mesure**, pour récupérer casque
et clavier : les périphériques ont réellement moins d'axes de choix, et maintenir
6 revenait à appliquer un critère numérique contre la réalité du domaine.

**`keyboard` est retirée.** Elle plafonne à 4 attributs : `switches` (54,0 %) et
`backlit` (56,3 %) sont trop lacunaires. Les absences ne sont pourtant pas
aléatoires — elles se concentrent sur les styles `Standard`, `Slim` et
`Ergonomic`, c'est-à-dire des claviers à membrane non rétroéclairés. Lire ces
`null` comme « membrane » et « aucun » repêcherait la catégorie, et l'hypothèse
est crédible. **Elle est refusée quand même** : la source ne le dit pas, et un
projet dont l'argument central est de ne rien inventer ne peut pas commencer par
combler ses propres trous. Voir 3.4quater.

**`cpu` est repêchée** par la marque, attribut dérivé de façon déterministe. Elle
n'échouait que d'un attribut, et pour une raison de documentation : `smt` est
promis par `API.md` et **n'existe dans aucun des 1 413 CPU**. Le décompte initial
de cette section reposait sur la doc de la source, pas sur ses données.

**Alternative écartée — outillage électroportatif.** Attributs nettement plus
discriminants et chiffrés (tension, couple, autonomie), donc un meilleur terrain
de jeu pour le moteur de matching. Écartée sur le volume de données disponible.

**Conséquence assumée :** seuls **24 % des produits de la source portent un
prix**. Le catalogue exploitable tombe à 9 687 produits, ce qui reste très
au-dessus des ~1 000 visés en 3.1, mais la sélection n'est pas neutre — les
produits sans prix sont vraisemblablement les moins distribués. À documenter.

### 3.4quater — Règle de comptage des attributs

Une grandeur **dérivée de façon déterministe** de champs présents compte comme un
attribut à part entière. Un **comblement d'absence** ne compte pas, et n'est pas
autorisé.

| Cas | Nature | Compte ? |
| --- | --- | --- |
| `price_per_gb` = `price / capacity` | fonction de deux champs renseignés | ✅ |
| `marque` = premier mot de `name` | parsing déterministe, couverture 100 % | ✅ |
| `switches = null` → « membrane » | hypothèse comblant un trou | ❌ |

**Pourquoi cette règle existe.** Le verdict brut de l'étape 3 était incohérent :
`internal-hard-drive` n'ouvrait que grâce à `price_per_gb`, une grandeur dérivée,
pendant qu'on envisageait de refuser à `cpu` un repêchage par la marque, dérivée
elle aussi. On ne peut pas compter l'une et refuser l'autre. La ligne de partage
qui tient n'est pas « champ source contre champ dérivé », mais **calcul contre
supposition** : le premier ne crée aucune information, le second en invente.

**Conséquence directe :** la marque n'existe dans **aucune** catégorie de la
source — elle n'est présente que dans le premier mot de `name`. Son extraction
est donc une transformation à écrire et à tester (étape 5), appliquée
uniformément aux 6 catégories. C'est aussi un filtre dur que les utilisateurs
expriment réellement (« je veux du Intel »), pas un artifice de décompte.

**Fragilité à assumer, et elle est réelle :** cette règle est écrite **après**
avoir vu les résultats de la mesure. Trois éléments la distinguent d'un
déplacement de poteaux de but, et le README doit les porter : elle s'énonce
comme un principe général et non comme une exception ; elle s'applique aux 6
catégories, pas à celle qu'elle sauve ; et elle **continue d'en fermer une**.

### 3.4ter — Langue du catalogue : anglais en base, français à la réponse

**Décision (renversée à l'étape 5, après mesure).** Le catalogue reste **en
anglais**, tel que la source le donne. Aucune traduction n'est stockée. La jonction
avec le français se fait **au moment de répondre au client**, dans la phrase de
recommandation de l'étape 8 — jamais dans la base.

La décision initiale était l'inverse : une passe LLM réduite produisait deux champs,
`nom_fr` (traduction du nom court) et `description` (résumé d'usage), figés dans le
seed. Elle a été écrite, testée, exécutée sur 40 produits — et c'est cet essai qui l'a
invalidée.

**Ce que la mesure a dit.** Sur les 38 traductions obtenues, `nom_fr` **égalait le nom
source 38 fois sur 38**. Vérification faite ensuite sur les **1 026 noms du seed, sans
aucun appel API** : aucune catégorie ne porte de contenu traduisible.

```
Asus TUF Gaming VG279QM1A     Seagate IronWolf Pro NAS
G.Skill Trident Z5 RGB 48 GB  ASRock Phantom Gaming OC
```

Marque + référence commerciale. « TUF Gaming », « Trident Z5 », « IronWolf Pro » sont
des noms de gamme déposés : les traduire casserait l'identité du produit, et un client
qui cherche « IronWolf » ne retrouverait pas ce qu'on lui a montré.

**Pourquoi la décision initiale était mal fondée**, et c'est le point à retenir : elle
a été prise **avant d'avoir regardé les noms**. Sur l'idée qu'on se faisait des données
— « les données sont en anglais, donc il faut traduire » — et non sur les données.
C'est le **même mécanisme que le `smt` de l'étape 3** (un attribut que la
documentation promettait, présent dans zéro enregistrement) et que le `temperature=0`
de l'étape 5 (un paramètre supposé disponible, retiré du SDK). Trois fois, la mesure a
contredit une évidence, et trois fois l'évidence avait été écrite en premier.

**Le second champ tombe pour une autre raison : la redondance.** L'agent de l'étape 8
reçoit les produits retenus par le moteur et leur trace d'explication, et **écrit déjà
une phrase française à leur sujet**. Un `description` pré-généré fait le même travail,
un an à l'avance et figé, sur un besoin client qu'il ne connaît pas. Ce n'est pas une
sécurité, c'est une duplication — payée en jetons, en cache à maintenir et en champ
généré dans la base.

**Ce que le projet y gagne**, et qui vaut mieux que ce qu'il perd :

- **Aucun octet de la base ne vient d'un modèle.** La promesse passe de « le LLM ne
  produit jamais un fait » à quelque chose de **vérifiable en lisant le schéma** :
  sept colonnes de contenu et deux horodatages, aucune sortie de génération. C'est
  l'argument central du projet, et il devient constatable au lieu d'être affirmé.
- **L'étape 5 devient entièrement déterministe.** Aucune clé API n'est nécessaire
  avant l'étape 8 — ni pour construire le catalogue, ni pour le charger, ni pour le
  tester. Le projet s'installe et se vérifie sans compte chez un fournisseur.
- **Le multilingue devient une phrase du prompt système**, pas 1 026 générations par
  langue. Ajouter l'espagnol coûte une ligne, pas un budget.
- **Le piège tendu à l'étape 6 disparaît.** Il n'y a plus de champ texte généré dont
  il faudrait se rappeler qu'il ne doit ni filtrer ni scorer. Une règle qu'on n'a plus
  besoin d'énoncer est plus solide que la même règle écrite en commentaire.

**Le français qui reste est dérivé, donc déterministe.** `LIBELLES_CATEGORIE`
(`schemas.py`) associe les 6 catégories à leur nom commun : `cpu` → « processeur »,
`monitor` → « écran », `internal-hard-drive` → « stockage interne », `memory` →
« mémoire vive », `video-card` → « carte graphique », `headphones` → « casque ». Le
nom générique français qu'on voulait obtenir d'un modèle **se déduit de la catégorie**,
il ne dépend d'aucun produit en particulier. C'est de la donnée, pas du rendu : la mise
en forme d'affichage est l'affaire de l'étape 11.

**Alternative écartée — pré-générer les descriptions et les stocker** (la décision
initiale). Elle duplique le travail de l'étape 8, coûte une génération par produit
**et par langue**, et fait entrer un champ généré dans une base dont l'argument est de
n'en contenir aucun. Le seul avantage qu'elle gardait — un texte relu une fois pour
toutes — est précisément ce qui est perdu ci-dessous, et il ne suffit pas.

**Alternative écartée — traduire quand même les noms.** Écartée par la mesure, pas par
principe : il n'y a rien à traduire, et forcer la traduction d'une référence
commerciale fabriquerait un produit qui n'existe pas.

**Ce qui est perdu, et il faut le dire.** La relecture par échantillon que promettait
la version précédente de cette section. Un texte figé se relit une fois ; un texte
produit au runtime, jamais. Le garde-fou devient le **validateur de l'étape 9**, qui
voit passer chaque réponse — ce qui était de toute façon déjà le cas pour la phrase de
recommandation, jamais couverte par la relecture d'échantillon.

**Ce que la décision achète à l'étape 9**, en revanche : un nom de produit cité par
l'agent devient vérifiable **au caractère près** contre la base. Avec un `nom_fr`, il
aurait fallu comparer à une traduction, c'est-à-dire à un texte lui-même généré.

**Une limite à ne pas maquiller : les prix restent en USD, figés à juillet 2025.** La
langue devient gratuite, la devise non. Fabriquer un taux de change serait inventer un
fait (§2). C'est écrit dans le README, ce n'est pas laissé à deviner.

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
| ~~Normalisation du dataset~~ | ~~Haiku~~ | **Sans objet depuis l'étape 5** — voir ci-dessous |
| Client simulé dans les évals | Haiku | Génération de tours de parole, coût dominant en volume |

Modèles configurables par variable d'environnement. Prompt caching activé sur le
prompt système, qui est long et stable.

**La normalisation du dataset n'appelle plus aucun modèle.** La passe LLM de l'étape 5
a été supprimée (§3.4ter) : le catalogue est produit par du code déterministe, de bout
en bout. `model_extraction` **reste configuré** — la constante existe, elle est typée
et testée — mais plus rien ne la lit à cette étape. La ligne est barrée plutôt
qu'effacée : c'est une décision renversée, pas une décision qui n'a jamais eu lieu.

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

### Étape 2 — Socle du dépôt ✅

Structure de projet, `pyproject.toml`, `.env.example`, `docker-compose.yml` avec
Postgres, `ruff` et `pytest` configurés, un test bidon qui passe.

**Porte de sortie :** `docker-compose up` démarre Postgres, `pytest` tourne vert
sur un dépôt vide. **Franchie.**

Cette étape paraît accessoire. Elle évite de bricoler la configuration au milieu
d'un travail de fond, ce qui est là qu'on introduit des clés en dur.

**Décisions prises pendant l'exécution**, qui n'étaient pas dans le cadrage :

- **uv** comme gestionnaire de dépendances et de version Python, `uv.lock`
  commité. Alternative écartée — Poetry (plus répandu, mais plus lent et sans
  gestion du runtime Python) ; pip + requirements (aucun prérequis, mais pas de
  résolution reproductible, ce qui contredit l'argument de rigueur du projet).
- **Layout `src/`** : le paquet n'est importable qu'installé, donc un import qui
  marche depuis la racine mais casse ailleurs est impossible.
- **Contrôle explicite des noms de variables d'environnement**
  (`verifier_cles_inconnues`). `RAIYON_BUDGET_TOLERANC=0.4` — un `E` manquant —
  laissait sinon la tolérance à 0.15 sans le moindre signal. Le réflexe
  `extra="forbid"` de Pydantic a été essayé et **ne fonctionne pas** ici :
  combiné à `env_file` et à un `validation_alias`, il fait échouer la validation
  de tous les champs. D'où le contrôle écrit à la main, avec suggestion du nom
  le plus proche.
- **Marqueurs pytest `integration` et `llm` désélectionnés par défaut.** La suite
  par défaut ne touche donc ni Postgres ni l'API, ce qui est le critère
  d'acceptation nº5 posé dès l'étape 2 plutôt qu'à l'étape 6.
- **Plugin mypy de Pydantic activé tout de suite**, alors qu'il ne sert encore à
  rien : l'ajouter après l'étape 4 ferait apparaître des dizaines d'erreurs d'un
  coup sur les modèles.

---

### Étape 3 — Exploration du dataset et schéma d'attributs ✅

**C'était l'étape la plus risquée du projet.** Tout ce qui suit en dépendait.

Le choix de la source étant tranché (3.4), l'étape n'a pas été une exploration à
l'aveugle mais **une vérification** : le schéma promettait des attributs, la
mesure a établi lesquels sont réellement renseignés.

**Porte de sortie :** `catalogue/schema_attributs.md`, où chaque catégorie
retenue expose au moins 5 attributs discriminants à **≥ 80 % de remplissage**,
plus 20 produits réels par catégorie. Accompagnée de
`catalogue/rapport_exploration.md`, la mesure brute. **Franchie**, avec 6
catégories sur 7 (voir 3.4bis).

**Ce que l'étape a appris, et qui n'était pas prévu :**

- **Seuls 24 % des produits portent un prix.** Le volume exploitable n'est pas
  66 778 mais 9 687. Sans effet sur le projet, mais ce chiffre invalidait toute
  mesure faite sur le dataset entier.
- **`smt` n'existe dans aucun CPU** alors que `API.md` le documente. La leçon
  vaut au-delà de ce champ : le décompte d'attributs de 3.4bis avait été fait sur
  la documentation de la source, ce qui est précisément l'erreur que cette étape
  devait attraper.
- **`frequency_response` mélange deux unités dans un même champ** (Hz puis kHz).
  Les 32 « inversions » apparentes min > max viennent de là. Un correctif
  min/max détruirait la donnée : la désambiguïsation se fait par ordre de
  grandeur (étape 5).
- **`name` n'est pas une clé** — 5 390 noms pour 9 687 produits — et les doublons
  n'ont pas la même nature selon la catégorie : sur `memory`, 346 noms dupliqués
  et **zéro** aux attributs identiques (ce sont des variantes réelles) ; sur
  `cpu`, 51 dupliqués **tous** identiques (ce sont des redondances).
- **Aucune catégorie ne porte de champ marque.** D'où 3.4quater.

**Décisions d'arbitrage prises à la sortie de l'étape :** règle de comptage des
attributs (3.4quater), retrait de `keyboard` et repêchage de `cpu` (3.4bis),
volume du catalogue relevé à ~1 000 produits (3.1).

---

### Étape 4 — Schéma SQL et migrations ✅

Modèles SQLAlchemy (`produits`, `sessions`, `tours_conversation`), modèles Pydantic
miroirs, migration Alembic initiale `0001_schema_initial`, index sur
`(categorie, prix_usd)`, sur `marque` et index GIN sur `specs`.

Aucun produit du dataset n'est entré en base : c'est le travail de l'étape 5. Seules
les fixtures de test insèrent des lignes.

**Amendement de l'étape 5 — deux colonnes de `0001` ont été retirées.** Le schéma de
cette étape créait `nom_fr text NULL` (« rempli par la passe LLM de l'étape 5 ») et
`description text NULL` (« résumé d'usage généré par LLM »). La passe en question a été
supprimée après mesure, et la migration **`0002_catalogue_sans_champs_generes`** a
retiré les deux colonnes — voir §3.4ter pour la décision et le chiffre qui l'a
provoquée. La ligne n'est pas effacée d'ici : le schéma de l'étape 4 est bien celui-là,
et l'historique des décisions fait partie du produit.

**Porte de sortie :** `make check` vert (37 tests unitaires) **et** `make test-int`
vert (11 tests d'intégration) sur une base créée depuis zéro. **Franchie.**

**Ce que l'étape a tranché**, avec l'alternative écartée à chaque fois :

- **A — Indexation : GIN seul, balayage séquentiel assumé sur les plages.** Décision
  écrite en 3.3bis, avec sa limite et son échappatoire. Alternative écartée : une
  vingtaine d'index d'expression pour une table de 1 000 lignes.
- **B — Base de test : base dédiée `raiyon_test` sur le Postgres de `docker-compose`.**
  Créée, migrée et supprimée par la suite ; la base de travail n'est jamais touchée.
  Alternative écartée — `testcontainers` : la même garantie, contre une dépendance de
  plus et une dizaine de secondes par exécution, alors que le conteneur est déjà là.
- **C — Moteur SQLAlchemy synchrone.** Le moteur de matching et le pipeline restent
  des fonctions pures, testables sans boucle asyncio — ce qui est la condition du
  critère d'acceptation nº5. Alternative écartée — un engine asyncio : il aurait
  imposé `async def` jusque dans les tests du moteur, pour un gain nul à ce volume.
  L'API enveloppera ses appels base dans `asyncio.to_thread` à l'étape 10.
- **D — Validation par union discriminée sur `categorie`, `extra="forbid"`.** Un
  produit `cpu` porteur d'un `screen_size` est rejeté avant SQL ; c'est ce qui donne
  un sens à « rien n'entre en base sans avoir été typé ». La catégorie n'est **pas**
  dupliquée dans le JSONB : elle y est injectée juste avant la discrimination et
  retirée juste avant l'écriture, pour la même raison qu'en 3.10 — deux copies
  peuvent diverger. Alternative écartée — un modèle unique à champs optionnels : il
  aurait accepté n'importe quel attribut sur n'importe quelle catégorie.
- **E — Prix en USD, sans conversion.** La colonne s'appelle `prix_usd` : l'unité est
  dans le nom pour qu'aucune couche supérieure ne puisse l'oublier. Alternative
  écartée — stocker un prix en euros : fabriquer un taux de change serait inventer un
  fait, ce que §2 interdit.
- **F — Pas de stock chiffré.** `disponible boolean not null default true`. La source
  ne porte aucune quantité ; un entier dirait ce qu'on ne sait pas.
- **Règle de nullabilité, sans exception : obligatoire si et seulement si le taux de
  remplissage mesuré à l'étape 3 vaut 100 %.** `internal-hard-drive.type` est à
  99,6 %, il est donc optionnel au niveau du modèle, bien qu'il soit le premier
  arbitrage du domaine. Écarter les 0,4 % restants est une décision de pipeline
  (étape 5) ; la prendre dans le schéma reviendrait à combler une absence (3.4quater).
- **Bornes numériques physiquement plausibles, pas mesurées.** Un produit qui bat un
  record ne doit pas être rejeté par le schéma. La plage observée est en commentaire
  à côté de chaque borne, avec son unité.

**Ce que l'étape a appris, et qui n'était pas prévu :**

- **La cible `numeric(4,2)` de `schema_attributs.md` aurait rejeté trois produits
  réels.** `cpu.core_clock` porte `3.333` GHz sur deux processeurs, `video-card.memory`
  porte `0.875` Go sur une carte. Ces valeurs vivant dans le JSONB, aucune colonne
  `numeric` ne les arrondit : la contrainte Pydantic était le seul garde-fou, et
  recopier le type cible sans vérifier aurait fait échouer le pipeline sur des données
  valides. Les précisions ont été relevées à trois décimales après mesure. **Même
  mécanisme que le `smt` de l'étape 3** — une valeur documentée, jamais vérifiée.
- **Les `Decimal` transitent en chaînes dans le JSONB.** `model_dump(mode="json")` les
  sérialise ainsi, et c'est le bon comportement : un flottant JSON ne rend pas `0.087`
  à l'identique. Les filtres de plage n'y perdent rien (`specs->>'…'` rend du texte
  dans les deux cas), mais une containment `@>` sur une valeur numérique doit comparer
  une **chaîne** — piège à connaître pour l'étape 6.
- **La fixture `isolated_env` de l'étape 2 rendait la base introuvable.** Elle est
  `autouse`, retire les variables `RAIYON_*` et déplace le répertoire courant, donc
  `.env` n'existe plus pour les tests d'intégration. L'URL est désormais lue à
  l'import du `conftest.py` d'intégration, avant qu'aucune fixture n'ait pu s'exécuter
  — plutôt que réinjectée après coup, ce qui aurait fait dépendre ces tests de l'ordre
  des fixtures.

---

### Étape 5 — Pipeline de normalisation des données ✅

**Une seule passe produit le catalogue, et elle est déterministe.**

**Normalisation sans LLM.** Lecture du dataset brut → filtrage sur les 6 catégories et
sur les produits à prix → aplatissement des unions hétérogènes → conversion d'unités →
déduplication → validation Pydantic. Tous les **faits** — prix, marque, référence,
attributs — sortent de cette passe et d'elle seule. Le chargement en base (passe C) ne
fait que relire, revalider et insérer.

⚠️ **Le périmètre livré a changé en cours d'étape.** Une **passe B** appelait un modèle
pour produire `nom_fr` et un résumé d'usage (3.4ter, version initiale). Elle a été
écrite, testée avec un faux client, exécutée sur 40 produits — puis **supprimée**, avec
ses deux colonnes, son cache, son prompt et sa cible `make`. Ce que l'essai a mesuré est
en §3.4ter ; ce qu'il en reste ici est un catalogue dont **aucun octet ne vient d'un
modèle de langage**. Les passes gardent leurs lettres d'origine (A et C) : la place
vide de la B est une trace, pas un oubli.

**Cinq transformations identifiées à l'étape 3, chacune à tester :**

- **`marque`** : premier mot de `name`, sur les 6 catégories (3.4quater).
- **`internal-hard-drive.type`** : `"SSD"` ou un entier de tours/minute → deux
  colonnes, `type` ∈ {`SSD`, `HDD`} et `rpm` nullable.
- **`form_factor`** : `2.5`/`3.5` en nombre ou `"M.2-2280"` en chaîne → une seule
  énumération textuelle.
- **`memory.speed` et `memory.modules`** : tuples → `ddr_generation` /
  `frequence_mhz` et `nb_modules` / `taille_module_gb`, plus
  `capacite_totale_gb` dérivée.
- **`headphones.frequency_response`** : unités mélangées Hz/kHz, désambiguïsées
  **par ordre de grandeur**. Les 32 cas d'inversion apparente min > max servent de
  cas de test. Un correctif par `min`/`max` est interdit : il détruirait la donnée.

**Déduplication — une règle unique.** Dédupliquer sur `(name + tous les attributs
hors prix)`, garder le prix le plus bas. Elle absorbe les 51 redondances `cpu` et
préserve les 346 variantes `memory` sans traitement par catégorie : la règle est
uniforme, seul son effet diffère. Clé primaire : identifiant synthétique, jamais
`name`.

Le seed est committé. Le pipeline n'est pas rejoué à l'installation.

Prévoir dès maintenant, dans le seed, les **cas limites** dont les tests auront
besoin : un produit juste au-dessus d'un budget rond, une combinaison de critères
sans aucun résultat, deux produits quasi identiques à départager.

**Porte de sortie :** `make seed` remplit la base avec ~1 000 produits validés ;
un rapport imprime le taux de remplissage par attribut et par catégorie ; aucun
produit en base n'a un attribut hors de sa plage déclarée ; **aucune clé API n'est
requise pour construire, charger ou tester le catalogue**. **Franchie** — 1 026
produits en base, `data/seed/rapport_seed.md` committé, 163 tests unitaires et
19 tests d'intégration verts.

**Deux cibles `make`, et aucune ne consomme l'API :**

| cible | passe | exige `data/raw/` | consomme l'API |
| --- | --- | --- | --- |
| `seed-build` | A — normalisation déterministe | oui (avec contrôle sha256) | **non** |
| `seed` | C — chargement en base | non | **non** |

⚠️ **Conséquence connue et non traitée.** `make seed` construit un engine, donc charge
`Settings`, où `ANTHROPIC_API_KEY` est un champ **obligatoire** depuis l'étape 2 : la
commande réclame une clé qu'elle n'utilisera jamais. Sans `.env`, elle échoue au
démarrage — comportement voulu par l'étape 2, sur une raison qui n'existe plus ici.
**Ce n'est pas corrigé maintenant** : rendre la clé optionnelle rouvrirait la décision
de l'étape 2 (« son absence fait échouer le démarrage avec un message explicite ») sur
la base d'un seul cas d'usage. L'arbitrage attend l'**étape 8**, quand un appel API
existera vraiment dans le projet. `make seed-build`, lui, ne touche pas du tout la
configuration : il passe sans `.env` et sans variable d'environnement, ce qui a été
vérifié en le lançant dans un environnement vidé. La garantie qui compte à cette étape
est ailleurs, et elle est testée : aucun module de `raiyon.catalogue` ne charge le SDK.

**Ce que l'étape a tranché**, avec l'alternative écartée à chaque fois :

- **A — Le pipeline ne corrige jamais une donnée en silence.** Trois issues pour une
  ligne, et trois seulement : elle est normalisée, elle est écartée avec un motif
  compté au rapport, ou elle fait échouer le pipeline bruyamment. Alternative écartée
  — raboter une valeur inattendue pour qu'elle « passe » : ce serait faire entrer en
  base un fait que la source ne dit pas, donc un bug plus grave que l'arrêt.
- **B — Séparation stricte des passes, devenue une garantie plus forte.** Le test
  `tests/test_isolation_passe_a.py` vérifiait que la passe A n'importait pas le SDK
  Anthropic. Depuis le retrait de la passe B, il vérifie qu'**aucun module de
  `raiyon.catalogue` ne le charge** — la liste des modules est découverte sur le
  disque, pas écrite à la main, sinon le fichier ajouté demain échapperait au contrôle.
  Il relance un interpréteur neuf par module, parce que `pytest` a déjà chargé le SDK
  au moment où le test s'exécute, et garde une **contre-épreuve** qui importe
  `anthropic` directement : sans elle, tout passerait sur un SDK absent. Alternative
  écartée — une seule passe avec un drapeau `--avec-llm` : la discipline ne serait plus
  qu'une convention, et une convention finit par céder.
- **C — L'identifiant *est* la clé de déduplication.** `id = {categorie}-{10
  hexadécimaux de sha256(clé canonique)}`, la clé canonique étant le JSON trié de
  `{nom source + specs normalisées}`. Deux lignes qui produisent le même `id` sont le
  même produit par construction. Alternative écartée — une heuristique de
  déduplication séparée du calcul de l'identifiant : il faudrait garder les deux
  cohérentes, et rien ne le garantirait.
- **D — La clé exclut le prix *et toute grandeur dérivée du prix*.** C'est le piège
  central de l'étape : `price_per_gb` est une fonction du prix, et le laisser dans la
  clé aurait annulé la déduplication sur `internal-hard-drive` et `memory`. Il est
  donc **recalculé après** la déduplication, sur le prix retenu. Alternative écartée —
  recopier la valeur source : elle correspond au prix de l'annonce d'origine, qui
  n'est plus celui du produit après qu'on a gardé le moins cher ; deux champs
  diraient des choses différentes du même fait.
- **E — Sélection stratifiée par décile de prix, à graine fixe** (`20260828`,
  constante de code). Alternative écartée — un tirage uniforme : plus simple, mais la
  carte graphique à 3 863 USD et le moniteur à 2 699 USD du seed disparaîtraient
  presque sûrement, et le moteur de l'étape 6 n'aurait plus rien pour exercer sa zone
  de tolérance budgétaire.
- **F — Le seed est committé en JSONL**, une ligne par produit, triée par `id`.
  `make seed` ne fait que le charger. Alternative écartée — un dump SQL : plus rapide
  à charger, mais le diff est illisible et l'insertion contournerait `ProduitEnBase`,
  qui est censé être la seule porte d'entrée de la table.
- **G — ~~La passe LLM est cachée et incrémentale.~~ Arbitrage annulé.** Il rendait
  effectif un garde-fou (« figée dans le seed, jamais rejouée ») d'une passe qui n'a
  pas survécu à sa propre mesure. `data/seed/traductions.json` a été supprimé avec elle.
  Conservé ici parce qu'il a été pris, et que ce qui l'a annulé — §3.4ter — se comprend
  mieux en sachant jusqu'où la décision initiale avait été menée : cachée, incrémentale,
  testée, et fausse à la racine.

**Ce que l'étape a appris, et qui n'était pas prévu :**

- **⭐ La passe LLM n'avait rien à faire.** C'est le résultat le plus utile de l'étape,
  et il a coûté 40 appels. `nom_fr` égalait le nom source **38 fois sur 38** ; le
  résumé d'usage faisait double emploi avec la phrase que l'agent de l'étape 8 écrit de
  toute façon. La décision 3.4ter avait été prise **avant d'avoir regardé les noms** —
  troisième occurrence du même mécanisme après le `smt` de l'étape 3 et le
  `temperature=0` ci-dessous : une évidence écrite avant la mesure. La différence,
  cette fois, est qu'elle a été mesurée **pendant** l'étape et non découverte après.
  Le détail est en §3.4ter ; ce qu'il faut retenir ici est la règle : **une décision
  sur les données se prend après les avoir regardées**, et 40 appels valent mieux
  qu'un an de champ généré dans une base.
- **La règle « premier mot de `name` » est fausse sur 391 produits.** Mesure faite
  avant d'écrire quoi que ce soit : `Western Digital` est la 9ᵉ marque du seed, et la
  règle brute en aurait fait `Western`. Idem pour `Silicon Power` (87 lignes). D'où une
  **table fermée de 19 marques en plusieurs mots**, écrite à la main et commentée une
  par une, avec un critère d'entrée explicite : le premier mot seul n'est pas une
  marque du catalogue. Ce critère **ferme la porte** à `Sabrent Rocket`, `JBL Quantum`,
  `ATI FirePro` ou `Creative Labs`, qui sont des gammes — la table corrige un parsing,
  elle ne devine pas une marque.
- **La déduplication absorbe 455 lignes, pas 51.** Le chiffre attendu était celui des
  51 noms `cpu` redondants de l'étape 3 ; la mesure sur les attributs donne 55 pour
  `cpu`, 248 pour `memory`, 110 pour `internal-hard-drive`. L'étape 3 comptait des
  **noms dupliqués**, la déduplication compare des **enregistrements entiers** : ce ne
  sont pas les mêmes objets, et la prédiction reposait sur la confusion des deux.
  L'écart de prix maximal dans un groupe (1 669 USD sur un `cpu`) est le chiffre qui
  révélerait une clé trop lâche ; il s'explique ici par des annonces du même
  processeur à des prix très éloignés, pas par une fusion abusive.
- **`price_per_gb` de la source est juste, mais pas exact.** L'écart médian au recalcul
  est **nul**, le 99ᵉ centile à 0,67 % et le maximum à 4,55 % sur
  `internal-hard-drive` ; il est nul partout sur `memory`. 0,66 % des lignes dépassent
  1 % d'écart, sous le seuil d'arrêt de 1 % — donc le pipeline continue, mais de
  justesse, et le contrôle reste au rapport pour qu'une régénération de la source le
  refasse.
- **Seules 8 lignes sont réellement écartées sur 8 863.** L'entonnoir est beaucoup plus
  propre qu'attendu : `type` absent sur 8 disques, et **zéro rejet de validation
  Pydantic** sur 8 400 produits dédupliqués. Le schéma de l'étape 4, écrit sur les
  bornes mesurées, n'a rien rejeté de valide — ce qui était l'objectif de la règle
  « bornes physiquement plausibles, pas mesurées ».
- **G3 se choisit, elle ne se prend pas.** La première combinaison de filtres durs
  vide qu'on rencontre est `core_count = 1 ET tdp = 105` : elle est vide parce qu'elle
  est physiquement absurde, et elle ne démontre rien. Retenir plutôt celle dont le
  **critère le moins bien servi l'est le mieux** donne « un M.2-2280 en SATA 6.0 Gb/s »
  — 52 produits d'un côté, 85 de l'autre, zéro à l'intersection. C'est une demande
  qu'un client formule vraiment, et c'est le vrai cas d'échec du moteur.
- **`temperature=0` n'existe plus.** Le cadrage de l'étape le demandait pour la passe B ;
  le SDK `anthropic` 1.1.0 a retiré `temperature`, `top_p` et `top_k`. Ce qui portait le
  besoin est repris par `tool_choice` forcé et `strict: true` sur le schéma de l'outil ;
  la reproductibilité mot pour mot, elle, est portée par le cache committé (arbitrage G).
  **Même mécanisme que le `smt` de l'étape 3** : un paramètre supposé disponible, jamais
  vérifié contre la version réellement installée.
- **Un test a trouvé un bug que la relecture avait laissé passer.** Le contrôle « pas de
  mention monétaire dans `resume_usage` » cherchait `EUR` en sous-chaîne : il rejetait
  « 8 co**eur**s », un résumé parfaitement correct. Les codes de devise se cherchent en
  mot entier, les symboles (`$`, `€`, `£`) en sous-chaîne. Le code a disparu avec la
  passe B ; la règle vaudra encore pour le validateur de l'étape 9, qui cherchera des
  montants dans du texte français.

### 3.1bis — Sélection des ~1 000 produits, et le biais qu'elle introduit

**Retenu.** Échantillonnage **stratifié par décile de prix**, calculé par catégorie sur
les produits dédupliqués, quota égal par décile, report des strates déficitaires sur
les voisines, **graine constante** (`20260828`, constante de code dans
`selection.py` — jamais une variable d'environnement, qui se change par accident entre
deux exécutions). Cible : 170 produits par catégorie, soit 1 020 tirés, portés à
1 026 par les repêchages de cas limites (voir G4 ci-dessous).

Le tirage n'utilise pas `random` : les candidats sont ordonnés par une empreinte
`sha256(graine:categorie:id)` et l'on prend les premiers. `random.sample` ne garantit
pas le même résultat d'une version de Python à l'autre, et le seed est un fichier
committé dont le diff doit rester vide quand rien ne change.

**Le biais est assumé, et il doit être dit.** Le seed **n'est pas** la source :

- les taux de remplissage y diffèrent légèrement — `video-card.boost_clock` est à
  78,9 % sur le seed contre 80,3 % sur la source, donc **sous le seuil de 80 %** qui
  avait ouvert la catégorie à l'étape 3. La porte de sortie de l'étape 3 portait sur la
  source ; ce chiffre-ci ne la referme pas, mais il confirme que la marge de 0,3 point
  était une coïncidence et non une marge (risque déjà inscrit au §7) ;
- toute statistique produite ensuite — rapport, éval, README — porte sur le **seed**,
  et le rapport le dit en tête ;
- **la stratification conserve la _forme_ de la distribution des prix, pas ses
  _extrêmes_.** Avec 17 tirages dans le dernier décile, le produit le plus cher a une
  chance sur huit d'être retenu, et sur le premier seed livré aucun des six ne l'avait
  été : le plus cher des moniteurs y valait 2 699 USD contre **9 333 USD** à la source,
  la carte graphique la plus chère 3 863 USD contre **7 516 USD**. Un moteur à
  contrainte budgétaire dont le catalogue s'arrête à 2 699 USD ne peut pas être exercé
  sur un budget large. La garantie **G4** corrige ce point précis en repêchant le
  produit le plus cher de chaque catégorie — un **ajout après tirage**, comme G1 et G2 :
  la graine, les quotas et le découpage en strates ne bougent pas, et le seed passe de
  1 020 à 1 026 produits sans qu'aucune ligne existante ne change.

**Alternative écartée — un tirage uniforme.** Plus simple à écrire et à expliquer, mais
il perd la queue haute : les prix rares sont rares, donc un tirage uniforme ne les
prend presque jamais, et le moteur de l'étape 6 n'aurait aucun produit cher sur lequel
exercer la zone de tolérance budgétaire de 3.10.

**Alternative écartée — prendre les 170 premiers de chaque catégorie.** Reproductible
sans graine, mais l'ordre du fichier source n'a aucune signification : ce serait un
biais non caractérisé au lieu d'un biais choisi.

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

**Contrainte créée par le correctif de l'étape 5 (§3.4ter) : les noms de produits sont
cités verbatim, dans la langue de la source.** Jamais traduits, jamais réécrits, jamais
« francisés » — pas même l'espace ou la casse. C'est la phrase française qui porte la
langue ; le nom, lui, est un identifiant que le client va retaper dans un moteur de
recherche. Le prompt système le dit explicitement, et c'est **le seul français du
produit qui ne soit pas généré** qui vient en renfort : `LIBELLES_CATEGORIE` donne
« écran », « carte graphique », etc., dérivés de la catégorie et non du produit.

Le gain se ramasse à l'**étape 9** : un nom de produit cité devient vérifiable **au
caractère près** contre la base, par simple égalité de chaînes. Avec un `nom_fr` en
base, le validateur aurait dû comparer la sortie du modèle à un texte lui-même généré
— une vérification qui ne prouve rien.

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
| ~~Les attributs sont déclarés au schéma mais peu renseignés~~ | **Éteint** à l'étape 3 | Mesuré : 6 catégories sur 7 ouvrent la porte, `keyboard` retirée |
| **`monitor` et `video-card` ouvrent au dernier attribut** | Faible depuis l'ajout de la marque (3.4quater), qui leur donne une marge d'un attribut | `response_time` est à 78,3 % et `boost_clock` à 80,3 % : ces deux-là restent à surveiller si la source est régénérée |
| **La règle de comptage 3.4quater a été écrite après la mesure** | Moyenne — c'est une critique légitime en relecture de portfolio | Énoncée en principe général, appliquée aux 6 catégories, et elle en ferme toujours une. À exposer telle quelle dans le README plutôt qu'à taire |
| **Prix figés à juillet 2025, en USD** | Certaine — c'est un snapshot | Assumé et documenté au README. Sans effet sur la démonstration, qui porte sur le raisonnement et non sur l'exactitude commerciale |
| **L'agent dérive vers l'interrogatoire ou la recommandation prématurée** | Moyenne — c'est la qualité perçue | Règle « donner avant de demander » dans le prompt, métrique suivie, itération outillée à l'étape 13 |
| **Les cassettes deviennent obsolètes silencieusement** | Moyenne — les tests passent à côté de la réalité | Hash du prompt stocké dans la cassette ; le test échoue si le prompt a changé |
| **Le nettoyage du dataset déborde** | Moyenne — dérive du projet | Geler le périmètre à ce qui est propre plutôt que poursuivre l'exhaustivité |
| **Latence perçue de la boucle multi-outils** | Faible | Streaming des événements typés dès le premier appel d'outil |

---

## 8. Hors périmètre

Paiement, compte utilisateur, multilingue, gestion de panier, historique
inter-sessions.
