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
# renseigner ANTHROPIC_API_KEY dans .env
make up        # démarre Postgres et attend le healthcheck
make migrate   # applique les migrations (crée le schéma)
make check     # lint + types + tests
make test-int  # tests d'intégration : migrations, contraintes, index
```

`make` seul liste les autres cibles.

Les tests d'intégration créent leur propre base jetable `raiyon_test` sur le
Postgres de `docker-compose`, la migrent et la suppriment : ils ne touchent pas à
la base de travail. Sans Postgres joignable, ils sont ignorés avec un message qui
dit quoi faire, jamais en échec silencieux.

Le cadrage complet — décisions d'architecture, alternatives écartées, plan
d'exécution — est dans [`PROJET.md`](PROJET.md).
