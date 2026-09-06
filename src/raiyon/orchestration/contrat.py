"""Ce que les deux orchestrations partagent **avant** de diverger : leur type de retour,
les deux rôles de l'API, les deux phrases de repli écrites en Python.

### Pourquoi ce module existe, et ce qu'il corrige

Jusqu'à l'étape 16, ces six noms vivaient dans `agent/boucle.py`. Le module neutre — celui
qui porte le `Protocol` `Orchestrateur` et qui prétend ne connaître aucune des deux
orchestrations — faisait `from raiyon.agent.boucle import IssueDuTour` : **le contrat commun
aux deux orchestrations était défini à l'intérieur de l'une d'elles**, et `machine/` en
dépendait pour son propre type de retour.

C'est plus qu'une gêne de lecture. Le fondement de l'étape 15 est que le harnais puisse
mettre les deux orchestrations à la même place ; une comparaison dont l'un des deux termes
définit le vocabulaire de l'autre est déjà déséquilibrée sur le papier, même quand le code
tourne.

⚠️ **Aucune de ces définitions n'a changé en déménageant.** Le déplacement est vérifié par
ce qui ne bouge pas : `make check` rend le même compte, et les cinq documents de
`docs/eval/` se régénèrent à l'identique — pour les deux orchestrations à la fois.
"""

from dataclasses import dataclass
from typing import Any

from raiyon.tools.etat import EtatSession

PHRASE_DE_REPLI = (
    "Je m'y perds un peu — pouvez-vous me redire ce que vous cherchez, et pour quel usage ?"
)
"""Écrite en Python, jamais générée. Voir l'alternative écartée dans `Repli`.

Celle du repli de validation vit dans `validateur/repli.py` : deux situations, donc deux
phrases. Ici le modèle a tourné en rond ; là il a affirmé ce qu'il n'avait pas."""

PHRASE_REPONSE_VIDE = (
    "Je n'ai rien produit en réponse à votre message — c'est de mon côté, pas du vôtre. "
    "Pouvez-vous me le redire ?"
)
"""Écrite en Python, jamais générée (correctif de l'étape 12). Troisième phrase du lot.

Elle ne renvoie pas le client à sa formulation — le message était très bien — mais dit
d'où vient la faute. C'est la seule des trois qui décrit un défaut **de l'orchestration**,
et la seule où l'on peut le dire au client sans lui montrer de mécanique interne.

⚠️ Elle ne cite aucun chiffre et aucun produit : elle n'a pas de contexte fourni à
respecter, puisqu'elle est rendue quand le modèle n'a rien produit du tout."""

FINS_INTERROMPUES: dict[str, str] = {
    "max_tokens": "le plafond de jetons a coupé la génération",
    "refusal": "un classificateur de sécurité a interrompu la génération",
}
"""Les `stop_reason` qui disent **une génération coupée au milieu d'un message**.

⚠️ **Les deux sont la même famille, et le dépôt n'en testait qu'un.** `max_tokens` était
surveillé depuis l'étape 8 ; `refusal` ne l'était par personne, et il est arrivé — une
fois, au premier tir réel de l'étape 17 : 453 jetons, 20,8 secondes, et un
`ask_clarification` dont les arguments étaient `{}`. **Un appel d'outil coupé dans ses
arguments a exactement la forme d'une troncature**, et c'est ce qui rattache les deux.

Rien n'est traité différemment : les deux restent opaques pour l'orchestration, qui
continue son chemin comme avant. Ils sont **nommés et comptés**, ce qui est tout ce que
l'étape 17 demande — et ce qui manquait pour que la seconde soit seulement visible.

*Alternative écartée — replier sur `refusal`.* Elle changerait le comportement sur la foi
d'une occurrence. Ici la boucle s'est rattrapée seule : le répartiteur a refusé l'argument
manquant et le modèle a corrigé au tour suivant. Décider d'un repli demande de savoir à
quelle fréquence ça arrive, ce que la colonne `stop_reason` d'`appels_modele` dira."""

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
    """Ce qu'une orchestration laisse derrière elle, et que seule la persistance consomme."""

    etat: EtatSession
    tours: tuple[TourProduit, ...]
    iterations: int
    outils_appeles: tuple[str, ...]


def signaler_si_interrompue(
    logueur: Any,  # noqa: ANN401 — un `structlog.BoundLogger`, sans faire entrer le type ici
    evenement: str,
    fin: str,
    *,
    consequence: str,
    **champs: Any,  # noqa: ANN401 — les champs libres d'une ligne structlog
) -> None:
    """Un `WARNING` quand la génération a été coupée, et rien sinon. **Aucun effet de bord.**

    Le logueur est passé par l'appelant plutôt que créé ici : c'est son nom de module qui
    doit apparaître dans la ligne, sans quoi `boucle.` et `machine.` se confondraient dans
    un journal où l'on cherche justement laquelle des deux a été coupée.
    """
    if fin not in FINS_INTERROMPUES:
        return
    logueur.warning(
        evenement,
        fin=fin,
        cause=FINS_INTERROMPUES[fin],
        consequence=consequence,
        **champs,
    )
