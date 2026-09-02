# Prompt Claude Code — Étape 13, révision du plan après le blocage de crédits

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.
> Il **remplace les jalons 1 à 3** de `docs/prompts/etape-13.md`. Le jalon 0 de ce
> document-là reste la référence de ce qui a été construit, et il ne se refait pas.

---

## Où on en est

Le jalon 0 est construit et vert — 886 tests purs, 90 d'intégration — et **rien n'est
committé**. La campagne v1 s'est arrêtée à **21 prises sur 36**, crédits épuisés. Les
crédits sont rechargés pour **une campagne**, pas trois.

## Ce qui change, et pourquoi

`etape-13.md` prévoyait `systeme.v2.md` (cible 1 seule) puis `systeme.v3.md` (cibles 2 et
3), et une campagne v1 neuve pour comparer deux jeux du même jour. **Ce découpage est
révisé** : il coûtait ~500 appels, le budget est devenu contraignant, et il est arbitré à
la baisse en connaissance de cause.

Le plan révisé : **une seule `systeme.v2.md`, portant les trois cibles**, comparée au jeu
de l'étape 12 qui existe déjà. Une campagne, ~206 appels.

**Ce que ça coûte, et tu l'écris dans le rapport plutôt que de le laisser deviner :**

1. **L'attribution entre les trois cibles ne vient plus de l'isolation expérimentale.**
   Elle vient de l'**appendice des phrases refusées** : on lit que « 65 $ » et « 47 $ de
   plus » ont disparu, on ne le déduit pas d'un delta global. C'est une attribution par
   inspection, plus faible qu'un plan d'expérience, et suffisante ici parce que les cibles
   2 et 3 n'ont **aucune empreinte** sur le taux de rejet — leur effet ne peut pas être
   confondu avec celui de la cible 1 sur cette métrique.
2. **La dérive du modèle reste dans la comparaison** v1-étape12 → v2, puisque les deux jeux
   ne datent pas du même jour. Elle se publie comme **borne supérieure**, jamais comme la
   dérive : l'écart confond la dérive du modèle et le bruit d'échantillonnage que §7
   documente, et il majore la première sans la mesurer.
3. **Le prompt grandit de trois sections d'un coup.** Si une métrique se dégrade
   globalement — nº3 qui monte, nº4 qui baisse — **la longueur du prompt est un suspect au
   même titre que son contenu**, et la parade serait de fondre plutôt que d'ajouter. Écris-le
   comme risque avant de lancer la campagne, pas après avoir vu les chiffres.

**Ce qui est reporté, et écrit comme tel** : le découpage v2/v3 (la trace de la décision et
de sa révision reste dans `docs/prompts/`, les deux documents se lisent ensemble), la dette
nº1 de l'étape 8, `grief.v1.md`, et la généralisation du catalogue — qui n'est pas une
extension de cette étape mais un projet, parce qu'elle rouvre §3.5.

---

## Jalon 1 — committer, sauver les 21 prises, et la question de validateur qui est gratuite

Aucun appel API dans ce jalon. Aucun.

### A. Committer le jalon 0

Il est vert et il n'existe nulle part. Le rapport partiel n'est pas un obstacle : le
garde-fou que tu as écrit refuse justement d'en produire un faux. Message de commit qui dit
que l'instrument est construit et que la campagne v1 est incomplète.

**Tes deux arbitrages, tranchés :**

* **`systeme.v2.md` rédigé en avance pendant le jalon 0 : garde-le.** Il est inerte, aucune
  empreinte n'en dépend, et il devient le point d'arrêt du jalon 2 ci-dessous. Note dans le
  commit qu'il a été écrit hors du périmètre annoncé — le dire coûte une ligne, et c'est la
  discipline que le dépôt tient partout ailleurs.
* **`PROJET.md` §5 étape 13 déjà écrit pour le jalon 0 : très bien**, y compris le constat
  que « viser en priorité la métrique nº3 » est inapplicable. Il se complétera au jalon 3.

### B. Les 21 prises v1 ne sont pas perdues — elles mesurent la dérive

Elles sont payées, et elles couvrent 21 paires avec le jeu de l'étape 12. **Une mesure de
dérive n'a pas besoin d'un jeu complet : elle a besoin de paires.** Vingt et une suffisent
largement pour une borne supérieure.

* range-les sous `evals/cassettes/systeme.v1-partielle/`, marquées comme jeu **incomplet et
  archivé** — donc exemptes du refus de rapport partiel, comme tu l'as prévu ;
* `make eval-comparer` compare sur **l'intersection des prises présentes dans les deux
  jeux**, et **nomme ce que l'intersection couvre** — 21 prises sur 19 scénarios-prises
  communs, en excluant `zero_budget_trop_bas`, `desserrage_refuse`,
  `question_de_domaine` et `categorie_efface_budget` qui manquent d'un côté ;
* ⚠️ l'exclusion n'est pas neutre : **trois des cinq tours à griefs de l'étape 12 sont
  précisément dans les scénarios manquants.** La borne de dérive porte donc sur les
  scénarios les plus calmes, ce qui la sous-estime probablement. Écris-le à côté du chiffre,
  sinon le chiffre ment par omission.

### C. Enregistrer le `usage` dans l'en-tête de cassette

Trois lignes dans le client d'enregistrement de `eval/client.py`, qui appelle le SDK
directement : il lit `response.usage` et le pose dans la cassette. **Il ne touche ni au
`Protocol` `ClientLLM`, ni à `ReponseLLM`** — la même raison qui a fait écarter la capture
de l'identifiant de modèle résolu ne s'applique pas ici, puisque rien de la boucle ne passe
par là.

Et `make eval-enregistrer` affiche un cumul en cours de campagne : prises faites, appels,
jetons entrants et sortants. La campagne d'aujourd'hui s'est arrêtée au milieu sans que
personne ne puisse dire ce qu'elle avait consommé ; ça ne doit pas se reproduire au milieu
de la campagne v2.

### D. La ligne de validateur sur `desserrage_refuse.1` — à trancher **avant** d'écrire v2

C'est ta trouvaille du jalon 0, et elle est plus importante que son étiquette « à
qualifier ». Deux des quatre griefs de ce tour portent sur :

> « le passage à **300 $** et le **24 pouces** n'ont pas été pris en compte »

Le modèle répète au client **les chiffres que le client vient d'énoncer**, pour lui dire
qu'ils ont été refusés — c'est-à-dire exactement ce que la section 9 du prompt lui ordonne
de faire (« dites-le au client »). Le validateur mord sur un comportement correct.

**Tu as eu raison de ne pas le corriger dans v2** : apprendre au modèle à ne plus citer ces
chiffres lui apprendrait à taire ce que §9 exige. C'est une ligne de validateur.

Le diagnostic à poser, et il est cadré : le `ContexteFourni` range les faits par leur
provenance — outils. **La parole du client n'est une provenance pour personne**, et c'est
pour ça que le grief tombe. La question à trancher est donc : *un nombre énoncé par le
client dans son propre message est-il un fait fourni ?*

* **Alternative 1 — oui, avec une provenance dédiée.** Les nombres du message client entrent
  dans le contexte, dans un champ à part, comme les agrégats l'ont fait à l'étape 9. Ça
  ferme le faux positif proprement.
  ⚠️ **Et ça ouvre un trou que tu dois mesurer avant de le choisir** : un client qui écrit
  « l'ASRock est à 50 $ » rendrait « 50 $ » citable dans une phrase qui nomme un produit. Le
  validateur ne sait pas distinguer une citation attribuée d'une affirmation.
* **Alternative 2 — non, et le faux positif est le prix de la règle 2.** Cohérent avec la
  position tenue partout : une règle qui ne sait pas trancher ne fait pas semblant. Mais ici
  elle tranche, et **contre** le comportement demandé.
* **Alternative 3 — restreindre la provenance client aux nombres que `record_criteria` a
  effectivement refusés**, qui sont dans l'état de session et donc déjà connus du code.
  Beaucoup plus étroit, et adossé à un fait que le moteur a produit plutôt qu'à du texte.

**Ce qui rend cette question gratuite, et c'est pour ça qu'elle passe avant la campagne :**
un changement de validateur se mesure **au rejeu**, sur les 40 cassettes déjà sur le disque,
sans un seul appel API (arbitrage A de l'étape 12). Tu peux donc chiffrer les trois
alternatives avant d'en choisir une, et v1 comme v2 seront ensuite mesurés par le **même**
validateur — c'est la condition pour que la comparaison du jalon 2 veuille dire quelque
chose.

**Expose-moi les trois avec leurs chiffres, et attends mon arbitrage avant de commiter le
choix.**

---

## Jalon 2 — `systeme.v2.md`, les trois cibles, une campagne

### Le contenu

**Trois sections ajoutées, aucune section existante modifiée.** Le diff doit rester lisible
d'un coup d'œil.

1. **Les façons de fabriquer un chiffre à partir de chiffres vrais** — estimer (déjà en §2),
   **arrondir une borne** (`65 $` pour `64,98 $`), **dériver un écart entre deux nombres
   fournis** (`47 $ de plus`, arithmétiquement vrai et jamais fourni — c'est l'opération que
   v1 ne nomme nulle part), **chiffrer un assouplissement** que le diagnostic n'a pas rendu
   (`redescendez à 120 Hz`). Avec l'exception qui est fournie, elle : l'écart au budget d'un
   produit hors budget, que §7 du prompt exige de dire.
2. **Le périmètre de domaine.** §2 de `PROJET.md` l'a gagné au correctif de l'étape 12 — le
   LLM ne produit jamais un fait **sur le catalogue**, et cet assistant conseille à partir du
   catalogue sans enseigner la technologie. **Rien de cela n'a jamais été dit au modèle.** La
   section doit dire ce que l'assistant ne fera pas **et** basculer sur ce que le catalogue
   contient — « 32 de ces écrans sont en VA » est un fait fourni, et `probe_catalog` existe
   pour le faire dire.
3. **Ce que le front rend.** Le gras et les sauts de ligne, rien d'autre. Pas de backticks,
   pas de listes numérotées, pas de titres. §7 le dit depuis l'étape 11 : c'est le prompt
   qu'on corrige, pas le front qu'on arme d'un parseur.

⚠️ **Attends-toi à ce que le compteur de chiffres des tours de domaine ne tombe pas à zéro**,
et à ce que ce soit le bon résultat — la section 2 demande explicitement de citer ce que le
catalogue contient. C'est l'appendice verbatim qui tranche, pas le compteur.

### Le point d'arrêt

**Montre-moi le diff `systeme.v1.md` → `systeme.v2.md` et attends.** 206 appels sont trop
chers pour être dépensés sur une rédaction que je n'ai pas relue. Tu as déjà un
`systeme.v2.md` écrit au jalon 0 : reprends-le, complète-le des sections 2 et 3, et
présente-le comme un diff.

### La campagne

36 prises — trois par scénario, **six sur `question_de_domaine`**. D'un seul tenant : le
préfixe mis en cache expire après quelques minutes d'inactivité, et une écriture de cache
coûte 1,25× une lecture. Enregistrer par petits bouts espacés fait repayer le préfixe à
chaque reprise.

**Si la campagne s'interrompt encore**, dis-moi immédiatement où elle en est et ce qu'elle a
consommé — le cumul du jalon 1, point C, existe pour ça.

### La comparaison

`docs/eval/rapport.v2.md`, puis les tableaux face au jeu de l'étape 12. Pour **chaque**
écart, la mention explicite de s'il dépasse ou non la dispersion mesurée. **Un écart
inférieur à la dispersion n'est pas un signal, et tu l'écris ainsi.**

Rappels de lecture, tous les trois déjà dans `etape-13.md` et tous les trois faciles à
oublier une fois les chiffres sous les yeux :

* **nº3 ne peut pas s'améliorer** — minimum atteignable 1, médiane déjà à 1,0. C'est un
  garde-fou : ce qu'on surveille, c'est qu'elle ne monte pas ;
* **un taux de rejet qui baisse n'est pas en soi une bonne nouvelle.** Croise-le avec la
  ligne « règles jamais déclenchées » : si un code cesse de tirer **et** que la forme
  correspondante a disparu de l'appendice, c'est le prompt ; s'il cesse de tirer sans que la
  prose ait changé, c'est un trou ;
* les cibles 2 et 3 ne doivent **rien** faire au taux de rejet. S'il bouge de façon que la
  cible 1 n'explique pas, c'est un effet inattendu d'un changement censé n'en avoir aucun, et
  c'est le risque principal d'une v2 qui porte trois choses.

---

## Jalon 3 — arbitrage, neutralisation, documentation

1. **`systeme.v2.md` passe-t-il en vigueur ?** C'est un arbitrage, pas une évidence. Expose
   le pour et le contre si une métrique a reculé.
2. **La neutralisation.** Casse quelque chose de ce que tu as ajouté — l'appendice des
   phrases refusées, la sélection de version, la comparaison sur intersection — et montre-moi
   le test qui tombe.
3. **Documentation**, dans le même commit :
   * `PROJET.md` §5 étape 13 : le parcours complet, **la révision du découpage et sa raison
     budgétaire**, les alternatives écartées, et l'arbitrage de validateur du jalon 1 D ;
   * §7 : les lignes du domaine, de `PHRASE_DE_DOMAINE` — qui se ferme en disant qu'un bon
     prompt la rend **plus rare**, pas plus fréquente — et du markdown. La dette nº1 et le
     découpage v2/v3 non fait y entrent comme lignes ouvertes, avec leur raison ;
   * `README.md` : le tableau des critères depuis le rapport de la version retenue ;
   * `docs/eval/LISEZMOI.md` : lequel des rapports décrit quoi. Quatre fichiers presque
     identiques sans index sont un piège pour le relecteur.

## Porte de sortie

* `make check` et `make test-int` verts.
* Le jalon 0 committé, et le jeu partiel archivé et nommé.
* L'arbitrage de validateur tranché **sur des chiffres obtenus au rejeu**, sans appel API.
* `systeme.v1.md` et `systeme.v2.md` coexistent, 36 prises v2 enregistrées, `rapport.v2.md`
  écrit.
* **La comparaison v1-étape12 / v2, chiffres en main**, avec la dispersion en regard de
  chaque écart, et la borne de dérive publiée avec sa réserve d'échantillon.
* Une neutralisation montrée.

## Méthode

Un jalon à la fois. **Trois points d'arrêt obligatoires** : les trois alternatives de
validateur chiffrées avant que tu en commites une, le diff v1 → v2 avant la campagne, et
tout moment où `make eval` réclame une régénération que le jalon en cours n'annonçait pas.

Expose l'alternative avant de trancher ce que je n'ai pas tranché, et dis-moi explicitement
quand un choix est risqué ou fragile. Étape 13 et rien d'autre : ni `schema_outils.py`, ni
`grief.v1.md`, ni le front, ni le catalogue.
