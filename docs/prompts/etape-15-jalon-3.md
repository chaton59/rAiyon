# Prompt Claude Code — Étape 15, jalon 3 : `systeme.machine.v1.md`, par soustraction

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.
> Point de départ : jalon 2 committé, arbre propre, `make check` vert à 981.
> **Zéro appel API.** Ce jalon écrit un fichier de prompt et un test. Rien d'autre.

---

## Ce que ce jalon livre

`prompts/systeme.machine.v1.md`, dérivé de `prompts/systeme.v2.md` **par soustraction
pure**, et le test qui garantit que c'en est une.

La spécification existe déjà : `docs/prompts/etape-15.md`, écrite au jalon 1 contre le
fichier relu section par section. **Suis-la, ne la refais pas.**

> Retirées : **§5, §6, §8.** Restent : §1, §2, §3, §4, §7, §9, §10, §11, §12, §13, §14.

La numérotation d'origine est **conservée avec ses trous**. Le trou est le message : un
numéro manquant se lit comme « cette règle n'est plus au prompt, elle est dans
`decider()` ». Une renumérotation donnerait deux prompts dont les sections 2 se
ressemblent sans être les mêmes, et toute discussion ultérieure deviendrait ambiguë.

---

## A. ⚠️ Ce qu'il ne faut surtout pas toucher

**`prompts/systeme.v2.md` est intouchable, et le coût d'y toucher est chiffré.**

Il est le prompt en vigueur, et les 36 cassettes de `evals/cassettes/systeme.v2/` portent
son `prompt_empreinte`. **Un seul caractère modifié périme la campagne entière** — 191
appels, la ligne de base de toute l'étape 15. `make eval` échouerait en le disant, ce qui
est le bon comportement et une catastrophe budgétaire quand même.

Deux lignes de `systeme.v2.md` sont **périmées et doivent le rester** :

* son titre dit `rAiyon v1` ;
* sa troisième ligne dit « **Onze sections**, une idée chacune » — il en a quatorze.

Elles datent de v1 et personne ne les a suivies. **Ne les corrige pas.** Une correction de
coquille vaut zéro et coûte une campagne.

Amusant et à noter dans `docs/prompts/etape-15.md` : après soustraction de trois sections,
le prompt dérivé en compte **onze**. La ligne périmée devient donc **exacte** pour la
machine par accident, tout en restant fausse pour l'agent. La soustraction pure la conserve
telle quelle ; écris l'accident plutôt que de le laisser découvrir.

---

## B. La vérification des références pendantes — déjà faite, et la règle ne se déclenche pas

La règle de dérivation prévoyait : *si une suppression laisse une référence pendante, la
section reste et la double application se dit ailleurs.*

**Elle ne se déclenche pas.** `systeme.v2.md` ne contient que deux renvois internes — « la
section 2 » (§12) et « la section 12 » (§13) —, et les deux visent des sections
**conservées**. Aucune section survivante ne renvoie à §5, §6 ou §8.

Vérifie-le toi-même sur le fichier plutôt que de me croire, puis écris-le : c'est une
propriété du texte, pas une chance, et elle rend la soustraction totalement propre.

---

## C. Le test — ce qui fait de la règle une garantie

Un test pur : **chaque ligne de `systeme.machine.v1.md` apparaît dans `systeme.v2.md`,
dans le même ordre.** Une sous-séquence, pas une inclusion d'ensemble : l'ordre est ce qui
interdit de réarranger.

Aucune liste d'exceptions, aucune ligne autorisée en plus. C'est ce qui fait que le diff
**est** la spécification de ce que l'orchestration a repris au modèle : un lecteur tape
`diff prompts/systeme.v2.md prompts/systeme.machine.v1.md` et obtient la réponse
exhaustive, sans commentaire à croire.

Le test échoue en nommant la première ligne fautive.

---

## D. Le point ouvert du jalon 1, tranché : **un seul texte, aux deux appels**

L'extraction et la rédaction reçoivent le **même** `systeme`.

*Alternative écartée — deux fichiers, `machine.extraction.v1.md` et
`machine.redaction.v1.md`.* Plus propre par appel, et elle **rouvre l'axe d'identité des
cassettes** : `EnTete` porte **un** `prompt_version` et **un** `prompt_empreinte`. Deux
fichiers demanderaient soit deux champs, soit une empreinte composite — c'est-à-dire de
retoucher `cassette.py` et de défaire l'arbitrage d'axe d'identité de l'étape. Et le diff
cesserait d'être la soustraction d'un fichier à un fichier.

Ce que le choix coûte, écrit plutôt que tu : l'appel d'extraction lit §11, §13 et §14, qui
ne le concernent pas ; l'appel de rédaction lit §9, dont il ne peut rien faire. C'est de
la redondance inerte, pas une contradiction.

### La conséquence sur le cache, et une prédiction à poser maintenant

Le préfixe mis en cache est `tools` + `system` (§3.13). Les deux appels de la machine
n'envoient **pas** les mêmes outils — l'extraction expose `record_criteria`, la rédaction
n'en expose aucun. Il y a donc **deux préfixes distincts** là où l'agent n'en a qu'un.

> **Prédiction, posée avant la campagne.** `cache_ecrit` de la machine sera nettement
> supérieur à celui de l'agent, et `jetons_entree` ne baissera pas proportionnellement au
> nombre d'appels. La mesure nº7 doit donc publier **les jetons autant que les appels** :
> une orchestration deux fois moins bavarde en appels peut être plus chère en entrée.

Écris-la dans `PREDICTIONS` sous la clé du jeu au jalon 5 — ici, note-la simplement dans
`docs/prompts/etape-15.md` pour ne pas la perdre.

### `outils_empreinte`

Le champ enregistre le **jeu d'outils de l'extraction**, seul jeu non vide. C'est complet
au regard de ce que l'empreinte sert à faire : périmer la cassette quand le schéma d'outils
change, et `record_criteria` est le seul dont le schéma puisse changer. Écris-le à côté du
champ.

---

## E. Ce que `docs/prompts/etape-15.md` gagne

Ce fichier existe et porte déjà la spécification. Ajoute-lui, sans réécrire ce qui y est :

1. l'accident des « onze sections » (point A) ;
2. la vérification des références pendantes et le fait que la règle ne s'est pas
   déclenchée (point B) ;
3. la décision « un seul texte aux deux appels » avec son motif d'axe d'identité (point D) ;
4. la prédiction sur le cache (point D) ;
5. **la double application**, qui était le point à trancher : les règles que la machine
   applique **à la fois** dans `decider()` et par une section conservée du prompt — la
   dernière phrase de §10 (« vous n'assouplissez jamais de vous-même ») est déjà tenue par
   construction. Une double application **dite** est honnête ; c'est ici qu'elle se dit, et
   pas dans le prompt, pour que le fichier reste un sous-ensemble strict.

---

## F. La paire de variables, à écrire là où on la tapera

La campagne se lance avec **deux** variables, et en oublier une est la faute la plus chère
de l'étape :

```bash
RAIYON_ORCHESTRATION=machine RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval-enregistrer
```

La garde du jalon 0 attrape le mélange dans un jeu **déjà peuplé** ; elle ne peut rien
pour la première campagne, et c'est le tir d'essai du jalon 4 qui couvre ce cas.

Ajoute la paire au commentaire de la cible `eval-enregistrer` du `Makefile`, à côté de
l'avertissement jumeau qui existe déjà pour `RAIYON_PROMPT_SYSTEME` seul. C'est la seule
modification du `Makefile` autorisée dans ce jalon.

---

## Porte de sortie

```bash
make check                              # vert, ≥ 981 + le test de sous-séquence
unset ANTHROPIC_API_KEY && make eval    # inchangé, aucun rapport ne bouge
git status --short
git diff --stat
diff prompts/systeme.v2.md prompts/systeme.machine.v1.md   # que des suppressions
```

1. **`prompts/systeme.v2.md` n'apparaît pas dans `git status`.** Absolu.
2. Le `diff` ne contient **que** des lignes retirées — aucune ligne ajoutée, aucune
   modifiée. C'est la vérification à l'œil de ce que le test garantit.
3. `make eval` rejoue à l'identique.
4. Aucun appel API.

Commit à la fin.

---

## Ce que ce jalon ne décide pas

* Le tir d'essai `hors_catalogue` — jalon 4 ;
* les prédictions dans `PREDICTIONS` — jalon 5, avant l'enregistrement ;
* la dette des six helpers privés importés de `boucle.py` — après la campagne, comme le
  jalon 2 l'a écrit au §7.

Si l'un te paraît nécessaire ici, **c'est que tu débordes.** Arrête-toi et dis-le.
