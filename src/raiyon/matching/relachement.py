"""Zéro résultat : diagnostic et propositions. **Aucune requête, aucune application.**

Ce module reçoit des **comptages déjà faits** par le dépôt et n'interroge rien. C'est
ce qui rend la partie la plus subtile du moteur testable hors base, en injectant des
nombres à la main — et c'est là que se joue le critère d'acceptation nº6 : *dire
pourquoi il n'y a rien, et proposer l'assouplissement du critère le plus coûteux.*

Trois règles, et elles disent toutes la même chose sous trois angles : **le moteur
propose, il n'applique jamais.**

1. La valeur proposée est **prise dans le catalogue** — la plus proche effectivement
   présente parmi les produits qui satisfont tous les autres critères. Un seuil rond
   calculé (« descendez à 1 To ») rendrait encore zéro si le premier disque
   disponible est à 960 Go, et affirmerait sur le stock un fait qui n'en est pas un.
2. Un critère de compatibilité ne se relâche pas par degré : il ne peut qu'être
   abandonné. Il se propose donc **en dernier**, et porte un drapeau que l'étape 8
   lira pour ne s'en servir qu'à défaut d'autre chose.
3. Si le budget est le critère bloquant, la réponse n'est pas « relâchez votre
   budget » : c'est l'ensemble `au_dessus_du_budget` de §3.10, déjà calculé et rendu
   avec l'écart exact. `prix_usd` est **exclu** des candidats au retrait, ici comme
   dans la requête — deux endroits qui décideraient du budget finiraient par le dire
   différemment.

**Les combinaisons de degré 2 sont hors périmètre**, et leur absence est une réponse :
quand aucun retrait unique n'ouvre le catalogue, le moteur le dit (`aucun_retrait_
simple`) au lieu de se taire.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from raiyon.matching.attributs import Attribut
from raiyon.matching.criteres import CritereResolu, Importance, Operateur, RequeteMatching
from raiyon.matching.depot import RelevesDeRelachement
from raiyon.matching.trace import ValeurTracee

CHAMPS_JAMAIS_PROPOSES: frozenset[str] = frozenset({"prix_usd", "categorie"})
"""Le budget a sa propre réponse (§3.10) et la catégorie n'est pas négociable : on ne
propose pas un clavier à qui demande un écran (arbitrage K)."""

RANG_IMPORTANCE: dict[Importance, int] = {
    Importance.SOUHAIT: 0,
    Importance.IMPORTANT: 1,
    Importance.BLOQUANT: 2,
}
"""On propose d'abord d'abandonner ce à quoi le client tenait le moins. L'ordre vient
de ce qu'il a **déclaré**, pas de ce qui arrangerait le moteur."""


class Motif(StrEnum):
    """Pourquoi il n'y a rien. Quatre cas, et ils n'appellent pas la même réponse."""

    BUDGET_TROP_BAS = "budget_trop_bas"
    """Tout le reste est satisfait, mais au-dessus du budget. La réponse est
    l'ensemble `au_dessus_du_budget`, avec son écart exact — pas une invitation à
    relever le budget."""

    DONNEE_ABSENTE = "donnee_absente"
    """Les produits écartés l'ont été faute de valeur déclarée, pas parce qu'ils
    échouaient au critère. « Aucun produit ne déclare sa fréquence de rafraîchissement »
    n'est pas « aucun produit ne fait 144 Hz », et la proposition change de nature."""

    ABSENCE_STRUCTURELLE = "absence_structurelle"
    """Le critère porte un attribut qu'une autre colonne rend inapplicable à une partie
    du catalogue. Ni un critère trop strict, ni une donnée manquante : un troisième cas.

    « 7 200 tr/min en M.2 PCIe » ne rend rien parce que les disques M.2 PCIe sont des
    SSD, et qu'un SSD **n'a pas** de vitesse de rotation. Dire « ces disques ne
    déclarent pas leur vitesse » serait une affirmation fausse sur le catalogue ; dire
    « aucun disque ne tourne à 7 200 tr/min » aussi. La bonne phrase est « vous avez
    demandé un disque mécanique », et l'étape 8 a besoin de ce motif pour l'écrire sans
    que le moteur rédige quoi que ce soit.

    Ce motif ne se déclenche pas sur le seul drapeau du registre : il faut **aussi**
    qu'aucune valeur ne soit atteignable parmi les produits rouverts. Un attribut peut
    être structurellement inapplicable à une partie du catalogue **et** demandé trop
    strictement sur le reste — ce sont deux phrases différentes à dire au client, et
    c'est la valeur atteignable qui les sépare.
    """

    CRITERE_TROP_STRICT = "critere_trop_strict"
    AUCUN_RETRAIT_SIMPLE = "aucun_retrait_simple"
    """Aucun retrait d'un seul critère ne rouvre le catalogue. Le moteur le dit ;
    explorer les combinaisons de degré 2 est hors périmètre."""


LIBELLES_MOTIF: dict[Motif, str] = {
    Motif.BUDGET_TROP_BAS: "tout le reste convient, mais au-dessus du budget",
    Motif.DONNEE_ABSENTE: "les produits écartés ne déclarent pas cette valeur",
    Motif.ABSENCE_STRUCTURELLE: "cet attribut ne s'applique pas à ce type de produit",
    Motif.CRITERE_TROP_STRICT: "un critère est trop strict pour le catalogue",
    Motif.AUCUN_RETRAIT_SIMPLE: "aucun assouplissement d'un seul critère ne rouvre le catalogue",
}
"""Le français d'un motif de zéro résultat, **du même côté que le motif**.

Même geste que `LIBELLES_CATEGORIE` et `LIBELLES_OPTIMISATION`. Il compte plus que les
deux autres : le zéro résultat est le **critère d'acceptation nº6**, et c'est à l'étape 11
qu'il devient visible. `critere_trop_strict` affiché tel quel à un client ne serait pas
« le cas zéro résultat rendu lisible » — ce serait un identifiant montré faute de mieux.

⚠️ **Ces phrases ne remplacent pas celles de l'agent.** Le moteur ne rédige pas (§3.7) :
le modèle écrit la vraie réponse, en tenant compte du reste de la conversation. Ce libellé
est ce que le **panneau** affiche à côté des propositions, c'est-à-dire ce que le code a
constaté — au même titre que les critères et les comptes.
"""


@dataclass(frozen=True, slots=True)
class Proposition:
    """Un assouplissement possible. Formulé, jamais appliqué."""

    champ: str
    libelle_fr: str
    unite: str | None
    importance: Importance
    operateur: Operateur
    valeur_demandee: ValeurTracee
    valeur_atteignable: Decimal | None
    """La valeur la plus proche présente au catalogue, dans le sens qui relâche.
    `None` sur un critère non numérique : une interface ne s'assouplit pas, elle
    s'abandonne."""

    produits_rouverts: int
    motif: Motif
    dernier_recours: bool
    """Critère de compatibilité : à ne proposer que s'il ne reste rien d'autre."""


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Ce que le moteur rend quand `produits` est vide."""

    motif: Motif
    propositions: tuple[Proposition, ...]


def _motif_du_retrait(
    attribut: Attribut,
    rouverts: int,
    ecartes_faute_de_donnee: int,
    valeur_atteignable: Decimal | None,
) -> Motif:
    """Une seule règle, appliquée trois fois : **ce que le retrait rouvrirait**.

    Chaque branche répond à la même question — les produits que le retrait de ce critère
    ferait remonter, qu'ont-ils à voir avec ce critère ? — et les trois réponses
    n'appellent pas la même phrase :

    1. **aucun d'eux ne déclare l'attribut, et une autre colonne explique pourquoi.** Un
       disque M.2 PCIe est un SSD, et un SSD n'a pas de vitesse de rotation. La demande
       ne s'applique pas à ce qui reste → `absence_structurelle` ;
    2. **aucun d'eux ne déclare l'attribut, et rien ne l'explique** — les comptages
       coïncident. Ce n'est pas le critère qui est trop strict, c'est la donnée qui
       manque. Sans cette comparaison, le moteur dirait « aucun produit ne fait 144 Hz »
       en pensant « sept écrans ne déclarent pas leur fréquence » → `donnee_absente` ;
    3. **certains le déclarent, aucun n'atteint le seuil** → `critere_trop_strict`.

    ⚠️ Le drapeau du registre **ne suffit pas** à conclure au premier cas, et c'est le
    correctif que la première version appelait à tort une limite assumée. `rpm >= 7200`
    dans un budget de 25 USD ne rend rien, mais deux disques mécaniques y tournent à
    5 400 : dire « vous avez demandé un disque mécanique » serait faux, il y en a. La
    phrase juste est « il y en a, mais aucun à 7 200 tr/min ». C'est `valeur_atteignable`
    — la plus proche **réellement présente** parmi les produits qui satisfont tout le
    reste — qui tranche, et elle est déjà calculée par le dépôt.
    """
    if attribut.absence_structurelle and valeur_atteignable is None:
        return Motif.ABSENCE_STRUCTURELLE
    if ecartes_faute_de_donnee > 0 and rouverts == ecartes_faute_de_donnee:
        return Motif.DONNEE_ABSENTE
    return Motif.CRITERE_TROP_STRICT


def _proposition(
    resolu: CritereResolu, releves: RelevesDeRelachement, ecartes_faute_de_donnee: int
) -> Proposition:
    """Assemble une proposition à partir des comptages du dépôt."""
    rouverts = releves.rouvre_si_retire.get(resolu.champ, 0)
    atteignable = releves.valeurs_atteignables.get(resolu.champ)
    return Proposition(
        champ=resolu.champ,
        libelle_fr=resolu.attribut.libelle_fr,
        unite=resolu.attribut.unite,
        importance=resolu.importance,
        operateur=resolu.operateur,
        valeur_demandee=resolu.valeur,
        valeur_atteignable=atteignable,
        produits_rouverts=rouverts,
        motif=_motif_du_retrait(resolu.attribut, rouverts, ecartes_faute_de_donnee, atteignable),
        dernier_recours=resolu.attribut.est_de_compatibilite,
    )


def _cle_de_tri(proposition: Proposition) -> tuple[bool, int, int, str]:
    """Compatibilité en dernier, puis importance déclarée, puis produits rouverts.

    Le champ ferme l'ordre : deux propositions identiques sur les trois premiers
    termes se classeraient sinon selon l'ordre de déclaration des critères, ce qui
    ferait dépendre une réponse client de la façon dont l'agent a rempli sa liste.
    """
    return (
        proposition.dernier_recours,
        RANG_IMPORTANCE[proposition.importance],
        -proposition.produits_rouverts,
        proposition.champ,
    )


def diagnostiquer(
    requete: RequeteMatching,
    releves: RelevesDeRelachement,
    ecartes_faute_de_donnee: Mapping[str, int],
    produits_au_dessus_du_budget: int = 0,
) -> Diagnostic:
    """Dit pourquoi il n'y a rien, et ce qu'on pourrait relâcher. Dans cet ordre.

    Le motif d'ensemble est celui de la **meilleure** proposition — celle que l'agent
    formulera —, sauf si le budget explique déjà tout : dans ce cas, tous les autres
    critères sont satisfaits quelque part, et c'est la zone de tolérance qui répond.
    Les propositions sont rendues quand même, car relâcher un critère technique peut
    ouvrir des produits **moins chers**, ce que la zone de tolérance ne montre pas.
    """
    propositions = tuple(
        sorted(
            (
                _proposition(resolu, releves, ecartes_faute_de_donnee.get(resolu.champ, 0))
                for resolu in requete.resolus()
                if resolu.filtre
                and resolu.champ not in CHAMPS_JAMAIS_PROPOSES
                and releves.rouvre_si_retire.get(resolu.champ, 0) > 0
            ),
            key=_cle_de_tri,
        )
    )

    if produits_au_dessus_du_budget > 0:
        return Diagnostic(Motif.BUDGET_TROP_BAS, propositions)
    if not propositions:
        return Diagnostic(Motif.AUCUN_RETRAIT_SIMPLE, ())
    return Diagnostic(propositions[0].motif, propositions)
