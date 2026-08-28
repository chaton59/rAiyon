"""Clé canonique, identifiant synthétique, déduplication.

**L'identifiant *est* la clé de déduplication** (arbitrage C de l'étape 5). Deux
lignes qui produisent le même `id` sont le même produit par construction : la
déduplication devient un regroupement par `id`, pas une heuristique séparée qu'il
faudrait garder cohérente avec le calcul de l'identifiant.

**La clé exclut le prix et toute grandeur dérivée du prix** (arbitrage D). C'est le
piège central de l'étape : `price_per_gb` est une fonction du prix, et le laisser
dans la clé empêcherait deux enregistrements identiques à prix différents de se
rejoindre — donc annulerait la déduplication sur les deux catégories qui le portent.
La discipline qui rend cela vrai vit dans `normalisation.py` : les grandeurs dérivées
du prix ne sont ajoutées qu'**après** ce module.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

LONGUEUR_EMPREINTE = 10
"""10 hexadécimaux, soit 40 bits — la forme imposée par `MOTIF_ID` (étape 4).

Sur ~10 000 lignes, la probabilité d'une collision est de l'ordre de 5·10⁻⁵. Elle
n'est pas nulle, donc `dedupliquer()` la **détecte** au lieu de la supposer absente :
deux clés canoniques différentes sous le même identifiant fusionneraient en silence
deux produits distincts, ce qui est exactement le mode d'échec que ce module existe
pour empêcher.
"""


def _serialisable(valeur: Any) -> Any:  # noqa: ANN401
    """Rend une valeur sérialisable en JSON de façon **stable entre deux machines**.

    Les `Decimal` partent en chaînes, jamais en flottants : `json.dumps(0.1)` dépend
    de la représentation binaire du nombre, et l'identifiant doit être identique
    quelle que soit la machine qui rejoue le pipeline.
    """
    if isinstance(valeur, Decimal):
        return str(valeur)
    if isinstance(valeur, dict):
        return {cle: _serialisable(sous_valeur) for cle, sous_valeur in valeur.items()}
    if isinstance(valeur, list | tuple):
        return [_serialisable(element) for element in valeur]
    return valeur


def cle_canonique(nom: str, specs: dict[str, Any]) -> str:
    """Rend la représentation canonique d'un produit : son nom source et ses specs.

    Le prix n'y figure pas, ni aucune grandeur qui en dérive — c'est ce qui fait que
    deux annonces du même produit à deux prix se rejoignent.

    Quatre réglages, et chacun sert la stabilité de l'identifiant :
    `sort_keys` (l'ordre d'insertion d'un dictionnaire Python ne doit pas décider de
    l'identifiant), `separators` sans espace (une version de Python qui changerait
    ses espaces par défaut réécrirait tout le seed), `ensure_ascii=False` (les
    caractères non-ASCII des noms sources partent tels quels, encodés en UTF-8 par
    l'appelant), et les `Decimal` en chaînes.
    """
    return json.dumps(
        {"nom": nom, "specs": _serialisable(specs)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def calculer_id(categorie: str, cle: str) -> str:
    """`{categorie}-{10 premiers hexadécimaux de sha256(clé canonique)}`.

    L'encodage UTF-8 est explicite : `str.encode()` prend UTF-8 par défaut en Python,
    mais l'identifiant du catalogue committé ne doit pas dépendre d'un défaut.
    """
    empreinte = hashlib.sha256(cle.encode("utf-8")).hexdigest()[:LONGUEUR_EMPREINTE]
    return f"{categorie}-{empreinte}"


@dataclass(frozen=True)
class LigneNormalisee:
    """Une ligne source normalisée, avant déduplication et avant les dérivées du prix."""

    id: str
    cle: str
    categorie: str
    nom: str
    marque: str
    prix_usd: Decimal
    specs: dict[str, Any]
    price_per_gb_source: Decimal | None = None
    """Valeur `price_per_gb` telle que la source l'écrit, conservée pour un seul usage.

    Elle sert au **contrôle** de la transformation 6 — comparer le recalcul à la
    valeur source sur les lignes non dédupliquées — et à rien d'autre. Elle n'entre ni
    dans `cle`, ni dans `specs` : c'est une grandeur dérivée du prix, et l'arbitrage D
    l'exclut de la clé. Ce qui est écrit en base est **toujours** le recalcul.
    """


@dataclass(frozen=True)
class StatsDeduplication:
    """Ce que la déduplication a fait sur une catégorie — trois chiffres, pas un de plus."""

    categorie: str
    lignes_entrantes: int
    groupes: int
    lignes_absorbees: int
    ecart_prix_max: Decimal
    """Écart de prix maximal **à l'intérieur d'un groupe**.

    C'est le chiffre qui révélerait une clé trop lâche : deux produits différents
    fusionnés se trahissent par un écart de prix que rien n'explique.
    """
    id_ecart_max: str | None


def dedupliquer(
    lignes: Iterable[LigneNormalisee],
) -> tuple[list[LigneNormalisee], dict[str, StatsDeduplication]]:
    """Regroupe par `id`, garde le **prix le plus bas**. Une règle, uniforme.

    Le même code absorbe les 51 redondances de `cpu` et préserve les 346 variantes de
    `memory` : seul son effet diffère, parce que les variantes `memory` diffèrent par
    des attributs (couleur, fréquence, latence) qui entrent dans la clé.

    À prix égal, c'est la première ligne rencontrée qui gagne, et l'ordre de lecture
    du fichier source est déterministe : deux exécutions rendent le même résultat.
    """
    groupes: dict[str, list[LigneNormalisee]] = {}
    cles_par_id: dict[str, str] = {}

    for ligne in lignes:
        connue = cles_par_id.setdefault(ligne.id, ligne.cle)
        if connue != ligne.cle:
            raise CollisionIdentifiant(ligne.id, connue, ligne.cle)
        groupes.setdefault(ligne.id, []).append(ligne)

    retenues: list[LigneNormalisee] = []
    stats_brutes: dict[str, dict[str, Any]] = {}

    for identifiant, membres in groupes.items():
        gagnante = min(membres, key=lambda ligne: ligne.prix_usd)
        retenues.append(gagnante)

        prix = [membre.prix_usd for membre in membres]
        ecart = max(prix) - min(prix)
        stats = stats_brutes.setdefault(
            gagnante.categorie,
            {"entrantes": 0, "groupes": 0, "absorbees": 0, "ecart": Decimal(0), "id": None},
        )
        stats["entrantes"] += len(membres)
        stats["groupes"] += 1
        stats["absorbees"] += len(membres) - 1
        if ecart > stats["ecart"]:
            stats["ecart"] = ecart
            stats["id"] = identifiant

    return retenues, {
        categorie: StatsDeduplication(
            categorie=categorie,
            lignes_entrantes=valeurs["entrantes"],
            groupes=valeurs["groupes"],
            lignes_absorbees=valeurs["absorbees"],
            ecart_prix_max=valeurs["ecart"],
            id_ecart_max=valeurs["id"],
        )
        for categorie, valeurs in stats_brutes.items()
    }


class CollisionIdentifiant(Exception):
    """Deux clés canoniques distinctes sous le même identifiant tronqué.

    Arrêt immédiat : continuer fusionnerait deux produits différents en un seul, en
    silence. La sortie de secours, si cela arrivait un jour, serait d'allonger
    `LONGUEUR_EMPREINTE` — mais c'est une décision, pas un rattrapage automatique,
    parce qu'elle réécrit tous les identifiants du seed.
    """

    def __init__(self, identifiant: str, premiere: str, seconde: str) -> None:
        super().__init__(
            f"collision sur {identifiant!r} entre deux produits distincts :\n"
            f"  1. {premiere}\n  2. {seconde}"
        )
        self.identifiant = identifiant
