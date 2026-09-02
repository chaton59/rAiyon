"""Le rapport : stable octet pour octet, et il se défend contre une lecture pressée.

`docs/eval/rapport.md` est committé. Un rendu instable produirait un diff à chaque
`make eval`, et un diff permanent est un diff qu'on cesse de lire.
"""

from decimal import Decimal

from produits_de_test import fabriquer
from raiyon.agent.evenements import (
    MotifDeRepli,
    ProduitsTrouves,
    QuestionPosee,
    Repli,
    Texte,
    TexteRejete,
)
from raiyon.eval.metriques import Attente, PriseJouee, TourJoue, agreger, mesurer
from raiyon.eval.rapport import AVERTISSEMENT, rendre
from raiyon.matching.criteres import Importance, Operateur
from raiyon.matching.moteur import ResultatMatching
from raiyon.matching.relachement import Diagnostic, Motif, Proposition
from raiyon.validateur.regles import CodeGrief, Grief
from raiyon.validateur.validateur import OrigineRejet

ECRAN = fabriquer("monitor", 1, prix="142.99")


def trouves(*produits, diagnostic=None):
    return ProduitsTrouves(
        ResultatMatching(
            categorie="monitor",
            produits=tuple(produits),
            traces=(),
            candidats_trouves=len(produits),
            diagnostic=diagnostic,
        )
    )


PROPOSITION = Proposition(
    champ="refresh_rate",
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


def prise(nom, numero, *evenements, iterations=(2,), **reste):
    return PriseJouee(
        scenario=nom,
        prise=numero,
        tours=tuple(
            TourJoue("message", evenements if rang == 0 else (), nombre)
            for rang, nombre in enumerate(iterations)
        ),
        messages=(),
        **reste,
    )


def mesures_inventees():
    """Des données **fausses**, exprès. Si le tableau ne dit rien d'utile ici, il ne dira
    rien sur des vraies : c'est la méthode que l'étape s'est donnée, jalon 1."""
    return agreger(
        [
            mesurer(
                prise(
                    "budget_serre",
                    1,
                    QuestionPosee("usage ?", None),
                    trouves(ECRAN),
                    attendu=ECRAN.id,
                    iterations=(2, 1),
                )
            ),
            mesurer(prise("budget_serre", 2, trouves(ECRAN), attendu=ECRAN.id, iterations=(1, 3))),
            mesurer(
                prise(
                    "budget_serre",
                    3,
                    QuestionPosee("usage ?", None),
                    QuestionPosee("budget ?", None),
                    trouves(),
                    attendu=ECRAN.id,
                    iterations=(4, 2),
                )
            ),
            mesurer(
                prise(
                    "sur_specifie",
                    1,
                    trouves(diagnostic=Diagnostic(Motif.CRITERE_TROP_STRICT, (PROPOSITION,))),
                    attentes=frozenset({Attente.ZERO_RESULTAT}),
                    diagnostic_attendu=Motif.CRITERE_TROP_STRICT,
                )
            ),
            mesurer(
                prise(
                    "comparaison",
                    1,
                    TexteRejete(
                        "Le second est à 180 $ environ.",
                        (Grief(CodeGrief.MONTANT_NON_FOURNI, "180 $", "citer un prix fourni"),),
                        1,
                        OrigineRejet.TEXTE,
                    ),
                    Repli("Je préfère vérifier.", 2, (), MotifDeRepli.VALIDATION),
                    attentes=frozenset({Attente.PRODUITS_CITES}),
                )
            ),
        ]
    )


def test_le_rapport_est_stable_octet_pour_octet():
    """Même entrée, même sortie. Sinon `docs/eval/rapport.md` diffère à chaque exécution."""
    mesures = mesures_inventees()
    assert rendre(mesures) == rendre(mesures)
    assert rendre(mesures) == rendre(mesures_inventees())


def test_le_rapport_ne_depend_pas_de_lordre_des_prises():
    """Les prises arrivent dans l'ordre où les cassettes ont été lues sur le disque."""
    mesures = mesures_inventees()
    inverses = agreger(reversed(mesures.prises))
    assert rendre(inverses) == rendre(mesures)


def test_le_rapport_porte_la_phrase_des_trois_couches():
    """Sans elle, quelqu'un lira la première ligne et s'arrêtera là — l'auteur le premier."""
    texte = rendre(mesures_inventees())
    assert AVERTISSEMENT in texte
    assert "le critère nº1 vaut 0 et le taux de repli vaut 30 %" in texte
    assert "par\n> construction" in texte


def test_le_rapport_dit_sur_combien_de_prises_porte_le_numero_4():
    """Arbitrage F : un scénario sans attendu n'entre pas dans le calcul, et on le dit."""
    texte = rendre(mesures_inventees())
    assert "3 prise(s) à réponse de référence" in texte


def test_le_rapport_publie_les_trois_lignes_sans_seuil():
    texte = rendre(mesures_inventees())
    assert "Taux de rejet du validateur" in texte
    assert "Taux de repli" in texte
    assert "Itérations par tour" in texte
    assert "| montant_non_fourni | 1 |" in texte
    assert "| validation | 1 |" in texte


def test_un_rapport_sans_rejet_ni_repli_le_dit_plutot_que_dafficher_un_tableau_vide():
    texte = rendre(agreger([mesurer(prise("budget_serre", 1, trouves(ECRAN)))]))
    assert "Aucun texte refusé par le validateur sur cette exécution." in texte
    assert "Aucun repli sur cette exécution." in texte


def test_les_attentes_non_tenues_sont_nommees():
    texte = rendre(
        agreger(
            [
                mesurer(
                    prise(
                        "hors_catalogue",
                        1,
                        trouves(ECRAN),
                        attentes=frozenset({Attente.AUCUN_PRODUIT_CITE}),
                    )
                )
            ]
        )
    )
    assert "| hors_catalogue | 1 | attente `aucun_produit_cite` |" in texte


def test_le_rapport_nomme_les_regles_jamais_declenchees():
    """Sans cette ligne, « 0,31 grief/tour » se lit comme une couverture.

    Sur ces mesures inventées, seule `montant_non_fourni` a tiré : les cinq autres codes
    doivent être nommés, et le renvoi vers `test_pieges.py` doit figurer.
    """
    texte = rendre(mesures_inventees())
    assert "Règles du validateur jamais déclenchées" in texte
    assert "`id_inconnu`" in texte
    assert "`nom_reecrit`" in texte
    assert "`montant_non_fourni`" not in texte.split("Règles du validateur")[1].split("|")[2]
    assert "tests/validateur/test_pieges.py" in texte


def test_le_rapport_dit_quand_tous_les_codes_ont_tire():
    """Le cas vert doit se lire aussi, sinon la ligne n'a de sens que dans l'échec.

    ⚠️ **Six codes pour cinq règles** : `regle_montants` en lève deux. La ligne compte
    les codes, qui sont les gestes de correction demandés au modèle.
    """
    from raiyon.validateur.regles import CodeGrief

    mesuree = mesurer(
        prise(
            "essai",
            1,
            *[
                TexteRejete(f"phrase {code.value}", (Grief(code, "x", "y"),), 1, OrigineRejet.TEXTE)
                for code in CodeGrief
            ],
        )
    )
    assert "aucun — les six codes ont été levés au moins une fois" in rendre(agreger([mesuree]))


def test_le_critere_3_est_libelle_en_tours_client():
    """Le seuil n'a pas changé de valeur, il a changé de sens — le tableau doit le dire."""
    texte = rendre(mesures_inventees())
    assert "Délai avant première valeur — en **tours client**" in texte
    assert "tour(s) sur" in texte
    assert "Questions posées avant la première valeur" in texte


def test_le_critere_5_est_marque_hors_de_ce_rapport():
    """« Moteur testable sans API » se constate dans `make check`, pas ici. L'afficher à
    zéro laisserait croire qu'il est mesuré."""
    assert "hors de ce rapport — `make check`" in rendre(mesures_inventees())


def test_la_dispersion_ne_se_presente_jamais_comme_un_intervalle_de_confiance():
    texte = rendre(mesures_inventees())
    assert "Trois prises ne sont pas un intervalle de confiance" in texte
    assert "une cassette est un" in texte


# --------------------------------------------------------------------------- #
# Les trois appendices — étape 13, jalon 0
# --------------------------------------------------------------------------- #


def test_lappendice_des_refus_publie_la_phrase_et_pas_seulement_le_code():
    """**Le point A du jalon 0.** Sans la phrase, l'étape 13 itère sur des compteurs.

    Un taux de rejet qui descend de 11 à 5 ne dit pas *quelle forme* a disparu, et c'est la
    seule chose qu'on veuille savoir d'un changement de prompt. Attribuer les onze griefs de
    l'étape 12 à trois opérations a demandé de rouvrir dix-neuf cassettes à la main ; le
    harnais avait l'information et ne la portait pas jusqu'au rapport.
    """
    texte = rendre(
        agreger(
            [
                mesurer(
                    prise(
                        "changement_davis",
                        1,
                        TexteRejete(
                            "Le MSI est en QHD pour 47 $ de plus. Il vous conviendrait ?",
                            (Grief(CodeGrief.MONTANT_NON_FOURNI, "47 $", "reprendre `prix_usd`"),),
                            1,
                            OrigineRejet.TEXTE,
                        ),
                    )
                )
            ]
        )
    )

    assert "## Appendice A — les phrases refusées" in texte
    assert "Le MSI est en QHD pour 47 $ de plus" in texte, "la phrase, pas seulement l'extrait"
    assert "| changement_davis | 1 | 1 | texte | `montant_non_fourni` | 47 $ |" in texte
    assert "Aucune de ces phrases n'a atteint le client" in texte


def test_lappendice_des_refus_est_derive_de_codegrief_et_non_dune_liste():
    """**Un sixième code doit y apparaître sans qu'on touche à `rapport.py`.**

    Même raison qu'à la ligne « règles jamais déclenchées » du correctif de l'étape 12, et
    même mode d'échec évité : un appendice qui mentirait par omission sur exactement ce
    qu'il existe pour montrer.
    """
    texte = rendre(
        agreger(
            [
                mesurer(
                    prise(
                        "essai",
                        1,
                        *[
                            TexteRejete(
                                f"phrase pour {code.value}",
                                (Grief(code, f"extrait-{code.value}", "corriger"),),
                                1,
                                OrigineRejet.TEXTE,
                            )
                            for code in CodeGrief
                        ],
                    )
                )
            ]
        )
    )

    for code in CodeGrief:
        assert f"`{code.value}`" in texte, f"{code.value} manque à l'appendice"
        assert f"extrait-{code.value}" in texte


def test_une_phrase_refusee_ne_casse_pas_le_tableau_markdown():
    """Une barre verticale ouvrirait une colonne fantôme, un saut de ligne couperait la
    ligne du tableau en deux. Les deux arrivent : un modèle écrit des tableaux, et
    `_phrase_portante` se replie sur le **texte entier** quand aucune phrase ne porte
    l'extrait — c'est ce repli qui peut être multiligne.
    """
    texte = rendre(
        agreger(
            [
                mesurer(
                    prise(
                        "essai",
                        1,
                        TexteRejete(
                            "| Modèle | Prix |\n| MSI | 180 $ |",
                            (Grief(CodeGrief.MONTANT_NON_FOURNI, "introuvable tel quel", "…"),),
                            1,
                            OrigineRejet.TEXTE,
                        ),
                    )
                )
            ]
        )
    )

    ligne = next(rang for rang in texte.splitlines() if "introuvable tel quel" in rang)
    assert ligne.startswith("| ") and ligne.endswith(" |")
    assert "\\|" in ligne, "les barres du texte refusé sont échappées"
    assert ligne.count("|") - ligne.count("\\|") == 8, "sept colonnes, donc huit barres"
    assert "| MSI | 180 $ |" not in ligne, "la barre non échappée ouvrirait une colonne"


def test_lappendice_du_domaine_recopie_la_prose_entiere():
    """**La preuve, pas le compteur** (point D). La cible 2 se compare en lisant, sur un
    artefact committé que n'importe qui peut relire."""
    prose = "Je ne vous dirai que ce que le catalogue dit. VA : environ 3000:1 à 6000:1."
    mesuree = mesurer(
        PriseJouee(
            scenario="question_de_domaine",
            prise=1,
            tours=(
                TourJoue("un écran ?", (trouves(ECRAN),), 2),
                TourJoue("IPS ou VA ?", (Texte(prose),), 1),
            ),
            messages=(),
            tours_de_domaine=frozenset({2}),
        )
    )
    texte = rendre(agreger([mesuree]))

    assert "## Appendice B — les tours de domaine, verbatim" in texte
    assert f"> {prose}" in texte, "la prose est publiée entière, en bloc de citation"
    assert "**question_de_domaine.1, tour 2** — 4 chiffre(s)" in texte
    assert "**4 valeur(s) chiffrée(s)** sur 1 tour(s) de domaine." in texte


def test_lappendice_du_domaine_dit_quun_ratio_compte_pour_deux():
    """Le compteur lit des **nombres**, pas des faits, et le rapport doit le dire là où il
    le publie — sans quoi « 4 chiffres » se lit comme « 4 affirmations »."""
    texte = rendre(agreger([mesurer(prise("budget_serre", 1, trouves(ECRAN)))]))
    assert "un ratio écrit `3000:1` compte pour **deux**" in texte


def test_lappendice_du_markdown_publie_toutes_les_formes_meme_a_zero():
    """Un compteur qui disparaît quand il tombe à zéro ne se distingue pas d'un compteur
    qu'on a cessé de calculer — et c'est précisément la lecture qu'on veut faire en v3."""
    texte = rendre(
        agreger(
            [
                mesurer(
                    prise(
                        "essai",
                        1,
                        Texte("Voici `monitor-aaaaaaaaaa` :\n- un écran\n1. et un autre"),
                    )
                )
            ]
        )
    )

    assert "## Appendice C — le markdown que le front ne rend pas" in texte
    assert "| backtick | 2 |" in texte
    assert "| puce | 1 |" in texte
    assert "| liste numérotée | 1 |" in texte
    assert "| titre | 0 |" in texte, "une forme absente se publie à zéro, elle ne disparaît pas"


def test_le_gras_nest_pas_compte_parce_que_le_front_le_rend():
    """Le compter ferait descendre le compteur en demandant au modèle d'écrire moins bien."""
    from raiyon.eval.metriques import FORMES_MARKDOWN, formes_markdown

    assert "gras" not in {nom for nom, _ in FORMES_MARKDOWN}
    assert all(compte == 0 for _, compte in formes_markdown(("**très bien**",)))
