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
    PLANCHER_DETENDUE,
    SIGNAL,
    Compteur,
    couvrir,
    ecarts,
    etendue_par_scenario,
    rendre,
    scenarios_a_une_prise,
    valeur_par_passe,
)
from raiyon.eval.cout import Cout
from raiyon.eval.metriques import RESERVE_ITERATIONS, PriseJouee, TourJoue, agreger, mesurer
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


def test_un_scenario_a_une_seule_prise_ne_contribue_pas_zero_et_est_nomme():
    """**Sa dispersion est inconnue, pas nulle.** Le plancher évite qu'elle compte zéro,
    mais il ne prétend pas la connaître — d'où le nommage, et d'où les trois prises que
    l'étape 13 paie partout."""
    mesures = campagne(("a", 1, 5))

    assert etendue_par_scenario(mesures, REJETS) == PLANCHER_DETENDUE
    assert scenarios_a_une_prise(mesures) == ("a",)
    assert "Dispersion inconnue, comptée pour zéro" in rendre(
        mesures, mesures, nom_avant="x", nom_apres="y", question="?"
    )


def test_un_scenario_jamais_vu_bouger_ne_rend_pas_tout_ecart_significatif():
    """**Le piège que ce module décrivait sans s'en protéger.**

    Il écrit qu'une dispersion nulle veut dire « on ne l'a pas vu bouger », et il traitait
    pourtant l'étendue observée comme une borne dure : un scénario vu trois fois à la même
    valeur rendait **tout** écart « au-delà du bruit ».

    Le cas réel : la métrique nº3 est constante sur les onze scénarios de la ligne de base,
    et une baisse de 1,33 y était déclarée significative — alors que l'étape 12 avait
    mesuré `besoin_flou` à 2, 2 puis 3 tours sur le même prompt.
    """
    calme = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 0))
    un_peu = campagne(("a", 1, 1), ("a", 2, 1), ("a", 3, 1))

    (ecart,) = [e for e in ecarts(calme, un_peu) if e.libelle == "Rejets du validateur"]
    assert ecart.dispersion == PLANCHER_DETENDUE
    assert ecart.delta == 1.0
    assert ecart.verdict == BRUIT, (
        "un écart d'un pas contre un plancher d'un pas n'est pas au-delà de lui : trois "
        "tirages identiques bornent l'étendue par en dessous, ils ne la mesurent pas"
    )

    texte = rendre(calme, un_peu, nom_avant="v1", nom_apres="v2", question="?")
    assert "ne compte pas zéro" in texte
    assert "« calme par chance » ne se distinguent pas" in texte


# --------------------------------------------------------------------------- #
# Le verdict — et il se trompe du bon côté
# --------------------------------------------------------------------------- #


def test_un_ecart_inferieur_a_la_dispersion_nest_pas_un_signal():
    """**La règle du brief, appliquée plutôt que rappelée.**"""
    avant = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 6))  # étendue 6, moyenne 2,0
    apres = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 0))  # moyenne 0, écart -2,0

    (ecart,) = [e for e in ecarts(avant, apres) if e.libelle == "Rejets du validateur"]
    assert (ecart.avant, ecart.apres, ecart.delta) == (2.0, 0.0, -2.0)
    assert ecart.dispersion == 6.0
    assert ecart.verdict == BRUIT


def test_un_ecart_egal_a_la_dispersion_nest_pas_au_dela_delle():
    """La frontière est stricte, et elle penche du côté prudent : « supérieur à », pas
    « supérieur ou égal ». Un écart qui vaut exactement le bruit observé est du bruit."""
    avant = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 3))  # étendue 3, moyenne 1,0
    apres = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 0))  # moyenne 0, écart -1,0

    (ecart,) = [e for e in ecarts(avant, apres) if e.libelle == "Rejets du validateur"]
    assert ecart.dispersion == 3.0
    assert ecart.verdict == BRUIT


def test_un_ecart_strictement_superieur_a_la_dispersion_est_un_signal():
    avant = campagne(("a", 1, 3), ("a", 2, 3), ("a", 3, 4))  # étendue 1, moyenne 3,33
    apres = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 0))  # moyenne 0

    (ecart,) = [e for e in ecarts(avant, apres) if e.libelle == "Rejets du validateur"]
    assert ecart.dispersion == 1.0
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
    stable = campagne(("a", 1, 9), ("a", 2, 9), ("a", 3, 9))  # étendue plancher, moyenne 9,0
    instable = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 9))  # étendue 9, moyenne 3,0

    (depuis_stable,) = [e for e in ecarts(stable, instable) if e.libelle == "Rejets du validateur"]
    (depuis_instable,) = [
        e for e in ecarts(instable, stable) if e.libelle == "Rejets du validateur"
    ]

    # Le **même** écart de 6, lu depuis deux étalons de bruit : significatif contre une
    # référence stable, dans le bruit contre une référence qui bougeait déjà de 9.
    assert (depuis_stable.dispersion, depuis_stable.verdict) == (PLANCHER_DETENDUE, SIGNAL)
    assert (depuis_instable.dispersion, depuis_instable.verdict) == (9, BRUIT)


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

    assert "| `nom_reecrit` | 1.00 | 0.00 | -1.00 | 1 → 0 |" in texte


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
    assert (ecart.avant, ecart.apres) == (0.0, 1.0)
    assert ecart.verdict == BRUIT, (
        "un repli de plus sur un scénario jamais vu replier ne dépasse pas le plancher — "
        "il faudrait plus d'un pas, ou plus de scénarios touchés"
    )


# --------------------------------------------------------------------------- #
# La couverture — ce que l'intersection compare, et ce qu'elle coûte
# --------------------------------------------------------------------------- #


def test_lintersection_porte_sur_les_scenarios_et_non_sur_les_numeros_de_prise():
    """**La première rédaction de ce module était fausse, et voici le cas qui l'a dit.**

    Elle appariait `(scénario, prise)`. Or un numéro de prise est un **index**, pas une
    identité : la température n'est pas fixée, et la prise 2 d'une campagne n'a aucun lien
    avec la prise 2 d'une autre. L'appariement ne rapprochait rien, et il **jetait des
    données payées** — sur les jeux réels de l'étape 13, il réduisait 21 prises à 11 en
    écartant les prises 2 et 3 des scénarios que l'étape 12 n'avait tirés qu'une fois.
    """
    reference = campagne(("a", 1, 0), ("b", 1, 0))
    campagne_neuve = campagne(("a", 1, 0), ("a", 2, 0), ("a", 3, 0), ("b", 1, 0), ("b", 2, 0))

    couverture, _, reduit_apres = couvrir(reference, campagne_neuve)

    assert couverture.scenarios == ("a", "b")
    assert (couverture.prises_avant, couverture.prises_apres) == (2, 5)
    assert len(reduit_apres.prises) == 5, "aucune prise du jeu neuf n'est jetée"


def test_un_scenario_absent_dun_cote_sort_de_la_comparaison_et_est_nomme():
    reference = campagne(("a", 1, 0), ("absent_apres", 1, 0))
    autre = campagne(("a", 1, 0), ("absent_avant", 1, 0))

    couverture, reduit_avant, reduit_apres = couvrir(reference, autre)

    assert couverture.scenarios == ("a",)
    assert couverture.absents_apres == ("absent_apres",)
    assert couverture.absents_avant == ("absent_avant",)
    assert not couverture.complete
    assert {prise.scenario for prise in reduit_avant.prises} == {"a"}
    assert {prise.scenario for prise in reduit_apres.prises} == {"a"}


def test_lexclusion_est_chiffree_et_non_seulement_signalee():
    """⚠️ **Le point qui décide de ce que la comparaison a le droit de conclure.**

    Les scénarios écartés ne sont pas un échantillon au hasard : ce sont ceux qui manquent
    d'un côté. S'ils portaient l'essentiel des griefs de la référence, la comparaison porte
    sur ses scénarios les plus **calmes**, et tout écart y est mécaniquement plus petit.

    Le dire ne suffit pas — il faut le chiffrer, à côté du tableau, avant que le lecteur
    ait conclu. C'est le cas réel de l'étape 13 : les scénarios manquants de la campagne v1
    portaient 5 des 11 rejets de l'étape 12.
    """
    reference = campagne(("calme", 1, 0), ("bruyant", 1, 5))
    autre = campagne(("calme", 1, 0))

    couverture, _, _ = couvrir(reference, autre)

    assert (couverture.rejets_exclus, couverture.rejets_total) == (5, 5)
    texte = rendre(
        *couvrir(reference, autre)[1:],
        nom_avant="ref",
        nom_apres="autre",
        question="?",
        couverture=couverture,
    )
    assert "portaient **5 des 5 rejets** de ref" in texte
    assert "sous-estime" in texte


def test_deux_jeux_de_meme_couverture_le_disent_sans_reserve():
    """Une réserve affichée quand il n'y en a pas est une réserve qu'on cesse de lire."""
    mesures = campagne(("a", 1, 0), ("a", 2, 0))
    couverture, avant, apres = couvrir(mesures, mesures)

    texte = rendre(
        avant, apres, nom_avant="v1", nom_apres="v2", question="?", couverture=couverture
    )

    assert couverture.complete
    assert "La comparaison est complète." in texte
    assert "sous-estime" not in texte


def test_une_moyenne_par_scenario_ne_laisse_pas_un_scenario_peser_plus_que_les_autres():
    """`question_de_domaine` porte **six** prises quand les autres en portent trois. Une
    moyenne prise sur toutes les prises confondues le ferait peser deux fois plus, et la
    comparaison bougerait quand on change le nombre de prises d'un seul scénario — ce que
    l'étape 13 a précisément fait."""
    trois = campagne(("a", 1, 3), ("a", 2, 3), ("a", 3, 3), ("b", 1, 0))
    six = campagne(*[("a", numero, 3) for numero in range(1, 7)], ("b", 1, 0))

    assert valeur_par_passe(trois, REJETS) == valeur_par_passe(six, REJETS) == 3.0


# --------------------------------------------------------------------------- #
# Le coût d'enregistrement — étape 15, jalon 0, point D
# --------------------------------------------------------------------------- #


def test_le_cout_se_compare_mais_ne_recoit_aucun_verdict():
    """⚠️ **La raison est dans la grandeur elle-même.** La colonne « Verdict » du tableau
    des écarts se calcule depuis la dispersion des prises d'un rejeu ; un coût figé à
    l'enregistrement n'en a aucune — il a été payé une fois, il ne sera pas retiré. Un
    « au-delà du bruit » calculé dessus serait faux avec l'air d'un résultat."""
    mesures = campagne(("a", 1, 1), ("a", 2, 1))
    texte = rendre(
        mesures,
        mesures,
        nom_avant="v1",
        nom_apres="v2",
        question="?",
        cout_avant=Cout(appels=150, prises=36, prises_sans_usage=0, tours=100),
        cout_apres=Cout(appels=191, prises=36, prises_sans_usage=0, tours=102),
    )

    assert "## Le coût d'enregistrement" in texte
    assert "+0.37 appel/tour" in texte
    assert "ne porte pas de verdict" in texte

    coeur = texte.split("## Le coût d'enregistrement")[1].split("## Les critères")[0]
    assert SIGNAL not in coeur and BRUIT not in coeur


def test_un_cote_sans_usage_supprime_lecart_et_le_dit_des_deux_cotes():
    """`v1-base` porte 3 prises avec `usage` sur 31, `v2` les 36 siennes. Publier un écart
    entre les deux comparerait des tailles d'échantillon."""
    mesures = campagne(("a", 1, 1), ("a", 2, 1))
    texte = rendre(
        mesures,
        mesures,
        nom_avant="v1-base",
        nom_apres="v2",
        question="?",
        cout_avant=Cout(appels=18, prises=31, prises_sans_usage=28, tours=95),
        cout_apres=Cout(appels=191, prises=36, prises_sans_usage=0, tours=102),
    )

    assert "non disponible — 28 prise(s) sur 31 sans `usage`" in texte
    assert "non calculable" in texte


def test_la_reserve_sur_les_iterations_accompagne_le_tableau_des_ecarts():
    """`Itérations` est l'un des six compteurs comparés, et c'est celui qui cessera d'être
    comparable dès que l'étape 15 mettra deux orchestrations côte à côte."""
    mesures = campagne(("a", 1, 1), ("a", 2, 1))

    assert RESERVE_ITERATIONS in rendre(
        mesures, mesures, nom_avant="v1", nom_apres="v2", question="?"
    )
