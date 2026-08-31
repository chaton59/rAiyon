"""Ce que la boucle rend : des événements typés, jamais du texte brut.

### Pourquoi des événements dès l'étape 8 (arbitrage 1)

§3.12 décrit une API qui émet `criteria_updated`, `catalog_probe`, `products_found`,
`text_delta` — et une interface qui affiche « voici ce que j'ai compris de ton besoin ».
Ces événements sont donc un besoin de l'étape 10, pas une abstraction spéculative.

*Alternative écartée — des retours simples maintenant, les événements à l'étape 10.* Une
abstraction de moins à porter pendant deux étapes ; écartée parce que l'étape 10
réécrirait alors la boucle au lieu d'en remplacer le producteur, ce que §6 dit d'éviter.
**L'étape 10 doit pouvoir remplacer `messages.create()` par `messages.stream()` sans que
le consommateur bouge.**

C'est cette phrase qui a tranché la forme de `Texte` et de `QuestionPosee` — voir plus
bas, c'est le seul point de conception non trivial du module.

### Aucun événement ne porte l'`EtatSession`

Même règle que `en_tool_result()`, et pour la même raison : ces objets seront sérialisés
vers le client à l'étape 10. Chaque événement déclare donc ses champs explicitement,
plutôt que d'emballer le `ResultatOutil` dont il vient. `ProduitsTrouves` fait exception
et porte le `ResultatMatching` entier — mais c'est une exception apparente : cette
dataclass-là ne contient **structurellement** pas d'état, elle sort du moteur qui n'en a
jamais entendu parler.

### Un refus d'outil n'est pas un événement

Sept types, et aucun ne dit « l'outil a refusé ». Un refus fait partie du dialogue avec le
modèle (`erreurs.py`) : il part dans un `tool_result` en erreur, le modèle corrige et
rappelle. L'exposer au client montrerait la mécanique interne pour une situation dont il
n'a rien à faire. Il reste visible en log `INFO` et sous `--trace`.
"""

from dataclasses import dataclass
from decimal import Decimal

from raiyon.catalogue.schemas import Categorie
from raiyon.matching.criteres import Critere, Optimisation
from raiyon.matching.depot import BornesPrix
from raiyon.matching.moteur import ResultatMatching
from raiyon.matching.sondage import ChampDiscriminant, Distribution
from raiyon.tools.etat import MouvementRefuse
from raiyon.tools.outils import BesoinDeBudget


@dataclass(frozen=True, slots=True)
class Texte:
    """Un bloc de texte du modèle, tel qu'il l'a écrit.

    ⚠️ **Il est émis dès qu'il est lu, sans savoir ce qui suit dans le message.** C'est ce
    qui rend le streaming de l'étape 10 substituable : en streaming, les deltas de texte
    arrivent *avant* que l'on sache si un `tool_use` viendra derrière. Un événement qui
    aurait besoin de connaître la suite du message pour être construit — par exemple un
    `Texte` qui saurait qu'il est le préambule d'une question — obligerait à bufferiser,
    donc à annuler l'intérêt du streaming.
    """

    texte: str


@dataclass(frozen=True, slots=True)
class CriteresMisAJour:
    """Le panneau « voici ce que j'ai compris » de §3.12, à la source.

    `mouvements_refuses` en fait partie : c'est ce qui permet d'afficher « je garde
    144 Hz » plutôt que de laisser le client croire qu'il a été entendu.
    """

    categorie: Categorie
    criteres: tuple[Critere, ...]
    budget_usd: Decimal | None
    optimisation: Optimisation
    mouvements_refuses: tuple[MouvementRefuse, ...]


@dataclass(frozen=True, slots=True)
class Sondage:
    """Des agrégats, et structurellement aucun produit — comme l'outil dont il vient."""

    categorie: Categorie
    dans_le_budget: int
    dans_la_zone_de_tolerance: int
    fourchette_prix: BornesPrix | None
    champs: tuple[Distribution, ...]


@dataclass(frozen=True, slots=True)
class QuestionSuggeree:
    """Le champ de plus fort gain d'information. **Une suggestion, pas un ordre** (§3.8)."""

    categorie: Categorie
    candidats: int
    budget: BesoinDeBudget | None
    champ: ChampDiscriminant | None


@dataclass(frozen=True, slots=True)
class ProduitsTrouves:
    """La seule sortie du projet qui porte des produits, et elle porte aussi la trace.

    Le `ResultatMatching` est emballé tel quel : il sépare `produits` et
    `au_dessus_du_budget`, ce que §3.10 exige, et le réduire ici rouvrirait la possibilité
    de les confondre en aval.
    """

    resultat: ResultatMatching


@dataclass(frozen=True, slots=True)
class QuestionPosee:
    """`ask_clarification` a été appelé : **le tour est clos**.

    Il ne porte pas le préambule. Ce qui part au client est la suite d'événements —
    les `Texte` du message, puis cette question — et non un champ qui les recopierait.
    Deux raisons, et la première est décisive :

    1. le préambule n'est pas connu au moment où le texte est lu, en streaming comme
       ici ; le porter obligerait à retenir le texte jusqu'à la fin du message ;
    2. un préambule à la fois émis en `Texte` et recopié ici serait affiché deux fois par
       un consommateur qui traite les deux — la question posée deux fois est exactement le
       défaut que l'étape 7 a corrigé en rendant `ask_clarification` terminal.
    """

    question: str
    champ_vise: str | None


@dataclass(frozen=True, slots=True)
class Repli:
    """`max_iterations` atteint : le tour est clos par une phrase écrite en Python.

    *Alternative écartée — un dernier appel sans outils pour forcer une réponse texte.*
    Plus élégante, et c'est ce que l'étape 9 rendra sûr. Écartée ici : après huit
    itérations le modèle a précisément tourné en rond, et **rien ne valide encore sa
    sortie** — ce serait le texte le moins fiable de toute la conversation qu'on
    enverrait au client.
    """

    message: str
    iterations: int
    outils_appeles: tuple[str, ...]


Evenement = (
    CriteresMisAJour | Sondage | QuestionSuggeree | ProduitsTrouves | QuestionPosee | Texte | Repli
)
