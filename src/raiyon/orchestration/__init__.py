"""Deux orchestrations, une signature, et **c'est mypy qui vérifie que c'en est une**.

`session.tour()` ne connaît plus `repondre` : il demande à ce module qui conduit le tour, et
reçoit une fonction. Le choix se lit dans `Settings.orchestration`, et nulle part ailleurs —
`config.py` reste le point unique de lecture de l'environnement.

Le paquet porte trois modules, et la façade est celui-ci :

| Module | Contenu |
|---|---|
| `__init__.py` | le `Protocol`, la table, `repondre_en_vigueur()` |
| `contrat.py` | `IssueDuTour`, `TourProduit`, les rôles, les phrases de repli |
| `blocs.py` | les blocs de conversation que les deux orchestrations écrivent pareil |

---

### Pourquoi un `Protocol` plutôt qu'un commentaire

« Les deux orchestrations ont la même signature » est une affirmation qui se périme au
premier paramètre ajouté d'un côté. Écrite comme un `Protocol` et posée en type de retour
de `repondre_en_vigueur()`, elle devient une **vérification** : mypy refuse la fonction qui
n'est pas substituable, et il la refuse au bon endroit — celui qui prétend rendre l'une ou
l'autre.

C'est ce qui rend le fondement de l'étape 15 vérifiable plutôt que déclaré : la comparaison
de deux orchestrations n'a de sens que si le harnais peut les mettre à la même place.
`raiyon/eval/executeur.py` ne connaît que la signature de `session.tour()`, et
`session.tour()` ne connaît que celle-ci.

⚠️ **`boucle.repondre` ne change pas d'une ligne.** Le `Protocol` a été écrit **d'après**
elle, pas l'inverse : c'est la machine qui devait s'y conformer, et elle s'y conforme.

---

### ⚠️ Pourquoi la table est une fonction, et pas un dictionnaire de module

Elle en était un jusqu'à l'étape 16, qui a fait de ce module un paquet. Le paquet crée un
cycle que la règle « les sous-modules n'importent jamais le `__init__` » **ne suffit pas** à
éviter, parce qu'elle ne dit rien du mécanisme réel : en Python, importer
`raiyon.orchestration.contrat` exécute d'abord `raiyon/orchestration/__init__.py`. Un
`import raiyon.agent.boucle` fait donc, dans cet ordre :

```
boucle (partiel)  →  orchestration.contrat  →  orchestration/__init__  →  boucle.repondre
                                                                          ↑ pas encore défini
```

— et lève `ImportError: cannot import name 'repondre' from partially initialized module`.
Cela casse tout ce qui charge `raiyon` par l'agent ou par la machine, `make check` compris.

Résoudre les deux fonctions **dans** `orchestrations()` ferme le cycle sans rien perdre :
mypy vérifie le littéral contre `dict[str, Orchestrateur]` exactement comme il vérifiait
l'annotation du dictionnaire de module, donc la substituabilité reste contrôlée à la
compilation. Et c'est cohérent avec ce que `repondre_en_vigueur()` promettait déjà —
résoudre à chaque tour, ne rien mémoriser à l'import.

*Alternative écartée — sortir `contrat` et `blocs` du paquet, dans un `raiyon/partage/`.*
Le graphe redevient acyclique sans rien rendre paresseux, et la façade ne bouge pas d'une
ligne. Écartée parce qu'elle sépare le contrat du module qui le porte : on chercherait
`IssueDuTour` sous `orchestration`, où le `Protocol` la nomme, et elle serait ailleurs.
"""

from collections.abc import Generator, Sequence
from typing import Any, Protocol

import structlog

from raiyon.agent.client import ClientLLM
from raiyon.agent.evenements import Evenement
from raiyon.config import get_settings
from raiyon.orchestration.contrat import IssueDuTour
from raiyon.tools.etat import EtatSession
from raiyon.tools.repartiteur import ContexteOutils

logueur = structlog.get_logger(__name__)


class Orchestrateur(Protocol):
    """Ce que `session.tour()` attend de celui qui conduit un tour client.

    Un générateur d'`Evenement` dont la valeur de retour est un `IssueDuTour` : c'est le
    contrat que trois consommateurs indépendants consomment déjà — la console, le fil SSE
    et l'exécuteur d'éval —, et c'est lui qui rend le harnais agnostique à l'orchestration.
    """

    def __call__(
        self,
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
    ) -> Generator[Evenement, None, IssueDuTour]: ...


def orchestrations() -> dict[str, Orchestrateur]:
    """Les deux, par le nom que `RAIYON_ORCHESTRATION` accepte.

    ⚠️ **C'est ici que mypy fait son travail** : une fonction dont la signature diverge du
    `Protocol` ne rentre pas dans ce dictionnaire, et l'erreur nomme le paramètre fautif.
    Les clés reprennent les valeurs du `Literal` de `Settings.orchestration` ; un test
    vérifie que les deux ensembles coïncident, parce qu'une valeur acceptée par la
    configuration et absente d'ici lèverait un `KeyError` au premier message d'une
    conversation.

    Les deux imports sont **dans** la fonction, et c'est structurel plutôt que cosmétique :
    voir la docstring du module. Ils ne coûtent rien après le premier — un accès à
    `sys.modules`.
    """
    from raiyon.agent.boucle import repondre
    from raiyon.machine.orchestrateur import repondre_machine

    return {
        "agent": repondre,
        "machine": repondre_machine,
    }


def repondre_en_vigueur() -> Orchestrateur:
    """L'orchestration configurée. **Résolue à chaque tour, pas au démarrage.**

    Un module chargé une fois garderait la valeur lue au premier import ; la résoudre ici
    fait que `get_settings.cache_clear()` suffit à basculer, ce dont les tests se servent et
    ce qui évite un second cache à invalider.
    """
    orchestration = get_settings().orchestration
    logueur.debug("orchestration.en_vigueur", orchestration=orchestration)
    return orchestrations()[orchestration]
