"""Chargement des prompts versionnés, et leur empreinte (§3.14).

Les prompts vivent dans `prompts/`, en markdown numéroté, chargés au runtime plutôt
qu'écrits en constante Python. Sans cela, impossible de comparer deux formulations sur la
même suite de scénarios — ce qui est le cœur du travail de l'étape 13.

### L'empreinte coûte trois lignes maintenant et en vaut beaucoup à l'étape 12

§7 liste « les cassettes deviennent obsolètes silencieusement » comme un risque moyen, et
son atténuation est le hash du prompt stocké dans la cassette. Écrire l'empreinte
maintenant, et la loguer à chaque appel, évite d'avoir à la rétro-ajouter sur des
cassettes déjà enregistrées — c'est-à-dire d'avoir à toutes les régénérer pour savoir
laquelle était périmée.

Douze caractères de sha256 : de quoi distinguer deux rédactions à l'œil dans un log, sans
prétendre à une propriété cryptographique dont on n'a pas l'usage.
"""

import hashlib
from functools import lru_cache
from pathlib import Path

import structlog

logueur = structlog.get_logger(__name__)

REPERTOIRE = Path(__file__).resolve().parents[3] / "prompts"
"""`src/raiyon/agent/prompts.py` → racine du dépôt. Le projet est installé en mode
éditable (`uv sync` sur un `hatchling` qui pointe `src/raiyon`), donc ce chemin résout.
Une installation figée en `site-packages` ne verrait pas `prompts/` — le jour où le
projet s'empaquette, les prompts deviennent des données de paquet ; il n'y a pas de
raison de payer cette complexité avant."""

SYSTEME_V1 = "systeme.v1"
"""La version en vigueur, nommée une fois. La boucle ne cite pas de nom de fichier."""


class PromptIntrouvable(Exception):
    """Le fichier de prompt n'existe pas. Un démarrage sans prompt n'est pas rattrapable."""


@lru_cache(maxsize=8)
def charger(nom: str) -> str:
    """Le texte d'un prompt, par son nom sans extension. Mis en cache par nom.

    Le cache n'est pas une optimisation — le fichier fait deux kilo-octets — mais une
    garantie : le prompt système part dans le préfixe mis en cache par l'API (arbitrage
    7), et il doit être identique **octet pour octet** d'un appel à l'autre. Relire le
    fichier à chaque tour ferait dépendre cette identité du fait que personne ne l'édite
    pendant qu'une conversation tourne.
    """
    chemin = REPERTOIRE / f"{nom}.md"
    if not chemin.is_file():
        raise PromptIntrouvable(
            f"{chemin} est introuvable. Les prompts versionnés vivent dans "
            f"{REPERTOIRE} (§3.14) — vérifier le nom, ou que le dépôt est complet."
        )
    return chemin.read_text(encoding="utf-8")


def empreinte(texte: str) -> str:
    """Les douze premiers caractères du sha256. Logué à chaque appel avec la version."""
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:12]


def prompt_systeme() -> tuple[str, str]:
    """Le prompt système en vigueur et son empreinte, et il les loggue.

    Rendre les deux ensemble plutôt que de laisser l'appelant recalculer l'empreinte :
    c'est ce qui garantit que ce qui est logué est bien ce qui est envoyé.
    """
    texte = charger(SYSTEME_V1)
    signature = empreinte(texte)
    logueur.info("prompts.systeme", version=SYSTEME_V1, empreinte=signature, octets=len(texte))
    return texte, signature
