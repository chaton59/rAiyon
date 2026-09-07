"""Le contexte réellement fourni au modèle, **typé par provenance**. Pur.

### Pourquoi la provenance, et pas un sac de nombres (arbitrage B de l'étape 9)

C'est le piège de l'étape, et il était déjà visible dans la conversation de l'étape 8 :
`probe_catalog` avait rendu la fourchette `108.00 $` à `399.99 $`, et un écran valait
`108.00 $`. Un validateur qui vérifie « tout nombre cité apparaît quelque part dans un
`tool_result` » **accepterait** « cet écran est à 108 $ » alors que la borne d'un
sondage n'est le prix de personne — c'est l'oracle à prix que §7 nomme.

Les faits fournis sont donc rangés par **d'où ils viennent**, pas par ce qu'ils valent :

* `produits` — ce que `search_products` a rendu, `id` par `id` ;
* `hors_budget` — l'écart exact des produits de la zone de tolérance (§3.10) ;
* `prix` — le prix de chaque produit fourni, dérivé de `produits` ;
* `valeurs_de_specs` — les valeurs de caractéristiques **attribuables à un produit** ;
* `valeurs_de_distribution` — les valeurs que `probe_catalog` a vues dans le
  sous-catalogue, attribuables à **l'ensemble** et à personne en particulier ;
* `agregats` — les nombres fournis qui ne sont attribuables à aucun produit : bornes de
  prix, comptages, budget, valeurs atteignables d'un diagnostic ;
* `montants_agregats` — **ceux de ces agrégats qui sont des montants en dollars**, et
  eux seuls (étape 33) ;
* `budget_usd` — le plafond, seul agrégat citable à côté d'un produit (voir son champ).

⚠️ **Les valeurs des distributions de `probe_catalog` n'entrent pas dans
`valeurs_de_specs`.** Elles décrivent un ensemble, pas un produit : « 12 écrans sont à
165 Hz » ne rend pas vrai « celui-ci est à 165 Hz ». C'est ce qui fait échouer le piège
nº9 sur une version aplatie, et c'est la raison d'être de tout ce module.

### Il se lit sur les `tool_result`, et il est cumulatif sur la session

Pas sur un état interne : c'est ce qui garantit qu'il décrit **ce que le modèle a
réellement vu**. Et pas sur le tour : un produit rendu au tour 3 et cité au tour 6
(« je prends le premier ») est légitime, et un contexte par tour rejetterait la moitié
des conversations réelles.

Un `tool_result` marqué `is_error` est ignoré : un refus est un échange avec le modèle
(`erreurs.py`), il ne fournit aucun fait.

### Ce module lit les clés du protocole ; `en_tool_result()` est seule à les écrire

La lecture se fait **par clé**, jamais par nom d'outil. Deux raisons : le bloc
`tool_result` ne porte pas le nom de l'outil (il faudrait le rechercher dans le
`tool_use` appairé), et une clé identique dit la même chose où qu'elle apparaisse —
`fourchette_prix` est une fourchette dans `probe_catalog` comme dans le champ `budget`
de `suggest_next_question`. Les noms de clés sont donc rassemblés en constantes en tête
de module, en un seul endroit, comme de l'autre côté.

⚠️ **L'étape 13 apparie un `tool_use` à son `tool_result`, et la règle tient quand
même** — parce que ce qui déclenche l'appariement est une **clé**, pas un nom d'outil.
Quand un `tool_result` porte `mouvements_refuses` non vide, la valeur qui a été refusée
n'est pas dans le résultat : elle est dans la requête qui l'a produite. On remonte donc
au bloc appairé **par son identifiant**, sans jamais demander de quel outil il s'agit.
Le jour où un second outil rendrait `mouvements_refuses`, il serait lu de la même façon,
ce qui est exactement la propriété que « par clé » achète. Voir
`valeurs_des_mouvements_refuses`.
"""

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog
from pydantic import ValidationError

from raiyon.catalogue.schemas import ProduitEnBase
from raiyon.validateur.extraction import canonique, en_decimal, montants

logueur = structlog.get_logger(__name__)

# --------------------------------------------------------------------------- #
# Les clés du protocole, en un seul endroit — miroir de `en_tool_result()`
# --------------------------------------------------------------------------- #

# ⚠️ `prix_usd` et `specs` n'y figurent pas, et c'est délibéré : ils sont lus par
# `ProduitEnBase`, qui les nomme déjà et les **valide** au passage. Les redéclarer ici
# créerait un second endroit où le nom d'un champ de produit peut changer — exactement
# ce que ce bloc de constantes existe pour éviter.
CLE_OK = "ok"
CLE_FAITS_DU_CATALOGUE = "faits_du_catalogue"
"""🔴 **La déclaration qui fait entrer une charge utile dans le contexte** (étape 27).

Une charge qui ne la porte pas à `True` ne fournit **aucun** fait. C'est l'exclusion du
contenu web du §3.18, et elle est écrite comme une **adhésion explicite**, pas comme une
liste d'exceptions.

### Pourquoi l'adhésion plutôt que l'exclusion, et l'asymétrie qui tranche

L'écriture inverse — « le web déclare `faits_du_catalogue: false` et le reste entre par
défaut » — est plus courte et se lit mieux. Elle échoue du mauvais côté :

| Écriture | Un futur outil dont on oublie la déclaration |
|---|---|
| Exclusion (`false` à poser) | son contenu devient **citable** — hallucination, en silence |
| Adhésion (`true` à poser) | ses faits ne sont **pas** citables — du texte vrai est refusé |

Le second est un faux positif : il se voit dans la prose refusée, dans le taux de rejet
par code, et il se corrige en une ligne. Le premier est un trou silencieux dans la seule
garantie que le §2 promet. C'est exactement la règle que `_decoder()` applique déjà à un
`tool_result` illisible : **jugé sans lui, donc plus sévèrement, jamais plus laxement.**

⚠️ **Elle est lue par clé, jamais par nom d'outil** — la règle du module tient. Le nom de
l'outil n'apparaît nulle part dans le `tool_result`, et s'y fier reviendrait à faire
dépendre le validateur d'un protocole qu'il ne contrôle pas.

`tests/validateur/test_exclusion_du_web.py` est la garde : il construit une charge d'avis
qui **porte tout ce qu'il faut pour polluer** — des comptages, un prix, un identifiant —
et exige qu'elle ne fournisse rien. Il échoue si la déclaration est ajoutée à la branche
`ResultatAvis` d'`en_tool_result()`."""

CLE_PRODUITS = "produits"
CLE_AU_DESSUS_DU_BUDGET = "au_dessus_du_budget"
ROLE_CLIENT = "user"
"""⚠️ Les `tool_result` portent ce rôle aussi : il n'existe pas de rôle « outil » dans
l'API. C'est pourquoi `montants_des_messages_client()` écarte d'abord les blocs qui en
portent un, avant même de regarder le texte."""

CLE_PRODUIT = "produit"
CLE_ECART = "ecart_usd"
CLE_ID = "id"
CLE_BUDGET_USD = "budget_usd"
CLE_BUDGET = "budget"
CLE_FOURCHETTE = "fourchette_prix"
CLE_PLUS_BAS = "plus_bas"
CLE_PLUS_HAUT = "plus_haut"
CLE_CRITERES = "criteres"
CLE_VALEUR = "valeur"
CLE_CHAMPS = "champs"
CLE_CHAMP = "champ"
CLE_DISTRIBUTION = "distribution"
CLE_VALEURS = "valeurs"
CLE_EFFECTIF = "effectif"
CLE_ECARTES = "ecartes_faute_de_donnee"
CLE_DIAGNOSTIC = "diagnostic"
CLE_PROPOSITIONS = "propositions"
CLE_MOUVEMENTS_REFUSES = "mouvements_refuses"

# Les clés d'un bloc `tool_use`, et celle qui l'appaire à son résultat. Elles ne
# décrivent pas un fait du catalogue : elles servent uniquement à retrouver la requête
# dont un `tool_result` est la réponse (voir `valeurs_des_mouvements_refuses`).
TYPE_TOOL_USE = "tool_use"
CLE_ID_DE_BLOC = "id"
CLE_ENTREE = "input"
CLE_TOOL_USE_ID = "tool_use_id"
CLE_ATTEIGNABLE = "valeur_atteignable"
CLE_ROUVERTS = "produits_rouverts"

COMPTAGES = ("dans_le_budget", "dans_la_zone_de_tolerance", "candidats", "candidats_trouves")
"""Les entiers que les outils rendent et que l'agent a le droit de citer. Ce sont des
agrégats : ils décrivent un ensemble, jamais un produit."""

TYPE_TOOL_RESULT = "tool_result"
CLE_CONTENU = "content"
CLE_EST_ERREUR = "is_error"
CLE_TYPE = "type"


# --------------------------------------------------------------------------- #
# Le contexte
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ContexteFourni:
    """Ce que le code a mis sous les yeux du modèle, rangé par provenance."""

    produits: Mapping[str, ProduitEnBase]
    """`id` → produit, depuis `search_products`. La zone de tolérance en fait partie :
    ces produits ont bien été fournis, et leur nom comme leur `id` sont citables. C'est
    `hors_budget` qui porte la contrainte de présentation, pas l'absence d'entrée ici."""

    hors_budget: Mapping[str, Decimal]
    """`id` → `ecart_usd` exact, pour les produits de la zone de tolérance (§3.10)."""

    prix: Mapping[str, Decimal]
    """`id` → prix, dérivé de `produits`. Séparé de `agregats` : c'est toute la
    différence entre « ce produit coûte ça » et « il existe des produits à ce prix »."""

    valeurs_de_specs: frozenset[str]
    """Toute valeur de caractéristique **attribuable à un produit fourni**, en texte
    canonique (`canonique()` pour les nombres). Les valeurs enregistrées par
    `record_criteria` en font partie : ce sont celles que le client a dites, et que le
    code a renvoyées au modèle."""

    agregats: frozenset[Decimal]
    """Les nombres fournis qui ne sont le fait d'aucun produit : bornes de prix,
    comptages, budget, effectifs d'une distribution, valeurs atteignables d'un
    diagnostic.

    ⚠️ **Hétérogène par nature, et c'est pour cela qu'il ne suffit plus seul à la
    règle 2** — voir `montants_agregats`. Il reste tel quel : la règle 5 le consulte
    **sans condition** (une valeur atteignable de diagnostic y est citable, §12.3), et
    `repli.rediger()` y lit les comptages du sondage."""

    montants_agregats: frozenset[Decimal]
    """Les agrégats qui sont des **montants en dollars**. Sous-ensemble d'`agregats`.

    Deux provenances, et elles sont exhaustives : les bornes de `fourchette_prix` — celle
    de `probe_catalog` comme celle du champ `budget` de `suggest_next_question` — et
    `budget_usd`. Tout le reste d'`agregats` est un **comptage** (effectifs d'une
    distribution, `COMPTAGES`, `ecartes_faute_de_donnee`, `produits_rouverts`) ou une
    **valeur de spec** (`valeur_atteignable`, jamais un prix : `prix_usd` est dans
    `CHAMPS_JAMAIS_PROPOSES`, le budget a sa propre réponse §3.10).

    ### Le trou qu'il ferme, et il a été trouvé en usage réel (étape 33)

    La règle 2, dans sa branche « aucun produit nommé », comparait un montant en dollars à
    `agregats` tout entier. Un **comptage** y validait donc un **montant** :

    > « Pour 10 $ de plus, le MSI a un avantage concret » — accepté, parce que le sondage
    > avait rendu `effectif: 10` pour les 10 écrans à 144 Hz.

    Le 10 n'était le prix de personne, l'écart de personne, et aucun outil ne l'avait
    rendu comme montant. Il passait par collision numérique. La même phrase avec 13 $
    levait un grief ; avec 10 $ elle n'en levait aucun. Un validateur bâti tout entier sur
    l'égalité exacte se retrouvait à dépendre de l'espace des nombres.

    ### 🔴 Ce que ce compartiment n'est pas : un assouplissement

    C'est la distinction qui explique tout le reste, et elle sépare **deux défauts qu'on
    confond facilement**.

    * *Une règle qui tranche **contre** un comportement demandé.* C'est ce que
      `valeurs_refusees` a corrigé : le prompt ordonnait de dire au client quel mouvement
      avait été refusé, et le validateur refusait la phrase qui obéissait. Le correctif y
      était forcément un **élargissement** — il fallait rendre citable ce qui devait
      l'être.
    * *Une règle qui **s'abstient par accident**.* C'est ce cas-ci. Rien n'a jamais
      demandé au modèle d'écrire « 10 $ de plus » : §12.2 l'interdit explicitement, et le
      validateur l'attrape **403 fois sur 405** dans le corpus. Les 2 échappées ne sont pas
      une permission, ce sont des faux négatifs. Le correctif est donc un
      **resserrement**, et c'est l'inverse du précédent.

    Les confondre menait à une conclusion fausse et séduisante — « la règle 2 punit
    l'obéissance au §3, puisque écrire le nom verbatim fait basculer la phrase dans la
    branche `nommes` ». Le basculement est réel ; la punition, non. Ce que §3 fait
    apparaître, c'est un grief **juste** que la branche d'à côté ratait.

    ### La mesure, et ce qu'elle a coûté

    Rejeu de la règle 2 sur les 17 630 messages assistants de la base, contexte reconstruit
    message par message : **2 messages nouvellement refusés**, et les deux sont des écarts
    dérivés (`10 $`, `2 $`). Sur les 413 occurrences de « X $ de plus / de moins » du
    corpus : 403 déjà refusées, 8 `ecart_usd` légitimes (l'exception écrite au §12.2), 2
    passées par ce trou. Aucune prose légitime n'y est perdue, et la suite complète —
    unitaires et intégration — passe sans modification.

    ⚠️ **La conséquence est assumée et elle est le but** : « pour 10 $ de plus » disparaît
    aussi du message qui l'avait *fait passer*, pas seulement de celui qui s'était fait
    prendre.

    ### 🔴 Et §12 n'est pas « rouvrable » — la formulation qui le laissait croire est fausse

    Il serait tentant d'écrire « le jour où l'on voudra autoriser une différence entre deux
    prix fournis, on rouvrira §12 délibérément ». C'est faux, et le mécanisme le dit :
    **la règle 2 teste l'appartenance d'une valeur à un ensemble, jamais le rôle du nombre
    dans la phrase.** Admettre 10 comme écart admet « ce produit est à 10 $ » du même
    geste — un seul `montant.valeur not in autorises` décide des deux.

    Autoriser l'écart supposerait donc un validateur qui **comprend les rôles** : qui
    distingue « à 10 $ » de « 10 $ de plus », donc qui lit une fonction grammaticale et non
    une valeur. C'est **un autre objet, pas un réglage de celui-ci** — et c'est la même
    frontière que le dépôt a déjà refusé de franchir deux fois, pour le guillemet du pouce
    et pour la portée entre guillemets (§7) : encoder de la sémantique dans un analyseur
    lexical.

    §12.2 est donc fermé par la structure du validateur, pas par une préférence. Ce qui
    peut changer un jour est le validateur ; §12 suivra, il ne décidera pas.

    ### Pas de valeur par défaut — et c'est désormais une règle, pas un arbitrage local

    Le champ est **obligatoire**. Un défaut à `frozenset()` rendrait tout contexte bâti à
    la main plus sévère qu'il ne doit l'être — un faux positif, qui se voit ; un défaut
    recopiant `agregats` rouvrirait le trou en silence — un faux négatif, qui ne se voit
    pas. **Entre un faux positif qui se voit et un faux négatif qui ne se voit pas, on
    choisit celui qui se voit** : c'est l'arbitrage déjà écrit pour l'adhésion
    `faits_du_catalogue`, et deux occurrences en font une règle — §9.3.

    Aucun test ne construit `ContexteFourni` directement : le coût de l'obligation est de
    deux lignes, dans ce fichier."""

    valeurs_de_distribution: frozenset[str] = frozenset()
    """Les valeurs **présentes dans une distribution** de `probe_catalog`, en texte
    canonique. Elles décrivent un **ensemble**, jamais un produit.

    ⚠️ **Elles sont séparées de `valeurs_de_specs`, et cette séparation est tout
    l'arbitrage B.** « 12 écrans sont à 165 Hz » est un fait fourni ; « celui-ci est à
    165 Hz » ne l'est pas. La règle 5 les admet donc dans une phrase qui ne nomme aucun
    produit et les refuse dans une phrase qui en nomme un — exactement comme la règle 2
    fait des bornes de prix. Les verser dans `valeurs_de_specs` rendrait le piège nº9
    indétectable ; les jeter entièrement interdirait de dire ce que le catalogue
    contient, qui est la raison d'être de `probe_catalog` (§3.7)."""

    montants_du_client: frozenset[Decimal] = frozenset()
    """Les montants que le **client** a écrits dans ses propres messages (étape 25).

    ### Le faux positif que ça ferme, et il est structurel

    Mesuré sur une conversation réelle : le client dit « je dirais 300 $ », le modèle
    répond « D'accord, 300 $ pour démarrer » — et le validateur refuse, parce qu'aucun
    `tool_result` n'a encore rendu 300.

    `record_criteria` **rend pourtant `budget_usd`**, et il entre dans `agregats`. Le
    budget n'est donc pas absent du contexte : il y arrive **une itération trop tard**.
    Et comme `fourni` est calculé *avant* l'appel modèle — c'est l'arbitrage B, les faits
    que le modèle avait sous les yeux —, même un modèle qui enregistrerait et parlerait
    dans le même message serait refusé. **Accuser réception d'un budget est structurellement
    impossible au tour où le client l'énonce**, quoi que fasse le modèle.

    ### La garde, et elle n'est pas négociable

    ⚠️ **Ces montants n'entrent que dans la branche agrégat de la règle 2.** Jamais dans
    `prix_etranger_au_produit` : sinon un client qui dit « 300 $ » autorise « ce produit
    est à 300 $ », et le validateur perd sa propriété centrale — aucun prix de produit ne
    vient d'ailleurs que du moteur.

    ⚠️ **Et les messages de reprise en sont exclus.** Un message de reprise est un bloc
    `user` de la même forme qu'un tour client, et il **cite les extraits refusés** : les
    admettre rendrait le validateur auto-annulant. Mesuré à l'étape 13 : 18 griefs sur 19
    disparaissaient. `test_la_reprise_ne_fournit_jamais_un_fait` est la garde, et elle vaut
    toujours — cette provenance-ci est celle qu'elle décrivait comme « la rédaction naïve
    de l'alternative écartée », et elle n'est pas naïve précisément parce qu'elle exclut la
    reprise.

    *Précédent* : `valeurs_refusees` sont admises dans la même branche et sont **écrites par
    le modèle**. Des montants écrits par le client y sont strictement plus sûrs."""

    valeurs_refusees: frozenset[Decimal] = frozenset()
    """Les valeurs qu'un **mouvement refusé** portait (étape 13, jalon 1).

    ### Le besoin, et il est exactement celui-là

    La section 9 du prompt ordonne au modèle de **dire au client quel mouvement a été
    refusé** — « je garde le 144 Hz tant que vous ne me dites pas le contraire ». Un refus
    visible vaut mieux qu'un refus contourné. Or le dire suppose de citer la valeur
    refusée, et cette valeur n'est dans aucun `tool_result` : le jeton de parole ne
    l'ayant pas appliquée, elle n'apparaît ni dans `criteres`, ni dans `budget_usd`.

    Le validateur refusait donc « le passage à 300 $ et le 24 pouces n'ont pas été pris en
    compte » — c'est-à-dire qu'il **punissait l'obéissance à la section 9**. Ce n'est pas
    le cas d'une règle qui ne sait pas trancher et s'abstient ; c'est une règle qui tranche
    contre le comportement demandé.

    ⚠️ **Ce champ n'est pas une approximation étroite du besoin : c'est le besoin.** Les
    valeurs citables au titre de la section 9 sont précisément celles des mouvements
    refusés, ni plus ni moins. L'alternative écartée — admettre « tous les nombres que le
    client a écrits » — couvrait le besoin **par recouvrement** et non par identité : sur
    les quarante cassettes du dépôt elle admettait **119 nombres** là où celle-ci en admet
    **2**, pour faire taire exactement les deux mêmes griefs. L'écart de 117 ne sert à
    rien ; il n'est que de la surface.

    ### ⚠️ La provenance est un refus du moteur, **la valeur est écrite par le modèle**

    Les deux moitiés comptent, et la seconde interdit de traiter ce champ comme les
    autres. Le moteur fournit le **refus** — le jeton de parole a bien rejeté ce
    mouvement, c'est un fait produit par du code. Mais le **nombre**, lui, sort des
    arguments que le modèle a passés à l'outil. Un modèle peut donc se fabriquer une
    valeur citable en la faisant refuser exprès.

    C'est pourquoi ces valeurs sont admises **uniquement dans une phrase qui ne nomme
    aucun produit** — la discipline de `valeurs_de_distribution`, et pour la même raison.
    Elles décrivent ce que le client a demandé, jamais ce qu'un produit vaut.

    ⚠️ **Elles ne vont surtout pas dans `agregats`.** La règle 2 s'y comporterait bien —
    un agrégat reste refusé dans une phrase à produit —, mais la règle 5 consulte
    `agregats` **sans condition** : un `refresh_rate` refusé à 999 deviendrait citable en
    « cet écran est à 999 Hz ». Le compartiment dédié ferme ce chemin, que les agrégats
    laissent ouvert."""

    budget_usd: Decimal | None = None
    """Le plafond en vigueur, **tel que les outils l'ont rendu au modèle**.

    Il est aussi dans `agregats` — c'en est un — mais il en sort par un champ à lui pour
    une raison précise : c'est le **seul** agrégat admis dans une phrase qui nomme un
    produit (règle 2).

    ⚠️ **Ce n'est pas une commodité, et il ne faut élargir à rien d'autre.** Le budget
    n'est pas un fait du catalogue : c'est une **parole du client**, entrée par
    `record_criteria` et renvoyée dans son `tool_result`. §2 interdit au modèle
    d'inventer un fait ; répéter au client le montant qu'il vient d'annoncer n'en est pas
    un. Une borne de sondage, elle, est une affirmation sur le catalogue **et** un
    montant que le modèle n'a pas le droit d'attribuer à un produit — c'est le piège nº6,
    et c'est le seul test de l'étape qui échoue si quelqu'un aplatit le contexte.

    Il vient des `tool_result`, jamais d'`EtatSession` : le contexte fourni décrit ce que
    le modèle a vu, et il se construit toujours depuis ce qui lui a été envoyé. La
    dernière valeur rencontrée gagne, `null` compris — un budget retiré en cours de
    session cesse d'être citable."""

    @property
    def vide(self) -> bool:
        """Aucun fait fourni. Le modèle n'a alors le droit d'affirmer aucun chiffre."""
        return not (self.produits or self.valeurs_de_specs or self.agregats)


CONTEXTE_VIDE = ContexteFourni({}, {}, {}, frozenset(), frozenset(), frozenset())


def contexte_des_messages(messages: Sequence[Mapping[str, Any]]) -> ContexteFourni:
    """Le contexte fourni, lu sur les `tool_result` d'une conversation entière.

    `messages` est la liste au format de l'API — historique relu en base compris. Un
    message assistant ne porte aucun `tool_result` : l'ordre d'ajout du message en
    cours de validation est donc sans effet sur le résultat.

    ⚠️ **Une seule chose se lit ailleurs que dans un `tool_result`** : la valeur d'un
    mouvement refusé, qui n'est que dans la requête. Voir
    `valeurs_des_mouvements_refuses`, et la docstring du module pour pourquoi la règle
    « par clé, jamais par nom d'outil » y survit.

    ⚠️ **Une seule provenance se lit dans le texte d'un message `user`, et elle est
    étroitement gardée** (étape 25). Le message de reprise de l'étape 9 est un
    bloc `user` de la **même forme** qu'un tour client, et il **cite les extraits refusés** :
    en tirer des faits rendrait le validateur auto-annulant — mesuré, 18 griefs sur 19
    disparaissaient. `montants_du_client` l'exclut donc explicitement, et
    `test_la_reprise_ne_fournit_jamais_un_fait` reste la garde qui le vérifie.

    La phrase « aucune provenance ne se lit dans le texte d'un message `user` » figurait ici
    jusqu'à l'étape 25. Elle est remplacée plutôt que nuancée : ce qui la fondait n'était pas
    « le texte du client est sale », c'était « le texte du client est **indiscernable** de la
    reprise ». Depuis que `prefixe_de_reprise()` les sépare, l'interdiction porte sur la
    reprise seule.
    """
    return contexte_des_resultats(
        _charges_utiles(messages),
        valeurs_refusees=valeurs_des_mouvements_refuses(messages),
        montants_du_client=montants_des_messages_client(messages),
    )


def montants_des_messages_client(messages: Sequence[Mapping[str, Any]]) -> frozenset[Decimal]:
    """Les montants écrits par le client, **hors messages de reprise et hors `tool_result`**.

    Les trois exclusions, dans l'ordre où elles comptent :

    1. un bloc portant un `tool_result` n'est pas une parole du client — les `tool_result`
       voyagent sous le rôle `user`, il n'existe pas de rôle « outil » ;
    2. un message commençant par le préfixe de reprise est écrit **pour le modèle** par
       `grief.v1.md`, et il cite les extraits que le validateur vient de refuser ;
    3. tout le reste est du texte que le client a réellement tapé.

    ⚠️ **Le point 2 est la garde entière.** Sans lui, un nombre refusé au tour n redevient
    citable au tour n+1 par le message qui le refusait.
    """
    from raiyon.agent.prompts import prefixe_de_reprise

    prefixe = prefixe_de_reprise()
    trouves: set[Decimal] = set()
    for message in messages:
        if message.get("role") != ROLE_CLIENT:
            continue
        blocs: Sequence[Mapping[str, Any]] = message.get("content") or ()
        if any(bloc.get("type") == "tool_result" for bloc in blocs):
            continue
        for bloc in blocs:
            if bloc.get("type") != "text":
                continue
            texte = str(bloc.get("text", ""))
            if prefixe and texte.strip().startswith(prefixe):
                continue
            trouves.update(montant.valeur for montant in montants(texte))
    return frozenset(trouves)


def contexte_des_resultats(
    charges: Iterable[Mapping[str, Any]],
    *,
    valeurs_refusees: frozenset[Decimal] = frozenset(),
    montants_du_client: frozenset[Decimal] = frozenset(),
) -> ContexteFourni:
    """Le contexte fourni, à partir des charges utiles déjà décodées.

    C'est la porte d'entrée des tests : un dictionnaire suffit, il n'y a ni base, ni
    clé, ni SDK dans le chemin.

    ⚠️ **Les deux conditions d'entrée sont ici, et pas dans `_charges_utiles()`** (étape 27).
    La première rédaction avait mis la garde `faits_du_catalogue` dans `_charges_utiles()`,
    qui est sur le chemin des **messages** ; `contexte_des_resultats()` est l'autre porte,
    celle des charges déjà décodées, et elle passait à côté. `test_exclusion_du_web` l'a
    dit tout de suite — les deux chemins ne rendaient pas le même contexte pour la même
    charge, ce qui est précisément la divergence que ce module refuse ailleurs.

    Elles vivent donc au **seul point par lequel tout passe** : `contexte_des_messages()`
    délègue ici, et un futur troisième appelant en hériterait sans rien savoir.
    """
    accumulateur = _Accumulateur()
    for charge in charges:
        if charge.get(CLE_OK) is not True:
            continue
        if charge.get(CLE_FAITS_DU_CATALOGUE) is not True:
            # L'adhésion explicite du §3.18 : une charge qui ne se déclare pas source de
            # faits n'en fournit aucun. Voir `CLE_FAITS_DU_CATALOGUE` pour l'asymétrie qui
            # fait préférer l'adhésion à l'exclusion.
            continue
        accumulateur.absorber(charge)
    return accumulateur.figer(
        valeurs_refusees=valeurs_refusees, montants_du_client=montants_du_client
    )


def valeurs_des_mouvements_refuses(
    messages: Sequence[Mapping[str, Any]],
) -> frozenset[Decimal]:
    """Les valeurs que le jeton de parole a refusé d'appliquer, sur toute la conversation.

    **Le seul endroit du validateur qui remonte d'un `tool_result` à sa requête.** Il le
    fait parce que la valeur refusée n'existe nulle part ailleurs : le mouvement n'ayant
    pas été appliqué, elle n'est ni dans `criteres`, ni dans `budget_usd`.

    ⚠️ **Le déclencheur est la clé `mouvements_refuses`, jamais un nom d'outil.** Un
    second outil qui rendrait cette clé demain serait lu de la même façon, sans que
    personne ait à l'inscrire ici — c'est la propriété que « par clé » achète, et elle
    survit à l'appariement. L'identifiant, lui, ne dit rien de sémantique : il ne sert
    qu'à retrouver *quelle requête* a produit *ce résultat*.

    ⚠️ **Ce que cette fonction rend est écrit par le modèle**, et c'est pour cela que ses
    valeurs sont cantonnées aux phrases sans produit (voir `ContexteFourni.valeurs_refusees`).
    Le moteur fournit le refus ; le nombre vient des arguments d'appel.

    *Alternative écartée — ajouter `valeur` à `MouvementRefuse`.* Bien plus direct, et
    **impossible sans tout réenregistrer** : le `tool_result` est recalculé au rejeu et
    entre dans l'empreinte de requête (arbitrage B de l'étape 12). Un champ de plus, et
    les quarante cassettes du dépôt divergent au deuxième tour.
    """
    requetes: dict[str, Mapping[str, Any]] = {}
    trouvees: set[Decimal] = set()
    for message in messages:
        contenu = message.get(CLE_CONTENU)
        if not isinstance(contenu, list):
            continue
        for bloc in contenu:
            if not isinstance(bloc, Mapping):
                continue
            if bloc.get(CLE_TYPE) == TYPE_TOOL_USE:
                entree = bloc.get(CLE_ENTREE)
                if isinstance(entree, Mapping):
                    requetes[str(bloc.get(CLE_ID_DE_BLOC))] = entree
            elif bloc.get(CLE_TYPE) == TYPE_TOOL_RESULT and not bloc.get(CLE_EST_ERREUR):
                charge = _decoder(bloc.get(CLE_CONTENU))
                requete = requetes.get(str(bloc.get(CLE_TOOL_USE_ID)))
                if charge is not None and requete is not None:
                    trouvees.update(_valeurs_refusees(requete, charge))
    return frozenset(trouvees)


def _valeurs_refusees(requete: Mapping[str, Any], resultat: Mapping[str, Any]) -> Iterator[Decimal]:
    """Ce que la requête demandait et que le résultat n'a pas appliqué."""
    refuses = {
        str(mouvement.get(CLE_CHAMP))
        for mouvement in resultat.get(CLE_MOUVEMENTS_REFUSES) or ()
        if isinstance(mouvement, Mapping)
    }
    if not refuses:
        return
    for critere in requete.get(CLE_CRITERES) or ():
        if not isinstance(critere, Mapping) or str(critere.get(CLE_CHAMP)) not in refuses:
            continue
        valeur = en_decimal(str(critere.get(CLE_VALEUR)))
        if valeur is not None:
            yield valeur
    # Le budget suit le même chemin, mais il n'est pas un critère : le refus se lit sur
    # l'écart entre ce qui a été demandé et ce qui a été rendu.
    demande = en_decimal(str(requete.get(CLE_BUDGET_USD)))
    rendu = en_decimal(str(resultat.get(CLE_BUDGET_USD)))
    if demande is not None and rendu is not None and demande != rendu:
        yield demande


def _charges_utiles(messages: Sequence[Mapping[str, Any]]) -> Iterator[Mapping[str, Any]]:
    """Les charges utiles des `tool_result` réussis, dans l'ordre de la conversation."""
    for message in messages:
        contenu = message.get(CLE_CONTENU)
        if not isinstance(contenu, list):
            continue
        for bloc in contenu:
            if not isinstance(bloc, Mapping) or bloc.get(CLE_TYPE) != TYPE_TOOL_RESULT:
                continue
            if bloc.get(CLE_EST_ERREUR):
                continue
            charge = _decoder(bloc.get(CLE_CONTENU))
            if charge is not None:
                yield charge


def _decoder(contenu: object) -> Mapping[str, Any] | None:
    """Le contenu d'un `tool_result`, qui est du JSON en chaîne (`bloc_tool_result`)."""
    if isinstance(contenu, Mapping):
        return contenu
    if not isinstance(contenu, str):
        return None
    try:
        charge = json.loads(contenu)
    except json.JSONDecodeError:
        # Un `tool_result` illisible n'est pas un incident du validateur : il ne
        # fournit simplement aucun fait, et le texte sera jugé sans lui — c'est-à-dire
        # plus sévèrement, jamais plus laxement.
        logueur.warning("validateur.tool_result_illisible", taille=len(contenu))
        return None
    return charge if isinstance(charge, Mapping) else None


# --------------------------------------------------------------------------- #
# L'accumulation, clé par clé
# --------------------------------------------------------------------------- #


class _Accumulateur:
    """L'état de construction du contexte. Mutable ici, figé à la sortie."""

    def __init__(self) -> None:
        self.produits: dict[str, ProduitEnBase] = {}
        self.hors_budget: dict[str, Decimal] = {}
        self.prix: dict[str, Decimal] = {}
        self.specs: set[str] = set()
        self.distribution: set[str] = set()
        self.agregats: set[Decimal] = set()
        self.montants_agregats: set[Decimal] = set()
        self.budget: Decimal | None = None

    def figer(
        self,
        *,
        valeurs_refusees: frozenset[Decimal] = frozenset(),
        montants_du_client: frozenset[Decimal] = frozenset(),
    ) -> ContexteFourni:
        """Les provenances accumulées, plus les deux qui ne s'accumulent pas.

        `valeurs_refusees` ne passe pas par `absorber()` : elle ne se lit pas dans une
        charge utile mais dans l'appariement d'une requête et de son résultat, ce qui est
        hors de portée d'un accumulateur qui reçoit des charges une par une.

        `montants_du_client` non plus, et pour une raison plus forte : elle ne se lit pas
        dans un `tool_result` du tout, mais dans les messages du client. C'est la **seule**
        provenance du module dans ce cas avec `valeurs_refusees`, et les deux sont donc
        passées explicitement — il ne doit pas être possible de les obtenir par accident.
        """
        return ContexteFourni(
            produits=dict(self.produits),
            hors_budget=dict(self.hors_budget),
            prix=dict(self.prix),
            valeurs_de_specs=frozenset(self.specs),
            valeurs_de_distribution=frozenset(self.distribution),
            agregats=frozenset(self.agregats),
            montants_agregats=frozenset(self.montants_agregats),
            valeurs_refusees=valeurs_refusees,
            montants_du_client=montants_du_client,
            budget_usd=self.budget,
        )

    def absorber(self, charge: Mapping[str, Any]) -> None:
        """Range une charge utile d'outil selon les clés qu'elle porte.

        ⚠️ **`produits` est absorbé avant `au_dessus_du_budget`, et l'ordre compte**
        (étape 32) : le premier **retire** de `hors_budget`, le second y écrit. Les deux
        ensembles sont disjoints dans une même charge (§3.10), donc aucune entrée posée par
        cette charge-ci ne peut être effacée par elle.
        """
        for brut in _liste(charge.get(CLE_PRODUITS)):
            produit = self._produit(brut)
            if produit is not None:
                # 🔴 **Un produit rendu DANS le budget cesse d'être hors budget** — sans
                # cette ligne, l'écart d'une recherche antérieure survivait à la recherche
                # qui l'avait rendu faux, et la règle `ecart_non_dit` exigeait qu'on
                # annonce un dépassement **qui n'existait plus**.
                #
                # Mesuré à l'étape 32, sur `desserrage_refuse`, 3 prises sur 3 : au tour 1
                # le budget vaut 200 $ et deux écrans à 226,99 $ et 229,00 $ sont rendus
                # au-dessus ; au tour 2 le client monte à 300 $, la même recherche les rend
                # **dans** le budget, et le modèle l'écrit — correctement. Le validateur
                # refusait, régénérait, et se repliait : **les trois seuls replis de la
                # campagne v3**, tous sur une prose vraie. Le modèle a même argumenté à la
                # seconde tentative — « la recherche que j'ai sous les yeux le confirme ».
                #
                # C'est la règle du §9.3 appliquée à l'exécution : on n'évalue pas une
                # phrase contre un état accumulé quand l'état est destructif. Ce n'est pas
                # un relâchement — rien de neuf ne devient citable, un fait périmé cesse
                # seulement de contredire le fait qui l'a remplacé.
                self.hors_budget.pop(produit.id, None)

        for brut in _liste(charge.get(CLE_AU_DESSUS_DU_BUDGET)):
            if not isinstance(brut, Mapping):
                continue
            produit = self._produit(brut.get(CLE_PRODUIT))
            ecart = _nombre(brut.get(CLE_ECART))
            if produit is not None and ecart is not None:
                self.hors_budget[produit.id] = ecart

        self._fourchette(charge.get(CLE_FOURCHETTE))
        budget = charge.get(CLE_BUDGET)
        if isinstance(budget, Mapping):
            self._fourchette(budget.get(CLE_FOURCHETTE))

        if CLE_BUDGET_USD in charge:
            # La clé est présente dans `record_criteria` **et** dans `probe_catalog`, et
            # les deux portent le plafond de session au moment de l'appel : lire la clé
            # plutôt que le nom de l'outil donne donc la bonne valeur, et la dernière
            # gagne. `null` est une valeur, pas une absence — un budget retiré doit
            # cesser d'être citable, et un `if valeur is not None` l'aurait figé.
            self.budget = _nombre(charge.get(CLE_BUDGET_USD))
        self._agregat_monetaire(charge.get(CLE_BUDGET_USD))
        # ⚠️ Les comptages passent par `_agregat`, jamais par `_agregat_monetaire` : un
        # effectif de 10 ne doit pas valider « 10 $ ». C'est tout l'objet de l'étape 33 —
        # voir `ContexteFourni.montants_agregats`.
        for cle in COMPTAGES:
            self._agregat(charge.get(cle))

        ecartes = charge.get(CLE_ECARTES)
        if isinstance(ecartes, Mapping):
            for compte in ecartes.values():
                self._agregat(compte)

        for critere in _liste(charge.get(CLE_CRITERES)):
            if isinstance(critere, Mapping):
                self._valeur_de_spec(critere.get(CLE_VALEUR))

        for distribution in _liste(charge.get(CLE_CHAMPS)):
            self._distribution(distribution)
        champ = charge.get(CLE_CHAMP)
        if isinstance(champ, Mapping):
            self._distribution(champ.get(CLE_DISTRIBUTION))

        diagnostic = charge.get(CLE_DIAGNOSTIC)
        if isinstance(diagnostic, Mapping):
            for proposition in _liste(diagnostic.get(CLE_PROPOSITIONS)):
                if not isinstance(proposition, Mapping):
                    continue
                self._agregat(proposition.get(CLE_ATTEIGNABLE))
                self._agregat(proposition.get(CLE_ROUVERTS))

    def _produit(self, brut: object) -> ProduitEnBase | None:
        """Revalide un produit fourni. Un produit que le schéma refuse n'entre pas.

        Le contexte ne contient donc que des produits qui auraient pu sortir de la base
        — c'est la même porte que `catalogue/schemas.py` garde à l'insertion, prise
        dans l'autre sens.
        """
        if not isinstance(brut, Mapping):
            return None
        try:
            produit = ProduitEnBase.model_validate(dict(brut))
        except ValidationError as erreur:
            logueur.warning(
                "validateur.produit_fourni_invalide",
                identifiant=brut.get(CLE_ID),
                detail=str(erreur),
                consequence="il ne sera pas citable ; le texte sera jugé sans lui",
            )
            return None
        self.produits[produit.id] = produit
        self.prix[produit.id] = produit.prix_usd
        for valeur in produit.specs_pour_base().values():
            self._valeur_de_spec(valeur)
        return produit

    def _valeur_de_spec(self, valeur: object) -> None:
        """Indexe une valeur attribuable à un produit, sous sa forme canonique."""
        if valeur is None or isinstance(valeur, bool):
            return
        if isinstance(valeur, int | float | Decimal):
            self.specs.add(canonique(Decimal(str(valeur))))
            return
        if isinstance(valeur, str):
            nombre = en_decimal(valeur)
            self.specs.add(canonique(nombre) if nombre is not None else valeur)

    def _agregat(self, valeur: object) -> None:
        """Un agrégat qui n'est **pas** un montant : comptage, effectif, valeur de spec."""
        nombre = _nombre(valeur)
        if nombre is not None:
            self.agregats.add(nombre)

    def _agregat_monetaire(self, valeur: object) -> None:
        """Un agrégat qui est un **montant en dollars**. Il entre dans les deux ensembles.

        Deux appelants, et il ne doit pas y en avoir un troisième sans qu'on relise
        `ContexteFourni.montants_agregats` : `_fourchette()` et le `budget_usd`. Un
        comptage qui passerait par ici redeviendrait citable comme prix.
        """
        nombre = _nombre(valeur)
        if nombre is not None:
            self.agregats.add(nombre)
            self.montants_agregats.add(nombre)

    def _fourchette(self, brut: object) -> None:
        """Les deux bornes d'une `fourchette_prix`. **Des montants, toujours.**

        La clé est lue par son nom, jamais par l'outil qui la porte (règle du module) :
        `fourchette_prix` est une fourchette de prix dans `probe_catalog` comme dans le
        champ `budget` de `suggest_next_question`.
        """
        if not isinstance(brut, Mapping):
            return
        self._agregat_monetaire(brut.get(CLE_PLUS_BAS))
        self._agregat_monetaire(brut.get(CLE_PLUS_HAUT))

    def _distribution(self, brut: object) -> None:
        """⚠️ **Les effectifs sont des agrégats, les valeurs vont dans un champ à part.**

        « 12 écrans à 165 Hz » est un fait sur un ensemble : le comptage est un agrégat
        comme un autre, mais la fréquence n'est citable **d'aucun produit**. Elle n'entre
        donc pas dans `valeurs_de_specs` — c'est ce que le piège nº9 vérifie — et pas non
        plus à la poubelle : sans elle, l'agent ne pourrait pas dire ce que le catalogue
        contient, ce qui est la raison d'être de `probe_catalog`.

        C'est la seule ligne de ce module qu'il ne faut pas « simplifier ».
        """
        if not isinstance(brut, Mapping):
            return
        for valeur in _liste(brut.get(CLE_VALEURS)):
            if isinstance(valeur, Mapping):
                self._agregat(valeur.get(CLE_EFFECTIF))
                self._valeur_de_distribution(valeur.get(CLE_VALEUR))

    def _valeur_de_distribution(self, valeur: object) -> None:
        """Indexe une valeur d'ensemble, sous la même forme canonique que les specs."""
        if isinstance(valeur, str):
            nombre = en_decimal(valeur)
            self.distribution.add(canonique(nombre) if nombre is not None else valeur)


def _liste(valeur: object) -> Sequence[Any]:
    return valeur if isinstance(valeur, list) else ()


def _nombre(valeur: object) -> Decimal | None:
    """Un nombre fourni, quelle que soit la façon dont le JSON l'a porté.

    Les `Decimal` partent en **chaînes** (`en_tool_result()`), les entiers en entiers :
    les deux passent par ici et ressortent en `Decimal`, jamais en flottant.
    """
    if isinstance(valeur, bool) or valeur is None:
        return None
    if isinstance(valeur, int | float | Decimal):
        return Decimal(str(valeur))
    if isinstance(valeur, str):
        return en_decimal(valeur)
    return None
