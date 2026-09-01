"""Le modèle de critères : générique, validé dynamiquement contre le registre.

Un critère est un quadruplet `(champ, opérateur, valeur, importance)`. Il n'existe
**pas** de modèle par catégorie.

*Alternative écartée — six modèles Pydantic typés, miroirs de `SpecsCpu`,
`SpecsMoniteur`…* Ils donneraient du typage statique et de meilleurs messages
d'erreur. Écartée pour deux raisons : ils créeraient six modèles à maintenir en
parallèle de six modèles de specs, donc une divergence garantie à la première
évolution du schéma ; et le schéma JSON d'outil de l'étape 7 en deviendrait énorme.
Le générique paie en typage ce qu'il gagne en surface, et c'est **le registre qui
récupère la validation** — champ inconnu, champ d'une autre catégorie, opérateur
incompatible avec le genre, promotion interdite.

Deux règles de rôle, et elles ne sont pas symétriques (arbitrage D) :

* **Rétrogradation, ouverte sur le gradué.** Un `souhait` sur un filtre dur gradué
  devient un score. « Plutôt 144 Hz » est une nuance que l'agent doit pouvoir dire.
* **Promotion, interdite et bruyante.** Un `bloquant` sur un attribut de rôle `score`
  lève. Promouvoir `boost_clock` — 66,1 % de remplissage sur le seed — en filtre dur
  exclurait un tiers du catalogue sur une absence de donnée : un comblement d'absence
  par la porte de derrière, que §3.4quater interdit.

La fusion des critères d'un tour à l'autre et la règle de collant appartiennent à
l'étape 7 ; rien de tout cela n'est ici. Ce module écrit seulement ce que cette
couche aura besoin de lire : le drapeau `retrogradable` du registre, et la trace des
rétrogradations effectivement appliquées.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from raiyon.catalogue.schemas import Categorie
from raiyon.matching.attributs import ATTRIBUTS, Attribut, Genre, Role

ValeurCritere = bool | int | Decimal | str
"""Ce qu'un critère peut porter. La conversion vers le type qu'attend le genre de
l'attribut est faite à la résolution, pas ici : c'est le registre qui sait qu'un
`refresh_rate` est un nombre et qu'une `interface` est une chaîne."""


class CritereInvalide(ValueError):
    """Un critère que le registre refuse. Toujours explicite sur le motif.

    Hérite de `ValueError` : levée depuis `resoudre_critere()`, elle sort telle
    quelle ; levée depuis un validateur de `RequeteMatching`, Pydantic l'enveloppe
    dans une `ValidationError` en conservant son message. C'est voulu — l'étape 7
    validera les arguments de ses outils par des schémas Pydantic, et n'aura ainsi
    qu'un seul type d'erreur à traiter pour tout ce qui entre.
    """


class Importance(StrEnum):
    """Ce que le client a dit du critère, pas ce que le moteur en fait."""

    SOUHAIT = "souhait"
    IMPORTANT = "important"
    BLOQUANT = "bloquant"


class Operateur(StrEnum):
    """Comparaisons admises.

    Trois suffisent. `contient` n'existe pas, et c'est une décision : sur les
    énumérations, « RTX 4070 » attraperait silencieusement « RTX 4070 Ti » et le
    critère d'acceptation nº4 se dégraderait sans qu'on le voie (§3.7). Un `parmi`
    (plusieurs valeurs acceptées) serait légitime ; il attendra que l'étape 7 en
    montre le besoin plutôt que d'être ajouté par anticipation.
    """

    AU_MOINS = "au_moins"
    AU_PLUS = "au_plus"
    EGAL = "egal"


class Optimisation(StrEnum):
    """Ce que le client demande de faire du prix dans le **classement**.

    Le budget, lui, n'est pas ici : il borne, il ne classe pas. Deux intentions
    distinctes et non interchangeables — le moins cher et le mieux placé ne sont pas
    le même produit (arbitrage H).
    """

    AUCUNE = "aucune"
    """Par défaut. Le prix ne marque rien et ne sert qu'au départage."""

    MOINS_CHER = "moins_cher"
    RAPPORT_QUALITE_PRIX = "rapport_qualite_prix"


LIBELLES_OPTIMISATION: dict[Optimisation, str] = {
    Optimisation.AUCUNE: "aucune",
    Optimisation.MOINS_CHER: "le moins cher",
    Optimisation.RAPPORT_QUALITE_PRIX: "le meilleur rapport qualité/prix",
}
"""Le français d'une valeur d'énumération, **du même côté que la valeur**.

Même geste que `LIBELLES_CATEGORIE` : le fil porte le jeton *et* son libellé, et le front
n'a aucune table de traduction à tenir (§3.4ter). Sans cela, l'étape 11 afficherait
`rapport_qualite_prix` à un client, ou coderait « le meilleur rapport qualité/prix » dans
du JavaScript — c'est-à-dire une seconde source de français, hors du dépôt Python.

C'est de la **donnée** : aucune majuscule, aucun article superflu. La mise en forme est
l'affaire du front.
"""


OPERATEURS_ADMIS: dict[Genre, frozenset[Operateur]] = {
    Genre.NUMERIQUE: frozenset(Operateur),
    Genre.ENUMERE: frozenset({Operateur.EGAL}),
    Genre.BOOLEEN: frozenset({Operateur.EGAL}),
    Genre.TEXTE: frozenset({Operateur.EGAL}),
}

POIDS_PAR_IMPORTANCE: dict[Importance, Decimal] = {
    Importance.SOUHAIT: Decimal("1"),
    Importance.IMPORTANT: Decimal("2"),
}
"""Poids d'un critère scoré. `BLOQUANT` n'y figure pas : un critère bloquant filtre,
il ne pondère pas — et sur un attribut de rôle `score`, il lève."""

CHAMPS_A_CHAMP_DEDIE: frozenset[str] = frozenset({"prix_usd", "categorie", "disponible"})
"""Champs qui ne passent **jamais** par la liste de critères d'une requête.

`categorie` et `budget_usd` sont des champs propres de `RequeteMatching`, et
`disponible` est imposé par le moteur. Les accepter aussi comme critères ouvrirait
deux chemins vers la même contrainte, donc la possibilité qu'ils divergent — le mode
d'échec exact que §3.10 rend impossible sur le budget en lui donnant sa colonne."""


class Critere(BaseModel):
    """Un critère tel que la couche outils de l'étape 7 le transmettra."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    champ: str = Field(min_length=1)
    operateur: Operateur
    valeur: ValeurCritere
    importance: Importance = Importance.SOUHAIT


@dataclass(frozen=True, slots=True)
class CritereResolu:
    """Un critère confronté au registre : rôle réellement appliqué, poids, valeur typée."""

    critere: Critere
    attribut: Attribut
    role_applique: Role
    valeur: Decimal | bool | str
    retrograde: bool
    poids: Decimal | None

    @property
    def champ(self) -> str:
        return self.critere.champ

    @property
    def operateur(self) -> Operateur:
        return self.critere.operateur

    @property
    def importance(self) -> Importance:
        return self.critere.importance

    @property
    def filtre(self) -> bool:
        """Ce critère part-il en `WHERE` SQL ?"""
        return self.role_applique is Role.FILTRE_DUR


def _convertir(attribut: Attribut, valeur: ValeurCritere) -> Decimal | bool | str:
    """Amène la valeur au type qu'exige le genre de l'attribut, ou lève.

    Un `bool` est un `int` en Python : le test de booléen passe donc **avant** celui
    de nombre, faute de quoi `microphone=True` deviendrait `Decimal(1)`.
    """
    if attribut.genre is Genre.BOOLEEN:
        if not isinstance(valeur, bool):
            raise CritereInvalide(
                f"{attribut.champ} ({attribut.libelle_fr}) attend un booléen, reçu {valeur!r}"
            )
        return valeur

    if attribut.genre is Genre.NUMERIQUE:
        if isinstance(valeur, bool):
            raise CritereInvalide(
                f"{attribut.champ} ({attribut.libelle_fr}) attend un nombre, reçu un booléen"
            )
        try:
            return Decimal(str(valeur))
        except InvalidOperation as erreur:
            raise CritereInvalide(
                f"{attribut.champ} ({attribut.libelle_fr}) attend un nombre, reçu {valeur!r}"
            ) from erreur

    if not isinstance(valeur, str) or not valeur:
        raise CritereInvalide(
            f"{attribut.champ} ({attribut.libelle_fr}) attend une chaîne, reçu {valeur!r}"
        )
    return valeur


def resoudre_critere(categorie: Categorie, critere: Critere) -> CritereResolu:
    """Confronte un critère au registre et rend son rôle **effectivement** appliqué.

    C'est le seul endroit où un rôle se décide. Le moteur, le dépôt et la trace lisent
    `role_applique` ; aucun d'eux ne relit `Importance` pour en refaire le calcul.
    """
    attribut = ATTRIBUTS[categorie].get(critere.champ)
    if attribut is None:
        connus = ", ".join(sorted(ATTRIBUTS[categorie]))
        raise CritereInvalide(
            f"champ inconnu pour la catégorie {categorie!r} : {critere.champ!r} — "
            f"champs connus : {connus}"
        )

    if attribut.role is Role.AFFICHAGE:
        raise CritereInvalide(
            f"{critere.champ!r} ({attribut.libelle_fr}) est un champ d'affichage : il est "
            "montré au client, il n'entre jamais dans un filtre ni dans un score"
        )

    if attribut.impose:
        raise CritereInvalide(
            f"{critere.champ!r} est imposé par le moteur à chaque requête, il ne se pose "
            "pas en critère"
        )

    if critere.operateur not in OPERATEURS_ADMIS[attribut.genre]:
        admis = ", ".join(sorted(operateur.value for operateur in OPERATEURS_ADMIS[attribut.genre]))
        raise CritereInvalide(
            f"opérateur {critere.operateur.value!r} incompatible avec le genre "
            f"{attribut.genre.value!r} de {critere.champ!r} — admis : {admis}"
        )

    if critere.importance is Importance.BLOQUANT and attribut.role is Role.SCORE:
        raise CritereInvalide(
            f"{critere.champ!r} ({attribut.libelle_fr}) porte le rôle 'score' : le poser en "
            f"bloquant exclurait les {1 - attribut.taux_remplissage:.1%} de produits qui ne "
            "déclarent pas cette valeur, c'est-à-dire combler une absence par la porte de "
            "derrière (§3.4quater). Repasser en 'important'."
        )

    retrograde = (
        critere.importance is Importance.SOUHAIT
        and attribut.role is Role.FILTRE_DUR
        and attribut.retrogradable
    )
    role_applique = Role.SCORE if retrograde else attribut.role

    return CritereResolu(
        critere=critere,
        attribut=attribut,
        role_applique=role_applique,
        valeur=_convertir(attribut, critere.valeur),
        retrograde=retrograde,
        poids=POIDS_PAR_IMPORTANCE.get(critere.importance) if role_applique is Role.SCORE else None,
    )


class RequeteMatching(BaseModel):
    """Une demande complète adressée au moteur. **Une seule catégorie** (arbitrage K).

    Tous les produits rendus par un appel appartiennent à cette catégorie, et elle est
    obligatoire. Il n'y a ni panier, ni budget alloué, ni somme suivie d'un tour à
    l'autre : l'invariant se vérifie en une ligne, et une « config gaming » est
    structurellement impossible à servir en un seul appel. Ce n'est pas au moteur de
    refuser une telle demande — l'étape 8 la séquencera composant par composant.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    categorie: Categorie
    budget_usd: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    criteres: tuple[Critere, ...] = ()
    optimisation: Optimisation = Optimisation.AUCUNE

    @model_validator(mode="after")
    def _valider_les_criteres(self) -> Self:
        """Refuse les doublons et les champs à champ dédié, puis résout tout le reste.

        La résolution est faite ici, à la construction, et jetée : le but est que la
        requête ne puisse pas exister si l'un de ses critères est invalide. Le moteur
        rappelle `resolus()` sans avoir à se demander si quelqu'un a validé avant lui.
        """
        vus: set[tuple[str, Operateur]] = set()
        for critere in self.criteres:
            if critere.champ in CHAMPS_A_CHAMP_DEDIE:
                raise CritereInvalide(
                    f"{critere.champ!r} ne se pose pas en critère : la catégorie et le budget "
                    "sont des champs propres de la requête, et la disponibilité est imposée"
                )
            cle = (critere.champ, critere.operateur)
            if cle in vus:
                raise CritereInvalide(
                    f"deux critères {critere.operateur.value!r} sur {critere.champ!r} : "
                    "le second annulerait le premier, ou le compterait deux fois au score"
                )
            vus.add(cle)
            resoudre_critere(self.categorie, critere)
        return self

    def resolus(self) -> tuple[CritereResolu, ...]:
        """Les critères confrontés au registre, dans l'ordre où ils ont été donnés."""
        return tuple(resoudre_critere(self.categorie, critere) for critere in self.criteres)
