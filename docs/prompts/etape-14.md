# Étape 14 — README et finition · jalon 0 : l'inventaire

## État du dépôt

`main`, commit `2c010da`, arbre propre. L'étape 13 est close : `systeme.v2` en
vigueur, campagne de 36 prises enregistrée et comparée, cinq rapports et leur
`LISEZMOI.md` dans `docs/eval/`. `make check`, `make test-int` et `make eval`
sont verts.

Lis d'abord `README.md`, `.env.example`, le `Makefile`, `PROJET.md` §5 étape 14,
§7 et §8, et `docs/eval/LISEZMOI.md`.

## Ce que l'étape 14 cherche

La porte de sortie est la seule qui compte pour un portfolio : un `git clone`
suivi de la procédure du README, sur une machine neuve, aboutit à une
conversation fonctionnelle. **Elle s'exécute, elle ne se relit pas.**

Le README n'est pas à réécrire. Il a été tenu à jour à chaque étape et il est
précis. L'étape vérifie, dépérime, et retire ce qui suppose que le lecteur a
suivi la construction.

L'étape compte quatre jalons. **Celui-ci est le jalon 0, et il ne corrige rien.**
Les jalons 1 (dépérimer), 2 (ajouter ce que §5 étape 14 demande) et 3 (rejouer la
porte de sortie) viendront ensuite, un par un, chacun arbitré.

## Ce que le jalon 0 produit, et ce qu'il ne produit pas

**Il produit** une liste de constats : ce qui est faux dans le README, ce qui y
manque, ce que le clone a fait trébucher.

**Il ne produit aucune correction.** Pas une ligne de README, pas une ligne de
`.env.example`. Un constat non corrigé est le livrable ; corriger au fil de l'eau
détruirait la seule chose que ce jalon sait faire — dire l'état du dépôt tel
qu'il est aujourd'hui, avant qu'on y touche.

Si tu te surprends à écrire une correction, arrête-toi : elle appartient au
jalon 1.

## Contraintes non négociables

**Aucun changement de prompt, de schéma d'outils, de validateur ou de
catalogue.** Tout cela périmerait les cassettes et rouvrirait une étape fermée.

Cette contrainte porte sur toute l'étape 14, pas seulement sur ce jalon. Si le
clone révèle un défaut dont le correctif touche `src/`, un fichier de `prompts/`,
`schema_outils.py`, le validateur ou le catalogue : **arrête-toi et écris-le**.
Ce sera une ligne de §7, pas un commit. Un correctif de produit glissé dans la
dernière étape est exactement ce qu'une dernière étape ne doit pas contenir.

Ce que l'étape 14 s'autorise à toucher, aux jalons suivants : `README.md`,
`.env.example`, la documentation, et un test de garde.

---

# Partie A — le clone de découverte

## Pourquoi il est ici et pas au jalon 3

Une relecture du README contre le dépôt ne trouve que ce qu'on soupçonne déjà.
Un clone trouve une autre classe de défauts : un fichier non committé dont le
projet dépend, un ordre de commandes faux, un prérequis que personne n'a écrit.
Les découvrir au jalon 3 obligerait à corriger en deux passes, et la seconde
tomberait dans le dernier jalon de la dernière étape.

Le clone du jalon 3 redeviendra ce qu'il doit être : une vérification, pas une
découverte.

## La règle de lecture, et son exception

**On ne lit que le `README.md` du clone, et ce que le README dit d'ouvrir.**

`make install` copie `.env.example` en `.env` et il faut y écrire la clé :
ouvrir ce fichier est légitime. Ce qui est un constat, c'est **si le README ne
dit pas de le faire**.

**Tout fichier qu'on a dû ouvrir sans y être invité est une ligne de la liste.**
Sans exception : `Makefile`, `PROJET.md`, `docker-compose.yml`, un module de
`src/`. Avoir eu besoin d'y aller est précisément l'information cherchée.

## Ce que ce clone est, et ce qu'il n'est pas

**Ce n'est pas une machine vierge**, et le compte rendu doit le dire plutôt que
prétendre le contraire. Le cache `uv`, l'image Docker de Postgres et la clé API
sont partagés avec l'environnement courant.

Ce qu'il attrape réellement : un fichier non committé dont le projet dépend, une
commande du README qui n'existe pas, un ordre de commandes faux, une étape
manquante entre deux commandes, un message d'erreur qui ne dit pas quoi faire.

Ce qu'il n'attrape pas : une dépendance système installée à la main il y a six
semaines, une version de Docker ou de `uv` trop ancienne, un `~/.netrc`.

Écris les deux listes dans le compte rendu. C'est la même discipline que le
README applique déjà à `flux.js` : une atténuation nommée vaut mieux qu'une
preuve prétendue.

## Le piège à désamorcer avant de commencer

Le clone porte le même `docker-compose.yml` et le même `POSTGRES_PORT=5432` que
le dépôt d'origine. Si le conteneur d'origine tourne, le `make up` du clone
échouera sur un port déjà pris — et ce serait un **faux constat**, produit par le
protocole et non par le dépôt.

Donc, avant le clone : `docker compose down` dans le dépôt d'origine, et
vérifier que le port 5432 est libre. Le nom de projet Compose dérive du nom du
répertoire, donc le clone aura son propre volume : `make migrate` et `make seed`
sont nécessaires, ce n'est pas une anomalie.

Ne modifie **pas** `POSTGRES_PORT` pour contourner : ce serait dévier de la
procédure du README, c'est-à-dire ne plus tester ce qu'on prétend tester.

## Le protocole

1. `docker compose down` dans le dépôt d'origine ; vérifier que 5432 est libre.
2. `git clone` du dépôt local vers un répertoire temporaire hors de l'arbre de
   travail. Un clone ne porte que le contenu **committé** — c'est tout l'intérêt.
3. Ouvrir le `README.md` du clone et n'exécuter que ce qu'il dit, dans l'ordre
   où il le dit, jusqu'à **une conversation fonctionnelle**. La conversation
   compte : un README qui installe sans dialoguer n'a pas passé la porte.
4. Consigner, commande par commande : la commande exacte, son code de sortie, sa
   durée si elle est notable, et le **premier message d'erreur verbatim** en cas
   d'échec.
5. Consigner aussi les frictions qui ne sont pas des échecs : une commande qui
   marche mais dont le README n'annonce pas la durée, une sortie qui inquiète
   sans être une erreur, une variable qu'on a dû deviner.
6. **Ne corriger rien.** Si une commande échoue, note-le, contourne pour
   continuer si tu le peux, et dis explicitement que tu as contourné et comment.
7. Nettoyer : `docker compose down` dans le clone, puis supprimer le répertoire
   temporaire. Le compte rendu survit, le clone non.

Le clone consomme la clé API sur la conversation finale, et sur elle seule. C'est
accepté.

---

# Partie B — l'inventaire mesuré

## Le principe

**Mesurer, jamais recopier.** Trois des quatre faits périmés connus ont la même
cause : un chiffre écrit une fois puis jamais relu. Reconduire un chiffre parce
qu'il est déjà écrit est la faute que ce jalon existe pour ne plus commettre.

**Un chiffre qui ne se source nulle part est une ligne de la liste, pas un
chiffre corrigé.** N'invente aucune valeur de remplacement, même plausible.

## Les mesures à prendre

**Les compteurs de suites.** `make check` et `make test-int`, et relever les
comptes réels ainsi que les durées. Le README annonce 720 tests purs et 84
d'intégration ; l'ordre de grandeur réel est au-delà de 900. Relever aussi les
deux compteurs locaux de la section « Le moteur de matching » — 170 tests purs et
28 d'intégration pour `tests/matching/` — qui ont la même exposition.

**L'empreinte du prompt en vigueur.** L'exemple de `GET /health` du README
affiche `systeme.v1` et l'empreinte `6da03a675684`. Relever la version et
l'empreinte réellement servies par `systeme.v2`, telles que l'endpoint les rend.

**Le coût d'une campagne.** Le nombre d'appels au modèle de la campagne de
l'étape 13 — de mémoire 209 — se **source** dans `docs/prompts/etape-13-revision.md`
ou dans les artefacts de la campagne. S'il ne s'y trouve pas, dis-le : c'est une
ligne de la liste, et le jalon 2 écrira ce qui est mesurable plutôt que ce chiffre.

⚠️ Aucun compteur de jetons n'existe dans `rapport.v2.md`. **N'estime aucun
montant en dollars** : ce serait exactement le fait inventé que ce projet
s'interdit. Relève ce qui est comptable — appels, prises, scénarios, tours — et
rien d'autre.

## Le balayage du README

Le README fait 564 lignes. **Toute affirmation vérifiable est vérifiée**, et
chaque écart devient une ligne datée de la liste. Sans être exhaustif, ce qui
appelle une vérification :

- le tableau des six critères et sa note de bas de tableau — 36 prises,
  11 scénarios, 81 tours client — contre `docs/eval/rapport.v2.md` ;
- les trois couches du rapport : 6 griefs refusés, la répartition par code, le
  taux de repli annoncé à 0 sur 81 ;
- les taux de rejet comparés — 0,25 par tour sur v1, 0,07 sur v2 — et la
  dispersion, contre `docs/eval/comparaison.v1-base-v2.md` ;
- le markdown : 51 occurrences par passe → 0, dispersion ± 43 ;
- le catalogue : ~1 000 produits, 1 026 produits, 24 % de la source portant un
  prix, 6,4 Mo de JSON brut, les 38 traductions sur 38 ;
- la calibration : 497,5 USD/Go et la borne haute à 13,375 ;
- les inventaires : cinq outils, dix événements dont huit du domaine, dix-sept
  portes hostiles, quatre modules ES dans `web/` ;
- **chaque lien relatif du README résout vers un fichier qui existe** —
  `src/raiyon/db/models.py`, `data/seed/rapport_seed.md`, `data/raw/SOURCE.md`,
  `src/raiyon/matching/attributs.py`, `PROJET.md`, et les autres ;
- **chaque commande `make` citée existe dans le `Makefile`**, et chaque cible du
  `Makefile` que le README devrait citer y est ;
- la trame `curl` de la section API et les noms d'événements du tableau des dix,
  contre ce que le code émet réellement.

## Les mentions chronologiques

Relever **toutes** les mentions qui supposent que le lecteur a suivi la
construction : « à l'étape 9 », « depuis l'étape 12 », « sera corrigé à
l'étape 13 », « l'arbitrage B », « la dette nº1 ». Environ onze dans le README.

Relever les mêmes dans `.env.example` : « OPTIONNELLE depuis l'étape 8 »,
« étape 10, piège nº4 », « permettra à l'étape 12 », et les renvois à `PROJET.md`.

Deux d'entre elles parlent au **futur** d'étapes franchies — « c'est ce qui
permettra, à l'étape 12, de détecter une cassette » et « c'est le prompt qui sera
corrigé à l'étape 13 ». Les signaler à part : elles ne sont pas seulement opaques
au lecteur, elles sont fausses.

Ne les corrige pas. Le jalon 1 les traitera : effacées du corps, chaque phrase
réécrite au présent et autonome.

## La divergence `.env.example`

`config.py:21` porte `PROMPT_SYSTEME_PAR_DEFAUT = "systeme.v2"`. `.env.example`
porte `RAIYON_PROMPT_SYSTEME=systeme.v1`. Le fichier d'exemple **diverge du
code** au lieu de le refléter.

Confirmer la divergence, et vérifier qu'aucun code ne lit `.env.example` — si
c'est bien le cas, la corriger au jalon 1 est sans effet de bord et ne peut
périmer aucune cassette.

Relever aussi si un test existe déjà pour cette cohérence. Le jalon 1 en écrira
un : ce serait la troisième occurrence du même motif dans ce dépôt, après
`erreurs.py` et le quasi-accident `SYSTEME_PAR_DEFAUT` contre
`Settings.prompt_systeme` au jalon 3 de l'étape 13, où le dépôt annonçait v2 et
servait v1.

## Ce que §5 étape 14 demande et qui manque

Constater l'absence, sans commencer à combler — le jalon 2 s'en charge :

- un schéma d'architecture ;
- le périmètre exclu (§8) ;
- les dettes ouvertes (§7) ;
- le coût d'une campagne d'éval ;
- une carte du dépôt.

Pour la carte, relever la structure réelle de premier niveau. Le dépôt porte
`catalogue/` et `grande_echelle/` à la racine, qui ne sont nommés nulle part dans
le README.

---

# Le livrable

Un fichier `docs/etape-14-inventaire.md`, **document de travail** : il alimente
les jalons 1 et 2, et il sera supprimé au jalon 3 une fois absorbé. Écris-le en
tête du fichier, sinon il deviendra un artefact orphelin de plus.

Sa structure :

1. **Le clone** — le protocole tel qu'il s'est réellement déroulé, commande par
   commande avec codes de sortie ; les fichiers ouverts sans y être invité ; les
   contournements ; ce que ce clone n'a pas pu tester.
2. **Les faits périmés** — un tableau : ce que le README affirme, ce qui est
   mesuré, où c'est mesuré.
3. **Les chiffres non sourçables** — ceux dont aucun artefact du dépôt ne rend
   compte. Ne rien y proposer.
4. **Les mentions chronologiques** — ligne par ligne, README puis `.env.example`,
   avec les deux au futur signalées à part.
5. **Ce qui manque** au regard de §5 étape 14.
6. **Ce qui exigerait de toucher au produit** — le cas échéant, ce que le clone a
   révélé et dont le correctif tombe sous la contrainte non négociable. Rédigé
   comme une ligne de §7 : le fait, sa gravité, ce qui l'atténue.

Commit du seul fichier d'inventaire, message
`docs: l'inventaire de l'étape 14 (jalon 0)` — pour que le diff du jalon 1 reste
pur.

## La porte de sortie du jalon

L'inventaire est vert quand :

- le clone a été exécuté jusqu'à une conversation ou jusqu'à un échec **nommé** ;
- chaque chiffre du README est soit confirmé par une mesure, soit dans la liste ;
- `git diff` ne montre **que** `docs/etape-14-inventaire.md` ;
- `make check` est toujours vert, ce qui est trivial puisque rien n'a bougé — et
  c'est justement ce qu'on vérifie.

Puis arrête-toi. Le jalon 1 est un autre arbitrage.
