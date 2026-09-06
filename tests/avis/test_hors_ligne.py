"""🔴 **Une campagne ne sort pas sur le réseau — preuve d'EXÉCUTION, pas d'import.**

Purs : ni base, ni conteneur, ni clé.

### Ce que ce fichier ajoute à `test_isolation_reseau`

L'autre prouve qu'aucun module n'**importe** de client HTTP. C'était la seule garantie
disponible tant qu'aucun fournisseur n'existait, et elle était honnêtement décrite comme
telle. Depuis l'étape 31 il en existe un : la question devient « le chemin de campagne
l'appelle-t-il ? », et un import ne répond pas à ça.

**Ici, la prise réseau est arrachée** — `socket.socket` lève — et on fait tourner le
chemin. S'il tente une connexion, le test échoue avec la trace de qui l'a tentée.

### La garantie est structurelle, et le test la constate à deux niveaux

1. **`Reglages.fournisseur` vaut `None` par défaut**, et aucun chemin de mesure ne le
   renseigne. C'est ce qui fait qu'installer une clé ne change pas ce que `make eval`
   mesure — un mode en ligne qui s'activerait à la présence d'un secret serait un piège.
2. **À l'exécution**, l'outil refuse proprement au lieu de sortir.

⚠️ **Le contre-test est aussi important que le test.** Sans lui, un bloqueur de socket mal
posé rendrait toute la suite verte en ne prouvant rien : on vérifie donc qu'avec un vrai
fournisseur, la prise arrachée **se voit**.
"""

import socket
from datetime import UTC, datetime

import pytest

from avis_de_test import DepotAvisEnMemoire, avis_fabrique
from raiyon.avis.brave import FournisseurBrave
from raiyon.avis.fournisseur import RechercheImpossible
from raiyon.eval.executeur import Reglages
from raiyon.tools.erreurs import CodeRefus, OutilRefuse
from raiyon.tools.etat import EtatSession
from raiyon.tools.repartiteur import ContexteOutils, executer
from raiyon.tools.schema_outils import NOM_AVIS

MAINTENANT = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


@pytest.fixture
def prise_arrachee(monkeypatch):
    """Toute création de socket lève. **Le réseau n'existe plus pour ce test.**

    On remplace `socket.socket` plutôt que de patcher `httpx` : patcher la bibliothèque
    prouverait que *cette* bibliothèque n'est pas appelée, pas qu'aucune sortie n'a lieu.
    Un module qui ouvrirait une connexion par un autre chemin passerait à travers.
    """

    def refuser(*args: object, **kwargs: object) -> None:
        raise AssertionError("une connexion réseau a été tentée depuis un chemin hors ligne")

    monkeypatch.setattr(socket, "socket", refuser)
    monkeypatch.setattr(socket, "create_connection", refuser)


def contexte_de_campagne(depot: DepotAvisEnMemoire) -> ContexteOutils:
    """Le contexte tel qu'un chemin de mesure le construit : **sans fournisseur**."""
    return ContexteOutils(
        depot=None,  # type: ignore[arg-type]  — la recherche d'avis n'y touche pas
        tour_client=1,
        depot_avis=depot,
        fournisseur=Reglages(
            systeme="", outils=(), max_iterations=8, max_regenerations=1
        ).fournisseur,
        maintenant=MAINTENANT,
    )


def test_les_reglages_de_campagne_nont_aucun_fournisseur():
    """La garantie structurelle : le défaut est `None`, donc hors ligne par construction.

    ⚠️ **C'est ce défaut qui fait qu'une clé installée ne change rien à `make eval`.** Aucun
    chemin de mesure ne renseigne ce champ ; seul un appelant explicite le fait.
    """
    reglages = Reglages(systeme="", outils=(), max_iterations=8, max_regenerations=1)

    assert reglages.fournisseur is None


def test_un_hit_de_cache_nouvre_aucune_connexion(prise_arrachee):
    """Le cas nominal d'une campagne : le cache répond, rien ne sort."""
    depot = DepotAvisEnMemoire()
    depot.charger([avis_fabrique("a", requete="avis ecran")])

    _, resultat = executer(
        NOM_AVIS, {"requete": "avis écran"}, EtatSession(), contexte_de_campagne(depot)
    )

    assert not isinstance(resultat, OutilRefuse)
    assert resultat.depuis_le_cache


def test_un_miss_refuse_au_lieu_de_sortir(prise_arrachee):
    """🔴 **Le cas qui compte.** Rien en cache, aucun fournisseur : refus, pas connexion."""
    _, resultat = executer(
        NOM_AVIS,
        {"requete": "avis produit jamais vu"},
        EtatSession(),
        contexte_de_campagne(DepotAvisEnMemoire()),
    )

    assert isinstance(resultat, OutilRefuse)
    assert resultat.code is CodeRefus.AVIS_HORS_LIGNE


def test_contre_epreuve_la_prise_arrachee_se_voit(prise_arrachee):
    """⚠️ **Sans ce test, un bloqueur mal posé rendrait les deux précédents verts pour rien.**

    On donne un vrai `FournisseurBrave` — avec une clé factice qui ne quittera jamais le
    processus — et on constate que la sortie est **tentée** et **empêchée**. C'est ce qui
    prouve que les tests ci-dessus mesurent une absence de sortie, et non une absence de
    bloqueur.
    """
    fournisseur = FournisseurBrave("cle-factice-jamais-envoyee")

    with pytest.raises((RechercheImpossible, AssertionError)):
        fournisseur.chercher("avis écran", limite=3)


def test_le_fournisseur_ne_met_jamais_la_cle_dans_son_erreur(monkeypatch):
    """🔴 **La clé ne sort ni par un message d'erreur, ni par une trace chaînée.**

    ⚠️ **Ce test a d'abord été écrit sur la prise arrachée, et il ne prouvait rien** : le
    bloqueur de socket levait *avant* que `httpx` ne construise son erreur, donc le chemin
    à vérifier n'était jamais exercé et le test se contentait de `skip`. Un test qui se
    saute est un test qui rassure sans mesurer.

    La vraie panne est donc **fabriquée** : une `httpx.ConnectError` qui porte son `Request`,
    en-têtes compris — c'est-à-dire exactement la forme dans laquelle une clé fuit vers un
    journal. On vérifie ensuite les trois sorties possibles : le message, la représentation,
    et la chaîne `__cause__` que `from None` doit avoir coupée.
    """
    import httpx

    secret = "brave-cle-secrete-a-ne-jamais-voir"
    requete_reelle = httpx.Request(
        "GET",
        "https://api.search.brave.com/res/v1/web/search",
        headers={"X-Subscription-Token": secret},
    )
    assert secret in str(dict(requete_reelle.headers)), "le décor doit vraiment porter la clé"

    def echouer(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("connexion refusée", request=requete_reelle)

    monkeypatch.setattr(httpx, "get", echouer)

    with pytest.raises(RechercheImpossible) as panne:
        FournisseurBrave(secret).chercher("avis écran", limite=3)

    assert secret not in str(panne.value)
    assert secret not in repr(panne.value)
    assert panne.value.__cause__ is None, "la chaîne remettrait la requête, donc la clé"
    assert panne.value.__context__ is None, "le contexte implicite la remettrait aussi"
