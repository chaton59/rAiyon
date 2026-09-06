"""Le décor des tests du validateur : une conversation d'écrans, et son contexte fourni.

⚠️ **Les charges utiles ne sont pas écrites à la main.** Elles sortent des vrais outils,
sérialisées par le vrai `en_tool_result()` : un fixture recopié à la main testerait notre
souvenir du protocole, et c'est exactement le genre d'erreur que l'étape 9 existe pour
attraper. Le prix à payer est deux dépôts en mémoire ; le gain est qu'un renommage de clé
casse ces tests au lieu de les laisser passer.

### Le scénario, et pourquoi il a cette forme

1. le client demande un écran 144 Hz à 400 $ → `record_criteria` ;
2. `probe_catalog` sonde un sous-catalogue **plus large** que ce que la recherche rendra
   — il contient un écran à 165 Hz et un autre à 108,00 $, qui ne seront **jamais**
   rendus comme produits ;
3. `search_products` rend trois écrans et un quatrième au-dessus du budget.

Les deux valeurs du point 2 sont les pièges de l'étape :

* **108,00 $** est la borne basse de la fourchette de sondage. Attribuée à un produit
  nommé, c'est l'oracle à prix du §7 — et un contexte aplati l'accepterait.
* **165 Hz** existe dans la distribution du sondage et sur **aucun** produit fourni.
  Annoncé sur un écran, c'est une spec déduite d'un sondage.

Les produits « vus au sondage seulement » ne sont donc **pas** dans `ContexteFourni` :
c'est tout l'enjeu, et un fixture qui les y mettrait viderait les tests de leur sens.
"""

from dataclasses import replace
from decimal import Decimal
from typing import Any

from outils_de_test import TOLERANCE, DepotEnMemoire, etat_avec
from raiyon.catalogue.schemas import ProduitEnBase
from raiyon.matching.criteres import Importance, Operateur
from raiyon.tools.etat import CritereTexte, DemandeBudget, EtatSession, fusionner
from raiyon.tools.outils import (
    ArgumentsCritere,
    ArgumentsEnregistrement,
    en_tool_result,
    enregistrer_criteres,
    rechercher_produits,
    sonder_catalogue,
)
from raiyon.validateur.contexte import ContexteFourni, contexte_des_resultats

BUDGET = "400"


def ecran(numero: str, nom: str, marque: str, prix: str, **specs: Any) -> ProduitEnBase:
    """Un écran au nom réaliste. Le nom **est** la donnée testée : pas de « modele 1 »."""
    return ProduitEnBase(
        id=f"monitor-{numero}",
        nom=nom,
        marque=marque,
        categorie="monitor",
        prix_usd=Decimal(prix),
        disponible=True,
        specs={  # type: ignore[arg-type]
            "screen_size": Decimal("27"),
            "largeur_px": 2560,
            "hauteur_px": 1440,
            "aspect_ratio": "16:9",
            "panel_type": "IPS",
            "refresh_rate": 144,
            "response_time": Decimal("1"),
            **specs,
        },
    )


SAMSUNG = ecran("0000000001", "Samsung Odyssey G50A", "Samsung", "249.99")
DELL = ecran("0000000002", "Dell S2721DGF", "Dell", "329.99")
AOC = ecran("0000000003", "AOC 24G2SP", "AOC", "159.99", screen_size=Decimal("24"))
"""Vu au sondage seulement : le sous-catalogue est plus large que ce que la recherche rend."""
LG = ecran("0000000004", "LG 27GP850-B", "LG", "417.14")
"""Au-dessus du budget de 400 $ : écart exact de 17,14 $."""

GIGABYTE = ecran("0000000005", "Gigabyte M27Q X", "Gigabyte", "399.99", refresh_rate=165)
"""**Jamais rendu par une recherche.** Sa fréquence n'existe que dans la distribution du
sondage : c'est la valeur du piège nº9."""

SCEPTRE = ecran(
    "0000000007", "Sceptre C248W-1920RN", "Sceptre", "189.99", screen_size=Decimal("24")
)
"""**Le nom qui a fait crier la règle 5 en conversation réelle.** « C248W » s'y lit comme
248 watts, et la règle 5 refusait une recommandation exacte. Il est dans le décor
**nominal** — pas dans un test à part — parce que c'est là qu'il a mordu : sur une
recommandation juste, citée verbatim comme §3.4ter l'exige."""

AOPEN = ecran("0000000006", "AOPEN 27HC5R", "AOPEN", "108.00")
"""**Jamais rendu par une recherche.** Son prix est la borne basse de la fourchette :
c'est le montant du piège nº6."""

ASUS = ecran("0000000008", "Asus ROG Strix XG27AQ", "Asus", "429.99")
"""**Un second produit de la zone de tolérance**, écart exact de 29,99 $.

Il n'est **pas** dans le décor nominal : il n'existe que pour
`contexte_a_deux_hors_budget()`, qui sert le test de contamination de l'étape 18. Un seul
produit hors budget ne permet pas de vérifier que la règle 4 raisonne **par identifiant**
— avec un seul écart en jeu, « l'écart est cité quelque part » et « l'écart de ce
produit-là est cité » sont indistinguables."""

RENDUS = (SAMSUNG, DELL, SCEPTRE)
HORS_BUDGET = (LG,)
SONDES = (AOPEN, AOC, SAMSUNG, DELL, GIGABYTE)
"""Le sous-catalogue au moment du sondage — plus large que ce que la recherche rendra."""


def etat_du_scenario() -> EtatSession:
    """Écran, 144 Hz bloquant, 400 $ — construit par la porte normale (`fusionner`)."""
    return etat_avec(
        "monitor",
        CritereTexte(
            champ="refresh_rate",
            operateur=Operateur.AU_MOINS,
            valeur="144",
            importance=Importance.BLOQUANT,
        ),
        budget=BUDGET,
    )


def charge_enregistrement() -> dict[str, object]:
    """La charge utile de `record_criteria`, par l'outil réel."""
    resultat = enregistrer_criteres(
        EtatSession(),
        ArgumentsEnregistrement(
            categorie="monitor",
            criteres=(
                ArgumentsCritere(
                    champ="refresh_rate",
                    operateur=Operateur.AU_MOINS,
                    valeur="144",
                    importance=Importance.BLOQUANT,
                ),
            ),
            budget_usd=BUDGET,
        ),
        tour_client=1,
    )
    return en_tool_result(resultat)


def charge_sondage() -> dict[str, object]:
    """La charge utile de `probe_catalog`, sur le sous-catalogue large."""
    depot = DepotEnMemoire()
    depot.produits = list(SONDES)
    return en_tool_result(sonder_catalogue(etat_du_scenario(), depot, tolerance=TOLERANCE))


def resultat_de_recherche():
    """Le `ResultatMatching` réel — c'est lui que `repli.rediger()` consomme."""
    depot = DepotEnMemoire()
    depot.produits = list(RENDUS)
    depot.hors_budget = list(HORS_BUDGET)
    return rechercher_produits(
        etat_du_scenario(), depot, tour_client=1, tolerance=TOLERANCE
    ).resultat


def charge_recherche() -> dict[str, object]:
    """La charge utile de `search_products`, par l'outil réel."""
    depot = DepotEnMemoire()
    depot.produits = list(RENDUS)
    depot.hors_budget = list(HORS_BUDGET)
    return en_tool_result(
        rechercher_produits(etat_du_scenario(), depot, tour_client=1, tolerance=TOLERANCE)
    )


def charge_recherche_avec_budget(budget: str) -> dict[str, object]:
    """La même recherche, sous un autre plafond — le tour 2 de `desserrage_refuse`.

    Sert le faux positif de l'étape 32 : sous 400 $ le LG est `au_dessus_du_budget`, sous
    500 $ il est dans `produits`. Deux charges du **même outil réel**, et c'est le point —
    le défaut vivait dans l'accumulation de l'une sur l'autre, pas dans une règle.
    """
    depot = DepotEnMemoire()
    # ⚠️ Le dépôt de test **ne calcule pas** la frontière de budget : c'est l'appelant qui
    # range les produits dans l'un ou l'autre seau. Le tour 2 la déplace donc à la main —
    # LG passe des hors-budget aux rendus —, ce qui est exactement ce que le moteur réel
    # fait quand le plafond monte, et c'est la seule chose que ce décor doit reproduire.
    depot.produits = list(HORS_BUDGET)
    depot.hors_budget = []
    etat = replace(etat_du_scenario(), budget_usd=Decimal(budget))
    return en_tool_result(rechercher_produits(etat, depot, tour_client=2, tolerance=TOLERANCE))


def contexte_apres_sondage() -> ContexteFourni:
    """Critères enregistrés et sondage fait — **aucun produit fourni**."""
    return contexte_des_resultats([charge_enregistrement(), charge_sondage()])


def contexte_complet() -> ContexteFourni:
    """La conversation entière : critères, sondage, recherche. Le décor des pièges."""
    return contexte_des_resultats([charge_enregistrement(), charge_sondage(), charge_recherche()])


def contexte_a_deux_hors_budget() -> ContexteFourni:
    """Le même décor, mais **deux** produits en zone de tolérance : LG (17,14 $) et Asus
    (29,99 $).

    Sert le test de contamination de l'étape 18 : citer l'écart de l'un ne doit pas
    satisfaire l'autre. Avec un seul produit hors budget, la vérification par identifiant
    et la vérification « un écart quelconque est cité » rendent le même verdict.
    """
    depot = DepotEnMemoire()
    depot.produits = list(RENDUS)
    depot.hors_budget = [LG, ASUS]
    charge = en_tool_result(
        rechercher_produits(etat_du_scenario(), depot, tour_client=1, tolerance=TOLERANCE)
    )
    return contexte_des_resultats([charge_enregistrement(), charge_sondage(), charge])


def messages_du_scenario() -> list[dict[str, Any]]:
    """La même conversation, mais **au format API** : c'est ce que la boucle relira.

    Les charges utiles sont enveloppées comme `bloc_tool_result()` les enveloppe —
    en JSON, dans un bloc `tool_result` d'un message de rôle `user`.
    """
    import json

    blocs = [
        {
            "type": "tool_result",
            "tool_use_id": f"tu_{numero}",
            "content": json.dumps(charge, ensure_ascii=False),
            "is_error": False,
        }
        for numero, charge in enumerate(
            [charge_enregistrement(), charge_sondage(), charge_recherche()], start=1
        )
    ]
    return [{"role": "user", "content": [bloc]} for bloc in blocs]


def etat_sans_criteres() -> EtatSession:
    """Un état vierge, pour les cas où rien n'a encore été enregistré."""
    return fusionner(EtatSession(), tour_client=1, budget=DemandeBudget(None)).etat
