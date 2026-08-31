"""Lecture et écriture des sessions et des tours. L'aller-retour réel du JSONB.

### Persister dès l'étape 8, et l'arbitrage se tranche seul (arbitrage 9)

L'argument « garder la console utilisable sans conteneur » est **faux**, et il faut le
dire plutôt que de le laisser peser : la console a de toute façon besoin de Postgres,
puisque `search_products` interroge le dépôt. Il n'y a donc rien à gagner à différer.

Ce qu'on gagne à le faire maintenant : `en_jsonb()` et `depuis_jsonb()` sont exercés sur
un aller-retour réel, à l'étape où le reste est simple. Différer, c'est laisser l'étape 10
découvrir un défaut de sérialisation avec le streaming par-dessus.

### `tour_client` est le `numero` de la ligne du message client

Un entier croissant, unique par session, **stable au redémarrage**, jamais réutilisé —
tout ce dont le jeton de parole (§3.17) a besoin.

⚠️ **Ne pas compter les lignes de rôle `user` :** les `tool_result` en portent aussi (il
n'existe pas de rôle « outil » dans l'API), et le compte serait faux dès le premier appel
d'outil. Le numéro est donc pris sur `max(numero) + 1`.

⚠️ **Et surtout pas un compteur en mémoire.** `tour_du_dernier_desserrage` est persisté
par `en_jsonb()` ; un numéro de tour qui repartirait de zéro au redémarrage rendrait le
jeton de parole contournable en relançant la console — le tour 1 étant toujours plus
petit que le tour du dernier desserrage, ou égal à lui.

### Un seul commit, en fin de tour

L'ordre est : lire la session, reconstruire l'état et l'historique, poser la ligne du
message client, tourner la boucle, écrire ce qu'elle a produit, écrire l'état, commit.

Un tour est ainsi **atomique** : si l'API échoue au milieu, rien n'est écrit — pas même
le message du client. C'est le bon comportement, parce qu'un message client persisté sans
la réponse qui va avec produirait, au tour suivant, un historique se terminant par un
message `user` sans réponse ; l'API l'accepte, mais la conversation relue ne serait pas
celle qui a eu lieu.

⚠️ **`tour()` est un générateur : il n'écrit qu'à la fin.** Un appelant qui abandonne
l'itération en cours de route n'a rien persisté. La console le consomme entièrement.
"""

import uuid
from collections.abc import Generator, Sequence
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from raiyon.agent.boucle import ROLE_CLIENT, IssueDuTour, repondre
from raiyon.agent.client import ClientLLM
from raiyon.agent.evenements import Evenement
from raiyon.db.models import SessionConversation, TourConversation
from raiyon.matching.depot import DepotProduits
from raiyon.tools.etat import EtatSession, depuis_jsonb
from raiyon.tools.repartiteur import ContexteOutils

logueur = structlog.get_logger(__name__)


def creer_session(session: Session) -> SessionConversation:
    """Ouvre une conversation vide et rend la ligne, identifiant compris.

    L'UUID est généré côté application (`uuid4`) : l'API de l'étape 10 doit le connaître
    avant le premier flush pour l'émettre dans le flux SSE, et la console l'affiche au
    démarrage pour qu'on puisse y revenir.
    """
    conversation = SessionConversation(id=uuid.uuid4(), criteres_valides={}, statut="en_cours")
    session.add(conversation)
    session.flush()
    logueur.info("session.creee", session_id=str(conversation.id))
    return conversation


def lire_session(session: Session, identifiant: uuid.UUID) -> SessionConversation:
    """La ligne de session, ou une `SessionIntrouvable` qui nomme l'identifiant."""
    conversation = session.get(SessionConversation, identifiant)
    if conversation is None:
        raise SessionIntrouvable(f"aucune session {identifiant} — vérifier l'identifiant.")
    return conversation


class SessionIntrouvable(Exception):
    """L'identifiant de session donné ne correspond à aucune ligne."""


def etat_de(conversation: SessionConversation) -> EtatSession:
    """Reconstruit l'état, **revalidé** au passage par `depuis_jsonb()`.

    Le budget arrive par son propre argument parce qu'il vient de sa propre colonne
    (§3.10) : le laisser entrer par le JSONB ouvrirait la seconde copie que le schéma
    ferme.
    """
    return depuis_jsonb(conversation.criteres_valides, budget_usd=conversation.budget_usd)


def historique_de(session: Session, identifiant: uuid.UUID) -> list[dict[str, Any]]:
    """La conversation, dans l'ordre des numéros, en messages prêts pour l'API.

    Les blocs sont relus **bruts** : c'est la raison d'être de la colonne. Aplatir en
    texte détruirait les `tool_use` et les `tool_result`, donc l'appairage que l'API
    exige et le contexte dont le validateur de l'étape 9 a besoin.
    """
    lignes = session.scalars(
        select(TourConversation)
        .where(TourConversation.session_id == identifiant)
        .order_by(TourConversation.numero)
    ).all()
    return [{"role": ligne.role, "content": ligne.blocs} for ligne in lignes]


def prochain_numero(session: Session, identifiant: uuid.UUID) -> int:
    """`max(numero) + 1`, et **pas** un compte de lignes `user` — voir la docstring."""
    dernier = session.scalar(
        select(func.max(TourConversation.numero)).where(TourConversation.session_id == identifiant)
    )
    return 1 if dernier is None else int(dernier) + 1


def tour(
    session: Session,
    conversation: SessionConversation,
    *,
    client: ClientLLM,
    systeme: str,
    outils: Sequence[dict[str, Any]],
    message_client: str,
    depot: DepotProduits,
    max_iterations: int,
    tolerance: Decimal | None = None,
) -> Generator[Evenement, None, IssueDuTour]:
    """Un tour client complet : relire, tourner, écrire, commit. **À consommer en entier.**"""
    identifiant = conversation.id
    etat = etat_de(conversation)
    historique = historique_de(session, identifiant)
    numero = prochain_numero(session, identifiant)

    # La ligne du message client est posée **avant** la boucle : son `numero` est le
    # `tour_client` que le jeton de parole consomme (arbitrage 9).
    session.add(
        TourConversation(
            session_id=identifiant,
            numero=numero,
            role=ROLE_CLIENT,
            blocs=[{"type": "text", "text": message_client}],
        )
    )
    logueur.info("session.tour_client", session_id=str(identifiant), numero=numero)

    issue = yield from repondre(
        client=client,
        systeme=systeme,
        outils=outils,
        historique=historique,
        message_client=message_client,
        etat=etat,
        contexte=ContexteOutils(depot=depot, tour_client=numero, tolerance=tolerance),
        max_iterations=max_iterations,
    )

    for decalage, produit in enumerate(issue.tours, start=1):
        session.add(
            TourConversation(
                session_id=identifiant,
                numero=numero + decalage,
                role=produit.role,
                blocs=produit.blocs,
            )
        )

    conversation.criteres_valides = issue.etat.en_jsonb()
    conversation.budget_usd = issue.etat.budget_usd
    session.commit()
    logueur.info(
        "session.tour_ecrit",
        session_id=str(identifiant),
        tour_client=numero,
        lignes_ecrites=1 + len(issue.tours),
        iterations=issue.iterations,
    )
    return issue
