# Prompt Claude Code — Étape 5 : pipeline de normalisation des données

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`. Les étapes 1 à 4 sont franchies. Tu vas
réaliser **l'étape 5 et rien d'autre**.

## Avant d'écrire quoi que ce soit

Lis, dans cet ordre :

1. `PROJET.md` — §2 (contrainte non négociable), §3.1, §3.3, §3.4, §3.4bis,
   §3.4ter, §3.4quater, §3.13, §3.14, §4 (critères d'acceptation), §5 étape 5,
   §6 (ordre non négociable).
2. `catalogue/schema_attributs.md` — **la** source de vérité des attributs, de
   leurs types cibles, de leurs unités, de leurs plages et de leurs taux de
   remplissage. `catalogue/rapport_exploration.md` pour la mesure brute.
3. `src/raiyon/catalogue/schemas.py` — les modèles Pydantic sont écrits et
   testés. **Tu ne les modifies pas** : le pipeline se plie au schéma, pas
   l'inverse. Si une transformation ne passe pas la validation, c'est la
   transformation qui est fausse, jamais le modèle.
4. `src/raiyon/db/models.py`, `src/raiyon/db/engine.py`, `src/raiyon/config.py`,
   `Makefile`, `tests/conftest.py`, `data/raw/SOURCE.md`.

Ne déduis aucun attribut de la documentation de la source : l'étape 3 a démontré
qu'elle ment deux fois (le champ `smt` promis pour `cpu` n'existe nulle part, et
`frequency_response` n'est pas en kHz sur ses deux composantes).

`data/raw/` n'est pas versionné. Vérifie sa présence et l'intégrité des fichiers
(`sha256sum -c data/raw/CHECKSUMS.sha256`) avant de commencer ; si les fichiers
manquent, la commande de récupération est dans `data/raw/SOURCE.md`.

## Périmètre — ce que tu livres

Trois choses, dans cet ordre, et rien de plus :

- **A. Passe déterministe** — lecture du dataset brut, normalisation, calcul des
  identifiants, déduplication, validation, sélection, écriture d'un seed JSONL
  committé et d'un rapport.
- **B. Passe LLM réduite** — `nom_fr` et `description` (résumé d'usage) sur les
  produits du seed, via Haiku, dans un cache committé.
- **C. Chargement** — `make seed` charge le JSONL en base. Aucun appel API.

**Explicitement hors périmètre, à ne pas commencer :** moteur de matching
(étape 6), couche outils (étape 7), boucle agent (étape 8), validateur
anti-hallucination (étape 9), API (étape 10). Aucune requête de recherche, aucun
score, aucune notion de critère client n'apparaît à cette étape.

Ne modifie ni `src/raiyon/catalogue/schemas.py`, ni `src/raiyon/db/models.py`,
ni la migration `0001_schema_initial`, ni `src/raiyon/config.py` : le pipeline
n'a besoin d'aucune nouvelle variable d'environnement. La graine du tirage est
une **constante de code** documentée, pas une variable d'environnement — elle
doit être impossible à changer par accident entre deux exécutions.

## Arbitrages déjà rendus — applique-les, ne les rediscute pas

**A. Le pipeline ne corrige jamais une donnée en silence.** Trois issues
possibles pour une ligne, et trois seulement : elle est normalisée, elle est
**écartée avec un motif compté dans le rapport**, ou elle **fait échouer le
pipeline bruyamment**. Une valeur inattendue qui serait rabotée pour « passer »
est un bug plus grave que l'arrêt.

**B. Séparation stricte des deux passes.** Tous les faits — prix, marque,
attributs, identifiant — sortent de la passe A. La passe B écrit dans deux
champs, `nom_fr` et `description`, et dans aucun autre. Elles vivent dans des
modules distincts et des cibles `make` distinctes ; la passe A **n'importe pas**
le SDK Anthropic, et un test le vérifie.

**C. L'identifiant *est* la clé de déduplication.** `id = {categorie}-{10
premiers hexadécimaux de sha256(clé canonique)}`, où la clé canonique est le
JSON trié, sans espaces, de `{nom source + toutes les specs normalisées}`. Deux
lignes qui produisent le même `id` sont le même produit par construction : la
déduplication devient un regroupement par `id`, pas une heuristique séparée.

**D. La clé exclut le prix *et toute grandeur dérivée du prix*.** C'est le piège
central de l'étape : `price_per_gb` est une fonction du prix. Le laisser dans la
clé empêcherait deux enregistrements identiques à prix différents de se
rejoindre, donc annulerait la déduplication sur les catégories qui le portent.
Conséquence directe : `price_per_gb` est **recalculé après** la déduplication, à
partir du prix retenu — voir la transformation 6.

**E. Sélection stratifiée par prix, à graine fixe.** ~170 produits par
catégorie, tirés par décile de prix de la catégorie, graine constante. Le
catalogue garde la forme de la distribution réelle, y compris sa queue haute.
Alternative écartée — un tirage uniforme : plus simple, mais les cartes
graphiques à 7 500 USD et les moniteurs à 9 333 USD disparaissent presque
sûrement, et le moteur de l'étape 6 n'aurait plus rien pour exercer sa zone de
tolérance budgétaire.

**F. Le seed est committé en JSONL, une ligne par produit.** `make seed` ne fait
que charger ce fichier. Le pipeline n'est **pas** rejoué à l'installation :
`data/raw/` n'est pas versionné, et exiger une clé API pour installer le projet
serait absurde. Alternative écartée — un dump SQL : plus rapide à charger, mais
le diff est illisible et l'insertion contournerait `ProduitEnBase`, qui est
censé être la seule porte d'entrée de la table.

**G. La passe LLM est cachée et incrémentale.** Sorties écrites dans un fichier
committé indexé par `id` ; seuls les `id` absents du cache déclenchent un appel.
Rejouer la passe sur un catalogue inchangé ne coûte rien et ne change aucun
octet — c'est le garde-fou nº 1 de §3.4ter (« figée dans le seed, jamais
rejouée au runtime ») rendu effectif.

## A. Passe déterministe

### Ordre des opérations — il n'est pas commutatif

1. **Lecture** des 6 fichiers de `data/raw/` (`keyboard.json` est ignoré ; ne le
   mentionne nulle part ailleurs que dans le compte des lignes lues).
2. **Filtrage** : `price` présent et strictement positif. Compte ce que ce
   filtre retire, par catégorie — c'est le chiffre des 76 % écartés, il doit
   apparaître dans le rapport.
3. **Normalisation** des attributs, catégorie par catégorie (voir plus bas).
   Sans les grandeurs dérivées du prix.
4. **Calcul de la clé canonique et de l'`id`** (arbitrage C).
5. **Déduplication** : regrouper par `id`, garder **le prix le plus bas**.
6. **Calcul des grandeurs dérivées du prix** sur le prix retenu.
7. **Validation** par `ProduitEnBase`. Une ligne rejetée est écartée et
   journalisée avec son motif ; elle n'est jamais réparée.
8. **Sélection** stratifiée + garanties de cas limites.
9. **Écriture** du JSONL et du rapport.

### Les transformations à écrire

Toutes vivent dans des **fonctions pures** — une valeur source en entrée, une
valeur cible en sortie, aucune I/O, aucun état. C'est ce qui les rend testables
une par une.

1. **`marque`, sur les 6 catégories** (§3.4quater) : premier mot de `name`,
   casse source conservée. ⚠️ Cette règle produit `Western` pour
   « Western Digital Blue » et `Silicon` pour « Silicon Power ». **Mesure
   d'abord** : sors la liste des premiers mots par fréquence avant de coder quoi
   que ce soit. Si des marques en plusieurs mots apparaissent, tu es autorisé à
   maintenir une **table explicite de marques multi-mots**, écrite à la main,
   versionnée dans le module, commentée une par une — c'est un parsing
   déterministe documenté, pas une supposition sur une valeur absente. Cette
   table est **fermée** : un nom dont le premier mot n'y figure pas donne le
   premier mot, sans invention. Le rapport liste les marques retenues par
   volume, pour relecture.

2. **`internal-hard-drive.type`** : `"SSD"` → `type="SSD"`, `rpm=None` ; un
   entier de tours/minute → `type="HDD"`, `rpm=<entier>`. Toute autre forme fait
   échouer le pipeline. **Décision à appliquer, elle est à toi de rendre
   effective ici** : les lignes sans `type` (0,4 %, ~8 produits) sont
   **écartées**, avec un motif dédié dans le rapport. Motif : `type` est un
   filtre dur et le premier arbitrage du domaine ; un produit dont on ignore
   s'il est SSD ou HDD ne peut pas être filtré correctement, et un client qui
   demande un SSD ne doit pas recevoir un doute. L'écarter n'invente rien, le
   combler oui (§3.4quater). Alternative écartée — le garder avec `type=None` :
   le moteur de l'étape 6 devrait alors porter une troisième branche pour
   l'inconnu, sur 8 produits.

3. **`internal-hard-drive.form_factor`** : nombre `2.5` / `3.5` → chaînes
   `2.5"` / `3.5"` ; chaînes (`M.2-2280`, `mSATA`, `PCIe`…) inchangées. Une
   seule énumération textuelle en sortie. Le rapport liste les valeurs
   distinctes obtenues et leur effectif — c'est ainsi qu'on voit qu'aucune forme
   inattendue n'est passée.

4. **`memory.speed` et `memory.modules`** : `speed = [gen, mhz]` →
   `ddr_generation`, `frequence_mhz` ; `modules = [nb, taille]` → `nb_modules`,
   `taille_module_gb` ; puis `capacite_totale_gb = nb_modules ×
   taille_module_gb`. Le validateur croisé du modèle recalcule cette dernière :
   ne la lis pas ailleurs.

5. **`headphones.frequency_response`** — le champ le plus dangereux du dataset.
   Règle : composante 0 → `freq_min_hz` en **Hz**, composante 1 →
   `freq_max_khz` en **kHz**. Uniformément, sans condition, sans `min`/`max`.
   Les 32 cas où `fr[0] > fr[1]` ne sont pas des inversions : `[100, 10]` est un
   casque de communication à 100 Hz – 10 kHz.
   **Contrôle par ordre de grandeur, obligatoire** : le pipeline vérifie que la
   composante 0 tombe dans `[1, 1000]` et la composante 1 dans `[0,5, 200]`.
   Toute valeur hors de ces plages fait **échouer le pipeline** en nommant le
   produit fautif — parce qu'elle signifierait que la règle de position est
   fausse sur cet enregistrement, et c'est exactement ce que l'étape 3 a
   attrapé sur la documentation de la source. Ne la corrige pas, ne la devine
   pas : arrête-toi et dis-le.

6. **`price_per_gb` (`internal-hard-drive` et `memory`)** : **recalculé**, pas
   recopié. `prix_usd / capacity` pour les disques, `prix_usd /
   capacite_totale_gb` pour la mémoire, arrondi à 3 décimales (`ROUND_HALF_UP`,
   en `Decimal`, jamais en flottant). Raison : la déduplication retient le prix
   le plus bas, donc la valeur source peut correspondre à un prix qui n'est plus
   celui du produit — deux champs qui disent des choses différentes du même
   fait, ce que §3.10 cherche à rendre impossible ailleurs.
   **Contrôle à écrire** : compare le recalcul à la valeur source là où elle
   existe, sur les lignes **non dédupliquées** ; imprime l'écart relatif médian
   et le 99ᵉ centile dans le rapport. Si plus de 1 % des lignes s'écartent de
   plus de 1 %, arrête-toi : cela voudrait dire que la source ne calcule pas ce
   qu'on croit, et il faut le comprendre avant de continuer.

7. **`monitor.resolution`** : `[largeur, hauteur]` → `largeur_px`, `hauteur_px`.

Les valeurs absentes restent absentes. Aucune transformation ne remplit un
champ vide, jamais, quelle que soit la vraisemblance de la valeur.

### Déduplication

Une règle unique, uniforme sur les 6 catégories : regrouper par `id`, garder le
prix le plus bas. Elle doit absorber les 51 redondances de `cpu` et préserver
les 346 variantes de `memory` **sans aucun traitement par catégorie** : c'est le
même code, seul son effet diffère. Le rapport donne, par catégorie, le nombre de
groupes, le nombre de lignes absorbées et l'écart de prix maximal observé à
l'intérieur d'un groupe — ce dernier chiffre est celui qui révélerait une clé
trop lâche.

L'`id` doit être **stable entre deux exécutions et entre deux machines** :
sérialisation JSON triée par clé, `separators=(",", ":")`, `ensure_ascii=False`,
encodage UTF-8 explicite, `Decimal` sérialisés en chaînes. Un test rejoue le
calcul et vérifie l'égalité.

### Sélection — ~170 par catégorie

Déciles de prix calculés **par catégorie** sur les produits dédupliqués, quota
égal par décile, report des strates déficitaires sur les voisines pour atteindre
la cible. Graine constante. Deux exécutions donnent le même seed, au bit près.

**Garanties de cas limites.** L'étape 6 aura besoin de cas précis, et
`PROJET.md` demande de les prévoir dès maintenant. Ils sont **repêchés parmi
des produits réels**, jamais fabriqués — inventer un produit pour faire passer
un test futur violerait §2 dans le fichier même qui sert de catalogue.
Après tirage, un contrôle vérifie et complète :

- **G1 — budget frôlé** : pour chaque catégorie, au moins un produit dont le
  prix tombe dans `]seuil, seuil × 1,15]` pour un seuil rond plausible de la
  catégorie (100, 300, 500, 1 000 USD selon la médiane). C'est la zone de
  tolérance de §3.10 qui s'y exercera.
- **G2 — départage** : au moins un couple de produits de la même catégorie dont
  toutes les specs `filtre dur` sont identiques et qui ne diffèrent que par le
  prix et un champ `affichage`. C'est le cas « deux produits quasi identiques ».
- **G3 — zéro résultat** : au moins une combinaison de filtres durs plausible
  qui ne rend **aucun** produit du seed. Elle n'ajoute rien : elle se **constate**
  et s'écrit dans le rapport, avec la combinaison exacte.

Le rapport nomme les `id` qui satisfont G1 et G2 et la combinaison de G3. Ce
sont eux que les tests de l'étape 6 citeront ; s'ils changent, un test cassera,
ce qui est le comportement souhaité.

### Sorties

- `data/seed/produits.jsonl` — un `ProduitEnBase` sérialisé par ligne, trié par
  `id` pour que le diff git reste lisible. `nom_fr` et `description` à `null` à
  ce stade.
- `data/seed/rapport_seed.md` — committé lui aussi, c'est un livrable de
  l'étape : entonnoir ligne à ligne (lues → à prix → normalisées → dédupliquées
  → validées → sélectionnées), motifs de rejet avec effectifs, **taux de
  remplissage par attribut et par catégorie sur le seed final**, distribution de
  prix (min / médiane / max), marques par volume, valeurs distinctes des
  énumérations normalisées, contrôle `price_per_gb`, cas limites G1–G3.
- Ajoute `!data/seed/` aux exceptions de `.gitignore` si nécessaire — vérifie
  que le JSONL est bien suivi par git, la règle `data/raw/*` existante rend
  l'erreur facile.

## B. Passe LLM réduite

Modèle : `settings.model_extraction` (Haiku), `temperature=0`. Sortie
structurée par **tool use**, jamais par parsing de texte libre.

Deux champs produits, et deux seulement (§3.4ter) : `nom_fr` (traduction du nom
court) et `resume_usage` (usage en français, court, du type « bureautique et
multi-écrans »). Le prix, la marque, la référence constructeur et toute valeur
d'attribut restent intacts et **ne sont pas envoyés au modèle pour être
réécrits**.

Le prompt vit dans `prompts/traduction_catalogue.v1.md` (§3.14), chargé au
runtime, sa version loguée à chaque appel.

**Appels par lots de 20 produits**, avec un outil rendant une liste d'objets
`{id, nom_fr, resume_usage}`. Vérification d'appariement **stricte** : tout `id`
inconnu, manquant ou dupliqué dans la réponse invalide le lot entier, qui est
alors rejoué produit par produit. C'est la seule défense contre le décalage
d'indices, qui produirait des noms français attribués au mauvais produit — une
invention silencieuse, donc le pire mode d'échec possible ici.

**Validation programmatique de chaque sortie, avant écriture dans le cache :**

- `nom_fr` non vide, ≤ 80 caractères ;
- `nom_fr` **contient la marque à l'identique** ;
- tout jeton alphanumérique du nom source contenant un chiffre (`9800X3D`,
  `RTX`, `990`, `M.2-2280`) se retrouve **tel quel** dans `nom_fr` — c'est le
  test qui garantit qu'aucune référence constructeur n'a été traduite,
  arrondie ou inventée ;
- `resume_usage` non vide, ≤ 120 caractères, sans symbole monétaire (`$`, `€`,
  `USD`) ni mot « prix » ;
- tout nombre apparaissant dans `resume_usage` doit exister dans le nom source
  ou dans une valeur de `specs` du produit.

Une sortie qui échoue à un de ces contrôles est **rejetée** : le produit garde
`nom_fr = null` et `description = null`, et le rapport compte le rejet avec son
motif. Une deuxième tentative maximum, puis on laisse à `null`. Un catalogue
partiellement traduit est un défaut visible ; un nom faux est une invention.

**Cache** : `data/seed/traductions.json`, committé, indexé par `id`, valeur
`{nom_fr, resume_usage, modele, version_prompt, genere_le}`. Seuls les `id`
absents appellent l'API. Un `id` présent dans le cache mais absent du seed est
signalé, pas supprimé automatiquement.

**Relecture par échantillon** (garde-fou 1 de §3.4ter) : la passe écrit
`data/seed/echantillon_relecture.md`, 10 produits par catégorie tirés à graine
fixe, avec nom source, `nom_fr`, `resume_usage` et les specs — pour que la
relecture humaine soit possible sans ouvrir un JSON de 1 000 lignes.

## C. Chargement

`make seed` : lit le JSONL, fusionne le cache de traductions, **revalide chaque
ligne par `ProduitEnBase`**, insère via `Produit.depuis_schema()` dans une seule
transaction. Le fichier committé n'est pas digne de confiance du seul fait
d'être committé — c'est la même raison qui a fait de `ProduitEnBase` la porte
d'entrée unique.

Idempotent : `DELETE FROM produits` puis insertion, dans la même transaction. Le
catalogue est un instantané, pas un flux (§3.4) ; aucune clé étrangère n'y pend
aujourd'hui. Écris cette raison en commentaire — elle cessera d'être vraie le
jour où une table référencera `produits`.

Aucun appel API dans cette cible. Si la base est injoignable, message explicite
renvoyant à `make up`.

## Organisation du code

Dans `src/raiyon/catalogue/` :

- `normalisation.py` — les fonctions pures, une par transformation ;
- `identite.py` — clé canonique, `id`, déduplication ;
- `selection.py` — strates, tirage, garanties G1–G3 ;
- `pipeline.py` — orchestration de la passe A, rapport ;
- `traduction.py` — passe B, client Anthropic **injecté en paramètre** (c'est ce
  qui rend la passe testable sans clé API) ;
- `chargement.py` — passe C.

Points d'entrée en scripts fins sous `scripts/`, qui ne portent que le parsing
d'arguments et l'appel. La logique n'y vit pas.

`Makefile` : `seed-build` (passe A, exige `data/raw/`), `seed-llm` (passe B,
consomme la clé API, incrémentale), `seed` (passe C, aucune API). `check` reste
inchangé et ne doit toujours exiger ni base ni clé.

## Tests

**Unitaires, sans base ni clé API, dans `make check`** :

- `type` : `"SSD"` → SSD sans `rpm` ; `7200` → HDD avec `rpm=7200` ; absent →
  ligne écartée avec le bon motif ; forme inattendue → échec bruyant.
- `form_factor` : `2.5` → `2.5"` ; `3.5` → `3.5"` ; `"M.2-2280"` inchangé.
- `memory` : `speed`/`modules` éclatés, `capacite_totale_gb` cohérente.
- **`headphones`** : `[15, 25]` → `(15, 25)` ; **`[100, 10]` → `(100, 10)`, sans
  échange** — nomme ce test d'après le piège d'unité qu'il garde ; une valeur
  hors plage de contrôle → échec bruyant.
- `marque` : premier mot ; nom d'un seul mot ; une entrée de la table
  multi-mots ; un nom absent de la table → premier mot, sans invention.
- Déduplication : deux `cpu` identiques à prix différents → un produit, le prix
  le plus bas, le même `id` ; deux `memory` ne différant que par la couleur →
  deux produits ; `id` **stable** entre deux calculs.
- `price_per_gb` recalculé sur le prix retenu, **pas hérité** du doublon écarté
  — c'est le test qui garde l'arbitrage D ; écris-le explicitement.
- Sélection : reproductible à graine fixe ; couvre les déciles ; G1 et G2
  satisfaites sur un catalogue de test.
- Traduction, avec un faux client : lot bien apparié → accepté ; lot avec un
  `id` inconnu → rejeté et rejoué unitairement ; `nom_fr` perdant la référence
  `9800X3D` → rejeté ; `resume_usage` contenant un prix → rejeté ; cache déjà
  rempli → **zéro appel** (assertion sur le nombre d'appels du faux client).
- Isolation : `import raiyon.catalogue.pipeline` ne charge pas le SDK Anthropic
  (arbitrage B).
- **Sur le seed committé lui-même** : chaque ligne du JSONL revalide par
  `ProduitEnBase`, les `id` sont uniques et bien formés, les 6 catégories sont
  présentes, le volume est dans `[900, 1100]`. C'est le test anti-régression du
  livrable ; il tourne sans base et sans clé.

**Intégration, marqueur `integration`** : `make seed` charge le seed complet, un
produit relu depuis la base rend ses `Decimal` et ses clés de `specs` à
l'identique, et une seconde exécution laisse la table dans le même état
(idempotence).

## `PROJET.md`

Marque l'étape 5 ✅ et ajoute, dans la forme des étapes précédentes :

- **ce que l'étape a tranché** : arbitrages A à G ci-dessus, chacun avec
  **l'alternative écartée et son motif** ;
- une décision numérotée **3.1bis — sélection des ~1 000 produits**, qui énonce
  l'échantillonnage stratifié, la graine fixe, et **le biais assumé** : le seed
  n'est pas la source, les taux de remplissage y diffèrent légèrement, et toute
  statistique produite ensuite porte sur le seed ;
- un amendement à **3.4ter** : le cache committé, les cinq contrôles
  programmatiques de sortie, et le fait qu'un rejet laisse `null` plutôt que de
  produire un à-peu-près ;
- **ce que l'étape a appris et qui n'était pas prévu** — il y en aura : les
  marques en plusieurs mots, l'écart entre `price_per_gb` source et recalculé,
  et le nombre réel de lignes écartées sont trois endroits où la mesure va
  contredire une attente. Écris-les, avec les chiffres.

Mets à jour la ligne de statut en tête de fichier. `README.md` : les trois
cibles `seed-build` / `seed-llm` / `seed`, et l'attribution de la source telle
qu'elle est rédigée dans `data/raw/SOURCE.md`.

## Porte de sortie

`make check` vert, `make test-int` vert, `make seed` remplissant la base avec
~1 000 produits validés, et `data/seed/rapport_seed.md` lisible. Aucun produit
en base n'a d'attribut hors de sa plage déclarée.

Montre-moi le rapport et le diff. **N'enchaîne pas sur l'étape 6.**

## Style

Le dépôt est en français : noms de fonctions, docstrings et commentaires. Les
commentaires expliquent **pourquoi**, pas quoi. `ruff` avec `ANN` sur `src/`,
`mypy --strict` avec le plugin Pydantic, 100 colonnes. `src/raiyon/config.py` et
`src/raiyon/catalogue/schemas.py` donnent le niveau de commentaire attendu.

Si un point de ce prompt te paraît faux, contradictoire avec `PROJET.md`, ou
infaisable, **arrête-toi et dis-le** avant d'écrire le code.
