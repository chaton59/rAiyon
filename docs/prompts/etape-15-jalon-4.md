# Prompt Claude Code — Étape 15, jalon 4 : le tir d'essai

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.
> Point de départ : jalon 3 committé, arbre propre, `make check` vert à 1002.
> **Budget : ~18 appels.** Pas un de plus. Si tu es tenté d'en dépenser davantage,
> arrête-toi et dis-le — la campagne est au jalon 5, et elle a son propre budget.

---

## Pourquoi un tir d'essai

La campagne coûte ~170 appels et c'est le seul enregistrement du projet qui n'a **aucun
antécédent** : la machine n'a jamais produit une cassette. Un défaut de mécanique
découvert au rejeu de la campagne coûterait un réenregistrement complet — le plafond
entier de l'étape, consommé pour une faute qu'une douzaine d'appels auraient montrée.

C'est le motif de `make fumee`, qui mesure ce que l'API accepte du schéma d'outils **avant**
que la boucle en dépende. Il existe déjà dans le dépôt ; celui-ci en est la reprise.

---

## A. Ce qu'on enregistre, et pourquoi deux scénarios plutôt qu'un

```bash
RAIYON_ORCHESTRATION=machine RAIYON_PROMPT_SYSTEME=systeme.machine.v1 \
  make eval-enregistrer SCENARIO=hors_catalogue        # 3 prises x 2 tours ≈ 12 appels

RAIYON_ORCHESTRATION=machine RAIYON_PROMPT_SYSTEME=systeme.machine.v1 \
  make eval-enregistrer SCENARIO=budget_serre          # ≈ 6 appels
```

**`hors_catalogue` est le bon scénario pour éprouver la mécanique** : deux tours, une
catégorie absente du catalogue, et il met `decider()` devant un état qu'aucun test de
conduite n'a construit. C'est un bord, et les bords cassent.

⚠️ **C'est en revanche le pire échantillon possible pour lire un coût, et il faut le savoir
avant de voir le chiffre.** L'agent y consomme **1,00 appel par tour** — 6 appels pour 6
tours —, son minimum absolu : il répond « je n'ai pas cette catégorie » en un appel, sans
outil. La machine paie son plancher de 2,00. **Elle y sera deux fois plus chère, et ce
n'est pas le résultat de la campagne** : sur l'ensemble, l'agent est à 2,36 et varie de
1,00 (`hors_catalogue`) à 3,33 (`desserrage_refuse`).

`budget_serre` est ajouté pour cette raison : l'agent y est à **2,17 appel/tour**, une
valeur ordinaire. Il exerce aussi ce que `hors_catalogue` n'exerce pas — `ProduitsTrouves`,
une recommandation, le chemin du validateur.

Si tu veux économiser six appels, retire `budget_serre` — mais alors **n'écris aucune
conclusion sur le coût**, parce que l'échantillon restant est l'aberration de la suite.

---

## B. ⚠️ Le rapport ne sera pas écrit, et c'est correct

`_prises_manquantes()` refuse d'écrire `docs/eval/rapport.machine.v1.md` tant que le jeu
est incomplet. Le texte du rapport **est produit et s'affiche**, le fichier n'est pas créé.

C'est une garde de l'étape 13, écrite après que la campagne v1 s'est arrêtée à 21 prises
sur 36 sans que rien ne le dise :

> « Un rapport écrit depuis un jeu incomplet est un faux, et il ne s'annonce pas comme
> tel : le tableau a la même forme, les critères sont verts, et rien ne dit que quatre
> scénarios sur onze n'ont pas été joués. »

**Ne la contourne pas, ne l'assouplis pas, n'ajoute pas d'option.** Le tir d'essai vérifie
que le texte se **produit**, pas qu'un fichier apparaît. Un fichier `rapport.machine.v1.md`
dans `git status` à la fin de ce jalon est un échec du jalon.

---

## C. Ce qu'on vérifie sur les cassettes produites

Ouvre l'une des cassettes et constate, à l'œil :

| Champ | Valeur attendue |
|---|---|
| `orchestration` | `machine` — le champ du jalon 0, renseigné pour la première fois |
| `prompt_version` | `systeme.machine.v1` |
| `prompt_empreinte` | `595d66d5383e` — celle du jalon 3, pas `61b474af9184` |
| `outils_empreinte` | **différente** de celle de l'agent (`ae1370a553ae`) : un outil au lieu de cinq |
| `usage` | présent, avec ses cinq compteurs |

C'est le contrôle que la garde du jalon 0 **ne peut pas faire** : elle compare le jeu visé
à ce qu'il contient déjà, et un répertoire vide ne contient rien. Ce tableau est ce qui
couvre la première campagne, et c'est la raison d'être du jalon.

---

## D. Le rejeu, qui est le vrai test

```bash
unset ANTHROPIC_API_KEY
RAIYON_ORCHESTRATION=machine RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval
```

Ce qui doit se produire :

1. **aucune `DivergenceDeRequete`** — le rejeu reconstruit exactement les requêtes de
   l'enregistrement. C'est ce qui prouve que l'orchestrateur est déterministe à réponses
   du modèle fixées ;
2. **aucun « prise(s) consommée(s) sur N »** — la conversation rejouée a la même longueur ;
3. **les métriques sortent**, et les attentes du scénario sont **évaluées**. Une attente
   qui ne serait ni tenue ni manquée mais simplement absente signalerait que la machine
   n'émet pas l'événement qui la porte — c'est le signal du point E du jalon 2, et il
   s'arrête là ;
4. le message « jeu incomplet » sur `stderr`, et **aucun fichier écrit** (point B).

⚠️ **Un critère bloquant violé ici est un résultat, pas un bug** — c'est la règle que tu as
posée : `IssueDuTour` bien formé, donc ce que les métriques disent se publie. Ne corrige
rien pour faire verdir un chiffre. Rapporte-le tel quel : c'est peut-être la première
chose que la campagne allait mesurer.

Ce qui est un bug, et qui justifie une correction : une exception, un `tool_use` orphelin,
une divergence de requête, un état qui ne se réenchaîne pas.

---

## E. Ce qu'on note, sans en tirer de conclusion

Trois nombres, dans le compte rendu et **pas** dans un fichier committé :

* **appels par tour** de la machine sur ces deux scénarios, en face des 1,00 et 2,17 de
  l'agent — avec la réserve du point A écrite au-dessus, pas en dessous ;
* **`cache_ecrit` et `jetons_entree`**, pour éprouver la prédiction du jalon 3 : deux
  préfixes distincts au lieu d'un, donc un cache moins efficace. Sur deux scénarios ce
  n'est pas une mesure, c'est un ordre de grandeur — et il dira si l'écart est de 10 % ou
  d'un facteur deux, ce qui change ce qu'on écrira au jalon 5 ;
* **le nombre d'itérations** de `decider()` par tour, pour vérifier que la borne
  `max_iterations` n'a jamais mordu.

---

## Porte de sortie

```bash
make check                      # vert à 1002, inchangé — ce jalon n'écrit pas de code
git status --short
```

1. `evals/cassettes/systeme.machine.v1/` contient **4 cassettes** (3 + 1), toutes avec
   l'en-tête du point C ;
2. **aucun fichier sous `docs/eval/`** — le rapport n'est pas écrit (point B) ;
3. `make check` inchangé : si tu as dû écrire du code, dis lequel et pourquoi, parce que ce
   jalon n'en prévoit aucun ;
4. **`make eval` de l'agent inchangé** : `RAIYON_ORCHESTRATION` et `RAIYON_PROMPT_SYSTEME`
   remis à leurs défauts, `make eval` rejoue v2 à l'identique.

Commit des cassettes à la fin — elles seront écrasées par la campagne, et les commiter
maintenant rend le tir d'essai relisible s'il faut y revenir.

---

## Si ça casse

Corrige, **réenregistre les deux scénarios seulement**, et recommence ce jalon. Ce sont 18
appels, c'est le prix prévu, et c'est très exactement à quoi le tir d'essai sert.

Ce qu'il ne faut pas faire : passer à la campagne « pour voir », ou élargir le tir d'essai
scénario par scénario jusqu'à l'avoir payée deux fois.

---

## Ce que ce jalon ne décide pas

* Les prédictions dans `PREDICTIONS` — jalon 5, **avant** l'enregistrement, jamais après ;
* la campagne elle-même ;
* la dette des six helpers privés de `boucle.py` — après la campagne.
