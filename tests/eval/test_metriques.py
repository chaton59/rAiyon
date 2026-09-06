"""Les métriques, sur des suites d'événements **construites à la main**.

Pas sur une conversation réelle : une métrique qu'on ne sait vérifier que par une cassette
est une métrique qu'on ne sait pas vérifier. Ces tests sont purs, et ils tournent dans
`make check`.
"""

import json
from decimal import Decimal

import pytest

from produits_de_test import fabriquer
from raiyon.agent.evenements import (
    CriteresMisAJour,
    MotifDeRepli,
    ProduitsTrouves,
    QuestionPosee,
    QuestionSuggeree,
    Repli,
    Texte,
    TexteRejete,
)
from raiyon.eval import metriques
from raiyon.eval.metriques import (
    Attente,
    PriseJouee,
    TourJoue,
    agreger,
    mesurer,
    questions_avant_premiere_valeur,
    tours_avant_premiere_valeur,
)
from raiyon.matching.criteres import Critere, Importance, Operateur, Optimisation
from raiyon.matching.moteur import ProduitHorsBudget, ResultatMatching
from raiyon.matching.relachement import Diagnostic, Motif, Proposition
from raiyon.tools.etat import EtatSession, MouvementRefuse
from raiyon.tools.outils import ResultatEnregistrement, ResultatRecherche, en_tool_result
from raiyon.validateur.contexte import contexte_des_messages
from raiyon.validateur.regles import CodeGrief, Grief
from raiyon.validateur.validateur import OrigineRejet, valider

ECRAN = fabriquer("monitor", 1, prix="142.99")
AUTRE = fabriquer("monitor", 2, prix="189.99")


def question(texte="Pour quel usage ?"):
    return QuestionPosee(question=texte, champ_vise=None)


def trouves_avec(*produits, diagnostic=None, hors_budget=()):
    return ProduitsTrouves(
        ResultatMatching(
            categorie="monitor",
            produits=tuple(produits),
            traces=(),
            au_dessus_du_budget=tuple(hors_budget),
            candidats_trouves=len(produits),
            diagnostic=diagnostic,
        )
    )


def proposition(champ="refresh_rate"):
    return Proposition(
        champ=champ,
        libelle_fr="fréquence de rafraîchissement",
        unite="Hz",
        importance=Importance.BLOQUANT,
        operateur=Operateur.AU_MOINS,
        valeur_demandee=Decimal("500"),
        valeur_atteignable=Decimal("280"),
        produits_rouverts=56,
        motif=Motif.CRITERE_TROP_STRICT,
        dernier_recours=False,
    )


def criteres(*valeurs, budget=None, refuses=()):
    return CriteresMisAJour(
        categorie="monitor",
        criteres=tuple(
            Critere(
                champ=champ,
                operateur=Operateur.AU_MOINS,
                valeur=Decimal(valeur),
                importance=Importance.BLOQUANT,
            )
            for champ, valeur in valeurs
        ),
        budget_usd=None if budget is None else Decimal(budget),
        optimisation=Optimisation.AUCUNE,
        mouvements_refuses=tuple(refuses),
    )


def prise(*evenements, messages=(), **reste):
    """Une prise d'un seul tour. `messages` reste vide : le contexte fourni est alors vide,
    et toute prose citant un produit lèverait un grief — ce qui est exactement ce que
    plusieurs de ces tests veulent constater.

    La coupe vaut `len(messages)` **parce qu'il n'y a qu'un tour** : tous les messages lui
    appartiennent. Ce n'est pas un raccourci de fixture, c'est la valeur juste dans ce cas,
    et l'écrire évite d'affaiblir la garde de `_coupe` pour la commodité des tests.
    """
    return PriseJouee(
        scenario="essai",
        prise=1,
        tours=(
            TourJoue("bonjour", tuple(evenements), iterations=1, messages_a_la_fin=len(messages)),
        ),
        messages=tuple(messages),
        **reste,
    )


# --------------------------------------------------------------------------- #
# 5. Questions avant première valeur — le critère nº3
# --------------------------------------------------------------------------- #


def test_deux_questions_puis_des_produits_rendent_deux():
    assert questions_avant_premiere_valeur([question(), question(), trouves_avec(ECRAN)]) == 2


def test_une_suite_qui_commence_par_des_produits_rend_zero():
    assert questions_avant_premiere_valeur([trouves_avec(ECRAN), question()]) == 0


def test_les_questions_posees_apres_la_premiere_valeur_ne_comptent_pas():
    """C'est le **délai avant première valeur** de §3.9, pas un compte de questions."""
    suite = [question(), trouves_avec(ECRAN), question(), question()]
    assert questions_avant_premiere_valeur(suite) == 1


def test_un_zero_resultat_nest_pas_une_valeur():
    """`ProduitsTrouves` vide n'a rien montré au client : le compteur continue."""
    suite = [question(), trouves_avec(), question(), trouves_avec(ECRAN)]
    assert questions_avant_premiere_valeur(suite) == 2


def test_une_prise_sans_aucune_valeur_rend_none_et_sort_de_la_mediane():
    """« Zéro question avant une valeur jamais venue » serait le meilleur score possible
    pour le pire comportement possible. La prise est donc exclue, et le rapport la compte."""
    assert questions_avant_premiere_valeur([question(), question()]) is None

    mesures = agreger([mesurer(prise(question(), question()))])
    assert mesures.questions_par_prise == ()
    assert mesures.prises_sans_valeur == 1
    assert mesures.mediane_des_questions is None
    assert mesures.critere_3 is None


# --------------------------------------------------------------------------- #
# Critère nº3 — il compte des **tours client** depuis le correctif de l'étape 12
# --------------------------------------------------------------------------- #


def prise_multi(*tours_devenements, **reste):
    """Une prise à plusieurs tours client, chacun portant sa liste d'événements."""
    return PriseJouee(
        scenario="essai",
        prise=1,
        tours=tuple(
            TourJoue(f"message {rang}", tuple(evenements), 1)
            for rang, evenements in enumerate(tours_devenements, start=1)
        ),
        messages=(),
        **reste,
    )


def test_le_critere_3_compte_les_tours_client_pas_les_questions():
    """Le client parle deux fois avant de voir des produits : la mesure vaut **2**.

    Le nombre de questions posées dans ces tours n'y change rien — c'est justement le
    point : un agent qui explique longuement sans rien montrer coûte un tour, exactement
    comme un agent qui interroge.
    """
    tours = prise_multi(
        [question(), question(), question()],
        [trouves_avec(ECRAN)],
    ).tours
    assert tours_avant_premiere_valeur(tours) == 2


def test_une_valeur_livree_au_premier_tour_vaut_un():
    """1, pas 0 : le client a bien dû parler une fois. Le rang est 1-indexé."""
    assert tours_avant_premiere_valeur(prise_multi([trouves_avec(ECRAN)]).tours) == 1


def test_un_zero_resultat_ne_compte_pas_comme_une_valeur_livree():
    """Le client n'a rien vu : le compteur continue au tour suivant."""
    tours = prise_multi([trouves_avec()], [trouves_avec(ECRAN)]).tours
    assert tours_avant_premiere_valeur(tours) == 2


def test_une_prise_qui_ne_livre_jamais_de_valeur_reste_none_et_sort_de_la_mediane():
    """Le comportement de l'étape 12, à ne pas casser : « zéro tour avant une valeur qui
    n'est jamais venue » serait le meilleur score possible pour le pire comportement."""
    assert tours_avant_premiere_valeur(prise_multi([question()], [question()]).tours) is None

    mesures = agreger([mesurer(prise_multi([question()], [question()]))])
    assert mesures.tours_par_prise == ()
    assert mesures.prises_sans_valeur == 1
    assert mesures.mediane_des_tours is None
    assert mesures.critere_3 is None


def test_trois_tours_avant_la_premiere_valeur_font_tomber_le_critere_3():
    """Le seuil de 2 mord désormais : c'est l'interrogatoire que §3.9 nomme."""
    mesures = agreger([mesurer(prise_multi([question()], [question()], [trouves_avec(ECRAN)]))])
    assert mesures.mediane_des_tours == 3.0
    assert mesures.critere_3 is False


def test_les_questions_restent_calculees_et_publiees_sans_seuil():
    """Elles ne mesurent plus le critère — elles mesurent « donner avant de demander »."""
    mesuree = mesurer(prise_multi([question(), question()], [trouves_avec(ECRAN)]))
    assert mesuree.tours_avant_valeur == 2
    assert mesuree.questions_avant_valeur == 2
    assert agreger([mesuree]).questions_par_prise == (2,)


# --------------------------------------------------------------------------- #
# Les règles jamais déclenchées — **dérivées de `CodeGrief`**
# --------------------------------------------------------------------------- #


def test_sans_aucun_rejet_toutes_les_regles_sont_declarees_muettes():
    """⚠️ **Le test qui interdit une liste écrite à la main.**

    Il est dérivé de `CodeGrief` par construction : un sixième code ajouté à l'énumération
    apparaît ici sans qu'on touche à rien. Une liste codée en dur ferait échouer cette
    assertion le jour de cet ajout, ce qui est exactement le service qu'on lui demande.
    """
    mesures = agreger([mesurer(prise(trouves_avec(ECRAN)))])
    assert mesures.codes_declenches == frozenset()
    assert mesures.codes_jamais_declenches == tuple(CodeGrief)
    assert len(mesures.codes_jamais_declenches) == len(CodeGrief)


def test_un_code_declenche_sort_de_la_liste_des_muettes():
    mesuree = mesurer(
        prise(
            TexteRejete(
                "Je vous propose l'Odyssée de Samsung.",
                (Grief(CodeGrief.NOM_REECRIT, "l'Odyssée de Samsung", "recopier"),),
                1,
                OrigineRejet.TEXTE,
            )
        )
    )
    mesures = agreger([mesuree])
    assert mesures.codes_declenches == frozenset({CodeGrief.NOM_REECRIT})
    assert CodeGrief.NOM_REECRIT not in mesures.codes_jamais_declenches
    assert set(mesures.codes_jamais_declenches) | mesures.codes_declenches == set(CodeGrief)


def test_les_deux_ensembles_partitionnent_toujours_lenumeration():
    """La propriété qui rend la ligne du rapport lisible : rien ne tombe entre les deux."""
    mesures = agreger(
        [
            mesurer(
                prise(
                    TexteRejete(
                        "x", (Grief(CodeGrief.ID_INCONNU, "x", "y"),), 1, OrigineRejet.QUESTION
                    )
                )
            )
        ]
    )
    declenches = mesures.codes_declenches
    muets = set(mesures.codes_jamais_declenches)
    assert declenches & muets == set()
    assert declenches | muets == set(CodeGrief)


# --------------------------------------------------------------------------- #
# 6. Un repli compte comme repli, pas comme réponse
# --------------------------------------------------------------------------- #


def test_un_repli_de_validation_compte_comme_repli_et_non_comme_reponse():
    """Le tour est **servi, mais dégradé** : le client a lu une phrase écrite en Python.

    C'est la troisième couche du rapport, et celle qui empêche de lire un critère nº1 à
    zéro comme une bonne nouvelle.
    """
    mesuree = mesurer(
        prise(
            TexteRejete(
                texte="Voici le monitor-inconnu.",
                griefs=(Grief(CodeGrief.ID_INCONNU, "monitor-inconnu", "chercher d'abord"),),
                tentative=1,
                origine=OrigineRejet.TEXTE,
            ),
            Repli("Je préfère vérifier.", 2, ("search_products",), MotifDeRepli.VALIDATION),
        )
    )

    assert mesuree.replis == (MotifDeRepli.VALIDATION,)
    # ⚠️ Le message du repli n'est **pas** validé : il est écrit en Python, le relire
    # reviendrait à valider `repli.py` contre lui-même.
    assert mesuree.griefs_livres == ()

    mesures = agreger([mesuree])
    assert mesures.tours_replies == 1
    assert mesures.taux_de_repli == 1.0
    assert mesures.critere_1 is True, "critère nº1 vert, et pourtant 100 % de repli"


def test_les_deux_motifs_de_repli_sont_comptes_separement():
    """Un prompt à corriger et une couche outils à corriger ne sont pas le même défaut."""
    mesures = agreger(
        [
            mesurer(prise(Repli("a", 8, (), MotifDeRepli.MAX_ITERATIONS))),
            mesurer(prise(Repli("b", 2, (), MotifDeRepli.VALIDATION))),
        ]
    )
    assert sorted(motif.value for motif in mesures.replis) == ["max_iterations", "validation"]


def test_les_rejets_sont_comptes_par_origine_et_par_code():
    """Une conversation contient beaucoup plus de questions que de recommandations :
    un taux global masquerait lequel des deux chemins fuit (§ `OrigineRejet`)."""
    mesuree = mesurer(
        prise(
            TexteRejete(
                "x puis z",
                (Grief(CodeGrief.ID_INCONNU, "x", "y"), Grief(CodeGrief.NOM_REECRIT, "z", "w")),
                1,
                OrigineRejet.TEXTE,
            ),
            TexteRejete(
                "Il est à 180 $ ?",
                (Grief(CodeGrief.MONTANT_NON_FOURNI, "180 $", "y"),),
                2,
                OrigineRejet.QUESTION,
            ),
        )
    )
    assert len(mesuree.rejets) == 3
    assert {(rejet.origine.value, rejet.code.value) for rejet in mesuree.rejets} == {
        ("texte", "id_inconnu"),
        ("texte", "nom_reecrit"),
        ("question", "montant_non_fourni"),
    }


# --------------------------------------------------------------------------- #
# Les critères nº1 et nº2 — le second est un code de grief, pas une seconde lecture
# --------------------------------------------------------------------------- #


def test_la_prose_livree_est_relue_par_les_memes_cinq_regles():
    """Aucune expression régulière : la seule lecture de prose est le validateur (arb. E)."""
    mesuree = mesurer(prise(Texte("Je vous propose le monitor-0000000009 à 199 $.")))
    assert [grief.code for grief in mesuree.griefs_livres] == [
        CodeGrief.ID_INCONNU,
        CodeGrief.MONTANT_NON_FOURNI,
    ]
    assert agreger([mesuree]).critere_1 is False


def test_la_question_dask_clarification_est_relue_elle_aussi():
    """C'est le chemin le plus fréquent d'une conversation (correctif de l'étape 9)."""
    mesuree = mesurer(prise(question("Le monitor-0000000009 vous irait-il ?")))
    assert [grief.code for grief in mesuree.griefs_livres] == [CodeGrief.ID_INCONNU]


def test_le_critere_2_est_le_seul_code_ecart_non_dit():
    """`ECART_NON_DIT` **est** le critère nº2 ; les cinq autres codes sont le nº1.

    Séparer par le code plutôt que par une seconde lecture évite d'écrire deux fois la
    règle qui distingue les deux critères.
    """
    resultat = ResultatRecherche(
        etat=EtatSession(),
        resultat=ResultatMatching(
            categorie="monitor",
            produits=(AUTRE,),
            traces=(),
            au_dessus_du_budget=(ProduitHorsBudget(ECRAN, Decimal("12.99")),),
            candidats_trouves=1,
        ),
    )
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_1",
                    "content": json.dumps(en_tool_result(resultat), ensure_ascii=False),
                    "is_error": False,
                }
            ],
        }
    ]
    mesuree = mesurer(prise(Texte(f"Le {ECRAN.nom} est à 142,99 $."), messages=messages))

    assert [grief.code for grief in mesuree.violations_budget] == [CodeGrief.ECART_NON_DIT]
    assert mesuree.griefs_livres == ()
    mesures = agreger([mesuree])
    assert mesures.critere_1 is True
    assert mesures.critere_2 is False


# --------------------------------------------------------------------------- #
# 8. Le critère nº4 ne porte que sur les scénarios à attendu
# --------------------------------------------------------------------------- #


def test_un_scenario_sans_attendu_nentre_pas_dans_le_calcul_du_numero_4():
    mesures = agreger(
        [
            mesurer(prise(trouves_avec(ECRAN), attendu=ECRAN.id)),
            mesurer(prise(trouves_avec(AUTRE))),  # sans attendu
        ]
    )
    assert mesures.prises_avec_attendu == 1
    assert mesures.attendus_en_top3 == 1
    assert mesures.part_attendus_en_top3 == 1.0


def test_le_produit_attendu_absent_du_classement_fait_tomber_le_numero_4():
    mesures = agreger([mesurer(prise(trouves_avec(AUTRE), attendu=ECRAN.id))])
    assert mesures.part_attendus_en_top3 == 0.0
    assert mesures.critere_4 is False


def test_sans_aucun_attendu_le_numero_4_est_sans_objet_et_non_a_zero():
    """Zéro dirait « le moteur se trompe » là où il faut lire « rien n'a été mesuré »."""
    mesures = agreger([mesurer(prise(trouves_avec(ECRAN)))])
    assert mesures.part_attendus_en_top3 is None
    assert mesures.critere_4 is None


# --------------------------------------------------------------------------- #
# Le critère nº6 — zéro résultat traité
# --------------------------------------------------------------------------- #


def test_un_zero_resultat_sans_diagnostic_nest_pas_traite():
    mesures = agreger([mesurer(prise(trouves_avec()))])
    assert (mesures.zero_resultats, mesures.zero_resultats_traites) == (1, 0)
    assert mesures.critere_6 is False


def test_un_zero_resultat_avec_diagnostic_et_propositions_est_traite():
    diagnostic = Diagnostic(Motif.CRITERE_TROP_STRICT, (proposition(),))
    mesures = agreger([mesurer(prise(trouves_avec(diagnostic=diagnostic)))])
    assert (mesures.zero_resultats, mesures.zero_resultats_traites) == (1, 1)
    assert mesures.critere_6 is True


def test_un_budget_trop_bas_sans_proposition_est_traite_par_la_zone_de_tolerance():
    """§3.10 : la réponse est cet ensemble-là, avec son écart exact — pas une invitation
    à relever le budget. Exiger une proposition ferait échouer le cas que §3.10 traite
    le mieux."""
    evenement = trouves_avec(
        diagnostic=Diagnostic(Motif.BUDGET_TROP_BAS, ()),
        hors_budget=(ProduitHorsBudget(ECRAN, Decimal("12.99")),),
    )
    assert agreger([mesurer(prise(evenement))]).critere_6 is True


def test_aucun_retrait_simple_est_une_issue_a_lui_seul():
    """Le moteur dit qu'aucun retrait d'un seul critère ne rouvre le catalogue ; explorer
    les combinaisons de degré 2 est hors périmètre, et le dire **est** la réponse."""
    evenement = trouves_avec(diagnostic=Diagnostic(Motif.AUCUN_RETRAIT_SIMPLE, ()))
    assert agreger([mesurer(prise(evenement))]).critere_6 is True


def test_le_diagnostic_attendu_est_verifie_par_son_motif():
    mesuree = mesurer(
        prise(
            trouves_avec(diagnostic=Diagnostic(Motif.DONNEE_ABSENTE, (proposition(),))),
            diagnostic_attendu=Motif.BUDGET_TROP_BAS,
        )
    )
    assert mesuree.diagnostic_tenu is False
    assert mesuree.conforme is False
    assert agreger([mesuree]).diagnostics_manques[0][2] is Motif.BUDGET_TROP_BAS


# --------------------------------------------------------------------------- #
# Les attentes binaires — lues sur les événements, jamais sur la prose
# --------------------------------------------------------------------------- #


def test_le_besoin_de_budget_est_un_fait_publie_et_non_une_exigence():
    """La première exécution du harnais a montré que l'agent gère très bien un budget
    absent **sans** appeler `suggest_next_question` : il sonde, puis pose la question en
    texte. Une attente écrite sur l'outil mesurait donc l'outil, pas le produit.

    Le fait reste relevé — le rapport le publie sans seuil — et l'exigence est ailleurs.
    """
    from raiyon.tools.outils import BesoinDeBudget

    mesuree = mesurer(
        prise(
            QuestionSuggeree(
                categorie="monitor", candidats=46, budget=BesoinDeBudget(None), champ=None
            )
        )
    )
    assert Attente.BESOIN_DE_BUDGET in mesuree.faits
    assert mesuree.attentes_manquees == frozenset()
    assert agreger([mesuree]).prises_ou_loutil_a_signale_le_budget == 1


def test_une_recherche_sans_budget_connu_fait_tomber_lattente():
    """L'exigence réelle de « demander le budget avant de chercher »."""
    mesuree = mesurer(
        prise(
            criteres(("refresh_rate", "144")),  # aucun budget
            trouves_avec(ECRAN),
            attentes=frozenset({Attente.AUCUNE_RECHERCHE_SANS_BUDGET}),
        )
    )
    assert mesuree.attentes_manquees == frozenset({Attente.AUCUNE_RECHERCHE_SANS_BUDGET})


def test_une_recherche_apres_un_budget_pose_tient_lattente():
    mesuree = mesurer(
        prise(
            criteres(("refresh_rate", "144"), budget="145"),
            trouves_avec(ECRAN),
            attentes=frozenset({Attente.AUCUNE_RECHERCHE_SANS_BUDGET}),
        )
    )
    assert mesuree.attentes_manquees == frozenset()


def test_un_budget_efface_puis_une_recherche_fait_tomber_lattente():
    """**Reporter le budget en silence** sur la nouvelle catégorie serait la seconde
    source de vérité que §3.10 ferme (étape 7, arbitrage D)."""
    mesuree = mesurer(
        PriseJouee(
            scenario="essai",
            prise=1,
            tours=(
                TourJoue("t1", (criteres(("refresh_rate", "144"), budget="250"),), 1),
                TourJoue("t2", (criteres(budget=None), trouves_avec(ECRAN)), 1),
            ),
            messages=(),
            attentes=frozenset({Attente.AUCUNE_RECHERCHE_SANS_BUDGET}),
        )
    )
    assert mesuree.attentes_manquees == frozenset({Attente.AUCUNE_RECHERCHE_SANS_BUDGET})


def test_une_attente_non_tenue_est_nommee_dans_lagregat():
    mesuree = mesurer(prise(trouves_avec(ECRAN), attentes=frozenset({Attente.ZERO_RESULTAT})))
    assert mesuree.attentes_manquees == frozenset({Attente.ZERO_RESULTAT})
    assert agreger([mesuree]).attentes_manquees == (("essai", 1, Attente.ZERO_RESULTAT),)


def test_aucun_produit_cite_est_tenu_quand_rien_na_ete_montre():
    """L'attente de la catégorie hors catalogue : ne rien inventer."""
    mesuree = mesurer(prise(question(), attentes=frozenset({Attente.AUCUN_PRODUIT_CITE})))
    assert mesuree.attentes_manquees == frozenset()


def test_le_mouvement_refuse_se_lit_sur_criteres_mis_a_jour():
    """§3.17 : le jeton de parole a refusé, et l'événement le porte."""
    refus = MouvementRefuse("refresh_rate", Operateur.AU_MOINS, "un desserrage par tour")
    mesuree = mesurer(
        prise(
            criteres(("refresh_rate", "240"), budget="200", refuses=(refus,)),
            attentes=frozenset({Attente.MOUVEMENT_REFUSE, Attente.CRITERE_TENU}),
        )
    )
    assert mesuree.attentes_manquees == frozenset()


def test_un_critere_refuse_qui_finit_par_bouger_fait_tomber_critere_tenu():
    """Si le desserrage avait été obtenu par un autre chemin, la valeur aurait changé."""
    refus = MouvementRefuse("refresh_rate", Operateur.AU_MOINS, "un desserrage par tour")
    mesuree = mesurer(
        PriseJouee(
            scenario="essai",
            prise=1,
            tours=(
                TourJoue("t1", (criteres(("refresh_rate", "240"), refuses=(refus,)),), 1),
                TourJoue("t2", (criteres(("refresh_rate", "144")),), 1),
            ),
            messages=(),
            attentes=frozenset({Attente.CRITERE_TENU}),
        )
    )
    assert mesuree.attentes_manquees == frozenset({Attente.CRITERE_TENU})


def test_le_budget_efface_se_lit_sur_un_budget_pose_puis_rendu_a_none():
    """Le changement de catégorie de l'étape 7, arbitrage D."""
    mesuree = mesurer(
        PriseJouee(
            scenario="essai",
            prise=1,
            tours=(
                TourJoue("t1", (criteres(("refresh_rate", "144"), budget="250"),), 1),
                TourJoue("t2", (criteres(budget=None),), 1),
            ),
            messages=(),
            attentes=frozenset({Attente.BUDGET_EFFACE}),
        )
    )
    assert mesuree.attentes_manquees == frozenset()


@pytest.mark.parametrize("iterations", [(1,), (1, 3), (8, 8, 2)])
def test_les_iterations_par_tour_sont_publiees_telles_quelles(iterations):
    mesuree = mesurer(
        PriseJouee(
            scenario="essai",
            prise=1,
            tours=tuple(TourJoue("t", (), nombre) for nombre in iterations),
            messages=(),
        )
    )
    assert mesuree.iterations == iterations
    assert agreger([mesuree]).tours == len(iterations)


# --------------------------------------------------------------------------- #
# Les deux observations de l'étape 13 — et ce qui les empêche de devenir des règles
# --------------------------------------------------------------------------- #


def test_le_compteur_de_chiffres_reutilise_lextraction_du_validateur():
    """**Une seule lecture de nombre dans ce dépôt** (jalon 0, point D).

    Le jour où l'écriture d'un nombre change — un séparateur de milliers de plus, une
    notation qu'un modèle emploie —, les deux lectures doivent changer ensemble. Deux
    extractions finissent par en dire deux choses, et l'une des deux devient fausse sans
    que rien ne le signale.
    """
    from raiyon.validateur import extraction

    assert metriques.nombres is extraction.nombres


CLASSES_DE_CHIFFRES_TOLEREES = {
    ('("liste numérotée", r"(?m)^[ \\t]*\\d+\\.[ \\t]+"),', "raiyon/eval/metriques.py"),
}
"""La **seule** classe de chiffres admise dans `raiyon.eval`, et ce qu'elle fait.

Elle reconnaît un **marqueur de liste markdown** — « 1. », « 2. » en début de ligne —,
c'est-à-dire une forme de rédaction que le front n'affiche pas. Elle ne lit aucune valeur :
le chiffre y est un caractère de mise en forme, jamais un nombre qu'on compare à un
`tool_result`.

Toute autre serait une seconde lecture de nombre, et le jour où l'écriture d'un nombre
change, l'une des deux deviendrait fausse en silence."""


def test_aucun_module_du_harnais_ne_reecrit_une_extraction_de_nombre():
    """La contre-épreuve du test ci-dessus, **sur le disque**.

    Le test précédent constate que le bon appel existe ; celui-ci constate qu'aucun autre
    n'a été écrit à côté. C'est le même geste que `test_isolation_eval` : la propriété se
    vérifie sur les fichiers, pas sur les intentions.
    """
    from pathlib import Path

    racine = Path(metriques.__file__).parent
    trouvees = {
        (ligne.strip(), f"raiyon/eval/{chemin.name}")
        for chemin in sorted(racine.glob("*.py"))
        for ligne in chemin.read_text(encoding="utf-8").splitlines()
        if r"\d" in ligne or "[0-9]" in ligne
    }
    assert trouvees == CLASSES_DE_CHIFFRES_TOLEREES, (
        "une classe de chiffres non déclarée dans `raiyon.eval` : "
        f"{sorted(trouvees - CLASSES_DE_CHIFFRES_TOLEREES)}. Les nombres se lisent par "
        "`extraction.nombres`, une seule fois — voir CLASSES_DE_CHIFFRES_TOLEREES."
    )


def test_une_prose_de_domaine_chiffree_ne_fait_pas_echouer_leval():
    """**Le test qui empêche de repromouvoir le compteur en attente** (jalon 0, point D).

    L'attente évidente — « aucun chiffre sur un tour de domaine » — a été écrite puis
    refusée : elle est vraie sur v1 et deviendrait fausse dès qu'on demande au modèle de
    basculer sur ce que le catalogue contient, ce qui est le bon comportement. Elle
    pénaliserait le changement qu'elle évalue.

    Six mois plus tard, personne ne relira ce paragraphe. Ce test, si.
    """
    chiffree = PriseJouee(
        scenario="question_de_domaine",
        prise=1,
        tours=(TourJoue("IPS ou VA ?", (Texte("VA : environ 3000:1 à 6000:1."),), 1),),
        messages=(),
        tours_de_domaine=frozenset({1}),
    )
    mesures = agreger([mesurer(chiffree)])

    assert mesures.chiffres_de_domaine == 4
    assert mesures.prises[0].conforme is True
    assert mesures.bloquants_tenus is True, (
        "le compteur de chiffres est une observation : il ne décide de rien, et surtout "
        "pas du code de sortie de `make eval`"
    )


def test_un_tour_non_declare_de_domaine_nentre_pas_dans_le_compteur():
    """Le scénario **déclare** ses tours de domaine ; le harnais ne les devine pas."""
    prose = "Voici 3 écrans entre 142,99 $ et 229,00 $."
    tours = (TourJoue("un écran ?", (Texte(prose),), 1),)

    sans = mesurer(PriseJouee("essai", 1, tours, ()))
    avec = mesurer(PriseJouee("essai", 1, tours, (), tours_de_domaine=frozenset({1})))

    assert sans.chiffres_de_domaine == 0
    assert sans.prose_de_domaine == ()
    assert avec.chiffres_de_domaine == 3, "3, 142,99 et 229,00 — une virgule décimale, un nombre"
    assert avec.prose_de_domaine == ((1, (prose,)),)


def test_le_texte_refuse_porte_son_tour_et_sa_phrase():
    """Onze griefs dans cinq tours et onze griefs dans onze tours ne décrivent pas le même
    défaut — d'où le rang du tour, que l'agrégat plat des événements ne porte pas."""
    mesuree = mesurer(
        PriseJouee(
            scenario="changement_davis",
            prise=2,
            tours=(
                TourJoue("un écran ?", (), 1),
                TourJoue(
                    "et en QHD ?",
                    (
                        TexteRejete(
                            "Le MSI existe en QHD. Il est à 47 $ de plus.",
                            (Grief(CodeGrief.MONTANT_NON_FOURNI, "47 $", "reprendre `prix_usd`"),),
                            1,
                            OrigineRejet.TEXTE,
                        ),
                    ),
                    2,
                ),
            ),
            messages=(),
        )
    )

    (refus,) = mesuree.refus
    assert (refus.scenario, refus.prise, refus.tour) == ("changement_davis", 2, 2)
    assert refus.extrait == "47 $"
    assert refus.phrase == "Il est à 47 $ de plus"
    assert len(mesuree.refus) == len(mesuree.rejets)


def test_un_extrait_introuvable_publie_le_texte_entier_plutot_que_rien():
    """Publier trop de contexte est sans danger ; en publier trop peu perdrait l'opération
    que l'appendice existe pour nommer."""
    mesuree = mesurer(
        PriseJouee(
            scenario="essai",
            prise=1,
            tours=(
                TourJoue(
                    "?",
                    (
                        TexteRejete(
                            "Une phrase. Une autre.",
                            (Grief(CodeGrief.NOM_REECRIT, "absent du texte", "recopier"),),
                            1,
                            OrigineRejet.TEXTE,
                        ),
                    ),
                    1,
                ),
            ),
            messages=(),
        )
    )

    assert mesuree.refus[0].phrase == "Une phrase. Une autre."


def test_lusage_ne_traverse_jamais_le_protocol_du_client():
    """⚠️ **La contrainte du jalon 1, point C, vérifiée sur le disque.**

    Le coût d'un appel est posé sur `ClientAnthropic`, pas dans `ReponseLLM` ni dans le
    `Protocol` `ClientLLM`. L'y mettre obligerait le faux client de l'étape 8, le client de
    cassette et les surcharges de l'API à fabriquer une valeur qu'aucun d'eux ne possède —
    exactement la raison qui a fait écarter la capture de l'identifiant de modèle résolu.

    Ce test constate que le contrat de la boucle n'a pas bougé. Sans lui, la prochaine
    information « utile » qu'on veut faire remonter passera par là, et la couture qui rend
    `make eval` possible sans clé se refermera un champ à la fois.
    """
    from dataclasses import fields

    from raiyon.agent.client import ReponseLLM

    assert {champ.name for champ in fields(ReponseLLM)} == {"blocs", "fin"}


def test_un_client_qui_ne_mesure_rien_laisse_le_cumul_a_zero():
    """Le rejeu n'a pas d'usage, et c'est **exact** : une cassette rejouée ne consomme rien.

    L'enregistreur lit `dernier_usage` par `getattr` sur le client qu'il enveloppe. Un
    client qui n'en expose pas — le faux client, le client de cassette — laisse le cumul à
    zéro plutôt que de faire échouer l'enregistrement.
    """
    from raiyon.agent.client import ReponseLLM
    from raiyon.eval.client import ClientEnregistreur

    class SansUsage:
        def repondre(self, *, systeme, outils, messages):
            return ReponseLLM(blocs=[{"type": "text", "text": "bonjour"}], fin="end_turn")

    enregistreur = ClientEnregistreur(SansUsage())
    enregistreur.repondre(systeme="s", outils=[], messages=[])

    assert enregistreur.usage.appels == 0
    assert enregistreur.en_cassette.__doc__ is not None


# --------------------------------------------------------------------------- #
# 14. La coupe par tour — l'état est destructif (étape 32)
# --------------------------------------------------------------------------- #


def _en_message(resultat):
    """Un `tool_result` seul dans son message, comme la boucle les persiste."""
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "tu_1",
                "content": json.dumps(en_tool_result(resultat), ensure_ascii=False),
                "is_error": False,
            }
        ],
    }


def _budget_enregistre(categorie, budget):
    """Le `tool_result` de `record_criteria` — **le seul qui porte le budget**.

    Celui de `search_products` ne le porte pas : `ContexteFourni.budget_usd` se lit sur ce
    que le modèle a vu, et c'est l'enregistrement qui le lui montre.
    """
    etat = EtatSession(
        categorie_courante=categorie,
        budget_usd=None if budget is None else Decimal(budget),
    )
    return _en_message(
        ResultatEnregistrement(
            etat=etat,
            categorie=categorie,
            criteres=(),
            budget_usd=etat.budget_usd,
            optimisation=Optimisation.AUCUNE,
            mouvements_refuses=(),
        )
    )


def _ecran_trouve():
    """Le `tool_result` de `search_products` qui met `ECRAN` et son prix au contexte."""
    return _en_message(
        ResultatRecherche(
            etat=EtatSession(categorie_courante="monitor", budget_usd=Decimal("250")),
            resultat=ResultatMatching(
                categorie="monitor",
                produits=(ECRAN,),
                traces=(),
                au_dessus_du_budget=(),
                candidats_trouves=1,
            ),
        )
    )


def test_la_prose_se_relit_contre_le_contexte_de_son_tour_pas_celui_de_la_fin():
    """**L'état est destructif : le contexte de fin n'est pas un sur-ensemble.**

    Un changement de catégorie remet `budget_usd` à `None` (arbitrage D), et
    `ContexteFourni.budget_usd` dit que la dernière valeur rencontrée gagne, `null`
    compris. Une phrase qui cite le budget **à côté d'un produit** — la seule exception de
    la règle 2, écrite à l'étape 9 — est donc vraie au tour où elle est écrite et fausse
    relue depuis la fin.

    Le défaut était réel et mesuré : `categorie_efface_budget.3` a rendu le critère nº1
    rouge sur une phrase que le validateur avait laissé passer à raison.
    """
    prose = f"Le {ECRAN.nom} à 142,99 $ tient dans vos 250 $."
    messages = (
        _budget_enregistre("monitor", "250"),
        _ecran_trouve(),
        # Le tour 2 : le client passe au processeur, et le budget tombe (arbitrage D).
        _budget_enregistre("cpu", None),
    )
    jouee = PriseJouee(
        scenario="budget_efface",
        prise=1,
        tours=(
            TourJoue("un écran ?", (Texte(prose),), 1, messages_a_la_fin=2),
            TourJoue("en fait, un processeur", (), 1, messages_a_la_fin=3),
        ),
        messages=messages,
    )

    assert mesurer(jouee).griefs_livres == ()

    # ⚠️ **La contre-épreuve, sans laquelle ce test passerait au vert pour la mauvaise
    # raison** — il suffirait de retirer « 250 $ » de la prose. Elle constate que le
    # contexte de fin, lui, accuse : c'est la lecture que l'étape 32 a retirée.
    contexte_de_la_fin = contexte_des_messages(list(messages))
    assert [grief.code for grief in valider(prose, contexte_de_la_fin).griefs] == [
        CodeGrief.PRIX_ETRANGER_AU_PRODUIT
    ]


def test_une_coupe_manquante_est_une_erreur_pas_une_lecture_a_la_fin():
    """Deviner rétablirait en silence le défaut que la coupe vient de fermer."""
    jouee = PriseJouee(
        scenario="essai",
        prise=1,
        tours=(TourJoue("un écran ?", (Texte("bonjour"),), 1),),
        messages=(_budget_enregistre("monitor", "250"),),
    )
    with pytest.raises(metriques.CoupeManquante):
        mesurer(jouee)


# --------------------------------------------------------------------------- #
# 15. « Demande le budget dans le tour où tu livres » (étape 32)
# --------------------------------------------------------------------------- #


def _prise_qui_livre_sans_budget(prose):
    """Un tour qui montre des produits alors qu'aucun budget n'a été enregistré."""
    return PriseJouee(
        scenario="budget_absent",
        prise=1,
        tours=(
            TourJoue(
                "un écran pour jouer",
                (criteres(("refresh_rate", "144")), trouves_avec(ECRAN), Texte(prose)),
                1,
                messages_a_la_fin=0,
            ),
        ),
        messages=(),
    )


def test_livrer_sans_budget_est_tenu_si_le_budget_est_demande_dans_le_meme_tour():
    """La formulation réelle de v3, reprise mot pour mot de `budget_absent.1`."""
    prose = (
        "Voici trois écrans qui collent à vos critères.\n\n"
        "Vous avez un budget en tête ? Et la définition vous importe : "
        "plutôt du 1080p ou vous visez du 1440p ?"
    )
    tenues = metriques.mesurer(_prise_qui_livre_sans_budget(prose)).faits
    assert Attente.BUDGET_DEMANDE_EN_LIVRANT in tenues


def test_livrer_sans_budget_et_sans_le_demander_echoue():
    """**L'attente est plus contraignante que celle qu'elle remplace, et le voici.**

    « Aucune recherche sans budget » se tenait en ne faisant rien. Celle-ci interdit de
    montrer sans demander : la prose ci-dessous pose une vraie question, utile, et sur autre
    chose — c'est exactement la manière dont v3 peut échouer, et il ne faut pas que ce test
    passe au vert sur une prose muette.
    """
    prose = "Voici trois écrans qui collent à vos critères.\n\nPlutôt du 1080p ou du 1440p ?"
    tenues = metriques.mesurer(_prise_qui_livre_sans_budget(prose)).faits
    assert Attente.BUDGET_DEMANDE_EN_LIVRANT not in tenues


def test_le_budget_connu_dispense_de_le_demander():
    """L'attente ne porte que sur les tours qui livrent **sans** budget en vigueur."""
    jouee = PriseJouee(
        scenario="budget_serre",
        prise=1,
        tours=(
            TourJoue(
                "un écran à 250 dollars",
                (
                    criteres(("refresh_rate", "144"), budget="250"),
                    trouves_avec(ECRAN),
                    Texte("Voici trois écrans."),
                ),
                1,
                messages_a_la_fin=0,
            ),
        ),
        messages=(),
    )
    assert Attente.BUDGET_DEMANDE_EN_LIVRANT in metriques.mesurer(jouee).faits


def test_un_repli_ne_demande_jamais_le_budget():
    """Le message d'un `Repli` est écrit en Python : un tour qui livre sans budget et se
    replie ne peut pas tenir l'attente, et c'est le bon verdict — le client a vu des
    produits et n'a pas été interrogé."""
    jouee = PriseJouee(
        scenario="budget_absent",
        prise=1,
        tours=(
            TourJoue(
                "un écran pour jouer",
                (
                    criteres(("refresh_rate", "144")),
                    trouves_avec(ECRAN),
                    Repli("Je vérifie et je reviens.", 2, (), MotifDeRepli.VALIDATION),
                ),
                1,
                messages_a_la_fin=0,
            ),
        ),
        messages=(),
    )
    assert Attente.BUDGET_DEMANDE_EN_LIVRANT not in metriques.mesurer(jouee).faits
