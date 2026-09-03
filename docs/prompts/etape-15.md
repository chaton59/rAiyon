# Étape 15 — ce que `systeme.machine.v1` retire à `systeme.v2`, et ce qu'il garde

> **Spécification du diff du jalon 3**, écrite au jalon 1 comme sous-produit de
> `raiyon/machine/decision.py`. Elle ne modifie rien : `prompts/systeme.v2.md` est intact,
> et le jalon 3 fera la soustraction.
>
> Écrite le 3 septembre 2026, contre `prompts/systeme.v2.md` relu section par section —
> pas contre le souvenir qu'on en avait.

---

## La règle de dérivation

`systeme.machine.v1.md` est `systeme.v2.md` **moins les sections dont la conduite est
désormais dans le code**. Soustraction pure : aucune section n'est réécrite, aucune n'est
ajoutée, et la **numérotation d'origine est conservée avec ses trous**.

⚠️ **Le trou est le message.** Une renumérotation donnerait deux prompts dont les sections
2 se ressemblent sans être les mêmes, et toute discussion ultérieure — « la section 6
disait… » — deviendrait ambiguë entre les deux orchestrations. Un numéro manquant se lit
comme ce qu'il est : cette règle-là n'est plus au prompt, elle est dans `decider()`.

Le critère de tri, en une phrase :

> Une section qui dit **qui parle quand** part dans le code. Une section qui dit **ce qui
> peut être écrit** reste au prompt, et elle vaut pour les deux orchestrations.

---

## Le verdict, section par section

| § | Titre | Verdict | Motif |
|---|---|---|---|
| 1 | Ton rôle | **garder** | Ni conduite ni règle de contenu : c'est l'identité de celui qui écrit, et les deux orchestrations écrivent |
| 2 | La règle absolue | **garder** | Règle de contenu, et la plus importante — critère nº1 |
| 3 | Les noms de produits se citent verbatim | **garder** | Règle de contenu |
| 4 | Une fourchette n'est jamais un prix | **garder** | Règle de contenu |
| 5 | Donner avant de demander | **retirer** | Conduite pure — c'est la garde « `Sonder` puis `Suggerer` avant tout `DemanderPrecision` » |
| 6 | La question suggérée est une suggestion | **retirer**, avec une perte nommée | L'arbitrage passe à `_ce_quon_demande()`. Voir la réserve ci-dessous |
| 7 | Le budget est une contrainte dure | **garder** — ⚠️ *désaccord avec la lecture préparatoire* | Voir ci-dessous |
| 8 | Un composant à la fois | **retirer**, avec une perte nommée | Voir ci-dessous |
| 9 | Enregistrez ce que le client a dit | **garder** | Règle de contenu, et elle s'adresse à l'appel d'extraction. Voir le point ouvert |
| 10 | Zéro résultat | **garder** — ⚠️ *désaccord avec la lecture préparatoire* | Voir ci-dessous |
| 11 | La recommandation | **garder** | Règle de contenu |
| 12 | Trois façons de fabriquer un chiffre | **garder** | Règle de contenu |
| 13 | Ce que vous savez, et ce que vous ne savez pas | **garder** — ⚠️ *avec un point à trancher au jalon 3* | Voir ci-dessous |
| 14 | Ce que l'écran du client affiche | **garder** | Règle de contenu, et la seule cible de v2 dont l'effet est au-delà du bruit |

**Retirées : §5, §6, §8.** Restent : §1, §2, §3, §4, §7, §9, §10, §11, §12, §13, §14.

---

## Les trois désaccords, avec leur motif

### §7 — « Le budget est une contrainte dure » : elle **reste**

La lecture préparatoire la classait en conduite, sur la foi de son titre. Le corps de la
section dit autre chose :

> `search_products` rend deux ensembles séparés […] Un produit du second ne se cite
> **jamais** sans dire qu'il dépasse, et de combien exactement.

Ce n'est pas une règle sur le tour de parole : c'est une règle sur **ce qui peut être
écrit à propos d'un produit hors budget**, c'est-à-dire la couche prompt du critère
d'acceptation nº2 (§3.11, niveau 1) et le pendant rédactionnel du code de grief
`ecart_non_dit`.

La partie conduite — *ne pas chercher tant que le budget manque* — **n'est pas dans §7** :
elle n'était écrite nulle part dans le prompt, elle vivait dans le comportement de l'agent
et elle est mesurée par `Attente.AUCUNE_RECHERCHE_SANS_BUDGET`. C'est `decider()` qui
l'écrit pour la première fois, et cela ne retire rien à §7.

Retirer §7 laisserait la machine sans aucune instruction sur la zone de tolérance, alors
que `decider()` n'en dit rien non plus — elle vit dans `raiyon.tools`, et la section
« ce qu'elle ne redécide pas » de `decision.py` lui interdit d'y toucher. Le produit
perdrait une garantie que la machine ne remplace pas.

### §10 — « Zéro résultat » : elle **reste**

Quatre phrases, et une seule est de la conduite :

* « Dites pourquoi, avec le diagnostic rendu par l'outil » → **rédaction** ;
* « quel critère élimine quoi, combien de produits reviendraient » → **rédaction** ;
* « proposez l'assouplissement que le moteur a calculé, et laissez le client trancher » →
  **rédaction** ;
* « **Vous n'assouplissez jamais de vous-même** » → conduite, et elle est déjà tenue **par
  construction** : `enregistrer_criteres` n'est pas une action de `decider()`, donc aucune
  décision de la machine ne peut réécrire un critère.

La section est donc à **90 % rédactionnelle**, et c'est elle qui porte le critère
d'acceptation nº6 côté prose. La retirer laisserait la machine muette devant un zéro
résultat — au moment précis où le produit a le plus à dire.

⚠️ Sa dernière phrase devient **redondante** avec une garantie structurelle. Redondante
n'est pas fausse : elle reste vraie, elle ne coûte rien, et la retirer seule violerait la
règle de soustraction pure (on retire des sections, pas des phrases).

### §8 — « Un composant à la fois » : elle **part**, et voici ce qu'on perd

Deux paragraphes de nature différente :

* « Une seule recherche de produits par message du client » → conduite, et `decider()`
  la tient par construction : la seule route vers `Rechercher` exige que rien n'ait encore
  été produit dans le tour ;
* « Annoncez-le, commencez par une catégorie, terminez-la, puis **proposez la suivante au
  message suivant** » → rédaction, et la machine la perd.

**La perte est réelle et petite** : la machine ne proposera pas d'elle-même de passer au
composant suivant. Aucun scénario de la suite ne la mesure — `categorie_efface_budget` est
le client qui change de catégorie, pas l'assistant qui le propose. Elle est écrite ici pour
qu'on ne la découvre pas dans un rapport.

*Alternative écartée — garder §8 et n'en retirer que le second paragraphe.* Elle vaut mieux
sur le fond, et elle casse la règle de dérivation : dès qu'on édite à la phrase, le diff
cesse d'être une soustraction lisible et les deux prompts commencent à diverger là où
personne ne regarde.

---

## Ce que §6 emporte avec elle, et qui ne revient pas

> Si l'outil rend `marque`, préférez presque toujours l'usage — « c'est pour jouer, pour du
> montage, pour de la bureautique ? » — qui fait avancer plusieurs critères à la fois.

C'est **la moitié positive** de §6, et la machine ne sait pas l'exprimer : « l'usage » n'est
pas un champ du registre, donc aucune action de `decider()` ne peut le désigner. La machine
garde la moitié négative — le champ rendu ne commande pas — et perd celle-ci.

⚠️ **C'est un écart de qualité conversationnelle, pas un défaut d'implémentation.** Le
risque « le champ le plus discriminant n'est pas toujours la meilleure question » est déjà
au §7 de `PROJET.md`, mesuré : sur les 32 écrans à 144 Hz sous 400 $, `marque` marque 0,93
contre 0,73 pour le type de dalle. L'agent avait le prompt pour arbitrer ; la machine n'a
que le calcul.

---

## Le point à trancher au jalon 3 — §13 demande un outil que la rédaction n'aura pas

§13 reste, et sa dernière moitié pose un problème que la soustraction ne résout pas :

> Puis basculez : **sondez le sous-catalogue courant avec `probe_catalog`**, et dites la
> répartition qu'il vient de rendre — combien d'écrans en VA, combien en IPS.

Chez l'agent, le modèle appelle l'outil lui-même. Chez la machine, l'appel de rédaction est
le **second et dernier** appel du tour, et il n'orchestre rien : c'est `decider()` qui a
décidé des outils, avant lui. Une instruction qui dit « sondez » est donc inexécutable.

Et le cas n'est pas théorique : c'est exactement le tour 2 de `question_de_domaine`. Le
budget y est connu depuis le tour 1, l'état n'a pas changé, et `decider()` relance une
recherche — elle ne peut pas savoir qu'on lui a posé une question de domaine, puisqu'elle
ne voit pas la prose (c'est la frontière qui achète tout le reste).

**Ce jalon ne le tranche pas.** Trois issues existent, elles se pèsent au jalon 3 avec le
reste du prompt sous les yeux, et deux d'entre elles touchent du code :

1. laisser §13 tel quel et accepter que la machine réponde avec des produits au lieu d'une
   répartition — le coût des « virages hors-script » que §3.6 annonçait, payé cash et
   mesuré par la campagne ;
2. reformuler la dernière moitié de §13 — mais ce serait une **réécriture**, pas une
   soustraction, et la règle de dérivation y passerait ;
3. faire sonder `decider()` systématiquement avant de rédiger — un outil de plus par tour,
   sans appel modèle supplémentaire, mais une décision de conduite prise pour compenser une
   phrase de prompt, ce qui est le mauvais sens de dépendance.

---

## Un point ouvert que ce document ne décide pas

Le prompt dérivé sera lu par **deux appels** — l'extraction et la rédaction — là où l'agent
n'en avait qu'un. §9 (« `record_criteria` est la seule porte ») s'adresse au premier ; §11
(« un à trois produits, classés ») s'adresse au second. Où va la note qui le dit, et si les
deux appels reçoivent le même texte, est **l'affaire du jalon 3**.
