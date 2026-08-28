"""Le seed committé lui-même — test anti-régression du livrable de l'étape 5.

Ces tests ne portent pas sur du code : ils portent sur `data/seed/produits.jsonl`, le
fichier que `make seed` charge en base. Ils tournent **sans base et sans clé API**,
donc dans `make check`, ce qui est le point : le catalogue est relu et revalidé à
chaque exécution de la suite, pas seulement le jour où on le régénère.

Une modification à la main du JSONL, un conflit de merge mal résolu, une régénération
avec une graine différente — les trois se voient ici, en quelques millisecondes.
"""

import json
from decimal import Decimal

import pytest

from raiyon.catalogue.pipeline import FICHIER_RAPPORT, FICHIER_SEED, lire_seed
from raiyon.catalogue.schemas import CATEGORIES, MOTIF_ID, ProduitEnBase
from raiyon.catalogue.selection import CIBLE_PAR_CATEGORIE

VOLUME_ATTENDU = (900, 1100)
"""~1 000 produits (§3.1). La fourchette laisse la place aux repêchages G1, G2 et G4,
qui peuvent porter une catégorie quelques produits au-dessus de la cible : 6 x 170 =
1 020 tirés, plus au plus 6 repêchages G4 et quelques-uns pour G1 et G2."""


@pytest.fixture(scope="module")
def seed() -> list[ProduitEnBase]:
    """Le seed committé, relu et **revalidé** ligne à ligne par `ProduitEnBase`."""
    if not FICHIER_SEED.is_file():
        pytest.fail(f"{FICHIER_SEED} est absent — lancer `make seed-build`.")
    return lire_seed(FICHIER_SEED)


def test_chaque_ligne_du_jsonl_revalide_par_produit_en_base(seed):
    """`lire_seed` échoue sur la première ligne invalide : arriver ici suffit."""
    assert seed


def test_le_volume_est_celui_annonce(seed):
    bas, haut = VOLUME_ATTENDU
    assert bas <= len(seed) <= haut


def test_les_six_categories_sont_presentes_et_aucune_autre(seed):
    presentes = {produit.categorie for produit in seed}
    assert presentes == set(CATEGORIES)


def test_chaque_categorie_approche_la_cible(seed):
    for categorie in CATEGORIES:
        effectif = sum(1 for produit in seed if produit.categorie == categorie)
        assert CIBLE_PAR_CATEGORIE <= effectif <= CIBLE_PAR_CATEGORIE + 10, categorie


def test_les_identifiants_sont_uniques(seed):
    identifiants = [produit.id for produit in seed]
    assert len(identifiants) == len(set(identifiants))


def test_les_identifiants_sont_bien_formes(seed):
    import re

    motif = re.compile(MOTIF_ID)
    for produit in seed:
        assert motif.match(produit.id), produit.id
        assert produit.id.startswith(f"{produit.categorie}-")


def test_le_fichier_est_trie_par_id(seed):
    """Le tri est ce qui rend le diff git lisible quand un seul produit change."""
    identifiants = [produit.id for produit in seed]
    assert identifiants == sorted(identifiants)


def test_tous_les_prix_sont_strictement_positifs(seed):
    assert all(produit.prix_usd > Decimal(0) for produit in seed)


def test_toutes_les_marques_sont_renseignees(seed):
    """La marque est dérivée du premier mot de `name` (§3.4quater), jamais absente."""
    assert all(produit.marque.strip() for produit in seed)


def test_aucun_disque_du_seed_na_de_type_inconnu(seed):
    """Les 8 lignes sans `type` ont été écartées, c'est une décision de l'étape 5."""
    disques = [p for p in seed if p.categorie == "internal-hard-drive"]
    assert disques
    assert all(p.specs.type is not None for p in disques)  # type: ignore[union-attr]


CHAMPS_ATTENDUS = {"categorie", "disponible", "id", "marque", "nom", "prix_usd", "specs"}
"""Les sept clés d'une ligne du JSONL, et **aucune autre**.

`nom_fr` et `description` y figuraient, à `null`, en attendant la passe LLM. Le test
ci-dessous est ce qui empêche un champ généré d'y revenir sans décision (§3.4ter)."""


def test_une_ligne_ne_porte_que_les_champs_factuels(seed):
    """Aucun champ généré dans le JSONL — la liste est fermée, pas indicative.

    `ProduitEnBase` est en `extra="forbid"`, donc une clé inconnue ferait déjà échouer
    la relecture. Ce test attrape l'autre sens : une clé **ajoutée au modèle**, qui
    passerait la validation en silence. C'est par là qu'un champ généré rentrerait.
    """
    for numero, ligne in enumerate(FICHIER_SEED.read_text(encoding="utf-8").splitlines(), 1):
        assert set(json.loads(ligne)) == CHAMPS_ATTENDUS, f"ligne {numero}"
    assert {champ for produit in seed for champ in produit.model_dump()} == CHAMPS_ATTENDUS


def test_la_categorie_nest_pas_dupliquee_dans_les_specs():
    """Deux copies d'un même fait peuvent diverger — la règle vaut aussi pour le JSONL."""
    premiere = FICHIER_SEED.read_text(encoding="utf-8").splitlines()[0]
    assert "categorie" not in json.loads(premiere)["specs"]


def test_le_rapport_de_seed_est_committe():
    """C'est un livrable de l'étape, pas une sortie de console."""
    assert FICHIER_RAPPORT.is_file()
    contenu = FICHIER_RAPPORT.read_text(encoding="utf-8")
    for section in ("## Entonnoir", "### G1", "### G2", "### G3", "### G4", "price_per_gb"):
        assert section in contenu


def _g4_du_rapport() -> dict[str, tuple[str, Decimal]]:
    """Lit le tableau G4 du rapport committé : catégorie → (`id`, prix).

    Le rapport est relu, pas régénéré : c'est ce qui rend ce test capable de détecter
    une régénération du seed sans mise à jour du rapport, et l'inverse.
    """
    lignes = FICHIER_RAPPORT.read_text(encoding="utf-8").splitlines()
    debut = lignes.index("### G4 — haut de gamme")
    trouves: dict[str, tuple[str, Decimal]] = {}
    for ligne in lignes[debut:]:
        colonnes = [c.strip() for c in ligne.split("|")[1:-1]]
        if len(colonnes) != 4 or not colonnes[0].startswith("`"):
            continue
        categorie = colonnes[0].strip("`")
        if categorie in CATEGORIES:
            trouves[categorie] = (colonnes[1].strip("`"), Decimal(colonnes[2].removesuffix(" USD")))
    return trouves


def test_le_produit_le_plus_cher_de_chaque_categorie_est_celui_annonce_par_g4(seed):
    """**Le test qui garde le correctif G4 contre une régénération distraite.**

    La stratification par décile perd les extrêmes : sans G4, le plus cher des
    moniteurs du seed valait 2 699 USD contre 9 333 USD à la source. Si une
    régénération future faisait à nouveau disparaître le haut de gamme, ce test
    tomberait au lieu de laisser le catalogue s'appauvrir en silence.
    """
    annonces = _g4_du_rapport()
    assert set(annonces) == set(CATEGORIES)

    for categorie, (identifiant, prix) in annonces.items():
        du_seed = [p for p in seed if p.categorie == categorie]
        le_plus_cher = max(du_seed, key=lambda p: (p.prix_usd, p.id))
        assert le_plus_cher.prix_usd == prix, categorie
        assert any(p.id == identifiant and p.prix_usd == prix for p in du_seed), categorie
