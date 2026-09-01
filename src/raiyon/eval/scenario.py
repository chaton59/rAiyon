"""Les dix scénarios : leurs tours client, leurs attentes, leur réponse de référence.

**Pur.** Aucun appel, aucune base — juste des données. C'est ce qui permet de relire les
scénarios, et surtout les phrases qui justifient les attendus, sans rien démarrer.

---

### Les tours sont des **énoncés de besoin**, pas des réponses (arbitrage G)

Un client scripté ne réagit pas : le message du tour 3 est écrit d'avance et peut tomber
à côté de ce que l'assistant vient de demander. Chaque tour est donc écrit pour **se
suffire** — « en fait 180 Hz me suffisent largement » plutôt que « oui, IPS » — de sorte
qu'il reste sensé quelle que soit la question posée.

Le réalisme conversationnel est le rôle du **client simulé** (`client_simule.py`), pas
des scénarios déterministes. Les deux mesurent des choses différentes, et confondre les
deux donne des scénarios fragiles qui cassent au premier changement de prompt.

### La réponse de référence est **choisie à la main**, et justifiée (arbitrage F)

Le critère nº4 — « le produit attendu est dans le top 3 » — a besoin d'un attendu. **Il ne
vient pas du moteur** : le déterminer en lançant le moteur reviendrait à tester le moteur
contre lui-même, et la métrique vaudrait 100 % par construction.

Chaque `Attendu` porte donc un identifiant **choisi en lisant le catalogue**, et une
`justification` qui dit pourquoi c'est le bon produit pour ce besoin. Cette phrase est une
donnée, pas un commentaire : **c'est elle qu'on relira le jour où la métrique chutera**, et
sans elle on ne saura pas si c'est le moteur qui a régressé ou l'attendu qui était mauvais.

⚠️ **Six prises sur seize portent un attendu.** Un scénario dont l'attendu n'était pas
justifiable n'en porte pas — la comparaison, par exemple, mesure une non-hallucination et
pas un classement. Le rapport dit sur combien de prises la métrique porte.

⚠️ **La qualité de l'attendu n'est vérifiée par rien**, et c'est au §7. Quatre des six
sont adossés à une **unicité** constatée dans le catalogue (un seul produit satisfait les
contraintes), ce qui est le plus solide qu'on puisse faire sans jury humain. Les deux
autres reposent sur une lecture argumentée, et ils sont donc plus fragiles.

### Trois prises sur trois scénarios (arbitrage D)

La température n'est pas fixée (étape 8, arbitrage 12) : **une cassette est un tirage, pas
une espérance.** Un tirage par scénario, sauf sur `budget_serre`, `besoin_flou` et
`zero_budget_trop_bas`, où trois prises donnent un ordre de grandeur de la dispersion des
métriques nº3 et nº4.

⚠️ **Trois prises ne sont pas un intervalle de confiance**, et ni le rapport ni ce module
ne prétendent le contraire.

### Une attente qui nomme un outil est suspecte par défaut

Règle écrite après coup, parce qu'elle a coûté deux faux échecs à la première exécution du
harnais (étape 12). Le §5 nommait `BesoinDeBudget` pour le scénario « budget absent » ;
l'attente a échoué sur deux scénarios où l'agent s'était pourtant très bien conduit — il
avait sondé le catalogue puis posé la question en texte, sans passer par
`suggest_next_question`. Ce que le prompt système **autorise explicitement**, puisque §3.8
dit que la question suggérée est une suggestion.

L'attente mesurait donc **quel outil l'agent avait choisi**, pas ce que le produit avait
fait. Avant d'écrire une attente, se demander : *est-ce que je décris un résultat, ou un
chemin ?* `AUCUNE_RECHERCHE_SANS_BUDGET` décrit un résultat ; `BESOIN_DE_BUDGET` décrit un
chemin, et il est désormais **publié sans seuil** au lieu d'être exigé.

Le corollaire vaut aussi pour les attentes qui décrivent une **dégradation** : le scénario
`question_de_domaine` n'exige pas de repli, bien qu'il en produise un. Exiger un repli
reviendrait à figer une défaillance en critère de conformité, et à faire échouer le jour où
le modèle apprend à répondre sans rien affirmer. Le repli se lit dans le taux publié.
"""

from dataclasses import dataclass, field

from raiyon.eval.metriques import Attente
from raiyon.matching.relachement import Motif


@dataclass(frozen=True, slots=True)
class Attendu:
    """Le produit de référence d'un scénario, et **pourquoi c'est celui-là**."""

    produit_id: str
    justification: str
    """La phrase qu'on relira le jour où la métrique nº4 chutera. Sans elle, on ne saura
    pas si le moteur a régressé ou si l'attendu était mauvais."""


@dataclass(frozen=True, slots=True)
class Scenario:
    """Un nom, des tours, des attentes binaires, et parfois un attendu."""

    nom: str
    intention: str
    """Ce que le scénario cherche à mettre en défaut. Une phrase, lisible au rapport."""

    tours: tuple[str, ...]
    prises: int = 1
    attendu: Attendu | None = None
    attentes: frozenset[Attente] = field(default_factory=frozenset)
    diagnostic_attendu: Motif | None = None

    def fichier(self, prise: int) -> str:
        """Le nom de fichier d'une prise. Une prise, une cassette, un fichier lisible."""
        return f"{self.nom}.{prise}.json"


# --------------------------------------------------------------------------- #
# Les dix scénarios — les huit du §5 étape 12, plus deux qui visent des invariants
# --------------------------------------------------------------------------- #

SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        nom="budget_serre",
        intention="le bon produit existe, mais juste sous la limite",
        prises=3,
        tours=(
            "Bonjour. Je cherche un écran de 27 pouces au minimum, au moins 144 Hz, "
            "et je ne peux pas dépasser 145 dollars.",
            "Pourquoi celui-là plutôt qu'un autre ?",
        ),
        attentes=frozenset({Attente.PRODUITS_CITES}),
        attendu=Attendu(
            produit_id="monitor-ba17c6131b",
            justification=(
                "Choisi en lisant le catalogue : c'est le **seul** écran de 27 pouces ou "
                "plus à 144 Hz ou davantage dont le prix est sous 145 $ — l'ASRock "
                "Phantom Gaming PG27FRS1A, 142,99 $, 180 Hz, 27 pouces. Les quatre "
                "autres écrans à 144 Hz sous ce prix font 23,6 à 24,5 pouces. "
                "L'attendu est donc adossé à une unicité, pas à un jugement de valeur : "
                "s'il sort du top 3, c'est que le filtre dur sur la taille ou sur le "
                "budget a cessé de fonctionner."
            ),
        ),
    ),
    Scenario(
        nom="budget_absent",
        intention="l'agent doit demander le budget avant de chercher",
        tours=(
            "Je cherche un écran pour jouer, 27 pouces au minimum, 144 Hz au moins.",
            "Mon plafond est de 145 dollars.",
        ),
        attentes=frozenset({Attente.AUCUNE_RECHERCHE_SANS_BUDGET, Attente.PRODUITS_CITES}),
        attendu=Attendu(
            produit_id="monitor-ba17c6131b",
            justification=(
                "Même unicité que `budget_serre`, une fois le plafond de 145 $ donné au "
                "second tour : un seul écran de 27 pouces à 144 Hz ou plus tient sous ce "
                "prix. Ce scénario mesure en plus que la contrainte posée **au second "
                "tour** est bien celle qui a servi à chercher."
            ),
        ),
    ),
    Scenario(
        nom="besoin_flou",
        intention="délai avant première valeur sur un besoin qui ne dit presque rien",
        prises=3,
        tours=(
            "Bonjour, je voudrais un bon écran.",
            "C'est surtout pour jouer, et j'ai environ 250 dollars.",
            "Je suis plutôt sur du 27 pouces, et il me faut au moins 144 Hz.",
        ),
        attentes=frozenset({Attente.PRODUITS_CITES}),
    ),
    Scenario(
        nom="sur_specifie",
        intention="besoin sur-spécifié sans solution — diagnostic `critere_trop_strict`",
        tours=(
            "Il me faut un écran de 27 pouces au minimum, en 500 Hz, dalle IPS, "
            "et moins de 400 dollars.",
            "Le 500 Hz est vraiment ce qui compte pour moi.",
        ),
        attentes=frozenset({Attente.ZERO_RESULTAT}),
        diagnostic_attendu=Motif.CRITERE_TROP_STRICT,
    ),
    Scenario(
        nom="changement_davis",
        intention="un critère desserré en cours de route, jeton de parole consommé",
        tours=(
            "Un écran de 27 pouces au minimum, 240 Hz au moins, 200 dollars maximum.",
            "En fait 180 Hz me suffisent largement.",
        ),
        attentes=frozenset({Attente.ZERO_RESULTAT, Attente.PRODUITS_CITES}),
        attendu=Attendu(
            produit_id="monitor-ba17c6131b",
            justification=(
                "Après le desserrage à 180 Hz, le catalogue n'offre que deux écrans de "
                "27 pouces à 180 Hz ou plus sous 200 $ : l'ASRock à 142,99 $ et le MSI "
                "MAG 274CQF à 189,99 $, tous deux à 180 Hz exactement. À fréquence, "
                "taille et dalle équivalentes, le moins cher est le bon conseil. "
                "⚠️ **Attendu faible** : les deux candidats tiennent dans un top 3, la "
                "métrique passerait donc aussi si le classement les inversait. Ce que ce "
                "scénario mesure vraiment est ailleurs — que le desserrage a bien été "
                "appliqué, ce que l'attente `produits_cites` constate."
            ),
        ),
    ),
    Scenario(
        nom="comparaison",
        intention="comparer deux propositions sans réinventer les produits",
        tours=(
            "Un écran de 27 pouces au minimum, 144 Hz au moins, 250 dollars maximum, "
            "et plutôt une dalle IPS.",
            "Entre les deux premiers, lequel pour du jeu compétitif ? "
            "Redonnez-moi leurs prix exacts.",
        ),
        attentes=frozenset({Attente.PRODUITS_CITES}),
        attendu=Attendu(
            produit_id="monitor-9b319219eb",
            justification=(
                "Sur les écrans de 27 pouces à dalle IPS sous 250 $, l'Asus TUF Gaming "
                "VG279QM1A (229,00 $) est celui qui monte le plus haut en fréquence — "
                "280 Hz, contre 240 Hz pour le LG 27GP750-B et 170 Hz pour le MSI Optix "
                "G274. Pour un besoin de jeu où la dalle IPS est demandée, c'est le "
                "meilleur conseil que la lecture du catalogue donne. "
                "⚠️ **Attendu argumenté, pas unique** : il repose sur l'idée que 51 Hz "
                "de plus valent 2 dollars, ce qu'aucune mesure ne prouve. C'est le plus "
                "fragile des six, et c'est écrit ici plutôt que découvert plus tard."
            ),
        ),
    ),
    Scenario(
        nom="hors_catalogue",
        intention="catégorie absente du catalogue — dire qu'on ne sait pas faire",
        tours=(
            "Bonjour, je cherche une perceuse sans fil, budget 150 dollars.",
            "Vraiment rien ? C'est pour percer du béton.",
        ),
        attentes=frozenset({Attente.AUCUN_PRODUIT_CITE}),
    ),
    Scenario(
        nom="zero_budget_trop_bas",
        intention="zéro résultat par budget — diagnostic `budget_trop_bas`",
        prises=3,
        tours=(
            "Un écran de 27 pouces au minimum, 144 Hz au moins, et 130 dollars maximum.",
            "130 dollars, c'est mon plafond. Qu'est-ce que ça change ?",
        ),
        attentes=frozenset({Attente.ZERO_RESULTAT}),
        diagnostic_attendu=Motif.BUDGET_TROP_BAS,
    ),
    # ----------------------------------------------------------------------- #
    # Les deux qui visent des invariants que seuls des tests unitaires touchent
    # ----------------------------------------------------------------------- #
    Scenario(
        nom="desserrage_refuse",
        intention="trois desserrages en un tour — un seul passe, et l'agent doit le dire",
        tours=(
            "Un écran de 27 pouces au minimum, 240 Hz au moins, 200 dollars maximum.",
            "Bon, on assouplit : 144 Hz suffira, 24 pouces c'est bon aussi, "
            "et je peux monter à 300 dollars.",
        ),
        attentes=frozenset({Attente.ZERO_RESULTAT, Attente.MOUVEMENT_REFUSE, Attente.CRITERE_TENU}),
    ),
    Scenario(
        nom="question_de_domaine",
        intention=(
            "le client demande une explication technique que le catalogue ne porte pas — "
            "d'abord qualitative, puis chiffrée"
        ),
        prises=3,
        tours=(
            "Un écran de 27 pouces au minimum, 144 Hz au moins, 250 dollars maximum.",
            "C'est quoi la différence entre une dalle IPS et une dalle VA, au juste ?",
            "Et en chiffres, ça donne quoi ? Le contraste d'une dalle VA, "
            "c'est combien exactement ?",
        ),
        attentes=frozenset({Attente.PRODUITS_CITES, Attente.AUCUNE_RECHERCHE_SANS_BUDGET}),
    ),
    Scenario(
        nom="categorie_efface_budget",
        intention="changer de catégorie efface le budget — l'agent doit le redemander",
        tours=(
            "Un écran de 27 pouces au minimum, 144 Hz au moins, 250 dollars maximum.",
            "En fait je vais commencer par le processeur.",
        ),
        attentes=frozenset({Attente.BUDGET_EFFACE, Attente.AUCUNE_RECHERCHE_SANS_BUDGET}),
    ),
)

PAR_NOM: dict[str, Scenario] = {scenario.nom: scenario for scenario in SCENARIOS}


class ScenarioInconnu(Exception):
    """Le nom passé à `make eval-enregistrer` ne correspond à aucun scénario."""


def par_nom(nom: str) -> Scenario:
    """Un scénario par son nom, ou une erreur qui liste les noms valides."""
    if nom not in PAR_NOM:
        raise ScenarioInconnu(
            f"scénario {nom!r} inconnu. Les onze scénarios sont : "
            + ", ".join(sorted(PAR_NOM))
            + "."
        )
    return PAR_NOM[nom]


def prises_attendues() -> int:
    """Le nombre de cassettes que le dépôt doit porter. Une prise, une cassette."""
    return sum(scenario.prises for scenario in SCENARIOS)
