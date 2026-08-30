"""Le registre est-il fidèle à ses deux sources ? `schemas.py` et le rapport de seed.

Ces tests sont la contrepartie de l'arbitrage C : le registre est écrit à la main
depuis `catalogue/schema_attributs.md`, donc il **peut** diverger. Ce qui l'en empêche
n'est pas l'attention de qui l'écrit, c'est ce fichier.
"""

import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

from raiyon.catalogue.pipeline import FICHIER_SEED, lire_seed
from raiyon.catalogue.schemas import CATEGORIES, ProduitEnBase, Specs
from raiyon.matching.attributs import (
    ATTRIBUTS,
    COMPLET,
    Genre,
    Role,
    champs_a_compter,
    champs_incomplets,
    valeur_du_produit,
)

RAPPORT_SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "rapport_seed.md"

CHAMPS_COMMUNS = set(ProduitEnBase.model_fields) - {"specs"}


@pytest.fixture(scope="module")
def seed():
    """Le seed committé, relu et revalidé. Aucune base, aucun réseau."""
    if not FICHIER_SEED.is_file():
        pytest.skip(f"{FICHIER_SEED} est absent — lancer `make seed-build`.")
    return lire_seed(FICHIER_SEED)


def champs_de_specs(categorie):
    """Les champs du modèle Pydantic de cette catégorie, discriminateur exclu.

    `categorie` vit dans les specs pour rendre l'union discriminée possible, mais
    `specs_pour_base()` la retire avant l'écriture : elle n'est pas un attribut du
    JSONB, elle a sa colonne.
    """
    (modele,) = [
        variante
        for variante in Specs.__args__[0].__args__  # type: ignore[attr-defined]
        if variante.model_fields["categorie"].annotation.__args__[0] == categorie
    ]
    return set(modele.model_fields) - {"categorie"}


@pytest.mark.parametrize("categorie", CATEGORIES)
def test_le_registre_couvre_exactement_les_champs_du_schema(categorie):
    """Ni oubli, ni champ fantôme — et les champs `affichage` comptent.

    `color` figure au registre **avec son rôle** plutôt qu'omis : c'est ce qui permet
    de prouver qu'il ne filtre ni ne score, au lieu de constater qu'on l'a oublié.
    """
    assert set(ATTRIBUTS[categorie]) == champs_de_specs(categorie) | CHAMPS_COMMUNS


@pytest.mark.parametrize("categorie", CATEGORIES)
def test_tout_attribut_numerique_a_des_bornes_et_un_sens(categorie):
    """Un attribut scorable sans bornes ferait lever le calcul au premier client."""
    for attribut in ATTRIBUTS[categorie].values():
        if attribut.genre is not Genre.NUMERIQUE:
            continue
        assert attribut.borne_basse is not None, f"{categorie}.{attribut.champ}"
        assert attribut.borne_haute is not None, f"{categorie}.{attribut.champ}"
        assert attribut.borne_basse < attribut.borne_haute, f"{categorie}.{attribut.champ}"
        assert attribut.sens is not None, f"{categorie}.{attribut.champ}"


@pytest.mark.parametrize("categorie", CATEGORIES)
def test_tout_attribut_a_un_libelle_francais(categorie):
    """Le français dérivé d'un champ est de la donnée (§3.4ter), donc il est ici.

    Et c'est de la **donnée**, pas du rendu : pas de majuscule de début, pas d'article,
    pas de point final. Les sigles internes (« latence CAS », « génération DDR ») en
    sont, eux, puisqu'ils s'écrivent ainsi partout.
    """
    for attribut in ATTRIBUTS[categorie].values():
        assert attribut.libelle_fr
        assert not attribut.libelle_fr[0].isupper(), attribut.champ
        assert not attribut.libelle_fr.endswith("."), attribut.champ
        assert not attribut.libelle_fr.startswith(("le ", "la ", "les ", "un ", "une "))
        assert attribut.unite != ""


@pytest.mark.parametrize("categorie", CATEGORIES)
def test_les_unites_sont_presentes_quand_elles_existent(categorie):
    """Toute grandeur physique porte son unité : un nombre nu n'est pas une mesure."""
    sans_unite_admis = {
        "id",
        "nom",
        "marque",
        "categorie",
        "disponible",
        "microarchitecture",
        "graphics",
        "aspect_ratio",
        "panel_type",
        "form_factor",
        "interface",
        "type",
        "chipset",
        "microphone",
        "wireless",
        "enclosure_type",
        "color",
        "ddr_generation",
    }
    for champ, attribut in ATTRIBUTS[categorie].items():
        if champ in sans_unite_admis:
            continue
        assert attribut.unite, f"{categorie}.{champ} est une grandeur sans unité"


def test_la_retrogradation_est_fermee_sur_la_compatibilite():
    """« Plutôt de la DDR5 » n'est pas un souhait, c'est un malentendu (arbitrage D)."""
    fermes = {
        "ddr_generation",
        "interface",
        "form_factor",
        "type",
        "chipset",
        "microarchitecture",
        "aspect_ratio",
        "prix_usd",
        "categorie",
    }
    for categorie in CATEGORIES:
        for champ, attribut in ATTRIBUTS[categorie].items():
            if champ in fermes:
                assert not attribut.retrogradable, f"{categorie}.{champ}"


def test_la_retrogradation_ne_vise_que_des_filtres_durs_gradues():
    """La règle, et non la liste : gradué **et** filtre dur, sinon rien."""
    for categorie in CATEGORIES:
        for champ, attribut in ATTRIBUTS[categorie].items():
            if not attribut.retrogradable:
                continue
            assert attribut.role is Role.FILTRE_DUR, f"{categorie}.{champ}"
            assert attribut.genre is Genre.NUMERIQUE, f"{categorie}.{champ}"


@pytest.mark.parametrize(
    ("categorie", "champ"),
    [
        ("monitor", "screen_size"),
        ("monitor", "refresh_rate"),
        ("internal-hard-drive", "capacity"),
        ("memory", "capacite_totale_gb"),
        ("video-card", "memory"),
        ("video-card", "length"),
        ("cpu", "core_count"),
        ("cpu", "tdp"),
    ],
)
def test_les_filtres_durs_gradues_nommes_sont_bien_retrogradables(categorie, champ):
    """Les huit champs que l'arbitrage D désigne nommément."""
    assert ATTRIBUTS[categorie][champ].retrogradable


def test_la_resolution_n_est_pas_retrogradable():
    """« Du 4K » est un seuil exact, pas une approximation (`schema_attributs.md`).

    C'est la seule exception documentée à « numérique donc gradué », et elle vient de
    la source de vérité des rôles, pas d'un arbitrage du moteur.
    """
    assert not ATTRIBUTS["monitor"]["largeur_px"].retrogradable
    assert not ATTRIBUTS["monitor"]["hauteur_px"].retrogradable


def test_aucun_attribut_de_genre_texte_ne_peut_etre_score():
    """`marque` est le seul champ à saisie libre, et sa comparaison n'existe qu'en SQL.

    Tant que rien de genre `texte` n'est scorable, aucune seconde implémentation de la
    normalisation de marque n'est nécessaire côté Python (arbitrage L).
    """
    for categorie in CATEGORIES:
        for champ, attribut in ATTRIBUTS[categorie].items():
            if attribut.genre is not Genre.TEXTE:
                continue
            assert attribut.role is not Role.SCORE, f"{categorie}.{champ}"
            assert not attribut.retrogradable, f"{categorie}.{champ}"


def test_les_champs_daffichage_sont_declares_et_inertes():
    """Un champ `affichage` est au registre, avec son rôle, et sans bornes."""
    couleurs = [
        ATTRIBUTS[categorie]["color"] for categorie in ("memory", "video-card", "headphones")
    ]
    assert couleurs
    for attribut in couleurs:
        assert attribut.role is Role.AFFICHAGE
        assert not attribut.est_scorable
        assert not attribut.retrogradable


# --------------------------------------------------------------------------- #
# Les taux de remplissage viennent du rapport de seed, pas d'une estimation
# --------------------------------------------------------------------------- #


def taux_du_rapport():
    """Relit `data/seed/rapport_seed.md` et rend {catégorie: {champ: pourcentage}}.

    Le rapport est un livrable committé de l'étape 5 : le relire ici plutôt que de
    recopier ses chiffres dans le test transforme « les taux sont à jour » d'une
    intention en une vérification.
    """
    texte = RAPPORT_SEED.read_text(encoding="utf-8")
    section = texte.split("### Taux de remplissage par attribut, sur le seed final")[1]
    section = section.split("### Valeurs distinctes")[0]

    taux: dict[str, dict[str, Decimal]] = {}
    courante = None
    for ligne in section.splitlines():
        entete = re.match(r"\*\*`([a-z-]+)`\*\*", ligne)
        if entete:
            courante = entete.group(1)
            taux[courante] = {}
            continue
        cellule = re.match(r"\| `([a-z_]+)`.*?\|\s*\d+\s*\|\s*([\d.]+) %", ligne)
        if cellule and courante:
            taux[courante][cellule.group(1)] = Decimal(cellule.group(2))
    return taux


@pytest.mark.parametrize("categorie", CATEGORIES)
def test_les_taux_du_registre_sont_ceux_du_rapport_de_seed(categorie):
    """Un taux inventé rendrait le comptage des exclusions faux, et silencieusement."""
    mesures = taux_du_rapport()[categorie]
    assert set(mesures) == champs_de_specs(categorie), "le rapport a changé de forme"
    for champ, pourcentage in mesures.items():
        registre = ATTRIBUTS[categorie][champ].taux_remplissage * 100
        assert registre.quantize(Decimal("0.1")) == pourcentage, f"{categorie}.{champ}"


def test_les_colonnes_communes_sont_completes():
    """Elles sont `NOT NULL` en base : leur taux ne peut pas être autre chose que 1."""
    for categorie in CATEGORIES:
        for champ in CHAMPS_COMMUNS:
            assert ATTRIBUTS[categorie][champ].taux_remplissage == COMPLET


def filtres_durs(selection):
    """Les couples (catégorie, champ) de rôle `filtre dur` parmi une sélection."""
    return {
        (categorie, champ)
        for categorie in CATEGORIES
        for champ in selection(categorie)
        if ATTRIBUTS[categorie][champ].role is Role.FILTRE_DUR
    }


def test_trois_filtres_durs_sont_incomplets_sur_le_seed():
    """Constat de mesure. Le cadrage en annonçait deux.

    `internal-hard-drive.rpm` s'ajoute à `monitor.refresh_rate` et `video-card.length`.
    """
    assert filtres_durs(champs_incomplets) == {
        ("monitor", "refresh_rate"),
        ("video-card", "length"),
        ("internal-hard-drive", "rpm"),
    }


def test_seuls_deux_dentre_eux_se_comptent_comme_donnee_manquante():
    """`rpm` est incomplet, mais aucun de ses trous n'est une donnée manquante.

    Son taux de 33,9 % vaut la part de HDD du seed : un SSD n'a pas de vitesse de
    rotation. Le compter ferait dire au diagnostic « ces disques ne déclarent pas leur
    vitesse », alors que la vérité est « ce sont des SSD, ils n'en ont pas ». Le moteur
    n'a pas le droit de fabriquer une affirmation fausse sur le catalogue (§2).
    """
    assert filtres_durs(champs_a_compter) == {
        ("monitor", "refresh_rate"),
        ("video-card", "length"),
    }
    assert "rpm" in champs_incomplets("internal-hard-drive")
    assert "rpm" not in champs_a_compter("internal-hard-drive")


# --------------------------------------------------------------------------- #
# L'absence structurelle se vérifie sur le seed, elle ne se décrète pas
# --------------------------------------------------------------------------- #


def presence_determinee_par(produits, categorie, champ, colonne):
    """La **présence** de `champ` est-elle une fonction de la valeur de `colonne` ?

    Vrai si, à l'intérieur de chaque groupe de `colonne`, l'attribut est soit toujours
    renseigné, soit toujours absent. C'est le critère de pose de `explique_par`, et il
    est **exécutable** : connaître `type` suffit à savoir si `rpm` existe.
    """
    groupes = defaultdict(set)
    for produit in produits:
        if produit.categorie != categorie:
            continue
        valeur = valeur_du_produit(produit, ATTRIBUTS[categorie][colonne])
        renseigne = valeur_du_produit(produit, ATTRIBUTS[categorie][champ]) is not None
        groupes[valeur].add(renseigne)
    return all(len(presences) == 1 for presences in groupes.values())


def colonnes_candidates(categorie):
    """Colonnes qui peuvent **expliquer** une absence : les vocabulaires fermés.

    Restreint aux énumérations et aux booléens à dessein. Une colonne quasi unique par
    produit — un prix, un nom — « expliquerait » n'importe quoi par construction, chaque
    groupe ne contenant qu'une ligne : ce serait un artefact de cardinalité, pas une
    explication.
    """
    return [
        champ
        for champ, attribut in ATTRIBUTS[categorie].items()
        if attribut.genre in (Genre.ENUMERE, Genre.BOOLEEN)
    ]


def test_une_absence_structurelle_est_entierement_expliquee_par_sa_colonne(seed):
    """Le drapeau n'est pas documentaire : il se vérifie sur le seed committé.

    `SpecsDisqueInterne._coherence_type_rpm` impose déjà l'équivalence à l'insertion ;
    ce test la constate sur les 1 026 lignes livrées, sans relire le validateur.
    """
    portes = [
        (categorie, champ, attribut)
        for categorie in CATEGORIES
        for champ, attribut in ATTRIBUTS[categorie].items()
        if attribut.absence_structurelle
    ]
    assert portes, "aucun attribut ne porte le drapeau — le test ne prouverait rien"

    for categorie, champ, attribut in portes:
        assert attribut.explique_par in ATTRIBUTS[categorie], f"{categorie}.{champ}"
        assert presence_determinee_par(seed, categorie, champ, attribut.explique_par), (
            f"{categorie}.{champ} n'est pas déterminé par {attribut.explique_par}"
        )


def test_un_attribut_a_absence_structurelle_est_numerique():
    """La condition du motif repose sur la **valeur atteignable**, qui n'existe que là.

    `_valeur_atteignable` ne calcule rien sur une énumération — on n'assouplit pas une
    interface par degré. Un attribut énuméré portant `explique_par` retomberait donc
    dans le défaut que le second correctif vient de fermer : son motif serait
    `absence_structurelle` sans condition. Ce test le rend impossible d'y arriver par
    inadvertance.
    """
    for categorie in CATEGORIES:
        for champ, attribut in ATTRIBUTS[categorie].items():
            if attribut.absence_structurelle:
                assert attribut.genre is Genre.NUMERIQUE, f"{categorie}.{champ}"


def test_un_attribut_seulement_correle_ne_porte_pas_le_drapeau(seed):
    """`cpu.boost_clock` est à 66,1 %, et aucune colonne ne détermine son absence.

    C'est ce qui sépare le drapeau d'une opinion sur un taux de remplissage. L'absence
    de `boost_clock` est **corrélée** à la génération — les vieux processeurs n'en ont
    pas — mais aucune valeur de `microarchitecture` ne permet de conclure, et le test le
    montre plutôt que de le raconter. C'est la ligne de partage de §3.4quater : calcul
    déterministe contre supposition.
    """
    assert not ATTRIBUTS["cpu"]["boost_clock"].absence_structurelle
    for colonne in colonnes_candidates("cpu"):
        assert not presence_determinee_par(seed, "cpu", "boost_clock", colonne), colonne


def test_aucun_autre_attribut_incomplet_ne_remplit_le_critere(seed):
    """Si un autre le remplissait, il devrait porter le drapeau — et il ne l'a pas."""
    manquants = [
        (categorie, champ, colonne)
        for categorie in CATEGORIES
        for champ in champs_incomplets(categorie)
        if not ATTRIBUTS[categorie][champ].absence_structurelle
        for colonne in colonnes_candidates(categorie)
        if champ != colonne and presence_determinee_par(seed, categorie, champ, colonne)
    ]
    assert manquants == []


def test_les_colonnes_communes_ne_sont_pas_cherchees_dans_le_jsonb():
    """Un `dans_les_specs` oublié rend zéro produit **sans erreur**.

    La containment JSONB chercherait alors `specs->'marque'`, une clé qui n'existe pas,
    et le filtre échouerait en silence. Le drapeau est donc posé par la construction du
    registre, pas recopié sur chaque entrée — et ce test garde cette construction.
    """
    for categorie in CATEGORIES:
        for champ in CHAMPS_COMMUNS:
            assert not ATTRIBUTS[categorie][champ].dans_les_specs, f"{categorie}.{champ}"
        for champ in champs_de_specs(categorie):
            assert ATTRIBUTS[categorie][champ].dans_les_specs, f"{categorie}.{champ}"
