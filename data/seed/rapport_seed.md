# Rapport du seed — étape 5

Généré par `make seed-build` (`scripts/seed_build.py`). Passe déterministe,
sans le moindre appel à un modèle de langage. Committé : c'est un livrable de
l'étape, pas une sortie de console.

- Source : `docyx/pc-part-dataset`, commit `c52a04c` — voir `data/raw/SOURCE.md`
- Graine du tirage : `20260828` (constante de code, cf. `selection.py`)
- Généré le : 2026-08-28 16:09 UTC

> ⚠️ **Toutes les statistiques de ce rapport portent sur le seed, pas sur la
> source** (décision 3.1bis). L'échantillonnage stratifié conserve la forme de
> la distribution des prix, mais les taux de remplissage y diffèrent
> légèrement de ceux mesurés à l'étape 3.

## Entonnoir

| catégorie | lues | sans prix | à prix | normalisées | dédupliquées | validées | sélectionnées |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `cpu` | 1413 | 866 | 547 | 547 | 492 | 492 | 171 |
| `monitor` | 5074 | 3707 | 1367 | 1367 | 1337 | 1337 | 171 |
| `internal-hard-drive` | 6461 | 4358 | 2103 | 2095 | 1985 | 1985 | 171 |
| `memory` | 13553 | 10646 | 2907 | 2907 | 2659 | 2659 | 171 |
| `video-card` | 6636 | 5361 | 1275 | 1275 | 1270 | 1270 | 171 |
| `headphones` | 2946 | 2282 | 664 | 664 | 657 | 657 | 171 |
| `keyboard` *(retirée §3.4bis)* | 4310 | — | — | — | — | — | — |
| **total** | **40393** | **27220** | **8863** | **8855** | **8400** | **8400** | **1026** |

Le filtre sur le prix retire **27220 lignes sur 36083** des six catégories retenues, soit **75.4 %**. C'est le chiffre des 76 % annoncé à l'étape 3 : un produit sans prix n'entre pas dans un moteur à contrainte budgétaire.

## Motifs de rejet

| motif | lignes |
| --- | ---: |
| keyboard : catégorie retirée à l'étape 3 (§3.4bis) | 4310 |
| internal-hard-drive : type de disque absent | 8 |

Aucune de ces lignes n'a été réparée : une valeur manquante ou inattendue fait
sortir la ligne du pipeline, elle n'est jamais comblée (§3.4quater).

## Déduplication

Une règle unique sur les six catégories : regrouper par `id`, garder le prix le
plus bas. L'`id` **est** la clé de déduplication (arbitrage C), et il exclut le
prix et toute grandeur qui en dérive (arbitrage D).

| catégorie | lignes | groupes | absorbées | écart de prix max dans un groupe |
| --- | ---: | ---: | ---: | ---: |
| `cpu` | 547 | 492 | 55 | 1669.00 USD (`cpu-75177d4f9f`) |
| `monitor` | 1367 | 1337 | 30 | 134.00 USD (`monitor-4a66f55490`) |
| `internal-hard-drive` | 2095 | 1985 | 110 | 665.00 USD (`internal-hard-drive-0c327abc45`) |
| `memory` | 2907 | 2659 | 248 | 699.38 USD (`memory-b7a5898bb9`) |
| `video-card` | 1275 | 1270 | 5 | 40.13 USD (`video-card-0d73a9a36a`) |
| `headphones` | 664 | 657 | 7 | 50.82 USD (`headphones-3035942b28`) |

L'écart de prix maximal à l'intérieur d'un groupe est le chiffre qui révélerait
une clé trop lâche : deux produits différents fusionnés se trahiraient par un
écart que rien n'explique.

## Contrôle de `price_per_gb` (transformation 6)

Recalculé sur le prix retenu, jamais recopié. La comparaison à la valeur source
porte sur les lignes **non dédupliquées** : ailleurs, le prix retenu n'est plus
celui qui a servi à la source.

| catégorie | lignes comparées | écart médian | 99ᵉ centile | max | > 1 % |
| --- | ---: | ---: | ---: | ---: | ---: |
| `internal-hard-drive` | 1831 | 0.0000% | 0.6711% | 4.5455% | 12 (0.66%) |
| `memory` | 2417 | 0.0000% | 0.0292% | 0.0640% | 0 (0.00%) |

Seuil d'arrêt : plus de 1 % des lignes s'écartant de plus de 1 %. Il n'est pas
atteint.

## Le seed

### Distribution des prix (USD)

| catégorie | produits | min | médiane | max |
| --- | ---: | ---: | ---: | ---: |
| `cpu` | 171 | 25.00 | 165.00 | 2699.99 |
| `monitor` | 171 | 64.98 | 294.98 | 9333.00 |
| `internal-hard-drive` | 171 | 12.49 | 127.59 | 4777.83 |
| `memory` | 171 | 9.99 | 99.99 | 3737.49 |
| `video-card` | 171 | 62.99 | 599.00 | 7516.34 |
| `headphones` | 171 | 5.99 | 92.19 | 5999.00 |
| **total** | **1026** | | | |

### Strates de prix et repêchages

| catégorie | disponibles | cible | strates servies | repêchés G1 | repêchés G2 | repêchés G4 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `cpu` | 492 | 170 | 10/10 | 0 | 0 | 1 |
| `monitor` | 1337 | 170 | 10/10 | 0 | 0 | 1 |
| `internal-hard-drive` | 1985 | 170 | 10/10 | 0 | 0 | 1 |
| `memory` | 2659 | 170 | 10/10 | 0 | 0 | 1 |
| `video-card` | 1270 | 170 | 10/10 | 0 | 0 | 1 |
| `headphones` | 657 | 170 | 10/10 | 0 | 0 | 1 |

### Taux de remplissage par attribut, sur le seed final

**`cpu`** — 171 produits

| attribut | renseignés | taux |
| --- | ---: | ---: |
| `core_count` | 171 | 100.0 % |
| `core_clock` | 171 | 100.0 % |
| `tdp` | 171 | 100.0 % |
| `microarchitecture` | 171 | 100.0 % |
| `boost_clock` | 113 | 66.1 % |
| `graphics` | 91 | 53.2 % |

**`monitor`** — 171 produits

| attribut | renseignés | taux |
| --- | ---: | ---: |
| `screen_size` | 171 | 100.0 % |
| `largeur_px` | 171 | 100.0 % |
| `hauteur_px` | 171 | 100.0 % |
| `aspect_ratio` | 171 | 100.0 % |
| `panel_type` | 167 | 97.7 % |
| `refresh_rate` | 164 | 95.9 % |
| `response_time` | 128 | 74.9 % |

**`internal-hard-drive`** — 171 produits

| attribut | renseignés | taux |
| --- | ---: | ---: |
| `capacity` | 171 | 100.0 % |
| `form_factor` | 171 | 100.0 % |
| `interface` | 171 | 100.0 % |
| `type` | 171 | 100.0 % |
| `rpm` | 58 | 33.9 % |
| `price_per_gb` *(dérivé du prix)* | 171 | 100.0 % |
| `cache` | 63 | 36.8 % |

**`memory`** — 171 produits

| attribut | renseignés | taux |
| --- | ---: | ---: |
| `ddr_generation` | 171 | 100.0 % |
| `frequence_mhz` | 171 | 100.0 % |
| `nb_modules` | 171 | 100.0 % |
| `taille_module_gb` | 171 | 100.0 % |
| `capacite_totale_gb` | 171 | 100.0 % |
| `cas_latency` | 171 | 100.0 % |
| `first_word_latency` | 171 | 100.0 % |
| `price_per_gb` *(dérivé du prix)* | 171 | 100.0 % |
| `color` | 164 | 95.9 % |

**`video-card`** — 171 produits

| attribut | renseignés | taux |
| --- | ---: | ---: |
| `chipset` | 171 | 100.0 % |
| `memory` | 171 | 100.0 % |
| `length` | 165 | 96.5 % |
| `core_clock` | 167 | 97.7 % |
| `boost_clock` | 135 | 78.9 % |
| `color` | 169 | 98.8 % |

**`headphones`** — 171 produits

| attribut | renseignés | taux |
| --- | ---: | ---: |
| `type` | 171 | 100.0 % |
| `microphone` | 171 | 100.0 % |
| `wireless` | 171 | 100.0 % |
| `enclosure_type` | 171 | 100.0 % |
| `freq_min_hz` | 141 | 82.5 % |
| `freq_max_khz` | 141 | 82.5 % |
| `color` | 171 | 100.0 % |

### Valeurs distinctes des énumérations normalisées

- `cpu.microarchitecture` — 30 valeurs : `Kaby Lake` 13 · `Haswell` 12 · `Skylake` 12 · `Coffee Lake Refresh` 11 · `Sandy Bridge` 10 · `Coffee Lake` 8 · `Ivy Bridge` 8 · `Raptor Lake Refresh` 8 · `Broadwell` 7 · `Zen 4` 7 · `Alder Lake` 6 · `Comet Lake` 6 · `K10` 5 · `Piledriver` 5 · `Zen` 5 · `Zen 2` 5 · `Arrow Lake` 4 · `Core` 4 · `Haswell Refresh` 4 · `Nehalem` 4 · `Raptor Lake` 4 · `Zen 3` 4 · `Zen+` 4 · `Rocket Lake` 3 · `Wolfdale` 3 · `Steamroller` 2 · `Westmere` 2 · `Yorkfield` 2 · `Zen 5` 2 · `Excavator` 1
- `monitor.aspect_ratio` — 8 valeurs : `16:9` 141 · `21:9` 19 · `5:4` 4 · `32:9` 3 · `16:10` 1 · `4:3` 1 · `64:27` 1 · `8:9` 1
- `monitor.panel_type` — 8 valeurs : `IPS` 102 · `VA` 47 · `TN` 7 · `OLED` 5 · `QD-OLED` 3 · `Mini LED IPS` 1 · `PLS` 1 · `WOLED` 1
- `internal-hard-drive.type` — 2 valeurs : `SSD` 113 · `HDD` 58
- `internal-hard-drive.form_factor` — 6 valeurs : `2.5"` 58 · `M.2-2280` 52 · `3.5"` 49 · `M.2-2230` 8 · `M.2-2242` 3 · `mSATA` 1
- `internal-hard-drive.interface` — 10 valeurs : `SATA 6.0 Gb/s` 85 · `M.2 PCIe 4.0 X4` 40 · `M.2 PCIe 3.0 X4` 16 · `SATA 3.0 Gb/s` 16 · `M.2 PCIe 5.0 X4` 4 · `M.2 SATA` 3 · `SAS 6.0 Gb/s` 3 · `U.2` 2 · `SAS 12.0 Gb/s` 1 · `mSATA` 1
- `memory.ddr_generation` — 4 valeurs : `5` 76 · `4` 66 · `3` 25 · `2` 4
- `headphones.type` — 4 valeurs : `Circumaural` 126 · `Supra-aural` 18 · `In Ear` 17 · `Earbud` 10
- `headphones.enclosure_type` — 3 valeurs : `Closed` 157 · `Open` 11 · `Semi-open` 3

`internal-hard-drive.form_factor` est celle qui compte : deux types JSON
distincts de la source (`2.5` en nombre, `"M.2-2280"` en chaîne) y ont fusionné
en une seule énumération textuelle. Aucune forme inattendue n'est passée.

### Marques par volume

Premier mot de `name`, corrigé par la table fermée de marques en plusieurs mots
(`normalisation.MARQUES_MULTI_MOTS`). Aucune catégorie de la source ne porte de
champ marque : c'est une transformation, pas une lecture (§3.4quater).

| marque | produits |
| --- | ---: |
| Intel | 142 |
| MSI | 62 |
| Asus | 43 |
| Kingston | 43 |
| AMD | 42 |
| Corsair | 41 |
| LG | 33 |
| G.Skill | 31 |
| Western Digital | 30 |
| Samsung | 29 |
| Gigabyte | 28 |
| Seagate | 26 |
| PNY | 25 |
| Crucial | 22 |
| TEAMGROUP | 22 |
| Patriot | 21 |
| Acer | 19 |
| Audio-Technica | 17 |
| EVGA | 16 |
| Zotac | 16 |
| HP | 15 |
| Razer | 12 |
| Logitech | 12 |
| SteelSeries | 11 |
| Sennheiser | 10 |
| ADATA | 10 |
| VisionTek | 10 |
| Dell | 10 |
| ASRock | 10 |
| Lenovo | 9 |

110 marques distinctes au seed ; les 30 premières sont listées.

## Cas limites pour l'étape 6

Repêchés **parmi des produits réels**, jamais fabriqués : inventer un produit
pour faire passer un test futur violerait §2 dans le fichier même qui sert de
catalogue. Les identifiants ci-dessous sont ceux que les tests de l'étape 6
citeront — s'ils changent, un test cassera, ce qui est le comportement souhaité.

### G1 — budget frôlé

Au moins un produit par catégorie dans `]seuil, seuil x 1,15]`, la zone de
tolérance de §3.10.

| catégorie | seuil | produit | prix | repêché ? |
| --- | ---: | --- | ---: | --- |
| `cpu` | 100 USD | `cpu-bfbc23021a` | 108.99 USD | non — déjà tiré |
| `monitor` | 300 USD | `monitor-857dd58120` | 308.00 USD | non — déjà tiré |
| `internal-hard-drive` | 100 USD | `internal-hard-drive-c2dd3e2507` | 103.92 USD | non — déjà tiré |
| `memory` | 100 USD | `memory-fd8360b7eb` | 101.99 USD | non — déjà tiré |
| `video-card` | 500 USD | `video-card-be85208269` | 529.00 USD | non — déjà tiré |
| `headphones` | 100 USD | `headphones-2a0bb59183` | 104.36 USD | non — déjà tiré |

### G2 — départage

Deux produits `headphones` dont toutes les specs sont identiques, sauf le
prix et le champ d'affichage `color` :

- `headphones-06acf63b59` — 23.47 USD — color : 'Black / Silver'
- `headphones-393cd46c64` — 41.99 USD — color : 'Black'

Repêché : non — déjà tiré. Un champ `affichage`
n'entre ni dans un filtre ni dans un score : le moteur de l'étape 6 devra donc
les départager sur le prix seul.

### G3 — zéro résultat

Sur `internal-hard-drive` : `form_factor` = 'M.2-2280' ET `interface` = 'SATA 6.0 Gb/s' → **0 produit**.

Chaque critère pris seul est pourtant servi par le seed — c'est ce qui rend la
combinaison plausible plutôt qu'absurde :

- `form_factor=M.2-2280` seul → 52 produits
- `interface=SATA 6.0 Gb/s` seul → 85 produits

Cette combinaison ne se place pas, elle **se constate**. C'est le scénario du
critère d'acceptation nº6 : dire pourquoi il n'y a rien et proposer
l'assouplissement du critère le plus coûteux.

### G4 — haut de gamme

Le produit le plus cher de chaque catégorie est au seed. La stratification par
décile conserve la **forme** de la distribution des prix, pas ses **extrêmes** :
avec 17 tirages dans le dernier décile, le produit le plus cher a une chance sur
huit d'être retenu. Sans cette garantie, le catalogue n'offrirait aucun cas
« budget très large » et le haut de gamme réel du domaine serait absent.

| catégorie | produit | prix | repêché ? |
| --- | --- | ---: | --- |
| `cpu` | `cpu-c71852bd9d` | 2699.99 USD | oui |
| `monitor` | `monitor-0783259c60` | 9333.00 USD | oui |
| `internal-hard-drive` | `internal-hard-drive-8bc5b38352` | 4777.83 USD | oui |
| `memory` | `memory-41d690131b` | 3737.49 USD | oui |
| `video-card` | `video-card-74e3368c41` | 7516.34 USD | oui |
| `headphones` | `headphones-87c44ca03d` | 5999.00 USD | oui |

Aucune garantie symétrique sur le produit le moins cher : le premier décile est
dense, son minimum y est déjà représenté, et une garantie qui ne repêche jamais
rien serait du code mort qui se donne l'air d'une preuve.
