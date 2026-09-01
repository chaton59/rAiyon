"""Les endpoints, sur une base réelle et un faux modèle. **Les quatre pièges vivent ici.**

Aucun des défauts que l'étape 10 pouvait produire ne se voit en test unitaire : une
session base fermée trop tôt, un verrou pris sur la mauvaise connexion, une transaction
avortée rendue au pool, un `str()` d'exception parti au client. Ce fichier est écrit pour
chacun d'eux.

### Le montage

`ClientLLM` est remplacé par le faux client de l'étape 8 via `dependency_overrides`, et la
fabrique de sessions par une fabrique visant la base seedée de `tests/integration/`. Tout
le reste — le `lifespan`, le verrou, le générateur, la persistance — est le code de
production, sans aménagement.

⚠️ **La clé API est factice mais présente.** Le `lifespan` construit un `ClientAnthropic`,
et il **doit** échouer sans clé (piège nº4) : le neutraliser ici retirerait au test la
propriété la plus utile qu'il donne gratuitement, à savoir que l'application démarre
vraiment. La construction du SDK n'appelle aucune API. C'est le même geste que
`base_de_test.py` fait depuis l'étape 4.

### Ce que ces tests ne couvrent pas, et il vaut mieux l'écrire

La déconnexion client (arbitrage I) n'est pas exercée : `TestClient` ne sait pas couper un
flux au milieu, et un test qui simulerait le `GeneratorExit` en appelant `.close()` sur le
générateur testerait Python, pas Starlette. Ce qui est vérifié à la place est la propriété
dont dépend la propreté d'une déconnexion — que la connexion revienne au pool utilisable —
et elle l'est par `test_deux_tours_sequentiels_passent_tous_les_deux` et par
`test_une_exception_pendant_le_tour_ne_casse_pas_la_requete_suivante`.
"""

import json
import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from faux_client import FauxClient, appel_outil, message, texte
from scenarios import ECRAN_144
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from raiyon.api.app import MESSAGE_TOUR_EN_COURS, app, client_llm, fabrique_de_sessions
from raiyon.api.verrou import verrouiller_le_tour
from raiyon.db.models import SessionConversation, TourConversation
from raiyon.tools.schema_outils import NOM_ENREGISTRER, NOM_PRECISION, NOM_RECHERCHER

pytestmark = pytest.mark.integration

DELAI = 10
"""Secondes. Aucun test concurrent ne doit pouvoir bloquer la suite : un verrou mal pris
se manifesterait par une attente infinie, et une attente infinie en CI ne dit rien."""


# --------------------------------------------------------------------------- #
# Le montage
# --------------------------------------------------------------------------- #


@pytest.fixture
def fabrique(moteur_agregats: Engine) -> sessionmaker[Session]:
    """Une fabrique visant la base seedée. Les tours y **commitent réellement**.

    Pas la fixture `session` à transaction annulée des autres fichiers : le générateur SSE
    ouvre sa propre session et commite, et lui imposer une transaction externe
    testerait un montage que la production n'a pas. Chaque test travaille sur sa propre
    session de conversation, donc les commits ne se marchent pas dessus.
    """
    return sessionmaker(bind=moteur_agregats, expire_on_commit=False)


@pytest.fixture
def api(fabrique: sessionmaker[Session], monkeypatch) -> TestClient:
    """L'application réelle, `lifespan` compris."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "factice-tests-api")
    app.dependency_overrides[fabrique_de_sessions] = lambda: fabrique
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def brancher(modele: FauxClient) -> None:
    """Remplace le modèle pour le tour à venir. Un scénario par tour, comme en console."""
    app.dependency_overrides[client_llm] = lambda: modele


def ouvrir(api: TestClient) -> uuid.UUID:
    reponse = api.post("/sessions")
    assert reponse.status_code == 201
    return uuid.UUID(reponse.json()["id"])


def trames(reponse) -> list[tuple[str, dict]]:
    """Le flux SSE décodé, dans l'ordre — `[(nom, données), …]`."""
    lues: list[tuple[str, dict]] = []
    for bloc in reponse.text.split("\n\n"):
        if not bloc.strip():
            continue
        lignes = bloc.split("\n")
        lues.append(
            (lignes[0].removeprefix("event: "), json.loads(lignes[1].removeprefix("data: ")))
        )
    return lues


def scenario_complet() -> FauxClient:
    """Enregistrer, chercher, conclure. Le tour le plus représentatif du produit."""
    return FauxClient(
        [
            message(texte("Je note ça."), appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(appel_outil(NOM_RECHERCHER, id="tu_2")),
            message(texte("Voici trois écrans qui tiennent dans le budget.")),
        ]
    )


def poster(api: TestClient, identifiant: uuid.UUID, texte_client: str = "un écran 144 Hz à 400 $"):
    return api.post(f"/sessions/{identifiant}/messages", json={"message": texte_client})


# --------------------------------------------------------------------------- #
# 1 — La création de session
# --------------------------------------------------------------------------- #


def test_post_sessions_rend_un_uuid_et_la_ligne_existe_en_base(api, fabrique):
    identifiant = ouvrir(api)

    with fabrique() as base:
        conversation = base.get(SessionConversation, identifiant)

    assert conversation is not None
    assert conversation.statut == "en_cours"
    # L'UUID est généré côté application : il est connu **avant** le premier flush, ce
    # qui permet de le rendre sans relire la ligne.
    assert conversation.id == identifiant


# --------------------------------------------------------------------------- #
# 2 — Un tour complet
# --------------------------------------------------------------------------- #


def test_un_tour_complet_rend_la_suite_devenements_attendue_et_se_termine_par_done(api, fabrique):
    """La porte de sortie de l'étape, en test : les événements typés, dans l'ordre.

    L'ordre n'est pas cosmétique — c'est lui qui fait vivre le panneau de §3.12 pendant
    que la prose se fait attendre : les critères et les produits arrivent **avant** le
    message final.
    """
    identifiant = ouvrir(api)
    brancher(scenario_complet())

    reponse = poster(api, identifiant)

    assert reponse.status_code == 200
    assert reponse.headers["content-type"].startswith("text/event-stream")
    assert reponse.headers["cache-control"] == "no-cache"
    assert reponse.headers["x-accel-buffering"] == "no"

    lues = trames(reponse)
    assert [nom for nom, _ in lues] == [
        "message",
        "criteria_updated",
        "products_found",
        "message",
        "done",
    ]

    criteres = dict(lues)["criteria_updated"]
    assert criteres["libelle_categorie"] == "écran"
    assert criteres["budget_usd"] == "400.00"
    assert criteres["criteres"][0]["libelle_fr"] == "fréquence de rafraîchissement"
    assert criteres["criteres"][0]["unite"] == "Hz"

    produits = dict(lues)["products_found"]
    assert produits["produits"], "le catalogue seedé doit rendre des écrans 144 Hz sous 400 $"
    assert "traces" not in produits

    # Le tour a été consommé en entier, donc il a été persisté.
    with fabrique() as base:
        lignes = (
            base.query(TourConversation)
            .filter(TourConversation.session_id == identifiant)
            .order_by(TourConversation.numero)
            .all()
        )
    assert [ligne.role for ligne in lignes] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_les_prix_du_fil_sont_des_chaines(api):
    """§2 se joue au caractère : un flottant JSON perdrait des décimales."""
    identifiant = ouvrir(api)
    brancher(scenario_complet())

    produits = dict(trames(poster(api, identifiant)))["products_found"]

    for produit in produits["produits"]:
        assert isinstance(produit["prix_usd"], str)


# --------------------------------------------------------------------------- #
# 3 et 4 — Ce qui est refusé avant le premier octet (arbitrage E)
# --------------------------------------------------------------------------- #


def test_une_session_inconnue_rend_404_et_aucun_octet_de_flux(api):
    """La ligne de partage : **avant** le premier octet, il reste un code HTTP à donner."""
    brancher(scenario_complet())

    reponse = poster(api, uuid.uuid4())

    assert reponse.status_code == 404
    assert "event:" not in reponse.text
    assert not reponse.headers["content-type"].startswith("text/event-stream")
    # **Le pendant négatif du 409 aplati** : le 404 ne porte pas de `CodeErreur`, donc il
    # garde la forme de FastAPI. Un aplatissement gourmand aurait aussi pris le 422, qui
    # porte la liste d'erreurs de Pydantic et n'a pas de « message » unique à rendre.
    assert reponse.json().keys() == {"detail"}


def test_un_corps_vide_rend_422(api):
    identifiant = ouvrir(api)

    assert api.post(f"/sessions/{identifiant}/messages", json={}).status_code == 422
    assert api.post(f"/sessions/{identifiant}/messages", json={"message": ""}).status_code == 422


def test_un_champ_invente_rend_422(api):
    """`extra="forbid"` : une faute de frappe du front est une erreur, pas un oubli."""
    identifiant = ouvrir(api)

    reponse = api.post(
        f"/sessions/{identifiant}/messages", json={"message": "salut", "temperature": 0}
    )

    assert reponse.status_code == 422


# --------------------------------------------------------------------------- #
# 5 et 6 — Le verrou (arbitrage D)
# --------------------------------------------------------------------------- #


def test_deux_tours_concurrents_le_second_recoit_409(api, fabrique):
    """⚠️ **Le test qui vérifie que le verrou est pris sur la bonne connexion.**

    Un verrou posé sur une session base autre que celle qui écrit ne protégerait rien, et
    la relecture ne le dirait pas — le code aurait exactement la même forme. Le premier
    tour est donc bloqué **à l'intérieur** de la boucle, dans l'appel au modèle, c'est-à-
    dire à l'endroit précis où la connexion du tour est en cours d'usage.
    """
    identifiant = ouvrir(api)

    entre = threading.Event()
    relacher = threading.Event()

    class ClientQuiBloque(FauxClient):
        def repondre(self, **kwargs):
            entre.set()
            assert relacher.wait(DELAI), "le second tour n'a jamais rendu la main"
            return super().repondre(**kwargs)

    brancher(ClientQuiBloque(scenario_complet().reponses))

    premier: dict[str, object] = {}

    def tour_bloquant() -> None:
        premier["reponse"] = poster(api, identifiant)

    fil = threading.Thread(target=tour_bloquant)
    fil.start()
    try:
        assert entre.wait(DELAI), "le premier tour n'a jamais atteint l'appel au modèle"
        concurrent = poster(api, identifiant, "et sinon ?")
    finally:
        relacher.set()
        fil.join(DELAI)

    assert concurrent.status_code == 409
    # ⚠️ **À plat**, comme l'événement `error` — pas `{"detail": {...}}`. Le front lit un
    # seul vocabulaire d'erreur ; il ne doit pas porter deux lecteurs pour le lire.
    assert concurrent.json() == {"code": "tour_en_cours", "message": MESSAGE_TOUR_EN_COURS}
    assert "event:" not in concurrent.text
    assert premier["reponse"].status_code == 200


def test_deux_tours_sequentiels_passent_tous_les_deux(api):
    """Le pendant du test précédent : **le verrou est bien relâché par le commit.**

    Sans lui, un verrou correctement pris mais jamais rendu donnerait une session
    utilisable une seule fois — un défaut qui ne se voit qu'au deuxième message, donc
    jamais en développement.
    """
    identifiant = ouvrir(api)

    brancher(scenario_complet())
    premier = poster(api, identifiant)

    brancher(FauxClient([message(texte("Autre chose ?"))]))
    second = poster(api, identifiant, "merci")

    assert premier.status_code == 200
    assert second.status_code == 200
    assert trames(second)[-1][0] == "done"


def test_un_verrou_tenu_ailleurs_refuse_le_tour(api, fabrique, moteur_agregats):
    """Le verrou est consultatif **et inter-connexion** : c'est ce qui le rend valable
    en multi-worker, là où un `dict` de verrous par processus ne le serait pas (§3.12)."""
    identifiant = ouvrir(api)
    brancher(scenario_complet())

    tenant = fabrique()
    try:
        assert verrouiller_le_tour(tenant, identifiant) is True
        reponse = poster(api, identifiant)
    finally:
        tenant.rollback()
        tenant.close()

    assert reponse.status_code == 409


# --------------------------------------------------------------------------- #
# 7 — Après le premier octet, un événement typé (arbitrage E)
# --------------------------------------------------------------------------- #


SECRET = "connexion refusée sur 10.0.0.7:5432 — mot de passe pour raiyon_admin"
"""Une chaîne qui ressemble à ce qu'une vraie exception de base laisserait fuir."""


def test_une_exception_pendant_le_tour_donne_un_evenement_error_sans_le_message(api):
    """⚠️ **Une trace SQLAlchemy sur une page web est une fuite.**

    Le détail part en `logueur.exception` avec l'identifiant de session ; le client reçoit
    un code fermé et une phrase française. Le test le vérifie sur le flux entier, pas
    seulement sur le champ `message` : une fuite passerait tout aussi bien par ailleurs.
    """
    identifiant = ouvrir(api)

    class ClientQuiCasse(FauxClient):
        def repondre(self, **kwargs):
            raise RuntimeError(SECRET)

    brancher(ClientQuiCasse([]))

    reponse = poster(api, identifiant)
    lues = trames(reponse)

    assert reponse.status_code == 200, "le flux avait commencé : il n'y a plus de code à changer"
    assert [nom for nom, _ in lues] == ["error"]
    assert lues[0][1]["code"] == "interne"
    assert SECRET not in reponse.text
    assert "RuntimeError" not in reponse.text
    # Le flux se ferme sur l'erreur : `done` dirait « tour terminé », ce qui serait faux.
    assert "done" not in reponse.text


def test_une_exception_pendant_le_tour_ne_persiste_rien(api, fabrique):
    """L'atomicité de `session.py` : un tour est entier, ou il n'a pas eu lieu — **pas
    même le message du client**. C'est ce que le message d'erreur promet au client quand
    il lui dit qu'il peut renvoyer son message."""
    identifiant = ouvrir(api)

    class ClientQuiCasse(FauxClient):
        def repondre(self, **kwargs):
            raise RuntimeError(SECRET)

    brancher(ClientQuiCasse([]))
    poster(api, identifiant)

    with fabrique() as base:
        lignes = (
            base.query(TourConversation).filter(TourConversation.session_id == identifiant).count()
        )

    assert lignes == 0


def test_une_exception_pendant_le_tour_ne_casse_pas_la_requete_suivante(api):
    """**Le piège nº3, et il ne se voit que là.** Sans le `rollback()` du `finally`, la
    connexion revient au pool en transaction avortée : c'est la requête *suivante* qui
    échoue, avec une erreur qui ne désigne pas la vraie cause."""
    identifiant = ouvrir(api)

    class ClientQuiCasse(FauxClient):
        def repondre(self, **kwargs):
            raise RuntimeError(SECRET)

    brancher(ClientQuiCasse([]))
    poster(api, identifiant)

    brancher(scenario_complet())
    reprise = poster(api, identifiant, "on reprend")

    assert reprise.status_code == 200
    assert trames(reprise)[-1][0] == "done"


# --------------------------------------------------------------------------- #
# 8 — La relecture (arbitrage J)
# --------------------------------------------------------------------------- #


def test_get_session_rend_letat_et_la_prose_dans_lordre_apres_deux_tours(api):
    """L'état vient de `depuis_jsonb()`, la prose des blocs. **Aucun fait n'est
    reconstruit** : ni les critères depuis les `tool_result`, ni les produits."""
    identifiant = ouvrir(api)

    brancher(scenario_complet())
    poster(api, identifiant, "un écran 144 Hz à 400 $")

    brancher(
        FauxClient(
            [
                message(
                    texte("Une précision avant de conclure."),
                    appel_outil(
                        NOM_PRECISION,
                        {"question": "Tu joues plutôt en compétitif ?", "champ_vise": "panel_type"},
                        id="tu_3",
                    ),
                )
            ]
        )
    )
    poster(api, identifiant, "montre-moi autre chose")

    relue = api.get(f"/sessions/{identifiant}")

    assert relue.status_code == 200
    corps = relue.json()
    assert corps["statut"] == "en_cours"
    assert corps["etat"]["categorie"] == "monitor"
    assert corps["etat"]["libelle_categorie"] == "écran"
    assert corps["etat"]["budget_usd"] == "400.00"
    assert corps["etat"]["criteres"][0]["champ"] == "refresh_rate"
    assert corps["etat"]["criteres"][0]["unite"] == "Hz"

    assert [(parole["interlocuteur"], parole["texte"]) for parole in corps["prose"]] == [
        ("client", "un écran 144 Hz à 400 $"),
        ("assistant", "Je note ça."),
        ("assistant", "Voici trois écrans qui tiennent dans le budget."),
        ("client", "montre-moi autre chose"),
        ("assistant", "Une précision avant de conclure."),
        # La question d'`ask_clarification` est de la prose : elle part au client verbatim.
        ("assistant", "Tu joues plutôt en compétitif ?"),
    ]


def test_get_session_inconnue_rend_404(api):
    assert api.get(f"/sessions/{uuid.uuid4()}").status_code == 404


def test_get_session_neuve_rend_un_etat_vide_et_une_prose_vide(api):
    """Une session ouverte et jamais utilisée n'est pas un cas d'erreur."""
    corps = api.get(f"/sessions/{ouvrir(api)}").json()

    assert corps["etat"]["categorie"] is None
    assert corps["etat"]["libelle_categorie"] is None
    assert corps["etat"]["criteres"] == []
    assert corps["etat"]["budget_usd"] is None
    assert corps["prose"] == []


# --------------------------------------------------------------------------- #
# 9 — La porte de sortie exécutable par quelqu'un d'autre
# --------------------------------------------------------------------------- #


def test_health_rend_200_avec_la_base_joignable(api):
    reponse = api.get("/health")

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["base"] is True
    assert corps["prompt"]["version"] == "systeme.v1"
    assert len(corps["prompt"]["empreinte"]) == 12
    assert isinstance(corps["strict"], bool)


def test_le_front_est_servi_par_le_meme_processus(api):
    """Arbitrage L : un processus, une commande, aucun CORS à configurer.

    ⚠️ Et le montage `/` **ne mange pas** les routes — c'est la moitié du test qui compte,
    parce que l'inverse est silencieux : `/health` rendrait un 404 de fichier statique.
    """
    racine = api.get("/")

    assert racine.status_code == 200
    assert "text/html" in racine.headers["content-type"]
    assert api.get("/health").status_code == 200
