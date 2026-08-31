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

from decimal import Decimal

from raiyon.catalogue.schemas import LIBELLES_CATEGORIE, ProduitEnBase
from raiyon.matching.moteur import ProduitHorsBudget, ResultatMatching
from raiyon.matching.relachement import Proposition
from raiyon.matching.trace import LigneTrace, Statut, TraceProduit, ValeurTracee
from raiyon.validateur.extraction import canonique

PHRASE_SANS_RECHERCHE = (
    "Je préfère ne rien affirmer que je n'aie pas vérifié. "
    "Pouvez-vous me redire ce que vous cherchez, et pour quel usage ?"
)
"""Écrite en Python, jamais générée — même règle que `PHRASE_DE_REPLI`.

Elle en diffère par le motif, et le motif change la phrase : `max_iterations` dit « je
m'y perds », une validation échouée dit « je ne suis pas sûr de ce que j'allais vous
dire ». Deux phrases parce que deux situations, pas par goût de la variante."""

CHAMP_DU_PRIX = "prix_usd"
"""Écarté du « pourquoi » : le prix est déjà sur la ligne du produit, et l'y répéter le
mettrait dans une phrase qui ne nomme aucun produit — la règle 2 y verrait un montant
non attribuable."""

LIMITE_DE_LIGNES = 3
"""Trois raisons par produit. Au-delà, ce n'est plus un « pourquoi », c'est un tableau
de specs — et §1 demande un conseil."""


def rediger(resultat: ResultatMatching | None) -> str:
    """La recommandation écrite par le code. `None` → la phrase générique.

    Aucun `Decimal` n'est interpolé sans passer par un formateur de ce module : « les
    prix sont des `Decimal` typés que **le code** formate » (§2).
    """
    if resultat is None:
        return PHRASE_SANS_RECHERCHE
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
