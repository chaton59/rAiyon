"""Les cinq règles. Chacune est pure, et chacune rend un grief **lisible par le modèle**.

Signature commune : `(texte, ContexteFourni) -> tuple[Grief, ...]`. Aucune ne lève,
aucune ne connaît la boucle, aucune n'a besoin d'une base ni d'une clé.

1. **Identifiants** — tout jeton au format d'identifiant existe dans `contexte.produits`.
   *Ferme le produit inventé et l'`id` approximatif.*
2. **Montants** — dans une phrase qui nomme un produit, un montant en `$` est le prix
   **de ce produit** ou son écart au budget ; ailleurs, c'est un prix fourni ou un
   agrégat fourni. *Ferme le prix modifié, **et le prix de sondage attribué à un
   produit**.*
3. **Noms** — un nom fourni qui apparaît dans le texte y apparaît **verbatim**.
   *Ferme la francisation et la réécriture (§3.4ter).*
4. **Écart au budget** — un produit hors budget cité l'est dans une phrase qui porte son
   `ecart_usd` exact. *C'est le **critère d'acceptation nº2**, vérifié sur la phrase.*
5. **Valeurs unitaires** — tout nombre suivi d'une unité connue est une valeur de spec
   ou d'agrégat fournie ; une valeur de **distribution** n'est admise que dans une phrase
   qui ne nomme aucun produit. *Ferme la spec transformée et la spec déduite d'un
   sondage, sans interdire de décrire le catalogue.*

### La convention du message, et elle vient d'`erreurs.py`

Un `Grief` porte un **code** (un par geste de correction, pas un par phrase), l'extrait
fautif, et une phrase qui dit **quoi faire**. Il sera relu par le modèle dans le message
de reprise : « tu as halluciné » ne se corrige pas, « ce montant n'est pas le prix de ce
produit, reprends celui du `tool_result` » si.

### Ce que ces règles ne ferment pas, et qu'il faut savoir en les lisant

* **Un entier nu, sans unité et sans `$`, n'est vérifié par rien** (§7). C'est
  l'exemption assumée : sans elle, « je vous propose trois modèles » lèverait un grief.
* **Un produit entièrement inventé dont le prix est une borne de sondage passe**, tant
  qu'aucun produit fourni n'est nommé dans la phrase : la règle 2 ne sait pas qu'un nom
  qu'elle ne connaît pas est un nom de produit. C'est la part de l'oracle à prix que la
  règle 2 ne referme pas, et elle est au §7.
* **Le rapprochement de noms est flou** (`extraction.ressemble`) : il constate une
  ressemblance, il ne prouve pas une réécriture.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from raiyon.validateur.contexte import ContexteFourni
from raiyon.validateur.extraction import (
    canonique,
    identifiants,
    jetons,
    montants,
    phrases,
    ressemble,
    sans_les_noms,
    valeurs_unitaires,
)


class CodeGrief(StrEnum):
    """Ce que le modèle doit corriger. **Un code par geste**, comme `CodeRefus`."""

    ID_INCONNU = "id_inconnu"
    """Un identifiant cité n'a jamais été rendu par `search_products`."""

    PRIX_ETRANGER_AU_PRODUIT = "prix_etranger_au_produit"
    """Un montant figure dans une phrase qui nomme un produit sans être ni son prix ni
    son écart au budget. C'est la forme que prend l'oracle à prix : une borne de
    sondage collée à un modèle nommé."""

    MONTANT_NON_FOURNI = "montant_non_fourni"
    """Un montant qui n'est ni un prix fourni ni un agrégat fourni."""

    NOM_REECRIT = "nom_reecrit"
    """Un nom de produit apparaît réécrit — traduit, francisé, recasse. §3.4ter exige
    le caractère pour caractère : c'est un identifiant que le client va retaper."""

    ECART_NON_DIT = "ecart_non_dit"
    """Un produit de la zone de tolérance est cité sans son écart exact au budget.
    Critère d'acceptation nº2."""

    VALEUR_NON_FOURNIE = "valeur_non_fournie"
    """Un nombre suivi d'une unité qui n'est la caractéristique d'aucun produit fourni
    ni un agrégat rendu par un outil."""


@dataclass(frozen=True, slots=True)
class Grief:
    """Un fait non fourni, l'endroit où il a été écrit, et quoi faire à la place."""

    code: CodeGrief
    extrait: str
    correction: str

    def en_ligne(self) -> str:
        """La ligne telle qu'elle part au modèle dans le message de reprise."""
        return f"- **{self.code.value}** — « {self.extrait} » : {self.correction}"


Regle = Callable[[str, ContexteFourni], tuple[Grief, ...]]


# --------------------------------------------------------------------------- #
# Ce que les règles partagent : « quels produits cette phrase nomme-t-elle ? »
# --------------------------------------------------------------------------- #


def produits_nommes(phrase: str, contexte: ContexteFourni) -> tuple[str, ...]:
    """Les `id` des produits fournis que cette phrase désigne.

    Trois façons de nommer, et les trois comptent — c'est ce qui empêche de contourner
    la règle 2 en changeant de désignation :

    1. l'identifiant ;
    2. le nom, **verbatim** ;
    3. le nom **réécrit** (`ressemble()`), parce qu'une francisation qui déplace un
       prix reste une attribution de prix.
    """
    trouves: dict[str, None] = {}
    for identifiant in identifiants(phrase):
        if identifiant in contexte.produits:
            trouves[identifiant] = None
    reste = sans_les_noms(phrase, [produit.nom for produit in contexte.produits.values()])
    jetons_du_reste = jetons(reste)
    for identifiant, produit in contexte.produits.items():
        if (produit.nom and produit.nom in phrase) or ressemble(
            produit.nom, produit.marque, jetons_du_reste
        ):
            trouves[identifiant] = None
    return tuple(trouves)


# --------------------------------------------------------------------------- #
# 1 — Les identifiants
# --------------------------------------------------------------------------- #


def regle_identifiants(texte: str, contexte: ContexteFourni) -> tuple[Grief, ...]:
    """Tout jeton conforme au format d'identifiant doit exister dans le contexte.

    Le format `{categorie}-{10 hexadécimaux}` ne ressemble à aucun mot français : un
    jeton conforme **est** une citation d'identifiant. C'est la règle la plus sûre du
    lot, et c'est ce que le choix d'un identifiant synthétique achetait déjà à
    l'étape 5.
    """
    griefs = []
    for identifiant in identifiants(texte):
        if identifiant not in contexte.produits:
            griefs.append(
                Grief(
                    CodeGrief.ID_INCONNU,
                    identifiant,
                    "cet identifiant n'a été rendu par aucun appel à `search_products` "
                    "dans cette conversation. Reprendre un `id` d'un résultat que vous "
                    "avez sous les yeux, ou chercher avant de citer.",
                )
            )
    return _uniques(griefs)


# --------------------------------------------------------------------------- #
# 2 — Les montants, et à qui ils appartiennent
# --------------------------------------------------------------------------- #


def regle_montants(texte: str, contexte: ContexteFourni) -> tuple[Grief, ...]:
    """Un montant dans une phrase qui nomme un produit appartient à **ce** produit.

    C'est la règle qui ferme l'oracle à prix du §7 : `probe_catalog` rend une fourchette
    exacte sur le sous-catalogue courant, donc la borne basse d'un sondage resserré est
    presque le prix d'un produit — mais elle n'est le prix de **personne**, et la coller
    à un modèle nommé est une affirmation que le code n'a jamais fournie.

    Dans une phrase qui ne nomme aucun produit, tout prix fourni et tout agrégat fourni
    sont admis : « je vous propose trois modèles entre 108 $ et 400 $ » est vrai.

    **Le budget de session fait exception, et lui seul** (correctif de l'étape 9). « Le X
    à 249,99 $ rentre dans vos 400 $ » est la formulation naturelle d'une question de
    vendeur, et elle le devient d'autant plus depuis que les questions sont validées. Le
    budget n'est pas un fait du catalogue : c'est une **parole du client**, entrée par
    `record_criteria` et rendue dans son `tool_result` — le lui répéter n'invente rien.

    ⚠️ **Ne rien élargir au-delà.** Les bornes d'agrégat restent interdites dans une
    phrase à produit : le budget est un montant **unique et attribuable**, une fourchette
    de sondage est une affirmation sur le catalogue que rien n'attache à un produit.
    C'est la distinction du piège nº6, et c'est le seul test de l'étape qui échoue si
    quelqu'un aplatit le contexte.
    """
    griefs = []
    for phrase in phrases(texte):
        trouves = montants(phrase)
        if not trouves:
            continue
        nommes = produits_nommes(phrase, contexte)
        if nommes:
            autorises = {contexte.prix[nom] for nom in nommes if nom in contexte.prix}
            autorises |= {
                contexte.hors_budget[nom] for nom in nommes if nom in contexte.hors_budget
            }
            if contexte.budget_usd is not None:
                autorises.add(contexte.budget_usd)
            code = CodeGrief.PRIX_ETRANGER_AU_PRODUIT
            correction = (
                "ce montant n'est ni le prix du produit nommé dans cette phrase, ni son "
                "écart au budget, ni le budget du client. Reprendre `prix_usd` (ou "
                "`ecart_usd`) du `tool_result`, chiffre pour chiffre — et sortir de "
                "cette phrase tout montant qui décrit un ensemble plutôt que ce "
                "produit : une fourchette de sondage n'est jamais le prix d'un produit."
            )
        else:
            autorises = set(contexte.prix.values()) | set(contexte.agregats)
            code = CodeGrief.MONTANT_NON_FOURNI
            correction = (
                "aucun outil n'a rendu ce montant dans cette conversation. Le reprendre "
                "d'un résultat que vous avez sous les yeux, ou ne pas le citer."
            )
        for montant in trouves:
            if montant.valeur not in autorises:
                griefs.append(Grief(code, montant.extrait, correction))
    return _uniques(griefs)


# --------------------------------------------------------------------------- #
# 3 — Les noms se citent verbatim
# --------------------------------------------------------------------------- #


def regle_noms_verbatim(texte: str, contexte: ContexteFourni) -> tuple[Grief, ...]:
    """Un nom fourni qui apparaît dans le texte y apparaît caractère pour caractère.

    La méthode est en deux temps, et le premier est ce qui la rend vivable : on retire
    d'abord du texte toutes les occurrences **verbatim** des noms fournis. Ce qui reste
    ne peut donc plus contenir un nom correctement cité — et une ressemblance dans ce
    reste est, elle, une réécriture.

    ⚠️ **C'est une heuristique** (`extraction.ressemble`), et elle est au §7. Elle
    constate qu'un texte ressemble à un nom sans le contenir ; elle ne prouve rien.
    """
    griefs = []
    for phrase in phrases(texte):
        reste = sans_les_noms(phrase, [produit.nom for produit in contexte.produits.values()])
        jetons_du_reste = jetons(reste)
        for produit in contexte.produits.values():
            if produit.nom in phrase:
                continue
            if ressemble(produit.nom, produit.marque, jetons_du_reste):
                griefs.append(
                    Grief(
                        CodeGrief.NOM_REECRIT,
                        phrase,
                        f"le nom du catalogue est {produit.nom!r} : le recopier "
                        "caractère pour caractère, sans le traduire ni changer une "
                        "majuscule ou un espace. C'est un identifiant que le client va "
                        "retaper dans un moteur de recherche ; la catégorie, elle, se "
                        "dit en français.",
                    )
                )
    return _uniques(griefs)


# --------------------------------------------------------------------------- #
# 4 — Hors budget : jamais sans l'écart
# --------------------------------------------------------------------------- #


def regle_ecart_au_budget(texte: str, contexte: ContexteFourni) -> tuple[Grief, ...]:
    """Un produit de la zone de tolérance cité l'est avec son écart exact.

    C'est le **critère d'acceptation nº2** qui cesse d'être une propriété structurelle
    du moteur — `produits` et `au_dessus_du_budget` sont deux champs distincts — pour
    devenir aussi une vérification sur la phrase. Le moteur garantit que le modèle a
    reçu les deux ensembles séparés ; cette règle garantit qu'il ne les a pas
    recollés en écrivant.
    """
    griefs = []
    for phrase in phrases(texte):
        nommes = produits_nommes(phrase, contexte)
        if not nommes:
            continue
        cites = {montant.valeur for montant in montants(phrase)}
        for identifiant in nommes:
            ecart = contexte.hors_budget.get(identifiant)
            if ecart is None or ecart in cites:
                continue
            produit = contexte.produits[identifiant]
            griefs.append(
                Grief(
                    CodeGrief.ECART_NON_DIT,
                    phrase,
                    f"{produit.nom} est au-dessus du budget : le citer exige de dire "
                    f"qu'il dépasse et **de combien** — {ecart} $ exactement, tel que "
                    "`ecart_usd` le donne. Le glisser dans la liste ne se fait pas.",
                )
            )
    return _uniques(griefs)


# --------------------------------------------------------------------------- #
# 5 — Les valeurs unitaires
# --------------------------------------------------------------------------- #


def regle_valeurs_unitaires(texte: str, contexte: ContexteFourni) -> tuple[Grief, ...]:
    """Tout nombre suivi d'une unité connue vient d'un produit fourni ou d'un agrégat.

    C'est la règle qui attrape la spec transformée (« 165 Hz » sur un écran qui en porte
    144) **et** la spec déduite d'un sondage.

    **Elle raisonne par phrase, comme la règle 2, et pour la même raison.** Une valeur
    lue dans la distribution de `probe_catalog` décrit un **ensemble** :

    * dans une phrase qui ne nomme aucun produit, elle est vraie — « les fréquences vont
      de 60 à 240 Hz » est exactement ce que `probe_catalog` existe pour faire dire
      (§3.7), et le refuser interdirait à l'agent de décrire son catalogue ;
    * dans une phrase qui nomme un produit, elle est fausse — « celui-ci est à 165 Hz »
      n'est pas « 12 écrans sont à 165 Hz ». C'est le piège nº9.

    ⚠️ **Le premier des deux points a été trouvé en conversation réelle**, et il coûtait
    cher : l'agent annonçait la vraie plage de fréquences du sous-catalogue, le
    validateur la refusait, et un message informatif et exact finissait en repli sur
    template. C'est le mode d'échec que l'étape redoutait — un validateur qui crie sur du
    français correct — pris en flagrant délit.

    ⚠️ **Les noms cités verbatim sont retirés avant lecture**, et ce n'est pas un
    assouplissement de confort : le catalogue contient `Sceptre C248W-1920RN`, et
    « 248W » s'y lit comme 248 watts. Un nom recopié caractère pour caractère est un
    **identifiant** (§3.4ter), pas une affirmation de caractéristique. Trouvé en
    conversation réelle lui aussi, sur une recommandation parfaitement juste.

    Le retrait ne cache rien : il ne porte que sur les caractères d'un nom **exact du
    catalogue**. « le X en 27 pouces » reste lu, puisque « 27 pouces » n'est pas dans le
    nom. C'est le même geste qu'à la règle 3, pour la même raison.

    La règle 2, elle, n'en a pas besoin : elle lit un nombre suivi d'un symbole de
    monnaie, et aucun nom du catalogue n'en porte.
    """
    griefs = []
    noms = [produit.nom for produit in contexte.produits.values()]
    for phrase in phrases(texte):
        attribuable = bool(produits_nommes(phrase, contexte))
        autorisees = set(contexte.valeurs_de_specs)
        if not attribuable:
            autorisees |= contexte.valeurs_de_distribution
        for valeur in valeurs_unitaires(sans_les_noms(phrase, noms)):
            if canonique(valeur.valeur) in autorisees or valeur.valeur in contexte.agregats:
                continue
            griefs.append(
                Grief(
                    CodeGrief.VALEUR_NON_FOURNIE,
                    valeur.extrait,
                    "cette valeur n'est déclarée par aucun produit fourni"
                    + (
                        " — et une valeur lue dans la distribution d'un sondage décrit un "
                        "ensemble, pas le produit nommé dans cette phrase."
                        if attribuable
                        else ", et aucun outil ne l'a rendue, pas même en distribution."
                    )
                    + " Reprendre la caractéristique du `tool_result`, ou ne rien affirmer.",
                )
            )
    return _uniques(griefs)


REGLES: tuple[Regle, ...] = (
    regle_identifiants,
    regle_montants,
    regle_noms_verbatim,
    regle_ecart_au_budget,
    regle_valeurs_unitaires,
)
"""L'ordre est celui du tableau de l'étape 9, et il est celui dans lequel les griefs
partent au modèle : de l'identifiant vers la valeur, du plus grossier au plus fin."""


def _uniques(griefs: Sequence[Grief]) -> tuple[Grief, ...]:
    """Dédoublonne sur (code, extrait) : un même défaut répété est un seul grief.

    Sans cela, une recommandation qui répète trois fois le même prix faux produirait
    trois lignes identiques dans le message de reprise, et le modèle chercherait trois
    corrections là où il n'y en a qu'une.
    """
    vus: dict[tuple[CodeGrief, str], Grief] = {}
    for grief in griefs:
        vus.setdefault((grief.code, grief.extrait), grief)
    return tuple(vus.values())
