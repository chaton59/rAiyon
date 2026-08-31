"""L'enchaînement : appels, état, refus, garde d'itérations.

Chaque test est nommé d'après **ce qu'il empêche**, pas d'après ce qu'il exerce. Le plus
important du fichier est `test_deux_recherches_sur_deux_categories...` : il échoue si
l'état n'est pas réenchaîné entre deux `tool_use` d'un même message assistant, et c'est
la seule façon de constater ce défaut avant l'étape 12 — une cassette ne le verrait pas.
"""

import structlog
from faux_client import FauxClient, appel_outil, message, texte, verifier_appairage
from scenarios import ECRAN_144, etat_ecran, jouer

from outils_de_test import TOLERANCE, ecrans
from raiyon.agent.boucle import PHRASE_DE_REPLI
from raiyon.agent.evenements import (
    CriteresMisAJour,
    ProduitsTrouves,
    Repli,
    Sondage,
    Texte,
)
from raiyon.tools.erreurs import CodeRefus
from raiyon.tools.repartiteur import ContexteOutils
from raiyon.tools.schema_outils import (
    NOM_ENREGISTRER,
    NOM_QUESTION,
    NOM_RECHERCHER,
    NOM_SONDER,
)

# --------------------------------------------------------------------------- #
# 1 — Un message sans outil
# --------------------------------------------------------------------------- #


def test_un_message_sans_outil_rend_un_texte_et_un_seul_appel_api(contexte, outils):
    """Le cas le plus simple, et celui qui coûterait le plus cher s'il bouclait."""
    client = FauxClient([message(texte("Bonjour, que cherchez-vous ?"))])

    evenements, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 1
    assert evenements == [Texte("Bonjour, que cherchez-vous ?")]
    assert issue.outils_appeles == ()
    assert issue.iterations == 1
    # Un seul tour produit : le message assistant. Aucun `tool_result` à écrire.
    assert [tour.role for tour in issue.tours] == ["assistant"]


# --------------------------------------------------------------------------- #
# 2 — L'enchaînement nominal : enregistrer, chercher, rédiger
# --------------------------------------------------------------------------- #


def test_enregistrer_puis_chercher_fait_remonter_les_produits(contexte, outils):
    client = FauxClient(
        [
            message(texte("Je note."), appel_outil(NOM_ENREGISTRER, ECRAN_144)),
            message(appel_outil(NOM_RECHERCHER)),
            message(texte("Voici trois écrans.")),
        ]
    )

    evenements, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 3
    types = [type(evenement) for evenement in evenements]
    assert types == [Texte, CriteresMisAJour, ProduitsTrouves, Texte]

    criteres = evenements[1]
    assert criteres.categorie == "monitor"
    assert [critere.champ for critere in criteres.criteres] == ["refresh_rate"]

    produits = evenements[2]
    assert len(produits.resultat.produits) == 3
    # L'état sort de la boucle enrichi : c'est lui que `session.py` persistera.
    assert issue.etat.categorie_courante == "monitor"
    assert issue.etat.budget_usd is not None


# --------------------------------------------------------------------------- #
# 3 — Deux `tool_use` dans un même message : le réenchaînement
# --------------------------------------------------------------------------- #


def test_deux_outils_dans_un_message_le_second_voit_letat_du_premier(contexte, outils):
    """`probe_catalog` n'a de catégorie à sonder que si l'enregistrement a pris effet.

    Sans réenchaînement, le second appel partirait d'un état sans catégorie et
    recevrait `categorie_absente` — le test le constate par l'événement, pas par le log.
    """
    client = FauxClient(
        [
            message(
                appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1"),
                appel_outil(NOM_SONDER, {"champs": ["refresh_rate"]}, id="tu_2"),
            ),
            message(texte("32 candidats.")),
        ]
    )

    evenements, _ = jouer(client, contexte, outils)

    assert [type(evenement) for evenement in evenements] == [
        CriteresMisAJour,
        Sondage,
        Texte,
    ]
    assert evenements[1].categorie == "monitor"
    assert evenements[1].dans_le_budget == 3


def test_les_deux_tool_result_partent_dans_un_seul_message_dans_lordre(contexte, outils):
    client = FauxClient(
        [
            message(
                appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1"),
                appel_outil(NOM_QUESTION, id="tu_2"),
            ),
            message(texte("Fini.")),
        ]
    )

    _, issue = jouer(client, contexte, outils)

    resultats = issue.tours[1]
    assert resultats.role == "user"
    assert [bloc["tool_use_id"] for bloc in resultats.blocs] == ["tu_1", "tu_2"]


# --------------------------------------------------------------------------- #
# 4 — Le test le plus important de l'étape
# --------------------------------------------------------------------------- #


def test_deux_recherches_sur_deux_categories_dans_un_message_la_seconde_est_refusee(depot, outils):
    """**Il échoue si l'état n'est pas réenchaîné**, et c'est sa raison d'être.

    `rechercher_produits` pose `recherche_du_tour` dans l'**état qu'il rend**. Une boucle
    qui repartirait de l'état d'avant pour le `tool_use` suivant ne verrait rien, la garde
    « un tour, une catégorie » ne se déclencherait jamais, et l'agent servirait la
    « config gaming » que §8 met hors périmètre — sans que rien ne le signale.
    """
    depot.produits = [*ecrans(2, refresh_rate=165)]
    contexte = ContexteOutils(depot=depot, tour_client=1, tolerance=TOLERANCE)
    client = FauxClient(
        [
            message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_0")),
            message(
                appel_outil(NOM_RECHERCHER, id="tu_1"),
                appel_outil(NOM_ENREGISTRER, {"categorie": "cpu"}, id="tu_2"),
                appel_outil(NOM_RECHERCHER, id="tu_3"),
            ),
            message(texte("Un composant à la fois.")),
        ]
    )

    _, issue = jouer(client, contexte, outils)

    resultats = issue.tours[3].blocs
    assert [bloc["tool_use_id"] for bloc in resultats] == ["tu_1", "tu_2", "tu_3"]
    # Le premier a cherché, le troisième est refusé — et par le bon code.
    assert resultats[0]["is_error"] is False
    assert resultats[2]["is_error"] is True
    assert CodeRefus.DEUX_CATEGORIES_DANS_UN_TOUR.value in resultats[2]["content"]


# --------------------------------------------------------------------------- #
# 8, 9 — Les entrées invalides ne font pas tomber le tour
# --------------------------------------------------------------------------- #


def test_arguments_invalides_rendent_un_tool_result_en_erreur_et_la_boucle_continue(
    contexte, outils
):
    """Une propriété inventée et une valeur illisible : le modèle doit pouvoir corriger."""
    client = FauxClient(
        [
            message(appel_outil(NOM_ENREGISTRER, {**ECRAN_144, "urgence": "haute"}, id="tu_1")),
            message(
                appel_outil(
                    NOM_ENREGISTRER,
                    {
                        "categorie": "monitor",
                        "criteres": [
                            {
                                "champ": "refresh_rate",
                                "operateur": "au_moins",
                                "valeur": "beaucoup",
                                "importance": "souhait",
                            }
                        ],
                    },
                    id="tu_2",
                )
            ),
            message(texte("Je reformule.")),
        ]
    )

    evenements, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 3
    assert issue.tours[1].blocs[0]["is_error"] is True
    assert "urgence" in issue.tours[1].blocs[0]["content"]
    assert issue.tours[3].blocs[0]["is_error"] is True
    # Aucun événement structuré : un refus est un échange avec le modèle, pas avec le
    # client. Seul le texte final remonte.
    assert evenements == [Texte("Je reformule.")]


def test_nom_doutil_inconnu_rend_un_tool_result_en_erreur_code_outil_inconnu(contexte, outils):
    """Le mode `strict` garantit les noms d'outils — mais le repli de l'arbitrage 11
    retire précisément ce drapeau, donc la boucle ne peut pas s'y fier."""
    client = FauxClient(
        [
            message(appel_outil("browse_the_web", {"url": "…"}, id="tu_1")),
            message(texte("Pardon, je reprends.")),
        ]
    )

    _, issue = jouer(client, contexte, outils)

    bloc = issue.tours[1].blocs[0]
    assert bloc["is_error"] is True
    assert CodeRefus.OUTIL_INCONNU.value in bloc["content"]


# --------------------------------------------------------------------------- #
# 10 — Le garde-fou anti-boucle
# --------------------------------------------------------------------------- #


def test_max_iterations_clot_le_tour_par_un_repli_et_naappelle_pas_une_fois_de_plus(
    contexte, outils
):
    """Un modèle qui redit la même chose indéfiniment. La borne est technique (§3.9).

    ⚠️ Le journal se capture par `structlog.testing.capture_logs`, pas par `caplog` : le
    projet loggue en structlog, qui écrit sur la sortie standard sans passer par le
    `logging` de la bibliothèque standard. Un `caplog` vide aurait fait croire à un
    `WARNING` absent alors qu'il était bien émis.
    """
    client = FauxClient([message(appel_outil(NOM_QUESTION, id="tu_boucle"))])

    with structlog.testing.capture_logs() as journal:
        evenements, issue = jouer(client, contexte, outils, etat=etat_ecran(), max_iterations=3)

    assert client.nombre_dappels == 3
    assert issue.iterations == 3
    repli = evenements[-1]
    assert isinstance(repli, Repli)
    assert repli.message == PHRASE_DE_REPLI
    assert repli.outils_appeles == (NOM_QUESTION, NOM_QUESTION, NOM_QUESTION)
    alerte = [ligne for ligne in journal if ligne["event"] == "boucle.max_iterations"]
    assert len(alerte) == 1
    assert alerte[0]["log_level"] == "warning"
    assert alerte[0]["iterations"] == 3
    assert alerte[0]["outils_appeles"] == [NOM_QUESTION] * 3

    # Les `tool_result` de la dernière itération sont écrits : c'est ce qui fait que
    # le tour client suivant repartira d'un historique que l'API accepte.
    assert [tour.role for tour in issue.tours] == ["assistant", "user"] * 3


def test_la_derniere_iteration_a_bien_ses_tool_result_apparies(contexte, outils):
    """Le corollaire du précédent, formulé comme une propriété — voir `verifier_appairage`."""
    client = FauxClient([message(appel_outil(NOM_QUESTION, id="tu_boucle"))])

    _, issue = jouer(client, contexte, outils, etat=etat_ecran(), max_iterations=2)

    verifier_appairage(issue.tours)


# --------------------------------------------------------------------------- #
# 12 — La garantie du cache
# --------------------------------------------------------------------------- #


def test_le_prefixe_est_identique_entre_deux_appels_du_meme_tour(contexte, outils):
    """Le préfixe mis en cache est `tools` + `system` : il doit être identique octet pour
    octet d'un appel à l'autre (arbitrage 7).

    C'est ce qui interdit de mettre la date, l'état de session, le numéro de tour ou la
    catégorie courante dans le prompt système. Le test le constate au lieu de le rappeler
    en commentaire.
    """
    client = FauxClient(
        [
            message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(appel_outil(NOM_RECHERCHER, id="tu_2")),
            message(texte("Voilà.")),
        ]
    )

    jouer(client, contexte, outils)

    assert client.nombre_dappels == 3
    premiers = client.appels[0]
    for appel in client.appels[1:]:
        assert appel.systeme == premiers.systeme
        assert appel.outils == premiers.outils


def test_lhistorique_sallonge_a_chaque_appel_mais_le_prefixe_ne_bouge_pas(contexte, outils):
    """La contre-épreuve : sans elle, un client qui n'enverrait rien passerait le test
    précédent."""
    client = FauxClient(
        [
            message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(texte("Voilà.")),
        ]
    )

    jouer(client, contexte, outils)

    longueurs = [len(appel.messages) for appel in client.appels]
    assert longueurs == [1, 3]  # client, puis client + assistant + tool_result
