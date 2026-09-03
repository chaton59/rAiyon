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
from raiyon.eval.cassette import Cassette, EnTete, en_json
from raiyon.eval.cout import Cout


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
    cout = Cout(appels=191, prises=36, prises_sans_usage=0, tours=81)

    assert cout.publiable
    assert cout.par_tour == pytest.approx(2.358, abs=1e-3)
    assert "2.36 appel/tour" in cout.en_ligne()


def test_une_seule_prise_sans_usage_supprime_le_chiffre():
    """⚠️ **Tout ou rien, jamais une moyenne sur un sous-ensemble.**

    `v1-base` porte 3 prises avec `usage` sur 31. Une moyenne calculée sur ces trois-là et
    comparée aux 36 de `v2` comparerait des **tailles d'échantillon** — la faute que
    `docs/eval/LISEZMOI.md` interdit déjà pour les totaux.
    """
    cout = Cout(appels=18, prises=31, prises_sans_usage=28, tours=95)

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
    assert Cout(appels=0, prises=0, prises_sans_usage=0, tours=0).par_tour is None
    assert "aucune prise" in Cout(appels=0, prises=0, prises_sans_usage=0, tours=0).en_ligne()
