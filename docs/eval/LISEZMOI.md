# Les rapports d'éval — lequel décrit quoi

Cinq fichiers, presque identiques de forme et très différents de sens. Sans cet index,
c'est un piège : on ouvre le premier, on lit un tableau vert, et on croit avoir lu le bon.

**Un rapport se lit toujours avec ses trois appendices**, qui portent ce qu'un tableau ne
peut pas dire — les phrases que le validateur a refusées, la prose des tours de domaine
telle quelle, et le markdown que le front n'affiche pas.

## Les rapports

| Fichier | Ce qu'il décrit | Prompt | Prises |
|---|---|---|---|
| `rapport.v1-etape12.md` | Le tirage de l'**étape 12**, celui que §7 de `PROJET.md` cite | `systeme.v1` | 19, dont **1 écartée** |
| `rapport.v1-base.md` | La **ligne de base** contre laquelle v2 est comparée | `systeme.v1` | 31, **trois enregistrements** |
| `rapport.v2.md` | La campagne de l'**étape 13**, prompt en vigueur | `systeme.v2` | 36 |

⚠️ **`rapport.v1-etape12.md` n'est pas une base de comparaison.** C'est une archive : le
tirage que §7 et le correctif de l'étape 12 décrivent, conservé pour qu'ils citent quelque
chose qui existe. Une de ses dix-neuf prises — `desserrage_refuse.1` — ne se rejoue plus
depuis le correctif de validateur de l'étape 13, et le rapport le déclare en tête. Elle
portait **4 des 11 griefs** : ses totaux ne se comparent donc à rien tels quels.

⚠️ **`rapport.v1-base.md` est composé de trois enregistrements**, et il le déclare
scénario par scénario. Un scénario vient d'**une seule** source, jamais de deux : mélanger
deux dates dans les trois prises d'un même scénario ferait confondre la dispersion d'un
tirage avec l'écart entre deux enregistrements.

## Les comparaisons

| Fichier | La question qu'elle pose |
|---|---|
| `comparaison.v1-etape12-v1-partielle.md` | Une **borne supérieure** de la dérive du modèle entre deux dates, sur le même prompt |
| `comparaison.v1-base-v2.md` | L'effet des **trois cibles** de `systeme.v2` |

⚠️ **La borne de dérive majore, elle ne mesure pas.** L'écart entre deux enregistrements
du même prompt confond ce que le modèle a changé et le bruit d'échantillonnage que §7
documente déjà. Une phrase qui dirait « le modèle a dérivé de X » serait fausse.

## Comment lire un verdict

Chaque comparaison porte, pour chaque mesure, un verdict **calculé** : `au-delà` ou
`dans le bruit`. La dispersion est l'étendue `max - min` des prises de la campagne de
référence, scénario par scénario, sommée — de combien le total aurait pu bouger par le
seul tirage.

* **ce n'est ni un écart-type ni un test.** C'est une borne délibérément généreuse : elle
  déclare « au-delà » moins souvent qu'un test statistique, ce qui est le sens dans lequel
  ce dépôt préfère se tromper ;
* **un scénario vu trois fois à la même valeur ne compte pas zéro.** Trois tirages
  identiques bornent l'étendue par en dessous, ils ne la mesurent pas — chaque scénario
  contribue donc au moins un pas ;
* **les valeurs comparées sont des moyennes par scénario, sommées**, pas des totaux. Deux
  campagnes n'ont pas forcément le même nombre de prises, et comparer des totaux
  comparerait des tailles d'échantillon.

## Reproduire

```bash
make eval                    # le jeu de la version en vigueur → rapport.<jeu>.md
make eval-etape12            # l'archive → rapport.v1-etape12.md
make eval-comparer AVANT=v1-base APRES=v2 Q="ce que la comparaison cherche"
```

Aucune de ces commandes n'appelle l'API : le rejeu ne demande que les cassettes, la base et
le seed. Seul `make eval-enregistrer` consomme des jetons.

La ligne de base se rejoue en nommant sa version, puisqu'elle n'est plus celle en vigueur :

```bash
RAIYON_PROMPT_SYSTEME=systeme.v1 uv run python scripts/eval.py rejouer --jeu v1-base
```
