"""Sélection stratifiée et garanties de cas limites — arbitrage E de l'étape 5.

Ce que ces tests gardent : la reproductibilité à graine fixe (le seed est un fichier
committé, son diff doit rester vide quand rien ne change), la couverture des déciles
(sans elle, l'échantillon perd la queue haute des prix), et les garanties G1, G2 et
G4 — **repêchées parmi des produits réels, jamais fabriquées**.

Le tirage stratifié garde la *forme* de la distribution mais pas ses *extrêmes* : G4
existe pour ce point précis, et `test_g4_ne_retire_aucun_produit_deja_tire` est ce qui
garantit qu'elle corrige par ajout, sans toucher au tirage.
"""

from decimal import Decimal

import pytest

from raiyon.catalogue.schemas import ProduitEnBase
from raiyon.catalogue.selection import (
    NB_STRATES,
    constater_g3,
    garantir_g1,
    garantir_g2,
    garantir_g4,
    selectionner,
    selectionner_categorie,
    seuil_plausible,
)


def cpu(numero: int, prix: str) -> ProduitEnBase:
    """Un `cpu` de test dont seul le prix compte pour la stratification."""
    return ProduitEnBase(
        id=f"cpu-{numero:010x}",
        nom=f"Intel Core i{numero}",
        marque="Intel",
        categorie="cpu",
        prix_usd=Decimal(prix),
        specs={  # type: ignore[arg-type]
            "core_count": 4 + numero % 8,
            "core_clock": Decimal("3.4"),
            "tdp": 65,
            "microarchitecture": "Alder Lake",
        },
    )


def casque(numero: int, prix: str, couleur: str, micro: bool = True) -> ProduitEnBase:
    """Un `headphones` de test : la seule catégorie de ce fichier à porter un `affichage`."""
    return ProduitEnBase(
        id=f"headphones-{numero:010x}",
        nom=f"Casque {numero}",
        marque="Casque",
        categorie="headphones",
        prix_usd=Decimal(prix),
        specs={  # type: ignore[arg-type]
            "type": "Circumaural",
            "microphone": micro,
            "wireless": False,
            "enclosure_type": "Closed",
            "color": couleur,
        },
    )


CATALOGUE = [cpu(numero, str(10 + numero * 7)) for numero in range(200)]


# --------------------------------------------------------------------------- #
# Reproductibilité et couverture
# --------------------------------------------------------------------------- #


def test_le_tirage_est_reproductible_a_graine_fixe():
    """Deux exécutions donnent le même seed, au bit près — c'est un fichier committé."""
    premier, _ = selectionner_categorie("cpu", CATALOGUE, cible=50)
    second, _ = selectionner_categorie("cpu", CATALOGUE, cible=50)
    assert [p.id for p in premier] == [p.id for p in second]


def test_une_graine_differente_donne_un_echantillon_different():
    """Sans cela, le « tirage » ne tirerait rien et la graine ne servirait à rien."""
    avec, _ = selectionner_categorie("cpu", CATALOGUE, cible=50, graine=1)
    autre, _ = selectionner_categorie("cpu", CATALOGUE, cible=50, graine=2)
    assert [p.id for p in avec] != [p.id for p in autre]


def test_le_tirage_couvre_les_dix_deciles():
    """Un tirage uniforme perdrait la queue haute ; le stratifié la garde par construction."""
    _, rapport = selectionner_categorie("cpu", CATALOGUE, cible=50)
    assert len(rapport.strates) == NB_STRATES
    assert all(strate.retenus > 0 for strate in rapport.strates)


def test_la_queue_haute_des_prix_est_representee():
    tires, _ = selectionner_categorie("cpu", CATALOGUE, cible=50)
    prix_max_du_catalogue = max(p.prix_usd for p in CATALOGUE)
    assert max(p.prix_usd for p in tires) > prix_max_du_catalogue * Decimal("0.8")


def test_une_categorie_plus_petite_que_la_cible_est_prise_en_entier():
    """Le report des strates déficitaires sur les voisines ne doit pas boucler."""
    petit = CATALOGUE[:12]
    tires, _ = selectionner_categorie("cpu", petit, cible=50)
    assert len(tires) == 12


def test_les_strates_deficitaires_se_reportent_sur_les_voisines():
    """Cible atteinte malgré une strate trop petite : la place part à côté."""
    tires, rapport = selectionner_categorie("cpu", CATALOGUE, cible=101)
    assert len(tires) == 101
    assert sum(strate.retenus for strate in rapport.strates) == 101


# --------------------------------------------------------------------------- #
# G1 — budget frôlé
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("mediane", "attendu"), [("90", 100), ("169.89", 100), ("289.99", 300), ("595.35", 500)]
)
def test_le_seuil_retenu_est_un_budget_rond_quun_client_enonce(mediane, attendu):
    assert seuil_plausible([Decimal(mediane)]) == Decimal(attendu)


def test_g1_est_satisfaite_par_repechage_quand_le_tirage_ne_la_donne_pas():
    """Le produit est **repêché du pool réel**, pas fabriqué."""
    pool = [cpu(1, "50"), cpu(2, "80"), cpu(3, "110"), cpu(4, "400")]
    selection = [pool[0], pool[1], pool[3]]  # aucun dans ]100, 115]

    ajouts, cas = garantir_g1(selection, pool)
    assert [p.id for p in ajouts] == [pool[2].id]
    assert cas[0].repeche is True
    assert cas[0].seuil_usd == Decimal(100)
    assert Decimal(100) < cas[0].prix_usd <= Decimal(115)


def test_g1_ne_repeche_rien_si_le_tirage_la_satisfait_deja():
    pool = [cpu(1, "50"), cpu(2, "80"), cpu(3, "110")]
    ajouts, cas = garantir_g1(list(pool), pool)
    assert ajouts == []
    assert cas[0].repeche is False


def test_g1_ne_fabrique_rien_quand_la_source_na_rien_dans_la_zone():
    """Une garantie impossible se signale, elle ne s'invente pas."""
    pool = [cpu(1, "50"), cpu(2, "80"), cpu(3, "400")]
    ajouts, cas = garantir_g1(list(pool), pool)
    assert ajouts == []
    assert cas == []


# --------------------------------------------------------------------------- #
# G2 — départage
# --------------------------------------------------------------------------- #


def test_g2_trouve_un_couple_qui_ne_differe_que_par_le_prix_et_un_champ_daffichage():
    pool = [casque(1, "49.99", "Black"), casque(2, "59.99", "White"), casque(3, "89.99", "Red")]
    _, cas = garantir_g2(list(pool), pool)
    assert cas is not None
    assert cas.champ_affichage == "color"
    assert cas.prix_a < cas.prix_b


def test_g2_ignore_un_couple_qui_differe_par_un_filtre_dur():
    """`microphone` est un filtre dur : ces deux produits ne sont pas « quasi identiques »."""
    pool = [casque(1, "49.99", "Black", micro=True), casque(2, "59.99", "White", micro=False)]
    _, cas = garantir_g2(list(pool), pool)
    assert cas is None


def test_g2_repeche_les_deux_produits_du_couple():
    pool = [casque(1, "49.99", "Black"), casque(2, "59.99", "White"), casque(3, "89.99", "Red")]
    ajouts, cas = garantir_g2([pool[2]], pool)
    assert cas is not None and cas.repeche is True
    assert {p.id for p in ajouts} == {pool[0].id, pool[1].id}


# --------------------------------------------------------------------------- #
# G3 — zéro résultat
# --------------------------------------------------------------------------- #


def test_g3_retient_une_combinaison_dont_chaque_critere_est_bien_servi():
    """Le critère de choix fait la valeur du cas : une conjonction vide de deux
    exigences banales, pas une absurdité physique satisfaite par personne."""
    seed = [
        casque(1, "10", "Black", micro=True),
        casque(2, "20", "White", micro=True),
        casque(3, "30", "Red", micro=False),
    ]
    seed[2] = ProduitEnBase(
        id="headphones-00000000ff",
        nom="Casque ouvert",
        marque="Casque",
        categorie="headphones",
        prix_usd=Decimal("30"),
        specs={  # type: ignore[arg-type]
            "type": "In Ear",
            "microphone": False,
            "wireless": True,
            "enclosure_type": "Open",
        },
    )
    cas = constater_g3(seed)
    assert cas is not None
    # Chaque critère pris seul est servi ; leur conjonction ne l'est pas.
    assert all(effectif > 0 for effectif in cas.effectifs_isoles.values())
    assert len(cas.criteres) == 2


def test_g3_rend_none_quand_toutes_les_conjonctions_sont_servies():
    cas = constater_g3([casque(1, "10", "Black")])
    assert cas is None


# --------------------------------------------------------------------------- #
# G4 — haut de gamme
# --------------------------------------------------------------------------- #


def test_g4_repeche_le_produit_le_plus_cher_quand_le_tirage_la_manque():
    """La stratification perd les extrêmes : G4 les récupère, du pool réel."""
    pool = [cpu(1, "50"), cpu(2, "80"), cpu(3, "9333")]
    selection = [pool[0], pool[1]]  # le plus cher n'a pas été tiré

    ajouts, cas = garantir_g4(selection, pool)
    assert [p.id for p in ajouts] == [pool[2].id]
    assert len(cas) == 1
    assert cas[0].repeche is True
    assert cas[0].id_produit == pool[2].id
    assert cas[0].prix_usd == Decimal("9333")


def test_g4_najoute_rien_quand_le_plus_cher_est_deja_tire():
    """Un repêchage inutile gonflerait le seed sans rien garantir de plus."""
    pool = [cpu(1, "50"), cpu(2, "80"), cpu(3, "9333")]
    ajouts, cas = garantir_g4(list(pool), pool)
    assert ajouts == []
    assert cas[0].repeche is False
    assert cas[0].id_produit == pool[2].id


def test_g4_departage_une_egalite_de_prix_par_le_plus_petit_id():
    """Même règle de départage que G1, et deux exécutions donnent le même produit."""
    pool = [cpu(9, "500"), cpu(2, "500"), cpu(5, "100")]
    plus_petit_id = min(p.id for p in pool if p.prix_usd == Decimal("500"))

    premier, _ = garantir_g4([], pool)
    second, _ = garantir_g4([], pool)
    assert [p.id for p in premier] == [plus_petit_id]
    assert [p.id for p in premier] == [p.id for p in second]


def test_g4_produit_un_cas_par_categorie_presente():
    """Une catégorie sans cas G4 serait une catégorie sans haut de gamme."""
    resultat = selectionner(CATALOGUE, cible=30)
    assert [cas.categorie for cas in resultat.g4] == ["cpu"]
    assert resultat.g4[0].prix_usd == max(p.prix_usd for p in CATALOGUE)
    assert max(p.prix_usd for p in resultat.produits) == max(p.prix_usd for p in CATALOGUE)


def test_g4_ne_retire_aucun_produit_deja_tire():
    """Le correctif est un **ajout**, jamais une substitution : la graine ne bouge pas."""
    sans_le_plus_cher = sorted(CATALOGUE, key=lambda p: p.prix_usd)[:-1]
    avant = {p.id for p in selectionner(sans_le_plus_cher, cible=30).produits}
    apres = {p.id for p in selectionner(sans_le_plus_cher, cible=30).produits}
    assert avant == apres

    complet = {p.id for p in selectionner(CATALOGUE, cible=30).produits}
    tires_seuls, _ = selectionner_categorie("cpu", CATALOGUE, cible=30)
    assert {p.id for p in tires_seuls} <= complet


# --------------------------------------------------------------------------- #
# La sélection complète
# --------------------------------------------------------------------------- #


def test_selectionner_trie_par_id_pour_que_le_diff_git_reste_lisible():
    resultat = selectionner(CATALOGUE, cible=30)
    identifiants = [p.id for p in resultat.produits]
    assert identifiants == sorted(identifiants)
