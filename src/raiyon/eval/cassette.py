"""Le format de cassette : un en-tête qui la périme, et des prises ordonnées. **Pur.**

Ce module n'importe ni `anthropic`, ni `fastapi`, ni SQLAlchemy — il ne connaît que du
JSON, `raiyon.agent.client` pour la forme d'une réponse, et `raiyon.agent.prompts` pour
l'empreinte. C'est le seul module du harnais dont on puisse dire cela sans réserve, et
c'est ce qui rend le format lisible et modifiable sans rien démarrer.

---

### Une cassette n'enregistre que les réponses du modèle (arbitrage A)

**Rien d'autre.** Pas de `tool_result`, pas d'état, pas de produits. Ils sont
**recalculés** à chaque rejeu par le vrai moteur, la vraie couche outils et le vrai
validateur, sur le seed committé.

C'est ce qui fait que l'éval mesure la **pile entière** : un changement de scoring, une
borne recalibrée, une règle du validateur qui se resserre se voient dans les métriques au
rejeu suivant, sans rien réenregistrer.

*Alternative écartée — enregistrer aussi les `tool_result`.* Le rejeu serait entièrement
hors ligne, donc intégrable à `make check`. Écartée parce qu'elle **fige le moteur** : un
scoring cassé rejouerait ses anciens résultats et la suite resterait verte. On testerait
la conduite du dialogue contre un passé figé, pas le produit.

**Conséquence assumée** : le rejeu exige Postgres et le seed. `make check` reste inchangé.

### Rejeu par index, avec assertion d'empreinte (arbitrage B)

La cassette est une **liste ordonnée** de prises ; le rejeu rend la n-ième, comme le
`FauxClient` de l'étape 8. Mais chaque prise porte l'**empreinte de la requête** qui l'a
produite — système + outils + messages, sérialisés de façon stable — et le rejeu vérifie
qu'elle correspond à celle qu'il reçoit.

*Alternative écartée — un dictionnaire indexé par empreinte.* Robuste à un
réordonnancement, mais le message d'échec parlerait d'un hash absent au lieu d'un tour, et
une cassette lue hors ordre ne se relit pas à la main.

*Alternative écartée — l'index seul*, comme `FauxClient`. Une divergence **désynchronise
en silence** : le modèle reçoit la réponse du tour suivant, la conversation part ailleurs,
et les métriques décrivent une conversation qui n'a jamais eu lieu. C'est le mode d'échec
le plus coûteux d'un harnais d'éval, **parce qu'il produit des chiffres au lieu d'une
erreur**.

C'est pour cela que chaque prise porte aussi un `apercu` : une ligne par message, rôle et
extrait. Il ne sert à aucun calcul — il sert au `diff` du jour où la conversation diverge,
et à la relecture à la main d'un fichier de deux cents lignes.

### La cassette porte les empreintes qui la périment (arbitrage C)

Trois, et la deuxième est celle que la formulation « hash du prompt » du §5 laissait
échapper :

* l'empreinte du **prompt système**, avec sa version ;
* l'empreinte du **schéma d'outils** — il fait partie du préfixe mis en cache (§3.13) et
  détermine ce que le modèle peut faire ; un outil dont la description change rend la
  cassette aussi périmée qu'un prompt modifié ;
* le **modèle**, et la date d'enregistrement.

Au rejeu, une empreinte qui ne correspond plus **échoue en disant de régénérer**, avec la
commande à taper. §3.15 annonçait une « discipline à tenir » ; ici, ce n'est plus une
discipline — c'est une erreur.

### L'écriture refuse ce qu'elle ne saurait pas relire à l'identique

`ReponseLLM.blocs` sort de `model_dump(mode="json")` : du JSON natif, sans exception. Un
`Decimal` qui arriverait là serait donc le signe qu'un autre chemin a écrit dans les blocs
— et l'écrire en chaîne le relirait en chaîne, c'est-à-dire **silencieusement de travers**
dans un fichier dont toute la valeur est d'être fidèle. `ValeurNonSerialisable` le dit et
nomme la valeur.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from raiyon.agent.client import ReponseLLM
from raiyon.agent.prompts import empreinte

FORMAT = 1
"""Version du format de fichier. Une cassette d'un autre format est refusée, pas devinée."""

EXTRAIT = 80
"""Longueur d'un extrait dans l'aperçu. Assez pour reconnaître un message, assez peu pour
qu'une cassette de dix tours tienne à l'écran."""

COMMANDE_DE_REGENERATION = (
    "RAIYON_PROMPT_SYSTEME={version} make eval-enregistrer SCENARIO={scenario}"
)
"""La commande à taper. Écrite ici parce que c'est ici qu'on lève l'erreur qui l'exige.

⚠️ **La version y est depuis l'étape 13**, et sans elle le message serait un piège : trois
prompts coexistent désormais, `make eval-enregistrer` seul régénérerait contre la version
par défaut, et la cassette repartirait dans le mauvais jeu. Le message dit donc la commande
**complète**, celle qui régénère ce qu'on est en train de lire."""


class CassetteInvalide(Exception):
    """Le fichier n'est pas une cassette lisible : format inconnu, champ absent."""


class ValeurNonSerialisable(Exception):
    """Un bloc porte une valeur que le JSON ne relirait pas à l'identique."""


class CassettePerimee(Exception):
    """Une empreinte de l'en-tête ne correspond plus. **Régénérer, pas contourner.**"""


class DivergenceDeRequete(Exception):
    """La requête reçue au tour n n'est pas celle qui a produit la prise n."""


class CassetteEpuisee(Exception):
    """La boucle demande une prise de plus que la cassette n'en porte."""


@dataclass(frozen=True, slots=True)
class EnTete:
    """Ce qui périme une cassette, et ce qui l'identifie."""

    scenario: str
    prise: int
    """1, 2 ou 3. Trois prises sur trois scénarios (arbitrage D) — une ailleurs."""

    modele: str
    prompt_version: str
    prompt_empreinte: str
    outils_empreinte: str
    enregistree_le: str
    """Date ISO, sans heure. Elle situe l'enregistrement ; elle ne sert à aucun contrôle."""


@dataclass(frozen=True, slots=True)
class Prise:
    """Une réponse du modèle, et l'empreinte de la requête qui l'a produite."""

    requete: str
    """Empreinte de `systeme` + `outils` + `messages`. Le contrôle de l'arbitrage B."""

    apercu: tuple[str, ...]
    """Une ligne par message. Ne sert à aucun calcul — sert au `diff` d'une divergence."""

    blocs: list[dict[str, Any]]
    fin: str

    def en_reponse(self) -> ReponseLLM:
        return ReponseLLM(blocs=[dict(bloc) for bloc in self.blocs], fin=self.fin)


@dataclass(frozen=True, slots=True)
class Cassette:
    """Un en-tête, des prises ordonnées. Rien d'autre — surtout pas de `tool_result`."""

    entete: EnTete
    prises: tuple[Prise, ...]


# --------------------------------------------------------------------------- #
# Empreintes — la même fonction que les prompts, sur une sérialisation stable
# --------------------------------------------------------------------------- #


def _refuser(valeur: object) -> Any:  # noqa: ANN401
    """Le `default` de `json.dumps`. Il ne convertit rien : il nomme ce qu'il refuse."""
    raise ValeurNonSerialisable(
        f"{type(valeur).__name__} ({valeur!r}) n'est pas du JSON natif. Une cassette "
        "n'écrit que ce qu'elle relirait à l'identique — convertir ici relirait la "
        "valeur de travers, en silence, dans le seul fichier dont la fidélité fait "
        "toute la valeur."
    )


def canonique(objet: object) -> str:
    """La sérialisation stable : clés triées, sans espace, sans échappement d'accents.

    `sort_keys` est ce qui rend l'empreinte insensible à l'ordre des clés d'un
    dictionnaire, que ni le SDK ni `json` ne garantissent d'une version à l'autre.
    """
    return json.dumps(
        objet, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_refuser
    )


def empreinte_de_requete(
    *,
    systeme: str,
    outils: Sequence[Mapping[str, Any]],
    messages: Sequence[Mapping[str, Any]],
) -> str:
    """L'empreinte des trois choses qui décident de ce que le modèle va répondre.

    Les messages en font partie : c'est ce qui distingue le tour 3 du tour 4, et donc ce
    qui transforme une désynchronisation silencieuse en erreur nommée.
    """
    return empreinte(
        canonique({"systeme": systeme, "outils": list(outils), "messages": list(messages)})
    )


def empreinte_des_outils(outils: Sequence[Mapping[str, Any]]) -> str:
    """L'empreinte du schéma d'outils seul — celle qui périme la cassette (arbitrage C).

    Elle est distincte de celle de la requête : le schéma ne change qu'entre deux
    versions du code, alors que les messages changent à chaque tour.
    """
    return empreinte(canonique(list(outils)))


def apercu_de_requete(messages: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Une ligne par message : son rang, son rôle, ses types de blocs, un extrait.

    Lisible à l'œil et comparable par `difflib`. C'est tout ce qu'on lui demande.
    """
    return tuple(
        f"{rang:>2} {message.get('role', '?')} {_resume_des_blocs(message.get('content'))}"
        for rang, message in enumerate(messages, start=1)
    )


def _resume_des_blocs(contenu: object) -> str:
    if isinstance(contenu, str):
        return f"text «{_extrait(contenu)}»"
    if not isinstance(contenu, list):
        return f"?{type(contenu).__name__}"
    return " | ".join(_resume_du_bloc(bloc) for bloc in contenu)


def _resume_du_bloc(bloc: object) -> str:
    if not isinstance(bloc, Mapping):
        return f"?{type(bloc).__name__}"
    genre = str(bloc.get("type", "?"))
    if genre == "text":
        return f"text «{_extrait(str(bloc.get('text', '')))}»"
    if genre == "tool_use":
        return f"tool_use {bloc.get('name')} {_extrait(canonique(bloc.get('input') or {}))}"
    if genre == "tool_result":
        marque = "ERREUR " if bloc.get("is_error") else ""
        return f"tool_result {marque}«{_extrait(str(bloc.get('content', '')))}»"
    return genre


def _extrait(texte: str) -> str:
    """Un extrait sur une seule ligne — l'aperçu est un format ligne à ligne."""
    plat = " ".join(texte.split())
    return plat if len(plat) <= EXTRAIT else plat[:EXTRAIT] + "…"


# --------------------------------------------------------------------------- #
# Lecture et écriture — un aller-retour, et il est testé
# --------------------------------------------------------------------------- #


def en_json(cassette: Cassette) -> str:
    """Le texte du fichier. Indenté et terminé par un saut de ligne : il est committé.

    `sort_keys` n'est **pas** appliqué ici, contrairement à `canonique()` : le fichier se
    lit à la main, et l'ordre de déclaration des champs y est plus utile que l'ordre
    alphabétique. La stabilité du diff vient de la construction, pas du tri.
    """
    charge = {
        "format": FORMAT,
        "entete": {
            "scenario": cassette.entete.scenario,
            "prise": cassette.entete.prise,
            "modele": cassette.entete.modele,
            "prompt_version": cassette.entete.prompt_version,
            "prompt_empreinte": cassette.entete.prompt_empreinte,
            "outils_empreinte": cassette.entete.outils_empreinte,
            "enregistree_le": cassette.entete.enregistree_le,
        },
        "prises": [
            {
                "requete": prise.requete,
                "apercu": list(prise.apercu),
                "fin": prise.fin,
                "blocs": prise.blocs,
            }
            for prise in cassette.prises
        ],
    }
    return json.dumps(charge, indent=2, ensure_ascii=False, default=_refuser) + "\n"


def depuis_json(texte: str) -> Cassette:
    """Relit une cassette. Un champ absent lève `CassetteInvalide` en le nommant."""
    try:
        charge = json.loads(texte)
    except json.JSONDecodeError as erreur:
        raise CassetteInvalide(f"JSON illisible : {erreur}") from erreur
    if not isinstance(charge, dict):
        raise CassetteInvalide("la racine d'une cassette est un objet.")
    if charge.get("format") != FORMAT:
        raise CassetteInvalide(
            f"format {charge.get('format')!r}, attendu {FORMAT}. Régénérer la cassette."
        )
    return Cassette(entete=_entete(charge.get("entete")), prises=_prises(charge.get("prises")))


def _entete(brut: object) -> EnTete:
    if not isinstance(brut, dict):
        raise CassetteInvalide("`entete` absent ou mal formé.")
    manquants = sorted(
        champ
        for champ in (
            "scenario",
            "prise",
            "modele",
            "prompt_version",
            "prompt_empreinte",
            "outils_empreinte",
            "enregistree_le",
        )
        if champ not in brut
    )
    if manquants:
        raise CassetteInvalide(f"`entete` incomplet — champs absents : {', '.join(manquants)}.")
    return EnTete(
        scenario=str(brut["scenario"]),
        prise=int(brut["prise"]),
        modele=str(brut["modele"]),
        prompt_version=str(brut["prompt_version"]),
        prompt_empreinte=str(brut["prompt_empreinte"]),
        outils_empreinte=str(brut["outils_empreinte"]),
        enregistree_le=str(brut["enregistree_le"]),
    )


def _prises(brut: object) -> tuple[Prise, ...]:
    if not isinstance(brut, list):
        raise CassetteInvalide("`prises` absent ou n'est pas une liste.")
    prises: list[Prise] = []
    for rang, element in enumerate(brut, start=1):
        if not isinstance(element, dict):
            raise CassetteInvalide(f"la prise {rang} n'est pas un objet.")
        if "requete" not in element or "blocs" not in element:
            raise CassetteInvalide(f"la prise {rang} n'a pas de `requete` ou pas de `blocs`.")
        prises.append(
            Prise(
                requete=str(element["requete"]),
                apercu=tuple(str(ligne) for ligne in element.get("apercu", ())),
                blocs=list(element["blocs"]),
                fin=str(element.get("fin", "end_turn")),
            )
        )
    return tuple(prises)
