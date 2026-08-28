"""Contexte de migration Alembic.

Deux points portent des décisions, pas des réglages :

* **L'URL n'est jamais en dur.** Elle vient de `raiyon.config`, seul point de lecture
  de l'environnement du projet (`alembic.ini` la laisse vide). Un test d'intégration
  peut cependant la renseigner explicitement pour viser une base jetable ; cette
  valeur-là prime, sinon rien ne pourrait migrer autre chose que la base de travail.
* **`compare_type` et `compare_server_default` sont actifs.** Sans eux, changer un
  `Numeric(10, 2)` en `Numeric(12, 2)` ou une valeur par défaut ne produit aucune
  migration : le schéma dérive en silence du code, et on ne s'en aperçoit qu'en
  production.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from raiyon.config import get_settings
from raiyon.db.base import Base
from raiyon.db.models import Produit, SessionConversation, TourConversation  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `Base.metadata` ne connaît une table que si son module a été importé — d'où
# l'import ci-dessus, dont le seul rôle est cet effet de bord. Sans lui,
# l'autogénération produirait une migration vide, puis proposerait de tout supprimer.
target_metadata = Base.metadata


def url_de_la_base() -> str:
    """Rend l'URL à migrer : celle passée à Alembic si elle existe, sinon la config."""
    url_explicite = config.get_main_option("sqlalchemy.url")
    if url_explicite:
        return url_explicite
    return str(get_settings().database_url)


def run_migrations_offline() -> None:
    """Génère le SQL sans se connecter (`alembic upgrade head --sql`)."""
    context.configure(
        url=url_de_la_base(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Applique les migrations sur une connexion réelle."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url_de_la_base()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
