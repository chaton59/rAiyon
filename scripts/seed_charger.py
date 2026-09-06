"""Point d'entrée de la passe C — `make seed`. **Aucun appel API.**

Charge le seed committé en base : lecture, revalidation par `ProduitEnBase`, insertion
en une transaction. Depuis l'étape 26 il charge aussi `data/seed/avis.jsonl` — voir
`executer_passe_c()` pour pourquoi les deux vivent dans la même commande.

⚠️ **Conséquence connue et non traitée** (§3.4ter) : construire l'engine charge
`Settings`, où `ANTHROPIC_API_KEY` est obligatoire depuis l'étape 2. Cette commande
réclame donc une clé qu'elle n'utilisera jamais. La rendre optionnelle rouvrirait une
décision de l'étape 2 ; l'arbitrage attend l'étape 8, quand un appel API existera
vraiment. `make seed-build`, lui, ne touche pas la configuration.
"""

import argparse
import sys
from pathlib import Path

from raiyon.avis.chargement import SeedAvisInvalide
from raiyon.catalogue.chargement import BaseInjoignable, executer_passe_c
from raiyon.catalogue.normalisation import PipelineArrete
from raiyon.catalogue.pipeline import FICHIER_SEED


def main() -> int:
    """Remplit la table `produits`. Rend 1 si le seed est invalide ou la base absente."""
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--seed", type=Path, default=FICHIER_SEED)
    arguments = analyseur.parse_args()

    try:
        rapport, avis = executer_passe_c(arguments.seed)
    except BaseInjoignable as erreur:
        print(f"\n⛔ {erreur}\n", file=sys.stderr)
        return 1
    except (PipelineArrete, SeedAvisInvalide, FileNotFoundError) as erreur:
        print(f"\n⛔ Seed inutilisable — {erreur}\n", file=sys.stderr)
        return 1

    print(
        f"{rapport.lus} produits relus et revalidés · "
        f"{rapport.supprimes} supprimés · {rapport.inseres} insérés"
    )
    print(f"{avis.lus} avis relus et revalidés · {avis.inseres} insérés")
    if avis.orphelins:
        # ⚠️ Un avertissement, pas une erreur : une fixture qui nomme un produit disparu
        # est un défaut réel, mais faire échouer `make seed` entier dessus ferait payer au
        # catalogue la faute d'un avis. La ligne est écartée et dite.
        print(
            f"⚠️  {len(avis.orphelins)} avis écartés — produit absent du catalogue : "
            f"{', '.join(avis.orphelins)}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
