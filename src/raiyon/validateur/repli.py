"""Le niveau 3 de §3.11 : **le code rédige, le modèle n'écrit rien.** Texte sec, risque nul.

Quand une régénération n'a pas suffi, on cesse de demander au modèle. La recommandation
est écrite ici, en Python, à partir du dernier `ResultatMatching` du tour : nom
**verbatim**, `id`, prix formaté par le code (§2), et le « pourquoi » construit depuis
les `LigneTrace` de statut satisfait — c'est-à-dire depuis la trace d'explication que le
moteur produit, jamais depuis une inférence.

### Le texte produit ici passe le validateur, et c'est vérifié

`tests/validateur/test_repli.py` relit la sortie du repli avec `valider()`, contre le
contexte construit à partir du même résultat de recherche. Un repli qui ne passerait pas
son propre contrôle serait un aveu : le niveau 3 doit être le plus sûr des trois, pas
seulement le plus sec.

Trois conséquences de conception en découlent, et elles se lisent dans le code :

* **chaque produit tient sur une ligne avec son prix**, parce que la règle 2 raisonne
  par phrase — un prix dans une phrase qui ne nomme pas son produit serait un grief ;
* **un produit hors budget porte son écart sur la même ligne** (règle 4) ;
* **le prix ne figure jamais dans le « pourquoi »**, où il apparaîtrait sans son
  produit : `prix_usd` est écarté des lignes de trace reprises.

### Ce que ce module ne fait pas

Il ne remonte pas plus loin que le tour en cours. Le dernier `ResultatMatching` **typé**
d'une session vit dans le tour qui l'a produit ; le retrouver au tour suivant
demanderait de relire les `tool_result` persistés et d'en reconstruire les
`TraceProduit`, c'est-à-dire d'écrire un second lecteur du protocole à côté de
`contexte.py`. Sans recherche dans le tour, le repli est donc la phrase générique — et
c'est écrit au §5 étape 9 plutôt que découvert.
"""

from dataclasses import dataclass
from decimal import Decimal

from raiyon.catalogue.schemas import LIBELLES_CATEGORIE, Categorie, ProduitEnBase
from raiyon.matching.moteur import ProduitHorsBudget, ResultatMatching
from raiyon.matching.relachement import Proposition
from raiyon.matching.sondage import Distribution
from raiyon.matching.trace import LigneTrace, Statut, TraceProduit, ValeurTracee
from raiyon.validateur.extraction import canonique
from raiyon.validateur.validateur import OrigineRejet

PHRASE_GENERIQUE = (
    "Je préfère ne rien affirmer que je n'aie pas vérifié. "
    "Pouvez-vous me redire ce que vous cherchez, et pour quel usage ?"
)
"""Écrite en Python, jamais générée — même règle que `PHRASE_DE_REPLI`.

Elle en diffère par le motif, et le motif change la phrase : `max_iterations` dit « je
m'y perds », une validation échouée dit « je ne suis pas sûr de ce que j'allais vous
dire ». Deux phrases parce que deux situations, pas par goût de la variante.

~~Elle sert dans **deux** cas de validation : aucune recherche dans le tour, et une
**question** rejetée~~ — voir `rediger()`.

⚠️ **Elle n'en sert plus qu'un depuis le correctif de l'étape 12 : la question rejetée.**
Le premier cas — aucune recherche dans le tour — s'est révélé être presque toujours une
**question de domaine**, et lui répondre « pouvez-vous me redire ce que vous cherchez ? »
revient à demander au client de répéter une question qu'il a posée clairement. Voir
`PHRASE_DE_DOMAINE`. La ligne est barrée plutôt qu'effacée : les deux cas étaient
indistinguables tant qu'aucune conversation réelle n'avait montré à quoi ressemblait le
second."""

PHRASE_DE_DOMAINE = (
    "Je ne vous dirai que ce que le catalogue dit — je ne vais pas vous inventer une "
    "explication technique que je n'ai pas sous les yeux."
)
"""Le repli d'un texte refusé **quand aucun produit n'était en jeu** (correctif étape 12).

### D'où elle vient

Persona `joueur_serre`, `make eval-live`, tour 4 : « c'est quoi la différence entre une
dalle IPS et une dalle VA, au juste ? ». Le modèle a répondu depuis sa connaissance du
monde, le validateur a refusé deux fois, et le client a lu `PHRASE_GENERIQUE` — soit une
demande de répéter une question parfaitement claire, dans un produit qui s'appelle
« assistant conseil ».

### Ce qui ne se corrige **pas** ici, et pourquoi

**On ne desserre pas `regle_valeurs_unitaires`.** Une explication de domaine chiffrée est
une affirmation que le code ne peut pas vérifier, et le validateur n'a aucun moyen honnête
de distinguer « les dalles VA ont un meilleur contraste » d'un « les écrans de cette gamme
montent à 240 Hz » que rien n'a rendu. Une règle qui ne sait pas trancher ne doit pas faire
semblant — c'est la position tenue partout ailleurs dans ce dépôt.

C'est donc **la réponse** qui se corrige, pas la règle. Et cette phrase fait deux choses
que la générique ne faisait pas : elle dit ce que l'assistant peut et ne peut pas, et elle
**bascule sur ce qui est disponible** au lieu de renvoyer la question.

⚠️ Rien n'y est généré, et rien n'y est interpolé sans passer par un formateur de ce
module — même règle que le template de recommandation. Une phrase de repli qui inventerait
un chiffre serait le comble, et `tests/validateur/test_repli.py` la relit avec les cinq
règles pour cette raison."""

BASCULE_VERS_LE_CATALOGUE = (
    "En revanche, voici ce que le catalogue contient au rayon {libelle}, sur {nombre} produit(s) :"
)
"""L'amorce de la seconde moitié. `{nombre}` et `{libelle}` sont des faits fournis : le
comptage vient du sondage — donc de `contexte.agregats` — et le libellé du registre.

⚠️ **La formulation évite le pluriel exprès, et ce n'est pas du style.**
`LIBELLES_CATEGORIE` dit en toutes lettres « aucun article, aucun pluriel ici : c'est de
la donnée, pas du rendu ». Écrire « sur 5 écran » serait fautif, et ajouter une table de
pluriels ferait de ce module une **seconde source de français** pour les catégories —
exactement ce que §3.4ter refuse (« le français est du vocabulaire dérivé, jamais
recopié »). Le libellé reste donc au singulier, derrière « au rayon », et le compte porte
sur un nom générique avec la marque `(s)` que `_ligne_de_proposition()` emploie déjà."""

LIMITE_DE_CHAMPS = 3
LIMITE_DE_VALEURS = 4
"""Un repli reste court. Au-delà, ce n'est plus une réponse, c'est un export."""


@dataclass(frozen=True, slots=True)
class EtatDuCatalogue:
    """Ce qu'un sondage a rendu, **réduit à ce que la bascule a besoin de dire**.

    Un type à part plutôt que le `ResultatSondage` de `raiyon.tools` : celui-ci porte un
    `EtatSession`, et faire entrer l'état de session dans le rédacteur du repli rouvrirait
    exactement ce que `evenements.py` ferme — « chaque événement déclare ses champs
    explicitement plutôt que d'emballer le `ResultatOutil` dont il vient ». Accessoirement,
    `raiyon.validateur` n'a alors rien à importer de `raiyon.tools`.
    """

    categorie: Categorie
    candidats: int
    champs: tuple[Distribution, ...]


CHAMP_DU_PRIX = "prix_usd"
"""Écarté du « pourquoi » : le prix est déjà sur la ligne du produit, et l'y répéter le
mettrait dans une phrase qui ne nomme aucun produit — la règle 2 y verrait un montant
non attribuable."""

LIMITE_DE_LIGNES = 3
"""Trois raisons par produit. Au-delà, ce n'est plus un « pourquoi », c'est un tableau
de specs — et §1 demande un conseil."""


def rediger(
    resultat: ResultatMatching | None,
    origine: OrigineRejet = OrigineRejet.TEXTE,
    catalogue: EtatDuCatalogue | None = None,
) -> str:
    """La recommandation écrite par le code. Trois issues, et le choix se lit ci-dessous.

    Aucun `Decimal` n'est interpolé sans passer par un formateur de ce module : « les
    prix sont des `Decimal` typés que **le code** formate » (§2).

    ⚠️ **Une question rejetée ne se replie jamais sur le template**, même quand une
    recherche a eu lieu dans le tour. Répondre par un classement de produits à quelqu'un
    qu'on était en train d'interroger n'a aucun sens : le modèle cherchait une
    information, pas à conclure. Le choix se fait donc sur `origine`, pas seulement sur
    l'existence d'une recherche.

    **Les trois issues, dans l'ordre où elles sont testées** (correctif de l'étape 12) :

    1. `origine is QUESTION` → `PHRASE_GENERIQUE`. Inchangé.
    2. `resultat is None` → `PHRASE_DE_DOMAINE`, plus la bascule vers le catalogue si un
       sondage a eu lieu dans le tour. C'est le cas qui partageait la phrase générique et
       qui n'aurait jamais dû : aucun produit n'était en jeu, donc le modèle parlait du
       **domaine**, et « redites-moi ce que vous cherchez » répond à côté.
    3. sinon → le template, ou le zéro résultat avec son diagnostic.

    `catalogue` est facultatif : sans sondage dans le tour, la phrase de domaine dit ce
    qu'elle ne fera pas et s'arrête là. C'est moins bien, et c'est honnête.
    """
    if origine is OrigineRejet.QUESTION:
        return PHRASE_GENERIQUE
    if resultat is None:
        # Aucun produit n'était en jeu : le modèle affirmait quelque chose **sur le
        # domaine**, pas sur le catalogue. Lui demander de répéter sa question serait
        # répondre à côté (correctif de l'étape 12).
        return _domaine(catalogue)
    if not resultat.produits and not resultat.au_dessus_du_budget:
        return _rien_trouve(resultat)

    libelle = LIBELLES_CATEGORIE[resultat.categorie]
    lignes = [f"Voici ce que j'ai retenu, {libelle} par {libelle}, sans rien y ajouter :"]
    traces = {trace.produit_id: trace for trace in resultat.traces}

    for rang, produit in enumerate(resultat.produits, start=1):
        lignes.append("")
        lignes.append(_ligne_produit(rang, produit))
        pourquoi = _pourquoi(traces.get(produit.id))
        if pourquoi:
            lignes.append(f"   {pourquoi}")

    if resultat.au_dessus_du_budget:
        lignes.append("")
        lignes.append("Au-dessus de votre budget, et je le dis avant de les montrer :")
        for hors in resultat.au_dessus_du_budget:
            lignes.append(_ligne_hors_budget(hors))

    return "\n".join(lignes)


def _ligne_produit(rang: int, produit: ProduitEnBase) -> str:
    """`1) Samsung Odyssey G50A — monitor-… — 249.99 $`

    Le nom est recopié tel quel (§3.4ter). Le séparateur est un tiret cadratin et non un
    point : un point couperait la phrase avant le prix, et la règle 2 ne saurait plus à
    quel produit il appartient.
    """
    return f"{rang}) {produit.nom} — {produit.id} — {_montant(produit.prix_usd)}"


def _ligne_hors_budget(hors: ProduitHorsBudget) -> str:
    """Le produit, son prix, et **son écart exact** dans la même phrase (règle 4)."""
    return (
        f"- {hors.produit.nom} — {hors.produit.id} — {_montant(hors.produit.prix_usd)}, "
        f"soit {_montant(hors.ecart_usd)} de plus que votre budget"
    )


def _pourquoi(trace: TraceProduit | None) -> str:
    """Les critères satisfaits, tels que la trace les a constatés. Aucune phrase inventée.

    `Statut.MATCHE` seulement : un critère partiel ou raté n'est pas une raison de
    retenir un produit, et le repli n'est pas l'endroit où nuancer. Ce que le mode
    normal dit en plus — « celui-ci est à 120 Hz, pas 144 » — est précisément ce qu'un
    modèle sait écrire et qu'un gabarit ne sait pas.
    """
    if trace is None:
        return ""
    retenues = [
        _fait(ligne)
        for ligne in trace.lignes
        if ligne.statut is Statut.MATCHE
        and ligne.champ != CHAMP_DU_PRIX
        and ligne.valeur_produit is not None
    ]
    if not retenues:
        return ""
    return "retenu pour : " + ", ".join(retenues[:LIMITE_DE_LIGNES])


def _fait(ligne: LigneTrace) -> str:
    """`fréquence de rafraîchissement 165 Hz` — libellé du registre, valeur du produit.

    Le libellé et l'unité voyagent **avec** la ligne de trace, ce que `trace.py`
    annonçait à l'étape 6 comme étant précisément le besoin du repli de §3.11 niveau 3.
    """
    valeur = _valeur(ligne.valeur_produit)
    unite = f" {ligne.unite}" if ligne.unite else ""
    return f"{ligne.libelle_fr} {valeur}{unite}"


def _valeur(valeur: ValeurTracee) -> str:
    """Une valeur de trace en texte. Les booléens se disent, ils ne s'affichent pas."""
    if isinstance(valeur, bool):
        return "oui" if valeur else "non"
    if isinstance(valeur, Decimal):
        return canonique(valeur)
    return str(valeur)


def _domaine(catalogue: EtatDuCatalogue | None) -> str:
    """La phrase de domaine, et la bascule vers ce que le catalogue **contient**.

    ⚠️ **On ne devine pas « le champ dont le client parlait ».** Le déduire de la prose
    demanderait de lire le texte du modèle avec une heuristique, c'est-à-dire d'écrire un
    second validateur plus faible que le premier (étape 12, arbitrage E). On rend donc les
    distributions **que le sondage a effectivement produites**, dans l'ordre où l'outil les
    a rendues, tronquées. C'est ce que `probe_catalog` existe pour faire dire (§3.7), et
    c'est un fait fourni.

    Toutes les valeurs citées ici viennent de `contexte.valeurs_de_distribution` et tous
    les comptages de `contexte.agregats` : la phrase passe donc les cinq règles, et
    `tests/validateur/test_repli.py` le constate plutôt que de le supposer. Une ligne par
    champ, parce que le découpage en phrases du validateur coupe sur le saut de ligne —
    une valeur unitaire y est donc lue dans une phrase qui ne nomme aucun produit, ce que
    la règle 5 autorise et qui est exactement vrai.
    """
    if catalogue is None or not catalogue.champs:
        return PHRASE_DE_DOMAINE
    libelle = LIBELLES_CATEGORIE[catalogue.categorie]
    lignes = [
        PHRASE_DE_DOMAINE,
        "",
        BASCULE_VERS_LE_CATALOGUE.format(nombre=catalogue.candidats, libelle=libelle),
    ]
    lignes += [
        _ligne_de_distribution(distribution)
        for distribution in catalogue.champs[:LIMITE_DE_CHAMPS]
        if distribution.valeurs
    ]
    return "\n".join(lignes)


def _ligne_de_distribution(distribution: Distribution) -> str:
    """`- type de dalle : VA (32), IPS (13)` — libellé du registre, valeurs du sondage."""
    unite = f" {distribution.unite}" if distribution.unite else ""
    valeurs = ", ".join(
        f"{valeur.valeur}{unite} ({valeur.effectif})"
        for valeur in distribution.valeurs[:LIMITE_DE_VALEURS]
    )
    return f"- {distribution.libelle_fr} : {valeurs}"


def _rien_trouve(resultat: ResultatMatching) -> str:
    """Le zéro résultat, dit avec le diagnostic du moteur — critère d'acceptation nº6.

    Les propositions sont **formulées, jamais appliquées** : le repli laisse le client
    trancher, comme la section 10 du prompt système le demande au modèle.
    """
    entete = "Aucun produit ne satisfait tous vos critères en l'état."
    diagnostic = resultat.diagnostic
    if diagnostic is None:
        return entete
    return "\n".join([entete, *(_ligne_de_proposition(p) for p in diagnostic.propositions)])


def _ligne_de_proposition(proposition: Proposition) -> str:
    """`- en relâchant la fréquence de rafraîchissement à 120 Hz, 8 produit(s) reviennent`

    `valeur_atteignable` et `produits_rouverts` sont des agrégats fournis — le premier
    est une valeur réellement présente au catalogue, le second un comptage : la phrase
    produite ici passe donc le validateur, y compris sa valeur unitaire.
    """
    cible = ""
    if proposition.valeur_atteignable is not None:
        unite = f" {proposition.unite}" if proposition.unite else ""
        cible = f" à {canonique(proposition.valeur_atteignable)}{unite}"
    return (
        f"- en relâchant {proposition.libelle_fr}{cible}, "
        f"{proposition.produits_rouverts} produit(s) reviennent"
    )


def _montant(valeur: Decimal) -> str:
    """Les prix sont des `Decimal` typés que **le code** formate (§2)."""
    return f"{valeur:.2f} $"
