"""La boucle de tool use : appel, exécution, réinjection, jusqu'au texte ou au repli.

### La forme : un générateur d'événements, sur `messages.create()` (arbitrage 1)

*Alternative écartée — streamer dès maintenant.* La console serait plus vivante, mais on
paierait l'accumulation des deltas de `tool_use` en JSON partiel dans l'étape qui fait
déjà le premier appel API du projet. Le contrat d'événements est posé ; l'étape 10
remplace le producteur, pas le consommateur.

⚠️ **Amendement de l'étape 9 : cette promesse cesse de valoir pour `Texte`.** Voir plus
bas, c'est l'arbitrage structurant de l'étape.

---

### Le texte est bufferisé, validé, puis émis (étape 9, arbitrage A)

**Valider après génération et streamer le texte au client sont incompatibles** : on ne
rattrape pas une phrase déjà affichée. §3.11 promet trois niveaux cumulés, §3.12 promet
des `text_delta` ; les deux étaient en contradiction et personne ne l'avait écrit. C'est
§3.11 qui gagne.

Le texte d'un message assistant est donc **concaténé, relu par `raiyon.validateur`, puis
émis** — un seul `Texte`, jamais une suite de deltas. Les événements d'outils
(`CriteresMisAJour`, `Sondage`, `QuestionSuggeree`, `ProduitsTrouves`) continuent
d'arriver au fil de l'eau : le panneau de §3.12 vit pendant l'attente, seule la prose
arrive d'un bloc.

*Alternative écartée — streamer le texte et corriger à l'écran après coup.* Meilleure
latence perçue, mais le client voit une affirmation puis sa rétractation : c'est §2 pris
à l'envers, et une démonstration qui montrerait un prix faux pendant deux secondes ne
démontrerait rien.

Un texte refusé donne un `TexteRejete`, puis **une** régénération : le grief part dans le
même bloc `user` que les `tool_result`, après eux (arbitrage D). Second échec → repli sur
template. Le message fautif **reste dans l'historique** — le retirer casserait
l'appairage des `tool_result` et rendrait le grief incompréhensible ; le modèle voit donc
sa propre sortie rejetée au tour suivant, et c'est acceptable.

### La question d'`ask_clarification` est validée aussi (correctif de l'étape 9)

Elle n'est pas un bloc `text` : c'est un **argument d'outil** qui traverse le répartiteur
et part au client verbatim. Elle échappait donc au validateur — sur le chemin le plus
fréquent d'une conversation, qui contient beaucoup plus de questions que de
recommandations.

Elle est relue ici, après `_executer_les_appels` et avant `QuestionPosee`, par les
**mêmes** cinq règles et contre le **même** instantané `fourni` que le texte. Trois
conséquences, toutes voulues :

* le tour **ne se clôt pas** sur un rejet — `ask_clarification` est terminal pour l'outil,
  pas pour la boucle ; son `tool_result` est présent, et le grief le suit dans le bloc ;
* le budget de régénération est **partagé** avec celui du texte : il vaut pour le tour, pas
  par nature de sortie. Un budget par nature doublerait le pire cas d'appels API et
  donnerait deux compteurs à réconcilier à l'étape 12 ;
* le repli d'une question rejetée est la **phrase générique**, jamais le template de
  recommandation — on ne répond pas par un classement de produits à quelqu'un qu'on était
  en train d'interroger.

*Alternative écartée — concaténer texte et question et ne valider qu'une fois.* Plus
proche de ce que le client lit d'un seul tenant ; écartée parce qu'elle obligerait à
retarder l'émission du texte jusqu'**après** l'exécution des outils. Le préambule
arriverait alors après `[critères]` et `[sondage]`, et l'arbitrage A perdrait la propriété
qui le rend acceptable : les événements d'outils vivent pendant que la prose se fait
attendre, pas l'inverse.

⚠️ **Conséquence assumée** : un produit hors budget nommé dans le texte dont l'écart ne
serait donné que dans la question déclencherait la règle 4, puisque les deux sont validés
séparément. Le prompt système ne demande jamais de citer un produit dans un préambule de
question — si le cas se produit, c'est un signal, pas un faux positif.

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
    MotifDeRepli,
    ProduitsTrouves,
    QuestionPosee,
    QuestionSuggeree,
    Repli,
    Sondage,
    Texte,
    TexteRejete,
)
from raiyon.agent.prompts import message_de_grief
from raiyon.matching.moteur import ResultatMatching
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
from raiyon.validateur.contexte import contexte_des_messages
from raiyon.validateur.repli import rediger
from raiyon.validateur.validateur import (
    VERDICT_SANS_GRIEF,
    OrigineRejet,
    Verdict,
    valider,
)

logueur = structlog.get_logger(__name__)

PHRASE_DE_REPLI = (
    "Je m'y perds un peu — pouvez-vous me redire ce que vous cherchez, et pour quel usage ?"
)
"""Écrite en Python, jamais générée. Voir l'alternative écartée dans `Repli`.

Celle du repli de validation vit dans `validateur/repli.py` : deux situations, donc deux
phrases. Ici le modèle a tourné en rond ; là il a affirmé ce qu'il n'avait pas."""

SEPARATEUR_DE_BLOCS = "\n"
"""Ce qui recolle les blocs `text` d'un même message assistant avant validation.

L'API n'en rend qu'un en pratique ; en rendre plusieurs et les valider séparément
laisserait passer une phrase coupée en deux blocs — et le découpage en phrases du
validateur, qui coupe déjà sur le saut de ligne, retrouve exactement la même granularité
que si les blocs étaient restés séparés."""

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

    @property
    def texte(self) -> str:
        """Le texte du message, **entier**. C'est lui que le validateur relit."""
        return SEPARATEUR_DE_BLOCS.join(self.textes).strip()


@dataclass(frozen=True, slots=True)
class _Executions:
    """Ce qu'un message assistant a produit en exécutant ses outils.

    `recherche` est le dernier `ResultatMatching` **typé** du tour : c'est ce dont le
    repli sur template a besoin, et il ne survit pas à la sérialisation en `tool_result`
    — le reconstruire depuis le JSON demanderait un second lecteur du protocole.
    """

    etat: EtatSession
    resultats: list[dict[str, Any]]
    question: ResultatPrecision | None
    recherche: ResultatMatching | None


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
    max_regenerations: int,
) -> Generator[Evenement, None, IssueDuTour]:
    """Conduit un tour client de bout en bout et rend ce qu'il faut persister.

    `historique` est la conversation relue en base, dans l'ordre des numéros de tour.
    `message_client` est le texte du message ; sa ligne `tours_conversation` a déjà été
    posée par l'appelant — c'est son `numero` qui sert de `contexte.tour_client`
    (arbitrage 9), et c'est pourquoi elle ne figure pas dans `IssueDuTour.tours`.

    `max_regenerations` est un budget **de tour**, pas de message : deux refus dans un
    même tour valent deux refus, quel que soit le message qui les a produits. C'est ce
    qui borne le coût — chaque tentative est un appel API payé.
    """
    messages: list[dict[str, Any]] = [
        *historique,
        {"role": ROLE_CLIENT, "content": [{"type": "text", "text": message_client}]},
    ]
    tours: list[TourProduit] = []
    outils_appeles: list[str] = []
    iteration = 0
    regenerations = 0
    derniere_recherche: ResultatMatching | None = None

    while iteration < max_iterations:
        iteration += 1
        # Le contexte fourni se lit sur les `tool_result` **déjà** dans la conversation :
        # ce sont exactement les faits que le modèle avait sous les yeux en écrivant le
        # message qu'on s'apprête à lire. Il est cumulatif sur la session, historique
        # relu compris (étape 9, arbitrage B).
        fourni = contexte_des_messages(messages)
        reponse = client.repondre(systeme=systeme, outils=outils, messages=messages)
        messages.append({"role": ROLE_ASSISTANT, "content": reponse.blocs})
        tours.append(TourProduit(ROLE_ASSISTANT, reponse.blocs))

        message = _depouiller(reponse.blocs)
        verdict = valider(message.texte, fourni) if message.texte else VERDICT_SANS_GRIEF

        if verdict.griefs:
            regenerations += 1
            yield TexteRejete(verdict.griefs, regenerations, OrigineRejet.TEXTE)
            _journaliser_le_rejet(
                verdict, OrigineRejet.TEXTE, iteration, regenerations, max_regenerations
            )

            # Les outils du message fautif s'exécutent **quand même** : chaque `tool_use`
            # doit avoir son `tool_result` (piège technique nº1), et leurs résultats sont
            # des faits — le panneau de §3.12 n'a pas à mentir parce que la prose ment.
            executions = yield from _executer_les_appels(message.appels, etat, contexte)
            etat = executions.etat
            derniere_recherche = executions.recherche or derniere_recherche
            outils_appeles.extend(str(appel.get("name")) for appel in message.appels)

            # ⚠️ La question du même message n'est **pas** validée ici : le budget du tour
            # vient d'être consommé par le texte, et la valider ne changerait rien à ce
            # qui suit. Elle le sera au message régénéré, s'il en repose une.
            if regenerations > max_regenerations:
                # Repli sur template (§3.11 niveau 3). Les `tool_result` partent avant de
                # sortir : sans eux, c'est le tour **suivant** que l'API refuserait.
                _ajouter_les_resultats(messages, tours, executions.resultats)
                yield Repli(
                    rediger(derniere_recherche, OrigineRejet.TEXTE),
                    iteration,
                    tuple(outils_appeles),
                    MotifDeRepli.VALIDATION,
                )
                return IssueDuTour(etat, tuple(tours), iteration, tuple(outils_appeles))

            # Le grief part **après** les `tool_result`, dans le même bloc `user` :
            # l'API exige les résultats appairés avant tout autre contenu utilisateur.
            # Quand le message ne portait que du texte, le bloc ne contient que le grief.
            reprise = [*executions.resultats, _bloc_de_grief(verdict)]
            messages.append({"role": ROLE_CLIENT, "content": reprise})
            tours.append(TourProduit(ROLE_CLIENT, reprise))
            continue

        if message.texte:
            yield Texte(message.texte)

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
        executions = yield from _executer_les_appels(message.appels, etat, contexte)
        etat = executions.etat
        derniere_recherche = executions.recherche or derniere_recherche

        # La question d'`ask_clarification` est **de la prose qui part au client**, et
        # elle échappait au validateur : c'est un argument d'outil, pas un bloc `text`.
        # Elle est donc relue ici — par les **mêmes** cinq règles, contre le **même**
        # instantané `fourni` que le texte, c'est-à-dire ce que le modèle avait sous les
        # yeux en l'écrivant. Ni règle nouvelle, ni contexte élargi : élargir validerait
        # une affirmation que le modèle ne pouvait pas fonder.
        #
        # La validation vit ici et pas dans `demander_precision` : lui passer un
        # `ContexteFourni` casserait l'arbitrage C de l'étape 7 — un outil ne prend que
        # ce qu'il lit dans l'état — et ferait entrer le validateur dans `raiyon.tools`.
        verdict_question = (
            valider(executions.question.question, fourni)
            if executions.question is not None
            else VERDICT_SANS_GRIEF
        )
        if verdict_question.griefs:
            regenerations += 1
            yield TexteRejete(verdict_question.griefs, regenerations, OrigineRejet.QUESTION)
            _journaliser_le_rejet(
                verdict_question, OrigineRejet.QUESTION, iteration, regenerations, max_regenerations
            )

            if regenerations > max_regenerations:
                _ajouter_les_resultats(messages, tours, executions.resultats)
                yield Repli(
                    # Jamais le template : on ne répond pas par un classement de produits
                    # à quelqu'un qu'on était en train d'interroger.
                    rediger(derniere_recherche, OrigineRejet.QUESTION),
                    iteration,
                    tuple(outils_appeles),
                    MotifDeRepli.VALIDATION,
                )
                return IssueDuTour(etat, tuple(tours), iteration, tuple(outils_appeles))

            # Le tour **ne se clôt pas** : `ask_clarification` est terminal pour l'outil,
            # pas pour la boucle quand sa question est refusée. Son `tool_result` est bien
            # présent — l'outil s'est exécuté — et le grief le suit dans le même bloc.
            reprise = [*executions.resultats, _bloc_de_grief(verdict_question)]
            messages.append({"role": ROLE_CLIENT, "content": reprise})
            tours.append(TourProduit(ROLE_CLIENT, reprise))
            continue

        # Un seul bloc `user` porte **tous** les `tool_result`, dans l'ordre des
        # `tool_use`. C'est ce que l'API attend, et c'est ce qui rend l'appairage
        # vérifiable par une simple comparaison de listes.
        _ajouter_les_resultats(messages, tours, executions.resultats)

        if executions.question is not None:
            question = executions.question
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
    yield Repli(PHRASE_DE_REPLI, iteration, tuple(outils_appeles), MotifDeRepli.MAX_ITERATIONS)
    return IssueDuTour(etat, tuple(tours), iteration, tuple(outils_appeles))


def _ajouter_les_resultats(
    messages: list[dict[str, Any]], tours: list[TourProduit], resultats: list[dict[str, Any]]
) -> None:
    """Pose le bloc `user` des `tool_result`, s'il y en a.

    Le garde-fou n'est pas cosmétique : un message assistant sans `tool_use` ne produit
    aucun résultat, et l'API refuse un bloc de contenu vide.
    """
    if not resultats:
        return
    messages.append({"role": ROLE_CLIENT, "content": resultats})
    tours.append(TourProduit(ROLE_CLIENT, resultats))


def _bloc_de_grief(verdict: Verdict) -> dict[str, Any]:
    """Le message de reprise, en bloc `text`. Le texte vit dans `prompts/grief.v1.md`."""
    return {"type": "text", "text": message_de_grief(verdict.en_lignes())}


def _journaliser_le_rejet(
    verdict: Verdict, origine: OrigineRejet, iteration: int, regenerations: int, budget: int
) -> None:
    """Un `WARNING` par rejet, avec les codes — c'est le taux que l'étape 12 publiera."""
    logueur.warning(
        "boucle.texte_rejete",
        origine=origine.value,
        iteration=iteration,
        tentative=regenerations,
        budget=budget,
        codes=[grief.code.value for grief in verdict.griefs],
        consequence=(
            "repli sur template" if regenerations > budget else "une régénération est demandée"
        ),
    )


def _executer_les_appels(
    appels: Sequence[dict[str, Any]], etat: EtatSession, contexte: ContexteOutils
) -> Generator[Evenement, None, _Executions]:
    """Exécute tous les appels d'un message, séquentiellement, en réenchaînant l'état.

    Rend l'état final, les `tool_result` **dans l'ordre des `tool_use`**, la première
    demande de précision s'il y en a une, et le dernier `ResultatMatching` typé.

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
    message avant d'émettre le premier événement.

    ⚠️ **La seconde raison ne vaut plus pour le texte, et elle vaut toujours ici.**
    L'étape 9 bufferise la prose ; elle ne bufferise pas les événements d'outils, qui
    continuent de partir au fil de l'eau pendant l'attente (arbitrage A). L'asymétrie
    reste donc entière pour eux.
    """
    resultats: list[dict[str, Any]] = []
    question: ResultatPrecision | None = None
    recherche: ResultatMatching | None = None

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

        if isinstance(resultat, ResultatRecherche):
            recherche = resultat.resultat

        evenement = _evenement_de(resultat)
        if evenement is not None and question is None:
            yield evenement

    return _Executions(etat, resultats, question, recherche)


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
