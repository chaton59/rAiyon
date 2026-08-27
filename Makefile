# rAiyon — commandes de développement.
# `make` seul liste les cibles.

.DEFAULT_GOAL := help

.PHONY: help install up down logs psql fmt lint typecheck test check clean

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

check: lint typecheck test ## Porte de sortie : lint + types + tests
	@echo "✓ check vert"

clean: ## Supprime les caches d'outillage
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
	# -prune : sans lui, find redescend dans les dossiers qu'il vient de
	# supprimer et sort en code 1, ce qui fait échouer la cible.
	find . -name __pycache__ -type d -not -path './.venv/*' -prune -exec rm -rf {} +
