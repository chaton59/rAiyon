# Prompt Claude Code — Étape 19 : jouer les conversations d'essai, et ne rien corriger

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.
> Point de départ : étape 18 close et committée, `make check` vert à 1018.
> **Budget : ~30 appels** pour les trois conversations prioritaires sur les deux
> orchestrations. Les sept autres sont derrière un sélecteur et ne se lancent pas sans
> arbitrage.

---

## Ce que fait cette étape, et surtout ce qu'elle ne fait pas

Elle **joue** les conversations de `docs/eval/conversations-a-essayer.md` et **rapporte**.

⚠️ **Elle ne corrige rien.** Pas le validateur, pas les prompts, pas `decider()`, pas la
boucle. Un défaut trouvé se décrit — mécanisme, chemin, orchestration concernée — et se
laisse en l'état. Corriger dans la foulée mélangerait le diagnostic et le remède, et on ne
saurait plus ce que l'essai avait montré.

Les deux seuls défauts du projet trouvés hors des tests l'ont été en conversation réelle :
le tour muet de l'étape 12 et les deux règles insatisfaisables de l'étape 18. C'est le
troisième passage de la même méthode.

---

## A. `scripts/essais.py`

Un script de diagnostic, sur le modèle de `scripts/fumee.py` — un but étroit, une sortie
lisible, aucun effet de bord.

**Ce qu'il fait** : pour chaque conversation retenue, ouvre une session neuve, joue les
tours dans l'ordre par `raiyon.agent.session.tour()`, consomme le générateur **en entier**
(la valeur de retour est dans `StopIteration.value` — même geste que `eval/executeur.py`),
et imprime les événements.

**Les conversations vivent dans le script**, en littéral Python. Ne parse pas le markdown :
un document de prose n'est pas un format d'entrée, et le premier titre reformulé casserait
tout. Le document et le script se tiennent à jour à la main, et le script porte le numéro
de chaque conversation pour qu'on les rapproche.

**Options** :

| | |
|---|---|
| `--conversation N` | une seule, par son numéro dans le document (répétable) |
| `--orchestration agent\|machine\|deux` | défaut `deux` |
| par défaut | les **trois prioritaires** : 1, 2 et 6 |

⚠️ **Le défaut est un garde-fou budgétaire, pas une commodité.** Lancer les dix sans le
vouloir coûte ~120 appels. Écris-le dans l'aide de l'option.

**Ce qu'il imprime**, par tour :

* les événements dans l'ordre, en une ligne chacun ;
* **en évidence** : `TexteRejete` avec le code et l'extrait de **chaque** grief, et `Repli`
  avec son motif. Ce sont les deux seules choses qu'on cherche ;
* la prose livrée, telle quelle ;
* à la fin : l'`Usage` cumulé, par `getattr` sur le client comme le fait l'enregistreur de
  cassettes — pour que le coût réel soit lu et non estimé.

**Ce qu'il n'écrit pas** : aucun fichier dans `docs/`, aucune cassette, aucune ligne dans
`evals/`. Les sessions vont en base — c'est inévitable, `search_products` interroge le
dépôt — et c'est sans conséquence.

⚠️ **N'ajoute rien à `raiyon/eval/scenario.py`.** Ces conversations ne sont pas des
scénarios : elles n'ont ni attendu, ni attentes, ni prises, et les faire entrer dans la
suite changerait `prises_attendues()` et périmerait la complétude des trois jeux. La
frontière est nette et elle se dit dans la docstring du script : **un essai n'est pas une
mesure.**

---

## B. Les trois conversations prioritaires

Reprends le texte exact du document ; il est écrit pour viser un mécanisme précis.

**Nº1 — la comparaison hors budget.** C'est la non-régression de l'étape 18 : cette forme
était impossible avant. On veut la voir passer, sur les deux orchestrations.

**Nº2 — le produit hors budget nommé dans une question.** La plus intéressante : elle teste
une **prédiction**, pas seulement un chemin.

> `boucle.py` valide le texte et la question d'`ask_clarification` comme deux chaînes
> **séparées**. Depuis l'étape 18, la règle 4 raisonne sur la chaîne validée. Donc un texte
> qui dit l'écart ne couvre pas une question qui renomme le produit. **L'agent devrait
> échouer là où la machine passe** — son second appel est rédaction *ou* question, jamais
> les deux, donc une seule chaîne.

Si la prédiction se vérifie, c'est une asymétrie d'orchestration de plus, trouvée après la
campagne et gratuite. Si elle ne se vérifie pas, **dis-le et dis pourquoi** — une
prédiction infirmée vaut mieux qu'une prédiction oubliée.

**Nº6 — la question de domaine insistante.** Le trou qu'aucune règle ne couvre : un ratio
comme « 3000:1 » n'est ni un montant ni une valeur unitaire, et passe le validateur. On ne
cherche pas un grief ici — **on lit la prose**. Recopie-la verbatim dans le rapport, c'est
la seule façon de trancher.

---

## C. Le rapport, en fin d'exécution

Dans ton compte rendu, pas dans un fichier committé :

1. **Par conversation et par orchestration** : passé / refusé-puis-régénéré / repli ;
2. **Chaque grief levé**, avec son code, son extrait, et ton avis en une ligne : le
   validateur a-t-il eu raison ? Un grief **juste** est un bon résultat ;
3. **Le verdict de la prédiction nº2**, explicitement confirmée ou infirmée ;
4. **La prose de la nº6**, verbatim ;
5. **Le coût réel**, en appels et en jetons.

Et une distinction à tenir dans les mots, parce que tout le rapport en dépend :

> **Un mécanisme qui cède** — un refus impossible à satisfaire, un chiffre inventé, un
> repli sur un chemin nominal — **est un défaut**. Une formulation lourde, une question mal
> choisie, un classement discutable sont de la **qualité**, et ne se traitent pas ici.

---

## Porte de sortie

```bash
make check                    # vert à 1018, inchangé : le script n'est pas testé, il diagnostique
make up && make migrate && make seed
uv run python scripts/essais.py --orchestration deux
git status --short
```

1. `scripts/essais.py` est le **seul** fichier nouveau ;
2. rien sous `evals/`, `docs/eval/rapport*`, `prompts/`, `src/` ;
3. le coût imprimé tient sous **40 appels**. S'il dérape, arrête-toi et dis-le : une
   conversation qui part en boucle est elle-même un résultat.

Commit du script à la fin, avec un message qui dit qu'il diagnostique et ne mesure pas.

---

## Ce qui vient après, et qui n'est pas ici

Les sept autres conversations (~90 appels), et **les correctifs** de ce que celle-ci aura
trouvé. Les deux se décident avec le rapport sous les yeux.
