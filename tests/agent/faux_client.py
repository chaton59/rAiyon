"""Un `ClientLLM` scripté : il rend des réponses écrites à l'avance, et il les compte.

### Ce qu'il teste, et ce qu'il ne teste pas (arbitrage 2 de l'étape 8)

⚠️ **§3.15 écarte les « mocks écrits à la main »**, au motif qu'on y teste ses propres
suppositions sur ce que le LLM répond. La nuance, et elle est réelle : ce faux client ne
teste pas *ce que le modèle répond* — il teste *ce que la boucle fait d'une réponse
donnée*. Enchaînement des appels, réenchaînement de l'état, terminalité, appairage des
`tool_result`, garde d'itérations : rien de tout cela ne dépend de la qualité du modèle,
et **rien de tout cela ne se voit dans une cassette**, qui rejoue les réponses du modèle
et non notre gestion de l'état.

Il ne remplace donc pas les cassettes de l'étape 12, qui restent au plan. Ce qu'il achète
est écrit au §7 des risques en toutes lettres : **un défaut de conduite du dialogue passe
entièrement à travers `make check`.**

### Il journalise ses appels, et c'est là que se vérifie le cache

`appels` garde le `systeme` et les `outils` de chaque appel. C'est ce qui permet de
constater que le préfixe est identique d'un appel à l'autre du même tour (arbitrage 7)
sans instrumenter le client réel.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from raiyon.agent.client import ReponseLLM


@dataclass(frozen=True, slots=True)
class Appel:
    """Ce que la boucle a envoyé, tel qu'elle l'a envoyé."""

    systeme: str
    outils: tuple[dict[str, Any], ...]
    messages: list[dict[str, Any]]


@dataclass
class FauxClient:
    """Rend `reponses` dans l'ordre. La dernière est répétée si la boucle insiste.

    Répéter la dernière plutôt que lever : c'est ainsi que se teste `max_iterations` —
    un modèle qui boucle indéfiniment est un modèle qui redit la même chose, et un script
    de huit réponses identiques dirait la même chose en moins lisible.
    """

    reponses: list[ReponseLLM]
    appels: list[Appel] = field(default_factory=list)

    @property
    def nombre_dappels(self) -> int:
        return len(self.appels)

    def repondre(
        self,
        *,
        systeme: str,
        outils: Sequence[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> ReponseLLM:
        # `messages` est copié : la boucle continue de l'allonger après cet appel, et
        # garder la référence ferait mentir toutes les assertions sur l'historique.
        self.appels.append(Appel(systeme, tuple(outils), [dict(m) for m in messages]))
        indice = min(len(self.appels) - 1, len(self.reponses) - 1)
        return self.reponses[indice]


# --------------------------------------------------------------------------- #
# Fabriques de blocs — pour que les scénarios se lisent comme des dialogues
# --------------------------------------------------------------------------- #


def texte(contenu: str) -> dict[str, Any]:
    return {"type": "text", "text": contenu}


def appel_outil(nom: str, entree: dict[str, Any] | None = None, *, id: str = "") -> dict[str, Any]:
    """Un bloc `tool_use`. L'identifiant est dérivé du nom si on ne le donne pas."""
    return {"type": "tool_use", "id": id or f"tu_{nom}", "name": nom, "input": entree or {}}


def message(*blocs: dict[str, Any], fin: str | None = None) -> ReponseLLM:
    """Un tour de parole du modèle. `fin` se déduit de la présence d'un `tool_use`."""
    if fin is None:
        fin = "tool_use" if any(bloc["type"] == "tool_use" for bloc in blocs) else "end_turn"
    return ReponseLLM(blocs=list(blocs), fin=fin)


# --------------------------------------------------------------------------- #
# L'assertion générique de l'étape — appliquée à tous les scénarios
# --------------------------------------------------------------------------- #


def verifier_appairage(tours) -> None:
    """Chaque `tool_use` a exactement un `tool_result`, même id, même ordre.

    ⚠️ **C'est le piège technique nº1 de l'étape 8** : l'API refuse un historique où un
    `tool_use` n'a pas son `tool_result` appairé. Comme les tours sont persistés et relus
    au message suivant, un orphelin ne casse pas le tour courant — il casse **le
    suivant**, et le message d'erreur parlera d'un identifiant de bloc.

    Cette fonction est appelée par tous les scénarios de `test_boucle.py` et de
    `test_terminal.py`, sans exception : c'est une propriété de la boucle, pas d'un cas.
    """
    attendus: list[str] = []
    obtenus: list[str] = []
    for tour in tours:
        for bloc in tour.blocs:
            if bloc.get("type") == "tool_use":
                attendus.append(bloc["id"])
            elif bloc.get("type") == "tool_result":
                obtenus.append(bloc["tool_use_id"])
    assert obtenus == attendus, (
        f"appairage rompu — tool_use {attendus}, tool_result {obtenus}. "
        "L'API refusera cet historique au tour client suivant."
    )
