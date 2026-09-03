# Prompt Claude Code — Étape 15, jalon 2 : l'orchestrateur, branché sur les vrais outils

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.
> Point de départ : jalon 1 committé (`8a8b535`), arbre propre, `make check` vert à 952.
> **Un seul appel API autorisé, et à la toute fin** : la vérification manuelle du point H,
> ~10 appels. Tout le reste se teste avec le faux client de l'étape 8.

---

## Ce que ce jalon livre

Une seconde orchestration, **de signature identique à la première**, branchée sur les
vrais outils, émettant les mêmes événements, persistée par le même `session.tour()`.

À la fin de ce jalon, `RAIYON_ORCHESTRATION=machine make chat` tient une conversation.
Le prompt dérivé n'existe pas encore — c'est le jalon 3 —, donc la machine tourne
provisoirement sur `systeme.v2`. C'est **voulu** : les tests de ce jalon utilisent un faux
client scripté, pour qui le contenu du prompt est sans effet.

---

## A. Le préalable : la garde de contexte, qui rouvre le jalon 1

Arbitrage tranché après ton constat sur §13. La règle, **énoncée sans référence à §13**
pour que la dépendance parte dans le bon sens :

> **La rédaction reçoit toujours les agrégats du sous-catalogue courant.** La machine sonde
> avant d'écrire, à chaque tour, que le tour finisse par une recommandation ou par une
> question.

Elle se défend seule : §5 veut ce contexte pour un préambule de question, §4 et §12
veulent des chiffres fondés. §13 devient exécutable **par conséquence**, pas par cause —
et c'est ce qui évite l'issue 1, qui laissait dans le prompt une instruction inexécutable
et poussait donc le modèle à fabriquer une répartition. Une répartition fabriquée est
faite d'**entiers nus** : aucune règle du validateur ne mord dessus (§7, ligne « un entier
nu n'est vérifié par rien »), et la faute serait invisible sur 18 des 81 tours.

Concrètement : une garde de plus dans `decider()`, un test de conduite de plus, **mesure
nº8 de 16 à 17**, et les trois documents qui portent le chiffre mis à jour — `test_mesure_8.py`
échouera de lui-même sinon.

Coût : un appel d'outil de plus par tour, **aucun appel modèle**. Le plancher de 2,00
appel/tour tient.

⚠️ **Écris dans la docstring de la garde que c'est un avantage d'orchestration, pas un
correctif** : une machine à états peut *garantir* le contexte de sa rédaction ; un agent ne
le peut pas, décider de ses outils étant ce qui fait de lui un agent. Et la prédiction qui
va avec, posée maintenant : plus d'agrégats en contexte, c'est plus de chiffres dans la
prose, donc **potentiellement plus de rejets**. Si le taux de rejet de la machine monte,
c'est le premier endroit où regarder — pas une supériorité de l'agent.

---

## B. La forme d'un tour, et le plancher qui en découle

```
appel nº1  extraction        → un seul outil exposé : record_criteria
           enregistrer_criteres(...)          ← la couche outils, inchangée
           boucle decider() / outils          ← aucun appel modèle
           sondage systématique               ← point A
appel nº2  rédaction OU question              ← jamais les deux
           validation, une régénération, repli
```

**On ne force pas l'outil d'extraction.** `ClientLLM` n'a pas de `tool_choice`, et
l'ajouter rippellerait sur `ClientAnthropic`, `FauxClient`, `ClientCassette` et les
`dependency_overrides` de l'API. C'est aussi le bon design : forcer `record_criteria` sur
« compare la 1 et la 3 » ferait fabriquer un critère au modèle.

**Un message d'extraction sans `tool_use` est le chemin normal**, pas un incident : c'est
un tour qui n'apporte aucun critère nouveau. L'état passe inchangé à `decider()`. Écris-le
comme tel, avec un `logueur.info`, jamais un `WARNING`.

⚠️ Si le message d'extraction porte du **texte**, il est jeté. Il n'est ni émis, ni validé,
ni persisté comme prose : le seul texte qui part au client vient de l'appel nº2. Dis-le,
c'est le genre de chose qu'on redécouvre dans un appendice.

---

## C. La signature, et ce qui la rend vérifiable

Un `Protocol` nommé — `Orchestrateur` — porte la signature partagée :

```python
def __call__(self, *, client, systeme, outils, historique, message_client,
             etat, contexte, max_iterations, max_regenerations
             ) -> Generator[Evenement, None, IssueDuTour]: ...
```

`repondre` de `boucle.py` **s'y conforme déjà et ne change pas d'une ligne**. C'est mypy
qui vérifie que la substitution en est une ; sans ce `Protocol`, « même signature » serait
une intention.

`max_iterations` est accepté et **utilisé** : il borne la boucle `decider()`. Le graphe est
fini, donc la borne ne devrait jamais mordre — et c'est exactement pour ça qu'elle doit
exister, pour échouer bruyamment plutôt que de tourner.

### Le branchement

Nouveau module `src/raiyon/orchestration.py` : `repondre_en_vigueur()` lit
`get_settings().orchestration` et rend l'un des deux. `session.py` change **d'un import et
d'une ligne**, et rien d'autre.

⚠️ `config.py` reste le point unique de lecture de l'environnement : aucune lecture de
`RAIYON_ORCHESTRATION` ailleurs que dans `Settings`.

---

## D. L'historique va à la rédaction. Oui, et voici pourquoi

L'appel de rédaction reçoit `historique` — la conversation relue en base, comme l'agent.

*Alternative écartée — un rendu sans mémoire, qui ne verrait que l'état et le dernier
résultat du moteur.* Elle est plus simple et elle **truque la comparaison** : « compare
plutôt la 1 et la 3 » deviendrait impossible par construction, or `comparaison` est l'un
des trois scénarios où la prédiction nº6 annonce que la machine perd. Perdre par
construction rendrait la prédiction invérifiable, et la campagne démonstrative au lieu
d'expérimentale.

La différence entre les deux orchestrations doit rester **la décision**, jamais la mémoire.

---

## E. Ce qui ne bouge pas — et ce qu'un besoin de le changer signifie

**Interdits** : `matching/`, `tools/`, `validateur/`, `agent/boucle.py`, `agent/client.py`,
`agent/client_anthropic.py`, `eval/` en entier, `prompts/`, `evals/cassettes/`.

`session.py` est la **seule** exception, et pour un import et une ligne.

⚠️ **Si tu as besoin de toucher `eval/metriques.py` ou `eval/executeur.py`, arrête-toi et
dis-le.** Ce serait le signe que la machine n'émet pas les mêmes événements — donc que la
comparaison ne porterait plus sur les mêmes mesures, donc que le fondement de l'étape est
faux. C'est un signal, pas un obstacle à contourner.

La machine réutilise tels quels : les cinq règles du validateur, la construction du
`ContexteFourni`, le budget `max_regenerations` **de tour**, les templates de repli et
leurs `MotifDeRepli`, l'appairage `tool_use` / `tool_result`, et la forme des blocs
persistés.

⚠️ **Le piège technique nº1 de `boucle.py` vaut ici sans exception** : chaque `tool_use`
a son `tool_result`. Chez la machine, la question se pose différemment — c'est le code qui
appelle les outils, pas le modèle — mais l'historique persisté doit rester **relisible par
l'API Anthropic au tour suivant**, puisque les deux orchestrations écrivent dans la même
table et qu'une session peut être reprise. Décide comment les appels d'outils du code
apparaissent dans `tours_conversation.blocs`, écris la décision, et vérifie-la par un test
qui rejoue un historique de machine dans un second tour.

C'est le point technique le plus susceptible de casser tard. Traite-le tôt.

---

## F. Les événements

Mêmes types, mêmes moments : `CriteresMisAJour`, `Sondage`, `QuestionSuggeree`,
`ProduitsTrouves`, `QuestionPosee`, `Texte`, `TexteRejete`, `Repli`.

Relis `Attente` dans `eval/metriques.py` avant d'écrire l'émission : chaque attente est un
fait lu **sur les seuls événements**, et une attente qui cesserait d'être observable chez
la machine ferait échouer des scénarios pour une raison qui n'est pas la conduite.

`IssueDuTour.outils_appeles` est renseigné comme chez l'agent — c'est ce que le rapport
publie.

---

## G. Les tests

Sur le modèle de `tests/agent/`, avec le `FauxClient` : enchaînement, réenchaînement de
l'état entre deux actions, terminalité, appairage, borne d'itérations, tour d'extraction
sans `tool_use`, rejet puis régénération, second rejet puis repli.

Ils tournent **sans base** si le dépôt est un `DepotEnMemoire`, comme au jalon 1. Garde
cette propriété : c'est elle qui rend le jalon vérifiable hors ligne.

---

## H. La vérification manuelle — le seul endroit où on dépense

À la toute fin, une fois `make check` vert :

```bash
make up && make migrate && make seed
RAIYON_ORCHESTRATION=agent   make chat    # 2 tours
RAIYON_ORCHESTRATION=machine make chat    # 2 tours
```

~10 appels. Ce qu'on vérifie : la console affiche les mêmes types d'événements, la session
se persiste, un second tour relit l'historique sans erreur d'appairage.

⚠️ **Ce qu'on ne juge pas ici, c'est la prose.** La machine tourne sur `systeme.v2`, qui
lui dit d'appeler des outils qu'elle ne lui donne pas et de sonder au moment où elle ne
peut plus. Une réponse maladroite est **attendue** et n'est pas un défaut de ce jalon.

---

## Porte de sortie

```bash
make check                       # vert, ≥ 952 + les nouveaux, conteneur arrêté, sans clé
make test-int                    # 98, inchangé
unset ANTHROPIC_API_KEY && make eval   # inchangé : l'agent n'a pas bougé
git status --short
```

1. `make eval` rejoue **à l'identique** — aucun rapport ne bouge. L'agent n'a pas été
   touché, et c'est ce qui le prouve.
2. `git status` : rien sous `evals/cassettes/`, `prompts/`, `tools/`, `matching/`,
   `validateur/`, `eval/`. Dans `agent/`, **seul `session.py`**, et d'un import et d'une
   ligne.
3. Les deux orchestrations lancent une conversation (point H).

Commit à la fin.

---

## Ce que ce jalon ne décide pas

* `systeme.machine.v1.md` — jalon 3, par soustraction de §5, §6, §8, numérotation
  conservée avec ses trous ;
* si les deux appels reçoivent le même texte de prompt — jalon 3, le point ouvert que
  `docs/prompts/etape-15.md` a laissé ;
* le tir d'essai `hors_catalogue` — jalon 4.

Si l'un te paraît nécessaire pour finir ce jalon, **c'est que tu débordes.** Arrête-toi et
dis-le.
