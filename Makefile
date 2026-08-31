# rAiyon — commandes de développement.
# `make` seul liste les cibles.

.DEFAULT_GOAL := help

.PHONY: help install up down logs psql migrate revision seed-build seed calibrer fumee chat api fmt lint typecheck test test-int check clean

help: ## Liste les cibles disponibles
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Installe les dépendances, les hooks pre-commit et crée .env si absent
	uv sync
	uv run pre-commit install
	@test -f .env || { cp .env.example .env; echo "→ .env créé depuis .env.example — y mettre la vraie clé API"; }

up: ## Démarre Postgres et attend que le healthcheck passe
	docker compose up -d
	@printf 'Attente du healthcheck Postgres'
	@for i in $$(seq 1 40); do \
		if docker compose ps db | grep -q '(healthy)'; then \
			echo " → healthy"; exit 0; \
		fi; \
		printf '.'; sleep 1; \
	done; \
	echo; echo "ERREUR : Postgres n'est pas healthy après 40 s."; \
	docker compose ps db; docker compose logs --tail=30 db; exit 1

down: ## Arrête les conteneurs (le volume de données est conservé)
	docker compose down

logs: ## Suit les logs de la base
	docker compose logs -f db

psql: ## Ouvre un shell psql dans le conteneur
	docker compose exec db psql -U raiyon -d raiyon

migrate: ## Applique les migrations jusqu'à head
	uv run alembic upgrade head

revision: ## Génère une migration par autogénération — make revision m="ce qu'elle fait"
	@test -n '$(m)' || { echo 'ERREUR : make revision m="description de la migration"'; exit 1; }
	uv run alembic revision --autogenerate -m '$(m)'
	@echo "→ relire la révision générée : l'autogénération ne devine ni les"
	@echo "  justifications d'index, ni un downgrade réellement réversible."

seed-build: ## Passe A — reconstruit data/seed/ depuis data/raw/ (aucun appel API)
	@test -d data/raw && ls data/raw/*.json >/dev/null 2>&1 || { \
		echo "ERREUR : data/raw/ est vide — voir data/raw/SOURCE.md pour la récupération."; \
		exit 1; }
	@# `cd` obligatoire : CHECKSUMS.sha256 porte des noms de fichiers nus, pas des
	@# chemins, pour rester vérifiable depuis data/raw/ comme le dit SOURCE.md.
	@cd data/raw && sha256sum -c --status CHECKSUMS.sha256 \
		|| { echo "ERREUR : data/raw/ ne correspond pas à CHECKSUMS.sha256."; exit 1; }
	uv run python scripts/seed_build.py

seed: ## Passe C — charge le seed committé en base (aucun appel API)
	uv run python scripts/seed_charger.py

calibrer: ## Recalcule les bornes du moteur sur le seed committé (à recopier dans le registre)
	@# Sa sortie est du **code**, pas un cache : elle se recopie dans
	@# src/raiyon/matching/attributs.py, et un test vérifie qu'elle correspond.
	uv run python scripts/calibrer_bornes.py

fumee: ## Contrôle de fumée — un appel API jetable qui dit si strict:true passe
	@# Le seul but est de mesurer ce que l'API accepte du schéma d'outils avant
	@# que la boucle en dépende (étape 8, arbitrage 11). Consomme la clé API.
	uv run python scripts/fumee.py

chat: ## Console de conversation — nécessite base + seed + clé API
	@# `make up && make migrate && make seed` d'abord : search_products interroge
	@# le dépôt, la console n'est pas utilisable sans conteneur.
	@# ARGS passe les options : make chat ARGS="--trace --session <uuid>".
	uv run python scripts/console.py $(ARGS)

api: ## Serveur HTTP + interface web — nécessite base + seed + clé API
	@# Mêmes prérequis que `chat`, pour la même raison : la boucle interroge le
	@# dépôt, et le tour appelle le modèle. `--reload` est un réglage de
	@# développement — il redémarre le processus, donc il **remesure** le mode
	@# strict du client à chaque rechargement (étape 8, arbitrage 11).
	@# L'hôte et le port sont ici et nulle part ailleurs : aucune variable
	@# d'environnement n'a été ajoutée pour eux (étape 10, arbitrage K).
	uv run uvicorn raiyon.api.app:app --reload --host 127.0.0.1 --port 8000

fmt: ## Formate le code et applique les corrections automatiques de ruff
	uv run ruff format .
	uv run ruff check --fix .

lint: ## Vérifie le style sans rien modifier
	uv run ruff check .
	uv run ruff format --check .

typecheck: ## Vérifie les types (mypy strict sur src/)
	uv run mypy src

test: ## Lance la suite de tests
	uv run pytest

test-int: ## Tests d'intégration — nécessite une base joignable (make up)
	uv run pytest -m integration

check: lint typecheck test ## Porte de sortie : lint + types + tests
	@echo "✓ check vert"

clean: ## Supprime les caches d'outillage
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
	# -prune : sans lui, find redescend dans les dossiers qu'il vient de
	# supprimer et sort en code 1, ce qui fait échouer la cible.
	find . -name __pycache__ -type d -not -path './.venv/*' -prune -exec rm -rf {} +
