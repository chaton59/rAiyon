"""Point d'entrée de la passe A — `make seed-build`.

Script fin : parsing d'arguments et appel. Toute la logique vit dans
`raiyon.catalogue.pipeline`, pour qu'elle reste testable sans lancer un processus.

Exige `data/raw/` (non versionné — cf. `data/raw/SOURCE.md`). N'appelle aucune API.
"""

import argparse
import sys
from pathlib import Path

from raiyon.catalogue.normalisation import PipelineArrete
from raiyon.catalogue.pipeline import (
    BRUT,
    FICHIER_RAPPORT,
    FICHIER_SEED,
    ecrire_rapport,
    ecrire_seed,
    executer_passe_a,
)
from raiyon.catalogue.selection import CIBLE_PAR_CATEGORIE, GRAINE_TIRAGE


def main() -> int:
    """Construit le seed et son rapport. Rend 1 si le pipeline s'est arrêté."""
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--brut", type=Path, default=BRUT, help="répertoire des JSON sources")
    analyseur.add_argument("--seed", type=Path, default=FICHIER_SEED, help="JSONL de sortie")
    analyseur.add_argument("--rapport", type=Path, default=FICHIER_RAPPORT, help="rapport Markdown")
    analyseur.add_argument(
        "--cible",
        type=int,
        default=CIBLE_PAR_CATEGORIE,
        help=f"produits visés par catégorie (défaut : {CIBLE_PAR_CATEGORIE})",
    )
    arguments = analyseur.parse_args()

    try:
        resultat = executer_passe_a(
            repertoire_brut=arguments.brut, cible=arguments.cible, graine=GRAINE_TIRAGE
        )
    except PipelineArrete as arret:
        # Un arrêt bruyant est un succès du garde-fou, pas un plantage : le message
        # nomme le produit fautif et dit pourquoi la règle ne tient pas sur lui.
        print(f"\n⛔ Pipeline arrêté — {arret}\n", file=sys.stderr)
        return 1

    ecrire_seed(resultat.selection.produits, arguments.seed)
    ecrire_rapport(resultat, arguments.rapport)

    entonnoir = resultat.entonnoir
    print(
        f"lues {sum(entonnoir.lues.values())} → à prix {sum(entonnoir.a_prix.values())} "
        f"→ normalisées {sum(entonnoir.normalisees.values())} "
        f"→ dédupliquées {sum(entonnoir.dedupliquees.values())} "
        f"→ validées {sum(entonnoir.validees.values())} "
        f"→ seed {len(resultat.selection.produits)}"
    )
    print(f"→ {arguments.seed}")
    print(f"→ {arguments.rapport}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
