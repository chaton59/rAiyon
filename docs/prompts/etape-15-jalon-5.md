# Prompt Claude Code — Étape 15, jalon 5 : prédictions, campagne, verdict

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.
> Point de départ : jalon 4 committé, six cassettes de tir d'essai dans
> `evals/cassettes/systeme.machine.v1/`, `make check` vert à 1002.
> **Budget : ~170 appels.** Réserve d'un réenregistrement complet, **réservé aux bugs**.
> S'il en faut un second, on s'arrête et on rapporte.

---

## L'ordre est bloquant

**A avant B. Sans exception.** Les prédictions entrent dans le code **avant** la commande
d'enregistrement, pas après avoir vu un chiffre. C'est la discipline du jalon 3 de l'étape
13, et le dépôt a déjà payé son absence : le correctif de l'étape 12 a montré qu'un
diagnostic plausible sur le taux de repli — « les scénarios ne posent pas de questions de
domaine » — était **faux**, et il avait été formulé après coup.

---

## A. Les prédictions, dans `PREDICTIONS["machine.v1"]`

Elles sont posées, datées du 3 septembre 2026, et **deux d'entre elles ont déjà été
corrigées avant d'arriver ici** — c'est le tir d'essai qui les a corrigées, pas la
campagne. Écris-le : une prédiction révisée avant la mesure est honnête ; après, elle ne
vaut rien.

**1 — Le coût ne va pas dans le même sens selon qu'on compte les appels ou les jetons.**
La machine a un plancher mécanique de 2,00 appel/tour ; l'agent est à 2,36 mesuré sur v2.
Je prédis la machine dans **[2,00 ; 2,20]**, donc **moins d'appels** que l'agent. Et je
prédis en même temps une **entrée facturée supérieure**, entre **×1,3 et ×2,0** —
deux appels par tour sur une conversation qui grossit plus vite, trois paires
`tool_use`/`tool_result` par tour. Le tir d'essai donne ×2,34, mais sur `hors_catalogue`,
où l'agent est à son minimum absolu de 1,00 appel/tour : le ratio de campagne sera plus
bas. *Version antérieure, fausse et corrigée au jalon 4* : « deux préfixes de cache
distincts ». Il n'y en a qu'un, plus petit que celui de l'agent — un test l'assert.

**2 — Critère nº4 (attendu en top 3) : égal, ou légèrement inférieur, et l'écart ne vient
pas du moteur.** Le moteur est le même. Tout écart trace vers l'**extraction**, pas vers le
matching. *Révisée après le tir d'essai* : je disais « identique » ; `budget_serre.3` a
montré une extraction manquée, donc une recherche sur un état incomplet. Le mécanisme
existe, sa fréquence est inconnue.

**3 — Taux de rejet du validateur : égal ou supérieur chez la machine**, et deux mécanismes
le poussent vers le haut. *Révisée, et je disais l'inverse* : je prédisais une baisse, la
rédaction ne voyant que ce que le moteur vient de rendre. Le tir d'essai a montré les deux
forces contraires — la garde de contexte met **plus** de chiffres sous les yeux du modèle,
et une extraction manquée fait rédiger sur des produits hors sujet, ce qui a déclenché un
refus dès le premier échantillon.

**4 — Critère nº6 (zéro résultat) : la machine tient.** C'est une branche codée.

**5 — Critère nº3 (délai avant première valeur) : égal, médiane à 1,0.** Le code force
l'ordre que l'agent suivait déjà spontanément.

**6 — Là où la machine perd, et c'est là que le verdict doit chercher :**
`comparaison` (« compare la 1 et la 3 » — aucun état ne retient ce qui a été montré),
`changement_davis`, `question_de_domaine` (18 tours sur 81), et **tout tour dont les
critères sont formulés d'une façon que l'extraction en un coup manque**. Ce dernier est
nouveau : il vient du tir d'essai, pas d'une intuition.

**7 — Le résultat d'ensemble le plus probable** : aucun écart au-delà de la dispersion sur
les six critères, sauf le coût. C'est un verdict **valide**, accepté d'avance, et il ne
clôt pas l'étape — les mesures nº7 et nº8 la closent.

---

## B. La campagne

```bash
RAIYON_ORCHESTRATION=machine RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval-enregistrer
```

**Une seule passe, les onze scénarios, y compris les deux du tir d'essai.** Les 24 appels
du jalon 4 sont une prime d'assurance dépensée, pas récupérable.

⚠️ **Ne saute pas les deux scénarios déjà enregistrés pour économiser.** Le préfixe mis en
cache expire entre deux invocations espacées — §7 le documente (« une campagne dont
`cache_lu` s'effondre a repayé son préfixe »). La prédiction nº1 porte précisément sur le
coût d'entrée : une campagne enregistrée en morceaux contre un agent enregistré d'un trait
mesurerait la **méthode d'enregistrement**, pas l'orchestration.

La garde du jalon 0 est armée : le jeu contient six cassettes `orchestration: machine`, et
une campagne lancée avec la mauvaise variable sera refusée. C'est ce que le tir d'essai a
acheté — et **pas** `outils_empreinte`, qui vaut la même valeur des deux côtés.

---

## C. Le rejeu, le rapport, la comparaison

```bash
unset ANTHROPIC_API_KEY
RAIYON_ORCHESTRATION=machine RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval
make eval-comparer AVANT=v2 APRES=machine.v1 \
  Q="l'orchestration seule : agent avec outils contre machine à états, à catalogue, moteur, couche outils et validateur identiques"
```

La dispersion vient de **v2**, qui porte trois prises par scénario. Chaque écart porte son
verdict calculé — `au-delà` ou `dans le bruit` — et §7 dit qu'un écart inférieur à l'ordre
de grandeur du bruit **n'est pas un signal**.

`docs/eval/LISEZMOI.md` gagne ses lignes : `rapport.machine.v1.md` et
`comparaison.v2-machine.v1.md`, avec ce que chacun décrit. Sans cela l'index devient
exactement le piège qu'il existe pour empêcher.

---

## D. Le verdict — ce qu'il doit dire, et ce qu'il n'a pas le droit de dire

**La porte de sortie de l'étape : dire laquelle gagne *où*, jamais laquelle est
« meilleure ».** Une conclusion qui ne nommerait aucun critère sur lequel la machine perd
serait une conclusion fausse.

Quatre choses à écrire, dans cet ordre :

1. **Les six critères d'acceptation**, avec leur verdict de dispersion. Y compris et
   surtout les « dans le bruit », qui sont le résultat le plus probable.
2. **La mesure nº7**, appels **et** jetons. Publier les appels seuls dirait « moins
   chère » d'une orchestration qui coûte plus en entrée facturée.
3. **La mesure nº8** : 17 tests de conduite du dialogue chez la machine, 0 chez l'agent —
   avec sa réserve, qui voyage partout où le chiffre paraît :

   > Ces tests vérifient que la machine conduit le dialogue **comme on l'a écrit**. Ils ne
   > vérifient pas que la conduite est bonne, ni que le modèle qui rédige derrière respecte
   > quoi que ce soit.

4. **Une phrase sur la provenance de la suite** : les onze scénarios ont été écrits pour
   l'agent, à l'étape 12, avant que la machine soit envisagée. Cela la rend non truquée
   **dans les deux sens**, et il faut le dire que la machine gagne ou perde.

⚠️ **`iterations` ne se compare pas** : la réserve du jalon 0 est déjà dans les deux modules
de rendu. Ne la contredis pas dans la prose.

---

## E. Les deux résultats structurels, qui ne sont pas dans le tableau

Ils viennent du parcours, pas de la campagne, et ils sont ce que l'étape a réellement
appris. Écris-les dans le rapport **et** dans `PROJET.md` §5 étape 15.

**1 — L'extraction en un coup, sans recours.** `enregistrer_criteres` n'est pas une action
de `decider()` : une extraction manquée ne se rattrape pas dans le tour. L'agent, lui,
pouvait rappeler l'outil après avoir vu de mauvais résultats. C'est une différence plus
profonde que le tour de parole, et c'est le mécanisme derrière la phrase de §3.6 — « l'agent
encaisse naturellement les virages » —, désormais **observé** plutôt qu'affirmé.
Observé sur `budget_serre.3` au tir d'essai. La campagne dit sa fréquence.

*Ne le corrige pas.* Le correctif — laisser `decider()` redéclencher une extraction —
ajouterait un appel modèle, casserait le plancher de 2,00 et changerait le coût au milieu
de la comparaison. C'est un candidat pour une `systeme.machine.v2` que cette étape ne fait
pas.

**2 — « Ne pas chercher tant que le budget manque » n'est écrite dans aucun prompt.**
L'agent la tient par l'affordance de `question_suivante`, qui remonte `BesoinDeBudget` en
tête. `Attente.AUCUNE_RECHERCHE_SANS_BUDGET` la mesure depuis l'étape 12 sans que personne
ait remarqué qu'aucune instruction ne la portait. `decider()` l'écrit pour la première
fois. Une garantie tenue par chance de conception d'un côté, par construction de l'autre.

---

## F. La règle d'arrêt

* `IssueDuTour` **bien formé** → ce que disent les métriques est un **résultat**. On
  publie, la machine perd là, et c'est l'information qu'on était venu chercher. **Ne
  corrige rien pour faire verdir un chiffre.**
* `IssueDuTour` **mal formé** — exception, `tool_use` orphelin, état non réenchaîné,
  `DivergenceDeRequete` au rejeu → **bug**. On corrige, un réenregistrement complet.
* **Un second réenregistrement n'est pas au budget.** Il voudrait dire que la machine
  n'était pas prête à être enregistrée. On s'arrête et on rapporte.

---

## Porte de sortie

```bash
make check                              # vert, inchangé
unset ANTHROPIC_API_KEY && make eval    # l'agent rejoue v2 à l'identique
git status --short
```

1. `docs/eval/rapport.machine.v1.md` **écrit** — le jeu est complet, la garde de l'étape 13
   ne s'oppose plus ;
2. `docs/eval/comparaison.v2-machine.v1.md` écrit, avec ses verdicts de dispersion ;
3. `docs/eval/LISEZMOI.md` à jour ;
4. les deux orchestrations rejouent, chacune son jeu, sans clé ;
5. le verdict nomme **au moins un critère où la machine perd**.

Commit à la fin.

---

## Ce que ce jalon ne fait pas

* `PROJET.md` §5 étape 15 ✅, le README à deux colonnes, la ligne de §7 qui passe à
  moitié fermée — **jalon 6**, et il ne coûte rien ;
* la dette des six helpers privés de `boucle.py` — après l'étape ;
* le correctif de `NOMBRE` et la dette nº1 — leur version à un seul changement, comme §7
  l'a promis, et surtout **pas** pendant que v2 sert de ligne de base.
