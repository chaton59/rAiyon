"""Orchestration du moteur : dépôt → score → classement → trace → résultat.

Une seule fonction publique, `rechercher()`, et un résultat typé. Elle enchaîne les
deux moitiés de la frontière §3.16 sans jamais les mélanger : le dépôt dit qui est
candidat, le reste du module dit comment on le présente.

Ce que le résultat garantit, et qui ne dépend d'aucune consigne donnée au modèle :

* `produits` et `au_dessus_du_budget` sont **structurellement séparés** (§3.10). Le
  LLM ne peut pas présenter un produit hors budget comme étant dedans, quelle que soit
  sa sortie, parce qu'il ne les reçoit pas dans le même champ.
* Tous les produits rendus appartiennent à **une seule catégorie** (arbitrage K).
  L'invariant se vérifie en une ligne, et il est vérifié.
* `disponible = true` est toujours appliqué.
* `ecartes_faute_de_donnee` est **toujours présent**, vide quand il n'y a rien à dire.
* Il n'y a **pas de seuil de score plancher**. Un mauvais score reste une réponse ; un
  plancher recréerait un zéro résultat silencieux, exactement ce que le critère
  d'acceptation nº6 cherche à rendre impossible.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from raiyon.catalogue.schemas import Categorie, ProduitEnBase
from raiyon.config import get_settings
from raiyon.matching.criteres import RequeteMatching
from raiyon.matching.depot import DepotProduits, Fourchette, plafond_de_tolerance
from raiyon.matching.relachement import Diagnostic, diagnostiquer
from raiyon.matching.score import Evaluation, classer, classer_sans_le_prix, evaluer_lot
from raiyon.matching.trace import TraceProduit

LIMITE_PRODUITS = 3
"""1 à 3 produits recommandés (§1). Au-delà, ce n'est plus un conseil, c'est une liste."""

LIMITE_AU_DESSUS_DU_BUDGET = 2
"""La zone de tolérance est une mention, pas un second classement."""


class CategorieIncoherente(RuntimeError):
    """Un produit d'une autre catégorie est remonté. Ne doit jamais arriver."""


@dataclass(frozen=True, slots=True)
class ProduitHorsBudget:
    """Un produit de la zone de tolérance, avec l'écart exact (§3.10)."""

    produit: ProduitEnBase
    ecart_usd: Decimal


@dataclass(frozen=True, slots=True)
class ResultatMatching:
    """Ce que le moteur rend. La couche outils de l'étape 7 partira d'ici."""

    categorie: Categorie
    produits: tuple[ProduitEnBase, ...]
    traces: tuple[TraceProduit, ...]
    """Une trace par produit de `produits`, dans le même ordre.

    Les produits de la zone de tolérance n'en portent pas : leur explication **est**
    leur écart au budget, et les classer dans le même ordre reviendrait à les mêler au
    classement principal, ce que §3.10 interdit."""

    au_dessus_du_budget: tuple[ProduitHorsBudget, ...] = ()
    ecartes_faute_de_donnee: dict[str, int] = field(default_factory=dict)
    candidats_trouves: int = 0
    """Nombre de candidats avant troncature à trois. « Il me reste 12 modèles » est
    une information que l'agent utilisera (§3.7), et la perdre ici obligerait à
    re-interroger la base pour la retrouver."""

    diagnostic: Diagnostic | None = None
    """Renseigné **seulement** si `produits` est vide."""


def tolerance_budget() -> Decimal:
    """La tolérance de §3.10, en `Decimal`.

    ⚠️ `Settings.budget_tolerance` est typé `float`. La conversion passe par `str` :
    `Decimal(0.15)` vaut 0,1499999999999999944488848768742172978818416595458984375, et
    une multiplication `Decimal x float` sur un prix est un bug, pas un détail de
    style. Le budget porte un invariant produit, il se calcule en décimal exact.
    """
    return Decimal(str(get_settings().budget_tolerance))


def _trace(evaluation: Evaluation, rang: int, rang_sans_le_prix: int) -> TraceProduit:
    return TraceProduit(
        produit_id=evaluation.produit.id,
        score=evaluation.score,
        criteres_evalues=evaluation.criteres_evalues,
        criteres_indisponibles=evaluation.criteres_indisponibles,
        rang=rang,
        rang_sans_le_prix=rang_sans_le_prix,
        lignes=evaluation.lignes,
    )


def rechercher(
    depot: DepotProduits, requete: RequeteMatching, *, tolerance: Decimal | None = None
) -> ResultatMatching:
    """Exécute une recherche complète. Aucun appel LLM, aucune notion de session.

    `tolerance` est injectable pour que la suite de tests n'ait pas besoin de la
    configuration du processus — donc pas de clé API — là où elle vérifie un
    comportement de budget. Non renseignée, elle vient de `RAIYON_BUDGET_TOLERANCE`.
    """
    zone = tolerance if tolerance is not None else tolerance_budget()
    fourchette = Fourchette(max_inclus=requete.budget_usd)

    candidats = depot.candidats(requete, fourchette)
    _verifier_la_categorie(candidats, requete.categorie)
    ecartes = depot.ecartes_faute_de_donnee(requete, fourchette)

    evaluations = evaluer_lot(candidats, requete)
    classement = classer(evaluations)
    rangs_sans_le_prix = {
        evaluation.produit.id: rang
        for rang, evaluation in enumerate(classer_sans_le_prix(evaluations), start=1)
    }
    retenus = classement[:LIMITE_PRODUITS]

    hors_budget = _zone_de_tolerance(depot, requete, zone)

    diagnostic = None
    if not retenus:
        diagnostic = diagnostiquer(
            requete,
            depot.releves_de_relachement(requete, fourchette),
            ecartes,
            len(hors_budget),
        )

    return ResultatMatching(
        categorie=requete.categorie,
        produits=tuple(evaluation.produit for evaluation in retenus),
        traces=tuple(
            _trace(evaluation, rang, rangs_sans_le_prix[evaluation.produit.id])
            for rang, evaluation in enumerate(retenus, start=1)
        ),
        au_dessus_du_budget=hors_budget,
        ecartes_faute_de_donnee=ecartes,
        candidats_trouves=len(candidats),
        diagnostic=diagnostic,
    )


def _zone_de_tolerance(
    depot: DepotProduits, requete: RequeteMatching, tolerance: Decimal
) -> tuple[ProduitHorsBudget, ...]:
    """Les produits juste au-dessus du budget, avec leur écart. Jamais mélangés.

    Ils sont récupérés par le **même chemin** que les candidats, à la fourchette près :
    un produit hors budget satisfait donc exactement les mêmes critères durs que ceux
    du classement principal. Sans cela, la zone de tolérance deviendrait un second
    catalogue aux règles plus souples.
    """
    budget = requete.budget_usd
    if budget is None:
        return ()
    plafond = plafond_de_tolerance(budget, tolerance)
    produits = depot.candidats(requete, Fourchette(min_exclu=budget, max_inclus=plafond))
    _verifier_la_categorie(produits, requete.categorie)
    ordonnes = sorted(produits, key=lambda produit: (produit.prix_usd, produit.id))
    return tuple(
        ProduitHorsBudget(produit=produit, ecart_usd=produit.prix_usd - budget)
        for produit in ordonnes[:LIMITE_AU_DESSUS_DU_BUDGET]
    )


def _verifier_la_categorie(produits: list[ProduitEnBase], categorie: Categorie) -> None:
    """Un tour, une catégorie (arbitrage K). L'invariant se vérifie, il ne se suppose pas.

    Ce n'est pas une paranoïa gratuite : la couche outils de l'étape 7 laissera un
    modèle remplir la requête, et une « config gaming » demandée en un tour doit être
    impossible à servir **par construction**, pas par consigne de prompt.
    """
    intrus = {produit.categorie for produit in produits} - {categorie}
    if intrus:
        raise CategorieIncoherente(
            f"catégorie(s) inattendue(s) dans le résultat : {sorted(intrus)} — "
            f"attendu {categorie!r}"
        )
