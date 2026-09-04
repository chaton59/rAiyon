# Prompt Claude Code — Étape 22 : retirer la garde d'extraction, garder la clôture

> Point de départ : `15743f1` committé et poussé. **Zéro appel API.**
> C'est la dernière action du projet avant présentation.

---

## ⚠️ Ce n'est pas un `git revert` de commit

`15743f1` contient **deux choses** : la garde d'extraction, et toute la clôture du POC
(recensement, §5, §7, README, `LISEZMOI.md`). `git revert 15743f1` détruirait la clôture.

**Le retrait est chirurgical.** On enlève la garde, on garde tout le reste.

---

## Pourquoi on la retire

Elle a été écrite, testée et chiffrée — et le chiffre la condamne :

* **précision 2/10.** Elle tire sur 10 tours sur 81 pour 2 vrais positifs. Les 8 faux
  positifs sont des tours où le client n'énonce qu'un budget ou qu'une catégorie, et leurs
  arguments sont **identiques** à ceux d'un vrai positif : `{categorie, budget_usd}`. Deux
  resserrements ont été essayés, aucun ne les sépare. La condition de déclenchement
  n'identifie donc pas le défaut, et ça ne se répare pas en la réglant mieux ;
* **elle coûte 10 des 30 prises encore rejouables de `machine.v1`** — quatre scénarios
  vidés, la comparaison agent/machine réduite de 9 à 7 scénarios, et `comparaison.1`
  perdue, qui était la dernière prise capable de trancher 2 des 24 `ecart_non_dit` de
  l'étape 18 ;
* **contre un défaut mesuré à 2 tours sur 81**, soit 2,5 %, dont le correctif n'est pas
  mesurable sans une campagne fraîche (~176 appels).

C'est le même arbitrage que la dette nº1 (étape 17) et la consigne d'extraction (étape 21) :
**coût de fermeture supérieur au coût du défaut**. Le tenir ici et pas là serait incohérent.

---

## A. Ce qu'on retire

1. la garde dans l'orchestrateur de la machine, et ses quatre bornes ;
2. les 10 tests de la garde ;
3. les entrées de `DIVERGENCES_ATTENDUES` **ajoutées par la garde** — celles-là seulement.
   ⚠️ Les entrées venant de l'étape 18 (le correctif du validateur) **restent** ;
4. les mentions de la garde dans `PROJET.md` §5 et dans le `README.md` — elle n'existe plus
   comme fonctionnalité.

## B. Ce qu'on garde, sans y toucher

Le recensement du point A de l'étape 21, les deux constats de §7 (`ask_clarification` rare
chez l'agent avec son contrepoids ; `rapport_qualite_prix` non reproduit), §5 à jour des
étapes 19-21, le verdict suspendu de l'étape 15, `LISEZMOI.md`, le rouge attendu annoncé
dans le README.

## C. Ce qu'on écrit — une ligne de §7, et elle vaut le retrait

> **Un critère explicitement énoncé n'est pas toujours enregistré.** Mesuré à **2 tours sur
> 81** (`comparaison.1` t1, `sur_specifie.3` t2) sur les cassettes de `machine.v1`, 13 tours
> douteux écartés plutôt que comptés. Propre à l'extraction atomique : `enregistrer_criteres`
> n'étant pas une action de `decider()`, une extraction partielle ne se rattrape pas dans le
> tour — l'agent, lui, rappelle l'outil après avoir vu de mauvais résultats.
> **Correctif écrit, testé, chiffré, puis retiré** : une garde « catégorie posée, zéro
> critère » a une précision de **2/10**, les arguments d'un vrai et d'un faux positif étant
> identiques, et deux resserrements essayés ne les séparent pas. Elle coûtait **10 des 30
> prises encore rejouables** de `machine.v1`, dont `comparaison.1`. Non retenue pour cette
> raison, à l'étape 22. Candidate pour une `systeme.machine.v2`, avec la campagne qui la
> mesurerait.

⚠️ Écris-la comme une **décision datée**, pas comme un report : une décision se rouvre en la
contredisant, un report se reconduit tout seul. C'est la troisième du projet dans cette
forme, et la seule dont le prix a été **mesuré** au lieu d'être estimé — dis-le.

---

## Porte de sortie

```bash
make check                                          # revenu à 1018 : les 10 tests de la garde ont disparu
make test-int                                       # 98
unset ANTHROPIC_API_KEY
make eval && make eval-etape12                      # inchangés
RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval  # 30 prises rejouables, pas 20
make eval-comparer AVANT=v2 APRES=machine.v1 Q="la question déjà committée dans le fichier"
git status --short                                  # vide
git push origin main
```

1. **`machine.v1` est revenu à 30 prises rejouables** et la comparaison à **9 scénarios** —
   c'est la vérification qui compte, l'artefact de l'étape 15 est rendu ;
2. `make check` est revenu à **1018** ;
3. `make eval` de l'agent rejoue à l'identique ;
4. la ligne de §7 est écrite, datée de l'étape 22 ;
5. working tree vide, `origin/main` à jour.

⚠️ **Relance `eval-comparer` avec la question déjà committée** dans
`comparaison.v2-machine.v1.md`, jamais une nouvelle : la question est un input du fichier, et
la changer ferait bouger une ligne sans rapport avec ce retrait.

**N'ouvre aucun autre chantier.** C'est la dernière action avant présentation.
