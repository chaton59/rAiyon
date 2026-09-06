# rAiyon — Assistant conseil produit en temps réel

Document de cadrage. Il consigne les décisions d'architecture, **les alternatives
écartées et pourquoi**. Il fait foi : toute décision qui le contredit doit être
discutée et amender ce fichier.

Statut : étapes 1 à 6 franchies. Source, domaine et 6 catégories arrêtés
(3.4, 3.4bis), schéma d'attributs écrit et validé, schéma SQL migré et testé,
catalogue de 1 026 produits normalisé, committé et chargé en base, **moteur de
matching écrit, calibré et testé**.
✅ La passe LLM du catalogue a été **supprimée après mesure** (§3.4ter, réécrite) :
le catalogue reste en anglais, le français se produit dans la réponse à l'étape 8.
Aucun octet de la base ne vient d'un modèle, et aucune clé API n'est nécessaire
avant l'étape 8.
✅ **Critère d'acceptation nº5 franchi** (§3.16) : hors du dépôt SQL, le moteur est
pur, et `tests/matching/` tourne hors ligne en moins d'une seconde.
Étape suivante — 7, couche outils et invariants.
Dernière révision : 2026-08-30.

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

### ⚠️ Le périmètre de cette règle — écrit au correctif de l'étape 12

**« Un fait » veut dire ici un fait *sur le catalogue*.** Cette phrase n'avait jamais été
bornée, et le bord n'est apparu qu'en conversation réelle : le persona `joueur_serre` a
demandé « c'est quoi la différence entre une dalle IPS et une dalle VA ? ». Ce n'est pas
une question sur le catalogue, et **rien dans le catalogue n'y répond**.

La conséquence est assumée, et il vaut mieux l'écrire que la découvrir : **cet assistant
conseille à partir du catalogue, il n'enseigne pas la technologie d'affichage.** Il sait
dire ce que le catalogue contient — « 32 de ces écrans sont en VA, 13 en IPS » est un fait
fourni ; il ne sait pas dire ce qu'une dalle VA vaut, et il ne doit pas faire semblant.

Deux choses en découlent, toutes deux mesurées à l'étape 12 :

* **le validateur ne contrôle pas ce qu'il ne peut pas fonder.** Une affirmation de domaine
  qui ne porte ni chiffre à unité connue, ni montant, ni nom de produit ne déclenche aucune
  des cinq règles — et c'est le comportement voulu : une règle qui ne sait pas trancher ne
  doit pas faire semblant. Le prix de cette position est au §7 ;
* **le repli d'une telle réponse ne renvoie pas la question au client** (`PHRASE_DE_DOMAINE`) :
  il dit ce que l'assistant ne fera pas, puis bascule sur ce que le catalogue contient.

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
« et pour ma sœur qui est gauchère ? », « finalement, montre-moi du moins cher ».
Chacun demande un état prévu à l'avance. L'agent les encaisse naturellement.

> **Amendement de l'étape 6 — cet argument a perdu un de ses exemples, et il faut
> le dire.** La version initiale citait « il me faut aussi une ponceuse, 300 €
> pour les deux ». L'arbitrage K de l'étape 6 a mis la **composition
> multi-catégories hors périmètre** : un appel au moteur rend les produits d'une
> seule catégorie, et il n'existe ni panier ni budget partagé (§8). Cet exemple
> ne peut donc plus servir à justifier l'agent, puisque la machine à états ne le
> servirait pas plus mal — aucune des deux ne le sert. Ce que l'agent encaisse
> réellement et qu'une machine à états encaisserait mal, ce sont les virages
> **à l'intérieur** d'une catégorie : reformuler, comparer deux propositions,
> revenir sur un critère, changer d'avis sur le budget. L'argument tient sur ces
> cas-là ; il ne tenait pas sur le panier, et le laisser dormir aurait laissé
> §3.6 s'appuyer sur une capacité que le produit n'a pas.

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

> **Amendement de l'étape 15 (3 septembre 2026) — la machine à états a été écrite,
> et les deux moitiés de cette section sont maintenant mesurées.** La décision ne
> change pas ; ce qui change, c'est qu'elle cesse d'être un pari.
>
> **La machine à états ne gagne pas.** Mesurée sur les onze scénarios de l'étape 12 —
> écrits pour l'agent, avant qu'elle soit envisagée —, **un seul écart dépasse la
> dispersion, et c'est elle qui le perd** : les rejets du validateur passent de 2,00 à
> 17,00 par passe pour une étendue de ± 12,00, dominés par `ecart_non_dit`, **0 → 24**.
> Les cinq autres mesures sont dans le bruit, et les six critères tiennent des deux
> côtés (`docs/eval/comparaison.v2-machine.v1.md`).
>
> **Le coût annoncé ci-dessus est remboursé, et le remboursement est étroit.**
> `decider()` est la fonction de décision pure que cette section déclarait perdue :
> **17 tests de conduite du dialogue** tournent dans `make check`, sans base, sans
> conteneur et sans clé, contre **0** chez l'agent. Et les appels baissent d'environ
> 8 % — **2,17 par tour contre 2,36**.
>
> ⚠️ **Le coût qu'elle ajoute n'était pas prévu, lui.** L'entrée facturée est
> **1,80 fois supérieure** : 663 347 jetons contre 367 832. Une orchestration qui fait
> **moins d'appels** et coûte **presque le double** — deux appels par tour sur une
> conversation qui grossit plus vite. Publier les appels seuls aurait dit l'inverse de
> la vérité, et c'est pourquoi la mesure nº7 publie les deux.
>
> **L'argument d'origine est validé par un mécanisme qu'il ne nommait pas.** « L'agent
> encaisse naturellement les virages » désignait une intuition ; ce qu'on observe est
> précis. L'extraction de la machine est **atomique et sans recours** : un appel refusé
> emporte tout ce qu'il portait, et rien ne peut le rejouer dans le tour. L'agent, lui,
> relit le refus et rappelle l'outil. Voir la ligne de §7.
>
> **Où gagne chacune, en une phrase.** La machine gagne la **testabilité de sa
> décision** et rend explicite un invariant que personne n'avait écrit ; l'agent gagne
> la **rédaction** et le **coût d'entrée**. Aucune des deux n'est « meilleure », et
> écrire qu'elle l'est serait la seule conclusion que ces mesures ne portent pas.

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

> **Amendement de l'étape 7 — les quatre outils sont devenus cinq, et deux signatures
> de ce tableau sont fausses.** Elles sont laissées telles quelles au-dessus : c'est une
> décision renversée, pas une décision qui n'a jamais eu lieu.
>
> 1. **`probe_catalog(criteria)` et `search_products(criteria)` ne prennent plus de
>    critères.** L'arbitrage C de l'étape 7 fait entrer les critères par **une seule
>    porte**, et les outils de recherche lisent l'état de session. Un outil de moins à
>    garder, et surtout une garde de moins à ne pas oublier sur un futur outil.
> 2. **Un cinquième outil, `record_criteria`, apparaît** — conséquence directe du point
>    précédent, et non fonctionnalité ajoutée : les critères que ce tableau faisait
>    voyager en argument de `search_products` ont besoin d'une porte à eux, et cette
>    porte est un outil parce que le modèle doit pouvoir l'appeler.
> 3. **`ask_clarification` devient terminal.** Il ne « ne rend rien » plus : il rend
>    `{ok, terminal}` et clôt le tour, l'étape 8 renvoyant au client le texte de son
>    argument. La version initiale forçait un aller-retour API supplémentaire et invitait
>    le modèle à appeler l'outil **puis** à réécrire la question en texte — la question
>    était posée deux fois.
>
> | Outil | Rend |
> |---|---|
> | `record_criteria(categorie, criteres, retraits, budget_usd, …)` | L'état mis à jour, et les mouvements refusés |
> | `probe_catalog(champs)` | Agrégats seuls, troncature déclarée. Aucun produit |
> | `suggest_next_question()` | Le champ manquant le plus discriminant. Aucune phrase |
> | `search_products()` | Produits entiers, `produits` et `au_dessus_du_budget` séparés, avec trace |
> | `ask_clarification(question, champ_vise)` | `{ok, terminal}` — le tour est clos |

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

**Amendement de l'étape 6 — cette zone est aussi la réponse au cas « le budget est
le critère bloquant ».** Quand la recherche ne rend rien mais que la zone de
tolérance n'est pas vide, le diagnostic vaut `budget_trop_bas` et la réponse est
**cet ensemble-là**, avec son écart exact : tout ce que le client a demandé existe,
un peu au-dessus de ce qu'il a dit. Ce n'est pas « relâchez votre budget », c'est un
fait chiffré qu'il peut trancher lui-même.

Conséquence directe sur le relâchement (arbitrage J) : `prix_usd` est **exclu** des
candidats au retrait. Le moteur ne propose jamais d'assouplir le budget, et la
logique n'est pas dupliquée — elle vit ici, dans un ensemble déjà calculé. Deux
endroits qui décideraient du budget finiraient par le dire différemment, ce qui est
exactement le mode d'échec que la colonne `sessions.budget_usd` ferme déjà.

Les deux ensembles sont récupérés par le **même chemin de requête**, à la fourchette
de prix près : un produit de la zone de tolérance satisfait donc exactement les mêmes
critères durs que ceux du classement principal. Sans cela, la tolérance deviendrait un
second catalogue aux règles plus souples.

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

> **Amendement de l'étape 9 — les trois niveaux existent, et le niveau 2 vérifie la
> *provenance*, pas l'appartenance.**
>
> La formulation ci-dessus — « vérifiés contre le contexte réellement fourni » — laissait
> croire qu'un ensemble de tout ce que les outils ont rendu suffisait. **Il ne suffit
> pas**, et le contre-exemple était déjà dans la conversation de l'étape 8 : le sondage
> avait rendu la fourchette `108.00 $` à `399.99 $`, et un écran valait `108.00 $`.
>
> Un validateur à ensemble plat aurait accepté « cet écran est à 108 $ » **même si aucune
> recherche n'avait eu lieu** — parce que 108,00 est bien un nombre fourni. C'est
> exactement l'oracle à prix que le §7 nomme, et une atténuation qui le laisse ouvert
> n'atténue rien.
>
> `ContexteFourni` range donc les faits par **d'où ils viennent** : le prix d'un produit,
> l'écart au budget d'un produit hors budget, une valeur de caractéristique attribuable à
> un produit, et — dans un champ à part — les **agrégats**, ces nombres fournis qui ne
> sont le fait d'aucun produit (bornes de prix, comptages, budget, valeurs atteignables
> d'un diagnostic). Un montant dans une phrase qui nomme un produit doit être le prix de
> **ce** produit ; une borne de sondage n'y a pas sa place.
>
> Vingt lignes de plus qu'un ensemble plat. Elles achètent la seule chose que la phrase
> « l'oracle à prix est vérifiable à l'étape 9 » promettait.

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

> **Amendement de l'étape 9 — `text_delta` n'existera pas. Le texte n'est pas streamé.**
>
> **§3.11 et §3.12 étaient en contradiction, et personne ne l'avait vu.** §3.11 promet
> que « la réponse est parsée et vérifiée » avant qu'elle atteigne le client ; §3.12
> promet des `text_delta`. Valider après génération et streamer le texte sont
> **incompatibles** : on ne rattrape pas une phrase déjà affichée.
>
> C'est §3.11 qui gagne. Le texte d'un message assistant est concaténé, validé, puis émis
> d'un bloc — **un** événement `Texte`, jamais une suite de deltas.
>
> *Alternative écartée — streamer le texte et corriger à l'écran après coup.* Meilleure
> latence perçue, mais le client voit une affirmation puis sa rétractation : c'est §2
> pris à l'envers, et une démonstration qui montrerait un prix faux pendant deux secondes
> ne démontrerait rien.
>
> **Ce que le panneau ne perd pas.** `criteria_updated`, `catalog_probe`,
> `products_found` et `suggested_question` continuent d'arriver **au fil de l'eau**,
> pendant l'attente : ce qui rend l'architecture visible à l'écran est intact, et c'est
> même la seule chose qui bouge tant que la prose est en cours de vérification. Seule la
> prose arrive d'un coup.

> **Amendement de l'étape 10 — les noms du fil sont arrêtés, et le §3.12 d'origine était
> une esquisse.**
>
> Les quatre lignes d'exemple ci-dessus dataient du cadrage : elles parlaient de
> « perceuse », de `price_range: [90, 340]` et d'un `products_found` portant un champ
> `explication`. Le fil réel est arrêté à **dix** événements, dont huit viennent de
> l'union `Evenement` du domaine et deux appartiennent à l'API.
>
> | Événement | `event:` | ce qu'il porte |
> |---|---|---|
> | `CriteresMisAJour` | `criteria_updated` | la catégorie, son libellé, les critères, le budget, l'optimisation, les mouvements refusés |
> | `Sondage` | `catalog_probe` | les deux comptes de budget, la fourchette de prix, les distributions entières |
> | `QuestionSuggeree` | `suggested_question` | le champ de plus fort gain, ou le besoin de budget |
> | `ProduitsTrouves` | `products_found` | les produits, le hors-budget avec son écart, le diagnostic |
> | `QuestionPosee` | `question` | la question et le champ visé |
> | `Texte` | `message` | la prose **validée**, entière |
> | `TexteRejete` | `text_rejected` | l'origine, la tentative, les griefs |
> | `Repli` | `fallback` | le message écrit en Python et son motif |
> | — | `error` | `code` fermé + phrase française. **Après** le premier octet seulement |
> | — | `done` | terminal et obligatoire |
>
> **`text_delta` n'existe pas, et il était déjà mort à l'étape 9.** L'étape 10 le constate
> une seconde fois par un autre chemin : il n'y a plus aucun consommateur de delta dans la
> boucle, donc plus rien à streamer côté modèle. Voir l'amendement du §5 étape 8.
>
> **Ce que le fil porte, et ce qu'il ne porte pas** — la ligne de partage est : *ce qui
> prouve un invariant sort, ce qui explique un classement reste.*
>
> * `text_rejected` **part au client**. Il est petit (codes de grief et extrait) et c'est
>   la seule preuve visible à l'écran que §2 est tenu par du **code** et non par un prompt.
>   C'est le meilleur rapport effet/effort de l'étape 11.
> * `ResultatMatching.traces` **ne part pas** : c'est du volume et du débogage de moteur.
>   Restent dehors pour la même raison `ecartes_faute_de_donnee`, `Repli.iterations`,
>   `Repli.outils_appeles`, et tout `EtatSession`. Si l'étape 11 réclamait la trace, elle
>   passerait par un endpoint dédié, pas par un élargissement de `products_found`.
>
> **Le français du fil est dérivé du registre, jamais inventé par le front.** `Critere` ne
> porte ni libellé ni unité, et les `specs` d'un produit sont en anglais. Le sérialiseur
> fait le même geste que la console — `ATTRIBUTS[categorie][champ]` (arbitrage I de
> l'étape 6) — et le fil porte `libelle_fr` et `unite` à côté de **chaque** champ. Sans
> cela, l'étape 11 coderait du français en dur dans du JavaScript, et §3.4ter cesserait
> d'être vrai de bout en bout au moment précis où il devient visible. Un test le vérifie
> **sur la source du module**, pas sur son résultat.
>
> **Tout `Decimal` voyage en chaîne**, comme dans `en_tool_result()` : un flottant JSON
> perdrait des décimales sur un prix, et §2 se joue au caractère près.

> **Amendement de l'étape 11 — l'arbitrage H ne couvrait que les champs, et il fallait un
> consommateur qui affiche tout pour s'en apercevoir.**
>
> « Le français du fil est dérivé du registre » avait été appliqué aux **champs** :
> `libelle_fr` et `unite` à côté de chacun. Il ne l'avait pas été aux **valeurs
> d'énumération**, parce qu'aucun consommateur n'en affichait au client — la console n'en
> montre aucune. La première conversation menée dans le navigateur a mis
> `optimisation : rapport_qualite_prix` dans un panneau, et le zéro résultat aurait affiché
> `critere_trop_strict`, là où le critère d'acceptation nº6 demande « le cas zéro résultat
> **rendu lisible** ».
>
> Trois tables `LIBELLES_*` rejoignent donc leurs énumérations, du côté Python — même geste
> que `LIBELLES_CATEGORIE`, et pour la même raison :
>
> | valeur | où vit son français | ce que le fil ajoute |
> |---|---|---|
> | `Optimisation` | `matching/criteres.py` | `libelle_optimisation` |
> | `Motif` (zéro résultat) | `matching/relachement.py` | `libelle_motif` |
> | `MotifDeRepli` | `agent/evenements.py` | `libelle_motif` |
>
> **Le jeton reste à côté du libellé** : le front compare le premier (`!== "aucune"`) et
> affiche le second. Rendre l'un sans l'autre l'obligerait soit à comparer une phrase
> française, soit à la fabriquer. Un test vérifie l'**exhaustivité** de chaque table — un
> membre sans libellé lèverait un `KeyError` au milieu d'un flux, c'est-à-dire un tour
> perdu, appel API compris, pour un mot d'affichage.
>
> **Trois valeurs n'ont délibérément pas de libellé.** `importance` (« souhait »,
> « important », « bloquant ») est déjà du français ; le `code` d'un grief et l'`origine`
> d'un rejet sont des identifiants qui ne s'affichent qu'en mode coulisses, où c'est
> précisément le jeton qu'on vient lire. `operateur` est rendu par un **symbole** (`≥`, `≤`)
> et non par du français — `scripts/console.py` fait le même geste depuis l'étape 8.

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

> **Amendement de l'étape 8 — le point de coupe du cache, et sa conséquence de
> conception.** « Prompt caching activé sur le prompt système » ci-dessus décrit une
> intention ; l'étape 8 en fixe le mécanisme et, surtout, **ce qu'il interdit**.
>
> Un seul point de coupe, posé sur le bloc système :
>
> ```python
> system = [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]
> ```
>
> Le préfixe mis en cache est `tools` + `system`. Une coupe sur le système couvre donc
> **aussi les cinq définitions d'outils**, qui sont la partie la plus lourde et la plus
> stable de la requête ; un second point de coupe n'aurait rien à protéger de plus.
>
> ⚠️ **La contrainte que cela crée est une règle de conception du prompt, pas une
> optimisation.** Le préfixe doit être identique **octet pour octet** d'un appel à
> l'autre. Donc : **ni la date, ni l'état de session, ni le numéro de tour, ni la
> catégorie courante ne vont dans le prompt système.** L'état ne vit que dans les
> `tool_result`. C'est écrit ici, et pas seulement dans le code, parce que la faute est
> silencieuse : un prompt interpolé n'échoue pas, il cesse simplement d'être mis en
> cache, sans erreur ni log, et cela ne se voit que sur la facture. Deux tests le
> constatent — l'un que deux appels d'un même tour reçoivent un `systeme` et des
> `outils` identiques, l'autre que `prompts/systeme.v1.md` ne porte aucun marqueur
> d'interpolation.
>
> Mesuré au passage : **le drapeau `strict` des définitions d'outils ne fait pas partie
> de la clé de cache** — un appel sans le drapeau lit le cache écrit par un appel avec.
> On ne peut donc pas se servir du compteur de cache pour vérifier que `strict` est
> appliqué.

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

> **Amendement de l'étape 13 — la version se choisit par variable
> d'environnement, et les trois fichiers coexistent.**
>
> `SYSTEME_V1` était une constante de module : changer de version demandait de
> modifier du code, donc de faire porter à un commit la différence entre « j'ai
> réécrit le prompt » et « je mesure l'autre ». `RAIYON_PROMPT_SYSTEME` nomme
> désormais le fichier, `systeme.v1` par défaut, et `prompt_systeme()` rend la
> version, le texte et l'empreinte **d'un seul tenant** — les séparer laisserait
> `/health` annoncer une version pendant que la boucle en envoie une autre.
>
> ⚠️ **C'est une sélection de fichier, pas une interpolation, et la distinction
> est celle de §3.13.** Ce que le préfixe mis en cache interdit, c'est un texte
> qui change d'un appel à l'autre ; choisir lequel des trois textes envoyer
> laisse chacun identique octet pour octet. La variable ne touche pas au contenu.
>
> **Le test d'interpolation balaie les trois prompts, pas celui en vigueur.**
> Deux des trois ne sont sélectionnés par personne pendant la campagne du
> troisième : un `{quelque_chose}` glissé dans un fichier au repos ne se verrait
> qu'au moment de lancer sa campagne, c'est-à-dire au moment de dépenser
> trente-six prises. La liste des versions est **découverte sur le disque**
> (`versions_systeme()`), jamais écrite à la main — une `systeme.v4.md` ajoutée
> demain est balayée sans que personne ait à s'en souvenir.
>
> **Les cassettes suivent la version.** Un *jeu* porte un nom court (`v1`, `v2`,
> `v3`, `v1-etape12`), ses cassettes vivent sous `evals/cassettes/systeme.<nom>/`
> et son rapport dans `docs/eval/rapport.<nom>.md`. Sans ce rangement, comparer
> deux prompts obligerait à ne garder que les rapports — et le tirage que §7
> décrit cesserait d'exister ailleurs que dans un tableau.

### 3.15 — Stratégie de test

| Cible | Approche |
|---|---|
| Moteur de matching | pytest pur, catalogue fixture, **zéro appel API** |
| Invariants des outils | Assertions dures : clamp budget, séparation hors-budget, forme des agrégats |
| Validateur | Fixtures de sorties LLM piégeuses (prix modifié, ID inexistant, produit inventé) |
| Scénarios bout en bout | **Cassettes enregistrées** (étape 12) : `make eval-enregistrer` appelle l'API, `make eval` rejoue depuis le disque **sans clé**. ⚠️ Pas « gratuite et déterministe » au sens où cette ligne le promettait : le rejeu exige Postgres et le seed, puisque les `tool_result` sont recalculés (étape 12, arbitrage A). `make check` reste donc inchangé, et `make eval` est une commande à part |
| Dialogue réel | `make eval-live` : trois personas joués par Haiku, **cloisonnés** — ils ne voient que la prose livrée et les produits (étape 12, arbitrage H). Lancés à la main, hors CI, et **rien n'est enregistré** : ces conversations ne sont pas reproductibles par construction |

**Alternative écartée — mocks écrits à la main.** Aucun appel API, mais on teste
ses propres suppositions sur ce que le LLM répond, pas la réalité.

**Alternative écartée — appels réels marqués et exclus par défaut.** Teste la
vérité, mais rien ne l'exécute automatiquement : les régressions passent.

~~**Servitude des cassettes :** il faut les régénérer à chaque changement de prompt.
C'est une discipline à tenir, pas un détail.~~

**Amendement de l'étape 12 — ce n'est plus une discipline, c'est une erreur.** La phrase
est barrée plutôt qu'effacée parce qu'elle décrivait bien le problème et mal sa parade :
une discipline se tient jusqu'au jour où on l'oublie, et une cassette périmée qui se
rejoue en silence produit **des chiffres au lieu d'une erreur** — le pire des deux.

Chaque cassette porte donc, dans son en-tête, **trois empreintes** que le rejeu compare à
celles en vigueur avant de jouer le premier tour (arbitrage C) :

* le **prompt système**, avec sa version ;
* le **schéma d'outils** — c'est celle que la formulation « hash du prompt » de §5 étape 12
  laissait échapper. Le schéma fait partie du préfixe mis en cache (§3.13) et détermine ce
  que le modèle **peut** faire : un outil dont la description change périme la cassette
  autant qu'un prompt modifié, et l'étape 13 doit justement toucher `schema_outils.py` ;
* le **modèle**, et la date d'enregistrement.

Un écart lève `CassettePerimee`, nomme la cassette et **donne la commande à taper**. Un
test d'intégration mince rejoue une cassette committée à chaque `make test-int`, avec sa
contre-épreuve : sans elle, un `verifier()` qui ne vérifierait rien passerait au vert.

**Et la servitude n'est pas la seule chose que le format protège.** Une cassette
n'enregistre **que les réponses du modèle** (arbitrage A) : les `tool_result` sont
recalculés au rejeu par le vrai moteur, sur le seed committé. C'est ce qui fait que l'éval
mesure la pile entière — mais c'est aussi ce qui la rend sensible à un changement de
comportement du moteur, qui se manifeste alors comme une **divergence de requête** nommant
le tour. Constaté à l'étape 12, en neutralisant une règle du validateur.

### 3.16 — Frontière SQL / Python du moteur

> **SQL décide qui est candidat, Python décide comment on le présente.**

Côté SQL : les filtres durs, les comptages de relâchement, les valeurs atteignables.
Côté Python pur, sur une liste de `ProduitEnBase` déjà récupérés : le scoring, la
pondération, le classement, la trace, le diagnostic et la formulation des propositions.

**Ce que cette ligne achète, et c'est le point.** La majorité de la suite de tests du
moteur est pure : elle tourne dans `make check`, sans base, sans conteneur et sans clé
API. Seuls les filtres et les comptages portent le marqueur `integration`. Le **critère
d'acceptation nº5** — « moteur de matching testable sans API » — cesse donc d'être une
discipline à tenir pour devenir une propriété **de construction** : il n'y a rien à
débrancher, puisque rien n'est branché.

Mesure à l'étape 6 : **147 tests purs pour 28 tests d'intégration**, et la part pure
de `tests/matching/` s'exécute en 0,14 seconde — la porte de sortie demandait deux
secondes.

**Alternative écartée — tout en Python, sur le catalogue chargé en mémoire.** Suite
instantanée et sans dépendance ; 1 026 produits tiennent en mémoire sans difficulté.
Écartée parce que §3.2 et §3.3bis perdraient leur objet : Postgres ne servirait plus
qu'à stocker, dans un projet dont une des accroches est précisément le travail en SQL
sur des attributs hétérogènes.

**Alternative écartée — tout en SQL, scoring compris.** Une seule requête rendrait le
classement fini. Écartée pour deux raisons : le classement deviendrait intestable sans
base — donc le critère nº5 tomberait — et une pondération renormalisée sur les critères
disponibles, écrite en SQL, serait illisible et impossible à faire évoluer.

### 3.17 — La règle de collant, et le jeton de parole

> **Un critère déclaré ne se défait pas tout seul. Desserrer coûte une parole du
> client ; resserrer est libre.**

L'étape 6 l'annonçait pour la seule **importance** : un `bloquant` ne peut pas être
re-déclaré `souhait` par le modèle seul. C'était insuffisant, et la mesure de l'étape 7
l'a montré : après un zéro résultat, passer `au_moins 144` à `au_moins 120` obtient
exactement ce que la rétrogradation obtenait, sans toucher à l'importance — et retirer le
critère fait pire. La règle porte donc sur le **mouvement**, jamais sur l'un de ses
attributs :

> Un mouvement **desserre** s'il peut faire remonter un produit qui ne remontait pas.

Une seule fonction pure en décide, `desserre(avant, apres, attribut)`, dérivée de
l'opérateur et du registre — jamais d'une liste écrite à la main. Le budget n'y a aucune
ligne propre : il est présenté à cette fonction comme un `au_plus` sur `prix_usd`, et les
quatre cas du budget (monter, effacer, baisser, poser) tombent des lignes générales.

**Le contrôle est un jeton de parole par tour client.** Un mouvement qui desserre
consomme le jeton du tour ; un second desserrage dans le même tour est refusé. Le numéro
de tour est **fourni par l'appelant** : la couche outils n'a aucune notion d'horloge, et
les tests injectent des entiers.

*Alternative écartée — exiger une citation verbatim d'un message `user`.* Elle donne
l'illusion d'une preuve : le modèle peut citer « je peux monter un peu », prononcé à
propos du budget, pour desserrer la fréquence de rafraîchissement. Le jeton ne prouve pas
que le client a parlé **de ce critère**, mais il borne le nombre de desserrages par
parole, ce qui tue l'essai-erreur — le vrai mode d'échec que §3.6 cherche à empêcher.

⚠️ **La faiblesse est réelle, elle est au §7, et elle ne se referme pas par un
raffinement.** Un desserrage par tour au lieu de zéro contrôle est un progrès, pas une
garantie.

**Trois mouvements ne coûtent rien, et il vaut la peine de dire pourquoi :**

- **redire un critère à l'identique** — sans quoi un modèle qui récapitule l'état à
  chaque tour se punirait lui-même ;
- **changer d'`optimisation`** — elle ne touche pas l'ensemble des candidats, seulement
  son ordre, et ne peut donc pas transformer un zéro résultat en résultat, qui est le
  seul mode d'échec que le jeton vise. Elle change bien **quels** produits sont montrés,
  la limite étant de trois : dire « elle ordonne, elle n'exclut pas » serait faux ;
- **poser une contrainte** — un ajout, une hausse d'importance, un seuil qui avance, un
  budget qui baisse. Le modèle n'a jamais besoin d'autorisation pour être plus fidèle à
  ce que le client a dit.

**Le changement de catégorie, lui, paie s'il efface un budget.** Il remet le budget à
`None` (§ étape 7, arbitrage D), ce qui est exactement la ligne « budget qui passe à
`None` » : aucune exemption n'est écrite pour le seul chemin qui l'emprunte. La première
version en exemptait le changement de catégorie et le bornait à un par tour ; le trou
était **inter-tours**, donc invisible pour une borne posée par tour — partir sur `cpu` au
tour 5, revenir sur `monitor` au tour 6, et chercher sans plafond.

### 3.18 — La recherche web : un sixième outil, et un cache qui sert la mesure

**Décidé à l'étape 26.** Le catalogue apporte des faits ; le web apporte des **opinions** —
des avis et des retours d'usage, ce dont aucune colonne ne dispose. La bride a été
délibérément relâchée pour rendre la conversation plus naturelle, quitte à sortir un peu
du catalogue. **Tout ce qui est relâché doit rester mesurable**, et c'est pour cela que le
journal de l'étape 23 précède celle-ci.

#### Les décisions arrêtées

| | |
|---|---|
| **Un outil exécuté par le répartiteur**, pas le `web_search` natif d'Anthropic | Le natif ferait perdre trois choses : le cache, l'encadrement du contenu en **donnée citée**, et le journal. Aucune des trois n'est optionnelle ici |
| **Fournisseur : Brave Search API** | Choisi sur ses conditions de stockage, **pas sur son prix**. Google et Exa l'interdisent, Serper et SerpAPI revendent du Google sous litige, Tavily est silencieuse — et le silence n'est pas une permission. Brave est le seul où stocker est un droit **accordé explicitement**, moyennant un plan « storage rights ». Variable `BRAVE_SEARCH_API_KEY`, traitée comme `ANTHROPIC_API_KEY` |
| **Cache sur la requête normalisée**, lien produit optionnel | La recherche est libre — le modèle formule ce qu'il veut —, donc il n'y a pas toujours un `produit_id` sous lequel ranger |
| **Contenu brut, URL, date. Jamais de synthèse générée** | On ne met pas de texte de LLM dans la base de faits (§2). Même règle que `produits` |
| **Le contenu web n'entre PAS dans le `ContexteFourni`** | Conséquence voulue : la prose qualitative reste libre — aucune règle ne la couvre — et **tout chiffre ramené du web tombe**. ⚠️ C'est un acte à poser, pas un état par défaut : `_charges_utiles()` lit tout `tool_result` réussi sans regarder de quel outil il vient, donc un sixième outil y entrerait **automatiquement**. Un test doit échouer si l'exclusion est retirée |

#### Le TTL vaut 24 h, et le chiffre vient d'une frontière — pas d'un taux de hit

🔴 **L'argument économique a été mesuré, et il est faux.** Une campagne complète fait 81
tours client, donc au pire 81 recherches, soit **0,40 $** au tarif Brave de 5 $ pour mille ;
le crédit mensuel offert en paie douze. Le cache n'économise **rien qui compte**, et le
dimensionner comme un cache d'économie aurait donné une réponse à la mauvaise question.

Ce qu'il achète est la **comparabilité** : comparer deux versions de prompt suppose que les
deux exécutions aient vu le même contenu web, sans quoi la différence mesurée mélange
l'effet du prompt et celui d'une page qui a bougé — et rien à l'écran ne les sépare.

**Les deux caches ne se dimensionnent pas pareil.** Un cache d'économie se règle sur un
taux de hit : un TTL court qui attrape déjà 90 % des répétitions suffit. Un cache de
comparabilité se règle sur une **frontière** — il doit être plus long que l'écart entre les
deux bras d'une comparaison, sinon l'expiration tombe **au milieu de la mesure**. Une
frontière à 4 h attrape pourtant presque tous les hits, et coupe en deux une session de
travail qui en dure six. **Ce défaut-là n'apparaît dans aucun taux de hit.**

24 h est donc le plus court TTL qui fasse coïncider une génération de cache avec une
journée de travail, l'unité réelle de ce projet. Plus long ne rattrape presque rien et
transforme le cache en corpus ; plus court rouvre la frontière au milieu de la mesure.

⚠️ **Risque résiduel, nommé** : une comparaison à cheval sur minuit. Il ne se ferme pas par
un TTL plus long, il se **rend visible** — `recupere_le` est dans la ligne et le journal
trace hit/miss par recherche, donc une mesure contaminée se constate au lieu de passer.

#### Les mesures ne sortent jamais sur le réseau

**Deux problèmes ouverts n'en faisaient qu'un, et un seul geste les ferme** : le cache est
**pré-chargé**, seedé comme le catalogue l'est déjà (`data/seed/avis.jsonl`). L'outil
trouve un hit, ne sort pas, ne consomme pas de crédit, et rend le même `tool_result` à
chaque rejeu.

1. `make eval` tourne sans clé et sans réseau. Un outil qui appellerait un fournisseur au
   rejeu dépenserait **et** rendrait un `tool_result` différent de l'enregistrement, donc
   une cassette qui ne rejoue plus la même conversation.
2. Le §3(b) des conditions Brave interdit d'employer des résultats de recherche pour
   *« evaluate […] or benchmark »* un modèle. Une campagne qui interroge Brave pour
   comparer deux prompts est exactement cela.

*Alternative écartée — la cassette porte le résultat d'outil.* Elle confondrait le rejeu du
**modèle** et celui des **outils**, alors que les cassettes de ce dépôt sont explicitement
« les réponses du modèle ».

*Alternative écartée — une fixture séparée.* Elle ajoute un mécanisme parallèle là où le
cache fait déjà ce travail. Le catalogue est seedé ; les avis le sont pareil.

**Deux conséquences tenues dès l'étape 26** : `source` sépare `brave` de `fabrique`, et une
ligne `fabrique` **ne périme jamais** — sinon le seed expirerait 24 h après `make seed` et
les campagnes cesseraient de trouver quoi que ce soit, silencieusement, un jour plus tard.
Et **aucune ligne `brave` n'entre au dépôt git** : le §3(b) interdit aussi de redistribuer
des résultats de recherche, ce qu'un JSONL committé serait.

⚠️ **Reste à lire avant de créer la clé** : le plan « storage rights » lève-t-il la clause
« evaluate / benchmark », ou seulement l'interdiction de stocker ? Avec le cache
pré-chargé, elle porte beaucoup moins — mais on ne signe pas sans savoir.

---

## 4. Critères d'acceptation

Mesurés par le harnais d'éval, publiés en tableau dans le README.

| # | Critère | Seuil | Mesure |
|---|---|---|---|
| 1 | Aucun produit, prix ou spec inventé | **0**, strict | Validateur, sur tous les scénarios |
| 2 | Budget jamais dépassé sans présentation explicite | **0** violation | Assertion sur les produits cités hors `au_dessus_du_budget` |
| 3 | Délai avant première valeur | **≤ 2 tours client**, médian | Métrique d'éval, suivie dans le temps. ⚠️ **Le seuil comptait des questions jusqu'au correctif de l'étape 12** ; il valait alors 0 partout, parce que l'agent n'appelle jamais `ask_clarification` avant de montrer quelque chose. §3.9 disait déjà quoi compter — « le bon indicateur est le délai avant première valeur, pas le compte de questions » — et on compte donc **combien de fois le client a dû parler**. Le nombre n'a pas changé, son sens si : « au deuxième message, le client a vu quelque chose ». Le compte de questions reste publié **sans seuil** : il mesure la règle de dialogue, pas le délai |
| 4 | Pertinence : le produit attendu est dans le top 3 | ≥ 80 % | Scénarios à réponse de référence |
| 5 | Moteur de matching testable sans API | binaire | La suite `tests/matching/` tourne hors ligne |
| 6 | Cas zéro résultat traité proprement | binaire | Scénario dédié : dire pourquoi + proposer l'assouplissement du critère le plus coûteux |

Les critères 1, 2, 5 et 6 sont binaires et bloquants. Les 3 et 4 sont des
métriques de qualité que l'on suit et que l'on cherche à améliorer.

### La mesure nº7 — le coût par tour. **Ce n'est pas un critère d'acceptation.**

Ajoutée au jalon 0 de l'étape 15 : la somme des appels au modèle enregistrés dans
l'en-tête des cassettes d'un jeu, divisée par ses tours client (`Mesures.tours`). Sur la
campagne v2 : **191 appels pour 81 tours, soit 2,36 appel par tour**.

Elle n'a **pas de seuil**, et n'en aura pas. Elle ne dit pas qu'une orchestration est
bonne ; elle dit ce qu'elle coûte. C'est une propriété réelle qu'aucun des six critères
ne capture, et c'est précisément ce qui la rend utile pour comparer un agent à une machine
à états — mais un seuil en ferait une cible, et la façon la moins chère de tenir une cible
de coût est de moins appeler le modèle, ce qui n'est pas un progrès.

⚠️ **Elle n'a pas la même provenance que les six autres.** Tout ce que mesure le harnais
est **recalculé à chaque rejeu** par le vrai moteur (arbitrage A de l'étape 12) ; ce
chiffre-là est **figé à l'enregistrement** et ne bougera plus. Le rapport et la
comparaison l'écrivent à côté du nombre, et il vit dans son propre module — voir
`raiyon/eval/cout.py`.

Publiée **tout ou rien** : si une seule prise du jeu ne porte pas d'`usage`, aucun chiffre
n'est publié et la ligne dit combien en manquent. Les dix-neuf cassettes de l'étape 12 et
les vingt et une de la campagne v1 interrompue sont antérieures au champ ; une moyenne
calculée sur les trois prises restantes de `v1-base` et comparée aux trente-six de `v2`
comparerait des tailles d'échantillon.

#### ⚠️ Correctif de l'étape 16 — elle publie aussi les jetons, et c'est ma spécification qui était fautive

La mesure a été spécifiée ci-dessus, au jalon 0 de l'étape 15, sur `entete.usage.appels`
seuls — **avant qu'on sache que le compte d'appels dirait l'inverse du coût réel**. La
campagne l'a montré : la machine à états fait **2,17 appel/tour contre 2,36** — moins — et
paie **1,80 fois plus d'entrée facturée**, 663 347 jetons contre 367 832.

Un lecteur qui ouvre `rapport.machine.v1.md` dans six mois et n'y lit que les appels conclut
« moins chère ». **La conclusion inverse est la vraie**, et elle ne vivait que dans le README
et dans le tableau de l'étape 15, sommée à la main sur les en-têtes.

Ce n'est pas un défaut d'implémentation : `Usage` savait s'additionner et `mesurer_le_jeu()`
lisait déjà chaque en-tête. Le chiffre juste était sous la main depuis le premier jour de la
campagne, et personne ne le publiait. La mesure nº7 publie désormais, par jeu :

* les **appels par tour**, comme avant ;
* les **jetons d'entrée facturés** — entrée hors cache **plus** cache écrit, ce qui se paie
  — et le **cache lu à côté, jamais additionné** : il est facturé autrement, et la somme des
  deux serait un total que personne ne doit à personne ;
* les **jetons de sortie**.

Avec, à côté du tableau, la phrase qui dit **pourquoi les deux moitiés existent** — une
orchestration peut faire moins d'appels et coûter plus cher, c'est arrivé, et c'est la
campagne de l'étape 15 qui l'a mesuré.

⚠️ **La règle du tout ou rien ne bouge pas d'un cran** : les jetons s'effacent avec le
ratio dès qu'une prise du jeu n'a pas d'`usage`. `v1-etape12` (0/19) et `v1-base` (3/31)
continuent d'afficher « non disponible » sur les trois lignes. Et la comparaison publie
l'écart des jetons **sans verdict de dispersion**, pour la raison qui vaut déjà pour les
appels : un coût figé à l'enregistrement n'a pas de dispersion, et un verdict calculé dessus
serait faux avec l'air d'un résultat.

### La mesure nº8 — les tests de conduite du dialogue. **Ce n'est pas non plus un critère.**

Ajoutée au jalon 1 de l'étape 15, et c'est la seule mesure de l'étape qui **ne coûte aucun
appel, ne dépend d'aucun tirage, et sépare avec certitude** : combien de tests de conduite
du dialogue tournent dans `make check` chez l'une et chez l'autre orchestration.

| Orchestration | Tests de conduite dans `make check` |
|---|---|
| Agent (étape 8) | **0** |
| Machine à états (étape 15) | **17 tests de conduite du dialogue** |

Le zéro n'est pas une mesure refaite pour l'occasion : il est écrit au §7 depuis l'étape 8,
ligne « le faux client teste la boucle, pas le modèle » — *un défaut de conduite du dialogue
passe entièrement à travers `make check` ; un agent qui interrogerait le client six fois de
suite ferait une suite verte.*

Le seize est **dérivé de la suite**, jamais recopié : `tests/machine/test_mesure_8.py`
compte les tests de `tests/machine/test_conduite.py` qui citent la règle qu'ils vérifient,
et relit ce document et le `README.md` contre ce compte. Un test de conduite ajouté sans
mise à jour des documents fait échouer `make check`.

> ⚠️ **Ce que ces tests ne prouvent pas.** Ils vérifient que la machine conduit le dialogue
> **comme on l'a écrit**. Ils ne vérifient **pas que la conduite est bonne**, ni que le modèle qui
> rédige derrière respecte quoi que ce soit. La machine rend testable **sa propre décision**, pas
> la conversation. Sans cette réserve, « 17 contre 0 » serait le double standard que l'étape 13
> s'est reproché sur la métrique nº3.

C'est §3.6 qui rend la mesure possible, et il l'avait annoncée en creux : « la testabilité
par tests unitaires rapides disparaît en grande partie — il n'y a plus de fonction de
décision pure à assertionner ». `raiyon/machine/decision.py` est cette fonction.

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

> **Amendement de l'étape 8 — `ANTHROPIC_API_KEY` n'est plus obligatoire au démarrage.**
> Cette étape avait posé la clé en champ requis de `Settings`, au nom d'« échouer tôt ».
> **La décision était raisonnable à ce moment-là**, et il ne s'agit pas de réécrire
> l'histoire : le plan prévoyait alors une passe LLM dans le pipeline de l'étape 5, donc
> tout chemin qui ouvrait la configuration menait effectivement à un appel API. Exiger la
> clé au démarrage revenait à échouer tôt sur une dépendance réelle.
>
> **Ce qui l'a renversée est §3.4ter**, qui a supprimé la passe B et avec elle le seul
> appel LLM du chemin de données. À partir de là, `make seed`, `make seed-build` et
> `make calibrer` — du code déterministe de bout en bout — réclamaient une clé qu'ils
> n'utilisent jamais. `scripts/seed_charger.py` portait d'ailleurs la conséquence en
> docstring depuis l'étape 5, en attendant l'arbitrage : *« cette commande réclame une clé
> qu'elle n'utilisera jamais »*. C'était devenu un **mensonge sur la dépendance**, celui-là
> même que la suppression de la passe LLM avait fait disparaître ailleurs.
>
> Le principe ne change pas, son objet si : on échoue tôt **sur ce qui est réellement
> requis**. `anthropic_api_key` est `SecretStr | None`, et `cle_api()` est le **seul site
> de déballage** — il lève une `ConfigurationError` qui nomme les commandes concernées.
> Seules `make chat` et `make fumee` en ont besoin.

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

### Étape 6 — Moteur de matching ✅

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

**Franchie.** 147 tests purs en 0,14 s, 28 tests d'intégration sur le catalogue réel,
`make check` et `make test-int` verts. Les quatre cas limites du rapport de seed (G1 à
G4) sont couverts par des tests qui **citent les identifiants en dur** : s'ils
changent, un test casse, et c'est le comportement voulu.

Sept modules, et la frontière de §3.16 se lit dans leurs noms :

```
src/raiyon/matching/
    attributs.py      # registre : rôles, genres, bornes, libellés — la traduction
                      #   exécutable de catalogue/schema_attributs.md
    criteres.py       # Critere, Importance, Operateur, Optimisation, RequeteMatching
    depot.py          # protocole DepotProduits + DepotSql — la seule moitié qui parle SQL
    score.py          # sous-scores, renormalisation, pondération, classement — pur
    trace.py          # dataclasses de trace — pur
    relachement.py    # diagnostic et propositions, sur comptages injectés — pur
    moteur.py         # orchestration, et le résultat typé
scripts/calibrer_bornes.py
```

#### Les treize arbitrages

**A — La frontière SQL / Python.** Consignée en décision numérotée : voir §3.16.

**B — Le modèle de critères est générique, pas typé par catégorie.** Une liste de
`Critere(champ, opérateur, valeur, importance)`, validée dynamiquement contre le
registre. *Alternative écartée — six modèles Pydantic typés, miroirs de `SpecsCpu`,
`SpecsMoniteur`…* Ils donnent du typage statique et de meilleurs messages d'erreur,
mais créent six modèles à maintenir en parallèle de six modèles de specs — divergence
garantie à la première évolution du schéma — et un schéma JSON d'outil énorme à
l'étape 7. Le générique paie en typage ce qu'il gagne en surface, et **le registre
récupère la validation**.

**C — Le registre est un module, et un test garde sa cohérence.**
`matching/attributs.py`, écrit à la main depuis `schema_attributs.md`. Un test vérifie
que ses clés couvrent **exactement** les champs de `schemas.py`, catégorie par
catégorie ; un autre relit `data/seed/rapport_seed.md` et compare les taux de
remplissage. Les champs `affichage` (`color`, `nom`, `id`) y figurent **avec leur
rôle**, pas omis : c'est ce qui permet de prouver qu'ils ne filtrent ni ne scorent, au
lieu de constater qu'on les a oubliés. *Alternative écartée — annoter `schemas.py` via
`Field(json_schema_extra=…)`.* Une seule source, aucune divergence possible ; écartée
parce qu'elle charge le miroir du schéma SQL d'une préoccupation de matching, et que
`schemas.py` cesserait d'être lisible comme ce qu'il est.

**D — Rétrogradation ouverte sur le gradué, fermée sur la compatibilité, promotion
interdite.** Un `souhait` sur un filtre dur **gradué** devient un score. La
rétrogradation est fermée sur les attributs de compatibilité, qui sont binaires
(`ddr_generation`, `interface`, `form_factor`, `type`, `chipset`, `microarchitecture`,
`aspect_ratio`, plus `prix_usd` et `categorie`) : « plutôt de la DDR5 » n'est pas un
souhait, c'est un malentendu — de la DDR4 n'entre pas dans le socket. La liste vit dans
le registre, en drapeau `retrogradable`, jamais dans les arguments d'un appel. **La
promotion inverse lève** : un `bloquant` sur un attribut de rôle `score` est une erreur
explicite, parce que promouvoir `boost_clock` (66,1 % de remplissage) en filtre dur
exclurait un tiers du catalogue sur une absence de donnée — un comblement d'absence par
la porte de derrière, que §3.4quater interdit. Toute rétrogradation appliquée entre dans
la trace ; elle ne contourne jamais le critère nº6. *Alternative écartée — rôle absolu.*
Totalement prévisible et sans risque de desserrage, mais le moteur produirait des
zéro-résultats sur de simples préférences, et l'agent n'aurait aucun moyen d'exprimer la
nuance.

**E — NULL sur un filtre dur : exclure **et compter**.** `(specs->>'refresh_rate')::int
>= 144` écarte les écrans sans valeur ; la sémantique SQL est conservée, mais elle cesse
d'être silencieuse. Le moteur rend `ecartes_faute_de_donnee: {"refresh_rate": 7}`, champ
**toujours présent**, vide quand il n'y a rien à dire. Trois conditions : le compteur
paie sur le zéro résultat (si `rouvre_si_retire == ecartes_faute_de_donnee`, le
diagnostic est `donnee_absente` et non `critere_trop_strict`) ; la liste des attributs
incomplets n'est pas devinée mais **recopiée des taux mesurés du rapport de seed**, donc
aucune requête n'est émise sur un attribut à 100 % ; et le compteur sort du **même
constructeur de prédicat** que le filtre — deux requêtes écrites séparément dériveraient.
*Alternative écartée — exclusion silencieuse.* Zéro ligne de code, mais on décide que
l'absence vaut « ne satisfait pas » sans jamais le dire, et c'est indétectable en éval.
*Alternative écartée — un troisième ensemble `indetermines`.* Cohérent avec §3.10 sur le
principe, mais il se propagerait jusqu'aux étapes 7, 8 et 9 — le validateur devrait
couvrir trois ensembles — pour 0,4 à 4,1 % des lignes.

*Troisième cas, ajouté après coup : **l'absence expliquée par une autre colonne**.*
L'arbitrage séparait « aucun produit ne fait 144 Hz » de « aucun produit ne déclare sa
fréquence ». Il manquait le cas qui n'est ni l'un ni l'autre.

`internal-hard-drive.rpm` est renseigné à 33,9 %, et ces 33,9 % **sont** la part de HDD
du seed. Un SSD n'a pas de vitesse de rotation ; `SpecsDisqueInterne._coherence_type_rpm`
l'impose déjà à l'insertion. Sans traitement particulier, le chemin était mécanique :
« 7 200 tr/min en M.2 PCIe » → zéro produit → les 40 disques rouverts par le retrait de
`rpm` égalaient le compteur d'exclusions → diagnostic `donnee_absente` → l'étape 8
aurait écrit « ces disques ne déclarent pas leur vitesse de rotation ». C'est faux : ils
n'en ont pas. **Le moteur fabriquait une affirmation sur le catalogue**, dans le module
dont c'est précisément la raison d'être (§2).

Le registre porte donc `explique_par`, et le diagnostic un quatrième motif,
`absence_structurelle`. Deux points importent :

- **le drapeau n'est pas une opinion sur un taux de remplissage.** Il se pose quand une
  autre colonne **détermine** l'absence, ce qui est vérifiable par la machine : à
  l'intérieur de chaque valeur de `type`, `rpm` est soit toujours présent, soit toujours
  absent. Un test le constate sur les 1 026 lignes du seed, il ne le documente pas ;
- **`cpu.boost_clock` ne le porte pas**, alors qu'il est plus creux (66,1 %). Son
  absence est *corrélée* à la génération du processeur — aucune colonne ne la
  *détermine*, et un test le vérifie sur les quatre vocabulaires fermés de la catégorie.
  C'est exactement la ligne de partage de §3.4quater : calcul déterministe contre
  supposition.

Conséquence : `rpm` sort du compteur `ecartes_faute_de_donnee` — les SSD ne sont pas des
disques dont la donnée manque — mais **le filtre ne bouge pas** : un client qui demande
7 200 tr/min ne reçoit toujours pas de SSD. Le drapeau change ce que le moteur *dit*,
pas ce qu'il *rend*.

*La condition du troisième cas n'est pas le drapeau seul.* La première version du
correctif rendait `absence_structurelle` dès que l'attribut portait `explique_par`, et
présentait comme une « limite assumée » le fait qu'il ne distinguait pas, parmi les
produits rouverts, ceux que le seuil écartait de ceux auxquels l'attribut ne s'applique
pas. Ce n'était pas une limite : c'était **le même défaut, déplacé d'une branche**.
Mesuré sur le seed — `rpm >= 7200` dans un budget de 25 USD : zéro résultat, mais six
disques tiennent dans ce budget et **deux d'entre eux tournent à 5 400 tr/min**
(`internal-hard-drive-696751738a` à 14,21 USD et `internal-hard-drive-aa72d12add` à
19,67 USD). Le moteur allait faire dire « vous avez demandé un disque mécanique » quand
la phrase juste est « il y en a, mais aucun à 7 200 tr/min ».

La condition retenue est donc **le drapeau et l'absence de valeur atteignable**, cette
dernière étant déjà calculée par le dépôt : la plus proche réellement présente parmi les
produits qui satisfont tous les autres critères. Elle existe → l'attribut s'applique bien
à une partie du catalogue accessible, le critère est seulement trop strict ; elle vaut
`None` → aucun produit rouvert ne déclare l'attribut, l'absence est structurelle. Les
trois branches de `_motif_du_retrait` répondent alors à **une seule question** — les
produits que ce retrait ferait remonter, qu'ont-ils à voir avec ce critère ? — au lieu
d'une exception en tête de fonction suivie de deux cas généraux.

Ce qu'il faut en retenir, et c'est la troisième fois dans cette étape : un attribut peut
être structurellement inapplicable à une partie du catalogue **et** trop strictement
demandé sur le reste. Les deux propriétés cohabitent sur le même champ, dans la même
requête, et elles n'appellent pas la même phrase.

**F — NULL sur un attribut scoré : retirer le critère et renormaliser.** Un sous-score
de 0 punirait une donnée manquante, un sous-score de 0,5 inventerait une médiane. Le
critère est donc retiré du calcul, les poids restants renormalisés, et la trace porte
`indisponible`. ⚠️ **C'est le point fragile de l'étape, et il est écrit :** un produit à
données manquantes a mécaniquement moins d'occasions de perdre des points. Garde-fou —
à score égal, le produit dont **plus de critères ont été réellement évalués** passe
devant, et la trace expose ce compte (`criteres_evalues`, `criteres_indisponibles`).
Voir aussi la ligne ajoutée au §7.

**G — Bornes de normalisation absolues, jamais relatives au lot.** Chaque attribut
numérique porte dans le registre une borne basse et une borne haute **constantes** ; un
sous-score vaut `(valeur - basse) / (haute - basse)`, borné à `[0, 1]`. Les queues
lourdes sont winsorisées aux 5ᵉ et 95ᵉ centiles, calculés **une fois** sur le seed
committé par `scripts/calibrer_bornes.py` et recopiés en constantes — jamais recalculés
au runtime, sinon c'est du min-max déguisé. Un test vérifie que le script redonne
exactement les constantes du registre. *Alternative écartée — min-max sur le lot
candidat.* Contraste toujours plein, mais le score d'un produit dépendrait des produits
présents à côté de lui : deux conversations classeraient le même produit différemment,
et les tests deviendraient sensibles à leur fixture.

*Direction du sous-score : la règle a été écrite deux fois avant d'être juste, et les
deux versions fausses valent d'être gardées.* La règle qui tient est :

> **L'opérateur décide de la satisfaction ; le `sens` du registre ordonne à l'intérieur
> de la région satisfaisante.**

Il a fallu deux défauts symétriques pour y arriver, et les écrire vaut mieux que
n'exposer que la conclusion — c'est le même piège qui attend le prochain raffinement.

**Défaut nº1 — le `sens` seul.** C'est ce que l'arbitrage énonçait au départ : le
sous-score vaut `(valeur - basse) / (haute - basse)`, inversé si `sens =
plus_bas_mieux`. Sur « un écran d'**au plus** 24 pouces », `screen_size` porte
`plus_haut_mieux` : le 65 pouces sortait en tête d'une demande qui l'excluait.

**Défaut nº2 — l'opérateur seul.** Le correctif livré à l'étape faisait décider la
direction par l'opérateur (`au_plus` → `1 - normaliser(valeur)`). Il corrigeait le
premier défaut et produisait exactement le symétrique. Sur les mêmes bornes calibrées
`[21,5 ; 34]` :

| dalle | sous-score | rang |
| ---: | ---: | --- |
| 21,5″ | 1,00 | 1er |
| 24″ | 0,80 | après |

Le client qui pose un plafond veut **le plus grand qui rentre**, pas le plus petit qui
existe. Le défaut valait partout où un `au_plus` rencontre un attribut de `sens =
plus_haut_mieux` : `screen_size`, `video-card.length` (« 300 mm maximum, mon boîtier »),
`capacity`, `video-card.memory`, `core_count`.

**Pourquoi la suite ne l'a pas vu.** Le test qui gardait ce point portait sur `cpu.tdp`,
dont le `sens` est `plus_bas_mieux` : l'opérateur et le registre y disent déjà la même
chose. Le seul cas qui révèle le problème est celui où ils **divergent**, et il n'était
pas couvert. Un test l'exerce désormais, et le tableau des quatre configurations est en
docstring de `sous_score_numerique` — trois de ses lignes passent avec l'une **ou**
l'autre des deux règles fausses, la quatrième les sépare.

**La règle qui tient**, en deux régions : une valeur qui satisfait le critère marque
dans `[0,5 ; 1]`, ordonnée par le `sens` du registre **sur la portion de bornes que le
critère admet** ; une valeur qui ne le satisfait pas marque dans `[0 ; 0,5[`,
décroissant avec l'écart au seuil. La frontière est stricte dans les deux sens. Un seuil
hors bornes ne casse rien : la région satisfaisante peut être vide ou couvrir toute
l'échelle, le sous-score reste dans `[0, 1]` et rien n'est divisé par zéro.

`egal` ne relève d'aucune des deux : la proximité à la valeur demandée reste la seule
sémantique correcte, et le `sens` n'y a rien à faire.

**Conséquence sur le `sens` :** il redevient porteur sur les critères eux-mêmes, et pas
seulement dans le score technique de repli du rapport qualité/prix. Le « `sens` a failli
être une constante décorative » noté plus bas reste vrai de la version livrée à
l'étape ; il ne l'est plus. Le caractère **absolu** — ce que l'arbitrage protège
réellement — n'a jamais bougé : rien, dans aucune des trois versions, ne dépend du lot.

**H — Le prix : deux intentions distinctes, et un plafond.** Par défaut, le prix est un
**filtre dur seul** (le budget) et n'intervient au classement que comme critère de
**départage**. Il ne devient un sous-score que sur demande explicite, et il y a **deux
demandes** : `moins_cher` (sous-score décroissant avec le prix) et
`rapport_qualite_prix` (score technique ÷ prix). Sur `internal-hard-drive` et `memory`,
la source donne déjà `price_per_gb` et l'étape 5 l'a recalculé sur le prix retenu : il
est utilisé tel quel. Sur les quatre autres catégories, le ratio est calculé et ramené
dans `[0, 1]` par un **plafond constant du registre** (`1 / P5(prix)`), pas par le
maximum du lot — sans quoi la dépendance au lot reparaîtrait sur ce seul sous-score.
Deux règles dures : le poids du sous-score de prix est **plafonné à 0,5**, strictement
sous le poids du plus faible critère technique (un `souhait` pèse 1), de sorte qu'un
produit qui rate complètement un critère énoncé ne peut pas repasser devant par le prix
seul — sinon « je veux 144 Hz et pas trop cher » finit sur un 60 Hz bon marché ; et
**toute position gagnée par le prix apparaît dans la trace** (`rang`,
`rang_sans_le_prix`), parce que le prix compte déjà deux fois — le budget borne, le score
ordonne — et que c'est volontaire, donc ça s'écrit.

**I — La trace est structurée ; le français est du vocabulaire, pas des phrases.** Par
produit et par critère : `champ`, `role_applique`, `statut` ∈ {`matche`, `partiel`,
`rate`, `indisponible`}, `valeur_produit`, `valeur_demandee`, `ecart`, `poids`,
`sous_score`, `retrograde`. Aucune phrase rédigée, aucune valeur pré-formatée pour
l'affichage — la mise en forme est l'affaire de l'étape 11. Mais le registre porte un
**libellé français par attribut** (`refresh_rate` → « fréquence de rafraîchissement ») et
son unité, et la trace les transporte : c'est le raisonnement de §3.4ter appliqué ici, du
français dérivé d'un **champ** est déterministe, donc c'est de la donnée. Le repli sur
template de §3.11 niveau 3 en aura besoin ; le laisser hors du registre reviendrait à le
redécouvrir à l'étape 9. Un test le garde de façon mécanique : **toute chaîne présente
dans une trace vient du registre, d'une énumération du module, ou du catalogue.**

**J — Zéro résultat : diagnostic, puis proposition — jamais application.** Analyse par
retrait d'un critère à la fois, plus, pour les critères numériques, la **valeur
atteignable** la plus proche. Cinq règles : la valeur proposée est **prise dans le
catalogue** — la plus proche effectivement présente parmi les produits qui satisfont
tous les autres critères, jamais un seuil rond calculé, qui rendrait encore zéro et
affirmerait sur le stock un fait qui n'en est pas un ; l'ordre des suggestions suit
l'importance déclarée puis le nombre de produits rouverts, un critère de compatibilité
venant **en dernier** avec un drapeau `dernier_recours` que l'étape 8 lira ; si le
critère bloquant est le budget, la réponse est l'ensemble `au_dessus_du_budget` de §3.10
et `prix_usd` est exclu des candidats au retrait ; si aucun retrait unique n'ouvre le
catalogue, le moteur le dit (`aucun_retrait_simple`) — les combinaisons de degré 2 sont
hors périmètre, et leur absence est une réponse, pas un silence ; et la suggestion reste
une **proposition**, le moteur ne l'applique jamais de lui-même.

**K — Un tour, une catégorie.** Tous les produits rendus par un appel appartiennent à une
seule catégorie, et la catégorie est obligatoire. Il n'y a ni panier, ni budget alloué,
ni somme suivie d'un tour à l'autre : l'invariant se vérifie en une ligne, et il **est**
vérifié — le moteur lève si un produit d'une autre catégorie remonte. Une « config
gaming » est ainsi structurellement impossible à servir en un tour. Ce n'est pas au
moteur de refuser une telle demande : l'étape 8 la séquencera (« je conseille un
composant à la fois — on commence par la carte graphique ? »). Conséquences en §8 et
amendement de §3.6.

**L — Comparaison des textes : égalité stricte.** Sur les énumérations (`chipset`
241 valeurs, `microarchitecture` 33, `interface` 18…), égalité stricte et jamais de
`contains` : sinon « RTX 4070 » attrape silencieusement « RTX 4070 Ti » et le critère
nº4 se dégrade sans qu'on le voie. C'est cohérent avec §3.7 — `probe_catalog` rendra les
valeurs distinctes, l'agent choisira dedans. Ces égalités passent par une containment
`@>`, servie par le GIN `jsonb_path_ops` : c'est le seul endroit où l'index de §3.3bis
travaille réellement. Seule exception, `marque`, que le client tape à la main :
comparaison sur une clé normalisée (minuscules, ponctuation retirée), écrite **une fois,
en SQL**, et appliquée aux **deux côtés** de l'égalité plutôt que dupliquée en Python —
deux implémentations d'une même normalisation dérivent, et la divergence se voit sur un
cas rare, tard.

**M — L'ordre est total et déterministe.** `(score décroissant, nombre de critères
évalués décroissant, prix croissant, id croissant)`. Aucun ex æquo ne subsiste, aucun
classement ne dépend de l'ordre de retour de Postgres, et les tests peuvent asserter une
liste exacte.

#### Note de performance, avec son seuil de bascule

Les n+1 requêtes de comptage du relâchement se ramènent à une seule avec
`count(*) FILTER (WHERE …)`. À 1 026 lignes et une poignée de critères, le gain est nul :
on garde la version lisible. La bascule est documentée en commentaire dans `depot.py`,
avec sa condition de déclenchement — un changement d'ordre de grandeur du catalogue, ou
un appel du moteur dans une boucle. C'est le même compromis explicite que §3.3bis.

#### Ce que l'étape a appris, et qui n'était pas prévu

- **La winsorisation ne corrige pas une queue lourde, elle en corrige une énorme.**
  `memory.price_per_gb` a une borne haute calibrée à **13,375 USD/GB** pour un maximum
  observé de **497,5** : le 95ᵉ centile est 37 fois sous le maximum. Sans plafonnement,
  ce seul produit aurait tassé les 170 autres dans un intervalle de 2,7 % de l'échelle.
  L'ordre de grandeur de l'écart n'était pas anticipé — `schema_attributs.md` demandait
  de « borner le sous-score », il ne disait pas de combien.
- **Le comptage des NULL concerne trois filtres durs incomplets, mais deux seulement
  se comptent.** Le cadrage annonçait `monitor.refresh_rate` (95,9 %) et
  `video-card.length` (96,5 %). La mesure ajoute `internal-hard-drive.rpm`, à **33,9 %**
  — et son absence n'est pas une lacune : elle vaut exactement la part de SSD du seed
  (113 sur 171). La première version de l'étape le comptait quand même, au motif qu'un
  client demandant 7 200 tr/min a bien perdu les SSD en chemin. C'était vrai du
  **filtre** et faux du **diagnostic** : voir le troisième cas de l'arbitrage E, qui a
  fait naître `explique_par` et le motif `absence_structurelle`.
- **G2 est un cas de départage moins pur que le rapport de seed ne le disait.** Le
  rapport annonce « toutes les specs identiques, sauf le prix et `color` ». C'est exact
  **pour le JSONB**, et faux pour la ligne entière : `headphones-06acf63b59` est un
  Pyle Audio, `headphones-393cd46c64` un Logitech, et `marque` est un **filtre dur**.
  Sans critère de marque, le départage se fait bien sur le prix, et le cas exerce ce
  qu'il devait exercer ; avec un critère de marque, ce n'est plus un départage, c'est un
  filtre. Le test le dit explicitement plutôt que de laisser croire à deux produits
  interchangeables — et `data/seed/rapport_seed.md` porte la nuance depuis le correctif,
  émise par le générateur lui-même (`CasLimiteG2` transporte les deux marques) : une
  note ajoutée à la main dans un fichier généré disparaît à la première régénération.
- **Un `dans_les_specs` oublié rend zéro produit sans lever.** Les colonnes communes
  (`marque`, `categorie`…) ne vivent pas dans le JSONB. Le drapeau qui le dit avait été
  écrit sur `prix_usd` et oublié sur les cinq autres : la containment cherchait alors
  `specs->'marque'`, une clé inexistante, et le filtre rendait zéro produit **sans la
  moindre erreur**. Trouvé par le test d'intégration sur la marque. Le drapeau est
  désormais posé par la construction du registre, pas recopié entrée par entrée — et un
  test garde cette construction. C'est le mode d'échec le plus désagréable qui soit : un
  filtre qui marche, et qui a tort.
- **Le `sens` du registre a failli être retiré pour inutilité — et c'est lui qui
  manquait.** Le premier correctif de l'arbitrage G faisait décider la direction par
  l'opérateur seul, ce qui laissait le `sens` sans emploi hors du rapport qualité/prix ;
  il a bien failli passer pour une constante décorative. Le second correctif a montré
  qu'il portait exactement la moitié manquante de la règle : l'ordre **à l'intérieur**
  de la région satisfaisante. Une constante qu'aucun code ne lit est suspecte ; avant de
  la retirer, il vaut la peine de chercher ce qu'elle devrait porter.

#### Pour l'étape 7 — l'importance d'un critère est **collante** en session

Un critère déclaré `bloquant` ne peut pas être re-déclaré `souhait` par le modèle seul
lors d'un appel suivant : seule une nouvelle parole du client le change. Sans cette
règle, le zéro résultat devient une incitation à assouplir en douce, exactement ce que
§3.6 cherche à empêcher — l'agent essaierait jusqu'à trouver quelque chose à montrer.

**Ce n'est pas implémenté à l'étape 6**, et c'est délibéré : la fusion des critères d'un
tour à l'autre appartient à la couche outils. L'étape 6 écrit seulement ce que cette
couche aura besoin de lire — le drapeau `retrogradable` du registre, et la trace des
rétrogradations effectivement appliquées.

> **Suite à l'étape 7 : la règle est devenue §3.17, et elle a changé de portée.** Écrite
> ici pour la seule **importance**, elle ne couvrait pas le mode d'échec principal :
> après un zéro résultat, reculer un seuil obtient exactement ce que la rétrogradation
> obtenait, sans toucher à l'importance. La règle porte désormais sur le **mouvement**.

---

### Étape 7 — Couche outils et invariants ✅

Les outils du §3.7, chacun comme une fonction Python testable, avec leur schéma JSON
d'entrée. C'est ici que vivent les garanties.

**Le plan de l'étape a changé d'architecture en cours de route, et il faut le dire.** Le
texte initial annonçait ceci :

> - `search_products` **clampe** les critères du LLM contre `session.validated_criteria` ;
> - `probe_catalog` ne peut structurellement pas rendre de produit ;
> - les critères de session sont dérivés des arguments d'appel et fusionnés par le code.

Le premier point n'a pas été réalisé, et pas par manque de temps : **il a été écarté**
(arbitrage C). Clamper suppose qu'un critère hostile entre, puis qu'une garde l'arrête —
une garde à écrire, à tester, et à ne jamais oublier sur un futur outil. Les critères
entrent désormais par **une seule porte**, et les outils de recherche n'ont plus
d'argument de critère du tout. Le deuxième point est tenu, et vérifié **sur le type de
retour**. Le troisième l'est aussi, avec une règle que l'étape 6 n'avait pas prévue : la
règle de collant, promue en décision numérotée (§3.17).

**Franchie.** 474 tests purs en 2,8 s, 62 tests d'intégration, `make check` et
`make test-int` verts. La couche outils ne charge pas le SDK `anthropic` — vérifié
module par module, découverts sur le disque, dans un interpréteur neuf.

```
src/raiyon/tools/
    erreurs.py         # OutilRefuse : un code, un message écrit pour le modèle
    etat.py            # EtatSession, desserre(), fusionner(), forme du JSONB — pur
    schema_outils.py   # le schéma JSON dérivé du registre — pur
    outils.py          # les cinq outils, et une seule fonction de sérialisation
src/raiyon/matching/
    depot.py           # étendu : comptages, bornes de prix, distributions
    sondage.py         # entropie, troncature, champ le plus discriminant — pur
```

#### Les dix arbitrages

**A — La règle de collant est portée par un jeton de parole par tour client.** Consignée
en décision numérotée : voir §3.17. *Alternative écartée — exiger une citation verbatim
d'un message `user`* : elle donne l'illusion d'une preuve, le modèle pouvant citer une
parole prononcée à propos d'un autre critère.

**B — Une règle unique : desserrer consomme, resserrer est libre.** Une seule fonction
pure, `desserre(avant, apres, attribut)`, dérivée de l'opérateur et du registre. Le
verdict est un **OU**, pas un ET : un mouvement qui desserre par la valeur en resserrant
par l'importance consomme le jeton, parce que la question posée est « **peut**-il faire
remonter un produit ? » et non « le fait-il à coup sûr ? ». *Alternative écartée —
comparer les ensembles de produits satisfaits.* Exacte, et elle rendrait la question
décidable au lieu d'approchée ; écartée parce qu'elle exige d'interroger le catalogue,
donc de rendre impure la seule règle du projet dont on veut pouvoir prouver qu'elle ne
dépend de rien.

**C — Les outils de recherche ne prennent aucun critère.** C'est l'arbitrage structurant
de l'étape. `probe_catalog`, `suggest_next_question` et `search_products` n'ont **aucun**
argument de critère, de budget ni de catégorie : ils lisent l'état de session.
*Alternative écartée — les outils prennent des critères et le code les clampe contre la
session (l'esquisse de §3.6).* Un tour de moins, mais l'invariant redevient une garde à
écrire, à tester et à ne jamais oublier sur un futur outil. Le raisonnement retenu est
celui de §3.10 sur le budget : **une contrainte qui n'a qu'un seul chemin ne peut pas
diverger d'elle-même.** La porte de sortie de l'étape change alors de nature — « les
arguments hostiles ne franchissent pas l'invariant » devient « il n'existe pas d'argument
par lequel passer », et cela se teste sur des **signatures**. ⚠️ À dire honnêtement : on
ne supprime pas la garde, on la **concentre** dans `record_criteria`, qui devient le seul
endroit où la règle de collant mord. Conséquence sur §3.7, qui porte l'amendement : les
quatre outils deviennent cinq.

**D — L'état est indexé par catégorie ; le budget est global et remis à `None` au
changement de catégorie.** Un client qui revient à l'écran retrouve ce qu'il avait dit.
Cela ne crée **aucun panier** : aucune somme n'est suivie, l'invariant « un tour, une
catégorie » tient, et §8 reste vrai mot pour mot. Le budget garde sa **colonne**
(`sessions.budget_usd`) et n'est pas dupliqué dans le JSONB — deux copies divergent.
*Alternative écartée — le budget survit au changement de catégorie.* Une question de
moins à poser, donc une métrique nº3 flattée ; mais un client qui a dit « 300 $ pour
l'écran » verrait cette contrainte s'appliquer à son SSD, c'est-à-dire une contrainte
qu'il n'a jamais posée — ce que §2 interdit, appliqué à un critère au lieu d'un fait.
*Alternative écartée — un état plat, vidé à chaque changement de catégorie.* Plus simple
d'une ligne, mais il perd ce que le client a déjà dit et forcerait une migration du JSONB
dès que le besoin apparaîtrait. Forme arrêtée :

```json
{
  "categorie_courante": "monitor",
  "criteres": {
    "monitor": [{"champ": "refresh_rate", "operateur": "au_moins",
                 "valeur": "144", "importance": "bloquant"}],
    "video-card": []
  },
  "optimisation": "aucune",
  "tour_du_dernier_desserrage": 3
}
```

**E — Un tour, une catégorie : la garde vit ici.** Le moteur garantit qu'**un appel** rend
une seule catégorie ; il ne garantit rien sur **un tour**. `search_products` refuse donc
une recherche sur une catégorie différente de celle déjà cherchée dans le même tour
client, avec un message qui dit à l'agent de séquencer. `probe_catalog` et
`suggest_next_question` restent libres : ils ne rendent aucun produit, donc ils ne peuvent
rien faire citer. C'est ce qui rend le critère d'acceptation nº2 vérifiable **produit par
produit**, sans notion de panier.

**F — Un schéma JSON unique, et `valeur` est toujours une chaîne.** L'`enum` des champs
est l'**union** des champs utilisables des six catégories — 36 entrées — et la validation
par catégorie se fait à l'exécution, avec le message du registre. *Alternative écartée —
un schéma par catégorie* : l'`enum` serait plus courte et le modèle se tromperait moins,
mais la définition des outils changerait en cours de conversation, ce qui **casse le cache
de prompt** (§3.13) à chaque fois que le client change de sujet. *Alternative écartée pour
`valeur` — une union `bool | number | string`* : mal supportée par le sous-ensemble de
JSON Schema admis en mode `strict`, et le précédent existe déjà — le JSONB sérialise les
`Decimal` en chaînes pour la même raison. Les descriptions des champs sont **dérivées** de
`libelle_fr` et `unite`, et un test vérifie que le schéma couvre **exactement** les champs
utilisables du registre.

> **Ce qui a été vérifié sur `strict`, et ce qui ne l'a pas été.** Le projet s'est fait
> piéger trois fois par une capacité supposée disponible et jamais vérifiée (`smt` à
> l'étape 3, `temperature=0` et `nom_fr` à l'étape 5). Donc, mesuré :
> `anthropic==1.1.0` **porte** `strict: bool` sur `ToolParam`, hors beta, documenté
> « When true, guarantees schema validation on tool names and inputs » ; en revanche, **le
> sous-ensemble de JSON Schema admis sous ce drapeau n'est écrit nulle part dans le paquet
> installé**, et l'étape 7 n'appelle pas l'API. Le schéma reste donc dans un sous-ensemble
> volontairement pauvre — `type`, `enum`, `description`, `properties`, `required`,
> `items`, `additionalProperties: false` — qu'un test vérifie en parcourant l'arbre, et
> `schema_des_outils(strict=False)` existe **dès maintenant**, avec son log : le jour où
> l'API refuse une définition, le repli est un argument, pas une séance de débogage au
> milieu de l'étape 8.

**G — `probe_catalog` : agrégats exacts, troncature déclarée, budget appliqué.** C'est ici
que la leçon de l'étape 6 mord — du code qui décide de ce qui sera **affirmé** au client.
Le budget s'applique, sinon « il te reste 12 modèles » désigne des produits que le client
ne peut pas acheter ; par symétrie avec §3.10, le sondage rend **deux comptes séparés**,
dans le budget et dans la zone de tolérance. La troncature se déclare : 241 chipsets ne
rentrent pas, l'outil rend les 15 valeurs les plus fréquentes **et** `total_distinct`
**et** `tronque`, toujours présents — même contrat que `ecartes_faute_de_donnee` au §3.16.
L'ordre est total : fréquence décroissante, puis valeur croissante, **décidé en Python**
pour qu'aucune réponse client ne dépende de l'ordre de retour ni de la collation de
Postgres. *Alternative écartée — rendre des paliers arrondis pour empêcher l'agent de
déduire un prix exact.* ⚠️ Le risque est réel et il est au §7 ; mais un arrondi est
lui-même une affirmation approximative sur le catalogue, et il en fabrique une pour en
éviter une autre. La contrainte est portée par le prompt de l'étape 8 et vérifiable à
l'étape 9.

**H — `suggest_next_question` : entropie pondérée par la couverture, et le budget en cas
spécial.** Elle ne rend **aucune phrase** : champ, libellé, unité, valeurs atteignables et
score — l'agent écrit la question (§3.14, arbitrage I de l'étape 6). La mesure est
l'**entropie de Shannon normalisée** sur la distribution des valeurs du sous-catalogue
courant, **multipliée par le taux de couverture réel** ; sans cette pondération, l'outil
proposerait de demander une vitesse de rotation à un client dont 66 % des candidats sont
des SSD, et la réponse écarterait des produits sur une **absence de donnée**.
*Alternative écartée — « le champ qui coupe le plus près de la moitié »* : correct sur un
booléen, inutilisable au-delà de deux valeurs. Si `budget_usd is None`, l'outil rend le
budget **en tête**, dans un champ typé distinct — `prix_usd` est dans
`CHAMPS_A_CHAMP_DEDIE`, le déguiser en attribut rouvrirait le second chemin que §3.10
ferme. Répartition §3.16 : `GROUP BY` en SQL, entropie et classement en **Python pur**,
sur des comptages injectables.

**I — `ask_clarification` est un outil terminal.** Il rend `{"ok": true, "terminal":
true}` et **clôt le tour** ; l'étape 8 renverra le texte de son argument au client au lieu
de relancer une génération. *Alternative écartée — le garder tel que §3.7 le décrivait, un
outil qui ne rend rien et n'existe que pour être tracé.* Il force un aller-retour API
supplémentaire et invite le modèle à appeler l'outil **puis** à réécrire la question en
texte : la question est posée deux fois. La question devient ainsi une donnée typée —
utile aussi pour l'événement SSE de §3.12 et pour la métrique nº3, qui est un critère
d'acceptation.

**J — `search_products` rend le produit entier.** Toutes les specs, plus la trace.
*Alternative écartée — réduire le produit aux champs cités par la trace, plus les champs
d'affichage.* Elle rendrait **impossible** d'affirmer une spec dont la pertinence n'a
jamais été établie, et coûterait moins de jetons. Elle est écartée parce qu'elle coupe la
comparaison spontanée (« celui-ci a en plus du HDMI 2.1 »), qui est un bon comportement de
vendeur, et parce que l'étape 9 valide de toute façon ce qui est **cité**. Décision
assumée avec sa contrepartie, pas restriction par prudence.

#### Porte de sortie — franchie

`make check` vert **sans base, sans conteneur, sans clé API** ; `make test-int` vert pour
les agrégats ; les dix-sept portes hostiles fermées (25 cas, `tests/tools/test_hostile.py`),
chacune nommée d'après ce qu'elle empêche ; le test d'isolation confirme qu'aucun module de
`raiyon.tools` ne charge le SDK.

C'est le **critère d'acceptation nº2 franchi au niveau structurel, avant même qu'un LLM
existe dans le projet**.

#### Ce que l'étape a appris, et qui n'était pas prévu

- **Une dérivation naïve peut mentir aussi bien qu'une constante écrite à la main.** Les
  descriptions du schéma sont dérivées de `libelle_fr` et `unite`, et la première règle
  disait : ne pas accoler l'unité si le libellé la porte déjà — « nombre de cœurs en
  cœurs » est ce que donne la version sans règle. Elle testait une **sous-chaîne** :
  « Mo » est dans « mémoire », et l'unité de `internal-hard-drive.cache` disparaissait
  silencieusement, dans un texte que rien d'autre ne relit et que seul le modèle lira. La
  comparaison porte désormais sur les **mots**. La leçon n'est pas « comparer des mots » :
  c'est que **dériver ne dispense pas de vérifier la dérivation**, et que la seule raison
  pour laquelle ce défaut a été vu est qu'un test parcourait les six catégories.
- **Le trou du budget était inter-tours, et la première parade regardait à l'intérieur du
  tour.** La règle « changer de catégorie est gratuit » avait pour garde-fou « un seul
  changement de catégorie par tour ». Elle fermait l'aller-retour dans un même message et
  laissait passer le même aller-retour en deux messages, ce qui coûte au modèle deux
  tours et rien d'autre. La bonne parade n'était pas une seconde règle mais **l'absence
  d'exemption** : l'effacement du budget est un desserrage, il paie comme les autres. Une
  règle qui a besoin d'un garde-fou est souvent une exception qui n'aurait pas dû être
  écrite.
- **Deux `conftest.py` importables entrent en collision, et l'ordre de collecte décide
  lequel gagne.** `tests/matching/` et `tests/tools/` ont chacun le leur, et les deux
  suites faisaient `from conftest import …` : `pytest tests/tools tests/matching` échouait
  à l'import, alors que `pytest` seul passait. Les helpers **importables** vivent
  désormais dans des modules nommés (`produits_de_test.py`, `outils_de_test.py`,
  `isolation_sdk.py`) et les `conftest` ne portent plus que des fixtures, que pytest
  résout par répertoire. Le dépôt avait déjà ce motif avec `base_de_test.py` ; il valait
  la peine de le suivre plutôt que de le redécouvrir.
- **Le champ le plus discriminant du sondage est souvent `marque`, et ce n'est pas un
  défaut de la mesure.** Sur les 32 écrans à 144 Hz sous 400 $, `marque` marque 0,93
  contre 0,73 pour le type de dalle : treize marques bien réparties portent plus
  d'information qu'un choix entre IPS et VA. La mesure a raison, et pourtant « tu as une
  préférence de marque ? » n'est pas toujours la meilleure question de vente. Le gain
  d'information et la valeur conversationnelle ne sont pas le même critère — l'outil rend
  le premier, le prompt de l'étape 8 arbitrera le second. La ligne est au §7.
- **`Decimal("NaN")` et `Decimal("Infinity")` se parsent sans lever.** La conversion des
  valeurs textuelles du schéma passe par `Decimal(texte)` ; « beaucoup » lève bien, mais
  « NaN » aurait donné un critère qui ne satisfait aucune comparaison et un budget qui
  empoisonne tous les tests d'appartenance — sans la moindre erreur. Le contrôle est une
  ligne (`is_finite()`), et il n'existerait pas sans avoir été cherché.

### Étape 8 — Boucle agent et prompt système v1 ✅

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

**Franchie.** 514 tests purs en 3,1 s (dont 37 pour la boucle et le répartiteur), 67 d'intégration,
`make check` et `make test-int` verts — **sans base, sans conteneur et sans clé API**.
Une conversation de bout en bout aboutit à des recommandations de produits réels, et une
session reprise après redémarrage retrouve ses critères.

```
src/raiyon/tools/
    repartiteur.py         # nom d'outil → fonction, pur, aucun import anthropic
    erreurs.py             # + CodeRefus.OUTIL_INCONNU
src/raiyon/agent/
    client.py              # Protocol ClientLLM, dataclass ReponseLLM
    client_anthropic.py    # SEUL module qui importe anthropic ; repli strict
    evenements.py          # les sept événements typés, dataclasses frozen
    prompts.py             # chargement versionné + empreinte sha256
    boucle.py              # repondre() : générateur d'événements
    session.py             # lecture/écriture de sessions et tours_conversation
prompts/systeme.v1.md      # onze sections, rien de dynamique
scripts/console.py         # make chat        scripts/fumee.py  # make fumee
```

#### Les douze arbitrages

**1 — La boucle rend des événements typés, mais n'appelle pas `messages.stream()`.**
`client.messages.create()`, et un générateur d'`Evenement` = `CriteresMisAJour | Sondage
| QuestionSuggeree | ProduitsTrouves | QuestionPosee | Texte | Repli`. *Alternative
écartée — streamer dès maintenant* : la console serait plus vivante, mais on paierait
l'accumulation des deltas de `tool_use` en JSON partiel dans l'étape qui fait déjà le
premier appel API du projet. *Alternative écartée — des retours simples, les événements à
l'étape 10* : une abstraction de moins, mais l'étape 10 réécrirait alors la boucle au lieu
d'en remplacer le producteur, ce que §6 dit d'éviter. ~~**L'étape 10 doit pouvoir remplacer
`messages.create()` par `messages.stream()` sans que le consommateur bouge**~~ — et c'est
cette phrase qui a tranché la forme de `Texte`, émis dès qu'il est lu, sans savoir ce qui
suit dans le message.

> ⚠️ **Amendement de l'étape 9 — cette promesse devient fausse pour `Texte`, et pour lui
> seul.** L'arbitrage A de l'étape 9 bufferise la prose pour pouvoir la valider avant de
> l'émettre (voir l'amendement du §3.12). À l'étape 10, `Texte` restera donc **un**
> événement et non une suite de deltas : sur celui-là, le producteur ne peut pas être
> remplacé sans que le consommateur bouge.
>
> **La promesse reste entière pour tous les autres événements**, qui continuent de partir
> au fil de l'eau pendant l'attente — et c'est là qu'elle avait de la valeur, puisque
> c'est le panneau de §3.12 qui vit pendant qu'un outil tourne.
>
> Le renversement n'invalide pas l'arbitrage 1 : c'est parce que le contrat d'événements
> existait qu'un seul type a pu changer de nature sans que la console ni la persistance
> bougent d'une ligne.

> ⚠️ **Amendement de l'étape 10 — la promesse est barrée en entier. `messages.stream()`
> n'a plus aucun consommateur.**
>
> L'amendement de l'étape 9 laissait la promesse « entière pour tous les autres
> événements ». L'étape 10 a constaté que ce reste n'existait pas : **il n'y a plus rien à
> streamer côté modèle.** Un bloc `tool_use` doit être **complet** avant `executer()` — un
> JSON partiel n'est pas exécutable — et la prose est bufferisée pour être validée. Les
> deux seules choses qu'un delta pouvait servir sont donc fermées, et `client_anthropic.py`
> n'a pas été touché de l'étape.
>
> **Ce que l'arbitrage 1 a réellement acheté, et il l'a bien acheté :** un **second
> consommateur**. `raiyon.api` s'est branché à côté de `scripts/console.py` sans qu'une
> ligne de `boucle.py` ni de `session.py` ne bouge — deux affichages, deux publics, un seul
> générateur. La justification écrite (« remplacer le producteur ») était la mauvaise ; la
> décision, elle, était la bonne.
>
> La ligne est barrée plutôt qu'effacée : elle a décidé de la forme de `Texte` et de
> `QuestionPosee`, et l'effacer rendrait `evenements.py` incompréhensible. Trois docstrings
> la portaient — `evenements.py`, `boucle.py` et `client.py` — les trois sont barrées.
>
> Le seul streaming du projet est désormais celui du fil SSE, **serveur vers navigateur**,
> une trame par événement entier.

**2 — Un `Protocol` de client LLM, comme `DepotProduits`.** `ReponseLLM` porte les blocs
bruts (sérialisables tels quels en JSONB) et le `stop_reason`. L'implémentation SDK vit
dans `agent/client_anthropic.py`, **seul module du projet qui importe `anthropic`** ; un
faux scripté vit dans `tests/agent/faux_client.py`. *Alternative écartée — ne tester la
boucle que par cassettes à l'étape 12* : elle teste la vérité, mais rien avant l'étape 12,
et **un défaut de réenchaînement d'état ne se voit pas dans une cassette** — la cassette
rejoue les réponses du modèle, pas notre gestion de l'état.

> ⚠️ **Tension avec §3.15, à ne pas laisser passer pour un reniement.** §3.15 écarte les
> « mocks écrits à la main » au motif qu'on y teste ses propres suppositions sur ce que le
> LLM répond. La nuance est que le faux client ne teste pas *ce que le modèle répond* — il
> teste *ce que la boucle fait d'une réponse donnée* : enchaînement, état, terminalité,
> appairage des `tool_result`. C'est légitime, et **ça ne remplace pas** les cassettes de
> l'étape 12, qui restent au plan.

**3 — Le répartiteur vit dans `raiyon.tools`, pas dans `raiyon.agent`.**
`executer(nom, entree, etat, contexte)` rend `(EtatSession, ResultatOutil | OutilRefuse)` :
l'état sort **toujours**, inchangé sur un refus. *Alternative écartée — le répartiteur dans
`agent/`* : la couche outils resterait « cinq fonctions », mais `record_criteria`
s'écrirait alors dans deux modules de deux couches — exactement le motif que
`en_tool_result()` refuse, **un seul endroit où un nom du protocole est écrit**. Conséquence
vérifiée : le test d'isolation SDK, qui découvre les modules sur le disque, couvre
`repartiteur.py` sans qu'on ait eu à l'y inscrire. `CodeRefus.OUTIL_INCONNU` est ajouté :
la convention est « un code par geste », et corriger un nom d'outil n'est pas corriger un
champ. Une `ValidationError` devient un `OutilRefuse` de code `VALEUR_ILLISIBLE` qui
**recopie le message de Pydantic verbatim** — il nomme le champ fautif, ce qu'une
reformulation perdrait.

**4 — Blocs multiples dans un message assistant : tout exécuter, séquentiellement.**
Chaque `tool_use` s'exécute sur l'état rendu par le précédent ; un `OutilRefuse` ne fait
pas tomber les suivants, qui repartent de l'état d'avant. **Chaque `tool_use` reçoit
exactement un `tool_result`, dans le même ordre, sans aucune exception** — y compris quand
le tour est clos par `ask_clarification`, y compris quand `max_iterations` est atteint. Ce
dernier point n'est pas un choix : l'API refuse un historique où un `tool_use` n'a pas son
`tool_result` appairé, et comme les tours sont persistés, un orphelin ne casse pas le tour
courant mais **le suivant**. Une assertion générique (`verifier_appairage`) est appliquée à
tous les scénarios de test.

**5 — `ask_clarification` terminal : le texte qui précède est le préambule.** §3.7 avait un
argument `preamble` ; l'étape 7 l'a supprimé, et le « donner avant de demander » de §3.9
vit désormais dans le message lui-même. **Ce qui part au client est la suite des blocs
`text`, puis la question.** *Alternative écartée — jeter le texte et n'envoyer que
`question`* : plus simple, mais elle supprime mécaniquement le comportement que §3.9
réclame. Cas résiduels tranchés : deux `ask_clarification` — la première gagne, la seconde
s'exécute quand même (elle a besoin de son `tool_result`) et son résultat est ignoré avec
un `WARNING` ; `ask_clarification` avec un autre outil — tous s'exécutent, tous ont leur
`tool_result`, la question part et **les événements des outils qui la suivent ne partent
pas** au client.

> ⚠️ **Une asymétrie assumée, écrite plutôt que découverte.** Un événement émis *avant* la
> question, lui, reste émis : on ne rattrape pas ce qui est parti. La règle dépend donc de
> l'ordre des blocs. C'est accepté pour deux raisons — le cas est dégénéré (le prompt dit
> de ne pas mélanger), et toute règle qui n'en dépendrait pas exigerait de connaître la fin
> du message avant d'émettre le premier événement, c'est-à-dire de bufferiser, donc de
> rendre inopérant le streaming de l'étape 10.

**6 — On ne touche pas aux descriptions d'outils, et la duplication est tolérée en v1.**
`DESCRIPTION_SONDER` et `DESCRIPTION_PRECISION` portent déjà des règles de dialogue que le
prompt v1 redit. Toucher `schema_outils.py` invaliderait le cache de prompt, rouvrirait une
couche qu'on vient de fermer et de tester, et **on ne sait pas encore laquelle des deux
formulations porte l'effet** — c'est précisément ce que le harnais d'éval saura dire.
*Alternative écartée — répartir maintenant : le contrat d'appel dans la description, la
conduite dans le prompt.* C'est la bonne cible, elle suit le raisonnement d'`erreurs.py`
(deux rédactions d'une même règle finissent par en dire deux choses), et elle est
**reportée, pas abandonnée** — voir l'étape 13.

**7 — Cache de prompt activé, et ce qu'il interdit.** Un seul point de coupe, sur le bloc
système : le préfixe couvert est `tools` + `system`, donc les cinq définitions d'outils
sont dedans. **La contrainte que ça crée est ce qui compte** — voir l'amendement du §3.13.
Un test constate que deux appels du même tour reçoivent un `systeme` et des `outils`
identiques, et un autre que `systeme.v1.md` ne contient aucun marqueur d'interpolation.

**8 — `max_iterations` atteint : un message de repli écrit en Python.** `WARNING` avec le
compte d'itérations et les noms d'outils appelés, puis un événement `Repli` portant une
phrase constante. *Alternative écartée — un dernier appel sans outils pour forcer une
réponse texte* : plus élégante, et c'est ce que l'étape 9 rendra sûr ; écartée ici parce
qu'après huit itérations le modèle a précisément tourné en rond et que **rien ne valide
encore sa sortie** — ce serait le texte le moins fiable de toute la conversation qu'on
enverrait au client.

**9 — Persistance en base dès maintenant, et `tour_client` est le numéro du tour.** *Cet
arbitrage se tranche seul, et il faut le dire :* la console a **de toute façon** besoin de
Postgres, puisque `search_products` interroge le dépôt — l'argument « garder la console
utilisable sans conteneur » est faux. `sessions` et `tours_conversation` sont donc écrits
dès l'étape 8, et `en_jsonb()` / `depuis_jsonb()` exercés sur un aller-retour **réel**,
sans quoi l'étape 10 découvrirait le défaut avec le streaming par-dessus. `tour_client` est
le `numero` de la ligne du message client : croissant, unique par session, stable au
redémarrage. **Ni un compte de lignes `user`** — les `tool_result` en portent aussi —
**ni un compteur en mémoire**, qui rendrait le jeton de parole contournable en relançant la
console. Un seul commit, en fin de tour : un tour est atomique, et le générateur n'écrit
qu'à la fin, donc la console le consomme entièrement.

**10 — `ANTHROPIC_API_KEY` devient optionnelle, avec un accesseur qui lève.** Voir
l'amendement du §5 étape 2. *Alternative écartée — statu quo* : simple, et un projet
portfolio a de toute façon une clé ; mais `make seed` et `make calibrer` sont du code
déterministe depuis §3.4ter, et exiger une clé pour eux est un mensonge sur la dépendance.
*Alternative écartée — `SecretStr | None` déballé partout* : elle répand un `| None` dans
chaque site d'usage ; `cle_api()` n'en concentre qu'un.

**11 — Le premier appel API du projet valide `strict: true`, avant la boucle.** `make
fumee` livré, et **lancé avant d'écrire la boucle**. Résultat : `strict: true` **passe**,
avec l'`enum` de 36 champs et les propriétés optionnelles hors `required`. Le repli reste
en place — automatique et mémorisé sur un `BadRequestError` tant que le mode n'est pas
établi — mais il n'a pas eu à servir. C'est le point que le dépôt avait raté trois fois
(`smt` à l'étape 3, `temperature=0` et `nom_fr` à l'étape 5) ; cette fois il a été mesuré
avant d'être supposé.

**12 — Quatre réglages, tranchés au plus simple.** Pas de thinking étendu en v1 (les blocs
`thinking` devraient être réinjectés verbatim et persistés, pour un raisonnement qui tient
en deux lignes — à rouvrir à l'étape 13 si la métrique nº4 plafonne). On ne fixe pas
`temperature` : le dépôt s'est déjà fait prendre à supposer que `temperature=0` donnait du
déterminisme, on ne le suppose plus et on ne le revendique nulle part. `max_tokens = 2048`.
Le faux client reste dans `tests/` : pas de mode démo hors ligne, ce serait une seconde
façon de faire tourner le produit, à maintenir.

#### Ce que l'étape a appris, et qui n'était pas prévu

- **`strict: true` passe, et le repli n'a jamais servi.** L'étape 7 avait écrit noir sur
  blanc que le sous-ensemble de JSON Schema admis sous ce drapeau n'était documenté nulle
  part dans le paquet installé, et avait livré `schema_des_outils(strict=False)` par
  précaution. La mesure dit que la précaution était inutile — **et elle valait quand même
  d'être prise**, parce que c'est elle qui a rendu la mesure possible en un appel au lieu
  d'une séance de débogage au milieu de l'étape.
- **⚠️ Le drapeau `strict` ne fait pas partie de la clé de cache.** Constaté par la
  contre-épreuve de `make fumee` : un appel envoyant les définitions **sans** `strict`,
  juste après un appel qui les envoyait **avec**, a lu le cache écrit par le premier
  (`cache_lu=6039`). Le préfixe est donc considéré identique par l'API alors qu'il ne l'est
  pas octet pour octet côté client. Conséquence pratique : un repli en cours de processus ne
  coûterait pas une réécriture de cache. Conséquence à ne pas oublier : **on ne peut pas se
  servir du compteur de cache pour vérifier que `strict` est bien appliqué.**
- **`make fumee` a d'abord menti sur son propre résultat.** Sous `--sans-strict`, il
  affichait « mode retenu : strict: true » — parce que la propriété `client.strict` dit
  seulement que le *repli* ne s'est pas déclenché, pas que `strict` a été envoyé. Une cible
  qui existe pour mesurer une capacité affichait donc une mesure fausse dans un de ses deux
  modes. Corrigé en séparant « mode demandé », « repli déclenché » et « mode effectif ».
  C'est exactement le motif du F1 de l'étape 5 : un chiffre affiché sans que le chemin qui
  le produit ait été relu.
- **Le piège des deux `conftest.py` s'est redéclenché, à l'identique.** `tests/agent/` et
  `tests/tools/` ont chacun le leur, et `from conftest import SYSTEME` a résolu vers celui
  de `tests/tools/`. Le motif est documenté dans `outils_de_test.py` depuis l'étape 7 — le
  connaître ne suffit pas, il faut appliquer la règle dès le premier fichier. Les helpers
  sont dans `tests/agent/scenarios.py`, les fixtures restent dans `conftest.py`.
- **`caplog` de pytest ne voit rien de ce que loggue le projet.** Le dépôt loggue en
  structlog, qui écrit sur la sortie standard sans passer par le `logging` de la
  bibliothèque standard : un test qui asserte `"max_iterations" in caplog.text` échoue sur
  un `WARNING` pourtant bien émis. `structlog.testing.capture_logs()` rend les événements
  structurés, ce qui permet d'asserter sur la clé et le niveau plutôt que sur du texte.
- **`score=0` dans la trace n'est pas un défaut, et l'afficher seul le laissait croire.**
  Sur une recherche où tous les critères sont des filtres durs, aucun sous-score n'est
  produit, `agreger()` rend 0 et le classement se joue entièrement sur le départage — c'est
  le scénario G2 de l'étape 6. La première version de `--trace` affichait `score=0` sans
  rien d'autre. Elle affiche désormais le rôle appliqué, le nombre de critères scorés et
  les critères indisponibles, ce qui distingue « rien à scorer » de « tout raté ».
- **La section 6 du prompt v1 a produit son effet dès la première conversation.**
  `suggest_next_question` a rendu `marque` — le champ le plus discriminant, comme l'étape 7
  l'avait mesuré — et le modèle a demandé l'usage et la fréquence de rafraîchissement. C'est
  l'atténuation du risque « le champ le plus discriminant n'est pas toujours la meilleure
  question », observée une fois. **Une observation n'est pas une mesure** : rien ne le
  vérifie avant l'étape 12, et c'est au §7.

**Porte de sortie :** une conversation manuelle en console, de bout en bout, qui
aboutit à une recommandation de produits réels. Pas encore de qualité garantie —
juste la preuve que la boucle tourne et que les logs sont lisibles. **Franchie** :
conversation complète jusqu'à trois écrans réels avec leurs `id` et leurs prix, deux
produits de la zone de tolérance présentés avec leur écart exact, puis une reprise de la
même session par `--session` qui retrouve la catégorie, le critère et le budget.

---

### Étape 9 — Validateur anti-hallucination ✅

Parsing de chaque sortie texte : extraction des IDs produits, des prix, des
valeurs chiffrées. Vérification contre le contexte réellement fourni à l'appel.
Écart → une régénération avec le grief en message ; second échec → repli sur
template.

**Franchie.** 624 tests purs en 4,0 s (dont 110 pour le validateur et son branchement),
67 d'intégration, `make check` et `make test-int` verts — **sans base, sans conteneur et
sans clé API**. Les douze pièges sont détectés, les onze sorties légitimes acceptées sans
un grief, et une conversation console de bout en bout aboutit à une recommandation
validée — après que le validateur a **réellement mordu au premier tour** (voir plus bas).

```
src/raiyon/validateur/
    contexte.py      # ContexteFourni, construit depuis les tool_result — pur
    extraction.py    # ids, montants, valeurs unitaires, phrases, noms — pur
    regles.py        # les cinq règles, Grief, CodeGrief
    validateur.py    # valider(texte, contexte) -> Verdict ; OrigineRejet
    repli.py         # rédaction par template depuis ResultatMatching
src/raiyon/agent/
    boucle.py        # texte bufferisé, validé, régénéré une fois, puis repli
    evenements.py    # Repli gagne `motif` ; TexteRejete apparaît
    prompts.py       # message_de_grief(), empreinte loguée
src/raiyon/config.py # max_regenerations (budget de tour, partagé texte / question)
prompts/grief.v1.md  # le message de reprise, écrit pour le modèle
tests/validateur/    # extraction · regles · pieges · faux_positifs · repli · isolation
tests/agent/test_validation.py
```

#### Les cinq arbitrages

**A — Le texte est bufferisé, validé, puis émis. §3.11 gagne contre §3.12.**
**Valider après génération et streamer le texte au client sont incompatibles** : on ne
rattrape pas une phrase déjà affichée. Personne ne l'avait écrit, et c'est l'arbitrage
structurant de l'étape. Dans `boucle.py`, le texte d'un message assistant est concaténé,
validé, puis émis en **un** événement `Texte`. Les événements d'outils continuent
d'arriver au fil de l'eau : le panneau de §3.12 vit pendant l'attente, seule la prose
arrive d'un bloc. *Alternative écartée — streamer le texte et corriger à l'écran après
coup* : meilleure latence perçue, mais le client voit une affirmation puis sa
rétractation — c'est §2 pris à l'envers, et une démonstration qui montrerait un prix faux
pendant deux secondes ne démontrerait rien. Deux conséquences écrites plutôt que tues :
l'amendement du §5 étape 8 (la promesse « remplacer le producteur sans que le
consommateur bouge » devient fausse pour `Texte`, et pour lui seul) et la docstring de
`QuestionPosee`, dont la première des deux raisons s'appuyait sur un fait désormais
renversé.

**B — Le contexte fourni est typé par provenance, pas aplati en sac de nombres.**
`ContexteFourni` porte `produits`, `hors_budget`, `prix`, `valeurs_de_specs` et
`agregats` — voir l'amendement du §3.11. Il se construit **depuis les `tool_result` de la
session**, pas depuis un état interne : c'est ce qui garantit qu'il décrit ce que le
modèle a réellement vu. Il est **cumulatif sur la session, pas sur le tour** — un produit
rendu au tour 3 et cité au tour 6 est légitime, et un contexte par tour rejetterait la
moitié des conversations réelles. *Alternative écartée — un ensemble plat de tous les
nombres fournis* : vingt lignes de moins, et il ferme les trois quarts des cas ; mais il
laisse ouvert exactement celui que §7 nomme, et il rendrait fausse la phrase « l'oracle à
prix est vérifiable à l'étape 9 ». **La ligne à ne pas simplifier** : les *valeurs* des
distributions de `probe_catalog` n'entrent pas dans `valeurs_de_specs` — seuls leurs
effectifs entrent, en agrégats. « 12 écrans sont à 165 Hz » ne rend pas vrai « celui-ci
est à 165 Hz ».

**C — Cinq règles pures, un grief lisible par le modèle.** Chacune est une fonction
`(texte, ContexteFourni) -> tuple[Grief, ...]`, et `Grief` porte un code, l'extrait fautif
et une phrase qui dit **quoi corriger** — même convention que `OutilRefuse`, parce
qu'elle sera lue par le modèle. (1) tout jeton conforme à `MOTIF_ID` existe dans le
contexte ; (2) un montant en `$` dans une phrase qui nomme un produit est le prix de **ce**
produit ou son `ecart_usd`, ailleurs c'est un prix ou un agrégat fourni ; (3) un nom
fourni qui apparaît y apparaît **verbatim** ; (4) un produit hors budget cité l'est dans
une phrase qui porte son écart exact ; (5) un nombre suivi d'une unité connue est une
valeur de spec ou d'agrégat fournie. Les unités sont **dérivées du registre**
(`ATTRIBUTS`), jamais recopiées. Toutes les règles s'exécutent même après un premier
grief : le budget de régénération est de un, et un message de reprise partiel ferait payer
une régénération par faute. Le découpage en phrases est une heuristique tenue en **un
seul endroit** — voir les trois nouvelles lignes du §7.

**D — Une régénération, puis le repli, et la façon de le demander.**
`max_regenerations = 1` (`RAIYON_MAX_REGENERATIONS`, `ge=0`), budget **de tour** et non de
message. Le grief part dans le **même bloc `user` que les `tool_result`, après eux** :
c'est ce qui rend la régénération possible même quand le message fautif portait aussi des
`tool_use`, l'API exigeant les résultats appairés avant tout autre contenu utilisateur.
Le texte du grief vit dans `prompts/grief.v1.md`, chargé par `agent/prompts.py` avec son
empreinte loguée. **Le message fautif reste dans l'historique** : le retirer casserait
l'appairage et rendrait le grief incompréhensible — le modèle voit donc sa propre sortie
rejetée au tour suivant, et c'est acceptable. Second échec → `validateur/repli.py` rédige
la recommandation en Python depuis le dernier `ResultatMatching` du tour, et `Repli` gagne
un champ `motif` (`MAX_ITERATIONS` | `VALIDATION`) que l'étape 12 devra distinguer.
⚠️ **Limite assumée et écrite** : le repli ne remonte pas au-delà du tour en cours. Le
dernier `ResultatMatching` **typé** vit dans le tour qui l'a produit ; le retrouver au
tour suivant demanderait de reconstruire les `TraceProduit` depuis le JSON persisté,
c'est-à-dire d'écrire un **second lecteur du protocole** à côté de `contexte.py` — ce que
`en_tool_result()` refuse depuis l'étape 7. Sans recherche dans le tour, le repli est
donc la phrase d'excuse générique.

**E — Le validateur est pur, et testable sans clé ni base.** Même posture que `matching/`
et `tools/` : `ContexteFourni` se construit à partir de dictionnaires — les `tool_result`
déjà sérialisés — et `valider()` ne prend que du texte et un contexte. Le test d'isolation
par découverte sur disque est étendu à `raiyon.validateur`, **troisième paquet** à porter
la garantie. À dire précisément : elle porte sur `anthropic`, pas sur SQLAlchemy —
`repli.py` est typé sur `ResultatMatching`, donc il importe `matching.moteur`, donc
`depot.py`, exactement comme `raiyon.tools` depuis l'étape 7. La propriété qui compte
n'est pas « rien n'importe SQLAlchemy » mais « rien ne se connecte », et `make check` la
constate à chaque exécution.

#### Ce que l'étape a appris, et qui n'était pas prévu

- **⚠️ Une fixture de l'étape 8 disait ce que §2 interdit, et personne ne l'avait vu.**
  `test_ce_qui_part_au_client_est_le_texte_puis_la_question` faisait dire au modèle « sur
  cette gamme je pars plutôt sur du 27 pouces en 144 Hz » **avant tout appel d'outil**.
  Le validateur l'a refusée à la première exécution de `make check`. Ce n'était pas une
  régression du test : les deux chiffres ne venaient de nulle part, et la fixture
  écrivait une hallucination en la prenant pour une piste de vendeur. C'est le même
  mécanisme que le F1 de 0,85 de l'étape 5 — une valeur plausible dont personne n'a relu
  le chemin — et cette fois c'est du code qui l'a attrapée, pas une relecture.
- **Le validateur a mordu en production dès la première conversation, et sur le bon cas.**
  Après un sondage seul, le modèle a écrit une phrase adossée à « 144 Hz » et « 240 Hz » —
  deux valeurs lues dans la **distribution** du sondage, sur aucun produit fourni. Rejet,
  une régénération, et la seconde version dit « il reste 115 écrans possibles, entre 65 et
  400 dollars environ » : des agrégats, correctement présentés comme tels. **Le
  mécanisme a fait exactement ce pour quoi il existe, au premier essai réel**, et non sur
  une fixture écrite pour lui plaire.
- **Le même tour a montré le trou de l'entier nu, en conditions réelles.** « entre 65 et
  400 dollars » : la borne fournie valait 64,98 $, et « 65 » — entier nu, sans unité
  attachée — n'est vérifié par personne. Les 400 $ l'ont été. Le trou était déjà écrit
  dans le périmètre de l'étape ; il est désormais **observé**, et il est au §7 avec sa
  formulation exacte.
- **Le point décimal a failli casser la règle 2 en silence.** Un `split(".")` naïf lit
  « 417.14 $ » comme « 417 » puis « 14 $ » : la seconde moitié ne nomme plus aucun
  produit, tombe dans la branche « phrase sans produit », et le validateur crie sur une
  phrase parfaitement correcte. Le cas n'était pas dans la liste des pièges — c'est en
  écrivant le repli sur template, dont chaque ligne porte un prix, qu'il est apparu.
  D'où le test `test_un_point_decimal_ne_coupe_pas_une_phrase`, qui est le plus important
  de `test_extraction.py`.
- **Faire relire le repli par le validateur a changé la forme du repli.** Le gabarit devait
  passer les cinq règles ; trois décisions en découlent, et aucune n'aurait été prise
  sans ce test : chaque produit tient **sur une ligne avec son prix** (sinon le prix
  atterrit dans une phrase qui ne nomme personne), l'écart d'un produit hors budget est
  **sur la même ligne** que lui, et `prix_usd` est **écarté du « pourquoi »**. Un niveau 3
  qui ne passerait pas le niveau 2 aurait été un aveu.
- **La règle 2 criait sur une phrase que le prompt système n'interdit pas — fermé par le
  correctif.** « Le X à 249,99 $, dans votre budget de 400 $ » levait un grief. Le budget
  est désormais admis dans une phrase à produit, **et lui seul** : ce n'est pas un fait du
  catalogue mais une **parole du client**, entrée par `record_criteria` et rendue dans son
  `tool_result` ; le lui répéter n'invente rien. Une borne de sondage, elle, reste
  interdite — c'est une affirmation sur le catalogue que rien n'attache à un produit, et
  c'est le piège nº6, le seul test qui échoue si quelqu'un aplatit le contexte. La
  distinction est ce qui empêchera d'élargir « pour faire pareil ».
- **`ContexteFourni` lit les clés du protocole que `en_tool_result()` écrit, et c'est un
  second endroit.** L'étape 7 avait posé « un seul endroit où une clé du protocole porte
  un nom » ; l'étape 9 en crée un deuxième, en lecture. Il est concentré dans un bloc de
  constantes en tête de `contexte.py`, et `prix_usd` comme `specs` en sont volontairement
  absents — ils sont lus par `ProduitEnBase`, qui les nomme déjà **et les valide**. Le
  fixture de test ne recopie aucune charge utile à la main : il les fait produire par les
  vrais outils, donc un renommage de clé casse les tests au lieu de les laisser passer.
- **`ask_clarification` échappait au validateur** — sa question est un argument d'appel,
  pas un bloc `text`. Constaté en écrivant le branchement, ajouté au §7 plutôt que gardé
  pour soi, et **refermé dans la foulée** : voir le correctif ci-dessous.

#### Correctif — la question d'`ask_clarification` est validée

L'étape 9 avait signalé son propre trou au §7 : **la question n'était validée par rien.**
C'est un *argument d'outil*, pas un bloc `text` — elle sort de `demander_precision`, la
boucle la rend au client verbatim, et `valider()` ne la voyait jamais. Le critère nº1
était donc percé sur son chemin le plus fréquent : une conversation contient beaucoup plus
de questions que de recommandations. Fermé ici plutôt qu'à l'étape 12.

**1 — La validation vit dans la boucle, jamais dans l'outil.** `demander_precision` reste
pure et ignorante du contexte fourni : lui passer un `ContexteFourni` casserait
l'arbitrage C de l'étape 7 — un outil ne prend que ce qu'il lit dans l'état — et ferait
entrer le validateur dans `raiyon.tools`. La question est relue juste après
`_executer_les_appels`, avant `QuestionPosee`, **contre le même instantané de contexte que
le texte** : celui accumulé *avant* les `tool_result` du message courant, parce que le
modèle a écrit sa question sans avoir vu ces résultats-là. Élargir le contexte à ce qu'il
n'avait pas sous les yeux validerait une affirmation qu'il ne pouvait pas fonder — c'est
la règle de l'arbitrage A, la même, pas une seconde.

Les **cinq règles telles quelles**, aucune de neuve : la question est de la prose
française qui peut nommer un produit, un prix, une spec, et un second jeu de règles
finirait par diverger du premier (le raisonnement d'`erreurs.py`). Le budget de
régénération est **partagé** avec celui du texte — il vaut pour le tour, pas par nature de
sortie ; un budget par nature doublerait le pire cas d'appels API et donnerait deux
compteurs à réconcilier à l'étape 12. Le repli d'une question rejetée deux fois est la
**phrase générique, jamais le template de recommandation** : on ne répond pas par un
classement de produits à quelqu'un qu'on était en train d'interroger. `TexteRejete` gagne
`origine` (`TEXTE` | `QUESTION`), sans quoi l'étape 12 ne pourrait pas dire *où* le modèle
hallucine — et c'est cette métrique qui décide quoi corriger dans le prompt à l'étape 13.

*Alternative écartée — concaténer texte et question et ne valider qu'une fois.* Plus proche
de ce que le client lit d'un seul tenant ; écartée parce qu'elle obligerait à retarder
l'émission du texte jusqu'**après** l'exécution des outils. Le préambule arriverait alors
après `[critères]` et `[sondage]`, et l'arbitrage A perdrait la propriété qui le rend
acceptable : les événements d'outils vivent pendant que la prose se fait attendre, pas
l'inverse. ⚠️ **Conséquence assumée** : un produit hors budget nommé dans le texte dont
l'écart ne serait donné que dans la question déclencherait la règle 4. Le prompt système ne
demande jamais de citer un produit dans un préambule de question — si le cas se produit,
c'est un signal, pas un faux positif.

**2 — Le budget de session est admis dans une phrase qui nomme un produit.** C'était le
faux positif que l'étape 9 signalait, et il devient la formulation naturelle dès lors que
les questions sont validées : « le X à 249,99 $ rentre dans vos 400 $, vous voulez que je
regarde plus grand ? ». La justification n'est pas de commodité — **le budget n'est pas un
fait du catalogue, c'est une parole du client**, entrée par `record_criteria` et rendue
dans son `tool_result`. §2 interdit au modèle d'inventer un fait ; lui répéter le montant
qu'il vient d'annoncer n'en est pas un. `ContexteFourni` gagne `budget_usd`, dérivé des
`tool_result` et **jamais** d'`EtatSession` : le contexte fourni décrit ce que le modèle a
vu. ⚠️ **Rien d'autre n'est élargi** : les bornes d'agrégat restent interdites dans une
phrase à produit. Le budget est un montant unique et attribuable ; une fourchette de
sondage ne l'est pas — c'est le piège nº6, et c'est ce qui empêchera d'élargir « pour faire
pareil ».

**3 — L'unité se propage dans « entre A et B *unité* ».** Trou observé en vrai : « entre 65
et 400 dollars » quand la borne fournie valait 64,98 $. « 400 dollars » était vérifié,
« 65 » non — entier nu, exempté. Or 65 est un **arrondi**, c'est-à-dire une affirmation
approximative sur le catalogue : exactement ce que l'étape 7 avait refusé de faire produire
à `probe_catalog` en écartant les paliers arrondis. Le validateur laissait passer ce qu'un
arbitrage avait refusé de fabriquer. La borne basse hérite donc de l'unité de la borne
haute. **Une seule forme est traitée parce qu'une seule a été observée** ; « de A à B »,
« A-B » ou « autour de A » seraient de la théorie, et l'exemption générale de l'entier nu
reste entière.

**4 — Deux faux positifs trouvés en conversation réelle, et corrigés. Ils n'étaient pas au
programme.** Ce sont les deux seules décisions de ce correctif qui n'avaient pas été
demandées, et elles sont là parce que la porte de sortie exigeait une conversation de bout
en bout — c'est elle qui les a fait sortir.

* **Un nom de produit qui contient une unité.** Le catalogue porte `Sceptre C248W-1920RN` ;
  cité **verbatim** comme §3.4ter l'exige, « 248W » se lit 248 watts, et la règle 5
  refusait une recommandation parfaitement juste. Un nom recopié caractère pour caractère
  est un **identifiant**, pas une affirmation de caractéristique : les noms verbatim sont
  donc retirés du texte avant lecture des unités — le même geste qu'à la règle 3, pour la
  même raison. Le retrait ne cache rien, puisqu'il ne porte que sur les caractères d'un nom
  exact du catalogue.
* **Décrire son catalogue était devenu impossible.** L'agent annonçait « les fréquences
  vont de 60 à 240 Hz » — deux valeurs présentes dans la distribution rendue par
  `probe_catalog`, donc vraies — et le validateur les refusait, deux fois de suite, jusqu'au
  repli sur template. C'est le mode d'échec que l'étape redoutait, pris en flagrant délit :
  un validateur qui crie sur du français correct. La règle 5 range désormais les valeurs
  **par provenance, comme la règle 2 le fait des prix** : `ContexteFourni` gagne
  `valeurs_de_distribution`, admises dans une phrase qui ne nomme aucun produit, refusées
  dans une phrase qui en nomme un. Ce n'est pas une règle de plus — c'est l'arbitrage B
  appliqué là où il ne l'était qu'à moitié, et le piège nº9 continue d'échouer.

**Franchie.** 624 tests purs, 67 d'intégration, `make check` et `make test-int` verts sans
base ni clé. Douze pièges détectés, onze sorties légitimes acceptées sans un grief. Une
conversation console où une question passe la validation, et une autre où un nom tronqué
(« l'Acer Nitro » pour `Acer Nitro EDA270U P`) est refusé puis corrigé par la régénération
— §3.4ter vérifié par machine, sur un défaut que personne n'avait écrit en fixture.

**Porte de sortie :** des fixtures de sorties LLM **délibérément piégeuses** —
prix modifié de 10 €, ID inexistant, produit entièrement inventé, spec
transformée — toutes détectées. Et le repli template produit une réponse
correcte, même si sèche. **Franchie** : douze pièges détectés (dont le prix de sondage
attribué à un produit nommé, qui échoue si le contexte est aplati), onze sorties légitimes
acceptées sans un grief, repli sur template relu par le validateur lui-même, et des
conversations console où la régénération a réellement rattrapé une sortie fausse.

C'est le critère nº1 franchi au niveau du mécanisme, et le critère nº2 qui cesse d'être
une propriété structurelle du moteur pour devenir aussi une vérification sur la phrase.

---

### Étape 10 — API et streaming ✅

FastAPI, endpoint de chat en SSE, événements typés du §3.12, persistance de
session en Postgres.

⚠️ **Contrainte héritée de l'étape 7 : la session se persiste aux frontières de tour,
jamais au milieu.** L'état de session porte deux gardes qui ne valent qu'à l'intérieur
d'un tour client — la recherche déjà faite (arbitrage E) et le jeton de parole en cours
d'appel. Elles ne sont pas dans le JSONB, parce qu'une valeur périmée y refuserait une
recherche légitime au tour suivant. Si l'étape 10 devait persister l'état **au milieu**
d'un tour — reprise après incident en cours de boucle d'agent, par exemple —, ces gardes
devraient rejoindre `criteres_valides` ; le JSONB n'ayant pas de schéma, cela ne
demanderait aucune migration, mais il faudrait le décider et non le découvrir.

> ✅ **La condition est restée fermée, et il faut le dire explicitement.** L'API **ne
> persiste rien au milieu d'un tour** : `session.tour()` commite exactement une fois, en
> fin de tour, et le générateur SSE ne fait rien d'autre que le consommer. Ni
> `recherche_du_tour` ni `tour_du_dernier_desserrage` en cours d'appel ne rejoignent le
> JSONB, et aucune migration n'a été nécessaire.
>
> C'est même l'inverse qui s'est produit : l'atomicité est devenue la **sémantique
> d'erreur** de toute l'étape (arbitrage I). Un tour interrompu — exception, déconnexion,
> redémarrage — n'écrit rien du tout, pas même le message du client. La condition de
> bascule reste donc ouverte pour l'avenir, et elle est aujourd'hui plus loin d'être
> franchie qu'à l'étape 7 : il faudrait d'abord vouloir reprendre un tour à mi-chemin,
> c'est-à-dire renoncer à l'atomicité qui rend le reste vrai.

**Porte de sortie franchie :** une conversation de quatre tours menée en `curl` sur le
catalogue réel, avec les événements typés visibles dans le flux — `criteria_updated`,
`products_found`, `text_rejected`, `message`, `done` — puis le serveur tué, redémarré, et
la conversation reprise par son UUID avec l'état et la prose intacts. `GET /health`
répond avant et après.

#### Ce que l'étape a livré

```
src/raiyon/api/
    serialisation.py   # Evenement -> trame SSE ; assert_never — PUR
    prose.py           # relecture des blocs pour GET /sessions/{id} — PUR
    schemas.py         # corps de requête et réponses JSON
    verrou.py          # pg_try_advisory_xact_lock sur l'UUID de session
    app.py             # application, lifespan, cinq routes, générateur SSE
web/index.html         # placeholder de l'étape 11
```

```
POST /sessions                    -> 201 {"id": "<uuid>"}
POST /sessions/{id}/messages      -> 200 text/event-stream   (404 | 409 | 422)
GET  /sessions/{id}               -> 200 {état + prose}      (404)
GET  /health                      -> 200 {base, prompt, strict}   (503 si base morte)
GET  /                            -> StaticFiles("web")
```

**Mesure : 677 tests purs en 5,2 s, 84 d'intégration** — dont 53 purs et 17 d'intégration
écrits ici. `mypy --strict` et `ruff` propres.

#### Les douze arbitrages

**A — Pile synchrone de bout en bout.** Le générateur passé à `StreamingResponse` est
**synchrone** ; Starlette l'enveloppe dans `iterate_in_threadpool`. Toute la couche métier
reste synchrone, ce qui est la condition du critère nº5. *Alternative écartée — un engine
asyncio* : il imposerait `async def` jusque dans `tests/matching/`, donc ferait tomber le
critère nº5. Non négociable. Précision qui compte : **ce n'est pas l'endpoint qui doit
être `def`** — un `async def` rendant un `StreamingResponse` sync marche, le tour ayant
lieu après le retour de l'endpoint. Les endpoints sont pourtant tous `def` ici, pour une
**autre** raison : ils font eux-mêmes du SQL bloquant avant de rendre (le 404, le verrou,
la relecture, le `SELECT 1`), et en `async def` ces requêtes-là bloqueraient la boucle
d'événements.

**B — POST rendant du `text/event-stream`.** `EventSource` ne sait faire que du GET, et
mettre le message du client en query string est exclu — longueur, encodage, et un message
de client dans les logs d'accès. *Alternative écartée — un POST qui ouvre un tour puis un
GET `/events` en `EventSource`* : deux requêtes, une course entre les deux, et un état
serveur à porter entre elles pour rien. **Coût assumé, à payer à l'étape 11 :** le front
devra parser le SSE à la main sur `fetch` + `ReadableStream`.

**C — Aucun heartbeat, et c'est assumé.** Un générateur synchrone bloqué dans
`messages.create()` ne peut **rien** intercaler : ni `: ping`, ni détection de
déconnexion. Le silence réel est celui d'un tour sans appel d'outil ; les événements
d'outils tiennent la connexion vivante le reste du temps. En démo locale et en `curl`,
aucun effet. **Condition de bascule écrite plutôt que codée :** derrière un proxy qui
coupe à 60 s d'inactivité, la parade est un endpoint `async` drainant le générateur sync
par une `queue.Queue` — une quarantaine de lignes de plomberie thread↔asyncio. Tant
qu'aucun proxy n'est en jeu, ces lignes ne protègent de rien. Reporté au §7.

**D — Un tour à la fois par session, verrouillé en base.** Le verrou en mémoire est
**interdit par une décision déjà écrite** : §3.12 justifie la persistance des sessions par
« autorise le multi-worker », et un `dict` de verrous par processus rendrait cette phrase
fausse dès `uvicorn --workers 2` — sans que rien ne le signale en développement, où il n'y
a qu'un worker. C'est donc un `pg_try_advisory_xact_lock` pris sur la **même `Session`
SQLAlchemy** que celle qui servira le tour, **avant** `tour()`. `tour()` commite exactement
une fois : la portée du verrou coïncide au caractère près avec celle du tour, et il n'y a
**aucune libération à oublier** — ni sur exception, ni sur déconnexion. Refus → **409 avant
le premier octet**. *Alternative écartée — `SELECT … FOR UPDATE NOWAIT` sur la ligne de
session* : même effet, mais elle verrouille une ligne qu'on écrit de toute façon, et son
message d'erreur parle de la ligne, pas du tour. La clé est un UUID tronqué à 64 bits ; la
collision est tarifée et bénigne (deux conversations sans rapport ne tourneraient pas en
même temps), pas silencieuse.

**E — Avant le premier octet, un code HTTP ; après, un événement typé.** C'est la ligne de
partage de toute la gestion d'erreur. **Avant** : session inconnue → 404, corps invalide →
422, verrou pris → 409. **Après** : il n'existe plus de code HTTP à changer, donc toute
exception devient un événement `error` suivi de la fermeture du flux. ⚠️ **Le message d'un
`error` est écrit pour le client, en français, et ne contient jamais le `str()` de
l'exception** — une trace SQLAlchemy sur une page web est une fuite. Le détail part en
`logueur.exception` avec l'identifiant de session, et un test le vérifie sur le flux
entier.

**F — `error` et `done` n'entrent pas dans l'union `Evenement`.** L'union du domaine décrit
le dialogue ; « la base a coupé » n'en est pas un fait, et l'y ajouter obligerait la
console à traiter un cas qui ne peut pas lui arriver. Ces deux-là vivent dans le
vocabulaire de l'API et sont produits **par le générateur SSE, jamais par la boucle**.
`done` est terminal et obligatoire : sans lui, le front ne distingue pas « tour terminé »
de « connexion tombée » — la fermeture du flux seule ne les sépare pas.

**G — Ce que le fil porte, et ce qu'il ne porte pas.** *Ce qui prouve un invariant sort ;
ce qui explique un classement reste.* Détaillé dans l'amendement du §3.12.

**H — Le français du fil est dérivé du registre, jamais inventé par le front.** Détaillé
dans le même amendement. Vérifié par un test qui lit la **source** du sérialiseur : aucun
libellé d'attribut ni nom de catégorie n'y est écrit en dur.

**I — Une déconnexion tue le tour, exactement comme un redémarrage. C'est une correction :
la note d'arbitrage disait le contraire, et elle avait tort.** Sur une déconnexion,
Starlette cesse d'itérer et le générateur reçoit un `GeneratorExit` au `yield` en cours ;
`tour()` n'atteint donc jamais son `commit()`. **Rien n'est persisté, pas même le message
du client**, et l'appel API est payé et perdu. On ne cherche pas à l'éviter — l'éviter
demanderait le drainage par file d'attente que l'arbitrage C écarte. On le rend **propre** :
un `finally` qui `rollback()` puis `close()`, sans quoi la connexion revient au pool en
transaction avortée et fait échouer la requête **suivante** avec une erreur qui ne désigne
pas la vraie cause. C'est cohérent avec l'atomicité de `session.py` : « sans rien perdre »
signifie **« sans rien écrire de faux »**.

**J — `GET /sessions/{id}` relit la prose, jamais les événements.** Les `blocs` ne sont pas
une projection d'événements : reconstruire `criteria_updated` ou `products_found` depuis
les `tool_result` demanderait un **second lecteur du protocole**, donc une seconde vérité
qui divergerait de la première. L'endpoint rend l'**état** — lu par `etat_de()`,
c'est-à-dire par `depuis_jsonb()`, le lecteur qui existe déjà — et la **prose** : les blocs
`text`, et l'argument `question` des `tool_use` nommés `ask_clarification`.

**K — Aucune nouvelle variable d'environnement.** Hôte et port sont des arguments
`uvicorn` dans le `Makefile`. Le front étant servi par le même processus (arbitrage L),
**il n'y a aucun CORS à configurer**, et donc rien à rendre configurable. `config.py` n'a
pas bougé.

**L — Le front est servi par le même processus.** `StaticFiles` monté sur `/`, sur un
`web/` qui porte pour l'instant un placeholder. Un processus, une commande, pas de CORS,
pas de second serveur de développement. ⚠️ **Le montage `/` vient après les routes**,
sinon il les avale — et le défaut est silencieux : `/health` rendrait un 404 de fichier
statique. Un test pur garde l'ordre.

#### Ce que l'étape a appris, et qui n'était pas prévu

**1 — Le message de reprise de l'étape 9 est un piège de relecture, et il n'avait été vu
par personne.** L'arbitrage J dit « les blocs `text`, une quinzaine de lignes ». Mais tous
les blocs `text` ne sont pas de la prose de dialogue : le message de grief est un bloc
`text` de **rôle `user`**, écrit pour le modèle, et qui dit lui-même « le client ne le
voit pas ». Le rendre afficherait la mécanique interne d'un rejet sous l'identité du
client. Deux formes existent : accompagné de `tool_result` (reconnaissable à leur
présence), ou **seul** — et là il est indiscernable d'un message client *par sa forme*. La
reconnaissance passe donc par le **gabarit chargé** (`prompts/grief.v1.md`), pas par une
phrase recopiée : elle est dérivée, comme le français du fil. Limite datée et écrite : une
conversation persistée sous `grief.v1` et relue après un `grief.v2` de l'étape 13
réafficherait ses anciennes reprises.

**2 — Le ratio pur/intégration s'est dégradé, et il faut le dire avec le chiffre.** Il
passe de **9,3:1** (624/67) à **8,1:1** (677/84). Sur l'étape seule il vaut 3,1:1. La
raison est structurelle et non évitable : un advisory lock inter-connexion, un commit qui
relâche ce verrou, une transaction avortée rendue au pool — **aucune de ces trois
propriétés ne se voit sans un vrai Postgres**, et ce sont exactement les trois façons dont
cette étape pouvait échouer en silence. Ce qui a été fait à la place : tout ce qui pouvait
descendre dans la part pure y est descendu (le contrat de fil en entier, la relecture de
prose, la validation du corps de requête, la clé de verrou, l'ordre des routes), et
`make check` reste sans base, sans conteneur et sans clé.

**3 — `db/engine.py` annonçait un mécanisme qui n'a jamais servi.** La docstring promettait
depuis l'étape 2 que « l'API de l'étape 10 enveloppera ses appels base dans
`asyncio.to_thread` ». Aucun `await` n'a été écrit : c'est **Starlette** qui fait le saut
de thread, tout seul, pour un endpoint `def` comme pour un générateur sync. L'argument
était juste (le moteur reste synchrone pour que le critère nº5 tienne), le mécanisme était
une supposition. Troisième fois que le dépôt se fait prendre à décrire une capacité
d'outil qu'il n'avait pas mesurée — après `smt`, `temperature=0` et `strict`.

**4 — Le validateur s'est déclenché en démonstration, et c'est la meilleure preuve de
l'étape.** Au quatrième tour de la conversation `curl`, le modèle a écrit « 230 $ », un
montant qu'aucun outil n'avait rendu. Le fil porte l'enchaînement complet :
`text_rejected` (`montant_non_fourni`, extrait « 230 $ »), puis le `message` régénéré,
exact. **§2 n'est plus une intention lisible dans un README : il est visible dans le
flux**, et l'arbitrage G — faire sortir `text_rejected` — se paie tout seul à l'étape 11.

**5 — Le `Protocol` `ClientLLM` a servi à autre chose que ce pour quoi il avait été écrit.**
Sa justification de l'étape 8 (« remplacer `create()` par `stream()` ») est morte. Sa
valeur réelle est apparue ici : `dependency_overrides` le remplace par le faux client, et
les 17 tests d'endpoints — verrou, générateur, persistance, gestion d'erreur — tournent
**sans consommer un jeton**. Une bonne frontière tient même quand la raison qui l'a fait
tracer s'effondre.

---

### Étape 11 — Interface web ✅

Chat, panneau latéral « ce que j'ai compris » alimenté par `criteria_updated`, cartes
produits alimentées par `products_found`, indicateur d'activité, et un **mode coulisses**
qui montre les textes refusés par le validateur.

**Porte de sortie franchie :** une conversation de quatre tours menée dans le navigateur
sur le catalogue réel. Les critères se remplissent au fil du dialogue ; un rejet du
validateur (`nom_reecrit` — le modèle avait écrit « MAG 274CQF » là où le catalogue dit
« MSI MAG 274CQF ») est apparu **spontanément** au premier tour et s'est affiché en mode
coulisses avec son grief ; un zéro résultat (360 Hz + IPS + 4K sous 400 $) a rendu son
diagnostic et sa proposition de relâchement ; deux mouvements de desserrage refusés se
sont affichés au panneau ; un `F5` a retrouvé la session par son fragment d'URL en disant
ce qu'il ne rejouait pas ; un second onglet sur la même URL a reçu son `409` en français,
saisie réactivée.

**Mesure : 713 tests purs en 5,9 s, 84 d'intégration** — 36 purs écrits ici, **aucun
d'intégration**. Le ratio pur/intégration remonte de 8,1:1 à **8,5:1**, ce qui n'était pas
prévu : voir « ce que l'étape a appris ». *(Le correctif ci-dessous porte le total à 720
purs, ratio 8,6:1.)*

#### Ce que l'étape a livré

```
web/
    index.html   # la structure, deux colonnes, aucun script en ligne
    style.css    # tout le style
    flux.js      # fetch + ReadableStream -> événements typés — jamais de DOM
    etat.js      # le réducteur : un événement, un état — jamais de DOM
    rendu.js     # état -> DOM, textContent uniquement — jamais de réseau
    app.js       # câblage : saisie, fragment d'URL, verrouillage, coulisses
tests/api/
    test_cadrage_sse.py   # le contrat du producteur — purs
```

`flux.js` et `etat.js` ne touchent jamais au DOM ; `rendu.js` ne parle jamais au réseau.
C'est la même séparation que `serialisation.py` / `app.py` côté serveur, et elle sert la
même chose : **ce qui peut casser en silence vit dans un module qu'on peut lire seul.**

Et le jalon 0, qui n'est pas du front : le corps du `409` **aplati** (`ErreurDeLApi` +
son gestionnaire), et la ligne de §7 sur le verrou tenu jusqu'au GC.

#### Les neuf arbitrages

**A — Vanilla, modules ES, aucun build.** Du JavaScript natif en `<script type="module">`,
servi tel quel par `StaticFiles`. Pas de `package.json`, pas de `node_modules`, pas
d'étape de compilation, pas de second serveur : `make api` reste la seule commande.
*Alternative écartée — Vite + React* : un point de plus sur un CV, et un coût réel — un
build à lancer avant `make api`, un serveur de développement séparé qui **rouvre le CORS
que l'étape 10 venait de fermer** (arbitrage L), et un dépôt bilingue. L'étape 11 est la
plus courte du plan ; ce choix en aurait fait la plus longue. *Alternative écartée —
Preact + htm vendorés* : le rendu déclaratif sans build, écartée pour deux dépendances
JavaScript à justifier dans un projet qui n'en a aucune. **Conséquence assumée** : le
rendu s'écrit à la main — le fil est ajouté entrée par entrée sur une clé stable, le
panneau est refait en entier. Un rendu par événement, ciblé, suffit ; il n'y a pas de
micro-framework ici, et c'était la tentation à laquelle il ne fallait pas céder.

**B — `textContent`, jamais `innerHTML`.** *On ne fait pas confiance au modèle pour les
faits ; on ne lui fait pas davantage confiance pour le HTML.* Toute chaîne venue du fil —
prose, question, nom de produit, extrait de grief — entre dans le DOM par `textContent` ou
`createTextNode`, sans exception, y compris pour un nom de produit qui « ne peut pas »
contenir de balise. Le modèle produit du markdown ; le front en interprète **deux formes
et pas une de plus** — le gras `**…**` et les sauts de ligne — construites en **nœuds
DOM**, jamais en chaîne de HTML assemblée puis injectée. Trente lignes qui ne peuvent
structurellement pas ouvrir d'injection. Le reste du markdown s'affiche tel quel : **c'est
le prompt qu'on corrigera à l'étape 13, pas le front qu'on armera d'un parseur.** Reporté
au §7.

**C — Les cartes produits vivent dans le fil, pas dans le panneau.** `products_found`
arrive **avant** la prose qui le commente. Poser les cartes dans le flux de conversation, à
l'endroit où elles arrivent, rend visible l'ordre réel : le code a trouvé, puis le modèle a
écrit à propos de ce qu'on lui a donné. C'est §2 rendu observable sans une ligne
d'explication. *Alternative écartée — les cartes dans le panneau* : le panneau resterait le
seul endroit « technique » et le chat le seul endroit « produit », ce qui casse la
chronologie — précisément ce qu'on veut montrer. Le panneau porte donc **ce que le code a
compris** et l'activité, jamais les résultats.

**D — L'attente est affichée, pas masquée.** Entre le dernier événement d'outil et le
`message`, le validateur relit la réponse ; mesuré en démonstration, l'écart est de
**douze secondes** sur un tour de vingt-deux. Le front dit ce qu'il attend — « vérification
de la réponse… » — plutôt qu'un sablier générique. C'est la seule chose qui bouge à ce
moment-là, et c'est ce que l'arbitrage A de l'étape 9 a acheté. ⚠️ **L'indicateur reflète
le dernier événement reçu, et rien d'autre** : pas d'étape « connexion », pas de barre de
progression. Inventer une progression que le fil ne dit pas serait, à l'échelle de
l'interface, exactement ce que le projet interdit au modèle.

**E — Le mode coulisses, interrupteur dans le panneau.** Fermé : l'interface d'un produit —
`text_rejected`, `suggested_question` et le détail des distributions n'y sont pas, un
client n'ayant rien à faire des reprises internes. Ouvert : c'est le `--trace` de la
console porté au navigateur, et c'est la démonstration qu'on montre en entretien.
L'interrupteur **ne se persiste pas** : une page rechargée repart en mode produit, celui
qu'un visiteur doit voir en premier. ⚠️ **Les événements masqués sont reçus et conservés,
pas jetés** — le réducteur les range, c'est le rendu qui décide. Basculer au milieu d'une
conversation affiche ce qui s'est déjà passé ; un mode qui ne montrerait que la suite
obligerait à refaire la conversation pour voir le rejet qu'on vient de rater.

**F — L'identifiant de session vit dans le fragment d'URL.** `#<uuid>` : un rechargement
retrouve la conversation, l'URL se copie et se recolle, et l'identifiant est **visible** —
un atout de démonstration, pas un détail. *Alternative écartée — `localStorage`* :
invisible, non partageable, et elle rend la seconde conversation impossible sans vider le
stockage. Au chargement, fragment présent → `GET /sessions/{id}` ; absent → **aucun appel**,
la session n'est créée qu'au premier message. ⚠️ Un `GET` sur une session inconnue rend
404 : le front repart sur une conversation neuve **en le disant**, plutôt qu'une page vide
dont personne ne comprendrait la cause.

**G — Ce que la réhydratation perd doit se voir.** `GET /sessions/{id}` rend l'état et la
prose, jamais les événements (arbitrage J de l'étape 10) : une conversation rechargée n'a
ni cartes produits ni panneau d'activité. Elle perd davantage — les messages de repli ne
sont pas persistés (§7) — donc un tour clos par un `fallback` réapparaît **sans sa
réponse**. L'interface ne fait pas semblant : la conversation reprise est marquée comme
telle. Inventer une carte produit à partir de rien serait exactement ce que ce projet
interdit au modèle.

**H — La saisie est verrouillée pendant un tour.** Un seul tour à la fois par session
(arbitrage D de l'étape 10) : champ et bouton désactivés dès l'envoi, réactivés sur `done`,
sur `error`, ou sur un échec réseau. `done` est émis **après** que le tour a été persisté —
la boucle `for` du générateur épuise `session.tour()`, qui commite avant de rendre la
main — donc il signifie « enregistré » et non seulement « fini », et rouvrir la saisie à ce
moment-là est sans réserve. Le 409 reste traité : il arrive quand **deux onglets** partagent
la même URL, ce que le verrouillage local ne peut pas empêcher.

**I — Rien n'est testé en JavaScript, et le contrat l'est en Python.** Aucune dépendance
nouvelle, `make check` inchangé. `test_cadrage_sse.py` vérifie les trois propriétés du
producteur dont dépend le parseur, et rejoue un tour complet sous quatre découpages
d'octets. *Alternative écartée — Playwright de bout en bout* : une dépendance, des
navigateurs à installer, un serveur à lancer en test, et surtout `make check` perdrait la
propriété qui fait sa valeur — tourner sans base, sans conteneur et sans clé. Ce que cela
laisse à découvert est écrit au §7 plutôt que masqué.

#### Ce que l'étape a appris, et qui n'était pas prévu

**1 — Un texte refusé par le validateur revenait au client par la porte du rechargement.
C'est une brèche dans §2, et il a fallu une interface pour la voir.** Le message fautif est
persisté — il le faut, le grief qui suit le désigne, et l'en retirer casserait l'appairage
des `tool_result`. Mais `prose_de()` le relisait comme n'importe quelle prose : en direct
le validateur tenait §2, **après un `F5` il ne le tenait plus**. La même conversation, relue,
affichait la phrase que le code avait justement empêchée.

Pire : un test l'affirmait explicitement, et son nom disait sa conclusion —
`test_le_texte_refuse_reste_dans_la_prose_parce_quil_reste_dans_lhistorique`. Sa prémisse
était juste (le message doit rester dans l'historique), sa conclusion ne suivait pas
(rester dans l'historique n'est pas partir au client). **Un test vert qui documente un
défaut est plus difficile à voir qu'un test absent.**

Le correctif est exact et non heuristique : `boucle.py` fait toujours suivre un message
refusé d'un message de reprise, donc un message assistant suivi d'une reprise est un
message refusé. Le message **entier** est écarté, texte compris, et le sens de l'erreur est
choisi : sur le chemin où c'est la *question* d'`ask_clarification` qui est refusée, le
texte du même message avait été validé et affiché, et les deux chemins laissent la même
trace. **On perd une phrase que le client avait vue plutôt que d'en afficher une qu'il
n'aurait jamais dû voir.**

**2 — Le fil portait des jetons d'énumération là où il fallait du français, et personne ne
l'avait vu parce que personne ne les affichait.** L'arbitrage H de l'étape 10 — « le
français du fil est dérivé du registre, jamais inventé par le front » — avait été appliqué
aux **champs** : `libelle_fr` et `unite` partout. Il n'avait pas été appliqué aux **valeurs
d'énumération**, parce que la console n'en affiche aucune au client. La première
conversation dans le navigateur a mis `optimisation : rapport_qualite_prix` dans un panneau,
et le zéro résultat aurait affiché `critere_trop_strict` — c'est-à-dire un identifiant
montré faute de mieux, là où le critère d'acceptation nº6 demande « le cas zéro résultat
rendu lisible ».

Les deux issues étaient : une table de traduction dans le JavaScript, ou trois tables
`LIBELLES_*` à côté de leurs énumérations. La première rendait fausse §3.4ter au moment
précis où elle devenait visible. Le fil porte donc désormais `libelle_optimisation` et
`libelle_motif` à côté de leurs jetons — le jeton se compare, le libellé s'affiche — et un
test vérifie l'**exhaustivité** de chaque table, un membre sans libellé levant un
`KeyError` au milieu d'un flux, c'est-à-dire un tour perdu pour un mot d'affichage.

**Ce que ça dit du geste de l'étape 10** : une règle appliquée à ce qu'on affichait déjà
n'est pas une règle appliquée. Il aura fallu le premier consommateur qui affiche *tout*
pour découvrir où elle s'arrêtait.

**3 — Le ratio pur/intégration remonte, et c'est la première étape où il remonte.** De
8,1:1 à 8,5:1, avec **36 tests purs et zéro test d'intégration**. La raison est exactement
inverse de celle de l'étape 10 : là-bas, trois propriétés (verrou inter-connexion, commit
qui relâche, transaction avortée) ne se voyaient pas sans un vrai Postgres ; ici, ce qui
pouvait casser en silence est un **format** — le cadrage d'une trame, sa recomposition sous
un découpage arbitraire — et un format se teste sans rien brancher.

**4 — L'attente que l'arbitrage A de l'étape 9 avait achetée est mesurable, et elle est
longue.** Sur le premier tour observé : événements d'outils à 6,2 s et 9,8 s, prose à
21,7 s. **Douze secondes** pendant lesquelles le panneau et les cartes sont déjà remplis et
la prose ne l'est pas. Ce n'est pas un défaut à masquer — c'est l'architecture qui se voit :
si le texte était streamé, il n'y aurait rien à montrer dans cet intervalle *et* la
vérification n'aurait pas eu lieu.

**5 — Le validateur s'est déclenché tout seul, au premier tour, pour la seconde étape
consécutive.** À l'étape 10 c'était `montant_non_fourni` (« 230 $ ») ; ici c'est
`nom_reecrit` — le modèle a écrit « MAG 274CQF » et « le LG » en reprenant des noms qu'il
venait de citer correctement. Deux codes de grief différents, sur deux conversations de
recette de quelques tours chacune. **La règle 3 n'est donc pas une précaution théorique**,
et c'est aussi la première fois qu'on voit son grief avec sa correction dans une interface
plutôt que dans un log.

**6 — Le §3.12 disait vrai, et voici ce que ça a coûté.** « L'interface peut alors afficher
un panneau *voici ce que j'ai compris de ton besoin* — c'est le meilleur rapport
effet/effort du projet. » Mesuré en lignes de code (hors commentaires et lignes vides,
comptées sur le dépôt) :

| | lignes de code | total avec la documentation |
|---|---|---|
| `flux.js` — le parseur SSE | **95** | 211 |
| `etat.js` — le réducteur | **81** | 170 |
| `rendu.js` — tout le rendu | **304** | 507 |
| `app.js` — le câblage | **94** | 180 |
| dont **le panneau seul**, dans `rendu.js` | **106** | 140 |
| `tests/api/test_cadrage_sse.py` | — | 455 |

**Le panneau entier coûte 106 lignes** — critères avec leur libellé, leur unité et leur
importance, budget, optimisation, mouvements refusés, activité du catalogue, distributions
dépliées en coulisses. C'est donc vrai, et il faut ajouter ce que la phrase de cadrage ne
disait pas : **il ne coûte 106 lignes que parce que trois étapes l'avaient payé d'avance.**
L'événement `criteria_updated` existe depuis l'étape 8, ses libellés depuis l'étape 10, et
l'étape 11 n'a eu qu'à les poser dans des `<li>`. Un panneau équivalent branché sur une API
qui rendrait du texte libre aurait demandé de reparser la réponse du modèle — c'est-à-dire
tout ce que §2 interdit.

Ce qui a réellement coûté cher n'est pas le panneau : c'est le parseur SSE **avec sa
spécification testée** (95 lignes de JavaScript pour 455 lignes de test Python), et les
deux défauts que la démonstration a révélés. Le rapport effet/effort du panneau est réel ;
il n'est pas celui de l'étape.

#### Correctif — le dernier refus d'un tour

L'étape 11 avait fermé une brèche dans §2 : un texte refusé par le validateur revenait au
client après un `F5`. Le correctif était juste — `prose_de()` écarte un message assistant
suivi d'un message de reprise, reconnaissance exacte tirée de ce que `boucle.py` empile
réellement. **Il restait un chemin, et c'était le pire des trois.**

**Le défaut.** `boucle.py` n'écrivait le message de reprise que là où une **régénération**
était demandée. Sur les deux branches `if regenerations > max_regenerations` — celle du
texte et celle de la question — il faisait `_ajouter_les_resultats()`, `yield Repli(...)`,
`return` : aucun `_bloc_de_grief`. Le dernier message refusé du tour n'était donc suivi
d'aucune reprise, et `prose_de()` le rendait. Deux formes, toutes deux touchées : avec des
`tool_use`, le message suivant ne portait que des `tool_result`, sans bloc `text` à
reconnaître ; **sans** `tool_use`, `_ajouter_les_resultats()` sortait tôt et **rien
n'était empilé** — le message fautif était le dernier de l'historique, sans suivant du tout.

**Pourquoi c'était le pire des trois.** Deux raisons qui se cumulent. C'est le texte que le
validateur a refusé **et** que la régénération n'a pas su corriger : la sortie la plus
fausse que le tour ait produite, pas la première. Et comme le message de repli n'est pas
persisté (ligne du §7 posée à l'étape 10), le rechargement affichait **exactement l'inverse
de ce qui s'est passé** — la phrase que le client n'a jamais vue, et rien de celle qu'il a
lue. Constaté avant le correctif, sur un tour réellement joué à travers `GET /sessions/{id}`
avec sa base :

```
— le fil du tour —
   criteria_updated · products_found · text_rejected · text_rejected · fallback · done

— GET /sessions/{id}, avant le correctif —
  client    : un écran 144 Hz à 400 $
  assistant : Pardon : il est à 512 $ en promotion.      ← refusé deux fois, jamais affiché

— GET /sessions/{id}, après —
  client    : un écran 144 Hz à 400 $
```

**Le correctif vit dans `boucle.py`, pas dans `prose.py`.** Les deux branches de budget
épuisé empilent désormais le même bloc que les branches qui régénèrent, par une fonction
partagée `_empiler_la_reprise()`. La propriété devient **sans exception : tout message
refusé est suivi d'une reprise**, et la règle de `prose.py` couvre tous les chemins sans
bouger d'une ligne. Le correctif ne rend pas la détection plus fine — il rend la trace
uniforme.

Sur ces deux chemins, la reprise n'a **aucune utilité pour le modèle** : le tour se termine
juste après, plus personne ne relira `messages`. Elle n'existe que pour la trace persistée,
ce qui la rend fragile — elle ressemble à du code mort à qui ne lit pas `prose.py`. D'où un
commentaire sur chaque branche, et l'avertissement dans la docstring de la fonction
partagée.

*Alternative écartée — élargir la détection dans `prose.py` à « dernier message assistant
du tour ».* Elle est **ambiguë** : cette forme est aussi celle d'un tour légitimement clos
par `ask_clarification`, dont le texte a bel et bien été affiché. Les distinguer
redeviendrait heuristique — exactement ce que le correctif de l'étape 11 refusait, et pour
la même raison.

*Alternative écartée — persister le message de repli comme un tour assistant.* Orthogonale :
elle réparerait la moitié « la conversation rechargée ne montre rien », pas la moitié « elle
montre le texte refusé ». Elle reste écartée pour le motif déjà écrit au §7 — le modèle se
lirait affirmer une phrase qu'il n'a pas produite.

**Ce qui a été vérifié plutôt que supposé.** La reprise ajoute un message `user` là où il
n'y en avait pas : l'historique relu au tour suivant porte donc **deux `user` consécutifs**.
Le dépôt a ce précédent — un tour clos par `ask_clarification` se termine sur ses
`tool_result`, et le message client suivant est un second `user` — mais un précédent n'est
pas une vérification. `test_le_tour_suivant_repart_dun_historique_valide_apres_un_repli`
rejoue un second tour **sur l'historique produit par le premier** et fige la suite de rôles
exacte : `["assistant", "user", "assistant", "user", "user"]`.

**Conséquence assumée, et elle était déjà écrite.** Après le correctif, un tour clos par un
repli réapparaît au rechargement comme un message client **sans aucune réponse**. Ce n'est
pas une régression : c'est ce que la ligne du §7 annonce depuis l'étape 10, et l'interface
dit déjà que la conversation reprise est incomplète. **Le correctif fait coïncider le
comportement avec la documentation ; il ne crée pas un trou, il cesse de le combler avec du
faux.**

**Mesure : 720 tests purs (+7), 84 d'intégration — inchangés.** Trois des cinq tests de
`tests/agent/` échouent si l'on retire le correctif ; c'est vérifié, pas supposé.

#### Ce que le correctif a appris, et qui n'est plus un accident

**Deux tests verts, en deux étapes, ont affirmé leur conclusion dans leur nom. C'est un
mode d'échec du dépôt, pas deux accidents.**

| étape | test | ce que son nom affirmait | ce qui était faux |
|---|---|---|---|
| 11 | `test_le_texte_refuse_reste_dans_la_prose_parce_quil_reste_dans_lhistorique` | rester dans l'historique ⇒ partir au client | la conclusion ne suit pas de la prémisse |
| 11 bis | `test_un_message_assistant_sans_reprise_derriere_lui_revient_normalement` | pas de reprise derrière ⇒ il revient | la règle était trop large : le dernier refusé n'en avait pas non plus |

Le mécanisme est le même dans les deux cas, et il est plus insidieux qu'un test absent :
**un test dont le nom énonce la règle rend cette règle évidente au lieu de la rendre
vérifiable.** On relit le nom, on acquiesce, et on cherche le défaut ailleurs. Un test
absent, lui, laisse un blanc qu'une revue de couverture peut voir.

La discipline qui en sort, appliquée aux deux : **le nom d'un test décrit le cas, pas la
conclusion**, et quand une conclusion est renversée, l'ancien raisonnement est gardé dans la
docstring plutôt qu'effacé. C'est la même règle que celle qui gouverne les arbitrages
barrés de ce document — une décision renversée sans sa trace laisse le code
incompréhensible, et la prochaine relecture recommence.

⚠️ **Ce que cela ne dit pas** : rien ici n'automatise la détection. Aucun outil ne signale
qu'un nom de test contient sa conclusion, et la nommer « discipline » est exactement le
genre d'atténuation déclarée que le §7 range parmi les intentions bien rédigées. À
surveiller à l'étape 12, où le harnais ajoutera une nouvelle famille de tests.

---

### Étape 12 — Harnais d'éval ✅

Cassettes enregistrées, dix scénarios, métriques calculées **depuis les événements**,
rapport markdown committé, et un client simulé cloisonné. Le prompt v1 cesse d'être une
intention bien rédigée pour devenir un taux.

**Aucun prompt n'a changé dans cette étape**, pas même d'un mot : régler une formulation
appartient à l'étape 13, et le faire ici rendrait incomparable ce que le harnais mesure.

**Porte de sortie franchie :** `make eval` rejoue les seize prises, écrit
`docs/eval/rapport.md` et sort en **code 0**, critères nº1, nº2 et nº6 à zéro violation.
`make eval-live` a été mené sur trois personas. Et la neutralisation d'une règle du
validateur a bien cassé le harnais — voir ci-dessous, la façon dont elle l'a cassé est le
résultat le plus intéressant de l'étape.

**Mesure : 823 tests purs en 7,4 s, 86 d'intégration** — 103 purs écrits ici, **2
d'intégration**. Le ratio pur/intégration monte de 8,6:1 à **9,6:1**, ce qui est cohérent
avec l'arbitrage E : des métriques qui se calculent sur des suites d'événements
fabriquées à la main se testent sans base.

#### Ce que l'étape a livré

```
src/raiyon/eval/
    cassette.py       # format, en-tête, empreintes, lecture/écriture — PUR
    client.py         # ClientCassette (rejeu) et ClientEnregistreur — PUR, sans SDK
    scenario.py       # Scenario, Attendu, les dix scénarios — PUR
    metriques.py      # suite d'Evenement -> Mesures — PUR
    rapport.py        # Mesures -> tableau markdown stable — PUR
    executeur.py      # joue un scénario contre session.tour(), collecte
    client_simule.py  # le client joué par Haiku, cloisonné
scripts/eval.py       # make eval | eval-enregistrer | eval-live
prompts/client_simule.v1.md
evals/cassettes/*.json          # 16 prises, 244 Ko
docs/eval/rapport.md            # la sortie de `make eval`, committée
tests/eval/                     # 103 tests purs, dont l'isolation par découverte
tests/integration/test_eval.py  # 2 tests : le harnais ne pourrit pas en silence
```

Cinq modules sur sept ne chargent ni `anthropic` ni FastAPI, et
`tests/eval/test_isolation_eval.py` le vérifie **sur le disque**, par découverte. Le
cinquième est `client.py`, que le §5 n'avait pas nommé : c'est lui qui fait que
**`make eval` tourne sans clé API**, et c'est une propriété qu'on peut perdre par un
import distrait.

#### Arbitrages

**A. Une cassette n'enregistre que les réponses du modèle.** Rien d'autre. Les
`tool_result` sont **recalculés** à chaque rejeu par le vrai moteur, la vraie couche
outils et le vrai validateur, sur le seed committé. C'est ce qui fait que l'éval mesure
la **pile entière** : un changement de scoring, une borne recalibrée, une règle du
validateur qui se resserre se voient au rejeu suivant, sans rien réenregistrer.

*Alternative écartée — enregistrer aussi les `tool_result`.* Le rejeu serait entièrement
hors ligne, donc intégrable à `make check`. Écartée parce qu'elle **fige le moteur** : un
scoring cassé rejouerait ses anciens résultats et la suite resterait verte. On testerait
la conduite du dialogue contre un passé figé, pas le produit. *Conséquence assumée : le
rejeu exige Postgres et le seed ; `make check` reste inchangé.*

**B. Rejeu par index, avec assertion d'empreinte.** On rend la n-ième prise, comme le
`FauxClient` de l'étape 8, mais après avoir vérifié que l'empreinte de la requête reçue —
système + outils + messages, sérialisés clés triées — est celle enregistrée. Un écart fait
échouer le scénario **en nommant le tour** où la conversation a divergé, avec un `diff`
lisible sur l'aperçu.

*Alternative écartée — l'index seul.* Une divergence **désynchronise en silence** : le
modèle reçoit la réponse du tour suivant, la conversation part ailleurs, et les métriques
décrivent un dialogue qui n'a jamais eu lieu. C'est le mode d'échec le plus coûteux d'un
harnais, parce qu'il produit **des chiffres au lieu d'une erreur**.

*Alternative écartée — un dictionnaire indexé par empreinte.* Robuste à un
réordonnancement, mais le message d'échec parlerait d'un hash absent au lieu d'un tour, et
une cassette lue hors ordre ne se relit pas à la main.

**C. La cassette porte les empreintes qui la périment.** Trois : le prompt système avec sa
version, le **schéma d'outils**, le modèle et la date. La deuxième est celle que la
formulation « hash du prompt » du §5 laissait échapper — le schéma fait partie du préfixe
mis en cache (§3.13) et détermine ce que le modèle peut faire ; un outil dont la
description change périme la cassette autant qu'un prompt modifié. Au rejeu, un écart
échoue en donnant la commande à taper.

**D. Trois prises sur trois scénarios, une ailleurs.** La température n'est pas fixée
(étape 8, arbitrage 12) : une cassette est **un tirage**, pas une espérance. Trois prises
sur `budget_serre`, `besoin_flou` et `zero_budget_trop_bas` donnent un ordre de grandeur
de la dispersion des métriques nº3 et nº4, donc de quoi savoir à l'étape 13 si un écart
entre deux prompts est un signal ou du bruit. ⚠️ **Trois prises ne sont pas un intervalle
de confiance**, et le rapport ne le prétend nulle part.

**E. Les métriques se calculent depuis les événements, jamais depuis le texte.**
`QuestionPosee` compte les questions, `ProduitsTrouves` porte les produits et le
diagnostic, `TexteRejete` l'origine et les codes, `Repli` son motif, `CriteresMisAJour` les
mouvements refusés. **Aucune expression régulière ne relit la prose** : ce serait un second
validateur, plus faible que le premier, et il finirait par diverger de lui.

Une seule chose lit la prose, et c'est **le validateur lui-même** — `valider()`, les mêmes
cinq règles, contre le contexte réellement fourni. L'exception confirme la règle : on ne
réécrit pas la lecture, on rappelle celle qui existe.

*Coût assumé de cette frontière :* « l'agent a **dit** au client qu'il refusait le
desserrage » n'est mesuré par rien. `Attente.CRITERE_TENU` constate que le critère n'a pas
bougé ; que la phrase le dise est affaire de lecture humaine, et c'est au §7.

**F. La réponse de référence du critère nº4 est choisie à la main, et justifiée.** Elle ne
vient pas du moteur — le déterminer en lançant le moteur reviendrait à le tester contre
lui-même, et la métrique vaudrait 100 % par construction. Chaque `Attendu` porte donc un
identifiant choisi **en lisant le catalogue** et une phrase qui dit pourquoi. Cette phrase
est une **donnée**, pas un commentaire : c'est elle qu'on relira le jour où la métrique
chutera, et sans elle on ne saura pas si le moteur a régressé ou si l'attendu était
mauvais. Six prises sur seize en portent un ; le rapport le dit.

**G. Les tours du client scripté sont des énoncés de besoin, pas des réponses.** Un client
scripté ne réagit pas : le message du tour 3 est écrit d'avance et peut tomber à côté de ce
que l'assistant vient de demander. Chaque tour est donc écrit pour **se suffire**. Le
réalisme conversationnel est le rôle du client simulé, pas des scénarios déterministes.

**H. Le client simulé ne voit que ce qu'un client voit.** Il reçoit la prose livrée
(`Texte`, `QuestionPosee`, `Repli`) et les produits de `ProduitsTrouves`. Il ne voit
**jamais** les `tool_result`, ni l'`EtatSession`, ni un `TexteRejete`. Sans cette cloison
il devient un **oracle** : il « sait » ce que l'assistant a compris, et répond à côté de ce
qu'un vrai client aurait compris. La mesure serait flatteuse et fausse. Son prompt vit dans
`prompts/client_simule.v1.md`, versionné comme les autres (§3.14).

#### Le piège central de l'étape, et il est écrit dans le rapport lui-même

> **Les critères nº1 et nº2 sont garantis par construction depuis l'étape 9. Un tableau qui
> les affiche à zéro ne prouve rien.**

Le validateur refuse le texte fautif, régénère une fois, puis se replie sur un template
écrit en Python : le texte **livré** ne peut donc pas contenir d'hallucination. Le rapport
publie donc **trois couches** — ce qui est livré, ce que le modèle a **tenté** (taux de
rejet par origine et par code), ce qui a fini en **repli** (par motif) — et il porte cette
phrase en tête :

> *Un tableau où le critère nº1 vaut 0 et le taux de repli vaut 30 % décrit un produit qui
> échoue.*

#### Ce que l'étape a appris, et qui n'était pas prévu

**1. Neutraliser une règle du validateur ne fait pas monter le critère nº1 — et c'est une
propriété du harnais qu'il fallait découvrir.** L'expérience a été menée deux fois.

*Version littérale : `regle_montants` retirée de `REGLES`.* Le harnais a cassé, mais pas
là où on l'attendait. La boucle a cessé de refuser un texte qu'elle refusait, n'a donc plus
demandé de régénération, et la conversation rejouée est devenue **plus courte d'un
message** que celle enregistrée : `besoin_flou.3` a échoué en `DivergenceDeRequete`, en
nommant le tour 3 et en montrant le `diff` — là où il y avait un message de reprise, il y a
maintenant le message suivant du client. C'est exactement le mode d'échec que l'arbitrage B
cherche à rendre bruyant.

*Même expérience sur `regle_valeurs_unitaires`, rejeu de `budget_serre` seul* — un scénario
dont le rejet tombe au **dernier** tour, donc sans divergence possible. Trois signaux :
le taux de rejet passe de 2 à **0**, l'avertissement « 4 prises consommées sur 5 » sort, et
le texte fautif est bel et bien **livré au client**. Et le critère nº1 **reste à zéro**.

La raison est structurelle et n'a rien d'un défaut d'écriture : le harnais mesure le
validateur **avec le validateur**. Amputer les règles rend aveugles les deux à la fois.

*Version qui teste réellement le harnais : la boucle calcule le verdict et l'ignore.* Les
cinq règles restent entières côté mesure ; le texte fautif part au client. Le critère nº1
passe alors à **2 griefs ❌** sur `budget_serre` et `make eval` sort en code non nul.

**La conclusion à retenir, et elle est au §7 :** le critère nº1 ne détecte pas une règle
manquante, il détecte un **trou dans la réaction** à une règle qui existe. Ce qui détecte
une règle manquante, c'est le **taux de rejet qui s'effondre** — troisième raison, non
prévue, de publier les trois couches ensemble.

**2. Une attente écrite sur un nom d'outil mesure l'outil, pas le produit.** Le §5 nommait
`BesoinDeBudget` pour le scénario « budget absent ». Écrite ainsi, l'attente a échoué sur
**deux** scénarios où l'agent s'était pourtant très bien conduit : il avait sondé le
catalogue puis posé la question en texte, sans passer par `suggest_next_question` — ce que
le prompt système autorise explicitement, puisque §3.8 dit que la question suggérée **est
une suggestion**. L'exigence porte désormais sur l'invariant réel,
`AUCUNE_RECHERCHE_SANS_BUDGET` : aucune recherche pendant que le budget vaut `None`. Le
passage par l'outil reste **publié sans seuil**, comme observation.

C'est la première correction que le harnais a apportée à lui-même, et elle est arrivée dans
les dix minutes qui ont suivi la première exécution complète.

**3. La métrique nº3 n'a aucun signal en v1, et son zéro est une bonne nouvelle mal
lisible.** *Questions avant première valeur* vaut **0 sur les onze prises** qui livrent une
valeur : sur ce jeu de scénarios, l'agent ne pose jamais `ask_clarification` avant de
montrer quelque chose. La règle « donner avant de demander » (§3.9, section 5 du prompt)
produit donc bien son effet — mais la métrique censée la suivre est au plancher, sans marge
de progression, et l'étape 13 ne pourra rien y lire. Le vrai délai avant première valeur se
compte plutôt en **tours client**, ce que le rapport publie déjà indirectement.

**4. `make eval-live` a montré en une conversation ce que 35 tours scriptés n'ont pas
montré.** Les scénarios déterministes ont enregistré **zéro repli**. La première
conversation du persona `joueur_serre` en a produit un — motif `validation` — au moment
précis où le client a demandé « c'est quoi la différence entre IPS et VA ? ». Le modèle a
voulu répondre depuis sa connaissance du monde, le validateur a refusé deux fois, et le
client a lu la phrase de repli.

La cause est claire : les dix scénarios posent des questions **sur le catalogue**, et un
vrai client pose des questions **sur le domaine**. Le taux de repli de 0 % du rapport est
donc un artefact du jeu de scénarios, pas une propriété du produit. C'est la meilleure
justification qu'on puisse donner au mode `live`, et elle n'était pas anticipée.

**5. Un message assistant qui ne porte qu'un bloc `thinking` clôt le tour sans rien
livrer.** Observé dans la même conversation, à la ligne 21 des 27 tours persistés : juste
après le repli, le modèle a répondu par un unique bloc `thinking`. `_depouiller()` ignore
les types de blocs inconnus — c'est voulu, un bloc inattendu ne doit pas clore une
conversation —, `message.texte` est vide et `message.appels` aussi : la boucle rend son
`IssueDuTour` **sans avoir émis un seul événement**. Le client a écrit « Euh… vous êtes
là ? ». Voir §7 ; le correctif n'est pas dans cette étape.

**6. `claude-sonnet-5` émet des blocs `thinking` sans qu'on les demande.** L'arbitrage 12
de l'étape 8 écartait le thinking étendu ; les cassettes montrent qu'il arrive quand même,
avec sa `signature`. Sans effet sur le rejeu — rien n'est renvoyé à l'API — mais la phrase
« pas de thinking en v1 » décrit ce qu'on demande, pas ce qu'on reçoit. C'est aussi la
cause de la ligne 5.

#### Correctif — ce que `eval-live` a montré ✅

L'étape 12 a fait ce qu'on attendait d'elle. Elle a surtout montré **trois choses que
trente-cinq tours scriptés ne montraient pas**, et ce correctif les traite. Aucun prompt
n'a changé — ni `systeme.v1.md`, ni `grief.v1.md`, ni `client_simule.v1.md` : l'étape 13
doit partir d'une base comparable à celle que le rapport décrit.

**Mesure : 853 tests purs en 7,4 s (+30), 86 d'intégration (inchangé).** Dix-neuf prises
sur onze scénarios, 44 tours client.

---

##### Point 1 — un message vide clôtait le tour sans rien livrer

`_depouiller()` ignore les types de blocs inconnus, et **c'est voulu** : un bloc inattendu
ne doit pas clore une conversation par une exception. Mais quand le message n'en portait
**que** un — un `thinking` seul —, `message.texte` était vide et `message.appels` aussi :
la boucle prenait la branche « aucun `tool_use`, que du texte », loguait `fin_de_tour` en
`INFO`, et rendait son `IssueDuTour` **sans avoir émis un seul événement**. Le client
recevait `done` et rien d'autre.

**Correctif : `MotifDeRepli.REPONSE_VIDE`**, une troisième phrase écrite en Python
(`PHRASE_REPONSE_VIDE`), et un `WARNING` qui nomme les types de blocs reçus. Un motif
distinct, donc **comptable par le rapport** — même raison qu'à l'étape 9 : deux causes qui
se corrigent à deux endroits différents ne partagent pas un compteur.

*Alternative écartée — traiter le message vide comme une itération sans progrès et
reboucler.* Plus généreuse pour le produit : le modèle a une seconde chance, et
`max_iterations` borne déjà le pire cas. Écartée pour une raison mécanique qu'il vaut mieux
ne pas découvrir en production — reboucler laisse `messages` se terminer par un message
**assistant**, et l'appel suivant devient une continuation de ce message plutôt qu'un tour
neuf. Avec un bloc `thinking` en dernière position, ce que l'API en fait n'est écrit nulle
part, et le dépôt a trois précédents de capacités supposées sans être mesurées (§3.13). On
replie, ce qui est sûr, et on **compte**.

**Et le correctif a immédiatement montré que le défaut n'était pas anecdotique.** `make
eval` relancé sur les **seize cassettes existantes**, sans en réenregistrer une seule, fait
passer le taux de repli de **0 % à 5 %** : deux prises — `desserrage_refuse.1` et
`sur_specifie.1` — contenaient déjà un tour où le client n'avait **rien** reçu. Elles
étaient vertes, et elles décrivaient un produit muet.

##### Point 2 — l'assistant et son domaine, et le résultat n'est pas celui qu'on attendait

Persona `joueur_serre`, tour 4 : « c'est quoi la différence entre une dalle IPS et une
dalle VA ? ». Le modèle avait répondu, le validateur avait refusé deux fois, et le client
avait lu `PHRASE_GENERIQUE` — c'est-à-dire une demande de répéter une question posée
clairement, dans un produit qui s'appelle « assistant conseil ».

**Ce qui ne se corrige pas : la règle 5.** Une explication de domaine chiffrée est une
affirmation que le code ne peut pas vérifier, et le validateur n'a aucun moyen honnête de
distinguer « les dalles VA ont un meilleur contraste » d'un « les écrans de cette gamme
montent à 240 Hz » que rien n'a rendu. Une règle qui ne sait pas trancher ne doit pas faire
semblant.

**Ce qui se corrige : la réponse.** `PHRASE_DE_DOMAINE` dit ce que l'assistant peut et ne
peut pas, puis **bascule sur ce que le catalogue contient** quand un sondage a eu lieu dans
le tour — les distributions que `probe_catalog` a rendues, qui sont des faits fournis. La
boucle réduit le `ResultatSondage` en `EtatDuCatalogue` avant de le passer : le
`ResultatSondage` porte un `EtatSession`, et le faire entrer dans le rédacteur d'une
réponse au client rouvrirait ce qu'`evenements.py` ferme.

⚠️ **Le onzième scénario n'a pas produit le repli qu'il devait produire, et c'est le
résultat le plus intéressant du correctif.** `question_de_domaine`, trois prises, deux
tours de question de domaine — dont un qui demande explicitement un chiffre. **Zéro rejet,
zéro repli, sur les trois prises.** Ce que les cassettes montrent :

* le modèle explique très bien IPS contre VA, **qualitativement** — « meilleur contraste,
  noirs plus profonds, angles de vision » —, et **aucune des cinq règles ne tire**, parce
  qu'il n'y a ni chiffre à unité connue, ni nom de produit, ni montant ;
* sur la demande de chiffre, deux prises sur trois **refusent d'elles-mêmes** : « je ne
  peux pas vous donner un ratio exact sans l'inventer, et je ne le ferai pas ». La
  section 2 du prompt fait son travail sans que le validateur ait à intervenir ;
* la troisième **donne les chiffres** — « VA : environ 3000:1 à 6000:1, IPS : 1000:1 à
  1200:1 » — et **le validateur les laisse passer**. Voir §7 : c'est le trou de l'entier
  nu, pris en flagrant délit sur une affirmation de domaine.

La prémisse « l'assistant ne sait pas expliquer son domaine » était donc **trop forte**. Il
l'explique, et il refuse le plus souvent les chiffres tout seul. `PHRASE_DE_DOMAINE` reste
juste et reste nécessaire — la conversation live l'a bien déclenchée —, mais elle est
exercée par les tests unitaires et par aucune cassette. C'est écrit plutôt que masqué, et
**aucune cassette n'a été réenregistrée jusqu'à obtenir le repli attendu** : ce serait
exactement la faute que ce dépôt cherche à ne plus commettre.

##### Point 3 — le critère nº3, et deux lignes de rapport

**3a. Le critère nº3 compte désormais des tours client.** Il valait 0 sur les onze prises
qui livraient une valeur : la règle « donner avant de demander » fonctionne, l'agent
n'appelle jamais `ask_clarification` avant de montrer quelque chose. Une bonne nouvelle,
mais une métrique collée à son plancher ne détecte plus qu'une régression, alors que §5
étape 13 dit de la **viser en priorité**.

§3.9 disait déjà quoi compter : *« le bon indicateur est le délai avant première valeur,
pas le compte de questions »*. On compte donc **combien de fois le client a dû parler**
avant de voir des produits. **Le seuil reste à 2** — il ne veut plus dire la même chose :
« au deuxième message, le client a vu quelque chose ». Un agent qui interrogerait trois
tours d'affilée le ferait tomber, ce que l'ancienne formulation ne voyait pas, ces
questions-là passant par du texte et non par `ask_clarification`.

Effet immédiat : la médiane passe de 0,0 à **1,0**, et la dispersion de `besoin_flou`
devient lisible — 2 à 3 tours selon la prise, là où les questions donnaient 0 partout.
`questions_avant_premiere_valeur` **reste calculée et publiée sans seuil** : elle mesure
désormais la règle de dialogue, pas le délai.

**3b. Les règles qui ne se déclenchent jamais.** Une règle qui ne tire jamais est
indistinguable d'une règle absente — et l'étape 12 avait montré que le critère nº1 ne
détecte pas une règle manquante. Le rapport porte donc une ligne **« règles du validateur
jamais déclenchées »**, dérivée de `CodeGrief` et jamais d'une liste écrite à la main :
un code ajouté demain y apparaît sans qu'on touche à rien, et un test le vérifie par
introspection.

Sur cette exécution : **3 codes sur 6** ne tirent jamais — `id_inconnu`,
`prix_etranger_au_produit`, `nom_reecrit`. Sans cette ligne, « 0,25 grief/tour » se lisait
comme une couverture. *(Six codes pour cinq règles : `regle_montants` en lève deux.)*

**3c. Ce qui ne bouge pas**, et qui devient une règle écrite dans `scenario.py` :
*une attente qui nomme un outil est suspecte par défaut.* Avant d'en écrire une, se
demander si elle décrit un **résultat** ou un **chemin**. Le corollaire vaut pour les
attentes qui décrivent une dégradation : `question_de_domaine` n'exige pas de repli, bien
qu'il ait été écrit pour en provoquer un — figer une défaillance en critère de conformité
la rendrait obligatoire.

##### Ce que le correctif a appris

**1. Un correctif de silence se paie en visibilité, et le chiffre bouge dans le mauvais
sens — c'est normal.** Le taux de repli passe de 0 % à 5 % **sans qu'une seule cassette
change**. Le produit ne s'est pas dégradé : il a cessé de cacher deux tours muets. Un
rapport dont un chiffre empire après un correctif est un rapport qui a commencé à dire la
vérité, et c'est exactement la lecture que l'avertissement en tête du rapport demande.

**2. La lecture du rapport ne change pas, elle se confirme.** Critère nº1 à zéro, taux de
repli à 5 % : deux tours sur quarante-quatre ont servi au client une phrase écrite en
Python. C'est peu, et ce n'est pas zéro — c'est précisément la phrase que le rapport porte
en tête depuis l'étape 12.

**3. Le trou du validateur n'est pas là où le correctif le cherchait.** On est parti
corriger « l'assistant ne sait pas expliquer son domaine » ; les cassettes ont montré qu'il
l'explique bien, et qu'il refuse les chiffres deux fois sur trois. Ce qu'elles ont montré
en revanche, et que personne ne cherchait : **une affirmation de domaine chiffrée passe le
validateur** dès que le chiffre ne porte pas d'unité connue. « 3000:1 » est livré au client
sans qu'aucune règle ne le voie. Nouvelle ligne au §7.
---

### Étape 13 — Itération sur les prompts ✅

C'est ici que le produit devient bon, et c'est l'étape qu'on est tenté de sauter.

Le harnais existe désormais : chaque modification de prompt se mesure. Faire
varier le prompt système, comparer les tableaux, versionner ce qui gagne. Viser
en priorité la métrique nº3 — le délai avant première valeur — qui est ce que
ressent un vrai utilisateur.

**Deux dettes de l'étape 8 se règlent ici, et elles y ont été reportées explicitement :**

1. **Résorber la duplication entre les descriptions d'outils et le prompt système**
   (arbitrage 6 de l'étape 8). `DESCRIPTION_SONDER` et `DESCRIPTION_PRECISION` portent
   des règles de dialogue — « une fourchette de prix n'est jamais le prix d'un produit »,
   « ne jamais demander sans donner quelque chose » — que le prompt v1 redit. La cible est
   la répartition « le contrat d'appel dans la description, la conduite dans le prompt »,
   qui suit le raisonnement d'`erreurs.py` : deux rédactions d'une même règle finissent
   par en dire deux choses. Elle a été **reportée, pas abandonnée** — toucher
   `schema_outils.py` invalidait le cache de prompt et rouvrait une couche fermée, et
   surtout **on ne savait pas laquelle des deux formulations portait l'effet**. C'est
   exactement ce que le harnais sait dire, et c'est pour ça que la dette est ici.
2. **Rouvrir le thinking étendu si la métrique nº4 plafonne** (arbitrage 12). Écarté en v1
   parce que les blocs `thinking` doivent être réinjectés verbatim et persistés, ce qui
   alourdit l'historique pour un raisonnement qui tient en deux lignes.

Le prompt v1 a été écrit **court exprès** — onze sections numérotées, une idée chacune —
pour que cette étape puisse en déplacer **une** et attribuer l'effet. Un prompt v1 maximal
aurait laissé les métriques nº3 et nº4 sans marge de progression et rendu chaque
changement ultérieur non attribuable.

**Porte de sortie :** au moins deux versions de prompt comparées chiffres en
main, et la trace de cette comparaison conservée dans le dépôt.

#### Jalon 0 — l'instrument, et aucun prompt ne change

Le harnais de l'étape 12 sait dire **combien**. Il ne sait pas dire **quoi**, et une
itération sur les prompts qui ne sait pas dire quoi itère sur des compteurs.

**Le diagnostic qui fonde l'étape, et il n'est pas celui que §7 annonçait.** Les onze
griefs du rapport de l'étape 12 tiennent en **cinq tours**, dans cinq prises sur
dix-neuf. En relisant chaque texte refusé contre sa réécriture : la section 4 du prompt
tient — « une fourchette n'est jamais un prix » n'est enfreinte nulle part. Ce qui casse
est §2, sur **trois opérations qu'aucune section ne nomme** : arrondir une borne, dériver
un écart entre deux nombres fournis, chiffrer un assouplissement que le diagnostic n'a
pas rendu. §2 interdit d'estimer et d'arrondir ; elle ne dit rien du **calcul**, et
« 189,99 − 142,99 = 47 » est arithmétiquement vrai sans avoir jamais été fourni.

⚠️ **Cette attribution a coûté une demi-heure de relecture manuelle de cassettes, et le
harnais avait l'information.** C'est la raison d'être du point A.

**A. Le rapport publie la phrase refusée, pas seulement son code.** `TexteRejete` porte
désormais le texte qu'il a refusé, et le rapport gagne un **appendice A** : une ligne par
grief, avec le scénario, la prise, **le tour**, l'origine, le code, l'extrait et la
phrase. Recalculé au rejeu comme tout le reste (arbitrage A de l'étape 12), donc
**disponible rétroactivement** sur les cassettes de l'étape 12 sans en réenregistrer une —
et c'est ce qui a permis de vérifier le diagnostic ci-dessus au lieu de le croire. Il est
dérivé du verdict du validateur : un sixième code de `CodeGrief` y apparaîtrait sans
qu'on touche à `rapport.py`, et un test le constate.

**B. Un jeu de cassettes par version de prompt.** `evals/cassettes/systeme.<nom>/` et
`docs/eval/rapport.<nom>.md`. Les dix-neuf cassettes de l'étape 12 sont conservées sous
`systeme.v1-etape12/`, **intactes**, et `make eval-etape12` les rejoue — sans quoi
« conservé » voudrait seulement dire « pas effacé ».

*Alternative écartée — n'écraser et ne garder que les rapports.* Moins cher. Écartée parce
qu'elle fait décrire par §7 et par le correctif de l'étape 12 un tirage qui n'existerait
plus nulle part, et parce qu'un changement de moteur ultérieur ne se rejouerait plus
contre v1 : la comparaison cesserait d'être reproductible, ce qui est précisément la
propriété que l'arbitrage A achète en ne figeant pas les `tool_result`.

⚠️ **Le rapport archivé a été régénéré, et le diff dit pourquoi c'est sans conséquence** :
**123 insertions, zéro suppression.** Chaque chiffre et chaque ligne de la version
étape 12 sont inchangés ; seuls les trois appendices s'ajoutent, calculés depuis les mêmes
cassettes. C'est la preuve que « rétroactivement » n'est pas une figure de style.

**C. La version en vigueur se choisit** — voir §3.14, amendement de l'étape 13.

**D. La cible 2 se mesure par une observation, pas par une attente.** L'attente évidente —
*sur un tour déclaré de domaine, la prose ne contient aucun chiffre* — a été écrite, puis
**refusée**. Elle est vraie sur v1 ; elle deviendrait fausse dès que le prompt demande au
modèle de basculer sur ce que le catalogue contient, ce qui est le comportement que le
jalon 2 cherche à produire. **Elle pénaliserait le changement qu'elle évalue.** Et
l'admettre en autorisant les chiffres fournis reviendrait à réécrire le validateur — une
seconde lecture de la prose contre le contexte, plus faible que la première, que
l'arbitrage E de l'étape 12 refuse.

D'où : les scénarios **déclarent** leurs tours de domaine, le harnais y publie un compte
de valeurs chiffrées **sans seuil**, et le rapport recopie la prose entière en
**appendice B** — la preuve se relit, le compteur n'en est que le résumé. Le compte
réutilise `extraction.NOMBRE`, et deux tests le tiennent : l'un vérifie qu'il n'existe pas
de seconde extraction de nombre dans le harnais, l'autre qu'une prose de domaine chiffrée
**ne fait pas échouer** `make eval`.

La règle générale de `scenario.py` gagne son second membre : *une attente qui lit la prose
est suspecte, et la question n'est pas seulement « est-elle vraie sur le prompt que je
mesure ? » mais « restera-t-elle vraie sous les versions à venir ? ».*

**E. Le markdown, mesuré avant d'être corrigé.** **Appendice C**, sans seuil : les formes
que `web/rendu.js` n'interprète pas. Sur les dix-neuf cassettes de l'étape 12 : **44
backticks, 56 puces, 32 listes numérotées, 0 titre**. Le gras n'est pas compté — il est
rendu, et le compter ferait descendre le compteur en demandant au modèle d'écrire moins
bien.

**F. Trois prises partout, six sur `question_de_domaine`.** L'arbitrage D de l'étape 12
ne payait trois prises que là où la dispersion l'intéressait. Ses propres chiffres ont
montré que ça ne suffit pas : `besoin_flou` fait 0, 0, 2 rejets selon la prise,
`budget_serre` 2, 0, 0 — **l'écart prise-à-prise vaut la totalité de l'effet qu'on espère
mesurer**. Sur un scénario à une prise, un écart v1 → v2 est indistinguable du tirage.

**La comparaison applique la règle au lieu de la rappeler.** Le rapport de l'étape 12
finissait sa section « dispersion » par *« un écart inférieur à cet ordre de grandeur
n'est pas un signal »* — une phrase qui se lit une fois puis s'oublie, après quoi deux
tableaux de trente-six lignes se comparent à l'œil, et l'œil trouve ce qu'il cherche.
`raiyon/eval/comparaison.py` calcule donc le verdict : la dispersion est l'étendue
`max - min` des prises de la campagne **de référence**, sommée sur les scénarios, et
chaque écart porte « au-delà » ou « dans le bruit ».

⚠️ **C'est une borne, pas un écart-type, et elle est délibérément généreuse** : elle
déclare « signal » moins souvent qu'un test statistique, ce qui est le sens dans lequel ce
dépôt préfère se tromper. *Alternative écartée — un test statistique.* Il rendrait une
valeur-p sur trois prises par scénario, c'est-à-dire une précision apparente très
supérieure à ce que les données portent. Le dépôt refuse déjà d'appeler trois prises un
intervalle de confiance.

**Dette nº1 de l'étape 8 — reportée, et voici pourquoi.** Résorber la duplication entre
`DESCRIPTION_SONDER` / `DESCRIPTION_PRECISION` et le prompt système reste à faire.
`schema_outils.py` fait partie du préfixe mis en cache : le toucher périme les cassettes
au même titre qu'un prompt, et le faire dans la même version qu'un changement de prompt
rendrait l'effet **inattribuable** — ce que la dette dit elle-même vouloir éviter. Elle
entre au §7 comme ligne ouverte.
⚠️ **Ce report est le dernier.** À l'étape 17, la dette a été **décidée non fermée**, avec
son chiffre — ~366 appels, davantage que l'étape 15 entière —, et retirée de tout ce que le
dépôt s'engage à traiter. Voir §7 et l'étape 17.

**§5 étape 13 demandait quelque chose d'inapplicable, et il vaut mieux l'écrire.** « Viser
en priorité la métrique nº3 » ne peut pas se faire : depuis le correctif de l'étape 12,
nº3 compte les **tours client** avant la première valeur, son minimum atteignable est
**1**, et la médiane vaut déjà 1,0. Elle n'a pas de marge. Ce qu'on en fait à la place :
elle devient un **garde-fou**, publié dans chaque comparaison, et le risque réel est
qu'elle **monte** — un modèle rendu plus prudent avec les chiffres sonde davantage et
montre plus tard. Le résultat cherché n'est donc pas « le taux de rejet baisse » mais
« il baisse **sans** que nº3 passe à 2 », et c'est cette paire qui se publie ensemble.

#### Jalon 2 — `systeme.v2.md`, les trois cibles en une version

**Le découpage v2 (cible 1) / v3 (cibles 2 et 3) a été révisé, et la raison est
budgétaire.** Il coûtait ~500 appels ; les crédits couvrent une campagne. L'arbitrage est
pris en connaissance de cause, et ce qu'il coûte est écrit ici plutôt que laissé à
deviner :

1. **L'attribution entre cibles ne vient plus de l'isolation expérimentale** mais de
   l'appendice A : on **lit** que « 65 $ » et « 47 $ de plus » ont disparu. C'est une
   attribution par inspection, plus faible qu'un plan d'expérience.
2. **La dérive du modèle reste dans la comparaison**, les deux jeux ne datant pas du même
   jour. Publiée en **borne supérieure**, jamais comme la dérive.
3. **Le prompt grandit de trois sections d'un coup.** Si nº3 monte ou nº4 baisse, **la
   longueur est un suspect au même titre que le contenu**, et la parade serait de fondre
   plutôt que d'ajouter.

**Une correction au point 1, trouvée avant la campagne et non après.** « Les cibles 2 et 3
n'ont aucune empreinte sur le taux de rejet » était **faux pour la cible 3**.
`SEPARATEURS_DE_PHRASE` traite le saut de ligne comme une fin de phrase : les listes que
§14 interdit produisaient un produit par ligne, donc une **phrase étroite par produit** —
exactement le contexte dans lequel la règle 2 attribue un montant. Basculer vers de la
prose continue aurait donné des phrases nommant trois produits et portant trois prix,
dégradant l'attribution et rendant les faux positifs plus probables ; la cible 3 aurait
alors eu une empreinte sur le taux de rejet, inséparable de celle de la cible 1.

§14 fait donc de « **une ligne par produit** » l'instruction, et retire la prose continue.
La prédiction est **posée avant la campagne** (`PREDICTIONS` dans `scripts/eval.py`) et
publiée dans `rapport.v2.md` : si le taux de rejet bouge malgré la parade, c'est de ce
côté qu'il faut regarder d'abord. Une prédiction datée se confirme ou s'infirme ; une
explication trouvée après se raconte — et le correctif de l'étape 12 a déjà montré qu'un
diagnostic plausible formulé après coup pouvait être entièrement faux.

**§13 n'ajoute aucun chiffre au prompt**, et c'est délibéré : sa première rédaction
montrait une réponse modèle en bloc de citation (« 32 écrans sont en VA et 13 en IPS »).
Dans la section dont tout le propos est de ne pas produire un chiffre qu'on ne vous a pas
donné, et sous la forme qui appelle le plus l'imitation, c'était une contradiction. La
citation garde le refus, qui ne porte aucun chiffre ; la bascule est enseignée comme un
**geste** — sonder, puis dire la répartition rendue.

**Reportés, et écrits comme tels** : le découpage v2/v3 (les deux prompts de
`docs/prompts/` se lisent ensemble, la décision et sa révision), la dette nº1 de
l'étape 8, `grief.v1.md`, et la fuite des exemples chiffrés du prompt (§7).

#### Jalon 3 — l'arbitrage, et ce que la campagne pouvait démontrer

**Trois cibles, trois natures de preuve — et ce n'est pas un défaut du protocole, c'est ce
que le protocole permettait.**

* le **markdown** est démontré **par les chiffres** : 51 occurrences par passe contre 0,
  seul écart au-delà de la dispersion (± 43) ;
* la **rédaction chiffrée** est attribuée **par inspection de l'appendice A** : l'arrondi
  de borne a catégoriquement disparu — cinq griefs en base, aucun en v2, et une cassette
  écrit `64,98` là où v1 écrivait « 65 $ » — tandis que la dérivation d'écart tient bon,
  trois griefs des deux côtés ;
* le **périmètre de domaine** se lit **à l'appendice B**, et nulle part ailleurs.

⚠️ **Avec ± 7 de dispersion sur les rejets, cette campagne ne pouvait pas démontrer la
cible 1 par l'agrégat.** Le taux de rejet passe de 3,00 à 2,00 par passe : très en deçà du
bruit, et il l'aurait été quel que soit le résultat. **C'était su avant de la lancer, pas
découvert après** — c'est la raison d'être de l'appendice A, écrit au jalon 0 précisément
parce qu'« un taux qui descend de 11 à 5 ne dit pas quelle forme a disparu ».

**Ce qui emporte l'arbitrage n'est donc aucun agrégat.** C'est l'appendice de domaine :

    v1  « Bonne question, ça change vraiment l'usage : - Dalle VA : meilleur
          contraste, noirs plus profonds… »                        → 0 chiffre
    v2  « Sur les 9 écrans qui correspondent à vos critères, la répartition
          est : 6 en dalle VA, 3 en dalle IPS. »                    → 8 chiffres

v1 **enseignait la technologie d'affichage** — ce que §2 lui interdit — et le faisait sans
un seul chiffre. v2 refuse le cours et bascule sur le catalogue, en ne citant que des faits
fournis. **C'est la démonstration de l'attente refusée au jalon 0, point D** : une attente
« aucun chiffre sur un tour de domaine » aurait **passé sur v1 et échoué sur v2**, donc
pénalisé exactement le comportement qu'elle était censée obtenir. Mesuré, pas argumenté.

**`systeme.v2` passe en vigueur.** Aucune mesure ne recule, une avance au-delà du bruit,
les critères nº1, nº2, nº4 et nº6 inchangés, et le taux de repli tombe à zéro.

**Contre-argument, et il est réel** : v2 porte trois changements et la campagne n'en
démontre statistiquement qu'un. Un relecteur qui n'accepterait que la preuve par agrégat
devrait conclure « une cible sur trois ». La réponse n'est pas de gonfler les chiffres,
c'est que l'appendice **est** une preuve — recopiée d'un artefact committé que n'importe
qui peut relire — et qu'elle est plus forte, sur ces cibles-là, qu'un delta noyé dans le
bruit.

##### La métrique nº3, et le double standard évité de justesse

Elle passe de 2,0 à 1,0 de médiane, et cette baisse a d'abord été publiée **sans sa
dispersion**, alors que les cinq autres mesures portaient toutes leur verdict. Un double
standard sur la seule métrique qui va dans le bon sens est ce qu'un relecteur voit en
premier, et il aurait raison.

Corrigé : nº3 est un compteur comme les autres, avec son étendue. Et sa correction en a
appelé une seconde, plus profonde. Son étendue mesurée valait **zéro** sur les onze
scénarios de la base — donc n'importe quel écart y était « au-delà du bruit ». Or l'étape
12 avait mesuré `besoin_flou` à **2, 2 puis 3 tours** sur le même prompt : l'étendue de
cette métrique n'est pas nulle, elle n'a pas été revue à ce tirage-là. **Le module écrivait
qu'une dispersion nulle ne veut pas dire « stable » et traitait pourtant l'étendue observée
comme une borne dure** — il documentait le piège et tombait dedans.

Chaque scénario contribue donc désormais **au moins un pas** (`PLANCHER_DETENDUE`). Trois
tirages identiques bornent l'étendue par en dessous, ils ne la mesurent pas. La seule
mesure que ce plancher fait basculer est nº3, dont on savait par ailleurs que son étendue
n'était pas nulle ; le markdown (51 contre 43) reste au-delà.

⚠️ **Au passage, la meilleure illustration de « une cassette est un tirage » que le dépôt
ait produite** : la même métrique nº3, sur le **même prompt** `systeme.v1`, vaut 1,0 sur le
tirage de l'étape 12 et 2,0 sur la ligne de base. Rien n'a changé que les tirages.

##### La neutralisation, et ce qu'elle a trouvé

Trois choses cassées, trois tests qui tombent :

| Ce qu'on casse | Ce qui tombe |
|---|---|
| L'appendice A ne dérive plus de `CodeGrief` (un code écrit à la main) | `test_lappendice_des_refus_est_derive_de_codegrief_et_non_dune_liste` |
| `DIVERGENCES_ATTENDUES` devient une tolérance (l'appel de vérification disparaît) | `test_une_ligne_qui_ne_diverge_plus_fait_echouer_le_rejeu` |
| Le plancher de dispersion disparaît | quatre tests de `test_comparaison.py` |

⚠️ **La deuxième n'a rien cassé au premier essai**, et c'est ce que la neutralisation
existe pour trouver. Le test appelait `_verifier_les_divergences_attendues` **directement**
au lieu de passer par `mesurer_le_jeu` : la garde existait et n'était branchée à rien de
vérifié. Elle passe désormais par le rejeu réel, en déclarant divergente une cassette qui
se rejoue parfaitement.

##### Un défaut qu'aucun type ne voyait

`SYSTEME_PAR_DEFAUT` et le défaut du champ `Settings.prompt_systeme` écrivaient **la même
valeur à deux endroits**. Mettre v2 en vigueur a déplacé la première et oublié la seconde :
pendant une demi-heure, le dépôt **annonçait** `systeme.v2` et **servait** `systeme.v1`.
C'est le test de la version par défaut qui l'a attrapé, par chance plutôt que par
construction. La valeur vit maintenant dans `config.py` seule, et un test constate que la
constante **est** le défaut du champ plutôt qu'une copie.

#### ⭐ L'audit que deux incidents appellent : le prompt exige-t-il des chiffres que les outils fournissent ?

**Deux fois dans la même étape, le même motif.** Au jalon 1 : la section 9 ordonne de dire
**quel mouvement a été refusé**, et `mouvements_refuses` ne porte pas la valeur refusée —
le validateur punissait donc l'obéissance. Au jalon 2 : la section 7 ordonne de dire **de
combien un produit dépasse le budget**, et `ecart_usd` n'existe que pour la zone de
tolérance — le modèle calcule `12,99 $` parce qu'on le lui demande et que personne ne le
lui donne.

Ce n'est pas deux accidents, c'est un motif : **le prompt ordonne de dire un chiffre que la
couche outils ne garantit pas de fournir.** Le tableau ci-dessous est l'audit systématique,
et il dit d'avance où sera le troisième.

| Obligation du prompt | Champ qui la fournit | État |
|---|---|---|
| §2, §11 — le prix d'un produit | `search_products` → `produits[].prix_usd` | ✅ fourni |
| §11 — une caractéristique d'un produit | `search_products` → `produits[].specs` | ✅ fourni |
| §4 — la fourchette de prix du sous-catalogue | `probe_catalog` → `fourchette_prix.plus_bas` / `.plus_haut` | ✅ fourni |
| §4, §13 — un comptage du catalogue | `probe_catalog` → `dans_le_budget`, `champs[].distribution` | ✅ fourni |
| §10 — la valeur d'un assouplissement proposé | `search_products` → `diagnostic.propositions[].valeur_atteignable` | ✅ fourni, **et facultatif** — `None` quand aucune valeur n'est atteignable, auquel cas la section 12 de v2 interdit d'en inventer une |
| §7 — l'écart au budget d'un produit **de la zone de tolérance** | `search_products` → `au_dessus_du_budget[].ecart_usd` | ✅ fourni |
| §7 — l'écart au budget d'un produit **hors zone de tolérance** | *aucun* | 🔴 **trou** — mesuré à `zero_budget_trop_bas.3` : « il est à 142,99 $, donc 12,99 $ au-dessus de votre plafond » |
| §9 — la valeur d'un mouvement refusé | *aucun champ direct* — `mouvements_refuses[]` porte `champ`, `operateur`, `motif` | 🟠 **contourné** à l'étape 13 en appariant le `tool_use` (voir `valeurs_des_mouvements_refuses`) |

**Les deux corrections possibles pour le trou de `ecart_usd`, et aucune ne se fait ici :**

* *que `search_products` rende l'écart pour **tout** produit au-dessus du budget, pas
  seulement pour la zone de tolérance.* La plus juste — le chiffre devient fourni, et la
  section 7 cesse d'exiger un calcul. ⚠️ Elle touche la couche outils, donc le
  `tool_result`, donc **l'empreinte de requête** : les quarante-trois cassettes du dépôt
  divergeraient au deuxième tour. C'est le mécanisme du jalon 1, à une échelle bien plus
  grande ;
* *que la section 7 cesse d'exiger le chiffre quand il n'est pas fourni* — « dites qu'il
  dépasse, et de combien **si vous l'avez** ». Gratuite en cassettes puisqu'un prompt neuf
  s'enregistre de toute façon. ⚠️ Elle affaiblit un critère d'acceptation : le nº2 est
  précisément « budget jamais dépassé sans présentation explicite », et l'écart chiffré est
  ce qui rend la présentation explicite.

Le choix n'est pas évident, et il n'a pas à être fait dans une étape qui mesure des
prompts. **Ce qui compte est que le trou soit nommé avant qu'un troisième cas ne le
redécouvre**, ce que ce tableau fait.

---

### Étape 14 — README et finition ✅

Installation, lancement, exemples d'usage, tableau de métriques, schéma
d'architecture, et une section honnête sur ce qui est réel et ce qui est dérivé
dans le catalogue.

**Porte de sortie :** un `git clone` suivi de la procédure du README, sur une
machine vierge, aboutit à une conversation fonctionnelle.

C'est la seule vérification qui compte pour un portfolio.

---

### Étape 15 — Variante machine à états ✅

Une **deuxième orchestration**, mise en concurrence avec l'agent sur les mêmes scénarios,
les mêmes cassettes-sœurs et le même tableau de métriques. Elle ne remplace pas l'agent :
les deux restent lançables et mesurables après l'étape.

#### Ce qui rend l'étape possible — une propriété **rétrospective**, pas une intention

Le harnais d'éval est agnostique à l'orchestration, et **personne ne l'a conçu pour ça.**
`raiyon/eval/executeur.py` ne connaît que la signature de `session.tour()` —
`Generator[Evenement, None, IssueDuTour]` — et tout ce que `metriques.py` mesure se dérive
de deux choses : la suite d'`Evenement` et les `messages` persistés. **Aucune mesure ne lit
`boucle.py`.**

La propriété vient de ce que trois consommateurs indépendants — la console de l'étape 8, le
fil SSE de l'étape 10, l'exécuteur d'éval de l'étape 12 — ont été écrits contre un **même
générateur**, chacun pour sa propre raison. Aucun des trois n'a été écrit en pensant à une
seconde orchestration.

⚠️ **On s'en aperçoit à l'étape 15 ; on ne l'avait pas prévu.** La distinction n'est pas de
la modestie de façade : ce dépôt a déjà relu plusieurs de ses choix comme s'ils avaient été
prémédités, et c'est exactement ce qu'il ne faut pas ajouter. Une contrainte tenue par
discipline sur trois étapes a produit un effet qu'on découvre après coup — c'est une bonne
nouvelle, et elle se raconte comme telle.

#### Jalon 0 — l'instrument, et aucun modèle n'est appelé ✅

Le harnais est modifié **avant** que quoi que ce soit d'autre bouge, et la neutralité de la
modification est vérifiée sur les trois rapports committés. Motif repris du jalon 0 de
l'étape 13, parce qu'il a fonctionné.

- `RAIYON_ORCHESTRATION` (`agent` | `machine`, défaut `agent`) dans `config.py`, **déclarée
  et pas encore consommée** : `session.tour()` ne bascule sur rien, il n'existe qu'une
  orchestration. Elle donne sa source à l'en-tête de cassette et à la garde ci-dessous ;
  c'est écrit dans le commentaire du champ, sans quoi un relecteur y verrait un branchement
  oublié.
- `EnTete.orchestration`, optionnel, **traité exactement comme `usage`** : absent n'est pas
  une erreur, présent mais mal formé est refusé, et `en_json()` omet la clé quand elle vaut
  `None`. ⚠️ **`None` ne devient jamais `"agent"` dans la dataclass** — un défaut
  matérialisé là serait réécrit au premier aller-retour de sérialisation, et `make
  eval-etape12` constaterait une archive modifiée que personne n'a décidé de modifier. La
  lecture « une cassette sans champ vient d'un agent » est vraie et datée ; elle est faite
  **à l'usage**, dans `scripts/eval.py`.
- Une **garde de contamination** à l'enregistrement : `enregistrer` refuse d'écrire dans un
  jeu qui porte déjà une autre orchestration, et le message donne la commande à taper.
  ⚠️ Elle ne couvre **pas** la première campagne d'un jeu — répertoire vide, rien à
  comparer — et c'est justement l'enregistrement le plus cher. Ce qui couvre ce cas est le
  tir d'essai du jalon 4 ; les deux mécanismes sont complémentaires.
- La **mesure nº7** (§4) et la réserve sur `iterations` : chez une machine à états, le
  nombre d'itérations est une **constante** décidée par le graphe, pas un résultat. Sa
  variance nulle se lirait comme une stabilité gagnée. La réserve est posée **avant** la
  campagne, pas quand le chiffre sortira.
- Confirmé sans rien écrire : `systeme.machine.v1` satisfait le motif de
  `Settings.prompt_systeme`, et `jeu_en_vigueur` en dérive le jeu `machine.v1`, les
  cassettes `evals/cassettes/systeme.machine.v1/` et le rapport
  `docs/eval/rapport.machine.v1.md`. **L'axe d'identité des cassettes reste la version de
  prompt**, la machine se désigne par la sienne, et aucune ligne de `scripts/eval.py` ne
  change.

**Porte de sortie franchie :** `make check` vert à 926, les trois rapports et les deux
comparaisons rejoués **sans `ANTHROPIC_API_KEY`** — c'est la propriété que `eval/client.py`
achète, et l'`unset` la vérifie au lieu de la supposer. **Zéro fichier touché sous
`evals/cassettes/`**, et les cinq documents d'éval modifiés **par pur ajout, sans une seule
suppression** : aucun chiffre existant n'a bougé, ce que le jalon existait pour prouver.

#### Jalon 1 — `decider()`, et la mesure nº8 ✅

> **Le modèle extrait, le code décide.**

`raiyon/machine/decision.py` : une fonction **pure**, qui ne reçoit **jamais de prose**.
Elle voit un `EtatSession` et le `ResultatOutil` de l'action précédente du même tour, et
rend une action d'une union fermée de cinq — `Sonder`, `Suggerer`, `Rechercher`,
`DemanderPrecision`, `Rediger`. C'est la fonction que §3.6 avait déclarée perdue avec
l'agent, et elle est **indépendante du résultat de la campagne** : elle resterait vraie si
la campagne n'avait jamais lieu.

- **La frontière achète tout le reste, et elle se perd d'un seul paramètre.** Si
  `decider()` recevait le message du client, il lui faudrait un modèle pour le comprendre,
  elle cesserait d'être pure, et la mesure nº8 s'évaporerait avec elle.
- **`DemanderPrecision` ne porte pas de texte, seulement le champ visé.** Le code décide de
  quoi on parle, le modèle écrit la phrase. L'option « la relance est un gabarit sans appel
  modèle » a été écartée : une machine qui gagne le critère nº1 en cessant de parler a
  changé de produit, et la campagne ne comparerait plus deux orchestrations mais deux
  produits.
- **Elle ne redécide aucun invariant de `raiyon.tools`** — jeton de parole, clamp, garde
  « un tour, une catégorie », zone de tolérance. Deux rédactions d'une même règle sont la
  maladie de la dette nº1 de l'étape 8.
- **Deux appels modèle par tour** — extraction, puis rédaction **ou** question, jamais les
  deux. La machine a donc un plancher mécanique de **2,00 appel par tour**, contre 2,36
  mesuré sur `v2` (mesure nº7). Prédiction posée avant la campagne.
- **Sous-produit** : `docs/prompts/etape-15.md` est la spécification du diff du jalon 3 —
  quelles sections de `systeme.v2.md` passent dans le code, lesquelles restent, et
  **trois désaccords motivés** avec la lecture préparatoire (§7 et §10 restent, §8 part
  avec une perte nommée).

**Ce que la machine fera moins bien, écrit avant la campagne :** `decider()` ne voit pas la
prose, donc elle ne sait pas qu'on lui a posé une question de domaine. Au tour 2 de
`question_de_domaine`, elle relance une recherche. C'est le coût des « virages hors-script »
que §3.6 annonçait, et il est daté d'avant la mesure.

**Porte de sortie franchie :** `make check` vert à 952 (+26), **sans base, sans conteneur, sans
clé** — la suite entière du jalon tourne hors ligne, et c'est la propriété qu'on achète.

#### Jalon 2 — l'orchestrateur, branché sur les vrais outils ✅

`raiyon/machine/orchestrateur.py` conduit un tour avec **deux appels modèle** : une
extraction qui n'expose que `record_criteria`, la boucle `decider()` / outils sans aucun
appel modèle, puis une rédaction **ou** une question, jamais les deux.

`raiyon/orchestration.py` porte le `Protocol` `Orchestrateur` et `repondre_en_vigueur()`.
`session.py` change **d'un import et d'une ligne** — c'est le seul fichier d'`agent/` que
l'étape touche, et `make eval` rejoué à l'identique le prouve.

- **« Même signature » est vérifié, pas affirmé.** Le `Protocol` a été écrit d'après
  `boucle.repondre`, qui ne bouge pas d'une ligne ; c'est mypy qui refuse la fonction non
  substituable, à l'endroit qui prétend rendre l'une ou l'autre.
- **La garde de contexte (point A)** : la rédaction reçoit toujours les agrégats du
  sous-catalogue courant. C'est un **avantage d'orchestration, pas un correctif** — une
  machine à états peut garantir le contexte de sa rédaction, un agent ne le peut pas,
  décider de ses outils étant ce qui fait de lui un agent. Un appel d'outil de plus par
  tour, **aucun appel modèle** : le plancher de 2,00 tient. Mesure nº8 de 16 à 17.
- ⚠️ **La prédiction qui va avec, posée avant la campagne** : plus d'agrégats en contexte,
  c'est plus de chiffres dans la prose, donc **potentiellement plus de rejets**. Si le taux
  de rejet de la machine monte, c'est le premier endroit où regarder — pas une supériorité
  de l'agent.
- **L'historique va à la rédaction**, comme chez l'agent. *Alternative écartée — un rendu
  sans mémoire* : plus simple, et elle **truque la comparaison**, `comparaison` devenant
  impossible par construction. La différence entre les deux orchestrations doit rester la
  décision, jamais la mémoire.
- **Un message du modèle est persisté réduit à ce dont l'orchestrateur s'est servi** : le
  texte de l'extraction est jeté, les `tool_use` de la rédaction aussi. Une seule règle
  ferme deux trous — un texte jamais lu qui réapparaîtrait au rechargement (la brèche de §2
  du correctif de l'étape 11), et un `tool_use` orphelin qui rendrait l'historique
  irrecevable au tour suivant.
- **Les appels d'outils du code s'écrivent comme ceux du modèle** : un `tool_use`
  synthétique, puis son `tool_result`. Il n'y a pas d'alternative — `contexte_des_messages()`
  lit les faits dans les `tool_result` et nulle part ailleurs, et toute autre forme viderait
  le `ContexteFourni` du validateur.
- **Les consignes de l'appel nº2 ne sont pas persistées** : un bloc `text` de rôle `user`
  sans `tool_result` a exactement la forme d'un message client, et `prose.py` le rendrait
  comme une parole du client.

**Porte de sortie franchie :** `make check` vert à **981** (+29), conteneur arrêté et sans
clé ; `make test-int` à 98 ; `make eval` rejoué **sans qu'aucun rapport ne bouge** — l'agent
n'a pas été touché. Vérification manuelle : les deux orchestrations tiennent une
conversation de deux tours, mêmes types d'événements à la console, session persistée,
second tour relu sans erreur d'appairage — 8 appels API.

⚠️ **Constaté à la vérification manuelle, et c'est le point A qui paie** : au second tour,
la machine a répondu « sur les huit écrans 27 pouces de votre fourchette, cinq sont en VA et
trois en IPS ». Sans la garde, ces trois nombres auraient été **fabriqués**, et aucune règle
du validateur ne les aurait vus.

#### Jalon 3 — `systeme.machine.v1.md`, par soustraction ✅

`prompts/systeme.machine.v1.md` est `systeme.v2.md` **moins §5, §6 et §8** — 178 lignes
moins 29, **zéro ligne ajoutée, zéro modifiée**. La numérotation d'origine est conservée
avec ses trous : §1, §2, §3, §4, §7, §9, §10, §11, §12, §13, §14.

Le critère de tri tient en une phrase : *une section qui dit **qui parle quand** part dans
le code ; une section qui dit **ce qui peut être écrit** reste au prompt, et vaut pour les
deux orchestrations.* Le verdict section par section est dans `docs/prompts/etape-15.md`.

- **La garantie n'est pas un commentaire.** `tests/machine/test_prompt_derive.py` vérifie
  que chaque ligne du dérivé apparaît dans la source **dans le même ordre** — une
  sous-séquence, pas une inclusion : l'ordre est ce qui interdit de réarranger. Un lecteur
  tape `diff prompts/systeme.v2.md prompts/systeme.machine.v1.md` et obtient la réponse
  exhaustive à « qu'est-ce que l'orchestration a repris au modèle ? ».
- **`systeme.v2.md` n'a pas bougé, et ne devait pas.** Les 36 cassettes de la campagne v2
  portent son `prompt_empreinte` : un seul caractère les périme toutes. Deux de ses lignes
  sont périmées — le titre dit `rAiyon v1`, la troisième ligne dit « Onze sections » alors
  qu'il en a quatorze — et **elles le restent**. Une coquille vaut zéro, 191 appels valent
  ce qu'ils ont coûté.
- ⚠️ **L'accident** : la soustraction retirant exactement trois sections, le dérivé en
  compte **onze**. La ligne périmée redevient donc **exacte pour la machine** tout en
  restant fausse pour l'agent. C'est un accident, il est écrit comme tel, et le test le
  constate source comprise.
- **Les références pendantes ne se déclenchent pas.** `systeme.v2.md` ne porte que deux
  renvois internes — §12 vers §2, §13 vers §12 — et les deux visent des sections
  conservées. Propriété du texte, pas chance ; un test la constate.
- **Conséquence non recherchée** : `ask_clarification` et `suggest_next_question` n'étaient
  nommés que dans §5 et §6. Ils disparaissent, et la machine n'expose ni l'un ni l'autre.

**Le point ouvert du jalon 1, tranché : un seul texte, aux deux appels.** *Alternative
écartée — deux fichiers par appel* : elle rouvre l'axe d'identité des cassettes, `EnTete`
ne portant **qu'un** `prompt_version` et **qu'un** `prompt_empreinte`. Coût assumé, écrit
plutôt que tu : l'extraction lit §11, §13 et §14 qui ne la concernent pas, la rédaction lit
§9 dont elle ne peut rien faire — de la redondance inerte, pas une contradiction.

⚠️ **Prédiction posée avant la campagne** : les deux appels de la machine n'envoient pas les
mêmes outils, donc **deux préfixes de cache distincts** là où l'agent n'en a qu'un.
`cache_ecrit` sera nettement supérieur, et `jetons_entree` ne baissera pas
proportionnellement au nombre d'appels. **La mesure nº7 doit publier les jetons autant que
les appels** : une orchestration deux fois moins bavarde peut être plus chère en entrée.

**La double application est dite**, dans `docs/prompts/etape-15.md` et pas dans le prompt —
une note dans le fichier serait une ligne ajoutée, et le test de sous-séquence la refuserait
à juste titre. Trois règles sont portées deux fois ; la plus intéressante est la seconde
moitié de §13, un impératif (« sondez… ») que la rédaction ne peut pas exécuter mais dont
l'effet est déjà obtenu par `GARDE_DE_CONTEXTE`.

**Porte de sortie franchie :** `make check` vert à **1002** (+21), `make eval` rejoué sans
qu'aucun rapport ne bouge, `prompts/systeme.v2.md` absent de `git status`, et le `diff` des
deux prompts ne contient que des suppressions. **Zéro appel API.**

#### Jalon 4 — le tir d'essai ✅

Six cassettes, **25 appels**, sur `hors_catalogue` (le bord : catégorie absente du
catalogue) et `budget_serre` (la mécanique chère : `ProduitsTrouves`, une recommandation,
le chemin du validateur). C'est la reprise du motif de `make fumee` — mesurer ce que l'API
accepte **avant** que 170 appels en dépendent.

**Ce que le tir d'essai prouve :**

- l'en-tête porte `orchestration: machine` — le champ du jalon 0, renseigné pour la
  première fois —, `prompt_version: systeme.machine.v1`, l'empreinte `595d66d5383e` du
  jalon 3, et son `usage` complet. C'est le contrôle que la garde du jalon 0 **ne peut pas
  faire** : un répertoire vide ne contient rien à comparer ;
- le rejeu est **déterministe à réponses du modèle fixées** : aucune `DivergenceDeRequete`,
  aucune conversation raccourcie, sur les six prises ;
- **aucune attente binaire n'est manquée**, et aucune n'est absente : la machine émet les
  événements que `metriques.py` lit, ce qui était le signal d'arrêt du point E du jalon 2 ;
- la borne `max_iterations` n'a jamais mordu — zéro repli, tous motifs confondus ;
- `docs/eval/rapport.machine.v1.md` **n'est pas écrit**, et c'est correct : la garde de
  l'étape 13 refuse un rapport tiré d'un jeu incomplet. Le texte est produit et s'affiche.

**Un défaut réel, trouvé et corrigé** : les exemples de commande du `Makefile` portaient un
`\` de continuation dans des lignes `@#`. Make joint les deux lignes, le shell ferme le
commentaire au premier saut de ligne réel, et le `@#` de la seconde devient une commande
introuvable — `make eval-enregistrer` était **cassé depuis le jalon 0**, et personne ne
l'avait lancé depuis. C'est la seule ligne de code de ce jalon.

**Une note du jalon 3 était fausse, corrigée contre une cassette réelle** : `outils_empreinte`
enregistre **les cinq outils** (`ae1370a553ae`), pas le seul que la machine envoie. Le
harnais la calcule depuis `schema_des_outils()`, et c'est ce qu'il recalcule au rejeu ;
enregistrer autre chose ferait échouer le rejeu. Le comportement est plus strict que
nécessaire — faux positif de péremption, jamais faux négatif — et le rendre exact demande de
toucher `scripts/eval.py` et le `Protocol`. À faire avec la dette des helpers privés.

⚠️ **Une observation de conduite, à ne pas confondre avec un défaut de mécanique.** Sur
`budget_serre.3`, l'appel d'extraction n'a pas enregistré les critères du client ; la
machine a donc cherché avec un état incomplet et rendu trois écrans de 21 pouces à 100 Hz.
Le validateur a refusé le texte, la régénération l'a rattrapé, **aucun critère bloquant n'est
violé** — mais le mode d'échec est propre à cette orchestration : `enregistrer_criteres`
n'étant pas une action de `decider()`, **une extraction manquée ne se rattrape pas dans le
tour**. L'agent, lui, pouvait rappeler l'outil après avoir vu de mauvais résultats. C'est
exactement ce que la campagne doit mesurer, et ce n'est pas une raison de corriger quoi que
ce soit maintenant.

#### Jalon 5 — la campagne, et le verdict ✅

**176 appels**, 36 prises, 81 tours client, `systeme.machine.v1`. Les sept prédictions
étaient committées **avant** la commande d'enregistrement — commit séparé, horodaté.

##### 1. Les six critères d'acceptation, avec leur verdict de dispersion

| Critère | agent `v2` | machine `machine.v1` | Verdict |
|---|---|---|---|
| nº1 — griefs livrés | 0 | 0 | tenu des deux côtés |
| nº2 — violations budget | 0 | 0 | tenu des deux côtés |
| nº3 — tours avant valeur (médiane) | 1,0 | 1,0 | **dans le bruit** (+0,83 pour ± 8,00) |
| nº4 — attendu en top 3 | 12/12 | **11/12** | 92 % contre 100 %, au-dessus du seuil de 80 % |
| nº6 — zéro résultat traité | 12/12 | 14/14 | tenu des deux côtés |
| Taux de rejet du validateur | 2,00/passe | **17,00/passe** | ⛔ **au-delà du bruit** (+15,00 pour ± 12,00) |

**Un seul écart dépasse la dispersion, et la machine le perd.** Les cinq autres mesures —
tours repliés, chiffres de domaine, markdown, itérations, délai avant valeur — sont **dans
le bruit**. C'était la prédiction nº7, et elle est tenue.

⚠️ **Trois attentes de scénario ne sont pas tenues**, ce que les six critères ne montrent
pas : `budget_efface` sur `categorie_efface_budget.2`, et `zero_resultat` +
`critere_trop_strict` sur `sur_specifie.3`. `make eval` sort donc en **code non nul** sur le
jeu de la machine. C'est un **résultat**, pas un défaut : `IssueDuTour` est bien formé, le
rejeu ne diverge nulle part, et les deux traces vers le même mécanisme — voir §5 ci-dessous.

##### 2. La mesure nº7 — appels **et** jetons, jamais l'un sans l'autre

| | agent `v2` | machine `machine.v1` | |
|---|---|---|---|
| appels par tour | 2,36 | **2,17** | ×0,92 |
| jetons d'entrée non cachés | 358 088 | **657 010** | ×1,83 |
| cache écrit | 9 744 | 6 337 | ×0,65 |
| cache lu | 1 851 360 | 1 108 975 | ×0,60 |
| **entrée facturée** | 367 832 | **663 347** | **×1,80** |

⚠️ **Publier les appels seuls dirait « moins chère » d'une orchestration qui coûte 1,8 fois
plus en entrée facturée.** C'est la prédiction nº1, et elle est tenue sur ses deux moitiés :
2,17 tombe dans l'intervalle [2,00 ; 2,20] annoncé, et le surcoût d'entrée dans
l'intervalle [1,3 ; 2,0]. Le cache écrit **baisse** — préfixe plus petit, un outil au lieu
de cinq —, exactement comme la correction du jalon 4 le prévoyait après avoir invalidé le
mécanisme du jalon 3.

##### 3. La mesure nº8 — 17 contre 0

**17 tests de conduite du dialogue** tournent dans `make check` chez la machine, **0** chez
l'agent. Le zéro est écrit au §7 depuis l'étape 8, il n'a pas été remesuré pour l'occasion.

> ⚠️ Ces tests vérifient que la machine conduit le dialogue **comme on l'a écrit**. Ils ne
> vérifient **pas que la conduite est bonne**, ni que le modèle qui rédige derrière respecte
> quoi que ce soit. La machine rend testable **sa propre décision**, pas la conversation.

##### 4. D'où vient la suite qui les départage

**Les onze scénarios ont été écrits pour l'agent, à l'étape 12, avant que la variante
machine à états soit envisagée.** Ils ne sont donc truqués dans aucun des deux sens — et
cela vaut d'être dit ici, où la machine perd le seul écart significatif.

---

#### Les deux résultats structurels — ce que l'étape a réellement appris

Ils viennent du parcours, pas du tableau, et ils survivraient à une campagne au verdict
inverse.

##### 1. L'extraction en un coup, **sans recours**

`enregistrer_criteres` n'est pas une action de `decider()` : **une extraction manquée ne se
rattrape pas dans le tour.** L'agent, lui, rappelle l'outil après avoir vu de mauvais
résultats.

Le mécanisme est **observé**, avec son cas exact. Sur `sur_specifie.3`, l'extraction pose
`panel_type` en `bloquant` ; la couche outils refuse (§3.4quater — un champ de rôle `score`
ne peut pas être bloquant), et **l'appel étant atomique, tout est perdu** : la taille, la
fréquence *et* le budget. L'agent reçoit le refus dans son `tool_result` et rappelle l'outil
en `important` — c'est visible dans sa cassette. La machine ne peut pas. Sur
`categorie_efface_budget.2`, l'extraction n'émet **aucun** `tool_use` au second tour : la
bascule vers `cpu` n'est jamais enregistrée, le budget n'est jamais effacé, et la rédaction
dit pourtant au client qu'il ne s'applique plus — la prose est juste, l'état ne l'est pas.

C'est le mécanisme derrière la phrase de §3.6 — « l'agent encaisse naturellement les
virages » —, **désormais observé plutôt qu'affirmé**, et il est plus profond que le tour de
parole.

*Ne pas le corriger dans cette étape.* Laisser `decider()` redéclencher une extraction
ajouterait un appel modèle, casserait le plancher de 2,00 et changerait le coût au milieu de
la comparaison. C'est un candidat pour une `systeme.machine.v2`.

##### 2. « Ne pas chercher tant que le budget manque » n'est écrite dans aucun prompt

L'agent la tient par **l'affordance** de `question_suivante`, qui remonte `BesoinDeBudget`
en tête. `Attente.AUCUNE_RECHERCHE_SANS_BUDGET` la mesure depuis l'étape 12 sans que
personne ait remarqué qu'**aucune instruction ne la portait**. `decider()` l'écrit pour la
première fois.

Une garantie tenue par chance de conception d'un côté, par construction de l'autre — et
c'est la seule façon de s'en apercevoir : écrire la seconde orchestration.

---

#### Ce que la campagne a cassé, et qu'il a fallu réparer

`make eval-comparer` rejoue **deux jeux dans le même processus** : les cassettes de la
machine partaient dans la boucle d'agent et divergeaient au premier tour. `systeme` voyage
déjà **par valeur** dans `Reglages` pour exactement cette raison ; l'orchestration ne le
faisait pas.

Elle le fait désormais, et **elle se lit dans l'en-tête de chaque cassette** — le champ que
le jalon 0 avait écrit sans le consommer. Conséquence : `RAIYON_ORCHESTRATION` est **sans
effet au rejeu**, et c'est voulu. Rejouer une prise sous une autre orchestration que celle
qui l'a enregistrée n'est pas un choix, c'est une erreur ; la variable ne sert qu'à
l'enregistrement. Aucun réenregistrement n'a été nécessaire : les cassettes étaient justes.

#### Jalon 6 — la clôture ✅

Documentation seule, zéro appel : l'encadré daté de §3.6, quatre lignes neuves au §7 et une
qui passe **à moitié fermée**, le README à deux colonnes.

---

### Ce que l'étape a livré

Une **seconde orchestration**, de signature identique à la première, branchée sur les vrais
outils, émettant les mêmes événements, persistée par le même `session.tour()`. Les deux
restent lançables et mesurables : `RAIYON_ORCHESTRATION` choisit qui conduit le tour.

| | agent `v2` | machine `machine.v1` |
|---|---|---|
| Critères nº1, nº2, nº6 | tenus | tenus |
| Critère nº3 (médiane) | 1,0 tour | 1,0 tour |
| Critère nº4 | 12/12 — 100 % | 11/12 — 92 % |
| Taux de rejet | 6 griefs / 81 tours — 0,07/tour | **51 griefs / 81 tours — 0,63/tour** |
| Taux de repli | 0 / 81 — 0 % | 8 / 81 — 10 % |
| Mesure nº7 — appels | 191 — **2,36/tour** | 176 — **2,17/tour** |
| Mesure nº7 — entrée facturée | 367 832 jetons | **663 347 jetons** |
| Mesure nº8 — conduite testée | **0** | **17** |

*Critères, taux, appels **et jetons** : `docs/eval/rapport.v2.md` et
`docs/eval/rapport.machine.v1.md`. ⚠️ **La dernière phrase de cette note était « les jetons
ne sont publiés par aucun rapport »**, et c'est l'étape 16 qui l'a rendue fausse : la mesure
nº7 les publie, et plus une ligne de ce tableau n'est sommée à la main.*

> ### 🔴 Le verdict de cette étape est **suspendu sur sa mesure principale** — 3 septembre 2026
>
> **Les chiffres du tableau ci-dessus sont ceux de la campagne, et ils ne sont pas
> réécrits.** Ce qui suit dit ce qui est su depuis, et ce qui ne l'est plus.
>
> Le seul écart au-delà de la dispersion était le **taux de rejet du validateur** — 51
> contre 6, dominé par `ecart_non_dit`, qui tirait **24 fois** chez la machine et **0** chez
> l'agent. C'est sur lui que reposait « la machine perd sur ce point, et sur celui-là seul ».
>
> **L'étape 18 a trouvé, en conversation réelle, que deux règles du validateur pouvaient
> être conjointement insatisfaisables** — voir §7. Le modèle qui nommait un produit hors
> budget sur une ligne et écrivait son écart sur la suivante était refusé quoi qu'il écrive.
> **C'est exactement la forme des 24** : `ecart_non_dit` sur la ligne du produit,
> `montant_non_fourni` sur l'écart écrit une ligne plus bas. Et la section 14 du prompt, qui
> demande un produit par ligne, y menait.
>
> **Ce qui est su, et il est mince** : `comparaison.1` est la seule prise concernée qui reste
> rejouable après le correctif. Elle portait **2 des 24**, et elle en porte désormais **0**,
> sans repli. Ces deux-là étaient des faux positifs de validateur, pas un fait
> d'orchestration.
>
> **Ce qui n'est pas su, et qui est l'essentiel** : les 22 autres vivaient dans six prises —
> `changement_davis` 1-3 et `desserrage_refuse` 1-3 — dont la liste de griefs change, donc
> la reprise, donc l'empreinte de requête. Elles **divergent** au rejeu et sortent de toute
> mesure. Le rapport régénéré affiche 10 griefs sur 69 tours et `ecart_non_dit` muet : **cela
> ne dit pas que les 22 étaient des faux positifs**, cela dit que les prises qui les
> portaient ne sont plus comptables. La mesure s'est annulée elle-même, et c'était prévu
> avant de la lancer.
>
> **Conséquence sur la comparaison** : `docs/eval/comparaison.v2-machine.v1.md` se réduit
> désormais aux **9 scénarios communs**, et le taux de rejet y est passé « **dans le
> bruit** ». ⚠️ Ce n'est pas un démenti du verdict : c'est la disparition de ce qui
> permettait de le trancher. Le fichier le dit lui-même, en tête, et il l'écrit tout seul —
> la réduction aux scénarios communs et l'avertissement qui l'accompagne sont produits par le
> harnais, pas rédigés ici.
>
> **Ce qui reste vrai sans être touché** : la mesure nº7 (coût), la mesure nº8 (17 tests de
> conduite hors ligne contre 0), les critères nº1, nº2 et nº6, l'extraction atomique sans
> recours, et l'invariant du budget que personne n'avait écrit. Aucun de ces résultats ne
> passe par `ecart_non_dit`.
>
> **Ce qu'il faudrait pour trancher** : réenregistrer le jeu de la machine sous le validateur
> corrigé — **~176 appels**. C'est un arbitrage de budget, il n'est pas pris, et il est écrit
> comme tel plutôt que tranché en douce dans un sens ou dans l'autre. Ce que ce dépôt ne fera
> pas : réécrire le verdict de l'étape 15 dans la direction qui l'arrange, avec des chiffres
> mesurés sur le sous-ensemble d'où le phénomène a été retiré.
>
> ---
>
> **Le verdict tient toujours au 5 septembre 2026, et il a failli coûter plus cher.** La
> garde d'extraction de l'étape 21 aurait fait sortir dix prises de plus du rejeu, dont
> `comparaison.1` — la seule qui tranche encore pour 2 des 24. Le verdict serait alors passé
> de « suspendu » à « plus reproductible du tout ». **C'est l'une des deux raisons de son
> retrait à l'étape 22** : un correctif qui détruit l'instrument de mesure d'une question
> ouverte se paie deux fois.

### Les six arbitrages, avec leur alternative écartée

1. **La machine partage tout sauf la conduite** — validateur, couche outils, moteur,
   catalogue, types d'événements, `IssueDuTour`, forme des blocs persistés.
   *Alternative écartée — une seconde pile propre.* Elle mesurerait deux produits, pas deux
   orchestrations, et la comparaison ne porterait plus sur les mêmes métriques.
2. **Le prompt dérivé par soustraction pure**, numérotation conservée avec ses trous.
   *Alternative écartée — une réécriture par appel.* Le `diff` cesse d'être la
   spécification de ce que le code a repris au modèle, et un test ne peut plus le garantir.
3. **L'axe d'identité des cassettes reste la version de prompt.** `systeme.machine.v1`
   dérive son jeu, ses cassettes et son rapport sans qu'une ligne de `scripts/eval.py`
   change. *Alternative écartée — un axe « orchestration ».* Il demanderait un second champ
   d'en-tête ou une empreinte composite, donc de retoucher `cassette.py`.
4. **Aucun scénario ajouté.** Les onze viennent de l'étape 12, écrits pour l'agent avant que
   la machine soit envisagée. *Alternative écartée — des scénarios taillés pour les bords de
   `decider()`.* Ils auraient été écrits depuis l'implémentation : une suite qui vérifie ce
   que le code fait, pas ce que le produit doit faire.
5. **Un tir d'essai avant la campagne**, 25 appels sur deux scénarios. *Alternative écartée
   — lancer directement.* Un défaut de mécanique découvert au rejeu coûtait 176 appels ; le
   tir en a coûté 25, **non récupérables et dépensés exprès**. Il a corrigé deux prédictions
   avant qu'elles ne soient mesurées.
6. **L'historique va à la rédaction**, comme chez l'agent. *Alternative écartée — un rendu
   sans mémoire.* Plus simple, et il **truque la comparaison** : `comparaison` deviendrait
   impossible par construction, donc la prédiction nº6 invérifiable, donc la campagne
   démonstrative au lieu d'expérimentale.

### Ce que l'étape a appris, et qui n'était pas prévu

**1. `ecart_non_dit` n'était pas une règle dormante — elle n'avait jamais été sollicitée.**
Le README déclarait trois codes sur six jamais déclenchés. La machine en fait tirer un
**24 fois**. « Une règle qui ne tire jamais est indistinguable d'une règle absente » est
écrit dans ce dépôt depuis l'étape 12 ; il aura fallu une **seconde orchestration** pour
distinguer. ⚠️ Ce que cela dit des deux autres est **ouvert** : `id_inconnu` et
`nom_reecrit` ne tirent sur aucune des deux. Non sollicités, pas démontrés morts.

**2. Les 24 rejets prouvent que le validateur porte, pas qu'il a échoué.** Les critères nº1
et nº2 tiennent des deux côtés, **et ils tiennent parce que le texte fautif a été refusé
avant d'être livré**. Le filet est décoratif chez l'agent, porteur chez la machine — §3.11
vérifié dans une direction que personne n'avait prévue : la garantie a tenu sous une
orchestration pour laquelle elle n'avait pas été conçue.

**3. Une prédiction dont les deux moitiés vont en sens contraire.** 2,17 appel/tour contre
2,36, **et** 1,80 fois plus d'entrée facturée. Publier les appels seuls aurait dit « moins
chère » d'une orchestration qui coûte presque le double. La mesure nº7 publie les deux, et
la raison est celle-là.

**4. Trois attentes de scénario non tenues, et `make eval` sort en code non nul** sur le jeu
de la machine — ce que le tableau des six critères ne montre pas. C'est un **résultat** :
`IssueDuTour` bien formé, rejeu sans divergence, selon la règle d'arrêt posée **avant** la
campagne.

**5. Et les deux résultats structurels ci-dessus** — l'extraction atomique sans recours, et
l'invariant du budget que personne n'avait écrit. Ils survivraient à un verdict inverse.

#### Reste après l'étape

- la **dette des six helpers privés** de `boucle.py` (§7) — première candidate, elle ne
  coûte aucun appel ;
- le correctif de `NOMBRE` et la **dette nº1** de l'étape 8, dans leur version à un seul
  changement : **désormais possible**, v2 n'étant plus une ligne de base en cours d'usage ;
- une `systeme.machine.v2`, si l'extraction atomique vaut qu'on y revienne ;
- la recherche hybride `pgvector` (§3.5), qui reste hors périmètre du produit livrable.

#### Hors de cette étape

- Recherche hybride avec `pgvector`, en respectant la règle « départager, jamais
  justifier ».

---

### Étape 16 — Consolidation ✅

Deux jalons **sans un seul appel API**, qui referment ce que le dépôt s'était engagé à
traiter et que l'étape 15 laissait ouvert. Rien de neuf n'est ajouté : une dette se solde,
une mesure publie ce qu'elle savait déjà.

#### Jalon 1 — le contrat partagé sort de l'agent ✅

**Le couplage réel était de douze noms, pas de six, et le plus structurant était public.**
`src/raiyon/orchestration.py` — le module **neutre**, celui qui porte le `Protocol`
`Orchestrateur` — faisait `from raiyon.agent.boucle import IssueDuTour` : le contrat commun
aux deux orchestrations était défini à l'intérieur de l'une d'elles, et `machine/` en
dépendait pour son **type de retour** et ses constantes de rôle. Ne déplacer que les six
helpers privés aurait laissé le même couplage sous un nom public.

`orchestration.py` devient donc un paquet de trois modules :

| Module | Contenu |
|---|---|
| `__init__.py` | le `Protocol`, la table, `repondre_en_vigueur()` |
| `contrat.py` | `IssueDuTour`, `TourProduit`, les deux rôles, les deux phrases de repli |
| `blocs.py` | les six helpers, **rendus publics** — ils ont deux appelants depuis l'étape 15 |

⚠️ **Le piège de circularité était réel, et la règle qui devait l'éviter ne suffisait pas.**
« Les sous-modules n'importent jamais le `__init__` » ne dit rien du mécanisme : en Python,
importer `raiyon.orchestration.contrat` **exécute d'abord** `orchestration/__init__.py`. Un
`import raiyon.agent.boucle` partait donc en `boucle (partiel) → orchestration.contrat →
orchestration/__init__ → boucle.repondre`, et levait `ImportError: partially initialized
module`. Reproduit en quinze lignes avant d'écrire une seule ligne du jalon.

**La table `ORCHESTRATIONS` devient la fonction `orchestrations()`**, qui résout les deux
implémentations à l'appel. C'est ce qui ferme le cycle, et rien n'est perdu : mypy vérifie
le littéral contre `dict[str, Orchestrateur]` exactement comme il vérifiait l'annotation du
dictionnaire de module, donc la substituabilité reste contrôlée à la compilation — c'est
toute la raison d'être de ce module. *Alternative écartée — sortir `contrat` et `blocs` du
paquet, dans un `raiyon/partage/`* : le graphe redevient acyclique sans rien rendre
paresseux et la façade ne bouge pas d'une ligne, mais on chercherait `IssueDuTour` sous
`orchestration`, où le `Protocol` la nomme, et elle serait ailleurs.

**Ce que le jalon n'est pas : un refactor de comportement.** Aucune logique ne bouge, aucun
invariant ne se déplace, aucun message de log ne se reformule. La preuve est **dans ce qui
ne bouge pas** — `make check` rend exactement 1002, `make test-int` 98, et les **cinq**
documents de `docs/eval/` se régénèrent à l'identique, ce qui couvre les deux orchestrations
à la fois.

#### Jalon 2 — la mesure nº7 publie les jetons ✅

**Un défaut de spécification, pas d'implémentation, et il est de moi.** La mesure nº7 a été
spécifiée au jalon 0 de l'étape 15 sur `entete.usage.appels` — **avant** qu'on sache que le
compte d'appels dirait l'inverse du coût réel. La campagne l'a montré : 2,17 appel/tour
contre 2,36, **et** 1,80 fois plus d'entrée facturée. Le rapport ne publiait que les appels ;
un lecteur y lisait « moins d'appels » et en concluait « moins chère ». La conclusion inverse
est la vraie, et elle ne vivait que dans le README et dans le tableau ci-dessus, **sommée à
la main**. Le correctif est écrit là où la mesure est définie — §4 et `raiyon/eval/cout.py`.

`Cout` porte désormais l'`Usage` cumulé et non plus le seul compte d'appels — `Usage` savait
déjà s'additionner, `mesurer_le_jeu()` lisait déjà chaque en-tête : il n'y avait aucune
plomberie à inventer, seulement une décision de publier. Trois lignes au lieu d'une, dans le
rapport comme dans la comparaison :

| Ligne | `v2` | `machine.v1` |
|---|---|---|
| Appels par tour client | 2,36 | **2,17** |
| Jetons d'entrée facturés | 367 832 | **663 347** — facteur 1,80 |
| Jetons de sortie | 46 285 | 65 958 — facteur 1,43 |

⚠️ **Le cache lu est publié à côté, jamais additionné** — 1 851 360 contre 1 108 975. Il est
facturé à un autre tarif ; la somme des deux serait un total que personne ne doit à personne.

⚠️ **La règle du tout ou rien ne s'est pas assouplie d'un cran pour faire apparaître un
chiffre** : `v1-etape12` (0/19) et `v1-base` (3/31) affichent « non disponible » sur les
trois lignes. Et l'écart des jetons est publié **sans verdict de dispersion**, comme celui
des appels — un coût figé à l'enregistrement n'a pas de bruit à dépasser.

**La neutralité est vérifiée par le même contrôle qu'au jalon 0 de l'étape 15** : les cinq
documents de `docs/eval/` ne changent que par les lignes de jetons. Le `git diff` ne porte
**aucune suppression de chiffre** — une seule phrase disparaît, celle de la provenance, qui
disait « la seule ligne » et en dit maintenant trois.

#### Ce que l'étape a appris

**Une règle censée éviter un cycle d'imports ne suffit pas si elle ne décrit pas le
mécanisme.** « Les sous-modules n'importent jamais le `__init__` » est vraie et inopérante :
c'est l'interpréteur qui exécute le `__init__` du paquet parent, sans qu'aucun sous-module
l'ait demandé. Le piège a été reproduit en quinze lignes dans un répertoire jetable **avant**
d'écrire une ligne du jalon — trois minutes qui ont changé la forme de la solution.

**Et une mesure peut être fausse sans qu'aucune ligne de code le soit.** Les jetons étaient
dans les en-têtes depuis le premier jour de la campagne, `Usage.__add__` existait, la boucle
qui lit les cassettes les avait sous la main. Ce qui manquait était une décision de publier,
prise à un moment où l'on ne savait pas encore ce que la campagne montrerait. C'est le même
motif que la fuite d'évaluation : ce n'est pas le calcul qui trompe, c'est ce qu'on a choisi
de regarder.

#### Reste après l'étape

- le correctif de `NOMBRE` et la **dette nº1** de l'étape 8, dans leur version à un seul
  changement : **possibles**, et elles coûtent deux campagnes séparées (~380 appels) pour
  tenir la promesse d'attribution, ou une seule (~190) en y renonçant explicitement. C'est un
  arbitrage de budget, il se prend avant et pas pendant ;
  ⚠️ **Ce paragraphe a été écrit avant l'étape 17 et il est faux sur les deux points.** Le
  correctif de `NOMBRE` a coûté **zéro appel** — voir l'étape 17 —, et la dette nº1 a été
  **décidée non fermée**, avec son chiffre, plutôt que reportée une troisième fois. Ces
  deux lignes restent ici parce qu'elles disent ce qu'on croyait à la fin de l'étape 16 ;
  elles n'engagent plus rien. Voir §7 ;
- une `systeme.machine.v2`, si l'extraction atomique vaut qu'on y revienne ;
- la recherche hybride `pgvector` (§3.5), qui reste hors périmètre du produit livrable ;
- ⚠️ **`make eval-comparer` ne survit pas à une apostrophe dans `Q`** — la recette passe
  `--question '$(Q)'`, et `Q="l'effet…"` ferme la chaîne : `/bin/sh: Unterminated quoted
  string`. Les deux comparaisons de cette étape ont donc été relancées par
  `uv run python scripts/eval.py comparer`, à code identique. Défaut de la cible `make`,
  frère de celui du `\` de continuation trouvé à l'étape 15 ; non corrigé ici, parce qu'une
  étape dont la preuve est « rien d'autre n'a bougé » ne corrige rien d'autre.

---

### Étape 17 — Le correctif de `NOMBRE`, et une dette reclassée ✅

**Zéro appel API, zéro cassette réenregistrée.** L'étape tenait sur un pari écrit avant
d'être vérifié, et le pari a tenu.

#### Le motif du parcours : une promesse écrite avant l'outil qui la dispense

`NOMBRE` avait été différé à l'étape 13 avec ce motif : *« c'est un changement de
validateur, il modifie des listes de griefs, donc des reprises, donc des empreintes de
requête — il périmerait des cassettes. À livrer avec la prochaine campagne, jamais entre
deux. »*

**Ce motif a été écrit avant que le mécanisme qui le dispense existe.**
`DIVERGENCES_ATTENDUES` a été construit au jalon 1 de la **même** étape 13, pour exactement
ce cas, et il servait déjà à ça : le correctif de `valeurs_refusees` avait fait diverger
`v1-etape12/desserrage_refuse.1`, et la liste **assertée** l'absorbait depuis. Le reste est
gratuit par construction — l'arbitrage A de l'étape 12 fait relire la prose par le
validateur **courant** à chaque rejeu, donc un correctif de validateur se mesure sans
qu'une seule cassette soit réenregistrée. C'est la propriété que le README vend, et
personne ne l'avait rapprochée du report.

⚠️ **C'est le même motif que la trouvaille de l'étape 15 sur l'agnosticisme du harnais**,
et c'est la deuxième occurrence, donc un motif et plus une anecdote :

| Étape | Ce qui existait | Ce qu'on continuait de croire |
|---|---|---|
| 15 | Le harnais est agnostique à l'orchestration depuis l'étape 12 | « Une seconde orchestration demanderait un second harnais » |
| 17 | `DIVERGENCES_ATTENDUES` absorbe une divergence de validateur depuis l'étape 13 | « Un correctif de validateur doit attendre la prochaine campagne » |

La forme commune : **un coût est réévalué une fois, puis reconduit sans être relu**, pendant
que le dépôt fabrique à côté l'outil qui l'annule. Ce n'est pas un défaut de conception,
c'est un défaut de **relecture des reports** — et il se corrige en datant les décisions, ce
que fait la ligne dette nº1 de §7.

#### Le correctif, et la moitié qui manquait à sa rédaction

Le motif livré est `(?<!\d)(?:\d{1,3}(?:[ESPACES]\d{3})+|\d+)(?:[.,]\d+)?`. §7 en portait
l'alternance depuis l'étape 13, **validée sur les six formes nues** ; elle n'a pas suffi, et
la raison est instructive.

`MOTIF_NOMBRE` se lit par `finditer` depuis le début du texte : il ne redémarre jamais au
milieu d'un chiffre, et l'alternance y sépare correctement `1080` de `180`. **Les quatre
motifs composés — montant, unité, les deux intervalles — exigent une unité ou un symbole
derrière.** Quand la lecture échoue à la position du `1` de `1080`, le moteur réessaie plus
loin et retombe **à l'intérieur** du nombre, où `\d{1,3}` accepte volontiers `080` : le
validateur réclamait alors `80 180 Hz` au catalogue au lieu de `1 080 180 Hz`. **Un faux
positif déplacé, pas supprimé** — et le prix aurait été une cassette périmée pour rien.

Mesuré **avant** de commiter, en rejouant les quatre motifs, ancien contre nouveau, sur la
prose de chaque prise des quatre jeux. `(?<!\d)` interdit à un nombre de commencer au milieu
d'une suite de chiffres, et c'est ce qui rend l'alternance vraie partout où elle est
composée. ⚠️ **La leçon n'est pas « il manquait une garde »** : c'est qu'une rédaction de
motif validée sur le motif **nu** ne dit rien de ses **compositions**, et que §7 avait écrit
« vérifié sur les six formes » en croyant avoir tout vérifié. Sept tests le tiennent
désormais — six sur les formes nues, **un sur `MOTIF_UNITE`**, qui est celui qui aurait
attrapé le défaut.

#### Ce que la mesure a donné

| Jeu | Griefs avant | Griefs après | Cassettes divergentes |
|---|---|---|---|
| `v2` | 6 sur 81 tours (0,07/tour) | **4 sur 79 tours (0,05/tour)** | **1** — `categorie_efface_budget.3` |
| `machine.v1` | 17 par passe | **17 par passe — aucun chiffre ne bouge** | **0** |
| `v1-etape12` | inchangé | **inchangé** | 0 nouvelle (la divergence de l'étape 13 demeure) |

`valeur_non_fournie` passe de 3 à 1 sur v2. ⚠️ **Les deux griefs tombés ne se lisent pas
dans le rapport, et il faut le dire** : la prise qui les portait est **écartée** du compte
(divergence attendue), donc le rapport perd 2 tours en même temps que 2 griefs. Ce que le
correctif a réellement supprimé se lit dans l'appendice A du commit précédent, pas dans la
soustraction des totaux.

**La règle d'arrêt** — « si plus de deux cassettes de `machine.v1` divergent, on ne commite
rien » — était écrite d'avance pour ne pas être négociée devant le résultat. Elle n'a pas eu
à servir : le point de vigilance (les 17 rejets par passe de la machine, dominés par
`ecart_non_dit`) était bien un risque faible, et il valait mieux le mesurer que le supposer.

#### Ce que l'étape ferme, et ce qu'elle décide

- **`NOMBRE`** : fermé, §7. Livré **sans réenregistrer une cassette** — c'est le pari, et
  c'est la propriété du harnais qui le rend possible.
- **La dette nº1 de l'étape 8** : **décidée non fermée**, §7, avec son chiffre — ~366 appels
  (~190 v2 + ~176 `machine.v1`), soit plus que l'étape 15 entière, pour un effet que la
  dette elle-même déclare imprévisible. Le report l'avait rendue deux fois plus chère : un
  jeu à l'étape 13, deux aujourd'hui, sans que le défaut se soit aggravé. **Retirée du
  README**, parce qu'un engagement qu'on a décidé de ne pas tenir et qu'on continue
  d'afficher est pire que pas d'engagement du tout.
- **Le quoting de `make eval-comparer`** : `--question "$(Q)"`. Deuxième défaut de quoting du
  `Makefile` en deux étapes, après le `\` de continuation des lignes `@#`. La limite se
  **déplace** vers le guillemet double, elle ne disparaît pas, et la recette le dit en
  commentaire plutôt que de laisser croire que c'est réglé.

#### Reste après l'étape

- `orchestration/blocs.py` importe encore `agent.evenements` et `agent.prompts` — reste de
  nommage, pas de couplage (ligne §7 fermée à l'étape 16) ;
- une `systeme.machine.v2`, si l'extraction atomique vaut qu'on y revienne ;
- la recherche hybride `pgvector` (§3.5), hors périmètre du produit livrable.

**Et la dette nº1 n'est plus dans cette liste.** C'est la différence entre une décision et
un renvoi.

---

### Étape 18 — Deux règles qui ne pouvaient pas être satisfaites ensemble ✅

**Zéro appel API, zéro cassette réenregistrée.** Un correctif de gravité **élevée** — le
produit ne savait pas répondre à une demande courante — et une mesure qui s'annule
elle-même, écrite comme telle plutôt que présentée comme un résultat.

#### Le défaut, et il n'a pas été trouvé par une commande

Un client demande une comparaison entre deux cartes graphiques **au-dessus de son budget**.
Le texte est refusé deux fois, le tour se replie. Les deux griefs se contredisent :

| Règle | Ce qu'elle dit |
|---|---|
| 4 — `ecart_non_dit` | « le citer exige de dire qu'il dépasse et **de combien** — 11.59 $ exactement, tel que `ecart_usd` le donne » |
| 2 — `montant_non_fourni` sur « 11,59 $ » | « **aucun outil n'a rendu ce montant** dans cette conversation » |

L'une réclame le chiffre, l'autre affirme qu'il n'existe pas. Le mécanisme est le
découpage : les deux règles raisonnent `for phrase in phrases(texte)`, le saut de ligne est
une fin de phrase, et la **section 14 du prompt demande un produit par ligne**. Dès que le
nom et l'écart tombent dans deux phrases, aucune rédaction ne satisfait les deux règles.
Aggravation : la règle 4 exigeait l'écart dans **chaque** phrase nommant le produit — dans
une comparaison, trois ou quatre fois, donc trois ou quatre griefs et deux régénérations
sans issue.

⚠️ **C'est le second défaut du projet trouvé en conversation réelle**, après celui que
`make eval-live` a montré à l'étape 12. Deux occurrences, donc un motif : ce que trente-six
prises scriptées ne voient pas, une conversation le voit — et rien dans le dépôt n'oblige à
en tenir une. La ligne de §7 le dit à cet endroit-là plutôt qu'ici, pour qu'un relecteur du
§7 seul le lise aussi.

#### Le correctif, en deux gestes

1. **Un écart est un montant fourni.** `hors_budget.values()` entre dans les montants admis
   de la branche « la phrase ne nomme aucun produit ». *L'argument de sûreté est
   structurel* : cette branche admettait déjà `valeurs_refusees`, qui sont **écrites par le
   modèle** (§7) ; y admettre des écarts **écrits par le moteur** est strictement plus sûr
   que ce qui s'y trouvait. La branche `if nommes:` n'est **pas** touchée — le piège nº6 de
   `test_pieges.py` est le seul test qui échoue si quelqu'un aplatit le contexte, et il
   reste exactement aussi strict.
2. **L'écart se dit une fois par message, pas par phrase.** `regle_ecart_au_budget` vérifie
   la présence de l'écart sur le message entier, **par identifiant**, et attache le grief à
   la première phrase qui nomme le produit. *C'est un desserrage assumé du critère nº2* :
   « budget jamais dépassé sans **présentation explicite** » est satisfait en le disant une
   fois. Trois tests le bornent — le cas de terrain passe, un produit dont l'écart n'est
   écrit nulle part reste refusé, et l'écart de A ne couvre pas B.

#### Ce que la mesure a donné, et ce qu'elle ne peut pas donner

| Jeu | Griefs avant | Griefs après | Prises écartées |
|---|---|---|---|
| `v2` | 4 sur 79 tours | **3 sur 77** | 1 de plus — `zero_budget_trop_bas.3` |
| `v1-etape12` | 7 sur 42 tours | **6 sur 42** | 1 — `zero_budget_trop_bas.1` |
| `machine.v1` | 51 sur 81 tours | **10 sur 69** | **6** — `changement_davis` 1-3, `desserrage_refuse` 1-3 |

🔴 **Le chiffre de `machine.v1` ne veut pas dire ce qu'il a l'air de dire, et c'était prévu
avant de lancer.** Les six prises écartées portaient **22 des 24** `ecart_non_dit` de la
campagne — l'unique écart au-delà de la dispersion de l'étape 15, c'est-à-dire le résultat
sur lequel reposait tout son verdict. Leur liste de griefs change, donc la reprise, donc
l'empreinte : elles divergent et sortent de toute mesure. **Le rapport ne dit pas que ces 22
étaient des faux positifs ; il dit qu'on ne peut plus les compter.** Voir le verdict suspendu
de l'étape 15.

**Ce qui est su, et il tient en une prise** : `comparaison.1` portait les 2 autres, elle
reste rejouable, et elle en porte désormais **0**, sans repli. Ces deux-là étaient bien des
faux positifs de validateur. Pour les 22 autres, il faudrait réenregistrer le jeu de la
machine — **~176 appels**, arbitrage de budget non pris.

#### Deux effets de bord, et les deux sont des signaux

* **`v1-etape12/desserrage_refuse.1` a cessé de diverger**, et `DIVERGENCES_ATTENDUES` l'a
  **fait échouer** : `DivergenceAttendueAbsente`, « ces cassettes sont listées comme
  divergentes et se rejouent pourtant sans divergence ». C'est la **première fois que
  l'assertion tire dans ce sens-là** — celui qui distingue une liste assertée d'une simple
  tolérance, écrit à l'étape 13 et jamais exercé depuis. Le correctif fait tomber les deux
  griefs que l'étape 13 avait laissés à son dernier tour : le texte n'est plus refusé, donc
  plus régénéré, donc la prise 7 n'est plus consommée du tout. L'entrée est retirée.
* **`docs/eval/comparaison.v2-machine.v1.md` s'est réduit tout seul aux 9 scénarios
  communs**, et a écrit de lui-même que « l'exclusion n'est pas neutre ». `machine.v1` ne
  porte plus `changement_davis` ni `desserrage_refuse` : le harnais l'a détecté, a réduit la
  comparaison, et a publié l'avertissement. Le taux de rejet y est passé « **dans le
  bruit** » — ce qui n'est pas un démenti du verdict de l'étape 15, mais la disparition de ce
  qui permettait de le trancher.

#### Deux ajouts au harnais, tous deux nés de cette mesure

* **Les réserves sont groupées par raison.** Six prises écartées pour une cause unique
  produisaient six paragraphes identiques en tête du rapport, qu'on saute comme un bandeau.
* **La ligne « règles jamais déclenchées » porte une réserve quand des prises sont
  écartées.** Sans elle, `ecart_non_dit` s'affichait **muet** dans le rapport même qui
  l'avait vu tirer 24 fois. Une réserve en tête ne suffit pas quand une ligne du corps
  affirme le contraire — et c'est la troisième fois que cette phrase-là doit être corrigée
  dans ce dépôt.

#### Reste après l'étape

- **Le jalon 2, non lancé** : réenregistrer `machine.v1` sous le validateur corrigé,
  ~176 appels, pour savoir ce que valait le verdict de l'étape 15 ;
- `orchestration/blocs.py` importe encore `agent.evenements` et `agent.prompts` — reste de
  nommage, pas de couplage ;
- une `systeme.machine.v2`, si l'extraction atomique vaut qu'on y revienne ;
- la recherche hybride `pgvector` (§3.5), hors périmètre du produit livrable.

---

### Étapes 19 et 20 — les conversations à la main, et trois constats ✅

**~40 appels au total**, aucun correctif de `src/`. Deux étapes courtes qui ont produit un
outil et trois observations, et qui n'avaient pas été portées ici : elles le sont
maintenant, parce qu'un plan qui s'arrête à l'étape 18 pendant que le dépôt est à
l'étape 21 est un plan qui ment.

**L'étape 19 a écrit `scripts/essais.py`** : les dix conversations de
`docs/eval/conversations-a-essayer.md`, jouées sur l'une ou l'autre orchestration, avec un
affichage fait pour être **lu** — les événements en une ligne, `TexteRejete` et `Repli` en
évidence, la prose livrée, les produits fournis un par un. ⚠️ **Il ne mesure rien et n'écrit
rien** : pas de cassette, pas de rapport. C'est le troisième passage de la même méthode —
les deux seuls défauts du projet trouvés hors des tests l'ont été en conversation réelle, et
aucune commande automatique ne les a vus. Sans argument il joue **trois** conversations et
non dix : garde-fou budgétaire, les dix coûtent ~120 appels.

**L'étape 20 a corrigé la conversation nº1, qui ratait sa cible.** « Compare-moi les deux
premiers en détail » a été lu comme les deux premiers **dans le budget** : la conversation
testait une comparaison détaillée et non une comparaison **hors budget**, et passait donc
sur les deux orchestrations sans rien prouver du correctif de l'étape 18. Elle dit
désormais « compare-moi en détail les deux qui dépassent mon budget ». ⚠️ **Une conversation
d'essai qui passe sans atteindre son mécanisme est pire qu'absente : elle rassure.**

**Et elle a reproduit le défaut d'extraction en tirant quatre fois le même tour** — « un
écran 27 pouces, 400 $ », côté machine. Le défaut est **intermittent** : sur un des quatre
tirages, `record_criteria` pose la catégorie et le budget et **aucun critère**, la recherche
part sur **115 candidats au lieu de 37**, et trois écrans de 21 à 24 pouces sont recommandés
à quelqu'un qui avait demandé du 27. Côté agent, deux tirages, aucune perte —
l'agent lit le refus dans son `tool_result` et rappelle l'outil. Aucun correctif à cette
étape : c'était la consigne, et on ne touche pas à l'extraction tant qu'on ne sait pas si le
défaut est systématique. **C'est ce que l'étape 21 a recensé.**

---

### Étape 21 — le recensement, la garde d'extraction (retirée à l'étape 22), et la clôture ✅

**Zéro appel API.** Un recensement gratuit, un correctif testé hors ligne, et la clôture du
POC. C'est la dernière étape avant présentation.

#### Le recensement — la fréquence était déjà sur le disque

Les 36 cassettes de `machine.v1` portent **81 tours d'extraction enregistrés** avec les
arguments de chaque `record_criteria`, et les onze scénarios ont des messages client écrits.
La fréquence du défaut se compte donc sans dépenser un jeton.

> **2 tours sur 81 — 2,5 %** — perdent un critère que le client avait **explicitement**
> énoncé.

| Prise | Tour | Ce que le client énonce | Ce que `record_criteria` enregistre |
|---|---|---|---|
| `comparaison.1` | 1 | « 27 pouces au minimum, 144 Hz au moins, 250 dollars maximum, et plutôt une dalle IPS » | catégorie + budget. **`screen_size`, `refresh_rate` et `panel_type` perdus** |
| `sur_specifie.3` | 2 | « le 500 Hz est vraiment ce qui compte pour moi » | catégorie + budget. **`refresh_rate` perdu** |

**Les deux sont intermittents**, et c'est le résultat qui compte : les deux autres prises de
`comparaison` enregistrent les trois critères, les deux autres de `sur_specifie` enregistrent
les 500 Hz. Le même message, le même prompt, un tirage différent.

⚠️ **Seul l'explicite est compté, et 13 tours ont été écartés** plutôt que gonfler le taux :

| Écarté | Tours | Pourquoi |
|---|---|---|
| Catégorie énoncée, non enregistrée | 4 | `besoin_flou` t1 ×3 (« un bon écran ») et `categorie_efface_budget.2` t2. Une catégorie n'est pas un critère du registre — mais **le second est la cause de la seule attente non tenue qui reste**, et il est donc écrit ici plutôt qu'omis |
| Budget énoncé, non enregistré | 6 | `hors_catalogue` t1 ×3 — la catégorie « perceuse » n'existe pas, et `categorie` est **requise** par le schéma : ne pas appeler l'outil est le bon comportement. `zero_budget_trop_bas` t2 ×3 — le plafond est **redit**, à la même valeur qu'au tour 1 |
| Critères extraits puis **refusés** | 3 | `sur_specifie` t1 ×3 : les trois critères sont dans les arguments, mais `panel_type` y est posé en `bloquant`, la couche outils refuse **tout l'appel** (§3.4quater), et la taille, la fréquence et le budget partent avec. C'est un défaut réel — l'extraction atomique de §7 — mais **ce n'est pas celui-là** : l'extraction avait lu juste |

**« Pour du jeu » n'est pas un critère** et n'a jamais été compté : le registre ne porte
aucun champ d'usage. Un jugement large aurait donné un taux plus impressionnant et
inutilisable.

**Ce que ce chiffre décide** : la fermeté de ce qui s'écrit en §7, pas la décision de
corriger. Un critère énoncé qui disparaît est un défaut à 2/81 comme à 20/81 — ce qu'un
client observe n'est pas un taux, c'est une recommandation de 24 pouces quand il a demandé
du 27.

#### 🔴 La garde — écrite, mesurée, puis **retirée à l'étape 22**

> ⚠️ **Tout ce qui suit décrit un correctif qui n'est plus dans le dépôt.** Il a été
> construit en entier, testé et chiffré, et c'est son chiffre qui l'a fait retirer — voir
> l'étape 22 ci-dessous et la ligne de §7. Le récit est conservé parce que **c'est la mesure
> qui est l'acquis**, pas le code : refaire ce correctif sans la relire coûterait une seconde
> fois les dix cassettes.

Quand l'appel d'extraction rendait un `record_criteria` posant une **catégorie sans aucun
critère**, la machine relançait l'extraction **une fois**. C'était le correctif que l'étape 15
avait différé au motif qu'il casserait le plancher de 2,00 appel/tour au milieu de la
comparaison des deux orchestrations ; l'étape 18 ayant suspendu cette comparaison, le motif
est tombé avec elle. **Levée d'un report, pas décision neuve** — et le report avait vu juste
sur le principe, à ceci près que le prix n'était pas celui qu'il annonçait.

Quatre bornes, toutes dans le code et toutes testées avec le faux client de l'étape 8 —
sans clé, sans base :

1. **une relance par tour, jamais deux.** Un garde-fou dont on peut monter le compteur
   devient une boucle : il n'y a pas de paramètre ;
2. **elle ne tire que sur une extraction à zéro critère.** Un tour qui n'apporte
   légitimement aucun critère — « compare plutôt la 1 et la 3 » — n'appelle aucun outil,
   donc ne pose aucune catégorie, donc ne déclenche rien ;
3. **si la relance rend encore zéro critère, on continue avec ce qu'on a.** Le défaut est
   alors du modèle et non de l'orchestration, et on ne paie pas un troisième appel pour le
   constater ;
4. **le premier `record_criteria` est exécuté et persisté avant la relance.** Le jeter
   perdrait le budget qu'il portait — dans le tirage de l'étape 20, c'est le seul fait que
   l'extraction ait correctement lu. La relance **complète**, elle n'annule pas.

**Le plancher publié changeait de définition** : « 2,00 appel/tour » devenait « 2,00, plus
un appel sur les tours où la garde tire ». Il est revenu à 2,00 avec le retrait.

#### 🔴 Ce que la garde coûtait, et c'est ce chiffre qui l'a condamnée

**Elle tirait sur 10 des 81 tours (12,3 %), pour 2 vrais positifs.** Précision mesurée :
**2 sur 10**.

| Elle tirait sur | Tours | Un critère était-il perdu ? |
|---|---|---|
| `besoin_flou` t2 ×3 — « pour jouer, et j'ai environ 250 dollars » | 3 | non |
| `budget_absent` t2 ×3 — « mon plafond est de 145 dollars » | 3 | non |
| `categorie_efface_budget` t2 ×2 — « je vais commencer par le processeur » | 2 | non |
| `comparaison.1` t1 | 1 | **oui** |
| `sur_specifie.3` t2 | 1 | **oui** |

⚠️ **Cette imprécision n'est pas réparable dans le code, et c'est le point.** Les arguments
d'un vrai positif et d'un faux positif sont **identiques** — `{categorie, budget_usd}` est
la forme des deux. Seul le message du client les distingue, et le lire est le travail du
modèle : c'est exactement ce que la relance lui redemandait. Une garde plus fine serait une
garde qui devine. **La condition de déclenchement n'identifie donc pas le défaut**, et ça ne
se règle pas en la réglant mieux — c'est le motif principal du retrait.

*Deux resserrements ont été écrits, puis écartés par les données.* Exiger que la **catégorie
soit neuve** manquerait `sur_specifie.3`, qui repose `monitor` alors que la session y est
déjà. Exiger que **la session n'ait aucun critère** manquerait le cas où le client ajoute un
quatrième critère à trois déjà posés et que l'extraction n'en enregistre aucun. Les deux
n'auraient épargné que `budget_absent`, soit trois cassettes sur dix.

#### 🔴 Le second prix, payé en cassettes — 10 des 30 prises encore rejouables

Un appel de plus change l'empreinte de la requête suivante : les dix prises où la garde
tirait **divergeaient**, et sortaient du rejeu. Une entrée dans `DIVERGENCES_ATTENDUES` par
cassette — une assertion, pas un skip — et le résultat mesuré, avant retrait :

| Jeu | Rejouable avant | Avec la garde |
|---|---|---|
| `machine.v1` | 30 sur 36 | **20 sur 36** |
| `v2` (agent) | 34 sur 36 | 34 sur 36 — **rien ne bouge**, la garde ne touchait pas `boucle.py` |
| `v1-etape12` (agent) | 18 sur 19 | 18 sur 19 |

**Quatre scénarios n'avaient plus aucune prise rejouable côté machine** — `besoin_flou`,
`budget_absent`, `changement_davis`, `desserrage_refuse` — et
`docs/eval/comparaison.v2-machine.v1.md` se réduisait de 9 à **7 scénarios communs**,
avertissement compris, qu'il écrit lui-même.

🔴 **Et `comparaison.1` en faisait partie.** C'est la dernière prise capable de trancher pour
2 des 24 `ecart_non_dit` de l'étape 18. Le verdict sur ces deux-là serait resté **acquis** —
il a été mesuré, il est écrit — mais il aurait cessé d'être **reproductible par un rejeu**.
C'est le coût le plus élevé, et il était prévisible : **réparer l'orchestration périme les
cassettes qui mesuraient l'orchestration**. C'est ce qui a décidé du retrait à l'étape 22.

#### Décidé de ne pas être fait, avec son prix — 4 septembre 2026

**La consigne d'extraction de `systeme.machine.v1` ne sera pas resserrée.** C'est pourtant
là que le défaut vit : le prompt de la machine ne dit nulle part « enregistre **tous** les
critères que le client énonce ». Le correctif tient en un paragraphe. **Ce qui coûte est la mesure** : le prompt vit dans les
`messages`, donc dans l'empreinte de requête, et le toucher périme **les 36 cassettes de
`machine.v1` d'un coup** — ~176 appels — pour un gain que rien ne peut chiffrer sans une
campagne fraîche.

**Dette connue, correctif écrit, coût de fermeture supérieur au coût du défaut, non fait
pour cette raison.** C'est une décision datée, pas un report — un report se reconduit tout
seul, une décision se rouvre en la contredisant. Ce qui la rouvrirait : toute campagne
`machine.v1` réenregistrée, dans laquelle elle voyagerait gratuitement. Candidate déclarée
pour une `systeme.machine.v2`. Même forme que la dette nº1 de l'étape 8, §7.

#### Deux constats portés en §7, sans correctif

**`ask_clarification` est rare chez l'agent** — **4 appels** sur les **125 tours d'agent**
enregistrés (81 en `v2`, 44 dans l'archive de l'étape 12), sur **deux scénarios sur onze**,
`sur_specifie` et `zero_budget_trop_bas`. Compté sur les blocs `tool_use` des cassettes,
sans rien rejouer. Toute la mécanique qui l'entoure — outil terminal de l'amendement de
§3.7, correctif de l'étape 9 qui valide la question, `OrigineRejet.QUESTION`, métrique des
questions avant première valeur — protège et mesure un chemin que le dialogue emprunte peu.
⚠️ **Et son contrepoids compte autant** : les questions, elles, sont **partout** — l'agent
en pose presque à chaque tour, en prose. L'outil est le **seul** endroit où une question est
un objet et non une phrase ; le supprimer ne supprimerait pas les questions, il supprimerait
la seule mesure qu'on en a. Et le 0 de la machine n'est **pas comparable** : elle n'expose
pas l'outil, sa question est écrite à l'appel de rédaction.

**`rapport_qualite_prix` ajouté sans que le client l'ait demandé** — observé une fois à
l'étape 19, **0 sur 6** tirages à l'étape 20. Symptôme unique, clos sauf réapparition.

#### Reste après l'étape, et ce n'est pas du travail en cours

- **réenregistrer `machine.v1`** — ~176 appels. Rétablirait le verdict de l'étape 15, et
  c'est la seule chose qui mesurerait un correctif d'extraction ;
- **`systeme.machine.v2`** — la consigne d'extraction, et l'extraction atomique en général ;
- **la dette nº1 de l'étape 8** — reclassée à l'étape 17, coût de fermeture ~366 appels ;
- **la recherche hybride `pgvector`** (§3.5), hors périmètre du produit livrable.

---

### Étape 22 — le retrait de la garde d'extraction ✅

**Zéro appel API. Dernière action du projet avant présentation.**

La garde écrite à l'étape 21 est retirée. Elle avait été construite en entier, testée hors
ligne et chiffrée — **et c'est son chiffre qui la retire**, pas un doute.

#### Les trois termes de l'arbitrage, tous mesurés

| | |
|---|---|
| **Ce qu'elle corrige** | un défaut à **2 tours sur 81** — 2,5 % —, dont le rattrapage réel n'est mesurable que par une campagne fraîche (~176 appels) |
| **Sa précision** | **2 sur 10**. Elle tirait sur 10 tours pour 2 vrais positifs, et les arguments d'un vrai et d'un faux positif sont **identiques** : `{categorie, budget_usd}`. Deux resserrements essayés ne les séparent pas — **la condition de déclenchement n'identifie pas le défaut**, et ça ne se règle pas en la réglant mieux |
| **Son prix** | **10 des 30 prises encore rejouables** de `machine.v1`, quatre scénarios vidés, la comparaison agent/machine réduite de 9 à 7 scénarios, et `comparaison.1` perdue — la dernière capable de trancher 2 des 24 `ecart_non_dit` de l'étape 18 |

**C'est le même arbitrage que la dette nº1 (étape 17) et que la consigne d'extraction
(étape 21) : coût de fermeture supérieur au coût du défaut.** Le tenir là et pas ici aurait
été un double standard, sur la seule des trois où le correctif avait déjà été écrit — c'est
précisément le moment où l'on est le plus tenté de garder ce qu'on vient de construire.

⚠️ **Et c'est la seule des trois dont le prix a été mesuré au lieu d'être estimé.** Les deux
autres refusent un correctif d'après une estimation de ce qu'il coûterait ; celle-ci le
refuse après l'avoir construit, exécuté et compté. Le coût du détour est **zéro appel API**
et une mesure qui n'existait pas avant : sans la garde écrite, la précision 2/10 serait
restée une intuition.

#### Ce que le retrait rend, vérifié

| | Avant retrait | Après |
|---|---|---|
| `machine.v1` rejouable | 20 sur 36 | **30 sur 36** |
| `comparaison.v2-machine.v1.md` | 7 scénarios | **9 scénarios** |
| `make check` | 1028 | **1018** |
| `rapport.machine.v1.md` et la comparaison | — | **identiques au bit près** à leur état d'avant l'étape 21 |

Les trois attentes de scénario non tenues du jeu machine sont revenues avec `sur_specifie.3`,
et le README les annonce **toutes les trois** à côté de la commande.

#### Ce que l'étape 21 laisse, et qui n'est pas retiré

Le **recensement** (2 tours sur 81, 13 écartés), les deux constats de §7
(`ask_clarification` rare avec son contrepoids, `rapport_qualite_prix` non reproduit), §5 à
jour des étapes 19 à 21, le verdict suspendu de l'étape 15, `LISEZMOI.md`, et le rouge
attendu annoncé dans le README. **Le retrait est chirurgical** : `git revert` du commit
aurait détruit la clôture avec la garde.

#### Ce qui reste, et qui n'est pas du travail en cours

Inchangé depuis l'étape 21, moins la ligne sur la garde : réenregistrer `machine.v1`
(~176 appels), `systeme.machine.v2`, la dette nº1 de l'étape 8 (~366 appels), la recherche
hybride `pgvector` (§3.5).

### Étapes 23 à 25 — posées ici, racontées plus tard ⏳

⚠️ **Trois lignes, pas trois récits.** Ces trois étapes sont committées et vertes, mais
leur compte rendu complet — les arbitrages, les alternatives écartées, les chiffres —
attend le jalon de consolidation, avec la campagne de cassettes v3. Elles sont posées ici
maintenant parce que **le code les nomme déjà** : sans ces trois lignes, une quarantaine de
docstrings renverraient à des numéros que §5 ne connaît pas.

| Étape | En une ligne |
|---|---|
| **23 — le journal d'observation** ✅ | `structlog` est enfin configuré (il ne l'avait jamais été, et `RAIYON_LOG_LEVEL` n'était lue par personne), un JSONL optionnel double le terminal, deux tables — `appels_modele` et `evenements_tour` — écrites dans le commit unique de fin de tour, et un tableau de bord `/journal` réservé à `dev`. En chemin : le raisonnement adaptatif était **actif depuis le premier appel du projet** alors qu'un commentaire annonçait le contraire, et `refusal` n'était surveillé par personne |
| **24 — `systeme.v3`** ✅ | trois sections changent — la 5 cesse d'obliger à réciter des agrégats, la 6 fait passer la recherche devant la question de plus, la 8 laisse au vendeur le choix de la première catégorie. **v2 reste le défaut**, faute de cassettes v3. Deux outils de mesure entrent avec elle, dont un écrit après une comparaison assemblée à la main qui s'est corrompue au caractère |
| **25 — le correctif du validateur** ✅ | accuser réception d'un budget que le client vient d'énoncer était **structurellement impossible** ; `montants_du_client` le rend possible, sous deux gardes — jamais le prix d'un produit, jamais un message de reprise. Plus `RAIYON_VALIDATION=avertissement`, qui fait tourner les règles sans les laisser bloquer, et `Grief.arrondi`, qui **compte** une tolérance écartée au lieu de l'appliquer |

⚠️ **Ces trois étapes se sont d'abord nommées « 17 » et « 21 »**, deux numéros déjà pris
par le correctif de `NOMBRE` et par la garde d'extraction. La collision a été corrigée dans
un commit dédié plutôt que par un `amend` : le numéro d'étape est le système de références
du dépôt, et une référence ambiguë vaut moins qu'une référence absente.

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
| **Les cassettes deviennent obsolètes silencieusement** | Moyenne — les tests passent à côté de la réalité | Trois empreintes dans l'en-tête (prompt, schéma d'outils, modèle) ; le rejeu échoue en disant de régénérer. **Le validateur est la quatrième**, découverte à l'étape 13 — voir sa ligne. ⚠️ **Ce qui date chaque tirage** : l'étape 12 a été enregistrée le **2026-08-31**, la campagne v1 partielle et v2 le **2026-09-02**, toutes sous le modèle configuré `claude-sonnet-5`. ⚠️ **L'en-tête n'épingle pas un instantané** : il enregistre le nom **configuré** du modèle, qui est un alias, pas la version que l'API a réellement servie. `ReponseLLM` ne porte que `blocs` et `fin`. *Alternative écartée — capturer l'identifiant résolu* : elle rouvre le `Protocol` du client, donc le faux client et les surcharges de l'API, pour une information dont l'étape 13 n'a pas besoin. À rouvrir le jour où la dérive devient une question à part entière
| **Le nettoyage du dataset déborde** | Moyenne — dérive du projet | Geler le périmètre à ce qui est propre plutôt que poursuivre l'exhaustivité |
| **Latence perçue de la boucle multi-outils** | Faible | Streaming des événements typés dès le premier appel d'outil |
| **`absence_structurelle` est posé à la main dans le registre** | Faible aujourd'hui, croissante si le catalogue s'étend | Un seul attribut le porte (`internal-hard-drive.rpm`), et un test vérifie sur le seed que son absence est bien **déterminée** par `type`. Mais rien ne détecte le cas inverse : un attribut futur dont l'absence serait expliquée par une autre colonne ne se signalerait pas tout seul, et son zéro résultat serait diagnostiqué `donnee_absente` — donc expliqué par une phrase fausse. Atténuation partielle : un test balaie tous les attributs incomplets et échoue si l'un d'eux remplit le critère sans porter le drapeau. Il ne couvre que les vocabulaires fermés, et que le seed |
| **Le jeton de parole ne vérifie pas que le client a parlé *de ce critère*** | Moyenne — c'est la limite de §3.17, et elle est structurelle | Un mouvement qui desserre consomme le jeton du tour ; rien ne détecte qu'un desserrage autorisé par une parole a été appliqué à un **autre** critère que celui dont le client parlait. « Je peux monter un peu », dit du budget, peut payer un recul de la fréquence de rafraîchissement. Un desserrage par tour au lieu de zéro contrôle tue l'essai-erreur — l'agent ne peut plus tâtonner jusqu'à trouver quelque chose à montrer — mais ce n'est pas une garantie, et l'alternative (exiger une citation verbatim) donne l'illusion d'une preuve sans en être une. Atténuation réelle : chaque mouvement est tracé, donc mesurable en éval à l'étape 12 |
| **Le budget effacé au changement de catégorie est tarifé, pas empêché** | Moyenne | Changer de catégorie remet le budget à `None` (étape 7, arbitrage D) et **paie le jeton du tour**, comme n'importe quel desserrage. Le modèle peut donc, en deux messages du client, revenir à la catégorie de départ sans plafond : c'est le prix d'une parole, pas une porte fermée. Le seul correctif qui fermerait vraiment est un **budget par catégorie**, et il rouvre exactement la divergence que §3.10 ferme en donnant au budget une colonne unique — deux copies d'une même contrainte finissent par dire deux choses. Le choix est donc assumé : une porte tarifée plutôt qu'une seconde source de vérité |
| **`probe_catalog` est un oracle à prix** | Moyenne — elle porte sur le critère nº1. **Partiellement fermée à l'étape 9** | Le sondage rend une fourchette de prix exacte sur le sous-catalogue courant. Avec deux ou trois sondages resserrés, l'agent connaît le prix d'un produit qu'on ne lui a **jamais** donné, et sans identifiant. L'alternative — rendre des paliers arrondis — a été écartée parce qu'un arrondi est lui-même une affirmation approximative sur le catalogue : il en fabrique une pour en éviter une autre. Atténuation : ~~le prompt~~ **la règle 2 du validateur** — un montant écrit dans une phrase qui nomme un produit fourni doit être le prix **de ce produit** ou son écart au budget, jamais une borne d'agrégat. Le piège nº6 de `tests/validateur/test_pieges.py` le constate, et il échoue si le contexte est aplati. ⚠️ **Ce qui reste ouvert** : la règle ne sait pas qu'un nom qu'elle ne connaît pas est un nom de produit. « L'Acer XV272U est à 108 $ », dans une conversation où seul un sondage a eu lieu, passe — 108 est un agrégat fourni, et aucun produit **connu** n'est nommé dans la phrase. Fermer ce cas demanderait de reconnaître un nom de produit inventé dans du texte libre, ce qu'aucune heuristique ne sait faire honnêtement |
| **`regle_valeurs_unitaires` lit un guillemet comme des pouces** | Faible aujourd'hui, certaine à terme | Mesuré à l'étape 28 : « Vantrix Pro 480 » cité entre guillemets dans une prose devient `480"`, donc **un écran de 480 pouces**, et déclenche `valeur_non_fournie`. Même famille que le correctif de `NOMBRE` (étape 17) : une expression qui reconnaît une unité dans une chaîne ne sait pas si le caractère appartient au nombre ou à la ponctuation. 🔴 **La prédiction s'est réalisée dans la même session, à la passe suivante** : « le "Nexoria ZX-9000" n'existe pas dans notre catalogue » — phrase parfaitement légitime, et même exactement celle que la mesure du cas (a) attend — a été refusée sur `9000"`, lu comme 9 000 pouces. Ce n'est donc plus un défaut sans occurrence : **il refuse de la prose vraie, et il l'a fait sur le seul chemin où nommer un produit hors catalogue est le bon comportement**. Conséquence de second ordre mesurée : à la régénération, le modèle a cessé de nommer le produit, et le client y perd. Consigné sans correctif : le fermer demande de distinguer un guillemet d'unité d'un guillemet de citation, ce qu'aucune heuristique locale ne fait honnêtement, et le défaut n'a aujourd'hui aucune occurrence sur du texte vrai |
| 🔴 **Un compte de griefs à une prise est dans le bruit — mesuré** | **Élevée**, et elle invalide des comparaisons déjà publiées | Étape 29 : trois exécutions **identiques** des quatre mêmes scénarios ont rendu **3, puis 0, puis 2** griefs, sans qu'aucune touche le chemin web (0 appel à `search_reviews` dans les trois). L'amplitude mesurée est donc de 0 à 3 sur un compte dont les valeurs publiées valaient 0 à 3. ⚠️ **Conséquence qui déborde le jalon : toute comparaison de comptes de griefs faite jusqu'ici — v2 contre v3, l'étape 28 — est dans le bruit. Aucune n'est fausse, aucune n'est établie.** La correction n'est pas une note : c'est le harnais qui doit porter les prises multiples, et `ligne_de_base.py` publie désormais `min/méd/max` au lieu d'un nombre seul. Ce risque a été trouvé en **rejouant plutôt qu'en déduisant** une ligne de base dont la déduction disait « rien ne bouge » — cinquième précédent de capacité supposée non mesurée, deuxième attrapé du bon côté |
| **Le 4/4 des cas adverses est un résultat, pas un taux** | Moyenne — c'est une lecture de portfolio qui peut déraper | Étape 28 : le modèle n'a suivi aucune des quatre injections. ⚠️ **Deux réserves voyagent avec ce chiffre partout où il est cité.** (1) Un tirage par cas : quatre conversations ne disent rien de la variance, et rien ne permet d'en tirer un taux de résistance. (2) **Deux des quatre charges n'ont été livrées qu'après avoir ajusté les fixtures à la forme réelle des requêtes du modèle** — la livraison est une précondition, pas la mesure, et deux tirages avaient échoué avant. Un 4/4 survendu vaut moins qu'un 2/4 honnête |
| **Aucune mesure du sixième outil côté machine à états** | Faible | Tout ce qui est mesuré aux étapes 27 et 28 l'est sur l'orchestration `agent`. La machine expose les mêmes six outils et passe par le même répartiteur, donc rien ne laisse attendre un écart — mais rien ne le constate non plus, et c'est exactement la forme d'affirmation que ce dépôt refuse ailleurs. À porter au jalon qui étend les scénarios |
| **L'entropie sur un champ numérique continu est grossière** | Faible | Sur `price_per_gb` ou `core_clock`, chaque produit porte presque sa propre valeur : l'entropie normalisée y est maximale alors que la question n'apprendrait rien. La parade est une **exclusion par nombre de valeurs distinctes** — au-delà de la moitié des candidats, le champ sort du classement. C'est **un seuil, pas une théorie**, et il n'a pas été calibré : le découpage en classes, qui serait la vraie réponse, est hors périmètre. Second effet, écrit plutôt que masqué : la normalisation par `log2(k)` mesure l'équilibre et non le gain brut, d'où un départage à score égal sur le nombre de valeurs atteignables |
| **Le champ le plus discriminant n'est pas toujours la meilleure question** | Faible — c'est la qualité perçue | Mesuré sur le seed : sur les 32 écrans à 144 Hz sous 400 $, `marque` marque 0,93 contre 0,73 pour le type de dalle, parce que treize marques bien réparties portent plus d'information que deux types de dalle. La mesure a raison ; « tu as une préférence de marque ? » n'est pourtant pas toujours ce qu'un vendeur demanderait. Gain d'information et valeur conversationnelle sont deux critères distincts : l'outil rend le premier et **reste une suggestion** (§3.8), le prompt de l'étape 8 arbitre le second, et la métrique nº3 le mesure |
| **La garde de l'arbitrage C concentre l'invariant, elle ne le supprime pas** | Faible, mais à ne pas oublier | Les outils de recherche n'ont plus d'argument de critère : il n'existe donc plus d'argument hostile à clamper. Mais la règle de collant doit toujours être appliquée quelque part, et ce quelque part est maintenant **unique** — `record_criteria`. Un futur outil qui écrirait dans l'état sans passer par `fusionner()` rouvrirait tout, et rien dans le typage ne l'en empêche. Atténuation : `EtatSession` est immuable et ses champs sont typés `Mapping`, donc une écriture en place ne compile pas sous `mypy --strict` ; mais construire un état neuf à la main reste possible |
| ~~**Le prompt v1 n'est mesuré par rien avant l'étape 12**~~ | **Éteint** à l'étape 12 — harnais d'éval branché, seize prises rejouées, rapport committé. La ligne est barrée plutôt qu'effacée : c'est le dernier risque **Élevé** du projet, et il a décidé de l'ordre des étapes 12 et 13 | Les sections 4 (« une fourchette n'est jamais un prix »), 6 (« la question suggérée est une suggestion ») et 9 (« dire le refus plutôt que le contourner ») étaient des **atténuations déclarées, pas vérifiées**. **Ce que le harnais mesure réellement, et il faut le dire précisément :** la section 4 est mesurée — `regle_montants` et `regle_valeurs_unitaires` la constatent phrase par phrase, et le taux de rejet par code dit combien de fois le modèle a essayé (7 `montant_non_fourni` et 3 `valeur_non_fournie` sur 35 tours à la première exécution). La section 9 est mesurée **à moitié** : `Attente.CRITERE_TENU` constate qu'un desserrage refusé n'a pas fini par passer, mais rien ne constate que l'agent l'a **dit** au client — voir la ligne dédiée ci-dessous. La section 6 n'est **pas** mesurée, et le harnais l'a appris à ses dépens : une attente écrite sur l'appel à `suggest_next_question` mesurait quel outil l'agent avait choisi, pas ce que le produit avait fait. Restent donc des intentions bien rédigées : la conduite du dialogue au sens large, que seul `make eval-live` donne à lire |
| ~~**Le faux client teste la boucle, pas le modèle**~~ | **À MOITIÉ fermée à l'étape 15** — et la moitié compte. **Fermée du côté de la machine** : `decider()` est pure, et **17 tests de conduite du dialogue** tournent dans `make check` sans base, sans conteneur et sans clé — un défaut de conduite de la machine ne passe plus. ⚠️ **Ouverte du côté de l'agent**, où elle l'était et le reste : il n'y a toujours aucune fonction de décision à assertionner, et c'est le prix de §3.6 que l'amendement de cette section confirme. La ligne est donc barrée à moitié, pas éteinte. ⚠️ **La réserve voyage avec le chiffre** : ces tests vérifient que la machine conduit le dialogue **comme on l'a écrit** ; ils ne vérifient pas que la conduite est bonne, ni que le modèle qui rédige derrière respecte quoi que ce soit. Le texte d'origine reste ci-contre parce qu'il décrit exactement ce qui vaut encore pour l'agent | `tests/agent/` couvre l'enchaînement, le réenchaînement de l'état, la terminalité, l'appairage des `tool_result` et la garde d'itérations — tout ce qui ne dépend pas de ce que le modèle répond. **Un défaut de conduite du dialogue passe donc entièrement à travers `make check`** : un agent qui interrogerait le client six fois de suite, ou qui citerait un prix jamais fourni, ferait une suite verte. C'est la contrepartie assumée de l'arbitrage 2, et elle ne se referme qu'avec les cassettes et le client simulé de l'étape 12 |
| ~~**Le texte sortant n'est validé par rien jusqu'à l'étape 9**~~ | **Éteint** à l'étape 9 — validateur programmatique branché, texte bufferisé, une régénération puis repli sur template. La ligne est barrée plutôt qu'effacée : c'est le risque qui a décidé de l'ordre du plan | §2 reposait **uniquement sur le prompt système** : un prix recopié de travers, un `id` approximatif ou une spec déduite d'un sondage partaient au client. C'est pour cette raison que l'étape 9 est passée avant l'étape 10 — mettre une API et un front devant un texte non validé aurait multiplié la surface avant de fermer le trou. **Le trou est fermé au niveau du mécanisme, pas de la couverture** : les trois lignes qui suivent disent ce que le validateur ne voit pas |
| ~~**Deux règles du validateur pouvaient être conjointement insatisfaisables**~~ | **🔴 Élevée — un chemin nominal du produit était impossible. Fermée à l'étape 18** | **Le défaut** : `regle_ecart_au_budget` exigeait l'écart au budget dans la **phrase** qui nomme le produit hors budget ; `regle_montants`, dans une phrase sans produit, n'admettait pas les écarts — `hors_budget.values()` n'était pas dans ses montants autorisés. Le nom sur une ligne et « il dépasse de 11,59 $ » sur la suivante, et les deux règles se contredisaient : l'une réclamait le chiffre, l'autre affirmait qu'« aucun outil n'a rendu ce montant » — d'un montant que le moteur avait rendu. **Le texte était refusé quoi que le modèle écrive**, deux fois, puis replié. ⚠️ **La section 14 du prompt y menait** : elle demande un produit par ligne, et `SEPARATEURS_DE_PHRASE` traite le saut de ligne comme une fin de phrase. Aggravation : la règle 4 exigeait l'écart dans **chaque** phrase nommant le produit — dans une comparaison, un produit est nommé trois ou quatre fois. **Ce que le produit ne savait donc pas faire** : comparer deux produits au-dessus du budget, une demande courante. **Le correctif, en deux gestes** : les écarts entrent dans les montants admis de la branche sans produit — strictement plus sûr que ce qui s'y trouvait déjà, qui admet des `valeurs_refusees` **écrites par le modèle** ; et la présence de l'écart se vérifie sur le **message**, plus sur la phrase, **par identifiant** — citer l'écart de A ne satisfait pas B. Trois tests bornent le desserrage. ⚠️ **C'est un desserrage assumé du critère nº2** : « sans présentation explicite » est satisfait en le disant **une fois** ; l'exiger à chaque phrase était un artefact du découpage — dont ce §7 disait déjà qu'il « devient trop étroit, jamais trop large », sans avoir envisagé qu'une étroitesse puisse **fabriquer une contrainte impossible**. ⚠️ **Trouvée en conversation réelle, par aucune commande automatique** — et c'est le **second** défaut du projet trouvé ainsi, après celui que `make eval-live` a montré à l'étape 12. Deux occurrences ne sont plus une anecdote : ce que trente-six prises scriptées ne voient pas, une conversation le voit, et le dépôt n'a pas de commande qui l'oblige. **Effet mesuré, sans réenregistrer une cassette** : v2 4 → 3 griefs, `v1-etape12` 7 → 6, `machine.v1` 51 → 10 — mais ce dernier chiffre porte sur 30 prises sur 36, et il **ne dit pas** que les 22 `ecart_non_dit` disparus étaient des faux positifs. Voir §5 étape 15, verdict suspendu |
| ~~**`NOMBRE` lit une résolution collée à une fréquence comme un seul nombre**~~ | **Fermée à l'étape 17** | `NOMBRE` valait `\d+(?:[ESPACES]\d{3})*(?:[.,]\d+)?` : l'espace y était un séparateur de milliers sans condition. « en 1920x1080 180 Hz » était donc lu **1 080 180 Hz**, une valeur qu'aucun produit ne déclare, et la règle 5 levait un `valeur_non_fournie` sur une phrase **exacte** — un **faux positif du validateur**, pas une faute du modèle, et il était apparu parce que la section 14 de v2 pousse à écrire un produit par ligne. **Le motif livré** : `(?<!\d)(?:\d{1,3}(?:[ESPACES]\d{3})+|\d+)(?:[.,]\d+)?`. ⚠️ **Il porte une garde que la rédaction de cette ligne n'avait pas, et sans elle le correctif ne corrigeait rien** — c'est la trouvaille de l'étape 17, et elle est de la même famille que le défaut qu'elle répare. L'alternance seule avait été **validée sur les six formes nues** (`1 299,99`, `9333`, `1920x1080 180 Hz`, `417.14`, `1080 180`, `144`), et elle y est juste : `MOTIF_NOMBRE` se lit par `finditer` depuis le début du texte et ne redémarre jamais au milieu d'un chiffre. **Les quatre motifs composés, eux, exigent une unité ou un symbole derrière** : quand la lecture échoue au `1` de `1080`, le moteur réessaie plus loin et retombe **à l'intérieur** du nombre, où `\d{1,3}` accepte `080` — le validateur réclamait alors `80 180 Hz` au lieu de `1 080 180 Hz`. Mesuré avant de commiter : un faux positif **déplacé**, pas supprimé, et une cassette périmée pour rien. `(?<!\d)` interdit à un nombre de commencer au milieu d'une suite de chiffres. ⚠️ **La rédaction évidente `\d{1,3}(?:[ESPACES]\d{3})*` reste fausse** et cassait plus qu'elle ne répare : sur `9333` elle lit `933` puis `3`. **Livré sans réenregistrer une seule cassette** — c'est le pari de l'étape 17, et il tient parce que l'arbitrage A de l'étape 12 fait relire la prose par le validateur **courant** à chaque rejeu. Effet mesuré : v2 passe de **6 griefs sur 81 tours à 4 sur 79**, `valeur_non_fournie` de 3 à 1 ; `machine.v1` et `v1-etape12` ne bougent **d'aucun chiffre**. Une seule cassette diverge — `v2/categorie_efface_budget.3`, absorbée par `DIVERGENCES_ATTENDUES` |
| **L'extraction de la machine est atomique, et une extraction manquée ne se rattrape pas dans le tour** | **Moyenne — propre à la machine, non corrigée volontairement** | Observé sur `sur_specifie.3` : l'appel d'extraction pose `panel_type` en `bloquant`, la couche outils refuse (§3.4quater — un champ de rôle `score` ne peut pas l'être), et **l'appel étant atomique, la taille, la fréquence et le budget sont perdus avec lui**. L'agent lit le refus dans son `tool_result` et rappelle l'outil en `important` — c'est dans sa cassette. La machine ne peut pas : `enregistrer_criteres` n'est **pas une action** de `decider()`. Même famille par omission sur `categorie_efface_budget.2`, où l'extraction n'émet aucun `tool_use` au second tour : la prose annonce au client que son budget ne s'applique plus tandis que l'état l'ignore. C'est le mécanisme derrière « l'agent encaisse naturellement les virages » (§3.6), **observé** plutôt qu'affirmé, et il est plus profond que le tour de parole. ⚠️ *Correctif écarté et daté* : laisser `decider()` redéclencher une extraction ajoute un appel modèle, casse le plancher de 2,00 et change le coût au milieu de la comparaison. Candidat pour une `systeme.machine.v2` que l'étape 15 ne fait pas. **Report tenté puis abandonné aux étapes 21-22** : le motif du report — « casser le plancher de 2,00 au milieu de la comparaison » — est tombé quand l'étape 18 a suspendu la comparaison, et une garde de relance a été écrite. ⚠️ **Elle ne couvrait de toute façon pas le cas d'origine** : sur `sur_specifie.3` au tour 1, l'extraction avait parfaitement lu les trois critères, c'est la couche outils qui a tout refusé — une garde qui lit les **arguments** du modèle ne voit rien là. Elle ne couvrait pas non plus `categorie_efface_budget.2`, dont le tour n'émet **aucun** `tool_use`. Elle est retirée, avec son chiffre, à la ligne suivante. Ce qui fermerait celle-ci pour de bon reste une extraction non atomique — `systeme.machine.v2` |
| **« Ne pas chercher tant que le budget manque » n'est écrite dans aucun prompt** | **Éteinte à l'étape 15** — la règle est désormais écrite quelque part | L'agent la tient par l'**affordance** de `question_suivante`, qui remonte `BesoinDeBudget` en tête, et jamais par une instruction. `Attente.AUCUNE_RECHERCHE_SANS_BUDGET` la mesure depuis l'étape 12 sans que personne ait remarqué qu'**aucune section du prompt ne la portait** — la relecture section par section du jalon 3 l'a établi. `decider()` l'écrit pour la première fois, en une garde. Une garantie tenue **par chance de conception** d'un côté, **par construction** de l'autre. ⚠️ **Écrire la seconde orchestration était la seule façon de s'en apercevoir**, et c'est l'argument le plus fort en faveur d'avoir fait l'étape |
| **`ecart_non_dit` n'était pas une règle dormante — elle n'avait jamais été sollicitée** | Faible, et c'est une **bonne** nouvelle | Le README déclarait trois codes sur six jamais déclenchés. La machine en fait tirer un **24 fois**, et le validateur les a tous refusés avant livraison : les critères nº1 et nº2 tiennent **des deux côtés**. Le filet est décoratif chez l'agent (2 rejets par passe) et **porteur** chez la machine (17). C'est §3.11 — « les garanties ne vivent pas dans l'orchestration, elles vivent dans les outils » — vérifié dans une direction que personne n'avait prévue : la garantie a tenu sous une orchestration pour laquelle elle n'avait pas été conçue. ⚠️ **Ce que cela dit des deux autres est ouvert, et doit rester écrit comme ouvert** : `id_inconnu` et `nom_reecrit` ne se déclenchent toujours sur aucune des deux orchestrations. Ils restent **non sollicités, pas démontrés morts** |
| **`RAIYON_ORCHESTRATION` n'a plus d'effet au rejeu** | Faible — **changement de comportement d'une variable documentée**, donc il se dit | Depuis le correctif du jalon 5 : l'orchestration voyage **par valeur** dans `Reglages`, comme `systeme` le fait depuis l'étape 13, et elle se lit dans l'**en-tête de chaque cassette**. La raison est la même que pour le prompt : `make eval-comparer` rejoue **deux jeux dans un même processus**, et une variable d'environnement n'a qu'une valeur — les cassettes de la machine partaient dans la boucle de l'agent et divergeaient au premier tour. Rejouer une prise sous une autre orchestration que celle qui l'a enregistrée n'est pas un choix, c'est une erreur : la variable ne sert donc plus qu'à `make eval-enregistrer` et à `make chat`. **Le champ que le jalon 0 avait écrit sans le consommer est devenu la source de vérité** |
| ~~**La machine importe six helpers privés de `boucle.py`**~~ | **Fermée à l'étape 16, jalon 1 — et le couplage réel était le double** | Le compte était faux : `machine/orchestrateur.py` importait **douze** noms de `boucle.py`, six privés et six publics, et le plus structurant des douze était public. Pire, `orchestration.py` — le module **neutre**, celui qui porte le `Protocol` — faisait `from raiyon.agent.boucle import IssueDuTour` : **le contrat commun aux deux orchestrations était défini à l'intérieur de l'une d'elles**, et la machine dépendait de l'agent pour son propre type de retour et ses constantes de rôle. Ne déplacer que les six privés aurait laissé le même couplage sous un nom public. Les douze sont donc sortis ensemble, dans le paquet `raiyon/orchestration/` — `contrat.py` pour les types, les rôles et les phrases, `blocs.py` pour les six helpers **rendus publics**, ce qu'ils auraient dû être dès qu'un second appelant est apparu. La ligne se ferme sur la preuve qu'elle réclamait elle-même : les **cinq** documents de `docs/eval/` se régénèrent à l'identique, pour les deux orchestrations à la fois, et `make check` rend exactement 1002. ⚠️ **Ce qui reste, et qui n'est pas la même dette** : `orchestration/blocs.py` importe encore `agent.evenements` (le vocabulaire de sortie, partagé) et `agent.prompts` (un chargeur de fichiers). Reste de nommage, pas reste de couplage — mais les déplacer demanderait de bouger deux modules de plus, ce que cette étape s'interdisait |
| **La consigne d'extraction de `systeme.machine.v1` ne sera pas resserrée — décision du 4 septembre 2026** | **Non faite, et ce n'est pas un report** | Le prompt de la machine ne dit nulle part « enregistre **tous** les critères que le client énonce ». C'est là que vit le défaut recensé à l'étape 21 — **2 tours sur 81** perdent un critère explicitement énoncé, sur `comparaison.1` et `sur_specifie.3`, ligne suivante. **Le correctif tient en un paragraphe.** Ce qui coûte est la mesure : le prompt système vit dans les `messages`, donc dans l'empreinte de requête (étape 12, arbitrage C), et le toucher périme **les 36 cassettes de `machine.v1` d'un coup** — ~176 appels — pour un gain que rien ne peut chiffrer sans une campagne fraîche. **Dette connue, correctif écrit, coût de fermeture supérieur au coût du défaut, non faite pour cette raison.** Même forme que la dette nº1 ci-dessous, et la même différence : un report se reconduit tout seul, une décision se rouvre en la contredisant. Ce qui la rouvrirait : toute campagne `machine.v1` réenregistrée, où elle voyagerait gratuitement — elle se paierait alors avec le verdict suspendu de l'étape 15, qui a besoin des mêmes appels. Candidate déclarée pour une `systeme.machine.v2` |
| **Un critère explicitement énoncé n'est pas toujours enregistré — décision du 5 septembre 2026** | **Moyenne — correctif écrit, testé, chiffré, puis retiré** | Mesuré à **2 tours sur 81** (`comparaison.1` t1, `sur_specifie.3` t2) sur les cassettes de `machine.v1`, **13 tours douteux écartés** plutôt que comptés : catégorie ou budget énoncés sans être enregistrés là où c'était le bon comportement, et critères correctement extraits puis refusés en bloc par la couche outils. Propre à l'extraction atomique — `enregistrer_criteres` n'étant pas une action de `decider()`, une extraction partielle ne se rattrape pas dans le tour ; l'agent, lui, rappelle l'outil après avoir vu de mauvais résultats. **Correctif écrit, testé, chiffré, puis retiré à l'étape 22** : une garde « catégorie posée, zéro critère » a une précision de **2/10** — les arguments d'un vrai et d'un faux positif sont **identiques**, `{categorie, budget_usd}` étant la forme des deux, et deux resserrements essayés ne les séparent pas. Elle coûtait **10 des 30 prises encore rejouables** de `machine.v1`, dont `comparaison.1`, la dernière capable de trancher 2 des 24 `ecart_non_dit` de l'étape 18. **Non retenue pour cette raison.** ⚠️ **C'est une décision datée, pas un report** — un report se reconduit tout seul, une décision se rouvre en la contredisant —, et **la seule des trois de ce dépôt dont le prix a été mesuré au lieu d'être estimé** : la dette nº1 et la consigne d'extraction refusent un correctif d'après une estimation, celle-ci le refuse après l'avoir construit et compté. Ce qui la rouvrirait : une campagne `machine.v1` réenregistrée, qui mesurerait enfin ce qu'un correctif d'extraction rattrape. Candidate pour une `systeme.machine.v2`, avec la campagne qui la mesurerait |
| **Un correctif périme les cassettes qui mesuraient le défaut qu'il corrige** | 🔴 **Élevée — c'est ce qui érode l'artefact le plus cher du projet** | `machine.v1` est rejouable à **30 prises sur 36** depuis l'étape 18, deux scénarios n'y ont **plus aucune** prise (`changement_davis`, `desserrage_refuse`), et `comparaison.v2-machine.v1.md` se réduit à **9 scénarios sur 11**. ⚠️ **Le motif est structurel, pas accidentel** : une cassette enregistre les réponses du modèle sous un historique donné, donc **toute correction de l'orchestration ou du validateur périme les prises qui portaient le défaut corrigé** — c'est-à-dire exactement celles qui le mesuraient. La mesure d'un correctif est en partie auto-annulante, et ce dépôt l'a constaté **trois fois** : étape 13 (validateur, 1 prise), étape 18 (validateur, 6 prises), étape 21 (orchestration, 10 prises — le correctif a été retiré à l'étape 22, **pour ce motif précisément**). ⚠️ **C'est devenu un critère de décision, et pas seulement un constat** : le coût en cassettes d'un correctif se compte désormais avant de le garder. Ce qui l'atténuerait n'est pas un mécanisme mais un budget — réenregistrer après chaque correctif. Ce qui ne doit **jamais** l'atténuer est une tolérance à la divergence : voir `DIVERGENCES_ATTENDUES`, qui affirme au lieu d'excuser |
| **`ask_clarification` est rare, et sa mécanique est plus grosse que son usage** | Faible — **constat de conception, aucun correctif** | **4 appels** sur les 125 tours d'agent enregistrés (81 en `v2`, 44 dans l'archive de l'étape 12), sur **deux scénarios sur onze**. Compté sur les blocs `tool_use` des cassettes, sans rejeu. Autour de ces 4 appels : l'outil terminal de l'amendement de §3.7, le correctif de l'étape 9 qui valide la question, `OrigineRejet.QUESTION`, et la métrique « questions avant première valeur ». ⚠️ **Et le contrepoids compte autant que le constat** : les questions, elles, sont **partout** — l'agent en pose presque à chaque tour, en prose. L'outil est le **seul** endroit où une question est un **objet** et non une phrase ; le supprimer ne supprimerait pas les questions, il supprimerait la seule mesure qu'on en a, et la seule validation. « Rare dans les cassettes » n'est donc pas « inutile ». ⚠️ Et le **0** de la machine n'est **pas comparable** : elle n'expose pas l'outil, sa question est écrite à l'appel de rédaction et validée par `OrigineRejet.QUESTION` autrement |
| **`rapport_qualite_prix` a été ajouté une fois sans que le client le demande** | Faible — **symptôme unique, clos sauf réapparition** | Observé une fois à l'étape 19, en conversation d'essai : l'extraction pose `optimisation: rapport_qualite_prix` sur un message qui ne demandait rien de tel. L'étape 20 a rejoué le tour six fois — quatre côté machine, deux côté agent — et ne l'a **pas** revu : **0 sur 6**. Une occurrence isolée n'est pas un motif, et une cassette porte la même forme (`comparaison.2`). Écrit ici plutôt que corrigé, et rouvert si un second cas apparaît |
| **La dette nº1 de l'étape 8 — décision de ne pas la fermer, prise le 3 septembre 2026** | **Non fermée, et ce n'est plus un report** | `DESCRIPTION_SONDER` et `DESCRIPTION_PRECISION` portent des règles de dialogue que le prompt système redit — « une fourchette n'est jamais le prix d'un produit », « ne jamais demander sans donner quelque chose ». Deux rédactions d'une même règle finissent par en dire deux choses. **Le correctif est écrit et tient en une suppression** : les deux descriptions perdent leur règle, le prompt la garde. **Ce qui coûte, ce n'est pas le correctif, c'est la mesure.** `schema_outils.py` est dans le préfixe mis en cache, et `outils_empreinte` se calcule sur `schema_des_outils()` — **les cinq définitions, y compris pour la machine à états**, qui n'en expose qu'une (découvert au jalon 4 de l'étape 15). Toucher une description périme donc **les deux jeux**, pas seulement celui de l'agent. Coût de fermeture : **~366 appels** — ~190 pour v2, ~176 pour `machine.v1` — soit plus que l'étape 15 entière. ⚠️ **Et le report l'a rendue deux fois plus chère** : quand elle a été différée à l'étape 13 il y avait **un** jeu, il y en a **deux**, et rien n'a rendu le défaut plus grave dans l'intervalle. Enfin, la dette elle-même dit qu'« on ne savait pas laquelle des deux rédactions portait l'effet » : on paierait ~366 appels pour un effet que personne ne sait prédire. **Conclusion : dette connue, correctif écrit, coût de fermeture supérieur au coût du défaut, non fermée pour cette raison.** C'est une **décision datée, pas un renvoi** — et la différence est qu'un renvoi se reconduit tout seul, une décision se rouvre en la contredisant. Ce qui la rouvrirait : un changement de prompt système qui périme les deux jeux de toute façon, la dette y voyage alors gratuitement. Elle est retirée de tout ce que le dépôt s'engage à traiter, README compris |
| **Le découpage v2/v3 n'a pas eu lieu** | Faible — **arbitrage budgétaire, écrit et daté** | L'étape 13 prévoyait `systeme.v2` (rédaction chiffrée seule) puis `systeme.v3` (domaine et markdown), pour attribuer chaque effet par isolation. Le plan coûtait ~500 appels ; les crédits en couvraient ~200. Les trois cibles sont donc parties ensemble, et **l'attribution vient de l'inspection des appendices, pas de l'isolation expérimentale** — plus faible, et suffisant ici parce que les cibles se lisent sur des artefacts différents. Les deux documents de `docs/prompts/` — la décision et sa révision — se lisent ensemble |
| **Le prompt fuit peut-être ses propres exemples chiffrés** | **Ouverte** — hypothèse testable, pas un constat | `systeme.v1.md` illustre quatre de ses onze sections avec des chiffres : « il reste 32 écrans entre 180 et 395 dollars » (§4), « du 27 pouces » (§5), « je garde le 144 Hz » (§9), « celui-ci est à 120 Hz, pas 144 » (§11). Un rapprochement, et **il ne prouve rien** : la phrase refusée de `budget_serre.1` est « redescendre à **120 Hz** », et 120 est le seul chiffre de §11. Ce peut être une coïncidence — 120 est aussi le cran plausible sous 144, et le modèle le connaît sans le prompt. ⚠️ **Ce qui est sûr, c'est que la question n'a jamais été posée**, et qu'un prompt qui enseigne par l'exemple donne au modèle des chiffres qu'aucun outil n'a rendus. Non traité à l'étape 13 : retirer ces exemples modifierait des sections **existantes**, et v2 est une addition pure — deux sections qui bougent, c'est une attribution perdue. **Candidat pour une v3 à un seul changement**, où l'effet serait attribuable. La v2 elle-même n'ajoute aucun chiffre inventé : son §13 a été réécrit pour enseigner le geste (« dites la répartition que le sondage vient de rendre ») au lieu de montrer une réponse chiffrée en bloc de citation, qui est la forme qui appelle le plus l'imitation |
| **Le validateur périme une cassette, et l'arbitrage C ne l'avait pas nommé** | **Moyenne — découverte à l'étape 13, et démontrée par un blocage réel** | L'arbitrage C de l'étape 12 nomme trois choses qui périment une cassette : le prompt système, le schéma d'outils, le modèle. **Le validateur est la quatrième.** Le mécanisme : quand un texte est refusé, la reprise est empilée dans `messages` avant la régénération (arbitrage D de l'étape 9) — elle fait donc partie de l'empreinte de requête du tour suivant. Un changement de validateur qui modifie la **liste des griefs** d'un tour régénéré change la reprise, donc l'empreinte, donc la cassette ne se rejoue plus. Constaté au jalon 1 de l'étape 13 : le correctif de `valeurs_refusees` fait tomber 2 des 4 griefs de `v1-etape12/desserrage_refuse.1`, et cette cassette a cessé d'être rejouable. **Une sur quarante** — la portée est étroite, mais elle n'est pas nulle et elle n'était écrite nulle part. ⚠️ **La divergence est le comportement correct** : sous le nouveau validateur, le modèle aurait reçu une autre reprise, et sa réponse enregistrée n'est pas celle qu'il aurait donnée. C'est l'arbitrage A qui fonctionne. *Alternative écartée — une empreinte de validateur dans l'en-tête de cassette*, qui rendrait la péremption automatique comme pour les trois autres : il faudrait hacher du **code source**, et un commentaire reformulé périmerait les quarante cassettes du dépôt. Une péremption qui se déclenche pour rien est une péremption qu'on finit par contourner. Atténuation retenue : `DIVERGENCES_ATTENDUES` (`scripts/eval.py`), une liste **assertée** et tenue à la main — une divergence non listée échoue, une cassette listée qui cesse de diverger échoue, une ligne qui nomme une cassette absente échoue. Ce n'est pas une tolérance, et la différence est ce qui empêche qu'une vraie régression du moteur y soit un jour excusée |
| **Une provenance lue dans un message `user` rendrait le validateur auto-annulant** | **Fermée à l'étape 13, et c'est le piège le plus coûteux de l'étape** | Le message de reprise de l'étape 9 est un bloc de rôle `user` **de la même forme qu'un tour client** — un seul bloc `text`, sans `tool_result` — et il **cite les extraits refusés**, puisque c'est sa fonction. Une provenance « les nombres des messages utilisateur » y prendrait donc les nombres que le validateur vient de refuser et les rendrait citables au tour suivant : le validateur s'annulerait lui-même. **Mesuré, pas déduit** : sur les quarante cassettes du dépôt, 18 griefs sur 19 disparaissaient. C'est la rédaction naïve de l'alternative écartée au jalon 1 de l'étape 13, et elle est **invisible à la lecture** — rien dans le code ne distingue une reprise d'un tour client. Atténuation : `tests/validateur/test_faux_positifs.py::test_la_reprise_ne_fournit_jamais_un_fait` construit une conversation où le seul porteur d'un nombre est une reprise, et exige qu'il reste refusé. Il échoue si quelqu'un réintroduit la provenance |
| **Une valeur de mouvement refusé est écrite par le modèle, pas par le moteur** | Faible — **ouverte volontairement à l'étape 13**, et bornée | `ContexteFourni.valeurs_refusees` admet les valeurs qu'un mouvement refusé demandait, pour que le modèle puisse obéir à la section 9 du prompt (« dites au client ce qui a été refusé ») sans être puni pour cela. ⚠️ **La provenance est un refus produit par le moteur ; la valeur, elle, sort des arguments d'appel du modèle** — qui peut donc se fabriquer un nombre citable en le faisant refuser exprès. Ce qu'il en obtient est ce qu'un entier nu lui donne déjà, et rien de plus : ces valeurs ne sont admises que dans une phrase qui **ne nomme aucun produit**, discipline de `valeurs_de_distribution`. Les pièges 13 et 14 le constatent — `Le [produit] est à 50 $` et `Le [produit] est à 999 Hz` restent refusés. **Elles ne vont surtout pas dans `agregats`** : la règle 5 consulte les agrégats sans condition, et un `refresh_rate` refusé à 999 y deviendrait citable comme spec de produit |
| **Un entier nu, sans unité et sans `$`, n'est vérifié par rien — sauf dans un intervalle** | Moyenne — c'est le trou connu et **assumé** du validateur, désormais réduit | La règle 5 ne mord que sur un nombre suivi d'une unité connue, la règle 2 que sur un montant en dollars. « 32 candidats » ou « il en reste douze » ne sont donc contrôlés par personne. L'exemption est délibérée : sans elle, « je vous propose trois modèles » lèverait un grief, et **un validateur qui crie sur du français correct finit par être débranché**. **Une exception depuis le correctif de l'étape 9** : dans « entre A et B *unité* », la borne basse hérite de l'unité de la borne haute et cesse d'être un entier nu. Elle vient d'un cas de terrain — le modèle a écrit « entre 65 et 400 dollars environ » là où la borne fournie valait 64,98 $, et 65 est un **arrondi**, c'est-à-dire l'affirmation approximative sur le catalogue que l'étape 7 avait refusé de faire produire à `probe_catalog`. Une seule forme est traitée parce qu'une seule a été observée ; « de A à B » ou « autour de A » seraient de la théorie. Fermeture complète possible et non retenue : exiger qu'un entier nu appartienne aux agrégats fournis, ce qui rendrait « trois modèles » et « les deux premiers » invalides |
| **Le découpage en phrases est une heuristique, pas une analyse syntaxique** | Faible à moyenne — elle porte la règle 2, qui est la plus fine du lot | `extraction.SEPARATEURS_DE_PHRASE` coupe sur `.`, `!`, `?` et le saut de ligne, avec une exception non négociable : un point **entre deux chiffres** n'est pas une fin de phrase, sans quoi « 417.14 $ » se lirait « 417 » puis « 14 $ ». La contrepartie est qu'« etc. » ou « M. Dupont » coupent une phrase en deux. Le sens de l'erreur est le bon : le contexte de phrase devient trop **étroit**, jamais trop large — une règle peut donc rater une attribution de prix, elle n'en invente pas. ⚠️ **Cette phrase était incomplète, et l'étape 18 l'a montré** : une étroitesse ne se contente pas toujours de rater. Quand **deux** règles lisent le même découpage et que l'une réclame un chiffre que l'autre refuse, l'étroitesse **fabrique une contrainte impossible à satisfaire** — le texte est alors refusé quoi que le modèle écrive. Ce n'est plus un faux négatif, c'est un chemin du produit qui se ferme ; voir la ligne dédiée ci-dessus. Le sens de l'erreur reste le bon **prise règle par règle** ; il ne l'est plus quand on les compose. Atténuation de conception : la décision vit dans **un seul endroit**, nommé, pour être remplaçable par un vrai découpage le jour où il en faudra un |
| **La détection d'un nom de produit réécrit est floue** | Faible, mais c'est la seule règle du validateur qui peut se tromper **contre** le modèle | La règle 3 ne peut pas se contenter d'une égalité : elle doit constater qu'un nom apparaît **de travers**, ce qui est le cas de la francisation que §3.4ter interdit (« l'Odyssée de Samsung »). Elle retire d'abord du texte les noms cités verbatim, puis cherche dans ce qui reste une ressemblance de jetons (`difflib`, seuil 0,8 par jeton et 0,6 sur le nom), avec deux garde-fous : la marque seule ne suffit jamais à accuser, et une liste de mots français courants (« modèle », « écran », « gamme »…) est exclue du rapprochement. **Ces trois nombres sont des seuils, pas une théorie.** Un catalogue dont un produit s'appellerait « Modèle X » les mettrait en défaut. Atténuation : `tests/validateur/test_faux_positifs.py` existe pour ça, et il est aussi bloquant que `test_pieges.py` |
| ~~**La question d'`ask_clarification` n'est pas validée**~~ | **Éteint** par le correctif de l'étape 9 | La question était un **argument d'appel**, pas un bloc `text` : elle traversait le répartiteur et partait au client sans qu'aucune règle ne la lise — sur le chemin le plus fréquent d'une conversation, qui contient beaucoup plus de questions que de recommandations. Elle est désormais relue dans `boucle.py` par les **mêmes** cinq règles, contre le **même** instantané de contexte que le texte, avec le **même** budget de régénération. La ligne est barrée plutôt qu'effacée : c'est le seul trou que l'étape 9 avait signalé elle-même et refermé sans qu'on le lui demande |
| **Une déconnexion client perd le tour en entier, et l'appel API avec** | Faible — c'est un choix, pas un défaut | Starlette cesse d'itérer, le générateur reçoit un `GeneratorExit`, et `session.tour()` n'atteint jamais son `commit()` : rien n'est persisté, **pas même le message du client**, alors que l'appel à Anthropic a été payé. C'est exactement la sémantique d'un redémarrage en milieu de tour, et c'est l'atomicité de `session.py` prise au mot — « sans rien perdre » signifie « sans rien écrire de faux ». Il n'y a **aucune reprise de flux** : un client qui recharge renvoie son message. Ce qui est traité, en revanche, c'est la propreté — un `finally` qui `rollback()` puis `close()`, sans quoi la connexion revient au pool en transaction avortée et fait échouer la requête *suivante* avec une erreur qui ne désigne pas la vraie cause. L'éviter demanderait le drainage par file d'attente que l'arbitrage C de l'étape 10 écarte |
| **Les messages de repli ne sont pas persistés : un tour clos par un repli revient sans aucune réponse** | Faible, et c'est désormais le comportement **voulu** | `Repli` est émis par la boucle mais n'entre pas dans `IssueDuTour.tours` — c'est du texte écrit en Python, que le modèle n'a jamais produit. `GET /sessions/{id}` relit la prose depuis les blocs (étape 10, arbitrage J) : un tour clos par un repli réapparaît donc **sans sa réponse** après un F5. **Conséquence complète, écrite depuis le correctif de l'étape 11 :** le message refusé qui a précédé ce repli ne revient plus non plus, puisqu'il est désormais suivi d'une reprise. Un tel tour revient donc comme un message client **seul**. C'est laid, et c'est juste — avant, le rechargement montrait exactement l'inverse de ce qui s'était passé : la phrase refusée deux fois, et rien du template que le client avait lu. L'interface de l'étape 11 annonce déjà la conversation reprise comme incomplète. Le correctif ne crée pas ce trou : **il cesse de le combler avec du faux.** Le correctif restant serait de persister le message de repli comme un tour assistant — mais il l'injecterait dans l'historique relu, donc dans ce que le modèle voit au tour suivant, et le modèle se lirait affirmer une phrase qu'il n'a pas écrite. Reste écarté pour ce motif, qui n'a pas bougé |
| **Aucun heartbeat sur le flux SSE** | Nulle en local, certaine derrière un proxy | Un générateur synchrone bloqué dans `messages.create()` ne peut rien intercaler : ni `: ping`, ni détection de déconnexion (étape 10, arbitrage C). Le silence réel est celui d'un tour sans appel d'outil — les événements d'outils tiennent la connexion vivante le reste du temps — et en démo locale comme en `curl`, l'effet est nul. **À rouvrir le jour d'un déploiement derrière un proxy qui coupe à 60 s d'inactivité** : la parade est nommée et chiffrée, un endpoint `async` drainant le générateur sync par une `queue.Queue`, soit une quarantaine de lignes de plomberie thread↔asyncio. Elle n'est pas écrite parce qu'aucun proxy n'est en jeu, et qu'elle ne protégerait de rien aujourd'hui |
| **Le garde-fou de l'arbitrage F favorise légèrement les produits à données manquantes** | Faible, mais réelle et constatée | Un critère indisponible sort du calcul et les poids sont renormalisés : un produit incomplet a donc moins d'occasions de perdre des points. Atténuation : à score égal, celui dont **plus de critères ont été évalués** passe devant, et la trace expose `criteres_evalues` / `criteres_indisponibles`. L'atténuation ne supprime pas le biais — elle ne joue qu'à score **exactement** égal. Un écran sans `refresh_rate` déclaré peut donc devancer un écran à 120 Hz sur un souhait de 144 Hz, et c'est visible dans la démonstration de l'étape. Les deux alternatives (0, ou 0,5) sont pires : l'une punit l'absence, l'autre l'invente |
| **Le verrou de tour reste tenu si le générateur SSE n'est jamais démarré** | Faible — fenêtre étroite, et le défaut s'auto-guérit | Le verrou est pris dans l'endpoint ; le `try/finally` qui le relâche vit dans le générateur. Or `_flux(...)` **construit** le générateur sans l'exécuter : tant que Starlette n'a pas appelé le premier `next()`, le `finally` n'existe pas. Si l'itération ne commence jamais — client déjà parti quand `http.response.start` est envoyé —, la `Session` reste ouverte, sa transaction non validée, et **le verrou tient jusqu'au ramasse-miettes**. Symptôme visible : un `409` « un tour est déjà en cours » sur une session où rien ne tourne, au renvoi d'une requête qui avait lâché. **La parade est nommée et non prise** : amorcer le générateur dans l'endpoint — un `next()` avant de rendre — pour entrer dans le `try` avant que Starlette n'itère. Elle coûte de rechaîner la première trame devant le reste du flux (`itertools.chain`), donc de compliquer le seul endroit du code qui doit rester lisible, et de déplacer le début du tour **avant** l'envoi des en-têtes — c'est-à-dire de rendre à nouveau possible une exception après la décision du code HTTP et avant le premier octet, exactement la ligne que l'arbitrage E trace. Le défaut, lui, se referme seul au GC, sa conséquence est un 409 qu'un renvoi résout, et aucun tour n'est perdu puisqu'aucun n'avait commencé |
| **Le parseur SSE et le réducteur du front ne sont vérifiés par aucun test** | Moyenne — c'est le seul code du projet dans ce cas | `tests/api/test_cadrage_sse.py` prouve que **le serveur émet** des trames bien formées, sans saut de ligne brut, et recomposables sous un découpage arbitraire des octets (1, 7, 64, 4096). Il ne prouve **pas** que `flux.js` les recompose : un parseur JavaScript qui oublierait sa queue passerait toute cette suite au vert, et son symptôme — un événement perdu de temps en temps, donc **une carte produit qui manque une fois sur dix** — ne se verrait qu'en démonstration. L'atténuation est la **concentration, pas la couverture** : la logique tient dans deux modules nommés et sans DOM (`flux.js`, 95 lignes de code ; `etat.js`, 81), dont l'un **transcrit** un algorithme écrit et testé en Python. C'est une atténuation et non une preuve, et le dire ainsi vaut mieux que la fausse assurance qu'on aurait achetée autrement. *Alternative écartée — Playwright de bout en bout* : une dépendance, des navigateurs à installer, un serveur à lancer en test, et surtout `make check` perdrait la propriété qui fait sa valeur — tourner **sans base, sans conteneur, sans clé**. La porte de sortie serait littéralement automatisée, et elle cesserait de tourner |
| **Une cassette est un tirage, pas une espérance** | Moyenne — elle porte l'étape 13 tout entière | La température n'est pas fixée (étape 8, arbitrage 12), et on ne l'a pas fixée à l'étape 12 : une cassette enregistre **une** réponse du modèle parmi celles qu'il aurait pu donner. Trois prises ont donc été enregistrées sur `budget_serre`, `besoin_flou` et `zero_budget_trop_bas` pour avoir un ordre de grandeur du bruit. ⚠️ **Trois prises ne sont pas un intervalle de confiance**, et le rapport ne le prétend nulle part : c'est un ordre de grandeur, infiniment mieux que le plancher de bruit inconnu qu'on aurait sinon, et rien de plus. Conséquence directe pour l'étape 13 : un écart entre deux prompts inférieur à cet ordre de grandeur **n'est pas un signal**, et le conclure serait exactement la faute que le motif nº3 du parcours cherche à ne plus commettre. Fermeture possible et non retenue : fixer `temperature=0` — le dépôt s'est déjà fait prendre à supposer que cela donnait du déterminisme (étape 5), et on ne le suppose plus |
| **La réponse de référence du critère nº4 est choisie à la main, et sa qualité n'est vérifiée par rien** | Moyenne — elle décide d'un critère d'acceptation | L'attendu ne vient pas du moteur (arbitrage F) : le déterminer en lançant le moteur ferait valoir la métrique 100 % par construction. Il vient donc d'une **lecture du catalogue**, et rien ne relit cette lecture. Une métrique nº4 qui chute peut donc accuser le moteur à tort. Atténuation réelle et partielle : quatre des six attendus sont adossés à une **unicité** constatée — un seul produit du catalogue satisfait les contraintes —, ce qui est le plus solide qu'on puisse faire sans jury humain, et un test pur vérifie que chaque identifiant existe bien dans le seed committé. Les deux autres (`changement_davis`, `comparaison`) reposent sur un argument, et leur `justification` le dit en toutes lettres dans `scenario.py`. **C'est cette phrase qu'il faut relire avant d'accuser le moteur**, et c'est pour ça qu'elle est une donnée et pas un commentaire |
| **Le critère nº1 ne détecte pas une règle manquante — seulement un trou dans la réaction à une règle existante** | Moyenne, et **mesurée** à l'étape 12 | Le harnais mesure le validateur **avec le validateur** : `valider()` relit la prose livrée avec les mêmes cinq règles que la boucle. Amputer `REGLES` rend donc aveugles les deux à la fois, et le critère nº1 reste à zéro pendant que du texte fautif part au client — constaté, en retirant `regle_valeurs_unitaires` puis en rejouant `budget_serre`. L'alternative — une seconde lecture indépendante de la prose — est refusée par l'arbitrage E : ce serait un second validateur, plus faible que le premier, qui finirait par diverger de lui. **Ce qui détecte une règle manquante existe pourtant, et c'est la troisième couche du rapport :** le taux de rejet s'effondre (2 → 0 sur ce scénario), l'avertissement « prises consommées » sort, et sur un scénario où le rejet ne tombe pas au dernier tour le rejeu échoue carrément en `DivergenceDeRequete`. Le critère nº1, lui, détecte bien ce pour quoi il est fait : la boucle rendue insensible à un verdict fait passer le compte à 2 griefs et `make eval` sort en code non nul |
| ~~**Un message assistant qui ne porte qu'un bloc `thinking` clôt le tour sans rien livrer**~~ | **Éteint** au correctif de l'étape 12 — `MotifDeRepli.REPONSE_VIDE`. La ligne est barrée plutôt qu'effacée : c'est le seul défaut du projet trouvé par une conversation avec un client simulé, et il était **déjà présent dans deux cassettes** que personne n'avait vues | `_depouiller()` ignore les types de blocs inconnus, et c'est voulu : un bloc inattendu ne doit pas clore une conversation par une exception. Mais quand le message n'en portait **que** un, il ne restait ni texte ni appel, et la boucle rendait son `IssueDuTour` sans avoir émis un seul événement — le client recevait `done` et rien d'autre. La boucle clôt désormais le tour par un `Repli(REPONSE_VIDE)`, phrase écrite en Python, avec un `WARNING` qui nomme les types de blocs reçus. **Ce que le motif dédié a immédiatement rendu visible** : `make eval` relancé sur les seize cassettes existantes, sans en réenregistrer une seule, fait passer le taux de repli de 0 % à 5 % — `desserrage_refuse.1` et `sur_specifie.1` contenaient déjà un tour muet. *Alternative écartée — reboucler en traitant le message vide comme une itération sans progrès* : elle laisse `messages` se terminer par un message **assistant**, donc l'appel suivant devient une continuation de ce message plutôt qu'un tour neuf ; avec un bloc `thinking` en dernière position, ce que l'API en fait n'est écrit nulle part, et le dépôt a trois précédents de capacités supposées sans être mesurées |
| ~~**La métrique nº3 est au plancher et n'a aucune marge de progression**~~ | **Éteint** au correctif de l'étape 12 — le critère compte désormais des **tours client** | *Questions avant première valeur* valait **0 sur les onze prises** qui livraient une valeur : la règle « donner avant de demander » produit son effet, l'agent n'appelle jamais `ask_clarification` avant de montrer quelque chose. Bonne nouvelle, mais §5 étape 13 demande de viser la métrique nº3 en priorité et il n'y avait rien à viser. §3.9 disait déjà quoi compter — « le bon indicateur est le délai avant première valeur, pas le compte de questions » : on compte **combien de fois le client a dû parler**. La médiane passe de 0,0 à 1,0, et la dispersion de `besoin_flou` devient lisible (2 à 3 tours selon la prise, là où les questions donnaient 0 partout). Le seuil reste à 2 et change de sens : « au deuxième message, le client a vu quelque chose ». Le compte de questions reste publié **sans seuil** — il mesure la règle de dialogue, et l'étape 13 aura besoin de savoir laquelle des deux a bougé |
| **Le taux de repli publié dépend du jeu de scénarios, et le correctif de l'étape 12 a montré comment** | Moyenne — **partiellement fermée**, et la cause n'était pas celle qu'on croyait | ~~Trente-cinq tours scriptés, zéro repli, alors que la première conversation de `make eval-live` en produisait un : les dix scénarios posent des questions **sur le catalogue**, un vrai client en pose **sur le domaine**.~~ **Le diagnostic était faux, et les cassettes l'ont dit.** Le zéro venait d'ailleurs : deux tours **muets** que personne ne comptait, faute d'un motif de repli pour eux. Le motif `REPONSE_VIDE` ajouté, les mêmes seize cassettes affichent **5 %** sans qu'une seule ait été réenregistrée. Quant à l'hypothèse des questions de domaine, le scénario `question_de_domaine` l'a testée sur trois prises et **ne l'a pas confirmée** : le modèle explique IPS contre VA sans citer un chiffre, aucune règle ne tire, aucun repli n'a lieu. Ce qui reste ouvert : le repli de domaine **existe** — la conversation live l'a déclenché — mais aucune cassette ne l'exerce, et rien n'oblige à lancer `eval-live`. Une régression sur ce chemin ne se verrait dans aucune commande automatique |
| **Rien ne constate que l'agent *dit* au client qu'il a refusé un desserrage** | Moyenne — c'est la moitié non mesurée de la section 9 du prompt | Le scénario `desserrage_refuse` vérifie deux faits, tous deux lus sur les événements : le jeton de parole a bien refusé (`CriteresMisAJour.mouvements_refuses` non vide) et le critère n'a pas fini par bouger (`Attente.CRITERE_TENU`). **Ni l'un ni l'autre ne dit ce que la prose affirme.** Un agent qui refuserait le desserrage et écrirait « c'est noté, je passe à 144 Hz » tiendrait les deux attentes. La fermer demanderait de lire la prose autrement que par le validateur, ce que l'arbitrage E refuse — un second validateur, plus faible, qui diverge du premier. Ce n'est pas une limite du harnais mais de ce qu'un harnais programmatique sait faire, et c'est exactement le genre de chose que le client simulé donne à **lire** sans savoir la compter |
| **Une affirmation de domaine chiffrée passe le validateur dès que le chiffre ne porte pas d'unité connue** | **Moyenne — inchangée côté validateur, fortement réduite côté prompt à l'étape 13** | Le trou du validateur est **le même** : « 3000:1 » n'est ni un montant, ni une valeur unitaire, et aucune des cinq règles ne tire. Il n'a pas été refermé, et il ne doit pas l'être — exiger qu'un nombre appartienne aux agrégats fournis rendrait « trois modèles » invalide, et un validateur qui crie sur du français correct finit débranché. **Ce qui a changé est ce que le modèle tente.** v1 répondait à « IPS ou VA ? » en **enseignant la technologie d'affichage** — ce que §2 lui interdit — et le faisait sans un seul chiffre, donc sans qu'aucune mesure ne le voie. La section 13 de v2 lui dit ce qu'il ne sait pas et le fait basculer sur la répartition du catalogue : « sur les 9 écrans qui correspondent à vos critères, 6 en VA, 3 en IPS ». Le compteur de chiffres **monte** — 3,67 → 7,67 par passe — et c'est le bon résultat, ces chiffres-là étant fournis. ⚠️ **Le compteur seul ne tranche rien** : c'est l'appendice B, relu à la main, qui distingue un cours de technologie d'un fait de catalogue. La ligne reste ouverte parce que rien n'**empêche** encore une affirmation de domaine chiffrée ; elle est devenue improbable, pas impossible
| ~~**`PHRASE_DE_DOMAINE` n'est exercée par aucune cassette**~~ | **Fermée à l'étape 13 — en constatant qu'elle devait le rester** | Le repli de domaine reste couvert par sept tests purs et par aucune cassette, sur trois campagnes et douze prises de `question_de_domaine`. **Et c'est le bon résultat.** `PHRASE_DE_DOMAINE` est ce qu'on sert quand la conduite a **déjà échoué** : un bon prompt la rend plus rare, pas plus fréquente. La section 13 de v2 fait en amont ce que le repli faisait en aval — dire ce que l'assistant ne fera pas, puis basculer sur le catalogue —, si bien que le chemin du repli est moins sollicité qu'avant, pas davantage. ⚠️ **Chercher une formulation de client qui le déclenche à coup sûr serait optimiser contre son propre correctif**, et la ligne se ferme en le disant plutôt qu'en fabriquant une couverture. Ce qui reste vrai : une régression sur ce chemin ne se verrait dans aucune commande automatique
| ~~**La prose du modèle contient du markdown que le front n'interprète qu'à moitié**~~ | **Fermée à l'étape 13** | Le front rend deux formes — le gras et les sauts de ligne — et le reste s'affichait tel quel : 44 backticks, 56 puces et 32 listes numérotées sur les cassettes de l'étape 12. **C'est le prompt qui a été corrigé, pas le front armé d'un parseur** : la section 14 de `systeme.v2.md` dit ce que l'écran affiche, et fait d'« une ligne par produit » l'instruction. Mesuré : **51 occurrences par passe → 0**, seul écart de la campagne v2 au-delà de la dispersion (± 43). ⚠️ **La section a eu une empreinte inattendue sur le validateur**, prédite avant la campagne : elle fait écrire la résolution collée à la fréquence, et `NOMBRE` lit « 1920x1080 180 Hz » comme un seul nombre — voir la ligne dédiée
| **La garde de `cle_api()` ne voit qu'une clé absente, pas une clé vide ou factice** | Faible depuis l'étape 14, jalon 1 — le chemin documenté est réparé, la garde ne l'est pas | `cle_api()` ne lève que sur `None` : une chaîne vide traverse et meurt sur un `TypeError` du SDK, une chaîne factice sur un `AuthenticationError: 401`, les deux en anglais et précédés d'un traceback. Le défaut était **atteignable par la procédure du README** tant que `.env.example` livrait `ANTHROPIC_API_KEY=sk-ant-xxxxx` : `make install` recopiait la valeur factice, donc le message français qui nomme les commandes concernées ne pouvait jamais se déclencher. **Atténué au jalon 1** — la ligne est commentée, `tests/test_env_example.py` échoue si elle cesse de l'être, et le chemin a été vu produire le bon message. **Ce qui reste ouvert** : une clé **mal recopiée** — tronquée, avec une espace, périmée — produit toujours un 401 brut, et c'est le cas le plus probable en usage réel. Élargir la garde touche `src/raiyon/config.py`, ce que l'étape 14 s'interdit ; la ligne est écrite pour que le correctif se décide ailleurs qu'au milieu d'une étape de finition |

---

## 8. Hors périmètre

Paiement, compte utilisateur, multilingue, gestion de panier, historique
inter-sessions.

### La composition multi-catégories (arbitrage K de l'étape 6)

Un appel au moteur rend les produits d'**une seule catégorie**, et la catégorie est
obligatoire. « Monte-moi une config gaming à 1 500 € » n'est donc pas servi en un tour :
l'étape 8 le **séquencera** composant par composant (« je conseille un composant à la
fois — on commence par la carte graphique ? »).

Ce que la composition demanderait, et qu'aucun des trois n'existe dans un MVP qui exclut
déjà le paiement et le compte client :

1. un **panier explicite** — la liste de ce qui a déjà été retenu, persistée et
   modifiable ;
2. un **budget alloué** par composant, avec retraits au fil des choix et
   réinitialisation quand le client change d'avis ;
3. un **critère d'acceptation nº2 redéfini par panier** : « budget jamais dépassé »
   cesse de porter sur un produit pour porter sur une somme, et le validateur de
   l'étape 9 devrait vérifier un total, pas une ligne.

**Le total dépensé à travers plusieurs tours n'est pas suivi.** C'est ce que « hors
périmètre » signifie ici, et c'est désormais **constatable** — l'invariant « un tour, une
catégorie » est vérifié par le moteur, qui lève si un produit d'une autre catégorie
remonte — plutôt que silencieux. Un client peut donc, en trois tours, se voir recommander
trois composants dont la somme dépasse ce qu'il avait annoncé : le moteur ne le sait pas,
et il ne prétend pas le savoir.

Conséquence documentée ailleurs : l'exemple « il me faut aussi une ponceuse, 300 € pour
les deux » ne peut plus servir à justifier l'agent contre la machine à états. §3.6 porte
l'amendement.
