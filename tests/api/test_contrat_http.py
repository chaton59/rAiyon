"""Ce qui se vérifie sans base : le corps de requête, la clé de verrou, l'ordre des routes.

Ces trois-là auraient pu vivre dans `tests/integration/test_api.py` — ils y auraient été
vrais, et ils y auraient coûté un conteneur pour rien. Les descendre ici est le geste que
§3.16 décrit sur le moteur : **ce qui ne dépend pas de la base ne doit pas en dépendre**.

Le troisième mérite un mot. `raiyon.api.app` s'importe **sans clé API et sans base** : le
client Anthropic et le moteur SQLAlchemy ne sont construits qu'au `lifespan`. C'est ce qui
permet de vérifier ici l'ordre du montage `/`, dont le défaut est silencieux — un
`StaticFiles` monté trop tôt ne lève pas, il rend simplement un 404 de fichier sur
`/health`.
"""

import uuid

import pytest
from pydantic import ValidationError

from raiyon.api.schemas import LONGUEUR_MAX_MESSAGE, MessageEntrant
from raiyon.api.verrou import cle_de

# --------------------------------------------------------------------------- #
# Le corps de requête — la moitié des 422 se joue ici, sans serveur
# --------------------------------------------------------------------------- #


def test_un_message_ordinaire_passe():
    assert MessageEntrant(message="un écran 144 Hz").message == "un écran 144 Hz"


@pytest.mark.parametrize("corps", [{}, {"message": ""}])
def test_un_corps_sans_message_est_refuse(corps):
    """Champ absent et chaîne vide sont deux façons de ne rien dire, et toutes deux
    coûteraient un appel API pour un tour sans contenu."""
    with pytest.raises(ValidationError):
        MessageEntrant(**corps)


def test_un_champ_invente_est_refuse():
    """`extra="forbid"`, comme `_Arguments` dans la couche outils : un champ inventé est
    une erreur, pas un oubli. Sans lui, `{"messsage": "..."}` donnerait un 422 sur le
    champ manquant — correct, mais qui ne dit pas où est la faute de frappe."""
    with pytest.raises(ValidationError):
        MessageEntrant(message="salut", temperature=0)


def test_un_message_demesure_est_refuse():
    """Starlette ne borne pas la taille d'un corps, et rien d'autre sur le chemin ne le
    ferait : sans cette borne, le message serait persisté **puis** envoyé au modèle."""
    with pytest.raises(ValidationError):
        MessageEntrant(message="a" * (LONGUEUR_MAX_MESSAGE + 1))

    assert MessageEntrant(message="a" * LONGUEUR_MAX_MESSAGE).message


# --------------------------------------------------------------------------- #
# La clé de verrou — pure arithmétique, et deux propriétés qui comptent
# --------------------------------------------------------------------------- #


def test_la_cle_de_verrou_est_deterministe():
    """Un tour et le tour suivant doivent viser **le même** verrou : une clé qui
    dépendrait d'autre chose que de l'UUID ne protégerait rien."""
    identifiant = uuid.UUID("3f2504e0-4f89-41d3-9a0c-0305e82c3301")

    assert cle_de(identifiant) == cle_de(identifiant)


def test_deux_sessions_distinctes_ont_des_cles_distinctes():
    """La troncature à 64 bits autorise une collision — voir la docstring de `verrou.py`,
    qui en tarife la conséquence. Ce test constate seulement que la fonction ne les
    fabrique pas elle-même, par exemple en ne lisant que les octets de version."""
    cles = {cle_de(uuid.uuid4()) for _ in range(2000)}

    assert len(cles) == 2000


def test_la_cle_tient_dans_un_bigint_postgres():
    """⚠️ `pg_try_advisory_xact_lock` prend un **entier signé** sur 64 bits. Une clé non
    signée dépasserait la borne haute une fois sur deux, et Postgres refuserait l'appel —
    donc un tour sur deux échouerait, ce qui est le genre de défaut qu'on met une journée
    à attribuer."""
    borne = 2**63

    for _ in range(2000):
        cle = cle_de(uuid.uuid4())
        assert -borne <= cle < borne


# --------------------------------------------------------------------------- #
# L'ordre des routes — le défaut silencieux de l'arbitrage L
# --------------------------------------------------------------------------- #


def test_le_montage_du_front_vient_apres_les_routes():
    """⚠️ **Un `StaticFiles` monté sur `/` avant les routes les avale**, sans erreur :
    `/health` rendrait un 404 de fichier statique, et le diagnostic prendrait un moment
    parce que la route existe bel et bien.

    Le test s'importe sans clé et sans base — le client Anthropic et le moteur SQLAlchemy
    ne sont construits qu'au `lifespan`.
    """
    from raiyon.api.app import CHEMIN_DU_MONTAGE, routes_publiques

    chemins = list(routes_publiques())
    metier = [
        "/sessions",
        "/sessions/{identifiant}/messages",
        "/sessions/{identifiant}",
        "/health",
    ]

    assert chemins[-1] == CHEMIN_DU_MONTAGE, "le front doit être monté en dernier"
    for chemin in metier:
        assert chemin in chemins, f"{chemin} n'est plus déclarée"
        assert chemins.index(chemin) < chemins.index(CHEMIN_DU_MONTAGE), (
            f"{chemin} est déclarée après le montage / : elle sera avalée par StaticFiles"
        )
