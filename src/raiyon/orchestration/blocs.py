"""Les blocs de conversation que les deux orchestrations écrivent de la même façon.

### Six fonctions qui ont deux appelants, et qui portaient un nom privé

Elles ont été écrites dans `agent/boucle.py` à l'étape 8, quand il n'y avait qu'une
orchestration. L'étape 15 en a ajouté une seconde, qui les a importées **sous leur nom
privé** — `from raiyon.agent.boucle import _bloc_tool_result, ...` — parce que les
dupliquer aurait donné deux rédactions de la forme des blocs persistés et de l'invariant de
reprise dont `api/prose.py` dépend, c'est-à-dire le seul endroit du dépôt où cette maladie a
déjà coûté un correctif (étape 11).

L'étape 16 les sort de l'agent et **leur rend un nom public**, ce qu'elles auraient dû
porter dès qu'un second appelant est apparu. Le `_` ne disait plus « détail interne » : il
disait « quelqu'un a franchi la frontière ».

### Ce que ces fonctions garantissent, et pourquoi elles doivent rester communes

Elles tiennent trois propriétés que les deux orchestrations doivent partager pour rester
comparables — et pour que le reste du dépôt fonctionne indifféremment sur l'une ou l'autre :

* **la forme des `tool_result`** — `contexte_des_messages()` lit les faits du validateur
  dans ces blocs et nulle part ailleurs (étape 9, arbitrage B) ;
* **l'invariant de reprise** — un message assistant refusé est toujours suivi d'un message
  portant une reprise, ce dont `api/prose.py` dépend ;
* **la traduction résultat typé → événement**, sans laquelle les deux orchestrations
  n'émettraient pas les mêmes événements et ne se mesureraient plus sur les mêmes
  métriques.

⚠️ **Ce module reste dépendant de `raiyon.agent` par deux imports** — `agent.evenements`
pour les types d'événements, `agent.prompts` pour le texte du grief. Ni l'un ni l'autre
n'est de l'orchestration : `evenements.py` est le vocabulaire de sortie que les deux
partagent, `prompts.py` est un chargeur de fichiers. C'est un reste de nommage, pas un reste
de couplage. Il est écrit ici plutôt que tu : le corriger demanderait de déplacer deux
modules de plus, ce que cette étape s'interdit parce que sa preuve de neutralité tient à
ce qu'elle ne touche rien d'autre.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from raiyon.agent.evenements import (
    CriteresMisAJour,
    Evenement,
    ProduitsTrouves,
    QuestionSuggeree,
    Sondage,
)
from raiyon.agent.prompts import message_de_grief
from raiyon.orchestration.contrat import ROLE_CLIENT, TourProduit
from raiyon.tools.erreurs import OutilRefuse
from raiyon.tools.outils import (
    ResultatEnregistrement,
    ResultatOutil,
    ResultatQuestion,
    ResultatRecherche,
    ResultatSondage,
    en_tool_result,
)
from raiyon.validateur.repli import EtatDuCatalogue
from raiyon.validateur.validateur import Verdict

SEPARATEUR_DE_BLOCS = "\n"
"""Ce qui recolle les blocs `text` d'un même message assistant avant validation.

L'API n'en rend qu'un en pratique ; en rendre plusieurs et les valider séparément
laisserait passer une phrase coupée en deux blocs — et le découpage en phrases du
validateur, qui coupe déjà sur le saut de ligne, retrouve exactement la même granularité
que si les blocs étaient restés séparés."""


@dataclass
class Message:
    """Le dépouillement d'un message assistant : ses textes, ses appels d'outils."""

    textes: list[str] = field(default_factory=list)
    appels: list[dict[str, Any]] = field(default_factory=list)

    @property
    def texte(self) -> str:
        """Le texte du message, **entier**. C'est lui que le validateur relit."""
        return SEPARATEUR_DE_BLOCS.join(self.textes).strip()


def ajouter_les_resultats(
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


def empiler_la_reprise(
    messages: list[dict[str, Any]],
    tours: list[TourProduit],
    resultats: list[dict[str, Any]],
    verdict: Verdict,
) -> None:
    """Le bloc `user` qui suit **tout** message refusé : les `tool_result`, puis le grief.

    ⚠️ **C'est l'invariant dont `raiyon.api.prose` dépend**, et il est tenu ici et nulle
    part ailleurs : *un message assistant refusé est toujours suivi d'un message portant une
    reprise.* Cinq chemins l'appellent — chez l'agent, les deux qui régénèrent et les deux
    qui abandonnent faute de budget ; chez la machine, celui de la rédaction —, et c'est
    précisément parce que les deux qui abandonnent l'avaient oublié que le correctif de
    l'étape 11 a dû être écrit.

    Sur les chemins qui abandonnent, ce bloc n'est **jamais relu par le modèle** : le tour
    se termine juste après. Il n'existe donc que pour la trace persistée, et c'est ce qui le
    rend fragile — il ressemble à du code mort à qui ne lit pas `prose.py`.

    L'ordre n'est pas négociable : l'API exige les `tool_result` appairés **avant** tout
    autre contenu utilisateur. Quand le message fautif ne portait que du texte, `resultats`
    est vide et le bloc ne contient que le grief.
    """
    reprise = [*resultats, _bloc_de_grief(verdict)]
    messages.append({"role": ROLE_CLIENT, "content": reprise})
    tours.append(TourProduit(ROLE_CLIENT, reprise))


def _bloc_de_grief(verdict: Verdict) -> dict[str, Any]:
    """Le message de reprise, en bloc `text`. Le texte vit dans `prompts/grief.v1.md`.

    Le seul des sept à garder son nom privé : il n'a qu'un appelant, et il est dans ce
    module. C'est la règle que l'étape 16 applique — un `_` dit « un seul appelant, ici »,
    et rien d'autre.
    """
    return {"type": "text", "text": message_de_grief(verdict.en_lignes())}


def catalogue_de(sondage: ResultatSondage | None) -> EtatDuCatalogue | None:
    """Le sondage réduit à ce que le repli de domaine a besoin de dire.

    ⚠️ **La réduction est le point, pas une commodité.** `ResultatSondage` porte un
    `EtatSession` ; le passer tel quel à `repli.py` ferait entrer l'état de session dans le
    rédacteur de la réponse, ce que `evenements.py` interdit pour tout ce qui sort vers le
    client — et ferait importer `raiyon.tools` par `raiyon.validateur`.
    """
    if sondage is None:
        return None
    return EtatDuCatalogue(
        categorie=sondage.categorie,
        candidats=sondage.dans_le_budget,
        champs=sondage.champs,
    )


def evenement_de(resultat: ResultatOutil) -> Evenement | None:
    """Le résultat typé d'un outil vers l'événement qui lui correspond.

    `ResultatPrecision` n'a pas de ligne ici : il est terminal, et c'est l'orchestration qui
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


def bloc_tool_result(identifiant: str, resultat: ResultatOutil | OutilRefuse) -> dict[str, Any]:
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


def depouiller(blocs: Sequence[dict[str, Any]]) -> Message:
    """Sépare textes et appels d'outils. Tout autre type de bloc est ignoré.

    ~~Il n'y en a pas en v1 — le thinking étendu est écarté (arbitrage 12)~~ — mais un bloc
    inconnu qui ferait lever ici clorait une conversation pour une raison qui n'a rien à
    voir avec le produit.

    ⚠️ **La première moitié est fausse, et les cassettes de l'étape 12 le prouvent.**
    L'arbitrage 12 décrivait ce qu'on croyait **demander** et non ce qu'on **recevait** :
    `claude-sonnet-5` émettait des blocs `thinking`, avec leur `signature`, sans qu'on les
    sollicite. La ligne est barrée plutôt qu'effacée.

    ⚠️ **Et depuis l'étape 23, la phrase « aucun `thinking` n'est activé » est fausse deux
    fois.** Elle l'était déjà comme description du reçu ; elle l'est devenue comme
    description du demandé, `client_anthropic.py` envoyant désormais
    `thinking={"type": "adaptive", "display": "summarized"}`. Le raisonnement adaptatif
    était **actif par défaut depuis le premier appel du projet** — ce qui a changé n'est
    pas son existence mais sa visibilité. Ce module continue d'ignorer ces blocs, et c'est
    toujours le bon comportement.

    Conséquence directe, et c'est le correctif de l'étape 12 : un message qui ne porte
    **que** de tels blocs n'est plus une hypothèse d'école. `repondre()` le clôt désormais
    par un `Repli(REPONSE_VIDE)` au lieu de ne rien émettre, et `repondre_machine()` fait
    de même à la rédaction.
    """
    message = Message()
    for bloc in blocs:
        if bloc.get("type") == "text":
            message.textes.append(str(bloc.get("text", "")))
        elif bloc.get("type") == "tool_use":
            message.appels.append(bloc)
    return message
