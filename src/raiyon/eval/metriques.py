"""Une suite d'événements vers des mesures. **Pur, et il ne lit jamais la prose au motif.**

### Les métriques se calculent depuis les événements (arbitrage E)

`QuestionPosee` compte les questions, `ProduitsTrouves` porte les produits et le
diagnostic, `TexteRejete` porte l'origine et les codes, `Repli` porte son motif,
`CriteresMisAJour` porte les mouvements refusés.

**Aucune métrique ne relit la prose du modèle avec une expression régulière.** Ce serait un
second validateur, plus faible que le premier, et il finirait par diverger de lui.

⚠️ **Une seule chose lit la prose, et c'est le validateur lui-même** — `valider()`, les
mêmes cinq règles, contre le contexte réellement fourni. C'est l'exception qui confirme la
règle : on ne réécrit pas la lecture, on rappelle celle qui existe.

---

### Le piège central : les critères nº1 et nº2 sont garantis par construction

Depuis l'étape 9, le validateur refuse le texte fautif, régénère une fois, puis se replie
sur un template écrit en Python. **Le texte livré ne peut donc pas contenir
d'hallucination**, et mesurer zéro, c'est mesurer le mécanisme contre lui-même.

Ce n'est pas une raison de ne pas le mesurer — c'est une raison de mesurer **trois couches
et de les publier ensemble** :

**Ce qui est livré** — 0 grief, 0 violation budget. Une valeur non nulle signifie que le
validateur a un **trou**, pas que le modèle a menti : c'est là toute l'information.

**Ce que le modèle a tenté** — taux de rejet, par origine et par code. C'est ce qui
**bouge**, et c'est ce que l'étape 13 corrige dans le prompt.

**Ce qui a fini en repli** — taux de repli, par motif. Un repli est une réponse
**dégradée livrée au client** : un tour replié est une défaillance produit, critère nº1
vert ou pas.

`rapport.py` publie les trois, et écrit la phrase qui empêche de s'arrêter à la première.

### Deux observations lisent la prose, et l'arbitrage E tient quand même (étape 13)

`chiffres_des_tours_de_domaine` et `formes_markdown` sont les deux seules choses de ce
module qui regardent du texte sans passer par le validateur. Ce n'est pas un
assouplissement de l'arbitrage E, et la différence est nette :

* **elles ne décident rien.** Aucun seuil, aucun `conforme`, aucun code de sortie. Une
  prose de domaine pleine de chiffres ne fait pas échouer `make eval` — un test le
  constate, exprès, pour empêcher qu'on les repromeuve en attentes sans relire pourquoi ;
* **elles ne fondent aucun fait.** Un second validateur dirait « ce chiffre est faux » ;
  celles-ci disent « il y a *n* chiffres » et « il y a *n* backticks ». Ce qui tranche est
  l'appendice verbatim du rapport, relu par un humain ;
* **elles ne réécrivent pas d'extraction.** Le compte de chiffres réutilise
  `extraction.nombres`, c'est-à-dire le `NOMBRE` du validateur. Deux lectures de nombre
  dans un dépôt finissent par en dire deux choses, et un test vérifie qu'il n'en existe
  pas de seconde ici.

### Le contexte de validation est celui de **fin de session**, et l'erreur va dans le bon sens

Le contexte fourni est déjà cumulatif sur la session (étape 9, arbitrage B) : celui de fin
de session **contient** celui dont la boucle disposait au moment d'écrire. Il est donc plus
permissif, jamais plus sévère. Conséquence à écrire plutôt qu'à découvrir : cette mesure
peut **sous-estimer** un trou, elle ne peut pas en inventer un.

### Le critère nº2 est un code de grief, pas une seconde lecture

`ECART_NON_DIT` est exactement « un produit de la zone de tolérance cité sans son écart
au budget », et sa docstring dit « Critère d'acceptation nº2 ». Le séparer des cinq autres
codes suffit donc à séparer les deux critères, sans écrire une deuxième fois la règle qui
les distingue.
"""

import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from raiyon.agent.evenements import (
    CriteresMisAJour,
    Evenement,
    MotifDeRepli,
    ProduitsTrouves,
    QuestionPosee,
    QuestionSuggeree,
    Repli,
    Texte,
    TexteRejete,
)
from raiyon.matching.relachement import Motif
from raiyon.validateur.contexte import contexte_des_messages
from raiyon.validateur.extraction import nombres, phrases
from raiyon.validateur.regles import CodeGrief
from raiyon.validateur.validateur import Grief, OrigineRejet, valider

CODE_DU_CRITERE_2 = CodeGrief.ECART_NON_DIT
"""Le seul code qui porte le critère nº2. Les cinq autres portent le critère nº1."""

SEUIL_TOURS = 2
"""Critère nº3 : médiane des **tours client** avant la première valeur.

⚠️ **Le critère comptait des questions jusqu'au correctif de l'étape 12**, et le seuil de
§4 valait « ≤ 2 questions ». Il valait 0 sur les onze prises qui livrent une valeur : la
règle « donner avant de demander » fonctionne, l'agent n'interroge jamais avant de montrer
quelque chose — mais une métrique collée à son plancher ne détecte plus qu'une régression,
et §5 étape 13 demande de la **viser en priorité**.

§3.9 disait déjà quoi compter : *« le bon indicateur est le délai avant première valeur,
pas le compte de questions »*. On compte donc ce que le client vit — **combien de fois
ai-je dû parler avant d'obtenir quelque chose** — et le seuil reste à 2, mais il ne veut
plus dire la même chose : il dit maintenant « au deuxième message du client, il a vu des
produits ». Un agent qui interrogerait trois tours d'affilée avant de montrer quoi que ce
soit le ferait tomber, ce qui est exactement le mode d'échec de l'interrogatoire que §3.9
nomme. L'ancien seuil ne l'aurait pas vu : ces questions-là passent par du texte, pas par
`ask_clarification`."""

SEUIL_QUESTIONS = 2
"""L'ancien seuil du critère nº3, **conservé sans portée**.

`questions_avant_premiere_valeur` reste calculée et **publiée sans seuil** : elle ne mesure
plus le critère, elle mesure la règle de dialogue de la section 5 du prompt. Les deux
méritent d'être suivies, et l'étape 13 aura besoin de savoir laquelle a bougé."""

SEUIL_TOP3 = 0.80
"""Critère nº4 : part des scénarios à attendu dont le produit de référence est dans le
classement rendu."""

RESERVE_ITERATIONS = (
    "⚠️ **`Itérations` ne se compare pas d'une orchestration à l'autre.** Chez une machine "
    "à états,\nc'est une **constante** décidée par le graphe, pas un résultat : sa variance "
    "nulle est une\npropriété connue d'avance, et elle se lirait comme une stabilité gagnée "
    "si personne ne\nl'écrivait. Posée au jalon 0 de l'étape 15, **avant** la campagne — pas "
    "quand le chiffre sortira."
)
"""La réserve que `rapport.py` et `comparaison.py` publient à côté d'`iterations`.

Écrite **une fois** et à côté de la mesure qu'elle qualifie, plutôt qu'en deux exemplaires
dans les deux modules de rendu : une réserve qui existe en double finit par n'être corrigée
qu'à un seul endroit — le dépôt a déjà payé ce motif deux fois (`erreurs.py`, puis
`SYSTEME_PAR_DEFAUT` contre `Settings.prompt_systeme`)."""


class Attente(StrEnum):
    """Une attente binaire d'un scénario, vérifiable **sur les seuls événements**.

    Chacune est un fait que le code a produit, jamais une lecture de ce que le modèle a
    écrit. C'est la frontière de l'arbitrage E, et elle a un coût qu'il faut nommer :
    « l'agent a **dit** au client qu'il refusait le desserrage » n'est pas ici, parce
    qu'aucune mesure honnête ne sait le constater. `CRITERE_TENU` constate que le critère
    n'a pas bougé — pas que la phrase le dit.
    """

    BESOIN_DE_BUDGET = "besoin_de_budget"
    """`suggest_next_question` a signalé que le budget manquait (`QuestionSuggeree.budget`).

    ⚠️ **Ce n'est pas une exigence de produit, et la première exécution du harnais l'a
    montré.** Le §5 étape 12 nommait `BesoinDeBudget` pour le scénario « budget absent » ;
    écrite comme attente, cette ligne a échoué sur deux scénarios où l'agent s'est pourtant
    bien conduit — il avait sondé le catalogue puis posé la question en texte, sans passer
    par `suggest_next_question`. L'attente mesurait **quel outil l'agent avait choisi**, pas
    ce que le produit avait fait.

    Elle reste dans l'énumération parce que le fait est vrai et intéressant — le rapport le
    **publie sans seuil** —, mais l'exigence est `AUCUNE_RECHERCHE_SANS_BUDGET`."""

    AUCUNE_RECHERCHE_SANS_BUDGET = "aucune_recherche_sans_budget"
    """Aucun `ProduitsTrouves` n'est survenu alors que le budget en vigueur valait `None`.

    C'est l'invariant que « demander le budget avant de chercher » désigne réellement, et
    il couvre les deux scénarios : celui où le budget n'a jamais été donné, et celui où un
    changement de catégorie l'a effacé (étape 7, arbitrage D). Le second est le plus
    intéressant — **reporter le budget en silence** sur la nouvelle catégorie serait
    exactement la seconde source de vérité que §3.10 ferme."""

    QUESTION_POSEE = "question_posee"
    """`ask_clarification` a clos un tour au moins une fois."""

    PRODUITS_CITES = "produits_cites"
    """Au moins un `ProduitsTrouves` non vide — le client a vu des produits."""

    AUCUN_PRODUIT_CITE = "aucun_produit_cite"
    """Aucun. C'est l'attente de la catégorie hors catalogue : ne rien inventer."""

    ZERO_RESULTAT = "zero_resultat"
    """Au moins une recherche a rendu zéro produit, donc un diagnostic."""

    MOUVEMENT_REFUSE = "mouvement_refuse"
    """Le jeton de parole a refusé au moins un mouvement (§3.17)."""

    CRITERE_TENU = "critere_tenu"
    """Aucun critère refusé n'a fini par passer : le dernier état enregistré porte encore
    la valeur d'avant le desserrage refusé.

    ⚠️ **Ce n'est pas « l'agent l'a dit au client ».** Cette attente-là n'existe pas, et
    son absence est écrite au §7."""

    BUDGET_EFFACE = "budget_efface"
    """Le budget est passé à `None` alors qu'il était posé — le changement de catégorie
    de l'étape 7, arbitrage D."""


@dataclass(frozen=True, slots=True)
class TourJoue:
    """Un tour client joué : ce que le client a dit, ce que la boucle a rendu."""

    message_client: str
    evenements: tuple[Evenement, ...]
    iterations: int


@dataclass(frozen=True, slots=True)
class PriseJouee:
    """Une prise d'un scénario, jouée de bout en bout.

    `messages` est la conversation **persistée** — c'est elle qui porte les `tool_result`,
    donc le contexte fourni. Les événements ne suffiraient pas : ils ne portent
    délibérément aucun état (voir `evenements.py`).
    """

    scenario: str
    prise: int
    tours: tuple[TourJoue, ...]
    messages: tuple[Mapping[str, Any], ...]
    attendu: str | None = None
    """L'identifiant du produit de référence, **choisi à la main** (arbitrage F). `None`
    quand le scénario n'en porte pas — il sort alors du calcul du critère nº4."""

    attentes: frozenset[Attente] = frozenset()
    diagnostic_attendu: Motif | None = None

    tours_de_domaine: frozenset[int] = frozenset()
    """Les rangs de tour que le scénario **déclare** de domaine. Recopié tel quel depuis
    `Scenario` : ce module ne sait pas ce qu'est une question de domaine, il sait publier
    ce qu'on lui a désigné."""

    @property
    def evenements(self) -> tuple[Evenement, ...]:
        """Tous les événements de la prise, dans l'ordre, tours confondus."""
        return tuple(evenement for tour in self.tours for evenement in tour.evenements)


@dataclass(frozen=True, slots=True)
class Rejet:
    """Un texte refusé : d'où il venait, et sur quel code."""

    origine: OrigineRejet
    code: CodeGrief


@dataclass(frozen=True, slots=True)
class Refus:
    """Un grief, **avec la phrase qui l'a levé** (étape 13, jalon 0, point A).

    `Rejet` compte ; `Refus` montre. Les deux existent parce qu'ils répondent à deux
    questions différentes, et que l'étape 12 n'avait que la première : *combien* de
    textes ont été refusés, et *sur quelle forme de phrase*.

    Un taux de rejet qui descend de 11 à 5 ne dit pas ce qui a disparu. Attribuer les
    onze griefs de l'étape 12 à trois opérations — arrondir une borne, dériver un écart
    entre deux prix fournis, chiffrer un assouplissement — a demandé de rouvrir dix-neuf
    cassettes et de lire chaque texte refusé contre sa réécriture. Le harnais avait
    l'information et ne la portait pas jusqu'au rapport.

    Il est **recalculé au rejeu**, comme tout le reste (arbitrage A) : il est donc
    disponible rétroactivement sur les cassettes déjà enregistrées, sans en régénérer
    une seule.
    """

    scenario: str
    prise: int
    tour: int
    """Le rang 1-indexé du tour client. Cinq griefs dans un même tour et cinq griefs
    répartis sur cinq tours ne décrivent pas le même défaut."""

    origine: OrigineRejet
    code: CodeGrief
    extrait: str
    """Ce que la règle a pointé — « 47 $ », un identifiant, une phrase entière selon la
    règle. C'est le champ `Grief.extrait`, tel quel."""

    phrase: str
    """La phrase du texte refusé qui **contient** l'extrait, ou le texte entier si aucune
    ne le contient.

    Le découpage est celui d'`extraction.phrases` — le seul endroit du dépôt qui décide
    où une phrase s'arrête. Sans ce champ, l'appendice publierait « 47 $ » sans « en QHD
    pour 47 $ de plus », c'est-à-dire le chiffre sans l'opération qui l'a produit, qui est
    la seule chose qu'un changement de prompt puisse viser."""


@dataclass(frozen=True, slots=True)
class MesuresDunePrise:
    """Ce qu'une prise a produit. Tout est un compte, rien n'est une opinion."""

    scenario: str
    prise: int
    tours: int

    griefs_livres: tuple[Grief, ...]
    """Critère nº1. Les codes autres qu'`ECART_NON_DIT`, dans la prose **livrée**."""

    violations_budget: tuple[Grief, ...]
    """Critère nº2. Les `ECART_NON_DIT` de la prose livrée."""

    tours_avant_valeur: int | None
    """**Critère nº3** — le rang du tour client où la première valeur est arrivée.

    1 signifie « le client a parlé une fois, il a vu des produits ». `None` si aucune
    valeur n'a jamais été livrée : la prise n'entre alors pas dans la médiane, parce que
    « zéro tour avant une valeur qui n'est jamais venue » serait le meilleur score possible
    pour le pire comportement possible."""

    questions_avant_valeur: int | None
    """Publiée sans seuil depuis le correctif de l'étape 12. Elle mesure la règle « donner
    avant de demander », pas le délai avant première valeur — voir `SEUIL_QUESTIONS`."""

    attendu_en_top3: bool | None
    """Critère nº4. `None` si le scénario ne porte pas d'attendu (arbitrage F)."""

    zero_resultats_traites: int
    zero_resultats: int
    """Critère nº6. Un zéro résultat est **traité** s'il porte un diagnostic et une issue."""

    rejets: tuple[Rejet, ...]
    refus: tuple[Refus, ...]
    """Les mêmes rejets, **avec leur phrase** — l'appendice du rapport (jalon 0, point A).

    Il y a exactement un `Refus` par `Rejet` : les deux sortent du même parcours des
    `TexteRejete`. Ils ne sont pas fusionnés parce qu'`agreger()` compte les uns et que
    le rapport recopie les autres, et qu'un tableau de comptes n'a rien à faire d'une
    phrase de deux cents caractères."""

    replis: tuple[MotifDeRepli, ...]
    iterations: tuple[int, ...]
    """Les itérations de boucle de chaque tour. **Publiée sans seuil, et voir
    `RESERVE_ITERATIONS`** : c'est une propriété de l'orchestration autant qu'un résultat,
    et elle cesse d'être comparable dès qu'on change d'orchestration."""

    prose_de_domaine: tuple[tuple[int, tuple[str, ...]], ...]
    """La prose livrée sur les tours que le scénario déclare de domaine, par rang de tour.

    **C'est la preuve, et le compteur n'est que son résumé** (jalon 0, point D). Le rapport
    la recopie entière : la cible 2 se compare en lisant, sur un artefact committé que
    n'importe qui peut relire, pas en croyant un compteur."""

    chiffres_de_domaine: int
    """Le compte de valeurs chiffrées de cette prose. **Publié sans seuil.**"""

    formes_markdown: tuple[tuple[str, int], ...]
    """Les formes que le front ne rend pas, dans la prose livrée. **Publié sans seuil.**"""

    faits: frozenset[Attente]
    """Tout ce que les événements constatent, **que le scénario l'ait demandé ou non**.
    C'est ce qui permet de publier une observation sans en faire une exigence."""

    attentes_manquees: frozenset[Attente]
    diagnostic_attendu: Motif | None
    diagnostics_vus: tuple[Motif, ...]

    @property
    def diagnostic_tenu(self) -> bool | None:
        """`None` quand le scénario n'attend aucun diagnostic particulier."""
        if self.diagnostic_attendu is None:
            return None
        return self.diagnostic_attendu in self.diagnostics_vus

    @property
    def conforme(self) -> bool:
        """Toutes les attentes binaires du scénario, diagnostic compris."""
        return not self.attentes_manquees and self.diagnostic_tenu is not False


@dataclass(frozen=True, slots=True)
class Mesures:
    """L'agrégat publié. Chaque champ correspond à une ligne du rapport."""

    prises: tuple[MesuresDunePrise, ...]

    # ---- Critères bloquants -------------------------------------------------
    griefs_livres: int
    violations_budget: int
    zero_resultats: int
    zero_resultats_traites: int

    # ---- Critères de qualité ------------------------------------------------
    tours_par_prise: tuple[int, ...]
    """Critère nº3. Un élément par prise **qui a livré une valeur**."""

    questions_par_prise: tuple[int, ...]
    """Publiée sans seuil. Même population que `tours_par_prise`."""

    prises_sans_valeur: int
    prises_avec_attendu: int
    attendus_en_top3: int

    # ---- Publiés sans seuil -------------------------------------------------
    rejets: tuple[Rejet, ...]
    refus: tuple[Refus, ...]
    """Les phrases refusées, triées, telles que l'appendice les publie."""

    replis: tuple[MotifDeRepli, ...]
    iterations: tuple[int, ...]
    tours: int
    tours_replies: int
    attentes_manquees: tuple[tuple[str, int, Attente], ...]
    diagnostics_manques: tuple[tuple[str, int, Motif], ...]
    codes_declenches: frozenset[CodeGrief]
    """Les codes de grief qu'au moins un texte a levés sur cette exécution.

    ⚠️ **Une règle qui ne tire jamais est indistinguable d'une règle absente**, et l'étape
    12 a montré pourquoi cela compte : le critère nº1 ne détecte pas une règle manquante,
    seulement un trou dans la réaction à une règle qui existe. Ce qui détecte une règle
    manquante est l'effondrement du taux de rejet — encore faut-il savoir **sur quoi** ce
    taux portait. Voir `codes_jamais_declenches`."""

    prises_ou_loutil_a_signale_le_budget: int
    """Publié sans seuil : sur combien de prises `suggest_next_question` a-t-il signalé le
    budget manquant. Voir `Attente.BESOIN_DE_BUDGET` — c'est une observation sur la
    conduite du dialogue, pas une exigence."""

    tours_de_domaine: int
    """Combien de tours déclarés de domaine cette exécution a joués. Le dénominateur du
    compteur de chiffres : « 3 chiffres » ne veut rien dire sans « sur 12 tours »."""

    chiffres_de_domaine: int
    """Le compte total de valeurs chiffrées sur ces tours. **Observation sans seuil**, et
    aucune propriété de `Mesures` ne le lit — surtout pas `bloquants_tenus`."""

    formes_markdown: tuple[tuple[str, int], ...]
    """Les formes que le front ne rend pas, sommées sur toutes les prises. Mesuré sur v1
    **avant** que v3 y touche : sans le point de départ, la baisse ne se lit pas."""

    @property
    def mediane_des_tours(self) -> float | None:
        """Critère nº3."""
        if not self.tours_par_prise:
            return None
        return float(statistics.median(self.tours_par_prise))

    @property
    def mediane_des_questions(self) -> float | None:
        """Publiée sans seuil — voir `SEUIL_QUESTIONS`."""
        if not self.questions_par_prise:
            return None
        return float(statistics.median(self.questions_par_prise))

    @property
    def codes_jamais_declenches(self) -> tuple[CodeGrief, ...]:
        """Les règles qu'aucun texte n'a fait tirer, **dérivées de `CodeGrief`**.

        Jamais d'une liste écrite à la main : un sixième code ajouté demain n'y
        figurerait jamais, et la ligne du rapport mentirait par omission — exactement le
        défaut qu'elle existe pour signaler.

        Un code absent d'ici ne veut pas dire que la règle est cassée : `test_pieges.py`
        l'exerce à chaque `make check`. Il veut dire que **cette suite de scénarios** ne
        la sollicite pas, et donc que le taux de rejet ne dit rien d'elle.
        """
        return tuple(code for code in CodeGrief if code not in self.codes_declenches)

    @property
    def part_attendus_en_top3(self) -> float | None:
        if not self.prises_avec_attendu:
            return None
        return self.attendus_en_top3 / self.prises_avec_attendu

    @property
    def taux_de_repli(self) -> float:
        return len(self.replis) / self.tours if self.tours else 0.0

    @property
    def taux_de_rejet(self) -> float:
        return len(self.rejets) / self.tours if self.tours else 0.0

    @property
    def critere_1(self) -> bool:
        return self.griefs_livres == 0

    @property
    def critere_2(self) -> bool:
        return self.violations_budget == 0

    @property
    def critere_6(self) -> bool:
        """Binaire et bloquant : tout zéro résultat rencontré est traité."""
        return self.zero_resultats_traites == self.zero_resultats

    @property
    def critere_3(self) -> bool | None:
        """Tours client, depuis le correctif de l'étape 12 — voir `SEUIL_TOURS`."""
        mediane = self.mediane_des_tours
        return None if mediane is None else mediane <= SEUIL_TOURS

    @property
    def critere_4(self) -> bool | None:
        part = self.part_attendus_en_top3
        return None if part is None else part >= SEUIL_TOP3

    @property
    def bloquants_tenus(self) -> bool:
        """Ce qui décide du code de sortie de `make eval`."""
        return self.critere_1 and self.critere_2 and self.critere_6 and not self.attentes_manquees


# --------------------------------------------------------------------------- #
# Ce que le client a lu — et les deux observations qui s'y comptent
# --------------------------------------------------------------------------- #


def prose_livree(evenements: Sequence[Evenement]) -> tuple[str, ...]:
    """Ce que le client a **lu**, dans l'ordre, replis compris.

    Trois natures de prose partent au client et les trois sont ici : le `Texte` d'un
    message, la `question` d'`ask_clarification`, et le message d'un `Repli` — qui est
    écrit en Python mais que le client lit comme le reste.

    ⚠️ **Le texte d'un `TexteRejete` n'y est pas**, et c'est la distinction qui compte :
    il n'a jamais atteint le client. Il se lit dans l'appendice des refus, séparément.

    Elle vivait dans `executeur.py` jusqu'à l'étape 13, où deux observations du rapport
    ont eu besoin d'elle. `executeur.py` importe déjà ce module ; l'inverse aurait fait
    dépendre le calcul des mesures d'une `Session` SQLAlchemy, ce que l'isolation du
    paquet interdit.
    """
    lignes: list[str] = []
    for evenement in evenements:
        if isinstance(evenement, Texte):
            lignes.append(evenement.texte)
        elif isinstance(evenement, QuestionPosee):
            lignes.append(evenement.question)
        elif isinstance(evenement, Repli):
            lignes.append(evenement.message)
    return tuple(lignes)


FORMES_MARKDOWN: tuple[tuple[str, str], ...] = (
    ("backtick", "`"),
    ("puce", r"(?m)^[ \t]*[-*+][ \t]+"),
    ("liste numérotée", r"(?m)^[ \t]*\d+\.[ \t]+"),
    ("titre", r"(?m)^[ \t]*#{1,6}[ \t]+"),
)
"""Les formes de markdown que le front **n'interprète pas**, et leur motif.

`web/rendu.js` rend **deux formes et pas une de plus** : le gras `**…**` et les sauts de
ligne, en nœuds DOM construits un par un. Le reste s'affiche tel quel — les backticks
autour d'un identifiant sont visibles à l'écran, constaté en démonstration (§7).

Les quatre retenues sont celles qu'on **constate** dans les dix-neuf cassettes de l'étape
12 (44 backticks, 61 puces, 37 listes numérotées) plus les titres, qu'un modèle écrit dès
qu'on lui demande une structure. Ni italique, ni lien, ni tableau, ni citation : aucun
n'apparaît, et les inventer donnerait un compteur toujours nul qu'on cesserait de lire.

⚠️ **Le gras n'y est pas, et ce n'est pas un oubli** : il est rendu. Le compter ferait
descendre le compteur en demandant au modèle d'écrire moins bien.

⚠️ **Publié sans seuil**, et mesuré sur v1 **avant** que v3 y touche — sans quoi on ne
saurait pas de combien on est parti."""

_MOTIFS_MARKDOWN = tuple((nom, re.compile(motif)) for nom, motif in FORMES_MARKDOWN)


def formes_markdown(lignes: Sequence[str]) -> tuple[tuple[str, int], ...]:
    """Combien de fois chaque forme non rendue apparaît dans la prose livrée.

    Toutes les formes sont rendues, **y compris à zéro** : un compteur qui disparaît
    quand il tombe à zéro ne se distingue pas d'un compteur qu'on a cessé de calculer.
    """
    return tuple(
        (nom, sum(len(motif.findall(ligne)) for ligne in lignes)) for nom, motif in _MOTIFS_MARKDOWN
    )


def chiffres_de_la_prose(lignes: Sequence[str]) -> int:
    """Le nombre de valeurs chiffrées de la prose livrée. **Observation, jamais seuil.**

    Réutilise `extraction.nombres`, donc le `NOMBRE` du validateur : voir la docstring du
    module, et le test qui vérifie qu'il n'existe pas de seconde extraction de nombre ici.

    ⚠️ **Ce que ce compte vaut réellement** — un ratio écrit `3000:1` compte pour **deux**
    nombres et non pour un, et un « 27 pouces » repris d'un `tool_result` compte comme un
    chiffre inventé le compterait. C'est une mesure de la **forme** de la prose, pas un
    décompte de faits ; l'appendice verbatim est ce qui tranche.
    """
    return sum(len(nombres(ligne)) for ligne in lignes)


# --------------------------------------------------------------------------- #
# Le calcul, prise par prise
# --------------------------------------------------------------------------- #


def mesurer(prise: PriseJouee) -> MesuresDunePrise:
    """Toutes les mesures d'une prise, en une passe sur ses événements."""
    evenements = prise.evenements
    griefs = _griefs_livres(prise)
    diagnostics = _diagnostics(evenements)
    tenues = _attentes_tenues(evenements)
    domaine = _prose_de_domaine(prise)

    return MesuresDunePrise(
        scenario=prise.scenario,
        prise=prise.prise,
        tours=len(prise.tours),
        griefs_livres=tuple(g for g in griefs if g.code is not CODE_DU_CRITERE_2),
        violations_budget=tuple(g for g in griefs if g.code is CODE_DU_CRITERE_2),
        tours_avant_valeur=tours_avant_premiere_valeur(prise.tours),
        questions_avant_valeur=questions_avant_premiere_valeur(evenements),
        attendu_en_top3=_attendu_en_top3(evenements, prise.attendu),
        zero_resultats=sum(1 for e in evenements if _est_un_zero_resultat(e)),
        zero_resultats_traites=sum(1 for e in evenements if _est_un_zero_resultat_traite(e)),
        rejets=tuple(
            Rejet(e.origine, grief.code)
            for e in evenements
            if isinstance(e, TexteRejete)
            for grief in e.griefs
        ),
        refus=_refus(prise),
        replis=tuple(e.motif for e in evenements if isinstance(e, Repli)),
        iterations=tuple(tour.iterations for tour in prise.tours),
        prose_de_domaine=domaine,
        chiffres_de_domaine=sum(chiffres_de_la_prose(lignes) for _, lignes in domaine),
        formes_markdown=formes_markdown(prose_livree(evenements)),
        faits=tenues,
        attentes_manquees=prise.attentes - tenues,
        diagnostic_attendu=prise.diagnostic_attendu,
        diagnostics_vus=diagnostics,
    )


def tours_avant_premiere_valeur(tours: Sequence[TourJoue]) -> int | None:
    """**Critère nº3** — au bout de combien de messages du client la première valeur arrive.

    C'est le « délai avant première valeur » de §3.9 pris au mot : ce que le client vit,
    c'est le nombre de fois qu'il a dû parler, pas le nombre de fois qu'on lui a posé une
    question. Un agent qui explique longuement sans rien montrer coûte un tour ; un agent
    qui pose une question **et** montre trois produits n'en coûte aucun de plus.

    Rend le rang **1-indexé** du tour où le premier `ProduitsTrouves` non vide apparaît, ou
    `None` si aucune valeur n'est jamais venue.
    """
    for rang, tour in enumerate(tours, start=1):
        if any(
            isinstance(evenement, ProduitsTrouves) and evenement.resultat.produits
            for evenement in tour.evenements
        ):
            return rang
    return None


def questions_avant_premiere_valeur(evenements: Sequence[Evenement]) -> int | None:
    """Combien de fois `ask_clarification` a clos un tour avant la première valeur.

    ⚠️ **Ce n'est plus le critère nº3** (correctif de l'étape 12) : c'est la mesure de la
    règle « donner avant de demander » (section 5 du prompt, §3.9), publiée sans seuil.
    Elle vaut 0 partout sur le jeu de scénarios actuel, et ce zéro est une **bonne**
    nouvelle mal lisible — d'où le déplacement du critère sur les tours client.

    Rend `None` si aucune valeur n'est jamais venue, pour la même raison.
    """
    questions = 0
    for evenement in evenements:
        if isinstance(evenement, ProduitsTrouves) and evenement.resultat.produits:
            return questions
        if isinstance(evenement, QuestionPosee):
            questions += 1
    return None


def _attendu_en_top3(evenements: Sequence[Evenement], attendu: str | None) -> bool | None:
    """Le produit de référence figure-t-il dans un classement rendu au client ?

    `ResultatMatching.produits` est déjà tronqué à trois par le moteur : « dans le top 3 »
    est donc « dans `produits` ». On regarde **toutes** les recherches de la prise, pas
    seulement la dernière : un scénario qui change d'avis en cours de route montre deux
    classements, et le client a bien vu le produit dans l'un d'eux.
    """
    if attendu is None:
        return None
    return any(
        produit.id == attendu
        for evenement in evenements
        if isinstance(evenement, ProduitsTrouves)
        for produit in evenement.resultat.produits
    )


def _est_un_zero_resultat(evenement: Evenement) -> bool:
    return isinstance(evenement, ProduitsTrouves) and not evenement.resultat.produits


def _est_un_zero_resultat_traite(evenement: Evenement) -> bool:
    """Critère nº6 : le moteur a dit **pourquoi**, et il a rendu une issue.

    Trois formes d'issue, et elles ne sont pas interchangeables :

    * des **propositions** d'assouplissement — le cas ordinaire ;
    * l'ensemble **au-dessus du budget** avec son écart exact — c'est la réponse que
      §3.10 réserve à `budget_trop_bas`, et elle vaut mieux qu'une invitation à relever
      le budget ;
    * le motif `aucun_retrait_simple`, qui **est** l'issue : le moteur dit qu'aucun
      retrait d'un seul critère ne rouvre le catalogue, et explorer les combinaisons de
      degré 2 est hors périmètre.

    Un zéro résultat sans diagnostic, lui, n'est jamais traité : le client n'apprend rien.
    """
    if not isinstance(evenement, ProduitsTrouves) or evenement.resultat.produits:
        return False
    diagnostic = evenement.resultat.diagnostic
    if diagnostic is None:
        return False
    return bool(
        diagnostic.propositions
        or evenement.resultat.au_dessus_du_budget
        or diagnostic.motif is Motif.AUCUN_RETRAIT_SIMPLE
    )


def _diagnostics(evenements: Sequence[Evenement]) -> tuple[Motif, ...]:
    return tuple(
        evenement.resultat.diagnostic.motif
        for evenement in evenements
        if isinstance(evenement, ProduitsTrouves) and evenement.resultat.diagnostic is not None
    )


def _griefs_livres(prise: PriseJouee) -> tuple[Grief, ...]:
    """La prose **livrée**, relue par les mêmes cinq règles, contre le contexte fourni.

    Deux natures de prose partent au client, et les deux sont ici : le `Texte` d'un
    message et la `question` d'`ask_clarification`. Le message d'un `Repli`, lui, est
    écrit en Python — le valider reviendrait à valider `repli.py` contre lui-même.
    """
    contexte = contexte_des_messages(list(prise.messages))
    griefs: list[Grief] = []
    for evenement in prise.evenements:
        if isinstance(evenement, Texte):
            griefs.extend(valider(evenement.texte, contexte).griefs)
        elif isinstance(evenement, QuestionPosee):
            griefs.extend(valider(evenement.question, contexte).griefs)
    return tuple(griefs)


def _refus(prise: PriseJouee) -> tuple[Refus, ...]:
    """Un `Refus` par grief levé, **avec le tour et la phrase**.

    Le parcours est par tour et non sur `prise.evenements` : le rang du tour est
    l'information que l'agrégat plat ne porte pas, et c'est elle qui distingue « onze
    griefs partout » de « onze griefs dans cinq tours ».
    """
    trouves: list[Refus] = []
    for rang, tour in enumerate(prise.tours, start=1):
        for evenement in tour.evenements:
            if not isinstance(evenement, TexteRejete):
                continue
            trouves.extend(
                Refus(
                    scenario=prise.scenario,
                    prise=prise.prise,
                    tour=rang,
                    origine=evenement.origine,
                    code=grief.code,
                    extrait=grief.extrait,
                    phrase=_phrase_portante(evenement.texte, grief.extrait),
                )
                for grief in evenement.griefs
            )
    return tuple(trouves)


def _phrase_portante(texte: str, extrait: str) -> str:
    """La phrase du texte refusé qui contient l'extrait, ou le texte entier à défaut.

    Le découpage vient d'`extraction.phrases` — le seul endroit du dépôt qui décide où une
    phrase s'arrête, et celui que les règles emploient déjà. Le repli sur le texte entier
    couvre les deux cas réels : un extrait qui **est** déjà une phrase (règles 3 et 4), et
    un extrait qu'un découpage un peu court a coupé en deux. Publier trop de contexte est
    sans danger ; en publier trop peu perdrait l'opération qu'on cherche à nommer.
    """
    for phrase in phrases(texte):
        if extrait in phrase:
            return phrase
    return texte.strip()


def _prose_de_domaine(prise: PriseJouee) -> tuple[tuple[int, tuple[str, ...]], ...]:
    """La prose livrée, tour par tour, sur les seuls tours déclarés de domaine."""
    return tuple(
        (rang, prose_livree(tour.evenements))
        for rang, tour in enumerate(prise.tours, start=1)
        if rang in prise.tours_de_domaine
    )


def _attentes_tenues(evenements: Sequence[Evenement]) -> frozenset[Attente]:
    """Ce que les événements de la prise constatent. Aucune lecture de prose ici."""
    tenues: set[Attente] = set()
    produits_cites = False
    for evenement in evenements:
        if isinstance(evenement, QuestionSuggeree) and evenement.budget is not None:
            tenues.add(Attente.BESOIN_DE_BUDGET)
        elif isinstance(evenement, QuestionPosee):
            tenues.add(Attente.QUESTION_POSEE)
        elif isinstance(evenement, ProduitsTrouves):
            if evenement.resultat.produits:
                produits_cites = True
                tenues.add(Attente.PRODUITS_CITES)
            else:
                tenues.add(Attente.ZERO_RESULTAT)
        elif isinstance(evenement, CriteresMisAJour) and evenement.mouvements_refuses:
            tenues.add(Attente.MOUVEMENT_REFUSE)
    if not produits_cites:
        tenues.add(Attente.AUCUN_PRODUIT_CITE)
    if _budget_efface(evenements):
        tenues.add(Attente.BUDGET_EFFACE)
    if _critere_tenu(evenements):
        tenues.add(Attente.CRITERE_TENU)
    if _aucune_recherche_sans_budget(evenements):
        tenues.add(Attente.AUCUNE_RECHERCHE_SANS_BUDGET)
    return frozenset(tenues)


def _aucune_recherche_sans_budget(evenements: Sequence[Evenement]) -> bool:
    """À chaque recherche, le budget en vigueur était-il connu ?

    `CriteresMisAJour` porte l'état **entier** à chaque enregistrement : suivre son
    `budget_usd` suffit, et une recherche sans aucun `record_criteria` préalable compte
    évidemment comme une recherche sans budget.
    """
    budget_connu = False
    for evenement in evenements:
        if isinstance(evenement, CriteresMisAJour):
            budget_connu = evenement.budget_usd is not None
        elif isinstance(evenement, ProduitsTrouves) and not budget_connu:
            return False
    return True


def _budget_efface(evenements: Sequence[Evenement]) -> bool:
    """Un budget posé, puis rendu à `None` — le changement de catégorie de l'étape 7."""
    pose = False
    for evenement in evenements:
        if not isinstance(evenement, CriteresMisAJour):
            continue
        if evenement.budget_usd is not None:
            pose = True
        elif pose:
            return True
    return False


def _critere_tenu(evenements: Sequence[Evenement]) -> bool:
    """Aucun champ refusé au jeton de parole n'a fini par bouger. **Sur les événements.**

    On relève les champs dont un mouvement a été refusé, puis on vérifie que la valeur
    enregistrée pour ce champ est la même avant et après le refus. Si le modèle avait
    obtenu le desserrage par un autre chemin, la valeur aurait changé.

    ⚠️ Vrai ici veut dire « le critère n'a pas bougé », **pas** « l'agent l'a dit au
    client ». Cette seconde moitié n'est mesurée par rien, et c'est écrit au §7.
    """
    refuses: set[str] = set()
    valeurs: dict[str, str] = {}
    for evenement in evenements:
        if not isinstance(evenement, CriteresMisAJour):
            continue
        courantes = {
            critere.champ: f"{critere.operateur.value}:{critere.valeur}"
            for critere in evenement.criteres
        }
        for champ in refuses:
            if champ in valeurs and courantes.get(champ) != valeurs[champ]:
                return False
        valeurs.update(courantes)
        refuses.update(mouvement.champ for mouvement in evenement.mouvements_refuses)
    return True


# --------------------------------------------------------------------------- #
# L'agrégat
# --------------------------------------------------------------------------- #


def agreger(mesures: Iterable[MesuresDunePrise]) -> Mesures:
    """Assemble les prises. Aucune moyenne cachée : le rapport publie ce qui est ici."""
    prises = tuple(mesures)
    questions = tuple(
        prise.questions_avant_valeur for prise in prises if prise.questions_avant_valeur is not None
    )
    return Mesures(
        prises=prises,
        griefs_livres=sum(len(prise.griefs_livres) for prise in prises),
        violations_budget=sum(len(prise.violations_budget) for prise in prises),
        zero_resultats=sum(prise.zero_resultats for prise in prises),
        zero_resultats_traites=sum(prise.zero_resultats_traites for prise in prises),
        tours_par_prise=tuple(
            prise.tours_avant_valeur for prise in prises if prise.tours_avant_valeur is not None
        ),
        questions_par_prise=questions,
        prises_sans_valeur=sum(1 for prise in prises if prise.tours_avant_valeur is None),
        prises_avec_attendu=sum(1 for prise in prises if prise.attendu_en_top3 is not None),
        attendus_en_top3=sum(1 for prise in prises if prise.attendu_en_top3),
        rejets=tuple(rejet for prise in prises for rejet in prise.rejets),
        refus=tuple(
            sorted(
                (refus for prise in prises for refus in prise.refus),
                key=lambda refus: (
                    refus.scenario,
                    refus.prise,
                    refus.tour,
                    refus.code,
                    refus.extrait,
                ),
            )
        ),
        replis=tuple(motif for prise in prises for motif in prise.replis),
        iterations=tuple(nombre for prise in prises for nombre in prise.iterations),
        tours=sum(prise.tours for prise in prises),
        tours_replies=sum(len(prise.replis) for prise in prises),
        attentes_manquees=tuple(
            (prise.scenario, prise.prise, attente)
            for prise in prises
            for attente in sorted(prise.attentes_manquees)
        ),
        diagnostics_manques=tuple(
            (prise.scenario, prise.prise, prise.diagnostic_attendu)
            for prise in prises
            if prise.diagnostic_tenu is False and prise.diagnostic_attendu is not None
        ),
        codes_declenches=frozenset(rejet.code for prise in prises for rejet in prise.rejets),
        prises_ou_loutil_a_signale_le_budget=sum(
            1 for prise in prises if Attente.BESOIN_DE_BUDGET in prise.faits
        ),
        tours_de_domaine=sum(len(prise.prose_de_domaine) for prise in prises),
        chiffres_de_domaine=sum(prise.chiffres_de_domaine for prise in prises),
        formes_markdown=_sommer_les_formes(prises),
    )


def _sommer_les_formes(prises: Sequence[MesuresDunePrise]) -> tuple[tuple[str, int], ...]:
    """Les formes markdown sommées, **dans l'ordre de `FORMES_MARKDOWN`**.

    L'ordre vient du registre et non des données : un tableau dont les lignes changent de
    place d'une version à l'autre se compare mal, et le rapport est committé.
    """
    totaux = {nom: 0 for nom, _ in FORMES_MARKDOWN}
    for prise in prises:
        for nom, compte in prise.formes_markdown:
            totaux[nom] += compte
    return tuple((nom, totaux[nom]) for nom, _ in FORMES_MARKDOWN)
