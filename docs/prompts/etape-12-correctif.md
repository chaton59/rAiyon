# Prompt Claude Code — Correctif de l'étape 12 : ce que `eval-live` a montré

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`, au commit `9543df5`. L'étape 12 est franchie : 823
tests purs, 86 d'intégration, seize cassettes, `make eval` qui rend un tableau et sort en
code non nul si un critère binaire tombe.

Elle a fait ce qu'on attendait d'elle, **et elle a surtout montré trois choses que trente-
cinq tours scriptés ne montraient pas.** Tu les traites ici, et rien d'autre.

⚠️ **Aucun prompt ne change dans ce commit** — ni `systeme.v1.md`, ni `grief.v1.md`, ni
`client_simule.v1.md`. L'étape 13 doit partir d'une base comparable à celle que le rapport
actuel décrit. Les trois points ci-dessous touchent `boucle.py`, `validateur/repli.py` et
`eval/metriques.py`, jamais `prompts/`.

## Avant d'écrire quoi que ce soit

Lis `src/raiyon/agent/boucle.py` (`repondre()` et `_depouiller()`),
`src/raiyon/agent/evenements.py` (`MotifDeRepli`), `src/raiyon/validateur/repli.py`,
`src/raiyon/validateur/regles.py` (`regle_valeurs_unitaires` et sa docstring),
`src/raiyon/eval/metriques.py`, et les lignes 5 et 6 du parcours de l'étape 12 dans
`PROJET.md`, plus les deux lignes de §7 qu'elles ont produites.

---

## Point 1 — Un message vide clôt le tour sans rien livrer

`_depouiller()` ignore les types de blocs inconnus, et **c'est voulu** : un bloc inattendu
ne doit pas clore une conversation par une exception. Mais quand le message n'en porte
**que** un — un `thinking` seul, observé en vrai à `make eval-live` —, `message.texte` est
vide et `message.appels` aussi. La boucle prend la branche « aucun `tool_use`, que du
texte », loggue `boucle.fin_de_tour` en `INFO`, et rend son `IssueDuTour` **sans avoir émis
un seul événement**.

Le client reçoit `done` et rien d'autre. Le client simulé a répondu « Euh… vous êtes là ? ».

### Le correctif : un motif de repli de plus

Ajoute `MotifDeRepli.REPONSE_VIDE`, et clos le tour par un `Repli` qui le porte, avec une
phrase écrite en Python — **jamais générée**, comme les deux autres.

*Alternative écartée — traiter le message vide comme une itération sans progrès et
reboucler.* Plus généreux pour le produit : le modèle a une seconde chance, et la garde
d'itérations borne déjà le pire cas. Écartée pour une raison mécanique qu'il vaut mieux ne
pas découvrir en production : reboucler laisse `messages` se terminer par un message
**assistant**, et l'appel suivant devient une continuation de ce message plutôt qu'un tour
neuf. Avec un bloc `thinking` en dernière position, ce que l'API en fait n'est écrit nulle
part, et le dépôt a déjà trois précédents de capacités supposées sans être mesurées.

⚠️ **Si tu veux malgré tout la reprise, mesure-la d'abord** — un appel réel, un message
assistant vide en queue, et tu me montres ce que l'API répond. Sans cette mesure, prends le
repli.

### Ce que ça rend mesurable

Un motif de repli distinct, donc **comptable par le rapport dès la prochaine exécution**.
C'est la même raison qui a fait naître `MotifDeRepli` à l'étape 9 : deux causes qui se
corrigent à deux endroits différents ne doivent pas partager un compteur.

### Une ligne d'`evenements.py` à corriger au passage

L'arbitrage 12 de l'étape 8 écarte le thinking étendu « en v1 ». Les cassettes montrent que
`claude-sonnet-5` en émet **sans qu'on le demande**. La formulation décrit donc ce qu'on
demande, pas ce qu'on reçoit — amende-la là où elle est écrite, sans supprimer la décision.

---

## Point 2 — L'assistant ne sait pas expliquer son domaine

Persona `joueur_serre`, tour 4 : « c'est quoi la différence entre IPS et VA, au juste ? ».
Le modèle a voulu répondre, le validateur a refusé deux fois, et le client a lu :

> Je préfère ne rien affirmer que je n'aie pas vérifié. Pouvez-vous me redire ce que vous
> cherchez, et pour quel usage ?

**On demande au client de répéter une question qu'il a posée clairement.** Dans un produit
qui s'appelle « assistant conseil ».

### L'arbitrage à rendre, et il n'est pas dans la règle 5

**On ne desserre pas `regle_valeurs_unitaires`.** Une explication de domaine chiffrée est
une affirmation que le code ne peut pas vérifier, et le validateur n'a aucun moyen honnête
de distinguer « les dalles VA ont un meilleur contraste que les IPS » d'un « les écrans de
cette gamme montent à 240 Hz » que rien n'a rendu. Une règle qui ne sait pas trancher ne
doit pas faire semblant — c'est la position tenue partout ailleurs dans ce dépôt.

**Écris donc le périmètre de §2 explicitement, parce qu'il ne l'a jamais été :** le LLM ne
produit jamais un fait **sur le catalogue**. La conséquence, assumée, est qu'il ne produit
pas non plus de fait sur le domaine — et donc que cet assistant conseille **à partir du
catalogue**, il n'enseigne pas la technologie d'affichage.

### Ce qui se corrige ici : la réponse, pas la règle

`PHRASE_GENERIQUE` sert aujourd'hui deux cas — aucune recherche dans le tour, et une
question rejetée. Elle en sert un troisième sans l'avoir prévu : un message refusé deux
fois **où aucun produit n'était en jeu**, c'est-à-dire une question de domaine.

Ajoute la troisième phrase. Elle doit faire deux choses que la générique ne fait pas :

1. **dire ce que l'assistant peut et ne peut pas** — « je ne vous dirai que ce que le
   catalogue dit, je ne vais pas vous inventer une comparaison de technologies » ;
2. **basculer sur ce qui est disponible** plutôt que renvoyer la question. S'il y a un
   `ResultatSondage` dans le tour, la phrase peut dire ce que le catalogue **contient** sur
   le champ en question — c'est exactement ce que `probe_catalog` existe pour faire dire
   (§3.7), et c'est un fait fourni.

⚠️ **Rien de cette phrase n'est généré, et rien n'y est interpolé sans passer par un
formateur de `repli.py`** — même règle que le template de recommandation. Une phrase de
repli qui inventerait un chiffre serait le comble.

⚠️ Le repli reste relu par le validateur, comme à l'étape 9. Si ta nouvelle phrase ne passe
pas ses propres règles, c'est la phrase qui est fautive.

### Un onzième scénario, et il change ce que le rapport dit

Le taux de repli à 0 % du rapport actuel est un **artefact du jeu de scénarios** : les dix
posent des questions sur le catalogue, un vrai client en pose sur le domaine. Ajoute
`question_de_domaine` — le client demande une explication technique en cours de dialogue —
et enregistre sa cassette.

Ce scénario doit **faire monter le taux de repli au-dessus de zéro**, et c'est le
résultat attendu : un rapport qui affiche 0 % de repli sur un produit qui se replie
réellement décrit mal ce produit.

---

## Point 3 — La métrique nº3 est au plancher, et deux ajouts au rapport

### 3a. Compte les **tours client** avant la première valeur

`questions_avant_premiere_valeur` vaut 0 sur les onze prises qui livrent une valeur. Ce
n'est **pas** un défaut de mesure — c'est la règle « donner avant de demander » qui
fonctionne, et il ne faut surtout pas réécrire les scénarios pour faire bouger le chiffre.

Mais une métrique collée à son plancher ne détecte plus qu'une régression vers le haut,
alors que §5 étape 13 dit de la viser en priorité.

**§3.9 dit déjà ce qu'il faut compter** : *« le bon indicateur est le délai avant première
valeur, pas le compte de questions »*. Le critère nº3 mesure donc désormais le **nombre de
tours client** avant le premier `ProduitsTrouves` non vide — ce que le client vit :
combien de fois ai-je dû parler avant d'obtenir quelque chose. Il ne sera pas au plancher
sur les scénarios où demander est légitime (budget absent, catégorie hors catalogue,
question de domaine).

`questions_avant_premiere_valeur` **reste calculée et publiée sans seuil** : elle ne
mesure plus le critère, elle mesure la règle de dialogue, et les deux méritent d'être
suivies.

⚠️ Le seuil de §4 est « ≤ 2 » et il portait sur des questions. Relis-le en tours client et
dis-moi si tu le gardes à 2 — je ne l'ai pas tranché, et il ne veut pas mécaniquement dire
la même chose.

### 3b. Les règles qui ne se déclenchent jamais

Ton propre constat de l'étape 12 : le critère nº1 détecte un trou dans la **réaction** à
une règle, et ce qui détecte une règle **manquante**, c'est l'effondrement du taux de
rejet. Il en reste une conséquence à fermer.

**Une règle qui ne tire jamais est indistinguable d'une règle absente.** Sur tes 35 tours,
trois codes tirent (`montant_non_fourni` ×7, `valeur_non_fournie` ×3, `ecart_non_dit` ×1)
et deux ne tirent pas : `id_inconnu` et `nom_reecrit`.

Ajoute au rapport une ligne **« règles jamais déclenchées sur la suite »**, dérivée de
`CodeGrief` — pas d'une liste écrite à la main, sinon un sixième code futur n'y
apparaîtrait jamais — avec le renvoi vers `tests/validateur/test_pieges.py`, qui les
exerce.

Sans elle, `0,31 grief/tour` se lit comme une couverture. Avec elle, on sait sur quoi le
chiffre porte — et à l'étape 13, un taux qui descend cesse d'être ambigu : on saura
**quelles** règles ont cessé de tirer.

### 3c. Ce qui ne bouge pas

`AUCUNE_RECHERCHE_SANS_BUDGET` reste l'attente, et le passage par `suggest_next_question`
reste publié sans seuil : une attente posée sur un nom d'outil mesure le mécanisme et non
le produit, et §3.8 dit que la question suggérée est une suggestion. **Écris cette règle
dans `scenario.py`** pour les scénarios futurs : *une attente qui nomme un outil est
suspecte par défaut.*

---

## Tests attendus

1. **Un message assistant qui ne porte qu'un bloc inconnu clôt le tour par
   `Repli(motif=REPONSE_VIDE)`** — avec le faux client, un bloc `thinking` seul. Le tour
   émet **exactement un** événement.
2. Le même cas **persiste l'historique correctement** : le message vide reste dans les
   `tours`, et le tour suivant repart d'un historique que l'API accepte.
3. **La troisième phrase de repli est rendue** quand un texte est refusé deux fois sans
   qu'aucun produit ne soit en jeu, et **la phrase générique reste rendue** sur une question
   rejetée. Les deux cas ne partagent pas de compteur.
4. **La phrase de repli de domaine passe les cinq règles du validateur**, contre un
   contexte fourni non vide. C'est le test qui empêche le comble.
5. **Le critère nº3 compte des tours client** : une prise où le client parle deux fois
   avant le premier `ProduitsTrouves` non vide rend 2, quel que soit le nombre de questions
   posées dans ces tours.
6. **Une prise qui ne livre jamais de valeur reste `None`** et n'entre pas dans la médiane
   — le comportement actuel, à ne pas casser.
7. **La ligne « règles jamais déclenchées » est dérivée de `CodeGrief`** : un test ajoute
   un code fictif à l'énumération, ou vérifie par introspection que la liste couvre tous
   les membres. Une liste écrite à la main doit faire échouer ce test.

---

## Porte de sortie

- `make check` vert — sans base, sans conteneur, sans clé.
- `make test-int` vert.
- **`make eval` relancé sans réenregistrer les seize cassettes existantes** : aucun prompt
  n'a changé, aucune empreinte ne bouge. Si une cassette réclame une régénération,
  arrête-toi et dis-le — cela voudrait dire que le correctif a changé autre chose que ce
  qu'il annonce.
- La cassette de `question_de_domaine` enregistrée, et **le taux de repli du rapport
  au-dessus de zéro**.
- Le tableau complet, avec le nº3 recompté et la ligne des règles jamais déclenchées.
  Colle-le-moi.
- **Neutralise la nouvelle branche `REPONSE_VIDE`** et montre-moi que le test nº1 tombe.
  Même geste qu'au correctif de l'étape 11 : un correctif qu'on ne peut pas casser n'est
  pas vérifié.

---

## Documentation — dans le même commit

1. `PROJET.md` : une section **« Correctif — ce que `eval-live` a montré »** sous l'étape
   12, avec les trois points et leurs alternatives écartées.
2. **§2 gagne son périmètre explicite** : « le LLM ne produit jamais un fait » signifie
   **un fait sur le catalogue**, et la conséquence assumée est que cet assistant conseille
   à partir du catalogue sans enseigner le domaine. C'est la première fois que §2 est
   borné, et il l'est parce qu'une conversation réelle a montré le bord.
3. **§7** : la ligne du tour vide passe de « correctif nommé et non pris » à **éteinte**,
   barrée et non effacée. Une ligne **nouvelle** : l'assistant ne sait pas expliquer son
   domaine, c'est le prix de §2 tel qu'il est écrit, et le desserrage de la règle 5 a été
   examiné puis écarté — avec la raison.
4. **§4** : le critère nº3 dit désormais « tours client », et le seuil est celui que tu
   auras tranché.
5. `README.md` : le tableau des critères, remis à jour depuis le nouveau rapport.
6. « Ce que le correctif a appris » — et si le taux de repli non nul change ta lecture du
   rapport, dis-le là.

---

## Méthode

Un jalon à la fois.

1. **Point 1** — le motif, la phrase, les tests 1 et 2. C'est le seul des trois qui répare
   un silence total côté client ; il passe devant.
2. **Point 3a et 3b** — les métriques, sans toucher aux cassettes. `make eval` doit
   redonner un tableau sur les mêmes enregistrements, avec des chiffres différents et
   explicables. Montre-moi les deux tableaux côte à côte.
3. **Point 2** — la phrase de domaine, le onzième scénario, sa cassette.
4. La neutralisation, puis la documentation.

Expose l'alternative avant de trancher ce que je n'ai pas tranché, et dis-moi explicitement
quand un choix est risqué ou fragile. **Ne commence pas l'étape 13** : aucun prompt ne
change, pas même d'un mot.
