"""La clé du cache : d'une requête libre à une chaîne comparable. **Pure, sans base.**

Le modèle formule ce qu'il veut. « avis ASRock PG27FRS1A », « ASRock PG27FRS1A avis »,
« Est-ce que l'ASRock PG27FRS1A est bien ? » sont trois façons de demander la même chose,
et un cache qui les traite comme trois clés distinctes ne sert jamais.

---

### Où est placé le curseur, et pourquoi il est plus haut qu'on ne le mettrait d'instinct

Le réflexe est de normaliser peu : moins on touche à la requête, moins on risque de servir
des avis hors sujet. Ce réflexe suppose que **le coût d'un miss est un appel réseau de
plus**. Ici il ne l'est pas.

Depuis la décision de l'étape 26, une campagne d'éval ne sort **jamais** sur le réseau :
elle lit un cache pré-chargé. Un miss n'y coûte donc pas un appel — il rend **zéro
résultat**, l'outil ne trouve rien, et le scénario exerce silencieusement un autre chemin
que celui qu'il prétend mesurer. **En mesure, un miss est un défaut ; un faux hit est un
défaut. Ils ne sont pas symétriques : le premier est invisible, le second se lit dans la
prose livrée.** C'est ce qui déplace le curseur vers le haut.

### Ce qui est appliqué, et qui ne change aucun sens

| Étape | Effet |
|---|---|
| NFKC | les formes de compatibilité Unicode se ramènent à une seule |
| `casefold()` | « Écran » et « écran » sont la même requête |
| retrait des diacritiques | « écran » et « ecran » aussi : on ne cherche pas dans les deux |
| non-alphanumérique → espace | ponctuation, apostrophes, tirets. « i7-920 » vaut « i7 920 » |
| déduplication des jetons | « avis avis écran » n'est pas une requête différente |

### Le tri des jetons — le seul pas qui peut fusionner deux requêtes différentes

Il est retenu, parce que l'ordre des mots d'une requête de recherche ne porte presque
jamais de sens : « avis X » et « X avis » sont la même demande, et le modèle produit les
deux. Sans le tri, cette paire-là — la plus fréquente de toutes — serait deux clés.

⚠️ **La famille de faux positifs qu'il ouvre est nommée : les comparatives.**
« AOC mieux que ASRock » et « ASRock mieux que AOC » deviennent la même clé alors que ce
sont deux questions opposées. L'atténuation est réelle mais partielle : les pages qui
répondent à l'une répondent en général à l'autre, puisqu'elles comparent les deux objets.
Ce n'est pas une preuve, c'est un pari, et il est écrit ici pour que le journal le
mesure — l'étape 27 trace la clé de chaque recherche, donc les collisions se comptent.

### 🔴 La limite qui coûtera le plus cher : la clé n'est pas tolérante au sous-ensemble

⚠️ **Le curseur est relevé sur l'ORDRE des mots, pas sur leur NOMBRE.** C'est une
qualification importante de tout ce qui précède, et elle a été constatée en branchant
l'outil sur le seed réel, pas déduite :

| Formulation | Clé |
|---|---|
| « ASRock Phantom Gaming PG27FRS1A avis » | `asrock avis gaming pg27frs1a phantom` |
| « avis ASRock PG27FRS1A » | `asrock avis pg27frs1a` |
| « ASRock PG27FRS1A avis utilisateurs » | `asrock avis pg27frs1a utilisateurs` |

Trois demandes identiques, **trois clés**. Un mot de plus ou de moins suffit, et le modèle
formule librement — donc c'est le mode de miss le plus probable en pratique, très loin
devant les collisions du tri.

**✅ Corrigé à l'étape 29 par `meilleure_correspondance()`, et le seuil vient d'un
relevé.** La parade est un appariement par recouvrement de Jaccard. Elle n'a pas été
écrite plus tôt exprès : un seuil se calibre sur des données, et les données n'existaient
pas avant que le miss bruyant les produise. Voir `SEUIL_RECOUVREMENT` pour les quatre
paires qui l'ont placé.

⚠️ **Ce que le recouvrement ne rattrape pas, et qui n'est pas de son ressort.** La requête
à trois produits observée à l'étape 28 — `MSI MAG 274CQF vs LG 27GP750-B vs Asus TUF…` —
recouvre à 0,333, sous le seuil, **et c'est correct** : une recherche d'avis qui nomme
trois écrans est mauvaise en soi, quelle que soit la façon dont on l'apparie. C'est un
défaut de produit, corrigé dans la description de l'outil (« une recherche porte sur UN
seul produit ou UN seul sujet »), pas dans le cache.

⚠️ **L'atténuation écrite à l'étape 27 aggravait ce qu'elle visait, et c'est mesuré.**
« Nommer le produit tel que le catalogue l'écrit » concentre bien les requêtes *produit*,
et fait exploser les requêtes *sujet* en comparaisons multi-produits. La description dit
donc maintenant **un objet à la fois**, produit ou sujet.

### Ce qui a été refusé, et pourquoi

* **Retrait des mots vides.** « est-ce que », « le », « de » ne pèsent rien dans le tri
  puisqu'ils sont partagés par toutes les formulations ; les retirer demanderait une liste
  française à tenir, qui vieillirait sans que rien ne le dise. Le tri fait le travail sans
  la liste.
* **Racinisation / lemmatisation.** « écran » et « écrans » resteraient deux clés — c'est
  le vrai défaut de ce qui suit —, mais y répondre demande une dépendance linguistique
  française, donc un modèle de plus dans un projet qui en compte déjà assez, pour un gain
  que rien ne chiffre aujourd'hui.
* **Synonymes (« avis » → « review »).** Une table de synonymes est une affirmation sur le
  domaine, écrite à la main, qu'aucune mesure ne fonde. C'est exactement la forme de
  décision que ce dépôt refuse ailleurs.

### `JETONS_MAX` est une garde d'index, pas une règle de sens

L'index unique porte la clé ; une entrée de btree Postgres est bornée à environ 2 700
octets, et une requête pathologiquement longue ferait échouer l'écriture au lieu de rater
le cache. Les jetons étant triés, la troncature est déterministe. Vingt-quatre jetons
après déduplication ne sont plus une requête de recherche, et deux requêtes qui partagent
leurs vingt-quatre premiers jetons triés sont, à ce stade, la même.
"""

import re
import unicodedata
from collections.abc import Iterable

SEUIL_RECOUVREMENT = 0.5
"""Recouvrement de Jaccard minimal pour qu'une clé en serve une autre. **Calibré, pas choisi.**

⚠️ **Le chiffre vient du relevé de l'étape 28**, pas d'une intuition — c'est exactement ce
que le miss bruyant avait été écrit pour produire. Sur les clés réellement formulées par le
modèle et sur celles du seed :

| Paire | Recouvrement | Ce qu'on veut |
|---|---|---|
| `avis dalle ips jouer joueurs pour va vs` ↔ `dalle ips jouer ou pour va` | **0,556** | fusionner |
| `avis dalle gamers ips jouer pour va vs` ↔ la même | **0,556** | fusionner |
| `asus avis gaming tuf vg279qm1a` ↔ `asus defauts vg279qm1a` | **0,333** | **ne pas** fusionner |
| requête à trois produits ↔ `asus avis gaming tuf vg279qm1a` | **0,333** | **ne pas** fusionner |

La fenêtre admissible est donc `]0,333 ; 0,556]`. Son milieu est 0,44 ; **0,5 est retenu
parce qu'il faut se tromper du bon côté**.

### L'asymétrie qui place le seuil, et elle n'est pas dans les chiffres

Un seuil trop haut rate un quasi-doublon : le miss est alors **bruyant** hors ligne
(`AVIS_HORS_LIGNE` nomme la clé) et déclenche une vraie recherche en ligne. Coût visible,
rattrapable, mesuré.

Un seuil trop bas sert les avis d'**une autre requête**, et personne ne le voit : la prose
parle de l'écran demandé en citant les retours d'un autre. C'est la panne silencieuse que
tout ce jalon existe pour éviter. Le seuil erre donc **haut** : 0,5 laisse 0,167 de marge
au-dessus de la pire fusion à tort connue, et seulement 0,056 sous la vraie fusion la plus
serrée. Ce déséquilibre est voulu.

⚠️ **Quatre paires ne sont pas une calibration**, et le chiffre se relira à la prochaine
campagne. Il est écrit ici avec ses données pour que la relecture ait de quoi trancher."""

JETONS_MAX = 24
"""Nombre de jetons conservés dans la clé. **Garde sur l'index**, voir la docstring."""

_NON_ALPHANUMERIQUE = re.compile(r"[^0-9a-z]+")
"""Appliqué **après** `casefold()` et le retrait des diacritiques : à ce stade il ne reste
que de l'ASCII minuscule, et la classe n'a donc pas à énumérer les alphabets."""


def normaliser(requete: str) -> str:
    """La clé de cache d'une requête libre. Rend `""` si rien d'exploitable ne subsiste.

    ⚠️ **Une clé vide n'est pas une clé.** `normaliser("???")` rend `""`, et un appelant qui
    l'utiliserait tel quel rangerait tous ses résultats sous la même entrée. C'est à la
    couche outils de refuser une requête vide — cette fonction reste **totale** parce
    qu'une fonction de normalisation qui lève oblige chaque appelant à savoir quand.
    """
    sans_accents = _sans_diacritiques(unicodedata.normalize("NFKC", requete).casefold())
    jetons = [jeton for jeton in _NON_ALPHANUMERIQUE.split(sans_accents) if jeton]
    return " ".join(sorted(set(jetons))[:JETONS_MAX])


def _sans_diacritiques(texte: str) -> str:
    """« écran » devient « ecran ». Les caractères non latins traversent inchangés.

    La décomposition NFD sépare la lettre de son signe ; on ne garde que ce qui n'est pas
    un signe combinant. Un idéogramme, qui n'a pas de forme décomposée, en sort identique —
    et sera retiré ensuite par `_NON_ALPHANUMERIQUE`, faute d'être de l'ASCII. C'est une
    limite assumée : le catalogue est en anglais, les conversations en français.
    """
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(caractere for caractere in decompose if not unicodedata.combining(caractere))


def recouvrement(une: str, autre: str) -> float:
    """L'indice de Jaccard entre deux clés : jetons communs sur jetons de l'union. Pur.

    ⚠️ **Sur des ensembles, pas des listes** — les clés sont déjà triées et dédupliquées
    par `normaliser()`, donc un jeton ne pèse qu'une fois quelle que soit sa fréquence.
    C'est cohérent avec la clé elle-même : deux requêtes qui ne diffèrent que par une
    répétition sont déjà la même clé.

    Deux clés vides rendent `0.0` et non `1.0` : une clé vide n'est pas une clé, et la
    faire recouvrir tout le monde serait le pire comportement possible.
    """
    jetons_une, jetons_autre = set(une.split()), set(autre.split())
    union = jetons_une | jetons_autre
    if not union:
        return 0.0
    return len(jetons_une & jetons_autre) / len(union)


def meilleure_correspondance(
    cle: str, candidates: Iterable[str], *, seuil: float = SEUIL_RECOUVREMENT
) -> str | None:
    """La clé connue qui recouvre le mieux `cle`, si elle passe le seuil. Pure.

    Rend `None` plutôt que la moins mauvaise : en dessous du seuil, il n'y a pas de
    correspondance « approximative acceptable », il y a un miss — qui est bruyant hors
    ligne et déclenche une recherche en ligne. Voir `SEUIL_RECOUVREMENT` pour l'asymétrie
    qui place le seuil.

    ⚠️ **Départage par la clé la plus courte à score égal.** Le cas se produit (deux
    entrées du seed peuvent recouvrir autant), et sans règle explicite le résultat
    dépendrait de l'ordre de la base — donc deux exécutions comparées pourraient servir
    des avis différents pour la même requête. C'est précisément ce que ce cache existe pour
    empêcher.
    """
    meilleures = sorted(
        ((recouvrement(cle, candidate), -len(candidate), candidate) for candidate in candidates),
        reverse=True,
    )
    if not meilleures or meilleures[0][0] < seuil:
        return None
    return meilleures[0][2]
