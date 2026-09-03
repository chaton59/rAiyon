"""La garde de contamination à l'enregistrement, et le coût par tour. **Purs.**

Étape 15, jalon 0, points C et D. Ni base, ni clé, ni conteneur : la garde lit des
fichiers JSON dans un répertoire, et le coût est une division. Les deux sont dans
`make check` pour cette raison.

⚠️ **Le jeu vide passe, et c'est un cas testé, pas un oubli.** La garde ne couvre pas la
**première** campagne d'un jeu — le répertoire est vide, il n'y a rien à comparer. Ce qui
couvre ce cas est le tir d'essai du jalon 4. Le test ci-dessous fixe ce comportement pour
que personne ne le « corrige » en croyant réparer un trou : le trou est connu, écrit, et
couvert ailleurs.
"""

import pytest

from eval import (  # scripts/ sur le pythonpath
    ORCHESTRATION_IMPLICITE,
    OrchestrationMelangee,
    verifier_lorchestration,
)
from raiyon.agent.client import USAGE_NUL, Usage
from raiyon.eval.cassette import Cassette, EnTete, en_json
from raiyon.eval.cout import Cout

USAGE_V2 = Usage(
    appels=191, jetons_entree=358_088, jetons_sortie=46_285, cache_ecrit=9_744, cache_lu=1_851_360
)
"""Les chiffres réels de la campagne `v2`, sommés sur ses 36 en-têtes.

Écrits une fois : les mêmes servent au ratio, aux jetons et à la règle du tout ou rien, et
trois jeux de nombres inventés rendraient les trois tests indépendants d'une même vérité."""

USAGE_PARTIEL = Usage(
    appels=18, jetons_entree=30_000, jetons_sortie=4_000, cache_ecrit=900, cache_lu=120_000
)
"""Ce que porteraient les 3 prises de `v1-base` qui ont un `usage`. **Aucun de ces nombres
ne doit apparaître dans un rapport** — c'est ce que le tout ou rien garantit."""


def poser(repertoire, nom, orchestration):
    """Écrit une cassette minimale portant — ou non — le champ `orchestration`."""
    repertoire.mkdir(parents=True, exist_ok=True)
    cassette = Cassette(
        entete=EnTete(
            scenario=nom,
            prise=1,
            modele="claude-sonnet-5",
            prompt_version="systeme.v2",
            prompt_empreinte="aaaaaaaaaaaa",
            outils_empreinte="bbbbbbbbbbbb",
            enregistree_le="2026-09-03",
            orchestration=orchestration,
        ),
        prises=(),
    )
    (repertoire / f"{nom}.1.json").write_text(en_json(cassette), encoding="utf-8")


# --------------------------------------------------------------------------- #
# La garde — les trois cas
# --------------------------------------------------------------------------- #


def test_un_jeu_vide_passe_et_cest_langle_mort_assume(tmp_path):
    """**Ce que la garde ne protège pas**, et il faut que ce soit écrit quelque part.

    La première campagne d'un jeu est l'enregistrement le plus cher du projet et le plus
    susceptible de partir avec la mauvaise variable — et c'est exactement celui que la
    garde ne voit pas. Elle n'est pas plus large qu'elle n'en a l'air ; le tir d'essai du
    jalon 4 est le mécanisme complémentaire, pas un doublon qu'on peut sauter.
    """
    verifier_lorchestration(tmp_path / "systeme.machine.v1", "machine.v1", "machine")


def test_un_jeu_homogene_passe(tmp_path):
    """Réenregistrer dans un jeu de même orchestration est le cas normal."""
    repertoire = tmp_path / "systeme.v2"
    poser(repertoire, "budget_serre", "agent")
    poser(repertoire, "hors_catalogue", "agent")

    verifier_lorchestration(repertoire, "v2", "agent")


def test_un_jeu_melange_est_refuse_en_nommant_les_deux_valeurs(tmp_path):
    """Le message nomme le jeu, les deux valeurs et la variable à poser — même forme que
    les messages de péremption d'empreinte, qui donnent la commande à taper."""
    repertoire = tmp_path / "systeme.v2"
    poser(repertoire, "budget_serre", "agent")

    with pytest.raises(OrchestrationMelangee) as erreur:
        verifier_lorchestration(repertoire, "v2", "machine")

    message = str(erreur.value)
    assert "v2" in message
    assert "agent" in message and "machine" in message
    assert "RAIYON_ORCHESTRATION" in message


def test_une_cassette_sans_champ_compte_comme_un_agent(tmp_path):
    """La lecture datée du 3 septembre 2026 : les soixante-dix-neuf cassettes du dépôt
    sont antérieures à l'étape 15 et viennent toutes de la boucle d'agent.

    Elle est faite **ici**, à l'usage, et pas dans `EnTete` — voir
    `test_une_cassette_sans_orchestration_reste_a_none_et_nest_pas_ecrite`.
    """
    repertoire = tmp_path / "systeme.v1-etape12"
    poser(repertoire, "budget_serre", None)

    verifier_lorchestration(repertoire, "v1-etape12", ORCHESTRATION_IMPLICITE)

    with pytest.raises(OrchestrationMelangee):
        verifier_lorchestration(repertoire, "v1-etape12", "machine")


# --------------------------------------------------------------------------- #
# Le coût par tour — la règle du tout ou rien
# --------------------------------------------------------------------------- #


def test_le_cout_se_publie_quand_toutes_les_prises_portent_leur_usage():
    """Les chiffres réels de la campagne v2 : 191 appels pour 81 tours client.

    Le dénominateur est `Mesures.tours`, c'est-à-dire les tours **effectivement joués** au
    rejeu — 81, soit exactement les tours scriptés des onze scénarios. Ce n'est pas le
    nombre d'appels au modèle : un tour en vaut plus d'un dès que l'agent outille."""
    cout = Cout(usage=USAGE_V2, prises=36, prises_sans_usage=0, tours=81)

    assert cout.publiable
    assert cout.par_tour == pytest.approx(2.358, abs=1e-3)
    assert "2.36 appel/tour" in cout.en_ligne()


def test_une_seule_prise_sans_usage_supprime_le_chiffre():
    """⚠️ **Tout ou rien, jamais une moyenne sur un sous-ensemble.**

    `v1-base` porte 3 prises avec `usage` sur 31. Une moyenne calculée sur ces trois-là et
    comparée aux 36 de `v2` comparerait des **tailles d'échantillon** — la faute que
    `docs/eval/LISEZMOI.md` interdit déjà pour les totaux.
    """
    cout = Cout(usage=USAGE_PARTIEL, prises=31, prises_sans_usage=28, tours=95)

    assert not cout.publiable
    assert cout.par_tour is None
    ligne = cout.en_ligne()
    assert "non disponible" in ligne
    assert "28 prise(s) sur 31" in ligne
    assert "18" not in ligne, "aucun chiffre de coût ne doit fuir dans la ligne d'absence"


def test_un_jeu_sans_aucune_prise_le_dit_plutot_que_de_diviser_par_zero():
    """Le cas ne se produit pas sur le chemin de `make eval` — un jeu sans prise lève
    `CassetteAbsente` avant. Il est fixé ici pour que la propriété soit une propriété du
    type, et non une conséquence de l'ordre des appels chez son seul appelant."""
    vide = Cout(usage=USAGE_NUL, prises=0, prises_sans_usage=0, tours=0)

    assert vide.par_tour is None
    assert "aucune prise" in vide.en_ligne()
    assert "aucune prise" in vide.en_ligne_entree()


# --------------------------------------------------------------------------- #
# Les jetons — étape 16, jalon 2
# --------------------------------------------------------------------------- #


def test_lentree_facturee_est_lentree_hors_cache_plus_le_cache_ecrit():
    """⚠️ **Le cache lu n'y entre pas, et c'est toute la mesure.** Il est facturé à un autre
    tarif ; l'additionner ferait un total que personne ne doit à personne — 2,2 millions de
    jetons pour une campagne qui en a payé 368 mille."""
    cout = Cout(usage=USAGE_V2, prises=36, prises_sans_usage=0, tours=81)

    assert cout.entree_facturee == 367_832
    assert cout.entree_facturee == USAGE_V2.jetons_entree + USAGE_V2.cache_ecrit
    assert USAGE_V2.cache_lu > 5 * cout.entree_facturee, (
        "le cache lu doit rester d'un ordre de grandeur qui rendrait la somme absurde — "
        "c'est ce qui donne son sens à la séparation"
    )


def test_la_cellule_des_jetons_donne_le_facture_sa_decomposition_et_le_cache_a_cote():
    """Les deux nombres sont dans la **même** cellule, jamais sur deux lignes d'un tableau
    de coûts : un lecteur les sommerait, et la somme ne veut rien dire."""
    ligne = Cout(usage=USAGE_V2, prises=36, prises_sans_usage=0, tours=81).en_ligne_entree()

    assert "367 832 facturés" in ligne
    assert "358 088 hors cache" in ligne
    assert "9 744 de cache écrit" in ligne
    assert "1 851 360 lus du cache" in ligne
    assert "autre tarif" in ligne


def test_les_jetons_suivent_la_meme_regle_du_tout_ou_rien_que_les_appels():
    """⚠️ **Elle ne s'assouplit pas pour faire apparaître un chiffre.** `v1-base` porte 3
    prises avec `usage` sur 31 : ses jetons sont aussi partiels que ses appels, et une somme
    partielle comparée à une somme complète compare deux tailles d'échantillon."""
    cout = Cout(usage=USAGE_PARTIEL, prises=31, prises_sans_usage=28, tours=95)

    assert not cout.jetons_publiables
    for cellule in (cout.en_ligne_entree(), cout.en_ligne_sortie()):
        assert "non disponible" in cellule
        assert "28 prise(s) sur 31" in cellule
        assert "30 000" not in cellule and "120 000" not in cellule


def test_un_jeu_sans_tour_publie_ses_jetons_et_tait_le_seul_ratio():
    """La seule chose qui sépare `jetons_publiables` de `publiable` : un total de jetons ne
    divise rien, donc il n'a pas besoin d'un dénominateur.

    Le cas ne se produit pas sur le chemin de `make eval` — un jeu dont toutes les prises
    ont divergé lève avant. Il est fixé ici pour que la distinction soit une propriété du
    type, et non une conséquence de l'ordre des appels chez son seul appelant.
    """
    cout = Cout(usage=USAGE_V2, prises=36, prises_sans_usage=0, tours=0)

    assert cout.jetons_publiables and not cout.publiable
    assert cout.par_tour is None
    assert "aucun tour client" in cout.en_ligne()
    assert "367 832 facturés" in cout.en_ligne_entree()
