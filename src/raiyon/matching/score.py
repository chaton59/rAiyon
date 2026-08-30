"""Sous-scores, renormalisation, pondération, classement. **Fonctions pures.**

Aucune requête ici, aucune session, aucun appel réseau : ce module ne travaille que
sur des `ProduitEnBase` déjà récupérés. C'est la moitié Python de la frontière
« SQL décide qui est candidat, Python décide comment on le présente » (§3.16), et
c'est ce qui rend le critère d'acceptation nº5 vrai **par construction** plutôt que
par discipline.

Trois règles gouvernent le calcul, et toutes les trois protègent la reproductibilité :

1. **Bornes absolues** (arbitrage G). Un sous-score est
   `(valeur - basse) / (haute - basse)`, borné à `[0, 1]`, sur des bornes constantes
   du registre. Jamais un min-max du lot candidat : le contraste serait toujours
   plein, mais le score d'un produit dépendrait des produits présents à côté de lui.
2. **L'opérateur décide de la satisfaction, le `sens` du registre ordonne à
   l'intérieur de la région satisfaisante.** Les deux sont nécessaires, et une seule
   des deux moitiés produit un défaut symétrique de l'autre : le `sens` seul classe un
   65 pouces en tête de « un écran d'au plus 24 pouces » ; l'opérateur seul y classe le
   plus petit écran du catalogue, alors que le client qui pose un plafond veut **le
   plus grand qui rentre**.
3. **Donnée absente : critère retiré, poids renormalisés** (arbitrage F). Un
   sous-score de 0 punirait l'absence, un sous-score de 0,5 inventerait une médiane
   — c'est-à-dire comblerait un trou, ce que §3.4quater interdit.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation

from raiyon.catalogue.schemas import Categorie, ProduitEnBase
from raiyon.matching.attributs import (
    ATTRIBUTS,
    PLAFONDS_RATIO,
    Attribut,
    Genre,
    Role,
    Sens,
    valeur_du_produit,
)
from raiyon.matching.criteres import (
    CritereResolu,
    Operateur,
    Optimisation,
    RequeteMatching,
)
from raiyon.matching.trace import LigneTrace, Statut, ValeurTracee

PRECISION = Decimal("0.000001")
"""Les scores sont arrondis : une division `Decimal` traîne 28 chiffres significatifs,
et un classement qui dépend du 22ᵉ n'est pas un classement, c'est un aléa."""

PLANCHER_SATISFAISANT = Decimal("0.5")
"""Frontière entre « le critère est satisfait » et « il ne l'est pas ».

Un produit qui satisfait le critère marque dans `[0,5 ; 1]`, un produit qui ne le
satisfait pas dans `[0 ; 0,5[`. La frontière est **stricte** dans les deux sens : aucun
produit non satisfaisant ne peut afficher 0,5, ce qui rend le sous-score lisible sans
avoir à consulter le statut à côté.
"""

PLAFOND_POIDS_PRIX = Decimal("0.5")
"""Poids maximal du sous-score de prix, et c'est une règle dure (arbitrage H).

Il est **strictement inférieur** au poids du plus faible critère technique — un
`souhait` pèse 1. Conséquence exacte, et c'est elle qu'un test exerce : un produit qui
rate complètement un critère technique énoncé ne peut pas repasser devant par le prix
seul. Sans ce plafond, « je veux 144 Hz et pas trop cher » finit sur un 60 Hz bon
marché.
"""


class RegistreIncomplet(ValueError):
    """Un attribut numérique sans bornes calibrées ou sans `sens`.

    C'est un bug de registre, jamais une mauvaise entrée du client : les tests de
    `tests/matching/test_attributs.py` garantissent que le cas n'arrive pas, et cette
    exception est là pour que, s'il arrivait, il fasse du bruit au lieu de choisir
    silencieusement une direction par défaut.
    """


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Un produit scoré, avec de quoi le classer et de quoi l'expliquer."""

    produit: ProduitEnBase
    score: Decimal
    score_sans_le_prix: Decimal
    lignes: tuple[LigneTrace, ...]
    avec_ligne_de_prix: bool = False
    """La dernière ligne est-elle le sous-score de prix ? Le savoir évite de le
    deviner en relisant la trace, et c'est ce qui permet de reclasser sans lui."""

    @property
    def criteres_evalues(self) -> int:
        """Critères qui ont réellement produit un sous-score.

        Les filtres durs n'y comptent pas : ils ne pondèrent rien, et le garde-fou de
        l'arbitrage F porte sur les occasions de perdre des points, pas sur les
        conditions d'entrée.
        """
        return sum(1 for ligne in self.lignes if ligne.sous_score is not None)

    @property
    def criteres_evalues_hors_prix(self) -> int:
        """Le même compte, sous-score de prix exclu."""
        lignes = self.lignes[:-1] if self.avec_ligne_de_prix else self.lignes
        return sum(1 for ligne in lignes if ligne.sous_score is not None)

    @property
    def criteres_indisponibles(self) -> int:
        return sum(1 for ligne in self.lignes if ligne.statut is Statut.INDISPONIBLE)


def en_decimal(valeur: object) -> Decimal | None:
    """Convertit une valeur de catalogue en `Decimal`, ou rend `None`.

    Un `bool` est un `int` en Python : il est écarté explicitement, faute de quoi
    `microphone=True` deviendrait la valeur numérique 1.
    """
    if valeur is None or isinstance(valeur, bool):
        return None
    if isinstance(valeur, Decimal):
        return valeur
    if isinstance(valeur, int | float | str):
        try:
            return Decimal(str(valeur))
        except InvalidOperation:
            return None
    return None


def normaliser(valeur: Decimal, basse: Decimal, haute: Decimal) -> Decimal:
    """Position de `valeur` entre deux bornes, écrasée dans `[0, 1]`.

    L'écrasement **est** la winsorisation : `memory.price_per_gb` monte à 497,5 USD/GB
    alors que la borne haute calibrée vaut 13,375. Sans plafonnement, ce seul produit
    tasserait tous les autres dans un mouchoir de poche.
    """
    if haute <= basse:
        return Decimal(0)
    return min(max((valeur - basse) / (haute - basse), Decimal(0)), Decimal(1)).quantize(PRECISION)


def _bornes(attribut: Attribut) -> tuple[Decimal, Decimal]:
    if attribut.borne_basse is None or attribut.borne_haute is None:
        raise RegistreIncomplet(
            f"{attribut.champ} est numérique mais n'a pas de bornes calibrées — "
            "relancer `uv run python scripts/calibrer_bornes.py` et recopier sa sortie"
        )
    return attribut.borne_basse, attribut.borne_haute


def _sens(attribut: Attribut) -> Sens:
    """Direction de mérite de l'attribut. Lève plutôt que d'en supposer une."""
    if attribut.sens is None:
        raise RegistreIncomplet(
            f"{attribut.champ} est numérique mais n'a pas de sens de mérite — sans lui, "
            "le classement à l'intérieur de la région satisfaisante serait arbitraire"
        )
    return attribut.sens


def sous_score_numerique(resolu: CritereResolu, valeur: Decimal) -> Decimal:
    """Sous-score d'un critère numérique.

    > **L'opérateur décide de la satisfaction ; le `sens` du registre ordonne à
    > l'intérieur de la région satisfaisante.**

    Il faut les deux, et ce tableau est là pour que le prochain raffinement ne
    réintroduise pas l'un des deux défauts symétriques — chacun a été livré une fois :

    | critère | `sens` du registre | attendu |
    | --- | --- | --- |
    | `refresh_rate` `au_moins` 144 | plus haut mieux | 240 Hz devant 144 Hz |
    | `screen_size` `au_plus` 24 | plus haut mieux | 24″ devant 21,5″ |
    | `tdp` `au_plus` 65 | plus bas mieux | 35 W devant 65 W |
    | `price_per_gb` `au_plus` 5 | plus bas mieux | 0,05 devant 4,90 |

    Les lignes 1, 3 et 4 sont rendues par l'opérateur **ou** par le `sens` : les deux y
    disent la même chose. C'est la ligne 2 qui les sépare — un plafond posé sur un
    attribut dont le mérite croît. Le client qui dit « au plus 24 pouces » veut le plus
    grand qui rentre, pas le plus petit qui existe.

    `egal` ne relève d'aucune des deux : la proximité à la valeur demandée est la seule
    sémantique correcte, et le `sens` n'y a rien à faire — « exactement 1 To » ne veut
    dire ni « le plus gros » ni « le plus petit ».
    """
    basse, haute = _bornes(resolu.attribut)
    seuil = resolu.valeur
    if not isinstance(seuil, Decimal):  # pragma: no cover - garanti par la résolution
        raise TypeError(f"{resolu.champ} : valeur numérique attendue, reçu {seuil!r}")

    if resolu.operateur is Operateur.EGAL:
        if haute <= basse:
            return Decimal(0)
        proximite = Decimal(1) - abs(valeur - seuil) / (haute - basse)
        return min(max(proximite, Decimal(0)), Decimal(1)).quantize(PRECISION)

    au_moins = resolu.operateur is Operateur.AU_MOINS
    satisfait = valeur >= seuil if au_moins else valeur <= seuil
    if satisfait:
        return _ordonner_les_satisfaisants(resolu, valeur, seuil, basse, haute, au_moins=au_moins)
    return _penaliser_l_ecart(valeur, seuil, basse, haute, au_moins=au_moins)


def _ordonner_les_satisfaisants(
    resolu: CritereResolu,
    valeur: Decimal,
    seuil: Decimal,
    basse: Decimal,
    haute: Decimal,
    *,
    au_moins: bool,
) -> Decimal:
    """Classe dans `[0,5 ; 1]` les valeurs qui satisfont le critère.

    La normalisation ne porte pas sur les bornes entières mais sur **la portion qui
    satisfait le critère** : « au plus 24 pouces » sur des bornes `[21,5 ; 34]` ordonne
    entre 21,5″ et 24″, pas entre 21,5″ et 34″. Sans cela, toutes les dalles admissibles
    se tasseraient dans le bas de l'échelle et le sous-score cesserait de discriminer là
    où le client, précisément, choisit.
    """
    bas, haut = (max(seuil, basse), haute) if au_moins else (basse, min(seuil, haute))
    if haut <= bas:
        # Le seuil est hors des bornes : la région satisfaisante ne rencontre pas
        # l'échelle calibrée, il n'y a rien à ordonner. « Au moins 500 Hz » sur
        # `[60, 240]` — tout ce qui satisfait est également et pleinement satisfaisant.
        return Decimal(1)
    position = min(max((valeur - bas) / (haut - bas), Decimal(0)), Decimal(1))
    merite = position if _sens(resolu.attribut) is Sens.PLUS_HAUT_MIEUX else Decimal(1) - position
    return (PLANCHER_SATISFAISANT + PLANCHER_SATISFAISANT * merite).quantize(PRECISION)


def _penaliser_l_ecart(
    valeur: Decimal, seuil: Decimal, basse: Decimal, haute: Decimal, *, au_moins: bool
) -> Decimal:
    """Classe dans `[0 ; 0,5[` les valeurs qui ne satisfont pas le critère.

    Le sous-score décroît avec l'écart au **seuil demandé**, rapporté à la portion de
    bornes que le critère rejette. Le `sens` du registre n'intervient pas : du côté qui
    rate, le seul mérite est de rater de peu.
    """
    amplitude = (seuil - basse) if au_moins else (haute - seuil)
    if amplitude <= 0:
        # Toute la région rejetée est hors des bornes : rien à graduer, tout y est au
        # plancher. « Au moins 30 Hz » sur `[60, 240]` — un écran à 20 Hz est en dehors
        # de l'échelle, pas un peu moins bon.
        return Decimal(0)
    ecart = (seuil - valeur) if au_moins else (valeur - seuil)
    manque = min(max(ecart / amplitude, Decimal(0)), Decimal(1))
    # Arrondi **vers le bas**, pour que la frontière de `PLANCHER_SATISFAISANT` reste
    # stricte : un écart minuscule ne doit pas remonter à 0,5 par l'arrondi et faire
    # passer un produit qui rate pour un produit qui satisfait.
    return (PLANCHER_SATISFAISANT * (Decimal(1) - manque)).quantize(PRECISION, rounding=ROUND_DOWN)


def _satisfait(resolu: CritereResolu, valeur: Decimal | bool | str) -> bool:
    """La valeur du produit satisfait-elle littéralement la demande ?"""
    demandee = resolu.valeur
    if isinstance(valeur, Decimal) and isinstance(demandee, Decimal):
        if resolu.operateur is Operateur.AU_MOINS:
            return valeur >= demandee
        if resolu.operateur is Operateur.AU_PLUS:
            return valeur <= demandee
    return valeur == demandee


def evaluer_critere(produit: ProduitEnBase, resolu: CritereResolu) -> LigneTrace:
    """Confronte un critère à un produit et rend sa ligne de trace.

    ⚠️ Les filtres durs de genre `texte` (`marque`) sont réputés **matchés** sans
    comparaison. Leur égalité se juge sur une clé normalisée — « G.Skill » et
    « gskill » sont la même marque — et cette normalisation s'écrit **une seule fois,
    en SQL** (arbitrage L). La rejouer ici en serait une seconde version, qui
    dériverait. Le produit est dans le lot : le dépôt a déjà tranché.
    """
    attribut = resolu.attribut
    brute = valeur_du_produit(produit, attribut)

    if attribut.genre is Genre.NUMERIQUE:
        valeur: ValeurTracee = en_decimal(brute)
    elif isinstance(brute, bool | str):
        valeur = brute
    else:
        valeur = None

    if valeur is None:
        return _ligne(resolu, Statut.INDISPONIBLE, None, None, None)

    if resolu.role_applique is Role.FILTRE_DUR:
        statut = (
            Statut.MATCHE
            if attribut.genre is Genre.TEXTE or _satisfait(resolu, valeur)
            else Statut.RATE
        )
        return _ligne(resolu, statut, valeur, None, None)

    if attribut.genre is Genre.NUMERIQUE and isinstance(valeur, Decimal):
        sous_score = sous_score_numerique(resolu, valeur)
    else:
        # Énumération ou booléen : l'égalité stricte ne connaît pas de demi-mesure.
        sous_score = Decimal(1) if _satisfait(resolu, valeur) else Decimal(0)

    if _satisfait(resolu, valeur):
        statut = Statut.MATCHE
    elif sous_score > 0:
        statut = Statut.PARTIEL
    else:
        statut = Statut.RATE
    return _ligne(resolu, statut, valeur, resolu.poids, sous_score)


def _ligne(
    resolu: CritereResolu,
    statut: Statut,
    valeur: ValeurTracee,
    poids: Decimal | None,
    sous_score: Decimal | None,
) -> LigneTrace:
    """Assemble la ligne de trace, écart compris."""
    demandee = resolu.valeur
    ecart = (
        valeur - demandee if isinstance(valeur, Decimal) and isinstance(demandee, Decimal) else None
    )
    return LigneTrace(
        champ=resolu.champ,
        libelle_fr=resolu.attribut.libelle_fr,
        unite=resolu.attribut.unite,
        role_applique=resolu.role_applique,
        statut=statut,
        valeur_produit=valeur,
        valeur_demandee=demandee,
        ecart=ecart,
        poids=poids,
        sous_score=sous_score,
        retrograde=resolu.retrograde,
    )


def agreger(lignes: Sequence[LigneTrace]) -> Decimal:
    """Moyenne pondérée des sous-scores disponibles, **poids renormalisés**.

    Les critères indisponibles ne comptent ni au numérateur ni au dénominateur : c'est
    la renormalisation de l'arbitrage F. Sans critère scoré du tout, le score vaut 0
    et le classement se joue entièrement sur le départage — c'est le cas nominal quand
    le client n'a posé que des filtres durs, et c'est le scénario G2.
    """
    total_poids = Decimal(0)
    total = Decimal(0)
    for ligne in lignes:
        if ligne.sous_score is None or ligne.poids is None:
            continue
        total_poids += ligne.poids
        total += ligne.poids * ligne.sous_score
    if total_poids == 0:
        return Decimal(0)
    return (total / total_poids).quantize(PRECISION)


# --------------------------------------------------------------------------- #
# Le prix — deux intentions distinctes, jamais une seule (arbitrage H)
# --------------------------------------------------------------------------- #


def score_technique_de_repli(produit: ProduitEnBase, categorie: Categorie) -> Decimal | None:
    """Mérite technique d'un produit quand le client n'a énoncé aucun critère scoré.

    « Le meilleur rapport qualité/prix en carte graphique » est une demande complète à
    elle seule : il faut bien un numérateur. On prend la moyenne des attributs de rôle
    `score` numériques de la catégorie, normalisés **dans le sens du registre**. C'est
    le seul endroit où `sens` s'applique **sans qu'aucun critère ne soit posé** ; il
    est aussi porteur dans `sous_score_numerique`, où il ordonne la région satisfaisante
    d'un `au_moins`/`au_plus`. Le prix au gigaoctet est exclu de la moyenne : il mesure
    le prix, pas la technique.
    """
    normalises: list[Decimal] = []
    for attribut in ATTRIBUTS[categorie].values():
        if attribut.role is not Role.SCORE or attribut.genre is not Genre.NUMERIQUE:
            continue
        if attribut.champ == "price_per_gb":
            continue
        valeur = en_decimal(valeur_du_produit(produit, attribut))
        if valeur is None:
            continue
        basse, haute = _bornes(attribut)
        position = normaliser(valeur, basse, haute)
        normalises.append(
            position if attribut.sens is Sens.PLUS_HAUT_MIEUX else Decimal(1) - position
        )
    if not normalises:
        return None
    return (sum(normalises, Decimal(0)) / len(normalises)).quantize(PRECISION)


def ligne_de_prix(
    produit: ProduitEnBase,
    requete: RequeteMatching,
    score_technique: Decimal | None,
    criteres_du_client: Sequence[CritereResolu],
) -> LigneTrace | None:
    """Le sous-score de prix, s'il a été demandé. `None` sinon — et c'est le défaut.

    Sans demande explicite, le prix **ne marque rien** : il borne (le budget) et il
    départage (l'ordre total), rien de plus. C'est exactement ce que le cas G2 exerce.

    `score_technique` vaut `None` quand le client n'a énoncé aucun critère scoré : le
    numérateur du rapport qualité/prix vient alors du repli sur le mérite intrinsèque
    de la catégorie. « Le meilleur rapport qualité/prix en carte graphique » est une
    demande complète à elle seule, et il faut bien un numérateur.
    """
    if requete.optimisation is Optimisation.AUCUNE:
        return None

    categorie = requete.categorie
    if requete.optimisation is Optimisation.MOINS_CHER:
        attribut = ATTRIBUTS[categorie]["prix_usd"]
        basse, haute = _bornes(attribut)
        sous_score = (Decimal(1) - normaliser(produit.prix_usd, basse, haute)).quantize(PRECISION)
        return _ligne_de_prix(attribut, produit.prix_usd, sous_score)

    prix_par_go = ATTRIBUTS[categorie].get("price_per_gb")
    if prix_par_go is not None:
        # La source donne déjà le rapport naturel, et l'étape 5 l'a recalculé sur le
        # prix retenu (arbitrage D de l'étape 5) : il est utilisable tel quel.
        if any(resolu.champ == "price_per_gb" for resolu in criteres_du_client):
            # Le client a posé son propre critère dessus : le compter deux fois lui
            # donnerait un poids qu'il n'a pas demandé.
            return None
        valeur = en_decimal(valeur_du_produit(produit, prix_par_go))
        if valeur is None:
            return _ligne_de_prix(prix_par_go, None, None)
        basse, haute = _bornes(prix_par_go)
        return _ligne_de_prix(
            prix_par_go, valeur, (Decimal(1) - normaliser(valeur, basse, haute)).quantize(PRECISION)
        )

    technique = (
        score_technique
        if score_technique is not None
        else score_technique_de_repli(produit, categorie)
    )
    if technique is None:
        return _ligne_de_prix(ATTRIBUTS[categorie]["prix_usd"], produit.prix_usd, None)

    # Ailleurs, le ratio se calcule — et se ramène dans `[0, 1]` par un **plafond
    # constant du registre**, jamais par le maximum du lot. Sinon la dépendance au lot
    # que l'arbitrage G écarte reparaîtrait sur ce seul sous-score, et « le meilleur
    # rapport qualité/prix » cesserait d'être reproductible d'une conversation à l'autre.
    plafond = PLAFONDS_RATIO[categorie]
    ratio = technique / produit.prix_usd
    sous_score = min(ratio / plafond, Decimal(1)).quantize(PRECISION)
    return _ligne_de_prix(ATTRIBUTS[categorie]["prix_usd"], produit.prix_usd, sous_score)


def _ligne_de_prix(
    attribut: Attribut, valeur: Decimal | None, sous_score: Decimal | None
) -> LigneTrace:
    """Ligne de trace du sous-score de prix. Pas de valeur demandée : il n'y a pas de
    seuil, seulement une intention de classement."""
    return LigneTrace(
        champ=attribut.champ,
        libelle_fr=attribut.libelle_fr,
        unite=attribut.unite,
        role_applique=Role.SCORE,
        statut=Statut.INDISPONIBLE if sous_score is None else Statut.MATCHE,
        valeur_produit=valeur,
        valeur_demandee=None,
        ecart=None,
        poids=None if sous_score is None else PLAFOND_POIDS_PRIX,
        sous_score=sous_score,
        retrograde=False,
    )


def evaluer(
    produit: ProduitEnBase, requete: RequeteMatching, resolus: Sequence[CritereResolu]
) -> Evaluation:
    """Score un produit et rend sa trace. Le prix passe en dernier, toujours.

    Deux scores sortent d'ici : celui qui compte, et celui qu'on aurait eu sans le
    sous-score de prix. Leur différence est ce qui rend visible, produit par produit,
    ce que le prix a déplacé dans le classement.
    """
    lignes = tuple(evaluer_critere(produit, resolu) for resolu in resolus)
    score_technique = agreger(lignes)
    enonce = any(ligne.sous_score is not None for ligne in lignes)

    prix = ligne_de_prix(produit, requete, score_technique if enonce else None, resolus)
    if prix is None:
        return Evaluation(produit, score_technique, score_technique, lignes)

    completes = (*lignes, prix)
    return Evaluation(produit, agreger(completes), score_technique, completes, True)


def evaluer_lot(
    produits: Sequence[ProduitEnBase], requete: RequeteMatching
) -> tuple[Evaluation, ...]:
    """Évalue un lot entier. Les critères ne sont résolus qu'une fois."""
    resolus = requete.resolus()
    return tuple(evaluer(produit, requete, resolus) for produit in produits)


# --------------------------------------------------------------------------- #
# Le classement
# --------------------------------------------------------------------------- #


def _cle_de_tri(
    evaluation: Evaluation, score: Decimal, evalues: int
) -> tuple[Decimal, int, Decimal, str]:
    """Ordre **total** : score, critères évalués, prix, identifiant.

    Aucun ex æquo ne subsiste, donc aucun classement ne dépend de l'ordre dans lequel
    Postgres a rendu ses lignes, et un test peut asserter une liste exacte.

    Le second terme est le garde-fou de l'arbitrage F : à score égal, le produit dont
    **plus de critères ont été réellement évalués** passe devant. Un produit à données
    manquantes a mécaniquement moins d'occasions de perdre des points ; sans ce terme,
    l'absence deviendrait un avantage.
    """
    return (-score, -evalues, evaluation.produit.prix_usd, evaluation.produit.id)


def classer(evaluations: Sequence[Evaluation]) -> tuple[Evaluation, ...]:
    """Le classement qui fait foi."""
    return tuple(
        sorted(
            evaluations,
            key=lambda evaluation: _cle_de_tri(
                evaluation, evaluation.score, evaluation.criteres_evalues
            ),
        )
    )


def classer_sans_le_prix(evaluations: Sequence[Evaluation]) -> tuple[Evaluation, ...]:
    """Le même classement, sous-score de prix retiré. Sert à mesurer ce qu'il a déplacé.

    Le prix reste au **départage** : c'est son rôle par défaut (arbitrage H), et le
    retirer ici mesurerait autre chose que l'effet du sous-score.
    """
    return tuple(
        sorted(
            evaluations,
            key=lambda evaluation: _cle_de_tri(
                evaluation, evaluation.score_sans_le_prix, evaluation.criteres_evalues_hors_prix
            ),
        )
    )
