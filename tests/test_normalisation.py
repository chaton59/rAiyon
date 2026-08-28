"""Les transformations de l'étape 5, une par une — aucune base, aucune clé API.

Chaque fonction de `normalisation.py` est pure : ces tests l'appellent directement,
sans pipeline autour. Ce qu'ils gardent, c'est l'arbitrage A — **trois issues, et
trois seulement** : la ligne se normalise, elle est écartée avec un motif, ou elle
arrête tout. Aucun test n'accepte une quatrième issue, et c'est le point.
"""

from decimal import Decimal

import pytest

from raiyon.catalogue.normalisation import (
    LigneEcartee,
    PipelineArrete,
    ajouter_grandeurs_derivees_du_prix,
    calculer_price_per_gb,
    eclater_frequency_response,
    eclater_modules_memoire,
    eclater_resolution,
    eclater_speed_memoire,
    en_decimal,
    extraire_marque,
    normaliser_form_factor,
    normaliser_prix,
    normaliser_type_disque,
    specs_memoire,
)

# --------------------------------------------------------------------------- #
# `internal-hard-drive.type`
# --------------------------------------------------------------------------- #


def test_type_ssd_donne_ssd_sans_rpm():
    assert normaliser_type_disque("SSD") == ("SSD", None)


def test_type_entier_donne_hdd_avec_rpm():
    assert normaliser_type_disque(7200) == ("HDD", 7200)


def test_type_absent_ecarte_la_ligne_avec_son_motif():
    """0,4 % des disques, soit 8 produits. Écartés, jamais comblés (§3.4quater)."""
    with pytest.raises(LigneEcartee) as echec:
        normaliser_type_disque(None)
    assert echec.value.motif == "type de disque absent"


@pytest.mark.parametrize("valeur", ["Fusion Drive", "HDD", True, 7200.5, -1, []])
def test_type_de_forme_inattendue_arrete_le_pipeline(valeur):
    """Une valeur inattendue rabotée pour « passer » serait pire que l'arrêt."""
    with pytest.raises(PipelineArrete):
        normaliser_type_disque(valeur)


# --------------------------------------------------------------------------- #
# `internal-hard-drive.form_factor`
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("source", "attendu"),
    [(2.5, '2.5"'), (3.5, '3.5"'), ("M.2-2280", "M.2-2280"), ("mSATA", "mSATA")],
)
def test_form_factor_donne_une_seule_enumeration_textuelle(source, attendu):
    assert normaliser_form_factor(source) == attendu


@pytest.mark.parametrize("valeur", [1.8, 5.25, None, True, []])
def test_form_factor_inattendu_arrete_le_pipeline(valeur):
    with pytest.raises(PipelineArrete):
        normaliser_form_factor(valeur)


# --------------------------------------------------------------------------- #
# `memory.speed` et `memory.modules`
# --------------------------------------------------------------------------- #


def test_speed_est_eclate_en_generation_et_frequence():
    assert eclater_speed_memoire([5, 6000]) == (5, 6000)


def test_modules_est_eclate_et_la_capacite_totale_est_derivee():
    assert eclater_modules_memoire([2, 16]) == (2, 16, 32)


def test_specs_memoire_produit_une_capacite_totale_coherente():
    """Le validateur croisé de `SpecsMemoire` recalcule cette colonne : elle doit tenir."""
    specs = specs_memoire(
        {
            "speed": [5, 6000],
            "modules": [4, 8],
            "cas_latency": 30,
            "first_word_latency": 10.0,
            "color": "Black",
        }
    )
    assert specs["ddr_generation"] == 5
    assert specs["frequence_mhz"] == 6000
    assert specs["capacite_totale_gb"] == specs["nb_modules"] * specs["taille_module_gb"] == 32


@pytest.mark.parametrize("valeur", [[5], [5, 6000, 1], "5", None, [5, "6000"], [5.5, 6000]])
def test_un_couple_malforme_arrete_le_pipeline(valeur):
    with pytest.raises(PipelineArrete):
        eclater_speed_memoire(valeur)


def test_resolution_est_eclatee_en_largeur_et_hauteur():
    assert eclater_resolution([2560, 1440]) == (2560, 1440)


# --------------------------------------------------------------------------- #
# `headphones.frequency_response` — le piège d'unité
# --------------------------------------------------------------------------- #


def test_frequency_response_lit_par_position_pas_par_min_max():
    """15 Hz - 25 kHz : les deux composantes n'ont pas la même unité."""
    assert eclater_frequency_response([15, 25], "HP HyperX Cloud II") == (15, Decimal(25))


def test_piege_dunite_un_100_10_nest_pas_une_inversion_a_corriger():
    """`[100, 10]` = 100 Hz - 10 kHz, un casque de communication. **Sans échange.**

    C'est le test qui garde le piège d'unité de l'étape 3 : `API.md` annonce les deux
    composantes en kHz, c'est faux pour la première, et les 32 « inversions »
    apparentes du dataset s'expliquent toutes par là. Un correctif `min`/`max`
    détruirait la donnée sur ces 32 produits — et ce test échouerait, ce qui est
    exactement son rôle.
    """
    assert eclater_frequency_response([100, 10], "MSI Immerse GH20") == (100, Decimal(10))


@pytest.mark.parametrize(
    "valeur",
    [
        [0, 25],  # composante 0 sous la plage de contrôle [1, 1000] Hz
        [2000, 25],  # composante 0 au-dessus : ce serait des kHz, la règle serait fausse
        [15, 0.2],  # composante 1 sous [0,5, 200] kHz
        [15, 25000],  # composante 1 au-dessus : ce serait des Hz
    ],
)
def test_une_frequence_hors_plage_de_controle_arrete_le_pipeline(valeur):
    """Hors plage = la règle de position est fausse sur cet enregistrement. On s'arrête."""
    with pytest.raises(PipelineArrete) as echec:
        eclater_frequency_response(valeur, "Produit fautif")
    assert "Produit fautif" in str(echec.value)


# --------------------------------------------------------------------------- #
# `marque` — §3.4quater
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("nom", "attendu"),
    [
        ("Intel Core i5-12400F", "Intel"),  # premier mot, cas courant
        ("TEAMGROUP", "TEAMGROUP"),  # nom d'un seul mot
        ("Western Digital Blue SN5000", "Western Digital"),  # table multi-mots
        ("Silicon Power UD90", "Silicon Power"),  # table multi-mots
        ("Sabrent Rocket 4 Plus", "Sabrent"),  # absent de la table → premier mot
        ("Creative Labs Sound Blaster", "Creative"),  # gamme, pas marque : premier mot
    ],
)
def test_extraction_de_la_marque(nom, attendu):
    assert extraire_marque(nom) == attendu


def test_la_table_multi_mots_est_fermee_et_ninvente_rien():
    """Un nom dont le début n'est pas dans la table rend son premier mot, point.

    C'est ce qui distingue un parsing déterministe documenté d'une heuristique : la
    table ne s'applique jamais « à peu près ».
    """
    assert extraire_marque("Western Union Truc") == "Western"
    assert extraire_marque("Cooler Airflow 9000") == "Cooler"


def test_la_casse_source_est_conservee():
    assert extraire_marque("gigabyte Eagle OC") == "gigabyte"


def test_un_nom_vide_arrete_le_pipeline():
    with pytest.raises(PipelineArrete):
        extraire_marque("   ")


# --------------------------------------------------------------------------- #
# Conversions numériques
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("source", "attendu"),
    [(5, "5"), (5.0, "5"), (4.70, "4.7"), (100.0, "100"), (0.875, "0.875"), (3.333, "3.333")],
)
def test_en_decimal_canonicalise_les_zeros_de_queue(source, attendu):
    """`5` et `5.0` doivent produire la même chaîne, sinon l'identifiant diffère."""
    assert str(en_decimal(source)) == attendu


def test_un_prix_a_plus_de_deux_decimales_arrete_le_pipeline():
    """La colonne est `numeric(10,2)` : arrondir ici modifierait un fait."""
    assert normaliser_prix(451.5) == Decimal("451.50")
    with pytest.raises(PipelineArrete):
        normaliser_prix(19.999)


# --------------------------------------------------------------------------- #
# `price_per_gb` — arbitrage D
# --------------------------------------------------------------------------- #


def test_price_per_gb_arrondit_a_trois_decimales_en_decimal():
    assert calculer_price_per_gb(Decimal("149.99"), 2000) == Decimal("0.075")
    assert calculer_price_per_gb(Decimal("100.00"), 3) == Decimal("33.333")


def test_les_grandeurs_derivees_du_prix_sont_absentes_avant_la_deduplication():
    """La clé canonique est calculée sur ces specs : `price_per_gb` ne doit pas y être."""
    specs = {"capacity": 1000, "form_factor": '2.5"', "interface": "SATA 6.0 Gb/s"}
    assert "price_per_gb" not in specs
    enrichies = ajouter_grandeurs_derivees_du_prix("internal-hard-drive", specs, Decimal("56.95"))
    assert enrichies["price_per_gb"] == Decimal("0.057")
    # Le dictionnaire d'origine n'est pas muté : l'ordre des opérations reste lisible.
    assert "price_per_gb" not in specs


def test_aucune_grandeur_derivee_sur_les_categories_qui_nen_portent_pas():
    specs = {"core_count": 8}
    assert ajouter_grandeurs_derivees_du_prix("cpu", specs, Decimal("100")) == specs
