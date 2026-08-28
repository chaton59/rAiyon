"""Validation des modèles Pydantic — aucune base, inclus dans `make check`.

Ces tests gardent trois choses distinctes : le typage par catégorie (l'union
discriminée sert-elle vraiment à quelque chose ?), les deux cohérences croisées, et
un piège d'unité qu'un correctif bien intentionné détruirait.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from raiyon.catalogue.schemas import CATEGORIES, LIBELLES_CATEGORIE, ProduitEnBase

# Une charge utile minimale et valide par catégorie : uniquement les champs
# obligatoires, c'est-à-dire ceux mesurés à 100 % de remplissage à l'étape 3.
SPECS_VALIDES = {
    "cpu": {
        "core_count": 8,
        "core_clock": Decimal("3.40"),
        "tdp": 65,
        "microarchitecture": "Zen 4",
    },
    "monitor": {
        "screen_size": Decimal("27"),
        "largeur_px": 2560,
        "hauteur_px": 1440,
        "aspect_ratio": "16:9",
    },
    "internal-hard-drive": {
        "capacity": 2000,
        "form_factor": "M.2-2280",
        "interface": "M.2 PCIe 4.0 X4",
    },
    "memory": {
        "ddr_generation": 5,
        "frequence_mhz": 6000,
        "nb_modules": 2,
        "taille_module_gb": 16,
        "capacite_totale_gb": 32,
        "cas_latency": 30,
        "first_word_latency": Decimal("10.000"),
    },
    "video-card": {
        "chipset": "GeForce RTX 4070",
        "memory": Decimal("12"),
    },
    "headphones": {
        "type": "Circumaural",
        "microphone": True,
        "wireless": False,
        "enclosure_type": "Closed",
    },
}

IDENTIFIANTS = {
    "cpu": "cpu-3f9a2c7b1d",
    "monitor": "monitor-0a1b2c3d4e",
    "internal-hard-drive": "internal-hard-drive-9f8e7d6c5b",
    "memory": "memory-1122334455",
    "video-card": "video-card-abcdef0123",
    "headphones": "headphones-deadbeef01",
}


def produit(categorie, specs=None, **surcharges):
    """Fabrique un produit valide de la catégorie, éventuellement altéré."""
    donnees = {
        "id": IDENTIFIANTS[categorie],
        "nom": "Produit de test",
        "marque": "TestCorp",
        "categorie": categorie,
        "prix_usd": Decimal("199.99"),
        "specs": SPECS_VALIDES[categorie] if specs is None else specs,
    }
    donnees.update(surcharges)
    return ProduitEnBase(**donnees)


@pytest.mark.parametrize("categorie", CATEGORIES)
def test_chaque_categorie_accepte_une_charge_utile_valide(categorie):
    """Les 6 catégories retenues sont modélisées et acceptent leurs champs obligatoires."""
    p = produit(categorie)
    assert p.categorie == categorie
    assert p.specs.categorie == categorie


def test_les_six_categories_sont_celles_de_letape_3():
    """`keyboard` a été retirée (§3.4bis) : elle ne doit revenir par aucune porte."""
    assert set(CATEGORIES) == {
        "cpu",
        "monitor",
        "internal-hard-drive",
        "memory",
        "video-card",
        "headphones",
    }


def test_chaque_categorie_a_son_libelle_francais_sans_trou():
    """`LIBELLES_CATEGORIE` couvre les 6, exactement — ni manque, ni orpheline.

    C'est le seul français que le catalogue contient, et il est **dérivé de la
    catégorie**, donc déterministe (§3.4ter). Une catégorie sans libellé obligerait
    l'étape 8 à en inventer un, ce qui est exactement ce que le retrait de la passe
    LLM est censé rendre impossible.
    """
    assert set(LIBELLES_CATEGORIE) == set(CATEGORIES)
    assert all(libelle.strip() for libelle in LIBELLES_CATEGORIE.values())
    assert len(set(LIBELLES_CATEGORIE.values())) == len(CATEGORIES)


def test_les_libelles_sont_de_la_donnee_pas_du_rendu():
    """Minuscules, sans article ni ponctuation : la mise en forme est l'étape 11.

    Sans cette règle, la casse choisie ici finirait par être celle qu'un gabarit
    d'affichage suppose, et le libellé cesserait d'être réutilisable ailleurs.
    """
    for libelle in LIBELLES_CATEGORIE.values():
        assert libelle == libelle.lower()
        assert not libelle.startswith(("le ", "la ", "les ", "un ", "une ", "l'"))
        assert libelle == libelle.strip(" .")


@pytest.mark.parametrize("categorie", CATEGORIES)
def test_une_cle_inconnue_est_rejetee(categorie):
    """`extra="forbid"` : une faute de frappe du pipeline échoue au lieu de dormir en base."""
    specs = {**SPECS_VALIDES[categorie], "champ_qui_nexiste_pas": 1}
    with pytest.raises(ValidationError, match="champ_qui_nexiste_pas"):
        produit(categorie, specs)


def test_un_screen_size_sur_un_cpu_est_rejete():
    """Le test qui prouve que l'union discriminée sert à quelque chose.

    Sans discrimination par catégorie, un attribut d'écran posé sur un processeur
    serait accepté par le premier modèle de l'union qui le tolère.
    """
    specs = {**SPECS_VALIDES["cpu"], "screen_size": 27}
    with pytest.raises(ValidationError, match="screen_size"):
        produit("cpu", specs)


def test_une_valeur_hors_borne_est_rejetee():
    """Les bornes sont physiquement plausibles : 900 W de TDP n'existe pas."""
    with pytest.raises(ValidationError, match="tdp"):
        produit("cpu", {**SPECS_VALIDES["cpu"], "tdp": 100_000})


def test_un_champ_obligatoire_manquant_est_rejete():
    """`core_count` est mesuré à 100 % : son absence est une anomalie, pas un cas nominal."""
    specs = {k: v for k, v in SPECS_VALIDES["cpu"].items() if k != "core_count"}
    with pytest.raises(ValidationError, match="core_count"):
        produit("cpu", specs)


def test_un_champ_optionnel_absent_est_accepte():
    """`boost_clock` est à 65,1 % : son absence est la donnée, pas une erreur."""
    assert produit("cpu").specs.boost_clock is None


def test_un_prix_negatif_ou_nul_est_rejete():
    """Le prix est l'invariant central (§3.10) : il est strictement positif."""
    for prix in (Decimal("0"), Decimal("-1")):
        with pytest.raises(ValidationError, match="prix_usd"):
            produit("cpu", prix_usd=prix)


def test_un_identifiant_mal_forme_est_rejete():
    """L'ID suit `{categorie}-{10 hexadécimaux}` : un ID inventé se voit tout de suite."""
    for identifiant in ("cpu-3f9a2c7b", "CPU-3f9a2c7b1d", "cpu_3f9a2c7b1d", "cpu-zzzzzzzzzz"):
        with pytest.raises(ValidationError):
            produit("cpu", id=identifiant)


def test_un_identifiant_dune_autre_categorie_est_rejete():
    """La forme seule ne suffit pas : le préfixe doit être la catégorie du produit."""
    with pytest.raises(ValidationError, match="préfixe"):
        produit("cpu", id="monitor-3f9a2c7b1d")


def test_ssd_avec_rpm_est_rejete():
    """Un SSD n'a pas de tours par minute — la normalisation s'est trompée de branche."""
    specs = {**SPECS_VALIDES["internal-hard-drive"], "type": "SSD", "rpm": 7200}
    with pytest.raises(ValidationError, match="rpm"):
        produit("internal-hard-drive", specs)


def test_hdd_sans_rpm_est_rejete():
    """Un HDD sans vitesse de rotation : la valeur a été perdue en route."""
    specs = {**SPECS_VALIDES["internal-hard-drive"], "type": "HDD"}
    with pytest.raises(ValidationError, match="rpm"):
        produit("internal-hard-drive", specs)


def test_disque_sans_type_est_accepte():
    """`type` est à 99,6 %, donc optionnel : écarter les 0,4 % est une décision d'étape 5."""
    p = produit("internal-hard-drive")
    assert p.specs.type is None
    assert p.specs.rpm is None


def test_capacite_totale_incoherente_est_rejetee():
    """`capacite_totale_gb` est dérivée : si elle ne se recalcule pas, la donnée est corrompue."""
    specs = {**SPECS_VALIDES["memory"], "capacite_totale_gb": 64}
    with pytest.raises(ValidationError, match="capacite_totale_gb"):
        produit("memory", specs)


def test_casque_frequences_en_unites_differentes_acceptees():
    """⚠️ Le piège d'unité gardé par ce test — ne pas « corriger » ce cas.

    `freq_min_hz=100` avec `freq_max_khz=10` n'est pas une inversion : c'est 100 Hz -
    10 kHz, un casque de communication MSI parfaitement réel. Les 32 cas de ce type
    dans le dataset viennent tous du mélange d'unités du champ source. Ajouter un
    validateur `freq_min <= freq_max` ferait passer ce test au rouge — c'est
    exactement son rôle.
    """
    specs = {**SPECS_VALIDES["headphones"], "freq_min_hz": 100, "freq_max_khz": Decimal("10")}
    p = produit("headphones", specs)
    assert p.specs.freq_min_hz == 100
    assert p.specs.freq_max_khz == Decimal("10")


def test_la_categorie_ne_peut_pas_diverger_entre_colonne_et_specs():
    """La catégorie a une seule source de vérité, quoi que fournisse l'appelant."""
    specs = {**SPECS_VALIDES["cpu"], "categorie": "monitor"}
    with pytest.raises(ValidationError):
        produit("cpu", specs)


def test_specs_pour_base_retire_la_categorie_et_serialise_les_decimaux():
    """Le JSONB ne duplique pas la catégorie, et les `Decimal` y passent en chaînes.

    La chaîne est un choix : un flottant JSON ne rend pas `0.087` à l'identique, et
    `specs->>'…'` rend du texte de toute façon — le cast `::numeric` des filtres de
    plage fonctionne pareil.
    """
    payload = produit("cpu").specs_pour_base()
    assert "categorie" not in payload
    assert payload["core_clock"] == "3.40"
    # Les champs optionnels absents restent présents à `null` : la forme du JSONB est
    # constante par catégorie, ce dont le rapport de remplissage de l'étape 5 a besoin.
    assert payload["boost_clock"] is None
