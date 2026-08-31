"""Ce qu'on sait lire dans un texte libre : identifiants, montants, valeurs unitaires.

**Pur.** Aucune connaissance du contexte fourni : ce module dit ce que la phrase
*contient*, `regles.py` dit si le contexte l'autorise. La séparation n'est pas
cosmétique — elle permet de tester l'extraction sur des chaînes nues, sans construire
un catalogue, et elle laisse un seul endroit à changer le jour où le découpage en
phrases devient autre chose qu'un `split`.

### Le découpage en phrases est une **heuristique**, et elle vit ici seule

`SEPARATEURS_DE_PHRASE` est le seul endroit du projet qui décide où une phrase
s'arrête. Ce n'est pas une analyse syntaxique : c'est un `split` sur `.`, `!`, `?` et
le saut de ligne, avec **une** exception qui n'est pas négociable — un point entre
deux chiffres n'est pas une fin de phrase. Sans elle, « 417.14 $ » se couperait en
« 417 » et « 14 $ », et la règle 2 comparerait des nombres qui n'existent pas.

La conséquence, écrite plutôt que découverte : « M. Dupont » ou « etc. » coupent une
phrase en deux. Le prix payé est un contexte de phrase trop étroit, jamais trop
large — une règle peut donc rater une attribution, elle n'en invente pas.

### Les nombres se lisent en `Decimal`, dans les deux séparateurs décimaux

`en_tool_result()` sérialise les `Decimal` en chaînes (`"108.00"`) ; le modèle écrit
en français (`108,00 $`). `en_decimal()` ramène les deux à la même valeur, et
`canonique()` leur donne la même écriture — `Decimal("108")` et `Decimal("108.00")`
sont égaux, mais leurs `str()` ne le sont pas, et c'est sur des chaînes que les
valeurs de specs sont indexées.

⚠️ **Aucune comparaison ne passe par un flottant.** C'est la même règle que
`tolerance_budget()` : un prix porte un invariant produit, il se compare en décimal
exact.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from raiyon.catalogue.schemas import MOTIF_ID
from raiyon.matching.attributs import ATTRIBUTS

# --------------------------------------------------------------------------- #
# Phrases
# --------------------------------------------------------------------------- #

SEPARATEURS_DE_PHRASE = re.compile(r"(?<!\d)\.(?!\d)|[!?\n]")
"""**Le seul endroit** où le projet décide où une phrase s'arrête. Voir la docstring
du module : c'est une heuristique, et le point décimal en est l'exception."""


def phrases(texte: str) -> tuple[str, ...]:
    """Découpe en phrases, les vides retirées. Heuristique — voir le module."""
    return tuple(
        morceau.strip() for morceau in SEPARATEURS_DE_PHRASE.split(texte) if morceau.strip()
    )


# --------------------------------------------------------------------------- #
# Nombres
# --------------------------------------------------------------------------- #

ESPACES = "\u0020\u00a0\u202f\u2009"
"""Espace, insécable, insécable étroite, fine — écrites en points de code exprès.

Un séparateur de milliers français peut être n'importe lequel des quatre selon le
clavier et le modèle, et les quatre sont **visuellement identiques** : les poser en
littéral rendrait ce module impossible à relire, et une faute de frappe y serait
indétectable à l'œil. C'est aussi ce que `ruff` dit en refusant les espaces ambigus."""

_ESPACES_A_RETIRER = str.maketrans("", "", ESPACES)

NOMBRE = rf"\d+(?:[{ESPACES}]\d{{3}})*(?:[.,]\d+)?"
"""Un nombre tel qu'un modèle l'écrit : `144`, `417.14`, `417,14`, `1 299,99`."""


def en_decimal(texte: str) -> Decimal | None:
    """Lit un nombre écrit en français ou en anglais. `None` si ce n'en est pas un.

    Trois cas, dans cet ordre :

    1. **les deux séparateurs** — le plus à droite est le séparateur décimal
       (`1.299,99` comme `1,299.99`) ;
    2. **une seule virgule** — décimale si un ou deux chiffres suivent (`417,14`),
       séparateur de milliers sinon (`1,299`) ;
    3. **un seul point** — toujours décimal. C'est la convention de `en_tool_result()`,
       et l'ambiguïté restante (`1.299`) se tranche du côté qui ne fabrique pas de
       valeur : lire mille deux cent quatre-vingt-dix-neuf là où le modèle écrivait
       1,299 donnerait un montant que personne n'a fourni.
    """
    nu = texte.translate(_ESPACES_A_RETIRER)
    if "," in nu and "." in nu:
        if nu.rfind(",") > nu.rfind("."):
            nu = nu.replace(".", "").replace(",", ".")
        else:
            nu = nu.replace(",", "")
    elif nu.count(",") == 1:
        entier, _, decimales = nu.partition(",")
        nu = f"{entier}.{decimales}" if 1 <= len(decimales) <= 2 else f"{entier}{decimales}"
    else:
        nu = nu.replace(",", "")
    try:
        return Decimal(nu)
    except InvalidOperation:
        return None


def canonique(valeur: Decimal) -> str:
    """L'écriture unique d'un décimal. `27`, `27.0` et `27.00` rendent tous `"27"`.

    `Decimal.normalize()` seul ne suffit pas : il rend `2E+1` pour `Decimal("20")`,
    et l'index des valeurs de specs deviendrait illisible autant qu'inutilisable.
    """
    reduit = valeur.normalize()
    _, _, exposant = reduit.as_tuple()
    if isinstance(exposant, int) and exposant > 0:
        reduit = reduit.quantize(Decimal(1))
    return str(reduit)


# --------------------------------------------------------------------------- #
# Identifiants
# --------------------------------------------------------------------------- #

MOTIF_ID_LIBRE = re.compile(rf"(?<![\w-]){MOTIF_ID.removeprefix('^').removesuffix('$')}(?![\w-])")
"""`MOTIF_ID` désancré, borné à gauche et à droite. **Dérivé, jamais recopié** : le
jour où le format d'identifiant change, il change ici aussi.

C'est ce que §3.4 du schéma promettait — « un ID inventé par le LLM est trivialement
détectable » : `{categorie}-{10 hexadécimaux}` ne ressemble à aucun mot français, donc
un jeton conforme dans une phrase **est** une citation d'identifiant, jamais un
faux positif de vocabulaire."""


def identifiants(texte: str) -> tuple[str, ...]:
    """Les jetons conformes au format d'identifiant, dans l'ordre, dédoublonnés."""
    return tuple(dict.fromkeys(MOTIF_ID_LIBRE.findall(texte)))


# --------------------------------------------------------------------------- #
# Montants
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Montant:
    """Un montant en dollars lu dans le texte, et l'extrait qui le porte."""

    valeur: Decimal
    extrait: str


MOTIF_MONTANT = re.compile(rf"({NOMBRE})[{ESPACES}]*(?:\$|dollars?|USD(?!/))", re.IGNORECASE)
"""⚠️ `USD(?!/)` : `USD/Go` est une **unité de spec** (`price_per_gb`), pas un montant.
Sans la garde négative, « 0,10 USD/Go » entrerait dans la règle 2 comme un prix."""


def montants(texte: str) -> tuple[Montant, ...]:
    """Tous les montants en dollars du texte, dans l'ordre d'apparition."""
    trouves = []
    for occurrence in MOTIF_MONTANT.finditer(texte):
        valeur = en_decimal(occurrence.group(1))
        if valeur is not None:
            trouves.append(Montant(valeur, occurrence.group(0).strip()))
    return tuple(trouves)


# --------------------------------------------------------------------------- #
# Valeurs unitaires
# --------------------------------------------------------------------------- #

UNITE_DE_PRIX = "USD"
"""Sortie de la liste des unités : un prix est l'affaire de la règle 2, qui sait à
quel produit il doit appartenir. L'y laisser produirait deux griefs pour une faute."""

UNITES_SUPPLEMENTAIRES = frozenset({"To", "coeurs", "px", '"'})
"""Ce que le registre ne porte pas et qu'un modèle écrit quand même : le téraoctet
(le catalogue compte en `Go`), `cœurs` sans ligature, `px` pour `pixels`, et le
pouce en guillemet droit. Écrites ici plutôt que dans `attributs.py` : ce sont des
formes de **rédaction**, pas des unités du catalogue.

⚠️ **`GB`, `TB` et `MB` en sont volontairement absents.** Les noms de produits du
catalogue sont anglais et en contiennent (`Corsair Vengeance 16 GB`) : les déclarer
unités ferait crier la règle 5 sur un nom cité **verbatim**, c'est-à-dire sur le
comportement exact que §3.4ter réclame."""


def unites_connues() -> frozenset[str]:
    """Les unités du registre, moins le prix, plus les formes de rédaction.

    Dérivées d'`ATTRIBUTS` et non écrites à la main : une unité ajoutée au catalogue
    entre ici toute seule, et le validateur ne se met pas à ignorer un champ neuf.
    """
    du_registre = {
        attribut.unite
        for champs in ATTRIBUTS.values()
        for attribut in champs.values()
        if attribut.unite is not None and attribut.unite != UNITE_DE_PRIX
    }
    return frozenset(du_registre | UNITES_SUPPLEMENTAIRES)


def _motif_des_unites() -> re.Pattern[str]:
    """Alternation des unités, **les plus longues d'abord** (`USD/Go` avant `Go`).

    La borne de droite refuse une lettre : `12 Go` est une capacité, `12 Gold` non.
    """
    alternatives = "|".join(
        re.escape(unite) for unite in sorted(unites_connues(), key=_par_longueur)
    )
    return re.compile(rf"({NOMBRE})[{ESPACES}]*({alternatives})(?![A-Za-zÀ-ÖØ-öø-ÿ])")


def _par_longueur(unite: str) -> tuple[int, str]:
    return (-len(unite), unite)


MOTIF_UNITE = _motif_des_unites()


@dataclass(frozen=True, slots=True)
class ValeurUnitaire:
    """Un nombre suivi d'une unité connue, et l'extrait qui le porte."""

    valeur: Decimal
    unite: str
    extrait: str


def valeurs_unitaires(texte: str) -> tuple[ValeurUnitaire, ...]:
    """Tous les « nombre + unité » du texte, dans l'ordre d'apparition.

    ⚠️ **Un entier nu — sans unité et sans `$` — n'est rendu par personne**, ni ici ni
    par `montants()`. C'est l'exemption assumée du §7 : sans elle, « je vous propose
    trois modèles » déclencherait un grief, et un validateur qui crie sur du français
    correct finit par être débranché. La conséquence est réelle : « 32 candidats »
    pourrait être faux sans que rien ne le voie.
    """
    trouves = []
    for occurrence in MOTIF_UNITE.finditer(texte):
        valeur = en_decimal(occurrence.group(1))
        if valeur is not None:
            trouves.append(ValeurUnitaire(valeur, occurrence.group(2), occurrence.group(0).strip()))
    return tuple(trouves)


# --------------------------------------------------------------------------- #
# Noms de produits — le verbatim, et sa contrefaçon
# --------------------------------------------------------------------------- #

SEUIL_DE_PROXIMITE = 0.8
"""Rapport `difflib` à partir duquel deux jetons sont « le même mot mal écrit ».
Mesuré sur le cas qui motive la règle : `odyssey` contre `odyssee` vaut 0,857."""

SEUIL_DE_RESSEMBLANCE = 0.6
"""Part des jetons d'un nom qu'il faut retrouver dans une phrase pour dire que le nom
y est cité. Deux jetons sur trois — `Samsung` et une `Odyssée` francisée — suffisent ;
la marque seule ne suffit jamais (voir `ressemble()`)."""

LONGUEUR_MINIMALE_POUR_LE_FLOU = 4
"""En dessous, on n'accepte que l'égalité : `de` et `dell` ne sont pas le même mot,
et un rapport calculé sur trois lettres ne dit rien."""

MOTS_GENERIQUES = frozenset(
    {
        "modele",
        "modeles",
        "produit",
        "produits",
        "reference",
        "references",
        "gamme",
        "gammes",
        "version",
        "versions",
        "option",
        "options",
        "ecran",
        "ecrans",
        "processeur",
        "processeurs",
        "casque",
        "casques",
        "memoire",
        "stockage",
        "carte",
        "cartes",
        "graphique",
        "graphiques",
        "budget",
        "prix",
        "choix",
    }
)
"""Vocabulaire courant que le rapprochement flou ne doit jamais attraper. **C'est un
garde-fou de faux positif, pas une théorie** : sans lui, « trois modèles » pourrait
ressembler à un nom de produit contenant `modele`, et le validateur crierait sur du
français correct."""


def replier(texte: str) -> str:
    """Minuscules, accents retirés. La comparaison de jetons se fait là-dessus.

    ⚠️ **Le verbatim, lui, ne passe jamais par ici.** Le repli sert à détecter qu'un
    nom a été *réécrit* ; l'égalité qui l'innocente est une égalité de caractères,
    casse et espaces compris (§3.4ter).
    """
    decompose = unicodedata.normalize("NFKD", texte.casefold())
    return "".join(caractere for caractere in decompose if not unicodedata.combining(caractere))


_JETON = re.compile(r"[0-9a-z]+")


def jetons(texte: str) -> tuple[str, ...]:
    """Les mots du texte, repliés. La ponctuation et les tirets sont des séparateurs."""
    return tuple(_JETON.findall(replier(texte)))


def sans_les_noms(texte: str, noms: Iterable[str]) -> str:
    """Retire du texte les occurrences **verbatim** des noms fournis.

    C'est l'étape qui rend la règle 3 utilisable : un nom cité correctement disparaît,
    donc ses jetons ne peuvent plus servir à accuser un autre produit de la même
    marque. Les plus longs d'abord — sans quoi retirer `Dell S27` d'abord empêcherait
    de reconnaître `Dell S2721DGF`.
    """
    reste = texte
    for nom in sorted(noms, key=len, reverse=True):
        if nom:
            reste = reste.replace(nom, " ")
    return reste


def _proche(attendu: str, presents: Sequence[str]) -> bool:
    """Un jeton du nom est-il présent, tel quel ou à une faute près ?"""
    for present in presents:
        if present in MOTS_GENERIQUES:
            continue
        if present == attendu:
            return True
        if (
            len(present) >= LONGUEUR_MINIMALE_POUR_LE_FLOU
            and len(attendu) >= LONGUEUR_MINIMALE_POUR_LE_FLOU
            and SequenceMatcher(None, attendu, present).ratio() >= SEUIL_DE_PROXIMITE
        ):
            return True
    return False


def ressemble(nom: str, marque: str, presents: Sequence[str]) -> bool:
    """Le nom est-il cité **de travers** dans ces jetons ?

    Deux conditions cumulées, et la seconde est ce qui rend la règle vivable :

    1. une part suffisante des jetons du nom se retrouve dans le texte ;
    2. **au moins un jeton hors marque** en fait partie.

    Sans la seconde, « les deux Samsung que je vous propose » accuserait chaque
    Samsung du catalogue. Avec elle, « l'Odyssée de Samsung » reste détecté : c'est
    `odyssey` francisé, pas la marque, qui déclenche.

    ⚠️ **C'est une heuristique**, et elle est au §7. Elle ne prouve pas qu'un nom a été
    réécrit ; elle constate qu'un texte ressemble à un nom sans le contenir.
    """
    attendus = [jeton for jeton in jetons(nom) if len(jeton) >= 2]
    if not attendus:
        return False
    jetons_de_la_marque = set(jetons(marque))
    retrouves = 0
    hors_marque = False
    for attendu in attendus:
        if not _proche(attendu, presents):
            continue
        retrouves += 1
        if attendu not in jetons_de_la_marque:
            hors_marque = True
    return hors_marque and retrouves / len(attendus) >= SEUIL_DE_RESSEMBLANCE
