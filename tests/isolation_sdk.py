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

⚠️ **La garantie n'a jamais porté sur SQLAlchemy, et l'étape 10 le redit.** `raiyon.tools`
et `raiyon.validateur` importent `matching.depot`, donc `sqlalchemy` ; les modules purs de
`raiyon.api` aussi, puisqu'ils sont typés sur les événements du domaine. La propriété qui
compte n'est pas « rien n'importe SQLAlchemy » mais **« rien ne se connecte »** : la part
pure de la suite tourne sans conteneur, et `make check` le constate à chaque exécution.

L'étape 10 a généralisé le mécanisme à un paquet quelconque (`modules_charges_par`), parce
que `raiyon.api` a besoin de la même preuve sur **`fastapi`** : un module de sérialisation
qui importerait `Response` cesserait d'être testable hors serveur.
"""

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1] / "src" / "raiyon"

VERIFICATION = """
import sys
import {module}
racines = {racines!r}
charges = sorted(nom for nom in sys.modules if nom.split(".")[0] in racines)
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


def modules_charges_par(module: str, racines: frozenset[str]) -> list[str]:
    """Importe `module` dans un interpréteur neuf et rend ce qu'il a tiré de `racines`.

    `racines` est un ensemble de paquets de premier niveau (`{"anthropic"}`,
    `{"fastapi", "starlette"}`…). Rendre la **liste** de ce qui a été chargé plutôt qu'un
    booléen n'est pas du confort : sur un échec, le message de pytest nomme le module
    coupable, ce qui évite de rejouer l'import à la main pour le trouver.
    """
    resultat = subprocess.run(
        [sys.executable, "-c", VERIFICATION.format(module=module, racines=sorted(racines))],
        capture_output=True,
        text=True,
        check=True,
    )
    return [nom for nom in resultat.stdout.strip().split(",") if nom]


VERIFICATION_PAR_PREFIXE = """
import sys
import {module}
prefixes = {prefixes!r}
charges = sorted(
    nom for nom in sys.modules
    if any(nom == prefixe or nom.startswith(prefixe + ".") for prefixe in prefixes)
)
print(",".join(charges))
"""


def modules_charges_sous(module: str, prefixes: frozenset[str]) -> list[str]:
    """Comme `modules_charges_par`, mais sur des **préfixes pointés** plutôt que des
    paquets de premier niveau.

    Ajouté à l'étape 15 pour une garantie que le mécanisme d'origine ne sait pas exprimer :
    `raiyon.machine` doit ignorer `raiyon.agent`. Découper sur le premier segment rendrait
    `raiyon`, qui est chargé par tout le monde et ne prouverait rien.

    ⚠️ **Ce que cette variante ne peut pas promettre, et il faut le redire ici** : elle ne
    dit rien de `raiyon.db`. `raiyon.machine.decision` est typé sur `EtatSession` et sur
    `ResultatOutil`, donc sur `raiyon.matching.depot`, donc sur `raiyon.db.models` — comme
    `raiyon.tools` et `raiyon.validateur` avant lui. La propriété qui compte reste
    **« rien ne se connecte »**, et c'est le temps d'exécution de `make check` qui la
    constate.
    """
    resultat = subprocess.run(
        [
            sys.executable,
            "-c",
            VERIFICATION_PAR_PREFIXE.format(module=module, prefixes=sorted(prefixes)),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return [nom for nom in resultat.stdout.strip().split(",") if nom]


def modules_anthropic_charges_par(module: str) -> list[str]:
    """Le cas historique, et de loin le plus important : le SDK Anthropic."""
    return modules_charges_par(module, frozenset({"anthropic"}))
