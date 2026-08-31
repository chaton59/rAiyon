"""Le mécanisme qui prouve qu'un paquet ne charge pas le SDK Anthropic.

Extrait de `test_isolation_passe_a.py` à l'étape 7, quand un second paquet a eu besoin de
la même garantie. Trois propriétés font tout l'intérêt du dispositif, et les recopier
approximativement ailleurs les perdrait :

* les modules sont **découverts sur le disque**, jamais listés à la main — une liste
  écrite ne couvrirait pas le module ajouté demain, et c'est précisément celui-là qui
  ferait entrer le SDK ;
* chaque module est importé dans un **interpréteur neuf** : `pytest` charge le SDK
  ailleurs dans la suite, donc regarder `sys.modules` dans le processus courant ne
  prouverait rien ;
* la **contre-épreuve** existe : sans elle, tout passerait sur une machine où le SDK
  n'est pas installé.
"""

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1] / "src" / "raiyon"

VERIFICATION = """
import sys
import {module}
charges = sorted(nom for nom in sys.modules if nom.split(".")[0] == "anthropic")
print(",".join(charges))
"""


def modules_du_paquet(paquet: str) -> list[str]:
    """Tous les modules importables d'un paquet de `raiyon`, découverts sur le disque."""
    repertoire = RACINE / paquet.removeprefix("raiyon.").replace(".", "/")
    noms = sorted(
        f"{paquet}.{chemin.stem}" for chemin in repertoire.glob("*.py") if chemin.stem != "__init__"
    )
    assert noms, f"aucun module trouvé dans {repertoire} — le chemin a dû changer"
    return [paquet, *noms]


def modules_anthropic_charges_par(module: str) -> list[str]:
    """Importe `module` dans un interpréteur neuf et rend ce qu'il a tiré d'`anthropic`."""
    resultat = subprocess.run(
        [sys.executable, "-c", VERIFICATION.format(module=module)],
        capture_output=True,
        text=True,
        check=True,
    )
    return [nom for nom in resultat.stdout.strip().split(",") if nom]
