"""Point d'entrée de la passe C — `make seed`. **Aucun appel API.**

Charge le seed committé en base : lecture, revalidation par `ProduitEnBase`, insertion
en une transaction.

⚠️ **Conséquence connue et non traitée** (§3.4ter) : construire l'engine charge
`Settings`, où `ANTHROPIC_API_KEY` est obligatoire depuis l'étape 2. Cette commande
réclame donc une clé qu'elle n'utilisera jamais. La rendre optionnelle rouvrirait une
décision de l'étape 2 ; l'arbitrage attend l'étape 8, quand un appel API existera
vraiment. `make seed-build`, lui, ne touche pas la configuration.
"""

import argparse
import sys
from pathlib import Path

from raiyon.catalogue.chargement import BaseInjoignable, executer_passe_c
from raiyon.catalogue.normalisation import PipelineArrete
from raiyon.catalogue.pipeline import FICHIER_SEED


def main() -> int:
    """Remplit la table `produits`. Rend 1 si le seed est invalide ou la base absente."""
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--seed", type=Path, default=FICHIER_SEED)
    arguments = analyseur.parse_args()

    try:
        rapport = executer_passe_c(arguments.seed)
    except BaseInjoignable as erreur:
        print(f"\n⛔ {erreur}\n", file=sys.stderr)
        return 1
    except (PipelineArrete, FileNotFoundError) as erreur:
        print(f"\n⛔ Seed inutilisable — {erreur}\n", file=sys.stderr)
        return 1

    print(
        f"{rapport.lus} produits relus et revalidés · "
        f"{rapport.supprimes} supprimés · {rapport.inseres} insérés"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
