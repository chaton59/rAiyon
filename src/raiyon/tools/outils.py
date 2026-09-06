"""Les cinq outils, en fonctions pures sur `EtatSession`, et leur sérialisation.

### L'arbitrage structurant : les outils de recherche ne prennent aucun critère

Les critères entrent par **une seule porte**, `enregistrer_criteres`. `sonder_catalogue`,
`question_suivante` et `rechercher_produits` ne prennent **aucun argument de critère, ni
de budget, ni de catégorie** : ils lisent l'état de session.

*Alternative écartée — les outils prennent des critères et le code les clampe contre la
session, comme l'esquissait §3.6.* Un tour de moins, mais l'invariant redevient une garde
à écrire, à tester et à ne jamais oublier sur un futur outil. Le raisonnement retenu est
celui de §3.10 sur le budget : **une contrainte qui n'a qu'un seul chemin ne peut pas
diverger d'elle-même.** La porte de sortie de l'étape change alors de nature — « les
arguments hostiles ne franchissent pas l'invariant » devient « il n'existe pas d'argument
par lequel passer ».

⚠️ **À dire honnêtement : on ne supprime pas la garde, on la concentre** dans
`enregistrer_criteres`, qui devient le seul endroit où la règle de collant mord.

### Quatre outils sont devenus cinq

§3.7 en décrivait quatre. Le cinquième, `record_criteria`, n'est pas une fonctionnalité
de plus : c'est la conséquence directe de l'arbitrage ci-dessus. Les critères que §3.7
faisait passer en argument de `search_products` ont besoin d'une porte à eux, et cette
porte est un outil parce que le modèle doit pouvoir l'appeler.

### Ce que rend `rechercher_produits` : le produit entier

Toutes les specs, plus la trace. *Alternative écartée — réduire le produit aux champs
cités par la trace, plus les champs d'affichage.* Elle rendrait **impossible** d'affirmer
une spec dont la pertinence n'a jamais été établie, et coûterait moins de jetons ; elle
est écartée parce qu'elle coupe la comparaison spontanée (« celui-ci a en plus du HDMI
2.1 »), qui est un bon comportement de vendeur, et parce que l'étape 9 valide de toute
façon ce qui est **cité**. Décision assumée avec sa contrepartie, pas restriction par
prudence.

### Deux natures de sortie, et une seule fonction pour les écrire

Les outils rendent des **dataclasses typées** ; `en_tool_result()` est seule à les
transformer en dictionnaire. Les tests assertionnent donc sur des objets, pas sur du
JSON, et il n'existe qu'un endroit où une clé du protocole peut changer de nom.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import assert_never

from pydantic import BaseModel, ConfigDict, Field

from raiyon.avis.cache import Avis, DepotAvis, EtatCache
from raiyon.avis.encadrement import encadrer_les_avis
from raiyon.avis.fournisseur import Fournisseur, RechercheImpossible
from raiyon.avis.recherche import AvisHorsLigne, RequeteVide, chercher_des_avis
from raiyon.catalogue.schemas import Categorie
from raiyon.matching.attributs import ATTRIBUTS
from raiyon.matching.criteres import Critere, Importance, Operateur, Optimisation
from raiyon.matching.depot import (
    BornesPrix,
    DepotProduits,
    Fourchette,
    fourchette_de_tolerance,
)
from raiyon.matching.moteur import ResultatMatching, rechercher, tolerance_budget
from raiyon.matching.sondage import (
    ChampDiscriminant,
    Distribution,
    champ_le_plus_discriminant,
    resumer,
)
from raiyon.tools.erreurs import CodeRefus, OutilRefuse
from raiyon.tools.etat import (
    CritereTexte,
    DemandeBudget,
    EtatSession,
    MouvementRefuse,
    Recherche,
    RecherchesDavis,
    fusionner,
)
from raiyon.tools.schema_outils import champs_utilisables

# --------------------------------------------------------------------------- #
# Les arguments — miroirs Pydantic du schéma JSON
# --------------------------------------------------------------------------- #
#
# `criteres.py` l'annonçait à l'étape 6 : « l'étape 7 validera les arguments de ses
# outils par des schémas Pydantic, et n'aura ainsi qu'un seul type d'erreur à traiter
# pour tout ce qui entre ». `CritereInvalide` héritant de `ValueError`, une erreur du
# registre remonte enveloppée dans une `ValidationError` sans perdre son message.
#
# Ces modèles ne **génèrent** pas le schéma JSON — celui-ci est dérivé du registre
# (`schema_outils.py`), qui sait des choses que Pydantic ignore : les libellés français,
# les unités, et quels champs vivent dans quelle catégorie. Un test vérifie que les deux
# faces déclarent exactement les mêmes propriétés, ce qui ferme la divergence sans faire
# dépendre l'une de l'autre.


AVIS_PAR_MESSAGE = 1
"""Recherches d'avis autorisées par message du client (étape 27).

Même chiffre que la recherche de produits, **motif différent** : là-bas c'est « un
composant à la fois » (arbitrage K), ici c'est la surface d'injection et le jeton qu'un
second appel doublerait. Voir `chercher_des_avis_web()` pour l'arbitrage complet."""


class _Arguments(BaseModel):
    """`extra="forbid"` : un argument inventé par le modèle est une erreur, pas un oubli."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ArgumentsCritere(_Arguments):
    champ: str
    operateur: Operateur
    valeur: str
    importance: Importance = Importance.SOUHAIT


class ArgumentsCle(_Arguments):
    champ: str
    operateur: Operateur


class ArgumentsEnregistrement(_Arguments):
    categorie: Categorie
    criteres: tuple[ArgumentsCritere, ...] = ()
    retraits: tuple[ArgumentsCle, ...] = ()
    budget_usd: str | None = None
    retirer_le_budget: bool = False
    optimisation: Optimisation | None = None


class ArgumentsSondage(_Arguments):
    champs: tuple[str, ...] = ()


class ArgumentsPrecision(_Arguments):
    question: str = Field(min_length=1)
    champ_vise: str | None = None


class ArgumentsAvis(_Arguments):
    """Une requête libre, et rien d'autre.

    ⚠️ **Pas de `produit_id`**, alors que le cache en porte un. Il serait commode — le
    modèle sait quel produit il regarde — et ce serait un champ dont le **modèle est le
    seul auteur**, écrit dans une colonne de faits. §2 dit l'inverse : un lien produit
    affirme qu'une recherche libre porte sur ce produit-là, et rien ne le vérifie. Le
    `produit_id` du cache reste donc posé par le seed, écrit à la main et relu.
    """

    requete: str = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Les résultats — typés, et sans produit là où il ne doit pas y en avoir
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ResultatEnregistrement:
    """L'état après le tour, et ce qui n'a pas pu s'appliquer.

    `mouvements_refuses` n'est pas une erreur : l'outil a réussi et appliqué le reste.
    C'est ce qui permet à l'agent de dire « je garde 144 Hz tant que tu ne me dis pas le
    contraire », au lieu de subir un échec qu'il ne saurait pas expliquer.
    """

    etat: EtatSession
    categorie: Categorie
    criteres: tuple[Critere, ...]
    budget_usd: Decimal | None
    optimisation: Optimisation
    mouvements_refuses: tuple[MouvementRefuse, ...]

    terminal: bool = False


@dataclass(frozen=True, slots=True)
class ResultatSondage:
    """Des agrégats, et **structurellement aucun produit**.

    Aucun champ de cette classe ne porte d'identifiant, de nom, ni de ligne de catalogue,
    et un test le constate **sur le type** plutôt que sur une exécution : une exécution
    ne prouve que le jeu de données qu'on lui a donné.

    Les deux comptes sont séparés par symétrie avec §3.10 : sans cela, « il te reste 12
    modèles » désignerait des produits que le client ne peut pas acheter.
    """

    etat: EtatSession
    categorie: Categorie
    budget_usd: Decimal | None
    dans_le_budget: int
    dans_la_zone_de_tolerance: int
    fourchette_prix: BornesPrix | None
    champs: tuple[Distribution, ...]
    ecartes_faute_de_donnee: Mapping[str, int]

    terminal: bool = False


@dataclass(frozen=True, slots=True)
class BesoinDeBudget:
    """Le budget manquant, **dans un champ typé distinct** — pas déguisé en attribut.

    `prix_usd` est dans `CHAMPS_A_CHAMP_DEDIE` : le rendre comme un champ à demander
    parmi les autres rouvrirait le second chemin vers le budget que §3.10 ferme. Il est
    donc rendu en tête, et à part.
    """

    fourchette_prix: BornesPrix | None


@dataclass(frozen=True, slots=True)
class ResultatQuestion:
    """Le champ à demander, et **aucune phrase** (arbitrage I de l'étape 6)."""

    etat: EtatSession
    categorie: Categorie
    candidats: int
    budget: BesoinDeBudget | None
    """Renseigné **seulement** si le budget est inconnu. C'est presque toujours la
    question de plus fort gain, et c'est celle que le client attend."""

    champ: ChampDiscriminant | None
    """`None` quand plus rien ne discrimine : c'est une réponse, pas un incident."""

    terminal: bool = False


@dataclass(frozen=True, slots=True)
class ResultatRecherche:
    """Le résultat du moteur, tel quel. La seule sortie du projet qui porte des produits."""

    etat: EtatSession
    resultat: ResultatMatching

    terminal: bool = False


@dataclass(frozen=True, slots=True)
class ResultatPrecision:
    """Un outil **terminal** : le tour est clos, l'étape 8 rendra `question` au client.

    *Alternative écartée — le garder tel que §3.7 le décrit, un outil qui ne rend rien et
    n'existe que pour être tracé.* Il force un aller-retour API supplémentaire et invite
    le modèle à appeler l'outil **puis** à réécrire la question en texte : la question est
    alors posée deux fois. En la rendant terminale, elle devient une donnée typée — utile
    aussi pour l'événement SSE de §3.12 et pour la métrique nº3, qui est un critère
    d'acceptation.
    """

    etat: EtatSession
    question: str
    champ_vise: str | None

    terminal: bool = True


@dataclass(frozen=True, slots=True)
class ResultatAvis:
    """Des avis web, et **structurellement aucun fait de catalogue** (étape 27).

    Aucun champ de cette classe ne porte d'identifiant produit, de prix, ni de comptage de
    catalogue — et un test le constate **sur le type**, comme pour `ResultatSondage` : une
    exécution ne prouve que le jeu de données qu'on lui a donné.

    ⚠️ **C'est la seule sortie du projet qui porte du texte que le projet n'a pas écrit.**
    D'où deux propriétés qui ne se lisent pas dans les champs et qui vivent dans
    `en_tool_result()` : le contenu part **encadré** (`raiyon.avis.encadrement`), et la
    charge utile ne déclare pas `faits_du_catalogue`, donc rien n'en entre dans le
    `ContexteFourni` (§3.18).
    """

    etat: EtatSession
    requete_normalisee: str
    avis: tuple[Avis, ...]
    etat_cache: EtatCache
    latence_ms: int

    source: str = "cache"
    """D'où vient ce contenu-ci : `cache`, ou le nom du fournisseur (étape 31)."""

    cout_usd: float = 0.0
    """Ce que cette recherche a coûté au fournisseur. Zéro sur un hit, par définition."""

    terminal: bool = False

    @property
    def depuis_le_cache(self) -> bool:
        """Le hit/miss du journal, **dérivé de `etat_cache` et jamais stocké à côté**.

        ⚠️ La première rédaction portait les deux en champs, et `blocs.py` reconstruisait
        l'état du cache depuis le booléen — ce qui écrasait `perime` en `absent`. C'est la
        règle générale du dépôt appliquée ici : partout où l'on re-dérive une information
        depuis une autre qui en sait moins, on se trompe. Une seule source, une propriété.
        """
        return self.etat_cache is EtatCache.TROUVE


ResultatOutil = (
    ResultatEnregistrement
    | ResultatSondage
    | ResultatQuestion
    | ResultatRecherche
    | ResultatPrecision
    | ResultatAvis
)


# --------------------------------------------------------------------------- #
# Les cinq outils
# --------------------------------------------------------------------------- #


def enregistrer_criteres(
    etat: EtatSession, arguments: ArgumentsEnregistrement, *, tour_client: int
) -> ResultatEnregistrement:
    """La seule porte par laquelle un critère entre dans la session."""
    if arguments.retirer_le_budget and arguments.budget_usd is not None:
        raise OutilRefuse(
            CodeRefus.VALEUR_ILLISIBLE,
            "budget_usd et retirer_le_budget sont donnés ensemble : choisir entre poser "
            "un plafond et le retirer.",
        )
    budget: DemandeBudget | None = None
    if arguments.retirer_le_budget:
        budget = DemandeBudget(None)
    elif arguments.budget_usd is not None:
        budget = DemandeBudget(arguments.budget_usd)

    fusion = fusionner(
        etat,
        tour_client=tour_client,
        categorie=arguments.categorie,
        ajouts=[
            CritereTexte(
                champ=entrant.champ,
                operateur=entrant.operateur,
                valeur=entrant.valeur,
                importance=entrant.importance,
            )
            for entrant in arguments.criteres
        ],
        retraits=[(retrait.champ, retrait.operateur) for retrait in arguments.retraits],
        budget=budget,
        optimisation=arguments.optimisation,
    )
    return ResultatEnregistrement(
        etat=fusion.etat,
        categorie=arguments.categorie,
        criteres=fusion.etat.criteres_de(arguments.categorie),
        budget_usd=fusion.etat.budget_usd,
        optimisation=fusion.etat.optimisation,
        mouvements_refuses=fusion.refuses,
    )


def sonder_catalogue(
    etat: EtatSession,
    depot: DepotProduits,
    arguments: ArgumentsSondage | None = None,
    *,
    tolerance: Decimal | None = None,
) -> ResultatSondage:
    """Compte, décrit, et ne rend aucun produit.

    Le budget s'applique, sinon « il te reste 12 modèles » désignerait des produits que
    le client ne peut pas acheter. Les agrégats **comptent comme contexte fourni**, et
    l'étape 9 les vérifiera comme tels.

    ⚠️ *Alternative écartée — rendre des paliers arrondis pour empêcher l'agent de déduire
    un prix exact.* Le risque est réel et il est au §7 : avec deux ou trois sondages
    resserrés, l'agent connaît le prix d'un produit qu'on ne lui a jamais donné, sans
    identifiant. Mais un arrondi est lui-même une affirmation approximative sur le
    catalogue : il en fabrique une pour en éviter une autre. La contrainte est portée par
    le prompt de l'étape 8 — « une fourchette de sondage n'est jamais le prix d'un
    produit » — et vérifiable à l'étape 9.
    """
    categorie = _categorie_courante(etat)
    requete = etat.requete()
    fourchette = Fourchette(max_inclus=etat.budget_usd)
    champs = _champs_demandes(categorie, (arguments or ArgumentsSondage()).champs)
    comptages = depot.distributions(requete, fourchette, champs)

    zone = 0
    if etat.budget_usd is not None:
        zone = depot.compter(
            requete, fourchette_de_tolerance(etat.budget_usd, _tolerance(tolerance))
        )

    return ResultatSondage(
        etat=etat,
        categorie=categorie,
        budget_usd=etat.budget_usd,
        dans_le_budget=depot.compter(requete, fourchette),
        dans_la_zone_de_tolerance=zone,
        fourchette_prix=depot.bornes_de_prix(requete, fourchette),
        champs=tuple(resumer(comptages[champ], ATTRIBUTS[categorie][champ]) for champ in champs),
        ecartes_faute_de_donnee=depot.ecartes_faute_de_donnee(requete, fourchette),
    )


def question_suivante(
    etat: EtatSession, depot: DepotProduits, *, tolerance: Decimal | None = None
) -> ResultatQuestion:
    """Le champ manquant le plus discriminant, et le budget en cas spécial.

    Les champs déjà contraints sont exclus du calcul : §3.7 parle du champ **manquant**,
    et redemander ce que le client vient de dire est le mode d'échec que §3.9 nomme
    l'interrogatoire.
    """
    categorie = _categorie_courante(etat)
    requete = etat.requete()
    fourchette = Fourchette(max_inclus=etat.budget_usd)

    deja_dits = {critere.champ for critere in etat.criteres_de(categorie)}
    attributs = {
        champ: attribut
        for champ, attribut in champs_utilisables(categorie).items()
        if champ not in deja_dits
    }
    comptages = depot.distributions(requete, fourchette, tuple(attributs))

    besoin = None
    if etat.budget_usd is None:
        besoin = BesoinDeBudget(fourchette_prix=depot.bornes_de_prix(requete, fourchette))

    return ResultatQuestion(
        etat=etat,
        categorie=categorie,
        candidats=depot.compter(requete, fourchette),
        budget=besoin,
        champ=champ_le_plus_discriminant(comptages, attributs),
    )


def rechercher_produits(
    etat: EtatSession, depot: DepotProduits, *, tour_client: int, tolerance: Decimal | None = None
) -> ResultatRecherche:
    """Cherche, et **refuse une seconde catégorie dans le même tour** (arbitrage E).

    Le moteur garantit qu'un **appel** rend une seule catégorie. Il ne garantit rien sur
    un **tour** : rien ne l'empêcherait d'être appelé deux fois sur deux catégories et de
    servir la « config gaming » que §8 met hors périmètre. `sonder_catalogue` et
    `question_suivante` restent libres — ils ne rendent aucun produit, donc ils ne peuvent
    rien faire citer.

    C'est ce qui rend le critère d'acceptation nº2 vérifiable **produit par produit**,
    sans notion de panier.
    """
    categorie = _categorie_courante(etat)
    precedente = etat.recherche_du_tour
    if (
        precedente is not None
        and precedente.tour_client == tour_client
        and precedente.categorie != categorie
    ):
        raise OutilRefuse(
            CodeRefus.DEUX_CATEGORIES_DANS_UN_TOUR,
            f"une recherche a déjà été faite dans ce message du client, sur "
            f"{precedente.categorie!r}. On conseille un composant à la fois : terminer "
            f"celui-là, puis proposer de passer à {categorie!r} au message suivant.",
        )

    return ResultatRecherche(
        etat=replace(etat, recherche_du_tour=Recherche(tour_client, categorie)),
        resultat=rechercher(depot, etat.requete(), tolerance=tolerance),
    )


def demander_precision(etat: EtatSession, arguments: ArgumentsPrecision) -> ResultatPrecision:
    """Pose la question et **clôt le tour**. L'étape 8 rendra le texte au client tel quel."""
    champ = arguments.champ_vise
    if champ is not None:
        categorie = _categorie_courante(etat)
        if champ not in ATTRIBUTS[categorie]:
            raise OutilRefuse(
                CodeRefus.CHAMP_INCONNU,
                f"{champ!r} n'existe pas dans la catégorie {categorie!r} — poser la "
                "question sans champ visé, ou viser un champ de cette catégorie.",
            )
    return ResultatPrecision(etat=etat, question=arguments.question, champ_vise=champ)


def chercher_des_avis_web(
    etat: EtatSession,
    arguments: ArgumentsAvis,
    *,
    depot: DepotAvis,
    fournisseur: Fournisseur | None,
    tour_client: int,
    maintenant: datetime,
) -> ResultatAvis:
    """Le sixième outil. **Ne touche ni au catalogue, ni à l'état des critères.**

    ### La borne : une recherche d'avis par message du client

    Même borne que `search_products`, et **le motif n'est pas le même**. Là-bas, elle vient
    de « un composant à la fois » (arbitrage K) ; ici, elle vient de ce que chaque appel
    fait entrer dans la fenêtre : du **texte de tiers**, c'est-à-dire de la surface
    d'injection et du jeton. Deux appels doublent les deux, dans un tour qui ne peut de
    toute façon porter qu'une recommandation.

    ⚠️ **Ce n'est pas une borne de coût.** L'argument économique a été mesuré et il est
    faux (§3.18) : 81 recherches valent 0,40 $. Une borne posée « pour économiser » aurait
    été une borne sans raison, et la première mesure l'aurait fait sauter.

    *Alternative écartée — deux appels, pour permettre de comparer deux produits.* C'est le
    besoin réel qui la justifierait, et il se sert autrement : une requête « X vs Y avis »
    couvre les deux, et la description de l'outil le dit. Si l'étape 28 montre le modèle
    buter sur cette borne, elle est une constante — mais on ne relâche pas d'avance une
    garde qui protège la surface d'injection, sur une gêne supposée.

    Le compteur est **incrémenté même quand l'appel échoue** en aval : il compte ce que le
    modèle a demandé, pas ce qui a réussi. Sans quoi un miss hors ligne rendrait la borne
    gratuite, et un tour pourrait enchaîner les refus.
    """
    precedentes = etat.avis_du_tour
    deja = precedentes.compte if precedentes and precedentes.tour_client == tour_client else 0
    if deja >= AVIS_PAR_MESSAGE:
        raise OutilRefuse(
            CodeRefus.TROP_DAVIS_DANS_UN_TOUR,
            "une recherche d'avis a déjà eu lieu dans ce message du client. "
            "Une seule par message : formuler une requête qui couvre le besoin en une "
            "fois, ou reprendre au message suivant.",
        )
    apres = replace(etat, avis_du_tour=RecherchesDavis(tour_client, deja + 1))

    try:
        trouvaille = chercher_des_avis(
            arguments.requete,
            depot=depot,
            fournisseur=fournisseur,
            maintenant=maintenant,
        )
    except RequeteVide as vide:
        raise OutilRefuse(
            CodeRefus.REQUETE_VIDE,
            f"{arguments.requete!r} ne contient aucun mot cherchable. Formuler la "
            "recherche avec le nom du produit ou le sujet voulu.",
        ) from vide
    except RechercheImpossible as panne:
        # ⚠️ **Une panne réseau n'interrompt pas la conversation.** Le fournisseur a déjà
        # filtré la clé de son message (`_erreur_propre`) ; ce qui remonte au modèle dit
        # qu'il n'y a pas d'avis, pas qu'il s'est passé quelque chose de technique.
        raise OutilRefuse(
            CodeRefus.AVIS_HORS_LIGNE,
            f"{panne}. Poursuivre sans avis, ou reformuler au message suivant.",
        ) from None
    except AvisHorsLigne as hors_ligne:
        # 🔴 Le miss bruyant du mode hors ligne. Le message nomme la clé **normalisée** :
        # c'est exactement ce qu'il faut écrire dans `data/seed/avis.jsonl`.
        raise OutilRefuse(
            CodeRefus.AVIS_HORS_LIGNE,
            f"aucun avis en cache pour la requête normalisée "
            f"{hors_ligne.requete_normalisee!r}, et aucune recherche en ligne n'est "
            "disponible dans cette exécution.",
        ) from hors_ligne

    return ResultatAvis(
        etat=apres,
        requete_normalisee=trouvaille.requete_normalisee,
        avis=trouvaille.avis,
        etat_cache=trouvaille.etat_cache,
        latence_ms=trouvaille.latence_ms,
        source=trouvaille.source,
        cout_usd=trouvaille.cout_usd,
    )


def _categorie_courante(etat: EtatSession) -> Categorie:
    """Un tour, une catégorie — et elle est obligatoire (arbitrage K de l'étape 6)."""
    if etat.categorie_courante is None:
        raise OutilRefuse(
            CodeRefus.CATEGORIE_ABSENTE,
            "aucune catégorie n'est encore enregistrée : il n'y a pas de sous-catalogue "
            "sur lequel travailler. Enregistrer d'abord la catégorie et ce que le client "
            "a dit.",
        )
    return etat.categorie_courante


def _champs_demandes(categorie: Categorie, demandes: Sequence[str]) -> tuple[str, ...]:
    """Les champs à décrire, dédoublonnés, dans l'ordre demandé — ou tous par défaut."""
    utilisables = champs_utilisables(categorie)
    if not demandes:
        return tuple(utilisables)
    retenus: dict[str, None] = {}
    for champ in demandes:
        if champ not in utilisables:
            raise OutilRefuse(
                CodeRefus.CHAMP_INCONNU,
                f"{champ!r} ne se sonde pas dans la catégorie {categorie!r} — champs "
                "sondables : " + ", ".join(sorted(utilisables)),
            )
        retenus[champ] = None
    return tuple(retenus)


def _tolerance(tolerance: Decimal | None) -> Decimal:
    """Injectable jusqu'aux tests : aucun test de `tests/tools/` n'a besoin de `.env`."""
    return tolerance if tolerance is not None else tolerance_budget()


# --------------------------------------------------------------------------- #
# La sérialisation — une seule fonction
# --------------------------------------------------------------------------- #


def en_tool_result(resultat: ResultatOutil | OutilRefuse) -> dict[str, object]:
    """Le contenu du bloc `tool_result`. **Le seul endroit où une clé porte un nom.**

    Un `OutilRefuse` passe par ici aussi : c'est un `tool_result` comme un autre, que
    l'étape 8 marquera `is_error`. Le modèle lit le message, corrige, rappelle — le refus
    fait partie du dialogue, il ne l'interrompt pas.

    L'état de session n'est **jamais** sérialisé : chaque branche construit sa charge
    utile explicitement, et `_json()` ne fait que normaliser les valeurs. Un
    `asdict(resultat)` générique aurait envoyé au modèle l'objet même qui le contraint.
    """
    if isinstance(resultat, OutilRefuse):
        return {"ok": False, "erreur": resultat.code.value, "message": resultat.message}
    if isinstance(resultat, ResultatAvis):
        # ⚠️ **Cette branche ne déclare PAS `faits_du_catalogue`, et c'est l'exclusion du
        # §3.18 elle-même.** Le validateur ne lit que les charges qui la portent à `True` :
        # rien de ce que le web rend n'est donc citable comme un fait. Voir
        # `tests/validateur/test_exclusion_du_web.py`, qui échoue si on la rétablit ici.
        rappel, encadres = encadrer_les_avis(resultat.avis)
        return {
            "ok": True,
            "avertissement": rappel,
            "requete": resultat.requete_normalisee,
            "nombre": len(encadres),
            "avis": encadres,
        }
    if isinstance(resultat, ResultatEnregistrement):
        return _charge(
            {
                "ok": True,
                "faits_du_catalogue": True,
                "categorie": resultat.categorie,
                "criteres": list(resultat.criteres),
                "budget_usd": resultat.budget_usd,
                "optimisation": resultat.optimisation,
                "mouvements_refuses": list(resultat.mouvements_refuses),
            }
        )
    if isinstance(resultat, ResultatSondage):
        return _charge(
            {
                "ok": True,
                "faits_du_catalogue": True,
                "categorie": resultat.categorie,
                "budget_usd": resultat.budget_usd,
                "dans_le_budget": resultat.dans_le_budget,
                "dans_la_zone_de_tolerance": resultat.dans_la_zone_de_tolerance,
                "fourchette_prix": resultat.fourchette_prix,
                "champs": list(resultat.champs),
                "ecartes_faute_de_donnee": dict(resultat.ecartes_faute_de_donnee),
            }
        )
    if isinstance(resultat, ResultatQuestion):
        return _charge(
            {
                "ok": True,
                "faits_du_catalogue": True,
                "categorie": resultat.categorie,
                "candidats": resultat.candidats,
                "budget": resultat.budget,
                "champ": resultat.champ,
            }
        )
    if isinstance(resultat, ResultatRecherche):
        moteur = resultat.resultat
        return _charge(
            {
                "ok": True,
                "faits_du_catalogue": True,
                "categorie": moteur.categorie,
                "candidats_trouves": moteur.candidats_trouves,
                "produits": [produit.model_dump(mode="json") for produit in moteur.produits],
                "traces": list(moteur.traces),
                "au_dessus_du_budget": [
                    {
                        "produit": hors.produit.model_dump(mode="json"),
                        "ecart_usd": hors.ecart_usd,
                    }
                    for hors in moteur.au_dessus_du_budget
                ],
                "ecartes_faute_de_donnee": dict(moteur.ecartes_faute_de_donnee),
                "diagnostic": moteur.diagnostic,
            }
        )
    if isinstance(resultat, ResultatPrecision):
        return {
            "ok": True,
            "terminal": True,
            "question": resultat.question,
            "champ_vise": resultat.champ_vise,
        }
    assert_never(resultat)


def _charge(donnees: dict[str, object]) -> dict[str, object]:
    """Normalise chaque valeur d'une charge utile, sans toucher à ses clés."""
    return {cle: _json(valeur) for cle, valeur in donnees.items()}


def _json(valeur: object) -> object:
    """Normalise les valeurs, jamais la forme.

    Les `Decimal` partent en **chaînes**, comme partout ailleurs dans le projet : un
    flottant JSON perdrait des décimales sur un prix, et le validateur de l'étape 9
    compare des caractères.
    """
    if isinstance(valeur, StrEnum):
        return valeur.value
    if isinstance(valeur, Decimal):
        return str(valeur)
    if isinstance(valeur, BaseModel):
        return valeur.model_dump(mode="json")
    if is_dataclass(valeur) and not isinstance(valeur, type):
        return {
            champ.name: _json(getattr(valeur, champ.name))
            for champ in fields(valeur)
            if champ.name != "etat"
        }
    if isinstance(valeur, list | tuple):
        return [_json(element) for element in valeur]
    if isinstance(valeur, dict):
        return {str(cle): _json(element) for cle, element in valeur.items()}
    return valeur
