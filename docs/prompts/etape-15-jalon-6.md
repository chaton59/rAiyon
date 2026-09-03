# Prompt Claude Code — Étape 15, jalon 6 : la clôture

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.
> Point de départ : jalon 5 committé, `rapport.machine.v1.md` et
> `comparaison.v2-machine.v1.md` écrits, `make check` vert à 1002.
> **Zéro appel API.** Ce jalon écrit de la documentation et rien d'autre.

---

## Règle générale : aucun chiffre n'est retapé

Tout nombre qui entre dans `PROJET.md` ou `README.md` vient des rapports committés. Si tu
dois en recalculer un, dis-le et dis d'où il sort. Un tableau de README recomposé à la
main diverge de son rapport en six mois, et c'est le dépôt qui aura tort.

**Interdits** : `prompts/`, `evals/cassettes/`, `src/` sauf mention explicite ci-dessous.

---

## A. `PROJET.md` §3.6 — la décision est confirmée, et pour des raisons mesurées

§3.6 écarte la machine à états sur un argument, et écrit ce que le choix de l'agent
coûte : « la testabilité par tests unitaires rapides disparaît ». **Les deux moitiés sont
maintenant mesurées.** Amende la section — sans réécrire la décision, qui ne change pas —
avec un encadré daté qui dit :

* **la machine à états a été écrite, mesurée sur la même suite, et elle ne gagne pas.**
  Un seul écart dépasse la dispersion, et c'est elle qui le perd : rejets du validateur
  2,00 → 17,00 par passe (±12,00), dominés par `ecart_non_dit`, 0 → 24 ;
* **le coût qu'elle rembourse est réel mais étroit** : 17 tests de conduite du dialogue
  dans `make check` contre 0, et ~8 % d'appels en moins (2,17 contre 2,36 par tour) ;
* **le coût qu'elle ajoute ne l'était pas** : ×1,80 d'entrée facturée, 663 347 contre
  367 832 jetons. Une orchestration qui fait moins d'appels et coûte presque le double ;
* **l'argument original de §3.6 est validé par un mécanisme qu'il ne nommait pas.**
  « L'agent encaisse naturellement les virages » désignait une intuition ; ce qu'on
  observe est précis — voir la ligne de §7 sur l'extraction atomique.

⚠️ **N'écris pas que l'agent « gagne ».** Écris où chacune gagne. La machine gagne la
testabilité de sa décision et un invariant rendu explicite ; elle perd la rédaction et le
coût d'entrée.

---

## B. `PROJET.md` §5 — l'étape 15, close

`### Étape 15 — Variante machine à états ✅`, sur la forme des étapes précédentes : ce que
l'étape a livré, les arbitrages avec leur alternative, et **ce qu'elle a appris et qui
n'était pas prévu**.

Les arbitrages à porter, avec l'alternative écartée pour chacun : ce que la machine
partage (tout sauf la conduite) ; le prompt dérivé par soustraction pure ; l'axe d'identité
des cassettes resté sur la version de prompt ; aucun scénario ajouté ; le tir d'essai avant
la campagne ; l'historique donné à la rédaction.

La section « ce que l'étape a appris » porte au minimum les quatre points de C, D et E
ci-dessous.

---

## C. Ce que l'étape a appris — et qui n'était pas prévu

**1. `ecart_non_dit` n'était pas une règle dormante. Elle n'avait jamais été sollicitée.**
Le README déclare que trois codes sur six ne se déclenchent jamais sur cette suite. La
machine en fait tirer un **24 fois**. Une règle qui ne tire jamais est indistinguable d'une
règle absente — c'est écrit dans le dépôt depuis l'étape 12 — et il aura fallu une seconde
orchestration pour distinguer. **Ce que cela dit des deux autres** (`id_inconnu`,
`nom_reecrit`) est ouvert et doit être écrit comme ouvert : ils restent non sollicités, pas
démontrés morts.

**2. Les 24 rejets sont la preuve que le validateur porte, pas qu'il a échoué.** Les
critères nº1 et nº2 tiennent **des deux côtés**, et ils tiennent parce que le texte fautif a
été refusé avant d'être livré. Le filet est décoratif chez l'agent — 2 rejets par passe — et
**porteur** chez la machine. C'est §3.11 (« les garanties ne vivent pas dans
l'orchestration, elles vivent dans les outils ») vérifié dans une direction que personne
n'avait prévue : la garantie a tenu sous une orchestration pour laquelle elle n'avait pas
été conçue.

**3. Une prédiction en deux moitiés qui vont en sens contraire.** 2,17 appel/tour contre
2,36, et ×1,80 d'entrée facturée. Publier les appels seuls aurait dit « moins chère » d'une
orchestration qui coûte presque le double. La mesure nº7 publie les deux, et la raison est
ici.

**4. Trois attentes de scénario non tenues, et `make eval` sort en code non nul sur le jeu
de la machine.** Le tableau ne le montre pas ; le rapport, si. C'est un **résultat** —
`IssueDuTour` bien formé, rejeu sans divergence — et non un défaut, selon la règle posée
avant la campagne.

---

## D. `PROJET.md` §7 — les lignes qui bougent, et celles qui apparaissent

**Une ligne passe à moitié fermée :**

> ~~**Le faux client teste la boucle, pas le modèle**~~ → **à moitié fermée à l'étape 15**

Fermée du côté de la machine : `decider()` est pure, et 17 tests de conduite du dialogue
tournent dans `make check` sans base, sans conteneur et sans clé. **Ouverte du côté de
l'agent**, où elle l'était et le reste — il n'y a toujours aucune fonction de décision à
assertionner. La ligne est barrée à moitié, pas éteinte.

⚠️ **La réserve voyage avec le chiffre**, ici comme partout :

> Ces tests vérifient que la machine conduit le dialogue **comme on l'a écrit**. Ils ne
> vérifient pas que la conduite est bonne, ni que le modèle qui rédige derrière respecte
> quoi que ce soit.

**Quatre lignes nouvelles :**

1. **L'extraction est atomique, et une extraction manquée ne se rattrape pas dans le tour.**
   Gravité moyenne, **propre à la machine**, non corrigée volontairement. Le mécanisme,
   observé sur `sur_specifie.3` : l'extraction pose `panel_type` en `bloquant`, la couche
   outils refuse (§3.4quater), et **l'appel étant atomique, la taille, la fréquence et le
   budget sont perdus avec lui**. L'agent lit le refus dans son `tool_result` et rappelle
   l'outil en `important` — c'est dans sa cassette. La machine ne peut pas :
   `enregistrer_criteres` n'est pas une action de `decider()`. Même famille par omission sur
   `categorie_efface_budget.2`, où la prose annonce au client que son budget ne s'applique
   plus tandis que l'état l'ignore. *Correctif écarté et daté* : laisser `decider()`
   redéclencher une extraction ajoute un appel modèle, casse le plancher de 2,00 et change
   le coût au milieu de la comparaison. Candidat pour une `systeme.machine.v2` que cette
   étape ne fait pas.
2. **« Ne pas chercher tant que le budget manque » n'est écrite dans aucun prompt.**
   L'agent la tient par l'affordance de `question_suivante`, qui remonte `BesoinDeBudget` en
   tête ; `Attente.AUCUNE_RECHERCHE_SANS_BUDGET` la mesure depuis l'étape 12 sans que
   personne ait remarqué qu'aucune instruction ne la portait. `decider()` l'écrit pour la
   première fois. **Écrire la seconde orchestration était la seule façon de s'en
   apercevoir**, et c'est l'argument le plus fort en faveur d'avoir fait l'étape.
3. **L'orchestrateur importe six helpers privés de `boucle.py`.** Dette assumée, écrite au
   jalon 2. Les dupliquer donnerait deux rédactions de la forme des blocs et de l'invariant
   de reprise — la maladie de la dette nº1. Les extraire touche `boucle.py`, ce que l'étape
   s'interdisait pour garder `make eval` inchangé comme preuve non déclarative. **À solder
   maintenant que la campagne est passée.**
4. **`RAIYON_ORCHESTRATION` n'a plus d'effet au rejeu**, depuis le correctif du jalon 5 :
   l'orchestration voyage par valeur dans `Reglages` et se lit dans l'en-tête de chaque
   cassette. C'est un changement de comportement d'une variable documentée — il se dit, avec
   sa raison : `comparer` rejoue deux jeux dans un processus, et un choix lu dans
   l'environnement y ferait partir les cassettes de la machine dans la boucle de l'agent.
   Le champ que le jalon 0 avait écrit sans le consommer est devenu la source de vérité.

---

## E. `README.md`

1. **La ligne des codes de grief dormants est fausse et doit changer.** Elle dit que
   `id_inconnu`, `nom_reecrit` et `ecart_non_dit` ne se déclenchent jamais. C'est vrai de
   l'agent, faux du projet : la machine fait tirer `ecart_non_dit` 24 fois. Réécris-la en
   nommant l'orchestration à chaque fois, et garde le raisonnement d'origine — une règle qui
   ne tire jamais est indistinguable d'une règle absente — qui est **renforcé**, pas
   affaibli, par ce qui vient d'arriver.
2. **Les deux orchestrations : comment lancer chacune**, avec la paire de variables
   (`RAIYON_ORCHESTRATION` et `RAIYON_PROMPT_SYSTEME`), et le fait que `RAIYON_ORCHESTRATION`
   ne vaut qu'à l'enregistrement et à la conversation, pas au rejeu.
3. **Le tableau de métriques à deux colonnes**, chiffres repris des rapports committés, avec
   les mesures nº7 (appels **et** jetons) et nº8 (17 contre 0, avec sa réserve).
4. **Le coût d'une campagne** : la ligne existante dit 36 prises et 191 appels. Ajoute celle
   de la machine à côté, et le fait que le tir d'essai a coûté 24 appels **non
   récupérables**, dépensés exprès.

---

## Porte de sortie

```bash
make check                              # vert à 1002, inchangé
unset ANTHROPIC_API_KEY && make eval    # les deux jeux rejouent, chacun le sien
git status --short
git diff --stat
```

1. Aucun fichier sous `prompts/`, `evals/cassettes/`, `src/`. Ce jalon est documentaire.
2. `docs/eval/` inchangé — les rapports ont été écrits au jalon 5 et ne se retouchent pas.
3. Chaque chiffre de `README.md` et de `PROJET.md` se retrouve dans un rapport committé.
4. §5 porte `Étape 15 ✅`, et §3.6 porte son encadré daté.

Commit à la fin. Message qui dit que l'étape est close et laquelle des deux orchestrations
gagne où — **pas** laquelle est meilleure.

---

## Ce qui reste après, et qui n'est plus l'étape 15

* la dette des six helpers privés (§7, ligne 3 ci-dessus) — première candidate, elle ne
  coûte aucun appel ;
* le correctif de `NOMBRE` et la dette nº1 de l'étape 8, dans leur version à un seul
  changement, avec la campagne qu'elles attendent — **maintenant possible** : v2 n'est plus
  une ligne de base en cours d'usage ;
* `systeme.machine.v2`, si l'extraction atomique valait qu'on y revienne ;
* la recherche hybride `pgvector` (§3.5), qui reste hors périmètre du produit livrable.
