"""Le niveau 3 de §3.11 : le code rédige, et **son texte passe son propre validateur**.

C'est le test central du fichier. Un repli qui ne passerait pas le contrôle qu'il existe
pour remplacer serait un aveu : le niveau 3 doit être le plus sûr des trois, pas
seulement le plus sec. Il attrape aussi la classe de fautes la plus discrète du module —
un prix posé dans une phrase qui ne nomme pas son produit, une ligne coupée par un point
décimal, un écart oublié.
"""

from decimal import Decimal

import pytest
from contexte_de_test import (
    LG,
    SAMSUNG,
    SONDES,
    contexte_apres_sondage,
    contexte_complet,
    etat_du_scenario,
    resultat_de_recherche,
)

from outils_de_test import TOLERANCE, DepotEnMemoire
from raiyon.matching.moteur import ResultatMatching
from raiyon.tools.outils import sonder_catalogue
from raiyon.validateur.repli import (
    LIMITE_DE_CHAMPS,
    PHRASE_DE_DOMAINE,
    PHRASE_GENERIQUE,
    EtatDuCatalogue,
    rediger,
)
from raiyon.validateur.validateur import OrigineRejet, valider


def catalogue_du_scenario() -> EtatDuCatalogue:
    """Ce que la boucle construit à partir du sondage réel du décor.

    Le même geste que `boucle._catalogue_de()` : on **réduit** le `ResultatSondage`, on ne
    le passe pas tel quel — il porte un `EtatSession`, qui n'a rien à faire dans le
    rédacteur d'une réponse au client.
    """
    depot = DepotEnMemoire()
    depot.produits = list(SONDES)
    sondage = sonder_catalogue(etat_du_scenario(), depot, tolerance=TOLERANCE)
    return EtatDuCatalogue(
        categorie=sondage.categorie,
        candidats=sondage.dans_le_budget,
        champs=sondage.champs,
    )


@pytest.fixture
def resultat():
    return resultat_de_recherche()


def test_le_texte_du_repli_passe_le_validateur(resultat):
    """**Le test qui compte.** Le gabarit est relu par les cinq règles, sans indulgence."""
    verdict = valider(rediger(resultat), contexte_complet())

    assert verdict.valide, f"le repli lève : {[grief.en_ligne() for grief in verdict.griefs]}"


def test_le_repli_cite_les_noms_verbatim_les_ids_et_les_prix(resultat):
    texte = rediger(resultat)

    assert SAMSUNG.nom in texte
    assert SAMSUNG.id in texte
    assert "249.99 $" in texte


def test_le_repli_presente_le_hors_budget_avec_son_ecart_exact(resultat):
    """Critère nº2 : le produit de la zone de tolérance ne se glisse pas dans la liste."""
    texte = rediger(resultat)

    assert LG.nom in texte
    assert "17.14 $ de plus" in texte


def test_le_pourquoi_vient_de_la_trace_et_jamais_du_prix(resultat):
    """Le « pourquoi » est construit depuis les `LigneTrace` satisfaites (§3.11 niveau 3).

    `prix_usd` en est écarté : la ligne du « pourquoi » ne nomme aucun produit, et un
    montant y serait un montant non attribuable — le repli produirait lui-même un grief.
    """
    texte = rediger(resultat)

    assert "retenu pour" in texte
    assert "fréquence de rafraîchissement 144 Hz" in texte
    for ligne in texte.splitlines():
        if ligne.strip().startswith("retenu pour"):
            assert "$" not in ligne


def test_une_question_rejetee_reste_la_phrase_generique():
    """Inchangé : on ne répond pas par un classement à quelqu'un qu'on interrogeait.

    C'est le **seul** cas qui rend encore la phrase générique depuis le correctif de
    l'étape 12 — et il le rend même quand une recherche a eu lieu dans le tour.
    """
    assert rediger(None, OrigineRejet.QUESTION) == PHRASE_GENERIQUE
    assert rediger(resultat_de_recherche(), OrigineRejet.QUESTION) == PHRASE_GENERIQUE


def test_sans_recherche_le_repli_est_desormais_la_phrase_de_domaine():
    """~~« Si aucune recherche n'a eu lieu, le repli est la phrase d'excuse générique. »~~

    **Renversé au correctif de l'étape 12**, et par une conversation réelle : ce cas-là
    est presque toujours une **question de domaine** (« c'est quoi la différence entre IPS
    et VA ? »), et lui répondre « pouvez-vous me redire ce que vous cherchez ? » demande au
    client de répéter une question qu'il a posée clairement.
    """
    texte = rediger(None)

    assert texte != PHRASE_GENERIQUE
    assert texte == PHRASE_DE_DOMAINE
    assert "je ne vais pas vous inventer" in texte


def test_les_deux_phrases_de_validation_ne_partagent_plus_de_condition():
    """Elles se choisissent sur deux faits différents, pas sur un seul avec un « ou ».

    C'est ce qui a permis au défaut de vivre : `origine is QUESTION or resultat is None`
    faisait tomber les deux cas dans la même branche, et personne ne pouvait voir qu'ils
    appelaient deux réponses.
    """
    assert rediger(None, OrigineRejet.QUESTION) != rediger(None, OrigineRejet.TEXTE)


def test_la_phrase_de_domaine_bascule_sur_ce_que_le_catalogue_contient():
    """La seconde moitié : **dire ce qu'on a**, plutôt que renvoyer la question.

    Les distributions viennent du sondage réel du décor — celles que `probe_catalog` a
    rendues —, jamais d'une déduction sur le champ dont le client parlait. Le déduire de la
    prose serait un second validateur, plus faible que le premier (étape 12, arbitrage E).
    """
    texte = rediger(None, OrigineRejet.TEXTE, catalogue_du_scenario())

    assert texte.startswith(PHRASE_DE_DOMAINE)
    assert "voici ce que le catalogue contient" in texte
    assert "écran" in texte
    # Une ligne par champ : le découpage en phrases du validateur coupe sur le saut de
    # ligne, donc chaque valeur unitaire est lue dans une phrase qui ne nomme aucun produit.
    lignes = [ligne for ligne in texte.splitlines() if ligne.startswith("- ")]
    assert lignes, f"aucune ligne de distribution dans :\n{texte}"
    assert len(lignes) <= LIMITE_DE_CHAMPS


def test_la_phrase_de_domaine_sans_sondage_dit_ce_quelle_ne_fera_pas_et_sarrete():
    """Moins bien, et honnête : sans sondage dans le tour, il n'y a rien à basculer."""
    assert rediger(None, OrigineRejet.TEXTE, None) == PHRASE_DE_DOMAINE


def test_la_phrase_de_domaine_passe_les_cinq_regles_du_validateur():
    """⚠️ **Le test qui empêche le comble.**

    Une phrase de repli qui inventerait un chiffre serait exactement la faute que le repli
    existe pour éviter. Elle est donc relue par `valider()`, contre un contexte fourni
    **non vide** — celui de la conversation entière, produits compris, ce qui est le cas
    le plus exigeant : la règle 5 y refuse une valeur de distribution dans une phrase qui
    nomme un produit, et la règle 2 y refuse une borne de sondage collée à un modèle.
    """
    texte = rediger(None, OrigineRejet.TEXTE, catalogue_du_scenario())

    verdict = valider(texte, contexte_complet())
    assert verdict.valide, f"le repli de domaine lève ses propres griefs : {verdict.griefs}"


def test_la_phrase_de_domaine_passe_aussi_contre_le_contexte_du_seul_sondage():
    """Le cas réel : un repli de domaine survient souvent **avant** toute recherche.

    Le contexte ne porte alors aucun produit, donc aucune `valeurs_de_specs` — les valeurs
    citées doivent venir de `valeurs_de_distribution` seules.
    """
    texte = rediger(None, OrigineRejet.TEXTE, catalogue_du_scenario())

    verdict = valider(texte, contexte_apres_sondage())
    assert verdict.valide, f"griefs contre le contexte du sondage seul : {verdict.griefs}"


def test_la_phrase_generique_passe_aussi_le_validateur():
    """Elle ne porte aucun chiffre — et c'est vérifié, pas supposé."""
    assert valider(PHRASE_GENERIQUE, contexte_complet()).valide


def test_un_zero_resultat_est_dit_avec_le_diagnostic_du_moteur():
    """Critère nº6 : dire pourquoi, proposer l'assouplissement, laisser le client trancher.

    Le repli reste un mode dégradé : il **formule** la proposition que le moteur a
    calculée, il ne l'applique pas.
    """
    vide = ResultatMatching(categorie="monitor", produits=(), traces=())

    texte = rediger(vide)

    assert "Aucun produit" in texte
    assert valider(texte, contexte_complet()).valide


def test_le_repli_formate_les_montants_lui_meme(resultat):
    """« Les prix sont des `Decimal` typés que **le code** formate » (§2).

    Deux décimales, toujours : un `str(Decimal)` laisserait passer `249.9` là où la base
    porte `249.90`, et le client comparerait deux écritures d'un même prix.
    """
    assert f"{Decimal('249.99'):.2f} $" in rediger(resultat)
