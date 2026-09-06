"""Les deux routes du journal : ce qu'elles rendent, et **qu'elles n'existent pas hors `dev`**.

Même montage que `test_api.py` — l'application réelle, `lifespan` compris, un faux modèle
par `dependency_overrides` et la base seedée. Rien n'est simulé du côté serveur : les tours
sont joués par les vraies routes, et le journal relit ce qu'elles ont écrit.

⚠️ **Le test qui compte le plus est celui du 404 hors `dev`.** Ces pages exposent des
conversations entières — la prose du client et les arguments exacts de chaque appel
d'outil. Une garde qui ne serait vérifiée qu'en relisant `app.py` finirait par sauter à la
première route ajoutée à côté.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from faux_client import FauxClient, appel_outil, message, texte
from scenarios import ECRAN_144
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from raiyon.api.app import app, client_llm, fabrique_de_sessions
from raiyon.config import get_settings
from raiyon.db.models import SessionConversation
from raiyon.tools.schema_outils import NOM_ENREGISTRER, NOM_RECHERCHER

pytestmark = pytest.mark.integration


@pytest.fixture
def fabrique(moteur_agregats: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=moteur_agregats, expire_on_commit=False)


@pytest.fixture
def api(fabrique: sessionmaker[Session], monkeypatch) -> TestClient:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "factice-tests-journal")
    app.dependency_overrides[fabrique_de_sessions] = lambda: fabrique
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _scenario() -> FauxClient:
    """Enregistrer, chercher, conclure : trois appels, deux outils, un texte livré."""
    return FauxClient(
        [
            message(texte("Je note ça."), appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(appel_outil(NOM_RECHERCHER, id="tu_2")),
            message(texte("Voici trois écrans.")),
        ]
    )


def _jouer_un_tour(api: TestClient) -> uuid.UUID:
    identifiant = uuid.UUID(api.post("/sessions").json()["id"])
    app.dependency_overrides[client_llm] = lambda: _scenario()
    reponse = api.post(
        f"/sessions/{identifiant}/messages", json={"message": "un écran 144 Hz à 400 $"}
    )
    assert reponse.status_code == 200
    return identifiant


# --------------------------------------------------------------------------- #
# La garde d'environnement
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("environnement", ["prod", "test"])
def test_les_deux_routes_repondent_404_hors_dev(api, environnement, monkeypatch):
    """⚠️ **404 et non 403 : la route doit dire qu'elle n'existe pas.**

    Un 403 sur `/journal/{uuid}` confirmerait à qui le demande qu'une session porte cet
    identifiant. C'est peu, et c'est déjà plus que rien.
    """
    monkeypatch.setenv("RAIYON_APP_ENV", environnement)
    get_settings.cache_clear()
    # Les réglages sont capturés au `lifespan` : il faut donc rouvrir l'application pour
    # que la garde voie la nouvelle valeur — c'est aussi ce qui se passe en vrai, un
    # changement d'environnement passant par un redémarrage.
    with TestClient(app) as client:
        assert client.get("/journal").status_code == 404
        assert client.get(f"/journal/{uuid.uuid4()}").status_code == 404


def test_en_dev_les_deux_routes_repondent(api):
    """Le pendant du test précédent : sans lui, un 404 permanent le satisferait aussi."""
    identifiant = _jouer_un_tour(api)

    assert api.get("/journal").status_code == 200
    assert api.get(f"/journal/{identifiant}").status_code == 200


def test_une_session_inconnue_rend_404_en_dev(api):
    """Le 404 d'absence, distinct de celui de la garde — même code, deux causes."""
    assert api.get(f"/journal/{uuid.uuid4()}").status_code == 404


# --------------------------------------------------------------------------- #
# Ce que la liste rend
# --------------------------------------------------------------------------- #


def test_la_liste_porte_les_totaux_de_la_session(api):
    identifiant = _jouer_un_tour(api)

    (ligne,) = [entree for entree in api.get("/journal").json() if entree["id"] == str(identifiant)]
    assert ligne["appels"] == 3
    assert ligne["tours"] == 1
    assert ligne["mesuree"] is True
    assert ligne["replis"] == 0
    assert ligne["griefs"] == 0


def test_une_session_sans_tour_apparait_comme_non_mesuree(api, fabrique):
    """⚠️ **Le drapeau qui empêche la liste de mentir** (contrainte 3.4).

    Une session d'avant l'étape 23 a des tours et zéro appel. Sans `mesuree`, la page
    afficherait « 0 appel » comme si la conversation n'avait rien coûté — au lieu de dire
    qu'on ne sait pas ce qu'elle a coûté.
    """
    with fabrique() as base:
        conversation = SessionConversation(id=uuid.uuid4(), criteres_valides={})
        base.add(conversation)
        base.commit()
        identifiant = conversation.id

    (ligne,) = [entree for entree in api.get("/journal").json() if entree["id"] == str(identifiant)]
    assert ligne["mesuree"] is False
    assert ligne["appels"] == 0


# --------------------------------------------------------------------------- #
# Ce que la chronologie rend
# --------------------------------------------------------------------------- #


def test_la_chronologie_rend_le_tour_ses_appels_et_ses_outils(api):
    """Un appel par ligne assistant, apparié à sa mesure, avec ses arguments exacts."""
    identifiant = _jouer_un_tour(api)

    chronologie = api.get(f"/journal/{identifiant}").json()
    (tour,) = chronologie["tours"]

    assert tour["message_client"] == "un écran 144 Hz à 400 $"
    assert [appel["iteration"] for appel in tour["appels"]] == [1, 2, 3]

    premier = tour["appels"][0]
    assert premier["texte"] == "Je note ça."
    (outil,) = premier["outils"]
    assert outil["nom"] == NOM_ENREGISTRER
    # Les arguments **exacts**, pas un résumé : c'est ce qui permet de relire ce que le
    # modèle a réellement demandé quand un critère a disparu.
    assert outil["arguments"] == ECRAN_144
    assert outil["resultat"] is not None


def test_chaque_appel_porte_sa_mesure_et_son_stop_reason(api):
    identifiant = _jouer_un_tour(api)

    (tour,) = api.get(f"/journal/{identifiant}").json()["tours"]

    mesures = [appel["mesure"] for appel in tour["appels"]]
    assert all(mesure is not None for mesure in mesures)
    assert [mesure["stop_reason"] for mesure in mesures] == ["tool_use", "tool_use", "end_turn"]
    assert all(mesure["interrompue"] is False for mesure in mesures)
    assert all(mesure["latence_ms"] >= 0 for mesure in mesures)


def test_un_appel_sans_raisonnement_rend_none_et_non_une_chaine_vide(api):
    """⚠️ **Un état normal, pas une donnée manquante** — 1 appel sur 5 en portait un.

    `None` : l'adaptatif n'a pas raisonné. `""` : un bloc existe mais son texte est vide,
    c'est-à-dire un appel passé sous `display: "omitted"`. Les deux se distinguent, parce
    que la page doit dire deux choses différentes.
    """
    identifiant = _jouer_un_tour(api)

    (tour,) = api.get(f"/journal/{identifiant}").json()["tours"]

    assert all(appel["raisonnement"] is None for appel in tour["appels"])
    assert all(appel["resume_produit_par_lapi"] is True for appel in tour["appels"])


def test_lentete_porte_les_chiffres_sur_lesquels_on_arbitre(api):
    """Les totaux, le coût estimé, les latences, et les deux comptes par clé."""
    identifiant = _jouer_un_tour(api)

    entete = api.get(f"/journal/{identifiant}").json()["entete"]

    assert entete["appels"] == 3
    assert entete["tours"] == 1
    assert entete["mesuree"] is True
    assert entete["latence_ms_mediane"] is not None
    assert entete["latence_ms_max"] >= entete["latence_ms_mediane"]
    assert entete["replis_par_motif"] == {}
    assert entete["griefs_par_code"] == {}
    # Le faux client ne nomme pas son modèle : le tarif est donc inconnu, et le coût vaut
    # `None` plutôt qu'un chiffre inventé pour remplir la case.
    assert entete["cout_estime_usd"] is None
    assert entete["efforts"] == ["defaut"]


def test_les_griefs_du_validateur_sont_comptes_par_code(api):
    """C'est **le** chiffre sur lequel un relâchement du validateur se décide.

    Un total agrégé dirait qu'il y a eu six rejets sans dire si c'est six fois la même
    règle — or c'est exactement la question que le relâchement pose.
    """
    identifiant = uuid.UUID(api.post("/sessions").json()["id"])
    # Un texte qui cite un prix qu'aucun `tool_result` ne fonde : le validateur le refuse,
    # la régénération est demandée, puis le second texte passe.
    app.dependency_overrides[client_llm] = lambda: FauxClient(
        [
            message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(appel_outil(NOM_RECHERCHER, id="tu_2")),
            message(texte("Le meilleur est à 47 $.")),
            message(texte("Voici trois écrans.")),
        ]
    )
    api.post(f"/sessions/{identifiant}/messages", json={"message": "un écran 144 Hz à 400 $"})

    chronologie = api.get(f"/journal/{identifiant}").json()
    (tour,) = chronologie["tours"]

    rejets = [
        evenement for evenement in tour["evenements"] if evenement["genre"] == "text_rejected"
    ]
    assert len(rejets) == 1
    # Le rejet se lit **à son rang réel**, pas relégué en fin de tour.
    assert rejets[0]["rang"] < max(evenement["rang"] for evenement in tour["evenements"])
    assert rejets[0]["charge"]["griefs"]
    assert chronologie["entete"]["griefs_par_code"]


def test_lappel_dont_le_texte_a_ete_refuse_est_marque_et_porte_son_grief(api):
    """⚠️ **Le point où la page pouvait le plus facilement mentir.**

    Un texte refusé est un bloc `text` d'un message assistant, **exactement comme un texte
    livré**. Sans `refuse`, les deux se rendraient à l'identique et la chronologie se
    lirait comme si le client avait reçu deux messages — alors que le premier n'a jamais
    quitté le serveur.

    La règle vient de `prose.py` (« un message assistant suivi d'une reprise a été
    refusé »), importée et non réécrite.
    """
    identifiant = uuid.UUID(api.post("/sessions").json()["id"])
    app.dependency_overrides[client_llm] = lambda: FauxClient(
        [
            message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(appel_outil(NOM_RECHERCHER, id="tu_2")),
            message(texte("Le meilleur est à 47 $.")),
            message(texte("Voici trois écrans.")),
        ]
    )
    api.post(f"/sessions/{identifiant}/messages", json={"message": "un écran 144 Hz à 400 $"})

    (tour,) = api.get(f"/journal/{identifiant}").json()["tours"]
    refuses = [appel for appel in tour["appels"] if appel["refuse"]]
    livres = [appel for appel in tour["appels"] if appel["texte"] and not appel["refuse"]]

    (refuse,) = refuses
    assert refuse["texte"] == "Le meilleur est à 47 $."
    # Le grief est **rattaché à l'appel qui l'a produit**, pas relégué en fin de tour où
    # il faudrait deviner de quel texte il parle.
    assert refuse["grief"]["griefs"]
    assert refuse["grief"]["origine"] == "texte"

    (livre,) = livres
    assert livre["texte"] == "Voici trois écrans."
    assert livre["grief"] is None
    # L'appel refusé vient **avant** celui qui a été livré : l'ordre réel, pas un tri.
    assert refuse["iteration"] < livre["iteration"]


def test_un_outil_refuse_par_le_repartiteur_est_marque(api):
    """⚠️ **La même faute que le texte refusé, au même endroit.**

    Un bloc `tool_use` en base n'est pas la preuve que son effet a atteint quoi que ce
    soit : le répartiteur refuse, rend un `tool_result` en erreur, et **aucun événement ne
    part au client** — `evenements.py` écrit qu'un refus d'outil n'en est pas un. Sans le
    drapeau, un `record_criteria` refusé se lit comme un `record_criteria` réussi et la
    timeline laisse croire qu'un critère a été enregistré.

    `search_products` ne prend aucun argument (arbitrage C de l'étape 7) : lui en passer un
    est le chemin de refus le plus court, et il est réel — le modèle l'a pris en
    conversation réelle.
    """
    identifiant = uuid.UUID(api.post("/sessions").json()["id"])
    app.dependency_overrides[client_llm] = lambda: FauxClient(
        [
            message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(appel_outil(NOM_RECHERCHER, {"categorie": "monitor"}, id="tu_2")),
            message(appel_outil(NOM_RECHERCHER, id="tu_3")),
            message(texte("Voici trois écrans.")),
        ]
    )
    api.post(f"/sessions/{identifiant}/messages", json={"message": "un écran 144 Hz à 400 $"})

    (tour,) = api.get(f"/journal/{identifiant}").json()["tours"]
    outils = [outil for appel in tour["appels"] for outil in appel["outils"]]
    par_id = {outil["id"]: outil for outil in outils}

    assert par_id["tu_2"]["refuse"] is True, "l'appel à arguments illisibles doit être marqué"
    assert par_id["tu_1"]["refuse"] is False
    assert par_id["tu_3"]["refuse"] is False
    # Le refus reste lisible : c'est ce que le modèle a lu pour se corriger.
    assert par_id["tu_2"]["resultat"] is not None


def test_une_session_ancienne_rend_ses_tours_sans_ses_mesures(api, fabrique):
    """⚠️ **Contrainte 3.4 : la page ne doit ni planter ni mentir sur l'historique.**

    Les 71 860 tours déjà en base n'ont ni appel ni événement, et rien ne permet de les
    leur fabriquer. La chronologie se construit donc sur `tours_conversation`, qui existe
    depuis l'étape 8 — les deux tables neuves ne font que l'enrichir.
    """
    from raiyon.db.models import TourConversation

    with fabrique() as base:
        conversation = SessionConversation(id=uuid.uuid4(), criteres_valides={})
        base.add(conversation)
        base.flush()
        identifiant = conversation.id
        base.add_all(
            [
                TourConversation(
                    session_id=identifiant,
                    numero=1,
                    role="user",
                    blocs=[{"type": "text", "text": "un écran 144 Hz"}],
                ),
                TourConversation(
                    session_id=identifiant,
                    numero=2,
                    role="assistant",
                    # Le bloc `thinking` vide de tout l'historique d'avant l'étape 23 :
                    # signé, et sans une lettre de texte.
                    blocs=[
                        {"type": "thinking", "thinking": "", "signature": "Er0E…"},
                        {"type": "text", "text": "Voici trois écrans."},
                    ],
                ),
            ]
        )
        base.commit()

    chronologie = api.get(f"/journal/{identifiant}").json()
    (tour,) = chronologie["tours"]

    assert tour["mesure"] is False
    assert tour["evenements"] == []
    (appel,) = tour["appels"]
    assert appel["mesure"] is None
    assert appel["texte"] == "Voici trois écrans."
    # `""` et non `None` : le bloc existait, c'est son texte qui était vide. La page dit
    # « raisonnement non affiché », pas « pas de raisonnement ».
    assert appel["raisonnement"] == ""
    assert chronologie["entete"]["mesuree"] is False
    assert chronologie["entete"]["cout_estime_usd"] is None
