"""Charge `data/seed/avis.jsonl` en base. **Aucun appel API, aucun appel réseau.**

Le pendant de `catalogue.chargement` pour les avis, et il est délibérément écrit sur le
même patron : lire, revalider ligne à ligne, vider, insérer, dans une transaction. Le
seed d'avis n'est pas un après-coup du cache — c'est **ce qui le remplit** dans toutes les
exécutions qui ne doivent pas sortir sur le réseau, c'est-à-dire toutes les mesures.

⚠️ **L'ordre importe et il est tenu par l'appelant.** La FK `produit_id → produits.id`
casse en `ON DELETE CASCADE` : recharger le catalogue emporte les avis. Les avis se
chargent donc **après** le catalogue, et `scripts/seed_charger.py` enchaîne les deux dans
la même commande pour qu'aucun ordre d'appel n'ait à être retenu.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError
from sqlalchemy import CursorResult, delete, select
from sqlalchemy.orm import Session

from raiyon.avis.cache import vers_ligne
from raiyon.avis.schemas import AvisEnSeed
from raiyon.catalogue.pipeline import SEED
from raiyon.db.models import AvisProduit, Produit

FICHIER_SEED_AVIS = SEED / "avis.jsonl"


class SeedAvisInvalide(Exception):
    """Une ligne du seed ne passe pas `AvisEnSeed`. Le message nomme la ligne."""


@dataclass(frozen=True)
class RapportAvis:
    """Ce que le chargement a mis en base."""

    lus: int
    inseres: int
    supprimes: int
    orphelins: tuple[str, ...]
    """Les `produit_id` cités par le seed et absents du catalogue.

    ⚠️ **Ils ne font pas échouer le chargement, ils sont rendus.** Une fixture qui nomme un
    produit disparu du catalogue est un vrai défaut — l'avis ne sera jamais servi avec son
    lien —, mais lever ferait échouer `make seed` entier sur une ligne de fixture, donc
    ferait payer au catalogue la faute d'un avis. Le script les imprime."""


def lire_seed_avis(chemin: Path = FICHIER_SEED_AVIS) -> list[AvisEnSeed]:
    """Relit le seed en **revalidant** chaque ligne. Lève sur la première invalide.

    Le fichier est écrit à la main, donc c'est exactement le fichier dont la revalidation
    a le plus de valeur — l'inverse de l'intuition qui voudrait qu'un fichier committé soit
    sûr.
    """
    if not chemin.is_file():
        raise FileNotFoundError(f"{chemin} est absent — le seed d'avis fait partie du dépôt.")
    avis: list[AvisEnSeed] = []
    for numero, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), start=1):
        if not ligne.strip():
            continue
        try:
            avis.append(AvisEnSeed.model_validate(json.loads(ligne)))
        except (ValidationError, json.JSONDecodeError) as erreur:
            raise SeedAvisInvalide(f"{chemin.name} ligne {numero} : {erreur}") from erreur
    return avis


def charger_avis_en_base(session: Session, avis: Sequence[AvisEnSeed]) -> RapportAvis:
    """Vide `avis_produit` puis insère, **dans la transaction de l'appelant**.

    ⚠️ **Le vidage porte sur toute la table, pas seulement sur les lignes `fabrique`.** Un
    `make seed` remet la base dans l'état du dépôt ; y laisser survivre des lignes `brave`
    d'une exécution précédente donnerait une base dont le contenu dépend de son histoire,
    et deux postes ne mesureraient plus la même chose. Idempotent par construction : deux
    exécutions laissent la table identique.
    """
    # `rowcount` n'est pas déclaré sur `Result` : il appartient à `CursorResult`, que tout
    # `DELETE` rend en pratique. Même `cast` que `catalogue.chargement`, pour la même raison.
    efface = cast(CursorResult[Any], session.execute(delete(AvisProduit)))
    supprimes = efface.rowcount or 0
    orphelins = _produits_absents(session, avis)
    retenus = [ligne for ligne in avis if ligne.produit_id not in orphelins]
    session.add_all(vers_ligne(ligne.en_avis()) for ligne in retenus)
    session.flush()
    return RapportAvis(
        lus=len(avis),
        inseres=len(retenus),
        supprimes=supprimes,
        orphelins=orphelins,
    )


def _produits_absents(session: Session, avis: Sequence[AvisEnSeed]) -> tuple[str, ...]:
    """Les `produit_id` du seed qui n'existent pas dans `produits`.

    Constaté **avant** l'insertion : la FK lèverait de toute façon, mais son message parle
    d'une contrainte et non de la fixture qui l'a violée. Une requête de plus achète un
    diagnostic qui nomme la ligne — et permet d'écarter la fixture fautive au lieu de faire
    échouer le chargement du catalogue avec elle.
    """
    demandes = {ligne.produit_id for ligne in avis if ligne.produit_id is not None}
    if not demandes:
        return ()
    presents = set(session.scalars(select(Produit.id).where(Produit.id.in_(demandes))).all())
    return tuple(sorted(demandes - presents))
