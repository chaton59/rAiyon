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

from raiyon.eval.metriques import Mesures, MesuresDunePrise

SIGNAL = "au-delà"
BRUIT = "dans le bruit"
IDENTIQUE = "identique"
SANS_OBJET = "—"


@dataclass(frozen=True, slots=True)
class Compteur:
    """Une mesure comptée **par prise**, donc une dont la dispersion s'estime.

    Le total et la dispersion sortent de la même fonction : sans cela, on comparerait un
    total à l'étendue d'autre chose, et le verdict porterait sur deux grandeurs
    différentes sans que rien ne le dise.
    """

    libelle: str
    par_prise: Callable[[MesuresDunePrise], int]
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
)
"""Les mesures qui bougent quand un prompt change. **Les critères binaires n'y sont pas** :
ils sont tenus par du code depuis l'étape 9 et ne bougeront pas — les comparer publierait
cinq lignes « 0 → 0 » qui feraient perdre les cinq qui parlent.

`sens` n'est pas décoratif. Le résultat cherché à l'étape 13 n'est pas « le taux de rejet
baisse » mais « il baisse **sans** que la métrique nº3 monte » : une mesure qu'on veut voir
stable et qui bouge est une information, même quand elle bouge « dans le bon sens »."""


@dataclass(frozen=True, slots=True)
class Ecart:
    """Un compteur, ses deux totaux, l'étendue de référence, et le verdict."""

    libelle: str
    avant: int
    apres: int
    dispersion: int
    sens: str

    @property
    def delta(self) -> int:
        return self.apres - self.avant

    @property
    def verdict(self) -> str:
        """**La phrase que le brief exige, calculée plutôt que rédigée.**"""
        if self.delta == 0:
            return IDENTIQUE
        return SIGNAL if abs(self.delta) > self.dispersion else BRUIT


def etendue_par_scenario(mesures: Mesures, compteur: Compteur) -> int:
    """La somme, sur les scénarios, de `max - min` des prises. Voir la docstring du module.

    Un scénario à une seule prise contribue **zéro** : son étendue n'est pas nulle, elle
    est **inconnue**. La sous-estimer rendrait la dispersion trop petite, donc le verdict
    trop généreux — c'est pourquoi l'étape 13 paie trois prises partout, et pourquoi
    `_avertissement()` dit combien de scénarios n'en ont qu'une.
    """
    groupes: dict[str, list[int]] = {}
    for prise in mesures.prises:
        groupes.setdefault(prise.scenario, []).append(compteur.par_prise(prise))
    return sum(max(valeurs) - min(valeurs) for valeurs in groupes.values())


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
            avant=sum(compteur.par_prise(prise) for prise in avant.prises),
            apres=sum(compteur.par_prise(prise) for prise in apres.prises),
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
                    str(ecart.avant),
                    str(ecart.apres),
                    f"{ecart.delta:+d}",
                    f"± {ecart.dispersion}",
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
        "> ⚠️ **Une dispersion nulle ne veut pas dire « stable ».** Elle veut dire qu'on n'a",
        "> pas vu ce scénario bouger sur trois prises — « stable par construction » et « calme",
        "> par chance » ne se distinguent pas à ce nombre de tirages.",
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
    """Par code, des deux côtés. **Dérivé des rejets**, jamais d'une liste écrite ici."""
    codes = sorted({rejet.code for rejet in avant.rejets} | {rejet.code for rejet in apres.rejets})
    if not codes:
        return ["Aucun texte refusé, ni d'un côté ni de l'autre."]
    return _tableau(
        ("Code de grief", nom_avant, nom_apres, "Écart"),
        [
            (
                f"`{code.value}`",
                str(gauche := sum(1 for rejet in avant.rejets if rejet.code is code)),
                str(droite := sum(1 for rejet in apres.rejets if rejet.code is code)),
                f"{droite - gauche:+d}",
            )
            for code in codes
        ],
    )


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


__all__ = ["COMPTEURS", "Ecart", "ecarts", "etendue_par_scenario", "rendre"]
