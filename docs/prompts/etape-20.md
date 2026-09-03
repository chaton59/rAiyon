# Prompt Claude Code — Étape 20 : trois constats, aucun correctif

> Point de départ : étape 19 committée. **Budget : ~8 appels**, au point C seulement.
> **Aucun correctif dans cette étape.** On mesure, on rapporte, on arbitre ensuite.

---

## A. Recensement d'`ask_clarification` — zéro appel

L'étape 19 a montré **zéro appel** à `ask_clarification` sur six parcours : l'agent pose
ses questions dans le bloc `text` et finit sur `end_turn`.

Compte les appels dans les cassettes des **trois jeux** (`v2`, `machine.v1`,
`v1-etape12`) : lis les blocs `tool_use` des prises enregistrées, sans rejouer.

Rends un tableau : par jeu, nombre de prises, nombre de tours, nombre d'appels à
`ask_clarification`, et **quels scénarios** le déclenchent.

**Ce que ça décide.** Si l'outil est rare partout, alors l'outil terminal de l'amendement
de §3.7, le correctif de l'étape 9 qui valide la question, `OrigineRejet.QUESTION` et la
métrique « questions avant première valeur » protègent et mesurent un chemin que le
dialogue emprunte peu. Ce serait un constat de conception, à écrire dans §7 — **pas ici**,
et surtout pas un correctif.

⚠️ Ne conclus pas au-delà du compte. « Rare dans les cassettes » n'est pas « inutile » :
`ask_clarification` est ce qui rend une question **traçable**, et une question posée en
texte ne l'est pas. Dis les deux.

---

## B. La conversation nº1 était mal écrite — zéro appel

Dans `docs/eval/conversations-a-essayer.md` et dans `scripts/essais.py`, remplace le second
tour de la nº1 :

> ~~compare-moi les deux premiers en détail~~ → **compare-moi en détail les deux qui
> dépassent mon budget**

« les deux premiers » a été lu comme les deux premiers **dans le budget** : la conversation
testait une comparaison détaillée, pas une comparaison **hors budget**, et passait donc
sans rien prouver. Note la correction dans le document, avec sa raison — une conversation
d'essai qui rate sa cible est un piège pour le prochain qui la lance.

Commite aussi `docs/eval/conversations-a-essayer.md` et `docs/prompts/etape-19.md`, restés
non suivis. La docstring de `scripts/essais.py` référence le premier.

---

## C. Reproduire le critère perdu — ~8 appels

L'étape 19 a observé, **sur un seul tirage**, que la machine perdait `screen_size = 27` et
ajoutait `rapport_qualite_prix` que le client n'avait pas demandé.

Rejoue **le premier tour seul** de la nº6 — « un écran 27 pouces, 400 $ » — sur la
**machine**, quatre fois. Un tour, pas la conversation entière.

Pour chaque tirage, imprime les critères enregistrés par `record_criteria` et le nombre de
candidats. Puis, pour comparaison, **deux tirages côté agent**.

Trois questions, et les trois se répondent par un compte :

1. la perte de `screen_size` est-elle **systématique ou intermittente** chez la machine ?
2. `rapport_qualite_prix` est-il ajouté à chaque fois ?
3. l'agent le fait-il aussi, ou est-ce propre à l'extraction en un coup ?

⚠️ **Ne corrige ni `machine/decision.py`, ni son prompt, ni le validateur.** Le validateur
n'y peut rien de toute façon : chaque chiffre cité est fourni. Le lieu à regarder est
l'appel d'extraction, et on ne le touche pas tant qu'on ne sait pas si le défaut est
systématique.

---

## Porte de sortie

```bash
make check                              # inchangé
git status --short
```

1. Le tableau du point A ;
2. la nº1 corrigée et les deux fichiers committés ;
3. les six tirages du point C, avec les critères enregistrés à chaque fois ;
4. **le coût réel sous 12 appels** ;
5. **aucune modification** de `src/`, `prompts/`, `evals/cassettes/`.

Commit à la fin.
