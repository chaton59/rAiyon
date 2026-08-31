"""Ce qu'on peut dire d'un sous-catalogue sans en montrer un seul produit. **Pur.**

Deux usages, une seule mécanique :

* **le sondage** (`probe_catalog`) rend les valeurs présentes, tronquées et déclarées
  comme telles ;
* **la relance** (`suggest_next_question`) rend le champ dont la réponse découperait le
  mieux ce qui reste.

Les deux partent des `Comptages` que le dépôt a produits par `GROUP BY`, et **rien ici
n'interroge la base** : c'est la frontière de §3.16, et c'est ce qui rend l'entropie
testable en injectant des nombres à la main, comme `relachement.py`.

---

### La mesure : entropie de Shannon normalisée, pondérée par la couverture

`score = H(valeurs) / log2(k) x (produits déclarant la valeur / total)`

La pondération n'est pas un raffinement. Sans elle, l'outil proposerait de demander une
vitesse de rotation à un client dont 66 % des candidats sont des SSD — et la réponse
écarterait des produits sur une **absence de donnée**, ce que §3.4quater interdit.

*Alternative écartée — « le champ qui coupe le plus près de la moitié ».* Correct sur un
booléen, inutilisable au-delà de deux valeurs.

⚠️ **Deux limites, écrites plutôt que masquées.**

1. **L'entropie sur les valeurs distinctes est grossière pour un numérique continu.**
   Sur `price_per_gb` ou `core_clock`, chaque produit a presque sa propre valeur et
   l'entropie est donc maximale — le champ paraît idéal alors que la question serait
   inutile. D'où l'exclusion par `SEUIL_DE_DISPERSION` ci-dessous : c'est **un seuil,
   pas une théorie**. Le découpage en classes est hors périmètre.
2. **La normalisation par `log2(k)` mesure l'équilibre, pas le gain brut.** Un champ
   binaire parfaitement équilibré et un champ à quinze valeurs équilibrées marquent tous
   deux 1, alors que le second apporte 3,9 bits contre 1. C'est ce que l'arbitrage H
   demande ; le départage à score égal se fait donc sur le nombre de valeurs
   atteignables, ce qui rattrape l'essentiel du cas sans changer la mesure.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from raiyon.matching.attributs import Attribut, Genre
from raiyon.matching.depot import Comptages

LIMITE_VALEURS_RENDUES = 15
"""Combien de valeurs distinctes partent au modèle. 241 chipsets ne rentrent pas, et le
nombre exact importe moins que le fait que la troncature soit **déclarée** : sans
`total_distinct` et `tronque`, l'agent écrirait « les chipsets disponibles sont… » et ce
serait faux par omission."""

SEUIL_DE_DISPERSION = Decimal("0.5")
"""Un champ dont les valeurs distinctes dépassent cette part des candidats est écarté du
classement : un champ que presque personne ne partage ne discrimine rien d'utile à
demander. Seuil, pas théorie — voir la limite nº1 en tête de module."""

PRECISION = Decimal("0.0001")
"""Le score est arrondi **une fois**, et c'est ce nombre arrondi qui classe *et* qui part
au modèle. Deux précisions — une pour trier, une pour afficher — feraient exister deux
classements dont un seul serait visible."""


@dataclass(frozen=True, slots=True)
class ValeurComptee:
    """Une valeur du catalogue et son effectif. Le nombre est un fait, pas un ratio."""

    valeur: str
    effectif: int


@dataclass(frozen=True, slots=True)
class Distribution:
    """Ce qu'un champ dit du sous-catalogue, **troncature déclarée**.

    `total_distinct` et `tronque` sont **toujours présents**, y compris quand il n'y a
    rien à tronquer — même contrat que `ecartes_faute_de_donnee` au §3.16. Un champ
    optionnel n'existe qu'à moitié : celui qui le lit finit par supposer sa valeur.
    """

    champ: str
    libelle_fr: str
    unite: str | None
    valeurs: tuple[ValeurComptee, ...]
    total_distinct: int
    tronque: bool
    renseignes: int
    total: int

    @property
    def sans_valeur(self) -> int:
        """Produits du sous-catalogue qui ne déclarent pas ce champ."""
        return self.total - self.renseignes


@dataclass(frozen=True, slots=True)
class ChampDiscriminant:
    """Le champ à demander, et de quoi rédiger la question — **sans aucune phrase**.

    Le français est du vocabulaire, pas des phrases (arbitrage I de l'étape 6) : le
    libellé et l'unité viennent du registre, les valeurs viennent du catalogue, et c'est
    l'agent qui écrit « tu préfères une dalle IPS ou VA ? ».
    """

    champ: str
    libelle_fr: str
    unite: str | None
    score: Decimal
    distribution: Distribution


def ordonner(comptages: Comptages, attribut: Attribut) -> tuple[ValeurComptee, ...]:
    """Fréquence décroissante, puis valeur croissante. **Ordre total, décidé ici.**

    Aucune réponse client ne doit dépendre de l'ordre de retour de Postgres — ni de sa
    collation. La valeur croissante se lit dans le genre déclaré par le registre : sur un
    numérique, « 512 » vient après « 1000 », ce que l'ordre alphabétique inverserait.
    """
    return tuple(
        ValeurComptee(valeur=valeur, effectif=effectif)
        for valeur, effectif in sorted(
            comptages.effectifs, key=lambda ligne: (-ligne[1], _cle_de_valeur(attribut, ligne[0]))
        )
    )


def _cle_de_valeur(attribut: Attribut, valeur: str) -> Decimal | str:
    """Le tri d'un champ est homogène : soit tout numérique, soit tout textuel."""
    if attribut.genre is not Genre.NUMERIQUE:
        return valeur
    try:
        return Decimal(valeur)
    except ArithmeticError:
        # Une valeur numérique illisible ne doit pas faire échouer un sondage : elle
        # passe en queue de tri plutôt que de faire lever l'outil. Le cas n'existe pas
        # sur le seed — `ProduitEnBase` le rendrait impossible — mais le tri ne doit pas
        # être ce qui l'apprend.
        return Decimal("Infinity")


def resumer(
    comptages: Comptages, attribut: Attribut, limite: int = LIMITE_VALEURS_RENDUES
) -> Distribution:
    """Ordonne, tronque, et **dit qu'il a tronqué**."""
    ordonnees = ordonner(comptages, attribut)
    return Distribution(
        champ=comptages.champ,
        libelle_fr=attribut.libelle_fr,
        unite=attribut.unite,
        valeurs=ordonnees[:limite],
        total_distinct=comptages.total_distinct,
        tronque=len(ordonnees) > limite,
        renseignes=comptages.renseignes,
        total=comptages.total,
    )


def entropie_normalisee(effectifs: Sequence[int]) -> Decimal:
    """Entropie de Shannon ramenée dans `[0, 1]` par `log2(k)`.

    Vaut 0 sur une valeur unique — savoir que tous les écrans restants sont en 16:9
    n'apprend rien —, et 1 sur une distribution parfaitement équilibrée.
    """
    total = sum(effectifs)
    positifs = [effectif for effectif in effectifs if effectif > 0]
    if total <= 0 or len(positifs) < 2:
        return Decimal(0)
    entropie = -sum((effectif / total) * math.log2(effectif / total) for effectif in positifs)
    return _arrondir(entropie / math.log2(len(positifs)))


def score_de_discrimination(comptages: Comptages) -> Decimal:
    """L'entropie normalisée, **multipliée par la couverture réelle du sous-catalogue**."""
    if comptages.total <= 0:
        return Decimal(0)
    couverture = Decimal(comptages.renseignes) / Decimal(comptages.total)
    valeurs = [effectif for _, effectif in comptages.effectifs]
    return _arrondir(float(entropie_normalisee(valeurs) * couverture))


def _arrondir(valeur: float) -> Decimal:
    return Decimal(str(valeur)).quantize(PRECISION)


def trop_disperse(comptages: Comptages) -> bool:
    """Un champ que presque personne ne partage ne discrimine rien d'utile à demander.

    C'est la parade — approximative, et assumée comme telle — à la limite nº1 : sur un
    numérique continu, chaque produit porte presque sa propre valeur, et l'entropie
    normalisée y est maximale sans qu'il y ait quoi que ce soit à demander.
    """
    return Decimal(comptages.total_distinct) > SEUIL_DE_DISPERSION * Decimal(comptages.total)


def champ_le_plus_discriminant(
    comptages: Mapping[str, Comptages], attributs: Mapping[str, Attribut]
) -> ChampDiscriminant | None:
    """Le champ dont la réponse découperait le mieux ce qui reste, ou `None`.

    `None` est une réponse : quand plus rien ne discrimine — un seul candidat, ou des
    champs tous unanimes —, il n'y a pas de question utile à poser, et inventer la
    moins mauvaise ferait exactement l'interrogatoire que §3.9 cherche à éviter.

    L'ordre est total : `(score décroissant, valeurs distinctes décroissantes, champ)`.
    Le second terme rattrape la limite nº2 — à équilibre égal, le champ à quinze valeurs
    apprend plus que le binaire —, et le nom du champ ferme l'ordre pour que rien ne
    dépende de celui du dictionnaire.
    """
    classables = [
        (score_de_discrimination(compte), compte)
        for champ, compte in comptages.items()
        if champ in attributs and not trop_disperse(compte)
    ]
    retenus = [(score, compte) for score, compte in classables if score > 0]
    if not retenus:
        return None

    score, compte = min(
        retenus, key=lambda ligne: (-ligne[0], -ligne[1].total_distinct, ligne[1].champ)
    )
    attribut = attributs[compte.champ]
    return ChampDiscriminant(
        champ=compte.champ,
        libelle_fr=attribut.libelle_fr,
        unite=attribut.unite,
        score=score,
        distribution=resumer(compte, attribut),
    )
