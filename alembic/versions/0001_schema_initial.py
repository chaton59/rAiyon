"""Schéma initial : produits, sessions, tours de conversation.

Revision ID: 0001
Revises:
Create Date: 2026-08-27

Trois tables, et rien de plus : aucun produit du dataset n'entre en base à cette
étape. Le peuplement est le travail du pipeline de l'étape 5.

**Compromis d'indexation assumé (PROJET.md §3.3bis).** Les attributs propres aux
catégories vivent dans `specs` JSONB, servi par un seul index GIN `jsonb_path_ops`.
Cet index sert l'égalité et la containment ; il **ne sert pas** les comparaisons de
plage du type `(specs->>'capacity')::int >= 2000`, qui feront un balayage séquentiel
de la table. À ~1 000 produits cela coûte quelques millisecondes, donc on l'accepte -
mais il faut le dire : ce schéma ne démontre pas la promesse « SQL pour le scaling ».
L'échappatoire connue, si le volume changeait d'ordre de grandeur, est l'ajout
d'index d'expression B-tree sur les champs numériques les plus filtrés
(`((specs->>'capacity')::int)`), un par champ et par catégorie.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crée les trois tables, leurs contraintes et leurs index."""
    op.create_table(
        "produits",
        # Identifiant synthétique `{categorie}-{10 hexadécimaux}`. La contrainte ne
        # vérifie que la forme : le calcul (préfixe de sha256 de la clé de
        # déduplication) est écrit à l'étape 5. Un ID inventé par un LLM est ainsi
        # détectable, ce qui ne serait pas le cas d'un slug déduit du nom.
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("nom", sa.Text(), nullable=False),
        sa.Column("nom_fr", sa.Text(), nullable=True),
        sa.Column("marque", sa.Text(), nullable=False),
        sa.Column("categorie", sa.String(length=32), nullable=False),
        # Prix en dollars, sans conversion : la source est en USD et fabriquer un
        # taux de change serait inventer un fait (§2). L'unité est dans le nom.
        sa.Column("prix_usd", sa.Numeric(precision=10, scale=2), nullable=False),
        # Champ généré par LLM (§3.4ter) : affichage seul, jamais un critère.
        sa.Column("description", sa.Text(), nullable=True),
        # La source ne porte aucune quantité : un booléen dit ce que l'on sait.
        sa.Column("disponible", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "specs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "cree_le", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "maj_le", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        # Les 6 catégories retenues (§3.4bis). `keyboard` est absente et doit le
        # rester : elle n'atteignait 5 attributs qu'en comblant une absence.
        sa.CheckConstraint(
            "categorie IN ('cpu', 'monitor', 'internal-hard-drive', 'memory', "
            "'video-card', 'headphones')",
            name=op.f("ck_produits_categorie_connue"),
        ),
        sa.CheckConstraint("id ~ '^[a-z-]+-[0-9a-f]{10}$'", name=op.f("ck_produits_forme_id")),
        # Garantie qui tient même si quelqu'un contourne Pydantic. Un prix nul ou
        # négatif viderait de son sens le filtre budgétaire, invariant central (§3.10).
        sa.CheckConstraint("prix_usd > 0", name=op.f("ck_produits_prix_positif")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_produits")),
    )
    # Les deux filtres durs présents dans *toutes* les requêtes du moteur ; la
    # catégorie est en tête parce qu'elle est toujours une égalité, le prix ensuite
    # parce qu'il est toujours une plage.
    op.create_index(
        "ix_produits_categorie_prix_usd", "produits", ["categorie", "prix_usd"], unique=False
    )
    # Filtre dur réellement exprimé par les clients (« je veux du Intel »), et seule
    # colonne qui porte la marque - elle n'existe dans aucune catégorie de la source.
    op.create_index("ix_produits_marque", "produits", ["marque"], unique=False)
    # `jsonb_path_ops` : environ deux fois plus compact que l'opérateur par défaut, et
    # suffisant puisqu'on ne cherche jamais l'existence d'une clé seule. Sa limite est
    # écrite en tête de fichier - c'est le compromis de l'étape 4.
    op.create_index(
        "ix_produits_specs",
        "produits",
        ["specs"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"specs": "jsonb_path_ops"},
    )

    op.create_table(
        "sessions",
        # UUID généré côté application : l'API doit connaître l'identifiant avant le
        # premier flush pour l'émettre dans le flux SSE.
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "cree_le", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "maj_le", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        # Le budget a sa propre colonne, hors de `criteres_valides` : c'est lui que la
        # couche outils lit pour borner la recherche (§3.6) et il porte l'invariant du
        # §3.10. Le dupliquer dans le JSONB autoriserait les deux copies à diverger.
        sa.Column("budget_usd", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column(
            "criteres_valides",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "statut",
            sa.String(length=32),
            server_default=sa.text("'en_cours'"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "statut IN ('en_cours', 'recommandation_rendue', 'abandonnee')",
            name=op.f("ck_sessions_statut_connu"),
        ),
        sa.CheckConstraint("budget_usd > 0", name=op.f("ck_sessions_budget_positif")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )

    op.create_table(
        "tours_conversation",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        # Blocs de contenu Anthropic bruts, pas un texte aplati : le harnais d'éval
        # (étape 12) doit rejouer une conversation à l'identique et le validateur
        # (étape 9) a besoin des `tool_result` pour savoir ce qui a été fourni au
        # modèle. Aplatir détruirait les deux, et sans retour possible.
        sa.Column("blocs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "cree_le", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        # Deux valeurs seulement : les `tool_result` portent le rôle `user` dans
        # l'API Anthropic, il n'existe pas de rôle « outil ».
        sa.CheckConstraint(
            "role IN ('user', 'assistant')", name=op.f("ck_tours_conversation_role_connu")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_tours_conversation_session_id_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tours_conversation")),
        # L'ordre des tours est une donnée : un numéro dupliqué rendrait la relecture
        # d'une conversation ambiguë, donc l'éval non reproductible.
        sa.UniqueConstraint("session_id", "numero", name="uq_tours_conversation_session_id_numero"),
    )
    # Postgres ne crée pas d'index sur une clé étrangère. Sans celui-ci, toutes les
    # lectures d'une conversation et les DELETE en cascade balaient la table.
    op.create_index(
        "ix_tours_conversation_session_id", "tours_conversation", ["session_id"], unique=False
    )


def downgrade() -> None:
    """Défait la migration entièrement - vérifié par `tests/test_db.py`, pas supposé.

    L'ordre est l'inverse strict de `upgrade()` : `tours_conversation` avant
    `sessions`, sans quoi la clé étrangère bloque la suppression.
    """
    op.drop_index("ix_tours_conversation_session_id", table_name="tours_conversation")
    op.drop_table("tours_conversation")
    op.drop_table("sessions")
    op.drop_index(
        "ix_produits_specs",
        table_name="produits",
        postgresql_using="gin",
        postgresql_ops={"specs": "jsonb_path_ops"},
    )
    op.drop_index("ix_produits_marque", table_name="produits")
    op.drop_index("ix_produits_categorie_prix_usd", table_name="produits")
    op.drop_table("produits")
