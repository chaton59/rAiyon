"""Joue un scénario contre `session.tour()`, et collecte ce que la boucle rend.

**C'est le troisième consommateur du générateur, pas une quatrième mécanique.** La console
(`scripts/console.py`) et le fil SSE (`raiyon.api.app`) le consomment déjà ; celui-ci fait
le même geste, avec la même contrainte non négociable :

> ⚠️ **`session.tour()` n'écrit qu'à la fin.** Un consommateur qui abandonne l'itération
> en cours de route n'a rien persisté — pas même le message du client. On consomme donc en
> entier, et la valeur de retour se récupère par `StopIteration.value`, jamais par une
> boucle `for` qui la jetterait.

Ce module a besoin de Postgres et du seed : c'est la conséquence assumée de l'arbitrage A
— les `tool_result` ne sont pas enregistrés, ils sont **recalculés** par le vrai moteur.
`make check` reste donc inchangé, et le rejeu vit dans `make eval`.

### Une session par prise, jamais réutilisée

Deux prises d'un même scénario doivent partir du même état vide. Réutiliser une session
ferait relire à la seconde l'historique de la première, et l'empreinte de requête de son
premier tour ne correspondrait à rien — la cassette échouerait en disant « divergence »
là où la faute serait ici.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.orm import Session

from raiyon.agent.client import ClientLLM
from raiyon.agent.evenements import Evenement
from raiyon.agent.session import creer_session, historique_de, tour
from raiyon.avis.fournisseur import Fournisseur
from raiyon.db.models import SessionConversation
from raiyon.eval.metriques import PriseJouee, TourJoue
from raiyon.eval.scenario import Scenario
from raiyon.matching.depot import DepotProduits
from raiyon.orchestration import Orchestrateur
from raiyon.orchestration.contrat import IssueDuTour

logueur = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Reglages:
    """Ce que la boucle attend, groupé. Les valeurs viennent de `Settings`, pas d'ici."""

    systeme: str
    outils: tuple[dict[str, Any], ...]
    max_iterations: int
    max_regenerations: int
    tolerance: Decimal | None = None

    fournisseur: Fournisseur | None = None
    """Le récupérateur d'avis web. `None` — **le défaut** — veut dire hors ligne.

    🔴 **C'est ce défaut qui garantit qu'une campagne ne sort jamais sur le réseau**, et il
    le garantit *par construction* plutôt que par une variable d'environnement. `jouer()`,
    `scripts/eval.py` et le rejeu de cassettes ne le renseignent nulle part : il n'existe
    donc aucun chemin de mesure qui puisse appeler Brave, même avec une clé en place.

    ⚠️ **La clé présente ne suffit pas ici, et c'est voulu.** Un mode en ligne qui
    s'activerait à la seule présence d'un secret ferait qu'installer une clé changerait
    silencieusement ce que `make eval` mesure. **Cette règle vise les chemins de mesure, et
    elle y est sans exception** : `jouer()`, `scripts/eval.py` et le rejeu de cassettes ne
    renseignent ce champ nulle part.

    Deux appelants construisent un fournisseur, et deux seulement — vérifié à l'étape 33 :
    `scripts/essais.py --en-ligne`, qui exige le drapeau **et** la clé, et `raiyon.api.app`,
    qui le construit au démarrage sur la présence de la clé parce qu'un serveur est le
    produit et non une mesure. ⚠️ **`scripts/console.py` n'en construit pas** — la console
    reste hors ligne."""

    orchestrateur: Orchestrateur | None = None
    """Qui conduit le tour. `None` = celle que la configuration désigne.

    ⚠️ **Elle voyage ici pour la même raison que `systeme`** : la comparaison rejoue deux
    jeux dans le **même processus**, et une variable d'environnement n'a qu'une valeur.
    `scripts/eval.py` la dérive de l'en-tête de chaque cassette — celle qui a enregistré la
    prise est celle qui doit la rejouer, et l'inverse produit une `DivergenceDeRequete` dès
    le premier tour."""


def jouer(
    base: Session,
    scenario: Scenario,
    prise: int,
    *,
    client: ClientLLM,
    depot: DepotProduits,
    reglages: Reglages,
) -> PriseJouee:
    """Joue les tours du scénario dans l'ordre et rend de quoi mesurer.

    L'historique **persisté** est relu en fin de parcours : c'est lui qui porte les
    `tool_result`, donc le contexte fourni dont le critère nº1 a besoin. Les événements
    ne le portent pas, et c'est voulu — aucun d'eux ne transporte d'état.
    """
    conversation = creer_session(base)
    base.commit()
    logueur.info(
        "eval.prise_ouverte",
        scenario=scenario.nom,
        prise=prise,
        session_id=str(conversation.id),
        tours=len(scenario.tours),
    )

    tours: list[TourJoue] = []
    for message_client in scenario.tours:
        evenements, issue = jouer_un_tour(
            base, conversation, message_client, client=client, depot=depot, reglages=reglages
        )
        # ⚠️ **L'historique est relu à chaque tour, et pas seulement à la fin** (étape 32).
        # La longueur seule est retenue : c'est la coupe qui situe le moment de la
        # livraison, et sans elle le critère nº1 relit du passé avec un contexte du futur.
        # Une requête de plus par tour, dans le harnais et nulle part ailleurs.
        tours.append(
            TourJoue(
                message_client,
                evenements,
                issue.iterations,
                messages_a_la_fin=len(historique_de(base, conversation.id)),
            )
        )

    return PriseJouee(
        scenario=scenario.nom,
        prise=prise,
        tours=tuple(tours),
        messages=tuple(historique_de(base, conversation.id)),
        session_id=conversation.id,
        attendu=None if scenario.attendu is None else scenario.attendu.produit_id,
        attentes=scenario.attentes,
        diagnostic_attendu=scenario.diagnostic_attendu,
        tours_de_domaine=scenario.tours_de_domaine,
    )


def jouer_un_tour(
    base: Session,
    conversation: SessionConversation,
    message_client: str,
    *,
    client: ClientLLM,
    depot: DepotProduits,
    reglages: Reglages,
) -> tuple[tuple[Evenement, ...], IssueDuTour]:
    """Consomme le générateur **en entier** et rend `(événements, issue)`.

    La boucle `while` explicite plutôt qu'un `for` : la valeur de retour du générateur
    n'est accessible que par `StopIteration.value`, et c'est elle qui porte le nombre
    d'itérations que le rapport publie. C'est la même mécanique que `_afficher()` dans la
    console, et pour la même raison.
    """
    generateur = tour(
        base,
        conversation,
        client=client,
        systeme=reglages.systeme,
        outils=reglages.outils,
        message_client=message_client,
        depot=depot,
        max_iterations=reglages.max_iterations,
        max_regenerations=reglages.max_regenerations,
        tolerance=reglages.tolerance,
        orchestrateur=reglages.orchestrateur,
        fournisseur=reglages.fournisseur,
    )
    evenements: list[Evenement] = []
    while True:
        try:
            evenements.append(next(generateur))
        except StopIteration as arret:
            issue: IssueDuTour = arret.value
            return tuple(evenements), issue
