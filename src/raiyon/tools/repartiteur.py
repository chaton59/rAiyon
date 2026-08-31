"""Nom d'outil → fonction. **Pur, et dans `raiyon.tools`, pas dans `raiyon.agent`.**

### L'arbitrage : le répartiteur vit du côté des outils (arbitrage 3 de l'étape 8)

*Alternative écartée — le répartiteur dans `agent/`.* La couche outils resterait « cinq
fonctions », et la boucle porterait sa propre table de correspondance. Elle est écartée
parce que `record_criteria` s'écrirait alors dans deux modules de deux couches — la
constante ici, la branche là-bas — et c'est exactement le motif que `en_tool_result()`
refuse : **un seul endroit où un nom du protocole est écrit.**

Conséquence directe et vérifiée : ce module n'importe rien d'`anthropic`, et le test
d'isolation de `tests/tools/` le prend automatiquement en compte, puisqu'il découvre les
modules du paquet sur le disque. La table de correspondance entre le protocole et le code
se teste donc **sans clé API**.

### Ce que rend `executer()`, et pourquoi l'état sort avec le résultat

`(EtatSession, ResultatOutil | OutilRefuse)`. L'état sort **toujours**, y compris sur un
refus — inchangé dans ce cas. C'est ce qui permet à l'appelant d'écrire un réenchaînement
sans condition :

```python
etat, resultat = executer(nom, entree, etat, contexte)
```

⚠️ **C'est une exigence de correction, pas de style.** Chaque outil rend un `etat`, y
compris `rechercher_produits` qui y pose `recherche_du_tour`. Si l'appelant ne réenchaîne
pas l'état d'un `tool_use` au suivant **à l'intérieur d'un même message assistant**, la
garde « un tour, une catégorie » (arbitrage E de l'étape 7) ne se déclenche jamais.

### Deux natures d'entrée invalide, un seul type de sortie

`OutilRefuse` levé par un outil et `ValidationError` levée par Pydantic sont deux choses
différentes en Python et une seule chose pour le modèle : *ton appel n'est pas passé,
voilà pourquoi, corrige*. Le répartiteur les ramène donc toutes deux à un `OutilRefuse`,
sans lever.

La conversion `ValidationError` → `OutilRefuse` porte le code `VALEUR_ILLISIBLE` et
**recopie le message de Pydantic tel quel** : il nomme le champ fautif et la contrainte
violée, ce qu'une reformulation perdrait. C'est la même règle que celle d'`erreurs.py`
sur les messages du registre — deux rédactions d'une même règle finissent par en dire
deux choses.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog
from pydantic import ValidationError

from raiyon.matching.depot import DepotProduits
from raiyon.tools.erreurs import CodeRefus, OutilRefuse
from raiyon.tools.etat import EtatSession
from raiyon.tools.outils import (
    ArgumentsEnregistrement,
    ArgumentsPrecision,
    ArgumentsSondage,
    ResultatOutil,
    demander_precision,
    enregistrer_criteres,
    question_suivante,
    rechercher_produits,
    sonder_catalogue,
)
from raiyon.tools.schema_outils import (
    NOM_ENREGISTRER,
    NOM_PRECISION,
    NOM_QUESTION,
    NOM_RECHERCHER,
    NOM_SONDER,
)

logueur = structlog.get_logger(__name__)

NOMS: tuple[str, ...] = (NOM_ENREGISTRER, NOM_SONDER, NOM_QUESTION, NOM_RECHERCHER, NOM_PRECISION)
"""Les cinq noms, dans l'ordre du schéma. Un test vérifie qu'ils correspondent
exactement à ceux que `schema_des_outils()` déclare : une divergence rendrait un outil
annoncé au modèle et injoignable, ou l'inverse."""


@dataclass(frozen=True, slots=True)
class ContexteOutils:
    """Ce dont les outils ont besoin et qui ne vient pas du modèle.

    `tour_client` porte le jeton de parole (§3.17) et la garde « un tour, une catégorie ».
    Il est **fourni**, jamais compté ici : la couche outils n'a aucune notion d'horloge,
    et l'étape 8 le prend au `numero` de la ligne `tours_conversation` du message client
    (arbitrage 9), ce qui le rend stable au redémarrage.

    `tolerance` est injectable pour la même raison qu'ailleurs dans la couche : aucun
    test pur n'a besoin de `.env`. `None` signifie « lire la configuration ».
    """

    depot: DepotProduits
    tour_client: int
    tolerance: Decimal | None = None


def executer(
    nom: str, entree: Mapping[str, Any], etat: EtatSession, contexte: ContexteOutils
) -> tuple[EtatSession, ResultatOutil | OutilRefuse]:
    """Parse, appelle, et rend le **nouvel** état avec le résultat.

    Sur refus — outil inconnu, arguments invalides, invariant violé — l'état rendu est
    celui reçu, **inchangé**. Un appel refusé ne laisse aucune trace dans la session :
    c'est ce qui permet à la boucle d'enchaîner les `tool_use` suivants d'un même message
    sans avoir à distinguer les cas.
    """
    try:
        resultat = _appeler(nom, entree, etat, contexte)
    except OutilRefuse as refus:
        logueur.info("repartiteur.refus", outil=nom, code=refus.code.value, message=refus.message)
        return etat, refus
    except ValidationError as erreur:
        # Le message de Pydantic part verbatim : il nomme le champ et la contrainte.
        # Le nom `illisible` plutôt que `refus` : Python supprime la variable d'un
        # `except ... as` en sortant du bloc, et mypy refuse de la réutiliser ici.
        illisible = OutilRefuse(CodeRefus.VALEUR_ILLISIBLE, str(erreur))
        logueur.info("repartiteur.arguments_invalides", outil=nom, message=illisible.message)
        return etat, illisible

    logueur.info("repartiteur.appel", outil=nom, terminal=resultat.terminal)
    return resultat.etat, resultat


def _appeler(
    nom: str, entree: Mapping[str, Any], etat: EtatSession, contexte: ContexteOutils
) -> ResultatOutil:
    """La table de correspondance. **Le seul endroit qui lie un nom du protocole au code.**"""
    arguments = dict(entree)
    if nom == NOM_ENREGISTRER:
        return enregistrer_criteres(
            etat, ArgumentsEnregistrement(**arguments), tour_client=contexte.tour_client
        )
    if nom == NOM_SONDER:
        return sonder_catalogue(
            etat, contexte.depot, ArgumentsSondage(**arguments), tolerance=contexte.tolerance
        )
    if nom == NOM_QUESTION:
        _refuser_tout_argument(nom, arguments)
        return question_suivante(etat, contexte.depot, tolerance=contexte.tolerance)
    if nom == NOM_RECHERCHER:
        _refuser_tout_argument(nom, arguments)
        return rechercher_produits(
            etat,
            contexte.depot,
            tour_client=contexte.tour_client,
            tolerance=contexte.tolerance,
        )
    if nom == NOM_PRECISION:
        return demander_precision(etat, ArgumentsPrecision(**arguments))

    raise OutilRefuse(
        CodeRefus.OUTIL_INCONNU,
        f"{nom!r} n'est pas un outil de cette session — outils disponibles : " + ", ".join(NOMS),
    )


def _refuser_tout_argument(nom: str, arguments: Mapping[str, Any]) -> None:
    """`suggest_next_question` et `search_products` ne prennent **rien**, et le disent.

    Ces deux-là n'ont pas de modèle Pydantic : leur schéma est un objet vide, il n'y a
    donc aucun champ à déclarer. Le contrôle est écrit ici plutôt qu'omis, et c'est un
    choix de sûreté, pas de symétrie.

    ⚠️ **Ignorer un argument surnuméraire serait le pire des trois comportements.** Un
    modèle qui appelle `search_products({"criteres": [...]})` et reçoit un résultat
    croirait que ses critères ont filtré la recherche ; il décrirait ensuite les produits
    comme satisfaisant des contraintes qui n'ont jamais été appliquées. Un refus coûte un
    aller-retour et dit au modèle où les critères entrent réellement (arbitrage C de
    l'étape 7).
    """
    if arguments:
        raise OutilRefuse(
            CodeRefus.VALEUR_ILLISIBLE,
            f"{nom} ne prend aucun argument : il lit l'état de la session. Reçu "
            + ", ".join(sorted(arguments))
            + f". Les critères, le budget et la catégorie entrent par {NOM_ENREGISTRER}.",
        )
