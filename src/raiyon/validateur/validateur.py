"""La porte d'entrée : `valider(texte, contexte) -> Verdict`. **Pure.**

C'est le niveau 2 de §3.11 — « la réponse est parsée, tous les IDs, prix et valeurs
chiffrées sont extraits et vérifiés contre le contexte réellement fourni » — et c'est
lui qui transforme « zéro hallucination » d'une intention en un test qui passe ou
échoue.

### `Grief` et `CodeGrief` sont définis dans `regles.py`, et réexportés ici

Ils sont **produits** par les règles ; les définir ici obligerait `regles.py` à importer
ce module, qui importe `regles.py` pour connaître `REGLES`. Le cycle n'a pas d'intérêt :
le nom d'import public reste `raiyon.validateur.validateur`, et c'est ce que le reste du
projet écrit.

### Ce module ne connaît ni la boucle, ni la régénération, ni le repli

Il dit **ce qui ne va pas**. Ce qu'on en fait — régénérer une fois, puis se replier sur
un template — est une décision de la boucle (arbitrage D), et la garder dehors est ce
qui permet à l'étape 12 de rejouer le validateur sur une cassette sans rejouer un tour.
"""

from dataclasses import dataclass
from enum import StrEnum

from raiyon.validateur.contexte import ContexteFourni
from raiyon.validateur.regles import REGLES, CodeGrief, Grief

__all__ = [
    "VERDICT_SANS_GRIEF",
    "CodeGrief",
    "Grief",
    "OrigineRejet",
    "Verdict",
    "valider",
]


class OrigineRejet(StrEnum):
    """Ce que le validateur a refusé. **Deux chemins de sortie, deux natures de défaut.**

    Ce n'est pas de la décoration : sans elle, l'étape 12 ne pourra pas dire *où* le
    modèle hallucine, et c'est précisément la métrique qui décide quoi corriger dans le
    prompt à l'étape 13. Une conversation contient beaucoup plus de questions que de
    recommandations — un taux global masquerait lequel des deux chemins fuit.

    Elle commande aussi le repli : on ne répond pas par un classement de produits à
    quelqu'un qu'on était en train d'interroger (voir `repli.rediger`).
    """

    TEXTE = "texte"
    """Les blocs `text` d'un message assistant, concaténés."""

    QUESTION = "question"
    """L'argument `question` d'`ask_clarification`. Elle n'est pas un bloc `text` : elle
    traverse le répartiteur et part au client verbatim, et c'est ce qui la rendait
    invisible au validateur jusqu'au correctif de l'étape 9."""


@dataclass(frozen=True, slots=True)
class Verdict:
    """Le résultat d'une validation : la liste des griefs, vide si le texte passe."""

    griefs: tuple[Grief, ...]

    @property
    def valide(self) -> bool:
        return not self.griefs

    def en_lignes(self) -> tuple[str, ...]:
        """Les griefs tels qu'ils partent au modèle, un par ligne."""
        return tuple(grief.en_ligne() for grief in self.griefs)


VERDICT_SANS_GRIEF = Verdict(())
"""Le verdict d'un message sans texte. Nommé plutôt que reconstruit : un message
assistant qui ne porte que des `tool_use` n'affirme rien, il n'y a rien à valider."""


def valider(texte: str, contexte: ContexteFourni) -> Verdict:
    """Relit un texte contre le contexte fourni et rend les griefs, dans l'ordre.

    Toutes les règles sont exécutées, **même après un premier grief** : un message de
    reprise qui ne signalerait que la première faute ferait payer une régénération par
    faute, alors que le budget est de une (arbitrage D).
    """
    griefs: list[Grief] = []
    for regle in REGLES:
        griefs.extend(regle(texte, contexte))
    return Verdict(tuple(griefs))
