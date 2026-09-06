"""Les deux tables d'observation, écrites par le vrai `session.tour()`, dans son commit.

**Ce que ces tests couvrent et que `tests/test_observation.py` ne peut pas couvrir.** Les
tests unitaires du décorateur constatent qu'il compte ; ceux-ci constatent que ce qu'il
compte **arrive en base**, avec le bon `tour_client`, le bon `rang`, et **dans le même
commit** que la conversation. C'est le passage par Postgres qui les rend nécessaires : une
charge JSONB qui ne se sérialise pas, une contrainte qui refuse une valeur, un ordre qui
n'est pas celui qu'on croit — rien de tout cela ne se voit en mémoire.

⚠️ **Le test le plus important est celui de l'atomicité.** L'arbitrage 9 dit qu'un tour est
soit entièrement là, soit absent ; l'étape 23 y ajoute deux tables et doit le laisser vrai.
Un second commit pour l'observation aurait passé tous les autres tests de ce fichier.
"""

import pytest
from faux_client import FauxClient, appel_outil, message, texte
from scenarios import ECRAN_144, SYSTEME
from sqlalchemy import select

from outils_de_test import TOLERANCE
from raiyon.agent.client import EFFORT_NON_FIXE, ReponseLLM
from raiyon.agent.session import creer_session, tour
from raiyon.db.models import AppelModele, EvenementTour, TourConversation
from raiyon.observation import DISPLAY_PAR_DEFAUT, MODELE_INCONNU
from raiyon.tools.schema_outils import (
    NOM_ENREGISTRER,
    NOM_RECHERCHER,
    schema_des_outils,
)

pytestmark = pytest.mark.integration


def _jouer(base, conversation, client, depot, message_client="Bonjour"):
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
        max_regenerations=1,
        tolerance=TOLERANCE,
    )
    while True:
        try:
            next(generateur)
        except StopIteration as arret:
            return arret.value


PHRASE_LIVREE = "Voici trois écrans."
"""⚠️ **Volontairement sans un chiffre.** Le validateur de l'étape 9 refuse toute
affirmation que les `tool_result` ne fondent pas, et un texte refusé changerait le nombre
d'appels et d'événements que ces tests comptent. Ils portent sur l'observation, pas sur la
validation — celle-ci a ses propres fichiers."""


def _client_nominal() -> FauxClient:
    """Critères, recherche, phrase : trois appels, le chemin qu'on veut voir au tableau.

    ⚠️ `search_products` **ne prend aucun argument** : il lit l'état de la session
    (arbitrage C de l'étape 7). Lui en passer un fait refuser l'appel par le répartiteur,
    et la boucle repart pour une itération de plus."""
    return FauxClient(
        reponses=[
            message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(appel_outil(NOM_RECHERCHER, id="tu_2")),
            message(texte(PHRASE_LIVREE)),
        ]
    )


def _appels(base, identifiant):
    return list(
        base.scalars(
            select(AppelModele)
            .where(AppelModele.session_id == identifiant)
            .order_by(AppelModele.tour_client, AppelModele.iteration)
        )
    )


def _evenements(base, identifiant):
    return list(
        base.scalars(
            select(EvenementTour)
            .where(EvenementTour.session_id == identifiant)
            .order_by(EvenementTour.tour_client, EvenementTour.rang)
        )
    )


def test_un_tour_ecrit_ses_appels_et_ses_evenements(session, depot_catalogue):
    """Le cas nominal : trois appels, et les événements dans l'ordre où ils sont sortis."""
    conversation = creer_session(session)
    identifiant = conversation.id

    _jouer(session, conversation, _client_nominal(), depot_catalogue)

    appels = _appels(session, identifiant)
    assert [appel.iteration for appel in appels] == [1, 2, 3]
    assert {appel.tour_client for appel in appels} == {1}

    genres = [evenement.genre for evenement in _evenements(session, identifiant)]
    assert genres == ["criteria_updated", "products_found", "message"]


def test_le_rang_repart_de_un_a_chaque_tour_client(session, depot_catalogue):
    """`rang` est **par tour**, pas par session : c'est ce que la timeline lit.

    Le couple `(tour_client, rang)` est unique et croissant dans le tour ; un rang global
    obligerait le tableau de bord à soustraire pour retrouver la place d'un événement dans
    son tour.
    """
    conversation = creer_session(session)
    identifiant = conversation.id

    _jouer(session, conversation, _client_nominal(), depot_catalogue, "Bonjour")
    _jouer(
        session,
        conversation,
        FauxClient(reponses=[message(texte("Le premier reste mon conseil."))]),
        depot_catalogue,
        "Et sinon ?",
    )

    evenements = _evenements(session, identifiant)
    par_tour: dict[int, list[int]] = {}
    for evenement in evenements:
        par_tour.setdefault(evenement.tour_client, []).append(evenement.rang)

    assert list(par_tour.values()) == [[1, 2, 3], [1]]
    # ⚠️ Les deux tours ne portent pas des numéros consécutifs : le second suit les lignes
    # de `tool_result` écrites par le premier (ici 1 puis 7, six lignes ayant été écrites).
    # La valeur exacte n'est pas assertée — elle dépend du scénario, alors que la propriété
    # qui compte est que `tour_client` **croît** sans que `rang` en hérite.
    premier, second = sorted(par_tour)
    assert premier == 1
    assert second > premier + 1


def test_les_colonnes_de_configuration_sont_remplies(session, depot_catalogue):
    """⚠️ **Ce qui rendra l'arbitrage `effort` décidable sur du trafic réel.**

    Le faux client ne déclare rien : on vérifie donc les valeurs honnêtes — `defaut` pour
    un effort qu'on n'a pas envoyé, le défaut de l'API pour un `display` que personne n'a
    demandé, et `inconnu` pour un modèle contre lequel aucun appel n'a eu lieu.
    """
    conversation = creer_session(session)
    identifiant = conversation.id

    _jouer(session, conversation, _client_nominal(), depot_catalogue)

    appel = _appels(session, identifiant)[0]
    assert appel.effort == EFFORT_NON_FIXE
    assert appel.display == DISPLAY_PAR_DEFAUT
    assert appel.modele == MODELE_INCONNU
    assert appel.empreinte_systeme
    assert appel.stop_reason == "tool_use"


def test_un_tour_qui_plante_necrit_ni_appel_ni_evenement(session, depot_catalogue):
    """⚠️ **L'atomicité de l'arbitrage 9, étendue aux deux tables neuves.**

    Le premier appel aboutit — donc une ligne d'observation existe déjà en mémoire — et le
    second lève. Rien ne doit atteindre la base : ni le message du client, ni les appels,
    ni les événements. Un second commit pour l'observation ferait échouer ce test seul, ce
    qui est exactement pourquoi il est écrit.
    """

    class ClientQuiCasseAuSecond(FauxClient):
        def repondre(self, **kwargs) -> ReponseLLM:
            if self.nombre_dappels >= 1:
                raise TimeoutError("l'API n'a pas répondu")
            return super().repondre(**kwargs)

    conversation = creer_session(session)
    identifiant = conversation.id
    session.commit()

    with pytest.raises(TimeoutError):
        _jouer(
            session,
            conversation,
            ClientQuiCasseAuSecond(reponses=[message(appel_outil(NOM_ENREGISTRER, ECRAN_144))]),
            depot_catalogue,
        )
    session.rollback()

    assert _appels(session, identifiant) == []
    assert _evenements(session, identifiant) == []
    assert (
        session.scalars(
            select(TourConversation).where(TourConversation.session_id == identifiant)
        ).all()
        == []
    )


def test_supprimer_une_session_supprime_ses_appels_et_ses_evenements(session, depot_catalogue):
    """La cascade, comme sur `tours_conversation` : l'observation ne survit pas à sa session."""
    conversation = creer_session(session)
    identifiant = conversation.id

    _jouer(session, conversation, _client_nominal(), depot_catalogue)
    session.delete(conversation)
    session.flush()

    assert _appels(session, identifiant) == []
    assert _evenements(session, identifiant) == []


def test_la_charge_dun_evenement_revient_du_jsonb_identique(session, depot_catalogue):
    """Le JSONB doit rendre ce qu'on lui a donné — c'est le passage que la mémoire ne teste pas."""
    from raiyon.agent.evenements import Texte
    from raiyon.observation import evenement_journalise

    conversation = creer_session(session)
    identifiant = conversation.id

    _jouer(session, conversation, _client_nominal(), depot_catalogue)

    (rendu,) = [
        evenement for evenement in _evenements(session, identifiant) if evenement.genre == "message"
    ]
    assert (rendu.genre, rendu.charge) == evenement_journalise(Texte(PHRASE_LIVREE))
