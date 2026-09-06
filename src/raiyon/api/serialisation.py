"""Le contrat de fil : un `Evenement` du domaine vers une trame SSE. **Module pur.**

Ce module ne connaît ni FastAPI, ni le SDK Anthropic, ni la moindre connexion. Il ne sait
que traduire, et c'est ce qui permet de le tester en entier dans `make check`.

---

### Pourquoi il existe séparément : `assert_never`

La dernière branche de `nom_et_donnees()` appelle `typing.assert_never`. Un neuvième
événement ajouté à l'union en étape 12 ou 13 fera donc **échouer `make typecheck`** au
lieu d'être silencieusement absent du fil. C'est la même mécanique qu'`en_tool_result()`
dans `raiyon.tools.outils`, et c'est la seule raison suffisante de ne pas écrire cette
traduction dans les routes.

### Le français du fil est **dérivé du registre**, jamais inventé par le front (arbitrage H)

`Critere` ne porte ni libellé ni unité — c'est ce que le client a dit, pas ce que le
catalogue en sait — et les `specs` d'un produit sont en anglais. La console résout les
deux par `ATTRIBUTS[categorie][champ]` (arbitrage I de l'étape 6) ; **ce module fait
exactement le même geste**, et le fil porte `libelle_fr` et `unite` à côté de chaque
champ.

Sans cela, l'étape 11 coderait du français en dur dans du JavaScript, et §3.4ter —
« le français est du vocabulaire dérivé, jamais recopié » — cesserait d'être vrai de bout
en bout au moment précis où il devient visible à l'écran.

Trois structures portent déjà leur libellé, parce que le moteur le leur a posé au
registre : `Distribution`, `ChampDiscriminant` et `Proposition`. Elles sont recopiées
telles quelles plutôt que re-résolues — une seconde résolution serait une seconde
occasion de diverger.

### Ce que le fil porte, et ce qu'il ne porte pas (arbitrage G)

> **Ce qui prouve un invariant sort ; ce qui explique un classement reste.**

`text_rejected` part au client : petit (codes de grief et extrait), et c'est la seule
preuve visible à l'écran que §2 est tenu par du **code** et non par un prompt.

`ResultatMatching.traces` ne part pas : c'est du volume et du débogage de moteur.
`products_found` est réduit aux champs affichables, et un test le constate par une
assertion négative explicite. Restent dehors pour la même raison :
`ecartes_faute_de_donnee`, `Repli.iterations`, `Repli.outils_appeles`, et tout
`EtatSession` — cette dernière règle est déjà posée par `evenements.py`, et elle vaut ici.

Si l'étape 11 réclamait la trace, elle passerait par un endpoint dédié — pas par un
élargissement de `products_found`.

### Deux événements n'appartiennent pas au domaine (arbitrage F)

`error` et `done` sont produits par le générateur SSE, **jamais par la boucle**. L'union
d'`agent/evenements.py` décrit le dialogue ; « la base a coupé » n'en est pas un fait, et
l'y ajouter obligerait la console à traiter un cas qui ne peut pas lui arriver. Leurs noms
vivent donc ici, dans le vocabulaire de l'API, à côté des huit autres — un consommateur
n'a qu'une seule table à lire.

`done` est terminal et **obligatoire** : sans lui, le front ne distingue pas « tour
terminé » de « connexion tombée ». La fermeture du flux seule ne les sépare pas.

### Les `Decimal` sortent en chaînes, sans exception

Même convention qu'`en_tool_result()` : un flottant JSON perdrait des décimales sur un
prix, et §2 se joue au caractère près. Les booléens et les entiers, eux, gardent leur type
JSON — le front les affiche, il ne les compare pas à ce que le modèle a écrit.

### Le piège du SSE écrit à la main

Une trame est **une ligne de données**. `json.dumps` échappe tous les caractères de
contrôle, sauts de ligne compris, donc la prose multi-lignes du modèle ne peut pas couper
le flux au milieu d'un message. C'est vérifié par un test, pas par relecture : c'est le
défaut classique de cet encadrement, et il ne se voit qu'en production.
"""

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from enum import StrEnum
from typing import Any, assert_never

from raiyon.agent.evenements import (
    LIBELLES_MOTIF_DE_REPLI,
    CriteresMisAJour,
    Evenement,
    ProduitsTrouves,
    QuestionPosee,
    QuestionSuggeree,
    Repli,
    Sondage,
    Texte,
    TexteRejete,
)
from raiyon.catalogue.schemas import LIBELLES_CATEGORIE, Categorie, ProduitEnBase
from raiyon.matching.attributs import ATTRIBUTS, valeur_du_produit
from raiyon.matching.criteres import LIBELLES_OPTIMISATION, Critere, Optimisation
from raiyon.matching.depot import BornesPrix
from raiyon.matching.relachement import LIBELLES_MOTIF, Diagnostic, Motif, Proposition
from raiyon.matching.sondage import ChampDiscriminant, Distribution
from raiyon.tools.etat import MouvementRefuse, valeur_en_texte
from raiyon.tools.outils import BesoinDeBudget
from raiyon.validateur.regles import Grief

Donnees = dict[str, Any]
"""La charge utile d'une trame, avant `json.dumps`. Des types JSON, et rien d'autre."""


class NomEvenement(StrEnum):
    """Les dix noms du fil. **Fermé** : le front n'a pas d'autre vocabulaire à connaître.

    Les huit premiers viennent de l'union `Evenement` ; les deux derniers appartiennent à
    l'API (arbitrage F). Ils vivent dans la même énumération parce qu'ils voyagent dans le
    même champ `event:` et qu'un consommateur les lit avec le même `switch`.
    """

    CRITERES = "criteria_updated"
    SONDAGE = "catalog_probe"
    QUESTION_SUGGEREE = "suggested_question"
    PRODUITS = "products_found"
    QUESTION = "question"
    MESSAGE = "message"
    TEXTE_REJETE = "text_rejected"
    REPLI = "fallback"

    ERREUR = "error"
    """Produit par le générateur SSE seul. Suivi de la fermeture du flux."""

    FIN = "done"
    """Terminal et obligatoire. Sans lui, « tour fini » et « connexion tombée » se
    confondent."""


class CodeErreur(StrEnum):
    """Le vocabulaire des échecs de l'API. **Fermé**, jamais du texte libre.

    Deux valeurs, et elles sortent par deux portes différentes — c'est la ligne de partage
    de l'arbitrage E, lisible dans le type :

    * `TOUR_EN_COURS` ne voyage que dans le corps d'un **409**, décidé avant le premier
      octet ;
    * `INTERNE` ne voyage que dans un événement `error`, après le premier octet, quand il
      n'existe plus de code HTTP à changer.

    Une seule énumération pour les deux portes : le front affiche le même message quel que
    soit le chemin par lequel l'échec lui arrive.
    """

    TOUR_EN_COURS = "tour_en_cours"
    INTERNE = "interne"


# --------------------------------------------------------------------------- #
# L'encadrement SSE — trois lignes, aucune variante
# --------------------------------------------------------------------------- #


def trame(nom: NomEvenement, donnees: Mapping[str, Any]) -> str:
    """`event: <nom>` / `data: <JSON sur une seule ligne>` / ligne vide.

    `ensure_ascii=False` : le fil est en UTF-8, et l'échappement `\\uXXXX` rendrait une
    trame illisible en `curl` pour un gain nul. Les sauts de ligne de la prose, eux,
    **sont** échappés — `json.dumps` échappe tout caractère de contrôle — et c'est ce qui
    garantit qu'une trame reste une ligne.
    """
    return f"event: {nom.value}\ndata: {json.dumps(donnees, ensure_ascii=False)}\n\n"


def trame_de(evenement: Evenement) -> str:
    """La trame d'un événement du domaine."""
    nom, donnees = nom_et_donnees(evenement)
    return trame(nom, donnees)


def charge_derreur(code: CodeErreur, message: str) -> Donnees:
    """`{code, message}` — **la seule forme d'un échec porteur de `CodeErreur`**.

    Partagée par les deux portes de l'arbitrage E : l'événement `error`, après le premier
    octet, et le corps du **409**, avant. C'est ce qui rend vraie la promesse de
    `CodeErreur` — « le front affiche le même message quel que soit le chemin par lequel
    l'échec lui arrive » — au lieu de la laisser à la charge d'un lecteur qui saurait
    déballer le `detail` de `HTTPException` d'un côté et pas de l'autre.

    Le 404 et le 422 gardent leur forme FastAPI : ils ne portent **pas** de `CodeErreur`,
    et leur en inventer un pour uniformiser une clé donnerait un vocabulaire d'erreurs
    dont deux valeurs sur quatre ne voudraient rien dire.
    """
    return {"code": code.value, "message": message}


def trame_derreur(code: CodeErreur, message: str) -> str:
    """⚠️ `message` est écrit **pour le client, en français**, jamais le `str()` d'une
    exception : une trace SQLAlchemy sur une page web est une fuite (arbitrage E)."""
    return trame(NomEvenement.ERREUR, charge_derreur(code, message))


def trame_de_fin() -> str:
    """La trame terminale. Charge utile vide : sa seule information est son nom."""
    return trame(NomEvenement.FIN, {})


# --------------------------------------------------------------------------- #
# La traduction — une branche par événement, et `assert_never` au bout
# --------------------------------------------------------------------------- #


def nom_et_donnees(evenement: Evenement) -> tuple[NomEvenement, Donnees]:
    """Le nom de fil et la charge utile d'un événement du domaine.

    **L'exhaustivité est vérifiée par `mypy`, pas par relecture.** Un neuvième type ajouté
    à l'union `Evenement` fait échouer `make typecheck` sur `assert_never` — voir la
    docstring du module.
    """
    if isinstance(evenement, CriteresMisAJour):
        return NomEvenement.CRITERES, _criteres_mis_a_jour(evenement)
    if isinstance(evenement, Sondage):
        return NomEvenement.SONDAGE, _sondage(evenement)
    if isinstance(evenement, QuestionSuggeree):
        return NomEvenement.QUESTION_SUGGEREE, _question_suggeree(evenement)
    if isinstance(evenement, ProduitsTrouves):
        return NomEvenement.PRODUITS, _produits_trouves(evenement)
    if isinstance(evenement, QuestionPosee):
        return NomEvenement.QUESTION, {
            "question": evenement.question,
            "champ_vise": evenement.champ_vise,
        }
    if isinstance(evenement, Texte):
        return NomEvenement.MESSAGE, {"texte": evenement.texte}
    if isinstance(evenement, TexteRejete):
        return NomEvenement.TEXTE_REJETE, _texte_rejete(evenement)
    if isinstance(evenement, Repli):
        # ⚠️ Ni `iterations` ni `outils_appeles` : ce sont des métriques de boucle, pas
        # des faits du dialogue (arbitrage G). L'étape 12 les compte dans les logs.
        return NomEvenement.REPLI, {
            "message": evenement.message,
            "motif": evenement.motif.value,
            "libelle_motif": LIBELLES_MOTIF_DE_REPLI[evenement.motif],
        }
    assert_never(evenement)


def _criteres_mis_a_jour(evenement: CriteresMisAJour) -> Donnees:
    """Le panneau « voici ce que j'ai compris » de §3.12, à la source.

    `libelle_categorie` n'est porté que par cet événement, et c'est suffisant : la
    catégorie n'entre dans une session que par `record_criteria`, donc aucun autre
    événement ne peut arriver avant lui. Le répéter partout ferait porter au fil six
    copies d'un mot qui vient d'une table de six entrées.
    """
    return {
        "categorie": evenement.categorie,
        "libelle_categorie": LIBELLES_CATEGORIE[evenement.categorie],
        "criteres": criteres_serialises(evenement.categorie, evenement.criteres),
        "budget_usd": _montant(evenement.budget_usd),
        **optimisation_serialisee(evenement.optimisation),
        "mouvements_refuses": [
            {**_champ(evenement.categorie, refuse.champ), **_mouvement(refuse)}
            for refuse in evenement.mouvements_refuses
        ],
    }


def criteres_serialises(categorie: Categorie, criteres: Sequence[Critere]) -> list[Donnees]:
    """Les critères tels qu'ils voyagent. **Le seul endroit où ces clés portent un nom.**

    Partagé avec `GET /sessions/{id}`, qui rend le même état sous la même forme : deux
    écritures de la même structure finiraient par diverger, et le front devrait alors
    savoir laquelle il lit.
    """
    return [
        {
            **_champ(categorie, critere.champ),
            "operateur": critere.operateur.value,
            "valeur": valeur_en_texte(critere.valeur),
            "importance": critere.importance.value,
        }
        for critere in criteres
    ]


def _mouvement(refuse: MouvementRefuse) -> Donnees:
    """Ce qui n'a pas pu s'appliquer, et pourquoi. **Ce n'est pas une erreur.**

    C'est ce qui permet à l'étape 11 d'afficher « je garde 144 Hz » plutôt que de laisser
    le client croire qu'il a été entendu.
    """
    return {"operateur": refuse.operateur.value, "motif": refuse.motif}


def _sondage(evenement: Sondage) -> Donnees:
    """Des agrégats, et structurellement aucun produit — comme l'outil dont il vient."""
    return {
        "categorie": evenement.categorie,
        "dans_le_budget": evenement.dans_le_budget,
        "dans_la_zone_de_tolerance": evenement.dans_la_zone_de_tolerance,
        "fourchette_prix": _fourchette(evenement.fourchette_prix),
        "champs": [_distribution(champ) for champ in evenement.champs],
    }


def _question_suggeree(evenement: QuestionSuggeree) -> Donnees:
    """Le champ de plus fort gain d'information. **Une suggestion, pas un ordre** (§3.8)."""
    return {
        "categorie": evenement.categorie,
        "candidats": evenement.candidats,
        "budget": _besoin_de_budget(evenement.budget),
        "champ": _champ_discriminant(evenement.champ),
    }


def _produits_trouves(evenement: ProduitsTrouves) -> Donnees:
    """La seule sortie du projet qui porte des produits — **et pas sa trace** (arbitrage G).

    `produits` et `au_dessus_du_budget` restent séparés, comme §3.10 l'exige : les
    confondre ici rouvrirait au fil ce que le moteur a fermé.
    """
    resultat = evenement.resultat
    return {
        "categorie": resultat.categorie,
        "candidats_trouves": resultat.candidats_trouves,
        "produits": [_produit(resultat.categorie, produit) for produit in resultat.produits],
        "au_dessus_du_budget": [
            {
                "produit": _produit(resultat.categorie, hors.produit),
                "ecart_usd": _montant(hors.ecart_usd),
            }
            for hors in resultat.au_dessus_du_budget
        ],
        "diagnostic": _diagnostic(resultat.diagnostic),
    }


def _texte_rejete(evenement: TexteRejete) -> Donnees:
    """La preuve visible que le validateur existe (arbitrage G).

    `origine` sépare la prose de la question d'`ask_clarification` : c'est ce qui permettra
    à l'étape 12 de dire *où* le modèle hallucine, et le fil serait le mauvais endroit
    pour perdre cette distinction.
    """
    return {
        "origine": evenement.origine.value,
        "tentative": evenement.tentative,
        # ⚠️ **Sans lui, le même événement décrirait deux situations opposées.** En mode
        # bloquant le texte n'a jamais atteint le client ; en `avertissement` il l'a atteint,
        # et le grief n'est qu'un signalement. Le tableau de bord marque « jamais lu par le
        # client » — il lui faut de quoi ne pas le dire à tort.
        "bloquant": evenement.bloquant,
        "griefs": [_grief(grief) for grief in evenement.griefs],
    }


# --------------------------------------------------------------------------- #
# Les briques partagées
# --------------------------------------------------------------------------- #


def optimisation_serialisee(optimisation: Optimisation) -> Donnees:
    """`{optimisation, libelle_optimisation}` — le jeton **et** son français (arbitrage H).

    Partagé avec `GET /sessions/{id}`, qui rend le même état sous la même forme, pour la
    même raison que `criteres_serialises()` : deux écritures de la même structure finiraient
    par diverger, et le front devrait alors savoir laquelle il lit.

    Le jeton reste : c'est un identifiant fermé, que le front compare (`!== "aucune"`) et
    n'affiche pas. Le libellé est ce qu'il affiche. Rendre l'un sans l'autre obligerait le
    front soit à comparer une phrase française, soit à la fabriquer lui-même.
    """
    return {
        "optimisation": optimisation.value,
        "libelle_optimisation": LIBELLES_OPTIMISATION[optimisation],
    }


def _motif(motif: Motif) -> Donnees:
    """`{motif, libelle_motif}` — le motif de zéro résultat et sa phrase.

    C'est le **critère d'acceptation nº6** qui se joue ici : `critere_trop_strict` affiché
    tel quel à un client ne serait pas « le cas zéro résultat rendu lisible ». Le libellé
    vient de `LIBELLES_MOTIF`, à côté de l'énumération, jamais d'une table du front.
    """
    return {"motif": motif.value, "libelle_motif": LIBELLES_MOTIF[motif]}


def _champ(categorie: Categorie, champ: str) -> Donnees:
    """`{champ, libelle_fr, unite}` — le français vient du **registre** (arbitrage H).

    Le repli sur le nom technique n'arrive pas en pratique : `fusionner()` refuse un champ
    absent du registre, donc aucun critère ne peut en porter un. Il est écrit quand même
    parce que l'alternative est un `KeyError` **au milieu d'un flux** — c'est-à-dire un
    tour perdu, appel API compris, pour un mot d'affichage. Rendre le nom anglais du champ
    dégrade la lisibilité ; lever détruit la conversation.
    """
    attribut = ATTRIBUTS[categorie].get(champ)
    return {
        "champ": champ,
        "libelle_fr": champ if attribut is None else attribut.libelle_fr,
        "unite": None if attribut is None else attribut.unite,
    }


def _produit(categorie: Categorie, produit: ProduitEnBase) -> Donnees:
    """Un produit tel qu'une carte de l'étape 11 l'affiche."""
    return {
        "id": produit.id,
        "nom": produit.nom,
        "marque": produit.marque,
        "prix_usd": _montant(produit.prix_usd),
        "disponible": produit.disponible,
        "specs": _specs(categorie, produit),
    }


def _specs(categorie: Categorie, produit: ProduitEnBase) -> list[Donnees]:
    """Les specs **dérivées du registre**, pas le JSONB brut.

    Le parcours part du registre et non du produit, ce qui donne trois propriétés d'un
    coup, sans aucune règle à écrire :

    * les champs **inconnus du registre sont ignorés** — ils n'ont ni libellé ni unité, et
      les inventer serait exactement ce que §3.4ter interdit ;
    * les colonnes communes (`id`, `nom`, `marque`, `prix_usd`, `categorie`) sortent
      d'elles-mêmes, puisque `dans_les_specs` les distingue déjà pour le dépôt ;
    * l'**ordre est celui du registre**, donc stable d'un produit à l'autre et d'une
      exécution à l'autre. Un ordre venu du JSONB dépendrait de l'insertion.

    Les champs de rôle `affichage` (`color`) y sont : ils ne filtrent ni ne scorent, mais
    ils se montrent — c'est leur définition.

    Une valeur absente ne produit **pas** de ligne. Un champ affiché à vide n'est pas une
    information sur le produit, et un `null` dans une carte se lit comme un défaut de
    données. Ce que l'absence dit du produit — un SSD n'a pas de vitesse de rotation — est
    porté par le diagnostic du moteur, qui sait le dire en phrase.
    """
    lignes: list[Donnees] = []
    for champ, attribut in ATTRIBUTS[categorie].items():
        if not attribut.dans_les_specs:
            continue
        valeur = valeur_du_produit(produit, attribut)
        if valeur is None:
            continue
        lignes.append({**_champ(categorie, champ), "valeur": _valeur(valeur)})
    return lignes


def _diagnostic(diagnostic: Diagnostic | None) -> Donnees | None:
    """Le zéro résultat, dit et proposé — critère d'acceptation nº6. `None` sinon."""
    if diagnostic is None:
        return None
    return {
        **_motif(diagnostic.motif),
        "propositions": [_proposition(proposition) for proposition in diagnostic.propositions],
    }


def _proposition(proposition: Proposition) -> Donnees:
    """Un assouplissement possible. **Formulé, jamais appliqué.**

    `libelle_fr` et `unite` sont recopiés de la proposition : le moteur les a déjà pris au
    registre, et les re-résoudre ici serait une seconde occasion de diverger.
    """
    return {
        "champ": proposition.champ,
        "libelle_fr": proposition.libelle_fr,
        "unite": proposition.unite,
        "valeur_atteignable": _montant(proposition.valeur_atteignable),
        "produits_rouverts": proposition.produits_rouverts,
        **_motif(proposition.motif),
        "dernier_recours": proposition.dernier_recours,
    }


def _distribution(distribution: Distribution) -> Donnees:
    """La `Distribution` entière. **Ce n'est pas la trace** : c'est ce que le catalogue
    contient, et c'est ce qui permet au panneau de le dire.

    `total_distinct` et `tronque` voyagent toujours, y compris quand il n'y a rien à
    tronquer : un champ optionnel n'existe qu'à moitié, et celui qui le lit finit par
    supposer sa valeur.
    """
    return {
        "champ": distribution.champ,
        "libelle_fr": distribution.libelle_fr,
        "unite": distribution.unite,
        "valeurs": [
            {"valeur": comptee.valeur, "effectif": comptee.effectif}
            for comptee in distribution.valeurs
        ],
        "total_distinct": distribution.total_distinct,
        "tronque": distribution.tronque,
        "renseignes": distribution.renseignes,
        "total": distribution.total,
    }


def _champ_discriminant(champ: ChampDiscriminant | None) -> Donnees | None:
    """`None` quand plus rien ne discrimine : **c'est une réponse, pas un incident.**"""
    if champ is None:
        return None
    return {
        "champ": champ.champ,
        "libelle_fr": champ.libelle_fr,
        "unite": champ.unite,
        "score": str(champ.score),
        "distribution": _distribution(champ.distribution),
    }


def _besoin_de_budget(besoin: BesoinDeBudget | None) -> Donnees | None:
    """Renseigné **seulement** si le budget est inconnu — et il passe alors devant."""
    if besoin is None:
        return None
    return {"fourchette_prix": _fourchette(besoin.fourchette_prix)}


def _fourchette(bornes: BornesPrix | None) -> Donnees | None:
    """`null` est une **information** — le sous-catalogue est vide — pas un zéro.

    C'est écrit dans `BornesPrix` : deux extrêmes sont deux produits qui existent, et leur
    absence dit qu'il n'y a rien à décrire. Un `{plus_bas: 0, plus_haut: 0}` dirait qu'il
    existe des produits gratuits.
    """
    if bornes is None:
        return None
    return {"plus_bas": _montant(bornes.plus_bas), "plus_haut": _montant(bornes.plus_haut)}


def _grief(grief: Grief) -> Donnees:
    """Le code, l'extrait fautif, la correction demandée. Rien du texte refusé lui-même."""
    return {
        "code": grief.code.value,
        "extrait": grief.extrait,
        "correction": grief.correction,
        # Instrumentation de la tolérance d'arrondi **écartée** (étape 21, jalon 2). Il ne
        # change aucune décision ; il passe par le fil pour atterrir dans `evenements_tour`,
        # où une campagne pourra le compter. Voir `Grief.arrondi`.
        "arrondi": grief.arrondi,
    }


def _montant(valeur: Decimal | None) -> str | None:
    """Tout `Decimal` sort en **chaîne**, comme dans `en_tool_result()`.

    Un flottant JSON perdrait des décimales sur un prix, et le validateur de l'étape 9
    compare des caractères : afficher `108.0` là où la base dit `108.00` ferait mentir la
    page sur une valeur que le code a justement pris soin de ne pas approximer.
    """
    return None if valeur is None else str(valeur)


def _valeur(valeur: object) -> Any:  # noqa: ANN401
    """La valeur d'une spec, normalisée : seuls les `Decimal` changent de type.

    Les booléens et les entiers gardent le leur — le front les affiche, il ne les compare
    à rien. Le test de `bool` vient **avant** celui d'`int` : en Python, `True` est un
    entier, et l'ordre inverse enverrait `1` là où le catalogue dit « avec micro ».
    """
    if isinstance(valeur, Decimal):
        return str(valeur)
    if isinstance(valeur, bool | int | str):
        return valeur
    return str(valeur)
