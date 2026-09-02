# Étape 14 · jalon 1 — dépérimer

## État

`main`, commit `3a88d12`, arbre propre. Le jalon 0 est clos : le clone a franchi
la porte de sortie et `docs/etape-14-inventaire.md` porte ses constats.

**Lis `docs/etape-14-inventaire.md` en entier avant de toucher à quoi que ce
soit. C'est la source de ce jalon.** Le présent document arbitre ; l'inventaire
énumère. Là où les deux se contredisent, l'inventaire a mesuré et il gagne — mais
dis-le plutôt que de trancher en silence.

## La discipline du jalon

**Le diff ne fait que soustraire et corriger. Aucune section de prose nouvelle.**

La frontière, précisément, parce que c'est là qu'on déborde :

- **autorisé** — réécrire une phrase en place, corriger un chiffre, retirer une
  proposition subordonnée, ajouter la phrase qui manquait à une procédure
  incomplète ;
- **interdit** — un titre neuf, un paragraphe neuf, un argument que le README ne
  porte pas encore, une explication de *pourquoi* une décision a été prise.

Si tu te surprends à écrire une section, arrête-toi : elle appartient au jalon 2.

**Le README dit ce qui est ; `PROJET.md` dit pourquoi.** Une limite se nomme en
une phrase avec son lien, jamais avec sa justification — sans amputer
l'honnêteté du fichier, qui est sa meilleure qualité.

⚠️ **Une section est protégée et ne se déporte pas** : « Comment lire ce tableau,
et pourquoi il ne dit pas ce qu'il a l'air de dire ». Elle a l'air d'une
justification et n'en est pas une — c'est le mode d'emploi du tableau qui la
précède, et sans elle un `0` au critère nº1 se lit à l'envers. Elle reste dans le
README, entière. Ses **chiffres** sont à jour comme les autres ; sa prose ne
bouge pas.

## Contraintes non négociables

**Aucun changement de prompt, de schéma d'outils, de validateur ou de
catalogue.** Tout cela périmerait les cassettes et rouvrirait une étape fermée.

Ce que ce jalon s'autorise à toucher, et rien d'autre :

| Fichier | Ce qui peut bouger |
|---|---|
| `README.md` | tout, dans la discipline ci-dessus |
| `.env.example` | les faits périmés, la chronologie, la clé factice |
| `Makefile` | **le motif de la cible `help`, et lui seul** |
| `tests/` | un fichier de garde neuf |

Si un correctif exige de toucher `src/`, un fichier de `prompts/`,
`schema_outils.py`, le validateur ou le catalogue : **arrête-toi et écris-le**.
Ce sera une ligne de §7 au jalon 2. Le cas connu est déjà instruit — voir §6 de
l'inventaire, la garde de `cle_api()` — et il n'y a rien à en faire ici.

---

# Le travail

## 1. Les faits périmés

**L'inventaire §2 fait foi.** Ses neuf entrées se corrigent, chacune contre la
mesure qui l'accompagne. Les quatre qui portent le plus :

- les compteurs de suites : 720 → **904**, 84 → **98** ;
- l'exemple de `GET /health` : `systeme.v1` / `6da03a675684` →
  `systeme.v2` / `61b474af9184`, version **et** empreinte ;
- le taux de rejet v1 annoncé à 0,25 par tour : il vaut **0,13** sur la ligne de
  base. Le 0,25 est un chiffre de l'étape 12, pas de `rapport.v1-base.md`, et
  c'est la comparaison v1-base ↔ v2 que le passage décrit ;
- la **quatrième** base jetable, non citée là où le README en énumère trois.

⚠️ **Ne touche pas aux compteurs de `tests/matching/`** — 170 purs et 28
d'intégration. L'inventaire les a vérifiés : ils sont **justes**. L'énoncé de
l'étape les soupçonnait par analogie ; la mesure a tranché contre le soupçon.

**Remesure plutôt que recopier**, y compris les chiffres que l'inventaire donne :
il date de la veille et `make check` est la source. Un écart entre l'inventaire
et ta mesure est une information — signale-le.

## 2. Les durées

Deux traitements différents, et la raison tient à ce que chacune sert.

**Retirer** la durée de `make check` (« **720** en 6,0 s »). Elle ne porte aucun
argument, et elle se repérimera au prochain test ajouté. Le compteur reste, la
durée part.

**Garder et remesurer** celle de `tests/matching/` en part pure (0,16 s). Ce
sub-seconde porte le critère nº5 : c'est lui qui fait atterrir « il n'y a rien à
débrancher pour tester le moteur hors ligne, parce qu'il n'y a rien de branché ».
L'inventaire la reproduit à 0,18 s ; mesure la tienne et écris-la.

## 3. La clé API factice

Le défaut, en une phrase : `make install` écrit `ANTHROPIC_API_KEY=sk-ant-xxxxx`,
donc `cle_api()` ne voit jamais `None`, donc le message qui dit quoi faire — il
existe, il est bon, il nomme les commandes — est **inatteignable par le chemin
documenté**. Ce que le lecteur obtient à la place : 24 lignes de traceback et un
`AuthenticationError: 401`. C'est le pire premier contact possible.

Deux correctifs, qui rattrapent deux échecs différents :

1. **Commenter la ligne dans `.env.example`.** `make install` produit alors un
   `.env` sans clé, `cle is None`, et le bon message se déclenche. Rattrape le
   lecteur qui n'a pas tout lu.
2. **Le README dit d'ouvrir `.env` et d'y mettre la clé.** Une phrase, dans la
   procédure de démarrage, là où `make install` est cité. Rend le chemin
   documenté complet. C'est la phrase qui manquait à une procédure incomplète,
   donc elle est dans la discipline du jalon.

Avant de commenter, **vérifie que rien ne lit `sk-ant-xxxxx`** : tests,
`.github/workflows/ci.yml`, scripts, documentation. Si quelque chose en dépend,
arrête-toi et dis-le.

Après avoir commenté, **vérifie le chemin en entier** : produire un `.env` depuis
le nouveau `.env.example` dans une copie de travail jetable, lancer `make fumee`,
et constater que la sortie est le message de `cle_api()` et non un traceback.
Un correctif de message d'erreur qui n'a pas été vu s'afficher n'est pas vérifié.

## 4. La divergence `systeme.v1`, et sa garde

`.env.example:34` épingle `systeme.v1` ; `config.py:21` porte
`PROMPT_SYSTEME_PAR_DEFAUT = "systeme.v2"`. Comme `.env` **écrase** le défaut du
code, un clone frais **sert v1** pendant que le tableau du README décrit v2. Ce
n'est pas une coquille de documentation : le dépôt livre silencieusement autre
chose que ce qu'il annonce.

Aligner `.env.example` sur le code, puis **écrire la garde**, parce qu'une
divergence corrigée à la main aujourd'hui reviendra. C'est la troisième
occurrence du motif dans ce dépôt — après `erreurs.py`, et le quasi-accident
`SYSTEME_PAR_DEFAUT` contre `Settings.prompt_systeme` au jalon 3 de l'étape 13,
où le dépôt annonçait déjà v2 et servait déjà v1.

Le test, pur, sans base ni clé, dans `make check` :

- il lit `.env.example` **par un chemin résolu depuis la racine du dépôt**, pas
  depuis le `cwd` — un test qui ne trouve son fichier que lancé du bon
  répertoire est un test qui sera un jour ignoré en silence ;
- il extrait `RAIYON_PROMPT_SYSTEME=` et **échoue si la valeur diffère de**
  `PROMPT_SYSTEME_PAR_DEFAUT` ;
- il **échoue aussi si la ligne `ANTHROPIC_API_KEY` cesse d'être commentée**.
  Ce n'est pas cosmétique : c'est la différence entre le message qui dit quoi
  faire et un 401. Le nom du test porte cette raison.

Si tu vois un motif de ne pas asserter la seconde, expose-le plutôt que de
l'omettre.

## 5. Le motif de la cible `help`

`^[a-zA-Z_-]+:` n'admet pas de chiffre, donc `make eval-etape12` n'apparaît pas
dans `make`, alors que le README affirme « `make` seul liste les autres cibles ».

Ajouter les chiffres à la classe. **La cible `help` et rien d'autre** — les
commentaires datés du `Makefile` restent tous, ils s'adressent au mainteneur et
ce sont eux qui empêchent qu'on simplifie une cible par erreur un jour.

Vérifie en comparant la liste des cibles **avant et après** : `eval-etape12`
apparaît, et rien d'autre n'apparaît ni ne disparaît.

## 6. Les illustrations non sourcées

Deux cas, deux traitements — et la différence est de savoir si le chiffre se
recalcule.

**Les deux trames de la section API** (`text_rejected` sur `230 $`, puis le
`message` qui suit). Aucun artefact du dépôt ne les porte ; elles exigent un
rejet du validateur qu'on ne commande pas à la demande. **La phrase de
provenance tombe** — « Ces deux trames sont réelles : elles viennent d'une
conversation de recette. » Les trames restent : elles montrent une **forme**, et
c'est leur vrai rôle. Une affirmation invérifiable de provenance dans un README
dont la thèse est « rien n'est affirmé sans source » est la pire ligne du fichier.

**La ligne `[sondage]` de la trace console** — `32 candidats · 108.00 $ à
399.99 $ · 4 dans la zone de tolérance`. Elle ne se retire pas : elle se
**calcule**. C'est une fonction pure du catalogue et des critères, et
`probe_catalog` sur `monitor` / `refresh_rate ≥ 144` / budget 400 la reproduit
contre le seed committé, **sans un seul appel API**. Calcule-la et écris les
valeurs mesurées. Si elles diffèrent de celles imprimées, ce sont les tiennes qui
sont vraies.

Les identifiants et prix des produits du même bloc ont déjà été vérifiés exacts
par l'inventaire : n'y touche pas.

## 7. La chronologie

**Zéro mention d'étape dans le corps du README.** Dix occurrences, plus une
référence listée pour mémoire — l'inventaire §4.1 les énumère. Chacune devient
une phrase autonome au présent : « garanti par construction », « le prompt le
corrige », et non « depuis l'étape 9 », « sera corrigé à l'étape 13 ».

**Deux d'entre elles parlent au futur d'étapes franchies** (inventaire §4.2) :
« c'est ce qui permettra, à l'étape 12, de détecter une cassette » et « c'est le
prompt qui sera corrigé à l'étape 13 ». Elles ne sont pas seulement opaques, elles
sont **fausses** — le lecteur apprend qu'une chose reste à faire alors qu'elle est
faite. Ce sont les deux plus urgentes du lot.

**`.env.example` subit le même traitement** : neuf mentions (§4.3), dont une au
futur (§4.4). C'est le fichier qu'on copie et qu'on ouvre à l'installation, donc
le premier contact après le README.

⚠️ **La ligne de fin qui nommera les alternatives écartées et `docs/prompts/`
n'est pas de ce jalon.** C'est de la prose neuve : jalon 2. Ne laisse pas un
« voir PROJET.md » orphelin à sa place en attendant — soit la phrase se suffit,
soit elle attend.

---

# La porte de sortie du jalon

- `make check` vert, `make test-int` vert, et la nouvelle garde passe ;
- **relis ton propre diff hunk par hunk** : chacun est soit une soustraction,
  soit une correction de fait, soit la phrase manquante d'une procédure. Un hunk
  qui n'entre dans aucune des trois est du jalon 2 — retire-le ;
- **aucun titre neuf**, aucun paragraphe neuf ;
- le chemin de la clé a été **vu** produire le bon message, pas seulement corrigé ;
- `make` liste `eval-etape12` ;
- plus une seule occurrence d'« étape N » dans `README.md` ni dans
  `.env.example`.

Un commit, message `docs: dépérimer le README et .env.example (étape 14, jalon 1)`.

Puis arrête-toi, et donne :

1. le diff résumé, fichier par fichier, en distinguant soustractions et
   corrections de fait ;
2. les écarts entre l'inventaire et tes propres mesures, s'il y en a ;
3. ce que tu as failli écrire et qui appartenait au jalon 2 — c'est l'information
   la plus utile pour cadrer le jalon suivant.
