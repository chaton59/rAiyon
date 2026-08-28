# Prompt Claude Code — correctif d'étape 5 : suppression de la passe LLM

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`. L'étape 5 est livrée, le correctif G4 est
appliqué, et la passe B a tourné sur 40 produits. Ce que cet essai a mesuré
invalide une décision de cadrage. Tu vas appliquer le correctif qui en découle,
**et rien d'autre**. N'ouvre pas l'étape 6.

## La décision, et pourquoi elle change

**La passe LLM du catalogue est supprimée. Le catalogue reste en anglais, la
langue française se produit au moment de répondre au client, dans la phrase de
recommandation de l'étape 8.**

Deux mesures ont conduit là, dans cet ordre.

**1. `nom_fr` n'avait rien à traduire.** Sur les 38 traductions obtenues, le nom
français **égale le nom source 38 fois sur 38**. Vérification faite ensuite sur
les 1 026 noms du seed, sans appel API : aucune catégorie ne porte de contenu
traduisible.

```
Asus TUF Gaming VG279QM1A     Seagate IronWolf Pro NAS
G.Skill Trident Z5 RGB 48 GB  ASRock Phantom Gaming OC
```

Marque + référence commerciale. « TUF Gaming », « Trident Z5 », « IronWolf Pro »
sont des noms de gamme déposés : les traduire casserait l'identité du produit.
3.4ter a été écrite **avant** d'avoir vu les noms — même mécanisme que le `smt` de
l'étape 3, une décision prise sur l'idée qu'on se faisait des données.

**2. Le résumé d'usage fait double emploi avec l'étape 8.** L'agent reçoit les
produits retenus par le moteur et leur trace d'explication, et **écrit déjà une
phrase française à leur sujet**. Un `description` pré-généré fait le même travail,
un an à l'avance et figé. Ce n'est pas une sécurité, c'est une redondance —
payée en jetons, en cache à maintenir et en champ généré dans la base.

Ce que le projet y gagne, et qu'il faut écrire noir sur blanc :

- **Aucun octet de la base ne vient d'un modèle.** La promesse passe de « le LLM
  ne produit jamais un fait » à quelque chose de vérifiable en lisant le schéma.
- **L'étape 5 devient entièrement déterministe** : aucune clé API n'est nécessaire
  avant l'étape 8, ni pour construire le catalogue, ni pour le charger, ni pour
  le tester.
- **Le multilingue devient une phrase du prompt système**, pas 1 026 générations
  par langue.
- **Le piège tendu à l'étape 6 disparaît** : il n'y a plus de champ texte généré
  dont il faudrait se rappeler qu'il ne doit ni filtrer ni scorer.

Ce qu'il perd, à consigner honnêtement : la relecture par échantillon promise par
3.4ter. Un texte figé se relit une fois, un texte produit au runtime jamais. Le
garde-fou devient le **validateur de l'étape 9**, qui voit passer chaque réponse —
ce qui était de toute façon déjà le cas pour la phrase de recommandation.

Et une limite à ne pas maquiller : **les prix restent en USD, figés à juillet
2025**. La langue devient gratuite, la devise non. Fabriquer un taux de change
serait inventer un fait (§2). À dire dans le README, pas à laisser croire.

## Ce que tu supprimes

- `src/raiyon/catalogue/traduction.py`, `scripts/seed_llm.py`,
  `tests/test_traduction.py`, `prompts/traduction_catalogue.v1.md`, la cible
  `seed-llm` du `Makefile`, et les fichiers `data/seed/traductions.json` et
  `data/seed/echantillon_relecture.md`.
- Les colonnes `nom_fr` **et** `description` : retirées de `ProduitEnBase`
  (`schemas.py`), du modèle `Produit` (`models.py`), et de la base par une
  migration **`0002_catalogue_sans_champs_generes`** dont le `downgrade()` recrée
  les deux colonnes `text` nullables — et fonctionne réellement, vérifie-le.
- `chargement.py` : plus de fusion de cache. `executer_passe_c` lit, revalide,
  charge. La revalidation par `ProduitEnBase` **reste** : elle n'a jamais eu de
  rapport avec le LLM.

Ne réécris pas `docs/prompts/etape-4.md` ni `docs/prompts/etape-5.md` : ce sont
des **archives**, elles disent ce qui a été demandé à l'époque. Supprime en
revanche `docs/prompts/etape-5-correctif-nom-fr.md`, qui n'a jamais été exécuté et
que celui-ci remplace.

## Ce que tu gardes ou ajoutes

**`LIBELLES_CATEGORIE`** — les 6 catégories vers leur nom commun français :
`cpu` → « processeur », `monitor` → « écran », `internal-hard-drive` →
« stockage interne », `memory` → « mémoire vive », `video-card` → « carte
graphique », `headphones` → « casque ». C'est de la **donnée**, pas du rendu :
aucun formatage d'affichage à cette étape, c'est l'affaire de l'étape 11. Un test
vérifie que les 6 y sont, sans trou.

Écris en commentaire pourquoi elle existe : le nom générique français que le
projet voulait obtenir d'un modèle est **dérivable de la catégorie**, donc
déterministe, donc hors de portée de l'invention.

**Le test d'isolation se durcit.** Il vérifiait que la passe A n'importe pas le
SDK Anthropic ; il doit maintenant vérifier qu'**aucun module de
`src/raiyon/catalogue/` ne le charge**, et que `raiyon.catalogue` n'expose plus
rien qui s'appelle traduction. Garde la contre-épreuve qui importe `anthropic`
directement, sans elle le test passerait sur un SDK absent.

## Régénération du seed

`make seed-build` est déterministe. Le diff attendu est **exactement deux clés
retirées par ligne** (`nom_fr`, `description`), sur 1 026 lignes, **aucun `id`
modifié, aucune ligne ajoutée ou supprimée**. Si autre chose bouge, arrête-toi et
dis-le.

Le rapport `data/seed/rapport_seed.md` est régénéré ; vérifie que G1 à G4 et le
constat G3 sont inchangés.

## `PROJET.md`

**Réécris 3.4ter.** Ce n'est pas un amendement, c'est un renversement, et le
document doit le porter comme tel — titre compris (« Langue du catalogue : anglais
en base, français à la réponse »). Il faut y lire :

- la décision : la base est en anglais, la jonction avec le français se fait dans
  la phrase de recommandation (étape 8), jamais dans la base ;
- ce que la mesure a dit, avec les deux chiffres (38/38, puis 1 026 noms vérifiés
  sans appel API) ;
- **pourquoi la décision initiale était mal fondée** : prise sur une idée des
  données, pas sur les données ;
- l'alternative écartée — pré-générer et stocker : elle duplique le travail de
  l'étape 8, coûte une génération par produit et par langue, et fait entrer un
  champ généré dans une base dont l'argument est de n'en contenir aucun ;
- ce qui est perdu (relecture par échantillon) et ce qui le remplace (validateur
  de l'étape 9) ;
- la limite devise : USD figés, pas de conversion.

**Amende aussi :**

- **3.13** — la ligne « Normalisation du dataset | Haiku » n'a plus d'objet ; le
  modèle d'extraction reste configuré, il ne sert plus à cette étape.
- **Étape 4** — le tableau annonce `nom_fr` « rempli par la passe LLM de
  l'étape 5 ». N'efface pas la ligne : ajoute la mention que la colonne a été
  retirée à l'étape 5, avec le renvoi. L'historique des décisions est le produit.
- **Étape 5** — la passe B disparaît du périmètre livré ; deux cibles `make` au
  lieu de trois ; la porte de sortie ne mentionne plus aucune clé API.
- **Étape 8** — ajoute la contrainte que ce correctif y crée : les noms de produits
  sont cités **verbatim, dans la langue de la source**, jamais traduits ni
  réécrits ; c'est le français de la phrase qui porte la langue, pas le nom. Note
  le gain pour l'étape 9 : un nom de produit devient vérifiable **au caractère
  près** contre la base.

Mets à jour la ligne de statut. `README.md` : plus de `seed-llm`, le catalogue est
en anglais et c'est un choix documenté, les prix sont en USD figés.

## Porte de sortie

`make check` vert, `make test-int` vert, `make seed-build` régénéré avec le diff
attendu, `make migrate` puis `make seed` verts.

**Sur l'absence de clé API, sois précis — il y a un piège.** `make seed-build` ne
touche pas la configuration : il doit passer **sans `.env` du tout**, vérifie-le en
le lançant dans un environnement vidé de `ANTHROPIC_API_KEY`. `make seed`, lui,
construit un engine, donc charge `Settings`, où la clé est un champ **obligatoire**
depuis l'étape 2 — il réclamera une clé qu'il n'utilisera jamais.

**Ne corrige pas ça ici** : rendre la clé optionnelle rouvrirait une décision de
l'étape 2 (« son absence fait échouer le démarrage avec un message explicite »).
Constate-le, écris-le dans `PROJET.md` à l'étape 5 comme une **conséquence connue
et non traitée**, et laisse l'arbitrage pour l'étape 8, quand un appel API existera
vraiment dans le projet. La garantie qui compte à cette étape est ailleurs, et elle
est déjà testée : aucun module du catalogue ne charge le SDK.

Montre-moi le diff résumé et la nouvelle section 3.4ter.

Si un point de ce prompt te paraît faux ou contradictoire, arrête-toi et dis-le
avant d'écrire le code.
