"""La clé de cache : ce qui doit fusionner, et ce qui ne doit pas.

Purs : ni base, ni conteneur, ni clé API, ni réseau.

⚠️ **Ces tests fixent un curseur, pas une vérité.** La normalisation est un pari sur ce
que deux formulations veulent dire, et le pari est écrit dans la docstring du module
`raiyon.avis.normalisation`. Ce fichier le rend exécutable — y compris le faux positif
qu'il assume, qui a son test à lui plus bas.
"""

import pytest

from raiyon.avis.normalisation import JETONS_MAX, normaliser


class TestCeQuiDoitFusionner:
    """Les formes que le modèle produit pour une même demande."""

    def test_lordre_des_mots_ne_fait_pas_deux_cles(self):
        """⚠️ **La paire la plus fréquente de toutes**, et celle qui justifie le tri.

        Un modèle libre de formuler écrit « avis X » un tour et « X avis » le suivant. Sans
        le tri des jetons, ce serait deux entrées de cache, donc un miss sur deux.
        """
        assert normaliser("avis ASRock PG27FRS1A") == normaliser("ASRock PG27FRS1A avis")

    def test_la_casse_ne_fait_pas_deux_cles(self):
        assert normaliser("Écran Gaming") == normaliser("écran gaming")

    def test_les_accents_ne_font_pas_deux_cles(self):
        """On ne cherche pas en français accentué **et** en français nu."""
        assert normaliser("écran télé") == normaliser("ecran tele")

    def test_la_ponctuation_ne_fait_pas_deux_cles(self):
        """« Est-ce que X est bien ? » et « est ce que X est bien » sont la même demande."""
        assert normaliser("Est-ce que l'ASRock est bien ?") == normaliser(
            "est ce que l ASRock est bien"
        )

    def test_un_tiret_dans_une_reference_ne_fait_pas_deux_cles(self):
        """« i7-920 » et « i7 920 » : la source écrit l'un, le client tape souvent l'autre."""
        assert normaliser("Intel Core i7-920 avis") == normaliser("intel core i7 920 avis")

    def test_les_espaces_multiples_et_les_bords_sont_sans_effet(self):
        assert normaliser("  écran   gaming  ") == normaliser("écran gaming")

    def test_un_jeton_repete_ne_change_pas_la_cle(self):
        """« avis avis écran » n'est pas une requête différente de « avis écran »."""
        assert normaliser("avis avis écran") == normaliser("avis écran")


class TestCeQuiNeDoitPasFusionner:
    """Le curseur a une limite haute, et elle se vérifie."""

    def test_deux_produits_differents_restent_deux_cles(self):
        assert normaliser("avis ASRock PG27FRS1A") != normaliser("avis Asus VG279QM1A")

    def test_le_singulier_et_le_pluriel_restent_deux_cles(self):
        """⚠️ **Le vrai défaut de cette normalisation, et il est assumé.**

        « écran » et « écrans » sont deux clés. Le fermer demanderait une racinisation
        française, donc une dépendance linguistique, pour un gain que rien ne chiffre
        aujourd'hui. Ce test existe pour que le défaut soit **constaté** plutôt que
        découvert : si quelqu'un ajoute un jour la racinisation, c'est lui qui tombe, et
        c'est le bon endroit pour relire la décision.
        """
        assert normaliser("avis écran") != normaliser("avis écrans")

    def test_un_mot_de_plus_change_la_cle(self):
        assert normaliser("avis écran gaming") != normaliser("avis écran")

    def test_la_cle_nest_pas_tolerante_au_sous_ensemble(self):
        """🔴 **La limite qui coûtera le plus cher, constatée plutôt que découverte.**

        Le curseur est relevé sur l'**ordre** des mots, pas sur leur **nombre**. Trois
        façons de demander le même avis donnent trois clés, et le modèle formule librement :
        c'est le mode de miss le plus probable en pratique, très loin devant les collisions
        du tri.

        Trouvé en branchant l'outil sur le seed réel — « ASRock Phantom Gaming PG27FRS1A
        avis » est dans le seed, « avis ASRock PG27FRS1A » manque. La parade est un
        appariement par recouvrement, avec un seuil ; le seuil attend le chiffre que
        l'étape 28 produira en comptant les `ABSENT`, qui nomment la clé formulée.
        """
        cles = {
            normaliser("ASRock Phantom Gaming PG27FRS1A avis"),
            normaliser("avis ASRock PG27FRS1A"),
            normaliser("ASRock PG27FRS1A avis utilisateurs"),
        }

        assert len(cles) == 3


def test_le_tri_fusionne_les_comparatives_et_cest_le_pari_assume():
    """🔴 **Le faux positif nommé dans la docstring du module.**

    « A mieux que B » et « B mieux que A » deviennent la même clé alors que ce sont deux
    questions opposées. Le pari est que les pages qui répondent à l'une répondent à
    l'autre, puisqu'elles comparent les deux objets — c'est un pari, pas une preuve.

    Ce test **constate** la fusion au lieu de la découvrir en production. S'il tombe un
    jour, c'est que quelqu'un a retiré le tri, et il faudra alors relire ce que le tri
    achetait : la fusion de « avis X » et « X avis », qui est la paire la plus fréquente.
    """
    assert normaliser("AOC mieux que ASRock") == normaliser("ASRock mieux que AOC")


class TestLesBords:
    """Les entrées qui n'ont pas de clé, et celles qui en ont trop."""

    @pytest.mark.parametrize("entree", ["", "   ", "???", "!!! ...", "—"])
    def test_une_requete_sans_alphanumerique_ne_produit_aucune_cle(self, entree):
        """⚠️ **Rend `""`, et ne lève pas.**

        `normaliser()` est totale exprès : une fonction de normalisation qui lève oblige
        chaque appelant à savoir quand. Le refus d'une clé vide appartient à la couche
        outils — et la contrainte `requete_non_vide` de la table est le filet.
        """
        assert normaliser(entree) == ""

    def test_une_requete_tres_longue_est_bornee(self):
        """`JETONS_MAX` est une garde sur l'index btree, pas une règle de sens."""
        requete = " ".join(f"mot{numero}" for numero in range(JETONS_MAX * 3))

        cle = normaliser(requete)

        assert len(cle.split()) == JETONS_MAX

    def test_la_troncature_est_deterministe(self):
        """Deux fois la même requête longue donnent la même clé — les jetons sont triés."""
        requete = " ".join(f"mot{numero}" for numero in range(JETONS_MAX * 2))

        assert normaliser(requete) == normaliser(requete)

    def test_les_caracteres_non_latins_disparaissent(self):
        """Limite assumée : le catalogue est en anglais, les conversations en français."""
        assert normaliser("écran 显示器") == normaliser("écran")
