"""Produits inventés, partagés par les suites qui en ont besoin. **Jamais dans `data/`.**

Fabriquer un produit pour faire passer un test le ferait entrer dans le catalogue,
c'est-à-dire dans ce que le LLM aura le droit de citer, et §2 l'interdit. Ces produits
vivent donc dans `tests/`, et n'en sortent pas.

Ce module est **importé**, pas collecté — même raison que `base_de_test.py` : deux
répertoires de tests en ont besoin (`tests/matching/` depuis l'étape 6,
`tests/tools/` depuis l'étape 7) et un conftest ne s'importe pas depuis un autre.
`pythonpath = ["tests"]` le rend visible des deux.
"""

from decimal import Decimal
from typing import Any

from raiyon.catalogue.schemas import Categorie, ProduitEnBase

DEFAUTS: dict[Categorie, dict[str, Any]] = {
    "monitor": {
        "screen_size": Decimal("27"),
        "largeur_px": 2560,
        "hauteur_px": 1440,
        "aspect_ratio": "16:9",
        "panel_type": "IPS",
        "refresh_rate": 144,
        "response_time": Decimal("1"),
    },
    "internal-hard-drive": {
        "capacity": 1000,
        "form_factor": "M.2-2280",
        "interface": "M.2 PCIe 4.0 X4",
        "type": "SSD",
        "rpm": None,
        "price_per_gb": Decimal("0.100"),
        "cache": 1024,
    },
    "memory": {
        "ddr_generation": 5,
        "frequence_mhz": 6000,
        "nb_modules": 2,
        "taille_module_gb": 16,
        "capacite_totale_gb": 32,
        "cas_latency": 30,
        "first_word_latency": Decimal("10"),
        "price_per_gb": Decimal("4"),
        "color": "Black",
    },
    "headphones": {
        "type": "Circumaural",
        "microphone": True,
        "wireless": False,
        "enclosure_type": "Closed",
        "freq_min_hz": 20,
        "freq_max_khz": Decimal("20"),
        "color": "Black",
    },
    "video-card": {
        "chipset": "GeForce RTX 4070",
        "memory": Decimal("12"),
        "length": 300,
        "core_clock": 1920,
        "boost_clock": 2475,
        "color": "Black",
    },
    "cpu": {
        "core_count": 8,
        "core_clock": Decimal("3.8"),
        "tdp": 65,
        "microarchitecture": "Zen 4",
        "boost_clock": Decimal("5.0"),
        "graphics": None,
    },
}
"""Un produit « moyen » par catégorie. Les tests ne redisent que ce qu'ils changent,
ce qui fait qu'une assertion se lit sans dérouler la fixture."""


def fabriquer(
    categorie: Categorie,
    numero: int,
    prix: str,
    marque: str = "Acme",
    **specs: Any,
) -> ProduitEnBase:
    """Un produit inventé, valide au sens de `ProduitEnBase`.

    L'identifiant respecte `MOTIF_ID` (`{categorie}-{10 hexadécimaux}`) : un produit de
    test qui ne passerait pas la validation du schéma ne prouverait rien du moteur.
    """
    return ProduitEnBase(
        id=f"{categorie}-{numero:010x}",
        nom=f"{marque} modele {numero}",
        marque=marque,
        categorie=categorie,
        prix_usd=Decimal(prix),
        disponible=True,
        specs={**DEFAUTS[categorie], **specs},  # type: ignore[arg-type]
    )
