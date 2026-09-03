# Prompt Claude Code — Étape 16, consolidation : deux jalons gratuits

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.
> Point de départ : étape 15 close et committée, `make check` vert à 1002.
> **Zéro appel API sur les deux jalons.** Un seul jalon à la fois : le premier se commit
> avant que le second commence, et sa preuve de neutralité en dépend.

---

## Le cadrage

C'est l'**étape de consolidation** — celle qui était l'alternative nº2 à l'étape 15, et
qui referme ce que le dépôt s'est engagé à traiter. Trois dettes ; les deux premières ne
coûtent rien et sont ici. La troisième — le correctif de `NOMBRE` et la dette nº1 de
l'étape 8 — demande une campagne et se décide à part.

Ajoute `### Étape 16 — Consolidation` à `PROJET.md` §5 au premier jalon, et coche-la au
second.

---

# Jalon 1 — Le contrat partagé sort de l'agent

## Ce qui ne va pas, et c'est plus large que la ligne de dette

§7 dit « l'orchestrateur importe six helpers privés de `boucle.py` ». **Le couplage réel est
de douze noms, et le plus structurant est public.**

`src/raiyon/orchestration.py` — le module **neutre**, celui qui porte le `Protocol`
`Orchestrateur` et `repondre_en_vigueur()` — fait :

```python
from raiyon.agent.boucle import IssueDuTour, repondre
```

**Le contrat commun aux deux orchestrations est donc défini à l'intérieur de l'une
d'elles.** `machine/orchestrateur.py` importe les douze noms au même endroit : six privés
(`_ajouter_les_resultats`, `_bloc_tool_result`, `_catalogue_de`, `_depouiller`,
`_empiler_la_reprise`, `_evenement_de`) et six publics (`IssueDuTour`, `TourProduit`,
`ROLE_ASSISTANT`, `ROLE_CLIENT`, `PHRASE_DE_REPLI`, `PHRASE_REPONSE_VIDE`).

Ne déplacer que les six privés laisserait `machine/` dépendre d'`agent/` pour son **type de
retour** et ses constantes de rôle — le même couplage portant un nom public. Corrige-le en
entier ou pas du tout.

## La forme

`src/raiyon/orchestration.py` devient un paquet `src/raiyon/orchestration/` :

| Module | Contenu |
|---|---|
| `__init__.py` | `Orchestrateur` et `repondre_en_vigueur()` — inchangés |
| `contrat.py` | `IssueDuTour`, `TourProduit`, les deux rôles, les deux phrases de repli |
| `blocs.py` | les six helpers, **rendus publics** puisqu'ils ont désormais deux appelants |

`from raiyon.orchestration import repondre_en_vigueur` continue de résoudre : `session.py`
ne change pas.

⚠️ **Le piège de circularité, à traiter dès la première ligne** : `__init__.py` importe
`agent.boucle` et `machine.orchestrateur`, qui importeront tous deux
`orchestration.contrat`. Les sous-modules ne doivent **jamais** importer le paquet
`__init__` — seulement `orchestration.contrat` et `orchestration.blocs`. Une importation
circulaire ici casse tout ce qui charge `raiyon`, y compris `make check`.

## Ce que ce jalon n'est pas

**Un refactor de comportement.** Aucune logique ne change, aucun invariant ne se déplace,
aucun message de log ne se reformule. Les fonctions sont déplacées et renommées (le `_`
tombe), rien de plus.

Si tu vois quelque chose à améliorer en passant — **ne le fais pas**. Écris-le dans le
compte rendu. Un refactor qui corrige au passage n'est plus vérifiable par la propriété
ci-dessous.

## Porte de sortie — la preuve est dans ce qui ne bouge pas

```bash
make check                              # vert à 1002, le même compte, pas un de plus
make test-int                           # 98
unset ANTHROPIC_API_KEY
make eval                                                        # v2
make eval-etape12                                                # l'archive
RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval               # la machine
make eval-comparer AVANT=v1-base APRES=v2 Q="l'effet des trois cibles de systeme.v2, cible par cible"
make eval-comparer AVANT=v2 APRES=machine.v1 Q="l'orchestration seule : agent avec outils contre machine à états, à catalogue, moteur, couche outils et validateur identiques"
git status --short
```

1. **Aucun fichier de `docs/eval/` ne bouge.** Les cinq documents se régénèrent à
   l'identique. C'est la preuve non déclarative que le déplacement est neutre, et elle
   couvre les deux orchestrations à la fois.
2. `make check` rend **exactement** 1002. Un test de plus voudrait dire qu'on a ajouté du
   comportement ; un de moins, qu'on en a perdu.
3. Rien sous `prompts/`, `evals/cassettes/`, `tools/`, `matching/`, `validateur/`.
4. §7 : la ligne de dette passe **fermée**, en disant que le couplage réel était de douze
   noms et non de six, et que le module neutre dépendait de l'agent.

Commit. **Le jalon 2 ne commence pas avant.**

---

# Jalon 2 — La mesure nº7 publie les jetons

## Le défaut, et il est de spécification

La mesure nº7 a été spécifiée au jalon 0 de l'étape 15 sur `entete.usage.appels`, **avant
qu'on sache que le compte d'appels dirait l'inverse du coût réel**. La campagne l'a montré :
la machine fait **2,17 appel/tour contre 2,36** — moins — et coûte **×1,80 d'entrée
facturée**, 663 347 contre 367 832 jetons.

Le rapport ne publie que les appels. Un lecteur qui ouvre `rapport.machine.v1.md` dans six
mois lit « moins d'appels » et conclut « moins chère ». **La conclusion inverse est la
vraie**, et elle ne vit aujourd'hui que dans le README et `PROJET.md`, sommée à la main.

C'est une erreur de ma spécification, pas de son implémentation. Écris-le à l'endroit où
la mesure est définie.

## Ce qu'il faut ajouter

`Usage` sait déjà s'additionner (`__add__`), et `mesurer_le_jeu()` lit déjà chaque en-tête.
La mesure nº7 publie désormais, par jeu :

* les **appels par tour**, comme aujourd'hui ;
* les **jetons d'entrée facturés** — entrée non cachée + cache écrit, c'est-à-dire ce qui
  se paie —, et le **cache lu** à côté, qui ne se paie pas au même tarif ;
* les **jetons de sortie**.

Et une phrase, à côté du tableau, qui dit **pourquoi les deux moitiés existent** : une
orchestration peut faire moins d'appels et coûter plus cher, c'est arrivé, et c'est ce que
la campagne de l'étape 15 a mesuré.

⚠️ **La règle du tout ou rien du jalon 0 ne bouge pas** : rien n'est publié si une seule
prise du jeu n'a pas d'`usage`. `v1-etape12` (0/19) et `v1-base` (3/31) continuent
d'afficher « non disponible ». Ne l'assouplis pas pour faire apparaître un chiffre.

`comparaison.py` publie l'écart sur les jetons quand les deux jeux les portent, **sans
verdict de dispersion** — un coût gelé à l'enregistrement n'a pas de dispersion, et un
verdict calculé dessus serait faux. C'est déjà la règle pour les appels.

## Porte de sortie

```bash
make check
unset ANTHROPIC_API_KEY
make eval && make eval-etape12
RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval
make eval-comparer AVANT=v1-base APRES=v2 Q="l'effet des trois cibles de systeme.v2, cible par cible"
make eval-comparer AVANT=v2 APRES=machine.v1 Q="l'orchestration seule : agent avec outils contre machine à états, à catalogue, moteur, couche outils et validateur identiques"
git diff --stat docs/eval/
```

1. Les cinq documents ne changent **que** par les lignes de jetons. Aucun autre chiffre ne
   bouge — c'est le même contrôle de neutralité qu'au jalon 0 de l'étape 15.
2. Les 367 832 et 663 347 du README et de `PROJET.md` se retrouvent désormais **dans les
   rapports**. Remplace, aux deux endroits, la note « sommés à la main sur les en-têtes »
   par un renvoi au rapport : le chiffre a maintenant une source committée.
3. Rien sous `evals/cassettes/`.

Commit, et coche `Étape 16 ✅` dans §5.

---

## Ce qui reste, et qui n'est pas dans ce prompt

**Le correctif de `NOMBRE` et la dette nº1 de l'étape 8.** Les deux seules dettes que le
dépôt s'est explicitement engagé à traiter, toutes deux promises « dans une version à un
seul changement, avec la campagne qu'elle attend ».

Elles sont **désormais possibles** — v2 n'est plus une ligne de base en cours d'usage — et
elles coûtent : deux campagnes séparées (~380 appels) pour tenir la promesse d'attribution,
une seule (~190) en y renonçant explicitement.

⚠️ **Ne les commence pas.** C'est un arbitrage de budget, il se prend avant et pas pendant,
et il n'appartient pas à ce prompt.
