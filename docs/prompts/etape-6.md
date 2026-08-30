# Prompt Claude Code — Étape 6 : moteur de matching

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`. Les étapes 1 à 5 sont franchies : le
catalogue est en base, 1 026 produits, seed committé et déterministe. Tu vas
réaliser **l'étape 6 et rien d'autre**.

## Avant d'écrire quoi que ce soit

Lis, dans cet ordre :

1. `PROJET.md` — §2 (contrainte non négociable), §3.3, §3.3bis, §3.4ter,
   §3.6, §3.7, §3.10, §3.15, §4 (critères d'acceptation), §5 étape 6, §6.
2. `catalogue/schema_attributs.md` — **la** source de vérité des rôles
   `filtre dur` / `score` / `affichage`, des types cibles, des unités et des
   plages. La convention de lecture en tête du fichier est normative : un
   attribut `affichage` **n'entre jamais** dans le matching.
3. `data/seed/rapport_seed.md` — §« Taux de remplissage par attribut, sur le
   seed final » et §« Cas limites pour l'étape 6 ». Les identifiants G1 à G4
   sont figés : **tes tests les citent en dur**. S'ils changent un jour, un test
   casse, et c'est le comportement voulu.
4. `src/raiyon/catalogue/schemas.py` et `src/raiyon/db/models.py` — **tu ne les
   modifies pas**. Le moteur se plie au schéma. Note en particulier que
   `specs_pour_base()` sérialise les `Decimal` en **chaînes** dans le JSONB :
   `specs->>'price_per_gb'` rend du texte, le cast `::numeric` est obligatoire,
   et une containment `@>` sur un nombre doit comparer une chaîne.
5. `src/raiyon/config.py` (`budget_tolerance` existe déjà, `0.15`),
   `src/raiyon/db/engine.py`, `tests/conftest.py`,
   `tests/integration/conftest.py`, `Makefile`, `.github/workflows/ci.yml`.

Ne devine aucun taux de remplissage : ils sont mesurés dans le rapport de seed,
et ce sont **ceux du seed**, pas ceux de la source. `internal-hard-drive.type`
est à 99,6 % sur la source et à 100 % sur le seed — l'étape 5 a écarté les
lignes concernées.

## Périmètre — ce que tu livres

- **A. Un registre d'attributs** exécutable, dérivé de `schema_attributs.md`.
- **B. Un modèle de critères** générique et validé.
- **C. Un dépôt** qui traduit les critères durs en SQL et rend les candidats,
  les comptages de relâchement et les valeurs atteignables.
- **D. Un scoring, un classement et une trace d'explication**, en fonctions
  pures sur une liste de `ProduitEnBase`.
- **E. Le traitement du zéro résultat** : diagnostic et propositions.
- **F. Un script de calibration** des bornes, et les constantes qu'il produit.

**Explicitement hors périmètre, à ne pas commencer :** la couche outils et le
clamp de session (étape 7), la boucle agent (étape 8), le validateur (étape 9),
l'API (étape 10). Aucun appel LLM, aucune notion de session, aucun schéma JSON
d'outil n'apparaît à cette étape. En particulier, **tu n'écris pas la fusion des
critères ni la règle de collant** : elles appartiennent à l'étape 7. Tu écris
seulement ce qu'elles auront besoin de lire — le drapeau `retrogradable` du
registre et la trace des rétrogradations appliquées.

Ne modifie ni `schemas.py`, ni `models.py`, ni les migrations. `config.py` n'est
touché que si une constante doit devenir paramétrable, et ce n'est pas le cas
ici : `budget_tolerance` suffit. ⚠️ Il est typé `float` ; convertis-le en
`Decimal(str(...))` au point d'usage. Une multiplication `Decimal * float` sur
un prix est un bug, pas un détail de style.

## Arbitrages déjà rendus — applique-les, ne les rediscute pas

### A. La frontière SQL / Python, en une phrase

> **SQL décide qui est candidat, Python décide comment on le présente.**

Côté SQL : filtres durs, comptages de relâchement, valeurs atteignables.
Côté Python pur, sur une liste de `ProduitEnBase` : scoring, pondération,
classement, trace, diagnostic et formulation des propositions.

Conséquence sur les tests, et elle est voulue : la majorité de la suite est
pure, tourne dans `make check`, sans base ni clé. Seuls les filtres et les
comptages portent le marqueur `integration`. C'est ainsi que le critère
d'acceptation nº5 est franchi — la logique de matching est pure **par
construction**, seule la récupération est SQL.

*Alternative écartée — tout en Python sur le catalogue chargé en mémoire.* Suite
instantanée et sans dépendance, mais §3.2 et §3.3bis perdent leur objet :
Postgres ne servirait plus qu'à stocker, dans un projet dont l'accroche est le
SQL. *Alternative écartée — tout en SQL, y compris le scoring.* Le classement
deviendrait intestable sans base, et une pondération en SQL est illisible.

**Note de perf, à écrire en commentaire :** les n+1 requêtes de comptage du
relâchement se ramènent à une seule avec `count(*) FILTER (WHERE …)`. À 1 026
lignes le gain est nul, donc on garde la version lisible — mais la bascule est
documentée, avec sa condition de déclenchement. C'est le même compromis
explicite que §3.3bis.

### B. Le modèle de critères est générique, pas typé par catégorie

Une liste de `Critere(champ, operateur, valeur, importance)`, validée
dynamiquement contre le registre.

*Alternative écartée — six modèles Pydantic typés, miroirs de `SpecsCpu`,
`SpecsMoniteur`…* Ils donnent du typage statique et de meilleurs messages
d'erreur, mais créent six modèles à maintenir en parallèle de six modèles de
specs — divergence garantie à la première évolution — et un schéma d'outil
énorme à l'étape 7. Le générique paie en typage ce qu'il gagne en surface, et le
registre récupère la validation.

### C. Le registre est un module, et un test garde sa cohérence

`src/raiyon/matching/attributs.py`, écrit à la main depuis
`schema_attributs.md`. Un test vérifie que ses clés **couvrent exactement** les
champs de `schemas.py`, catégorie par catégorie — ni oubli, ni champ fantôme.

Les champs `affichage` (`color`) y figurent **avec leur rôle**, ils ne sont pas
omis : c'est ce qui permet à un test de prouver qu'ils ne filtrent ni ne scorent,
et c'est exactement ce que le cas G2 exerce.

*Alternative écartée — annoter `schemas.py` via `Field(json_schema_extra=…)`.*
Une seule source, aucune divergence possible. Écartée parce qu'elle charge le
miroir du schéma SQL d'une préoccupation de matching : `schemas.py` cesserait
d'être lisible comme ce qu'il est. Le test de couverture donne l'essentiel du
bénéfice sans le mélange.

### D. Rétrogradation : ouverte sur le gradué, fermée sur la compatibilité

Le rôle du registre est le **défaut**. Un critère déclaré `souhait` sur un
attribut `filtre dur` **gradué** (numérique ou ordinal — `screen_size`,
`capacity`, `refresh_rate`, `frequence_mhz`, `memory`, `core_count`, `tdp`,
`length`) est rétrogradé en score.

La rétrogradation est **fermée** sur les attributs de compatibilité, qui sont
binaires : `ddr_generation`, `interface`, `form_factor`, `type`, `chipset`,
`microarchitecture`, `aspect_ratio`, plus `prix_usd` et `categorie`. « Plutôt de
la DDR5 » n'est pas un souhait, c'est un malentendu : de la DDR4 n'entre pas
dans le socket. **La liste vit dans le registre**, en drapeau `retrogradable`,
jamais dans les arguments d'un appel.

**La promotion inverse est interdite et lève.** Un `bloquant` sur un attribut de
rôle `score` est une erreur explicite, pas une rétrogradation silencieuse :
promouvoir `boost_clock` (66,1 % de remplissage sur le seed) en filtre dur
exclurait un tiers du catalogue sur une absence de donnée — un comblement
d'absence par la porte de derrière, ce que §3.4quater interdit.

Toute rétrogradation effectivement appliquée **entre dans la trace**. Elle ne
contourne jamais le critère nº6 : si le client a posé la contrainte comme
bloquante, le zéro résultat se dit et se propose, il ne s'assouplit pas tout
seul.

*Alternative écartée — rôle absolu.* Totalement prévisible et sans risque de
desserrage, mais le moteur produirait des zéro-résultats sur de simples
préférences, et l'agent n'aurait aucun moyen d'exprimer la nuance.

### E. NULL sur un filtre dur : exclure **et compter**

`(specs->>'refresh_rate')::int >= 144` écarte les moniteurs sans valeur. La
sémantique SQL est conservée — l'absence ne satisfait pas le critère — mais elle
cesse d'être silencieuse : le moteur rend
`ecartes_faute_de_donnee: {"refresh_rate": 7}`, champ **toujours présent**, vide
quand il n'y a rien à dire.

Trois conditions :

1. **Le compteur paie sur le zéro résultat.** « Aucun produit ne déclare sa
   fréquence de rafraîchissement » n'est pas « aucun produit ne fait 144 Hz ».
   Sans le compteur, le moteur dit la seconde phrase en pensant la première. La
   règle est mécanique : si `rouvre_si_retire == ecartes_faute_de_donnee`, le
   diagnostic est `donnee_absente` et non `critere_trop_strict`, et la
   proposition change de nature.
2. **La liste des attributs incomplets n'est pas devinée** : elle se lit dans
   les taux de remplissage du rapport de seed, recopiés dans le registre. Aucune
   requête de comptage sur un attribut à 100 %, donc surcoût nul sur la quasi
   totalité des critères — sur le seed, seuls `monitor.refresh_rate` (95,9 %) et
   `video-card.length` (96,5 %) sont concernés parmi les filtres durs.
3. **Le compteur sort du même chemin de requête que le filtre.** Deux requêtes
   écrites séparément dériveront ; c'est le mode d'échec de la double
   implémentation, en plus petit. Un seul constructeur de prédicat, deux
   projections.

*Alternative écartée — exclusion silencieuse.* Zéro ligne de code, mais on
décide que l'absence vaut « ne satisfait pas » sans jamais le dire, et c'est
indétectable en éval. *Alternative écartée — un troisième ensemble
`indetermines`.* Cohérent avec §3.10 sur le principe, mais il se propage
jusqu'aux étapes 7, 8 et 9 (le validateur devrait couvrir trois ensembles) pour
0,4 à 4,1 % des lignes.

### F. NULL sur un attribut scoré : exclure le critère et renormaliser

Sous-score 0 punit une donnée manquante ; 0,5 invente une médiane, donc comble
une absence. Le critère est donc **retiré du calcul**, les poids restants
**renormalisés**, et la trace porte `indisponible` pour ce critère.

⚠️ **C'est le point fragile de l'étape, et il s'écrit :** un produit à données
manquantes a mécaniquement moins d'occasions de perdre des points. Garde-fou —
à score égal, le produit dont **plus de critères ont été réellement évalués**
passe devant, et la trace expose ce compte (`criteres_evalues`,
`criteres_indisponibles`).

### G. Bornes de normalisation absolues, jamais relatives au lot

Chaque attribut scoré porte dans le registre une borne basse et une borne haute
**constantes**. Un sous-score est `(valeur - basse) / (haute - basse)`, borné à
`[0, 1]`, inversé si `sens = plus_bas_mieux`.

*Alternative écartée — min-max sur le lot candidat courant.* Contraste toujours
plein, mais le score d'un produit dépend des autres produits présents : deux
conversations classeraient le même produit différemment, et les tests
deviendraient sensibles au fixture.

Les queues lourdes sont **winsorisées** — `memory.price_per_gb` monte à
497,5 USD/GB. Le percentile de winsorisation (95ᵉ) est calculé **une fois sur le
seed committé** et écrit en constante, jamais recalculé au runtime : sinon c'est
du min-max déguisé.

C'est l'objet du livrable F : `scripts/calibrer_bornes.py` lit
`data/seed/produits.jsonl`, imprime les bornes par `(catégorie, champ)`, et tu
**recopies sa sortie dans le registre**, avec en commentaire la date, le nombre
de lignes du seed et la commande qui l'a produite. Le script est rejouable ; son
résultat est du code. Un test vérifie que les constantes du registre sont bien
celles que le script redonne sur le seed committé.

### H. Le prix : deux intentions distinctes, et un plafond

Par défaut, le prix est un **filtre dur seul** (le budget), et il n'intervient
dans le classement que comme **critère de départage**. C'est là que le cas G2 se
joue : deux casques dont tout est identique sauf le prix et `color`, un champ
`affichage` qui ne peut ni filtrer ni scorer.

Le prix ne devient un sous-score que sur demande explicite, et il y a **deux
demandes, pas une** — le moins cher et le mieux placé ne sont pas le même
produit :

| intention | calcul |
| --- | --- |
| `moins_cher` | sous-score décroissant avec le prix |
| `rapport_qualite_prix` | score technique ÷ prix |

Sur `internal-hard-drive` et `memory`, la source donne déjà `price_per_gb` comme
rapport naturel, et l'étape 5 l'a **recalculé sur le prix retenu** (arbitrage D
de l'étape 5) : il est utilisable tel quel. Sur les quatre autres catégories, le
ratio est calculé, et **il doit être ramené en `[0, 1]` par un plafond constant
du registre, pas par le maximum du lot** — sans quoi la G réapparaît sur un seul
sous-score et le « meilleur rapport qualité/prix » cesse d'être reproductible.

Deux règles dures :

- **le poids du sous-score prix est plafonné** : il ne doit jamais pouvoir
  renverser un critère technique que le client a énoncé, sinon « je veux 144 Hz
  et pas trop cher » finit sur un 60 Hz bon marché. Le plafond est une constante
  nommée, avec un test qui l'exerce ;
- **toute position gagnée par le prix apparaît dans la trace.** Le prix compte
  déjà deux fois — le budget borne, le score ordonne — c'est volontaire, donc ça
  s'écrit, jamais implicitement.

### I. La trace est structurée ; le français est du vocabulaire, pas des phrases

La trace ne contient **aucune phrase rédigée**. Par produit et par critère :
`champ`, `role_applique`, `statut` ∈ {`matche`, `partiel`, `rate`,
`indisponible`}, `valeur_produit`, `valeur_demandee`, `ecart`, `poids`,
`sous_score`, et le drapeau `retrograde`.

Mais le registre porte un **libellé français par attribut** (`refresh_rate` →
« fréquence de rafraîchissement ») et son unité. C'est le raisonnement de
§3.4ter appliqué ici : du français dérivé d'un **champ** — et non d'un produit —
est déterministe, donc c'est de la donnée. Le repli sur template de §3.11 niveau
3 en aura besoin ; le laisser hors du registre, c'est le redécouvrir à l'étape 9.

Aucune valeur de la trace n'est pré-formatée pour l'affichage : la mise en forme
est l'affaire de l'étape 11.

### J. Zéro résultat : diagnostic, puis proposition — jamais application

Analyse par retrait d'un critère à la fois (leave-one-out), plus, pour les
critères numériques, la **valeur atteignable** la plus proche.

1. **La valeur proposée est prise dans le catalogue** : la plus proche
   effectivement présente parmi les produits qui satisfont **tous les autres**
   critères. Jamais un seuil rond calculé — proposer « descendez à 1 To » quand
   le premier disque disponible est à 960 Go rendrait encore zéro, et
   affirmerait un fait sur le stock qui n'en est pas un.
2. **Ordre des suggestions** : d'abord l'importance déclarée (`souhait` avant
   `important` avant `bloquant`), puis le nombre de produits rouverts. Un
   critère de compatibilité ne se relâche pas par degré, il ne peut qu'être
   abandonné : il se propose **en dernier**, et seulement s'il ne reste rien
   d'autre.
3. **Si le critère bloquant est le budget, la réponse n'est pas « relâchez votre
   budget »** : c'est l'ensemble `au_dessus_du_budget` de §3.10, déjà calculé,
   avec l'écart exact. Ne duplique pas cette logique dans le relâchement —
   `prix_usd` est **exclu** des candidats au retrait.
4. **Si aucun retrait unique n'ouvre le catalogue, le moteur le dit
   explicitement** au lieu de se taire. Les combinaisons de degré 2 sont hors
   périmètre ; l'absence de solution simple est une réponse, pas un silence.
5. **La suggestion reste une proposition.** Le moteur la formule, il ne
   l'applique jamais de lui-même.

Le cas G3 est le scénario de référence : sur `internal-hard-drive`,
`form_factor = 'M.2-2280'` ET `interface = 'SATA 6.0 Gb/s'` → 0 produit, alors
que chaque critère seul en sert 52 et 85.

### K. Un tour, une catégorie

**Tous les produits rendus par un appel appartiennent à une seule catégorie**, et
la catégorie est obligatoire. Il n'y a ni panier, ni budget alloué, ni somme à
suivre : l'invariant est vérifiable en une ligne, et une « config gaming » est
structurellement impossible à servir en un tour.

Ce n'est pas au moteur de refuser une telle demande : l'étape 8 la **séquencera**
(« je conseille un composant à la fois — on commence par la carte graphique ? »).
Tu n'écris rien de cela ici ; tu écris seulement la contrainte dans le moteur et
la ligne correspondante dans `PROJET.md` §8.

### L. Comparaison des textes : égalité stricte

Sur les énumérations (`chipset` 241 valeurs, `microarchitecture` 33, `interface`
18, `form_factor`, `panel_type`, `aspect_ratio`) : **égalité stricte**, jamais de
`contains`. Sinon « RTX 4070 » attrape silencieusement « RTX 4070 Ti » et le
critère nº4 se dégrade sans qu'on le voie. C'est cohérent avec §3.7 :
`probe_catalog` rendra les valeurs distinctes, l'agent choisira dedans.

Seule exception, `marque`, que le client tape à la main : comparaison sur une
clé normalisée (minuscules, ponctuation retirée — « G.Skill » et « gskill » sont
la même marque). ⚠️ Cette normalisation s'exprime en SQL ; écris-la une fois, en
SQL, et n'en fais pas une seconde version Python.

### M. L'ordre est total et déterministe

`(score décroissant, nombre de critères évalués décroissant, prix croissant, id
croissant)`. Aucun ex æquo ne subsiste, aucun classement ne dépend de l'ordre de
retour de Postgres, et les tests peuvent asserter une liste exacte.

## Organisation du code

```
src/raiyon/matching/
    attributs.py      # registre : rôles, genres, opérateurs, bornes, libellés
    criteres.py       # Critere, Importance, Operateur, Optimisation, RequeteMatching
    depot.py          # protocole DepotProduits + DepotSql : candidats, comptages, valeurs atteignables
    score.py          # sous-scores, renormalisation, pondération — pur
    trace.py          # dataclasses de trace — pur
    relachement.py    # diagnostic et propositions à partir de comptages injectés — pur
    moteur.py         # orchestration : dépôt → score → classement → trace → résultat
scripts/
    calibrer_bornes.py
```

`relachement.py` reçoit des **comptages déjà faits**, il n'interroge rien. C'est
ce qui rend la partie la plus subtile du moteur testable hors base, en injectant
des comptages à la main.

`moteur.py` expose une fonction unique, et son résultat est un modèle typé :
`produits` (au plus 3), `au_dessus_du_budget` (au plus 2), `traces`,
`ecartes_faute_de_donnee`, `diagnostic` (renseigné seulement si `produits` est
vide). Pas de seuil de score plancher : un mauvais score reste une réponse, un
plancher recréerait un zéro-résultat silencieux. `disponible = true` est toujours
appliqué.

## Tests

`tests/matching/`, et la répartition suit exactement la frontière de l'arbitrage A.

**Purs, dans `make check`, sans base ni clé :**

- **Registre** : ses clés couvrent exactement les champs de `schemas.py` par
  catégorie ; tout attribut de rôle `score` a des bornes et un sens ; tout
  attribut a un libellé français et une unité quand elle existe ; les taux de
  remplissage recopiés valent ceux du rapport de seed.
- **Critères** : opérateur incompatible avec le genre → refus ; champ inconnu
  → refus ; champ d'une autre catégorie → refus ; `bloquant` sur un attribut de
  rôle `score` → **lève** (arbitrage D) ; `souhait` sur un filtre dur gradué →
  rétrogradé et signalé ; `souhait` sur `ddr_generation`, `interface`,
  `form_factor`, `prix_usd` ou `categorie` → **reste bloquant**.
- **Score** : borne basse → 0, borne haute → 1, au-delà → borné ; `plus_bas_mieux`
  inversé ; valeur `None` → critère exclu **et poids renormalisés**, avec
  assertion sur la somme des poids ; winsorisation exercée sur une valeur
  extrême de `price_per_gb`.
- **Prix** : `moins_cher` et `rapport_qualite_prix` ne rendent pas le même
  classement sur un même lot — écris ce test, c'est lui qui garde l'arbitrage H ;
  le plafond de poids empêche le prix de renverser un critère technique énoncé ;
  sans demande explicite, le prix ne marque **rien** et ne sert qu'au départage.
- **Classement** : ordre total, aucun ex æquo ; à score égal, le produit à plus
  de critères évalués passe devant (garde-fou de l'arbitrage F).
- **Trace** : un champ `affichage` (`color`) n'apparaît jamais avec un poids ni
  un sous-score ; une rétrogradation appliquée est présente et marquée ; aucun
  champ de la trace ne contient de phrase rédigée.
- **Relâchement**, sur comptages injectés : ordre de tri respecté ; `prix_usd`
  jamais proposé ; un critère de compatibilité proposé en dernier ;
  `rouvre_si_retire == ecartes_faute_de_donnee` → diagnostic `donnee_absente` ;
  aucun retrait n'ouvrant rien → réponse explicite.
- **Calibration** : les constantes du registre sont celles que
  `scripts/calibrer_bornes.py` redonne sur le seed committé.

Les tests de scoring s'écrivent sur une fixture synthétique d'une douzaine de
produits, pour que l'assertion reste lisible. Ces produits inventés vivent dans
`tests/`, **jamais dans `data/`**.

**Intégration, marqueur `integration`, sur la base seedée :**

- Filtre dur numérique, catégoriel, booléen, multi-critères.
- **NULL** : un critère sur `monitor.refresh_rate` écarte les produits sans
  valeur **et** les compte ; le compteur vaut zéro sur un attribut à 100 %, et
  aucune requête de comptage n'est émise dans ce cas.
- `marque` : « G.Skill », « g.skill » et « gskill » rendent le même ensemble.
- **G1** — un budget à 100 USD sur `internal-hard-drive` place
  `internal-hard-drive-c2dd3e2507` (103,92 USD) dans `au_dessus_du_budget` et
  jamais dans `produits`, avec l'écart exact. Fais-le sur les six catégories.
- **G2** — `headphones-06acf63b59` (23,47) et `headphones-393cd46c64` (41,99) :
  specs identiques, seuls le prix et `color` diffèrent. Sans demande explicite
  sur le prix, ils ont le **même score**, et le départage se fait sur le prix.
- **G3** — `form_factor = 'M.2-2280'` + `interface = 'SATA 6.0 Gb/s'` → zéro
  produit, diagnostic `critere_trop_strict`, et les deux propositions rendues
  dans l'ordre 85 puis 52.
- **G4** — un budget très large sur `monitor` fait remonter
  `monitor-0783259c60` (9 333 USD) ; le catalogue exerce bien le haut de gamme.
- Budget bloquant : zéro produit mais `au_dessus_du_budget` non vide → le
  relâchement **ne propose pas** de relever le budget.

**Porte de sortie « moins de deux secondes » :** la fixture de base est à portée
`session` et le seed est chargé **une seule fois**. Sinon on mesure le coût des
migrations et non celui du moteur, et la porte échoue pour une raison qui n'a
rien à voir avec elle.

## `PROJET.md` et `README.md`

Marque l'étape 6 ✅, dans la forme des étapes précédentes :

- **les arbitrages A à M**, chacun avec son alternative écartée et son motif ;
- une décision numérotée **3.16 — frontière SQL / Python du moteur**, portant la
  phrase « SQL décide qui est candidat, Python décide comment on le présente »,
  et la conséquence sur la lecture du critère nº5 ;
- un amendement à **§3.10** : la zone de tolérance est aussi la réponse au cas
  « le budget est le critère bloquant », et le relâchement ne la duplique pas ;
- un amendement à **§3.6** : l'exemple « il me faut aussi une ponceuse, 300 €
  pour les deux » servait à rejeter la machine à états. La composition
  multi-catégories étant hors périmètre (arbitrage K), **cet argument est
  affaibli et doit être réécrit** — l'agent encaisse toujours les virages
  hors-script, mais le panier n'en fait pas partie. Ne laisse pas la
  contradiction dormir ;
- dans **§8 (hors périmètre)** : la composition multi-catégories demande un
  panier explicite, un budget alloué avec retraits et réinitialisation, et un
  critère nº2 redéfini par panier. Aucun des trois n'existe dans un MVP qui
  exclut le paiement et le compte client. **Le total dépensé à travers plusieurs
  tours n'est pas suivi** — c'est ce que « hors périmètre » signifie, et c'est
  désormais constatable plutôt que silencieux ;
- une ligne dans **§7 (risques)** : le garde-fou de l'arbitrage F favorise
  légèrement les produits à données manquantes ;
- **ce que l'étape a appris et qui n'était pas prévu.** Il y en aura. Les bornes
  de winsorisation, le nombre réel d'attributs concernés par le comptage NULL et
  le comportement de G2 sont trois endroits où la mesure va contredire une
  attente. Écris-les, avec les chiffres.

Note aussi, pour l'étape 7 et à un seul endroit : **l'importance d'un critère
est collante en session.** Un critère déclaré bloquant ne peut pas être
re-déclaré « souhait » par le modèle seul lors d'un appel suivant ; seule une
nouvelle parole du client le change. Sinon le zéro résultat devient une
incitation à assouplir en douce, ce que §3.6 cherche à empêcher. **Tu
n'implémentes pas cette règle ici** — tu l'écris pour qu'elle ne se perde pas.

Mets à jour la ligne de statut en tête de `PROJET.md`. `README.md` : la
commande de calibration et le fait que `tests/matching/` se scinde en une part
pure et une part `integration`.

## Porte de sortie

`make check` vert, `make test-int` vert, `tests/matching/` en moins de deux
secondes pour sa part pure. G1, G2, G3 et G4 couverts par des tests qui citent
les identifiants du rapport de seed. Aucun appel LLM nulle part, aucune clé API
requise.

Montre-moi le diff et le résultat d'un appel du moteur sur deux cas — un nominal
et G3. **N'enchaîne pas sur l'étape 7.**

## Style

Le dépôt est en français : noms de fonctions, docstrings et commentaires. Les
commentaires expliquent **pourquoi**, pas quoi. `ruff` avec `ANN` sur `src/`,
`mypy --strict` avec le plugin Pydantic, 100 colonnes. `src/raiyon/config.py`,
`src/raiyon/catalogue/schemas.py` et `src/raiyon/db/models.py` donnent le niveau
de commentaire attendu.

Si un point de ce prompt te paraît faux, contradictoire avec `PROJET.md`, ou
infaisable, **arrête-toi et dis-le** avant d'écrire le code.
