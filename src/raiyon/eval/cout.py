"""Le coût d'enregistrement d'un jeu — la mesure nº7. **Pur, et de provenance gelée.**

Ce module existe pour **une seule raison**, et elle tient dans un mot : la provenance.

Tout ce que porte `Mesures` est **recalculé à chaque rejeu** par le vrai moteur, la vraie
couche outils et le vrai validateur — c'est l'arbitrage A de l'étape 12, et c'est ce qui
fait qu'un scoring qui change se voit sans rien réenregistrer. Le coût, lui, est **figé à
l'enregistrement** : il se lit dans `entete.usage.appels`, il ne bougera plus jamais, et
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
"""

from dataclasses import dataclass

PROVENANCE = (
    "⚠️ **La mesure nº7 ne vient pas du rejeu.** C'est la seule ligne de ce fichier qui "
    "soit lue\ndans l'en-tête des cassettes plutôt que recalculée : elle est **figée à "
    "l'enregistrement** et ne\nbougera pas quand le moteur, le scoring ou le validateur "
    "changeront. Les autres chiffres, si."
)
"""La phrase que le rapport et la comparaison publient à côté du chiffre. **Écrite une
fois**, parce qu'une provenance expliquée à un seul des deux endroits laisse l'autre lire
le nombre comme les siens."""


@dataclass(frozen=True, slots=True)
class Cout:
    """Ce que l'enregistrement d'un jeu a consommé, rapporté à ses tours client."""

    appels: int
    """Somme des `entete.usage.appels` des prises mesurées. `0` si aucune n'en porte."""

    prises: int
    """Combien de prises ont été mesurées — le dénominateur de `prises_sans_usage`."""

    prises_sans_usage: int
    """Combien d'entre elles n'ont pas d'`usage` dans leur en-tête. Une seule suffit à
    rendre le coût non publiable ; voir la règle du tout ou rien, en tête de module."""

    tours: int
    """Les tours client de ces mêmes prises — `Mesures.tours`, qui porte déjà ce compte."""

    @property
    def publiable(self) -> bool:
        """Toutes les prises portent `usage`, et il y a de quoi diviser."""
        return self.prises > 0 and self.prises_sans_usage == 0 and self.tours > 0

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
