"""La trace d'explication : structurée, jamais rédigée.

C'est cette trace — et non le LLM — qui portera le « pourquoi » affiché au client
(§ étape 6, point 3). Elle contient donc des **faits**, un par critère et par produit,
et **aucune phrase**.

La règle est mécanique et un test la garde : toute chaîne de caractères présente dans
une trace vient soit du registre (un nom de champ, un libellé français, une unité),
soit d'une énumération de ce module, soit du catalogue lui-même (`IPS`, `M.2-2280`).
Rien n'y est composé, rien n'y est mis en forme : ni symbole d'unité accolé à un
nombre, ni pourcentage, ni majuscule de début de phrase. La mise en forme est
l'affaire de l'étape 11, la rédaction celle de l'étape 8.

Le libellé français et l'unité voyagent **avec** la ligne plutôt que d'être rejoints
au registre plus tard : c'est ce dont le repli sur template de §3.11 niveau 3 a
besoin, et le laisser dehors reviendrait à le redécouvrir à l'étape 9.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from raiyon.matching.attributs import Role

ValeurTracee = Decimal | bool | str | None
"""Une valeur telle qu'elle sort du catalogue ou du critère. Les entiers sont
convertis en `Decimal` pour que la trace soit uniformément typée : un consommateur
n'a pas à se demander si `capacity` arrive en `int` et `screen_size` en `Decimal`."""


class Statut(StrEnum):
    """Ce que le critère a donné sur ce produit."""

    MATCHE = "matche"
    PARTIEL = "partiel"
    """La valeur ne satisfait pas la demande mais n'est pas au plancher du sous-score.
    N'existe que sur un critère scoré : un filtre dur n'a pas de moitié."""

    RATE = "rate"
    INDISPONIBLE = "indisponible"
    """Le produit ne déclare pas cette valeur. Le critère est **retiré du calcul** et
    les poids restants sont renormalisés — un sous-score de 0 punirait une donnée
    manquante, un sous-score de 0,5 inventerait une médiane (arbitrage F)."""


@dataclass(frozen=True, slots=True)
class LigneTrace:
    """Un critère confronté à un produit."""

    champ: str
    libelle_fr: str
    unite: str | None
    role_applique: Role
    statut: Statut
    valeur_produit: ValeurTracee
    valeur_demandee: ValeurTracee
    ecart: Decimal | None
    """`valeur_produit - valeur_demandee` sur les numériques, `None` ailleurs. Signé :
    le sens du dépassement est une information, et l'absolu la détruirait."""

    poids: Decimal | None
    sous_score: Decimal | None
    retrograde: bool
    """Le critère a été posé en `souhait` sur un filtre dur gradué, et le moteur l'a
    traité en score. Toute rétrogradation appliquée entre dans la trace : elle ne
    contourne jamais le critère d'acceptation nº6 — un critère posé comme bloquant
    produit un zéro résultat qui se dit et se propose, il ne s'assouplit pas seul."""


@dataclass(frozen=True, slots=True)
class TraceProduit:
    """L'explication complète d'un produit retenu, et sa place dans le classement."""

    produit_id: str
    score: Decimal
    criteres_evalues: int
    criteres_indisponibles: int
    """Le garde-fou de l'arbitrage F, exposé plutôt que caché : un produit à données
    manquantes a mécaniquement moins d'occasions de perdre des points. À score égal,
    c'est le nombre de critères réellement évalués qui départage."""

    rang: int
    rang_sans_le_prix: int
    """Rang qu'aurait ce produit si le sous-score de prix ne comptait pas. Le prix
    intervient déjà deux fois — le budget borne, le score ordonne — c'est volontaire,
    donc ça s'écrit."""

    lignes: tuple[LigneTrace, ...]

    @property
    def positions_gagnees_par_le_prix(self) -> int:
        """Positif si le prix a fait remonter le produit, négatif s'il l'a fait
        descendre, nul si le prix n'a rien changé à sa place."""
        return self.rang_sans_le_prix - self.rang
