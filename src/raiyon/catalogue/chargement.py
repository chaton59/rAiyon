"""Passe C — chargement du seed committé en base. **Aucun appel API.**

`make seed` ne rejoue pas le pipeline : il lit `data/seed/produits.jsonl`, **revalide
chaque ligne par `ProduitEnBase`** et insère via `Produit.depuis_schema()`.

**Pourquoi revalider un fichier committé ?** Parce qu'être committé ne rend pas un
fichier digne de confiance : il se modifie à la main, il se résout à la main après un
conflit de merge, et un `git checkout` d'une branche ancienne le remplace. C'est la
même raison qui a fait de `ProduitEnBase` la porte d'entrée unique de la table — si
elle a une exception, ce n'est plus une porte. La revalidation n'a jamais eu de
rapport avec la passe LLM : elle survit à sa suppression sans changer d'un mot.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlalchemy import CursorResult, delete
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from raiyon.catalogue.pipeline import FICHIER_SEED, lire_seed
from raiyon.catalogue.schemas import ProduitEnBase
from raiyon.db.engine import session_scope
from raiyon.db.models import Produit

MESSAGE_SANS_BASE = (
    "Postgres est injoignable. Lancer `make up` (démarre le conteneur et attend le "
    "healthcheck), puis `make migrate`, puis relancer `make seed`."
)


class BaseInjoignable(Exception):
    """La base n'est pas là. Message explicite plutôt qu'une trace SQLAlchemy."""


@dataclass(frozen=True)
class RapportChargement:
    """Ce que le chargement a mis en base."""

    lus: int
    inseres: int
    supprimes: int


def charger_en_base(session: Session, produits: Sequence[ProduitEnBase]) -> tuple[int, int]:
    """Vide la table puis insère, **dans la même transaction**. Rend (supprimés, insérés).

    Idempotent par construction : deux exécutions laissent la table dans le même état.
    Le catalogue est un instantané, pas un flux (§3.4) — un `UPSERT` ligne à ligne
    laisserait vivre un produit retiré de la source.

    ⚠️ Ce `DELETE` est sûr **parce qu'aucune clé étrangère ne pend à `produits`
    aujourd'hui**. `sessions` et `tours_conversation` n'y référencent rien. Le jour où
    une table citera un produit — un historique de recommandations, par exemple — cette
    ligne devra devenir un `UPSERT`, faute de quoi le rechargement du seed emportera
    l'historique avec lui.
    """
    # `CursorResult.rowcount` : `Result` générique ne l'expose pas au typage, mais un
    # DELETE rend toujours un curseur. Le `cast` est de la paperasse, pas un doute.
    supprimes = cast(CursorResult[Any], session.execute(delete(Produit))).rowcount
    session.add_all([Produit.depuis_schema(produit) for produit in produits])
    return supprimes, len(produits)


def executer_passe_c(chemin_seed: Path = FICHIER_SEED) -> RapportChargement:
    """Lit, revalide, charge. Une seule transaction, aucun appel API.

    Trois opérations, et plus aucune fusion : ce que le JSONL contient est exactement
    ce qui entre en base. Le cache de traductions qui s'intercalait ici a disparu avec
    la passe B (§3.4ter).
    """
    produits = lire_seed(chemin_seed)

    try:
        with session_scope() as session:
            supprimes, inseres = charger_en_base(session, produits)
    except OperationalError as erreur:
        raise BaseInjoignable(MESSAGE_SANS_BASE) from erreur

    return RapportChargement(lus=len(produits), inseres=inseres, supprimes=supprimes)
