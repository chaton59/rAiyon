"""Le branchement du validateur dans la boucle : régénération, repli, historique valide.

Ce fichier ne teste pas les règles — `tests/validateur/` s'en charge, sans clé et sans
base. Il teste ce que la boucle **fait** d'un verdict : combien d'appels API elle
consomme, dans quel ordre elle pose les blocs, et ce qu'elle laisse derrière elle.

Le test le plus important est `test_le_texte_nest_jamais_emis_avant_detre_valide` :
c'est l'arbitrage A pris au mot. Une seule phrase fausse partie au client rendrait toute
l'étape décorative.
"""

import structlog
from faux_client import FauxClient, appel_outil, message, texte, verifier_appairage
from scenarios import ECRAN_144, jouer

from raiyon.agent.evenements import MotifDeRepli, ProduitsTrouves, Repli, Texte, TexteRejete
from raiyon.tools.schema_outils import NOM_ENREGISTRER, NOM_RECHERCHER
from raiyon.validateur.regles import CodeGrief

INVENTE = "Je vous conseille le monitor-00000000ff, à 259,99 $."
"""Un identifiant au bon format qu'aucune recherche n'a rendu, et un prix venu de nulle
part. Deux règles mordent, et c'est voulu : le message de reprise doit porter les deux."""

HONNETE = "Dites-moi plutôt pour quel usage, et je cherche."
"""Aucun chiffre, aucun identifiant : rien à vérifier, donc rien à reprocher."""


# --------------------------------------------------------------------------- #
# 1 — Le cas nominal : un texte valide ne coûte rien
# --------------------------------------------------------------------------- #


def test_un_texte_valide_part_au_client_sans_appel_supplementaire(contexte, outils):
    """Le validateur est un contrôle, pas une étape : il ne consomme aucun appel API."""
    client = FauxClient([message(texte(HONNETE))])

    evenements, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 1
    assert evenements == [Texte(HONNETE)]
    assert issue.iterations == 1


# --------------------------------------------------------------------------- #
# 2 — Une régénération, et une seule
# --------------------------------------------------------------------------- #


def test_un_texte_invalide_est_rejete_puis_regenere_en_deux_appels(contexte, outils):
    """**Deux appels API, pas trois.** Le budget de régénération est de un.

    C'est la propriété qui se compte, et la seule qui borne le coût du mécanisme : un
    validateur qui redemanderait jusqu'à satisfaction transformerait une hallucination
    en facture.
    """
    client = FauxClient([message(texte(INVENTE)), message(texte(HONNETE))])

    evenements, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 2
    assert [type(evenement) for evenement in evenements] == [TexteRejete, Texte]
    assert evenements[1] == Texte(HONNETE)
    assert issue.iterations == 2


def test_le_texte_rejete_porte_les_codes_et_le_numero_de_tentative(contexte, outils):
    """`TexteRejete` n'est pas du confort : sans lui, l'étape 12 devrait deviner un taux
    qu'on peut compter, et `--trace` ne montrerait pas qu'une régénération a eu lieu."""
    client = FauxClient([message(texte(INVENTE)), message(texte(HONNETE))])

    evenements, _ = jouer(client, contexte, outils)

    rejet = evenements[0]
    assert rejet.tentative == 1
    assert {grief.code for grief in rejet.griefs} == {
        CodeGrief.ID_INCONNU,
        CodeGrief.MONTANT_NON_FOURNI,
    }


def test_le_message_fautif_reste_dans_lhistorique_avec_le_grief_a_sa_suite(contexte, outils):
    """**Le retirer casserait l'appairage et rendrait le grief incompréhensible.**

    Le modèle voit donc sa propre sortie rejetée au tour suivant. C'est acceptable, et
    ça se dit : c'est le prix de l'invariant « chaque `tool_use` a son `tool_result` ».
    """
    client = FauxClient([message(texte(INVENTE)), message(texte(HONNETE))])

    _, issue = jouer(client, contexte, outils)

    assert INVENTE in str(issue.tours[0].blocs)
    reprise = issue.tours[1]
    assert reprise.role == "user"
    assert reprise.blocs[-1]["type"] == "text"
    assert "monitor-00000000ff" in reprise.blocs[-1]["text"]


# --------------------------------------------------------------------------- #
# 3 — Deux échecs : le repli, et le tour est clos
# --------------------------------------------------------------------------- #


def test_deux_echecs_closent_le_tour_par_un_repli_de_motif_validation(contexte, outils):
    """Aucun troisième appel : après deux refus, c'est le code qui rédige (§3.11 nº3)."""
    client = FauxClient([message(texte(INVENTE))])

    evenements, issue = jouer(client, contexte, outils)

    assert client.nombre_dappels == 2
    repli = evenements[-1]
    assert isinstance(repli, Repli)
    assert repli.motif is MotifDeRepli.VALIDATION
    assert issue.iterations == 2


def test_le_texte_nest_jamais_emis_avant_detre_valide(contexte, outils):
    """**L'arbitrage A pris au mot.** Sur un scénario qui échoue deux fois, aucun `Texte`.

    Si cette assertion tombait, tout le reste de l'étape serait décoratif : le client
    aurait lu la phrase que le validateur refuse, et la corriger après coup serait §2
    pris à l'envers.
    """
    client = FauxClient([message(texte(INVENTE))])

    evenements, _ = jouer(client, contexte, outils)

    assert not [evenement for evenement in evenements if isinstance(evenement, Texte)]


def test_un_repli_de_validation_est_journalise_avec_ses_codes(contexte, outils):
    """`caplog` ne voit rien de ce que loggue le projet (structlog) — leçon de l'étape 8."""
    client = FauxClient([message(texte(INVENTE))])

    with structlog.testing.capture_logs() as journal:
        jouer(client, contexte, outils)

    rejets = [ligne for ligne in journal if ligne["event"] == "boucle.texte_rejete"]
    assert [ligne["log_level"] for ligne in rejets] == ["warning", "warning"]
    assert rejets[-1]["consequence"] == "repli sur template"


# --------------------------------------------------------------------------- #
# 4 — Le message fautif portait des `tool_use`
# --------------------------------------------------------------------------- #


def test_les_tool_result_precedent_le_grief_dans_le_bloc_de_reprise(contexte, outils):
    """**L'API exige les `tool_result` appairés avant tout autre contenu utilisateur.**

    C'est ce qui rend la régénération possible quand le message fautif portait aussi des
    `tool_use` — et c'est la raison pour laquelle le grief voyage dans le même bloc
    `user` que les résultats, après eux, plutôt que dans un message à lui.
    """
    client = FauxClient(
        [
            message(texte(INVENTE), appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(texte(HONNETE)),
        ]
    )

    _, issue = jouer(client, contexte, outils)

    reprise = issue.tours[1].blocs
    assert [bloc["type"] for bloc in reprise] == ["tool_result", "text"]
    assert reprise[0]["tool_use_id"] == "tu_1"
    verifier_appairage(issue.tours)


def test_lappairage_reste_vert_meme_quand_le_repli_clot_le_tour(contexte, outils):
    """L'assertion générique de l'étape 8, appliquée au chemin le plus tordu de l'étape 9.

    Un `tool_use` laissé orphelin ne casse pas le tour courant : il casse **le suivant**,
    et le message d'erreur parlera d'un identifiant de bloc.
    """
    client = FauxClient(
        [message(texte(INVENTE), appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1"))]
    )

    _, issue = jouer(client, contexte, outils)

    verifier_appairage(issue.tours)


def test_les_evenements_doutils_partent_meme_quand_le_texte_est_rejete(contexte, outils):
    """Le panneau de §3.12 n'a pas à mentir parce que la prose ment.

    Les outils ont tourné, l'état a changé, les produits existent : les cacher
    donnerait au client une vue plus fausse que celle qu'on refuse.
    """
    client = FauxClient(
        [
            message(texte(INVENTE), appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(appel_outil(NOM_RECHERCHER, id="tu_2")),
            message(texte(HONNETE)),
        ]
    )

    evenements, _ = jouer(client, contexte, outils)

    assert any(isinstance(evenement, ProduitsTrouves) for evenement in evenements)


# --------------------------------------------------------------------------- #
# 5 — Le repli sans recherche
# --------------------------------------------------------------------------- #


def test_un_repli_sans_recherche_rend_la_phrase_generique_et_ne_leve_pas(contexte, outils):
    """Aucune recherche dans le tour : il n'y a rien à rédiger, donc on s'excuse.

    C'est le cas dégradé du cas dégradé, et il ne doit surtout pas être une exception :
    une `KeyError` ici transformerait une hallucination en incident de service.
    """
    client = FauxClient([message(texte(INVENTE))])

    evenements, _ = jouer(client, contexte, outils)

    repli = evenements[-1]
    assert isinstance(repli, Repli)
    assert "$" not in repli.message


def test_un_repli_apres_recherche_rend_la_recommandation_par_template(contexte, outils):
    """Le niveau 3 de §3.11 : le code rédige à partir du dernier `ResultatMatching`."""
    client = FauxClient(
        [
            message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(appel_outil(NOM_RECHERCHER, id="tu_2")),
            message(texte(INVENTE)),
        ]
    )

    evenements, _ = jouer(client, contexte, outils)

    repli = evenements[-1]
    assert isinstance(repli, Repli)
    assert repli.motif is MotifDeRepli.VALIDATION
    assert "monitor-" in repli.message


# --------------------------------------------------------------------------- #
# 6 — Le budget de régénération est un réglage
# --------------------------------------------------------------------------- #


def test_un_budget_de_zero_branche_directement_le_repli(contexte, outils):
    """`RAIYON_MAX_REGENERATIONS=0` est une valeur légitime, pas une désactivation.

    C'est ce qui permettra à l'étape 12 de mesurer ce que la régénération rattrape
    réellement : la comparer à zéro, sur les mêmes scénarios.
    """
    client = FauxClient([message(texte(INVENTE)), message(texte(HONNETE))])

    evenements, _ = jouer(client, contexte, outils, max_regenerations=0)

    assert client.nombre_dappels == 1
    assert isinstance(evenements[-1], Repli)
