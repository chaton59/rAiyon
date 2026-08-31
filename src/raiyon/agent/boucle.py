"""La boucle de tool use : appel, exécution, réinjection, jusqu'au texte ou au repli.

### La forme : un générateur d'événements, sur `messages.create()` (arbitrage 1)

*Alternative écartée — streamer dès maintenant.* La console serait plus vivante, mais on
paierait l'accumulation des deltas de `tool_use` en JSON partiel dans l'étape qui fait
déjà le premier appel API du projet. Le contrat d'événements est posé ; l'étape 10
remplace le producteur, pas le consommateur.

Le générateur rend `Evenement` et **retourne** une `IssueDuTour`. C'est bien un
`Iterator[Evenement]` pour la console, qui n'a que les événements à consommer ; le type
de retour porte en plus ce dont la persistance a besoin — l'état final et les lignes à
écrire. Le passer par un objet mutable rempli au passage aurait fait la même chose sans
que mypy le vérifie.

⚠️ **Le générateur ne produit son issue qu'à la fin. Un consommateur qui s'arrête au
premier événement n'écrit rien en base** — c'est vrai ici comme dans `session.py`, qui le
redit à l'endroit où ça compte.

---

### Le piège technique nº1 : chaque `tool_use` a son `tool_result` (arbitrage 4)

**Sans aucune exception** — y compris quand le tour est clos par `ask_clarification`, y
compris quand `max_iterations` est atteint, y compris sur un outil inconnu ou des
arguments illisibles.

Ce n'est pas un choix de conception : l'API **refuse** un historique où un `tool_use`
n'a pas son `tool_result` appairé. Comme les tours sont persistés et relus au message
suivant, un `tool_use` laissé orphelin ne casse pas le tour courant — il casse **le
suivant**, et le message d'erreur parlera d'un identifiant de bloc, pas de l'endroit où
la faute a été commise.

### Le réenchaînement de l'état est une exigence de correction

Chaque `tool_use` s'exécute **sur l'état rendu par le précédent**, à l'intérieur d'un même
message assistant. Sans cela, la garde « un tour, une catégorie » (arbitrage E de l'étape
7) ne se déclenche jamais : `rechercher_produits` pose `recherche_du_tour` dans l'état
qu'il rend, et un second appel qui repartirait de l'état d'avant ne verrait rien.

Un `OutilRefuse` ne fait pas tomber les appels suivants : le répartiteur rend alors l'état
**inchangé**, et ils repartent de là.

### `ask_clarification` terminal, et le préambule (arbitrage 5)

§3.7 avait un argument `preamble` ; l'étape 7 l'a supprimé. Le « donner avant de
demander » de §3.9 vit donc dans le message lui-même : **ce qui part au client est la
suite des blocs `text` du message assistant, puis la question.** Le prompt système le dit
— « écris ta piste en texte, puis pose la question par l'outil ».

*Alternative écartée — jeter le texte et n'envoyer que `question`.* La règle serait plus
simple et l'outil vraiment terminal ; mais elle supprime mécaniquement le comportement que
§3.9 réclame, et le modèle n'a plus aucun endroit où donner quelque chose en retour.

Trois cas résiduels, tranchés :

* **deux `ask_clarification` dans un même message** — la première gagne ; la seconde
  s'exécute quand même (elle a besoin de son `tool_result`) et son résultat est ignoré,
  avec un `WARNING` ;
* **`ask_clarification` avec un autre outil** — tous s'exécutent, tous ont leur
  `tool_result`, la question part et les autres résultats sont perdus ;
* **aucun `tool_use`, que du texte** — fin normale du tour.
"""

import json
from collections.abc import Generator, Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog

from raiyon.agent.client import ClientLLM
from raiyon.agent.evenements import (
    CriteresMisAJour,
    Evenement,
    ProduitsTrouves,
    QuestionPosee,
    QuestionSuggeree,
    Repli,
    Sondage,
    Texte,
)
from raiyon.tools.erreurs import OutilRefuse
from raiyon.tools.etat import EtatSession
from raiyon.tools.outils import (
    ResultatEnregistrement,
    ResultatOutil,
    ResultatPrecision,
    ResultatQuestion,
    ResultatRecherche,
    ResultatSondage,
    en_tool_result,
)
from raiyon.tools.repartiteur import ContexteOutils, executer

logueur = structlog.get_logger(__name__)

PHRASE_DE_REPLI = (
    "Je m'y perds un peu — pouvez-vous me redire ce que vous cherchez, et pour quel usage ?"
)
"""Écrite en Python, jamais générée. Voir l'alternative écartée dans `Repli`."""

ROLE_ASSISTANT = "assistant"
ROLE_CLIENT = "user"
"""⚠️ Les `tool_result` portent le rôle `user` dans l'API Anthropic : il n'existe pas de
rôle « outil ». Le commentaire de `models.py` dit la même chose sur la colonne."""


@dataclass(frozen=True, slots=True)
class TourProduit:
    """Une ligne à écrire dans `tours_conversation`. Le numéro est posé par `session.py`."""

    role: str
    blocs: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class IssueDuTour:
    """Ce que la boucle laisse derrière elle, et que seule la persistance consomme."""

    etat: EtatSession
    tours: tuple[TourProduit, ...]
    iterations: int
    outils_appeles: tuple[str, ...]


@dataclass
class _Message:
    """Le dépouillement d'un message assistant : ses textes, ses appels d'outils."""

    textes: list[str] = field(default_factory=list)
    appels: list[dict[str, Any]] = field(default_factory=list)


def repondre(
    *,
    client: ClientLLM,
    systeme: str,
    outils: Sequence[dict[str, Any]],
    historique: Sequence[dict[str, Any]],
    message_client: str,
    etat: EtatSession,
    contexte: ContexteOutils,
    max_iterations: int,
) -> Generator[Evenement, None, IssueDuTour]:
    """Conduit un tour client de bout en bout et rend ce qu'il faut persister.

    `historique` est la conversation relue en base, dans l'ordre des numéros de tour.
    `message_client` est le texte du message ; sa ligne `tours_conversation` a déjà été
    posée par l'appelant — c'est son `numero` qui sert de `contexte.tour_client`
    (arbitrage 9), et c'est pourquoi elle ne figure pas dans `IssueDuTour.tours`.
    """
    messages: list[dict[str, Any]] = [
        *historique,
        {"role": ROLE_CLIENT, "content": [{"type": "text", "text": message_client}]},
    ]
    tours: list[TourProduit] = []
    outils_appeles: list[str] = []
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        reponse = client.repondre(systeme=systeme, outils=outils, messages=messages)
        messages.append({"role": ROLE_ASSISTANT, "content": reponse.blocs})
        tours.append(TourProduit(ROLE_ASSISTANT, reponse.blocs))

        message = _depouiller(reponse.blocs)
        # Le texte part **avant** l'exécution des outils, et sans savoir ce qui suit :
        # c'est ce qui rend le streaming substituable à l'étape 10 (voir `Texte`).
        for texte in message.textes:
            yield Texte(texte)

        if not message.appels:
            if reponse.fin == "max_tokens":
                # 2 048 jetons devraient suffire largement (arbitrage 12) ; une
                # troncature est donc un signal, pas une fatalité à absorber en silence.
                logueur.warning(
                    "boucle.reponse_tronquee",
                    iteration=iteration,
                    consequence="le dernier message part au client tel quel, incomplet",
                )
            logueur.info("boucle.fin_de_tour", iterations=iteration, fin=reponse.fin)
            return IssueDuTour(etat, tuple(tours), iteration, tuple(outils_appeles))

        outils_appeles.extend(str(appel.get("name")) for appel in message.appels)
        etat, resultats, question = yield from _executer_les_appels(message.appels, etat, contexte)

        # Un seul bloc `user` porte **tous** les `tool_result`, dans l'ordre des
        # `tool_use`. C'est ce que l'API attend, et c'est ce qui rend l'appairage
        # vérifiable par une simple comparaison de listes.
        messages.append({"role": ROLE_CLIENT, "content": resultats})
        tours.append(TourProduit(ROLE_CLIENT, resultats))

        if question is not None:
            yield QuestionPosee(question=question.question, champ_vise=question.champ_vise)
            logueur.info("boucle.tour_clos_par_question", iterations=iteration)
            return IssueDuTour(etat, tuple(tours), iteration, tuple(outils_appeles))

    # `max_iterations` atteint. Les `tool_result` de la dernière itération sont déjà
    # dans `tours` : c'est ce qui fait que le tour client suivant repartira d'un
    # historique valide (arbitrage 4).
    logueur.warning(
        "boucle.max_iterations",
        iterations=iteration,
        outils_appeles=outils_appeles,
        consequence="tour clos par un message de repli écrit en Python",
    )
    yield Repli(PHRASE_DE_REPLI, iteration, tuple(outils_appeles))
    return IssueDuTour(etat, tuple(tours), iteration, tuple(outils_appeles))


def _executer_les_appels(
    appels: Sequence[dict[str, Any]], etat: EtatSession, contexte: ContexteOutils
) -> Generator[Evenement, None, tuple[EtatSession, list[dict[str, Any]], ResultatPrecision | None]]:
    """Exécute tous les appels d'un message, séquentiellement, en réenchaînant l'état.

    Rend l'état final, les `tool_result` **dans l'ordre des `tool_use`**, et la première
    demande de précision s'il y en a une.

    ⚠️ **Une fois la question vue, les événements suivants ne partent plus** — « les
    autres résultats sont perdus » (arbitrage 5). Sans cela, un `search_products` appelé
    après `ask_clarification` afficherait au client une liste de produits que l'assistant
    ne commentera jamais, puisque le tour est clos : une recommandation sans son
    « pourquoi », ce que la section 11 du prompt système interdit.

    **L'asymétrie est réelle et il vaut mieux l'écrire que la découvrir :** un événement
    émis *avant* la question, lui, reste émis — on ne le rattrape pas. La règle dépend
    donc de l'ordre des blocs dans le message. C'est assumé, pour deux raisons : le cas
    est dégénéré (le prompt système dit de ne pas mélanger `ask_clarification` avec un
    autre outil), et toute règle qui n'en dépendrait pas exigerait de connaître la fin du
    message avant d'émettre le premier événement — c'est-à-dire de bufferiser, donc de
    rendre le streaming de l'étape 10 inopérant.
    """
    resultats: list[dict[str, Any]] = []
    question: ResultatPrecision | None = None

    for appel in appels:
        nom = str(appel.get("name", ""))
        entree = appel.get("input") or {}
        etat, resultat = executer(nom, entree, etat, contexte)
        resultats.append(_bloc_tool_result(str(appel.get("id", "")), resultat))

        if isinstance(resultat, OutilRefuse):
            # Aucun événement : un refus est un échange avec le modèle, pas avec le
            # client (voir la docstring d'`evenements.py`). Le répartiteur l'a logué.
            continue

        if isinstance(resultat, ResultatPrecision):
            if question is None:
                question = resultat
            else:
                # Elle s'est exécutée — elle avait besoin de son `tool_result` — et son
                # résultat est perdu. Le prompt système dit de n'appeler cet outil
                # qu'une fois ; c'est la seule chose à faire quand il ne l'a pas fait.
                logueur.warning(
                    "boucle.seconde_demande_de_precision_ignoree",
                    question=resultat.question,
                    consequence="la première question gagne, celle-ci est perdue",
                )
            continue

        evenement = _evenement_de(resultat)
        if evenement is not None and question is None:
            yield evenement

    return etat, resultats, question


def _evenement_de(resultat: ResultatOutil) -> Evenement | None:
    """Le résultat typé d'un outil vers l'événement qui lui correspond.

    `ResultatPrecision` n'a pas de ligne ici : il est terminal, et c'est la boucle qui
    décide de son sort — la seconde d'un même message étant ignorée, l'événement ne peut
    pas être construit à cet endroit.
    """
    if isinstance(resultat, ResultatEnregistrement):
        return CriteresMisAJour(
            categorie=resultat.categorie,
            criteres=resultat.criteres,
            budget_usd=resultat.budget_usd,
            optimisation=resultat.optimisation,
            mouvements_refuses=resultat.mouvements_refuses,
        )
    if isinstance(resultat, ResultatSondage):
        return Sondage(
            categorie=resultat.categorie,
            dans_le_budget=resultat.dans_le_budget,
            dans_la_zone_de_tolerance=resultat.dans_la_zone_de_tolerance,
            fourchette_prix=resultat.fourchette_prix,
            champs=resultat.champs,
        )
    if isinstance(resultat, ResultatQuestion):
        return QuestionSuggeree(
            categorie=resultat.categorie,
            candidats=resultat.candidats,
            budget=resultat.budget,
            champ=resultat.champ,
        )
    if isinstance(resultat, ResultatRecherche):
        return ProduitsTrouves(resultat.resultat)
    return None


def _bloc_tool_result(identifiant: str, resultat: ResultatOutil | OutilRefuse) -> dict[str, Any]:
    """Le bloc à réinjecter. `en_tool_result()` est seule à nommer les clés du protocole.

    `ensure_ascii=False` : le message d'un refus est écrit **pour le modèle**, en
    français, et l'échappement `\\uXXXX` le rendrait illisible dans les logs comme dans
    une cassette de l'étape 12 pour un gain nul.
    """
    return {
        "type": "tool_result",
        "tool_use_id": identifiant,
        "content": json.dumps(en_tool_result(resultat), ensure_ascii=False),
        "is_error": isinstance(resultat, OutilRefuse),
    }


def _depouiller(blocs: Sequence[dict[str, Any]]) -> _Message:
    """Sépare textes et appels d'outils. Tout autre type de bloc est ignoré.

    Il n'y en a pas en v1 — le thinking étendu est écarté (arbitrage 12) — mais un bloc
    inconnu qui ferait lever ici clorait une conversation pour une raison qui n'a rien à
    voir avec le produit.
    """
    message = _Message()
    for bloc in blocs:
        if bloc.get("type") == "text":
            message.textes.append(str(bloc.get("text", "")))
        elif bloc.get("type") == "tool_use":
            message.appels.append(bloc)
    return message
