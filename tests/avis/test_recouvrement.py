"""L'appariement par recouvrement — le seuil, et ce qu'il fusionne à tort.

Purs : ni base, ni conteneur, ni clé, ni réseau.

⚠️ **Ces tests sont écrits sur les clés RÉELLEMENT collectées à l'étape 28**, pas sur des
exemples inventés pour la démonstration. C'est ce qui les rend capables de tomber : un
seuil déplacé casse une paire qu'on a vraiment observée, pas une paire choisie pour
l'illustrer.
"""

import pytest

from raiyon.avis.normalisation import (
    SEUIL_RECOUVREMENT,
    meilleure_correspondance,
    normaliser,
    recouvrement,
)

# --------------------------------------------------------------------------- #
# Le jeu de clés du relevé 3.4 — observé, pas inventé
# --------------------------------------------------------------------------- #

RECLAMEES = {
    "joueurs": "dalle IPS vs VA pour jouer avis joueurs",
    "gamers": "dalle IPS vs VA pour jouer avis gamers",
    "trois_produits": (
        "MSI MAG 274CQF vs LG 27GP750-B vs Asus TUF Gaming VG279QM1A avis retours d'usage"
    ),
}
SEED = {
    "ips_va": "dalle IPS ou VA pour jouer",
    "asus_avis": "Asus TUF Gaming VG279QM1A avis",
    "asus_defauts": "Asus VG279QM1A defauts",
    "asrock": "ASRock Phantom Gaming PG27FRS1A avis",
}


def cle(nom: str, source: dict[str, str]) -> str:
    return normaliser(source[nom])


class TestLeSeuil:
    """Les quatre paires qui l'ont placé, chacune avec son verdict."""

    @pytest.mark.parametrize("variante", ["joueurs", "gamers"])
    def test_les_quasi_doublons_passent_le_seuil(self, variante):
        """0,556 — deux formulations du même besoin, à un mot près.

        C'est le cas que le relevé 3.4 a produit **deux fois**, avec deux mots différents
        (« joueurs » puis « gamers »). Sans appariement, c'étaient deux recherches payées
        pour une, et deux entrées de cache qui cassent la comparabilité.
        """
        score = recouvrement(cle(variante, RECLAMEES), cle("ips_va", SEED))

        assert score >= SEUIL_RECOUVREMENT
        assert score == pytest.approx(0.556, abs=0.001)

    def test_deux_questions_differentes_sur_le_meme_produit_ne_fusionnent_pas(self):
        """🔴 **La paire qui borne le seuil par le bas** — 0,333.

        « avis » et « défauts » sur le même écran sont deux questions distinctes : la
        première demande une appréciation générale, la seconde ce qu'on lui reproche. Les
        fusionner servirait une réponse à l'autre question **sans que personne ne le voie**.
        """
        score = recouvrement(cle("asus_avis", SEED), cle("asus_defauts", SEED))

        assert score < SEUIL_RECOUVREMENT
        assert score == pytest.approx(0.333, abs=0.001)

    def test_la_requete_a_trois_produits_ne_sapparie_a_rien(self):
        """⚠️ **Sous le seuil, et c'est correct** — ce n'est pas au cache de la rattraper.

        Une recherche d'avis qui nomme trois écrans est mauvaise **en soi**, quelle que
        soit la façon dont on l'apparie : aucune page d'avis ne traite trois références à
        la fois. C'est un défaut de produit, corrigé dans la description de l'outil, pas
        dans l'appariement.
        """
        candidats = [cle(nom, SEED) for nom in SEED]

        assert meilleure_correspondance(cle("trois_produits", RECLAMEES), candidats) is None

    def test_le_seuil_est_dans_la_fenetre_que_les_donnees_dessinent(self):
        """La fenêtre `]0,333 ; 0,556]`, constatée plutôt qu'affirmée dans une docstring."""
        assert 0.333 < SEUIL_RECOUVREMENT <= 0.556


class TestLappariement:
    """`meilleure_correspondance()` : ce qu'elle rend, et ce qu'elle refuse."""

    def test_une_cle_identique_se_rend_elle_meme(self):
        candidats = [cle(nom, SEED) for nom in SEED]

        assert meilleure_correspondance(cle("asrock", SEED), candidats) == cle("asrock", SEED)

    def test_le_quasi_doublon_est_servi_par_la_bonne_entree(self):
        candidats = [cle(nom, SEED) for nom in SEED]

        trouvee = meilleure_correspondance(cle("joueurs", RECLAMEES), candidats)

        assert trouvee == cle("ips_va", SEED)

    def test_aucun_candidat_ne_rend_rien(self):
        assert meilleure_correspondance("avis ecran", []) is None

    def test_sous_le_seuil_rend_none_et_pas_la_moins_mauvaise(self):
        """⚠️ **Il n'existe pas de « correspondance approximative acceptable » par défaut.**

        En dessous du seuil il y a un miss — bruyant hors ligne, et une vraie recherche en
        ligne. Rendre la moins mauvaise serait servir des avis hors sujet en silence, ce
        que tout ce jalon existe pour éviter.
        """
        assert (
            meilleure_correspondance("avis carte graphique", ["dalle ips jouer ou pour va"]) is None
        )

    def test_le_departage_a_score_egal_est_deterministe(self):
        """Sinon deux exécutions comparées serviraient des avis différents.

        L'ordre des candidats vient de la base ; sans règle explicite, il déciderait. La
        règle est « la plus courte », et elle se vérifie en présentant les candidats dans
        les deux sens.
        """
        candidats = ["avis ecran gaming", "avis ecran gaming pas cher"]

        premier = meilleure_correspondance("avis ecran", candidats)
        second = meilleure_correspondance("avis ecran", list(reversed(candidats)))

        assert premier == second == "avis ecran gaming"


class TestLeRecouvrement:
    """La fonction elle-même, sur ses bords."""

    def test_deux_cles_identiques_recouvrent_entierement(self):
        assert recouvrement("avis ecran", "avis ecran") == 1.0

    def test_deux_cles_disjointes_ne_recouvrent_pas(self):
        assert recouvrement("avis ecran", "carte graphique") == 0.0

    def test_deux_cles_vides_ne_recouvrent_pas(self):
        """⚠️ `0.0` et non `1.0` : une clé vide n'est pas une clé.

        La faire recouvrir tout le monde serait le pire comportement possible — elle
        servirait n'importe quel groupe à n'importe quelle requête.
        """
        assert recouvrement("", "") == 0.0

    def test_une_cle_vide_ne_recouvre_rien(self):
        assert recouvrement("", "avis ecran") == 0.0

    def test_la_repetition_dun_jeton_ne_change_rien(self):
        """Cohérent avec la clé : `normaliser()` déduplique déjà."""
        assert recouvrement("avis avis ecran", "avis ecran") == 1.0

    def test_le_recouvrement_est_symetrique(self):
        une, autre = "avis dalle ips va", "dalle ips jouer ou pour va"

        assert recouvrement(une, autre) == recouvrement(autre, une)
