"""Les frontières du cache, colonne `cache↗` de `scripts/ligne_de_base.py` (étape 34).

La colonne existe pour lire **le seul point resté ouvert** de l'étape 34 : le point de coupe
mobile survit-il à l'aller-retour de l'historique par `tours_conversation` ? Elle répond
`9/9` si oui, `0/9` si non, et les deux sont des gains — mais pas le même.

⚠️ **Un test vert n'est pas une mesure tant qu'on n'a pas vérifié qu'il savait rougir**
(§9.3). Ce fichier contient donc les deux lectures, jouées sur la **même** conversation :
les mêmes tours, les mêmes appels, seul `cache_lu` change. Sans la contre-épreuve, une
fonction qui rendrait toujours `0/n` passerait le premier test.
"""

from ligne_de_base import _frontieres_du_cache

from raiyon.db.models import AppelModele

SOCLE = 13_078
"""Le préfixe `tools` + `system`, mesuré le 2026-09-07. Écrit ici pour fabriquer les cas,
**jamais lu par la fonction** — elle le redécouvre comme le plus petit `cache_lu` non nul,
et c'est ce qui la garde juste au prochain changement de prompt."""


def appel(tour, iteration, cache_lu):
    return AppelModele(tour_client=tour, iteration=iteration, cache_lu=cache_lu)


def conversation(lus):
    """Trois tours de deux appels ; `lus` donne le `cache_lu` de chacun, dans l'ordre."""
    tours = [(1, 1), (1, 2), (7, 1), (7, 2), (13, 1), (13, 2)]
    return [appel(t, i, lu) for (t, i), lu in zip(tours, lus, strict=True)]


def test_le_prefixe_fixe_seul_ne_tient_aucune_frontiere():
    """L'état d'avant l'étape 34 : `cache_lu` constant, le préfixe protégé ne grossit pas."""
    appels = conversation([0, SOCLE, SOCLE, SOCLE, SOCLE, SOCLE])

    assert _frontieres_du_cache(appels) == (0, 2)


def test_un_cache_qui_grossit_tient_toutes_les_frontieres():
    """⭐ La contre-épreuve, sur la même conversation : seuls les nombres changent."""
    appels = conversation([0, SOCLE, SOCLE + 700, SOCLE + 1400, SOCLE + 2000, SOCLE + 2600])

    assert _frontieres_du_cache(appels) == (2, 2)


def test_une_frontiere_qui_retombe_au_socle_ne_compte_pas():
    """Le cas mixte, et c'est celui que le dépôt s'attend le moins à savoir lire : la coupe
    tient **à l'intérieur** d'un tour et tombe **entre** deux tours."""
    appels = conversation([0, SOCLE, SOCLE, SOCLE + 700, SOCLE, SOCLE + 700])

    assert _frontieres_du_cache(appels) == (0, 2)


def test_le_socle_est_relu_et_non_suppose():
    """Un prompt plus lourd déplace le socle ; la fonction doit suivre sans qu'on la touche."""
    autre = 40_000
    appels = conversation([0, autre, autre, autre, autre + 900, autre + 1800])

    assert _frontieres_du_cache(appels) == (1, 2)


def test_le_premier_tour_na_pas_de_frontiere_devant_lui():
    """Deux tours, donc une seule frontière — pas deux."""
    appels = [appel(1, 1, 0), appel(1, 2, SOCLE), appel(7, 1, SOCLE + 500)]

    assert _frontieres_du_cache(appels) == (1, 1)


def test_une_session_dun_seul_tour_ne_rend_rien():
    """`—` à l'affichage : il n'y avait rien à observer, ce qui n'est pas un échec."""
    assert _frontieres_du_cache([appel(1, 1, 0), appel(1, 2, SOCLE)]) is None


def test_une_session_sans_cache_ne_rend_rien():
    assert _frontieres_du_cache([appel(1, 1, 0), appel(7, 1, 0)]) is None


def test_aucun_appel_ne_rend_rien():
    assert _frontieres_du_cache([]) is None
