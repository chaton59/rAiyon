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

### Les deux tables d'observation entrent dans **ce** commit (étape 23)

`appels_modele` et `evenements_tour` sont écrites juste avant le `commit()`, avec les lignes
de conversation et l'état. Un seul commit par tour, donc l'atomicité de l'arbitrage 9 est
préservée telle quelle : **un tour est encore soit entièrement là, soit absent**, mesures
comprises. Un tableau de bord qui montrerait des appels sans les tours correspondants
décrirait une conversation qui n'a pas eu lieu.

⚠️ **Conséquence assumée : un tour qui plante n'écrit rien, pas même ses appels.** Les
jetons brûlés par les appels qui ont abouti avant l'erreur n'apparaissent donc dans aucune
table. C'est le journal JSONL qui couvre ce cas, ligne par ligne, à mesure — et c'est
précisément pourquoi il a été écrit avant celles-ci.

*Alternative écartée — un second commit pour l'observation, hors de l'atomicité.* Elle
sauverait les mesures d'un tour raté, et elle ouvrirait l'état que le §3.17 ferme : des
appels persistés pour un tour client qui n'existe pas, donc une jointure qui rend des
orphelins et un tableau de bord dont les totaux ne se recoupent pas avec la conversation.

⚠️ **`tour()` est un générateur : il n'écrit qu'à la fin.** Un appelant qui abandonne
l'itération en cours de route n'a rien persisté. La console le consomme entièrement, et
le générateur SSE de l'étape 10 aussi.

C'est de là que vient toute la sémantique d'erreur de l'API (étape 10, arbitrage I) : une
**déconnexion client** interrompt l'itération, donc le tour n'est pas persisté — pas même
le message du client — et l'appel API est payé et perdu. C'est exactement la sémantique
d'un redémarrage en milieu de tour, et c'est cohérent avec l'atomicité ci-dessus : « sans
rien perdre » signifie **« sans rien écrire de faux »**.
"""

import uuid
from collections.abc import Generator, Sequence
from decimal import Decimal
from typing import Any, cast

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from raiyon.agent.client import ClientLLM
from raiyon.agent.evenements import Evenement
from raiyon.avis.cache import DepotAvisSql, ttl_des_avis
from raiyon.avis.fournisseur import Fournisseur
from raiyon.db.models import (
    AppelModele,
    EvenementTour,
    SessionConversation,
    TourConversation,
)
from raiyon.matching.depot import DepotProduits
from raiyon.observation import ClientJournalisant, evenement_journalise
from raiyon.orchestration import Orchestrateur, repondre_en_vigueur
from raiyon.orchestration.contrat import ROLE_CLIENT, IssueDuTour
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
    max_regenerations: int,
    tolerance: Decimal | None = None,
    orchestrateur: Orchestrateur | None = None,
    fournisseur: Fournisseur | None = None,
) -> Generator[Evenement, None, IssueDuTour]:
    """Un tour client complet : relire, tourner, écrire, commit. **À consommer en entier.**

    `orchestrateur` **par valeur**, exactement comme `systeme` : `None` veut dire « celle
    que la configuration désigne », et la passer sert à ce que l'environnement ne peut pas
    faire — conduire **deux orchestrations dans un même processus**.

    ⚠️ C'est ce dont `make eval-comparer` a besoin, et le besoin est le même que pour le
    prompt : la comparaison rejoue deux jeux dans le même processus, et une variable
    d'environnement n'a qu'une valeur. Sans ce paramètre, les cassettes de la machine se
    rejouaient dans la boucle d'agent et divergeaient au premier tour — constaté à l'étape
    15, jalon 5.
    """
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

    # ⚠️ **L'enveloppe d'observation est posée ici, pas par l'appelant** (étape 23). Une
    # instance par tour : `iteration` repart donc de 1 sans compteur à remettre à zéro, et
    # il n'existe aucun chemin qui persiste un tour sans le compter. Le client reçu — réel,
    # faux, de cassette, ou déjà enveloppé par `ClientEnregistreur` — traverse inchangé.
    journalisant = ClientJournalisant(reel=client)

    # ⚠️ **Le seul point de bascule entre les deux orchestrations** (étape 15, jalon 2).
    # `session.tour()` ne connaît aucune des deux : il connaît la signature que le
    # `Protocol` `Orchestrateur` porte, et c'est mypy qui vérifie que la substitution en
    # est une.
    #
    # L'observation ne change rien à cette bascule : les deux orchestrations reçoivent un
    # `ClientLLM`, et aucune des deux ne peut distinguer le décorateur d'un client nu.
    evenements: list[Evenement] = []
    issue = yield from _en_notant(
        (orchestrateur or repondre_en_vigueur())(
            client=journalisant,
            systeme=systeme,
            outils=outils,
            historique=historique,
            message_client=message_client,
            etat=etat,
            contexte=ContexteOutils(
                depot=depot,
                tour_client=numero,
                tolerance=tolerance,
                # ⚠️ **Le cache d'avis vit dans la session SQLAlchemy du tour** : ses
                # écritures héritent donc de l'atomicité de l'arbitrage 9, comme les
                # lignes de conversation et les tables d'observation. Un tour qui plante
                # ne laisse pas un cache à moitié rempli.
                depot_avis=DepotAvisSql(session, ttl=ttl_des_avis()),
                # ⚠️ **`None` par défaut : hors ligne** (§3.18). Le fournisseur est
                # **injecté**, jamais construit ici : c'est ce qui fait qu'une campagne ne
                # peut pas sortir sur le réseau, même avec une clé en place. Seul un
                # appelant qui en construit un explicitement — `--en-ligne`, la console,
                # l'API — ouvre ce chemin.
                fournisseur=fournisseur,
            ),
            max_iterations=max_iterations,
            max_regenerations=max_regenerations,
        ),
        evenements,
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

    appels = journalisant.drainer()
    for appel in appels:
        session.add(
            AppelModele(
                session_id=identifiant,
                tour_client=numero,
                iteration=appel.iteration,
                modele=appel.modele,
                empreinte_systeme=appel.empreinte_systeme,
                effort=appel.effort,
                display=appel.display,
                stop_reason=appel.stop_reason,
                jetons_entree=appel.jetons_entree,
                jetons_sortie=appel.jetons_sortie,
                cache_ecrit=appel.cache_ecrit,
                cache_lu=appel.cache_lu,
                latence_ms=appel.latence_ms,
            )
        )

    # `rang` est compté ici, à partir de 1, et **pas** déduit de l'horodatage : deux
    # événements d'un même message d'outils tombent dans la même milliseconde.
    for rang, evenement in enumerate(evenements, start=1):
        genre, charge = evenement_journalise(evenement)
        session.add(
            EvenementTour(
                session_id=identifiant,
                tour_client=numero,
                rang=rang,
                genre=genre,
                charge=charge,
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
        appels=len(appels),
        evenements=len(evenements),
        jetons_sortie=sum(appel.jetons_sortie for appel in appels),
    )
    return issue


def _en_notant(
    source: Generator[Evenement, None, IssueDuTour], recueil: list[Evenement]
) -> Generator[Evenement, None, IssueDuTour]:
    """Relaie les événements de l'orchestration **et en garde une copie**, dans l'ordre.

    ⚠️ **Un relais, pas une consommation.** `tour()` est un générateur dont l'appelant
    décide du rythme ; accumuler en consommant tout d'abord détruirait le direct — le fil
    SSE n'enverrait plus rien avant la fin du tour, ce qui est exactement l'inverse de ce
    que §3.12 promet. Chaque événement est donc rendu à l'appelant à l'instant où il sort.

    ⚠️ **Et c'est ce qui fait que l'observation hérite de l'atomicité du tour.** Un appelant
    qui abandonne l'itération n'atteint pas le `commit()`, donc n'écrit ni conversation ni
    événements : la liste accumulée meurt avec le générateur. C'est la même sémantique que
    pour `tours_conversation`, et il n'y a rien de plus à faire pour l'obtenir.

    *Alternative écartée — accumuler dans la boucle d'émission de chaque appelant.* Trois
    appelants (console, fil SSE, exécuteur d'éval), donc trois occasions d'oublier, et une
    session sans mesure qui ne se remarquerait qu'au tableau de bord.
    """
    while True:
        try:
            evenement = next(source)
        except StopIteration as fin:
            return cast(IssueDuTour, fin.value)
        recueil.append(evenement)
        yield evenement
