"""Le cadrage du fil, tel que `web/flux.js` le suppose. **Purs : ni base, ni conteneur, ni clé.**

L'étape 11 branche un parseur écrit à la main sur `fetch` + `ReadableStream` — c'est le
coût assumé de l'arbitrage B de l'étape 10, `EventSource` ne sachant faire que du GET. Ce
parseur repose sur **trois propriétés du producteur**, et ce sont exactement les trois qui
peuvent se dégrader en silence côté serveur, sans qu'aucun test existant ne le voie :

1. une trame est une ligne `event:`, une ligne `data:`, une ligne vide — **sur tous** les
   types d'événements ;
2. aucun `data:` ne contient de saut de ligne brut, y compris pour une prose multi-lignes
   ou un extrait de grief — c'est ce qui autorise le découpage sur `\\n\\n` ;
3. le flux se recompose sous un découpage **arbitraire** des octets.

### ⚠️ Ce que ces tests ne couvrent pas, et qui est écrit au §7

Ils prouvent que le **serveur émet** des trames bien formées et recomposables. Ils ne
prouvent **pas** que `flux.js` les recompose : un parseur JavaScript qui oublierait sa
queue passerait toute cette suite au vert, et le symptôme — un événement perdu de temps en
temps, donc une carte produit qui manque une fois sur dix — ne se verrait qu'en
démonstration.

L'atténuation est la **concentration**, pas la couverture : l'algorithme est écrit **une
fois**, ici, en Python testé, et `flux.js` le transcrit ligne pour ligne dans un module
sans DOM. C'est une atténuation, et le dire ainsi vaut mieux qu'un test Playwright qui
donnerait l'illusion de la couverture pour le prix d'une suite qui cesse de tourner « sans
base, sans conteneur, sans clé ».

### Le parseur implémente le cadrage **du projet**, pas la spécification SSE

`trame()` émet exactement `event:`, un `data:` unique, une ligne vide. Le parseur de
référence ci-dessous refuse tout le reste — multi-`data:`, `id:`, `retry:`, commentaires
`:`. Un parseur générique serait plus long, non exercé, et faussement rassurant : il
prétendrait accepter des formes que ce producteur ne produit pas et que rien ne
vérifierait. La limite est donc **écrite**, ce qui la rend révisable le jour où le
producteur changerait.
"""

import codecs
import json
import re
from collections.abc import Iterable, Iterator
from decimal import Decimal

import pytest
from faux_client import FauxClient, appel_outil, message, texte
from scenarios import ECRAN_144, jouer

from outils_de_test import TOLERANCE, DepotEnMemoire, ecrans
from produits_de_test import fabriquer
from raiyon.agent.evenements import (
    AvisConsultes,
    CriteresMisAJour,
    MotifDeRepli,
    ProduitsTrouves,
    QuestionPosee,
    QuestionSuggeree,
    Repli,
    Sondage,
    Texte,
    TexteRejete,
)
from raiyon.api.serialisation import (
    CodeErreur,
    NomEvenement,
    trame_de,
    trame_de_fin,
    trame_derreur,
)
from raiyon.matching.criteres import Critere, Importance, Operateur, Optimisation
from raiyon.matching.depot import BornesPrix
from raiyon.matching.moteur import ProduitHorsBudget, ResultatMatching
from raiyon.matching.relachement import Diagnostic, Motif, Proposition
from raiyon.matching.sondage import ChampDiscriminant, Distribution, ValeurComptee
from raiyon.tools.repartiteur import ContexteOutils
from raiyon.tools.schema_outils import (
    NOM_ENREGISTRER,
    NOM_QUESTION,
    NOM_RECHERCHER,
    NOM_SONDER,
    schema_des_outils,
)
from raiyon.validateur.regles import CodeGrief, Grief
from raiyon.validateur.validateur import OrigineRejet

# --------------------------------------------------------------------------- #
# Le parseur de référence — **la spécification que `web/flux.js` transcrit**
# --------------------------------------------------------------------------- #

SEPARATEUR = "\n\n"
"""Ce qui sépare deux trames. Le seul délimiteur du cadrage."""


def recomposer(morceaux: Iterable[bytes]) -> list[tuple[str, dict]]:
    """Des morceaux réseau vers des événements typés. **Accumuler, découper, garder la queue.**

    ⚠️ **Cet algorithme est la spécification de `web/flux.js`.** Les deux se lisent en
    parallèle, et les deux pièges qu'il ferme sont ceux qui ne se voient pas en relecture :

    * **le décodage est incrémental.** `codecs.getincrementaldecoder("utf-8")` est ici ce
      que `new TextDecoder("utf-8")` avec `{ stream: true }` est là-bas. Sans lui, un
      caractère multi-octets coupé entre deux morceaux produit un `�` — et la prose est en
      français, donc les accents sont partout et le défaut est **intermittent** ;
    * **la queue est conservée.** Les morceaux d'un `ReadableStream` ne s'alignent pas sur
      les trames. On traite les segments complets et on garde le dernier morceau pour le
      tour suivant. C'est l'erreur classique du SSE écrit à la main, et son symptôme est un
      événement perdu de temps en temps, pas un plantage.

    Le flux se termine par un séparateur, donc la queue est **vide** à la fin : un reste
    non vide signifie une trame tronquée, c'est-à-dire une connexion coupée en plein
    milieu. Le parseur le dit plutôt que de la jeter en silence.
    """
    decodeur = codecs.getincrementaldecoder("utf-8")()
    tampon = ""
    evenements: list[tuple[str, dict]] = []
    for morceau in morceaux:
        tampon += decodeur.decode(morceau)
        *complets, tampon = tampon.split(SEPARATEUR)
        evenements.extend(lire_trame(segment) for segment in complets)
    assert tampon == "", f"trame tronquée en fin de flux : {tampon!r}"
    return evenements


def lire_trame(segment: str) -> tuple[str, dict]:
    """`event: <nom>` puis `data: <JSON>`, et **rien d'autre** — le cadrage du projet.

    Deux lignes exactement. Le dépaquetage lève sur une troisième, ce qui est le
    comportement voulu : une trame que ce producteur ne peut pas avoir écrite doit
    s'arrêter ici, et non se propager sous une forme à demi lue.
    """
    ligne_nom, ligne_donnees = segment.split("\n")
    assert ligne_nom.startswith("event: "), ligne_nom
    assert ligne_donnees.startswith("data: "), ligne_donnees
    return ligne_nom.removeprefix("event: "), json.loads(ligne_donnees.removeprefix("data: "))


def par_morceaux(octets: bytes, taille: int) -> Iterator[bytes]:
    """Le flux coupé tous les `taille` octets — **sans égard pour les trames**, exactement
    comme un `ReadableStream` le rend."""
    for debut in range(0, len(octets), taille):
        yield octets[debut : debut + taille]


TAILLES = [1, 7, 64, 4096]
"""1 coupe **à l'intérieur** d'un caractère accentué ; 7 tombe rarement sur une frontière ;
64 coupe au milieu d'une trame ; 4096 en rend plusieurs d'un coup. Les quatre régimes qu'un
réseau produit."""


# --------------------------------------------------------------------------- #
# Un de chaque — les dix noms du fil, avec ce qui peut casser un cadrage
# --------------------------------------------------------------------------- #

PROSE_MULTILIGNE = (
    "Voici trois écrans à 144 Hz :\n"
    "1. **MSI MAG 255XFV** — le meilleur rapport qualité/prix\r\n"
    "2. **BenQ MOBIUZ EX240N**\r"
    "3. **AOPEN UM.UW1AA.P01**\n\n"
    "Dites-moi si la dalle vous importe."
)
"""Les trois formes de retour à la ligne, plus un `\\n\\n` **dans la prose elle-même** :
c'est le pire cas du découpage sur `\\n\\n`, et il ne se voit qu'ici."""

DISTRIBUTION_DALLE = Distribution(
    champ="panel_type",
    libelle_fr="type de dalle",
    unite=None,
    valeurs=(ValeurComptee("IPS", 19), ValeurComptee("VA", 8)),
    total_distinct=3,
    tronque=True,
    renseignes=27,
    total=32,
)

ECRAN = fabriquer("monitor", 1, prix="129.99", marque="MSI")


def un_de_chaque() -> list[str]:
    """Une trame de chacun des onze noms — les neuf du domaine, `error` et `done`.

    Elles sont construites à la main plutôt que jouées : un tour réel ne produit pas
    `fallback` **et** `message`, ni `question` **et** `products_found`. Les propriétés 1 et
    2 portent sur **le cadrage de chaque type**, pas sur un enchaînement, et un scénario
    qui les produirait tous n'existe pas.
    """
    evenements = [
        CriteresMisAJour(
            categorie="monitor",
            criteres=(
                Critere(
                    champ="refresh_rate",
                    operateur=Operateur.AU_MOINS,
                    valeur=Decimal("144"),
                    importance=Importance.BLOQUANT,
                ),
            ),
            budget_usd=Decimal("400.00"),
            optimisation=Optimisation.AUCUNE,
            mouvements_refuses=(),
        ),
        Sondage(
            categorie="monitor",
            dans_le_budget=32,
            dans_la_zone_de_tolerance=4,
            fourchette_prix=BornesPrix(plus_bas=Decimal("108.00"), plus_haut=Decimal("399.99")),
            champs=(DISTRIBUTION_DALLE,),
        ),
        QuestionSuggeree(
            categorie="monitor",
            candidats=32,
            budget=None,
            champ=ChampDiscriminant(
                champ="panel_type",
                libelle_fr="type de dalle",
                unite=None,
                score=Decimal("0.73"),
                distribution=DISTRIBUTION_DALLE,
            ),
        ),
        ProduitsTrouves(
            ResultatMatching(
                categorie="monitor",
                candidats_trouves=32,
                produits=(ECRAN,),
                au_dessus_du_budget=(
                    ProduitHorsBudget(
                        produit=fabriquer("monitor", 2, prix="417.14", marque="Samsung"),
                        ecart_usd=Decimal("17.14"),
                    ),
                ),
                traces=(),
                ecartes_faute_de_donnee={},
                diagnostic=Diagnostic(
                    motif=Motif.CRITERE_TROP_STRICT,
                    propositions=(
                        Proposition(
                            champ="refresh_rate",
                            libelle_fr="fréquence de rafraîchissement",
                            unite="Hz",
                            importance=Importance.BLOQUANT,
                            operateur=Operateur.AU_MOINS,
                            valeur_demandee=Decimal("144"),
                            valeur_atteignable=Decimal("120"),
                            produits_rouverts=7,
                            motif=Motif.CRITERE_TROP_STRICT,
                            dernier_recours=False,
                        ),
                    ),
                ),
            )
        ),
        QuestionPosee(question="Vous jouez plutôt en 1440p ou en 4K ?", champ_vise="largeur_px"),
        # ⚠️ Aucun titre, aucun extrait, aucune URL : cet événement décrit **l'acte**
        # de chercher, jamais ce que les pages disent. Voir `AvisConsultes`.
        AvisConsultes(
            requete_normalisee="asrock avis pg27frs1a",
            nombre=2,
            depuis_le_cache=True,
            etat_cache="trouve",
            latence_ms=0,
        ),
        Texte(PROSE_MULTILIGNE),
        TexteRejete(
            texte="Celui-ci est à 230 $.",
            griefs=(
                Grief(
                    CodeGrief.MONTANT_NON_FOURNI,
                    "230 $",
                    # ⚠️ Un grief porte un **extrait du texte refusé** : il peut donc
                    # contenir tout ce que le modèle a écrit, sauts de ligne compris.
                    "aucun outil n'a rendu ce montant.\nLe reprendre d'un résultat,\r\nou ne "
                    "pas le citer.",
                ),
            ),
            tentative=1,
            origine=OrigineRejet.TEXTE,
        ),
        Repli(
            "Je m'y perds un peu — reformulez ?", 8, ("search_products",), MotifDeRepli.VALIDATION
        ),
    ]
    return [
        *(trame_de(evenement) for evenement in evenements),
        trame_derreur(CodeErreur.INTERNE, "Une erreur interne a interrompu ce tour."),
        trame_de_fin(),
    ]


# --------------------------------------------------------------------------- #
# 1 — Une trame est trois lignes, sur tous les types sans exception
# --------------------------------------------------------------------------- #

CADRAGE = re.compile(r"\Aevent: (?P<nom>[a-z_]+)\ndata: (?P<donnees>\{.*\})\n\n\Z", re.DOTALL)
"""Le cadrage entier, en une expression. `re.DOTALL` est délibéré : il **autoriserait** un
saut de ligne dans les données, et c'est le test nº2 qui le refuse. Les deux propriétés
restent ainsi séparées, et un échec dit laquelle des deux a cédé."""


@pytest.mark.parametrize("rendu", un_de_chaque(), ids=lambda rendu: rendu.split("\n")[0])
def test_une_trame_est_un_event_un_data_et_une_ligne_vide(rendu):
    """La propriété que le découpage sur `\\n\\n` suppose, vérifiée type par type.

    Un `event:` sans son `data:` — pour une charge utile vide, par exemple — ferait un
    parseur qui décale d'une trame et attribue chaque charge utile au nom précédent. Le
    symptôme serait un panneau rempli avec les produits, ce qui n'est pas le genre de
    défaut qu'on diagnostique vite.
    """
    correspondance = CADRAGE.match(rendu)

    assert correspondance is not None, f"cadrage rompu : {rendu!r}"
    assert correspondance["nom"] in {nom.value for nom in NomEvenement}
    assert isinstance(json.loads(correspondance["donnees"]), dict)


def test_les_onze_noms_du_fil_sont_couverts():
    """Le décor lui-même est vérifié : un douzième nom ajouté à `NomEvenement` sans
    trame d'exemple ferait passer les tests ci-dessus **sans jamais l'exercer**.

    ⚠️ Dix jusqu'à l'étape 27 ; `reviews_consulted` est le onzième. Ce test a échoué à
    son arrivée — c'est son travail, et c'est pourquoi le compte est dans son nom.
    """
    noms = {rendu.split("\n")[0].removeprefix("event: ") for rendu in un_de_chaque()}

    assert noms == {nom.value for nom in NomEvenement}


# --------------------------------------------------------------------------- #
# 2 — Aucun `data:` ne porte de saut de ligne brut
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("rendu", un_de_chaque(), ids=lambda rendu: rendu.split("\n")[0])
def test_aucune_charge_utile_ne_contient_de_saut_de_ligne_brut(rendu):
    """⚠️ **C'est ce qui autorise le découpage sur `\\n\\n`, et rien d'autre ne le garantit.**

    `json.dumps` échappe tout caractère de contrôle, donc la prose multi-lignes du modèle
    et l'extrait d'un grief — qui est un morceau de cette prose — tiennent sur une ligne.
    Un producteur qui passerait un jour à `indent=2` pour « déboguer plus facilement »
    casserait le flux sans qu'aucune erreur ne soit levée nulle part.
    """
    assert rendu.count("\n") == 3, "une trame porte exactement trois retours à la ligne"
    assert "\r" not in rendu, "un retour chariot brut coupe aussi une trame"


def test_une_prose_multiligne_traverse_le_cadrage_sans_perte():
    """Le pendant positif : le texte ressort **au caractère près**, `\\n\\n` compris."""
    (nom, donnees), *reste = recomposer([trame_de(Texte(PROSE_MULTILIGNE)).encode()])

    assert reste == []
    assert nom == "message"
    assert donnees["texte"] == PROSE_MULTILIGNE


# --------------------------------------------------------------------------- #
# 3 — Le flux se recompose sous un découpage arbitraire
# --------------------------------------------------------------------------- #


def tour_complet() -> list[str]:
    """Un tour joué avec le faux client de l'étape 8, **sans base ni clé**.

    Trois appels d'outils dans un message, une recherche dans le suivant, un texte refusé
    par le validateur, puis le texte régénéré : le fil réel d'une conversation, avec sa
    reprise. C'est le flux que `flux.js` recevra, et non une suite d'événements assemblée à
    la main pour l'occasion.
    """
    depot = DepotEnMemoire()
    depot.produits = ecrans(3, refresh_rate=165)
    contexte = ContexteOutils(depot=depot, tour_client=1, tolerance=TOLERANCE)

    client = FauxClient(
        [
            message(
                appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1"),
                appel_outil(NOM_SONDER, {"champs": ["refresh_rate"]}, id="tu_2"),
                appel_outil(NOM_QUESTION, id="tu_3"),
            ),
            message(appel_outil(NOM_RECHERCHER, id="tu_4")),
            # ⚠️ 230 $ n'a été rendu par aucun outil : le validateur refuse ce texte, et
            # le fil porte le `text_rejected` avant le message régénéré.
            message(texte("Le premier est à 230 $, une affaire.")),
            message(texte(PROSE_REGENEREE)),
        ]
    )

    evenements, _ = jouer(client, contexte, schema_des_outils(), message_client="un écran 144 Hz")
    return [*(trame_de(evenement) for evenement in evenements), trame_de_fin()]


PROSE_REGENEREE = (
    "Trois écrans tiennent votre contrainte de 144 Hz :\n"
    "1. **Acme modele 1**\n"
    "2. **Acme modele 2**\n"
    "3. **Acme modele 3**\n"
    "Le premier suffit largement, à moins que la dalle ne compte pour vous."
)
"""Des accents, des sauts de ligne, du gras markdown — et **aucun montant**, pour que ce
test porte sur le cadrage et non sur les règles du validateur, qui ont leur propre suite."""


@pytest.mark.parametrize("taille", TAILLES)
def test_le_flux_se_recompose_sous_nimporte_quel_decoupage(taille):
    """**Le test qui décrit `flux.js`.** Le même tour, coupé en morceaux de `taille` octets,
    rend exactement la même suite d'événements que la concaténation entière.

    Un parseur qui jetterait sa queue perdrait une trame sur deux à `taille=7` et aucune à
    `taille=4096` : c'est la forme exacte du défaut « une carte produit qui manque une fois
    sur dix ».
    """
    flux = "".join(tour_complet()).encode()

    attendus = recomposer([flux])
    obtenus = recomposer(par_morceaux(flux, taille))

    assert obtenus == attendus


def test_un_accent_coupe_entre_deux_morceaux_ne_produit_pas_de_caractere_de_remplacement():
    """⚠️ **Le piège nº1 de l'étape, et il est intermittent.** « é » fait deux octets en
    UTF-8 ; coupé entre deux morceaux, un décodeur non incrémental rend `�` au milieu d'un
    mot. En français, ce n'est pas un cas limite — c'est une phrase sur deux.

    Le découpage à un octet garantit que **toutes** les frontières multi-octets sont
    coupées, ce qu'un découpage aléatoire ne garantirait pas.
    """
    flux = trame_de(Texte("fréquence de rafraîchissement — 144 Hz")).encode()

    (_, donnees), *_ = recomposer(par_morceaux(flux, 1))

    assert "�" not in donnees["texte"]
    assert donnees["texte"] == "fréquence de rafraîchissement — 144 Hz"


def test_une_trame_tronquee_est_signalee_et_non_jetee():
    """La queue non vide en fin de flux **est** une information : la connexion a coupé au
    milieu d'une trame. Un parseur qui la jetterait en silence ferait passer une
    conversation amputée pour une conversation finie — ce que `done` sert justement à
    distinguer."""
    tronque = trame_de(Texte("bonjour"))[:-1].encode()

    with pytest.raises(AssertionError, match="tronquée"):
        recomposer([tronque])


# --------------------------------------------------------------------------- #
# 4 — L'ordre d'un tour : les outils avant la prose, `done` en dernier
# --------------------------------------------------------------------------- #


def test_les_evenements_doutils_precedent_la_prose_et_done_est_dernier():
    """**C'est l'arbitrage A de l'étape 9 rendu observable**, et c'est ce que l'interface
    doit montrer plutôt que masquer : le panneau et les cartes se remplissent pendant que
    le validateur relit la réponse, et la prose arrive en dernier.

    `done` en fin de liste est ce qui autorise le front à réactiver la saisie sans réserve :
    il est émis **après** que le tour a été persisté, la boucle `for` du générateur ayant
    épuisé `session.tour()`, qui commite avant de rendre la main.
    """
    noms = [nom for nom, _ in recomposer(["".join(tour_complet()).encode()])]

    outils = {"criteria_updated", "catalog_probe", "suggested_question", "products_found"}

    assert noms[-1] == "done"
    assert noms.index("message") == len(noms) - 2
    assert set(noms[: noms.index("text_rejected")]) == outils, (
        "un événement d'outil est arrivé après la première tentative de prose"
    )
    assert noms.index("text_rejected") < noms.index("message"), (
        "le rejet du validateur précède le texte régénéré — c'est ce que montre le mode coulisses"
    )
