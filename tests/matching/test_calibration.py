"""Les constantes du registre sont-elles bien celles que le script redonne ?

Le script est rejouable, son résultat est du **code** — et c'est cette égalité qui
l'empêche de devenir un cache. Modifier une borne à la main casse ce test, ce qui est
le comportement voulu : une borne qui ne sort pas de la mesure n'a rien à faire là.
"""

from decimal import Decimal

import pytest

from raiyon.catalogue.pipeline import FICHIER_SEED, lire_seed
from raiyon.matching.attributs import BORNES_CALIBREES, PLAFONDS_RATIO


@pytest.fixture(scope="module")
def seed():
    if not FICHIER_SEED.is_file():
        pytest.skip(f"{FICHIER_SEED} est absent — lancer `make seed-build`.")
    return lire_seed(FICHIER_SEED)


def test_les_bornes_du_registre_sont_celles_du_seed_committe(seed):
    from calibrer_bornes import calibrer_bornes

    assert calibrer_bornes(seed) == BORNES_CALIBREES


def test_les_plafonds_de_ratio_du_registre_sont_ceux_du_seed_committe(seed):
    from calibrer_bornes import calibrer_plafonds_ratio

    assert calibrer_plafonds_ratio(seed) == PLAFONDS_RATIO


def test_les_plafonds_ne_couvrent_que_les_categories_sans_prix_au_gigaoctet(seed):
    """Ailleurs, la source donne déjà le rapport : un plafond y serait du code mort."""
    assert set(PLAFONDS_RATIO) == {"cpu", "monitor", "video-card", "headphones"}


def test_le_percentile_prend_une_valeur_reellement_observee():
    """Rang le plus proche, pas d'interpolation : la borne existe au catalogue."""
    from calibrer_bornes import percentile

    valeurs = [Decimal(n) for n in (1, 2, 3, 4, 100)]
    assert percentile(valeurs, 95) == Decimal(100)
    assert percentile(valeurs, 5) == Decimal(1)
    assert percentile(valeurs, 50) == Decimal(3)
