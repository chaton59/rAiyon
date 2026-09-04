# Prompt Claude Code — Étape 21 : la garde d'extraction, et la clôture du POC

> Point de départ : étape 20 committée. **Zéro appel API.**
> **C'est la dernière étape avant présentation.** À la fin, le dépôt doit se lire comme
> fini : `make check` vert, documents cohérents, décisions en suspens **parquées et
> datées** plutôt que laissées comme des fils qui pendent.

---

## A. Recensement du critère perdu — sur les cassettes, gratuit

Les 36 cassettes de `machine.v1` portent **81 tours d'extraction enregistrés**, avec les
arguments de chaque `record_criteria`. Les onze scénarios ont des messages client écrits et
connus. La fréquence du défaut est donc **déjà sur le disque**.

Pour chaque tour de chaque prise : compare ce que le message client énonce à ce que
`record_criteria` a enregistré, et compte les tours où **un critère explicitement énoncé
n'a pas été enregistré**.

Rends : le compte, le taux sur 81, et la liste des tours concernés avec le critère perdu.

⚠️ **Ne compte que l'explicite.** « un écran 27 pouces » énonce `screen_size = 27` ;
« pour du jeu » n'énonce aucun critère du registre. Un jugement large gonflerait le taux et
rendrait le chiffre inutilisable. En cas de doute, ne compte pas, et dis combien de cas
douteux tu as écartés.

**Ce que ça décide** : la fermeté de ce qui s'écrit en §7, pas la décision de corriger. Un
critère énoncé qui disparaît est un défaut à 2/81 comme à 20/81.

---

## B. La garde d'extraction — le correctif, testé hors ligne

Quand l'appel d'extraction rend un `record_criteria` qui pose une **catégorie** (et
éventuellement un budget) mais **aucun critère**, la machine relance l'extraction **une
seule fois**.

C'est exactement le tirage fautif de l'étape 20 : critères `AUCUN`, budget 400 $, 115
candidats au lieu de 37, et trois écrans de 21 à 24 pouces recommandés à quelqu'un qui
avait demandé du 27.

**Bornes, à écrire dans le code :**

* **une seule relance par tour**, jamais deux — c'est un garde-fou, pas une boucle ;
* la relance n'a lieu que sur un `record_criteria` **à zéro critère**. Un tour qui
  n'apporte légitimement aucun critère (« compare la 1 et la 3 ») ne pose pas de catégorie
  neuve et ne doit **pas** la déclencher ;
* si la relance rend encore zéro critère, on continue avec ce qu'on a. Le défaut est alors
  du modèle, pas de l'orchestration, et on ne paie pas un troisième appel pour le
  constater ;
* le plancher de 2,00 appel/tour devient « 2,00, plus un appel sur les tours où la garde
  tire ». Dis-le dans la docstring : c'est une mesure publiée qui change de définition.

**Tests avec le faux client de l'étape 8**, sans clé et sans base : la garde tire sur zéro
critère avec catégorie ; elle ne tire pas sur un tour sans catégorie neuve ; elle ne tire
qu'une fois ; le tour se termine normalement si la relance échoue.

⚠️ **C'est le correctif que l'étape 15 avait différé**, au motif qu'il casserait le plancher
de 2,00 au milieu de la comparaison. Ce motif est tombé : l'étape 18 a suspendu la
comparaison. Écris-le, c'est la levée d'un report, pas une décision neuve.

---

## C. Les dégâts sur les cassettes, et `DIVERGENCES_ATTENDUES`

La garde ne change rien sur les tours où elle ne tire pas. Sur ceux où elle tire, un appel
de plus apparaît : la cassette diverge ou s'épuise.

```bash
unset ANTHROPIC_API_KEY
RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval
make eval                                   # v2 — l'agent n'est pas touché, rien ne doit bouger
make eval-etape12
```

Une entrée dans `DIVERGENCES_ATTENDUES` par cassette concernée, avec sa raison complète.
**C'est une assertion, pas un skip** : elle échoue si une divergence annoncée n'a pas lieu.

Rapporte combien de prises `machine.v1` restent rejouables après cette étape — c'est le
chiffre qui dit ce qui reste de l'artefact de l'étape 15.

---

## D. Ce qui est décidé de ne pas être fait, avec son prix

**La consigne d'extraction ne sera pas resserrée.** Elle vit dans les `messages`, donc dans
l'empreinte de requête : la toucher périme **les 36 cassettes de `machine.v1`** d'un coup,
pour un gain que rien ne peut mesurer sans une campagne fraîche (~176 appels).

Écris-le en §7 comme une décision datée, sur le modèle de la dette nº1 : correctif
identifié, coût de fermeture supérieur au coût du défaut, **non fait pour cette raison**,
candidat pour une `systeme.machine.v2`. Une décision se rouvre en la contredisant ; un
report se reconduit tout seul.

**Deux constats à porter en §7, sans correctif :**

1. **`ask_clarification` est rare chez l'agent** — 4 appels sur 295, deux scénarios sur
   onze, trois campagnes. La mécanique qui l'entoure (outil terminal de l'amendement de
   §3.7, correctif de l'étape 9 qui valide la question, `OrigineRejet.QUESTION`, métrique
   des questions) protège et mesure un chemin que le dialogue emprunte peu. ⚠️ **Avec son
   contrepoids, qui compte autant** : les questions, elles, sont partout — l'agent en pose
   presque à chaque tour, en prose. L'outil est le **seul** endroit où une question est un
   objet et non une phrase ; le supprimer ne supprimerait pas les questions, il
   supprimerait la seule mesure qu'on en a. Et le 0 de la machine n'est **pas comparable** :
   elle n'expose pas l'outil, sa question est écrite à l'appel de rédaction.
2. **`rapport_qualite_prix` ajouté sans demande** — observé une fois à l'étape 19, **0 sur
   6** à l'étape 20. Symptôme unique, clos sauf réapparition.

---

## E. La clôture — le dépôt doit se lire comme fini

C'est la partie qui décide de la présentation, et elle vaut autant que le correctif.

1. **`make eval` sur le jeu de la machine sort en code non nul**, et c'est voulu — trois
   attentes de scénario non tenues, verdict de l'étape 15. **Ça doit être impossible à
   rater dans le README**, juste à côté de la commande : un lecteur qui la lance ne doit pas
   croire à une régression. Un rouge attendu qui n'est pas annoncé est un rouge tout court.
2. **Le verdict de l'étape 15 est suspendu, pas oublié.** §5 doit dire en une phrase ce qui
   est su, ce qui ne l'est pas, et ce qu'il faudrait — ~176 appels — pour trancher. Idem
   pour la garde de ce jalon, dont le gain n'est pas mesuré.
3. **Tout est committé et poussé.** Aucun fichier non suivi ; `git push origin main` à la
   fin, le remote a douze commits de retard depuis l'étape 14.
4. **Le README dit la vérité sur l'état** : deux orchestrations lançables, la campagne de la
   machine partiellement suspendue, les mesures nº7 et nº8 avec leurs réserves.
5. **Relis `docs/eval/LISEZMOI.md`** : c'est l'index, et il devient le piège qu'il existe
   pour empêcher si une prise écartée de plus n'y est pas dite.

⚠️ **N'ouvre aucun chantier neuf.** Si tu vois quelque chose à améliorer, écris-le dans
« ce qui reste » et n'y touche pas. Une étape de clôture qui corrige au passage n'est plus
une clôture.

---

## Porte de sortie

```bash
make check                              # vert, ≥ 1018 + les tests de la garde
make test-int                           # 98
unset ANTHROPIC_API_KEY
make eval && make eval-etape12
RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval
git status --short                      # vide
git push origin main
```

1. `make eval` de l'**agent** rejoue à l'identique — la garde ne touche pas `boucle.py` ;
2. le nombre de prises `machine.v1` encore rejouables est **écrit** ;
3. le taux du point A est écrit, avec les cas douteux écartés ;
4. `git status` vide, remote à jour ;
5. le rouge attendu du jeu machine est annoncé dans le README, à côté de la commande.

---

## Ce qui reste après, et qui n'est pas du travail en cours

Une seule correction est encore autorisée après cette étape ; garde-la pour ce qui casserait
à la présentation.

* réenregistrer `machine.v1` (~176 appels) — rétablirait le verdict de l'étape 15 **et**
  mesurerait la garde de ce jalon ; les deux questions se paient ensemble ;
* `systeme.machine.v2` — la consigne d'extraction, et l'extraction atomique en général ;
* la dette nº1 de l'étape 8 — reclassée à l'étape 17, coût de fermeture ~366 appels ;
* la recherche hybride `pgvector` (§3.5), hors périmètre du produit livrable.
