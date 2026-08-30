# Prompt Claude Code — second correctif d'étape 6 : la condition de l'absence structurelle

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`. L'étape 6 et son premier correctif sont
livrés, verts, **non commités**. Tu vas appliquer **un correctif ciblé, et rien
d'autre** : une condition dans `_motif_du_retrait`, et le test qui la garde.

**N'ouvre pas l'étape 7.** Aucune donnée ne change : `data/seed/produits.jsonl`
doit garder un diff vide, et les bornes calibrées ne bougent pas.

## Le constat

Tu as documenté une limite en fin de docstring d'`ABSENCE_STRUCTURELLE` : le
motif ne distingue pas, parmi les produits rouverts, ceux que le seuil écartait
de ceux auxquels l'attribut ne s'applique pas.

Ce n'est pas une limite, c'est le défaut que le premier correctif devait
supprimer, déplacé d'une branche. Mesuré sur le seed committé —
`internal-hard-drive`, `rpm >= 7200`, budget 25 USD :

```
7200 tr/min et plus, dans le budget  → 0
5400 tr/min, dans le budget          → 2
    internal-hard-drive-696751738a   Western Digital AV-GP   14.21 USD
    internal-hard-drive-aa72d12add   Western Digital AV-GP   19.67 USD
```

Zéro résultat, motif `absence_structurelle` — parce que `_motif_du_retrait`
rend ce motif **sans condition** dès que l'attribut porte le drapeau. L'étape 8
dira donc « vous avez demandé un disque mécanique ». Or il y en a, dans son
budget : ils tournent à 5 400. La phrase juste est « il y en a, mais aucun à
7 200 tr/min ».

C'est une affirmation fausse sur le catalogue produite par le moteur — §2, le
même cas que celui qui a motivé le premier correctif, dans le motif qui l'avait
remplacé.

## Ce que tu écris

La donnée qui tranche est **déjà calculée dans la même fonction** :
`releves.valeurs_atteignables` porte la valeur la plus proche réellement
présente parmi les produits qui satisfont tous les autres critères.

- elle **existe** → l'attribut s'applique bien à une partie du catalogue
  atteignable, et le critère est seulement trop strict → `CRITERE_TROP_STRICT` ;
- elle vaut **`None`** → aucun produit rouvert ne déclare l'attribut, l'absence
  est structurelle → `ABSENCE_STRUCTURELLE`.

Passe la valeur atteignable à `_motif_du_retrait` et conditionne la première
branche. C'est la sœur exacte de la règle de `DONNEE_ABSENTE` — « tout ce qui
rouvrirait est dépourvu de la valeur » — et les trois branches disent alors la
même chose sous trois angles, au lieu d'une exception en tête de fonction.
Réécris la docstring dans ce sens : elle expose une règle, plus un cas
particulier suivi de deux cas généraux.

Retire la limite assumée de la docstring d'`ABSENCE_STRUCTURELLE` : elle n'est
plus vraie. **Garde en revanche la phrase qui explique le motif** — le troisième
cas reste un troisième cas, c'est sa condition de déclenchement qui se resserre.

Le cas de test existant (`rpm >= 7200` **et** `interface = M.2 PCIe 4.0 X4`) a
`valeur_atteignable = None` : il doit rester vert et garder son motif. Vérifie-le
plutôt que de le supposer.

## Tests

- **Intégration** : le reproducteur ci-dessus — `rpm >= 7200`, budget 25 USD sur
  `internal-hard-drive` → zéro produit, motif **`critere_trop_strict`**,
  `valeur_atteignable = 5400`, et `rpm` toujours absent de
  `ecartes_faute_de_donnee`. Les deux identifiants sont dans le seed committé ;
  cite-les, comme pour G1 à G4.
- **Intégration** : le cas existant reste en `absence_structurelle`, avec
  `valeur_atteignable = None`. Les deux tests côte à côte montrent que c'est la
  valeur atteignable qui sépare, et non l'attribut.
- **Unitaire, pur** : `_motif_du_retrait` sur un attribut à absence structurelle
  rend `CRITERE_TROP_STRICT` quand une valeur atteignable existe, et
  `ABSENCE_STRUCTURELLE` quand elle est nulle. Les comptages sont injectés.

## `PROJET.md`

Amende l'arbitrage E, en deux ou trois phrases : la condition du troisième cas
n'est pas le drapeau seul mais **le drapeau et l'absence de valeur
atteignable**. Écris pourquoi le drapeau seul ne suffisait pas, avec les chiffres
du reproducteur — un attribut peut être structurellement inapplicable à une
partie du catalogue **et** trop strictement demandé sur le reste, et ce sont deux
phrases différentes à dire au client.

La ligne de §7 sur le drapeau posé à la main reste valable, ne la touche pas.

## Porte de sortie

`make check` vert, `make test-int` vert, la part pure de `tests/matching/`
toujours sous les deux secondes. `data/seed/produits.jsonl` : diff vide.

Montre-moi les deux diagnostics côte à côte — celui du reproducteur et celui du
cas M.2 PCIe. Rien n'est commité. **N'enchaîne pas sur l'étape 7.**

Même style que le reste du dépôt : français, commentaires qui expliquent
pourquoi. Si un point de ce prompt te paraît faux ou infaisable, **arrête-toi et
dis-le** avant d'écrire le code.
