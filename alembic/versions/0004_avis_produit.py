"""Le cache des avis web : `avis_produit`.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-06

Une table, et une décision d'architecture qui tient dans sa colonne `source`.

---

### Ce que cette table n'est pas

Ce n'est **pas** un cache d'économie. La mesure a été faite avant de l'écrire : une
campagne complète fait 81 tours client, donc au pire 81 recherches, soit 0,40 $ au tarif
Brave. Le crédit mensuel offert en paie douze. Une table entière ne se justifie pas par là.

Elle sert la **comparabilité** : comparer deux versions de prompt suppose que les deux
exécutions aient vu le même contenu web, sans quoi la différence mesurée mélange l'effet
du prompt et celui d'une page qui a bougé. C'est cette raison-là qui fixe le TTL à 24 h —
il doit être plus long que l'écart entre deux exécutions comparées, et une session de
travail dure plus de quatre heures. Le raisonnement complet vit dans la docstring de
`raiyon.db.models.AvisProduit`, à côté du schéma qu'il explique.

### `source` sépare ce qui périme de ce qui ne périme pas

`brave` est daté et périme. `fabrique` est **écrit à la main**, committé dans
`data/seed/avis.jsonl`, et ne périme **jamais** : une fixture n'a pas de fraîcheur à
perdre. Sans cette exception, le seed d'avis expirerait vingt-quatre heures après
`make seed` et les campagnes cesseraient de trouver quoi que ce soit — silencieusement.

⚠️ **Aucune ligne `brave` n'entre au dépôt** : les conditions Brave §3(b) interdisent de
redistribuer des résultats de recherche, et un JSONL committé en serait une redistribution.

### `ON DELETE CASCADE` vers `produits`, et sa conséquence

`make seed` vide `produits` avant de le remplir : la cascade emporte donc les avis liés à
chaque chargement de catalogue. C'est voulu — un avis sur un produit qui n'existe plus
n'est pas un fait — et la conséquence est tenue à l'endroit où elle se produit :
`make seed` charge le catalogue **puis** les avis, dans la même commande.

### `UNIQUE (requete_normalisee, url)` tient lieu de verrou

Deux processus qui remplissent la même clé au même instant se départagent sur cette
contrainte : le second reçoit un `IntegrityError`, relit, et sert ce que le premier a
écrit. Pas de verrou consultatif, donc pas de chemin où un processus attend.

### Le `downgrade()` supprime la table et perd son contenu

Les lignes `brave` se récupèrent, les lignes `fabrique` sont dans le seed committé. Rien
n'est perdu qui ne se reconstruise par `make seed`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crée `avis_produit`, ses contraintes et ses deux index."""
    op.create_table(
        "avis_produit",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        # La clé, telle que `raiyon.avis.normalisation.normaliser()` la produit. La requête
        # d'origine n'est pas stockée : garder les deux inviterait à lire l'une en croyant
        # lire l'autre. Ce que le modèle a réellement écrit vit dans `evenements_tour`.
        sa.Column("requete_normalisee", sa.Text(), nullable=False),
        # Nullable : la recherche est libre, il n'y a pas toujours un produit sous lequel
        # ranger. C'est un lien, pas une clé — il n'entre pas dans l'identité de la ligne.
        sa.Column("produit_id", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("titre", sa.Text(), nullable=False),
        # Du texte brut de tiers, jamais une synthèse : aucun octet de cette colonne ne
        # vient d'un modèle de langage. Même règle que `produits`, même raison (§2).
        sa.Column("extrait", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "recupere_le",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Le vocabulaire est clos et il porte un comportement : `fabrique` ne périme pas.
        sa.CheckConstraint("source IN ('brave', 'fabrique')", name="source_connue"),
        # Une clé vide rangerait tous les résultats sous la même entrée. `normaliser()`
        # peut en produire une — sur « ??? » — et c'est à la couche outils de la refuser ;
        # la base ne fait pas confiance à cette promesse.
        sa.CheckConstraint("requete_normalisee <> ''", name="requete_non_vide"),
        # Borne explicite, tenue aussi en Python par `tronquer_extrait()`. Ici c'est le
        # filet : une écriture qui contournerait la couche haute ne passe pas.
        sa.CheckConstraint("char_length(extrait) <= 500", name="extrait_borne"),
        sa.ForeignKeyConstraint(["produit_id"], ["produits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("requete_normalisee", "url", name="uq_avis_produit_requete_url"),
    )
    # Toutes les lectures du cache partent de la clé. `recupere_le` n'ajouterait rien à
    # l'index : le groupe d'une clé tient en quelques lignes, et la péremption se décide
    # en Python sur le groupe entier.
    op.create_index("ix_avis_produit_requete", "avis_produit", ["requete_normalisee"])
    # La FK ne crée pas d'index côté Postgres, et son absence ferait ramer les DELETE en
    # cascade de `make seed`, qui en déclenche autant qu'il y a de produits.
    op.create_index("ix_avis_produit_produit_id", "avis_produit", ["produit_id"])


def downgrade() -> None:
    """Supprime la table. Les index et contraintes tombent avec elle."""
    op.drop_index("ix_avis_produit_produit_id", table_name="avis_produit")
    op.drop_index("ix_avis_produit_requete", table_name="avis_produit")
    op.drop_table("avis_produit")
