"""Base déclarative et convention de nommage des contraintes.

La convention n'est pas cosmétique. Sans elle, Postgres nomme lui-même les
contraintes et les index créés sans nom explicite (`produits_categorie_check`,
`produits_pkey`...), Alembic autogénère alors des `downgrade()` qui ne savent plus
quoi supprimer, et une migration cesse d'être réversible sans qu'aucun test ne le
dise. Elle est posée avant la première migration parce qu'après, il faut renommer
l'existant.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

CONVENTION_DE_NOMMAGE = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    # `%(constraint_name)s` impose de nommer chaque CheckConstraint : c'est
    # volontaire, un `ck_produits_check1` ne dit rien à qui lit un downgrade.
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base commune à tous les modèles. `Base.metadata` est la cible d'Alembic."""

    metadata = MetaData(naming_convention=CONVENTION_DE_NOMMAGE)
