"""Le coût d'enregistrement d'un jeu — la mesure nº7. **Pur, et de provenance gelée.**

Ce module existe pour **une seule raison**, et elle tient dans un mot : la provenance.

Tout ce que porte `Mesures` est **recalculé à chaque rejeu** par le vrai moteur, la vraie
couche outils et le vrai validateur — c'est l'arbitrage A de l'étape 12, et c'est ce qui
fait qu'un scoring qui change se voit sans rien réenregistrer. Le coût, lui, est **figé à
l'enregistrement** : il se lit dans `entete.usage`, il ne bougera plus jamais, et
aucun changement du moteur ne le fera bouger.

Poser un nombre de cette provenance-là au milieu de nombres qui se recalculent est
exactement le genre de confusion que ce dépôt écrit des paragraphes pour éviter. Il vit
donc dans **son propre module**, `Mesures` ne le porte pas, et `mesurer_le_jeu()` le rend
à côté de l'agrégat plutôt que dedans.

*Alternative écartée — un champ de plus dans `Mesures`.* Moins de plomberie, et la
provenance devient invisible à la lecture du type. C'est un mauvais échange sur une
structure dont la docstring dit « chaque champ correspond à une ligne du rapport ».

---

### Tout ou rien, jamais une moyenne sur un sous-ensemble

Le coût n'est publié **que si toutes les prises mesurées portent `usage`**. Sinon, une
ligne explicite qui dit combien en manquent, et aucun chiffre.

Ce n'est pas de la prudence théorique : l'état du disque au 3 septembre 2026 rend le cas
immédiat.

| Jeu | Prises avec `usage` | Coût publiable |
|---|---|---|
| `v2` | 36 / 36 | oui |
| `v1-desserrage` | 3 / 3 | oui |
| `v1-etape12` | 0 / 19 | **non** |
| `v1-base` (composé) | 3 / 31 | **non** |

Une moyenne calculée sur 3 prises de `v1-base` et comparée aux 36 de `v2` comparerait des
**tailles d'échantillon** — la faute que `docs/eval/LISEZMOI.md` interdit déjà pour les totaux.

⚠️ **Et c'est sans conséquence pour l'étape 15** : la comparaison qui compte est `v2` contre
`machine.v1`, et les deux porteront `usage` sur toutes leurs prises. La ligne « non
disponible » n'apparaît que sur les rapports rétrospectifs, où elle est la vérité.

### Le numérateur et le dénominateur viennent de la même population

Les appels sont sommés sur les prises **effectivement mesurées**, pas sur les fichiers du
répertoire : une prise écartée pour divergence attendue ne compte ni ses appels, ni ses
tours. Compter ses appels au numérateur et pas ses tours au dénominateur donnerait un
ratio dont les deux moitiés ne décrivent pas le même tirage.

---

### ⚠️ Le compte d'appels seul dit l'inverse du coût réel (correctif de l'étape 16)

La mesure a été spécifiée au jalon 0 de l'étape 15 sur `entete.usage.appels` — **avant**
qu'on sache ce que la campagne allait montrer. Elle l'a montré : la machine à états fait
**2,17 appel/tour contre 2,36** pour l'agent — moins — et coûte **1,80 fois plus d'entrée
facturée**, 663 347 jetons contre 367 832. Elle fait exactement deux appels par tour, mais
chacun renvoie la conversation entière, et celle-ci grossit plus vite.

Un rapport qui ne publie que les appels se lit donc « moins d'appels, donc moins chère », et
**la conclusion inverse est la vraie**. C'est une erreur de spécification, pas
d'implémentation : le chiffre juste existait dans les en-têtes depuis le premier jour de la
campagne, personne ne le publiait, et il ne vivait sommé à la main que dans le README.

`Cout` porte donc l'`Usage` cumulé et non plus le seul compte d'appels. Trois grandeurs sont
publiées à côté du ratio :

* l'**entrée facturée** — entrée hors cache **plus** cache écrit, c'est-à-dire ce qui se
  paie ;
* le **cache lu**, à côté et jamais additionné aux précédents : il ne se paie pas au même
  tarif, et l'ajouter ferait un total que personne ne doit à personne ;
* la **sortie**.

La règle du tout ou rien ne bouge pas d'un cran : ces trois-là s'effacent avec le ratio dès
qu'une prise du jeu n'a pas d'`usage`.
"""

from dataclasses import dataclass

from raiyon.agent.client import Usage

PROVENANCE = (
    "⚠️ **La mesure nº7 ne vient pas du rejeu.** Ce sont les seules lignes de ce fichier "
    "qui soient lues\ndans l'en-tête des cassettes plutôt que recalculées : elles sont "
    "**figées à l'enregistrement** et ne\nbougeront pas quand le moteur, le scoring ou le "
    "validateur changeront. Les autres chiffres, si."
)
"""La phrase que le rapport et la comparaison publient à côté du chiffre. **Écrite une
fois**, parce qu'une provenance expliquée à un seul des deux endroits laisse l'autre lire
le nombre comme les siens."""

POURQUOI_LES_DEUX_MOITIES = (
    "⚠️ **Les appels et les jetons peuvent aller en sens contraire, et c'est arrivé.** La "
    "campagne\nde l'étape 15 a mesuré une orchestration qui fait **moins d'appels par "
    "tour** que l'autre et qui\npaie **près du double** en entrée facturée : deux appels "
    "par tour, mais chacun renvoie une\nconversation qui grossit plus vite. Publier le "
    "compte d'appels seul dirait donc l'inverse de\nla vérité, et c'est pourquoi les "
    "deux moitiés de la mesure nº7 sont écrites ensemble.\nLes deux campagnes de l'étape "
    "15 sont chiffrées côte à côte dans leur comparaison."
)
"""L'autre phrase écrite une seule fois, pour la même raison que `PROVENANCE`.

⚠️ **Elle ne cite aucun total, et c'est délibéré.** Elle accompagne les cinq documents,
dont trois n'ont pas de coût publiable ; des chiffres appartenant à deux autres campagnes,
posés à côté de cellules qui disent « non disponible », se liraient comme ceux du document
qu'on a sous les yeux. Elle dit donc le phénomène et renvoie à l'endroit où les deux jeux
sont à l'écran ensemble."""


@dataclass(frozen=True, slots=True)
class Cout:
    """Ce que l'enregistrement d'un jeu a consommé, rapporté à ses tours client."""

    usage: Usage
    """Le cumul des `entete.usage` des prises mesurées. `USAGE_NUL` si aucune n'en porte.

    ⚠️ **Il porte l'`Usage` entier, et non le seul compte d'appels comme jusqu'à l'étape
    16.** `Usage.__add__` existait déjà et `mesurer_le_jeu()` lisait déjà chaque en-tête :
    ce qui manquait n'était pas la plomberie, c'était la décision de publier — voir le
    correctif en tête de module."""

    prises: int
    """Combien de prises ont été mesurées — le dénominateur de `prises_sans_usage`."""

    prises_sans_usage: int
    """Combien d'entre elles n'ont pas d'`usage` dans leur en-tête. Une seule suffit à
    rendre le coût non publiable ; voir la règle du tout ou rien, en tête de module."""

    tours: int
    """Les tours client de ces mêmes prises — `Mesures.tours`, qui porte déjà ce compte."""

    @property
    def appels(self) -> int:
        """Somme des appels au modèle des prises mesurées. Le numérateur de `par_tour`."""
        return self.usage.appels

    @property
    def entree_facturee(self) -> int:
        """**Ce qui se paie en entrée** : l'entrée hors cache, plus le cache écrit.

        ⚠️ **Le cache lu n'y entre pas**, et ce n'est pas une omission : il est facturé à un
        tarif différent, et l'ajouter ici fabriquerait un total que personne ne doit à
        personne. Il est publié à côté, où il dit ce qu'il dit — que l'arbitrage 7 produit
        son effet.
        """
        return self.usage.jetons_entree + self.usage.cache_ecrit

    @property
    def jetons_publiables(self) -> bool:
        """Toutes les prises mesurées portent `usage`, et il y en a au moins une.

        C'est la règle du tout ou rien, **et rien de plus** : les totaux de jetons sont des
        sommes, pas des ratios, et ils n'ont donc pas besoin d'un dénominateur. C'est la
        seule chose qui les sépare de `publiable`.
        """
        return self.prises > 0 and self.prises_sans_usage == 0

    @property
    def publiable(self) -> bool:
        """Toutes les prises portent `usage`, et il y a de quoi diviser."""
        return self.jetons_publiables and self.tours > 0

    @property
    def par_tour(self) -> float | None:
        """Les appels au modèle par tour client, ou `None` quand le coût n'est pas
        publiable. **Jamais un chiffre partiel** — voir la règle du tout ou rien."""
        return self.appels / self.tours if self.publiable else None

    def en_ligne(self) -> str:
        """La cellule du tableau : le chiffre, ou la raison de son absence.

        La raison est nommée, jamais un tiret : « non disponible » sans dénombrement
        laisserait croire à une mesure ratée là où il s'agit de cassettes plus anciennes
        que le champ `usage`.
        """
        if self.prises == 0:
            return "non disponible — aucune prise mesurée"
        if self.prises_sans_usage:
            return (
                f"non disponible — {self.prises_sans_usage} prise(s) sur {self.prises} sans `usage`"
            )
        if self.tours == 0:
            return "non disponible — aucun tour client mesuré"
        return (
            f"{self.appels} appel(s) sur {self.tours} tour(s) — "
            f"{self.appels / self.tours:.2f} appel/tour"
        )

    def en_ligne_entree(self) -> str:
        """La cellule des jetons d'entrée : ce qui se paie, et le cache lu à côté.

        Les deux nombres sont dans la **même** cellule et séparés par un point-virgule, pas
        additionnés : un lecteur qui les verrait sur deux lignes d'un tableau de coûts les
        sommerait, et la somme ne veut rien dire.
        """
        if (absence := self._absence()) is not None:
            return absence
        return (
            f"{_milliers(self.entree_facturee)} facturés "
            f"({_milliers(self.usage.jetons_entree)} hors cache "
            f"+ {_milliers(self.usage.cache_ecrit)} de cache écrit) ; "
            f"{_milliers(self.usage.cache_lu)} lus du cache, à un autre tarif"
        )

    def en_ligne_sortie(self) -> str:
        """La cellule des jetons de sortie. Rien à décomposer : il n'y a qu'un compteur."""
        if (absence := self._absence()) is not None:
            return absence
        return f"{_milliers(self.usage.jetons_sortie)} jetons"

    def _absence(self) -> str | None:
        """La raison pour laquelle aucun jeton n'est publié, ou `None` s'il y en a.

        Elle est la même que celle des appels, **moins** le cas du dénominateur : un total
        de jetons ne divise rien. Écrite ici plutôt que recopiée dans les deux cellules.
        """
        if self.prises == 0:
            return "non disponible — aucune prise mesurée"
        if self.prises_sans_usage:
            return (
                f"non disponible — {self.prises_sans_usage} prise(s) sur {self.prises} sans `usage`"
            )
        return None


def _milliers(nombre: int) -> str:
    """`367832` → `367 832`. L'espace fine du français, en espace ordinaire.

    Une espace insécable serait plus juste typographiquement et invisible dans un `git
    diff` : ces fichiers se relisent en diff, et un caractère qu'on ne voit pas ne se
    relit pas.
    """
    return f"{nombre:,}".replace(",", " ")
