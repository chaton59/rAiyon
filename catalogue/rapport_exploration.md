# Rapport d'exploration du dataset — étape 3

Mesure brute, sans interprétation. Généré par `scripts/explore_dataset.py`.
Source : `docyx/pc-part-dataset`, commit `c52a04ca9465c83997ed335f7767b09a2005dd26`
(voir `data/raw/SOURCE.md`).

Les taux de remplissage sont calculés **sur les produits ayant un prix**, pas sur
le fichier entier : un produit sans prix ne peut pas entrer dans un moteur à
contrainte budgétaire.

## Vue d'ensemble

| catégorie | produits | avec prix | part exploitable |
| --- | --- | --- | --- |
| `cpu` | 1413 | 547 | 38.7 % |
| `monitor` | 5074 | 1367 | 26.9 % |
| `internal-hard-drive` | 6461 | 2103 | 32.5 % |
| `memory` | 13553 | 2907 | 21.4 % |
| `video-card` | 6636 | 1275 | 19.2 % |
| `headphones` | 2946 | 664 | 22.5 % |
| `keyboard` | 4310 | 824 | 19.1 % |
| **total** | **40393** | **9687** | **24.0 %** |

## `cpu`

- Produits au total : **1413**
- Produits avec un `price` non nul : **547** (38.7 % du fichier) — c'est la base de toutes les mesures qui suivent
- Champs présents dans le fichier : `name`, `price`, `core_count`, `core_clock`, `boost_clock`, `microarchitecture`, `tdp`, `graphics`
- ⚠️ Champs annoncés par `API.md` et **absents du fichier** : `smt`
- Noms distincts : **492** — 51 noms portés par plusieurs entrées, dont **51** où les attributs hors prix sont strictement identiques (le reste sont des variantes réelles)

### Distribution des prix (USD, snapshot juillet 2025)

| min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- |
| 12.99 | 94.34 | 169.89 | 307.77 | 2699.99 |

| seuil | produits en dessous | part |
| --- | --- | --- |
| < 100 USD | 165 | 30.2 % |
| < 200 USD | 325 | 59.4 % |
| < 300 USD | 407 | 74.4 % |
| < 500 USD | 496 | 90.7 % |
| < 1000 USD | 532 | 97.3 % |

### Taux de remplissage (sur les produits à prix)

| attribut | renseignés | taux | types rencontrés |
| --- | --- | --- | --- |
| `core_count` | 547 | **100.0 %** | `number` (547) |
| `core_clock` | 547 | **100.0 %** | `number` (547) |
| `microarchitecture` | 547 | **100.0 %** | `string` (547) |
| `tdp` | 547 | **100.0 %** | `number` (547) |
| `boost_clock` | 356 | **65.1 %** | `number` (356) |
| `graphics` | 282 | **51.6 %** | `string` (282) |

### Attributs numériques

| attribut | n | min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- | --- | --- |
| `core_count` | 547 | 1 | 4 | 4 | 8 | 64 |
| `core_clock` | 547 | 1.6 | 2.865 | 3.3 | 3.6 | 4.7 |
| `boost_clock` | 356 | 2.3 | 3.9 | 4.4 | 4.9 | 6.2 |
| `tdp` | 547 | 35 | 65 | 72 | 105 | 280 |

### Attributs énumérables — cardinalité et 10 valeurs les plus fréquentes

**`microarchitecture`** — cardinalité **33** sur 547 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `Kaby Lake` | 42 | 7.7 % |
| `Sandy Bridge` | 36 | 6.6 % |
| `Skylake` | 35 | 6.4 % |
| `Haswell` | 34 | 6.2 % |
| `Coffee Lake` | 29 | 5.3 % |
| `Coffee Lake Refresh` | 27 | 4.9 % |
| `Ivy Bridge` | 27 | 4.9 % |
| `Comet Lake` | 24 | 4.4 % |
| `Zen 4` | 22 | 4.0 % |
| `Alder Lake` | 19 | 3.5 % |

**`graphics`** — cardinalité **35** sur 282 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `Intel UHD Graphics 630` | 43 | 15.2 % |
| `Radeon` | 25 | 8.9 % |
| `Intel HD Graphics 630` | 23 | 8.2 % |
| `Intel HD Graphics` | 23 | 8.2 % |
| `Intel UHD Graphics 770` | 22 | 7.8 % |
| `Intel HD Graphics 4600` | 17 | 6.0 % |
| `Intel HD Graphics 530` | 13 | 4.6 % |
| `Intel UHD Graphics 610` | 12 | 4.3 % |
| `Intel HD Graphics P630` | 11 | 3.9 % |
| `Intel HD Graphics 2500` | 10 | 3.5 % |


## `monitor`

- Produits au total : **5074**
- Produits avec un `price` non nul : **1367** (26.9 % du fichier) — c'est la base de toutes les mesures qui suivent
- Champs présents dans le fichier : `name`, `price`, `screen_size`, `resolution`, `refresh_rate`, `response_time`, `panel_type`, `aspect_ratio`
- Noms distincts : **1306** — 39 noms portés par plusieurs entrées, dont **16** où les attributs hors prix sont strictement identiques (le reste sont des variantes réelles)

### Distribution des prix (USD, snapshot juillet 2025)

| min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- |
| 55.00 | 189.64 | 289.99 | 499.99 | 9333.00 |

| seuil | produits en dessous | part |
| --- | --- | --- |
| < 100 USD | 50 | 3.7 % |
| < 200 USD | 414 | 30.3 % |
| < 300 USD | 739 | 54.1 % |
| < 500 USD | 1029 | 75.3 % |
| < 1000 USD | 1260 | 92.2 % |

### Taux de remplissage (sur les produits à prix)

| attribut | renseignés | taux | types rencontrés |
| --- | --- | --- | --- |
| `screen_size` | 1367 | **100.0 %** | `number` (1367) |
| `resolution` | 1367 | **100.0 %** | `[number]` (1367) |
| `aspect_ratio` | 1367 | **100.0 %** | `string` (1367) |
| `panel_type` | 1319 | **96.5 %** | `string` (1319) |
| `refresh_rate` | 1301 | **95.2 %** | `number` (1301) |
| `response_time` | 1070 | **78.3 %** | `number` (1070) |

### Attributs numériques

| attribut | n | min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- | --- | --- |
| `screen_size` | 1367 | 14 | 24 | 27 | 31.5 | 65 |
| `resolution[0]` | 1367 | 1 024 | 1 920 | 2 560 | 3 440 | 7 680 |
| `resolution[1]` | 1367 | 768 | 1 080 | 1 200 | 1 440 | 4 320 |
| `refresh_rate` | 1301 | 60 | 60 | 100 | 165 | 600 |
| `response_time` | 1070 | 0.01 | 1 | 4 | 5 | 20 |

### Attributs énumérables — cardinalité et 10 valeurs les plus fréquentes

**`resolution`** — cardinalité **24** sur 1367 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `[1920, 1080]` | 597 | 43.7 % |
| `[2560, 1440]` | 294 | 21.5 % |
| `[3840, 2160]` | 229 | 16.8 % |
| `[3440, 1440]` | 102 | 7.5 % |
| `[1280, 1024]` | 25 | 1.8 % |
| `[5120, 1440]` | 24 | 1.8 % |
| `[2560, 1080]` | 21 | 1.5 % |
| `[1920, 1200]` | 19 | 1.4 % |
| `[1600, 900]` | 12 | 0.9 % |
| `[3840, 1600]` | 12 | 0.9 % |

**`panel_type`** — cardinalité **13** sur 1319 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `IPS` | 807 | 61.2 % |
| `VA` | 317 | 24.0 % |
| `TN` | 83 | 6.3 % |
| `QD-OLED` | 49 | 3.7 % |
| `OLED` | 33 | 2.5 % |
| `Mini LED IPS` | 6 | 0.5 % |
| `Nano IPS` | 6 | 0.5 % |
| `WOLED` | 5 | 0.4 % |
| `PLS` | 5 | 0.4 % |
| `Mini LED VA` | 4 | 0.3 % |

**`aspect_ratio`** — cardinalité **11** sur 1367 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `16:9` | 1141 | 83.5 % |
| `21:9` | 123 | 9.0 % |
| `32:9` | 26 | 1.9 % |
| `16:10` | 26 | 1.9 % |
| `5:4` | 25 | 1.8 % |
| `12:5` | 12 | 0.9 % |
| `64:27` | 7 | 0.5 % |
| `4:3` | 3 | 0.2 % |
| `8:9` | 2 | 0.1 % |
| `11:6` | 1 | 0.1 % |


## `internal-hard-drive`

- Produits au total : **6461**
- Produits avec un `price` non nul : **2103** (32.5 % du fichier) — c'est la base de toutes les mesures qui suivent
- Champs présents dans le fichier : `name`, `price`, `capacity`, `price_per_gb`, `type`, `cache`, `form_factor`, `interface`
- Noms distincts : **773** — 445 noms portés par plusieurs entrées, dont **0** où les attributs hors prix sont strictement identiques (le reste sont des variantes réelles)

### Distribution des prix (USD, snapshot juillet 2025)

| min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- |
| 10.99 | 69.36 | 126.97 | 239.22 | 4777.83 |

| seuil | produits en dessous | part |
| --- | --- | --- |
| < 100 USD | 848 | 40.3 % |
| < 200 USD | 1453 | 69.1 % |
| < 300 USD | 1776 | 84.5 % |
| < 500 USD | 2014 | 95.8 % |
| < 1000 USD | 2081 | 99.0 % |

### Taux de remplissage (sur les produits à prix)

| attribut | renseignés | taux | types rencontrés |
| --- | --- | --- | --- |
| `capacity` | 2103 | **100.0 %** | `number` (2103) |
| `form_factor` | 2103 | **100.0 %** | `number` (1176), `string` (927) ⚠️ |
| `interface` | 2103 | **100.0 %** | `string` (2103) |
| `type` | 2095 | **99.6 %** | `string` (1398), `number` (697) ⚠️ |
| `price_per_gb` | 2048 | **97.4 %** | `number` (2048) |
| `cache` | 767 | **36.5 %** | `number` (767) |

**Champs à type hétérogène** (⚠️ ci-dessus) :

- `type` → `string` : 1398 (66.7 %) · `number` : 697 (33.3 %)
- `form_factor` → `number` : 1176 (55.9 %) · `string` : 927 (44.1 %)

### Attributs numériques

| attribut | n | min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- | --- | --- |
| `capacity` | 2103 | 32 | 500 | 1 000 | 3 000 | 26 000 |
| `price_per_gb` | 2048 | 0.015 | 0.053 | 0.087 | 0.151 | 4.53 |
| `type` | 697 | 5 400 | 5 400 | 7 200 | 7 200 | 15 000 |
| `cache` | 767 | 8 | 64 | 128 | 256 | 8 192 |
| `form_factor` | 1176 | 2.5 | 2.5 | 2.5 | 3.5 | 3.5 |

### Attributs énumérables — cardinalité et 10 valeurs les plus fréquentes

**`type`** — cardinalité **1** sur 2095 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `SSD` | 1398 | 66.7 % |

**`form_factor`** — cardinalité **7** sur 2103 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `M.2-2280` | 823 | 39.1 % |
| `M.2-2230` | 45 | 2.1 % |
| `M.2-2242` | 27 | 1.3 % |
| `mSATA` | 17 | 0.8 % |
| `PCIe` | 11 | 0.5 % |
| `M.2-22110` | 3 | 0.1 % |
| `M.2-2260` | 1 | 0.0 % |

**`interface`** — cardinalité **18** sur 2103 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `SATA 6.0 Gb/s` | 942 | 44.8 % |
| `M.2 PCIe 4.0 X4` | 486 | 23.1 % |
| `M.2 PCIe 3.0 X4` | 255 | 12.1 % |
| `SATA 3.0 Gb/s` | 138 | 6.6 % |
| `M.2 PCIe 5.0 X4` | 87 | 4.1 % |
| `M.2 SATA` | 64 | 3.0 % |
| `SAS 12.0 Gb/s` | 48 | 2.3 % |
| `SAS 6.0 Gb/s` | 26 | 1.2 % |
| `mSATA` | 17 | 0.8 % |
| `U.2` | 13 | 0.6 % |


## `memory`

- Produits au total : **13553**
- Produits avec un `price` non nul : **2907** (21.4 % du fichier) — c'est la base de toutes les mesures qui suivent
- Champs présents dans le fichier : `name`, `price`, `speed`, `modules`, `price_per_gb`, `color`, `first_word_latency`, `cas_latency`
- Noms distincts : **1111** — 346 noms portés par plusieurs entrées, dont **0** où les attributs hors prix sont strictement identiques (le reste sont des variantes réelles)

### Distribution des prix (USD, snapshot juillet 2025)

| min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- |
| 5.00 | 50.73 | 100.27 | 179.99 | 3737.49 |

| seuil | produits en dessous | part |
| --- | --- | --- |
| < 100 USD | 1452 | 49.9 % |
| < 200 USD | 2304 | 79.3 % |
| < 300 USD | 2615 | 90.0 % |
| < 500 USD | 2774 | 95.4 % |
| < 1000 USD | 2855 | 98.2 % |

### Taux de remplissage (sur les produits à prix)

| attribut | renseignés | taux | types rencontrés |
| --- | --- | --- | --- |
| `speed` | 2907 | **100.0 %** | `[number]` (2907) |
| `modules` | 2907 | **100.0 %** | `[number]` (2907) |
| `first_word_latency` | 2907 | **100.0 %** | `number` (2907) |
| `cas_latency` | 2907 | **100.0 %** | `number` (2907) |
| `price_per_gb` | 2851 | **98.1 %** | `number` (2851) |
| `color` | 2743 | **94.4 %** | `string` (2743) |

### Attributs numériques

| attribut | n | min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- | --- | --- |
| `speed[0]` | 2907 | 2 | 4 | 4 | 5 | 5 |
| `speed[1]` | 2907 | 400 | 2 400 | 3 600 | 6 000 | 8 400 |
| `modules[0]` | 2907 | 1 | 1 | 2 | 2 | 8 |
| `modules[1]` | 2907 | 1 | 8 | 16 | 24 | 64 |
| `price_per_gb` | 2851 | 1.059 | 2.999 | 4.062 | 5.928 | 497.5 |
| `first_word_latency` | 2907 | 7.368 | 10 | 12 | 13.75 | 19.167 |
| `cas_latency` | 2907 | 3 | 16 | 19 | 34 | 52 |

### Attributs énumérables — cardinalité et 10 valeurs les plus fréquentes

**`speed`** — cardinalité **50** sur 2907 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `[5, 6000]` | 371 | 12.8 % |
| `[4, 3200]` | 341 | 11.7 % |
| `[3, 1600]` | 250 | 8.6 % |
| `[5, 5600]` | 227 | 7.8 % |
| `[5, 6400]` | 211 | 7.3 % |
| `[4, 3600]` | 210 | 7.2 % |
| `[4, 2666]` | 181 | 6.2 % |
| `[3, 1333]` | 144 | 5.0 % |
| `[4, 2400]` | 124 | 4.3 % |
| `[5, 5200]` | 107 | 3.7 % |

**`modules`** — cardinalité **38** sur 2907 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `[2, 16]` | 640 | 22.0 % |
| `[2, 8]` | 368 | 12.7 % |
| `[2, 32]` | 281 | 9.7 % |
| `[1, 16]` | 279 | 9.6 % |
| `[1, 8]` | 263 | 9.0 % |
| `[1, 32]` | 157 | 5.4 % |
| `[1, 4]` | 141 | 4.9 % |
| `[2, 4]` | 118 | 4.1 % |
| `[2, 24]` | 106 | 3.6 % |
| `[4, 16]` | 91 | 3.1 % |

**`color`** — cardinalité **38** sur 2743 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `Black` | 1043 | 38.0 % |
| `Green` | 303 | 11.0 % |
| `White` | 279 | 10.2 % |
| `Black / Green` | 146 | 5.3 % |
| `Black / Silver` | 138 | 5.0 % |
| `Green / Black` | 113 | 4.1 % |
| `Silver / Black` | 90 | 3.3 % |
| `Black / Red` | 81 | 3.0 % |
| `Black / Yellow` | 71 | 2.6 % |
| `Black / White` | 65 | 2.4 % |


## `video-card`

- Produits au total : **6636**
- Produits avec un `price` non nul : **1275** (19.2 % du fichier) — c'est la base de toutes les mesures qui suivent
- Champs présents dans le fichier : `name`, `price`, `chipset`, `memory`, `core_clock`, `boost_clock`, `color`, `length`
- Noms distincts : **615** — 178 noms portés par plusieurs entrées, dont **1** où les attributs hors prix sont strictement identiques (le reste sont des variantes réelles)

### Distribution des prix (USD, snapshot juillet 2025)

| min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- |
| 45.99 | 354.24 | 595.35 | 998.00 | 7516.34 |

| seuil | produits en dessous | part |
| --- | --- | --- |
| < 100 USD | 37 | 2.9 % |
| < 200 USD | 134 | 10.5 % |
| < 300 USD | 254 | 19.9 % |
| < 500 USD | 551 | 43.2 % |
| < 1000 USD | 978 | 76.7 % |

### Taux de remplissage (sur les produits à prix)

| attribut | renseignés | taux | types rencontrés |
| --- | --- | --- | --- |
| `chipset` | 1275 | **100.0 %** | `string` (1275) |
| `memory` | 1275 | **100.0 %** | `number` (1275) |
| `color` | 1256 | **98.5 %** | `string` (1256) |
| `core_clock` | 1254 | **98.4 %** | `number` (1254) |
| `length` | 1243 | **97.5 %** | `number` (1243) |
| `boost_clock` | 1024 | **80.3 %** | `number` (1024) |

### Attributs numériques

| attribut | n | min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- | --- | --- |
| `memory` | 1275 | 0.25 | 8 | 8 | 16 | 48 |
| `core_clock` | 1254 | 115 | 1 365 | 1 626 | 2 220 | 2 740 |
| `boost_clock` | 1024 | 876 | 1 740 | 2 190 | 2 602 | 3 320 |
| `length` | 1243 | 115 | 240 | 279 | 306.5 | 360 |

### Attributs énumérables — cardinalité et 10 valeurs les plus fréquentes

**`chipset`** — cardinalité **241** sur 1275 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `GeForce RTX 5060 Ti` | 48 | 3.8 % |
| `GeForce RTX 5070` | 35 | 2.7 % |
| `GeForce RTX 5080` | 35 | 2.7 % |
| `Radeon RX 9070 XT` | 34 | 2.7 % |
| `GeForce RTX 5070 Ti` | 32 | 2.5 % |
| `GeForce RTX 5060` | 31 | 2.4 % |
| `Radeon RX 9060 XT` | 29 | 2.3 % |
| `GeForce RTX 5090` | 27 | 2.1 % |
| `GeForce RTX 4070` | 21 | 1.6 % |
| `GeForce RTX 3060 12GB` | 20 | 1.6 % |

**`color`** — cardinalité **44** sur 1256 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `Black` | 587 | 46.7 % |
| `Black / Silver` | 211 | 16.8 % |
| `Black / Red` | 84 | 6.7 % |
| `White` | 61 | 4.9 % |
| `Silver / Black` | 43 | 3.4 % |
| `Black / Gray` | 40 | 3.2 % |
| `Black / White` | 29 | 2.3 % |
| `Black / Green` | 28 | 2.2 % |
| `White / Silver` | 23 | 1.8 % |
| `Black / Orange` | 15 | 1.2 % |


## `headphones`

- Produits au total : **2946**
- Produits avec un `price` non nul : **664** (22.5 % du fichier) — c'est la base de toutes les mesures qui suivent
- Champs présents dans le fichier : `name`, `price`, `type`, `frequency_response`, `microphone`, `wireless`, `enclosure_type`, `color`
- Noms distincts : **538** — 87 noms portés par plusieurs entrées, dont **5** où les attributs hors prix sont strictement identiques (le reste sont des variantes réelles)

### Distribution des prix (USD, snapshot juillet 2025)

| min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- |
| 5.99 | 39.99 | 89.99 | 187.18 | 5999.00 |

| seuil | produits en dessous | part |
| --- | --- | --- |
| < 100 USD | 364 | 54.8 % |
| < 200 USD | 529 | 79.7 % |
| < 300 USD | 593 | 89.3 % |
| < 500 USD | 642 | 96.7 % |
| < 1000 USD | 653 | 98.3 % |

### Taux de remplissage (sur les produits à prix)

| attribut | renseignés | taux | types rencontrés |
| --- | --- | --- | --- |
| `type` | 664 | **100.0 %** | `string` (664) |
| `microphone` | 664 | **100.0 %** | `bool` (664) |
| `wireless` | 664 | **100.0 %** | `bool` (664) |
| `enclosure_type` | 664 | **100.0 %** | `string` (664) |
| `color` | 655 | **98.6 %** | `string` (655) |
| `frequency_response` | 556 | **83.7 %** | `[number]` (556) |

### Attributs numériques

| attribut | n | min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- | --- | --- |
| `frequency_response[0]` | 556 | 4 | 10 | 20 | 20 | 150 |
| `frequency_response[1]` | 556 | 2 | 20 | 20 | 28 | 75 |

### Attributs énumérables — cardinalité et 10 valeurs les plus fréquentes

**`type`** — cardinalité **4** sur 664 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `Circumaural` | 484 | 72.9 % |
| `Supra-aural` | 70 | 10.5 % |
| `In Ear` | 60 | 9.0 % |
| `Earbud` | 50 | 7.5 % |

**`frequency_response`** — cardinalité **95** sur 556 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `[20, 20]` | 234 | 42.1 % |
| `[20, 40]` | 29 | 5.2 % |
| `[10, 40]` | 19 | 3.4 % |
| `[20, 22]` | 19 | 3.4 % |
| `[12, 28]` | 17 | 3.1 % |
| `[5, 40]` | 14 | 2.5 % |
| `[5, 35]` | 9 | 1.6 % |
| `[10, 22]` | 8 | 1.4 % |
| `[10, 21]` | 7 | 1.3 % |
| `[4, 40]` | 7 | 1.3 % |

**`microphone`** — cardinalité **2** sur 664 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `True` | 472 | 71.1 % |
| `False` | 192 | 28.9 % |

**`wireless`** — cardinalité **2** sur 664 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `False` | 450 | 67.8 % |
| `True` | 214 | 32.2 % |

**`enclosure_type`** — cardinalité **3** sur 664 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `Closed` | 598 | 90.1 % |
| `Open` | 55 | 8.3 % |
| `Semi-open` | 11 | 1.7 % |

**`color`** — cardinalité **63** sur 655 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `Black` | 250 | 38.2 % |
| `Black / Silver` | 82 | 12.5 % |
| `White` | 51 | 7.8 % |
| `Black / Red` | 43 | 6.6 % |
| `Black / Blue` | 24 | 3.7 % |
| `Black / Green` | 21 | 3.2 % |
| `White / Black` | 13 | 2.0 % |
| `Blue` | 13 | 2.0 % |
| `Silver` | 9 | 1.4 % |
| `White / Gray` | 8 | 1.2 % |


## `keyboard`

- Produits au total : **4310**
- Produits avec un `price` non nul : **824** (19.1 % du fichier) — c'est la base de toutes les mesures qui suivent
- Champs présents dans le fichier : `name`, `price`, `style`, `switches`, `backlit`, `tenkeyless`, `connection_type`, `color`
- Noms distincts : **556** — 136 noms portés par plusieurs entrées, dont **8** où les attributs hors prix sont strictement identiques (le reste sont des variantes réelles)

### Distribution des prix (USD, snapshot juillet 2025)

| min | p25 | médiane | p75 | max |
| --- | --- | --- | --- | --- |
| 10.77 | 48.96 | 92.32 | 149.99 | 909.36 |

| seuil | produits en dessous | part |
| --- | --- | --- |
| < 100 USD | 478 | 58.0 % |
| < 200 USD | 731 | 88.7 % |
| < 300 USD | 798 | 96.8 % |
| < 500 USD | 819 | 99.4 % |
| < 1000 USD | 824 | 100.0 % |

### Taux de remplissage (sur les produits à prix)

| attribut | renseignés | taux | types rencontrés |
| --- | --- | --- | --- |
| `style` | 824 | **100.0 %** | `string` (824) |
| `tenkeyless` | 824 | **100.0 %** | `bool` (824) |
| `connection_type` | 817 | **99.2 %** | `string` (817) |
| `color` | 812 | **98.5 %** | `string` (812) |
| `backlit` | 464 | **56.3 %** | `string` (464) |
| `switches` | 445 | **54.0 %** | `string` (445) |

### Attributs énumérables — cardinalité et 10 valeurs les plus fréquentes

**`style`** — cardinalité **6** sur 824 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `Gaming` | 362 | 43.9 % |
| `Standard` | 240 | 29.1 % |
| `Mini` | 92 | 11.2 % |
| `Slim` | 74 | 9.0 % |
| `Ergonomic` | 48 | 5.8 % |
| `Ergonomic Split` | 8 | 1.0 % |

**`switches`** — cardinalité **150** sur 445 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `Cherry MX Blue` | 19 | 4.3 % |
| `Cherry MX Brown` | 15 | 3.4 % |
| `Cherry MX Red` | 13 | 2.9 % |
| `Razer Green` | 11 | 2.5 % |
| `Cherry MX Speed Silver` | 11 | 2.5 % |
| `TTC Brown` | 10 | 2.2 % |
| `Outemu Blue` | 9 | 2.0 % |
| `SteelSeries OmniPoint 2.0` | 7 | 1.6 % |
| `Gateron Red` | 7 | 1.6 % |
| `Razer Yellow` | 7 | 1.6 % |

**`backlit`** — cardinalité **7** sur 464 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `RGB` | 379 | 81.7 % |
| `White` | 45 | 9.7 % |
| `Blue` | 13 | 2.8 % |
| `Multicolor` | 12 | 2.6 % |
| `Red` | 11 | 2.4 % |
| `Green` | 3 | 0.6 % |
| `Orange` | 1 | 0.2 % |

**`tenkeyless`** — cardinalité **2** sur 824 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `False` | 510 | 61.9 % |
| `True` | 314 | 38.1 % |

**`connection_type`** — cardinalité **10** sur 817 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `Wired` | 479 | 58.6 % |
| `Wired, Wireless, Bluetooth Wireless` | 113 | 13.8 % |
| `Wireless` | 96 | 11.8 % |
| `Wired, Wireless` | 34 | 4.2 % |
| `Wired, Bluetooth Wireless` | 27 | 3.3 % |
| `Bluetooth Wireless` | 27 | 3.3 % |
| `Wired, Wired` | 16 | 2.0 % |
| `Wired, Wired, Wireless, Bluetooth Wireless` | 12 | 1.5 % |
| `Wireless, Bluetooth Wireless` | 11 | 1.3 % |
| `Wired, Wired, Bluetooth Wireless` | 2 | 0.2 % |

**`color`** — cardinalité **45** sur 812 valeurs renseignées

| valeur | effectif | part |
| --- | --- | --- |
| `Black` | 563 | 69.3 % |
| `White` | 57 | 7.0 % |
| `Black / Gray` | 33 | 4.1 % |
| `Gray` | 16 | 2.0 % |
| `Black / Silver` | 11 | 1.4 % |
| `Black / Red` | 11 | 1.4 % |
| `Pink` | 10 | 1.2 % |
| `Gray / Black` | 9 | 1.1 % |
| `Silver / Black` | 9 | 1.1 % |
| `White / Silver` | 8 | 1.0 % |
