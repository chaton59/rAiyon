# Prompt Claude Code — Étape 4 : schéma SQL et migrations

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`. Les étapes 1 à 3 sont franchies. Tu vas
réaliser **l'étape 4 et rien d'autre**.

## Avant d'écrire quoi que ce soit

Lis, dans cet ordre :

1. `PROJET.md` — §2 (contrainte non négociable), §3.3, §3.6, §3.10, §3.12, §3.15,
   §4 (critères d'acceptation), §5 étape 4, §6 (ordre non négociable).
2. `catalogue/schema_attributs.md` — c'est **la** source de vérité des attributs,
   de leurs types cibles, de leurs plages et de leurs taux de remplissage.
3. `src/raiyon/config.py`, `tests/conftest.py`, `Makefile`, `pyproject.toml`,
   `.github/workflows/`.

Ne déduis aucun attribut de la documentation de la source : l'étape 3 a démontré
qu'elle ment (le champ `smt` promis pour `cpu` n'existe dans aucun
enregistrement). `schema_attributs.md` fait foi.

## Périmètre — ce que tu livres

Modèles SQLAlchemy, modèles Pydantic miroirs, migration Alembic initiale, tests.
Rien de plus.

**Explicitement hors périmètre, à ne pas commencer :** pipeline de normalisation
(étape 5), moteur de matching (étape 6), outils de l'agent (étape 7), tout appel
LLM, toute insertion de données réelles. Aucun produit du dataset n'entre en base
à cette étape — seules les fixtures de test insèrent des lignes.

Ne modifie pas `src/raiyon/config.py` : le schéma n'a besoin d'aucune nouvelle
variable d'environnement. La base de test se dérive de `RAIYON_DATABASE_URL`.

## Arbitrages déjà rendus — applique-les, ne les rediscute pas

**A. Indexation : JSONB + GIN seul, balayage séquentiel assumé sur les plages.**
Les attributs propres aux catégories vivent dans `specs` JSONB (§3.3). Un index
GIN `jsonb_path_ops` sert l'égalité et la containment, **pas** les comparaisons de
plage (`(specs->>'capacity')::int >= 2000`), qui feront un balayage séquentiel. À
~1 000 produits c'est quelques millisecondes. Aucun index d'expression n'est créé
à cette étape. Écris ce compromis **et sa limite** en commentaire dans la
migration et dans `PROJET.md` : la promesse « SQL pour le scaling » n'est pas
démontrée par ce schéma, l'échappatoire connue est l'ajout d'index d'expression
B-tree sur les champs numériques les plus filtrés.

**B. Base de test : base dédiée `raiyon_test` sur le Postgres de docker-compose.**
Pas de `testcontainers`. Les tests qui touchent la base portent le marqueur
`integration` (déjà déclaré dans `pyproject.toml`) et restent hors de `make check`.

**C. Moteur SQLAlchemy synchrone.** Engine sync psycopg, sessions synchrones. Le
moteur de matching et le pipeline resteront des fonctions pures testables sans
boucle asyncio ; l'API enveloppera ses appels base dans `asyncio.to_thread` à
l'étape 10. Ne crée pas d'engine async.

**D. Validation par union discriminée.** `specs` est validé par un modèle Pydantic
**par catégorie**, réunis en union discriminée sur le champ `categorie`, avec
`extra="forbid"`. Un produit `cpu` porteur d'un `screen_size` doit être rejeté.
C'est ce qui donne un sens à « rien n'entre en base sans avoir été typé et validé ».

**E. Prix en USD, sans conversion.** La source est en dollars. Tu stockes
`prix_usd` et rien d'autre : fabriquer un taux de change serait inventer un fait,
ce que §2 interdit. La colonne porte l'unité dans son nom pour qu'aucune couche
supérieure ne puisse l'oublier.

**F. Pas de stock chiffré.** La source ne porte aucune quantité. Une colonne
`disponible boolean not null default true`, pas un entier inventé.

## Le schéma

### Table `produits`

| colonne | type | contraintes | note |
| --- | --- | --- | --- |
| `id` | `text` | PK, `CHECK (id ~ '^[a-z-]+-[0-9a-f]{10}$')` | identifiant synthétique, jamais `name` |
| `nom` | `text` | NOT NULL | nom source, en anglais |
| `nom_fr` | `text` | NULL | rempli par la passe LLM de l'étape 5 |
| `marque` | `text` | NOT NULL | premier mot de `name` (§3.4quater) |
| `categorie` | `varchar(32)` | NOT NULL, `CHECK IN (…)` | les **6** catégories retenues |
| `prix_usd` | `numeric(10,2)` | NOT NULL, `CHECK (prix_usd > 0)` | filtre dur central (§3.10) |
| `description` | `text` | NULL | résumé d'usage généré par LLM à l'étape 5 |
| `disponible` | `boolean` | NOT NULL DEFAULT true | |
| `specs` | `jsonb` | NOT NULL DEFAULT `'{}'` | attributs propres à la catégorie |
| `cree_le` / `maj_le` | `timestamptz` | NOT NULL, défaut serveur `now()` | |

Les 6 catégories : `cpu`, `monitor`, `internal-hard-drive`, `memory`,
`video-card`, `headphones`. `keyboard` est **retirée** (§3.4bis) — ne la mets nulle
part, pas même en commentaire de complaisance.

**Format de `id` : `{categorie}-{10 hex}`**, par exemple `cpu-3f9a2c7b1d`, où les
10 caractères sont un préfixe de `sha256` de la clé de déduplication (nom + tous
les attributs hors prix). L'étape 4 déclare seulement la colonne et sa contrainte
de forme ; le calcul est écrit à l'étape 5. Deux raisons à ce format : rejouer le
pipeline redonne les mêmes identifiants (le diff du seed reste lisible), et un ID
inventé par le LLM est trivialement détectable par le validateur de l'étape 9 —
ce qui ne serait pas le cas d'un slug reconstituable à partir du nom.

**Contrainte `CHECK` sur `description`, à ne pas ajouter** — mais écris en
commentaire du modèle que ce champ est **généré**, donc non factuel : il ne doit
jamais servir de critère de filtrage ni de score. C'est un piège que l'étape 6
peut tendre.

**Index** :

- B-tree composite sur `(categorie, prix_usd)` — les deux filtres durs présents
  dans *toutes* les requêtes du moteur ; l'ordre place la catégorie en tête parce
  qu'elle est toujours une égalité.
- B-tree sur `marque` — filtre dur sur les 6 catégories (§3.4quater).
- GIN `jsonb_path_ops` sur `specs`.

Justifie chaque index par un commentaire d'une ligne dans la migration. Un index
sans justification écrite est un index qu'on n'ose plus supprimer.

### Table `sessions`

| colonne | type | contraintes |
| --- | --- | --- |
| `id` | `uuid` | PK, généré côté application (uuid4) |
| `cree_le` / `maj_le` | `timestamptz` | NOT NULL, défaut `now()` |
| `budget_usd` | `numeric(10,2)` | NULL, `CHECK (budget_usd > 0)` |
| `criteres_valides` | `jsonb` | NOT NULL DEFAULT `'{}'` |
| `statut` | `varchar(32)` | NOT NULL DEFAULT `'en_cours'`, `CHECK IN ('en_cours','recommandation_rendue','abandonnee')` |

**Le budget a sa propre colonne**, hors de `criteres_valides`, bien qu'il soit un
critère. Raison : c'est lui que la couche outils lit pour borner la recherche
(§3.6, `session.budget`) et il porte l'invariant produit. Le dupliquer dans le
JSONB ouvrirait la possibilité que les deux divergent, ce qui est exactement le
mode d'échec que §3.10 cherche à rendre impossible. Écris cette raison en
commentaire.

### Table `tours_conversation`

| colonne | type | contraintes |
| --- | --- | --- |
| `id` | `bigint` | PK, identity |
| `session_id` | `uuid` | FK → `sessions.id` `ON DELETE CASCADE`, indexé |
| `numero` | `int` | NOT NULL, `UNIQUE (session_id, numero)` |
| `role` | `varchar(16)` | NOT NULL, `CHECK IN ('user','assistant')` |
| `blocs` | `jsonb` | NOT NULL |
| `cree_le` | `timestamptz` | NOT NULL, défaut `now()` |

`blocs` stocke les **blocs de contenu Anthropic bruts** (`text`, `tool_use`,
`tool_result`), pas un texte aplati. Raison : le harnais d'éval de l'étape 12 doit
rejouer une conversation à l'identique, et le validateur de l'étape 9 a besoin des
`tool_result` pour savoir quels produits ont réellement été fournis au modèle.
Aplatir en `text` détruirait les deux. Note que les `tool_result` portent le rôle
`user` dans l'API Anthropic — d'où le `CHECK` à deux valeurs.

## Modèles Pydantic miroirs

Dans `src/raiyon/catalogue/schemas.py`.

**Règle de nullabilité, sans exception ni interprétation :** un attribut est
obligatoire **si et seulement si** son taux de remplissage mesuré à l'étape 3 est
de 100 %. Tous les autres sont `| None`, y compris ceux qui sont conceptuellement
essentiels — `internal-hard-drive.type` est à 99,6 %, il est donc optionnel au
niveau du modèle, et c'est le pipeline de l'étape 5 qui décidera d'écarter ou non
les lignes concernées. Mets un commentaire là-dessus : anticiper cette décision
ici reviendrait à combler une absence, ce que §3.4quater interdit.

**Bornes :** chaque champ numérique porte un `Field(ge=…, le=…)` dont la borne est
une valeur **physiquement plausible englobant la plage observée**, pas la plage
observée elle-même — un produit qui bat le record ne doit pas être rejeté. Mets la
plage observée en commentaire à côté de chaque borne, avec son unité.

Les clés de `specs` reprennent **exactement** les noms de colonne cible de
`schema_attributs.md` :

- **`cpu`** — `core_count` int (obl.), `core_clock` Decimal GHz (obl.), `tdp` int W
  (obl.), `microarchitecture` str (obl.), `boost_clock` Decimal|None,
  `graphics` str|None.
- **`monitor`** — `screen_size` Decimal pouces (obl.), `largeur_px` int (obl.),
  `hauteur_px` int (obl.), `aspect_ratio` str (obl.), `panel_type` str|None,
  `refresh_rate` int Hz|None, `response_time` Decimal ms|None.
- **`internal-hard-drive`** — `capacity` int GB (obl.), `type` `Literal["SSD","HDD"]`|None,
  `rpm` int|None, `form_factor` str (obl.), `interface` str (obl.),
  `price_per_gb` Decimal USD/GB|None, `cache` int MB|None.
- **`memory`** — `ddr_generation` int (obl.), `frequence_mhz` int (obl.),
  `nb_modules` int (obl.), `taille_module_gb` int (obl.), `capacite_totale_gb` int
  (obl., dérivée), `cas_latency` int (obl.), `first_word_latency` Decimal ns (obl.),
  `price_per_gb` Decimal|None, `color` str|None.
- **`video-card`** — `chipset` str (obl.), `memory` Decimal GB de VRAM (obl.),
  `length` int mm|None, `core_clock` int MHz|None, `boost_clock` int MHz|None,
  `color` str|None.
- **`headphones`** — `type` `Literal["Circumaural","Supra-aural","In Ear","Earbud"]`
  (obl.), `microphone` bool (obl.), `wireless` bool (obl.),
  `enclosure_type` `Literal["Closed","Open","Semi-open"]` (obl.),
  `freq_min_hz` int **Hz**|None, `freq_max_khz` Decimal **kHz**|None,
  `color` str|None.

**Deux validateurs croisés à écrire :**

1. `internal-hard-drive` : `type == "SSD"` ⇒ `rpm` **doit** être `None` ;
   `type == "HDD"` ⇒ `rpm` **doit** être renseigné. Un SSD n'a pas de tours/minute.
2. `memory` : `capacite_totale_gb == nb_modules * taille_module_gb`. C'est une
   grandeur dérivée ; si elle ne se recalcule pas, la donnée est corrompue.

**Un validateur croisé formellement interdit :** aucune contrainte du type
`freq_min <= freq_max` sur `headphones`. Les deux composantes sont dans des
**unités différentes** (Hz et kHz) : `freq_min_hz=100`, `freq_max_khz=10` est un
casque de communication MSI parfaitement valide. Un correctif `min`/`max`
détruirait la donnée sur 32 produits. Écris ce commentaire à l'endroit où un
développeur pressé serait tenté d'ajouter la contrainte.

Prévois aussi un modèle `ProduitEnBase` (les colonnes communes + `specs` en union
discriminée) qui est le seul point d'entrée de l'insertion.

## Infrastructure

- `src/raiyon/db/base.py` : `DeclarativeBase` avec une **naming convention**
  explicite sur `MetaData` (`ix_`, `uq_`, `ck_`, `fk_`, `pk_`). Sans elle,
  l'autogénération Alembic produit des contraintes anonymes qu'on ne sait plus
  supprimer dans un `downgrade`.
- `src/raiyon/db/models.py` : les trois modèles.
- `src/raiyon/db/engine.py` : `create_engine(str(settings.database_url),
  pool_pre_ping=True)` mis en cache, `sessionmaker(expire_on_commit=False)`, et un
  `session_scope()` en gestionnaire de contexte qui commit ou rollback.
- `alembic/` : `env.py` lit l'URL via `get_settings()` — **jamais** d'URL en dur ni
  dans `alembic.ini` ; `target_metadata = Base.metadata` ; `compare_type=True` et
  `compare_server_default=True`.
- Une seule migration, `0001_schema_initial`. Elle a un `downgrade()` qui
  fonctionne réellement — vérifie-le, ne le suppose pas.

## Tests

**Unitaires, sans base, inclus dans `make check`** (`tests/test_schemas.py`) :

- chaque catégorie accepte une charge utile valide ;
- une clé inconnue est rejetée (`extra="forbid"`) ;
- une valeur hors bornes est rejetée ;
- un `screen_size` sur un `cpu` est rejeté — c'est le test qui prouve que l'union
  discriminée sert à quelque chose ;
- SSD avec `rpm` renseigné → rejeté ; HDD sans `rpm` → rejeté ;
- `capacite_totale_gb` incohérente → rejetée ;
- `headphones` avec `freq_min_hz=100` et `freq_max_khz=10` → **accepté**. Nomme ce
  test explicitement d'après le piège d'unité qu'il garde.

**Intégration, marqueur `integration`** (`tests/test_db.py`) :

- `alembic upgrade head` s'applique sur une base vide, puis `downgrade base` la
  vide entièrement ;
- insertion et relecture d'un produit : `Decimal`, `bool` et clés de `specs`
  reviennent à l'identique (attention au round-trip des `Decimal` en JSONB) ;
- un produit malformé est rejeté par Pydantic **avant** d'atteindre la base ;
- `prix_usd = 0` est rejeté par le `CHECK` de la base, et une catégorie inconnue
  aussi — la garantie doit tenir même si quelqu'un contourne Pydantic ;
- une session avec 3 tours : supprimer la session supprime les tours (cascade) ;
- `(session_id, numero)` en double → `IntegrityError` ;
- l'index GIN sur `specs` existe réellement (interroge `pg_indexes`) — la
  migration a pu l'oublier sans que rien d'autre ne le signale.

**Fixture de base de test** dans `tests/conftest.py` (ou un `conftest.py` dédié
au dossier d'intégration, pour ne pas alourdir la suite unitaire) : elle dérive
l'URL de `RAIYON_DATABASE_URL` en remplaçant le nom de base par `raiyon_test`,
crée la base via une connexion `AUTOCOMMIT` à la base de maintenance, applique
les migrations par `alembic.command.upgrade`, puis supprime la base à la fin.
Si Postgres est injoignable, le test **skip** avec un message qui dit quoi faire
(`make up`) — il n'échoue pas et ne se tait pas non plus.

Attention : la fixture `isolated_env` existante est `autouse=True`, retire les
variables `RAIYON_*` et déplace le répertoire courant. Les tests d'intégration ont
besoin de l'URL réelle ; règle le conflit proprement (fixture qui repose l'URL, ou
capture de la valeur avant nettoyage) et explique en commentaire pourquoi.

## Outillage à mettre à jour

- `Makefile` : `migrate` (upgrade head), `revision m="…"` (autogenerate),
  `test-int` (pytest `-m integration`). `check` reste inchangé.
- `.github/workflows/` : ajoute une étape `make test-int` après `make test`. Le
  service Postgres est déjà déclaré ; aucun secret n'est requis, le job doit
  continuer à passer sur un fork.
- `README.md` : la ligne de commande pour lancer la migration.

## `PROJET.md`

Marque l'étape 4 ✅ et ajoute, dans la même forme que les étapes précédentes :

- ce que l'étape a tranché : arbitrages A à F ci-dessus, avec **l'alternative
  écartée et son motif**, pas seulement la décision ;
- une décision numérotée **3.3bis — indexation des specs**, qui énonce le
  compromis GIN et sa limite de manière explicite ;
- ce que l'étape a appris et qui n'était pas prévu, s'il y a lieu.

Mets à jour la ligne de statut en tête de fichier.

## Porte de sortie

`make check` vert **et** `make test-int` vert, sur une base créée depuis zéro.
Montre-moi le diff et le résultat des deux commandes. N'enchaîne pas sur
l'étape 5.

## Style

Le dépôt est en français : noms de fonctions, docstrings et commentaires. Les
commentaires expliquent **pourquoi**, pas quoi. `ruff` avec `ANN` sur `src/`,
`mypy --strict` avec le plugin Pydantic, 100 colonnes. Regarde `config.py` pour le
niveau de commentaire attendu — c'est la référence.

Si un point de ce prompt te paraît faux, contradictoire avec `PROJET.md`, ou
infaisable, **arrête-toi et dis-le** avant d'écrire le code.
