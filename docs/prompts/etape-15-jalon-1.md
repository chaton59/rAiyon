# Prompt Claude Code — Étape 15, jalon 1 : `decider()`, et la mesure nº8

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.
> Point de départ : le jalon 0 committé, arbre propre, `make check` vert à 926.
> **Aucun appel API, aucun jeton, aucune base.** Ce jalon s'écrit et se vérifie hors ligne
> de bout en bout. Si tu as besoin de Postgres pour finir, tu as débordé.

---

## Ce que ce jalon livre, et pourquoi c'est la charge de l'étape

§3.6 a écarté la machine à états explicite, et il a écrit ce que ce choix coûtait :

> « La testabilité par tests unitaires rapides disparaît en grande partie : il n'y a plus
> de fonction de décision pure à assertionner. »

Ce jalon écrit exactement cette fonction. Elle est le cœur intellectuel de l'étape 15, et
**elle est indépendante du résultat de la campagne** : elle serait vraie même si la
campagne n'avait jamais lieu.

Elle donne aussi la **mesure nº8**, la seule de l'étape qui ne coûte aucun appel, ne
dépend d'aucun tirage, et sépare avec certitude : *combien de tests de conduite du
dialogue tournent dans `make check` chez l'une et chez l'autre.* Chez l'agent, zéro — §7
le dit déjà, ligne « le faux client teste la boucle, pas le modèle ». Chez la machine, le
nombre que tu écriras.

---

## Le périmètre, en négatif

**Ne touche pas** : `matching/`, `tools/`, `validateur/`, `agent/`, `api/`, `prompts/`,
`evals/cassettes/`, `scripts/eval.py`.

**N'écris pas l'orchestrateur.** Pas de générateur, pas d'`Evenement`, pas d'appel au
modèle, pas de persistance. Le jalon 2 branche ; celui-ci ne fait que la décision.

**N'écris pas `systeme.machine.v1.md`.** C'est le jalon 3. Ce jalon en produit la
**spécification** (section E), pas le fichier.

---

## A. La frontière, à écrire en premier dans le module

> **Le modèle extrait, le code décide.**

`decider()` ne reçoit **jamais de prose**. Ni le message du client, ni un texte du modèle,
ni une chaîne libre. Si elle recevait le texte du client, elle aurait besoin du modèle,
elle ne serait plus pure, et la mesure nº8 s'évaporerait avec elle.

Écris cette phrase en tête de la docstring du module, avec sa conséquence : c'est elle
qui achète tout le jalon.

---

## B. La forme

Nouveau paquet `src/raiyon/machine/`, module `decision.py`.

**Il n'importe rien de `raiyon.agent`, rien de `raiyon.db`, rien du SDK.** Ses seules
dépendances sont `raiyon.tools.etat` et `raiyon.tools.outils` pour les types. C'est une
propriété vérifiable, et tu la verrouilles avec le mécanisme qui existe déjà —
`MODULES_PURS` de `tests/api/test_isolation_api.py` et `tests/eval/test_isolation_eval.py`,
avec son test de couverture qui **échoue quand un module du paquet n'a pas été classé**.
Reprends les deux, pas seulement le premier.

### La signature

Entrée :

* `etat: EtatSession` — les critères déjà fusionnés, le budget, `recherche_du_tour`,
  `tour_du_dernier_desserrage` ;
* `dernier: ResultatOutil | None` — le résultat de l'action précédente **dans ce même
  tour** ; `None` au premier passage.

Sortie : une union fermée d'actions, chacune un `dataclass(frozen=True, slots=True)` :

| Action | Ce qu'elle porte | Ce qu'elle déclenche au jalon 2 |
|---|---|---|
| `Sonder` | les champs demandés | `sonder_catalogue` |
| `Suggerer` | — | `question_suivante` |
| `Rechercher` | — | `rechercher_produits` |
| `DemanderPrecision` | le **champ visé**, jamais une phrase | le tour se clôt, le modèle écrit la question |
| `Rediger` | — | le tour se clôt, le modèle écrit la recommandation |

⚠️ **`DemanderPrecision` ne porte pas de texte, et c'est l'arbitrage qui empêche le
questionnaire.** §3.8 refuse la liste de priorité codée ; l'option « la relance est un
gabarit sans appel modèle » a été explicitement écartée à l'arbitrage de l'étape, parce
qu'une machine qui gagne le critère nº1 en cessant de parler a changé de produit. Le code
décide **de quoi** on parle ; le modèle écrit **la phrase**. Écris-le dans la docstring de
l'action.

### Deux appels modèle par tour, et le plancher qui en découle

La forme d'un tour au jalon 2 sera : extraction (appel nº1) → `enregistrer_criteres` →
boucle `decider()` / outils, sans modèle → rédaction ou question (appel nº2).

Le second appel est **soit** la recommandation **soit** la question, jamais les deux. La
machine a donc un plancher mécanique de **2,00 appel par tour**, contre 2,36 mesuré chez
l'agent. C'est la prédiction nº1 révisée de l'étape ; ne fais rien qui l'invalide sans le
dire.

---

## C. Ce que `decider()` décide — et ce qu'elle ne redécide pas

**Elle décide quel outil appeler ensuite. Elle n'applique aucun invariant que la couche
outils applique déjà.**

Le jeton de parole (§3.17), le clamp des critères, la garde « un tour, une catégorie », la
zone de tolérance du budget (§3.10) vivent dans `tools/` et **y restent**. Si `decider()`
les réimplémente, on obtient deux rédactions d'une même règle — c'est très exactement la
maladie de la dette nº1 de l'étape 8, que le dépôt s'est engagé à ne plus reproduire.

Ce qu'elle décide, en revanche, ce sont les règles de **conduite** que le prompt portait :

| Règle | Source | Ce que `decider()` en fait |
|---|---|---|
| Le budget est une contrainte dure | §3.10, prompt §7 | jamais `Rechercher` tant que `etat.budget_usd is None` |
| Donner avant de demander | §3.9, prompt §5 | jamais `DemanderPrecision` avant qu'une action ait produit quelque chose à montrer |
| La question suggérée est une suggestion | §3.8, prompt §6 | consulte `Suggerer`, puis **arbitre** ; le champ rendu ne commande pas |
| Une question à la fois | périmètre du MVP | au plus un `DemanderPrecision` par tour |
| Zéro résultat | prompt §10 | sur un zéro, aller au diagnostic et à l'assouplissement, pas relancer une recherche |
| Un composant à la fois | prompt §8 | une seule catégorie par tour |

⚠️ **`AUCUNE_RECHERCHE_SANS_BUDGET` est une `Attente` du harnais**, pas une invention de
ce jalon. Relis sa docstring dans `eval/metriques.py` avant d'écrire la première règle :
elle dit précisément ce que « demander le budget avant de chercher » désigne, et pourquoi
`BESOIN_DE_BUDGET` ne le désigne **pas**.

---

## D. La mesure nº8 — les tests, et le piège qui les guette

Une suite de tests purs de **conduite du dialogue** : ils construisent un `EtatSession` et
un `ResultatOutil`, appellent `decider()`, et assertionnent l'action. Sans base, sans
conteneur, sans clé, en millisecondes.

⚠️ **Le piège, et il décide de la valeur de la mesure : n'écris pas ces tests en lisant
ton implémentation.** Écris-les depuis §3.8, §3.9, §3.10, §3.17 et les sections du prompt
listées ci-dessus. Un test dérivé du code compte comme une ligne de plus dans un chiffre
publié tout en ne vérifiant qu'une tautologie — c'est la même circularité que celle qui a
fait refuser l'ajout de scénarios écrits depuis §3.6.

Concrètement : chaque test porte dans sa docstring **la référence de la règle qu'il
vérifie**. Un test sans référence n'est pas un test de conduite, et il ne compte pas dans
la mesure nº8.

### La réserve, qui voyage avec le chiffre partout

Écris-la une seule fois, à côté du compte, comme la réserve sur `iterations` du jalon 0 :

> Ces tests vérifient que la machine conduit le dialogue **comme on l'a écrit**. Ils ne
> vérifient pas que la conduite est bonne, ni que le modèle qui rédige derrière respecte
> quoi que ce soit. La machine rend testable **sa propre décision**, pas la conversation.

Sans elle, « N contre 0 » est le double standard de la métrique nº3 de l'étape 13, et
c'est la seule façon de rater une mesure par ailleurs imparable. Elle doit accompagner le
chiffre dans `PROJET.md`, dans le rapport et dans le `README.md` — partout où il paraît.

---

## E. Le sous-produit qui rend le jalon 3 mécanique

En écrivant le tableau de la section C, tu produis la liste des sections de
`prompts/systeme.v2.md` dont la conduite est **désormais dans le code**. Écris-la, telle
quelle, dans `docs/prompts/etape-15.md` (crée-le) : c'est la **spécification du diff** du
jalon 3.

D'après la lecture faite en préparation, les candidates sont **§5, §6, §7, §8, §10** — la
conduite du tour de parole. Restent au prompt §2, §3, §4, §9, §11, §12, §13, §14 : ce sont
des règles sur **ce qui peut être écrit**, pas sur qui parle quand, et elles valent pour
les deux orchestrations.

**Vérifie cette répartition contre le fichier plutôt que de la recopier**, et si tu n'es
pas d'accord sur une section, dis-le avec son numéro et son motif. Ne modifie pas le
prompt : le jalon 3 le fera, et il le fera par soustraction pure, numérotation d'origine
conservée avec ses trous.

---

## Porte de sortie

```bash
make check      # vert, ≥ 926 + N, et rien d'autre n'a bougé
git status --short
```

1. `make check` vert, **sans base, sans conteneur, sans clé** — la suite entière de ce
   jalon tourne hors ligne, et c'est la propriété qu'on achète.
2. **N est écrit** : le nombre de tests de conduite du dialogue. Le 0 en face vient de la
   ligne existante de §7, citée, jamais d'une mesure refaite pour l'occasion.
3. Le test de couverture d'isolation échoue si un module de `raiyon.machine` n'a pas été
   classé — vérifie-le en ajoutant un module vide, puis retire-le.
4. `git status` : aucun fichier sous `evals/cassettes/`, `prompts/`, `agent/`, `tools/`,
   `matching/`, `validateur/`.

Commit à la fin. Message qui dit que la décision est pure et testée, et qu'aucune
orchestration n'est encore branchée.

---

## Ce que ce jalon ne décide pas

* **Si l'appel de rédaction voit l'historique** — jalon 2. La réponse est oui, et le motif
  sera écrit là-bas : le refuser perdrait `comparaison` par construction, donc rendrait la
  prédiction nº6 invérifiable, donc la campagne démonstrative au lieu d'expérimentale.
* **Où `session.tour()` bascule entre les deux orchestrations** — jalon 2.
* **Le nom définitif du paquet si le jalon 2 le fait bouger** — on le déplacera là-bas si
  besoin, avec la raison.

Si l'un de ces points te paraît nécessaire pour finir ce jalon, **c'est que tu débordes**.
Arrête-toi et dis-le.
