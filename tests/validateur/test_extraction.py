"""Ce qu'on sait lire dans une phrase. Aucun contexte, aucun catalogue : des chaînes.

Le test le plus important du fichier est `test_un_point_decimal_ne_coupe_pas_une_phrase` :
sans cette exception, « 417.14 $ » se lirait « 417 » puis « 14 $ », et la règle 2
comparerait des montants qui n'ont jamais été écrits. Le découpage en phrases est une
heuristique — c'est écrit au §7 — mais celle-là n'est pas négociable.
"""

from decimal import Decimal

import pytest

from raiyon.validateur.extraction import (
    canonique,
    en_decimal,
    identifiants,
    jetons,
    montants,
    nombres,
    phrases,
    ressemble,
    sans_les_noms,
    unites_connues,
    valeurs_unitaires,
)

# --------------------------------------------------------------------------- #
# Phrases
# --------------------------------------------------------------------------- #


def test_le_decoupage_separe_sur_le_point_le_point_dexclamation_et_la_ligne():
    assert phrases("Un. Deux ! Trois ?\nQuatre") == ("Un", "Deux", "Trois", "Quatre")


def test_un_point_decimal_ne_coupe_pas_une_phrase():
    """**Le test qui empêche la faute la plus coûteuse du module.**

    Un `split(".")` naïf transformerait « le X est à 417.14 $ » en deux phrases, dont la
    seconde — « 14 $ » — ne nommerait plus aucun produit. La règle 2 comparerait alors
    14 à la liste des agrégats et crierait sur une phrase correcte.
    """
    assert phrases("Le X est à 417.14 $.") == ("Le X est à 417.14 $",)


def test_un_point_dans_une_reference_ne_coupe_pas_non_plus():
    """`M.2-2280` est une valeur du catalogue, pas deux phrases.

    ⚠️ Effet de bord assumé de l'exception : un point **final** collé à un chiffre
    (« il est à 144. ») n'est pas une fin de phrase non plus. Le contexte de phrase est
    alors trop large d'un caractère, jamais trop étroit — aucune règle n'en dépend.
    """
    assert phrases("Le format est M.2-2280, en 1 To. Il tient.") == (
        "Le format est M.2-2280, en 1 To",
        "Il tient",
    )


# --------------------------------------------------------------------------- #
# Nombres
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("144", "144"),
        ("417.14", "417.14"),
        ("417,14", "417,14".replace(",", ".")),
        ("1 299,99", "1299.99"),
        ("1.299,99", "1299.99"),
        ("1,299.99", "1299.99"),
        ("1,299", "1299"),
    ],
)
def test_les_deux_separateurs_decimaux_se_lisent(texte, attendu):
    """Le modèle écrit en français, `en_tool_result()` sérialise en anglais."""
    assert en_decimal(texte) == Decimal(attendu)


def test_un_texte_qui_nest_pas_un_nombre_rend_none():
    assert en_decimal("beaucoup") is None


@pytest.mark.parametrize(("valeur", "attendu"), [("27", "27"), ("27.00", "27"), ("20", "20")])
def test_la_forme_canonique_ecrit_un_meme_nombre_dune_seule_facon(valeur, attendu):
    """`Decimal.normalize()` seul rendrait `2E+1` pour 20 — l'index deviendrait faux."""
    assert canonique(Decimal(valeur)) == attendu


# --- Les six formes du correctif de l'étape 17 ------------------------------ #
#
# `NOMBRE` traitait l'espace comme un séparateur de milliers sans regarder ce qui
# précédait : « 1920x1080 180 Hz » se lisait **1 080 180 Hz**, et la règle 5 levait un
# `valeur_non_fournie` sur une phrase exacte. Ces six formes ont servi à valider la
# rédaction du correctif avant qu'elle soit écrite au §7 ; elles sont ici pour la rendre
# opposable. Les quatre premières sont la non-régression, les deux suivantes le défaut.
#
# ⚠️ **Ces six-là ne suffisent pas, et c'est ce que l'étape 17 a découvert** : elles
# lisent le motif **nu**, où le défaut se répare avec la seule alternance. Le septième
# test est dans la section « Valeurs unitaires » — il lit un motif **composé**, et c'est
# le seul qui aurait attrapé le faux positif.


def test_un_millier_separe_par_une_espace_reste_un_seul_nombre():
    r"""`1 299,99` est un prix, pas `1` suivi de `299,99`. C'est ce que le `*` achetait,
    et ce que la rédaction évidente `\d{1,3}(?:[ESPACES]\d{3})*` aurait perdu."""
    assert nombres("1 299,99") == (Decimal("1299.99"),)


def test_un_entier_de_quatre_chiffres_reste_entier():
    r"""`9333` est une valeur du catalogue. Sous `\d{1,3}(?:…)*` elle se lirait `933`
    puis `3` — deux nombres qu'aucune prose n'a écrits."""
    assert nombres("9333") == (Decimal("9333"),)


def test_un_decimal_ne_se_coupe_pas_sur_son_point():
    assert nombres("417.14") == (Decimal("417.14"),)


def test_un_entier_court_se_lit_seul():
    assert nombres("144") == (Decimal("144"),)


def test_une_resolution_collee_a_une_frequence_fait_trois_nombres():
    """**Le défaut corrigé.** Deux des six griefs de la campagne v2 venaient de là
    (`categorie_efface_budget.3`) : le validateur réclamait `1 080 180 Hz` au catalogue."""
    assert nombres("en 1920x1080 180 Hz") == (
        Decimal("1920"),
        Decimal("1080"),
        Decimal("180"),
    )


def test_deux_nombres_de_quatre_chiffres_cote_a_cote_restent_deux():
    r"""La forme nue du défaut, sans la résolution autour : un séparateur de milliers ne
    suit jamais un groupe de quatre chiffres. Sous `\d{1,3}(?:…)*` on lirait `108` puis
    `0 180`."""
    assert nombres("1080 180") == (Decimal("1080"), Decimal("180"))


# --------------------------------------------------------------------------- #
# Identifiants
# --------------------------------------------------------------------------- #


def test_un_identifiant_se_reconnait_dans_une_phrase_francaise():
    assert identifiants("Je vous propose le monitor-0000000001, il est très bien.") == (
        "monitor-0000000001",
    )


def test_une_categorie_a_tiret_ne_casse_pas_la_reconnaissance():
    assert identifiants("le internal-hard-drive-00ff00ff00 convient") == (
        "internal-hard-drive-00ff00ff00",
    )


def test_aucun_mot_francais_ne_ressemble_a_un_identifiant():
    """C'est ce que le format synthétique de l'étape 5 achetait : zéro faux positif."""
    assert identifiants("Un écran de 27 pouces, à 144 Hz, sous 400 dollars.") == ()


# --------------------------------------------------------------------------- #
# Montants
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "texte", ["249,99 $", "249.99 $", "249,99 dollars", "249.99 USD", "249,99$"]
)
def test_un_montant_se_lit_dans_toutes_ses_ecritures(texte):
    assert [montant.valeur for montant in montants(texte)] == [Decimal("249.99")]


def test_un_prix_au_gigaoctet_nest_pas_un_montant():
    """`USD/Go` est une unité de spec (`price_per_gb`), pas un prix de produit.

    Sans la garde négative sur `USD`, la règle 2 réclamerait qu'un prix au gigaoctet
    soit le prix d'un produit — et lèverait un grief sur une caractéristique exacte.
    """
    assert montants("il est à 0,10 USD/Go") == ()


def test_un_entier_nu_nest_pas_un_montant():
    """L'exemption assumée du §7, constatée plutôt que supposée."""
    assert montants("je vous propose trois modèles") == ()


# --------------------------------------------------------------------------- #
# Valeurs unitaires
# --------------------------------------------------------------------------- #


def test_les_unites_viennent_du_registre():
    """Dérivées, pas recopiées : une unité ajoutée au catalogue entre toute seule."""
    connues = unites_connues()
    assert {"Hz", "Go", "pouces", "GHz", "W"} <= connues
    assert "USD" not in connues, "un prix est l'affaire de la règle 2, pas de la règle 5"


def test_un_nombre_suivi_dune_unite_est_lu_avec_son_unite():
    lues = valeurs_unitaires("un 27 pouces à 144 Hz")
    assert [(valeur.valeur, valeur.unite) for valeur in lues] == [
        (Decimal("27"), "pouces"),
        (Decimal("144"), "Hz"),
    ]


def test_une_unite_collee_a_un_mot_nest_pas_une_unite():
    """`12 Gold` n'est pas une capacité. La borne de droite refuse une lettre."""
    assert valeurs_unitaires("l'édition 12 Gold") == ()


def test_une_resolution_suivie_dune_frequence_ne_donne_quune_valeur_unitaire():
    r"""**Le faux positif de la campagne v2, pris là où il mordait vraiment.**

    ⚠️ Le test jumeau sur `nombres()` ne suffit pas, et c'est la découverte de l'étape 17 :
    le motif nu se lit d'un bout à l'autre du texte et ne redémarre jamais au milieu d'un
    chiffre, alors que `MOTIF_UNITE` **exige une unité derrière**. Quand la lecture échoue
    au `1` de `1080`, le moteur réessaie plus loin et retombe dans le nombre — sans la
    garde `(?<!\d)`, l'alternance seule lisait `080 180 Hz`, soit le même grief sur une
    autre valeur inventée."""
    lues = valeurs_unitaires("en 1920x1080 180 Hz")
    assert [(valeur.valeur, valeur.unite) for valeur in lues] == [(Decimal("180"), "Hz")]


def test_les_abreviations_anglaises_ne_sont_pas_des_unites():
    """⚠️ Décision assumée : `16 GB` apparaît dans des **noms** de produits du catalogue,
    et §3.4ter exige de les citer verbatim. Les déclarer unités ferait crier la règle 5
    sur le comportement exact qu'on réclame."""
    assert valeurs_unitaires("Corsair Vengeance LPX 16 GB") == ()


# --------------------------------------------------------------------------- #
# Noms — le verbatim et sa contrefaçon
# --------------------------------------------------------------------------- #


def test_un_nom_cite_verbatim_disparait_du_reste():
    reste = sans_les_noms("Le Samsung Odyssey G50A est parfait.", ["Samsung Odyssey G50A"])
    assert "Samsung" not in reste


def test_un_nom_francise_ressemble_au_nom_du_catalogue():
    """« l'Odyssée de Samsung » pour `Samsung Odyssey G50A` — le cas qui motive la règle."""
    assert ressemble("Samsung Odyssey G50A", "Samsung", jetons("L'Odyssée de Samsung"))


def test_la_marque_seule_ne_suffit_jamais_a_accuser_un_nom():
    """Sans cette garde, « les deux Samsung » accuserait chaque Samsung du catalogue."""
    assert not ressemble("Samsung Odyssey G50A", "Samsung", jetons("les deux Samsung"))


def test_un_mot_francais_courant_ne_ressemble_a_aucun_nom():
    """Le garde-fou de faux positif : « trois modèles » n'est pas une contrefaçon."""
    assert not ressemble("Samsung Odyssey G50A", "Samsung", jetons("trois modèles proposés"))
