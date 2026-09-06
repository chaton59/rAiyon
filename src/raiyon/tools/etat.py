"""L'état de session, et la règle qui empêche le modèle de défaire ce que le client a dit.

Trois choses vivent ici, et une seule fonction les relie :

1. **`EtatSession`** — ce que le client a déclaré, indexé par catégorie, plus la forme
   JSONB que l'étape 10 persistera. Dataclass **pure** : aucune écriture SQLAlchemy,
   aucune horloge, aucun appel de configuration.
2. **`desserre()`** — le verdict sur un mouvement : *peut-il faire remonter un produit
   qui ne remontait pas ?*
3. **`fusionner()`** — la porte unique par laquelle les critères entrent, et le seul
   endroit où la règle de collant mord.

---

### Le jeton de parole (§3.17, arbitrage A de l'étape 7)

Un mouvement qui **desserre** consomme le jeton du tour client. Un second desserrage
dans le même tour est refusé. Le numéro de tour est **fourni par l'appelant** : la
couche outils n'a aucune notion d'horloge, et les tests injectent des entiers.

*Alternative écartée — exiger une citation verbatim d'un message `user`.* Elle donne
l'illusion d'une preuve : le modèle peut citer « je peux monter un peu », prononcé à
propos du budget, pour desserrer la fréquence de rafraîchissement. Le jeton ne prouve
pas que le client a parlé **de ce critère** ; il borne le nombre de desserrages par
parole, ce qui tue l'essai-erreur — le vrai mode d'échec que §3.6 cherche à empêcher.

⚠️ **La faiblesse est réelle et elle est au §7 des risques :** rien ne détecte qu'un
desserrage autorisé par une parole a été appliqué à un autre critère que celui dont le
client parlait. Un desserrage par tour au lieu de zéro contrôle est un progrès, pas une
garantie.

### Une règle unique : desserrer consomme, resserrer est libre

Le texte de l'étape 6 ne parlait que de l'**importance**. C'était insuffisant : après un
zéro résultat, passer `au_moins 144` à `au_moins 120` obtient exactement ce que la
rétrogradation obtenait, sans toucher à l'importance. Retirer le critère fait pire. La
règle porte donc sur le **mouvement**, pas sur l'un de ses attributs.

### Ce que la fusion ne compte pas comme un mouvement

* **Redire à l'identique un critère déjà en place ne coûte rien.** Un modèle qui
  récapitule l'état à chaque tour ne doit pas dépenser son jeton pour ça.
* **Changer d'`optimisation` non plus.** Elle ne touche pas l'ensemble des candidats,
  seulement son ordre (arbitrage H de l'étape 6) : elle ne peut donc pas transformer un
  zéro résultat en résultat, qui est le seul mode d'échec que le jeton vise. Elle change
  bien **quels** produits sont montrés, `LIMITE_PRODUITS` valant 3 — dire « elle ordonne,
  elle n'exclut pas » serait faux, et cette nuance a coûté une relecture.

### Le changement de catégorie paie le jeton s'il efface un budget

Le changement de catégorie remet le budget à `None` (arbitrage D). C'est exactement la
ligne « budget qui passe à `None` → desserre » de l'arbitrage B, et aucune exemption
n'est écrite pour le seul chemin qui l'emprunte : **s'il y avait un budget en vigueur,
le changement consomme le jeton** ; s'il n'y en avait pas, il est gratuit.

Sans cela, le trou était inter-tours, donc invisible pour une borne posée par tour :

    tour 5 : monitor, budget 300 → categorie="cpu"     gratuit, budget → None
    tour 6 : categorie="monitor"                       gratuit, budget toujours None

⚠️ **Ça tarife l'effacement, ça ne l'empêche pas** — la ligne est au §7. Le seul
correctif qui fermerait vraiment est un budget par catégorie, et il rouvre la divergence
que §3.10 ferme en donnant au budget une colonne unique.

Quand le jeton est déjà pris, le changement de catégorie **échoue** (`OutilRefuse`) au
lieu de s'appliquer à moitié : il n'y a pas de demi-changement de sujet. Poser un budget
sur la nouvelle catégorie reste libre — « maintenant un SSD, 100 $ » passe en un seul
appel, le changement paie le jeton et le budget posé depuis `None` est un resserrage.

### La forme du JSONB est arrêtée ici, l'écriture est l'affaire de l'étape 10

`sessions.criteres_valides` porte exactement quatre clés, et **le budget n'en fait pas
partie** : il garde sa colonne (§3.10 et `models.py`), parce que deux copies d'une même
contrainte divergent. `en_jsonb()` ne le sérialise donc pas, et `depuis_jsonb()` le
reçoit **à part** — la signature rend l'oubli impossible plutôt que documenté.

Les gardes **de tour** (`recherche_du_tour`, `tour_du_changement_de_categorie`) ne sont
pas persistées : elles n'ont de sens qu'à l'intérieur d'un tour, et une valeur périmée
refuserait une recherche légitime au tour suivant. Condition de bascule, écrite pour ne
pas être redécouverte : si l'étape 10 persistait l'état **au milieu** d'un tour — et non
à sa fin — ces deux champs devraient rejoindre le JSONB, sans migration puisque le
JSONB n'a pas de schéma.

### Les valeurs voyagent en **texte**, ici comme dans le schéma d'outil

`{"champ": "refresh_rate", "operateur": "au_moins", "valeur": "144"}` : la valeur est
une chaîne dans le JSONB **et** dans le schéma JSON des outils (arbitrage F), pour la
même raison qu'ailleurs dans le projet — `specs_pour_base()` sérialise déjà les
`Decimal` en chaînes afin qu'un aller-retour JSON les rende au caractère près. La
conversion vers le genre déclaré par le registre est donc écrite **une seule fois**,
dans ce module, et sert les deux chemins.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Any

from raiyon.catalogue.schemas import CATEGORIES, Categorie
from raiyon.matching.attributs import ATTRIBUTS, Attribut, Genre
from raiyon.matching.criteres import (
    CHAMPS_A_CHAMP_DEDIE,
    Critere,
    CritereInvalide,
    Importance,
    Operateur,
    Optimisation,
    RequeteMatching,
    ValeurCritere,
    resoudre_critere,
)
from raiyon.matching.depot import CENTIMES

# L'ordre des importances n'appartient pas au relâchement : c'est celui de
# l'énumération elle-même. Le réécrire ici en ferait deux, et deux ordres d'un même
# énuméré finissent par diverger sur un cas rare, tard.
from raiyon.matching.relachement import RANG_IMPORTANCE
from raiyon.tools.erreurs import CodeRefus, OutilRefuse

CleCritere = tuple[str, Operateur]
"""La clé d'un critère de session.

**Le champ seul ne suffit pas.** `Critere` autorise `au_moins` et `au_plus` sur le même
champ : un critère de session peut donc être un intervalle (« entre 24 et 27 pouces »),
et une fusion indexée par le champ seul écraserait silencieusement l'une des deux
bornes.
"""


@dataclass(frozen=True, slots=True)
class CritereTexte:
    """Un critère tel qu'il arrive — du modèle, ou du JSONB relu.

    Seule `valeur` est textuelle : `operateur` et `importance` sont des énumérations
    fermées, que le schéma JSON énumère et que Pydantic valide à l'entrée de l'outil.
    C'est `valeur` qui ne peut pas être typée dans le schéma (arbitrage F), donc c'est
    elle, et elle seule, qui se convertit ici.
    """

    champ: str
    operateur: Operateur
    valeur: str
    importance: Importance = Importance.SOUHAIT

    @property
    def cle(self) -> CleCritere:
        return (self.champ, self.operateur)


@dataclass(frozen=True, slots=True)
class DemandeBudget:
    """Ce que le tour dit du budget. `valeur=None` signifie « plus de plafond ».

    L'objet entier vaut `None` quand le tour ne dit **rien** du budget. Sans cette
    distinction, « ne pas parler du budget » et « retirer le budget » seraient le même
    argument — et le second desserre, quand le premier ne fait rien.
    """

    valeur: str | None


@dataclass(frozen=True, slots=True)
class Mouvement:
    """Un critère qui change, sur une clé `(champ, opérateur)`.

    `avant` et `apres` valent `None` pour dire l'absence : un ajout part de `None`, un
    retrait y va. Les deux à `None` n'est pas un mouvement, c'est un non-événement, et
    `fusionner()` ne le produit pas.
    """

    cle: CleCritere
    avant: Critere | None
    apres: Critere | None

    @property
    def champ(self) -> str:
        return self.cle[0]

    @property
    def operateur(self) -> Operateur:
        return self.cle[1]


@dataclass(frozen=True, slots=True)
class MouvementRefuse:
    """Un mouvement légitime en soi, mais qui n'avait plus de jeton pour ce tour.

    **Ce n'est pas une erreur** : l'outil réussit, applique le reste, et rend ceci.
    L'agent peut alors dire au client « je garde 144 Hz tant que tu ne me dis pas le
    contraire » — ce qui est une réponse, pas un incident.
    """

    champ: str
    operateur: Operateur
    motif: str


@dataclass(frozen=True, slots=True)
class Recherche:
    """La recherche de produits déjà faite dans ce tour (arbitrage E).

    Le moteur garantit qu'un **appel** rend une seule catégorie ; il ne garantit rien
    sur un **tour**. Sans cette trace, l'agent pourrait chercher un écran puis une carte
    graphique dans le même tour et rédiger la « config gaming » que §8 met hors
    périmètre.
    """

    tour_client: int
    categorie: Categorie


@dataclass(frozen=True, slots=True)
class RecherchesDavis:
    """Combien de recherches d'avis ce message du client a déjà consommées (étape 27).

    ⚠️ **Un compteur, pas un booléen**, alors que la borne vaut 1. Le journal veut savoir
    si le modèle a **essayé** deux fois, pas seulement qu'il a été refusé une fois : c'est
    ce chiffre qui dira à quelle fréquence la borne serre, et donc s'il faut la rediscuter.
    Un booléen répondrait « oui, refusé » sans jamais dire combien.
    """

    tour_client: int
    compte: int


@dataclass(frozen=True, slots=True)
class EtatSession:
    """Ce que le client a dit, indexé par catégorie. Aucune notion de panier.

    Un client qui revient à l'écran retrouve ce qu'il avait dit. Cela ne crée **aucun
    panier** : aucune somme n'est suivie, l'invariant « un tour, une catégorie » tient,
    et §8 reste vrai mot pour mot.

    *Alternative écartée — un état plat, vidé à chaque changement de catégorie.* Plus
    simple d'une ligne, mais il perd ce que le client a déjà dit, et forcerait une
    migration du JSONB dès que le besoin apparaîtrait.

    L'état ne se modifie jamais : chaque fonction en rend un nouveau. `criteres` est
    typé `Mapping` et non `dict` pour que mypy refuse une écriture en place — la
    garantie est statique, elle ne repose pas sur la discipline.
    """

    categorie_courante: Categorie | None = None
    criteres: Mapping[Categorie, tuple[Critere, ...]] = field(default_factory=dict)
    budget_usd: Decimal | None = None
    """Global à la session, et **remis à `None` au changement de catégorie**
    (arbitrage D). Il vit dans la colonne `sessions.budget_usd`, jamais dans le JSONB.

    *Alternative écartée — le budget survit au changement de catégorie.* Une question de
    moins à poser, donc une métrique nº3 flattée ; mais un client qui a dit « 300 $ pour
    l'écran » verrait cette contrainte s'appliquer à son SSD, c'est-à-dire une contrainte
    qu'il n'a jamais posée. C'est exactement ce que §2 interdit, appliqué à un critère au
    lieu d'un fait."""

    optimisation: Optimisation = Optimisation.AUCUNE
    tour_du_dernier_desserrage: int | None = None

    recherche_du_tour: Recherche | None = None
    """Garde de tour, **non persistée** — voir la docstring du module."""

    avis_du_tour: RecherchesDavis | None = None
    """Les recherches d'avis déjà faites dans ce message du client (étape 27).

    Garde de tour, **non persistée** pour la même raison que `recherche_du_tour` : une
    valeur périmée refuserait une recherche légitime au tour suivant.

    ⚠️ **Elle porte son `tour_client`, elle ne se remet pas à zéro.** Il n'existe pas de
    `nouveau_tour()` dans ce projet, et en écrire un pour ce champ créerait un second
    mécanisme d'expiration à côté de celui que `recherche_du_tour` emploie déjà. La garde
    compare le tour porté au tour courant : un état d'un tour précédent est simplement
    ignoré, comme celui d'une recherche de produits."""

    def criteres_de(self, categorie: Categorie) -> tuple[Critere, ...]:
        """Les critères déclarés pour cette catégorie, dans l'ordre de déclaration."""
        return self.criteres.get(categorie, ())

    def par_cle(self, categorie: Categorie) -> dict[CleCritere, Critere]:
        """Les critères d'une catégorie, indexés par `(champ, opérateur)`."""
        return {
            (critere.champ, critere.operateur): critere for critere in self.criteres_de(categorie)
        }

    def requete(self) -> RequeteMatching:
        """La requête que le moteur consommera. **Le seul chemin vers le moteur.**

        Les outils de recherche ne prennent aucun critère (arbitrage C) : ils lisent
        l'état. C'est ce qui fait qu'« aucun argument hostile ne franchit l'invariant »
        devient « il n'existe pas d'argument par lequel passer ».
        """
        if self.categorie_courante is None:
            raise ValueError("aucune catégorie courante : appeler enregistrer_criteres d'abord")
        return RequeteMatching(
            categorie=self.categorie_courante,
            budget_usd=self.budget_usd,
            criteres=self.criteres_de(self.categorie_courante),
            optimisation=self.optimisation,
        )

    def en_jsonb(self) -> dict[str, Any]:
        """La forme de `sessions.criteres_valides`. **Sans le budget** (§3.10)."""
        return {
            "categorie_courante": self.categorie_courante,
            "criteres": {
                categorie: [_critere_en_jsonb(critere) for critere in criteres]
                for categorie, criteres in self.criteres.items()
            },
            "optimisation": self.optimisation.value,
            "tour_du_dernier_desserrage": self.tour_du_dernier_desserrage,
        }


def _critere_en_jsonb(critere: Critere) -> dict[str, str]:
    return {
        "champ": critere.champ,
        "operateur": critere.operateur.value,
        "valeur": valeur_en_texte(critere.valeur),
        "importance": critere.importance.value,
    }


def depuis_jsonb(donnees: Mapping[str, Any], *, budget_usd: Decimal | None = None) -> EtatSession:
    """Relit `sessions.criteres_valides`, et **revalide tout au passage**.

    La revalidation passe par la même porte que l'entrée : `resoudre_critere()`. Une
    ligne corrompue est ainsi arrêtée ici plutôt que trois couches plus loin, dans une
    requête — c'est la raison qui fait déjà revalider le seed committé au chargement.

    Le budget arrive **par un autre argument** parce qu'il vient d'une autre colonne.
    Le laisser entrer par le dictionnaire ouvrirait la porte à une seconde copie.
    """
    categorie_courante = donnees.get("categorie_courante")
    if categorie_courante is not None and categorie_courante not in CATEGORIES:
        raise ValueError(f"catégorie inconnue dans criteres_valides : {categorie_courante!r}")

    criteres: dict[Categorie, tuple[Critere, ...]] = {}
    for nom, liste in dict(donnees.get("criteres", {})).items():
        if nom not in CATEGORIES:
            raise ValueError(f"catégorie inconnue dans criteres_valides : {nom!r}")
        categorie: Categorie = nom
        criteres[categorie] = tuple(
            _valider(
                categorie,
                CritereTexte(
                    champ=str(brut["champ"]),
                    operateur=Operateur(brut["operateur"]),
                    valeur=str(brut["valeur"]),
                    importance=Importance(brut.get("importance", Importance.SOUHAIT)),
                ),
            )
            for brut in liste
        )

    return EtatSession(
        categorie_courante=categorie_courante,
        criteres=criteres,
        budget_usd=budget_usd,
        optimisation=Optimisation(donnees.get("optimisation", Optimisation.AUCUNE)),
        tour_du_dernier_desserrage=donnees.get("tour_du_dernier_desserrage"),
    )


# --------------------------------------------------------------------------- #
# Conversion texte ↔ valeur — écrite une fois, servie deux fois
# --------------------------------------------------------------------------- #

TEXTES_BOOLEENS: dict[str, bool] = {"true": True, "false": False}
"""Les deux seules écritures admises. Ni « oui », ni « 1 », ni « yes » : le schéma JSON
les donne au modèle dans la description du champ, et accepter des synonymes reviendrait
à deviner ce qu'il a voulu dire."""


def valeur_en_texte(valeur: ValeurCritere) -> str:
    """La valeur telle qu'elle voyage : une chaîne, toujours."""
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    return str(valeur)


def valeur_depuis_texte(attribut: Attribut, texte: str) -> ValeurCritere:
    """Convertit selon le **genre déclaré par le registre**, ou refuse en le disant.

    C'est la moitié que `_convertir()` de `criteres.py` ne fait pas : celui-ci amène un
    `int` ou un `Decimal` au type attendu, mais il n'a jamais eu à lire du texte. La
    frontière entre les deux est nette — ici, le texte devient une valeur Python ; là,
    la valeur Python devient la valeur du genre.
    """
    if attribut.genre is Genre.BOOLEEN:
        booleen = TEXTES_BOOLEENS.get(texte.strip().lower())
        if booleen is None:
            raise OutilRefuse(
                CodeRefus.VALEUR_ILLISIBLE,
                f"{attribut.champ} ({attribut.libelle_fr}) est un booléen : la valeur doit être "
                f'"true" ou "false", reçu {texte!r}',
            )
        return booleen

    if attribut.genre is Genre.NUMERIQUE:
        try:
            nombre = Decimal(texte.strip())
        except InvalidOperation as erreur:
            raise OutilRefuse(
                CodeRefus.VALEUR_ILLISIBLE,
                f"{attribut.champ} ({attribut.libelle_fr}) est un nombre"
                f"{_unite(attribut)} : la valeur doit s'écrire en chiffres, reçu {texte!r}",
            ) from erreur
        if not nombre.is_finite():
            raise OutilRefuse(
                CodeRefus.VALEUR_ILLISIBLE,
                f"{attribut.champ} ({attribut.libelle_fr}) attend un nombre fini, reçu {texte!r}",
            )
        return nombre

    if not texte:
        raise OutilRefuse(
            CodeRefus.VALEUR_ILLISIBLE,
            f"{attribut.champ} ({attribut.libelle_fr}) attend une valeur, reçu une chaîne vide — "
            "sonder le catalogue rend les valeurs réellement présentes",
        )
    return texte


def _unite(attribut: Attribut) -> str:
    return f" en {attribut.unite}" if attribut.unite else ""


# --------------------------------------------------------------------------- #
# La règle de collant : un mouvement desserre-t-il ?
# --------------------------------------------------------------------------- #


def desserre(avant: Critere | None, apres: Critere | None, attribut: Attribut) -> bool:
    """Ce mouvement peut-il faire remonter un produit qui ne remontait pas ?

    Une seule fonction pour toutes les formes de desserrage, dérivée de l'opérateur et
    du registre — jamais d'une liste écrite à la main :

    | mouvement | verdict |
    | --- | --- |
    | ajout d'un critère sur une clé libre | resserre — **libre** |
    | retrait d'un critère | **desserre** |
    | baisse d'importance (`bloquant` > `important` > `souhait`) | **desserre** |
    | hausse d'importance | resserre — libre |
    | `au_moins` : valeur qui baisse | **desserre** |
    | `au_plus` : valeur qui monte | **desserre** |
    | `egal` : toute valeur différente | **desserre** (on ne peut pas savoir) |
    | changement d'opérateur sur le même champ | retrait + ajout → **desserre** |
    | budget qui monte, ou qui passe à `None` | **desserre** |
    | budget qui baisse, ou posé depuis `None` | resserre — libre |

    Les deux dernières lignes ne demandent aucun code : le budget est présenté à cette
    fonction comme un `au_plus` sur `prix_usd` (voir `_critere_de_budget()`), et les
    quatre cas tombent alors des lignes précédentes.

    **Le verdict est un OU, pas un ET.** Un mouvement qui desserre par un bout et
    resserre par l'autre — `au_moins 144 souhait` devenant `au_moins 120 bloquant` —
    consomme le jeton. C'est le sens conservateur, et le seul qui ne s'ouvre pas à une
    combinaison : la question posée est « **peut**-il faire remonter un produit ? », pas
    « le fait-il à coup sûr ? ».

    *Alternative écartée — comparer les ensembles de produits satisfaits.* Exacte, et
    elle rendrait la question décidable au lieu d'approchée ; écartée parce qu'elle
    exige d'interroger le catalogue, donc de rendre impure la seule règle du projet dont
    on veut pouvoir prouver qu'elle ne dépend de rien.
    """
    if avant is None:
        return False
    if apres is None:
        return True
    if (avant.champ, avant.operateur) != (apres.champ, apres.operateur):
        # Changer d'opérateur, c'est retirer une contrainte et en poser une autre. Le
        # retrait desserre, et rien ne dit que l'ajout compense : « au moins 144 » puis
        # « au plus 240 » laisse remonter tous les 60 Hz.
        return True
    if RANG_IMPORTANCE[apres.importance] < RANG_IMPORTANCE[avant.importance]:
        return True
    return _valeur_desserree(avant, apres, attribut)


def _valeur_desserree(avant: Critere, apres: Critere, attribut: Attribut) -> bool:
    """Le seuil a-t-il bougé dans le sens qui rouvre le catalogue ?"""
    if attribut.genre is Genre.NUMERIQUE:
        return _seuil_desserre(avant.operateur, _nombre(avant.valeur), _nombre(apres.valeur))
    # Sur un genre non gradué, l'opérateur est nécessairement `egal` : toute valeur
    # différente désigne d'autres produits, et rien ne dit qu'ils sont moins nombreux.
    # On ne peut pas savoir sans le catalogue, donc on refuse de supposer.
    return avant.valeur != apres.valeur


def _seuil_desserre(operateur: Operateur, avant: Decimal, apres: Decimal) -> bool:
    if operateur is Operateur.AU_MOINS:
        return apres < avant
    if operateur is Operateur.AU_PLUS:
        return apres > avant
    return apres != avant


def _nombre(valeur: ValeurCritere) -> Decimal:
    """Un critère numérique porte un `Decimal` dès son entrée ; ceci ferme le typage."""
    if isinstance(valeur, bool):
        return Decimal(int(valeur))
    return Decimal(str(valeur))


def _critere_de_budget(montant: Decimal | None) -> Critere | None:
    """Le budget, vu comme le critère qu'il est pour la seule question du desserrage.

    ⚠️ **Ce critère n'est jamais stocké et ne part jamais au moteur.** `prix_usd` a un
    champ dédié dans `RequeteMatching` et une colonne dans `sessions`, précisément pour
    qu'il n'existe qu'un seul chemin vers le budget (§3.10) ; ce qui est fabriqué ici
    est un **argument de comparaison**, vivant le temps d'un appel de `desserre()`.
    L'alternative — une seconde fonction `desserre_le_budget()` — dupliquerait les
    quatre lignes du tableau que la première écrit déjà.
    """
    if montant is None:
        return None
    return Critere(
        champ="prix_usd",
        operateur=Operateur.AU_PLUS,
        valeur=montant,
        importance=Importance.BLOQUANT,
    )


# --------------------------------------------------------------------------- #
# La fusion : la porte unique
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Fusion:
    """Ce que rend `fusionner()` : le nouvel état, ce qui a bougé, ce qui a été refusé."""

    etat: EtatSession
    appliques: tuple[Mouvement, ...]
    refuses: tuple[MouvementRefuse, ...]


MOTIF_JETON = (
    "un seul assouplissement par message du client, et il est déjà pris pour ce tour. "
    "Le critère reste en place : le dire au client, et ne le rouvrir que s'il le "
    "redemande lui-même — ce sera alors un nouveau tour, donc un nouveau jeton."
)


def fusionner(
    etat: EtatSession,
    *,
    tour_client: int,
    categorie: Categorie,
    ajouts: Sequence[CritereTexte] = (),
    retraits: Sequence[CleCritere] = (),
    budget: DemandeBudget | None = None,
    optimisation: Optimisation | None = None,
) -> Fusion:
    """Applique un tour de déclarations. **Le seul endroit où un critère entre.**

    L'ordre de traitement est celui que le modèle a donné : d'abord ses critères, puis
    ses retraits, puis le budget. C'est ce qui décide, quand deux mouvements desserrent,
    lequel obtient le jeton. *Alternative écartée — un ordre canonique par champ.* Il
    rendrait le résultat indépendant de la façon dont le modèle a rempli sa liste, mais
    ferait dépendre l'assouplissement retenu de l'alphabet plutôt que de ce que le
    client vient de dire.
    """
    if categorie not in CATEGORIES:
        raise OutilRefuse(
            CodeRefus.CATEGORIE_INCONNUE,
            f"catégorie inconnue : {categorie!r} — catégories du catalogue : "
            + ", ".join(CATEGORIES),
        )

    etat, jeton_pris = _changer_de_categorie(etat, categorie, tour_client)
    courants = etat.par_cle(categorie)
    mouvements = _mouvements(etat, categorie, courants, ajouts, retraits, budget)

    appliques: list[Mouvement] = []
    refuses: list[MouvementRefuse] = []
    budget_retenu = etat.budget_usd

    for mouvement in mouvements:
        attribut = ATTRIBUTS[categorie][mouvement.champ]
        if desserre(mouvement.avant, mouvement.apres, attribut):
            if jeton_pris:
                refuses.append(MouvementRefuse(mouvement.champ, mouvement.operateur, MOTIF_JETON))
                continue
            jeton_pris = True
        if mouvement.champ == "prix_usd":
            budget_retenu = None if mouvement.apres is None else _nombre(mouvement.apres.valeur)
        else:
            courants = _appliquer(courants, mouvement)
        appliques.append(mouvement)

    nouveaux = dict(etat.criteres)
    nouveaux[categorie] = tuple(courants.values())
    return Fusion(
        etat=replace(
            etat,
            criteres=nouveaux,
            budget_usd=budget_retenu,
            optimisation=etat.optimisation if optimisation is None else optimisation,
            tour_du_dernier_desserrage=tour_client
            if jeton_pris
            else etat.tour_du_dernier_desserrage,
        ),
        appliques=tuple(appliques),
        refuses=tuple(refuses),
    )


def _appliquer(
    courants: dict[CleCritere, Critere], mouvement: Mouvement
) -> dict[CleCritere, Critere]:
    """Rend un dictionnaire neuf : la position d'une clé mise à jour ne bouge pas.

    Un critère réécrit garde sa place dans la liste, ce qui évite qu'un simple
    changement d'importance fasse défiler l'ordre des critères dans l'état persisté et
    dans tout ce qui le relit.
    """
    suivants = dict(courants)
    if mouvement.apres is None:
        suivants.pop(mouvement.cle, None)
    else:
        suivants[mouvement.cle] = mouvement.apres
    return suivants


def _changer_de_categorie(
    etat: EtatSession, categorie: Categorie, tour_client: int
) -> tuple[EtatSession, bool]:
    """Change de sujet, et dit si le jeton du tour vient d'y passer.

    L'effacement du budget n'est pas jugé par une règle écrite ici : il est soumis à
    `desserre()` comme n'importe quel mouvement, sous la forme d'un `au_plus` sur
    `prix_usd` qui disparaît. Une seule règle, un seul juge.
    """
    jeton_pris = etat.tour_du_dernier_desserrage == tour_client
    if etat.categorie_courante == categorie:
        return etat, jeton_pris
    if etat.categorie_courante is None:
        return replace(etat, categorie_courante=categorie), jeton_pris

    efface_le_budget = desserre(
        _critere_de_budget(etat.budget_usd), None, ATTRIBUTS[categorie]["prix_usd"]
    )
    if efface_le_budget:
        if jeton_pris:
            raise OutilRefuse(
                CodeRefus.CHANGEMENT_DE_CATEGORIE_SANS_JETON,
                f"changer de catégorie efface le budget de {etat.budget_usd} USD, et le "
                "jeton d'assouplissement de ce tour est déjà pris. Terminer la catégorie "
                "en cours, et prendre la suivante au tour d'après — on conseille un "
                "composant à la fois.",
            )
        jeton_pris = True

    # La garde de recherche du tour n'est **pas** effacée au passage : changer de
    # catégorie après avoir cherché ne doit pas rouvrir le droit de chercher une
    # seconde fois dans le même tour, sans quoi l'arbitrage E se contournerait par
    # cette porte-là.
    return (
        replace(etat, categorie_courante=categorie, budget_usd=None),
        jeton_pris,
    )


def _mouvements(
    etat: EtatSession,
    categorie: Categorie,
    courants: Mapping[CleCritere, Critere],
    ajouts: Sequence[CritereTexte],
    retraits: Sequence[CleCritere],
    budget: DemandeBudget | None,
) -> list[Mouvement]:
    """Traduit les déclarations du tour en mouvements, et refuse ce que le registre refuse.

    Un mouvement sans effet — redire à l'identique un critère en place, retirer une clé
    qui n'existe pas — n'est **pas** produit : il ne coûte donc aucun jeton, et un modèle
    qui récapitule l'état à chaque tour ne se punit pas lui-même.
    """
    vus: set[CleCritere] = set()
    mouvements: list[Mouvement] = []

    for entrant in ajouts:
        critere = _valider(categorie, entrant)
        cle = entrant.cle
        _refuser_le_doublon(cle, vus)
        avant = courants.get(cle)
        if avant != critere:
            mouvements.append(Mouvement(cle=cle, avant=avant, apres=critere))

    for cle in retraits:
        _refuser_le_doublon(cle, vus)
        avant = courants.get(cle)
        if avant is not None:
            mouvements.append(Mouvement(cle=cle, avant=avant, apres=None))

    if budget is not None:
        mouvements.extend(_mouvement_de_budget(etat, categorie, budget))
    return mouvements


def _mouvement_de_budget(
    etat: EtatSession, categorie: Categorie, budget: DemandeBudget
) -> list[Mouvement]:
    """Le budget passe par la même moulinette que les critères, sans jamais y entrer."""
    attribut = ATTRIBUTS[categorie]["prix_usd"]
    apres: Decimal | None = None
    if budget.valeur is not None:
        montant = valeur_depuis_texte(attribut, budget.valeur)
        apres = _nombre(montant)
        if apres <= 0 or apres != apres.quantize(CENTIMES):
            raise OutilRefuse(
                CodeRefus.VALEUR_ILLISIBLE,
                f"le budget se donne en dollars, strictement positif et à deux décimales "
                f"au plus — reçu {budget.valeur!r}",
            )
        # Mis à l'échelle de la colonne `sessions.budget_usd` (`numeric(10,2)`) **dès
        # l'entrée** : sans cela, « 400 » vaudrait `Decimal("400")` en mémoire et
        # `Decimal("400.00")` après un aller-retour en base, et l'écart au budget d'un
        # produit hors zone s'écrirait « 20 » avant persistance et « 20.00 » après.
        apres = apres.quantize(CENTIMES)
    if etat.budget_usd == apres:
        return []
    return [
        Mouvement(
            cle=("prix_usd", Operateur.AU_PLUS),
            avant=_critere_de_budget(etat.budget_usd),
            apres=_critere_de_budget(apres),
        )
    ]


def _refuser_le_doublon(cle: CleCritere, vus: set[CleCritere]) -> None:
    """`au_moins` et `au_plus` cohabitent sur un champ ; deux fois la même clé, non.

    Le second annulerait le premier, ou le compterait deux fois au score — c'est déjà
    ce que `RequeteMatching` refuse, dit ici plus tôt et avec le geste à faire.
    """
    if cle in vus:
        raise OutilRefuse(
            CodeRefus.CRITERE_INVALIDE,
            f"deux fois {cle[1].value!r} sur {cle[0]!r} dans le même appel : le second "
            "annulerait le premier. Pour un intervalle, poser 'au_moins' **et** 'au_plus'.",
        )
    vus.add(cle)


def _valider(categorie: Categorie, entrant: CritereTexte) -> Critere:
    """Confronte un critère entrant au registre. **Aucune valeur ne passe autrement.**

    Le message d'erreur est celui du registre, repris verbatim : `resoudre_critere()`
    rédige déjà pour être lu par un modèle (« Repasser en 'important' »), et une seconde
    rédaction de la même règle finirait par en dire autre chose.
    """
    if entrant.champ in CHAMPS_A_CHAMP_DEDIE:
        raise OutilRefuse(
            CodeRefus.CRITERE_INVALIDE,
            f"{entrant.champ!r} ne se pose pas en critère : le budget a son propre argument, "
            "la catégorie aussi, et la disponibilité est imposée par le moteur.",
        )
    attribut = ATTRIBUTS[categorie].get(entrant.champ)
    if attribut is None:
        raise OutilRefuse(
            CodeRefus.CRITERE_INVALIDE,
            f"champ inconnu pour la catégorie {categorie!r} : {entrant.champ!r} — "
            "champs connus : " + ", ".join(sorted(ATTRIBUTS[categorie])),
        )
    critere = Critere(
        champ=entrant.champ,
        operateur=entrant.operateur,
        valeur=valeur_depuis_texte(attribut, entrant.valeur),
        importance=entrant.importance,
    )
    try:
        resoudre_critere(categorie, critere)
    except CritereInvalide as erreur:
        raise OutilRefuse(CodeRefus.CRITERE_INVALIDE, str(erreur)) from erreur
    return critere
