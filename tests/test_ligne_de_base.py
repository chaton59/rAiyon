"""Ce que `scripts/ligne_de_base.py` publie et qu'il calculait sans le publier (étape 34).

Deux valeurs, un même défaut refermé : `_mesurer()` sommait `cache_lu` et `jetons_entree`,
et rien ne les rendait. C'est le motif de §9.0 — une valeur produite que personne ne lit —
dans le script qui aurait dû en être le lecteur.

---

### Les frontières du cache, colonne `cache↗`

La colonne existe pour lire **le seul point resté ouvert** de l'étape 34 : le point de coupe
mobile survit-il à l'aller-retour de l'historique par `tours_conversation` ? Elle répond
`9/9` si oui, `0/9` si non, et les deux sont des gains — mais pas le même.

⚠️ **Un test vert n'est pas une mesure tant qu'on n'a pas vérifié qu'il savait rougir**
(§9.3). Ce fichier contient donc les deux lectures, jouées sur la **même** conversation :
les mêmes tours, les mêmes appels, seul `cache_lu` change. Sans la contre-épreuve, une
fonction qui rendrait toujours `0/n` passerait le premier test.
"""

from ligne_de_base import _frontieres_du_cache, _usage_cumule

from raiyon.agent.client import USAGE_NUL, Usage
from raiyon.db.models import AppelModele
from raiyon.eval.cout import Cout

SOCLE = 13_078
"""Le préfixe `tools` + `system`, mesuré le 2026-09-07. Écrit ici pour fabriquer les cas,
**jamais lu par la fonction** — elle le redécouvre comme le plus petit `cache_lu` non nul,
et c'est ce qui la garde juste au prochain changement de prompt."""


def appel(tour, iteration, cache_lu, entree=0, sortie=0, ecrit=0):
    return AppelModele(
        tour_client=tour,
        iteration=iteration,
        cache_lu=cache_lu,
        jetons_entree=entree,
        jetons_sortie=sortie,
        cache_ecrit=ecrit,
    )


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


# --------------------------------------------------------------------------- #
# L'entrée facturée — la seconde valeur qui se calculait sans se publier
# --------------------------------------------------------------------------- #

TROIS_APPELS = [
    appel(1, 1, cache_lu=0, entree=100, sortie=1, ecrit=10_000),
    appel(1, 2, cache_lu=10_000, entree=200, sortie=2, ecrit=0),
    appel(7, 1, cache_lu=10_000, entree=400, sortie=4, ecrit=0),
]
"""Les cinq compteurs portent des ordres de grandeur distincts **à dessein** : une fonction
qui intervertirait deux champs, ou qui n'en sommerait qu'un, rendrait un total qui ne
ressemble à aucun des attendus."""


def test_le_cumul_somme_les_cinq_compteurs():
    assert _usage_cumule(TROIS_APPELS) == Usage(
        appels=3, jetons_entree=700, jetons_sortie=7, cache_ecrit=10_000, cache_lu=20_000
    )


def test_le_cumul_distingue_deux_conversations():
    """⭐ La contre-épreuve : une fonction qui rendrait toujours la même chose — le neutre,
    le premier appel, un compte d'appels seul — passerait le test précédent par accident sur
    un jeu mal choisi. Elle ne passe pas celui-ci."""
    plus_courte = _usage_cumule(TROIS_APPELS[:2])

    assert plus_courte != _usage_cumule(TROIS_APPELS)
    assert plus_courte != USAGE_NUL
    assert plus_courte.appels == 2


def test_aucun_appel_rend_le_neutre():
    """Et c'est ce qui rend atteignable la branche « aucun appel persisté » du script :
    zéro appel n'est pas zéro dépense, c'est un tour qui n'a rien commité (arbitrage 9)."""
    assert _usage_cumule([]) == USAGE_NUL


def _cout(appels):
    return Cout(usage=_usage_cumule(appels), prises=1, prises_sans_usage=0, tours=2)


def test_lentree_facturee_est_celle_du_depot():
    """🔴 **Le test qui compte de cette moitié.** La définition n'est pas réécrite dans le
    script, elle est **exécutée** — et c'est cette propriété-là qu'on vérifie, pas
    l'arithmétique de `Cout`, qui a ses propres tests dans `tests/eval/`."""
    assert _cout(TROIS_APPELS).entree_facturee == 700 + 10_000


def test_le_cache_lu_nentre_pas_dans_lentree_facturee():
    """⭐ La contre-épreuve de la précédente, et elle vise une faute plausible : additionner
    les trois compteurs d'entrée « pour avoir le total ». Le cache lu se paie à un autre
    tarif ; l'ajouter fabriquerait un total que personne ne doit à personne."""
    cout = _cout(TROIS_APPELS)

    assert cout.entree_facturee != cout.usage.jetons_entree + cout.usage.cache_lu
    assert cout.entree_facturee != sum(
        (cout.usage.jetons_entree, cout.usage.cache_ecrit, cout.usage.cache_lu)
    )
    assert "à un autre tarif" in cout.en_ligne_entree()


def test_la_ligne_dentree_publie_les_deux_moities_separement():
    """Le rendu du script, tel qu'il sort : le facturé décomposé, le cache lu à côté."""
    ligne = _cout(TROIS_APPELS).en_ligne_entree()

    assert ligne.startswith("10 700 facturés (700 hors cache + 10 000 de cache écrit)")
    assert "20 000 lus du cache" in ligne
