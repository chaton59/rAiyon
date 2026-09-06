"""Deux tables d'observation : `appels_modele` et `evenements_tour`.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-04

Ce que le schéma savait d'un tour avant cette migration : les blocs bruts échangés avec
le modèle, et l'état de session. Ce qu'il ne savait pas, et qui décide de tout le reste
de l'étape 23 : **combien d'appels ont eu lieu, ce qu'ils ont coûté, combien de temps ils
ont pris, et dans quel ordre les événements sont sortis**. Ces faits vivaient dans des
logs qui s'évaporaient à la fermeture du shell.

---

### Aucune des deux tables ne duplique la conversation

`tours_conversation` reste la seule source des blocs. `appels_modele` porte des
compteurs et une empreinte ; `evenements_tour` porte ce que le fil SSE a envoyé au
client, c'est-à-dire une **projection** des mêmes faits, pas leur original.

⚠️ **`evenements_tour` contient bien une seconde copie du texte livré**, par les
événements `message` et `fallback`, et c'est une décision assumée — voir la docstring
de `raiyon.observation`. La règle « pas de seconde persistance » s'applique aux blocs
bruts, dont dépendent le rejeu et la validation ; elle ne s'applique pas à une timeline
dont l'ordre est précisément l'information.

### Le `downgrade()` supprime les deux tables et perd leur contenu

Il n'y a rien à préserver : ce sont des tables d'observation, reconstruites par les tours
suivants. Aucune autre table ne les référence, donc l'ordre de suppression est libre ;
elles sont retirées dans l'ordre inverse de la création par convention, pour que la
migration se lise dans les deux sens.

### Les tours antérieurs n'ont ni appels ni événements, et c'est correct

Aucun remplissage rétroactif n'est possible : les compteurs n'ont jamais été écrits nulle
part. Le tableau de bord de l'étape 23 doit donc rendre une timeline vide **sans mentir
et sans planter** pour les 71 860 tours déjà en base — c'est un cas nominal, pas une
dégradation.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crée les deux tables, leurs contraintes et leurs index."""
    op.create_table(
        "appels_modele",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Le `numero` de la ligne du message client — le jeton de parole du §3.17.
        sa.Column("tour_client", sa.Integer(), nullable=False),
        # Le rang de l'appel **dans le tour**, borné par `max_agent_iterations`.
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("modele", sa.Text(), nullable=False),
        # L'empreinte du prompt, pas son texte : 8,6 Ko multipliés par appel diraient la
        # même chose. C'est la même empreinte que `/health` et que l'en-tête de cassette.
        sa.Column("empreinte_systeme", sa.String(length=64), nullable=False),
        # ⚠️ `'defaut'` et non NULL quand l'effort n'est pas envoyé : les deux états sont
        # différents — « on n'a rien fixé » n'est pas « on ne sait pas » — et c'est
        # justement la distinction que la colonne existe pour porter.
        sa.Column(
            "effort", sa.String(length=16), nullable=False, server_default=sa.text("'defaut'")
        ),
        sa.Column("display", sa.String(length=16), nullable=False),
        sa.Column("stop_reason", sa.String(length=32), nullable=False),
        sa.Column("jetons_entree", sa.Integer(), nullable=False),
        sa.Column("jetons_sortie", sa.Integer(), nullable=False),
        sa.Column("cache_ecrit", sa.Integer(), nullable=False),
        sa.Column("cache_lu", sa.Integer(), nullable=False),
        sa.Column("latence_ms", sa.Integer(), nullable=False),
        sa.Column(
            "horodatage",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("iteration >= 1", name="iteration_positive"),
        sa.CheckConstraint("latence_ms >= 0", name="latence_positive"),
        # Les deux seules valeurs que l'API accepte. Mesuré : une troisième rend un 400
        # qui les énumère (`Input should be 'summarized', 'omitted'`).
        sa.CheckConstraint("display IN ('summarized', 'omitted')", name="display_connu"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Toutes les lectures du tableau de bord partent d'une session et lisent dans l'ordre
    # du tour. La FK ne crée pas d'index côté Postgres, et son absence ferait aussi ramer
    # les DELETE en cascade — même raison que sur `tours_conversation`.
    op.create_index(
        "ix_appels_modele_session_tour",
        "appels_modele",
        ["session_id", "tour_client", "iteration"],
    )

    op.create_table(
        "evenements_tour",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tour_client", sa.Integer(), nullable=False),
        # ⚠️ L'ordre est une donnée, pas une convention d'insertion : deux événements d'un
        # même message d'outils tombent dans la même milliseconde, et un tri par
        # horodatage rendrait alors la timeline non déterministe.
        sa.Column("rang", sa.Integer(), nullable=False),
        # Un des dix noms de `NomEvenement`. **Sans contrainte de liste** : le vocabulaire
        # est fermé côté Python et vérifié par `assert_never` ; le recopier en SQL ferait
        # une seconde liste, que la migration gagnerait le jour de la divergence.
        sa.Column("genre", sa.String(length=32), nullable=False),
        sa.Column("charge", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "horodatage",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rang >= 1", name="rang_positif"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "tour_client", "rang", name="uq_evenements_tour_rang"),
    )
    op.create_index(
        "ix_evenements_tour_session_tour",
        "evenements_tour",
        ["session_id", "tour_client", "rang"],
    )


def downgrade() -> None:
    """Supprime les deux tables. Leur contenu est perdu, et il est reconstructible."""
    op.drop_index("ix_evenements_tour_session_tour", table_name="evenements_tour")
    op.drop_table("evenements_tour")
    op.drop_index("ix_appels_modele_session_tour", table_name="appels_modele")
    op.drop_table("appels_modele")
