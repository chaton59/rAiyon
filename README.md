# rAiyon

Assistant conseil produit en temps réel : le client décrit son besoin en langage
naturel, l'assistant dialogue avec lui puis recommande des produits **réels** du
catalogue. Le LLM ne produit jamais un fait — il met en mots des faits que le
code lui a fournis.

## Prérequis

- [uv](https://docs.astral.sh/uv/) (gère aussi la version de Python)
- Docker et Docker Compose (pour Postgres)

## Démarrage

```bash
make install   # dépendances, hooks pre-commit, création de .env
make up        # démarre Postgres et attend le healthcheck
make migrate   # applique les migrations (crée le schéma)
make seed      # charge le catalogue committé (~1 000 produits, aucun appel API)
make check     # lint + types + tests
make test-int  # tests d'intégration : migrations, contraintes, index, chargement
```

**`ANTHROPIC_API_KEY` n'est requise que pour `make chat` et `make fumee`.** Tout le
reste — installation, migrations, seed, calibration, `make check` — est du code
déterministe qui n'appelle aucun modèle, et exiger une clé pour ces commandes serait un
mensonge sur la dépendance. Son absence est signalée au moment de s'en servir, par un
message qui dit quoi faire.

`make` seul liste les autres cibles.

Les tests d'intégration créent leurs propres bases jetables sur le Postgres de
`docker-compose` (`raiyon_test` pour le schéma et le chargement, `raiyon_test_matching`
pour le moteur, `raiyon_test_agregats` pour les agrégats de la couche outils, les deux
dernières seedées une seule fois par session), les migrent et les suppriment : ils ne
touchent pas à la base de travail. Sans Postgres joignable, ils sont ignorés avec un
message qui dit quoi faire, jamais en échec silencieux.

| suite | tests | ce qu'elle exige |
| --- | --- | --- |
| `make check` — la totalité de la part pure | **514** en 3,1 s | rien : ni base, ni conteneur, ni clé API |
| `make test-int` | **67** | un Postgres joignable |

## Lancer une conversation

```bash
make up && make migrate && make seed   # une fois : la console interroge le catalogue
make fumee                             # contrôle : un appel API jetable, dit si strict passe
make chat                              # dialogue en console, Ctrl-D pour sortir
```

`make chat` crée une session, affiche son UUID, et lit stdin ligne à ligne. Deux
niveaux d'affichage :

- **par défaut** — le dialogue, plus une ligne compacte par événement non textuel.
  C'est le panneau « voici ce que j'ai compris de votre besoin » en version terminal,
  et c'est ce qui rend l'architecture visible : on voit que le **code** a compris,
  cherché et trouvé, indépendamment de ce que le modèle raconte ;
- **`--trace`** — en plus, les distributions du sondage et la trace d'explication
  critère par critère, avec le rôle appliqué et le sous-score.

```
[critères] écran · ≥ 144 Hz fréquence de rafraîchissement (important) · budget 400.00 $
[sondage]  32 candidats · 108.00 $ à 399.99 $ · 4 dans la zone de tolérance
[question] marque suggéré (marque) · 32 candidats
[produits] 3 trouvés sur 32 candidats · 2 au-dessus du budget
    monitor-9d9e443e00  AOPEN UM.UW1AA.P01  108.00 $
    monitor-ee31fe1bb3  MSI MAG 255XFV  129.99 $
    monitor-3e3a4798db  BenQ MOBIUZ EX240N  139.99 $
    +17.14 $ monitor-80e6d42e2f  Samsung Odyssey G50A  417.14 $
```

La conversation est **persistée** : `uv run python scripts/console.py --session <uuid>`
reprend une session existante et retrouve ses critères, son budget et son historique.
Les produits au-dessus du budget sont rendus dans un ensemble séparé, avec leur écart
exact — jamais mélangés au classement principal.

`make chat` consomme la clé API. Le prompt système en vigueur et son empreinte sont
affichés au démarrage et logués à chaque appel : c'est ce qui permettra, à l'étape 12,
de détecter une cassette enregistrée sur un prompt qui a changé depuis.

## Le catalogue

Le catalogue est **committé** dans `data/seed/produits.jsonl` : `make seed` ne fait
que le charger. Les données brutes (6,4 Mo de JSON) ne sont pas versionnées, et
exiger une clé API pour installer le projet serait absurde.

Deux cibles, et **aucune des deux n'appelle un modèle de langage** :

| cible | ce qu'elle fait | exige `data/raw/` | consomme la clé API |
| --- | --- | --- | --- |
| `make seed-build` | reconstruit `data/seed/` depuis les données brutes | oui | **non** |
| `make seed` | charge le seed committé en base | non | **non** |

**Aucune colonne de la table `produits` ne contient une sortie de modèle.** Ce n'est
pas une intention, c'est constatable : les colonnes sont toutes dans
[`models.py`](src/raiyon/db/models.py), et un test vérifie qu'aucun module de
`raiyon.catalogue` ne charge même le SDK Anthropic, dans un interpréteur neuf.

Une passe intermédiaire traduisait les noms de produits et générait un résumé
d'usage. Elle a été supprimée après l'avoir mesurée : sur 38 traductions, le nom
français **égalait le nom source 38 fois sur 38** — un catalogue de marques et de
références (« TUF Gaming », « IronWolf Pro ») n'a rien de traduisible, et le résumé
faisait double emploi avec la phrase que l'agent écrit de toute façon. Le raisonnement
complet est en [`PROJET.md`](PROJET.md) §3.4ter.

**Le catalogue est donc en anglais, et c'est un choix documenté.** Le français se
produit au moment de répondre au client, dans la phrase de recommandation : c'est elle
qui porte la langue, pas la base. Les noms de produits y sont cités **verbatim**, ce
qui les rend vérifiables au caractère près.

Le compte rendu de la passe déterministe — entonnoir ligne à ligne, motifs de
rejet, taux de remplissage par attribut, contrôles — est committé lui aussi :
[`data/seed/rapport_seed.md`](data/seed/rapport_seed.md).

Pour reconstruire le catalogue à partir de zéro, récupérer d'abord `data/raw/`
selon [`data/raw/SOURCE.md`](data/raw/SOURCE.md), puis `make seed-build`.

## Le moteur de matching

Le moteur traduit un besoin en produits classés, avec le « pourquoi » de chacun. Une
seule phrase le gouverne :

> **SQL décide qui est candidat, Python décide comment on le présente.**

Côté SQL : les filtres durs, les comptages, les valeurs atteignables. Côté Python pur :
le scoring, le classement, la trace d'explication et le traitement du zéro résultat.

**Conséquence directe, et c'est le critère d'acceptation nº5 :** `tests/matching/` se
scinde en deux parts. La **part pure** — 170 tests — tourne dans `make check`, sans
Postgres, sans conteneur et **sans clé API**, en 0,16 seconde. La part **`integration`**
— 28 tests — porte le marqueur du même nom, travaille sur le catalogue réel des
1 026 produits et se lance par `make test-int`. Il n'y a rien à débrancher pour tester
le moteur hors ligne, parce qu'il n'y a rien de branché.

Les tests d'intégration citent **en dur** les identifiants des cas limites du
[rapport de seed](data/seed/rapport_seed.md) (budget frôlé, départage, zéro résultat,
haut de gamme). Si le catalogue change, ils cassent — c'est le comportement voulu.

### Les bornes de score sont calibrées, pas devinées

Un sous-score est une position entre deux bornes **constantes**, jamais un min-max du
lot courant : sans cela, le score d'un produit dépendrait des produits présents à côté
de lui, et deux conversations le classeraient différemment.

```bash
make calibrer   # imprime les bornes mesurées sur data/seed/produits.jsonl
```

Sa sortie se **recopie** dans [`attributs.py`](src/raiyon/matching/attributs.py) : le
script est rejouable, son résultat est du code. Un test rejoue le script sur le seed
committé et compare aux constantes du registre — modifier une borne à la main casse donc
un test.

Les queues lourdes sont winsorisées au 95ᵉ centile. L'écart n'est pas anecdotique : le
prix au gigaoctet des mémoires monte à **497,5 USD/Go** sur des modules minuscules, pour
une borne haute calibrée à **13,375**.

## La couche outils, et ce qu'elle rend impossible

Le modèle dispose de cinq outils. Un seul écrit dans la session :

| outil | rend |
| --- | --- |
| `record_criteria` | l'état mis à jour, et les mouvements refusés |
| `probe_catalog` | des agrégats seuls — **aucun produit**, vérifié sur le type de retour |
| `suggest_next_question` | le champ manquant le plus discriminant — **aucune phrase** |
| `search_products` | les produits entiers, `produits` et `au_dessus_du_budget` séparés |
| `ask_clarification` | une question, et la clôture du tour |

**Les quatre derniers ne prennent aucun critère, aucun budget, aucune catégorie.** Ils
lisent l'état de session. Ce n'est pas une commodité : c'est ce qui fait qu'il n'existe
pas d'argument par lequel contourner une contrainte que le client a posée. La question
« l'argument hostile est-il arrêté ? » devient « existe-t-il un argument ? », et elle se
vérifie sur des **signatures**.

**Un critère déclaré ne se défait pas tout seul.** Desserrer — retirer un critère,
baisser son importance, reculer un seuil, relever le budget — coûte **une parole du
client** : un seul de ces mouvements est accepté par message, le second est refusé et
l'outil le dit sans erreur, pour que l'agent puisse répondre « je garde 144 Hz tant que
tu ne me dis pas le contraire ». Resserrer est toujours libre. La limite est écrite
plutôt que tue : le jeton borne le **nombre** d'assouplissements par parole, il ne
vérifie pas que le client parlait de ce critère-là.

Le schéma JSON des outils est **dérivé du registre d'attributs**, jamais écrit à la
main : un test vérifie que son énumération de champs couvre exactement les champs
utilisables, catégorie par catégorie. Un schéma qui promettrait un champ que le moteur
refuse ferait échouer le modèle tour après tour sans que rien ne casse côté code.

Dix-sept portes hostiles sont fermées et testées une par une, chacune nommée d'après ce
qu'elle empêche : budget élargi en cours de tour, catégorie inexistante, champ d'une
autre catégorie, champ d'affichage posé en critère, promotion d'un attribut de score en
bloquant, seuil qui recule après un zéro résultat… Les critères contradictoires, eux, ne
lèvent pas : « au moins 200 Hz et au plus 100 Hz » rend zéro produit **et un
diagnostic**, parce qu'une contradiction est une réponse, pas un bug.

Aucun module de `raiyon.tools` ne charge le SDK Anthropic — vérifié module par module,
découverts sur le disque, chacun dans un interpréteur neuf.

## Données

> Données produits issues de [`docyx/pc-part-dataset`](https://github.com/docyx/pc-part-dataset)
> (licence MIT), snapshot du 23 juillet 2025, lui-même scrapé de PCPartPicker.
> Les prix sont en USD et figés à cette date : le catalogue est un instantané, pas un flux.

**Les prix restent en USD, sans conversion.** La langue est gratuite, la devise non :
fabriquer un taux de change reviendrait à afficher un prix que personne n'a constaté.
Un montant en euros serait donc un fait inventé, ce que ce projet s'interdit.

Seuls 24 % des produits de la source portent un prix ; les autres sont écartés, car
un produit sans prix n'entre pas dans un moteur à contrainte budgétaire. Le
catalogue livré est un **échantillon stratifié par décile de prix**, à graine fixe :
il conserve la forme de la distribution réelle, queue haute comprise, mais ses taux
de remplissage diffèrent légèrement de ceux de la source. Toute statistique publiée
ensuite porte sur ce catalogue, pas sur le dataset.

Le cadrage complet — décisions d'architecture, alternatives écartées, plan
d'exécution — est dans [`PROJET.md`](PROJET.md).
