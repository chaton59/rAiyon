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
from raiyon.validateur.regles import CodeGrief
from raiyon.validateur.validateur import Grief, OrigineRejet, valider

CODE_DU_CRITERE_2 = CodeGrief.ECART_NON_DIT
"""Le seul code qui porte le critère nº2. Les cinq autres portent le critère nº1."""

SEUIL_QUESTIONS = 2
"""Critère nº3 : médiane des questions avant première valeur. §3.9 en fait une métrique,
pas un plafond — le seuil vit donc ici, dans la mesure, et pas dans la boucle."""

SEUIL_TOP3 = 0.80
"""Critère nº4 : part des scénarios à attendu dont le produit de référence est dans le
classement rendu."""


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
class MesuresDunePrise:
    """Ce qu'une prise a produit. Tout est un compte, rien n'est une opinion."""

    scenario: str
    prise: int
    tours: int

    griefs_livres: tuple[Grief, ...]
    """Critère nº1. Les codes autres qu'`ECART_NON_DIT`, dans la prose **livrée**."""

    violations_budget: tuple[Grief, ...]
    """Critère nº2. Les `ECART_NON_DIT` de la prose livrée."""

    questions_avant_valeur: int | None
    """Critère nº3. `None` si aucune valeur n'a jamais été livrée : la prise n'entre alors
    pas dans la médiane, parce que « zéro question avant une valeur qui n'est jamais
    venue » serait le meilleur score possible pour le pire comportement possible."""

    attendu_en_top3: bool | None
    """Critère nº4. `None` si le scénario ne porte pas d'attendu (arbitrage F)."""

    zero_resultats_traites: int
    zero_resultats: int
    """Critère nº6. Un zéro résultat est **traité** s'il porte un diagnostic et une issue."""

    rejets: tuple[Rejet, ...]
    replis: tuple[MotifDeRepli, ...]
    iterations: tuple[int, ...]

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
    questions_par_prise: tuple[int, ...]
    prises_sans_valeur: int
    prises_avec_attendu: int
    attendus_en_top3: int

    # ---- Publiés sans seuil -------------------------------------------------
    rejets: tuple[Rejet, ...]
    replis: tuple[MotifDeRepli, ...]
    iterations: tuple[int, ...]
    tours: int
    tours_replies: int
    attentes_manquees: tuple[tuple[str, int, Attente], ...]
    diagnostics_manques: tuple[tuple[str, int, Motif], ...]
    prises_ou_loutil_a_signale_le_budget: int
    """Publié sans seuil : sur combien de prises `suggest_next_question` a-t-il signalé le
    budget manquant. Voir `Attente.BESOIN_DE_BUDGET` — c'est une observation sur la
    conduite du dialogue, pas une exigence."""

    @property
    def mediane_des_questions(self) -> float | None:
        if not self.questions_par_prise:
            return None
        return float(statistics.median(self.questions_par_prise))

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
        mediane = self.mediane_des_questions
        return None if mediane is None else mediane <= SEUIL_QUESTIONS

    @property
    def critere_4(self) -> bool | None:
        part = self.part_attendus_en_top3
        return None if part is None else part >= SEUIL_TOP3

    @property
    def bloquants_tenus(self) -> bool:
        """Ce qui décide du code de sortie de `make eval`."""
        return self.critere_1 and self.critere_2 and self.critere_6 and not self.attentes_manquees


# --------------------------------------------------------------------------- #
# Le calcul, prise par prise
# --------------------------------------------------------------------------- #


def mesurer(prise: PriseJouee) -> MesuresDunePrise:
    """Toutes les mesures d'une prise, en une passe sur ses événements."""
    evenements = prise.evenements
    griefs = _griefs_livres(prise)
    diagnostics = _diagnostics(evenements)
    tenues = _attentes_tenues(evenements)

    return MesuresDunePrise(
        scenario=prise.scenario,
        prise=prise.prise,
        tours=len(prise.tours),
        griefs_livres=tuple(g for g in griefs if g.code is not CODE_DU_CRITERE_2),
        violations_budget=tuple(g for g in griefs if g.code is CODE_DU_CRITERE_2),
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
        replis=tuple(e.motif for e in evenements if isinstance(e, Repli)),
        iterations=tuple(tour.iterations for tour in prise.tours),
        faits=tenues,
        attentes_manquees=prise.attentes - tenues,
        diagnostic_attendu=prise.diagnostic_attendu,
        diagnostics_vus=diagnostics,
    )


def questions_avant_premiere_valeur(evenements: Sequence[Evenement]) -> int | None:
    """Critère nº3 — le **délai avant première valeur** de §3.9, en questions.

    Compte les `QuestionPosee` qui précèdent le premier `ProduitsTrouves` non vide. Rend
    `None` si aucune valeur n'est jamais venue : voir la docstring du champ.
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
        questions_par_prise=questions,
        prises_sans_valeur=sum(1 for prise in prises if prise.questions_avant_valeur is None),
        prises_avec_attendu=sum(1 for prise in prises if prise.attendu_en_top3 is not None),
        attendus_en_top3=sum(1 for prise in prises if prise.attendu_en_top3),
        rejets=tuple(rejet for prise in prises for rejet in prise.rejets),
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
        prises_ou_loutil_a_signale_le_budget=sum(
            1 for prise in prises if Attente.BESOIN_DE_BUDGET in prise.faits
        ),
    )
