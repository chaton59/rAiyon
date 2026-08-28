# Source des données brutes

| | |
| --- | --- |
| Dépôt | https://github.com/docyx/pc-part-dataset |
| Commit figé | `c52a04ca9465c83997ed335f7767b09a2005dd26` |
| Date du commit | 2025-07-23 |
| Date de récupération | 2026-08-27 |
| Licence du dépôt | MIT — © 2021-2025 Doc Oliver |
| Origine réelle des données | scrapées de PCPartPicker (snapshot juillet 2025) |
| Devise | USD, prix figés à juillet 2025 |

## Fichiers retenus

Seules les **7 catégories** arrêtées en 3.4bis sont figées ici. Le dépôt amont en
contient 25 ; les 18 autres ne sont pas récupérées.

| fichier | taille |
| --- | --- |
| `cpu.json` | 220 Ko |
| `monitor.json` | 800 Ko |
| `internal-hard-drive.json` | 968 Ko |
| `memory.json` | 2,2 Mo |
| `video-card.json` | 1004 Ko |
| `headphones.json` | 504 Ko |
| `keyboard.json` | 736 Ko |
| **total** | **6,4 Mo** |

## `data/raw/` n'est pas versionné

6,4 Mo de JSON scrapé n'ont pas à entrer dans l'historique git : le répertoire est
listé dans `.gitignore`. Seul ce fichier `SOURCE.md` y est forcé, pour que la
commande de récupération reste dans le dépôt.

## Commande de récupération

```bash
git clone --depth 1 --filter=blob:none --no-checkout \
  https://github.com/docyx/pc-part-dataset.git /tmp/pc-part-dataset
cd /tmp/pc-part-dataset
git checkout c52a04ca9465c83997ed335f7767b09a2005dd26
git sparse-checkout init --cone
git sparse-checkout set data/json
git checkout

mkdir -p data/raw
cp /tmp/pc-part-dataset/data/json/{cpu,monitor,internal-hard-drive,memory,video-card,headphones,keyboard}.json \
   data/raw/
```

Vérification de l'intégrité après copie :

```bash
sha256sum -c data/raw/CHECKSUMS.sha256
```

## Attribution à porter dans le README

> Données produits issues de [`docyx/pc-part-dataset`](https://github.com/docyx/pc-part-dataset)
> (licence MIT), snapshot du 23 juillet 2025, lui-même scrapé de PCPartPicker.
> Les prix sont en USD et figés à cette date : le catalogue est un instantané, pas un flux.
