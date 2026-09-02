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
* `valeurs_de_distribution` — les valeurs que `probe_catalog` a vues dans le
  sous-catalogue, attribuables à **l'ensemble** et à personne en particulier ;
* `agregats` — les nombres fournis qui ne sont attribuables à aucun produit : bornes de
  prix, comptages, budget, valeurs atteignables d'un diagnostic ;
* `budget_usd` — le plafond, seul agrégat citable à côté d'un produit (voir son champ).

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

⚠️ **L'étape 13 apparie un `tool_use` à son `tool_result`, et la règle tient quand
même** — parce que ce qui déclenche l'appariement est une **clé**, pas un nom d'outil.
Quand un `tool_result` porte `mouvements_refuses` non vide, la valeur qui a été refusée
n'est pas dans le résultat : elle est dans la requête qui l'a produite. On remonte donc
au bloc appairé **par son identifiant**, sans jamais demander de quel outil il s'agit.
Le jour où un second outil rendrait `mouvements_refuses`, il serait lu de la même façon,
ce qui est exactement la propriété que « par clé » achète. Voir
`valeurs_des_mouvements_refuses`.
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
CLE_MOUVEMENTS_REFUSES = "mouvements_refuses"

# Les clés d'un bloc `tool_use`, et celle qui l'appaire à son résultat. Elles ne
# décrivent pas un fait du catalogue : elles servent uniquement à retrouver la requête
# dont un `tool_result` est la réponse (voir `valeurs_des_mouvements_refuses`).
TYPE_TOOL_USE = "tool_use"
CLE_ID_DE_BLOC = "id"
CLE_ENTREE = "input"
CLE_TOOL_USE_ID = "tool_use_id"
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

    valeurs_de_distribution: frozenset[str] = frozenset()
    """Les valeurs **présentes dans une distribution** de `probe_catalog`, en texte
    canonique. Elles décrivent un **ensemble**, jamais un produit.

    ⚠️ **Elles sont séparées de `valeurs_de_specs`, et cette séparation est tout
    l'arbitrage B.** « 12 écrans sont à 165 Hz » est un fait fourni ; « celui-ci est à
    165 Hz » ne l'est pas. La règle 5 les admet donc dans une phrase qui ne nomme aucun
    produit et les refuse dans une phrase qui en nomme un — exactement comme la règle 2
    fait des bornes de prix. Les verser dans `valeurs_de_specs` rendrait le piège nº9
    indétectable ; les jeter entièrement interdirait de dire ce que le catalogue
    contient, qui est la raison d'être de `probe_catalog` (§3.7)."""

    valeurs_refusees: frozenset[Decimal] = frozenset()
    """Les valeurs qu'un **mouvement refusé** portait (étape 13, jalon 1).

    ### Le besoin, et il est exactement celui-là

    La section 9 du prompt ordonne au modèle de **dire au client quel mouvement a été
    refusé** — « je garde le 144 Hz tant que vous ne me dites pas le contraire ». Un refus
    visible vaut mieux qu'un refus contourné. Or le dire suppose de citer la valeur
    refusée, et cette valeur n'est dans aucun `tool_result` : le jeton de parole ne
    l'ayant pas appliquée, elle n'apparaît ni dans `criteres`, ni dans `budget_usd`.

    Le validateur refusait donc « le passage à 300 $ et le 24 pouces n'ont pas été pris en
    compte » — c'est-à-dire qu'il **punissait l'obéissance à la section 9**. Ce n'est pas
    le cas d'une règle qui ne sait pas trancher et s'abstient ; c'est une règle qui tranche
    contre le comportement demandé.

    ⚠️ **Ce champ n'est pas une approximation étroite du besoin : c'est le besoin.** Les
    valeurs citables au titre de la section 9 sont précisément celles des mouvements
    refusés, ni plus ni moins. L'alternative écartée — admettre « tous les nombres que le
    client a écrits » — couvrait le besoin **par recouvrement** et non par identité : sur
    les quarante cassettes du dépôt elle admettait **119 nombres** là où celle-ci en admet
    **2**, pour faire taire exactement les deux mêmes griefs. L'écart de 117 ne sert à
    rien ; il n'est que de la surface.

    ### ⚠️ La provenance est un refus du moteur, **la valeur est écrite par le modèle**

    Les deux moitiés comptent, et la seconde interdit de traiter ce champ comme les
    autres. Le moteur fournit le **refus** — le jeton de parole a bien rejeté ce
    mouvement, c'est un fait produit par du code. Mais le **nombre**, lui, sort des
    arguments que le modèle a passés à l'outil. Un modèle peut donc se fabriquer une
    valeur citable en la faisant refuser exprès.

    C'est pourquoi ces valeurs sont admises **uniquement dans une phrase qui ne nomme
    aucun produit** — la discipline de `valeurs_de_distribution`, et pour la même raison.
    Elles décrivent ce que le client a demandé, jamais ce qu'un produit vaut.

    ⚠️ **Elles ne vont surtout pas dans `agregats`.** La règle 2 s'y comporterait bien —
    un agrégat reste refusé dans une phrase à produit —, mais la règle 5 consulte
    `agregats` **sans condition** : un `refresh_rate` refusé à 999 deviendrait citable en
    « cet écran est à 999 Hz ». Le compartiment dédié ferme ce chemin, que les agrégats
    laissent ouvert."""

    budget_usd: Decimal | None = None
    """Le plafond en vigueur, **tel que les outils l'ont rendu au modèle**.

    Il est aussi dans `agregats` — c'en est un — mais il en sort par un champ à lui pour
    une raison précise : c'est le **seul** agrégat admis dans une phrase qui nomme un
    produit (règle 2).

    ⚠️ **Ce n'est pas une commodité, et il ne faut élargir à rien d'autre.** Le budget
    n'est pas un fait du catalogue : c'est une **parole du client**, entrée par
    `record_criteria` et renvoyée dans son `tool_result`. §2 interdit au modèle
    d'inventer un fait ; répéter au client le montant qu'il vient d'annoncer n'en est pas
    un. Une borne de sondage, elle, est une affirmation sur le catalogue **et** un
    montant que le modèle n'a pas le droit d'attribuer à un produit — c'est le piège nº6,
    et c'est le seul test de l'étape qui échoue si quelqu'un aplatit le contexte.

    Il vient des `tool_result`, jamais d'`EtatSession` : le contexte fourni décrit ce que
    le modèle a vu, et il se construit toujours depuis ce qui lui a été envoyé. La
    dernière valeur rencontrée gagne, `null` compris — un budget retiré en cours de
    session cesse d'être citable."""

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

    ⚠️ **Une seule chose se lit ailleurs que dans un `tool_result`** : la valeur d'un
    mouvement refusé, qui n'est que dans la requête. Voir
    `valeurs_des_mouvements_refuses`, et la docstring du module pour pourquoi la règle
    « par clé, jamais par nom d'outil » y survit.

    ⚠️ **Aucune provenance ne se lit dans le texte d'un message `user`, et c'est une
    interdiction, pas un oubli.** Le message de reprise de l'étape 9 est un bloc `user`
    qui **cite les extraits refusés** : en tirer des faits rendrait le validateur
    auto-annulant — mesuré, 18 griefs sur 19 disparaissaient. Voir le test de régression
    `test_la_reprise_ne_fournit_jamais_un_fait`.
    """
    return contexte_des_resultats(
        _charges_utiles(messages),
        valeurs_refusees=valeurs_des_mouvements_refuses(messages),
    )


def contexte_des_resultats(
    charges: Iterable[Mapping[str, Any]],
    *,
    valeurs_refusees: frozenset[Decimal] = frozenset(),
) -> ContexteFourni:
    """Le contexte fourni, à partir des charges utiles déjà décodées.

    C'est la porte d'entrée des tests : un dictionnaire suffit, il n'y a ni base, ni
    clé, ni SDK dans le chemin.
    """
    accumulateur = _Accumulateur()
    for charge in charges:
        if charge.get(CLE_OK) is not True:
            continue
        accumulateur.absorber(charge)
    return accumulateur.figer(valeurs_refusees=valeurs_refusees)


def valeurs_des_mouvements_refuses(
    messages: Sequence[Mapping[str, Any]],
) -> frozenset[Decimal]:
    """Les valeurs que le jeton de parole a refusé d'appliquer, sur toute la conversation.

    **Le seul endroit du validateur qui remonte d'un `tool_result` à sa requête.** Il le
    fait parce que la valeur refusée n'existe nulle part ailleurs : le mouvement n'ayant
    pas été appliqué, elle n'est ni dans `criteres`, ni dans `budget_usd`.

    ⚠️ **Le déclencheur est la clé `mouvements_refuses`, jamais un nom d'outil.** Un
    second outil qui rendrait cette clé demain serait lu de la même façon, sans que
    personne ait à l'inscrire ici — c'est la propriété que « par clé » achète, et elle
    survit à l'appariement. L'identifiant, lui, ne dit rien de sémantique : il ne sert
    qu'à retrouver *quelle requête* a produit *ce résultat*.

    ⚠️ **Ce que cette fonction rend est écrit par le modèle**, et c'est pour cela que ses
    valeurs sont cantonnées aux phrases sans produit (voir `ContexteFourni.valeurs_refusees`).
    Le moteur fournit le refus ; le nombre vient des arguments d'appel.

    *Alternative écartée — ajouter `valeur` à `MouvementRefuse`.* Bien plus direct, et
    **impossible sans tout réenregistrer** : le `tool_result` est recalculé au rejeu et
    entre dans l'empreinte de requête (arbitrage B de l'étape 12). Un champ de plus, et
    les quarante cassettes du dépôt divergent au deuxième tour.
    """
    requetes: dict[str, Mapping[str, Any]] = {}
    trouvees: set[Decimal] = set()
    for message in messages:
        contenu = message.get(CLE_CONTENU)
        if not isinstance(contenu, list):
            continue
        for bloc in contenu:
            if not isinstance(bloc, Mapping):
                continue
            if bloc.get(CLE_TYPE) == TYPE_TOOL_USE:
                entree = bloc.get(CLE_ENTREE)
                if isinstance(entree, Mapping):
                    requetes[str(bloc.get(CLE_ID_DE_BLOC))] = entree
            elif bloc.get(CLE_TYPE) == TYPE_TOOL_RESULT and not bloc.get(CLE_EST_ERREUR):
                charge = _decoder(bloc.get(CLE_CONTENU))
                requete = requetes.get(str(bloc.get(CLE_TOOL_USE_ID)))
                if charge is not None and requete is not None:
                    trouvees.update(_valeurs_refusees(requete, charge))
    return frozenset(trouvees)


def _valeurs_refusees(requete: Mapping[str, Any], resultat: Mapping[str, Any]) -> Iterator[Decimal]:
    """Ce que la requête demandait et que le résultat n'a pas appliqué."""
    refuses = {
        str(mouvement.get(CLE_CHAMP))
        for mouvement in resultat.get(CLE_MOUVEMENTS_REFUSES) or ()
        if isinstance(mouvement, Mapping)
    }
    if not refuses:
        return
    for critere in requete.get(CLE_CRITERES) or ():
        if not isinstance(critere, Mapping) or str(critere.get(CLE_CHAMP)) not in refuses:
            continue
        valeur = en_decimal(str(critere.get(CLE_VALEUR)))
        if valeur is not None:
            yield valeur
    # Le budget suit le même chemin, mais il n'est pas un critère : le refus se lit sur
    # l'écart entre ce qui a été demandé et ce qui a été rendu.
    demande = en_decimal(str(requete.get(CLE_BUDGET_USD)))
    rendu = en_decimal(str(resultat.get(CLE_BUDGET_USD)))
    if demande is not None and rendu is not None and demande != rendu:
        yield demande


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
        self.distribution: set[str] = set()
        self.agregats: set[Decimal] = set()
        self.budget: Decimal | None = None

    def figer(self, *, valeurs_refusees: frozenset[Decimal] = frozenset()) -> ContexteFourni:
        """Les provenances accumulées, plus celle qui ne s'accumule pas.

        `valeurs_refusees` ne passe pas par `absorber()` : elle ne se lit pas dans une
        charge utile mais dans l'appariement d'une requête et de son résultat, ce qui est
        hors de portée d'un accumulateur qui reçoit des charges une par une.
        """
        return ContexteFourni(
            produits=dict(self.produits),
            hors_budget=dict(self.hors_budget),
            prix=dict(self.prix),
            valeurs_de_specs=frozenset(self.specs),
            valeurs_de_distribution=frozenset(self.distribution),
            agregats=frozenset(self.agregats),
            valeurs_refusees=valeurs_refusees,
            budget_usd=self.budget,
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

        if CLE_BUDGET_USD in charge:
            # La clé est présente dans `record_criteria` **et** dans `probe_catalog`, et
            # les deux portent le plafond de session au moment de l'appel : lire la clé
            # plutôt que le nom de l'outil donne donc la bonne valeur, et la dernière
            # gagne. `null` est une valeur, pas une absence — un budget retiré doit
            # cesser d'être citable, et un `if valeur is not None` l'aurait figé.
            self.budget = _nombre(charge.get(CLE_BUDGET_USD))
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
        """⚠️ **Les effectifs sont des agrégats, les valeurs vont dans un champ à part.**

        « 12 écrans à 165 Hz » est un fait sur un ensemble : le comptage est un agrégat
        comme un autre, mais la fréquence n'est citable **d'aucun produit**. Elle n'entre
        donc pas dans `valeurs_de_specs` — c'est ce que le piège nº9 vérifie — et pas non
        plus à la poubelle : sans elle, l'agent ne pourrait pas dire ce que le catalogue
        contient, ce qui est la raison d'être de `probe_catalog`.

        C'est la seule ligne de ce module qu'il ne faut pas « simplifier ».
        """
        if not isinstance(brut, Mapping):
            return
        for valeur in _liste(brut.get(CLE_VALEURS)):
            if isinstance(valeur, Mapping):
                self._agregat(valeur.get(CLE_EFFECTIF))
                self._valeur_de_distribution(valeur.get(CLE_VALEUR))

    def _valeur_de_distribution(self, valeur: object) -> None:
        """Indexe une valeur d'ensemble, sous la même forme canonique que les specs."""
        if isinstance(valeur, str):
            nombre = en_decimal(valeur)
            self.distribution.add(canonique(nombre) if nombre is not None else valeur)


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
