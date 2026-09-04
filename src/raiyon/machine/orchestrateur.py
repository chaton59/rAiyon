"""La seconde orchestration : deux appels modèle, et le code entre les deux.

Même signature que `boucle.repondre`, mêmes événements, même `IssueDuTour`, même table.
C'est `raiyon.orchestration.Orchestrateur` qui rend « même signature » vérifiable par
mypy plutôt qu'affirmé.

---

### La forme d'un tour

```
appel nº1  extraction        → un seul outil exposé : record_criteria
           enregistrer_criteres(...)          ← la couche outils, inchangée
           [garde d'extraction : au plus une relance, étape 21]
           boucle decider() / outils          ← aucun appel modèle
appel nº2  rédaction OU question              ← jamais les deux
           validation, une régénération, repli
```

⚠️ **Plancher de 2,00 appel par tour, plus un appel sur les tours où la garde tire** —
contre 2,36 mesuré sur la campagne `v2` de l'agent. **La définition a changé à l'étape 21**,
et c'est une mesure publiée : la campagne `machine.v1` a été enregistrée avant la garde, et
son 2,00 est celui d'un monde où la relance n'existait pas. Il reste un plancher, pas un
plafond : une régénération refusée en ajoute un, comme chez l'agent.

### La garde d'extraction — une relance, et une seule (étape 21)

Quand l'appel nº1 rend un `record_criteria` qui **pose une catégorie sans aucun critère**,
l'extraction est relancée une fois. C'est le correctif que l'étape 15 avait différé au motif
qu'il casserait le plancher de 2,00 au milieu de la comparaison des deux orchestrations ;
l'étape 18 a suspendu cette comparaison, et le motif est tombé avec elle.

**Le défaut qu'elle vise**, observé à l'étape 20 sur un tirage vivant et sur
`sur_specifie.3` dans les cassettes : le client demande un écran de 27 pouces à 400 $, la
machine enregistre la catégorie et le budget **et rien d'autre**, cherche sur 115 candidats
au lieu de 37, et recommande trois écrans de 21 à 24 pouces. Recensé sur les 81 tours
d'extraction enregistrés : **2 tours** perdent ainsi un critère explicitement énoncé.

Quatre bornes, et elles sont dans le code :

* **une relance par tour, jamais deux** — c'est un garde-fou, pas une boucle ;
* elle ne tire que sur une extraction **à zéro critère** (voir `_extraction_muette`) ;
* si la relance rend encore zéro critère, on continue avec ce qu'on a : le défaut est alors
  du modèle et non de l'orchestration, et un troisième appel ne ferait que le constater ;
* le premier `record_criteria` est **exécuté et persisté avant** la relance. Le jeter
  perdrait le budget qu'il portait — dans le tirage de l'étape 20, c'est le seul fait que
  l'extraction ait correctement lu.

⚠️ **Elle tire large, et c'est mesuré : 10 des 81 tours, pour 2 vrais positifs.** Les huit
autres sont des tours où le client n'énonçait qu'un budget ou qu'une catégorie. **Ce n'est
pas réparable ici** : les arguments d'un vrai positif et d'un faux positif sont identiques —
`{categorie, budget_usd}` est la forme des deux —, seul le message du client les distingue,
et le lire est le travail du modèle. C'est ce que la relance lui redemande, et une garde
plus fine serait une garde qui devine. Le coût d'un faux positif est **un appel**, et rien
d'autre : la consigne autorise « aucun critère » comme réponse.

⚠️ **Son gain, lui, n'est mesuré par rien.** Les cassettes de `machine.v1` ont été
enregistrées sans elle : sur les dix prises où elle tire, un appel de plus apparaît,
l'empreinte diverge et la prise sort du rejeu (`DIVERGENCES_ATTENDUES`) — la campagne passe
de 30 prises rejouables à **20 sur 36**. Savoir ce que la garde vaut demanderait de
réenregistrer le jeu — ~176 appels, arbitrage de budget non pris. Ce qui est su est que le
défaut existe et à quelle fréquence ; ce qui ne l'est pas est ce que la relance en rattrape.

### On ne force pas l'outil d'extraction, et c'est aussi le bon design

`ClientLLM` n'a pas de `tool_choice`, et l'ajouter rippellerait sur `ClientAnthropic`, le
`FauxClient`, `ClientCassette` et les `dependency_overrides` de l'API. Mais l'argument de
conception tient tout seul : forcer `record_criteria` sur « compare plutôt la 1 et la 3 »
ferait **fabriquer un critère** au modèle, ce que §2 interdit appliqué à l'état.

Un message d'extraction **sans `tool_use` est le chemin normal**, pas un incident : c'est
un tour qui n'apporte aucun critère nouveau. L'état passe inchangé à `decider()`, et un
`logueur.info` le note — jamais un `WARNING`.

---

### ⚠️ Un message du modèle est persisté **réduit à ce dont l'orchestrateur s'est servi**

C'est **la** décision technique de ce module, et elle règle deux problèmes d'un coup :

| Appel | Blocs jetés | Blocs gardés |
|---|---|---|
| extraction | les `text` | tout le reste, `tool_use` compris |
| rédaction | les `tool_use` | tout le reste, `text` compris |

Ce qui n'est ni l'un ni l'autre — un bloc `thinking`, que `claude-sonnet-5` émet sans qu'on
le sollicite (correctif de l'étape 12) — **passe tel quel**, comme chez l'agent. Le jeter
ferait des messages vides sur les réponses qui n'en portent que.

**Le texte de l'extraction est jeté** — ni émis, ni validé, ni persisté. Le seul texte qui
part au client vient de l'appel nº2. Le persister le ferait réapparaître au rechargement :
`prose.py` rend tout bloc `text` d'un message assistant non refusé, et le client verrait
une phrase qu'il n'a jamais lue. C'est exactement la brèche de §2 que le correctif de
l'étape 11 a fermée pour les textes refusés.

**Les `tool_use` de la rédaction sont jetés** pour une seconde raison, mécanique : un
`tool_use` persisté sans son `tool_result` rend l'historique **irrecevable par l'API au
tour suivant** (piège technique nº1 de l'étape 8). Les exécuter serait pire — la rédaction
n'est pas un point d'orchestration, et un `ask_clarification` émis là verrait sa question
rendue comme de la prose par `prose.py` sans avoir jamais atteint le client.

*Alternative écartée — les apparier avec un `tool_result` de refus.* L'historique reste
valide et le message reste intact, ce qui est plus fidèle. Écartée parce qu'elle ne règle
pas le second problème : la question d'un `ask_clarification` resterait affichée au
rechargement.

### Les appels d'outils du code sont écrits comme ceux du modèle

Chaque outil décidé par `decider()` produit **la même paire que chez l'agent** : un message
assistant portant un `tool_use`, puis un message `user` portant son `tool_result`. Les
identifiants sont dérivés du tour client et du rang.

⚠️ **Il n'y a pas d'alternative crédible, et il vaut la peine de dire pourquoi.**
`contexte_des_messages()` — donc tout le `ContexteFourni` du validateur — lit les faits
**dans les `tool_result` et nulle part ailleurs** (§9, arbitrage B). Persister les
résultats sous une autre forme viderait le contexte fourni, et chaque produit cité au tour
suivant deviendrait un grief. La forme n'est donc pas une commodité d'écriture : c'est ce
qui fait que les deux orchestrations partagent le même validateur.

Conséquence assumée : le message assistant qui porte ces `tool_use` est **synthétique** —
le modèle ne l'a pas écrit. Il ne porte aucune prose, `prose.py` n'en rend rien, et une
session commencée par une orchestration se reprend par l'autre.

### Les consignes ne sont pas persistées

L'appel nº2 reçoit une consigne écrite en Python — « répondez maintenant », « posez cette
question » —, et la relance de la garde une troisième depuis l'étape 21. Elles sont
ajoutées à `messages` pour l'appel, et **jamais à `tours`**.

⚠️ **Si elle l'était, `prose.py` la rendrait comme une parole du client** : c'est un bloc
`text` de rôle `user` sans `tool_result`, exactement la forme d'un message client. Le
message de reprise de l'étape 9 a le même problème et le résout par la reconnaissance du
gabarit ; ajouter une seconde reconnaissance rendrait `prose.py` heuristique, ce que sa
docstring refuse en toutes lettres.

Rien ne dépend de leur présence dans l'historique : elles ne portent aucun fait, et le tour
suivant n'a pas à les relire.
"""

from collections.abc import Generator, Sequence
from typing import Any

import structlog

from raiyon.agent.client import ClientLLM
from raiyon.agent.evenements import (
    Evenement,
    MotifDeRepli,
    QuestionPosee,
    Repli,
    Texte,
    TexteRejete,
)
from raiyon.machine.decision import (
    CIBLE_BUDGET,
    Action,
    DemanderPrecision,
    Rechercher,
    Rediger,
    Sonder,
    Suggerer,
    decider,
)
from raiyon.matching.moteur import ResultatMatching
from raiyon.orchestration.blocs import (
    ajouter_les_resultats,
    bloc_tool_result,
    catalogue_de,
    depouiller,
    empiler_la_reprise,
    evenement_de,
)
from raiyon.orchestration.contrat import (
    PHRASE_DE_REPLI,
    PHRASE_REPONSE_VIDE,
    ROLE_ASSISTANT,
    ROLE_CLIENT,
    IssueDuTour,
    TourProduit,
)
from raiyon.tools.erreurs import OutilRefuse
from raiyon.tools.etat import EtatSession
from raiyon.tools.outils import ResultatOutil, ResultatRecherche, ResultatSondage
from raiyon.tools.repartiteur import ContexteOutils, executer
from raiyon.tools.schema_outils import (
    NOM_ENREGISTRER,
    NOM_QUESTION,
    NOM_RECHERCHER,
    NOM_SONDER,
)
from raiyon.validateur.contexte import contexte_des_messages
from raiyon.validateur.repli import rediger
from raiyon.validateur.validateur import OrigineRejet, valider

logueur = structlog.get_logger(__name__)

CONSIGNE_DE_REDACTION = (
    "Répondez maintenant au client, en français, à partir des seuls résultats d'outils "
    "ci-dessus. N'appelez aucun outil : les outils de ce tour ont déjà été appelés, et "
    "leurs résultats sont ce que vous avez sous les yeux."
)
"""Ce qui déclenche l'appel nº2 sur le chemin de la recommandation.

Écrite en Python, jamais générée, et **jamais persistée** — voir la docstring du module.
Elle vit dans `messages` comme le message de reprise de l'étape 9 : un bloc `user` écrit
pour le modèle, que le client ne voit pas."""

CONSIGNE_DE_QUESTION = (
    "Posez maintenant au client **une seule question**, en français, portant sur {objet}. "
    "Donnez d'abord en une phrase ce que les résultats d'outils ci-dessus vous apprennent, "
    "puis posez la question. N'appelez aucun outil."
)
"""Le pendant sur le chemin de la question. `{objet}` est rempli par `_objet_de()`.

⚠️ **La consigne nomme l'objet, jamais la phrase** — c'est la frontière du jalon 1
appliquée à l'invite : `DemanderPrecision` porte un champ, le modèle écrit les mots. Une
consigne qui dicterait la question ferait de la relance un gabarit, ce que l'arbitrage de
l'étape a écarté : une machine qui gagne le critère nº1 en cessant de parler a changé de
produit."""

CONSIGNE_DE_RELANCE = (
    "Vous venez d'enregistrer une catégorie sans aucun critère. Relisez le dernier message "
    "du client : s'il énonce des critères de produit, appelez record_criteria pour les "
    "enregistrer. S'il n'en énonce aucun, n'appelez aucun outil."
)
"""Ce que la garde d'extraction ajoute avant sa relance, et **jamais à `tours`**.

Même statut que `CONSIGNE_DE_REDACTION` : un bloc `user` écrit en Python, que le client ne
voit pas — voir la docstring du module.

⚠️ **Elle nomme le défaut, jamais un critère.** Dicter les champs à chercher ferait écrire
au code ce que §2 confie au modèle, et un modèle à qui l'on suggère un critère finit par en
fabriquer un. C'est pour la même raison que la seconde branche — « s'il n'en énonce aucun,
n'appelez aucun outil » — est écrite : sans elle, la relance transformerait un tour
légitimement sans critère en tour à critère inventé."""

OBJET_DU_BUDGET = "le budget du client — quel montant il ne veut pas dépasser"
"""Le budget n'est pas un champ du registre (§3.10 lui donne une colonne), donc il n'a pas
de libellé français dans `ATTRIBUTS`. Il est nommé ici, une fois."""

NOM_DE_LOUTIL: dict[type[Action], str] = {
    Sonder: NOM_SONDER,
    Suggerer: NOM_QUESTION,
    Rechercher: NOM_RECHERCHER,
}
"""Action → nom de protocole. **Les noms viennent de `schema_outils`, jamais d'ici** : le
répartiteur est le seul endroit qui lie un nom du protocole à du code (étape 8,
arbitrage 3), et cette table le désigne sans le doubler."""


def repondre_machine(
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
    """Conduit un tour client par la machine à états. **Signature de `repondre`.**

    `max_iterations` borne la boucle `decider()`. Le graphe est fini — trois décisions au
    plus — donc la borne ne devrait jamais mordre, et c'est exactement pour cela qu'elle
    existe : échouer bruyamment plutôt que tourner.

    `max_regenerations` est le même budget **de tour** que chez l'agent, et il porte sur
    l'appel nº2 : un texte refusé deux fois se replie sur template.

    La garde d'extraction, elle, n'a **pas** de budget réglable : une relance, en dur. Un
    garde-fou dont on peut monter le compteur devient une boucle le jour où quelqu'un le
    monte.
    """
    outils_extraction = [outil for outil in outils if outil.get("name") == NOM_ENREGISTRER]
    if not outils_extraction:
        # Avant tout appel API : un `tools` vide avec des `tool_use` dans `messages` est
        # une erreur de l'API, et il vaut mieux la nommer ici que la lire dans un 400.
        raise ValueError(
            f"la machine expose {NOM_ENREGISTRER!r} à l'appel d'extraction, et il n'est pas "
            f"dans le schéma reçu : {sorted(str(outil.get('name')) for outil in outils)}"
        )

    messages: list[dict[str, Any]] = [
        *historique,
        {"role": ROLE_CLIENT, "content": [{"type": "text", "text": message_client}]},
    ]
    tours: list[TourProduit] = []
    outils_appeles: list[str] = []
    appels_modele = 0
    derniere_recherche: ResultatMatching | None = None
    dernier_sondage: ResultatSondage | None = None

    # ----------------------------------------------------------------- #
    # Appel nº1 — l'extraction, et au plus une relance (garde de l'étape 21)
    # ----------------------------------------------------------------- #
    relances = 0
    while True:
        reponse = client.repondre(systeme=systeme, outils=outils_extraction, messages=messages)
        appels_modele += 1
        extraction = depouiller(reponse.blocs)

        if not extraction.appels:
            logueur.info(
                "machine.extraction_sans_outil",
                fin=reponse.fin,
                texte_jete=bool(extraction.texte),
                relance=bool(relances),
                consequence="l'état passe inchangé à decider() — ce tour n'apporte aucun critère",
            )
        else:
            if extraction.texte:
                logueur.info(
                    "machine.texte_dextraction_jete",
                    longueur=len(extraction.texte),
                    consequence="seul l'appel nº2 parle au client",
                )
            _poser(messages, tours, ROLE_ASSISTANT, _sans(reponse.blocs, "text"))
            resultats: list[dict[str, Any]] = []
            for appel in extraction.appels:
                nom = str(appel.get("name", ""))
                outils_appeles.append(nom)
                etat, resultat = executer(nom, appel.get("input") or {}, etat, contexte)
                resultats.append(bloc_tool_result(str(appel.get("id", "")), resultat))
                if isinstance(resultat, OutilRefuse):
                    continue
                evenement = evenement_de(resultat)
                if evenement is not None:
                    yield evenement
            ajouter_les_resultats(messages, tours, resultats)

        if relances or not _extraction_muette(extraction.appels):
            break
        relances += 1
        logueur.warning(
            "machine.extraction_relancee",
            tour_client=contexte.tour_client,
            consequence="un appel de plus sur ce tour — le plancher de 2,00 ne tient pas ici",
        )
        # ⚠️ Dans `messages`, jamais dans `tours` — voir la docstring du module. Elle vient
        # **après** le `tool_result` du premier enregistrement : ce que le modèle relit
        # n'est pas seulement son appel, c'est le `criteres: []` que la couche outils lui
        # a renvoyé. Deux messages `user` de suite, comme sur le chemin de la rédaction.
        messages.append(
            {"role": ROLE_CLIENT, "content": [{"type": "text", "text": CONSIGNE_DE_RELANCE}]}
        )

    # ----------------------------------------------------------------- #
    # La boucle de décision — aucun appel modèle
    # ----------------------------------------------------------------- #
    dernier: ResultatOutil | None = None
    action: Action = Rediger()
    decisions = 0
    while decisions < max_iterations:
        decisions += 1
        action = decider(etat, dernier)
        if isinstance(action, Rediger | DemanderPrecision):
            break

        nom = NOM_DE_LOUTIL[type(action)]
        entree = {"champs": list(action.champs)} if isinstance(action, Sonder) else {}
        identifiant = f"mach{contexte.tour_client}_{decisions}"
        _poser(
            messages,
            tours,
            ROLE_ASSISTANT,
            [{"type": "tool_use", "id": identifiant, "name": nom, "input": entree}],
        )
        outils_appeles.append(nom)
        etat, resultat = executer(nom, entree, etat, contexte)
        ajouter_les_resultats(messages, tours, [bloc_tool_result(identifiant, resultat)])

        if isinstance(resultat, OutilRefuse):
            # Un outil que le **code** a appelé et que la couche outils refuse est un
            # défaut de `decider()`, pas une maladresse du modèle : il n'y a personne pour
            # corriger l'appel. On clôt le tour proprement plutôt que de reboucler.
            logueur.warning(
                "machine.outil_refuse",
                outil=nom,
                code=resultat.code.value,
                message=resultat.message,
                consequence="tour clos par un message de repli écrit en Python",
            )
            yield Repli(
                PHRASE_DE_REPLI, appels_modele, tuple(outils_appeles), MotifDeRepli.MAX_ITERATIONS
            )
            return IssueDuTour(etat, tuple(tours), appels_modele, tuple(outils_appeles))

        dernier = resultat
        if isinstance(resultat, ResultatRecherche):
            derniere_recherche = resultat.resultat
        elif isinstance(resultat, ResultatSondage):
            dernier_sondage = resultat
        evenement = evenement_de(resultat)
        if evenement is not None:
            yield evenement
    else:
        # La borne a mordu : le graphe est fini, donc c'est un défaut de `decider()`.
        logueur.warning(
            "machine.max_iterations",
            decisions=decisions,
            outils_appeles=outils_appeles,
            consequence="tour clos par un message de repli écrit en Python",
        )
        yield Repli(
            PHRASE_DE_REPLI, appels_modele, tuple(outils_appeles), MotifDeRepli.MAX_ITERATIONS
        )
        return IssueDuTour(etat, tuple(tours), appels_modele, tuple(outils_appeles))

    # ----------------------------------------------------------------- #
    # Appel nº2 — la rédaction, ou la question
    # ----------------------------------------------------------------- #
    # Le contexte fourni se lit sur les `tool_result` **déjà** dans la conversation, comme
    # chez l'agent : ce sont exactement les faits que le modèle a sous les yeux en
    # écrivant. Il est cumulatif sur la session, historique relu compris (étape 9,
    # arbitrage B).
    fourni = contexte_des_messages(messages)
    question = isinstance(action, DemanderPrecision)
    origine = OrigineRejet.QUESTION if question else OrigineRejet.TEXTE
    consigne = (
        CONSIGNE_DE_QUESTION.format(objet=_objet_de(action, etat))
        if isinstance(action, DemanderPrecision)
        else CONSIGNE_DE_REDACTION
    )
    # ⚠️ Dans `messages`, jamais dans `tours` — voir la docstring du module.
    messages.append({"role": ROLE_CLIENT, "content": [{"type": "text", "text": consigne}]})

    regenerations = 0
    while True:
        reponse = client.repondre(systeme=systeme, outils=outils_extraction, messages=messages)
        appels_modele += 1
        redigee = depouiller(reponse.blocs)
        if redigee.appels:
            logueur.info(
                "machine.outil_appele_a_la_redaction",
                outils=[str(appel.get("name")) for appel in redigee.appels],
                consequence="bloc jeté — la rédaction n'est pas un point d'orchestration",
            )
        persistes = _sans(reponse.blocs, "tool_use")
        if persistes:
            _poser(messages, tours, ROLE_ASSISTANT, persistes)

        if not redigee.texte:
            logueur.warning(
                "machine.reponse_vide",
                types_de_blocs=sorted({str(bloc.get("type")) for bloc in reponse.blocs}),
                fin=reponse.fin,
                consequence="tour clos par un message de repli écrit en Python",
            )
            yield Repli(
                PHRASE_REPONSE_VIDE,
                appels_modele,
                tuple(outils_appeles),
                MotifDeRepli.REPONSE_VIDE,
            )
            return IssueDuTour(etat, tuple(tours), appels_modele, tuple(outils_appeles))

        verdict = valider(redigee.texte, fourni)
        if not verdict.griefs:
            break

        regenerations += 1
        yield TexteRejete(redigee.texte, verdict.griefs, regenerations, origine)
        logueur.warning(
            "machine.texte_rejete",
            origine=origine.value,
            tentative=regenerations,
            budget=max_regenerations,
            codes=[grief.code.value for grief in verdict.griefs],
            consequence=(
                "repli sur template"
                if regenerations > max_regenerations
                else "une régénération est demandée"
            ),
        )
        # La reprise est empilée sur **tous** les chemins, y compris celui qui abandonne :
        # c'est l'invariant dont `prose.py` dépend — un message assistant refusé est
        # toujours suivi d'une reprise —, et c'est son oubli qui a coûté le correctif de
        # l'étape 11. Aucun `tool_result` ne l'accompagne : le message refusé n'en portait
        # pas, la rédaction n'appelant aucun outil.
        empiler_la_reprise(messages, tours, [], verdict)
        if regenerations > max_regenerations:
            yield Repli(
                # Jamais le template quand on interrogeait : on ne répond pas par un
                # classement de produits à quelqu'un à qui on posait une question.
                rediger(
                    derniere_recherche,
                    origine,
                    None if question else catalogue_de(dernier_sondage),
                ),
                appels_modele,
                tuple(outils_appeles),
                MotifDeRepli.VALIDATION,
            )
            return IssueDuTour(etat, tuple(tours), appels_modele, tuple(outils_appeles))

    if isinstance(action, DemanderPrecision):
        yield QuestionPosee(question=redigee.texte, champ_vise=_champ_vise(action))
        logueur.info("machine.tour_clos_par_question", appels_modele=appels_modele)
    else:
        yield Texte(redigee.texte)
        logueur.info("machine.fin_de_tour", appels_modele=appels_modele, fin=reponse.fin)
    return IssueDuTour(etat, tuple(tours), appels_modele, tuple(outils_appeles))


def _extraction_muette(appels: Sequence[dict[str, Any]]) -> bool:
    """L'extraction a-t-elle posé une catégorie **sans en tirer un seul critère** ?

    C'est le seul déclencheur de la garde, et il se lit sur les **arguments** du modèle,
    pas sur ce que la couche outils en a fait : un `record_criteria` refusé pour une autre
    raison est un autre défaut, celui de l'extraction atomique (§7), que cette étape ne
    traite pas.

    Trois décisions de rédaction, et chacune a une raison :

    * **le verdict porte sur la réponse entière, pas sur chaque appel.** Le modèle émet
      parfois deux `record_criteria` en parallèle — un pour le budget, un pour les critères
      (`budget_serre.2`, `desserrage_refuse.1` et `.3`, `question_de_domaine.3` dans les
      cassettes). Juger appel par appel ferait tirer la garde sur quatre tours qui ont
      parfaitement extrait ;
    * **un `retraits` non vide compte comme un critère.** Retirer un critère est une
      opération sur les critères, et le tour a donc bien apporté quelque chose ;
    * **la catégorie n'a pas à être neuve.** C'est tentant — un tour qui n'apporte
      légitimement aucun critère ne change pas de catégorie — et c'est faux : le tirage que
      la garde vise, `sur_specifie.3` au tour 2, repose `monitor` alors que la session y est
      déjà. Exiger la nouveauté ferait manquer le seul cas qu'on cherche à attraper.

    Un tour sans aucun `record_criteria` — « compare plutôt la 1 et la 3 » — ne pose aucune
    catégorie, donc ne déclenche rien. C'est le chemin normal de la docstring du module, et
    la garde n'y touche pas.
    """
    entrees = [
        appel.get("input") or {}
        for appel in appels
        if str(appel.get("name", "")) == NOM_ENREGISTRER
    ]
    if not any(entree.get("categorie") for entree in entrees):
        return False
    return not any(entree.get("criteres") or entree.get("retraits") for entree in entrees)


def _sans(blocs: Sequence[dict[str, Any]], genre: str) -> list[dict[str, Any]]:
    """Les blocs d'une réponse, moins ceux d'un type dont l'orchestrateur ne s'est pas servi.

    Deux appels, deux types retirés — voir le tableau de la docstring du module. Ce qui
    n'est ni `text` ni `tool_use` passe : un `thinking` seul doit rester, sans quoi le
    message persisté serait vide et l'API refuserait un bloc de contenu sans contenu.
    """
    return [dict(bloc) for bloc in blocs if bloc.get("type") != genre]


def _poser(
    messages: list[dict[str, Any]],
    tours: list[TourProduit],
    role: str,
    blocs: list[dict[str, Any]],
) -> None:
    """Ajoute un message **à la conversation et à ce qui sera persisté**, d'un seul geste.

    Les deux ne divergent qu'aux deux endroits que la docstring du module nomme — les
    consignes, qui ne vont que dans `messages`. Partout ailleurs, un seul appel garantit
    qu'un bloc envoyé au modèle est un bloc écrit en base, et réciproquement.
    """
    messages.append({"role": role, "content": blocs})
    tours.append(TourProduit(role, blocs))


def _champ_vise(action: DemanderPrecision) -> str | None:
    """`CIBLE_BUDGET` vers le `champ_vise` de `QuestionPosee`, qui ne connaît que le registre.

    La traduction se fait **ici, à la frontière**, et pas dans le type : `decider()` nomme
    toujours l'objet de sa question, et `None` y signifierait « je ne sais pas de quoi je
    parle ». Côté événement, `None` signifie « la question ne porte sur aucun attribut du
    catalogue », ce qui est exactement le cas du budget (§3.10 lui donne une colonne).
    """
    return None if action.champ == CIBLE_BUDGET else action.champ


def _objet_de(action: Action, etat: EtatSession) -> str:
    """Ce que la consigne nomme : le budget, ou un champ avec son libellé français.

    Le libellé vient du registre d'attributs — le même que celui qui fait dire « fréquence
    de rafraîchissement » à `ChampDiscriminant` (arbitrage I de l'étape 6 : le français est
    du vocabulaire, pas des phrases). Un champ absent du registre est rendu tel quel plutôt
    que de faire échouer un tour pour un libellé.
    """
    if not isinstance(action, DemanderPrecision) or action.champ == CIBLE_BUDGET:
        return OBJET_DU_BUDGET
    from raiyon.matching.attributs import ATTRIBUTS

    categorie = etat.categorie_courante
    attribut = ATTRIBUTS[categorie].get(action.champ) if categorie is not None else None
    return action.champ if attribut is None else f"{attribut.libelle_fr} ({action.champ})"
