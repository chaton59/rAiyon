"""Le niveau 3 de §3.11 : le code rédige, et **son texte passe son propre validateur**.

C'est le test central du fichier. Un repli qui ne passerait pas le contrôle qu'il existe
pour remplacer serait un aveu : le niveau 3 doit être le plus sûr des trois, pas
seulement le plus sec. Il attrape aussi la classe de fautes la plus discrète du module —
un prix posé dans une phrase qui ne nomme pas son produit, une ligne coupée par un point
décimal, un écart oublié.
"""

from decimal import Decimal

import pytest
from contexte_de_test import LG, SAMSUNG, contexte_complet, resultat_de_recherche

from raiyon.matching.moteur import ResultatMatching
from raiyon.validateur.repli import PHRASE_SANS_RECHERCHE, rediger
from raiyon.validateur.validateur import valider


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


def test_sans_recherche_le_repli_est_la_phrase_generique():
    """« Si aucune recherche n'a eu lieu, le repli est la phrase d'excuse générique. »"""
    assert rediger(None) == PHRASE_SANS_RECHERCHE


def test_la_phrase_generique_passe_aussi_le_validateur():
    """Elle ne porte aucun chiffre — et c'est vérifié, pas supposé."""
    assert valider(PHRASE_SANS_RECHERCHE, contexte_complet()).valide


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
