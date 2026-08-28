# Schéma d'attributs — étape 3

Ce document traduit les mesures de [`rapport_exploration.md`](rapport_exploration.md)
en décisions de modélisation. Il est à valider **avant** d'écrire la moindre ligne
de pipeline (étape 5) ou de modèle SQL (étape 4).

## Convention de lecture

Les trois rôles sont exclusifs et définis une fois pour toutes :

| rôle | définition | conséquence technique |
| --- | --- | --- |
| `filtre dur` | critère bloquant, traduisible en `WHERE` SQL | un produit qui ne le satisfait pas ne remonte **jamais** |
| `score` | critère souple, produit un sous-score 0-1 | pondère le classement, n'exclut rien |
| `affichage` | montré au client | **n'entre jamais** dans le matching |

Un attribut est dit **discriminant** s'il porte un rôle `filtre dur` ou `score`.
Un attribut `affichage` ne compte pas dans la porte de sortie.

**Taux de remplissage : mesurés sur les produits ayant un prix**, jamais sur le
fichier entier. Un produit sans prix n'entre pas dans un moteur à contrainte
budgétaire ; le compter au dénominateur donnerait une image fausse.

**Décompte conservateur.** Un champ source qui se décompose en plusieurs colonnes
cibles (`resolution`, `speed`, `modules`, `frequency_response`) est compté pour
**un seul** attribut, pas pour deux. La porte de sortie n'est donc jamais franchie
par un artefact de découpage.

## Colonnes communes à toutes les catégories

Conformément à la décision 3.3 (colonnes typées + `specs` en JSONB) :

| champ | type source | type cible | unité | plage observée | rôle |
| --- | --- | --- | --- | --- | --- |
| `name` | `string` | `text` | — | 9 687 lignes / 5 390 noms distincts | `affichage` |
| `price` | `number` | `numeric(10,2)` | USD | 5,00 – 9 333,00 | `filtre dur` |
| *(catégorie)* | dérivé du fichier source | `text` (énum. 7 valeurs) | — | 7 valeurs | `filtre dur` |

- **`price` en `filtre dur`** : c'est la contrainte budgétaire, l'invariant central du
  produit (3.10) ; un produit hors budget ne doit pas pouvoir être recommandé.
- **catégorie en `filtre dur`** : on ne propose pas un clavier à qui demande un écran.

⚠️ **`name` n'est pas une clé.** 5 390 noms distincts pour 9 687 produits à prix :
`Corsair Vengeance RGB 32 GB` désigne quatre entrées de couleurs, fréquences et
latences différentes. Il faut une **clé de substitution** (`id` généré) — le
détail est en fin de document, § « Points à trancher ».

---

## `cpu`

547 produits à prix sur 1 413. Prix 12,99 – 2 699,99 USD (médiane 169,89).

| champ | type source | type cible | unité | plage observée | rôle |
| --- | --- | --- | --- | --- | --- |
| `core_count` | `number` | `int` | cœurs | 1 – 64 (méd. 4) — **100 %** | `filtre dur` |
| `core_clock` | `number` | `numeric(4,2)` | GHz | 1,60 – 4,70 (méd. 3,30) — **100 %** | `score` |
| `tdp` | `number` | `int` | W | 35 – 280 (méd. 72) — **100 %** | `filtre dur` |
| `microarchitecture` | `string` | `text` (énum. 33) | — | `Kaby Lake` … `Zen 5` — **100 %** | `filtre dur` |
| `boost_clock` | `number` | `numeric(4,2)` | GHz | 2,30 – 6,20 — **65,1 %** ❌ | `score` |
| `graphics` | `string` | `text` (énum. 35) | — | 35 valeurs — **51,6 %** ❌ | `score` |
| `smt` | **absent du fichier** | — | — | — | — |

**Justification des `filtre dur`**
- `core_count` : « il me faut au moins 8 cœurs pour du montage vidéo » est une
  exigence de capacité, pas une préférence — un 4 cœurs ne fait pas l'affaire à
  moitié.
- `tdp` : borne physique, pas de confort — un TDP de 170 W dans un boîtier
  mini-ITX refroidi passivement ne fonctionne pas, quel que soit le reste.
- `microarchitecture` : seul vecteur de la marque et de la génération dans le
  fichier ; « je veux du AMD Zen 4 » est une contrainte de compatibilité (socket,
  chipset) que le moteur doit traiter comme bloquante.

**Ce que la mesure a démenti**
- `API.md` promet `smt` : le champ **n'existe dans aucun des 1 413 enregistrements**.
  Le décompte de 7 attributs en 3.4bis reposait sur la documentation, pas sur les
  données.
- `boost_clock` manque sur 191 des 547 processeurs à prix, tous anciens
  (Pentium E5700, Core i7-3770, Core i3-6100…). L'absence est corrélée à la
  génération, elle n'est pas aléatoire.

> **FERMÉE : 4 attributs discriminants ≥ 80 % de remplissage** (`core_count`,
> `core_clock`, `tdp`, `microarchitecture`), il en faut 5.
> Manquent : `boost_clock` (65,1 %, soit 15 points sous le seuil), `graphics`
> (51,6 %) et `smt` (champ inexistant). Aucun autre champ n'est disponible dans
> la source pour combler l'écart.

---

## `monitor`

1 367 produits à prix sur 5 074. Prix 55,00 – 9 333,00 USD (médiane 289,99).

| champ | type source | type cible | unité | plage observée | rôle |
| --- | --- | --- | --- | --- | --- |
| `screen_size` | `number` | `numeric(4,1)` | pouces | 14 – 65 (méd. 27) — **100 %** | `filtre dur` |
| `resolution` | `[number, number]` | 2 colonnes `int` (`largeur_px`, `hauteur_px`) | pixels | 1024×768 – 7680×4320 — **100 %** | `filtre dur` |
| `aspect_ratio` | `string` | `text` (énum. 11) | — | `16:9` 83,5 % … `32:9` — **100 %** | `filtre dur` |
| `panel_type` | `string` | `text` (énum. 13) | — | `IPS` 61,2 %, `VA` 24,0 %, `TN` 6,3 % — **96,5 %** | `score` |
| `refresh_rate` | `number` | `int` | Hz | 60 – 600 (méd. 100) — **95,2 %** | `filtre dur` |
| `response_time` | `number` | `numeric(4,2)` | ms | 0,01 – 20 (méd. 4) — **78,3 %** ❌ | `score` |

**Justification des `filtre dur`**
- `screen_size` : « 27 pouces minimum » est une contrainte d'encombrement et de
  confort visuel, vérifiable et binaire.
- `resolution` : « du 4K » désigne un seuil exact (3840×2160) ; proposer du 1440p
  à qui demande du 4K est un échec, pas une approximation.
- `aspect_ratio` : « un ultrawide » sépare `21:9`/`32:9` (11 % du catalogue) du
  reste — c'est un choix de format, il n'existe pas d'ultrawide partiel.
- `refresh_rate` : « 144 Hz minimum » pour du jeu compétitif est une exigence
  chiffrée ; un 60 Hz n'y répond pas à 40 %.

**Réserves à porter au dossier**
- `aspect_ratio` est **très concentré** : 83,5 % de `16:9`. Il ne discrimine
  réellement que la minorité ultrawide. Il reste un filtre dur légitime, mais son
  pouvoir de tri est faible sur la majorité des requêtes.
- `response_time` descend à 0,01 ms (Acer Predator X39, dalle OLED). Valeur
  constructeur, pas une mesure ; à afficher telle quelle, sans la retraiter.

> **OUVERTE : 5 attributs discriminants ≥ 80 % de remplissage** (`screen_size`,
> `resolution`, `aspect_ratio`, `panel_type`, `refresh_rate`).
> Marge nulle : `response_time` est à 78,3 %, soit 1,7 point sous le seuil.

---

## `internal-hard-drive`

2 103 produits à prix sur 6 461. Prix 10,99 – 4 777,83 USD (médiane 126,97).

| champ | type source | type cible | unité | plage observée | rôle |
| --- | --- | --- | --- | --- | --- |
| `capacity` | `number` | `int` | GB | 32 – 26 000 (méd. 1 000) — **100 %** | `filtre dur` |
| `type` | `string \| number` ⚠️ | `text` (énum. `SSD`/`HDD`) + `rpm int` nullable | RPM si HDD | `SSD` 66,7 % ; 5 400 / 7 200 / 15 000 RPM 33,3 % — **99,6 %** | `filtre dur` |
| `form_factor` | `number \| string` ⚠️ | `text` (énum. normalisée) | pouces ou format M.2 | `M.2-2280` 39,1 %, `2.5` 28,8 %, `3.5` 27,1 % — **100 %** | `filtre dur` |
| `interface` | `string` | `text` (énum. 18) | — | `SATA 6.0 Gb/s` 44,8 %, `M.2 PCIe 4.0 X4` 23,1 % — **100 %** | `filtre dur` |
| `price_per_gb` | `number` | `numeric(6,3)` | USD/GB | 0,015 – 4,530 (méd. 0,087) — **97,4 %** | `score` |
| `cache` | `number` | `int` | MB | 8 – 8 192 — **36,5 %** ❌ | `score` |

**Justification des `filtre dur`**
- `capacity` : « au moins 2 To » est une exigence de volume, sans substitut partiel.
- `type` : la distinction SSD / HDD est le premier arbitrage du domaine ; proposer
  un disque à plateaux 5 400 tr/min à qui demande un SSD est un contresens, pas un
  compromis.
- `form_factor` : contrainte de compatibilité physique — un 3,5″ n'entre pas dans
  un portable, un M.2-22110 n'entre pas dans un emplacement 2280.
- `interface` : contrainte de compatibilité carte mère — un disque M.2 PCIe 5.0
  ne se branche pas sur un port SATA.

**Champs à type hétérogène — la normalisation à écrire**
- `type` : `"SSD"` (1 398) ou un entier de tours/minute (697). Deux colonnes cibles :
  `type` ∈ {`SSD`, `HDD`} et `rpm` nullable, renseigné seulement pour les HDD.
- `form_factor` : `2.5` / `3.5` en nombre (1 176) ou `"M.2-2280"`, `"mSATA"`,
  `"PCIe"` en chaîne (927). Cible : une seule énumération textuelle où les nombres
  deviennent `2.5"` et `3.5"`.
- Ces deux champs et `interface` sont **fortement corrélés** (`SSD`+`M.2-2280` =
  823 lignes, `7200`+`3.5` = 413) : ils comptent chacun pour un attribut dans la
  porte de sortie, mais apportent moins d'information indépendante que leur nombre
  ne le suggère.
- `price_per_gb` est **dérivable** de `price` et `capacity`. Il est conservé comme
  `score` parce que c'est un critère de décision réel (« le meilleur rapport
  capacité/prix »), pas parce qu'il ajoute de l'information.

> **OUVERTE : 5 attributs discriminants ≥ 80 % de remplissage** (`capacity`,
> `type`, `form_factor`, `interface`, `price_per_gb`).
> `cache` est écarté (36,5 %). Réserve explicite : sans `price_per_gb`, qui est
> une grandeur dérivée, il n'en resterait que 4.

---

## `memory`

2 907 produits à prix sur 13 553. Prix 5,00 – 3 737,49 USD (médiane 100,27).

| champ | type source | type cible | unité | plage observée | rôle |
| --- | --- | --- | --- | --- | --- |
| `speed` | `[number, number]` | 2 colonnes : `ddr_generation int`, `frequence_mhz int` | — / MHz | DDR2 – DDR5 ; 400 – 8 400 MHz (méd. 3 600) — **100 %** | `filtre dur` |
| `modules` | `[number, number]` | 2 colonnes : `nb_modules int`, `taille_module_gb int` (+ `capacite_totale_gb` dérivée) | — / GB | 1 – 8 modules ; 1 – 64 GB par module — **100 %** | `filtre dur` |
| `cas_latency` | `number` | `int` | cycles | 3 – 52 (méd. 19) — **100 %** | `score` |
| `first_word_latency` | `number` | `numeric(6,3)` | ns | 7,368 – 19,167 (méd. 12) — **100 %** | `score` |
| `price_per_gb` | `number` | `numeric(7,3)` | USD/GB | 1,059 – 497,500 (méd. 4,062) — **98,1 %** | `score` |
| `color` | `string` | `text` (énum. 38) | — | `Black` 38,0 % — **94,4 %** | `affichage` |

**Justification des `filtre dur`**
- `speed` → `ddr_generation` : compatibilité carte mère absolue — de la DDR4 ne
  s'insère pas physiquement dans un socket DDR5. C'est le filtre dur le plus net
  de tout le catalogue.
- `modules` → `capacite_totale_gb` : « il me faut 32 Go » est une exigence de
  volume ; le nombre de barrettes est en outre bloquant lorsque le client précise
  le nombre d'emplacements libres.

**Remarques**
- `speed[0]` code la génération DDR (2 à 5), `speed[1]` la fréquence en MHz. La
  colonne `frequence_mhz` seule est un `score` (plus haut vaut mieux) ; c'est la
  génération qui est bloquante.
- `price_per_gb` monte à 497,5 USD/GB : valeur extrême sur des modules de très
  faible capacité. À conserver telle quelle, mais le sous-score doit être borné
  pour qu'une valeur aberrante n'écrase pas le classement.
- `color` reste en `affichage` conformément à 3.4bis, malgré ses 94,4 %.

> **OUVERTE : 5 attributs discriminants ≥ 80 % de remplissage** (`speed`,
> `modules`, `cas_latency`, `first_word_latency`, `price_per_gb`).
> C'est la catégorie la plus solide : les quatre premiers sont à 100 %, et le
> décompte conservateur sous-évalue le résultat — après décomposition des deux
> champs-listes, sept colonnes exploitables sont disponibles.

---

## `video-card`

1 275 produits à prix sur 6 636. Prix 45,99 – 7 516,34 USD (médiane 595,35).

| champ | type source | type cible | unité | plage observée | rôle |
| --- | --- | --- | --- | --- | --- |
| `chipset` | `string` | `text` (énum. 241) | — | `GeForce RTX 5060 Ti` … `Radeon RX 9070 XT` — **100 %** | `filtre dur` |
| `memory` | `number` | `numeric(4,2)` | GB (VRAM) | 0,25 – 48 (méd. 8) — **100 %** | `filtre dur` |
| `length` | `number` | `int` | mm | 115 – 360 (méd. 279) — **97,5 %** | `filtre dur` |
| `core_clock` | `number` | `int` | MHz | 115 – 2 740 (méd. 1 626) — **98,4 %** | `score` |
| `boost_clock` | `number` | `int` | MHz | 876 – 3 320 (méd. 2 190) — **80,3 %** ⚠️ | `score` |
| `color` | `string` | `text` (énum. 44) | — | `Black` 46,7 % — **98,5 %** | `affichage` |

**Justification des `filtre dur`**
- `chipset` : c'est l'identité du produit ; « une RTX 4070 » ne se satisfait pas
  d'une RTX 3060, même à prix égal.
- `memory` : « 12 Go de VRAM minimum » est un seuil technique dur pour du jeu en
  4K ou de l'inférence locale — en dessous, le cas d'usage ne fonctionne pas.
- `length` : contrainte physique de boîtier, mesurée en millimètres ; une carte de
  360 mm n'entre pas dans un châssis qui en accepte 300.

**Réserve sérieuse**
`boost_clock` est à **80,3 %**, soit 0,3 point au-dessus du seuil — 4 produits de
plus sans la valeur et la catégorie basculait. Ce n'est pas une marge, c'est une
coïncidence. Si `boost_clock` était écarté, il resterait 4 attributs et la
catégorie serait FERMÉE.

> **OUVERTE : 5 attributs discriminants ≥ 80 % de remplissage** (`chipset`,
> `memory`, `length`, `core_clock`, `boost_clock`).
> Ouverture au dernier attribut, avec 0,3 point de marge sur `boost_clock`.

---

## `headphones`

664 produits à prix sur 2 946. Prix 5,99 – 5 999,00 USD (médiane 89,99).

| champ | type source | type cible | unité | plage observée | rôle |
| --- | --- | --- | --- | --- | --- |
| `type` | `string` | `text` (énum. 4) | — | `Circumaural` 72,9 %, `Supra-aural` 10,5 %, `In Ear` 9,0 %, `Earbud` 7,5 % — **100 %** | `filtre dur` |
| `microphone` | `bool` | `boolean` | — | `true` 71,1 % — **100 %** | `filtre dur` |
| `wireless` | `bool` | `boolean` | — | `true` 32,2 % — **100 %** | `filtre dur` |
| `enclosure_type` | `string` | `text` (énum. 3) | — | `Closed` 90,1 %, `Open` 8,3 %, `Semi-open` 1,7 % — **100 %** | `filtre dur` |
| `frequency_response` | `[number, number]` ⚠️ | 2 colonnes : `freq_min_hz int`, `freq_max_khz numeric(4,1)` | Hz / kHz ⚠️ | 4 – 150 Hz ; 2 – 75 kHz — **83,7 %** | `score` |
| `color` | `string` | `text` (énum. 63) | — | `Black` 38,2 % — **98,6 %** | `affichage` |

**Justification des `filtre dur`**
- `type` : « des intra-auriculaires pour courir » exclut les circum-auraux par
  nature, pas par degré.
- `microphone` : « avec micro pour mes réunions » est binaire — un casque sans
  micro ne répond pas partiellement au besoin.
- `wireless` : filaire ou sans fil est un choix d'usage tranché, sans milieu.
- `enclosure_type` : « ouvert » et « fermé » désignent des usages opposés (isolation
  en open space contre scène sonore) ; c'est le seul champ qui les sépare.

**Piège d'unité — le champ le plus dangereux du dataset**
`API.md` annonce `frequency_response` en kHz pour ses deux composantes. **C'est faux
pour la première.** `["HP HyperX Cloud II", [15, 25]]` se lit 15 **Hz** – 25 **kHz**.
Les 32 cas où `fr[0] > fr[1]` s'expliquent tous par ce mélange (`[100, 10]` =
100 Hz – 10 kHz sur un casque de communication MSI, `[150, 6.8]` = 150 Hz –
6,8 kHz sur un Sennheiser SC260). Il n'y a **aucune inversion réelle** : appliquer
un `min/max` correctif détruirait la donnée. Les deux composantes doivent partir
dans deux colonnes d'unités différentes, et cela doit être couvert par un test.

**Réserve**
`enclosure_type` est concentré à 90,1 % sur `Closed`. Il est rempli à 100 % et
répond à une question client réelle, mais il ne trie que 10 % du catalogue.

> **OUVERTE : 5 attributs discriminants ≥ 80 % de remplissage** (`type`,
> `microphone`, `wireless`, `enclosure_type`, `frequency_response`).
> Les quatre premiers sont à 100 % ; `frequency_response` à 83,7 % apporte
> 3,7 points de marge.

---

## `keyboard`

824 produits à prix sur 4 310. Prix 10,77 – 909,36 USD (médiane 92,32).

| champ | type source | type cible | unité | plage observée | rôle |
| --- | --- | --- | --- | --- | --- |
| `style` | `string` | `text` (énum. 6) | — | `Gaming` 43,9 %, `Standard` 29,1 %, `Mini` 11,2 %, `Slim` 9,0 %, `Ergonomic` 5,8 %, `Ergonomic Split` 1,0 % — **100 %** | `filtre dur` |
| `tenkeyless` | `bool` | `boolean` | — | `true` 38,1 % — **100 %** | `filtre dur` |
| `connection_type` | `string` (multi-valué) | `text[]` (énum. 3 valeurs atomiques) | — | `Wired` 58,6 %, combinaisons 10 formes — **99,2 %** | `filtre dur` |
| `color` | `string` | `text` (énum. 45) | — | `Black` 69,3 % — **98,5 %** | `affichage` |
| `backlit` | `string` | `text` (énum. 7) | — | `RGB` 81,7 % des renseignés — **56,3 %** ❌ | `score` |
| `switches` | `string` | `text` (énum. 150) | — | `Cherry MX Blue` 4,3 % des renseignés — **54,0 %** ❌ | `filtre dur` |

**Justification des `filtre dur`**
- `style` : « un clavier ergonomique » ou « un format mini » est une contrainte de
  forme, pas une préférence graduelle.
- `tenkeyless` : avec ou sans pavé numérique — binaire, et c'est l'une des
  demandes les plus fréquentes du domaine.
- `connection_type` : « Bluetooth pour mon iPad » est une exigence de connectivité
  bloquante. ⚠️ Le champ est **multi-valué** (`"Wired, Wireless, Bluetooth Wireless"`)
  et contient des répétitions (`"Wired, Wired"`, 16 lignes) : il faut le découper en
  ensemble de valeurs atomiques (`Wired` 713, `Wireless` 266, `Bluetooth Wireless` 192),
  dédoublonné, et filtrer par appartenance.

**Ce que la mesure a démenti**
- `switches` n'est renseigné que sur **54,0 %** des claviers à prix, et sa
  cardinalité de 150 en fait de toute façon un champ difficile à filtrer sans
  table de correspondance (linéaire / tactile / clicky) que la source ne fournit pas.
- `backlit` n'est renseigné que sur **56,3 %**.
- Ces absences ne sont **pas aléatoires** : elles se concentrent sur les styles
  `Standard`, `Slim` et `Ergonomic` (claviers à membrane, non rétroéclairés).
  Un `null` y signifie vraisemblablement « membrane » et « pas de rétroéclairage »,
  mais **la source ne le dit pas** — le lire ainsi serait une interprétation, pas
  une normalisation. Voir « Points à trancher ».

> **FERMÉE : 3 attributs discriminants ≥ 80 % de remplissage** (`style`,
> `tenkeyless`, `connection_type`), il en faut 5.
> Manquent : `backlit` (56,3 %, soit 23,7 points sous le seuil) et `switches`
> (54,0 %, soit 26 points sous le seuil). `color` est à 98,5 % mais reste en
> `affichage` par la décision 3.4bis, il ne peut pas être compté.

---

## Synthèse de la porte de sortie

| catégorie | produits à prix | attributs discriminants ≥ 80 % | verdict |
| --- | --- | --- | --- |
| `memory` | 2 907 | 5 (dont 4 à 100 %) | ✅ **OUVERTE** |
| `headphones` | 664 | 5 (dont 4 à 100 %) | ✅ **OUVERTE** |
| `internal-hard-drive` | 2 103 | 5 | ✅ **OUVERTE** |
| `monitor` | 1 367 | 5 | ✅ **OUVERTE** (marge nulle) |
| `video-card` | 1 275 | 5 | ✅ **OUVERTE** (marge 0,3 pt) |
| `cpu` | 547 | 4 | ❌ **FERMÉE** |
| `keyboard` | 824 | 3 | ❌ **FERMÉE** |

**5 catégories ouvertes sur mesure brute — le plancher de l'étape 3 est atteint,
exactement.** Aucun seuil n'a été abaissé et aucune valeur n'a été complétée.

## Arbitrage rendu — verdict définitif

Les quatre points laissés ouverts par ce document ont été tranchés. Les décisions
font foi dans `PROJET.md` (3.1, 3.4bis, 3.4quater, étape 5) ; elles sont reprises
ici pour que le fichier reste lisible seul.

**1. Règle de comptage des attributs (nouvelle décision 3.4quater).**
Le verdict brut ci-dessus était incohérent : `internal-hard-drive` n'ouvrait que
grâce à `price_per_gb`, une grandeur **dérivée**, pendant que le repêchage de
`cpu` par la marque — dérivée elle aussi — était présenté comme un changement de
règle. La ligne de partage retenue n'est donc pas « source contre dérivé » mais
**calcul déterministe contre comblement d'absence** :

| Cas | Nature | Compte ? |
| --- | --- | --- |
| `price_per_gb` = `price / capacity` | fonction de deux champs renseignés | ✅ |
| `marque` = premier mot de `name` | parsing déterministe, couverture 100 % | ✅ |
| `switches = null` → « membrane » | hypothèse comblant un trou | ❌ |

**2. La marque est extraite sur toutes les catégories.** Elle n'existe nulle part
comme champ ; elle est dérivée du premier mot de `name`. C'est un `filtre dur`
que les utilisateurs expriment réellement. Chaque tableau de catégorie ci-dessus
gagne donc une ligne `marque`, à écrire lors de la normalisation (étape 5).

**3. Verdict final : 6 catégories.**

| catégorie | discriminants après 3.4quater | verdict |
| --- | --- | --- |
| `memory` | 6 | ✅ retenue |
| `internal-hard-drive` | 6 — ne dépend plus de `price_per_gb` | ✅ retenue |
| `monitor` | 6 | ✅ retenue |
| `video-card` | 6 | ✅ retenue |
| `headphones` | 6 | ✅ retenue |
| `cpu` | 5 | ✅ **repêchée** |
| `keyboard` | 4 | ❌ **retirée** |

`keyboard` est retirée en connaissance de cause : lire `switches`/`backlit = null`
comme « membrane / aucun » la sauverait et l'hypothèse est crédible, mais la
source ne le dit pas. C'est un comblement d'absence, donc refusé.

**4. Clé primaire et doublons.** Identifiant synthétique, jamais `name`. Une seule
règle de déduplication, uniforme : dédupliquer sur `(name + tous les attributs
hors prix)`, garder le prix le plus bas. Elle absorbe les 51 redondances `cpu` et
préserve les 346 variantes `memory` sans traitement particulier — la règle est la
même, seul son effet diffère selon la catégorie.

**5. Volume.** ~150-200 produits par catégorie, soit environ 1 000 au total, au
lieu des ~30 prévus au cadrage initial. À 30, un filtre dur réaliste renverrait
zéro résultat la plupart du temps : le cas d'échec deviendrait le cas courant.
