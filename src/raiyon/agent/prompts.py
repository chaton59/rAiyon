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
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import structlog

from raiyon.config import PROMPT_SYSTEME_PAR_DEFAUT, get_settings

logueur = structlog.get_logger(__name__)

REPERTOIRE = Path(__file__).resolve().parents[3] / "prompts"
"""`src/raiyon/agent/prompts.py` → racine du dépôt. Le projet est installé en mode
éditable (`uv sync` sur un `hatchling` qui pointe `src/raiyon`), donc ce chemin résout.
Une installation figée en `site-packages` ne verrait pas `prompts/` — le jour où le
projet s'empaquette, les prompts deviennent des données de paquet ; il n'y a pas de
raison de payer cette complexité avant."""

PREFIXE_SYSTEME = "systeme."
"""Ce qui distingue un prompt système d'un autre prompt de `prompts/`. Le préfixe est
lu par `versions_systeme()`, qui découvre les fichiers plutôt que de les lister."""

SYSTEME_PAR_DEFAUT = PROMPT_SYSTEME_PAR_DEFAUT
"""La version servie quand rien n'est configuré. **Arbitrée au jalon 3 de l'étape 13.**

⚠️ **Importée de `config.py`, jamais recopiée.** Elle a été écrite deux fois pendant une
demi-heure — ici et dans le défaut du champ `Settings.prompt_systeme` — et déplacer l'une
sans l'autre a fait annoncer `systeme.v2` à un dépôt qui servait `systeme.v1`. Aucun type
ne voit ce genre d'écart ; un seul endroit d'écriture, si.

`systeme.v1` jusque-là. v2 passe en vigueur parce qu'aucune mesure ne recule et qu'une
avance au-delà du bruit : le markdown que le front ne rend pas tombe de 51 à 0 par passe,
contre une dispersion de ± 43. Les cinq autres mesures sont dans le bruit, dans le bon
sens ou stables, et les critères nº1, nº2, nº4 et nº6 sont inchangés.

⚠️ **Ce n'est pas le taux de rejet qui l'a emporté** — il baisse de 3,00 à 2,00 par passe,
très en deçà de la dispersion. Ce qui emporte la décision et ne se lit dans aucun agrégat
est l'appendice de domaine : v1 **enseignait la technologie d'affichage**, ce que §2
interdit, et le faisait sans un chiffre ; v2 refuse le cours et bascule sur la répartition
du catalogue. Voir §5 étape 13."""


def version_systeme() -> str:
    """Le nom du fichier de prompt système en vigueur, sans extension.

    **Une sélection de fichier, pas une interpolation** (§3.13). Le préfixe mis en
    cache est `tools` + `system` et doit rester identique octet pour octet d'un appel
    à l'autre : ce qui viole cette règle, c'est un texte qui change, pas le fait de
    choisir lequel des trois textes envoyer. Chacun des trois reste, lui, immuable.

    La valeur vient de `Settings`, donc de `RAIYON_PROMPT_SYSTEME`, parce que
    `config.py` est le point unique de lecture de l'environnement dans ce projet.
    """
    return get_settings().prompt_systeme


def versions_systeme() -> tuple[str, ...]:
    """Les prompts système présents sur le disque, triés. **Découverts, pas listés.**

    Le test d'interpolation de l'arbitrage 7 balaie ce que cette fonction rend, et non
    la seule version en vigueur : à l'étape 13, trois fichiers coexistent, et deux
    d'entre eux ne sont sélectionnés par personne pendant la campagne du troisième. Un
    `{quelque_chose}` glissé dans le fichier au repos ne se verrait qu'au moment de
    lancer sa campagne, c'est-à-dire au moment de dépenser trente-six prises.

    Découvrir plutôt qu'écrire une liste : une `systeme.v4.md` ajoutée demain est
    balayée sans que personne n'ait à s'en souvenir. C'est le même geste que
    `codes_jamais_declenches`, qui dérive de `CodeGrief` au lieu d'une liste tenue à
    la main.
    """
    return tuple(sorted(chemin.stem for chemin in REPERTOIRE.glob(f"{PREFIXE_SYSTEME}*.md")))


GRIEF_V1 = "grief.v1"
"""Le message de reprise de l'étape 9, versionné **comme le prompt système** (§3.14).

Il est écrit pour être lu par le modèle, pas par le client : c'est la même convention
que les messages d'`erreurs.py`, et c'est pour cela qu'il vit dans `prompts/` plutôt
qu'en constante Python — l'étape 13 devra pouvoir en changer la formulation et mesurer
si le taux de régénération réussie bouge."""

MARQUE_DES_GRIEFS = "<!-- griefs -->"
"""L'emplacement de la liste des griefs dans `grief.v1.md`.

Un commentaire markdown plutôt qu'un `{griefs}` de `.format()` : le fichier peut alors
contenir des accolades sans qu'il faille les échapper, et une marque oubliée se voit à
la relecture au lieu de lever un `KeyError` au premier grief de production."""


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


@dataclass(frozen=True, slots=True)
class SystemeEnVigueur:
    """Le prompt système servi à cet appel : sa version, son texte, son empreinte.

    Les trois voyagent ensemble depuis que la version est **choisie** et non plus
    écrite en constante. Les séparer laisserait un appelant loguer `systeme.v1` en
    envoyant `systeme.v3` — exactement la faute que l'empreinte de cassette existe
    pour rendre impossible, réintroduite un cran plus haut.
    """

    version: str
    texte: str
    empreinte: str


def prompt_systeme() -> SystemeEnVigueur:
    """Le prompt système en vigueur, et il le loggue.

    Rendre la version, le texte et l'empreinte ensemble plutôt que de laisser
    l'appelant les recomposer : c'est ce qui garantit que ce qui est logué, ce qui est
    écrit dans l'en-tête d'une cassette et ce qui est envoyé au modèle sont le même
    fichier.
    """
    version = version_systeme()
    texte = charger(version)
    signature = empreinte(texte)
    logueur.info("prompts.systeme", version=version, empreinte=signature, octets=len(texte))
    return SystemeEnVigueur(version=version, texte=texte, empreinte=signature)


class GriefMalForme(Exception):
    """`grief.v1.md` ne porte pas sa marque d'insertion. Non rattrapable au runtime."""


def prefixe_de_reprise() -> str:
    """Ce par quoi commence tout message de reprise : le gabarit **avant** sa marque.

    Dérivé du fichier, jamais recopié. `message_de_grief()` construit son texte en
    remplaçant `MARQUE_DES_GRIEFS` dans ce même gabarit : le préfixe est donc exact au
    caractère près, et il le reste si l'étape 13 réécrit le corps du message.

    ⚠️ **Il vivait dans `api/prose.py` jusqu'à l'étape 21, et il a trois lecteurs.**
    `prose.py` masque la reprise au rechargement ; `api/journal.py` s'en sert pour ne pas
    compter un grief comme un tour client ; et `validateur/contexte.py` en dépend depuis le
    jalon 2 pour une raison bien plus lourde — **exclure la reprise de la provenance
    « parole du client »**. Un message de reprise cite les extraits refusés : les admettre
    rendrait le validateur auto-annulant, mesuré à 18 griefs sur 19.

    Il remonte donc à côté du gabarit qu'il décode, plutôt que d'obliger le validateur à
    importer `raiyon.api`.
    """
    gabarit = charger(GRIEF_V1)
    return gabarit.split(MARQUE_DES_GRIEFS, 1)[0].strip()


def message_de_grief(lignes: Sequence[str]) -> str:
    """Le message de reprise, griefs insérés, et il loggue la version employée.

    Le texte part dans le **même bloc `user` que les `tool_result`**, après eux
    (arbitrage D de l'étape 9) : c'est ce qui rend la régénération possible même quand
    le message fautif portait aussi des `tool_use`, l'API exigeant les `tool_result`
    appairés avant tout autre contenu utilisateur.
    """
    gabarit = charger(GRIEF_V1)
    if MARQUE_DES_GRIEFS not in gabarit:
        raise GriefMalForme(
            f"{GRIEF_V1}.md ne contient pas {MARQUE_DES_GRIEFS!r} : la liste des griefs "
            "n'aurait nulle part où aller, et le modèle recevrait une reprise sans motif."
        )
    signature = empreinte(gabarit)
    logueur.info("prompts.grief", version=GRIEF_V1, empreinte=signature, griefs=len(lignes))
    return gabarit.replace(MARQUE_DES_GRIEFS, "\n".join(lignes))
