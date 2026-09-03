"""La fonction de décision de la variante machine à états. **Pure, et hors ligne.**

> **Le modèle extrait, le code décide.**

`decider()` ne reçoit **jamais de prose** : ni le message du client, ni un texte du
modèle, ni une chaîne libre. Elle voit un `EtatSession` — ce que la couche outils a déjà
validé et fusionné — et le `ResultatOutil` de l'action précédente **du même tour**. Rien
d'autre.

⚠️ **C'est cette frontière qui achète tout le reste, et elle se perd d'un seul paramètre.**
Si `decider()` recevait le message du client, il lui faudrait un modèle pour le comprendre ;
elle cesserait d'être pure ; les tests de conduite du dialogue exigeraient une clé et un
tirage ; et la mesure nº8 s'évaporerait avec eux. Le jour où quelqu'un veut « juste faire
passer la phrase pour le cas où », c'est la ligne à lui montrer.

---

### Ce que §3.6 avait écrit, et que ce module rend faux

§3.6 a écarté la machine à états explicite, et il a nommé le prix du choix :

> « La testabilité par tests unitaires rapides disparaît en grande partie : il n'y a plus
> de fonction de décision pure à assertionner. »

C'est **exactement** cette fonction. Elle est le cœur de l'étape 15 et elle est
**indépendante du résultat de la campagne** : elle resterait vraie si la campagne n'avait
jamais lieu. Voir la mesure nº8 et sa réserve, plus bas.

### La forme d'un tour, et le plancher de coût qui en découle

Au jalon 2, un tour de la machine aura cette forme :

1. **extraction** — un appel modèle, qui remplit `enregistrer_criteres` ;
2. une boucle `decider()` → outil → `decider()` → … , **sans aucun appel modèle** ;
3. **rédaction ou question** — un second appel modèle, jamais les deux.

Le second appel est **soit** la recommandation **soit** la question. La machine a donc un
plancher mécanique de **2,00 appel par tour**, contre 2,36 mesuré sur la campagne `v2` de
l'agent (mesure nº7). C'est une prédiction posée d'avance, pas une observation : rien dans
ce module ne peut produire un troisième appel, puisque aucune action n'en déclenche un
en dehors des deux actions terminales.

### Ce que ce module ne décide pas, et n'a pas le droit de redécider

**Elle décide quel outil appeler ensuite. Elle n'applique aucun invariant que la couche
outils applique déjà.**

Le jeton de parole (§3.17), le clamp des critères, la garde « un tour, une catégorie »
d'`rechercher_produits`, la zone de tolérance du budget (§3.10) vivent dans `raiyon.tools`
et **y restent**. Les réimplémenter ici donnerait deux rédactions d'une même règle — la
maladie de la dette nº1 de l'étape 8, que le dépôt s'est engagé à ne plus reproduire.

⚠️ Un cas mérite d'être nommé parce qu'il se tient **par construction** plutôt que par une
garde : `enregistrer_criteres` n'est **pas** une action. La machine ne peut donc pas
« réessayer autrement » un mouvement que le jeton de parole vient de refuser (prompt §9) —
non parce qu'une règle l'interdit, mais parce qu'aucune action ne l'exprime. Dire le refus
au client reste le travail de la rédaction, qui voit `mouvements_refuses`.

### Ce qu'elle décide, en revanche : la conduite du tour de parole

| Règle | Source | Ce que `decider()` en fait |
|---|---|---|
| Budget = contrainte dure | §3.10, prompt §7 | jamais `Rechercher` tant que `budget_usd is None` |
| Donner avant de demander | §3.9, prompt §5 | `Sonder` puis `Suggerer` avant toute question |
| La question suggérée suggère | §3.8, prompt §6 | consulte `Suggerer`, puis arbitre |
| Une question à la fois | MVP, prompt §5 | `DemanderPrecision` est terminale, et unique |
| Zéro résultat | prompt §10 | après une recherche, on sonde puis on rédige — jamais 2 |
| Un composant à la fois | prompt §8, étape 7 | au plus un `Rechercher` par tour |
| Contexte de la rédaction | `GARDE_DE_CONTEXTE` | un `Sonder` dans tout tour à catégorie |

La première ligne est l'invariant que `Attente.AUCUNE_RECHERCHE_SANS_BUDGET` mesure sur
l'agent, et il couvre ses deux chemins : le budget jamais donné, et le budget effacé par un
changement de catégorie (étape 7, arbitrage D).

---

### Ce que cette machine fait moins bien que l'agent, écrit d'avance

`decider()` ne voit pas la prose, donc **elle ne sait pas qu'on lui a posé une question de
domaine**. Sur le tour 2 de `question_de_domaine` — « c'est quoi la différence entre une
dalle IPS et une VA ? » — l'état n'a pas changé, le budget est connu, et la machine
relance une recherche. Le modèle rédigera par-dessus, avec des produits en contexte.

C'est le coût que §3.6 annonçait sous le nom de « virages hors-script », et il est écrit
**avant** la campagne pour que le rapport ne le découvre pas comme une surprise.
"""

from dataclasses import dataclass

from raiyon.tools.etat import EtatSession
from raiyon.tools.outils import (
    ResultatOutil,
    ResultatPrecision,
    ResultatQuestion,
    ResultatRecherche,
    ResultatSondage,
)

CIBLE_BUDGET = "budget_usd"
"""Ce que `DemanderPrecision.champ` porte quand la question vise le budget.

Le budget **n'est pas un champ** : §3.10 lui donne une colonne (`sessions.budget_usd`) et
`CHAMPS_A_CHAMP_DEDIE` lui interdit d'entrer comme critère, précisément pour qu'il n'y ait
pas deux chemins vers la même contrainte. Le désigner par le nom de sa colonne est donc
exact, et il ne peut entrer en collision avec aucun attribut de catégorie.

*Alternative écartée — `champ: str | None`, où `None` voudrait dire « le budget ».* Un
`None` qui signifie quelque chose est une convention qu'il faut aller lire ailleurs ; le
jalon 2 la traduira de toute façon en `champ_vise=None` pour `demander_precision`, qui ne
connaît que les attributs de la catégorie. La traduction se fait à la frontière, pas dans
le type."""

RESERVE_MESURE_8 = (
    "Ces tests vérifient que la machine conduit le dialogue **comme on l'a écrit**. Ils ne "
    "vérifient\npas que la conduite est bonne, ni que le modèle qui rédige derrière "
    "respecte quoi que ce soit.\nLa machine rend testable **sa propre décision**, pas la "
    "conversation."
)
"""La réserve qui voyage avec la mesure nº8 **partout où le chiffre paraît**.

Écrite une seule fois et à côté de ce qu'elle qualifie, comme `RESERVE_ITERATIONS` au
jalon 0. Sans elle, « N contre 0 » est le double standard que l'étape 13 s'est reproché sur
la métrique nº3 : publier un écart flatteur sans l'étendue qui le relativise, sur la seule
mesure qui va dans le bon sens. C'est la façon de rater une mesure par ailleurs imparable —
le zéro d'en face, lui, ne se discute pas : il est écrit au §7 de `PROJET.md` depuis
l'étape 8, ligne « le faux client teste la boucle, pas le modèle »."""


GARDE_DE_CONTEXTE = (
    "La rédaction reçoit toujours les agrégats du sous-catalogue courant : la machine "
    "sonde\navant d'écrire, à chaque tour, que le tour finisse par une recommandation ou "
    "par une question."
)
"""La règle du jalon 2, et **ce n'est pas un correctif — c'est un avantage d'orchestration.**

Une machine à états peut **garantir** le contexte de sa rédaction. Un agent ne le peut pas :
décider de ses outils est précisément ce qui fait de lui un agent, et rien ne l'oblige à
sonder avant de parler. La garantie est donc une propriété que cette orchestration possède
et que l'autre ne possède pas, pas une rustine posée sur un défaut.

Elle se défend sans référence à aucune section du prompt : §5 veut ce contexte pour le
préambule d'une question, §4 et §12 veulent des chiffres fondés sur autre chose que la
mémoire du modèle. Ce sont trois raisons indépendantes, et la garde tomberait moins vite
qu'aucune d'elles.

⚠️ **Ce qu'elle empêche est précis, et coûteux si on le laisse arriver.** Sans agrégats en
contexte, un modèle à qui l'on demande la répartition d'un sous-catalogue la **fabrique** —
et une répartition fabriquée est faite d'**entiers nus**, sur lesquels aucune des cinq
règles du validateur ne mord (§7, ligne « un entier nu n'est vérifié par rien »). La faute
serait donc invisible, et elle le serait sur les tours où le client pose une question de
domaine.

⚠️ **La prédiction qui va avec, posée maintenant.** Plus d'agrégats en contexte, c'est plus
de chiffres disponibles dans la prose, donc **potentiellement plus de rejets du validateur**.
Si le taux de rejet de la machine monte, c'est le **premier** endroit où regarder — pas une
supériorité de l'agent.

Coût mécanique : un appel d'outil de plus par tour, et **aucun appel modèle**. Le plancher
de 2,00 appel par tour tient."""


class TourDejaClos(Exception):
    """`decider()` a été appelée après une action terminale : il n'y a plus de décision.

    `ResultatPrecision` clôt le tour (étape 7, amendement de §3.7). La boucle du jalon 2
    s'arrête donc dessus, et l'atteindre ici veut dire que la boucle a un défaut — pas que
    la machine hésite. Une exception nommée vaut mieux qu'une décision inventée : celle-ci
    déclencherait un troisième appel modèle et ferait mentir le plancher de 2,00.
    """


# --------------------------------------------------------------------------- #
# Les actions — une union fermée, et aucune ne porte de phrase
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Sonder:
    """Décrire ce qui reste, sans rendre un seul produit → `sonder_catalogue`."""

    champs: tuple[str, ...] = ()
    """Les champs à décrire. `()` = **tous les champs utilisables** de la catégorie, qui
    est le défaut de l'outil.

    ⚠️ **La machine ne le restreint jamais aujourd'hui, et c'est une décision.** Ne sonder
    que les champs que le client n'a pas encore contraints serait mieux — c'est ce que
    `question_suivante` fait pour son propre calcul, et sa docstring dit pourquoi
    (« redemander ce que le client vient de dire est le mode d'échec que §3.9 nomme
    l'interrogatoire »). Mais cette règle **appartient à la couche outils** : la réécrire
    ici en donnerait deux rédactions, ce que la section « ce qu'elle ne redécide pas »
    interdit. Le champ existe parce que l'action doit pouvoir nommer un sous-ensemble le
    jour où la couche outils exposera la règle ; il n'existe pas pour que ce module la
    devine."""


@dataclass(frozen=True, slots=True)
class Suggerer:
    """Demander à l'outil ce qui découperait le mieux ce qui reste → `question_suivante`.

    L'appeler n'engage à rien : §3.8 en fait une **suggestion**, et l'arbitrage est rendu
    par `_ce_quon_demande()` juste après.
    """


@dataclass(frozen=True, slots=True)
class Rechercher:
    """Chercher des produits → `rechercher_produits`. La seule action qui en rend."""


@dataclass(frozen=True, slots=True)
class DemanderPrecision:
    """Clore le tour sur une question → `demander_precision`.

    ⚠️ **Elle ne porte pas de texte, et c'est l'arbitrage qui empêche le questionnaire.**
    Le code décide **de quoi** on parle ; le modèle écrit **la phrase**. §3.8 refuse déjà
    la liste de priorité codée ; l'option « la relance est un gabarit sans appel modèle »
    a été écartée à l'arbitrage de l'étape 15, parce qu'une machine qui gagne le critère
    nº1 en cessant de parler a changé de produit — elle n'est plus comparable à l'agent,
    et la campagne ne mesurerait plus deux orchestrations mais deux produits.
    """

    champ: str
    """Un champ de la catégorie courante, ou `CIBLE_BUDGET`. Jamais `None`, jamais une
    phrase : une question dont on ne sait pas dire l'objet n'est pas une décision."""


@dataclass(frozen=True, slots=True)
class Rediger:
    """Clore le tour sur une réponse rédigée. Le modèle écrit ; le contexte est l'état et
    le dernier résultat d'outil."""


Action = Sonder | Suggerer | Rechercher | DemanderPrecision | Rediger
"""Les cinq actions, et **rien d'autre**. Deux d'entre elles closent le tour."""


# --------------------------------------------------------------------------- #
# La décision
# --------------------------------------------------------------------------- #


def decider(etat: EtatSession, dernier: ResultatOutil | None = None) -> Action:
    """L'action suivante du tour. **Pure : ni base, ni réseau, ni horloge, ni prose.**

    `dernier` est le résultat de l'action précédente **dans ce même tour**, et `None` au
    premier passage. Il n'est jamais terminal — voir `TourDejaClos`.

    Les gardes sont écrites dans l'ordre où elles priment, et cet ordre est lui-même une
    décision : la catégorie avant le budget, parce que sans catégorie il n'y a pas de
    sous-catalogue sur lequel un budget voudrait dire quelque chose.
    """
    if isinstance(dernier, ResultatPrecision):
        raise TourDejaClos(
            "`decider()` a été appelée après `demander_precision`, qui clôt le tour. "
            "La boucle du jalon 2 doit s'arrêter sur `terminal`, pas redemander une "
            "décision : celle-ci coûterait un troisième appel modèle."
        )

    # Règle — un composant à la fois, et il faut d'abord en avoir un (prompt §8,
    # arbitrage K de l'étape 6). Sans catégorie courante, les trois outils de catalogue
    # lèvent `CATEGORIE_ABSENTE` : il n'y a rien à sonder, rien à chercher, rien à
    # suggérer. C'est le cas `hors_catalogue`, dont l'attente est `AUCUN_PRODUIT_CITE` —
    # la bonne réponse est de le dire, pas d'appeler un outil qui refusera.
    if etat.categorie_courante is None:
        return Rediger()

    # Règle — zéro résultat (prompt §10) : on va au diagnostic et à l'assouplissement que
    # le moteur a calculés, **on ne relance pas une recherche**. Et comme la règle vaut
    # aussi quand la recherche a rendu des produits (prompt §11 : un à trois, classés),
    # elle s'écrit une fois pour les deux cas — ce qui donne au passage « une seule
    # recherche par message du client » **par construction** plutôt que par une garde.
    #
    # ⚠️ Depuis le jalon 2, la recherche est suivie d'un **sondage** et non de la rédaction
    # elle-même : c'est la garde de contexte, ci-dessous.
    if isinstance(dernier, ResultatRecherche):
        return Sonder()

    # Règle — la question suggérée est une suggestion (§3.8, prompt §6), **mais on ne
    # consulte pas un outil pour ignorer sa réponse**. Cette garde passe donc avant celle
    # du budget : la seule façon d'avoir un `ResultatQuestion` en main est d'avoir émis
    # `Suggerer`, et l'arbitrage se fait dans `_ce_quon_demande()`, pas en l'écrasant ici.
    if isinstance(dernier, ResultatQuestion):
        return _ce_quon_demande(dernier)

    # Règle — **la rédaction reçoit toujours les agrégats du sous-catalogue courant.**
    # Voir `GARDE_DE_CONTEXTE`. Sur le chemin sans budget, le sondage a déjà eu lieu deux
    # actions plus tôt et c'est `Suggerer` qui suit ; sur le chemin avec budget, c'est ici
    # que le tour bascule vers la rédaction, une fois le sondage rendu.
    if isinstance(dernier, ResultatSondage):
        return Rediger() if etat.budget_usd is not None else Suggerer()

    # Règle — le budget est une contrainte dure (§3.10, prompt §7). C'est l'invariant que
    # `Attente.AUCUNE_RECHERCHE_SANS_BUDGET` mesure, et il couvre les deux chemins : le
    # budget jamais donné, et le budget effacé par un changement de catégorie (étape 7,
    # arbitrage D). Tant qu'il manque, aucune recherche — donc aucun produit cité.
    if etat.budget_usd is not None:
        return Rechercher()

    # Le budget manque : le tour se terminera sur une question. Reste à **donner avant de
    # demander** (§3.9, prompt §5) — décrire ce qui reste, puis demander à l'outil de quoi
    # parler. `_ce_quon_demande()` recevra sa réponse au passage suivant.
    return Sonder()


def _ce_quon_demande(question: ResultatQuestion) -> Action:
    """L'arbitrage de §3.8 : **le champ rendu ne commande pas.**

    Trois cas, et le premier est celui qui fait l'arbitrage :

    1. l'outil signale que le **budget** manque → c'est la question, quel que soit le
       champ rendu à côté. §3.10 en fait une contrainte dure et la garde ci-dessus interdit
       toute recherche sans lui : demander un attribut à la place ferait passer un tour
       de plus avant la première valeur, pour une information qui ne débloque rien ;
    2. sinon, le **champ le plus discriminant**, tel quel — c'est le calcul de gain
       d'information de §3.8, et la machine n'a rien de mieux à lui opposer ;
    3. plus rien ne discrimine (`champ is None`) → il n'y a pas de question à poser. C'est
       **une réponse, pas un incident** (voir `ResultatQuestion.champ`) : on rédige.

    ⚠️ **Les cas 2 et 3 ne sont pas atteints par la boucle d'aujourd'hui**, et il vaut
    mieux l'écrire que le laisser découvrir : `question_suivante` ne renseigne `budget` que
    lorsque `etat.budget_usd is None`, qui est justement la seule condition sous laquelle
    `decider()` émet `Suggerer`. Ils sont écrits et testés parce que cette fonction est
    **totale sur le type qu'elle reçoit**, et non sur le sous-ensemble qu'une boucle lui
    envoie aujourd'hui — un `ResultatQuestion` obtenu sous budget connu y entre par
    `decider()` comme n'importe quel autre, et c'est ainsi que les tests les atteignent.

    ⚠️ **Ce que la machine perd de §6, et qu'elle ne récupère pas.** Le prompt dit que si
    l'outil rend `marque`, il vaut mieux demander l'usage — « c'est pour jouer, pour du
    montage ? » —, qui fait avancer plusieurs critères à la fois. L'usage n'est pas un
    champ : aucune action de ce module ne sait le désigner. La machine garde donc la
    moitié négative de la règle (le champ ne commande pas) et perd la moitié positive.
    C'est une perte réelle, et elle appartient au tableau des différences, pas aux
    regrets.
    """
    if question.budget is not None:
        return DemanderPrecision(CIBLE_BUDGET)
    if question.champ is not None:
        return DemanderPrecision(question.champ.champ)
    return Rediger()


__all__ = [
    "CIBLE_BUDGET",
    "GARDE_DE_CONTEXTE",
    "RESERVE_MESURE_8",
    "Action",
    "DemanderPrecision",
    "Rechercher",
    "Rediger",
    "Sonder",
    "Suggerer",
    "TourDejaClos",
    "decider",
]
