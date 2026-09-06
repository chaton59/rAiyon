"""L'application FastAPI : cinq routes, un générateur SSE, **et pas une ligne de boucle**.

L'API est un **second consommateur** d'événements, pas une réécriture. `scripts/console.py`
est son jumeau : il consomme le même générateur, il dérive le même français du même
registre, et il n'écrit rien non plus tant que le tour n'est pas fini.

---

### A. Pile synchrone de bout en bout

Le générateur passé à `StreamingResponse` est **synchrone** ; Starlette l'enveloppe dans
`iterate_in_threadpool`. Toute la pile métier reste donc synchrone, ce qui est la
condition du critère d'acceptation nº5 — « le moteur de matching est testable sans API ».

*Alternative écartée — un engine asyncio.* Il imposerait `async def` jusque dans
`tests/matching/`, donc ferait tomber le critère nº5. Non négociable.

⚠️ **Précision qui compte, et qui a failli être mal comprise : ce n'est pas l'endpoint qui
doit être `def`.** Un endpoint `async def` rendant un `StreamingResponse` construit sur un
générateur sync fonctionne parfaitement — le tour n'a pas lieu dans le corps de
l'endpoint, mais après son retour.

Les endpoints d'ici sont pourtant tous `def`, **pour une autre raison** : ils font eux-
mêmes du SQL bloquant avant de rendre (le 404, le verrou, la relecture, le `SELECT 1`).
En `async def`, ces requêtes-là bloqueraient la boucle d'événements. FastAPI exécute un
endpoint `def` dans le threadpool, ce qui règle la question sans rien changer au reste.

### C. Aucun heartbeat, et c'est assumé

Un générateur synchrone bloqué dans `messages.create()` ne peut **rien** intercaler : ni
`: ping`, ni détection de déconnexion. On ne fait donc rien.

Le silence réel est celui d'un tour sans appel d'outil : les événements d'outils arrivent
au fil de l'eau et tiennent la connexion vivante le reste du temps. En démo locale et en
`curl`, aucun effet.

**Condition de bascule, écrite maintenant pour ne pas être découverte plus tard :** le
jour où ce serveur passe derrière un proxy qui coupe à 60 s d'inactivité, la parade est un
endpoint `async` drainant le générateur sync par une `queue.Queue` — une quarantaine de
lignes de plomberie thread↔asyncio. Tant qu'aucun proxy n'est en jeu, ces lignes ne
protègent de rien.

### E. Avant le premier octet, un code HTTP ; après, un événement typé

C'est la ligne de partage de toute la gestion d'erreur, et elle explique la forme du code
ci-dessous.

**Avant** — session inconnue → `404`. Corps invalide → `422` (Pydantic). Verrou déjà pris
→ `409`. Ces trois cas sont décidés dans le corps de l'endpoint, donc avant que
`StreamingResponse` n'ait écrit quoi que ce soit.

⚠️ **Le 409 sort à plat, comme l'événement `error`** : `{"code", "message"}`, et non le
`{"detail": {...}}` qu'`HTTPException` produit seul. `ErreurDeLApi` et son gestionnaire
existent pour cela et pour rien d'autre — sans eux, le front porterait deux lecteurs
d'erreur pour un vocabulaire unique. Le 404 et le 422 gardent leur forme FastAPI : ils ne
portent pas de `CodeErreur`.

**Après** — il n'existe plus de code HTTP à changer. Toute exception devient un événement
`error`, suivi de la fermeture du flux.

⚠️ **Le message d'un `error` est écrit pour le client, en français, et ne contient jamais
le `str()` de l'exception.** Une trace SQLAlchemy sur une page web est une fuite. Le détail
part en `logueur.exception`, avec l'identifiant de session.

### I. Une déconnexion tue le tour, exactement comme un redémarrage

Sur une déconnexion, Starlette cesse d'itérer et le générateur reçoit un `GeneratorExit`
au `yield` en cours. `session.tour()` n'atteint donc jamais son `commit()` : **rien n'est
persisté, pas même le message du client**, et l'appel API à Anthropic est payé et perdu.

On ne cherche pas à l'éviter — l'éviter demanderait le drainage par file d'attente que
l'arbitrage C écarte. On le rend **propre** : le `finally` fait `rollback()` puis
`close()`, sans quoi la connexion revient au pool en transaction avortée et fait échouer
la requête suivante avec une erreur qui ne désigne pas la vraie cause.

C'est la même sémantique qu'un redémarrage en milieu de tour, et c'est cohérent :
l'atomicité de `session.py` dit que « sans rien perdre » signifie **« sans rien écrire de
faux »**. Un tour est entier, ou il n'a pas eu lieu.

### L. Le front est servi par le même processus

`StaticFiles` monté sur `/`. Un processus, une commande, **pas de CORS à configurer**, pas
de second serveur de développement à lancer pour la porte de sortie de l'étape 11.

⚠️ **Le montage `/` vient après les routes**, sinon il les avale.

---

### Les quatre pièges de l'étape, et où ils sont traités

1. **La `Session` SQLAlchemy ne vient pas d'un `Depends` avec `yield`.** Le générateur
   s'exécute **après** que l'endpoint a rendu : une session à portée de requête serait
   fermée, ou en cours de fermeture, quand la boucle tourne. Le symptôme est un
   `DetachedInstanceError` au troisième tour, pas au premier. Elle est donc ouverte à la
   main dans l'endpoint et **fermée par le générateur**, qui en devient propriétaire.

   Corollaire : le 404 et le 409 se décident sur cette même session, avant le flux — et
   surtout **sans commit**. Un verrou pris puis relâché par le commit d'une vérification
   ne verrouillerait rien.

2. **Le générateur se consomme en entier, ou il ne persiste rien.** Même règle que la
   console : la boucle d'émission est un `for` ordinaire, sans `break` ni `return`
   conditionnel. Le `for` épuise le générateur, donc `tour()` atteint son `commit()`.

3. **Le `finally` est obligatoire** — `rollback()` puis `close()`. Voir l'arbitrage I.

4. **Le client, le prompt et le schéma d'outils sont construits une fois, au démarrage**,
   et partagés. `ClientAnthropic` **mémorise son mode `strict`** sur l'instance, mesuré au
   premier appel (arbitrage 11 de l'étape 8) : une instance par requête reperdrait cette
   mesure et paierait un aller-retour de plus à chaque premier échec. Si `cle_api()` lève,
   **le processus refuse de démarrer** — c'est le « échouer tôt sur ce qui est réellement
   requis » de §3.13, et pour un serveur le premier moment réel est le démarrage.
"""

import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, cast

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from raiyon.agent.client import ClientLLM
from raiyon.agent.client_anthropic import ClientAnthropic
from raiyon.agent.prompts import SystemeEnVigueur, prompt_systeme
from raiyon.agent.session import (
    SessionIntrouvable,
    creer_session,
    etat_de,
    historique_de,
    lire_session,
    tour,
)
from raiyon.api import journal
from raiyon.api.prose import prose_de
from raiyon.api.schemas import (
    ErreurExposee,
    EtatExpose,
    MessageEntrant,
    ParoleExposee,
    PromptExpose,
    Sante,
    SessionCreee,
    SessionExposee,
)
from raiyon.api.serialisation import (
    CodeErreur,
    charge_derreur,
    criteres_serialises,
    optimisation_serialisee,
    trame_de,
    trame_de_fin,
    trame_derreur,
)
from raiyon.api.verrou import verrouiller_le_tour
from raiyon.catalogue.schemas import LIBELLES_CATEGORIE
from raiyon.config import ConfigurationError, Settings, get_settings
from raiyon.db.engine import get_sessionmaker
from raiyon.journal import configurer_journal
from raiyon.matching.depot import DepotSql
from raiyon.tools.schema_outils import schema_des_outils

logueur = structlog.get_logger(__name__)

REPERTOIRE_WEB = Path(__file__).resolve().parents[3] / "web"
"""`src/raiyon/api/app.py` → racine du dépôt, comme `prompts.REPERTOIRE`. Le projet est
installé en mode éditable, donc ce chemin résout ; une installation figée en
`site-packages` ne verrait pas `web/`, et c'est le jour où le projet s'empaquette qu'il
faudra en faire des données de paquet — pas avant."""

ENTETES_SSE = {
    "Cache-Control": "no-cache",
    # ⚠️ Sans cet en-tête, un nginx en frontal met le flux en tampon et le client ne
    # reçoit rien avant la fin du tour — c'est-à-dire exactement l'inverse de ce que
    # §3.12 promet. Il ne coûte rien en local, et il est illisible à rétro-diagnostiquer.
    "X-Accel-Buffering": "no",
}

MESSAGE_TOUR_EN_COURS = (
    "Un tour est déjà en cours sur cette session. Attendez sa fin avant d'envoyer "
    "le message suivant."
)

MESSAGE_INTERNE = (
    "Une erreur interne a interrompu ce tour. Rien n'a été enregistré — vous pouvez "
    "renvoyer votre message."
)
"""⚠️ Écrit **pour le client**, en français, et sans le `str()` de l'exception : une trace
SQLAlchemy sur une page web est une fuite (arbitrage E). Il dit aussi ce que l'atomicité
garantit — rien n'a été écrit — donc que renvoyer le message est sans risque."""


class ErreurDeLApi(HTTPException):
    """Une erreur **porteuse d'un `CodeErreur`**, rendue à plat par son gestionnaire.

    `HTTPException` emballe son `detail` : lever `HTTPException(409, {"code", "message"})`
    produit `{"detail": {"code", "message"}}` alors que l'événement `error` du fil rend
    `{"code", "message"}`. Le front porterait donc **deux lecteurs d'erreur** pour un seul
    vocabulaire, et la promesse de `CodeErreur` — « le même message quel que soit le chemin
    par lequel l'échec arrive » — serait fausse au premier 409 affiché.

    Le `detail` est renseigné quand même : c'est lui que lisent les outils qui ne
    connaissent pas ce type — Starlette, un log, un `raise` re-attrapé ailleurs.

    ⚠️ **Le 404 et le 422 ne passent pas par ici**, et c'est délibéré : ils ne portent pas
    de `CodeErreur`, et leur en inventer un pour uniformiser une clé ajouterait au
    vocabulaire fermé deux valeurs qui ne diraient rien de plus que le code HTTP.
    """

    def __init__(self, status_code: int, code: CodeErreur, message: str) -> None:
        super().__init__(status_code, charge_derreur(code, message))
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- #
# Ce qui est construit une fois, au démarrage
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Ressources:
    """Ce que tout tour partage. Construit au `lifespan`, jamais par requête (piège 4)."""

    client: ClientLLM
    prompt: SystemeEnVigueur
    """La version en vigueur, son texte et son empreinte, **d'un seul tenant**.

    Elles étaient deux champs jusqu'à l'étape 13, la version étant une constante. Depuis
    qu'elle se choisit par variable d'environnement, les séparer laisserait `/health`
    annoncer une version et la boucle en envoyer une autre."""

    outils: tuple[dict[str, Any], ...]
    fabrique: sessionmaker[Session]
    reglages: Settings


@asynccontextmanager
async def duree_de_vie(application: FastAPI) -> AsyncIterator[None]:
    """Construit les ressources partagées, ou **refuse de démarrer** en le disant.

    Une clé absente est une erreur de configuration, pas un incident de requête : la
    laisser passer donnerait un serveur qui répond `200` à `/health` et échoue au premier
    message, avec un message que personne ne lit au bon moment.

    ⚠️ **Le journal est configuré en premier**, avant même la clé : c'est le seul endroit
    d'où un `api.demarrage_impossible` peut atteindre un fichier. Configuré après, il
    n'aurait rien à dire du seul échec qui empêche le serveur d'exister.
    """
    journal = configurer_journal()
    try:
        client = ClientAnthropic()
        prompt = prompt_systeme()
    except ConfigurationError as erreur:
        logueur.error("api.demarrage_impossible", message=str(erreur))
        raise

    application.state.ressources = Ressources(
        client=client,
        prompt=prompt,
        outils=tuple(schema_des_outils()),
        fabrique=get_sessionmaker(),
        reglages=get_settings(),
    )
    logueur.info(
        "api.demarree",
        prompt=prompt.version,
        empreinte=prompt.empreinte,
        strict=client.strict,
        journal=None if journal is None else str(journal),
    )
    yield


app = FastAPI(
    title="rAiyon",
    summary="Assistant conseil produit — le LLM parle des faits, il ne les invente pas.",
    lifespan=duree_de_vie,
)


@app.exception_handler(ErreurDeLApi)
async def rendre_a_plat(_: Request, erreur: ErreurDeLApi) -> JSONResponse:
    """La même charge utile que l'événement `error` : `{code, message}`, sans `detail`.

    Starlette cherche un gestionnaire en remontant le `__mro__` de l'exception : celui-ci
    l'emporte sur celui d'`HTTPException`, qui continue de servir le 404.
    """
    return JSONResponse(
        status_code=erreur.status_code,
        content=charge_derreur(erreur.code, erreur.message),
    )


# --------------------------------------------------------------------------- #
# Les dépendances — trois portes, pour que les tests n'aient qu'à en pousser deux
# --------------------------------------------------------------------------- #


def ressources(requete: Request) -> Ressources:
    """Les ressources du processus. `app.state` n'est pas typé : le `cast` est la
    frontière où l'on redevient vérifiable par mypy."""
    return cast(Ressources, requete.app.state.ressources)


def client_llm(partagees: Annotated[Ressources, Depends(ressources)]) -> ClientLLM:
    """Le modèle. **Séparé exprès** : c'est la seule dépendance que les tests remplacent
    par le faux client de l'étape 8, et l'isoler évite de leur faire reconstruire tout le
    reste."""
    return partagees.client


def fabrique_de_sessions(
    partagees: Annotated[Ressources, Depends(ressources)],
) -> sessionmaker[Session]:
    """La fabrique de sessions base. Remplacée par les tests pour viser une base jetable."""
    return partagees.fabrique


Partagees = Annotated[Ressources, Depends(ressources)]
Modele = Annotated[ClientLLM, Depends(client_llm)]
Fabrique = Annotated[sessionmaker[Session], Depends(fabrique_de_sessions)]


# --------------------------------------------------------------------------- #
# Les routes
# --------------------------------------------------------------------------- #


@app.post("/sessions", status_code=status.HTTP_201_CREATED)
def ouvrir_une_session(fabrique: Fabrique) -> SessionCreee:
    """Ouvre une conversation vide et rend son identifiant.

    L'UUID est généré côté application, donc connu avant le premier flush : c'est ce qui
    permet de le rendre ici sans relire la ligne.
    """
    with fabrique() as base:
        conversation = creer_session(base)
        identifiant = conversation.id
        base.commit()
    return SessionCreee(id=identifiant)


@app.post(
    "/sessions/{identifiant}/messages",
    responses={status.HTTP_409_CONFLICT: {"model": ErreurExposee}},
)
def poster_un_message(
    identifiant: uuid.UUID,
    corps: MessageEntrant,
    partagees: Partagees,
    modele: Modele,
    fabrique: Fabrique,
) -> StreamingResponse:
    """Un tour client, en `text/event-stream`. **404, 409 et 422 avant le premier octet.**

    ### Pourquoi un POST rend du `text/event-stream` (arbitrage B)

    `EventSource` ne sait faire que du GET, et mettre le message du client en query string
    est exclu — longueur, encodage, et un message de client dans les logs d'accès.

    *Alternative écartée — un POST qui ouvre un tour, puis un GET `/events` en
    `EventSource`.* Deux requêtes, une course entre les deux, et un état serveur à porter
    entre elles pour rien.

    **Coût assumé, à payer à l'étape 11 :** le front devra parser le SSE à la main sur
    `fetch` + `ReadableStream`, là où `EventSource` l'aurait fait seul.

    ### La session base est ouverte ici et fermée là-bas

    Elle n'est **pas** obtenue par `Depends` : elle serait fermée quand le générateur
    tourne (piège 1). Elle est ouverte ici parce que le 404 et le verrou doivent être
    décidés avant le flux, et sur la connexion qui écrira — puis passée au générateur, qui
    en devient propriétaire et la ferme dans son `finally`.
    """
    base = fabrique()
    try:
        conversation = lire_session(base, identifiant)
    except SessionIntrouvable as erreur:
        base.close()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(erreur)) from erreur
    except Exception:
        base.close()
        raise

    # ⚠️ Aucun commit entre ici et `tour()` : le verrou est à portée de transaction, et un
    # commit le relâcherait avant même que le tour commence (arbitrage D).
    if not verrouiller_le_tour(base, identifiant):
        base.rollback()
        base.close()
        raise ErreurDeLApi(
            status.HTTP_409_CONFLICT, CodeErreur.TOUR_EN_COURS, MESSAGE_TOUR_EN_COURS
        )

    return StreamingResponse(
        _flux(base, conversation, message=corps.message, modele=modele, partagees=partagees),
        media_type="text/event-stream",
        headers=ENTETES_SSE,
    )


@app.get("/sessions/{identifiant}")
def relire_une_session(identifiant: uuid.UUID, fabrique: Fabrique) -> SessionExposee:
    """L'état et la prose. **Jamais une projection d'événements** (arbitrage J).

    ⚠️ **Limite connue et non corrigée ici : les messages de repli ne sont pas persistés.**
    `Repli` est émis par la boucle mais n'entre pas dans `IssueDuTour.tours` — c'est du
    texte écrit en Python, que le modèle n'a jamais produit. Une conversation rechargée
    après un F5 perd donc les tours clos par un repli. Le correctif serait de persister ce
    message comme un tour assistant, ce qui l'injecterait dans l'historique relu et
    changerait ce que le modèle voit au tour suivant : c'est une décision de l'étape 11 si
    elle en a besoin, pas un effet de bord à prendre ici.
    """
    with fabrique() as base:
        try:
            conversation = lire_session(base, identifiant)
        except SessionIntrouvable as erreur:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(erreur)) from erreur
        statut = conversation.statut
        etat = etat_de(conversation)
        historique = historique_de(base, identifiant)

    categorie = etat.categorie_courante
    return SessionExposee(
        id=identifiant,
        statut=statut,
        etat=EtatExpose(
            categorie=categorie,
            libelle_categorie=None if categorie is None else LIBELLES_CATEGORIE[categorie],
            criteres=(
                []
                if categorie is None
                else criteres_serialises(categorie, etat.criteres_de(categorie))
            ),
            budget_usd=None if etat.budget_usd is None else str(etat.budget_usd),
            **optimisation_serialisee(etat.optimisation),
        ),
        prose=[
            ParoleExposee(interlocuteur=parole.interlocuteur.value, texte=parole.texte)
            for parole in prose_de(historique)
        ],
    )


# --------------------------------------------------------------------------- #
# Le journal — **`dev` seulement**, et le 404 est la garde, pas un message
# --------------------------------------------------------------------------- #

MESSAGE_JOURNAL_ABSENT = (
    "Le journal n'existe que dans l'environnement de développement "
    "(RAIYON_APP_ENV=dev). Il expose des conversations entières."
)


def journal_ouvert(partagees: Partagees) -> None:
    """Lève un 404 hors `dev`. **Une dépendance, pas un `if` dans chaque route.**

    ⚠️ **404 et non 403 : la garde doit dire que la route n'existe pas**, pas qu'elle
    existe et se refuse. Un 403 sur `/journal/{uuid}` confirmerait à qui le demande qu'une
    session porte cet identifiant — c'est peu, et c'est déjà plus que rien.

    Ces deux routes rendent des conversations entières, avec la prose du client et les
    arguments exacts de chaque appel d'outil. Rien de tout cela n'a à exister sur un
    serveur qui ne sert pas à observer, et la seule façon de s'en assurer est de ne pas
    laisser le choix à la configuration d'aval.

    *Alternative écartée — ne pas monter les routes hors `dev`.* Plus radical, et la
    table des routes cesserait de dépendre uniquement du code : `routes_publiques()` — que
    le test de l'arbitrage L compare à une liste — rendrait deux résultats différents selon
    l'environnement, et ce test ne dirait plus rien.
    """
    if partagees.reglages.app_env != "dev":
        raise HTTPException(status.HTTP_404_NOT_FOUND, MESSAGE_JOURNAL_ABSENT)


JournalOuvert = Annotated[None, Depends(journal_ouvert)]


@app.get("/journal")
def lister_le_journal(_: JournalOuvert, fabrique: Fabrique) -> list[dict[str, Any]]:
    """Les sessions, les plus récentes d'abord, avec leurs totaux.

    Le type de retour est un `dict` nu et non un modèle Pydantic, contrairement au reste de
    l'API : cette page n'a pas de consommateur tiers à qui promettre un contrat, elle a un
    seul lecteur qui est la page d'à côté. Un schéma figé ici coûterait une classe par
    forme sans rien garantir de plus que ce que `journal.py` construit déjà.
    """
    with fabrique() as base:
        return journal.sessions(base)


@app.get("/journal/{identifiant}")
def lire_le_journal(identifiant: uuid.UUID, _: JournalOuvert, fabrique: Fabrique) -> dict[str, Any]:
    """La chronologie complète d'une session : en-tête agrégé, puis les tours.

    ⚠️ **Rend 200 pour une session d'avant l'étape 23**, avec ses tours et sans ses
    mesures. C'est le cas nominal pour les 71 860 tours déjà en base : la page dit « non
    mesuré » là où les colonnes manquent, au lieu de rendre une erreur ou d'afficher zéro.
    """
    with fabrique() as base:
        chronologie = journal.chronologie(base, identifiant)
    if chronologie is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"aucune session {identifiant} — vérifier l'identifiant."
        )
    return chronologie


@app.get("/health")
def sante(reponse: Response, partagees: Partagees, fabrique: Fabrique) -> Sante:
    """Base joignable, prompt en vigueur, mode `strict` retenu.

    C'est ce qui rend la porte de sortie **exécutable par quelqu'un d'autre** : les trois
    choses qui peuvent manquer avant une démonstration, en une requête.

    Le **503** sur base injoignable n'était pas demandé, et il est là quand même : un
    `/health` qui rend 200 quand la base est morte oblige à lire son corps pour savoir
    qu'il ment. Avec le code, `curl -f` suffit — le corps reste identique dans les deux
    cas, il ne perd donc rien.
    """
    joignable = True
    try:
        with fabrique() as base:
            base.execute(text("SELECT 1"))
    except SQLAlchemyError as erreur:
        joignable = False
        logueur.warning("api.base_injoignable", erreur=erreur.__class__.__name__)

    if not joignable:
        reponse.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return Sante(
        base=joignable,
        prompt=PromptExpose(version=partagees.prompt.version, empreinte=partagees.prompt.empreinte),
        strict=getattr(partagees.client, "strict", False),
    )


# --------------------------------------------------------------------------- #
# Le générateur SSE
# --------------------------------------------------------------------------- #


def _flux(
    base: Session,
    conversation: Any,  # noqa: ANN401 — `SessionConversation`, sans faire entrer db.models ici
    *,
    message: str,
    modele: ClientLLM,
    partagees: Ressources,
) -> Iterator[str]:
    """Le tour, converti en trames. **Consommé en entier, ou rien n'est persisté.**

    La boucle d'émission est un `for` ordinaire : elle épuise le générateur, donc `tour()`
    atteint son `commit()`. Ni `break` ni `return` conditionnel — c'est la règle que la
    console applique déjà, et elle vaut ici pour la même raison.

    La valeur de retour du générateur — l'`IssueDuTour` — est **jetée**, et c'est la seule
    différence avec la console : celle-ci en a besoin pour `--trace`, l'API n'affiche
    aucun bloc brut. Un `while / next / StopIteration` la récupérerait au prix d'un
    `return` dans la boucle, exactement ce que le piège nº2 interdit.
    """
    identifiant = conversation.id
    try:
        evenements = tour(
            base,
            conversation,
            client=modele,
            systeme=partagees.prompt.texte,
            outils=partagees.outils,
            message_client=message,
            depot=DepotSql(base),
            max_iterations=partagees.reglages.max_agent_iterations,
            max_regenerations=partagees.reglages.max_regenerations,
        )
        for evenement in evenements:
            yield trame_de(evenement)
        yield trame_de_fin()
    except Exception:
        # Après le premier octet, il n'existe plus de code HTTP à changer (arbitrage E).
        # Le détail part au log, avec l'identifiant ; le client reçoit une phrase.
        logueur.exception("api.tour_interrompu", session_id=str(identifiant))
        yield trame_derreur(CodeErreur.INTERNE, MESSAGE_INTERNE)
    finally:
        # ⚠️ Obligatoire, y compris sur `GeneratorExit` — une déconnexion client passe
        # exactement par ici. Sans le `rollback()`, la connexion revient au pool en
        # transaction avortée et fait échouer la requête suivante avec une erreur qui ne
        # désigne pas la vraie cause. Le verrou du tour tombe avec la transaction.
        base.rollback()
        base.close()


def _monter_le_front(application: FastAPI, repertoire: Path) -> None:
    """⚠️ **Après les routes, sinon le montage `/` les avale.**

    Le répertoire peut manquer sur une installation figée : `StaticFiles` lèverait au
    montage et empêcherait le serveur de démarrer pour une page de remplacement. On loggue
    et l'API reste utilisable — c'est l'inverse du démarrage sans clé, où l'absence est
    fatale parce qu'elle rend le produit inopérant.
    """
    if not repertoire.is_dir():
        logueur.warning("api.front_absent", repertoire=str(repertoire))
        return
    application.mount("/", StaticFiles(directory=repertoire, html=True), name="web")


_monter_le_front(app, REPERTOIRE_WEB)


CHEMIN_DU_MONTAGE = "/{path}"
"""Ce sous quoi un `Mount` sur `/` apparaît dans la table des routes. Nommé ici plutôt
que dans le test : c'est un détail de Starlette, pas une propriété de l'application."""


def routes_publiques(application: FastAPI = app) -> Sequence[str]:
    """Les chemins déclarés, **dans l'ordre de résolution**. Starlette prend le premier
    qui correspond, donc cet ordre est le contrat que garde le test de l'arbitrage L.

    `path_format` plutôt que `path` : le `path` d'un `Mount` est vide, et une liste où le
    montage n'apparaît pas est exactement celle qui ne peut pas répondre à la question
    qu'on lui pose.
    """
    return [
        str(getattr(route, "path_format", "") or getattr(route, "path", ""))
        for route in application.routes
    ]
