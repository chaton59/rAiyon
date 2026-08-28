"""Orchestration de la passe A, sur un faux `data/raw/` — aucune base, aucune clé API.

`data/raw/` n'est pas versionné : ces tests construisent leur propre répertoire source,
minuscule, ce qui les rend exécutables sur une machine qui n'a jamais téléchargé le
dataset. Ce qu'ils gardent : l'entonnoir (les chiffres du rapport doivent être ceux du
pipeline), l'ordre non commutatif des opérations, et le contrôle de la transformation 6
qui doit **arrêter** le pipeline plutôt que continuer sur une formule fausse.
"""

import json
from pathlib import Path

import pytest

from raiyon.catalogue.normalisation import PipelineArrete
from raiyon.catalogue.pipeline import (
    CATEGORIE_RETIREE,
    construire_rapport,
    ecrire_seed,
    executer_passe_a,
    lire_seed,
)
from raiyon.catalogue.schemas import CATEGORIES


def disque(nom: str, prix: float | None, capacite: int, **surcharges) -> dict:
    ligne = {
        "name": nom,
        "price": prix,
        "capacity": capacite,
        "type": "SSD",
        "form_factor": "M.2-2280",
        "interface": "M.2 PCIe 4.0 X4",
        "price_per_gb": round(prix / capacite, 3) if prix else None,
        "cache": None,
    }
    return {**ligne, **surcharges}


def processeur(nom: str, prix: float | None, tdp: int = 65) -> dict:
    return {
        "name": nom,
        "price": prix,
        "core_count": 6,
        "core_clock": 3.4,
        "tdp": tdp,
        "microarchitecture": "Alder Lake",
        "boost_clock": None,
        "graphics": None,
    }


def ecran(nom: str, prix: float) -> dict:
    return {
        "name": nom,
        "price": prix,
        "screen_size": 27,
        "resolution": [2560, 1440],
        "aspect_ratio": "16:9",
        "panel_type": "IPS",
        "refresh_rate": 165,
        "response_time": 1,
    }


def barrette(nom: str, prix: float, couleur: str = "Black") -> dict:
    return {
        "name": nom,
        "price": prix,
        "speed": [5, 6000],
        "modules": [2, 16],
        "cas_latency": 30,
        "first_word_latency": 10.0,
        "price_per_gb": round(prix / 32, 3),
        "color": couleur,
    }


def carte(nom: str, prix: float) -> dict:
    return {
        "name": nom,
        "price": prix,
        "chipset": "GeForce RTX 4070",
        "memory": 12,
        "length": 240,
        "core_clock": 1920,
        "boost_clock": 2475,
        "color": "Black",
    }


def casque(nom: str, prix: float) -> dict:
    return {
        "name": nom,
        "price": prix,
        "type": "Circumaural",
        "frequency_response": [15, 25],
        "microphone": True,
        "wireless": False,
        "enclosure_type": "Closed",
        "color": "Black",
    }


def ecrire_raw(racine: Path, contenus: dict[str, list[dict]]) -> Path:
    """Fabrique un `data/raw/` minimal. Les six catégories plus `keyboard`."""
    brut = racine / "raw"
    brut.mkdir()
    for categorie in (*CATEGORIES, CATEGORIE_RETIREE):
        lignes = contenus.get(categorie, [])
        (brut / f"{categorie}.json").write_text(json.dumps(lignes), encoding="utf-8")
    return brut


@pytest.fixture
def brut_minimal(tmp_path: Path) -> Path:
    """Un dataset jouet : quelques produits par catégorie, dont des pièges."""
    return ecrire_raw(
        tmp_path,
        {
            "cpu": [
                processeur("Intel Core i5-12400", 199.99),
                processeur("Intel Core i5-12400", 149.99),  # doublon strict → fusion
                processeur("AMD Ryzen 5 5600", 129.00),
                processeur("Intel Celeron", None),  # sans prix → filtré
                processeur("Intel Pentium", 0),  # prix nul → filtré
            ],
            "internal-hard-drive": [
                disque("Samsung 990 Pro", 149.99, 2000),
                disque("Crucial P3", 56.95, 1000),
                disque("Seagate Barracuda", 44.99, 2000, type=7200, form_factor=3.5),
                disque("Inconnu X", 30.00, 500, type=None),  # sans type → écarté
            ],
            "monitor": [ecran("LG 27GP850-B", 299.99), ecran("Dell S2721DGF", 279.99)],
            "memory": [
                barrette("Corsair Vengeance", 99.99, "Black"),
                barrette("Corsair Vengeance", 104.99, "White"),  # variante → conservée
            ],
            "video-card": [carte("MSI Ventus 3X", 549.99), carte("Asus Dual", 579.99)],
            "headphones": [casque("HP HyperX Cloud II", 70.98), casque("Razer Kraken", 49.99)],
            CATEGORIE_RETIREE: [{"name": "Logitech K120", "price": 19.99, "style": "Standard"}],
        },
    )


# --------------------------------------------------------------------------- #
# L'entonnoir
# --------------------------------------------------------------------------- #


def test_lentonnoir_compte_chaque_etape(brut_minimal):
    resultat = executer_passe_a(brut_minimal, cible=10)
    e = resultat.entonnoir

    assert e.lues["cpu"] == 5
    assert e.sans_prix["cpu"] == 2  # `None` et 0 : le filtre est « strictement positif »
    assert e.a_prix["cpu"] == 3
    assert e.normalisees["cpu"] == 3
    assert e.dedupliquees["cpu"] == 2  # le doublon strict a fusionné
    assert e.validees["cpu"] == 2


def test_la_ligne_sans_type_est_ecartee_avec_son_motif(brut_minimal):
    resultat = executer_passe_a(brut_minimal, cible=10)
    assert resultat.entonnoir.motifs["internal-hard-drive : type de disque absent"] == 1
    assert resultat.entonnoir.normalisees["internal-hard-drive"] == 3


def test_keyboard_est_compte_dans_les_lues_puis_ecarte(brut_minimal):
    """Le total « lues » doit correspondre à des fichiers réels, sans quoi il ment."""
    resultat = executer_passe_a(brut_minimal, cible=10)
    assert resultat.entonnoir.lues[CATEGORIE_RETIREE] == 1
    assert CATEGORIE_RETIREE not in resultat.entonnoir.a_prix
    assert all(p.categorie != CATEGORIE_RETIREE for p in resultat.selection.produits)


def test_la_deduplication_garde_le_prix_le_plus_bas(brut_minimal):
    resultat = executer_passe_a(brut_minimal, cible=10)
    processeurs = [p for p in resultat.selection.produits if p.categorie == "cpu"]
    i5 = next(p for p in processeurs if p.nom == "Intel Core i5-12400")
    assert str(i5.prix_usd) == "149.99"


def test_les_variantes_de_couleur_survivent_a_la_deduplication(brut_minimal):
    resultat = executer_passe_a(brut_minimal, cible=10)
    barrettes = [p for p in resultat.selection.produits if p.categorie == "memory"]
    assert len(barrettes) == 2


def test_price_per_gb_est_present_et_recalcule(brut_minimal):
    resultat = executer_passe_a(brut_minimal, cible=10)
    disques = [p for p in resultat.selection.produits if p.categorie == "internal-hard-drive"]
    samsung = next(p for p in disques if p.nom == "Samsung 990 Pro")
    assert samsung.specs_pour_base()["price_per_gb"] == "0.075"


def test_le_form_factor_numerique_devient_une_chaine(brut_minimal):
    resultat = executer_passe_a(brut_minimal, cible=10)
    seagate = next(p for p in resultat.selection.produits if p.nom == "Seagate Barracuda")
    specs = seagate.specs_pour_base()
    assert specs["form_factor"] == '3.5"'
    assert specs["type"] == "HDD"
    assert specs["rpm"] == 7200


# --------------------------------------------------------------------------- #
# Le contrôle de la transformation 6
# --------------------------------------------------------------------------- #


def test_un_price_per_gb_source_incoherent_arrete_le_pipeline(tmp_path):
    """Si la source ne calcule pas ce qu'on croit, il faut le comprendre, pas continuer.

    Le seuil est double : plus de 1 % des lignes s'écartant de plus de 1 %. Ici les
    trois disques annoncent un ratio dix fois trop grand — la formule supposée serait
    donc fausse, et le pipeline doit s'arrêter en le disant.
    """
    brut = ecrire_raw(
        tmp_path,
        {
            "internal-hard-drive": [
                disque("A", 100.0, 1000, price_per_gb=1.0),
                disque("B", 200.0, 1000, price_per_gb=2.0),
                disque("C", 300.0, 1000, price_per_gb=3.0),
            ]
        },
    )
    with pytest.raises(PipelineArrete) as echec:
        executer_passe_a(brut, cible=3)
    assert "price_per_gb" in str(echec.value)


def test_le_controle_tolere_les_arrondis_de_la_source(brut_minimal):
    """La source arrondit son propre ratio : quelques dixièmes de pourcent d'écart
    sont attendus et ne doivent rien arrêter."""
    resultat = executer_passe_a(brut_minimal, cible=10)
    controles = {c.categorie: c for c in resultat.controles_price_per_gb}
    assert controles["internal-hard-drive"].lignes_au_dela_du_seuil == 0


# --------------------------------------------------------------------------- #
# Sorties
# --------------------------------------------------------------------------- #


def test_le_pipeline_est_reproductible(brut_minimal, tmp_path):
    """Deux exécutions donnent le même seed, au bit près — c'est un fichier committé."""
    premier = tmp_path / "a.jsonl"
    second = tmp_path / "b.jsonl"
    ecrire_seed(executer_passe_a(brut_minimal, cible=10).selection.produits, premier)
    ecrire_seed(executer_passe_a(brut_minimal, cible=10).selection.produits, second)
    assert premier.read_bytes() == second.read_bytes()


def test_le_jsonl_fait_laller_retour_sans_perte(brut_minimal, tmp_path):
    produits = executer_passe_a(brut_minimal, cible=10).selection.produits
    chemin = tmp_path / "produits.jsonl"
    ecrire_seed(produits, chemin)
    relus = lire_seed(chemin)
    assert [p.model_dump(mode="json") for p in relus] == [
        p.model_dump(mode="json") for p in produits
    ]


def test_une_ligne_invalide_du_jsonl_est_refusee_a_la_relecture(tmp_path):
    """Être committé ne rend pas un fichier digne de confiance."""
    chemin = tmp_path / "produits.jsonl"
    chemin.write_text('{"id": "cpu-0000000001", "nom": "X"}\n', encoding="utf-8")
    with pytest.raises(PipelineArrete):
        lire_seed(chemin)


def test_le_rapport_porte_les_sections_attendues(brut_minimal):
    rapport = construire_rapport(executer_passe_a(brut_minimal, cible=10))
    for section in (
        "## Entonnoir",
        "## Motifs de rejet",
        "## Déduplication",
        "## Contrôle de `price_per_gb`",
        "Taux de remplissage",
        "Marques par volume",
        "### G1",
        "### G2",
        "### G3",
    ):
        assert section in rapport


def test_un_repertoire_brut_absent_dit_ou_trouver_les_donnees(tmp_path):
    with pytest.raises(FileNotFoundError) as echec:
        executer_passe_a(tmp_path / "nulle-part")
    assert "SOURCE.md" in str(echec.value)
