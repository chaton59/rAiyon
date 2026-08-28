# Prompt Claude Code — correctif d'étape 5 : garantie G4

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`. L'étape 5 est livrée et vérifiée. Tu vas
appliquer **un correctif ciblé, et rien d'autre** : ajouter une quatrième
garantie de cas limite à la sélection, régénérer le seed et son rapport.

**N'ouvre pas l'étape 6. Ne relance pas la passe B** (`make seed-llm`) : le
correctif change la composition du seed, la traduction se fait après.

## Le constat qui motive le correctif

La stratification par décile conserve la **forme** de la distribution des prix,
pas ses **extrêmes**. Mesuré sur le seed livré :

| catégorie | prix max source | prix max seed |
| --- | ---: | ---: |
| `monitor` | 9 333,00 | 2 699,00 |
| `video-card` | 7 516,34 | 3 862,99 |

Avec 17 tirages dans le dernier décile, le produit le plus cher a une chance sur
huit d'être retenu. Conséquence pour l'étape 6 : le catalogue n'offre aucun cas
« budget très large », et le haut de gamme réel du domaine est absent du seed.

Ce n'est pas un défaut de la stratification, c'est sa limite. On la corrige par
un repêchage, pas en changeant le tirage — la graine et les quotas ne bougent
pas, et les produits déjà tirés restent tirés.

## Ce que tu livres

**G4 — le produit le plus cher de chaque catégorie est au seed.**

Elle suit **exactement le mécanisme de G1 et G2** : un contrôle après tirage
qui, si le produit manque, l'ajoute (`ajouts`), et qui dans tous les cas
consigne le cas dans le rapport avec la mention `repêché ?`. Comme pour G1 et
G2, c'est un **ajout**, pas une substitution : la cible reste 170, le total peut
donc monter jusqu'à 1 026. La borne `[900, 1100]` de
`tests/test_seed_committe.py` couvre déjà ce cas — vérifie-le, ne le suppose pas.

Le produit est choisi de façon déterministe : prix maximal, `id` le plus petit
en cas d'égalité — la même règle de départage que celle déjà utilisée dans
`garantir_g1`.

Écris dans le code **pourquoi cette garantie existe**, avec le chiffre : le
tirage stratifié perd les extrêmes, et un moteur à contrainte budgétaire dont le
catalogue s'arrête à 2 699 USD ne peut pas être exercé sur un budget large.

## Ce que tu ne fais pas

- Ne touche ni à `GRAINE_TIRAGE`, ni à `CIBLE_PAR_CATEGORIE`, ni au découpage en
  strates, ni à la répartition des quotas. Le diff du seed doit être **fait
  uniquement d'ajouts** : si une ligne existante disparaît, tu as changé le
  tirage sans le vouloir — arrête-toi et dis-le.
- N'ajoute pas de garantie symétrique sur le produit le moins cher. Le premier
  décile est dense, le minimum y est déjà représenté ; une garantie qui ne
  repêche jamais rien est du code mort qui se donne l'air d'une preuve.
- Ne fabrique aucun produit. G4 se sert dans les produits réels dédupliqués,
  comme G1 et G2.

## Tests

Dans `tests/test_selection.py`, dans la forme des tests G1/G2 existants :

- un catalogue de test dont le produit le plus cher n'est **pas** tiré → il est
  repêché, et le cas est marqué `repêché` ;
- un catalogue où il est déjà tiré → **aucun ajout**, et le cas est marqué
  `déjà tiré` ;
- égalité de prix entre deux produits → c'est le plus petit `id` qui gagne, deux
  exécutions donnent le même.

Et dans `tests/test_seed_committe.py` : pour chacune des 6 catégories, le prix
maximal du seed est celui du produit G4 nommé dans le rapport. C'est le test qui
garde le correctif contre une régénération distraite.

## Rapport et documentation

- `data/seed/rapport_seed.md` : une section **G4** dans « Cas limites pour
  l'étape 6 », avec `id`, prix, et `repêché ?` par catégorie. Ajoute au tableau
  « Strates de prix et repêchages » une colonne `repêchés G4`.
- **Vérifie que G1, G2 et G3 tiennent toujours** après régénération. G3 en
  particulier se **constate** : six produits de plus peuvent remplir
  l'intersection qui était vide. Si la combinaison retenue n'est plus vide, le
  code doit en choisir une autre selon le critère déjà écrit (celle dont le
  critère le moins servi l'est le mieux) — et tu me le signales, parce que les
  `id` cités changeront.
- `PROJET.md` : amende **3.1bis** — la stratification conserve la forme de la
  distribution mais pas ses extrêmes, G4 corrige ce point précis, avec les deux
  chiffres du tableau ci-dessus. Deux ou trois phrases, pas une section.

## Porte de sortie

`make seed-build` régénéré, `make check` vert, `make test-int` vert, `make seed`
rechargé. Montre-moi le diff de `data/seed/produits.jsonl` **résumé par
catégorie** (nombre d'ajouts, nombre de suppressions — les suppressions doivent
être à zéro) et la nouvelle section du rapport.

Même style que le reste du dépôt : français, commentaires qui expliquent
pourquoi. Si un point de ce prompt te paraît faux ou contradictoire, arrête-toi
et dis-le avant d'écrire le code.
