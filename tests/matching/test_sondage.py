"""Entropie, ordre, troncature, classement — **sur des comptages écrits à la main**.

Aucune base, aucun SQL, aucun produit : `Comptages` est un objet de trois nombres, et
c'est tout ce dont la partie la plus subtile du sondage a besoin. C'est la même
propriété que `relachement.py` achète depuis l'étape 6, et la raison pour laquelle la
frontière de §3.16 vaut la peine d'être tenue.
"""

from decimal import Decimal

import pytest

from raiyon.matching.attributs import ATTRIBUTS
from raiyon.matching.depot import Comptages
from raiyon.matching.sondage import (
    LIMITE_VALEURS_RENDUES,
    champ_le_plus_discriminant,
    entropie_normalisee,
    ordonner,
    resumer,
    score_de_discrimination,
    trop_disperse,
)

ECRAN = ATTRIBUTS["monitor"]
DISQUE = ATTRIBUTS["internal-hard-drive"]


def comptages(champ: str, effectifs: dict[str, int], total: int | None = None) -> Comptages:
    """Des comptages injectés : la couverture se déduit du total qu'on impose."""
    renseignes = sum(effectifs.values())
    return Comptages(
        champ=champ,
        effectifs=tuple(effectifs.items()),
        renseignes=renseignes,
        total=total if total is not None else renseignes,
    )


# --------------------------------------------------------------------------- #
# L'ordre — total, et décidé en Python
# --------------------------------------------------------------------------- #


def test_lordre_est_la_frequence_decroissante():
    valeurs = ordonner(comptages("panel_type", {"TN": 1, "VA": 17, "IPS": 14}), ECRAN["panel_type"])
    assert [v.valeur for v in valeurs] == ["VA", "IPS", "TN"]


def test_a_frequence_egale_lordre_est_la_valeur_croissante():
    valeurs = ordonner(comptages("panel_type", {"VA": 3, "IPS": 3, "TN": 3}), ECRAN["panel_type"])
    assert [v.valeur for v in valeurs] == ["IPS", "TN", "VA"]


def test_un_champ_numerique_sordonne_en_nombres_pas_en_lettres():
    """« 512 » vient après « 1000 » dans l'ordre alphabétique, et c'est faux."""
    valeurs = ordonner(comptages("capacity", {"1000": 2, "512": 2, "2000": 2}), DISQUE["capacity"])
    assert [v.valeur for v in valeurs] == ["512", "1000", "2000"]


# --------------------------------------------------------------------------- #
# La troncature — déclarée, toujours
# --------------------------------------------------------------------------- #


def test_la_troncature_est_declaree_quand_elle_a_lieu():
    beaucoup = {f"valeur-{numero:03d}": 1 for numero in range(40)}
    resume = resumer(comptages("panel_type", beaucoup), ECRAN["panel_type"])
    assert len(resume.valeurs) == LIMITE_VALEURS_RENDUES
    assert resume.total_distinct == 40
    assert resume.tronque is True


def test_les_deux_champs_de_troncature_sont_la_meme_quand_il_ny_a_rien_a_dire():
    """Même contrat que `ecartes_faute_de_donnee` : un champ optionnel n'existe qu'à
    moitié, et celui qui le lit finit par supposer sa valeur."""
    resume = resumer(comptages("panel_type", {"IPS": 3}), ECRAN["panel_type"])
    assert resume.total_distinct == 1
    assert resume.tronque is False


def test_le_resume_transporte_le_libelle_et_lunite_du_registre():
    resume = resumer(comptages("refresh_rate", {"144": 3}), ECRAN["refresh_rate"])
    assert resume.libelle_fr == "fréquence de rafraîchissement"
    assert resume.unite == "Hz"


def test_le_resume_dit_combien_de_produits_se_taisent():
    resume = resumer(comptages("refresh_rate", {"144": 3}, total=10), ECRAN["refresh_rate"])
    assert resume.renseignes == 3
    assert resume.total == 10
    assert resume.sans_valeur == 7


# --------------------------------------------------------------------------- #
# L'entropie
# --------------------------------------------------------------------------- #


def test_une_valeur_unique_napprend_rien():
    """Savoir que tous les écrans restants sont en 16:9 ne découpe rien."""
    assert entropie_normalisee([12]) == Decimal(0)


def test_une_distribution_equilibree_vaut_un():
    assert entropie_normalisee([5, 5]) == Decimal("1.0000")
    assert entropie_normalisee([4, 4, 4, 4]) == Decimal("1.0000")


def test_une_distribution_desequilibree_vaut_moins():
    assert Decimal(0) < entropie_normalisee([19, 1]) < Decimal("0.5")


def test_lentropie_ignore_les_effectifs_nuls():
    assert entropie_normalisee([5, 5, 0]) == entropie_normalisee([5, 5])


def test_le_score_est_pondere_par_la_couverture():
    """Sans cette pondération, l'outil demanderait une vitesse de rotation à un client
    dont les deux tiers des candidats sont des SSD."""
    complet = comptages("rpm", {"5400": 5, "7200": 5}, total=10)
    partiel = comptages("rpm", {"5400": 5, "7200": 5}, total=20)
    assert score_de_discrimination(complet) == Decimal("1.0000")
    assert score_de_discrimination(partiel) == Decimal("0.5000")


def test_un_champ_que_personne_ne_declare_ne_marque_rien():
    assert score_de_discrimination(comptages("rpm", {}, total=10)) == Decimal(0)


def test_un_sous_catalogue_vide_ne_marque_rien():
    assert score_de_discrimination(comptages("rpm", {}, total=0)) == Decimal(0)


# --------------------------------------------------------------------------- #
# La dispersion — le seuil, et ce qu'il assume
# --------------------------------------------------------------------------- #


def test_un_champ_presque_unique_par_produit_est_ecarte():
    """C'est la limite nº1 : sur un numérique continu, l'entropie est maximale et la
    question inutile. Le seuil est une parade, pas une théorie."""
    presque_unique = comptages("price_per_gb", {str(numero): 1 for numero in range(11)}, total=20)
    assert trop_disperse(presque_unique) is True


def test_un_champ_partage_ne_lest_pas():
    partage = comptages("panel_type", {"IPS": 10, "VA": 10}, total=20)
    assert trop_disperse(partage) is False


# --------------------------------------------------------------------------- #
# Le classement
# --------------------------------------------------------------------------- #


def test_le_champ_le_plus_equilibre_gagne():
    resultat = champ_le_plus_discriminant(
        {
            "panel_type": comptages("panel_type", {"IPS": 19, "VA": 1}, total=20),
            "aspect_ratio": comptages("aspect_ratio", {"16:9": 10, "21:9": 10}, total=20),
        },
        {champ: ECRAN[champ] for champ in ("panel_type", "aspect_ratio")},
    )
    assert resultat is not None
    assert resultat.champ == "aspect_ratio"
    assert resultat.score == Decimal("1.0000")
    assert resultat.libelle_fr == "format d'image"


def test_a_score_egal_le_champ_qui_a_le_plus_de_valeurs_passe_devant():
    """Rattrape la limite nº2 : la normalisation par log2(k) met à égalité un binaire
    et un champ à quatre valeurs, alors que le second apprend deux fois plus."""
    resultat = champ_le_plus_discriminant(
        {
            "panel_type": comptages("panel_type", {"IPS": 10, "VA": 10}, total=20),
            "aspect_ratio": comptages(
                "aspect_ratio", {"16:9": 5, "21:9": 5, "16:10": 5, "4:3": 5}, total=20
            ),
        },
        {champ: ECRAN[champ] for champ in ("panel_type", "aspect_ratio")},
    )
    assert resultat is not None
    assert resultat.champ == "aspect_ratio"


def test_le_nom_du_champ_ferme_lordre():
    """Rien ne doit dépendre de l'ordre du dictionnaire."""
    egaux = {
        "panel_type": comptages("panel_type", {"a": 10, "b": 10}, total=20),
        "aspect_ratio": comptages("aspect_ratio", {"a": 10, "b": 10}, total=20),
    }
    premier = champ_le_plus_discriminant(egaux, {c: ECRAN[c] for c in egaux})
    inverse = dict(reversed(list(egaux.items())))
    second = champ_le_plus_discriminant(inverse, {c: ECRAN[c] for c in inverse})
    assert premier is not None and second is not None
    assert premier.champ == second.champ == "aspect_ratio"


def test_aucun_champ_discriminant_est_une_reponse():
    """Quand plus rien ne découpe, il est temps de proposer, pas de questionner."""
    unanimes = {"panel_type": comptages("panel_type", {"IPS": 12}, total=12)}
    assert champ_le_plus_discriminant(unanimes, {"panel_type": ECRAN["panel_type"]}) is None


def test_un_champ_sans_attribut_connu_est_ignore():
    """Le classement ne peut pas parler d'un champ que le registre ne décrit pas."""
    assert (
        champ_le_plus_discriminant({"inconnu": comptages("inconnu", {"a": 5, "b": 5})}, {}) is None
    )


@pytest.mark.parametrize("effectifs", [{}, {"seule": 7}])
def test_un_champ_sans_alternative_ne_gagne_jamais(effectifs):
    resultat = champ_le_plus_discriminant(
        {"panel_type": comptages("panel_type", effectifs, total=7)},
        {"panel_type": ECRAN["panel_type"]},
    )
    assert resultat is None
