# Prompt Claude Code — Correctif de l'étape 11 : le dernier refus d'un tour

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`, au commit `825edf0`. L'étape 11 est franchie :
interface web, mode coulisses, cadrage SSE testé, 713 tests purs et 84 d'intégration.

Elle a fermé une brèche dans §2 — **un texte refusé par le validateur revenait au client
après un F5** — et le correctif est juste : `prose_de()` écarte un message assistant suivi
d'un message de reprise, reconnaissance exacte et non heuristique, tirée de ce que
`boucle.py` empile réellement.

**Il reste un chemin, et c'est le pire des trois.**

Tu réalises **ce correctif et rien d'autre**. Aucune fonctionnalité, aucune étape 12.

## Avant d'écrire quoi que ce soit

Lis `src/raiyon/agent/boucle.py` (la fonction `repondre()` en entier),
`src/raiyon/api/prose.py` (`_a_ete_refuse()` et sa docstring), et
`tests/api/test_prose.py`.

## Le défaut, exactement

`_a_ete_refuse()` exige qu'un message de reprise suive le message assistant. Or
`boucle.py` n'écrit ce message de reprise **que sur le chemin où une régénération est
demandée**. Sur les **deux** branches `if regenerations > max_regenerations` — celle du
texte et celle de la question — il fait :

```python
_ajouter_les_resultats(messages, tours, executions.resultats)
yield Repli(...)
return IssueDuTour(...)
```

Aucun `_bloc_de_grief`. Le dernier message refusé d'un tour — celui qui a échoué **deux
fois**, et pour lequel le client a reçu un template — n'est donc suivi d'aucune reprise, et
`prose_de()` le rend.

Deux formes, toutes les deux touchées :

1. **le message fautif portait des `tool_use`** → il est suivi d'un message `user` de
   `tool_result` seuls, sans bloc `text` : aucune reprise à reconnaître ;
2. **il ne portait que du texte** → `_ajouter_les_resultats()` sort tôt, **rien n'est
   empilé**, et le message assistant est le dernier de l'historique : il n'y a pas de
   suivant du tout.

### Pourquoi c'est pire que le cas déjà fermé

Deux raisons qui se cumulent.

C'est le texte que le validateur a refusé **et** que la régénération n'a pas su corriger —
la sortie la plus fausse que le tour ait produite, pas la première.

Et comme le message de repli n'est pas persisté (ligne du §7 posée à l'étape 10), le
rechargement affiche **exactement l'inverse de ce qui s'est passé** : la phrase que le
client n'a jamais vue, et rien de celle qu'il a lue.

### Le motif se répète, et il faut le nommer

`test_un_message_assistant_sans_reprise_derriere_lui_revient_normalement` **énonce dans son
nom la règle qui est trop étroite**. Prémisse juste — un message assistant ordinaire
revient —, conclusion fausse appliquée au message fautif final.

C'est le même défaut que celui trouvé à l'étape 11 (`test_le_texte_refuse_reste_dans_la_
prose_parce_quil_reste_dans_lhistorique`), un cran plus loin : un test vert qui affirme sa
propre conclusion. Écris-le dans la note d'étape — c'est la deuxième occurrence, donc ce
n'est plus un accident.

## Le correctif — dans `boucle.py`, pas dans `prose.py`

**Uniformise la trace persistée.** Sur les deux branches de budget épuisé, empile le même
bloc que la branche `continue` construit déjà, puis sors :

```python
reprise = [*executions.resultats, _bloc_de_grief(verdict)]
messages.append({"role": ROLE_CLIENT, "content": reprise})
tours.append(TourProduit(ROLE_CLIENT, reprise))
```

(`verdict_question` sur la seconde branche.) `messages` n'est plus lu après le `return`,
mais l'y mettre garde les deux listes en correspondance — une divergence entre elles est
précisément le genre de chose qu'on ne veut pas avoir à raisonner plus tard.

**La propriété devient alors sans exception : tout message refusé est suivi d'une
reprise.** La règle exacte de `prose.py` couvre tous les chemins sans bouger d'une ligne,
et c'est ce qui compte — le correctif ne rend pas la détection plus fine, il rend la trace
uniforme.

### Ce qu'il faut vérifier plutôt que supposer

Deux messages `user` consécutifs apparaîtront désormais aussi sur ce chemin : la reprise,
puis le message du client au tour suivant. **Le dépôt a déjà ce précédent** — un tour clos
par `ask_clarification` se termine sur les `tool_result`, et le message client suivant est
un second `user` —, donc l'API l'accepte. Ne te contente pas de cet argument : ajoute
l'assertion à `tests/agent/`, sur ce chemin-là.

### Alternatives écartées — écris-les, ne les redécouvre pas

*Élargir la détection dans `prose.py` à « dernier message assistant du tour ».* Elle est
**ambiguë** : cette forme est aussi celle d'un tour légitimement clos par
`ask_clarification`, dont le texte a bel et bien été affiché. Les distinguer redeviendrait
heuristique — exactement ce que le correctif de l'étape 11 refusait, et pour la même
raison.

*Persister le message de repli comme un tour assistant.* Orthogonal : cela réparerait la
moitié « la conversation rechargée ne montre rien », pas la moitié « elle montre le texte
refusé ». Reste écartée, pour le motif déjà écrit au §7 — le modèle se lirait alors
affirmer une phrase qu'il n'a pas produite.

### Une conséquence à assumer, et elle est déjà écrite

Après le correctif, un tour clos par un repli réapparaît, au rechargement, comme un
message client **sans aucune réponse**. Ce n'est pas une régression : c'est exactement ce
que la ligne du §7 annonce depuis l'étape 10, et l'interface dit déjà que la conversation
reprise est incomplète. Le correctif fait coïncider le comportement avec la
documentation ; il ne crée pas un trou, il cesse de le combler avec du faux.

## Tests attendus

Dans `tests/api/test_prose.py` :

1. **Un texte refusé deux fois, tour clos par un repli, ne revient pas** — forme avec
   `tool_use` (message fautif, puis `user` de `tool_result` + reprise).
2. **La même chose sans `tool_use`** — message fautif, puis `user` portant la seule
   reprise. C'est la forme qui n'empilait rien du tout avant le correctif.
3. **Une question refusée deux fois n'emporte pas davantage de prose que la règle ne le
   dit** — la seconde branche est traitée comme la première.
4. Resserre `test_un_message_assistant_sans_reprise_derriere_lui_revient_normalement` :
   son nom doit décrire le **cas**, pas la conclusion. Garde l'ancien raisonnement dans la
   docstring plutôt que de l'effacer — c'est la discipline que l'étape 11 a appliquée au
   test précédent.

Dans `tests/agent/` :

5. **Le tour suivant part d'un historique valide** après un tour clos par repli sur budget
   épuisé : appairage `tool_use` / `tool_result` intact, et la reprise présente.
6. Les tests existants du repli (`Repli(motif=VALIDATION)`, aucun troisième appel API)
   restent verts **sans être modifiés**. S'il faut les toucher, arrête-toi et dis-le : cela
   voudrait dire que le correctif change autre chose que la trace.

## Porte de sortie

- `make check` vert — sans base, sans conteneur, sans clé.
- `make test-int` vert.
- **Le défaut reproduit avant, absent après** : provoque un tour où le texte est refusé
  deux fois (un faux client suffit), recharge la conversation par `GET /sessions/{id}`, et
  montre-moi la prose rendue dans les deux cas.

## Documentation — dans le même commit

1. `PROJET.md` §5 étape 11 : une section **« Correctif — le dernier refus d'un tour »**,
   sur le modèle du correctif de l'étape 9. Elle dit ce que l'étape 11 avait fermé, quel
   chemin restait, pourquoi c'était le pire des trois, et pourquoi le correctif vit dans
   `boucle.py`.
2. La docstring de `_a_ete_refuse()` : la propriété qu'elle invoque — « aucun autre chemin
   ne produit cette séquence » — **était fausse dans l'autre sens** (un chemin produisait
   un refus *sans* la séquence). Corrige-la en disant que l'invariant est désormais tenu
   par `boucle.py`, et **nomme les deux branches** qui le tiennent : c'est là qu'un futur
   `return` anticipé le casserait sans bruit.
3. `boucle.py` : un commentaire sur chaque branche disant que la reprise est empilée **pour
   la trace**, pas pour le modèle — elle n'est plus relue dans ce tour — et que
   `prose.py` en dépend. Sans cela, quelqu'un la retirera un jour comme du code mort.
4. **§7** : la ligne « les messages de repli ne sont pas persistés » gagne sa conséquence
   complète — un tour clos par un repli revient sans réponse, et c'est le comportement
   voulu depuis ce correctif.
5. « Ce que le correctif a appris » : deux tests verts en deux étapes ont affirmé leur
   conclusion dans leur nom. C'est un mode d'échec du dépôt, pas deux accidents — dis-le
   comme tel.

## Méthode

1. **Reproduis d'abord.** Écris le test nº2 (la forme sans `tool_use`), constate qu'il
   échoue, et montre-moi la prose fausse qu'il produit. Ne corrige rien avant.
2. Puis les deux branches de `boucle.py`, et les tests 1, 3, 5.
3. Puis le resserrage du test 4 et la documentation.

Dis-moi explicitement si le correctif fait bouger un test que je n'ai pas listé.
