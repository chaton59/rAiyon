"""Diagnostic et propositions, sur des **comptages injectés à la main**.

C'est ce que permet la frontière de l'arbitrage A : la partie la plus subtile du
moteur — celle qui décide de ce qu'on répond à un client quand il n'y a rien — se
teste sans base, en dictant les nombres au lieu de construire la situation qui les
produirait.
"""

from decimal import Decimal

from raiyon.matching.attributs import ATTRIBUTS
from raiyon.matching.criteres import Critere, Importance, Operateur, RequeteMatching
from raiyon.matching.depot import RelevesDeRelachement
from raiyon.matching.relachement import Motif, _motif_du_retrait, diagnostiquer


def critere(champ, operateur, valeur, importance=Importance.BLOQUANT):
    return Critere(champ=champ, operateur=operateur, valeur=valeur, importance=importance)


def test_le_critere_le_plus_couteux_est_propose_en_premier():
    """« Le plus coûteux » = celui dont le retrait rouvrirait le plus de produits."""
    requete = RequeteMatching(
        categorie="internal-hard-drive",
        criteres=(
            critere("form_factor", Operateur.EGAL, "M.2-2280"),
            critere("interface", Operateur.EGAL, "SATA 6.0 Gb/s"),
        ),
    )
    releves = RelevesDeRelachement(rouvre_si_retire={"form_factor": 85, "interface": 52})

    diagnostic = diagnostiquer(requete, releves, {})
    assert diagnostic.motif is Motif.CRITERE_TROP_STRICT
    assert [proposition.champ for proposition in diagnostic.propositions] == [
        "form_factor",
        "interface",
    ]
    assert [proposition.produits_rouverts for proposition in diagnostic.propositions] == [85, 52]


def test_limportance_declaree_passe_avant_le_nombre_de_produits_rouverts():
    """On propose d'abord d'abandonner ce à quoi le client tenait le moins."""
    requete = RequeteMatching(
        categorie="monitor",
        criteres=(
            critere("refresh_rate", Operateur.AU_MOINS, 144, Importance.BLOQUANT),
            critere("screen_size", Operateur.AU_MOINS, 32, Importance.IMPORTANT),
        ),
    )
    releves = RelevesDeRelachement(rouvre_si_retire={"refresh_rate": 90, "screen_size": 10})

    diagnostic = diagnostiquer(requete, releves, {})
    assert [proposition.champ for proposition in diagnostic.propositions] == [
        "screen_size",
        "refresh_rate",
    ]


def test_un_critere_de_compatibilite_est_propose_en_dernier():
    """Il ne se relâche pas par degré : il ne peut qu'être abandonné."""
    requete = RequeteMatching(
        categorie="internal-hard-drive",
        criteres=(
            critere("interface", Operateur.EGAL, "SATA 6.0 Gb/s"),
            critere("capacity", Operateur.AU_MOINS, 2000),
        ),
    )
    releves = RelevesDeRelachement(
        rouvre_si_retire={"interface": 100, "capacity": 10},
        valeurs_atteignables={"capacity": Decimal("960")},
    )

    diagnostic = diagnostiquer(requete, releves, {})
    propositions = diagnostic.propositions
    assert [proposition.champ for proposition in propositions] == ["capacity", "interface"]
    assert not propositions[0].dernier_recours
    assert propositions[1].dernier_recours
    assert propositions[0].valeur_atteignable == Decimal("960")
    assert propositions[1].valeur_atteignable is None


def test_la_valeur_proposee_est_celle_du_catalogue():
    """« Descendez à 960 Go », jamais « descendez à 1 To ».

    Un seuil rond calculé rendrait encore zéro si le premier disque disponible est à
    960 Go — et affirmerait sur le stock un fait qui n'en est pas un.
    """
    requete = RequeteMatching(
        categorie="internal-hard-drive",
        criteres=(critere("capacity", Operateur.AU_MOINS, 1000),),
    )
    releves = RelevesDeRelachement(
        rouvre_si_retire={"capacity": 12}, valeurs_atteignables={"capacity": Decimal("960")}
    )
    (proposition,) = diagnostiquer(requete, releves, {}).propositions
    assert proposition.valeur_atteignable == Decimal("960")
    assert proposition.valeur_demandee == Decimal("1000")


def test_quand_les_ecartes_expliquent_tout_le_motif_est_la_donnee_absente():
    """« Aucun écran ne déclare sa fréquence » n'est pas « aucun écran ne fait 144 Hz »."""
    requete = RequeteMatching(
        categorie="monitor", criteres=(critere("refresh_rate", Operateur.AU_MOINS, 144),)
    )
    releves = RelevesDeRelachement(rouvre_si_retire={"refresh_rate": 7})

    diagnostic = diagnostiquer(requete, releves, {"refresh_rate": 7})
    assert diagnostic.motif is Motif.DONNEE_ABSENTE
    assert diagnostic.propositions[0].motif is Motif.DONNEE_ABSENTE


def test_quand_les_ecartes_nexpliquent_quune_partie_le_critere_est_trop_strict():
    """Sept écrans sans valeur, mais quatre-vingt-dix rouverts : c'est le seuil qui bloque."""
    requete = RequeteMatching(
        categorie="monitor", criteres=(critere("refresh_rate", Operateur.AU_MOINS, 144),)
    )
    releves = RelevesDeRelachement(rouvre_si_retire={"refresh_rate": 90})

    diagnostic = diagnostiquer(requete, releves, {"refresh_rate": 7})
    assert diagnostic.motif is Motif.CRITERE_TROP_STRICT


def test_aucun_retrait_simple_est_une_reponse_pas_un_silence():
    """Les combinaisons de degré 2 sont hors périmètre ; leur absence se dit."""
    requete = RequeteMatching(
        categorie="monitor", criteres=(critere("refresh_rate", Operateur.AU_MOINS, 600),)
    )
    diagnostic = diagnostiquer(requete, RelevesDeRelachement(rouvre_si_retire={}), {})
    assert diagnostic.motif is Motif.AUCUN_RETRAIT_SIMPLE
    assert diagnostic.propositions == ()


def test_un_critere_dont_le_retrait_nouvre_rien_nest_pas_propose():
    """Proposer un assouplissement sans effet serait une fausse piste."""
    requete = RequeteMatching(
        categorie="internal-hard-drive",
        criteres=(
            critere("interface", Operateur.EGAL, "SATA 6.0 Gb/s"),
            critere("capacity", Operateur.AU_MOINS, 26000),
        ),
    )
    releves = RelevesDeRelachement(rouvre_si_retire={"interface": 3, "capacity": 0})
    diagnostic = diagnostiquer(requete, releves, {})
    assert [proposition.champ for proposition in diagnostic.propositions] == ["interface"]


def test_le_budget_nest_jamais_propose_au_relachement():
    """La réponse au budget bloquant est la zone de tolérance de §3.10, pas un conseil.

    Le comptage est ignoré même s'il arrive : `prix_usd` est exclu **ici aussi**, et
    pas seulement parce que la requête refuse de le porter en critère.
    """
    requete = RequeteMatching(
        categorie="monitor",
        budget_usd=Decimal("100"),
        criteres=(critere("refresh_rate", Operateur.AU_MOINS, 144),),
    )
    releves = RelevesDeRelachement(
        rouvre_si_retire={"refresh_rate": 4, "prix_usd": 120, "categorie": 800}
    )
    diagnostic = diagnostiquer(requete, releves, {}, produits_au_dessus_du_budget=2)

    assert diagnostic.motif is Motif.BUDGET_TROP_BAS
    champs = {proposition.champ for proposition in diagnostic.propositions}
    assert "prix_usd" not in champs
    assert "categorie" not in champs


# --------------------------------------------------------------------------- #
# Le troisième cas : une absence expliquée par une autre colonne
# --------------------------------------------------------------------------- #


def test_une_absence_structurelle_nest_jamais_une_donnee_manquante():
    """Même quand les comptages coïncident, `rpm` ne rend pas `donnee_absente`.

    C'est exactement la situation qui produisait la phrase fausse : le retrait de `rpm`
    rouvre 40 disques, les 40 avaient été écartés faute de valeur, l'égalité concluait
    « ces disques ne déclarent pas leur vitesse de rotation ». Ce sont des SSD.
    """
    rpm = ATTRIBUTS["internal-hard-drive"]["rpm"]
    assert rpm.absence_structurelle
    assert _motif_du_retrait(rpm, 40, 40, None) is Motif.ABSENCE_STRUCTURELLE
    assert _motif_du_retrait(rpm, 40, 0, None) is Motif.ABSENCE_STRUCTURELLE
    assert _motif_du_retrait(rpm, 0, 0, None) is Motif.ABSENCE_STRUCTURELLE


def test_une_valeur_atteignable_prime_sur_le_drapeau_du_registre():
    """Le drapeau ne suffit pas : encore faut-il que rien ne soit atteignable.

    Un attribut peut être structurellement inapplicable à une partie du catalogue **et**
    demandé trop strictement sur le reste. « Vous avez demandé un disque mécanique » est
    alors faux — il y en a, ils tournent à 5 400. Ce sont deux phrases différentes, et
    c'est la valeur atteignable qui les sépare.
    """
    rpm = ATTRIBUTS["internal-hard-drive"]["rpm"]
    assert _motif_du_retrait(rpm, 6, 0, Decimal("5400")) is Motif.CRITERE_TROP_STRICT
    assert _motif_du_retrait(rpm, 6, 0, None) is Motif.ABSENCE_STRUCTURELLE


def test_un_attribut_ordinaire_garde_les_deux_motifs_dorigine():
    """Le troisième cas s'ajoute, il ne remplace rien."""
    refresh = ATTRIBUTS["monitor"]["refresh_rate"]
    assert not refresh.absence_structurelle
    assert _motif_du_retrait(refresh, 7, 7, None) is Motif.DONNEE_ABSENTE
    assert _motif_du_retrait(refresh, 90, 7, Decimal("120")) is Motif.CRITERE_TROP_STRICT
    assert _motif_du_retrait(refresh, 90, 0, Decimal("120")) is Motif.CRITERE_TROP_STRICT


def test_une_valeur_atteignable_ne_sauve_pas_un_attribut_ordinaire():
    """La condition ne s'ajoute qu'à la première branche : les deux autres sont intactes."""
    refresh = ATTRIBUTS["monitor"]["refresh_rate"]
    assert _motif_du_retrait(refresh, 7, 7, Decimal("120")) is Motif.DONNEE_ABSENTE


def test_le_diagnostic_densemble_porte_le_motif_de_labsence_structurelle():
    """Le motif d'ensemble est celui de la meilleure proposition, ici `rpm`."""
    requete = RequeteMatching(
        categorie="internal-hard-drive",
        criteres=(
            critere("rpm", Operateur.AU_MOINS, 7200),
            critere("interface", Operateur.EGAL, "M.2 PCIe 4.0 X4"),
        ),
    )
    releves = RelevesDeRelachement(rouvre_si_retire={"rpm": 40, "interface": 32})

    diagnostic = diagnostiquer(requete, releves, {})
    assert diagnostic.motif is Motif.ABSENCE_STRUCTURELLE
    assert diagnostic.propositions[0].champ == "rpm"
