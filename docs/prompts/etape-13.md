# Prompt Claude Code — Étape 13 : itération sur les prompts

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`, au commit `a5521fc`. Les étapes 1 à 12 sont franchies,
correctif de l'étape 12 compris : 853 tests purs, 86 d'intégration, `make check`,
`make test-int` et `make eval` verts. Le harnais rejoue les dix-neuf prises committées et
rend `docs/eval/rapport.md`.

L'étape 13 est la seule du plan dont la porte de sortie est une **comparaison** : deux
versions de prompt, chiffres en main, et la trace conservée. Tu ne fais que ça.

## Ce qui a déjà été tranché — ne le rouvre pas

Ces huit points sont sortis d'un cadrage préalable. Ils sont des **contraintes**, pas des
suggestions. Si l'un d'eux te paraît faux en cours de route, **arrête-toi et dis-le**
plutôt que de le contourner.

1. **Deux versions, dans cet ordre.** `systeme.v2.md` porte la **cible 1 seule** (la
   rédaction chiffrée). `systeme.v3.md` porte les **cibles 2 et 3** (le périmètre de
   domaine, et le markdown que le front ne rend pas). La cible 1 est la seule à empreinte
   métrique forte : elle se mesure seule ou elle ne se mesure pas.
2. **`systeme.v1.md` ne se modifie pas en place**, et les trois fichiers coexistent. Sans
   les trois, il n'y a rien à comparer.
3. **Trois prises par scénario, six sur `question_de_domaine`, et v1 est réenregistrée.**
   La comparaison porte sur deux jeux du même jour et du même modèle.
4. **La cible 2 ne se mesure pas par une attente bloquante** — voir le jalon 0, point D,
   qui explique pourquoi l'attente évidente a été écrite puis refusée.
5. **La dette nº1 de l'étape 8** — résorber la duplication entre `DESCRIPTION_SONDER` /
   `DESCRIPTION_PRECISION` et le prompt système — est **reportée**, et tu l'écris comme
   telle. `schema_outils.py` fait partie du préfixe mis en cache : le toucher périme les
   cassettes au même titre qu'un prompt, et le faire dans la même version qu'un changement
   de prompt rend l'effet inattribuable, ce que la dette dit vouloir éviter.
6. **`grief.v1.md` ne change dans aucune des deux versions**, et c'est une ligne ouverte,
   pas un oubli — voir le jalon 3.
7. **Le préfixe mis en cache reste identique octet pour octet** (§3.13) : ni date, ni état,
   ni numéro de tour, ni catégorie dans le prompt système. Sélectionner un **fichier** par
   variable d'environnement n'interpole rien et ne viole pas cette règle ; interpoler quoi
   que ce soit dans le texte la viole.
8. **Ne coupe pas le nombre de prises pour tenir un budget.** L'écart-type des scénarios
   calmes est ce qui dit s'ils sont restés calmes par construction ou par chance. Si tu
   dois couper, coupe le **nombre de scénarios de la campagne v3**, et écris-le dans le
   rapport — tu perds alors la détection d'un effet inattendu ailleurs, qui est le risque
   principal d'un changement de prompt.

## Avant d'écrire quoi que ce soit

Lis `prompts/systeme.v1.md` en entier, `src/raiyon/agent/prompts.py`,
`src/raiyon/eval/cassette.py`, `client.py`, `executeur.py`, `metriques.py`, `rapport.py`,
`scenario.py`, `scripts/eval.py`, `src/raiyon/validateur/regles.py` et `extraction.py`,
`docs/eval/rapport.md`, et dans `PROJET.md` : §2 et son périmètre, §3.8, §3.9, §3.11,
§3.13, §3.14, §4, §5 étapes 12 et 13, et les lignes de §7 sur la cassette-tirage, l'entier
nu, l'affirmation de domaine chiffrée, `PHRASE_DE_DOMAINE`, et le markdown.

---

## Le diagnostic qui fonde l'étape — lis-le avant de proposer autre chose

Le rapport publie `montant_non_fourni ×7`, `valeur_non_fournie ×3`, `ecart_non_dit ×1`,
soit 11 griefs sur 44 tours. **Ces 11 griefs tiennent en cinq tours**, dans cinq prises sur
dix-neuf. En lisant chaque texte refusé contre sa réécriture dans les cassettes :

| Prise | Écrit puis refusé | Opération fautive |
|---|---|---|
| `besoin_flou.3` | « de **65 $** à **plus de 9000 $** » → réécrit « 64,98 $ à 9333,00 $ » | **arrondir** une borne de sondage |
| `changement_davis.1` | « en QHD **pour 47 $ de plus** », « en 240/180 Hz pour **moins de 150 $** » | **dériver un écart** entre deux prix fournis ; arrondir |
| `budget_serre.1` | « accepter **24 pouces**, ou redescendre à **120 Hz** » | **chiffrer un assouplissement** que le diagnostic n'a pas rendu |
| `zero_budget_trop_bas.1` | « il est à 142,99 dollars » sans dire de combien il dépasse | `ecart_non_dit`, corrigé à la réécriture |
| `desserrage_refuse.1` | quatre griefs, puis une **réécriture vide** — le `REPONSE_VIDE` que le correctif a compté | à qualifier ; voir le jalon 3 |

Ce que ça dit, et qui n'est pas ce que §7 annonçait : **la section 4 du prompt tient.** « Une
fourchette n'est jamais un prix » n'est enfreinte nulle part ; le modèle n'a pas servi une
borne de sondage comme prix de produit. Ce qui casse, c'est §2, sur **trois opérations
qu'aucune section ne nomme** : arrondir une borne, dériver un écart entre deux nombres
fournis, chiffrer un assouplissement. §2 interdit d'estimer et d'arrondir ; il ne dit rien
du **calcul**, et « 189,99 − 142,99 = 47 » est arithmétiquement vrai sans avoir jamais été
fourni.

⚠️ **Cette attribution est inférée des réécritures, pas lue.** Le rapport publie des codes,
pas des phrases. C'est la raison d'être du point A du jalon 0 : la refaire à la main a coûté
une demi-heure, et le harnais a déjà l'information.

⚠️ **Cinq événements.** La dispersion mesurée dit que `besoin_flou` fait 0, 0, 2 rejets
selon la prise, `budget_serre` 2, 0, 0, `zero_budget_trop_bas` 1, 0, 0. Sur le même prompt
et le même scénario, l'écart prise-à-prise vaut la totalité de l'effet qu'on espère
mesurer. C'est pour ça que le nombre de prises monte, et c'est pour ça que le point 8
ci-dessus n'est pas négociable.

---

## Jalon 0 — l'instrument, aucun prompt ne change

**Aucun fichier de `prompts/` n'est touché dans ce jalon.** Il installe de quoi comparer, et
il réenregistre v1. Si `make eval` réclame une régénération de cassette avant le
réenregistrement volontaire, **arrête-toi et dis-le** : cela voudrait dire que tu as changé
autre chose que ce que le jalon annonce.

### A. Le rapport publie la phrase refusée, pas seulement son code

Un appendice au rapport : une ligne par grief, avec le scénario, la prise, le tour, le code,
et **la phrase que le validateur a refusée**. Recalculée au rejeu comme tout le reste, donc
disponible rétroactivement sur les cassettes existantes sans en réenregistrer une.

Sans elle, l'étape 13 itère sur des compteurs : un taux qui descend de 11 à 5 ne dit pas
**quelle forme** a disparu, et c'est la seule chose qu'on veuille savoir d'un changement de
prompt.

### B. Le rangement, et ce qu'on conserve de l'étape 12

* les cassettes vont dans `evals/cassettes/<version>/`, la version étant celle du prompt
  système (`systeme.v1`, `systeme.v2`, `systeme.v3`) ;
* le rapport devient `docs/eval/rapport.<version>.md` ;
* **les dix-neuf cassettes actuelles sont conservées** sous `evals/cassettes/systeme.v1-etape12/`,
  et le rapport actuel sous `docs/eval/rapport.v1-etape12.md`, **intacts**. `systeme.v1.md`
  ne changeant pas, ce jeu reste rejouable : le tirage que la documentation de l'étape 12
  cite reste reconstituable, et pas seulement lisible.

*Alternative écartée — n'écraser et ne garder que les rapports.* Moins cher. Écartée parce
qu'elle fait décrire par §7 et par le correctif de l'étape 12 un tirage qui n'existe plus
nulle part, et parce qu'un changement de moteur ultérieur ne se rejouerait plus contre v1 :
la comparaison cesserait d'être reproductible, ce qui est précisément la propriété que
l'arbitrage A de l'étape 12 achète en ne figeant pas les `tool_result`.

### C. La version en vigueur devient sélectionnable

`SYSTEME_V1` est une constante de module. Elle devient une **sélection de fichier** par
variable d'environnement, avec `systeme.v1` par défaut jusqu'au jalon 3, exposée telle
quelle par `PromptExpose` et par le log de démarrage, et honorée par `scripts/eval.py` en
enregistrement comme en rejeu.

⚠️ **Elle sélectionne un fichier, elle n'interpole rien.** Le test existant qui vérifie
qu'aucun prompt ne porte de marqueur d'interpolation doit balayer **les trois fichiers**, pas
seulement celui en vigueur.

### D. La cible 2 se mesure par une observation, pas par une attente

**Écris cette section dans `scenario.py`, avec son histoire, parce qu'elle a été tranchée
deux fois.**

L'attente évidente — *sur un tour déclaré de domaine, la prose ne contient aucun chiffre* —
est vraie sur les six tours de domaine de v1 : deux prises sur trois refusent le chiffre
d'elles-mêmes, la troisième écrit `3000:1 à 6000:1`. Elle a pourtant été **refusée**, et
pour une raison qui ne se voit pas en regardant v1 :

> `PHRASE_DE_DOMAINE` existe pour **basculer sur ce que le sondage a rendu**, et le jalon 2
> va demander au modèle de faire exactement cela. Une attente « aucun chiffre » échouerait
> donc sur le comportement que v3 cherche à produire : **elle pénaliserait le changement
> qu'elle évalue.** Et l'admettre en autorisant les chiffres fournis, c'est réécrire le
> validateur — une seconde lecture de la prose contre le contexte, plus faible que la
> première, que l'arbitrage E de l'étape 12 refuse.

Donc : **une observation publiée sans seuil**, sur les tours que le scénario déclare de
domaine — *nombre de valeurs chiffrées dans la prose*. Aucun test ne peut échouer à tort,
et l'évolution v1 → v3 est lisible. Sur v1, la mesure vaut zéro sur deux prises et non nul
sur la troisième.

* **Réutilise `extraction.NOMBRE`** pour compter. N'écris pas une seconde façon d'extraire un
  nombre dans ce dépôt : le jour où l'une des deux change, elles diront deux choses. Dis dans
  le rapport ce que le compte vaut réellement sur v1 — un ratio écrit `3000:1` compte pour
  deux nombres et non pour un, et il vaut mieux l'écrire que laisser croire à un décompte de
  faits.
* **L'appendice verbatim est la preuve.** Le rapport publie la prose complète des tours
  déclarés de domaine, pour toutes les prises. La cible 2 se compare en lisant, sur un
  artefact committé que n'importe qui peut relire — pas en croyant un compteur.

**La règle générale de `scenario.py` gagne un second membre.** Elle disait : *une attente qui
nomme un outil est suspecte par défaut — décris un résultat, pas un chemin.* Ajoute ce que ce
cas lui apprend :

> *Une attente qui lit la prose est suspecte, et la question n'est pas seulement « est-elle
> vraie sur le prompt que je mesure ? » mais « restera-t-elle vraie sous les versions de
> prompt à venir ? ». Une attente qui pénalise le comportement qu'une version future cherche
> à produire mesure le passé et bloque le progrès.*

C'est exactement ce qui a lâché ici, et c'est la seule chose que le cas apprend au dépôt.

### E. Le markdown, mesuré avant d'être corrigé

Un compteur publié **sans seuil** : occurrences, dans la prose livrée, des formes que le
front ne rend pas — les backticks au premier chef, et ce que tu constateras en relisant les
textes des cassettes. Il n'a de sens que mesuré sur v1 **avant** que v3 y touche.

### F. Puis la campagne v1

Trois prises par scénario, **six sur `question_de_domaine`** — c'est un scénario à trois
tours, le surcoût est marginal, et c'est le seul endroit où le nombre de prises achète
quelque chose de qualitatif plutôt que de statistique.

**Porte du jalon 0 :** `make check` et `make test-int` verts ; `docs/eval/rapport.v1-etape12.md`
et ses cassettes intacts et **rejouables** ; `docs/eval/rapport.v1.md` neuf, avec les trois
appendices remplis ; et le tableau des deux v1 côte à côte, que tu me montres.

### G. Ce que l'écart entre les deux v1 mesure, et ce qu'il ne mesure pas

Publie-le. C'est une information que le dépôt n'a pas : deux jeux du même prompt, à deux
dates.

⚠️ **Publie-le comme une borne supérieure de la dérive du modèle, jamais comme la dérive.**
L'écart confond deux choses qu'aucune des deux campagnes ne sépare : ce que le modèle a
changé entre les deux dates, et le bruit d'échantillonnage que §7 documente déjà. Il majore
la première ; il ne la mesure pas. Une phrase qui dirait « le modèle a dérivé de X » serait
fausse, et c'est le genre de phrase que ce dépôt a déjà corrigée deux fois.

⚠️ **Et l'en-tête de cassette n'épingle pas un instantané** : il enregistre le nom
**configuré** du modèle, qui est un alias, pas la version que l'API a réellement servie.
`ReponseLLM` ne porte que `blocs` et `fin`. Dis-le là où tu écris la phrase de §7, plutôt que
de laisser croire à une reconstitution exacte. *Alternative écartée pour cette étape —
capturer l'identifiant résolu dans `ReponseLLM`* : elle rouvre le `Protocol` du client, donc
le faux client et les surcharges de l'API, pour une information dont l'étape 13 n'a pas
besoin ; à rouvrir le jour où la dérive devient une question à part entière.

---

## Jalon 1 — `systeme.v2.md`, la cible 1 seule

**Une section nouvelle, pas une §2 étendue.** Le prompt v1 a été écrit court exprès, onze
sections, une idée chacune, pour que cette étape puisse en déplacer une et attribuer
l'effet. Une douzième section laisse le diff v1 → v2 lisible d'un coup d'œil ; une §2
réécrite mélange ce qui bouge et ce qui ne bouge pas.

Ce qu'elle doit nommer, et le tableau du diagnostic ci-dessus dit pourquoi ces quatre-là :

1. **estimer** — déjà dans §2, à conserver ;
2. **arrondir une borne** — `65 $` pour `64,98 $`, `plus de 9000 $` pour `9333,00 $` ;
3. **dériver un écart entre deux nombres fournis** — `47 $ de plus`. Vrai arithmétiquement,
   jamais fourni. C'est l'opération que v1 ne nomme nulle part ;
4. **chiffrer un assouplissement que le diagnostic n'a pas rendu** — `accepter 24 pouces, ou
   redescendre à 120 Hz`. §10 dit « vous n'assouplissez jamais de vous-même » et ce n'est pas
   ce qui s'est passé : le modèle **propose** au lieu d'appliquer, ce qui est correct, mais il
   propose avec des chiffres inventés. §10 ne couvre pas ce cas.

Contraintes de rédaction :

* le diff `systeme.v1.md` → `systeme.v2.md` est **une addition**, et rien d'autre. Si tu
  penses qu'une section existante doit bouger aussi, dis-le-moi et attends — deux sections
  qui bougent, c'est une attribution perdue ;
* **montre-moi le diff avant d'enregistrer quoi que ce soit.** 36 prises coûtent trop cher
  pour être dépensées sur une rédaction que je n'ai pas relue ;
* pas de marqueur d'interpolation, pas de date, pas d'état.

⚠️ **Le résultat attendu n'est pas « la métrique nº3 s'améliore ».** Elle ne peut pas : elle
compte les tours client avant la première valeur, son minimum atteignable est **1**, et la
médiane vaut déjà 1,0. §5 étape 13 demande de viser nº3 en priorité, et cette phrase est
inapplicable telle quelle — **écris-le dans PROJET.md plutôt que de le contourner.** nº3 est
un garde-fou, et le risque réel de v2 est qu'elle **monte** : un modèle plus prudent avec les
chiffres sonde davantage et montre plus tard. Le résultat qu'on cherche est « le taux de
rejet baisse **sans** que nº3 passe à 2 », et c'est cette paire qu'il faut publier ensemble.

⚠️ **Et un taux de rejet qui baisse n'est pas en soi une bonne nouvelle.** Le rapport le dit
déjà pour le critère nº1 : ce qui détecte une règle manquante, c'est l'effondrement du taux
de rejet. Relis la ligne « règles jamais déclenchées » avant de conclure : si un code cesse
de tirer **et** que la forme correspondante a disparu des appendices, c'est le prompt ; si le
code cesse de tirer sans que rien n'ait changé dans la prose, c'est un trou.

**Porte du jalon 1 :** 36 prises v2 enregistrées, `docs/eval/rapport.v2.md` écrit, et les
deux tableaux v1/v2 côte à côte avec, pour chaque écart, la mention explicite de s'il est
supérieur ou inférieur à la dispersion mesurée. **Un écart inférieur à la dispersion n'est
pas un signal, et tu l'écris ainsi.**

---

## Jalon 2 — `systeme.v3.md`, cibles 2 et 3

Deux changements, aucun des deux n'a d'empreinte sur le taux de rejet — c'est ce qui les
autorise à voyager ensemble.

### Le périmètre de domaine

§2 de `PROJET.md` a gagné son périmètre au correctif de l'étape 12 : le LLM ne produit jamais
un fait **sur le catalogue**, et cet assistant conseille à partir du catalogue sans enseigner
la technologie d'affichage. **Rien de cela n'a jamais été dit au modèle.** Le prompt v1 ne
contient pas un mot sur les questions de domaine, et `PHRASE_DE_DOMAINE` est un repli — donc
ce qu'on sert quand la conduite a déjà échoué.

La section doit faire les deux choses que le correctif demandait à la phrase de repli, mais
en amont : dire ce que l'assistant ne fera pas, et **basculer sur ce que le catalogue
contient** — « 32 de ces écrans sont en VA, 13 en IPS » est un fait fourni, et
`probe_catalog` existe pour le faire dire (§3.7).

⚠️ **C'est ce basculement qui rend l'attente « aucun chiffre » fausse** (jalon 0, point D).
Attends-toi à ce que le compteur de chiffres des tours de domaine **ne tombe pas à zéro** en
v3, et à ce que ce soit le bon résultat. La lecture de l'appendice verbatim tranche ; le
compteur seul ne tranche rien.

### Le markdown

§7 le dit depuis l'étape 11 : le front rend **deux formes et pas une de plus**, le gras et les
sauts de ligne, et le reste s'affiche tel quel — les backticks autour d'un identifiant sont
visibles à l'écran, constaté en démonstration. Le sens du correctif est écrit là-bas :
demander au prompt de ne produire que ce que le front rend, plutôt que d'armer le front d'un
parseur markdown qui rouvrirait la surface d'injection que l'arbitrage B ferme.

Le compteur du jalon 0, point E, dit si ça a marché.

**Porte du jalon 2 :** 36 prises v3, `docs/eval/rapport.v3.md`, et la comparaison v2/v3 —
appendice de domaine relu à la main, compteur de markdown, et **le taux de rejet vérifié
comme inchangé**. S'il bouge, c'est un effet inattendu d'un changement censé n'en avoir aucun,
et ça vaut d'être écrit.

---

## Jalon 3 — arbitrage, neutralisation, documentation

1. **Quelle version passe en vigueur**, et pourquoi. C'est un arbitrage, pas une évidence :
   une v3 qui gagnerait sur le domaine en perdant sur le taux de rejet se discute.
2. **`grief.v1.md`.** La réécriture vide de `desserrage_refuse.1` suit immédiatement un
   message de grief ; l'autre `REPONSE_VIDE` (`sur_specifie.1`) ne suit aucun grief. Sur un
   seul événement, ce n'est pas un diagnostic. Regarde ce que les trois campagnes en disent :
   si un repli après grief survit à v3, il devient une v4 **à un seul changement**, et si
   aucun ne survit, la ligne se ferme en le disant. Dans les deux cas c'est écrit, pas laissé
   tomber en silence.
3. **La neutralisation.** Même geste qu'aux correctifs des étapes 11 et 12 : casse quelque
   chose de ce que tu viens d'ajouter — l'appendice des phrases refusées, ou la sélection de
   version — et montre-moi le test qui tombe. Un correctif qu'on ne peut pas casser n'est pas
   vérifié.

### Documentation, dans le même commit

* **`PROJET.md` §5 étape 13** : le parcours, avec les arbitrages **et leurs alternatives
  écartées** — le découpage v2/v3 contre une version par correction, l'attente refusée et
  pourquoi, le rangement, la dette nº1 reportée. Écris aussi le constat que §5 étape 13
  demandait quelque chose d'inapplicable sur nº3, et ce que tu as fait à la place.
* **§7** : la ligne « une affirmation de domaine chiffrée passe le validateur » se met à jour
  d'après ce que v3 mesure. La ligne « `PHRASE_DE_DOMAINE` n'est exercée par aucune cassette »
  **se ferme en disant qu'un bon prompt la rend plus rare, pas plus fréquente** : chercher une
  formulation de client qui la déclenche à coup sûr, ce serait optimiser contre son propre
  correctif. La ligne du markdown se ferme ou se réduit. La dette nº1 y entre comme ligne
  ouverte, avec sa raison. Et la phrase qui date le tirage de l'étape 12 porte **la date et le
  nom du modèle**, avec la réserve du jalon 0 point G sur l'alias.
* **§3.14** : la sélection de version par variable d'environnement, et la règle que les trois
  prompts sont balayés par le test d'interpolation.
* **`README.md`** : le tableau des critères depuis le rapport de la version retenue.
* **`docs/eval/`** : les quatre rapports coexistent, et un court `docs/eval/LISEZMOI.md` dit
  lequel décrit quoi — sans lui, quatre fichiers presque identiques sont un piège pour le
  relecteur de portfolio.

---

## Tests attendus

1. **La sélection de version** honore la variable d'environnement, et le défaut vaut
   `systeme.v1` tant que le jalon 3 n'a pas tranché.
2. **Le test d'interpolation balaie les trois prompts**, pas celui en vigueur. Ajouter un
   `{quelque_chose}` dans `systeme.v2.md` doit faire échouer la suite.
3. **L'appendice des phrases refusées est dérivé du verdict du validateur**, pas d'une liste
   écrite à la main : un sixième code de `CodeGrief` doit y apparaître sans qu'on touche au
   rapport — même raison qu'à la ligne « règles jamais déclenchées » du correctif de l'étape 12.
4. **Le compteur de chiffres des tours de domaine réutilise `extraction.NOMBRE`.** Un test
   vérifie qu'il n'existe pas de seconde extraction de nombre dans le harnais.
5. **Le compteur est une observation, pas une attente** : un scénario dont un tour de domaine
   porte des chiffres **ne fait pas échouer** `make eval`. C'est le test qui empêche
   quelqu'un de le repromouvoir en attente dans six mois sans relire pourquoi.
6. **Les cassettes de l'étape 12 restent rejouables** : un test, ou une cible de `make`, qui
   rejoue `evals/cassettes/systeme.v1-etape12/` et retrouve `rapport.v1-etape12.md`. Sans
   cela, « conservé » veut seulement dire « pas effacé ».
7. **Une cassette rangée sous la mauvaise version échoue en le disant** — l'empreinte de
   prompt le détecte déjà, mais le message doit nommer le répertoire, pas seulement le hash.

## Porte de sortie

* `make check` vert — sans base, sans conteneur, sans clé.
* `make test-int` vert.
* Quatre rapports dans `docs/eval/`, et les cassettes des quatre jeux.
* **Les trois comparaisons, chiffres en main** : v1-étape12 / v1 (borne supérieure de la
  dérive), v1 / v2 (cible 1), v2 / v3 (cibles 2 et 3). Pour chaque écart, dit explicitement
  s'il dépasse la dispersion mesurée.
* La version retenue en vigueur, et l'arbitrage écrit.
* Une neutralisation montrée.

## Méthode

Un jalon à la fois, et tu me montres le résultat avant de passer au suivant. Trois points
d'arrêt obligatoires : **le diff v1 → v2 avant la campagne v2**, **le diff v2 → v3 avant la
campagne v3**, et **tout moment où `make eval` réclame une régénération que le jalon en cours
n'annonçait pas**.

Expose l'alternative avant de trancher ce que je n'ai pas tranché, et dis-moi explicitement
quand un choix est risqué ou fragile. Étape 13 et rien d'autre : ni `schema_outils.py`, ni
`grief.v1.md`, ni le front.
