"""Le dépôt : la moitié SQL du moteur. **SQL décide qui est candidat** (§3.16).

Ce module traduit les critères durs en `WHERE`, et rien d'autre : ni score, ni
classement, ni diagnostic. La règle de partage tient en une phrase — *SQL décide qui
est candidat, Python décide comment on le présente* — et sa conséquence est le critère
d'acceptation nº5 : tout le reste du moteur est pur, donc testable sans base ni clé.

**Un seul constructeur de prédicat, plusieurs projections.** Les candidats, le
comptage des produits écartés faute de donnée, le comptage de relâchement et les
valeurs atteignables sortent tous de `_predicat()`. Deux requêtes écrites séparément
finiraient par dire des choses différentes du même critère ; c'est le mode d'échec de
la double implémentation, en plus petit et en plus discret.

**Ce que l'index sert et ce qu'il ne sert pas** (§3.3bis, inchangé) : les égalités sur
énumérations et booléens passent par une containment `@>`, servie par le GIN
`jsonb_path_ops`. Les comparaisons de plage — la forme la plus fréquente des filtres
durs du domaine — provoquent un balayage séquentiel. À 1 026 lignes, quelques
millisecondes ; c'est le compromis assumé de l'étape 4, pas un oubli.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from sqlalchemy import Numeric, Select, SQLColumnExpression, cast, func, literal, select
from sqlalchemy.orm import Session

from raiyon.catalogue.schemas import Categorie, ProduitEnBase
from raiyon.db.models import Produit
from raiyon.matching.attributs import ATTRIBUTS, Genre, champs_a_compter
from raiyon.matching.criteres import CritereResolu, Operateur, RequeteMatching

CENTIMES = Decimal("0.01")
"""L'échelle de `produits.prix_usd` et de `sessions.budget_usd`, tous deux
`numeric(10, 2)`."""


@dataclass(frozen=True, slots=True)
class Fourchette:
    """Bande de prix d'une requête. Bornes optionnelles, la basse **exclue**.

    La zone de tolérance de §3.10 est `]budget, budget x (1 + tolérance)]` : son
    ouverture à gauche est ce qui garantit qu'un produit ne peut pas se retrouver à la
    fois dans `produits` et dans `au_dessus_du_budget`.
    """

    min_exclu: Decimal | None = None
    max_inclus: Decimal | None = None


@dataclass(frozen=True, slots=True)
class RelevesDeRelachement:
    """Ce que le dépôt sait dire d'un zéro résultat. Des comptages, aucun conseil.

    `relachement.py` travaille sur cet objet **sans jamais interroger la base**, ce qui
    rend la partie la plus subtile du moteur testable en injectant des nombres à la
    main.
    """

    rouvre_si_retire: dict[str, int] = field(default_factory=dict)
    """Par champ : nombre de produits que le retrait de ce seul critère ferait
    remonter, tous les autres restant en place."""

    valeurs_atteignables: dict[str, Decimal] = field(default_factory=dict)
    """Par champ numérique : la valeur la plus proche **effectivement présente au
    catalogue** parmi les produits qui satisfont tous les autres critères. Jamais un
    seuil rond calculé : proposer « descendez à 1 To » quand le premier disque
    disponible est à 960 Go rendrait encore zéro, et affirmerait sur le stock un fait
    qui n'en est pas un."""


@dataclass(frozen=True, slots=True)
class BornesPrix:
    """Le prix du moins cher et du plus cher d'un sous-catalogue. Jamais une moyenne.

    Une moyenne serait une affirmation calculée sur le catalogue ; deux extrêmes sont
    deux produits qui existent. `None` quand le sous-catalogue est vide — l'absence de
    fourchette est une information, pas un zéro.
    """

    plus_bas: Decimal
    plus_haut: Decimal


@dataclass(frozen=True, slots=True)
class Comptages:
    """La distribution d'un champ sur le sous-catalogue courant. **Des comptages bruts.**

    Ni tri, ni troncature, ni pourcentage : `sondage.py` s'en charge, en Python pur, sur
    cet objet. C'est la même frontière que `RelevesDeRelachement` — SQL compte, Python
    décide de ce qu'on en dit — et elle achète la même chose : l'entropie et le
    classement se testent en injectant des nombres à la main (§3.16).
    """

    champ: str
    effectifs: tuple[tuple[str, int], ...]
    """`(valeur, nombre de produits)`, **valeurs absentes exclues**, dans l'ordre où
    Postgres les a rendues — c'est-à-dire dans aucun ordre garanti. Le tri est un choix
    de présentation, il se fait en Python et une seule fois."""

    renseignes: int
    """Produits qui déclarent une valeur. `total - renseignes` est le nombre de produits
    muets sur ce champ : c'est ce qui pondère l'entropie de l'arbitrage H, faute de quoi
    l'outil proposerait de demander une vitesse de rotation à un client dont les deux
    tiers des candidats sont des SSD."""

    total: int
    """Produits du sous-catalogue, muets compris."""

    @property
    def total_distinct(self) -> int:
        return len(self.effectifs)


def plafond_de_tolerance(budget: Decimal, tolerance: Decimal) -> Decimal:
    """Le haut de la zone de §3.10 : `budget x (1 + tolérance)`, arrondi au centime.

    **Une seule écriture de cette formule dans le projet.** Le moteur en a besoin pour
    récupérer les produits juste au-dessus du budget, la couche outils pour les compter :
    deux versions donneraient un jour deux bandes différentes, et le client verrait un
    produit compté dans le sondage puis absent de la recherche. C'est le raisonnement de
    §3.10 sur la colonne `budget_usd`, appliqué à la formule plutôt qu'à la valeur.

    L'arrondi au centime est celui de `numeric(10, 2)` : un plafond à trois décimales
    comparé à un prix qui n'en a que deux ferait dépendre l'appartenance à la zone d'une
    décimale que la base ne stocke pas.
    """
    return (budget * (Decimal(1) + tolerance)).quantize(CENTIMES)


def fourchette_de_tolerance(budget: Decimal, tolerance: Decimal) -> Fourchette:
    """La zone `]budget, budget x (1 + tolérance)]`, sous la forme qu'attend le dépôt."""
    return Fourchette(min_exclu=budget, max_inclus=plafond_de_tolerance(budget, tolerance))


class DepotProduits(Protocol):
    """Ce que le moteur attend d'une source de produits.

    Écrit en `Protocol` pour que la dépendance aille dans le bon sens : le moteur ne
    connaît pas SQLAlchemy, et un dépôt en mémoire reste possible sans que rien du
    moteur ne bouge.
    """

    def candidats(
        self, requete: RequeteMatching, fourchette: Fourchette
    ) -> list[ProduitEnBase]: ...

    def ecartes_faute_de_donnee(
        self, requete: RequeteMatching, fourchette: Fourchette
    ) -> dict[str, int]: ...

    def releves_de_relachement(
        self, requete: RequeteMatching, fourchette: Fourchette
    ) -> RelevesDeRelachement: ...

    def compter(self, requete: RequeteMatching, fourchette: Fourchette) -> int: ...

    def bornes_de_prix(
        self, requete: RequeteMatching, fourchette: Fourchette
    ) -> BornesPrix | None: ...

    def distributions(
        self, requete: RequeteMatching, fourchette: Fourchette, champs: Sequence[str]
    ) -> dict[str, Comptages]: ...


def cle_marque(expression: SQLColumnExpression[str]) -> SQLColumnExpression[str]:
    """Clé de comparaison des marques : minuscules, ponctuation retirée.

    « G.Skill », « g.skill » et « gskill » sont la même marque, et le client la tape à
    la main — c'est le seul champ textuel dans ce cas, les énumérations venant du
    catalogue (§3.7).

    ⚠️ **Cette normalisation n'existe qu'ici, et en SQL.** Elle est appliquée aux deux
    côtés de l'égalité, colonne et valeur demandée, plutôt que dupliquée en Python
    (arbitrage L) : deux implémentations d'une même normalisation dérivent, et la
    divergence se voit sur un cas rare, tard.
    """
    normalisee: SQLColumnExpression[str] = func.lower(
        func.regexp_replace(expression, "[^[:alnum:]]", "", "g")
    )
    return normalisee


def _valeur_specs(champ: str) -> SQLColumnExpression[str]:
    """`specs->>'champ'`, c'est-à-dire du **texte**, toujours.

    `specs_pour_base()` sérialise les `Decimal` en chaînes (`"0.208"`) pour qu'un
    aller-retour JSON les rende au caractère près. Un cast explicite est donc
    obligatoire avant toute comparaison numérique — et une containment `@>` sur un
    nombre devrait comparer une chaîne, raison pour laquelle elle est réservée ici aux
    énumérations et aux booléens.
    """
    texte: SQLColumnExpression[str] = Produit.specs[champ].astext
    return texte


def _predicat(resolu: CritereResolu) -> SQLColumnExpression[bool]:
    """Traduit un critère dur en condition SQL. Un seul endroit, plusieurs usages."""
    attribut = resolu.attribut
    valeur = resolu.valeur

    if not attribut.dans_les_specs:
        if attribut.champ == "marque" and isinstance(valeur, str):
            return cle_marque(Produit.marque) == cle_marque(literal(valeur))
        if attribut.champ == "prix_usd" and isinstance(valeur, Decimal):
            return _comparer(Produit.prix_usd, resolu.operateur, valeur)
        return Produit.categorie == valeur

    if attribut.genre is Genre.NUMERIQUE and isinstance(valeur, Decimal):
        return _comparer(cast(_valeur_specs(attribut.champ), Numeric), resolu.operateur, valeur)

    # Égalité stricte, servie par le GIN. Jamais un `contains` de sous-chaîne :
    # « RTX 4070 » attraperait « RTX 4070 Ti » et le critère nº4 se dégraderait sans
    # qu'on le voie (arbitrage L).
    return Produit.specs.contains({attribut.champ: valeur})


def _comparer(
    colonne: SQLColumnExpression[Decimal], operateur: Operateur, valeur: Decimal
) -> SQLColumnExpression[bool]:
    """Applique l'opérateur à une colonne numérique."""
    if operateur is Operateur.AU_MOINS:
        return colonne >= valeur
    if operateur is Operateur.AU_PLUS:
        return colonne <= valeur
    return colonne == valeur


def _est_absent(resolu: CritereResolu) -> SQLColumnExpression[bool]:
    """Le produit ne déclare pas cette valeur.

    `specs->>'champ'` rend NULL aussi bien pour une clé absente que pour un `null`
    JSON ; `specs_pour_base()` conservant les clés à `null`, les deux cas se
    confondent — et c'est ce qu'on veut, l'absence est l'absence.
    """
    if resolu.attribut.dans_les_specs:
        return _valeur_specs(resolu.champ).is_(None)
    colonne: SQLColumnExpression[object] = getattr(Produit, resolu.champ)
    return colonne.is_(None)


def _filtres_durs(requete: RequeteMatching) -> list[CritereResolu]:
    """Les critères que SQL applique. Les scores n'excluent rien, par définition."""
    return [resolu for resolu in requete.resolus() if resolu.filtre]


def _base(requete: RequeteMatching, fourchette: Fourchette) -> list[SQLColumnExpression[bool]]:
    """Conditions presentes dans **toutes** les requêtes du moteur.

    `disponible` est imposé : il n'est pas un critère du client, il est une propriété
    du catalogue que rien ne doit pouvoir contourner. La catégorie l'est aussi — un
    tour, une catégorie (arbitrage K).
    """
    conditions: list[SQLColumnExpression[bool]] = [
        Produit.categorie == requete.categorie,
        Produit.disponible.is_(True),
    ]
    if fourchette.min_exclu is not None:
        conditions.append(Produit.prix_usd > fourchette.min_exclu)
    if fourchette.max_inclus is not None:
        conditions.append(Produit.prix_usd <= fourchette.max_inclus)
    return conditions


def _requete(
    requete: RequeteMatching, fourchette: Fourchette, sauf: str | None = None
) -> list[SQLColumnExpression[bool]]:
    """Conditions de base plus les filtres durs, à l'exception d'un champ."""
    return [
        *_base(requete, fourchette),
        *(_predicat(resolu) for resolu in _filtres_durs(requete) if resolu.champ != sauf),
    ]


class DepotSql:
    """Implémentation Postgres de `DepotProduits`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def candidats(self, requete: RequeteMatching, fourchette: Fourchette) -> list[ProduitEnBase]:
        """Les produits qui satisfont tous les filtres durs, revalidés au passage.

        `ORDER BY id` ne sert pas au classement — celui-ci est un ordre total calculé
        en Python (arbitrage M) — mais rend la requête reproductible quand on la lit
        dans un log.
        """
        lignes = self._session.scalars(
            select(Produit).where(*_requete(requete, fourchette)).order_by(Produit.id)
        )
        return [produit_en_schema(ligne) for ligne in lignes]

    def ecartes_faute_de_donnee(
        self, requete: RequeteMatching, fourchette: Fourchette
    ) -> dict[str, int]:
        """Par champ : combien de produits le filtre a écartés faute de donnée.

        La sémantique SQL est conservée — l'absence ne satisfait pas le critère — mais
        elle cesse d'être silencieuse. « Aucun produit ne déclare sa fréquence de
        rafraîchissement » n'est pas « aucun produit ne fait 144 Hz », et sans ce
        compteur le moteur dirait la seconde phrase en pensant la première.

        La liste des champs interrogés est celle de `champs_a_compter()` : les taux de
        remplissage **mesurés sur le seed**, moins les absences structurelles. Sur un
        attribut à 100 %, aucune requête n'est émise ; sur `rpm`, aucune non plus, parce
        qu'un SSD n'est pas un disque dont on ignore la vitesse de rotation. Sur le
        seed, deux filtres durs seulement sont concernés.
        """
        a_compter = champs_a_compter(requete.categorie)
        comptes: dict[str, int] = {}
        for resolu in _filtres_durs(requete):
            if resolu.champ not in a_compter:
                continue
            comptes[resolu.champ] = self._compter(
                [*_requete(requete, fourchette, sauf=resolu.champ), _est_absent(resolu)]
            )
        return comptes

    def releves_de_relachement(
        self, requete: RequeteMatching, fourchette: Fourchette
    ) -> RelevesDeRelachement:
        """Comptages du leave-one-out, et valeur atteignable la plus proche.

        ⚠️ **Note de performance, et son seuil de bascule.** Ces n+1 requêtes se
        ramènent à une seule avec `count(*) FILTER (WHERE …)`, un agrégat par critère.
        À 1 026 lignes et au plus une poignée de critères, le gain est nul et la
        version lisible gagne. La bascule se justifiera si le catalogue change d'ordre
        de grandeur, ou si le moteur est appelé dans une boucle — c'est le même
        compromis explicite que §3.3bis, écrit pour ne pas être redécouvert.
        """
        releves = RelevesDeRelachement()
        for resolu in _filtres_durs(requete):
            conditions = _requete(requete, fourchette, sauf=resolu.champ)
            releves.rouvre_si_retire[resolu.champ] = self._compter(conditions)
            atteignable = self._valeur_atteignable(resolu, conditions)
            if atteignable is not None:
                releves.valeurs_atteignables[resolu.champ] = atteignable
        return releves

    # ----------------------------------------------------------------- #
    # Agrégats — l'extension de l'étape 7 (arbitrage G)
    # ----------------------------------------------------------------- #

    def compter(self, requete: RequeteMatching, fourchette: Fourchette) -> int:
        """Combien de produits satisfont les filtres durs, dans cette bande de prix.

        C'est le même prédicat que `candidats()`, sans la projection : « il te reste 12
        modèles » et « voici les trois meilleurs » ne peuvent donc pas parler de deux
        ensembles différents.
        """
        return self._compter(_requete(requete, fourchette))

    def bornes_de_prix(self, requete: RequeteMatching, fourchette: Fourchette) -> BornesPrix | None:
        """Le prix du moins cher et du plus cher du sous-catalogue, ou `None` s'il est vide."""
        requete_sql: Select[tuple[Decimal, Decimal]] = select(
            func.min(Produit.prix_usd), func.max(Produit.prix_usd)
        ).where(*_requete(requete, fourchette))
        plus_bas, plus_haut = self._session.execute(requete_sql).one()
        if plus_bas is None or plus_haut is None:
            return None
        return BornesPrix(plus_bas=Decimal(str(plus_bas)), plus_haut=Decimal(str(plus_haut)))

    def distributions(
        self, requete: RequeteMatching, fourchette: Fourchette, champs: Sequence[str]
    ) -> dict[str, Comptages]:
        """Un `GROUP BY` par champ demandé, plus le total du sous-catalogue.

        **Aucun `ORDER BY`.** Il en faudrait un pour que la sortie soit reproductible, et
        c'est précisément pourquoi il n'y en a pas : l'ordre des valeurs rendues au
        client est un choix de présentation (fréquence décroissante, puis valeur
        croissante), il se fait en Python, une seule fois, et il ne dépend donc ni de la
        collation de la base ni du plan d'exécution. Un tri écrit ici serait un second
        ordre, et deux ordres divergent.

        ⚠️ **Note de performance, même seuil de bascule que le relâchement** : une requête
        par champ. Sept champs sur 1 026 lignes coûtent quelques millisecondes ; les
        réunir en une seule passe `jsonb_each` deviendrait justifié si le catalogue
        changeait d'ordre de grandeur, ou si le sondage était appelé en boucle.
        """
        conditions = _requete(requete, fourchette)
        total = self._compter(conditions)
        return {
            champ: self._comptages(requete.categorie, champ, conditions, total) for champ in champs
        }

    def _comptages(
        self,
        categorie: Categorie,
        champ: str,
        conditions: Sequence[SQLColumnExpression[bool]],
        total: int,
    ) -> Comptages:
        """Le `GROUP BY` d'un champ, absences comprises puis séparées.

        Les lignes à `NULL` remontent avec les autres, et c'est ce qui donne la
        couverture sans seconde requête : ce que le champ ne dit pas est compté en même
        temps que ce qu'il dit.
        """
        attribut = ATTRIBUTS[categorie][champ]
        colonne: SQLColumnExpression[str] = (
            _valeur_specs(champ) if attribut.dans_les_specs else getattr(Produit, champ)
        )
        requete_sql: Select[tuple[str, int]] = (
            select(colonne, func.count()).where(*conditions).group_by(colonne)
        )
        lignes = self._session.execute(requete_sql).all()
        effectifs = tuple((str(valeur), nombre) for valeur, nombre in lignes if valeur is not None)
        return Comptages(
            champ=champ,
            effectifs=effectifs,
            renseignes=sum(nombre for _, nombre in effectifs),
            total=total,
        )

    def _compter(self, conditions: Sequence[SQLColumnExpression[bool]]) -> int:
        requete: Select[tuple[int]] = select(func.count()).select_from(Produit).where(*conditions)
        return self._session.scalar(requete) or 0

    def _valeur_atteignable(
        self, resolu: CritereResolu, conditions: Sequence[SQLColumnExpression[bool]]
    ) -> Decimal | None:
        """La valeur la plus proche dans le **sens qui relâche** le critère.

        Pour « au moins 2 To », c'est la plus grande capacité **inférieure** à 2 To
        parmi les produits qui satisfont tout le reste : c'est elle qui rouvrirait le
        catalogue, et elle existe au stock. Une valeur supérieure n'apprendrait rien —
        le critère la satisfait déjà.
        """
        attribut = resolu.attribut
        if attribut.genre is not Genre.NUMERIQUE or not isinstance(resolu.valeur, Decimal):
            return None
        valeur: SQLColumnExpression[Decimal] = (
            cast(_valeur_specs(attribut.champ), Numeric)
            if attribut.dans_les_specs
            else getattr(Produit, attribut.champ)
        )

        presentes = [*conditions, valeur.is_not(None)]
        if resolu.operateur is Operateur.AU_MOINS:
            requete = select(func.max(valeur)).where(*presentes, valeur < resolu.valeur)
        elif resolu.operateur is Operateur.AU_PLUS:
            requete = select(func.min(valeur)).where(*presentes, valeur > resolu.valeur)
        else:
            requete = (
                select(valeur)
                .where(*presentes)
                .order_by(func.abs(valeur - resolu.valeur), valeur)
                .limit(1)
            )
        resultat = self._session.scalar(requete)
        return Decimal(str(resultat)) if resultat is not None else None


def produit_en_schema(ligne: Produit) -> ProduitEnBase:
    """Convertit une ligne SQL en modèle validé, seule forme que le moteur manipule.

    La revalidation coûte quelques microsecondes par produit et achète deux choses :
    les `Decimal` reviennent typés depuis le JSONB où ils dorment en chaînes, et une
    ligne corrompue est arrêtée ici plutôt que trois couches plus loin, dans un score.
    C'est la même raison qui fait revalider le seed committé au chargement.
    """
    return ProduitEnBase.model_validate(
        {
            "id": ligne.id,
            "nom": ligne.nom,
            "marque": ligne.marque,
            "categorie": ligne.categorie,
            "prix_usd": ligne.prix_usd,
            "disponible": ligne.disponible,
            "specs": ligne.specs,
        }
    )
