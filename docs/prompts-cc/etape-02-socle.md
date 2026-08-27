# Prompt Claude Code — Étape 2 : Socle du dépôt

> À coller tel quel dans Claude Code, à la racine de `rAiyon/`.

---

## Contexte

Tu travailles sur **rAiyon**, un assistant conseil produit en temps réel. Le cadrage
complet est dans `PROJET.md` à la racine : **lis-le en premier**, en particulier les
§2 (contrainte non négociable), §3.12 (API), §3.13 (modèles), §5 (plan d'exécution) et
§6 (ordre non négociable).

Nous sommes à l'**étape 2 — Socle du dépôt**. Le dépôt ne contient aujourd'hui que
`PROJET.md` et `docs/`.

## Objectif

Mettre en place l'infrastructure du projet : structure, dépendances, base de données
locale, outillage qualité, CI. **Aucune logique métier.**

**Porte de sortie (§5) :** `docker compose up -d` démarre Postgres et le healthcheck
passe ; `make check` est vert (lint + types + tests) sur un dépôt sans code métier.

## Décisions déjà arbitrées — ne pas les rediscuter

- **uv** comme gestionnaire de dépendances et de version Python
- **Python 3.12**
- **Layout `src/`** : package `raiyon` sous `src/raiyon/`
- Outillage complet dès maintenant : Makefile + pre-commit + GitHub Actions

## Hors périmètre de cette étape — ne l'écris pas

- Modèles SQLAlchemy, migrations Alembic (→ étape 4)
- Application FastAPI, routes, même un `/health` (→ étape 10)
- Moteur de matching, outils, appels Anthropic (→ étapes 6+)
- README complet (→ étape 14 ; un stub de 15 lignes suffit ici)

Si tu es tenté d'anticiper, arrête-toi et signale-le plutôt que d'écrire le code.

---

## À produire

### 1. `pyproject.toml`

- Métadonnées : `name = "raiyon"`, `requires-python = ">=3.12"`, description courte.
- Build backend `hatchling`, packages = `["src/raiyon"]`.
- **Dépendances runtime** (déclarées maintenant pour éviter la churn, même si non
  utilisées à cette étape) : `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2`,
  `alembic`, `psycopg[binary]`, `pydantic>=2`, `pydantic-settings`, `anthropic`,
  `structlog`.
- **Groupe dev** (`[dependency-groups] dev`) : `pytest`, `pytest-asyncio`,
  `pytest-cov`, `httpx`, `ruff`, `mypy`, `pre-commit`.
- Config `[tool.ruff]` : `line-length = 100`, `target-version = "py312"`,
  select `E, F, I, UP, B, SIM, RUF, ANN`, formatter activé.
- Config `[tool.mypy]` : `strict = true` sur `src/`, `warn_unused_ignores`,
  fichiers de tests en mode non strict.
- Config `[tool.pytest.ini_options]` : `testpaths = ["tests"]`,
  `addopts = "-q --strict-markers"`, marqueurs déclarés `integration` (nécessite
  Postgres) et `llm` (nécessite une clé API) — les deux **désélectionnés par défaut**.

Crée aussi `.python-version` (`3.12`) et génère `uv.lock` (`uv lock`), qui doit être
commité.

### 2. Arborescence

```
src/raiyon/
  __init__.py          # __version__ uniquement
  config.py            # cf. point 3
  catalogue/__init__.py
  matching/__init__.py
  tools/__init__.py
  agent/__init__.py
  api/__init__.py
prompts/.gitkeep       # prompts système versionnés (§3.14)
tests/
  conftest.py
  test_config.py
docs/prompts-cc/       # existe déjà
```

Les `__init__.py` des sous-paquets restent vides — ce sont des emplacements réservés
qui rendent le plan d'exécution lisible dans l'arborescence.

### 3. `src/raiyon/config.py` — configuration typée

Point unique de lecture de l'environnement. **Aucune clé en dur nulle part ailleurs
dans le projet.**

- Classe `Settings(BaseSettings)` avec `model_config = SettingsConfigDict(env_file=".env", env_prefix="RAIYON_", frozen=True, extra="ignore")`.
- Exception : `anthropic_api_key: SecretStr` lit `ANTHROPIC_API_KEY` sans préfixe
  (via `validation_alias`), parce que c'est le nom conventionnel attendu par le SDK.
- Champs :

| Champ | Type | Défaut |
|---|---|---|
| `anthropic_api_key` | `SecretStr` | **aucun** — absent ⇒ erreur explicite |
| `database_url` | `PostgresDsn` | `postgresql+psycopg://raiyon:raiyon@localhost:5432/raiyon` |
| `model_agent` | `str` | `claude-sonnet-5` |
| `model_extraction` | `str` | `claude-haiku-4-5-20251001` |
| `model_eval_client` | `str` | `claude-haiku-4-5-20251001` |
| `budget_tolerance` | `float` | `0.15` — validé dans `[0, 0.5]` |
| `max_agent_iterations` | `int` | `8` — validé `>= 1` |
| `log_level` | `Literal["DEBUG","INFO","WARNING","ERROR"]` | `INFO` |
| `app_env` | `Literal["dev","test","prod"]` | `dev` |

- Fonction `get_settings() -> Settings` décorée `@lru_cache`. Elle doit exposer un
  moyen de vider le cache pour les tests (`get_settings.cache_clear()`).
- Le `repr` ne doit jamais laisser fuiter la clé — `SecretStr` s'en charge, vérifie-le
  par un test.

Les valeurs par défaut de `budget_tolerance` et `max_agent_iterations` viennent
directement de `PROJET.md` §3.10 et §3.9 : mets un commentaire qui pointe la section.

### 4. `.env.example` et `.env`

`.env.example` commité, exhaustif, commenté, **avec des valeurs factices**
(`ANTHROPIC_API_KEY=sk-ant-xxxxx`). `.env` est dans `.gitignore` et n'est jamais
commité. Le Makefile crée `.env` depuis l'exemple s'il n'existe pas.

### 5. `docker-compose.yml`

Un seul service `db` :

- image `postgres:16-alpine`
- `POSTGRES_USER/PASSWORD/DB` = `raiyon`, lus depuis l'environnement avec ces valeurs
  par défaut
- port hôte configurable : `${POSTGRES_PORT:-5432}:5432`
- volume nommé `raiyon_pgdata`
- **healthcheck** `pg_isready -U raiyon` (interval 5s, retries 10) — la porte de
  sortie dépend de lui
- `restart: unless-stopped`

Pas de service applicatif : à cette étape l'app tourne en local via uv.

### 6. `Makefile`

Cibles, avec `.PHONY` et une aide par défaut (`make` seul liste les cibles) :

| Cible | Effet |
|---|---|
| `install` | `uv sync` + `uv run pre-commit install` + crée `.env` si absent |
| `up` / `down` / `logs` | docker compose (`up -d` + attente du healthcheck) |
| `psql` | shell psql dans le conteneur |
| `fmt` | `uv run ruff format .` + `ruff check --fix` |
| `lint` | `uv run ruff check .` + `ruff format --check .` |
| `typecheck` | `uv run mypy src` |
| `test` | `uv run pytest` |
| `check` | `lint` + `typecheck` + `test` — **c'est la porte de sortie** |
| `clean` | caches pytest/ruff/mypy, `__pycache__` |

`up` doit boucler sur `docker compose ps` jusqu'au statut `healthy` et sortir en
erreur après un timeout, plutôt que de rendre la main sur une base pas prête.

### 7. `tests/`

- `conftest.py` : une fixture autouse qui isole l'environnement (`monkeypatch.delenv`
  sur toutes les variables `RAIYON_*` et `ANTHROPIC_API_KEY`, `get_settings.cache_clear()`
  avant et après chaque test) — sinon un `.env` local fait passer ou échouer les tests
  selon la machine.
- `test_config.py`, quatre tests au minimum :
  1. les valeurs par défaut sont celles attendues quand seule la clé API est fournie ;
  2. `ANTHROPIC_API_KEY` absente ⇒ `ValidationError` (échec bruyant, pas silencieux) ;
  3. `RAIYON_BUDGET_TOLERANCE=0.9` ⇒ `ValidationError` (borne haute respectée) ;
  4. `repr(settings)` et `str(settings.anthropic_api_key)` ne contiennent pas la clé.

Aucun test ne doit toucher le réseau ni Postgres à cette étape.

### 8. `.pre-commit-config.yaml`

`ruff` + `ruff-format`, `end-of-file-fixer`, `trailing-whitespace`,
`check-added-large-files`, `check-merge-conflict`, **`detect-private-key`**, et
`check-yaml`. Le hook de secrets n'est pas décoratif : c'est le filet sur la
contrainte « aucune clé en dur ».

### 9. `.github/workflows/ci.yml`

Sur `push` et `pull_request` :

- `astral-sh/setup-uv` avec cache activé, Python 3.12
- `uv sync --locked` (échoue si `uv.lock` est désynchronisé du `pyproject.toml`)
- `make lint`, `make typecheck`, `make test`
- un service `postgres:16-alpine` avec healthcheck, **déclaré dès maintenant** pour
  que l'étape 4 n'ait pas à retoucher la CI ; `DATABASE_URL` exporté en variable
  d'environnement du job
- aucun secret requis : le job doit passer sur un fork. Si des tests ont besoin d'une
  clé plus tard, ils porteront le marqueur `llm`, désélectionné par défaut.

### 10. `.gitignore` et `README.md`

`.gitignore` : `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`,
`.ruff_cache/`, `.mypy_cache/`, `.coverage`, `htmlcov/`, `data/raw/`, `.DS_Store`.
`uv.lock` **n'est pas** ignoré.

`README.md` : stub court — une phrase sur le projet, prérequis (uv, Docker),
`make install && make up && make check`, et un lien vers `PROJET.md`. Le README
complet est l'étape 14, ne le rédige pas maintenant.

---

## Vérification finale — à exécuter et à me montrer

Dans cet ordre, en collant la sortie réelle :

1. `make install`
2. `make up` puis `docker compose ps` — le service `db` doit être `healthy`
3. `make check` — lint, mypy et pytest verts
4. `git status` — vérifie qu'aucun `.env` ni secret n'est suivi ; liste les fichiers
   qui seraient commités
5. `uv run python -c "from raiyon.config import get_settings; print(get_settings().model_agent)"`
   depuis une machine sans `.env` ⇒ doit échouer avec un message clair sur
   `ANTHROPIC_API_KEY`

Puis fais un commit unique : `chore: socle du dépôt (étape 2)`.

## Règles de travail

- Un choix technique risqué ou fragile : **dis-le explicitement** au lieu de le noyer.
- Si une décision structurante non prévue ici apparaît, expose l'alternative et le
  compromis **avant** de trancher, et propose l'amendement correspondant à `PROJET.md`.
- Ne modifie pas `PROJET.md` de ta propre initiative.
