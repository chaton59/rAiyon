"""Le contexte réellement fourni au modèle, **typé par provenance**. Pur.

### Pourquoi la provenance, et pas un sac de nombres (arbitrage B de l'étape 9)

C'est le piège de l'étape, et il était déjà visible dans la conversation de l'étape 8 :
`probe_catalog` avait rendu la fourchette `108.00 $` à `399.99 $`, et un écran valait
`108.00 $`. Un validateur qui vérifie « tout nombre cité apparaît quelque part dans un
`tool_result` » **accepterait** « cet écran est à 108 $ » alors que la borne d'un
sondage n'est le prix de personne — c'est l'oracle à prix que §7 nomme.

Les faits fournis sont donc rangés par **d'où ils viennent**, pas par ce qu'ils valent :

* `produits` — ce que `search_products` a rendu, `id` par `id` ;
* `hors_budget` — l'écart exact des produits de la zone de tolérance (§3.10) ;
* `prix` — le prix de chaque produit fourni, dérivé de `produits` ;
* `valeurs_de_specs` — les valeurs de caractéristiques **attribuables à un produit** ;
* `agregats` — les nombres fournis qui ne sont attribuables à **aucun** produit :
  bornes de prix, comptages, budget, valeurs atteignables d'un diagnostic.

⚠️ **Les valeurs des distributions de `probe_catalog` n'entrent pas dans
`valeurs_de_specs`.** Elles décrivent un ensemble, pas un produit : « 12 écrans sont à
165 Hz » ne rend pas vrai « celui-ci est à 165 Hz ». C'est ce qui fait échouer le piège
nº9 sur une version aplatie, et c'est la raison d'être de tout ce module.

### Il se lit sur les `tool_result`, et il est cumulatif sur la session

Pas sur un état interne : c'est ce qui garantit qu'il décrit **ce que le modèle a
réellement vu**. Et pas sur le tour : un produit rendu au tour 3 et cité au tour 6
(« je prends le premier ») est légitime, et un contexte par tour rejetterait la moitié
des conversations réelles.

Un `tool_result` marqué `is_error` est ignoré : un refus est un échange avec le modèle
(`erreurs.py`), il ne fournit aucun fait.

### Ce module lit les clés du protocole ; `en_tool_result()` est seule à les écrire

La lecture se fait **par clé**, jamais par nom d'outil. Deux raisons : le bloc
`tool_result` ne porte pas le nom de l'outil (il faudrait le rechercher dans le
`tool_use` appairé), et une clé identique dit la même chose où qu'elle apparaisse —
`fourchette_prix` est une fourchette dans `probe_catalog` comme dans le champ `budget`
de `suggest_next_question`. Les noms de clés sont donc rassemblés en constantes en tête
de module, en un seul endroit, comme de l'autre côté.
"""

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog
from pydantic import ValidationError

from raiyon.catalogue.schemas import ProduitEnBase
from raiyon.validateur.extraction import canonique, en_decimal

logueur = structlog.get_logger(__name__)

# --------------------------------------------------------------------------- #
# Les clés du protocole, en un seul endroit — miroir de `en_tool_result()`
# --------------------------------------------------------------------------- #

# ⚠️ `prix_usd` et `specs` n'y figurent pas, et c'est délibéré : ils sont lus par
# `ProduitEnBase`, qui les nomme déjà et les **valide** au passage. Les redéclarer ici
# créerait un second endroit où le nom d'un champ de produit peut changer — exactement
# ce que ce bloc de constantes existe pour éviter.
CLE_OK = "ok"
CLE_PRODUITS = "produits"
CLE_AU_DESSUS_DU_BUDGET = "au_dessus_du_budget"
CLE_PRODUIT = "produit"
CLE_ECART = "ecart_usd"
CLE_ID = "id"
CLE_BUDGET_USD = "budget_usd"
CLE_BUDGET = "budget"
CLE_FOURCHETTE = "fourchette_prix"
CLE_PLUS_BAS = "plus_bas"
CLE_PLUS_HAUT = "plus_haut"
CLE_CRITERES = "criteres"
CLE_VALEUR = "valeur"
CLE_CHAMPS = "champs"
CLE_CHAMP = "champ"
CLE_DISTRIBUTION = "distribution"
CLE_VALEURS = "valeurs"
CLE_EFFECTIF = "effectif"
CLE_ECARTES = "ecartes_faute_de_donnee"
CLE_DIAGNOSTIC = "diagnostic"
CLE_PROPOSITIONS = "propositions"
CLE_ATTEIGNABLE = "valeur_atteignable"
CLE_ROUVERTS = "produits_rouverts"

COMPTAGES = ("dans_le_budget", "dans_la_zone_de_tolerance", "candidats", "candidats_trouves")
"""Les entiers que les outils rendent et que l'agent a le droit de citer. Ce sont des
agrégats : ils décrivent un ensemble, jamais un produit."""

TYPE_TOOL_RESULT = "tool_result"
CLE_CONTENU = "content"
CLE_EST_ERREUR = "is_error"
CLE_TYPE = "type"


# --------------------------------------------------------------------------- #
# Le contexte
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ContexteFourni:
    """Ce que le code a mis sous les yeux du modèle, rangé par provenance."""

    produits: Mapping[str, ProduitEnBase]
    """`id` → produit, depuis `search_products`. La zone de tolérance en fait partie :
    ces produits ont bien été fournis, et leur nom comme leur `id` sont citables. C'est
    `hors_budget` qui porte la contrainte de présentation, pas l'absence d'entrée ici."""

    hors_budget: Mapping[str, Decimal]
    """`id` → `ecart_usd` exact, pour les produits de la zone de tolérance (§3.10)."""

    prix: Mapping[str, Decimal]
    """`id` → prix, dérivé de `produits`. Séparé de `agregats` : c'est toute la
    différence entre « ce produit coûte ça » et « il existe des produits à ce prix »."""

    valeurs_de_specs: frozenset[str]
    """Toute valeur de caractéristique **attribuable à un produit fourni**, en texte
    canonique (`canonique()` pour les nombres). Les valeurs enregistrées par
    `record_criteria` en font partie : ce sont celles que le client a dites, et que le
    code a renvoyées au modèle."""

    agregats: frozenset[Decimal]
    """Les nombres fournis qui ne sont le fait d'aucun produit : bornes de prix,
    comptages, budget, effectifs d'une distribution, valeurs atteignables d'un
    diagnostic."""

    @property
    def vide(self) -> bool:
        """Aucun fait fourni. Le modèle n'a alors le droit d'affirmer aucun chiffre."""
        return not (self.produits or self.valeurs_de_specs or self.agregats)


CONTEXTE_VIDE = ContexteFourni({}, {}, {}, frozenset(), frozenset())


def contexte_des_messages(messages: Sequence[Mapping[str, Any]]) -> ContexteFourni:
    """Le contexte fourni, lu sur les `tool_result` d'une conversation entière.

    `messages` est la liste au format de l'API — historique relu en base compris. Un
    message assistant ne porte aucun `tool_result` : l'ordre d'ajout du message en
    cours de validation est donc sans effet sur le résultat.
    """
    return contexte_des_resultats(_charges_utiles(messages))


def contexte_des_resultats(charges: Iterable[Mapping[str, Any]]) -> ContexteFourni:
    """Le contexte fourni, à partir des charges utiles déjà décodées.

    C'est la porte d'entrée des tests : un dictionnaire suffit, il n'y a ni base, ni
    clé, ni SDK dans le chemin.
    """
    accumulateur = _Accumulateur()
    for charge in charges:
        if charge.get(CLE_OK) is not True:
            continue
        accumulateur.absorber(charge)
    return accumulateur.figer()


def _charges_utiles(messages: Sequence[Mapping[str, Any]]) -> Iterator[Mapping[str, Any]]:
    """Les charges utiles des `tool_result` réussis, dans l'ordre de la conversation."""
    for message in messages:
        contenu = message.get(CLE_CONTENU)
        if not isinstance(contenu, list):
            continue
        for bloc in contenu:
            if not isinstance(bloc, Mapping) or bloc.get(CLE_TYPE) != TYPE_TOOL_RESULT:
                continue
            if bloc.get(CLE_EST_ERREUR):
                continue
            charge = _decoder(bloc.get(CLE_CONTENU))
            if charge is not None:
                yield charge


def _decoder(contenu: object) -> Mapping[str, Any] | None:
    """Le contenu d'un `tool_result`, qui est du JSON en chaîne (`_bloc_tool_result`)."""
    if isinstance(contenu, Mapping):
        return contenu
    if not isinstance(contenu, str):
        return None
    try:
        charge = json.loads(contenu)
    except json.JSONDecodeError:
        # Un `tool_result` illisible n'est pas un incident du validateur : il ne
        # fournit simplement aucun fait, et le texte sera jugé sans lui — c'est-à-dire
        # plus sévèrement, jamais plus laxement.
        logueur.warning("validateur.tool_result_illisible", taille=len(contenu))
        return None
    return charge if isinstance(charge, Mapping) else None


# --------------------------------------------------------------------------- #
# L'accumulation, clé par clé
# --------------------------------------------------------------------------- #


class _Accumulateur:
    """L'état de construction du contexte. Mutable ici, figé à la sortie."""

    def __init__(self) -> None:
        self.produits: dict[str, ProduitEnBase] = {}
        self.hors_budget: dict[str, Decimal] = {}
        self.prix: dict[str, Decimal] = {}
        self.specs: set[str] = set()
        self.agregats: set[Decimal] = set()

    def figer(self) -> ContexteFourni:
        return ContexteFourni(
            produits=dict(self.produits),
            hors_budget=dict(self.hors_budget),
            prix=dict(self.prix),
            valeurs_de_specs=frozenset(self.specs),
            agregats=frozenset(self.agregats),
        )

    def absorber(self, charge: Mapping[str, Any]) -> None:
        """Range une charge utile d'outil selon les clés qu'elle porte."""
        for brut in _liste(charge.get(CLE_PRODUITS)):
            self._produit(brut)

        for brut in _liste(charge.get(CLE_AU_DESSUS_DU_BUDGET)):
            if not isinstance(brut, Mapping):
                continue
            produit = self._produit(brut.get(CLE_PRODUIT))
            ecart = _nombre(brut.get(CLE_ECART))
            if produit is not None and ecart is not None:
                self.hors_budget[produit.id] = ecart

        self._fourchette(charge.get(CLE_FOURCHETTE))
        budget = charge.get(CLE_BUDGET)
        if isinstance(budget, Mapping):
            self._fourchette(budget.get(CLE_FOURCHETTE))

        self._agregat(charge.get(CLE_BUDGET_USD))
        for cle in COMPTAGES:
            self._agregat(charge.get(cle))

        ecartes = charge.get(CLE_ECARTES)
        if isinstance(ecartes, Mapping):
            for compte in ecartes.values():
                self._agregat(compte)

        for critere in _liste(charge.get(CLE_CRITERES)):
            if isinstance(critere, Mapping):
                self._valeur_de_spec(critere.get(CLE_VALEUR))

        for distribution in _liste(charge.get(CLE_CHAMPS)):
            self._distribution(distribution)
        champ = charge.get(CLE_CHAMP)
        if isinstance(champ, Mapping):
            self._distribution(champ.get(CLE_DISTRIBUTION))

        diagnostic = charge.get(CLE_DIAGNOSTIC)
        if isinstance(diagnostic, Mapping):
            for proposition in _liste(diagnostic.get(CLE_PROPOSITIONS)):
                if not isinstance(proposition, Mapping):
                    continue
                self._agregat(proposition.get(CLE_ATTEIGNABLE))
                self._agregat(proposition.get(CLE_ROUVERTS))

    def _produit(self, brut: object) -> ProduitEnBase | None:
        """Revalide un produit fourni. Un produit que le schéma refuse n'entre pas.

        Le contexte ne contient donc que des produits qui auraient pu sortir de la base
        — c'est la même porte que `catalogue/schemas.py` garde à l'insertion, prise
        dans l'autre sens.
        """
        if not isinstance(brut, Mapping):
            return None
        try:
            produit = ProduitEnBase.model_validate(dict(brut))
        except ValidationError as erreur:
            logueur.warning(
                "validateur.produit_fourni_invalide",
                identifiant=brut.get(CLE_ID),
                detail=str(erreur),
                consequence="il ne sera pas citable ; le texte sera jugé sans lui",
            )
            return None
        self.produits[produit.id] = produit
        self.prix[produit.id] = produit.prix_usd
        for valeur in produit.specs_pour_base().values():
            self._valeur_de_spec(valeur)
        return produit

    def _valeur_de_spec(self, valeur: object) -> None:
        """Indexe une valeur attribuable à un produit, sous sa forme canonique."""
        if valeur is None or isinstance(valeur, bool):
            return
        if isinstance(valeur, int | float | Decimal):
            self.specs.add(canonique(Decimal(str(valeur))))
            return
        if isinstance(valeur, str):
            nombre = en_decimal(valeur)
            self.specs.add(canonique(nombre) if nombre is not None else valeur)

    def _agregat(self, valeur: object) -> None:
        nombre = _nombre(valeur)
        if nombre is not None:
            self.agregats.add(nombre)

    def _fourchette(self, brut: object) -> None:
        if not isinstance(brut, Mapping):
            return
        self._agregat(brut.get(CLE_PLUS_BAS))
        self._agregat(brut.get(CLE_PLUS_HAUT))

    def _distribution(self, brut: object) -> None:
        """⚠️ **Seuls les effectifs entrent, jamais les valeurs.**

        « 12 écrans à 165 Hz » est un fait sur un ensemble ; il ne rend citable aucune
        fréquence sur aucun produit. C'est exactement ce que le piège nº9 de l'étape
        vérifie, et la seule ligne de ce module qu'il ne faut pas « simplifier ».
        """
        if not isinstance(brut, Mapping):
            return
        for valeur in _liste(brut.get(CLE_VALEURS)):
            if isinstance(valeur, Mapping):
                self._agregat(valeur.get(CLE_EFFECTIF))


def _liste(valeur: object) -> Sequence[Any]:
    return valeur if isinstance(valeur, list) else ()


def _nombre(valeur: object) -> Decimal | None:
    """Un nombre fourni, quelle que soit la façon dont le JSON l'a porté.

    Les `Decimal` partent en **chaînes** (`en_tool_result()`), les entiers en entiers :
    les deux passent par ici et ressortent en `Decimal`, jamais en flottant.
    """
    if isinstance(valeur, bool) or valeur is None:
        return None
    if isinstance(valeur, int | float | Decimal):
        return Decimal(str(valeur))
    if isinstance(valeur, str):
        return en_decimal(valeur)
    return None
