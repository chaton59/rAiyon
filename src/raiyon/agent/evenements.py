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

Huit types, et aucun ne dit « l'outil a refusé ». Un refus fait partie du dialogue avec le
modèle (`erreurs.py`) : il part dans un `tool_result` en erreur, le modèle corrige et
rappelle. L'exposer au client montrerait la mécanique interne pour une situation dont il
n'a rien à faire. Il reste visible en log `INFO` et sous `--trace`.

⚠️ **`TexteRejete` en est l'exception apparente, et elle est assumée** (étape 9). Comme un
refus d'outil, il décrit une mécanique interne et n'est affiché que sous `--trace`. Comme
aucun refus d'outil, il porte une **métrique de critère d'acceptation** : le taux de
messages refusés par le validateur est ce que l'étape 12 doit publier, et le compter
depuis les logs plutôt que depuis le flux d'événements reviendrait à mesurer le produit
par son journal de débogage.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from raiyon.catalogue.schemas import Categorie
from raiyon.matching.criteres import Critere, Optimisation
from raiyon.matching.depot import BornesPrix
from raiyon.matching.moteur import ResultatMatching
from raiyon.matching.sondage import ChampDiscriminant, Distribution
from raiyon.tools.etat import MouvementRefuse
from raiyon.tools.outils import BesoinDeBudget
from raiyon.validateur.validateur import Grief


@dataclass(frozen=True, slots=True)
class Texte:
    """Le texte d'un message assistant, **entier, et déjà validé** (étape 9, arbitrage A).

    ⚠️ **Cette docstring disait le contraire à l'étape 8, et l'arbitrage a été renversé.**
    Le texte était alors émis dès qu'il était lu, sans savoir ce qui suivait dans le
    message : c'est ce qui rendait le streaming de l'étape 10 substituable, et c'est ce
    qui a tranché la forme de cet événement.

    **Valider après génération et streamer sont incompatibles** : on ne rattrape pas une
    phrase déjà affichée. §3.11 gagne contre §3.12. Le texte d'un message est donc
    concaténé, relu par `raiyon.validateur`, puis émis d'un bloc.

    Conséquence à ne pas taire : à l'étape 10, `Texte` reste **un** événement et non une
    suite de deltas. La promesse de l'étape 8 — « remplacer le producteur sans que le
    consommateur bouge » — reste vraie pour tous les autres événements et **devient
    fausse pour celui-là**. Les événements d'outils, eux, continuent d'arriver au fil de
    l'eau : le panneau de §3.12 vit pendant l'attente, seule la prose arrive d'un bloc.
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
    le `Texte` du message, puis cette question — et non un champ qui les recopierait.

    ⚠️ **La première des deux raisons de l'étape 8 n'est plus vraie**, et il faut le dire
    plutôt que de laisser la docstring s'appuyer sur un fait renversé : « le préambule
    n'est pas connu au moment où le texte est lu » supposait un texte émis au fil de
    l'eau. Depuis l'arbitrage A de l'étape 9, le texte est bufferisé et donc connu en
    entier avant d'être émis.

    La seconde raison suffit à elle seule et reste valable : un préambule à la fois émis
    en `Texte` et recopié ici serait affiché deux fois par un consommateur qui traite les
    deux — la question posée deux fois est exactement le défaut que l'étape 7 a corrigé
    en rendant `ask_clarification` terminal.
    """

    question: str
    champ_vise: str | None


class MotifDeRepli(StrEnum):
    """Pourquoi le tour a été clos par du texte écrit en Python. **Deux causes.**

    Les distinguer n'est pas du confort : l'étape 12 mesure un taux d'hallucination et
    un taux de bouclage, et un `Repli` sans motif l'empêcherait de les séparer. Ce sont
    aussi deux défauts différents — l'un se corrige dans le prompt, l'autre dans les
    outils.
    """

    MAX_ITERATIONS = "max_iterations"
    """Le modèle a tourné en rond jusqu'à la garde d'itérations (étape 8, arbitrage 8)."""

    VALIDATION = "validation"
    """Le texte a été refusé par le validateur, régénération comprise (étape 9)."""


@dataclass(frozen=True, slots=True)
class Repli:
    """Le tour est clos par une phrase écrite en Python, et `motif` dit laquelle.

    *Alternative écartée à l'étape 8 — un dernier appel sans outils pour forcer une
    réponse texte.* Elle était écartée parce que « rien ne valide encore la sortie » ;
    depuis l'étape 9 quelque chose la valide, et le repli sur template (§3.11 niveau 3)
    fait mieux que ce dernier appel : il ne coûte rien et son risque est nul.
    """

    message: str
    iterations: int
    outils_appeles: tuple[str, ...]
    motif: MotifDeRepli


@dataclass(frozen=True, slots=True)
class TexteRejete:
    """Le validateur a refusé un texte : une régénération va être demandée (étape 9).

    **Ce n'est pas du confort de trace.** Sans lui, `--trace` ne montrerait pas qu'une
    régénération a eu lieu, et l'étape 12 devrait deviner un taux qu'on peut compter :
    combien de messages sont refusés, sur quels codes de grief, et combien de fois la
    seconde tentative suffit.

    C'est le seul événement destiné au **développeur** et non au client — la console ne
    l'affiche que sous `--trace`, pour la même raison qu'un `OutilRefuse` n'est pas un
    événement : montrer la mécanique interne d'une situation dont le client n'a rien à
    faire. La différence est qu'un refus d'outil se compte dans les logs, alors qu'un
    texte rejeté est une **métrique de critère d'acceptation**.
    """

    griefs: tuple[Grief, ...]
    tentative: int
    """1 pour le premier refus. Au-delà de `max_regenerations`, c'est le repli."""


Evenement = (
    CriteresMisAJour
    | Sondage
    | QuestionSuggeree
    | ProduitsTrouves
    | QuestionPosee
    | Texte
    | TexteRejete
    | Repli
)
