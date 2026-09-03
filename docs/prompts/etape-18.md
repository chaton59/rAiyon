# Prompt Claude Code — Étape 18 : deux règles qui ne peuvent pas être satisfaites ensemble

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.
> Point de départ : étape 17 close et committée, `make check` vert à 1015.
> **Zéro appel API dans ce prompt.** Le jalon 2, qui en coûte ~176, n'est pas ici : il
> est décrit à la fin pour que la décision se prenne avec le chiffre sous les yeux, et il
> ne se lance pas sans arbitrage.

---

## Le défaut, trouvé en conversation réelle

Un client demande une comparaison entre deux cartes graphiques **au-dessus de son budget**.
Le texte est refusé deux fois, le tour se clôt sur un repli. Les deux griefs se
contredisent :

* `ecart_non_dit` : « le citer exige de dire qu'il dépasse et **de combien** — 11.59 $
  exactement, tel que `ecart_usd` le donne » ;
* `montant_non_fourni` sur « 11,59 $ » : « **aucun outil n'a rendu ce montant** dans cette
  conversation ».

Une règle réclame le chiffre, l'autre affirme qu'il n'existe pas.

### Le mécanisme, à vérifier dans `regles.py` avant de corriger

Les deux règles raisonnent `for phrase in phrases(texte)`, et `SEPARATEURS_DE_PHRASE`
traite le **saut de ligne** comme une fin de phrase.

* `regle_ecart_au_budget` : toute phrase qui **nomme** un produit de `hors_budget` doit
  contenir son écart ;
* `regle_montants`, branche `else` (la phrase ne nomme aucun produit) : le montant doit
  appartenir à `prix.values() | agregats | valeurs_refusees`. **`hors_budget.values()` n'y
  est pas.**

Dès que le nom et l'écart tombent dans deux phrases, la première prend `ecart_non_dit` et
la seconde `montant_non_fourni`. Et la section 14 du prompt demande **un produit par
ligne** : elle pousse vers ce découpage dès qu'on compare deux produits avec leurs specs.

Aggravation : la règle 4 exige l'écart dans **chaque** phrase qui nomme le produit. Dans
une comparaison, un produit est nommé trois ou quatre fois — donc trois ou quatre griefs,
et deux régénérations qui n'ont aucune chance d'aboutir.

---

## A. Correction 1 — l'écart est un montant fourni

Dans la branche `else` de `regle_montants`, ajoute `set(contexte.hors_budget.values())` aux
montants admis.

**Non discutable** : un écart est produit par le moteur, et le message de grief « aucun
outil n'a rendu ce montant » est **faux** sur son propre terrain.

L'argument de sûreté, à écrire dans le commentaire : cette branche admet déjà
`valeurs_refusees`, qui sont **écrites par le modèle** (§7, ligne « une valeur de mouvement
refusé est écrite par le modèle, pas par le moteur »). Admettre des écarts **écrits par le
moteur** est strictement plus sûr que ce qui s'y trouve déjà.

⚠️ **Ne touche pas à la branche `if nommes:`.** Le piège nº6 de `tests/validateur/test_pieges.py`
porte sur une phrase **avec** produit et doit rester exactement aussi strict — c'est le seul
test qui échoue si quelqu'un aplatit le contexte, et il ne doit pas cesser de l'être.

---

## B. Correction 2 — l'écart se dit une fois par message, pas par phrase

`regle_ecart_au_budget` cesse de raisonner par phrase pour la **présence** de l'écart : un
produit de `hors_budget` nommé dans le message doit avoir son écart cité **quelque part
dans ce message**. Le grief reste attaché à la première phrase qui nomme le produit, pour
que la reprise reste lisible.

**C'est un desserrage réel, et il s'arbitre :** le critère d'acceptation nº2 dit « budget
jamais dépassé sans **présentation explicite** ». Le dire une fois *est* la présentation.
L'exiger à chaque phrase est un artefact du découpage — dont §7 dit déjà qu'il « devient
trop **étroit**, jamais trop large ». Ici l'étroitesse ne se contente pas de rater : elle
**fabrique une contrainte impossible à satisfaire**, ce que §7 n'avait pas envisagé.
Ajoute cette phrase à la ligne de §7 sur le découpage en phrases.

### Les trois tests qui bornent le desserrage

1. **Le cas de terrain** : un message où le produit hors budget est nommé dans une phrase et
   son écart donné dans la suivante → **aucun grief**. C'est ce qui bloquait.
2. **Le critère nº2 tient** : un message qui nomme un produit hors budget et ne donne son
   écart **nulle part** → `ecart_non_dit`. Le desserrage ne doit pas devenir une exemption.
3. **Le piège de la contamination** : un message qui donne l'écart du produit A et nomme le
   produit B, hors budget, sans le sien → grief **sur B**. La vérification reste par
   identifiant ; c'est le test qui empêche qu'un écart quelconque satisfasse tout le monde.

---

## C. ⚠️ Ce qu'il faut mesurer, et rapporter avant de conclure

Ce correctif n'est **pas** de la même famille que celui de `NOMBRE` à l'étape 17, et il
faut le savoir avant de lancer quoi que ce soit.

`ecart_non_dit` a tiré **24 fois** dans la campagne `machine.v1`, et c'est le seul écart
au-delà de la dispersion — **le résultat sur lequel repose tout le verdict de l'étape 15**.
Deux conséquences :

1. **Une part de ces 24 pourrait être un artefact de validateur, pas un fait
   d'orchestration.** Si c'est le cas, le verdict de l'étape 15 est à relire.
2. **La mesure est en partie auto-annulante**, et c'est le piège de cette étape : les prises
   qui portaient ces rejets sont précisément celles dont la liste de griefs change, donc dont
   la reprise change, donc l'empreinte de requête — elles **divergent** au rejeu et sortent
   du rapport. Le « après » se mesurerait alors sur un sous-ensemble, et la soustraction des
   totaux ne voudrait rien dire. C'est déjà la nuance que l'étape 17 a dû écrire sur deux
   griefs ; ici l'échelle est tout autre.

**Ce qu'on fait donc, dans l'ordre :**

```bash
unset ANTHROPIC_API_KEY
make check
make eval                                          # v2 — ecart_non_dit y valait 0
make eval-etape12
RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval  # le jeu exposé
```

Et on **rapporte, avant de commiter les rapports** :

* combien de cassettes divergent, **jeu par jeu**, avec leurs noms ;
* combien de prises consomment moins de prises qu'enregistré (le texte n'est plus refusé,
  donc plus de régénération) ;
* le nouveau compte de griefs sur ce qui reste rejouable, **et l'avertissement explicite que
  ce compte porte sur un sous-ensemble** si des prises sont écartées.

Le jeu `v2` devrait être quasi indemne — `ecart_non_dit` y valait **0**. Le jeu
`machine.v1` est celui qui peut souffrir.

---

## D. Ce que le dépôt doit dire, quel que soit le chiffre

Le correctif se livre : le produit est aujourd'hui **inutilisable** pour une demande
courante — comparer deux produits au-dessus du budget —, et c'est un défaut plus grave
qu'un rapport partiel.

Mais il ne se livre pas en silence. Écris, à ces trois endroits :

1. **`docs/eval/rapport.machine.v1.md` et `comparaison.v2-machine.v1.md`** : les prises
   écartées, et une phrase disant que le total de griefs porte sur ce qui reste ;
2. **`PROJET.md` §5 étape 15** : le verdict est **suspendu sur sa mesure principale**, avec
   la raison — l'unique écart au-delà de la dispersion portait un code dont une part était
   un artefact de validateur, découvert après la campagne, en conversation réelle. **Ne
   réécris pas le verdict**, et ne prétends pas savoir ce qu'il deviendra : dis ce qui est
   su et ce qui ne l'est pas ;
3. **`PROJET.md` §7**, une ligne nouvelle : *deux règles du validateur pouvaient être
   conjointement insatisfaisables à la granularité de la phrase*. Gravité **élevée** — elle
   rendait un chemin nominal du produit impossible —, fermée par cette étape, et **trouvée
   en conversation réelle, par aucune commande automatique**. C'est le second défaut du
   projet trouvé ainsi, après celui de `eval-live` à l'étape 12 : la ligne le dit, parce que
   deux occurrences ne sont plus une anecdote.

⚠️ **Et la ligne du README sur les codes dormants change encore.** Elle disait
`ecart_non_dit` jamais déclenché, l'étape 15 l'a corrigée en disant 24 fois chez la
machine. Il faut maintenant y ajouter qu'une part de ces déclenchements était un faux
positif. Un compteur qui monte n'est pas une preuve que la règle est juste.

---

## Porte de sortie

```bash
make check                              # vert, ≥ 1015 + les trois tests du point B
make test-int                           # 98
unset ANTHROPIC_API_KEY
make eval && make eval-etape12
RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval
git status --short
```

1. **Aucun fichier sous `evals/cassettes/`.** Ce jalon ne réenregistre rien.
2. Le cas de terrain passe : le test 1 du point B est la reproduction exacte de ce qui
   bloquait.
3. `DIVERGENCES_ATTENDUES` porte une entrée par cassette qui diverge, avec sa raison
   complète — c'est une **assertion**, pas un skip.
4. Les trois documents du point D disent ce qu'ils ne savent pas.

Commit à la fin.

---

## Le jalon 2, qui n'est pas dans ce prompt

Si le rejeu montre que plusieurs cassettes de `machine.v1` divergent, la seule façon de
savoir **ce que valait réellement le verdict de l'étape 15** est de réenregistrer le jeu de
la machine sous le validateur corrigé : ~176 appels.

C'est un arbitrage de budget, et il se prend avec le nombre de divergences sous les yeux —
pas maintenant. **Ne le lance pas.** Rapporte le chiffre, et arrête-toi là.
