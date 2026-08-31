"""Helpers de la couche outils : état construit par la porte normale, dépôt en mémoire.

**Aucun de ces helpers n'a besoin de `.env`, ni de base, ni de clé API.** C'est la
propriété que la porte de sortie de l'étape 7 demande, et elle se tient par
construction : `EtatSession` est pure, et la tolérance budget est injectée plutôt que lue
dans la configuration.

Ce module est **importé**, pas collecté — même raison que `base_de_test.py` et
`produits_de_test.py`. Il ne s'appelle surtout pas `conftest` : `tests/matching/` en a
déjà un, les deux se seraient chargés sous le même nom de module, et
`pytest tests/tools tests/matching` aurait échoué à l'import selon l'ordre de collecte.
Le piège est réel — il s'est déclenché à l'écriture de ces tests.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from produits_de_test import fabriquer
from raiyon.catalogue.schemas import Categorie, ProduitEnBase
from raiyon.matching.attributs import ATTRIBUTS, valeur_du_produit
from raiyon.matching.criteres import Importance, Operateur, RequeteMatching
from raiyon.matching.depot import BornesPrix, Comptages, Fourchette, RelevesDeRelachement
from raiyon.tools.etat import CritereTexte, DemandeBudget, EtatSession, fusionner

TOLERANCE = Decimal("0.15")
"""La valeur par défaut de `RAIYON_BUDGET_TOLERANCE`, recopiée pour que les tests
n'aient pas à lire la configuration du processus — donc pas de clé API."""


def critere(
    champ: str,
    operateur: Operateur = Operateur.AU_MOINS,
    valeur: str = "144",
    importance: Importance = Importance.SOUHAIT,
) -> CritereTexte:
    """Un critère entrant, tel que le modèle l'écrirait : la valeur est du texte."""
    return CritereTexte(champ=champ, operateur=operateur, valeur=valeur, importance=importance)


def etat_avec(
    categorie: Categorie = "monitor",
    *criteres: CritereTexte,
    budget: str | None = None,
    tour_client: int = 1,
) -> EtatSession:
    """Un état construit **par la porte normale**, jamais à la main.

    Fabriquer un `EtatSession` en posant directement ses champs testerait un état que
    `fusionner()` ne peut pas produire. Les tests hostiles partent donc toujours d'un
    état légitime — c'est ce qui rend leur conclusion transposable à la production.
    """
    return fusionner(
        EtatSession(),
        tour_client=tour_client,
        categorie=categorie,
        ajouts=criteres,
        budget=None if budget is None else DemandeBudget(budget),
    ).etat


# --------------------------------------------------------------------------- #
# Le dépôt factice — il calcule ses agrégats sur ce qu'on lui a mis dedans
# --------------------------------------------------------------------------- #


@dataclass
class DepotEnMemoire:
    """Un dépôt en mémoire qui **dérive** ses agrégats de ses produits.

    Il ne rejoue pas les filtres — c'est le travail de `DepotSql`, et les tests
    d'intégration le vérifient sur le catalogue réel. Ce qu'il sert ici, ce sont les
    comptages : l'outil doit ordonner, tronquer, séparer les deux comptes de budget et
    dire ce qu'il a tronqué, et rien de tout cela ne dépend du SQL.

    Il **journalise les fourchettes** qu'on lui passe : c'est ainsi que les tests
    constatent que le sondage applique bien le budget, et que la bande de tolérance des
    outils est exactement celle que le moteur emploie.
    """

    produits: list[ProduitEnBase] = field(default_factory=list)
    hors_budget: list[ProduitEnBase] = field(default_factory=list)
    ecartes: dict[str, int] = field(default_factory=dict)
    releves: RelevesDeRelachement = field(default_factory=RelevesDeRelachement)
    fourchettes: list[Fourchette] = field(default_factory=list)

    def _lot(self, categorie: Categorie, fourchette: Fourchette) -> list[ProduitEnBase]:
        """Ce que le dépôt rendrait. Bornée à gauche, la fourchette désigne la zone de
        tolérance ; sinon, le classement principal.

        La catégorie est filtrée — c'est le seul filtre que ce dépôt applique. Sans lui,
        un test qui change de catégorie recevrait les produits de la précédente et
        déclencherait la garde du moteur, pour une raison qui ne dit rien du code testé.
        """
        self.fourchettes.append(fourchette)
        source = self.hors_budget if fourchette.min_exclu is not None else self.produits
        return [produit for produit in source if produit.categorie == categorie]

    def candidats(self, requete: RequeteMatching, fourchette: Fourchette) -> list[ProduitEnBase]:
        return self._lot(requete.categorie, fourchette)

    def ecartes_faute_de_donnee(
        self, requete: RequeteMatching, fourchette: Fourchette
    ) -> dict[str, int]:
        return dict(self.ecartes)

    def releves_de_relachement(
        self, requete: RequeteMatching, fourchette: Fourchette
    ) -> RelevesDeRelachement:
        return self.releves

    def compter(self, requete: RequeteMatching, fourchette: Fourchette) -> int:
        return len(self._lot(requete.categorie, fourchette))

    def bornes_de_prix(self, requete: RequeteMatching, fourchette: Fourchette) -> BornesPrix | None:
        lot = self._lot(requete.categorie, fourchette)
        if not lot:
            return None
        prix = [produit.prix_usd for produit in lot]
        return BornesPrix(plus_bas=min(prix), plus_haut=max(prix))

    def distributions(
        self, requete: RequeteMatching, fourchette: Fourchette, champs
    ) -> dict[str, Comptages]:
        lot = self._lot(requete.categorie, fourchette)
        comptages = {}
        for champ in champs:
            attribut = ATTRIBUTS[requete.categorie][champ]
            effectifs: dict[str, int] = {}
            for produit in lot:
                valeur = valeur_du_produit(produit, attribut)
                if valeur is None:
                    continue
                texte = "true" if valeur is True else "false" if valeur is False else str(valeur)
                effectifs[texte] = effectifs.get(texte, 0) + 1
            comptages[champ] = Comptages(
                champ=champ,
                effectifs=tuple(effectifs.items()),
                renseignes=sum(effectifs.values()),
                total=len(lot),
            )
        return comptages


def ecrans(nombre: int = 3, **specs) -> list[ProduitEnBase]:
    """Des écrans numérotés, tous identiques sauf ce que le test précise."""
    return [
        fabriquer("monitor", numero, prix=f"{100 + numero * 10}", **specs)
        for numero in range(1, nombre + 1)
    ]
