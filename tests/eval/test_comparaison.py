"""La comparaison de deux campagnes, et **le verdict « est-ce un signal ? »**.

Ce que ce fichier protège tient en une phrase, et c'est la conclusion de la section
« dispersion » du rapport de l'étape 12 :

> *Un écart de deux prompts inférieur à cet ordre de grandeur n'est pas un signal.*

Écrite dans un fichier, elle se lit une fois puis s'oublie. Calculée, elle s'applique. Les
tests ci-dessous vérifient qu'elle s'applique **dans le bon sens** — la faute qui coûterait
cher n'est pas de rater un effet, c'est d'en annoncer un que le tirage explique.
"""

from raiyon.agent.evenements import MotifDeRepli, Repli, Texte, TexteRejete
from raiyon.eval.comparaison import (
    BRUIT,
    IDENTIQUE,
    SIGNAL,
    Compteur,
    ecarts,
    etendue_par_scenario,
    rendre,
    scenarios_a_une_prise,
)
from raiyon.eval.metriques import PriseJouee, TourJoue, agreger, mesurer
from raiyon.validateur.regles import CodeGrief, Grief
from raiyon.validateur.validateur import OrigineRejet

REJETS = Compteur("Rejets", lambda prise: len(prise.rejets), "baisse")


def rejets(nombre: int) -> tuple:
    """Un tour portant `nombre` griefs, donc `nombre` rejets."""
    if not nombre:
        return ()
    return (
        TexteRejete(
            "une phrase refusée",
            tuple(
                Grief(CodeGrief.MONTANT_NON_FOURNI, f"{rang} $", "corriger")
                for rang in range(nombre)
            ),
            1,
            OrigineRejet.TEXTE,
        ),
    )


def campagne(*prises: tuple[str, int, int]):
    """`(scénario, prise, nombre de rejets)` → un agrégat."""
    return agreger(
        [
            mesurer(
                PriseJouee(
                    scenario=nom,
                    prise=numero,
                    tours=(TourJoue("message", (*rejets(nombre), Texte("livré")), 1),),
                    messages=(),
                )
            )
            for nom, numero, nombre in prises
        ]
    )


# --------------------------------------------------------------------------- #
# La dispersion — ce qu'elle mesure, et ce qu'elle ne mesure pas
# --------------------------------------------------------------------------- #


def test_la_dispersion_est_letendue_des_prises_sommee_sur_les_scenarios():
    """`max - min` par scénario, sommé : de combien le total aurait pu bouger par le seul
    tirage, si chaque scénario était tombé sur son extrême."""
    mesures = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 2), ("b", 1, 2), ("b", 2, 0), ("b", 3, 0))

    assert etendue_par_scenario(mesures, REJETS) == 4, "2 sur `a`, 2 sur `b`"


def test_un_scenario_a_une_seule_prise_contribue_zero_et_est_nomme():
    """**Sa dispersion est inconnue, pas nulle.** La compter zéro rend le verdict trop
    généreux, et c'est exactement pourquoi l'étape 13 paie trois prises partout — le
    tableau doit donc le dire au lecteur plutôt que de le laisser croire à une stabilité."""
    mesures = campagne(("a", 1, 5))

    assert etendue_par_scenario(mesures, REJETS) == 0
    assert scenarios_a_une_prise(mesures) == ("a",)
    assert "Dispersion inconnue, comptée pour zéro" in rendre(
        mesures, mesures, nom_avant="x", nom_apres="y", question="?"
    )


def test_une_dispersion_nulle_ne_se_presente_jamais_comme_une_stabilite():
    """Trois prises ne distinguent pas « stable par construction » de « calme par chance »,
    et le fichier doit porter la réserve — c'est lui qu'on relira, pas la docstring."""
    calme = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 0))

    texte = rendre(calme, calme, nom_avant="v1", nom_apres="v2", question="?")

    assert "Une dispersion nulle ne veut pas dire « stable »" in texte
    assert "calme\n> par chance" in texte


# --------------------------------------------------------------------------- #
# Le verdict — et il se trompe du bon côté
# --------------------------------------------------------------------------- #


def test_un_ecart_inferieur_a_la_dispersion_nest_pas_un_signal():
    """**La règle du brief, appliquée plutôt que rappelée.**"""
    avant = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 2))  # dispersion 2, total 2
    apres = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 0))  # total 0, écart -2

    (ecart,) = [e for e in ecarts(avant, apres) if e.libelle == "Rejets du validateur"]
    assert (ecart.avant, ecart.apres, ecart.delta) == (2, 0, -2)
    assert ecart.dispersion == 2
    assert ecart.verdict == BRUIT, "un écart égal à la dispersion n'est pas au-delà d'elle"


def test_un_ecart_strictement_superieur_a_la_dispersion_est_un_signal():
    avant = campagne(("a", 1, 3), ("a", 2, 3), ("a", 3, 4))  # dispersion 1, total 10
    apres = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 0))  # total 0, écart -10

    (ecart,) = [e for e in ecarts(avant, apres) if e.libelle == "Rejets du validateur"]
    assert ecart.dispersion == 1
    assert ecart.verdict == SIGNAL


def test_un_ecart_nul_se_dit_identique_et_non_dans_le_bruit():
    """« Dans le bruit » et « identique » ne veulent pas dire la même chose : le premier
    dit qu'on ne sait pas trancher, le second qu'il n'y a rien à trancher."""
    mesures = campagne(("a", 1, 1), ("a", 2, 1), ("a", 3, 1))

    assert all(ecart.verdict == IDENTIQUE for ecart in ecarts(mesures, mesures))


def test_la_dispersion_vient_de_la_campagne_de_reference_et_non_de_lautre():
    """La question posée est « le nouveau prompt a-t-il fait quelque chose que l'ancien ne
    faisait pas ? » : l'étalon de bruit est celui du monde d'avant. Le prendre après ferait
    dépendre le verdict de ce qu'on mesure — et un prompt instable s'auto-absoudrait."""
    stable = campagne(("a", 1, 4), ("a", 2, 4), ("a", 3, 4))  # dispersion 0, total 12
    instable = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 9))  # dispersion 9, total 9

    (depuis_stable,) = [e for e in ecarts(stable, instable) if e.libelle == "Rejets du validateur"]
    (depuis_instable,) = [
        e for e in ecarts(instable, stable) if e.libelle == "Rejets du validateur"
    ]

    assert depuis_stable.dispersion == 0
    assert depuis_stable.verdict == SIGNAL
    assert depuis_instable.dispersion == 9
    assert depuis_instable.verdict == BRUIT


# --------------------------------------------------------------------------- #
# Le fichier produit
# --------------------------------------------------------------------------- #


def test_la_comparaison_est_stable_octet_pour_octet():
    """Elle est committée, comme les rapports : un rendu instable produirait un diff qui ne
    dit rien, et un diff permanent est un diff qu'on cesse de lire."""
    avant, apres = campagne(("a", 1, 2), ("a", 2, 0)), campagne(("a", 1, 0), ("a", 2, 0))
    rendu = rendre(avant, apres, nom_avant="v1", nom_apres="v2", question="l'effet de la cible 1.")

    assert rendu == rendre(
        avant, apres, nom_avant="v1", nom_apres="v2", question="l'effet de la cible 1."
    )


def test_la_comparaison_dit_ce_quelle_cherche_a_savoir():
    """Trois comparaisons presque identiques cohabiteront dans `docs/eval/`. Celle qui ne
    dit pas ce qu'elle mesure sera lue comme celle d'à côté."""
    mesures = campagne(("a", 1, 1), ("a", 2, 1))
    texte = rendre(
        mesures,
        mesures,
        nom_avant="v1-etape12",
        nom_apres="v1",
        question="une **borne supérieure** de la dérive du modèle, jamais la dérive.",
    )

    assert "# Comparaison v1-etape12 → v1" in texte
    assert "borne supérieure** de la dérive du modèle, jamais la dérive." in texte


def test_le_tableau_des_codes_est_derive_des_rejets_et_non_dune_liste():
    """Un code neuf doit y apparaître sans qu'on touche à ce module — même raison qu'à la
    ligne « règles jamais déclenchées » du rapport."""
    avec_un_code = agreger(
        [
            mesurer(
                PriseJouee(
                    "a",
                    1,
                    (
                        TourJoue(
                            "m",
                            (
                                TexteRejete(
                                    "phrase",
                                    (Grief(CodeGrief.NOM_REECRIT, "Odyssée", "recopier"),),
                                    1,
                                    OrigineRejet.TEXTE,
                                ),
                            ),
                            1,
                        ),
                    ),
                    (),
                )
            )
        ]
    )
    vide = campagne(("a", 1, 0))

    texte = rendre(avec_un_code, vide, nom_avant="v1", nom_apres="v2", question="?")

    assert "| `nom_reecrit` | 1 | 0 | -1 |" in texte


def test_la_comparaison_rappelle_que_le_numero_3_est_un_garde_fou():
    """§5 étape 13 demande de « viser en priorité » la métrique nº3. Elle ne peut pas
    descendre — son minimum atteignable est 1, et la médiane vaut déjà 1,0. Ce qu'on
    surveille est qu'elle ne **monte** pas, et le fichier doit le dire là où il l'affiche.
    """
    mesures = campagne(("a", 1, 0), ("a", 2, 0))
    texte = rendre(mesures, mesures, nom_avant="v1", nom_apres="v2", question="?")

    assert "La métrique nº3 est un garde-fou, pas une cible" in texte
    assert "son minimum atteignable est **1**" in texte


def test_un_repli_compte_dans_la_comparaison():
    """Un repli est une réponse **dégradée livrée au client** : un prompt qui baisserait le
    taux de rejet en augmentant les replis n'aurait rien amélioré."""
    sans = campagne(("a", 1, 0), ("a", 2, 0))
    avec = agreger(
        [
            mesurer(
                PriseJouee(
                    "a",
                    numero,
                    (TourJoue("m", (Repli("Je vérifie.", 2, (), MotifDeRepli.VALIDATION),), 1),),
                    (),
                )
            )
            for numero in (1, 2)
        ]
    )

    (ecart,) = [e for e in ecarts(sans, avec) if e.libelle == "Tours repliés"]
    assert (ecart.avant, ecart.apres, ecart.verdict) == (0, 2, SIGNAL)
