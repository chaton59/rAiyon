"""La conduite du dialogue de la machine à états. **La mesure nº8 se compte ici.**

Ces tests construisent un état et un résultat d'outil, appellent `decider()`, et
assertionnent l'action. Ni base, ni conteneur, ni clé, ni réseau : quelques
millisecondes. C'est ce que §3.6 avait déclaré perdu — « il n'y a plus de fonction de
décision pure à assertionner » — et le zéro d'en face est écrit au §7 de `PROJET.md`,
ligne « le faux client teste la boucle, pas le modèle » : *un défaut de conduite du
dialogue passe entièrement à travers `make check`.*

⚠️ **Ils sont écrits depuis les règles, pas depuis l'implémentation**, et c'est ce qui
décide de la valeur de la mesure. Un test dérivé du code compte comme une ligne de plus
dans un chiffre publié tout en ne vérifiant qu'une tautologie — la circularité qui a fait
refuser, à l'étape 12, l'ajout de scénarios écrits depuis §3.6.

Chaque test porte donc **la référence de la règle qu'il vérifie**, sur une ligne qui
commence par `Règle — `. C'est ce marqueur que `test_mesure_8.py` compte : un test sans
référence n'est pas un test de conduite, et il ne compte pas.

### Les résultats d'outil ne sont pas fabriqués à la main

Ils sortent des **vrais outils**, appelés sur `DepotEnMemoire`. Construire un
`ResultatQuestion` à la main testerait une forme que `question_suivante` ne produit
peut-être pas — c'est la raison qui fait déjà passer `etat_avec()` par `fusionner()`
plutôt que par le constructeur d'`EtatSession`. Tout reste hors ligne : les cinq outils
sont purs dès lors que le dépôt l'est.
"""

import pytest

from outils_de_test import TOLERANCE, DepotEnMemoire, critere, ecrans, etat_avec
from produits_de_test import fabriquer
from raiyon.machine.decision import (
    CIBLE_BUDGET,
    DemanderPrecision,
    Rechercher,
    Rediger,
    Sonder,
    Suggerer,
    TourDejaClos,
    decider,
)
from raiyon.matching.criteres import Operateur
from raiyon.tools.etat import EtatSession
from raiyon.tools.outils import (
    ArgumentsCritere,
    ArgumentsEnregistrement,
    ArgumentsPrecision,
    demander_precision,
    enregistrer_criteres,
    question_suivante,
    rechercher_produits,
    sonder_catalogue,
)

VARIES = [
    fabriquer(
        "monitor", numero, prix=f"{100 + 10 * numero}", panel_type="IPS" if numero % 2 else "VA"
    )
    for numero in range(1, 7)
]
"""Six écrans qui diffèrent sur `panel_type` : il faut de la variété pour que
`question_suivante` ait un champ à rendre, sinon elle rend `None` — et c'est un cas testé
à part."""


def depot(produits=None) -> DepotEnMemoire:
    return DepotEnMemoire(produits=list(VARIES if produits is None else produits))


def sondage(etat: EtatSession, produits=None):
    return sonder_catalogue(etat, depot(produits), tolerance=TOLERANCE)


def question(etat: EtatSession, produits=None):
    return question_suivante(etat, depot(produits), tolerance=TOLERANCE)


def recherche(etat: EtatSession, produits=None):
    return rechercher_produits(etat, depot(produits), tour_client=1, tolerance=TOLERANCE)


# --------------------------------------------------------------------------- #
# Le budget est une contrainte dure
# --------------------------------------------------------------------------- #


def test_aucune_recherche_tant_que_le_budget_est_inconnu():
    """Règle — §3.10 et prompt §7 : le budget est une contrainte dure.

    C'est l'invariant que `Attente.AUCUNE_RECHERCHE_SANS_BUDGET` mesure sur l'agent, et sa
    docstring dit pourquoi c'est lui et non `BESOIN_DE_BUDGET` : ce qui compte est qu'aucun
    produit ne soit cité sans plafond, pas quel outil a servi à s'en apercevoir.
    """
    etat = etat_avec("monitor", critere("refresh_rate"))

    assert decider(etat) != Rechercher()
    assert decider(etat) == Sonder()


def test_le_budget_efface_par_un_changement_de_categorie_bloque_aussi_la_recherche():
    """Règle — §3.10 et étape 7, arbitrage D : changer de catégorie remet le budget à `None`.

    C'est le second chemin de `AUCUNE_RECHERCHE_SANS_BUDGET`, et le plus intéressant :
    reporter le budget en silence sur la nouvelle catégorie serait la seconde source de
    vérité que §3.10 ferme. Le scénario `categorie_efface_budget` le vise.
    """
    avec_ecran = etat_avec("monitor", critere("refresh_rate"), budget="250")
    assert decider(avec_ecran) == Rechercher()

    apres_bascule = etat_avec("cpu", tour_client=2)

    assert apres_bascule.budget_usd is None
    assert decider(apres_bascule) != Rechercher()


def test_le_budget_connu_ouvre_la_recherche_des_le_premier_passage():
    """Règle — §3.9 : le bon indicateur est le **délai avant première valeur**.

    Dès que rien ne bloque, on montre. Sonder d'abord « pour être sûr » coûterait un tour
    de plus sur le critère nº3, qui est un critère d'acceptation à médiane ≤ 2 tours.
    """
    assert decider(etat_avec("monitor", critere("refresh_rate"), budget="250")) == Rechercher()


# --------------------------------------------------------------------------- #
# Donner avant de demander
# --------------------------------------------------------------------------- #


def test_la_machine_ne_pose_jamais_de_question_en_premiere_action():
    """Règle — §3.9 et prompt §5 : ne jamais demander sans donner quelque chose en retour.

    `ask_clarification` clôt le tour. Le poser d'entrée, c'est l'interrogatoire que §3.9
    nomme : le client parle, et il ne reçoit qu'une question de plus.
    """
    action = decider(etat_avec("monitor"))

    assert not isinstance(action, DemanderPrecision)
    assert action == Sonder()


def test_la_route_vers_une_question_passe_par_le_sondage_puis_la_suggestion():
    """Règle — §3.9 et prompt §5, sur le tour entier : donner, **puis** demander.

    Le tour est déroulé comme la boucle du jalon 2 le fera. Ce que ce test fixe n'est pas
    la longueur de la trace mais son ordre : deux actions qui produisent du contexte
    arrivent avant celle qui clôt sur une question.
    """
    etat = etat_avec("monitor")

    premiere = decider(etat)
    deuxieme = decider(etat, sondage(etat))
    troisieme = decider(etat, question(etat))

    assert premiere == Sonder()
    assert deuxieme == Suggerer()
    assert troisieme == DemanderPrecision(CIBLE_BUDGET)


# --------------------------------------------------------------------------- #
# La question suggérée est une suggestion
# --------------------------------------------------------------------------- #


def test_le_champ_rendu_par_loutil_ne_commande_pas():
    """Règle — §3.8 et prompt §6 : `suggest_next_question` est un calcul de gain
    d'information, pas une recommandation de vente.

    L'outil rend ici **les deux** : le besoin de budget et le champ le plus discriminant.
    La machine arbitre, et elle prend le budget — parce que §3.10 en fait une contrainte
    dure et qu'aucune recherche n'est possible sans lui. Un test qui n'aurait pas de champ
    à côté du budget ne prouverait pas l'arbitrage, seulement l'absence de choix.
    """
    etat = etat_avec("monitor")
    suggeree = question(etat)

    assert suggeree.budget is not None
    assert suggeree.champ is not None, "sans champ concurrent, le test ne prouverait rien"
    assert decider(etat, suggeree) == DemanderPrecision(CIBLE_BUDGET)


def test_sans_besoin_de_budget_la_machine_demande_le_champ_le_plus_discriminant():
    """Règle — §3.8 : le champ dont la connaissance découperait le mieux l'espace restant.

    L'arbitrage de la règle précédente ne s'applique qu'au budget ; il ne dispense pas la
    machine d'écouter l'outil quand le budget est connu. `decider()` est **totale sur le
    type qu'elle reçoit**, et non sur le sous-ensemble que la boucle d'aujourd'hui lui
    envoie — voir la docstring de `_ce_quon_demande`.
    """
    etat = etat_avec("monitor", budget="300")
    suggeree = question(etat)

    assert suggeree.budget is None
    assert decider(etat, suggeree) == DemanderPrecision("panel_type")


def test_plus_rien_a_discriminer_est_une_reponse_pas_un_incident():
    """Règle — §3.8, cas limite : `ResultatQuestion.champ` vaut `None` quand plus rien ne
    discrimine.

    Sa docstring dit que « c'est une réponse, pas un incident ». La machine ne fabrique
    donc pas une question pour en avoir une : elle rédige.
    """
    etat = etat_avec("monitor", budget="300")
    suggeree = question(etat, produits=ecrans(3))

    assert (suggeree.budget, suggeree.champ) == (None, None)
    assert decider(etat, suggeree) == Rediger()


# --------------------------------------------------------------------------- #
# Une question à la fois
# --------------------------------------------------------------------------- #


def test_une_question_close_le_tour_et_il_ny_a_plus_de_decision():
    """Règle — prompt §5 : poser la question par l'outil, **une seule fois**, et n'appeler
    aucun autre outil dans le même message.

    `demander_precision` est terminal depuis l'amendement de §3.7. Redemander une décision
    après lui, c'est un troisième appel modèle dans le tour, donc le plancher de 2,00 appel
    par tour qui tombe.
    """
    etat = etat_avec("monitor")
    posee = demander_precision(etat, ArgumentsPrecision(question="Quel est votre budget ?"))

    with pytest.raises(TourDejaClos):
        decider(etat, posee)


# --------------------------------------------------------------------------- #
# Zéro résultat
# --------------------------------------------------------------------------- #


def test_un_zero_resultat_va_au_diagnostic_et_pas_a_une_seconde_recherche():
    """Règle — prompt §10 : dire pourquoi avec le diagnostic rendu par l'outil, proposer
    l'assouplissement calculé, et **ne jamais assouplir de soi-même**.

    Relancer une recherche serait précisément assouplir de soi-même : les critères n'ont
    pas bougé, donc la seule façon d'obtenir un résultat différent serait d'en changer un.
    """
    etat = etat_avec("monitor", critere("refresh_rate", valeur="500"), budget="250")
    vide = recherche(etat, produits=[])

    assert vide.resultat.produits == ()
    assert decider(etat, vide) == Rediger()


def test_la_machine_nassouplit_pas_le_budget_apres_un_zero_resultat():
    """Règle — §3.10 et prompt §10 : `prix_usd` est exclu des candidats au retrait, et le
    client tranche.

    Le moteur ne propose jamais de relever le budget ; il rend l'ensemble au-dessus avec
    son écart exact. La machine n'a donc aucune action qui touche au budget — et le test le
    constate sur l'union des actions, pas sur une exécution : aucune ne le porte.
    """
    etat = etat_avec("monitor", critere("refresh_rate"), budget="10")
    vide = recherche(etat, produits=[])
    action = decider(etat, vide)

    assert action == Rediger()
    assert not hasattr(action, "budget_usd")


# --------------------------------------------------------------------------- #
# Un composant à la fois
# --------------------------------------------------------------------------- #


def test_une_seule_recherche_par_message_du_client():
    """Règle — prompt §8 et étape 7, arbitrage E : une seule recherche de produits par
    message du client, un composant à la fois.

    La couche outils **refuse** déjà une seconde catégorie dans le même tour, et la machine
    ne la double pas : elle n'émet simplement jamais de seconde recherche, quelle que soit
    la catégorie. Le refus reste l'affaire de `rechercher_produits`.
    """
    etat = etat_avec("monitor", critere("refresh_rate"), budget="250")
    trouves = recherche(etat)

    assert trouves.resultat.produits != ()
    assert decider(etat, trouves) == Rediger()


def test_sans_categorie_aucun_outil_de_catalogue_nest_appele():
    """Règle — prompt §8 et étape 6, arbitrage K : la catégorie est obligatoire.

    C'est le scénario `hors_catalogue`, dont l'attente est `AUCUN_PRODUIT_CITE` : il n'y a
    pas de sous-catalogue, les trois outils lèveraient `CATEGORIE_ABSENTE`, et la bonne
    réponse est de le dire au client — pas d'appeler un outil qui refusera.
    """
    assert decider(EtatSession()) == Rediger()


# --------------------------------------------------------------------------- #
# Le jeton de parole, et ce que la machine ne peut pas faire
# --------------------------------------------------------------------------- #


def test_un_mouvement_refuse_ne_se_reessaie_pas():
    """Règle — prompt §9 et §3.17 : quand `record_criteria` refuse un mouvement, le dire au
    client au lieu de réessayer autrement.

    La machine tient la règle **par construction** : `enregistrer_criteres` n'est pas une
    action, donc aucune décision ne peut réécrire l'état. Le test le constate sur un état
    qui vient de voir un desserrage refusé — la décision suivante regarde le catalogue,
    elle ne retouche pas ce que le client a dit.
    """
    depart = etat_avec("monitor", critere("refresh_rate", valeur="240"), budget="200")
    enregistre = enregistrer_criteres(
        depart,
        ArgumentsEnregistrement(
            categorie="monitor",
            criteres=(
                ArgumentsCritere(champ="refresh_rate", operateur=Operateur.AU_MOINS, valeur="144"),
            ),
            budget_usd="300",
        ),
        tour_client=2,
    )

    assert enregistre.mouvements_refuses != (), "le jeton n'a pas mordu : le test ne prouve rien"
    assert decider(enregistre.etat, enregistre) == Rechercher()


def test_la_machine_ne_defait_pas_un_critere_quelle_ne_peut_pas_atteindre():
    """Règle — §3.17 : un critère déclaré ne se défait pas tout seul.

    Corollaire de la règle précédente, et il vaut la peine d'être asserté séparément :
    l'état que `decider()` reçoit est celui qu'elle rend au tour suivant, à l'identique.
    Une fonction de décision qui construirait un état est une porte de plus vers les
    critères, et l'arbitrage C de l'étape 7 n'en veut qu'une.
    """
    etat = etat_avec("monitor", critere("screen_size", Operateur.AU_MOINS, "27"), budget="250")

    decider(etat)
    decider(etat, sondage(etat))
    decider(etat, recherche(etat))

    assert etat == etat_avec(
        "monitor", critere("screen_size", Operateur.AU_MOINS, "27"), budget="250"
    )


# --------------------------------------------------------------------------- #
# Le plancher de deux appels modèle par tour
# --------------------------------------------------------------------------- #


def test_un_tour_se_termine_toujours_sur_une_action_terminale_unique():
    """Règle — §3.6, coût secondaire : l'agent consomme 2 à 4 appels API par tour, la
    machine en consomme deux.

    Le second appel est **soit** la rédaction **soit** la question, jamais les deux. Le
    test déroule les deux tours possibles et constate qu'aucun ne produit deux actions
    terminales, ni ne boucle : trois décisions au plus avant la fin.
    """
    sans_budget = etat_avec("monitor")
    trace_sans = [
        decider(sans_budget),
        decider(sans_budget, sondage(sans_budget)),
        decider(sans_budget, question(sans_budget)),
    ]

    avec_budget = etat_avec("monitor", critere("refresh_rate"), budget="250")
    trace_avec = [
        decider(avec_budget),
        decider(avec_budget, recherche(avec_budget)),
    ]

    for trace in (trace_sans, trace_avec):
        terminales = [action for action in trace if isinstance(action, DemanderPrecision | Rediger)]
        assert len(terminales) == 1
        assert trace.index(terminales[0]) == len(trace) - 1
