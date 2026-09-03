# Étape 15 — ce que `systeme.machine.v1` retire à `systeme.v2`, et ce qu'il garde

> **Spécification du diff**, écrite au jalon 1 comme sous-produit de
> `raiyon/machine/decision.py`, et **appliquée au jalon 3**.
> `prompts/systeme.machine.v1.md` en est la soustraction ; `prompts/systeme.v2.md` est
> intact, et le reste.
>
> Écrite le 3 septembre 2026, contre `prompts/systeme.v2.md` relu section par section —
> pas contre le souvenir qu'on en avait. Les sections ✅ ont été tranchées au jalon 3.
>
> **La garantie n'est pas dans ce document** : `tests/machine/test_prompt_derive.py` vérifie
> que chaque ligne du dérivé apparaît dans la source **dans le même ordre**. Le `diff` des
> deux fichiers est donc la réponse exhaustive à « qu'est-ce que l'orchestration a repris au
> modèle ? », sans commentaire à croire.

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

### ✅ Tranché au jalon 2 — l'issue 3, mais **pas pour cette raison-là**

C'est l'issue 3 qui a été retenue, et la manière dont elle l'a été est le point : la garde
n'a **pas** été écrite pour rendre §13 exécutable. Elle a été énoncée sans aucune référence
à §13 —

> La rédaction reçoit toujours les agrégats du sous-catalogue courant. La machine sonde
> avant d'écrire, à chaque tour, que le tour finisse par une recommandation ou par une
> question.

— et elle se défend seule : §5 veut ce contexte pour le préambule d'une question, §4 et §12
veulent des chiffres fondés sur autre chose que la mémoire du modèle. §13 devient exécutable
**par conséquence, pas par cause**, et la dépendance part donc dans le bon sens.

Ce qui a fait écarter l'issue 1 : sans agrégats en contexte, un modèle à qui l'on demande
une répartition la **fabrique**, et une répartition fabriquée est faite d'**entiers nus** —
sur lesquels aucune des cinq règles du validateur ne mord (§7, « un entier nu n'est vérifié
par rien »). La faute aurait été invisible, sur les tours où elle compte le plus.

⚠️ **Constaté à la vérification manuelle du jalon 2** : « sur les huit écrans 27 pouces de
votre fourchette, cinq sont en VA et trois en IPS ». Trois nombres, tous fournis.

---

## ✅ Le point ouvert, tranché : **un seul texte, aux deux appels**

Le prompt dérivé est lu par **deux appels** — l'extraction et la rédaction — là où l'agent
n'en avait qu'un. §9 (« `record_criteria` est la seule porte ») s'adresse au premier ; §11
(« un à trois produits, classés ») s'adresse au second. Ils reçoivent néanmoins **le même
texte**.

*Alternative écartée — deux fichiers, `machine.extraction.v1.md` et `machine.redaction.v1.md`.*
Plus propre par appel, et elle **rouvre l'axe d'identité des cassettes** : `EnTete` porte
**un** `prompt_version` et **un** `prompt_empreinte`. Deux fichiers demanderaient soit deux
champs, soit une empreinte composite — c'est-à-dire de retoucher `cassette.py` et de défaire
l'arbitrage d'axe d'identité de l'étape, confirmé au jalon 0. Et le diff cesserait d'être la
soustraction d'un fichier à un fichier, donc la spécification cesserait d'être lisible.

**Ce que le choix coûte, écrit plutôt que tu** : l'appel d'extraction lit §11, §13 et §14,
qui ne le concernent pas ; l'appel de rédaction lit §9, dont il ne peut rien faire. C'est de
la **redondance inerte**, pas une contradiction — aucune des deux moitiés ne dit à l'autre
de faire l'inverse de ce qu'elle fait.

### `outils_empreinte` enregistre le jeu d'outils de l'extraction

C'est le seul jeu non vide des deux appels, et c'est complet au regard de ce que l'empreinte
sert à faire : périmer la cassette quand le schéma d'outils change. `record_criteria` est le
seul outil que la machine expose, donc le seul dont le schéma puisse la périmer.

### ⚠️ La conséquence sur le cache, et une prédiction posée avant la campagne

Le préfixe mis en cache est `tools` + `system` (§3.13). Les deux appels de la machine
n'envoient **pas** les mêmes outils — l'extraction expose `record_criteria`, la rédaction
n'en expose aucun. Il y a donc **deux préfixes distincts** là où l'agent n'en a qu'un.

> **Prédiction.** `cache_ecrit` de la machine sera nettement supérieur à celui de l'agent,
> et `jetons_entree` ne baissera pas proportionnellement au nombre d'appels. La mesure nº7
> doit donc publier **les jetons autant que les appels** : une orchestration deux fois moins
> bavarde en appels peut être plus chère en entrée.

À reporter dans `PREDICTIONS`, sous la clé du jeu, **avant** l'enregistrement de la campagne.

---

## La double application, dite ici et pas dans le prompt

Trois règles sont désormais portées **deux fois** : par `decider()`, et par une section
conservée du prompt. Une double application **dite** est honnête ; une double application
tacite est la dette nº1 de l'étape 8.

Elle se dit **ici** et non dans le fichier de prompt, pour que celui-ci reste un
sous-ensemble strict de `systeme.v2.md` — la note y serait une ligne ajoutée, et le test de
sous-séquence la refuserait à juste titre.

| Règle | Dans le code | Dans le prompt conservé |
|---|---|---|
| « Vous n'assouplissez jamais de vous-même » | tenue **par construction** : `enregistrer_criteres` n'est pas une action de `decider()` | dernière phrase de §10 |
| Une seule recherche par message du client | tenue **par construction** : la seule route vers `Rechercher` exige que rien n'ait encore été produit dans le tour | §8 est retirée, donc **plus dite** — seul cas où la double application se ferme |
| « Sondez le sous-catalogue et dites la répartition » | `GARDE_DE_CONTEXTE` : le sondage a **déjà eu lieu** quand la rédaction lit cette phrase | §13, seconde moitié |

⚠️ **La troisième ligne est la plus intéressante, et c'est un impératif que la rédaction ne
peut pas exécuter** : elle n'a aucun outil. Ce que le prompt demande est pourtant déjà fait,
et ses résultats sont sous les yeux du modèle. La phrase se lit donc comme une invitation à
utiliser ce qu'il a, au lieu d'une instruction inexécutable. **Le laisser tel quel est un
choix**, et la campagne dira s'il tient : si la prose de la machine annonce qu'elle va
sonder au lieu de dire la répartition, c'est cette ligne qu'il faudra reprendre — par une
`systeme.machine.v2`, jamais par une retouche de v1.

---

## L'accident des « onze sections »

`systeme.v2.md` porte deux lignes périmées, et **elles le restent** :

* son titre dit `rAiyon v1` ;
* sa troisième ligne dit « **Onze sections**, une idée chacune » — il en a quatorze.

Elles datent de v1 et personne ne les a suivies. Les corriger coûterait **la campagne v2
entière** : les 36 cassettes de `evals/cassettes/systeme.v2/` portent le `prompt_empreinte`
du fichier, un seul caractère les périme toutes, et c'est la ligne de base de l'étape 15 —
191 appels. `make eval` échouerait en le disant, ce qui est le bon comportement et une
catastrophe budgétaire quand même. **Une coquille vaut zéro.**

La soustraction pure recopie donc ces deux lignes telles quelles. Et comme elle retire
exactement trois sections, la seconde **redevient exacte pour la machine** — onze sections,
et il y en a onze — tout en restant fausse pour l'agent.

C'est un **accident**, pas une intention, et il est écrit ici pour ne pas être relu plus
tard comme une élégance préméditée. `test_prompt_derive.py` le constate, source comprise :
si `systeme.v2.md` cesse d'en compter quatorze, l'accident n'en est plus un.

---

## Les références pendantes — la règle ne s'est pas déclenchée

La règle de dérivation prévoyait : *si une suppression laisse une référence pendante, la
section reste.* **Vérifié sur le fichier, et elle ne tire pas.**

`systeme.v2.md` ne porte que deux renvois internes :

* « **La section 2** interdit d'estimer et d'arrondir » — §12 vers §2, **conservée** ;
* « la règle de **la section 12** ne connaît pas d'exception ici » — §13 vers §12,
  **conservée**.

Aucune section survivante ne renvoie à §5, §6 ou §8. C'est une **propriété du texte**, pas
une chance, et elle rend la soustraction totalement propre — un test la constate.

**Conséquence non recherchée, et bienvenue** : `ask_clarification` et `suggest_next_question`
n'étaient nommés **que** dans §5 et §6. Ils disparaissent donc du prompt dérivé, et la
machine n'expose ni l'un ni l'autre. Un prompt qui les nommerait inviterait le modèle à
appeler des outils absents ; ce n'est pas ce qui a décidé du retrait, c'est ce que le
retrait donne en plus.

---

## La paire de variables, pour la campagne

⚠️ **Deux variables, et en oublier une est la faute la plus chère de l'étape :**

```bash
RAIYON_ORCHESTRATION=machine RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval-enregistrer
```

La garde du jalon 0 attrape le mélange dans un jeu **déjà peuplé** ; elle ne peut rien pour
la première campagne, dont le répertoire est vide. C'est le **tir d'essai du jalon 4** qui
couvre ce cas — douze appels sur `hors_catalogue` seul, dont la porte de sortie vérifie que
l'en-tête produit porte bien `orchestration: machine`.

La paire est aussi écrite dans le commentaire de la cible `eval-enregistrer` du `Makefile`,
c'est-à-dire **là où on la tapera**.
