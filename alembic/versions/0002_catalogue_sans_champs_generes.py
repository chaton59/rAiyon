"""Retrait de `nom_fr` et `description` : plus aucun champ généré en base.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-28

Les deux colonnes retirées ici étaient les deux seules que la passe LLM de l'étape 5
devait remplir. La passe a tourné sur 40 produits, et la mesure a invalidé les deux
(§3.4ter, réécrit) :

* `nom_fr` **égalait le nom source 38 fois sur 38** — un catalogue de marques et de
  références commerciales n'a rien de traduisible ;
* `description` (le résumé d'usage) fait double emploi avec la phrase française que
  l'agent de l'étape 8 écrit déjà à partir des produits retenus et de leur trace.

Ce que la migration achète : **aucun octet de la table `produits` ne vient d'un
modèle de langage**, et cela se lit dans le schéma au lieu de se promettre dans un
README. Le français du produit se produit au moment de répondre, jamais en base.

**Le `downgrade()` remet les deux colonnes, `text` nullables — et rien d'autre.** Il
ne restaure aucun contenu : les valeurs sont perdues, ce qui est sans conséquence
puisqu'elles étaient toutes nulles hors des 40 produits de l'essai, dont le cache a
été supprimé. Une différence à connaître : les colonnes reviennent **en fin de
table**, Postgres ne sachant pas insérer une colonne à une position donnée. Le schéma
est équivalent, l'ordre de `SELECT *` ne l'est pas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Supprime les deux colonnes que la passe LLM remplissait."""
    op.drop_column("produits", "description")
    op.drop_column("produits", "nom_fr")


def downgrade() -> None:
    """Recrée les deux colonnes, nullables et vides."""
    op.add_column("produits", sa.Column("nom_fr", sa.Text(), nullable=True))
    op.add_column("produits", sa.Column("description", sa.Text(), nullable=True))
