"""Deux campagnes côte à côte, et **la seule question qui compte : est-ce un signal ?**

**Pur.** Deux `Mesures` entrent, du markdown sort. Aucun rejeu, aucune base — le rejeu est
l'affaire de `scripts/eval.py`, qui appelle ce module avec les deux agrégats.

---

### Un écart inférieur à la dispersion n'est pas un signal, et le tableau le dit

C'est toute la raison d'être de ce module. Le rapport de l'étape 12 publiait déjà une
section « dispersion, et ce qu'elle ne prouve pas », et elle finit par cette phrase :

> *Un écart de deux prompts inférieur à cet ordre de grandeur n'est pas un signal.*

Écrite dans un fichier, cette phrase se lit une fois puis s'oublie ; la comparaison de deux
campagnes se fait ensuite à l'œil, sur deux tableaux de trente-six lignes, et l'œil trouve
toujours ce qu'il cherche. **La comparaison applique donc la règle au lieu de la rappeler**
— chaque écart porte son verdict, calculé.

### Comment la dispersion est estimée, et ce qu'elle vaut vraiment

Pour une mesure comptée par prise — rejets, replis, chiffres de domaine —, la **campagne de
référence** donne, scénario par scénario, l'étendue de ses prises : `max - min`. Sommée sur
les scénarios, cette étendue est de **combien le total aurait pu bouger par le seul
tirage**, si chaque scénario était tombé sur son extrême dans un sens puis dans l'autre.

⚠️ **C'est une borne, pas un écart-type, et elle est estimée sur trois prises.** Elle est
délibérément **généreuse** : elle surestime le bruit, donc elle déclare « signal » moins
souvent qu'un test statistique. C'est le sens dans lequel on veut se tromper — un dépôt qui
a déjà republié deux fois des chiffres revus à la baisse ne doit pas se mettre à annoncer
des effets que le tirage explique.

⚠️ **Elle ne sait rien des scénarios calmes.** Un scénario dont les trois prises font 0
rejet contribue une étendue nulle : la dispersion ne dit pas qu'il est stable, elle dit
qu'on ne l'a pas vu bouger. Trois prises ne distinguent pas « stable par construction » de
« calme par chance », et le tableau porte cette réserve.

*Alternative écartée — un test statistique (Mann-Whitney, bootstrap).* Il rendrait une
valeur-p sur trois prises par scénario, c'est-à-dire un chiffre dont la précision apparente
dépasserait de loin ce que les données portent. Le dépôt refuse déjà d'appeler trois prises
un intervalle de confiance ; les appeler un test serait la même faute avec plus de
décimales.
"""

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from raiyon.eval.metriques import Mesures, MesuresDunePrise, agreger

SIGNAL = "au-delà"
BRUIT = "dans le bruit"
IDENTIQUE = "identique"
SANS_OBJET = "—"


@dataclass(frozen=True, slots=True)
class Couverture:
    """Sur quelles prises la comparaison porte réellement, et **ce que ça lui coûte**.

    Deux campagnes n'ont pas forcément les mêmes prises. La comparaison porte alors sur
    leur **intersection** — comparer un total de 36 prises à un total de 21 comparerait
    deux tailles d'échantillon, et l'écart mesurerait surtout la différence de taille.

    ### L'intersection porte sur les **scénarios**, jamais sur les numéros de prise

    C'est la première rédaction de ce module, et elle était fausse. Elle appariait
    `(scénario, prise)` — la prise 2 de `besoin_flou` d'un jeu avec la prise 2 de l'autre.

    ⚠️ **Un numéro de prise n'est pas une identité, c'est un index.** La température n'est
    pas fixée : la prise 2 est un tirage de plus, sans aucun lien avec la prise 2 d'une
    autre campagne. Les apparier ne rapproche rien, et cela **jette des données payées** —
    sur les jeux réels de l'étape 13, l'appariement par numéro réduisait 21 prises à 11,
    en écartant les prises 2 et 3 de cinq scénarios que l'étape 12 n'avait tirés qu'une
    fois.

    Ce qui se compare est donc le **scénario**, avec toutes ses prises de chaque côté.

    ### Et la grandeur comparée est une moyenne par prise, jamais un total

    Les deux côtés n'ont pas le même nombre de prises — 1 d'un côté, 3 de l'autre sur cinq
    scénarios. Comparer des totaux comparerait des tailles d'échantillon, et l'écart
    mesurerait surtout combien de fois on a tiré.

    La valeur publiée est donc, **par scénario, la moyenne sur ses prises**, sommée sur les
    scénarios communs : *ce qu'une passe complète des scénarios comparés produit en
    moyenne*. C'est la même unité que la dispersion, qui est l'étendue `max - min` par
    scénario sommée — l'une et l'autre valent « pour une passe », et sont donc comparables.

    ⚠️ **Une intersection n'est pas neutre, et le dire ne suffit pas : il faut le
    chiffrer.** Les scénarios exclus ne sont pas un échantillon au hasard ; ce sont ceux
    qui manquent d'un côté, et rien ne garantit qu'ils ressemblaient aux autres. S'ils
    portaient l'essentiel des griefs de la campagne de référence, la comparaison porte sur
    ses scénarios les plus **calmes** — et tout écart y est mécaniquement plus petit.
    `rejets_exclus` sur `rejets_total` le dit en chiffres, à côté du tableau, plutôt que
    dans une note qu'on lira après avoir conclu.
    """

    scenarios: tuple[str, ...]
    """Les scénarios présents des deux côtés. L'unité de la comparaison."""

    prises_avant: int
    prises_apres: int
    """Combien de prises chaque côté apporte sur ces scénarios. Ils peuvent différer :
    c'est précisément pourquoi on compare des moyennes."""

    absents_avant: tuple[str, ...]
    """Scénarios de la campagne comparée que la référence ne porte pas."""

    absents_apres: tuple[str, ...]
    """Scénarios de la référence que la campagne comparée ne porte pas."""

    rejets_exclus: int
    """Rejets portés par les prises de la **référence** sur les scénarios écartés."""

    rejets_total: int
    """Rejets de la référence **entière**. Le dénominateur de la réserve ci-dessus."""

    @property
    def complete(self) -> bool:
        return not self.absents_avant and not self.absents_apres

    @property
    def scenarios_exclus(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.absents_avant) | set(self.absents_apres)))


def couvrir(avant: Mesures, apres: Mesures) -> tuple[Couverture, Mesures, Mesures]:
    """Réduit deux campagnes à leurs **scénarios communs**, et dit ce que l'exclusion emporte.

    Rend la couverture et les deux agrégats réduits, **toutes prises conservées** de
    chaque côté. Le filtrage se fait sur les mesures déjà calculées — aucun rejeu
    supplémentaire : une `MesuresDunePrise` porte son scénario, et `agreger()` accepte
    n'importe quel sous-ensemble.
    """
    noms_avant = {prise.scenario for prise in avant.prises}
    noms_apres = {prise.scenario for prise in apres.prises}
    communs = noms_avant & noms_apres

    couverture = Couverture(
        scenarios=tuple(sorted(communs)),
        prises_avant=sum(1 for prise in avant.prises if prise.scenario in communs),
        prises_apres=sum(1 for prise in apres.prises if prise.scenario in communs),
        absents_avant=tuple(sorted(noms_apres - noms_avant)),
        absents_apres=tuple(sorted(noms_avant - noms_apres)),
        rejets_exclus=sum(
            len(prise.rejets) for prise in avant.prises if prise.scenario not in communs
        ),
        rejets_total=len(avant.rejets),
    )
    return (
        couverture,
        agreger(prise for prise in avant.prises if prise.scenario in communs),
        agreger(prise for prise in apres.prises if prise.scenario in communs),
    )


@dataclass(frozen=True, slots=True)
class Compteur:
    """Une mesure comptée **par prise**, donc une dont la dispersion s'estime.

    Le total et la dispersion sortent de la même fonction : sans cela, on comparerait un
    total à l'étendue d'autre chose, et le verdict porterait sur deux grandeurs
    différentes sans que rien ne le dise.
    """

    libelle: str
    par_prise: Callable[[MesuresDunePrise], int | None]
    """`None` quand la mesure n'a pas de valeur sur cette prise — le délai avant première
    valeur d'une prise qui n'en a livré aucune. Ces prises sortent de la moyenne **et** de
    l'étendue : « zéro tour avant une valeur jamais venue » serait le meilleur score
    possible pour le pire comportement possible."""

    sens: str
    """Ce qu'on cherche : `"baisse"`, `"hausse"`, ou `"stable"` quand un mouvement dans
    l'un ou l'autre sens est également une information."""


COMPTEURS: tuple[Compteur, ...] = (
    Compteur("Rejets du validateur", lambda prise: len(prise.rejets), "baisse"),
    Compteur("Tours repliés", lambda prise: len(prise.replis), "baisse"),
    Compteur(
        "Chiffres sur les tours de domaine", lambda prise: prise.chiffres_de_domaine, "stable"
    ),
    Compteur(
        "Markdown non rendu par le front",
        lambda prise: sum(compte for _, compte in prise.formes_markdown),
        "baisse",
    ),
    Compteur("Itérations", lambda prise: sum(prise.iterations), "stable"),
    Compteur(
        "Tours avant la première valeur (nº3)", lambda prise: prise.tours_avant_valeur, "stable"
    ),
)
"""Les mesures qui bougent quand un prompt change. **Les critères binaires n'y sont pas** :
ils sont tenus par du code depuis l'étape 9 et ne bougeront pas — les comparer publierait
cinq lignes « 0 → 0 » qui feraient perdre les cinq qui parlent.

`sens` n'est pas décoratif. Le résultat cherché à l'étape 13 n'est pas « le taux de rejet
baisse » mais « il baisse **sans** que la métrique nº3 monte » : une mesure qu'on veut voir
stable et qui bouge est une information, même quand elle bouge « dans le bon sens »."""


@dataclass(frozen=True, slots=True)
class Ecart:
    """Un compteur, ses deux valeurs **par passe**, l'étendue de référence, le verdict."""

    libelle: str
    avant: float
    apres: float
    dispersion: float
    sens: str

    @property
    def delta(self) -> float:
        return self.apres - self.avant

    @property
    def verdict(self) -> str:
        """**La phrase que le brief exige, calculée plutôt que rédigée.**

        La comparaison se fait à `PRECISION` près : les valeurs sont des moyennes, et
        `0.30000000000000004 > 0.3` est un artefact de flottant, pas un signal.
        """
        if abs(self.delta) < PRECISION:
            return IDENTIQUE
        return SIGNAL if abs(self.delta) - self.dispersion > PRECISION else BRUIT


PRECISION = 1e-9
"""En deçà, deux moyennes sont la même. Les valeurs comparées sont des flottants issus de
divisions ; sans ce seuil, un verdict dépendrait d'un bit de mantisse."""


def _par_scenario(mesures: Mesures, compteur: Compteur) -> dict[str, list[int]]:
    """Les valeurs d'un compteur, par scénario, **les absences retirées**.

    Un scénario dont aucune prise n'a de valeur disparaît de la table : il ne contribue ni
    à la moyenne, ni à l'étendue. Le compter zéro le ferait peser comme un scénario
    parfait sur le délai avant première valeur, alors qu'il n'en a livré aucune.
    """
    groupes: dict[str, list[int]] = {}
    for prise in mesures.prises:
        valeur = compteur.par_prise(prise)
        if valeur is not None:
            groupes.setdefault(prise.scenario, []).append(valeur)
    return groupes


def valeur_par_passe(mesures: Mesures, compteur: Compteur) -> float:
    """La moyenne par prise de chaque scénario, sommée : **ce qu'une passe produit**.

    ⚠️ **Une somme de moyennes, jamais un total.** Les deux campagnes n'ont pas forcément
    le même nombre de prises par scénario — l'étape 12 en a tiré une là où l'étape 13 en
    tire trois. Comparer des totaux comparerait des tailles d'échantillon, et l'écart
    mesurerait surtout combien de fois on a tiré.

    La moyenne est prise **par scénario** et non sur toutes les prises confondues : sans
    cela, un scénario à six prises pèserait deux fois celui qui en a trois, et la
    comparaison bougerait quand on change le nombre de prises d'un seul scénario — ce que
    l'étape 13 a fait sur `question_de_domaine`.
    """
    return sum(sum(valeurs) / len(valeurs) for valeurs in _par_scenario(mesures, compteur).values())


PLANCHER_DETENDUE = 1
"""Ce qu'un scénario contribue à la dispersion quand ses prises donnent **la même valeur**.

⚠️ **Sans lui, ce module tombait dans le piège que sa propre docstring décrit.** Il écrit
qu'une dispersion nulle ne veut pas dire « stable » mais « on ne l'a pas vu bouger » — et
il traitait pourtant l'étendue observée comme une borne dure, si bien qu'un scénario vu
trois fois à la même valeur rendait **tout** écart « au-delà du bruit ».

Le cas qui l'a montré : la métrique nº3 est constante sur les onze scénarios de la ligne
de base, donc d'étendue nulle, et une baisse de 1,33 y était déclarée significative. Or
l'étape 12 avait mesuré `besoin_flou` à **2, 2 puis 3 tours** sur le même prompt : l'étendue
de cette métrique n'est pas nulle, elle n'a simplement pas été revue à ce tirage-là.

Trois tirages identiques ne prouvent pas une constante ; ils bornent l'étendue **par en
dessous**. On ajoute donc le plus petit pas observable — 1, puisque tous ces compteurs sont
entiers. C'est peu, et c'est exactement ce qu'il faut : la seule mesure que ce plancher
fait basculer est celle dont on savait par ailleurs que son étendue n'était pas nulle, et
le markdown (51 contre 43) reste au-delà."""


def etendue_par_scenario(mesures: Mesures, compteur: Compteur) -> float:
    """La somme, sur les scénarios, de `max - min` des prises, **jamais moins d'un pas**.

    **Même unité que `valeur_par_passe`** : l'une et l'autre valent « pour une passe
    complète des scénarios », et sont donc comparables. C'est ce qui autorise le verdict.

    Deux façons de sous-estimer, et le plancher n'en corrige qu'une :

    * **un scénario vu trois fois à la même valeur** contribue `PLANCHER_DETENDUE`, pas
      zéro — voir sa docstring ;
    * **un scénario à une seule prise** contribue ce même plancher, alors que son étendue
      est franchement **inconnue**. Le plancher ne prétend pas la connaître : c'est
      pourquoi l'étape 13 paie trois prises partout, et pourquoi `_avertissement()`
      nomme ceux qui n'en ont qu'une.
    """
    return float(
        sum(
            max(max(valeurs) - min(valeurs), PLANCHER_DETENDUE)
            for valeurs in _par_scenario(mesures, compteur).values()
        )
    )


def scenarios_a_une_prise(mesures: Mesures) -> tuple[str, ...]:
    """Ceux dont la dispersion est **inconnue**, pas nulle. Le tableau les nomme."""
    comptes: dict[str, int] = {}
    for prise in mesures.prises:
        comptes[prise.scenario] = comptes.get(prise.scenario, 0) + 1
    return tuple(sorted(nom for nom, compte in comptes.items() if compte < 2))


def ecarts(avant: Mesures, apres: Mesures) -> tuple[Ecart, ...]:
    """Un `Ecart` par compteur. La dispersion vient de la campagne **de référence**.

    De `avant` et non d'`apres` : la question posée est « le nouveau prompt a-t-il fait
    quelque chose que l'ancien ne faisait pas ? », et l'étalon de bruit est donc celui du
    monde d'avant. Prendre celui d'après ferait dépendre le verdict de ce qu'on mesure.
    """
    return tuple(
        Ecart(
            libelle=compteur.libelle,
            avant=valeur_par_passe(avant, compteur),
            apres=valeur_par_passe(apres, compteur),
            dispersion=etendue_par_scenario(avant, compteur),
            sens=compteur.sens,
        )
        for compteur in COMPTEURS
    )


def rendre(
    avant: Mesures,
    apres: Mesures,
    *,
    nom_avant: str,
    nom_apres: str,
    question: str,
    couverture: Couverture | None = None,
    reserves: Sequence[str] = (),
) -> str:
    """La comparaison entière, en markdown. Stable octet pour octet, comme le rapport.

    `question` est ce que cette comparaison cherche à savoir — « la borne supérieure de la
    dérive du modèle », « l'effet de la cible 1 ». Elle est **écrite dans le fichier**
    parce que trois comparaisons presque identiques cohabiteront dans `docs/eval/`, et que
    celle qui ne dit pas ce qu'elle mesure sera lue comme celle d'à côté.
    """
    lignes = [
        f"# Comparaison {nom_avant} → {nom_apres}",
        "",
        f"**Ce que cette comparaison cherche à savoir.** {question}",
        "",
        *_reserves(reserves),
        *_couverture(couverture, nom_avant, nom_apres),
        *_avertissement(avant, nom_avant),
        "",
        "## Les mesures qui bougent",
        "",
        *_tableau(
            (
                "Mesure",
                f"{nom_avant}",
                f"{nom_apres}",
                "Écart",
                "Dispersion",
                "Verdict",
                "Sens cherché",
            ),
            [
                (
                    ecart.libelle,
                    f"{ecart.avant:.2f}",
                    f"{ecart.apres:.2f}",
                    f"{ecart.delta:+.2f}",
                    f"± {ecart.dispersion:.2f}",
                    ecart.verdict,
                    ecart.sens,
                )
                for ecart in ecarts(avant, apres)
            ],
        ),
        "",
        "## Les critères, des deux côtés",
        "",
        *_tableau(
            ("Critère", f"{nom_avant}", f"{nom_apres}"),
            [
                ("nº1 — griefs livrés", str(avant.griefs_livres), str(apres.griefs_livres)),
                (
                    "nº2 — violations budget",
                    str(avant.violations_budget),
                    str(apres.violations_budget),
                ),
                (
                    "nº3 — tours avant valeur (médiane)",
                    _mediane(avant),
                    _mediane(apres),
                ),
                ("nº4 — attendu en top 3", _top3(avant), _top3(apres)),
                (
                    "nº6 — zéro résultat traité",
                    f"{avant.zero_resultats_traites}/{avant.zero_resultats}",
                    f"{apres.zero_resultats_traites}/{apres.zero_resultats}",
                ),
                (
                    "Prises sans aucune valeur livrée",
                    f"{avant.prises_sans_valeur}/{len(avant.prises)}",
                    f"{apres.prises_sans_valeur}/{len(apres.prises)}",
                ),
            ],
        ),
        "",
        "⚠️ **La métrique nº3 est un garde-fou, pas une cible.** Elle compte les tours client",
        "avant la première valeur : son minimum atteignable est **1**, et il est déjà atteint.",
        "Ce qu'on surveille ici est qu'elle ne **monte** pas — un modèle rendu plus prudent",
        "avec les chiffres sonde davantage et montre plus tard.",
        "",
        "⚠️ **Elle porte sa dispersion comme les cinq autres mesures**, dans le tableau",
        "ci-dessus. Publier une baisse de nº3 sans son étendue, après avoir appliqué",
        "« au-delà / dans le bruit » partout ailleurs, serait un double standard sur la seule",
        "métrique qui va dans le bon sens — c'est ce qu'un relecteur verrait en premier, et",
        "il aurait raison.",
        "",
        "## Les codes de grief, des deux côtés",
        "",
        *_tableau_des_codes(avant, apres, nom_avant, nom_apres),
        "",
        "⚠️ **Un code qui cesse de tirer n'est pas en soi une bonne nouvelle.** Si la forme",
        "correspondante a disparu des appendices A des deux rapports, c'est le prompt ; si le",
        "code cesse de tirer sans que rien n'ait changé dans la prose, c'est un trou. Les deux",
        "se lisent en ouvrant les rapports, pas en lisant ce tableau.",
    ]
    return "\n".join(lignes).rstrip("\n") + "\n"


def _reserves(reserves: Sequence[str]) -> list[str]:
    """Ce qu'aucun des deux tableaux ne dit, et qui change leur lecture.

    ⚠️ **Une prise écartée pour divergence disparaît des deux côtés en silence** : elle
    n'est ni dans les scénarios comparés, ni dans les scénarios « écartés » de la
    couverture, puisqu'aucun des deux jeux ne la porte plus. `Couverture` ne peut pas la
    voir — elle compare ce qui a été mesuré. Elle se déclare donc ici, ou nulle part.
    """
    if not reserves:
        return []
    return [
        "> ⚠️ **Ce que ces chiffres ne disent pas d'eux-mêmes.**",
        ">",
        *[
            (f"> - {ligne}" if rang == 0 else f">   {ligne}")
            for reserve in reserves
            for rang, ligne in enumerate(reserve.splitlines())
        ],
        "",
    ]


def _couverture(couverture: Couverture | None, nom_avant: str, nom_apres: str) -> list[str]:
    """Sur quoi la comparaison porte, **et ce que l'intersection lui a coûté**.

    En tête du fichier, avant les tableaux : une réserve d'échantillon lue après les
    chiffres arrive trop tard — la conclusion est déjà prise.
    """
    if couverture is None:
        return []
    if couverture.complete:
        return [
            f"**Couverture.** Les deux jeux portent les mêmes {len(couverture.scenarios)} "
            f"scénarios — {couverture.prises_avant} prises contre {couverture.prises_apres}. "
            "La comparaison est complète.",
            "",
            "Les valeurs comparées sont, par scénario, la **moyenne sur ses prises**, sommée",
            "sur les scénarios : ce qu'une passe complète produit en moyenne. Un total comparerait",
            "des tailles d'échantillon.",
            "",
        ]

    part = (
        f"{couverture.rejets_exclus} des {couverture.rejets_total}"
        if couverture.rejets_total
        else "0 des 0"
    )
    lignes = [
        f"> ⚠️ **Comparaison sur les {len(couverture.scenarios)} scénarios communs.** Les deux "
        "jeux ne portent pas",
        "> les mêmes scénarios. La comparaison est donc réduite à ceux présents des **deux**",
        f"> côtés — {couverture.prises_avant} prises de **{nom_avant}** contre "
        f"{couverture.prises_apres} de **{nom_apres}**.",
        ">",
        "> ⚠️ **Les prises ne sont pas appariées, et elles ne peuvent pas l'être** : un numéro",
        "> de prise est un index, pas une identité. La température n'est pas fixée, et la",
        "> prise 2 d'une campagne n'a aucun lien avec la prise 2 de l'autre. Les valeurs",
        "> comparées sont donc, par scénario, la **moyenne sur ses prises**, sommée sur les",
        "> scénarios : ce qu'une passe complète produit en moyenne.",
        ">",
        "> Scénarios écartés : "
        + ", ".join(f"`{nom}`" for nom in couverture.scenarios_exclus)
        + ".",
    ]
    if couverture.absents_apres:
        lignes.append(
            f"> Absents de **{nom_apres}** : "
            + ", ".join(f"`{nom}`" for nom in couverture.absents_apres)
            + "."
        )
    if couverture.absents_avant:
        lignes.append(
            f"> Absents de **{nom_avant}** : "
            + ", ".join(f"`{nom}`" for nom in couverture.absents_avant)
            + "."
        )
    lignes += [
        ">",
        "> ⚠️ **L'exclusion n'est pas neutre, et voici de combien** : les prises écartées",
        f"> portaient **{part} rejets** de {nom_avant}. La comparaison porte donc sur ses",
        "> scénarios les plus **calmes**, où tout écart est mécaniquement plus petit. Ce qui",
        "> est publié ici **sous-estime** vraisemblablement l'écart réel entre les deux",
        "> campagnes ; ce n'est pas une borne inférieure démontrée, c'est une raison de ne",
        "> pas lire un petit écart comme une absence d'effet.",
        "",
    ]
    return lignes


def _avertissement(reference: Mesures, nom: str) -> list[str]:
    """Ce que la dispersion vaut, **dans le fichier**, pas seulement dans une docstring."""
    solitaires = scenarios_a_une_prise(reference)
    lignes = [
        "> ⚠️ **Comment lire la colonne « Verdict ».** La dispersion est l'étendue `max - min`",
        f"> des prises de **{nom}**, scénario par scénario, sommée. C'est de combien le total",
        "> aurait pu bouger par le seul tirage — la température n'est pas fixée, et une",
        "> cassette est un tirage, pas une espérance.",
        ">",
        "> **Ce n'est ni un écart-type ni un test.** C'est une borne délibérément généreuse,",
        "> estimée sur trois prises : elle déclare « au-delà » moins souvent qu'un test",
        "> statistique, ce qui est le sens dans lequel ce dépôt préfère se tromper.",
        ">",
        "> ⚠️ **Un scénario vu trois fois à la même valeur ne compte pas zéro.** « Stable par",
        "> construction » et « calme par chance » ne se distinguent pas à trois tirages : trois",
        "> tirages identiques bornent l'étendue par en dessous, ils ne la mesurent pas. Chaque",
        f"> scénario contribue donc au moins **{PLANCHER_DETENDUE} pas**. Sans ce plancher, un",
        "> scénario jamais vu bouger rendrait n'importe quel écart significatif.",
    ]
    if solitaires:
        lignes += [
            ">",
            "> ⚠️ **Dispersion inconnue, comptée pour zéro**, sur : "
            + ", ".join(f"`{nom}`" for nom in solitaires)
            + ". Un seul tirage n'a pas d'étendue. Le verdict y est donc **trop généreux**.",
        ]
    return lignes


def _tableau_des_codes(avant: Mesures, apres: Mesures, nom_avant: str, nom_apres: str) -> list[str]:
    """Par code, des deux côtés. **Dérivé des rejets**, jamais d'une liste écrite ici.

    ⚠️ **Dans la même unité que le tableau du dessus — par passe, pas en total.** Deux
    campagnes de tailles différentes affichées l'une en total et l'autre en moyenne se
    contrediraient à l'œil : « 4 contre 8 » d'un côté et « 3,33 contre 2,67 » de l'autre
    décrivent pourtant les mêmes rejets. La ligne des totaux bruts est en dessous, dite
    comme telle.
    """
    codes = sorted({rejet.code for rejet in avant.rejets} | {rejet.code for rejet in apres.rejets})
    if not codes:
        return ["Aucun texte refusé, ni d'un côté ni de l'autre."]
    return _tableau(
        ("Code de grief", f"{nom_avant} /passe", f"{nom_apres} /passe", "Écart", "Bruts"),
        [
            (
                f"`{code.value}`",
                f"{(gauche := _code_par_passe(avant, code)):.2f}",
                f"{(droite := _code_par_passe(apres, code)):.2f}",
                f"{droite - gauche:+.2f}",
                f"{sum(1 for rejet in avant.rejets if rejet.code is code)} → "
                f"{sum(1 for rejet in apres.rejets if rejet.code is code)}",
            )
            for code in codes
        ],
    )


def _code_par_passe(mesures: Mesures, code: object) -> float:
    """La moyenne par scénario des rejets d'un code, sommée. Même unité que le reste."""
    groupes: dict[str, list[int]] = {}
    for prise in mesures.prises:
        groupes.setdefault(prise.scenario, []).append(
            sum(1 for rejet in prise.rejets if rejet.code is code)
        )
    return sum(sum(valeurs) / len(valeurs) for valeurs in groupes.values())


def _tableau(entetes: Sequence[str], lignes: Sequence[Sequence[str]]) -> list[str]:
    return [
        "| " + " | ".join(entetes) + " |",
        "|" + "|".join("---" for _ in entetes) + "|",
        *["| " + " | ".join(ligne) + " |" for ligne in lignes],
    ]


def _mediane(mesures: Mesures) -> str:
    if not mesures.tours_par_prise:
        return SANS_OBJET
    return f"{statistics.median(mesures.tours_par_prise):.1f}"


def _top3(mesures: Mesures) -> str:
    part = mesures.part_attendus_en_top3
    if part is None:
        return SANS_OBJET
    return f"{mesures.attendus_en_top3}/{mesures.prises_avec_attendu}"


__all__ = [
    "COMPTEURS",
    "PLANCHER_DETENDUE",
    "Couverture",
    "Ecart",
    "couvrir",
    "ecarts",
    "etendue_par_scenario",
    "rendre",
    "valeur_par_passe",
]
