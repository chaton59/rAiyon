# Les rapports d'éval — lequel décrit quoi

Huit fichiers, presque identiques de forme et très différents de sens. Sans cet index,
c'est un piège : on ouvre le premier, on lit un tableau vert, et on croit avoir lu le bon.

Un neuvième, `conversations-a-essayer.md`, n'est pas un rapport : c'est la liste des
conversations à tenir **à la main**, parce que les deux seuls défauts trouvés hors des
tests l'ont été en conversation réelle.

⚠️ **Depuis l'étape 15, deux d'entre eux ne décrivent pas une version de prompt mais une
_orchestration_.** Toutes les comparaisons antérieures opposent deux rédactions du même
prompt sur la même boucle d'agent ; `machine.v1` oppose deux **façons de conduire le tour
de parole**, à catalogue, moteur, couche outils et validateur identiques. Lire son verdict
comme celui d'un changement de prompt serait un contresens.

**Un rapport se lit toujours avec ses trois appendices**, qui portent ce qu'un tableau ne
peut pas dire — les phrases que le validateur a refusées, la prose des tours de domaine
telle quelle, et le markdown que le front n'affiche pas.

## Les rapports

| Fichier | Ce qu'il décrit | Prompt | Prises |
|---|---|---|---|
| `rapport.v1-etape12.md` | Le tirage de l'**étape 12**, celui que §7 de `PROJET.md` cite | `systeme.v1` | 19, dont **1 écartée** |
| `rapport.v1-base.md` | La **ligne de base** contre laquelle v2 est comparée | `systeme.v1` | 31, **trois enregistrements** |
| `rapport.v2.md` | La campagne de l'**étape 13** — prompt en vigueur **jusqu'au 2026-09-06** | `systeme.v2` | 36, dont **2 écartées** |
| `rapport.machine.v1.md` | La campagne de l'**étape 15** : la variante **machine à états** | `systeme.machine.v1` | 36, dont **6 écartées** |
| **`rapport.v3.md`** | La campagne de l'**étape 32** — **le prompt en vigueur** depuis le 2026-09-06 | `systeme.v3` | 36, **aucune écartée** |

⚠️ **`rapport.v3.md` est le seul que `make eval` régénère aujourd'hui**, et le seul dont le
jeu de cassettes soit encore rejouable. Les cinq autres jeux — 151 cassettes — déclarent
l'empreinte de schéma d'outils d'avant `search_reviews` (2026-09-06) : leurs rapports
restent **lisibles et cités**, mais ils ne se recalculent plus. Voir `eval.est_archive` et
`PROJET.md` §7.

⚠️ **Ce tableau a eu un trou entre le 2026-09-06 et le 2026-09-07** : `rapport.v3.md`
existait et n'y figurait pas, et la ligne de `v2` disait « prompt en vigueur » alors qu'il ne
l'était plus. **Un index est un test de ce qu'il indexe** — celui-ci n'en est pas un, faute
d'être exécutable, et c'est exactement pourquoi il a dérivé. Consigné plutôt que corrigé en
silence.

⚠️ **`rapport.v1-etape12.md` n'est pas une base de comparaison.** C'est une archive : le
tirage que §7 et le correctif de l'étape 12 décrivent, conservé pour qu'ils citent quelque
chose qui existe. Une de ses dix-neuf prises est écartée du rejeu, et le rapport le déclare
en tête : ses totaux ne se comparent donc à rien tels quels. ⚠️ **Ce n'est plus la même
prise depuis l'étape 18** : `desserrage_refuse.1` sortait depuis le correctif de l'étape 13
et **se rejoue de nouveau** — le correctif de l'étape 18 fait tomber les griefs qui
restaient, donc la régénération n'a plus lieu et l'empreinte cesse de diverger. C'est
`zero_budget_trop_bas.1` qui prend sa place.

🔴 **Un rapport dont des prises sont écartées ne se lit pas comme un rapport complet, et
c'est vrai des trois.** Un correctif de validateur change des listes de griefs, donc des
reprises, donc des empreintes de requête : les prises qui portaient le défaut corrigé sont
précisément celles qui cessent d'être rejouables. **La mesure d'un correctif de validateur
est donc en partie auto-annulante**, et le sens de l'erreur est toujours le même — le
« après » se lit sur un sous-ensemble d'où le phénomène a été retiré. Chaque rapport
l'annonce en tête, avec les prises concernées et la raison. Pour `rapport.machine.v1.md`,
l'effet est majeur : voir `PROJET.md` §5 étape 15, verdict suspendu.

⚠️ **Et le mécanisme ne vient pas que du validateur.** À l'étape 21, une garde
d'orchestration — écrite, mesurée, puis **retirée à l'étape 22** — aurait fait diverger dix
prises de plus de `machine.v1`, ramenant ce rapport à 20 prises sur 36 et la comparaison à
7 scénarios sur 11. **C'est ce prix-là qui l'a fait retirer** : voir `PROJET.md` §7. La
leçon reste écrite parce qu'elle vaut au-delà de ce cas — **toute** correction de
l'orchestration ou du validateur périme les prises qui portaient le défaut corrigé,
c'est-à-dire exactement celles qui le mesuraient.

⚠️ **`rapport.machine.v1.md` ne change pas de prompt, il change d'orchestration.**
`systeme.machine.v1.md` est `systeme.v2.md` **moins §5, §6 et §8** — une soustraction pure,
vérifiée par un test —, et ces trois sections sont exactement celles dont la conduite est
passée dans `raiyon/machine/decision.py`. Ce que le rapport décrit est donc la **même
rédaction** conduite autrement, pas une rédaction différente.

⚠️ **Deux lignes de ce rapport ne se lisent pas comme celles des autres.** La mesure nº7
(appels par tour) doit se lire **avec les jetons**, le compte d'appels et le coût d'entrée
n'allant pas dans le même sens chez la machine ; et `Itérations` **ne se compare pas** d'une
orchestration à l'autre — chez une machine à états c'est une constante décidée par le
graphe, et le rapport porte la réserve.

⚠️ **`rapport.v1-base.md` est composé de trois enregistrements**, et il le déclare
scénario par scénario. Un scénario vient d'**une seule** source, jamais de deux : mélanger
deux dates dans les trois prises d'un même scénario ferait confondre la dispersion d'un
tirage avec l'écart entre deux enregistrements.

## Les comparaisons

| Fichier | La question qu'elle pose |
|---|---|
| `comparaison.v1-etape12-v1-partielle.md` | Une **borne supérieure** de la dérive du modèle entre deux dates, sur le même prompt |
| `comparaison.v1-base-v2.md` | L'effet des **trois cibles** de `systeme.v2` |
| `comparaison.v2-machine.v1.md` | **L'orchestration seule** : agent avec outils contre machine à états |

⚠️ **`comparaison.v2-machine.v1.md` est la seule qui isole autre chose qu'un prompt.**
Le catalogue, le moteur, le scoring, la couche outils et le validateur sont identiques des
deux côtés ; le prompt ne diffère que des trois sections passées dans le code. Ce qui reste
est l'orchestration. ⚠️ **Les onze scénarios ont été écrits pour l'agent à l'étape 12**,
avant que la machine soit envisagée : la suite n'est truquée dans aucun des deux sens, et
c'est vrai que la machine y gagne ou qu'elle y perde.

🔴 **Depuis l'étape 18, elle ne porte plus que sur 9 scénarios sur 11.** `changement_davis`
et `desserrage_refuse` ont quitté le rejeu du côté machine, et ils portaient l'écart qui
faisait le verdict de l'étape 15. Le fichier le dit lui-même en tête — la réduction aux scénarios communs et
l'avertissement « l'exclusion n'est pas neutre » sont **écrits par le harnais**, pas rédigés
à la main. Lire `PROJET.md` §5 étape 15 avant d'en tirer une conclusion : le verdict y est
**suspendu**, et le tableau ci-dessous ne le remplace pas.

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

La machine se rejoue en nommant **sa version de prompt**, qui désigne son jeu :

```bash
RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval   # ⚠️ sort en code 2, et c'est attendu
make eval-comparer AVANT=v2 APRES=machine.v1 Q="ce que la comparaison cherche"
```

🔴 **Le rejeu du jeu machine sort en code non nul, et ce n'est pas une régression.** Trois
attentes de scénario ne sont pas tenues, sur deux prises — `categorie_efface_budget.2`
(`budget_efface`) et `sur_specifie.3` (`zero_resultat` et le diagnostic attendu). Les deux
décrivent l'**extraction atomique** de la machine, §7. Ce sont des résultats de la campagne
de l'étape 15, publiés comme tels. Le rapport est écrit avant la sortie en erreur : il se lit
normalement.

⚠️ **`RAIYON_ORCHESTRATION` est sans effet au rejeu, et c'est voulu** : l'orchestration se
lit dans l'en-tête de **chaque cassette**, parce que celle qui a enregistré une prise est la
seule qui puisse la rejouer — l'autre diverge au premier tour. Le choix n'existe pas au
rejeu, il est enregistré ; la variable ne sert qu'à `make eval-enregistrer`.

C'est ce qui permet à la comparaison de rejouer **deux orchestrations dans un même
processus**, comme elle rejoue déjà deux prompts : une variable d'environnement n'a qu'une
valeur, un en-tête de cassette en a une par prise.
