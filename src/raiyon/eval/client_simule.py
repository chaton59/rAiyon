"""Le client joué par Haiku. **Cloisonné : il ne voit que ce qu'un client voit.**

### La cloison est l'arbitrage H, et c'est tout le sujet

Le client simulé reçoit **la prose livrée** — le `Texte` d'un message, la `question`
d'`ask_clarification`, le message d'un `Repli` — et les produits de `ProduitsTrouves`.

Il ne voit **jamais** les `tool_result`, ni l'`EtatSession`, ni les critères enregistrés,
ni un `TexteRejete`. Sans cette cloison il devient un **oracle** : il « sait » ce que
l'assistant a compris, et il répond à côté de ce qu'un vrai client aurait compris. La
mesure serait alors flatteuse et fausse.

C'est la même frontière que celle de `serialisation.py` — « ce qui prouve un invariant
sort ; ce qui explique un classement reste » —, resserrée d'un cran : ici, même ce qui
prouve un invariant ne sort pas. Un client ne lit pas les codes de grief du validateur.

### Ce qu'il mesure, et ce qu'il ne mesure pas

Rien. **Aucune cassette n'est enregistrée** à partir de ces conversations : elles ne sont
pas reproductibles par construction, puisque les deux côtés sont non déterministes. Elles
servent à *lire* un dialogue que dix scénarios scriptés ne produisent pas — un client qui
réagit à côté, qui insiste, qui change de sujet.

Les scénarios déterministes mesurent ; le client simulé montre. Confondre les deux
donnerait des scénarios fragiles (arbitrage G) et des métriques irreproductibles.

### Il vit dans `prompts/`, versionné comme les autres (§3.14)

`client_simule.v1.md` porte une marque `<!-- persona -->` : le persona est **injecté**,
le reste du prompt est stable. Un `{persona}` de `.format()` aurait obligé à échapper
toutes les accolades du fichier ; c'est la même convention que `grief.v1.md`.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

import anthropic
import structlog

from raiyon.agent.evenements import (
    Evenement,
    ProduitsTrouves,
    QuestionPosee,
    Repli,
    Texte,
)
from raiyon.agent.prompts import charger, empreinte
from raiyon.config import cle_api, get_settings

logueur = structlog.get_logger(__name__)

CLIENT_SIMULE_V1 = "client_simule.v1"
MARQUE_DU_PERSONA = "<!-- persona -->"
MOT_DE_FIN = "FIN"
MAX_TOKENS = 512
"""Un tour de client tient en deux phrases. Un plafond bas borne le coût et interdit au
persona de partir en dissertation, ce qui n'est pas un comportement de client."""


class PersonaMalForme(Exception):
    """`client_simule.v1.md` ne porte pas sa marque : le persona n'aurait nulle part où aller."""


@dataclass(frozen=True, slots=True)
class Persona:
    """Qui joue, et ce qu'il veut. **Aucune connaissance du catalogue.**"""

    nom: str
    description: str
    ouverture: str
    """Le premier message, écrit à la main : le modèle ne sait pas ouvrir une conversation
    sans avoir déjà quelque chose à quoi répondre."""


def prompt_du_persona(persona: Persona) -> str:
    """Le prompt versionné, persona injecté à sa marque."""
    gabarit = charger(CLIENT_SIMULE_V1)
    if MARQUE_DU_PERSONA not in gabarit:
        raise PersonaMalForme(
            f"{CLIENT_SIMULE_V1}.md ne contient pas {MARQUE_DU_PERSONA!r} : le persona "
            "n'aurait nulle part où aller, et le modèle jouerait un client générique."
        )
    return gabarit.replace(MARQUE_DU_PERSONA, persona.description)


def ce_que_le_client_voit(evenements: Sequence[Evenement]) -> str:
    """**La cloison, en une fonction.** Quatre événements sur huit passent, et pas un de plus.

    `CriteresMisAJour`, `Sondage`, `QuestionSuggeree` et `TexteRejete` restent dehors :
    ce sont la mécanique interne, et un client qui les lirait cesserait d'être un client.

    Les produits sont rendus comme le client les lit à l'écran — nom, identifiant, prix —
    et la zone de tolérance porte son écart, parce que c'est ce que §3.10 exige que le
    client voie.
    """
    morceaux: list[str] = []
    for evenement in evenements:
        if isinstance(evenement, Texte):
            morceaux.append(evenement.texte)
        elif isinstance(evenement, QuestionPosee):
            morceaux.append(evenement.question)
        elif isinstance(evenement, Repli):
            morceaux.append(evenement.message)
        elif isinstance(evenement, ProduitsTrouves):
            morceaux.extend(_produits(evenement))
    return "\n".join(morceaux).strip() or "(le vendeur n'a rien répondu)"


def _produits(evenement: ProduitsTrouves) -> list[str]:
    resultat = evenement.resultat
    lignes = [
        f"[{produit.nom} — {produit.id} — {produit.prix_usd} $]" for produit in resultat.produits
    ]
    lignes += [
        f"[{hors.produit.nom} — {hors.produit.id} — {hors.produit.prix_usd} $, "
        f"soit {hors.ecart_usd} $ au-dessus du budget]"
        for hors in resultat.au_dessus_du_budget
    ]
    return lignes


@dataclass
class ClientSimule:
    """Un client joué par Haiku. Il tient sa propre conversation, à l'envers de l'agent.

    Les rôles sont inversés : ce que l'assistant a dit arrive en `user`, ce que le client
    répond est un `assistant`. C'est ce qui permet d'utiliser un modèle de dialogue
    ordinaire sans lui expliquer qu'il doit jouer l'autre côté à chaque tour.
    """

    persona: Persona
    modele: str = ""
    messages: list[dict[str, object]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=cle_api())
        self._systeme = prompt_du_persona(self.persona)
        if not self.modele:
            self.modele = get_settings().model_eval_client
        logueur.info(
            "eval.client_simule",
            persona=self.persona.nom,
            modele=self.modele,
            version=CLIENT_SIMULE_V1,
            empreinte=empreinte(self._systeme),
        )

    def repondre_a(self, evenements: Sequence[Evenement]) -> str:
        """Le tour suivant du client, à partir de **ce qu'un client aurait lu**."""
        self.messages.append({"role": "user", "content": ce_que_le_client_voit(evenements)})
        message = self._client.messages.create(
            model=self.modele,
            max_tokens=MAX_TOKENS,
            system=self._systeme,
            messages=self.messages,  # type: ignore[arg-type]
        )
        texte = "\n".join(bloc.text for bloc in message.content if bloc.type == "text").strip()
        self.messages.append({"role": "assistant", "content": texte})
        return texte


def a_termine(message: str) -> bool:
    """`FIN` seul sur la dernière ligne. Une conversation qui ne finit pas coûte des jetons."""
    lignes = [ligne.strip() for ligne in message.strip().splitlines() if ligne.strip()]
    return bool(lignes) and lignes[-1] == MOT_DE_FIN


def sans_le_mot_de_fin(message: str) -> str:
    """Le message tel qu'il part à l'agent. `FIN` est un signal, pas une parole de client."""
    lignes = message.strip().splitlines()
    while lignes and lignes[-1].strip() in ("", MOT_DE_FIN):
        lignes.pop()
    return "\n".join(lignes).strip()


PERSONAS: tuple[Persona, ...] = (
    Persona(
        nom="joueur_serre",
        description=(
            "Vous avez 22 ans, vous jouez à des jeux de tir compétitifs, et votre budget "
            "est vraiment serré : 150 dollars, pas un de plus. Vous voulez un écran fluide "
            "et vous savez qu'il vous faut « beaucoup de Hz », sans savoir dire combien. "
            "Vous vous méfiez qu'on vous vende plus cher que ce que vous avez dit."
        ),
        ouverture="Bonjour, je cherche un écran pour jouer.",
    ),
    Persona(
        nom="bureautique_indecis",
        description=(
            "Vous travaillez à domicile, sur des tableurs et de la visio. Vous ne connaissez "
            "rien au matériel et vous n'avez pas de budget en tête : vous voulez d'abord "
            "comprendre ce qui compte. Vous posez beaucoup de questions et vous n'aimez pas "
            "qu'on vous en pose trois de suite sans rien vous proposer."
        ),
        ouverture="Bonjour, il me faudrait un écran correct pour télétravailler.",
    ),
    Persona(
        nom="exigeant_hors_perimetre",
        description=(
            "Vous montez une machine complète et vous voulez tout d'un coup : un écran, un "
            "processeur et une carte graphique, pour 900 dollars au total. Vous êtes pressé "
            "et vous insistez pour qu'on vous donne les trois tout de suite. Vous acceptez "
            "de faire un composant à la fois si on vous explique pourquoi."
        ),
        ouverture="Salut, il me faut un écran, un CPU et une carte graphique pour 900 balles.",
    ),
)
"""Trois personas, choisis pour ce que les scénarios scriptés **ne** produisent pas : un
client qui ne sait pas chiffrer son besoin, un client qui juge la conduite du dialogue, et
un client qui demande ce que §3.7 refuse de faire en un tour."""
