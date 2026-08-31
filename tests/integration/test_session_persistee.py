"""L'aller-retour réel : un tour écrit, relu, et l'état reconstruit à l'identique.

**Pourquoi ce test existe à l'étape 8 et pas à l'étape 10.** `en_jsonb()` et
`depuis_jsonb()` sont écrites depuis l'étape 7 et testées entre elles, en mémoire. Rien
ne prouvait qu'un aller-retour par Postgres — donc par JSONB, donc par les conversions de
`Decimal` en chaîne — rendait le même état. Différer, c'est laisser l'étape 10 découvrir
un défaut de sérialisation avec le streaming par-dessus (arbitrage 9).

Trois propriétés, et la troisième est la moins évidente :

1. les critères et le budget reviennent identiques ;
2. `tour_du_dernier_desserrage` revient — c'est lui qui rend le **jeton de parole**
   incontournable par redémarrage (§3.17) ;
3. `tour_client` est le `numero` de la ligne du message client, et il **croît** malgré
   les lignes de rôle `user` que les `tool_result` insèrent au milieu. Un compteur qui
   compterait les lignes `user` serait faux dès le premier appel d'outil.
"""

from decimal import Decimal

import pytest
from faux_client import FauxClient, appel_outil, message, texte
from scenarios import ECRAN_144, SYSTEME

from outils_de_test import TOLERANCE
from raiyon.agent.session import (
    creer_session,
    etat_de,
    historique_de,
    lire_session,
    prochain_numero,
    tour,
)
from raiyon.db.models import TourConversation
from raiyon.tools.schema_outils import (
    NOM_ENREGISTRER,
    NOM_RECHERCHER,
    schema_des_outils,
)

pytestmark = pytest.mark.integration


def _jouer(base, conversation, client, depot, message_client):
    """Consomme le générateur en entier — sinon rien n'est écrit."""
    generateur = tour(
        base,
        conversation,
        client=client,
        systeme=SYSTEME,
        outils=schema_des_outils(),
        message_client=message_client,
        depot=depot,
        max_iterations=8,
        tolerance=TOLERANCE,
    )
    while True:
        try:
            next(generateur)
        except StopIteration as arret:
            return arret.value


def test_un_tour_ecrit_puis_relu_rend_le_meme_etat(session, depot_catalogue):
    """La propriété centrale : ce qui sort de la base est ce qui y est entré."""
    conversation = creer_session(session)
    client = FauxClient(
        [
            message(texte("Je note."), appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(appel_outil(NOM_RECHERCHER, id="tu_2")),
            message(texte("Voici trois écrans.")),
        ]
    )

    issue = _jouer(session, conversation, client, depot_catalogue, "Un écran 144 Hz, 400 $ max")

    # L'état relu **par la base**, pas celui gardé en mémoire.
    session.expire_all()
    relue = lire_session(session, conversation.id)
    etat = etat_de(relue)

    assert etat.categorie_courante == "monitor"
    assert etat.budget_usd == Decimal("400.00")
    criteres = etat.criteres_de("monitor")
    assert [critere.champ for critere in criteres] == ["refresh_rate"]
    assert criteres[0].valeur == Decimal("144")
    assert criteres[0].importance.value == "bloquant"
    # `recherche_du_tour` n'est **pas** persistée, et c'est voulu : elle ne vit que dans
    # le tour. Un état relu la retrouverait armée et refuserait la première recherche du
    # tour suivant.
    assert etat.recherche_du_tour is None
    assert issue.etat.recherche_du_tour is not None


def test_le_tour_du_dernier_desserrage_survit_au_rechargement(session, depot_catalogue):
    """Sans lui, relancer la console rendrait le jeton de parole contournable.

    Le jeton compare `tour_du_dernier_desserrage` au numéro de tour courant. Si l'un des
    deux repartait de zéro au redémarrage, un client pourrait desserrer deux fois par
    message en relançant entre les deux.
    """
    conversation = creer_session(session)
    client = FauxClient(
        [
            message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(texte("C'est noté.")),
        ]
    )
    _jouer(session, conversation, client, depot_catalogue, "144 Hz, 400 $")

    # Second tour : le budget monte — c'est un desserrage, il consomme le jeton.
    client_2 = FauxClient(
        [
            message(
                appel_outil(
                    NOM_ENREGISTRER, {"categorie": "monitor", "budget_usd": "600"}, id="tu_2"
                )
            ),
            message(texte("Je monte le budget.")),
        ]
    )
    _jouer(session, conversation, client_2, depot_catalogue, "je peux monter à 600")

    session.expire_all()
    etat = etat_de(lire_session(session, conversation.id))

    assert etat.budget_usd == Decimal("600.00")
    assert etat.tour_du_dernier_desserrage is not None
    # Le desserrage a eu lieu au second tour client, dont le `numero` est supérieur à 1.
    assert etat.tour_du_dernier_desserrage > 1


def test_le_numero_de_tour_client_croit_malgre_les_lignes_de_tool_result(session, depot_catalogue):
    """⚠️ Les `tool_result` portent le rôle `user` : compter les lignes `user` serait faux.

    Le numéro vient de `max(numero) + 1`, ce qui le rend croissant, unique par session et
    stable au redémarrage — tout ce dont le jeton de parole a besoin (arbitrage 9).
    """
    conversation = creer_session(session)
    scenario = [
        message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
        message(texte("Noté.")),
    ]

    premier = prochain_numero(session, conversation.id)
    _jouer(session, conversation, FauxClient(scenario), depot_catalogue, "un écran 144 Hz")
    second = prochain_numero(session, conversation.id)

    assert premier == 1
    # 1 message client + assistant + tool_result + assistant = 4 lignes écrites.
    assert second == 5

    lignes = (
        session.query(TourConversation)
        .filter(TourConversation.session_id == conversation.id)
        .order_by(TourConversation.numero)
        .all()
    )
    assert [ligne.role for ligne in lignes] == ["user", "assistant", "user", "assistant"]
    assert [ligne.numero for ligne in lignes] == [1, 2, 3, 4]
    # Deux lignes portent le rôle `user` alors qu'il n'y a eu qu'**un** message client :
    # la seconde est le `tool_result`. C'est précisément ce qui rendrait faux un
    # compteur fondé sur le rôle.
    assert sum(1 for ligne in lignes if ligne.role == "user") == 2


def test_lhistorique_relu_reconstruit_les_messages_dans_lordre(session, depot_catalogue):
    """Les blocs sont relus **bruts** : c'est la raison d'être de la colonne.

    Aplatir en texte détruirait les `tool_use` et les `tool_result`, donc l'appairage que
    l'API exige au tour suivant et le contexte dont le validateur de l'étape 9 a besoin.
    """
    conversation = creer_session(session)
    _jouer(
        session,
        conversation,
        FauxClient(
            [
                message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
                message(texte("Noté.")),
            ]
        ),
        depot_catalogue,
        "un écran 144 Hz",
    )

    historique = historique_de(session, conversation.id)

    assert [entree["role"] for entree in historique] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert historique[1]["content"][0]["type"] == "tool_use"
    assert historique[1]["content"][0]["id"] == "tu_1"
    assert historique[2]["content"][0]["type"] == "tool_result"
    assert historique[2]["content"][0]["tool_use_id"] == "tu_1"


def test_un_second_tour_repart_de_letat_relu_et_non_dun_etat_vide(session, depot_catalogue):
    """La preuve que la console reprise retrouve les critères — la porte de sortie nº5.

    Le second tour n'enregistre **rien** : il cherche directement. Si l'état n'était pas
    relu, `search_products` échouerait sur `categorie_absente`.
    """
    conversation = creer_session(session)
    _jouer(
        session,
        conversation,
        FauxClient(
            [
                message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
                message(texte("Noté.")),
            ]
        ),
        depot_catalogue,
        "un écran 144 Hz à 400 $",
    )

    session.expire_all()
    reprise = lire_session(session, conversation.id)
    client = FauxClient(
        [
            message(appel_outil(NOM_RECHERCHER, id="tu_2")),
            message(texte("Voici.")),
        ]
    )
    issue = _jouer(session, reprise, client, depot_catalogue, "montre-moi")

    resultats = issue.tours[1].blocs
    assert resultats[0]["is_error"] is False
    assert issue.etat.categorie_courante == "monitor"
    assert issue.etat.budget_usd == Decimal("400.00")
