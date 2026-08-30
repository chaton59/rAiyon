"""Calibre les bornes de normalisation du moteur sur le seed committé. **Aucun appel API.**

    uv run python scripts/calibrer_bornes.py

Imprime deux dictionnaires Python à **recopier dans `src/raiyon/matching/attributs.py`**.
Le script est rejouable ; son résultat est du code, pas un cache — et c'est tout le
propos de l'arbitrage G. Une borne recalculée au runtime rendrait le sous-score
dépendant du lot candidat, c'est-à-dire un min-max relatif déguisé : deux conversations
classeraient alors le même produit différemment, et un test de classement dépendrait de
sa fixture plutôt que du code.

`tests/matching/test_calibration.py` relance ces mêmes fonctions sur le seed et compare
au registre. Modifier une borne à la main casse donc un test, ce qui est le
comportement voulu.
"""

import argparse
import math
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from raiyon.catalogue.pipeline import FICHIER_SEED, lire_seed
from raiyon.catalogue.schemas import CATEGORIES, Categorie, ProduitEnBase
from raiyon.matching.attributs import ATTRIBUTS, Genre, valeur_du_produit

PERCENTILE_BAS = 5
PERCENTILE_HAUT = 95
"""Winsorisation au 5ᵉ et au 95ᵉ centile.

Le 95ᵉ est celui qui compte : `memory.price_per_gb` monte à 497,5 USD/GB sur des
modules de très faible capacité (valeur réelle, conservée en base). Normaliser sur ce
maximum écraserait 99 % du catalogue dans un sous-score indiscernable de zéro. Le 5ᵉ
est son symétrique, appliqué par cohérence plutôt que par nécessité mesurée.
"""

CATEGORIES_SANS_PRIX_PAR_GO: tuple[Categorie, ...] = tuple(
    categorie for categorie in CATEGORIES if "price_per_gb" not in ATTRIBUTS[categorie]
)
"""Les catégories où « rapport qualité/prix » doit être calculé faute d'un ratio donné
par la source. Dérivé du registre, jamais écrit à la main : le jour où une catégorie
gagne un `price_per_gb`, son plafond disparaît tout seul."""


def percentile(valeurs: Sequence[Decimal], centile: int) -> Decimal:
    """Centile par la méthode du **rang le plus proche**, sans interpolation.

    Conséquence voulue : la borne rendue est une valeur **réellement observée** dans le
    catalogue. Une interpolation linéaire fabriquerait un nombre que personne n'a
    mesuré — inoffensif sur une borne de normalisation, mais c'est le genre de détail
    dont ce projet s'interdit de prendre l'habitude.
    """
    ordonnees = sorted(valeurs)
    rang = math.ceil(centile / 100 * len(ordonnees))
    return ordonnees[min(max(rang - 1, 0), len(ordonnees) - 1)]


def valeurs_numeriques(
    produits: Sequence[ProduitEnBase], categorie: Categorie, champ: str
) -> list[Decimal]:
    """Valeurs non nulles d'un champ numérique, sur une catégorie. En `Decimal`."""
    attribut = ATTRIBUTS[categorie][champ]
    valeurs: list[Decimal] = []
    for produit in produits:
        if produit.categorie != categorie:
            continue
        brute = valeur_du_produit(produit, attribut)
        if isinstance(brute, Decimal):
            valeurs.append(brute)
        elif isinstance(brute, int) and not isinstance(brute, bool):
            valeurs.append(Decimal(brute))
    return valeurs


def calibrer_bornes(
    produits: Sequence[ProduitEnBase],
) -> dict[tuple[str, str], tuple[Decimal, Decimal]]:
    """Bornes basses et hautes de tous les attributs numériques, par catégorie.

    Tous, et pas seulement ceux de rôle `score` : un filtre dur gradué devient un score
    dès qu'il est posé en `souhait` (arbitrage D), et il lui faut alors des bornes.
    """
    bornes: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
    for categorie in CATEGORIES:
        for champ, attribut in ATTRIBUTS[categorie].items():
            if attribut.genre is not Genre.NUMERIQUE:
                continue
            valeurs = valeurs_numeriques(produits, categorie, champ)
            if not valeurs:
                continue
            bornes[categorie, champ] = (
                percentile(valeurs, PERCENTILE_BAS),
                percentile(valeurs, PERCENTILE_HAUT),
            )
    return bornes


def calibrer_plafonds_ratio(produits: Sequence[ProduitEnBase]) -> dict[str, Decimal]:
    """Plafond du ratio « score technique ÷ prix », pour les catégories sans `price_per_gb`.

    Vaut `1 / P5(prix)` : un produit au score technique parfait, vendu au prix du 5ᵉ
    centile de sa catégorie, atteint exactement 1. Au-delà, le sous-score est borné.
    Sans ce plafond constant, il faudrait diviser par le meilleur ratio **du lot** —
    et le « meilleur rapport qualité/prix » cesserait d'être reproductible.
    """
    plafonds: dict[str, Decimal] = {}
    for categorie in CATEGORIES_SANS_PRIX_PAR_GO:
        prix = valeurs_numeriques(produits, categorie, "prix_usd")
        if not prix:
            continue
        plafonds[categorie] = (Decimal(1) / percentile(prix, PERCENTILE_BAS)).quantize(
            Decimal("0.00000001")
        )
    return plafonds


def _literal(valeur: Decimal) -> str:
    """Rend `Decimal("…")`, forme dans laquelle la constante sera relue."""
    return f'Decimal("{valeur.normalize():f}")'


def rendre_constantes(
    bornes: dict[tuple[str, str], tuple[Decimal, Decimal]], plafonds: dict[str, Decimal]
) -> str:
    """Le bloc de code à recopier dans le registre."""
    lignes = ["BORNES_CALIBREES: dict[tuple[str, str], tuple[Decimal, Decimal]] = {"]
    for (categorie, champ), (basse, haute) in sorted(bornes.items()):
        lignes.append(f'    ("{categorie}", "{champ}"): ({_literal(basse)}, {_literal(haute)}),')
    lignes.append("}")
    lignes.append("")
    lignes.append("PLAFONDS_RATIO: dict[str, Decimal] = {")
    for categorie, plafond in sorted(plafonds.items()):
        lignes.append(f'    "{categorie}": {_literal(plafond)},')
    lignes.append("}")
    return "\n".join(lignes)


def main() -> int:
    """Imprime les constantes. Rend 1 si le seed est absent."""
    analyseur = argparse.ArgumentParser(description="Calibre les bornes du moteur de matching.")
    analyseur.add_argument("--seed", type=Path, default=FICHIER_SEED)
    arguments = analyseur.parse_args()

    try:
        produits = lire_seed(arguments.seed)
    except FileNotFoundError as erreur:
        print(f"\n⛔ {erreur}\n", file=sys.stderr)
        return 1

    bornes = calibrer_bornes(produits)
    plafonds = calibrer_plafonds_ratio(produits)

    print(f"# {len(produits)} produits lus depuis {arguments.seed}")
    print(f"# centiles {PERCENTILE_BAS} et {PERCENTILE_HAUT}, rang le plus proche\n")
    print(rendre_constantes(bornes, plafonds))

    degenerees = [cle for cle, (basse, haute) in bornes.items() if basse >= haute]
    if degenerees:
        print(
            "\n# ⚠️ bornes plates (basse >= haute), non scorables : "
            + ", ".join(f"{categorie}.{champ}" for categorie, champ in sorted(degenerees)),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
