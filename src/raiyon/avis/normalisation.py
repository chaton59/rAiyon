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
