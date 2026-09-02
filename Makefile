# rAiyon — commandes de développement.
# `make` seul liste les cibles.

.DEFAULT_GOAL := help

.PHONY: help install up down logs psql migrate revision seed-build seed calibrer fumee chat api eval eval-etape12 eval-comparer eval-enregistrer eval-live fmt lint typecheck test test-int check clean

help: ## Liste les cibles disponibles
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Installe les dépendances, les hooks pre-commit et crée .env si absent
	uv sync
	uv run pre-commit install
	@test -f .env || { cp .env.example .env; echo "→ .env créé depuis .env.example — y décommenter ANTHROPIC_API_KEY et mettre la vraie clé"; }

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

eval: ## Rejoue le jeu en vigueur, écrit docs/eval/rapport.<jeu>.md — base requise, clé NON requise
	@# Le rejeu n'appelle aucun modèle : `raiyon/eval/client.py` n'importe pas le
	@# SDK, et un test d'isolation le vérifie sur le disque. Il a en revanche besoin
	@# de la base et du seed, et c'est assumé (étape 12, arbitrage A) : les
	@# `tool_result` ne sont **pas** enregistrés, ils sont recalculés par le vrai
	@# moteur. Un scoring cassé se voit donc ici, sans rien réenregistrer.
	@#
	@# Sort en code non nul si un critère bloquant est violé — c'est la porte de
	@# sortie, pas un document à relire.
	@# RAIYON_PROMPT_SYSTEME choisit la version, donc le jeu : `systeme.v2` rejoue
	@# evals/cassettes/systeme.v2/ et écrit docs/eval/rapport.v2.md.
	uv run python scripts/eval.py rejouer

eval-etape12: ## Rejoue le jeu archivé de l'étape 12 et réécrit son rapport
	@# Étape 13, jalon 0, point B. Sans cette cible, « les cassettes de l'étape 12 sont
	@# conservées » voudrait seulement dire « pas effacées ». Ce qui est promis est plus
	@# fort : systeme.v1.md ne changeant pas, le tirage que §7 cite reste
	@# **reconstituable**. La cible échoue le jour où quelqu'un modifie v1 en place.
	@#
	@# Elle réécrit docs/eval/rapport.v1-etape12.md, donc `git diff` après coup est la
	@# vérification : un fichier inchangé veut dire que le jeu se rejoue à l'identique.
	RAIYON_PROMPT_SYSTEME=systeme.v1 uv run python scripts/eval.py rejouer --jeu v1-etape12

eval-comparer: ## Deux jeux côte à côte — make eval-comparer AVANT=v1 APRES=v2 Q="ce qu'on cherche"
	@# Rejeu, donc aucune clé API. Les deux jeux sont rejoués dans le **même** processus :
	@# la version de prompt de chacun est chargée par son nom, pas lue dans
	@# l'environnement. Écrit docs/eval/comparaison.<avant>-<apres>.md.
	@#
	@# La dispersion vient du jeu AVANT — c'est l'étalon de bruit du monde d'avant, et
	@# chaque écart porte son verdict : au-delà d'elle, ou dans le bruit.
	@test -n '$(AVANT)' -a -n '$(APRES)' -a -n '$(Q)' || { \
		echo 'ERREUR : make eval-comparer AVANT=v1 APRES=v2 Q="ce que la comparaison cherche"'; \
		exit 1; }
	uv run python scripts/eval.py comparer $(AVANT) $(APRES) --question '$(Q)'

eval-enregistrer: ## (Ré)enregistre les cassettes du jeu en vigueur — consomme la clé et des jetons
	@# SCENARIO=<nom> n'en refait qu'un. À lancer à chaque changement de prompt ou de
	@# schéma d'outils : l'écart d'empreinte fait échouer `make eval` en le disant.
	@#
	@# ⚠️ RAIYON_PROMPT_SYSTEME décide **où les cassettes atterrissent**. Sans elle, une
	@# campagne v2 écrirait dans evals/cassettes/systeme.v1/ et périmerait le jeu v1 :
	@#   RAIYON_PROMPT_SYSTEME=systeme.v2 make eval-enregistrer
	@#
	@# JEU=<nom> écrit ailleurs que dans le jeu de la version en vigueur — pour un
	@# complément qui ne doit pas se mêler à la campagne principale :
	@#   RAIYON_PROMPT_SYSTEME=systeme.v1 make eval-enregistrer SCENARIO=x JEU=v1-desserrage
	uv run python scripts/eval.py enregistrer $(if $(SCENARIO),--scenario $(SCENARIO),) $(if $(JEU),--jeu $(JEU),)

eval-live: ## 2-3 conversations avec le client simulé — clé requise, hors CI, rien n'est écrit
	@# Ces conversations ne sont **pas** reproductibles : les deux côtés sont non
	@# déterministes. Elles servent à lire un dialogue que les scénarios scriptés ne
	@# produisent pas, pas à mesurer. PERSONAS="nom nom" en choisit.
	uv run python scripts/eval.py live $(if $(PERSONAS),--personas $(PERSONAS),)

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
