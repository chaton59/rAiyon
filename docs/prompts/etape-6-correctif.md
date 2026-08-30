# Prompt Claude Code — correctif d'étape 6 : direction des sous-scores, absence structurelle, rapport de seed

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`. L'étape 6 est livrée, verte, **non
commitée**. Tu vas appliquer **trois correctifs ciblés, et rien d'autre**.

**N'ouvre pas l'étape 7.** Ne touche ni à `schemas.py`, ni à `models.py`, ni aux
migrations, ni aux bornes calibrées — le correctif ne change aucune donnée, il
change deux règles de calcul et une phrase de rapport.

---

## Correctif 1 — La direction d'un sous-score numérique

### Le constat

Le raffinement livré à l'arbitrage G fait décider la direction du sous-score par
**l'opérateur seul** : `sous_score_numerique` rend `1 - normaliser(valeur)` sur
un `au_plus`. Il corrigeait un vrai défaut — le `sens` du registre seul
classait un 65 pouces en tête de « un écran d'au plus 24 pouces ». Mais il a
produit le défaut symétrique.

`("monitor", "screen_size")` est calibré `[21.5, 34]`. Sur « écran d'au plus
24 pouces », déclaré en `souhait` :

| dalle | sous-score | rang |
| ---: | ---: | --- |
| 21,5″ | 1,00 | 1er |
| 24″ | 0,80 | après |

Le client qui pose un plafond veut **le plus grand qui rentre**, pas le plus
petit qui existe. Le défaut est reproductible partout où l'opérateur `au_plus`
rencontre un attribut de `sens = PLUS_HAUT_MIEUX` : `screen_size`,
`video-card.length` (« 300 mm maximum, mon boîtier »), `capacity`,
`video-card.memory`, `core_count`.

**Pourquoi la suite ne l'a pas vu :**
`test_un_critere_au_plus_inverse_le_sens` porte sur `cpu.tdp`, dont le `sens`
est `PLUS_BAS_MIEUX`. La direction de l'opérateur et celle du registre y disent
déjà la même chose. Le seul cas qui révèle le problème est celui où elles
divergent, et il n'est pas couvert.

### La règle à écrire

> **L'opérateur décide de la satisfaction ; le `sens` du registre ordonne à
> l'intérieur de la région satisfaisante.**

- valeur **satisfaisante** → sous-score dans `[0,5 ; 1]`, ordonné par le `sens`
  du registre sur la portion de bornes concernée ;
- valeur **non satisfaisante** → sous-score dans `[0 ; 0,5[`, décroissant avec
  l'écart au seuil demandé.

Vérifie qu'elle donne le bon résultat sur les quatre configurations, et écris ce
tableau en docstring — c'est lui qui empêchera le prochain raffinement de
réintroduire l'un des deux défauts :

| critère | `sens` registre | attendu |
| --- | --- | --- |
| `refresh_rate` `au_moins` 144 | plus haut mieux | 240 Hz devant 144 Hz |
| `screen_size` `au_plus` 24 | plus haut mieux | 24″ devant 21,5″ |
| `tdp` `au_plus` 65 | plus bas mieux | 35 W devant 65 W |
| `price_per_gb` `au_plus` 5 | plus bas mieux | 0,05 devant 4,90 |

`egal` ne change pas : la proximité à la valeur demandée reste la bonne
sémantique, et le `sens` n'y a rien à faire.

**Conséquence à assumer et à écrire :** `sens` redevient porteur sur les
critères rétrogradés, et non plus seulement dans le score technique du rapport
qualité/prix. La docstring de `score.py` qui dit que c'est « le seul endroit où
`sens` est porteur » devient fausse — corrige-la.

**Un seuil hors bornes ne doit pas casser la règle.** « Au moins 500 Hz » sur des
bornes `[60, 240]`, ou « au plus 10 pouces » sur `[21.5, 34]` : la région
satisfaisante peut être vide ou couvrir tout le catalogue. Le sous-score reste
dans `[0, 1]`, la fonction ne divise jamais par zéro, et un test le montre.

### Tests

- **Le test qui manquait** : `au_plus` sur un attribut `PLUS_HAUT_MIEUX` —
  nomme-le d'après ce qu'il garde, pas d'après ce qu'il appelle.
- Les quatre lignes du tableau, chacune en assertion d'ordre.
- Une valeur non satisfaisante marque strictement moins que n'importe quelle
  valeur satisfaisante, sur les deux directions d'opérateur.
- Seuil au-delà de la borne haute, seuil en deçà de la borne basse.
- `egal` inchangé — garde le test existant tel quel, il vérifie autre chose.

Reprends le cas nominal du rapport de livraison (écran, 400 USD, 144 Hz
souhaité, IPS important, 27″ bloquant, le moins cher possible) et **montre-moi
le classement avant et après**. Si l'ordre ne bouge pas, dis-le : cela voudra
dire que le correctif n'était pas exercé par ce cas-là, ce qui est une
information, pas un échec.

---

## Correctif 2 — `rpm` : une absence structurelle n'est pas une donnée manquante

### Le constat

Le registre porte déjà l'analyse juste : le taux de 33,9 % de
`internal-hard-drive.rpm` « vaut exactement la part de HDD du seed », l'absence
y est **structurelle**. Mais le commentaire conclut que le compteur la rapporte
quand même, et l'argument — « un client qui demande 7 200 tr/min a bien perdu
les SSD en chemin » — vaut pour le **filtre**, pas pour le **libellé du
diagnostic**.

Le chemin est mécanique : `rpm >= 7200` avec un autre critère → zéro produit →
`rouverts == ecartes_faute_de_donnee` → `_motif_du_retrait` rend
`DONNEE_ABSENTE` → l'étape 8 formulera « ces disques ne déclarent pas leur
vitesse de rotation ». La vérité est « ce sont des SSD, ils n'en ont pas ».

C'est le moteur qui fabrique une affirmation fausse sur le catalogue, dans le
module dont c'est précisément la raison d'être (§2). L'arbitrage E existait pour
séparer « aucun produit ne fait 144 Hz » de « aucun produit ne déclare sa
fréquence » ; il manque le troisième cas, qui n'est ni l'un ni l'autre.

### Ce que tu écris

Un drapeau `absence_structurelle: bool` sur `Attribut`, et un quatrième motif.

- **Le drapeau n'est pas une opinion sur le taux de remplissage.** Il se pose
  quand une **autre colonne explique l'absence**, et le registre le dit en une
  ligne : `rpm` est absent si et seulement si `type == "SSD"`, ce que
  `SpecsDisqueInterne._coherence_type_rpm` impose déjà. C'est vérifiable par la
  machine, pas déduit d'un pourcentage. `boost_clock` à 66,1 % ne le porte
  **pas** : rien dans le schéma n'explique son absence, elle est seulement
  corrélée à la génération. La distinction est exactement celle de §3.4quater
  (calcul déterministe contre comblement d'absence) et elle s'écrit.
- `rpm` sort du compteur `ecartes_faute_de_donnee` : les SSD ne sont pas des
  disques dont la donnée manque.
- Un motif `ABSENCE_STRUCTURELLE`, choisi quand le critère bloquant porte un
  attribut à absence structurelle. Il porte l'information dont l'étape 8 a
  besoin pour dire la vraie phrase — « vous avez demandé un disque mécanique, et
  aucun ne satisfait vos autres critères » — sans que le moteur rédige quoi que
  ce soit. La `Proposition` reste une proposition.

Documente le motif comme les trois autres : ce qu'il signifie, et pourquoi il
n'appelle pas la même réponse.

### Tests

- Unitaire, pur : `_motif_du_retrait` sur un attribut à absence structurelle ne
  rend jamais `DONNEE_ABSENTE`.
- Unitaire, pur : le compteur ignore `rpm` et continue de compter
  `refresh_rate`.
- **Intégration** : `rpm >= 7200` plus un second critère impossible sur
  `internal-hard-drive` → zéro produit, motif `ABSENCE_STRUCTURELLE`, et
  `ecartes_faute_de_donnee` **ne contient pas** `rpm`.
- Un test de registre : tout attribut portant `absence_structurelle` a, en
  commentaire, la colonne qui explique l'absence — ou, si tu trouves une forme
  qui le rend exécutable plutôt que documentaire, préfère-la et dis-le-moi.

---

## Correctif 3 — `data/seed/rapport_seed.md`, section G2

Le rapport affirme que les deux casques de G2 ont « toutes les specs
identiques, sauf le prix et le champ d'affichage `color` ». La mesure de
l'étape 6 dit autre chose : `headphones-06acf63b59` est un **Pyle Audio**,
`headphones-393cd46c64` un **Logitech**, et `marque` est un filtre dur. « Specs
identiques » vaut pour le JSONB, pas pour la ligne.

`PROJET.md` enregistre la correction ; le rapport figé garde l'erreur, et c'est
**lui** que les tests citent comme référence.

Ajoute une note sous la section G2 : les deux produits diffèrent aussi par la
marque, `marque` est un filtre dur, et le cas reste valide **parce qu'aucun
critère de marque n'est posé** — c'est ce qui laisse le départage se jouer sur
le prix seul.

**Ne régénère pas le seed. Ne touche à aucun identifiant.** C'est une note, deux
ou trois phrases, pas une reprise du rapport.

---

## `PROJET.md`

Trois amendements courts, dans la forme des précédents :

- **arbitrage G** : la règle « l'opérateur décide de la satisfaction, le `sens`
  ordonne à l'intérieur » remplace « la direction vient de l'opérateur ». Écris
  **les deux défauts symétriques**, celui d'avant le raffinement et celui
  d'après, avec les chiffres du 21,5″ et du 24″. C'est un raffinement qui a
  déplacé un défaut avant de le corriger, et c'est plus instructif que la règle
  finale seule ;
- **arbitrage E** : le troisième cas. Une absence expliquée par une autre
  colonne n'est ni un critère trop strict, ni une donnée manquante. Le critère
  de pose du drapeau — une autre colonne l'explique, vérifiable par le schéma —
  et le fait que `boost_clock` ne le porte pas ;
- **§7 risques** : la ligne sur le garde-fou de l'arbitrage F reste ; ajoute que
  le drapeau `absence_structurelle` est posé à la main et qu'un attribut futur
  dont l'absence serait expliquée par une autre colonne ne sera pas détecté tout
  seul.

---

## Porte de sortie

`make check` vert, `make test-int` vert, la part pure de `tests/matching/`
toujours sous les deux secondes. Aucune donnée changée : `data/seed/produits.jsonl`
a un diff **vide**, les bornes calibrées sont identiques, et
`test_calibration.py` le confirme.

Montre-moi le classement du cas nominal avant/après et le diagnostic du cas
`rpm`. Rien n'est commité. **N'enchaîne pas sur l'étape 7.**

Même style que le reste du dépôt : français, commentaires qui expliquent
pourquoi. Si un point de ce prompt te paraît faux, contradictoire avec
`PROJET.md` ou `catalogue/schema_attributs.md`, ou infaisable, **arrête-toi et
dis-le** avant d'écrire le code — comme tu l'as fait sur `frequence_mhz`.
