"""Identifiant, clé canonique, déduplication — arbitrages C et D de l'étape 5.

Ce fichier garde deux choses : que l'identifiant est **stable** (sinon le seed
committé se réécrit à chaque exécution et son diff devient illisible), et que la
déduplication absorbe les redondances sans écraser les variantes réelles.
"""

from decimal import Decimal

import pytest

from raiyon.catalogue.identite import (
    CollisionIdentifiant,
    LigneNormalisee,
    calculer_id,
    cle_canonique,
    dedupliquer,
)
from raiyon.catalogue.normalisation import ajouter_grandeurs_derivees_du_prix

SPECS_CPU = {
    "core_count": 6,
    "core_clock": Decimal("2.5"),
    "tdp": 65,
    "microarchitecture": "Alder Lake",
    "boost_clock": Decimal("4.4"),
    "graphics": None,
}


def ligne(categorie, nom, specs, prix, price_per_gb_source=None):
    """Construit une `LigneNormalisee` comme le fait le pipeline : clé puis identifiant."""
    cle = cle_canonique(nom, specs)
    return LigneNormalisee(
        id=calculer_id(categorie, cle),
        cle=cle,
        categorie=categorie,
        nom=nom,
        marque=nom.split()[0],
        prix_usd=Decimal(prix),
        specs=specs,
        price_per_gb_source=price_per_gb_source,
    )


# --------------------------------------------------------------------------- #
# Stabilité de l'identifiant
# --------------------------------------------------------------------------- #


def test_lidentifiant_est_stable_entre_deux_calculs():
    """Rejouer le pipeline doit redonner le même `id`, au caractère près."""
    premier = calculer_id("cpu", cle_canonique("Intel Core i5-12400", SPECS_CPU))
    second = calculer_id("cpu", cle_canonique("Intel Core i5-12400", dict(SPECS_CPU)))
    assert premier == second


def test_lordre_dinsertion_des_specs_ne_change_pas_lidentifiant():
    """`sort_keys` : l'ordre d'un dictionnaire Python ne doit pas décider de l'`id`."""
    a_lendroit = cle_canonique("X", {"a": 1, "b": 2})
    a_lenvers = cle_canonique("X", {"b": 2, "a": 1})
    assert a_lendroit == a_lenvers


def test_les_decimaux_partent_en_chaines_pas_en_flottants():
    """`json.dumps(0.1)` dépend de la représentation binaire : l'`id` ne le doit pas."""
    assert '"core_clock":"2.5"' in cle_canonique("X", {"core_clock": Decimal("2.5")})


def test_lidentifiant_porte_le_prefixe_de_sa_categorie():
    identifiant = calculer_id("internal-hard-drive", "peu importe")
    assert identifiant.startswith("internal-hard-drive-")
    assert len(identifiant.rsplit("-", 1)[1]) == 10


# --------------------------------------------------------------------------- #
# Déduplication — une règle unique, deux effets
# --------------------------------------------------------------------------- #


def test_deux_cpu_identiques_a_prix_differents_fusionnent_au_prix_le_plus_bas():
    """Le cas des 51 redondances de `cpu` : même nom, mêmes attributs, prix différents."""
    cher = ligne("cpu", "Intel Core i5-12400", SPECS_CPU, "199.99")
    pas_cher = ligne("cpu", "Intel Core i5-12400", SPECS_CPU, "149.99")
    assert cher.id == pas_cher.id

    retenues, stats = dedupliquer([cher, pas_cher])
    assert len(retenues) == 1
    assert retenues[0].prix_usd == Decimal("149.99")
    assert stats["cpu"].groupes == 1
    assert stats["cpu"].lignes_absorbees == 1
    assert stats["cpu"].ecart_prix_max == Decimal("50.00")


def test_deux_memory_ne_differant_que_par_la_couleur_restent_deux_produits():
    """Le cas des 346 variantes de `memory` : la couleur entre dans la clé."""
    base = {
        "ddr_generation": 5,
        "frequence_mhz": 6000,
        "nb_modules": 2,
        "taille_module_gb": 16,
        "capacite_totale_gb": 32,
        "cas_latency": 30,
        "first_word_latency": Decimal("10"),
    }
    noire = ligne("memory", "Corsair Vengeance", {**base, "color": "Black"}, "99.99")
    blanche = ligne("memory", "Corsair Vengeance", {**base, "color": "White"}, "104.99")

    retenues, stats = dedupliquer([noire, blanche])
    assert len(retenues) == 2
    assert stats["memory"].lignes_absorbees == 0


def test_la_regle_de_deduplication_est_la_meme_pour_les_deux_categories():
    """Aucun traitement par catégorie : c'est le même code, seul son effet diffère."""
    lignes = [
        ligne("cpu", "Intel Core i5-12400", SPECS_CPU, "199.99"),
        ligne("cpu", "Intel Core i5-12400", SPECS_CPU, "149.99"),
        ligne("memory", "Corsair X", {"color": "Black"}, "99.99"),
        ligne("memory", "Corsair X", {"color": "White"}, "99.99"),
    ]
    retenues, _ = dedupliquer(lignes)
    assert sorted(ligne.categorie for ligne in retenues) == ["cpu", "memory", "memory"]


def test_une_collision_didentifiant_arrete_tout():
    """Deux clés distinctes sous le même `id` fusionneraient deux produits en silence."""
    a = ligne("cpu", "Produit A", {"x": 1}, "10")
    b = LigneNormalisee(
        id=a.id,  # collision fabriquée : deux clés différentes, même identifiant
        cle=cle_canonique("Produit B", {"x": 2}),
        categorie="cpu",
        nom="Produit B",
        marque="Produit",
        prix_usd=Decimal("20"),
        specs={"x": 2},
    )
    with pytest.raises(CollisionIdentifiant):
        dedupliquer([a, b])


# --------------------------------------------------------------------------- #
# Arbitrage D — le piège central de l'étape
# --------------------------------------------------------------------------- #


def test_price_per_gb_est_recalcule_sur_le_prix_retenu_pas_herite_du_doublon():
    """**Le test qui garde l'arbitrage D.**

    Deux annonces du même disque : 149,99 USD avec `price_per_gb = 0.075` à la source,
    et 99,99 USD avec `price_per_gb = 0.050`. La déduplication garde le prix le plus
    bas. Si `price_per_gb` était recopié de la ligne écartée, le catalogue afficherait
    un prix de 99,99 USD à côté d'un ratio calculé sur 149,99 — deux champs disant des
    choses différentes du même fait, ce que §3.10 cherche à rendre impossible ailleurs.
    """
    specs = {"capacity": 2000, "form_factor": "M.2-2280", "interface": "M.2 PCIe 4.0 X4"}
    chere = ligne("internal-hard-drive", "Samsung 990 Pro", specs, "149.99", Decimal("0.075"))
    pas_chere = ligne("internal-hard-drive", "Samsung 990 Pro", specs, "99.99", Decimal("0.050"))

    retenues, _ = dedupliquer([chere, pas_chere])
    assert len(retenues) == 1
    retenue = retenues[0]
    assert retenue.prix_usd == Decimal("99.99")

    enrichies = ajouter_grandeurs_derivees_du_prix(
        retenue.categorie, retenue.specs, retenue.prix_usd
    )
    assert enrichies["price_per_gb"] == Decimal("0.050")
    assert enrichies["price_per_gb"] != Decimal("0.075")


def test_le_prix_nentre_pas_dans_la_cle_canonique():
    """Sinon la déduplication ne fusionnerait jamais deux annonces à prix différents."""
    specs = {"capacity": 2000}
    assert cle_canonique("Samsung 990 Pro", specs) == cle_canonique("Samsung 990 Pro", specs)
    assert "149.99" not in cle_canonique("Samsung 990 Pro", specs)
