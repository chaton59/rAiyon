"""La moitié SQL du moteur, sur le catalogue réel. Marqueur `integration`.

Ces tests sont ceux que la part pure ne peut pas écrire : ils vérifient que les
prédicats traduisent bien ce que le registre annonce, sur les 1 026 produits du seed
committé. Les identifiants cités sont **ceux du rapport de seed** (§ « Cas limites
pour l'étape 6 ») : s'ils changent un jour, un test casse, et c'est le comportement
voulu.

Aucun appel LLM, aucune clé API. La base est migrée et seedée **une seule fois** pour
toute la session (`moteur_catalogue`).
"""

from decimal import Decimal

import pytest
from sqlalchemy import event

from raiyon.matching.criteres import Critere, Importance, Operateur, RequeteMatching
from raiyon.matching.depot import Fourchette
from raiyon.matching.moteur import rechercher
from raiyon.matching.relachement import Motif
from raiyon.matching.score import classer, evaluer_lot

pytestmark = pytest.mark.integration

TOUT = Fourchette()
TOLERANCE = Decimal("0.15")


def critere(champ, operateur, valeur, importance=Importance.BLOQUANT):
    return Critere(champ=champ, operateur=operateur, valeur=valeur, importance=importance)


def requete(categorie, *criteres, **kwargs):
    return RequeteMatching(categorie=categorie, criteres=criteres, **kwargs)


# --------------------------------------------------------------------------- #
# Les filtres durs
# --------------------------------------------------------------------------- #


def test_filtre_numerique(depot):
    """`(specs->>'capacity')::numeric >= 2000` — balayage séquentiel assumé (§3.3bis)."""
    demande = requete("internal-hard-drive", critere("capacity", Operateur.AU_MOINS, 2000))
    assert len(depot.candidats(demande, TOUT)) == 74


def test_filtre_categoriel(depot):
    """Égalité stricte par containment `@>`, servie par le GIN."""
    demande = requete("internal-hard-drive", critere("interface", Operateur.EGAL, "SATA 6.0 Gb/s"))
    assert len(depot.candidats(demande, TOUT)) == 85


def test_filtre_booleen(depot):
    demande = requete("headphones", critere("wireless", Operateur.EGAL, True))
    assert len(depot.candidats(demande, TOUT)) == 59


def test_filtres_multiples_se_cumulent(depot):
    demande = requete(
        "headphones",
        critere("wireless", Operateur.EGAL, True),
        critere("microphone", Operateur.EGAL, True),
        critere("type", Operateur.EGAL, "Circumaural"),
    )
    assert len(depot.candidats(demande, TOUT)) == 52


def test_la_categorie_et_la_disponibilite_sont_toujours_appliquees(depot):
    """Un tour, une catégorie ; et `disponible = true` sans qu'on ait à le demander."""
    produits = depot.candidats(requete("cpu"), TOUT)
    assert len(produits) == 171
    assert {produit.categorie for produit in produits} == {"cpu"}
    assert all(produit.disponible for produit in produits)


def test_un_critere_score_nexclut_rien(depot):
    """Le rôle `score` pondère, il ne filtre pas — par définition."""
    avec = requete(
        "cpu", critere("boost_clock", Operateur.AU_MOINS, Decimal("6"), Importance.IMPORTANT)
    )
    assert len(depot.candidats(avec, TOUT)) == 171


# --------------------------------------------------------------------------- #
# NULL sur un filtre dur : exclure **et** compter
# --------------------------------------------------------------------------- #


def test_un_null_sur_un_filtre_dur_exclut_et_se_compte(depot):
    """58 écrans à 144 Hz ou plus, et 7 qui ne déclarent pas leur fréquence.

    L'absence ne satisfait pas le critère — c'est la sémantique SQL, elle est
    conservée — mais elle cesse d'être silencieuse.
    """
    demande = requete("monitor", critere("refresh_rate", Operateur.AU_MOINS, 144))
    assert len(depot.candidats(demande, TOUT)) == 58
    assert depot.ecartes_faute_de_donnee(demande, TOUT) == {"refresh_rate": 7}


def test_aucune_requete_de_comptage_sur_un_attribut_complet(depot, moteur_catalogue):
    """À 100 % de remplissage, le comptage n'a rien à dire et n'est pas émis.

    Le registre le sait par mesure — les taux viennent du rapport de seed — donc le
    surcoût est nul sur la quasi-totalité des critères.
    """
    executees: list[str] = []

    @event.listens_for(moteur_catalogue, "before_cursor_execute")
    def enregistrer(conn, cursor, statement, parameters, context, executemany):
        executees.append(statement)

    try:
        demande = requete("internal-hard-drive", critere("form_factor", Operateur.EGAL, "M.2-2280"))
        assert depot.ecartes_faute_de_donnee(demande, TOUT) == {}
    finally:
        event.remove(moteur_catalogue, "before_cursor_execute", enregistrer)

    assert executees == []


def test_le_comptage_des_absents_partage_le_chemin_du_filtre(depot):
    """Les deux ensembles sont disjoints et couvrent le sous-catalogue restant.

    C'est la garantie qu'apporte le constructeur de prédicat unique : filtrés,
    écartés faute de donnée et non retenus se comptent sur la même base.
    """
    demande = requete("video-card", critere("length", Operateur.AU_PLUS, 300))
    retenus = len(depot.candidats(demande, TOUT))
    absents = depot.ecartes_faute_de_donnee(demande, TOUT)["length"]
    assert retenus == 105
    assert absents == 6
    assert retenus + absents <= 171


def test_une_absence_structurelle_ne_se_compte_pas_comme_donnee_manquante(depot):
    """« 7 200 tr/min en M.2 PCIe » : zéro produit, et la bonne raison.

    Les disques M.2 PCIe sont des SSD, et un SSD n'a pas de vitesse de rotation. Avant
    ce correctif, les 40 disques rouverts par le retrait de `rpm` égalaient le compteur
    d'exclusions faute de donnée, et le diagnostic concluait `donnee_absente` — l'étape 8
    aurait dit « ces disques ne déclarent pas leur vitesse ». C'est faux : ils n'en ont
    pas.
    """
    demande = requete(
        "internal-hard-drive",
        critere("rpm", Operateur.AU_MOINS, 7200),
        critere("interface", Operateur.EGAL, "M.2 PCIe 4.0 X4"),
    )
    resultat = rechercher(depot, demande, tolerance=TOLERANCE)

    assert resultat.produits == ()
    assert "rpm" not in resultat.ecartes_faute_de_donnee
    assert resultat.diagnostic is not None
    assert resultat.diagnostic.motif is Motif.ABSENCE_STRUCTURELLE

    propositions = {p.champ: p for p in resultat.diagnostic.propositions}
    assert propositions["rpm"].produits_rouverts == 40
    assert propositions["interface"].produits_rouverts == 32
    # Ce qui déclenche le motif n'est pas le drapeau du registre mais **l'absence de
    # valeur atteignable** : aucun des 40 disques M.2 PCIe rouverts ne déclare de
    # vitesse de rotation, parce qu'aucun n'en a.
    assert propositions["rpm"].valeur_atteignable is None


def test_une_valeur_atteignable_ramene_le_motif_au_critere_trop_strict(depot):
    """Le pendant du test précédent, et c'est le couple qui prouve la règle.

    Même attribut, même drapeau de registre, motif différent — parce qu'ici deux disques
    mécaniques **existent dans le budget**, à 5 400 tr/min. Dire « vous avez demandé un
    disque mécanique » serait faux : il y en a. La phrase juste est « il y en a, mais
    aucun à 7 200 tr/min », et c'est `valeur_atteignable` qui la rend possible.
    """
    demande = requete(
        "internal-hard-drive",
        critere("rpm", Operateur.AU_MOINS, 7200),
        budget_usd=Decimal("25"),
    )
    resultat = rechercher(depot, demande, tolerance=TOLERANCE)

    assert resultat.produits == ()
    assert resultat.diagnostic is not None
    assert resultat.diagnostic.motif is Motif.CRITERE_TROP_STRICT
    assert "rpm" not in resultat.ecartes_faute_de_donnee

    (proposition,) = resultat.diagnostic.propositions
    assert proposition.champ == "rpm"
    assert proposition.valeur_atteignable == Decimal("5400")

    # Les deux disques que le seed met dans ce budget, et qui rendent la phrase fausse.
    dans_le_budget = {
        produit.id
        for produit in depot.candidats(requete("internal-hard-drive"), TOUT)
        if produit.prix_usd <= Decimal("25") and produit.specs.rpm == 5400
    }
    assert dans_le_budget == {
        "internal-hard-drive-696751738a",
        "internal-hard-drive-aa72d12add",
    }


def test_le_filtre_sur_rpm_ecarte_toujours_les_ssd(depot):
    """Le drapeau change le **diagnostic**, pas le filtre.

    Un client qui demande 7 200 tr/min ne veut pas de SSD, et il n'en reçoit pas : la
    sémantique SQL — l'absence ne satisfait pas le critère — est inchangée.
    """
    demande = requete("internal-hard-drive", critere("rpm", Operateur.AU_MOINS, 7200))
    produits = depot.candidats(demande, TOUT)
    assert len(produits) == 32
    assert all(produit.specs.type == "HDD" for produit in produits)


# --------------------------------------------------------------------------- #
# La marque : normalisation écrite une seule fois, en SQL
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("saisie", ["G.Skill", "g.skill", "gskill", "G Skill", "GSKILL"])
def test_les_variantes_de_marque_rendent_le_meme_ensemble(depot, saisie):
    """« G.Skill » et « gskill » sont la même marque, et le client la tape à la main."""
    demande = requete("memory", critere("marque", Operateur.EGAL, saisie))
    assert len(depot.candidats(demande, TOUT)) == 31


# --------------------------------------------------------------------------- #
# G1 — budget frôlé, sur les six catégories
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("categorie", "budget", "identifiant", "prix"),
    [
        ("cpu", "100", "cpu-bfbc23021a", "108.99"),
        ("monitor", "300", "monitor-857dd58120", "308.00"),
        ("internal-hard-drive", "100", "internal-hard-drive-c2dd3e2507", "103.92"),
        ("memory", "100", "memory-fd8360b7eb", "101.99"),
        ("video-card", "500", "video-card-be85208269", "529.00"),
        ("headphones", "100", "headphones-2a0bb59183", "104.36"),
    ],
)
def test_g1_le_produit_frole_le_budget_sans_jamais_entrer_dedans(
    depot, categorie, budget, identifiant, prix
):
    """§3.10 : les deux ensembles sont séparés, et l'écart est exact.

    Le produit est dans la zone de tolérance, donc jamais dans `produits` — quelle que
    soit la sortie du modèle, il ne peut pas être présenté comme tenant dans le budget.
    """
    plafond = Decimal(budget)
    resultat = rechercher(depot, requete(categorie, budget_usd=plafond), tolerance=TOLERANCE)

    assert identifiant not in {produit.id for produit in resultat.produits}
    assert all(produit.prix_usd <= plafond for produit in resultat.produits)

    hors_budget = {hors.produit.id: hors for hors in resultat.au_dessus_du_budget}
    assert identifiant in hors_budget
    assert hors_budget[identifiant].ecart_usd == Decimal(prix) - plafond


# --------------------------------------------------------------------------- #
# G2 — départage : ce qui ne filtre ni ne score ne peut pas trancher
# --------------------------------------------------------------------------- #


def test_g2_deux_casques_identiques_se_departagent_sur_le_prix(depot):
    """`color` est un champ d'affichage : il ne peut pas départager.

    ⚠️ Ce que la mesure ajoute au rapport de seed : ces deux casques ont **aussi** des
    marques différentes (Pyle Audio et Logitech). « Specs identiques » vaut pour le
    JSONB, pas pour la ligne entière — et `marque` est un filtre dur. Sans critère de
    marque, le départage se fait bien sur le prix ; avec, ce n'est plus un départage,
    c'est un filtre.
    """
    demande = requete(
        "headphones",
        critere("type", Operateur.EGAL, "Supra-aural"),
        critere("enclosure_type", Operateur.EGAL, "Closed"),
        critere("microphone", Operateur.EGAL, True),
        critere("wireless", Operateur.EGAL, False),
    )
    classement = classer(evaluer_lot(depot.candidats(demande, TOUT), demande))
    par_id = {evaluation.produit.id: evaluation for evaluation in classement}
    ordre = [evaluation.produit.id for evaluation in classement]

    moins_cher = "headphones-06acf63b59"
    plus_cher = "headphones-393cd46c64"

    assert par_id[moins_cher].score == par_id[plus_cher].score == 0
    assert par_id[moins_cher].produit.prix_usd == Decimal("23.47")
    assert par_id[plus_cher].produit.prix_usd == Decimal("41.99")
    assert ordre.index(moins_cher) < ordre.index(plus_cher)
    assert par_id[moins_cher].produit.marque != par_id[plus_cher].produit.marque


# --------------------------------------------------------------------------- #
# G3 — zéro résultat
# --------------------------------------------------------------------------- #


def test_g3_deux_criteres_plausibles_qui_ne_se_rencontrent_jamais(depot):
    """M.2-2280 sert 52 produits, SATA 6.0 Gb/s en sert 85, leur intersection zéro.

    La combinaison ne se place pas, elle **se constate** : c'est le scénario du critère
    d'acceptation nº6.
    """
    demande = requete(
        "internal-hard-drive",
        critere("form_factor", Operateur.EGAL, "M.2-2280"),
        critere("interface", Operateur.EGAL, "SATA 6.0 Gb/s"),
    )
    resultat = rechercher(depot, demande, tolerance=TOLERANCE)

    assert resultat.produits == ()
    assert resultat.diagnostic is not None
    assert resultat.diagnostic.motif is Motif.CRITERE_TROP_STRICT

    propositions = resultat.diagnostic.propositions
    assert [proposition.champ for proposition in propositions] == ["form_factor", "interface"]
    assert [proposition.produits_rouverts for proposition in propositions] == [85, 52]
    assert all(proposition.dernier_recours for proposition in propositions)


def test_g3_la_valeur_proposee_sur_un_numerique_existe_au_catalogue(depot):
    """« Descendez à 1 500 Go », parce que 1 500 Go existe — pas « à 2 To »."""
    demande = requete(
        "internal-hard-drive",
        critere("capacity", Operateur.AU_MOINS, 2000),
        critere("interface", Operateur.EGAL, "mSATA"),
    )
    resultat = rechercher(depot, demande, tolerance=TOLERANCE)

    assert resultat.produits == ()
    propositions = {p.champ: p for p in resultat.diagnostic.propositions}
    assert propositions["capacity"].valeur_atteignable is not None
    assert propositions["capacity"].valeur_atteignable < Decimal("2000")
    # La proposition sort du catalogue : un produit porte exactement cette capacité.
    atteignable = propositions["capacity"].valeur_atteignable
    voisins = depot.candidats(requete("internal-hard-drive"), TOUT)
    assert any(produit.specs.capacity == atteignable for produit in voisins)


def test_un_budget_bloquant_ne_se_propose_pas_au_relachement(depot):
    """La réponse est la zone de tolérance, pas « relâchez votre budget » (§3.10)."""
    demande = requete(
        "video-card",
        critere("chipset", Operateur.EGAL, "GeForce RTX 4090"),
        budget_usd=Decimal("100"),
    )
    resultat = rechercher(depot, demande, tolerance=Decimal("30"))

    assert resultat.produits == ()
    assert resultat.au_dessus_du_budget
    assert resultat.diagnostic.motif is Motif.BUDGET_TROP_BAS
    assert all(proposition.champ != "prix_usd" for proposition in resultat.diagnostic.propositions)


# --------------------------------------------------------------------------- #
# G4 — haut de gamme
# --------------------------------------------------------------------------- #


def test_g4_un_budget_tres_large_fait_remonter_le_haut_de_gamme(depot):
    """L'écran à 9 333 USD est au catalogue, et il n'est atteignable qu'au budget large.

    Sans la garantie de repêchage de l'étape 5, la stratification par décile aurait pu
    l'écarter — et le catalogue n'offrirait aucun cas « budget très large ».
    """
    demande = requete("monitor", critere("screen_size", Operateur.AU_MOINS, 55))
    haut_de_gamme = "monitor-0783259c60"

    etroit = rechercher(
        depot,
        demande.model_copy(update={"budget_usd": Decimal("2000")}),
        tolerance=TOLERANCE,
    )
    assert haut_de_gamme not in {produit.id for produit in etroit.produits}

    large = rechercher(
        depot,
        demande.model_copy(update={"budget_usd": Decimal("10000")}),
        tolerance=TOLERANCE,
    )
    identifiants = {produit.id for produit in large.produits}
    assert haut_de_gamme in identifiants
    assert max(produit.prix_usd for produit in large.produits) == Decimal("9333.00")
