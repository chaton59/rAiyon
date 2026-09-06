"""Le décor des tests d'avis : un dépôt en mémoire, et de quoi fabriquer un `Avis`.

Vit à la racine de `tests/` — comme `produits_de_test.py` et `outils_de_test.py` — parce
que trois répertoires en ont besoin : `tests/avis/`, `tests/tools/` et `tests/validateur/`.
Un conftest ne s'importe pas depuis un autre.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from raiyon.avis.cache import SOURCE_FABRIQUE, Avis, EtatCache, Lecture, est_perime
from raiyon.avis.normalisation import normaliser

QUAND = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
"""L'horodatage par défaut. Fixe : deux exécutions doivent produire le même décor."""


def avis_fabrique(
    marqueur: str,
    *,
    requete: str = "avis ecran",
    titre: str | None = None,
    extrait: str | None = None,
    produit_id: str | None = None,
) -> Avis:
    """Un avis `fabrique` — donc qui ne périme jamais, comme ceux du seed."""
    return Avis(
        requete_normalisee=normaliser(requete),
        url=f"https://exemple-fixtures.invalid/{marqueur}",
        titre=titre if titre is not None else f"Titre {marqueur}",
        extrait=extrait if extrait is not None else f"Extrait fabriqué {marqueur}.",
        source=SOURCE_FABRIQUE,
        recupere_le=QUAND,
        produit_id=produit_id,
    )


class DepotAvisEnMemoire:
    """Un `DepotAvis` sans base, pour les tests purs de la couche outils.

    ⚠️ **Il applique la même règle de péremption que `DepotAvisSql`**, en appelant
    `est_perime()` — la fonction réelle, pas une copie. Un faux dépôt qui réimplémenterait
    la règle testerait la copie, et le jour où les deux divergeraient c'est le faux qui
    resterait vert.

    C'est aussi la forme qu'aurait le repli « cache en mémoire vivant le temps d'un tour »
    si le plan à droits de stockage se révélait déraisonnable.
    """

    def __init__(self, ttl_heures: int = 24) -> None:
        from datetime import timedelta

        self._ttl = timedelta(hours=ttl_heures)
        self.groupes: dict[str, tuple[Avis, ...]] = {}
        self.ecritures: list[str] = []
        """Les clés écrites, dans l'ordre — pour constater qu'un hit n'écrit rien."""

    def charger(self, avis: Sequence[Avis]) -> None:
        """Pré-charge le dépôt, comme `make seed` pré-charge la table."""
        for un_avis in avis:
            cle = un_avis.requete_normalisee
            self.groupes[cle] = (*self.groupes.get(cle, ()), un_avis)

    def lire(self, requete_normalisee: str, *, maintenant: datetime) -> Lecture:
        groupe = self.groupes.get(requete_normalisee)
        if groupe is None:
            return Lecture((), EtatCache.ABSENT)
        if any(est_perime(un_avis, maintenant=maintenant, ttl=self._ttl) for un_avis in groupe):
            return Lecture((), EtatCache.PERIME)
        return Lecture(tuple(sorted(groupe, key=lambda un_avis: un_avis.url)), EtatCache.TROUVE)

    def ecrire(self, requete_normalisee: str, avis: Sequence[Avis]) -> tuple[Avis, ...]:
        self.ecritures.append(requete_normalisee)
        self.groupes[requete_normalisee] = tuple(avis)
        return tuple(avis)
