"""Le seed d'avis committé — le pendant de `test_seed_committe` pour `avis.jsonl`.

Ces tests ne portent pas sur du code, ils portent sur **le fichier**. Ils tournent sans
base, sans conteneur et sans clé, donc dans `make check` : les fixtures sont relues et
revalidées à chaque exécution de la suite, pas seulement le jour où on les écrit.

⚠️ **C'est le fichier du dépôt dont la revalidation vaut le plus cher**, exactement à
l'inverse de l'intuition. Il est écrit **à la main** — c'est sa raison d'être — donc c'est
celui où une faute de frappe, une accolade oubliée ou un `produit_id` recopié de travers
ont le plus de chances d'entrer. Le catalogue, lui, est généré.
"""

import json

import pytest

from raiyon.avis.cache import SOURCE_FABRIQUE
from raiyon.avis.chargement import FICHIER_SEED_AVIS, lire_seed_avis
from raiyon.avis.normalisation import normaliser
from raiyon.avis.schemas import AvisEnSeed
from raiyon.catalogue.pipeline import FICHIER_SEED, lire_seed
from raiyon.db.models import EXTRAIT_MAX_CARACTERES


@pytest.fixture(scope="module")
def avis() -> list[AvisEnSeed]:
    """Le seed d'avis committé, relu et **revalidé** ligne à ligne."""
    return lire_seed_avis()


@pytest.fixture(scope="module")
def identifiants_du_catalogue() -> set[str]:
    """Les `id` du catalogue committé. **Les deux fichiers se croisent sans base.**"""
    return {produit.id for produit in lire_seed(FICHIER_SEED)}


def test_le_seed_davis_existe_et_nest_pas_vide(avis):
    """Un cache pré-chargé vide est un cache qui ne sert jamais.

    Le symptôme d'un fichier disparu serait une campagne qui ne trouve aucun avis — sans
    erreur, sans message. Le constater ici coûte une milliseconde.
    """
    assert avis, f"{FICHIER_SEED_AVIS.name} ne porte aucune fixture"


def test_chaque_produit_cite_existe_dans_le_catalogue(avis, identifiants_du_catalogue):
    """🔴 **Le défaut le plus probable de ce fichier, et il est silencieux en base.**

    Un `produit_id` recopié de travers ne fait pas échouer `make seed` : `charger_avis_en_base`
    écarte la ligne et l'imprime en avertissement — délibérément, pour ne pas faire payer au
    catalogue la faute d'un avis. L'avertissement se lit une fois et s'oublie ; ce test, lui,
    tombe à chaque `make check`.
    """
    cites = {fixture.produit_id for fixture in avis if fixture.produit_id is not None}

    inconnus = sorted(cites - identifiants_du_catalogue)

    assert not inconnus, (
        f"{FICHIER_SEED_AVIS.name} cite des produits absents du catalogue : {inconnus}"
    )


def test_aucune_ligne_ne_declare_sa_source(avis):
    """⚠️ **La garde contre la redistribution, vérifiée sur le fichier.**

    `AvisEnSeed` interdit le champ (`extra="forbid"`) et `en_avis()` pose `fabrique` en
    dur : toute ligne du seed est fabriquée par construction. Ce test le constate sur le
    JSONL lui-même, parce que c'est le fichier qui part au dépôt public — et que le §3(b)
    des conditions Brave interdit de redistribuer des résultats de recherche.
    """
    lignes = [
        json.loads(ligne)
        for ligne in FICHIER_SEED_AVIS.read_text(encoding="utf-8").splitlines()
        if ligne.strip()
    ]

    porteuses = [ligne for ligne in lignes if "source" in ligne]

    assert not porteuses, (
        "une ligne du seed déclare une `source`. Le seed est fabriqué, jamais récupéré : "
        "y laisser entrer un résultat de recherche réel en ferait une redistribution."
    )


def test_toutes_les_fixtures_sont_marquees_fabriquees_une_fois_construites(avis):
    """La contre-épreuve du test précédent : l'absence du champ donne bien `fabrique`."""
    assert {fixture.en_avis().source for fixture in avis} == {SOURCE_FABRIQUE}


def test_chaque_requete_produit_une_cle_non_vide(avis):
    """Une clé vide rangerait toutes les fixtures sous la même entrée.

    `AvisEnSeed` le refuse déjà à la validation ; ce test constate qu'aucune ligne n'a
    trouvé le chemin qui contourne — et il documente la contrainte à l'endroit où on
    écrit les fixtures.
    """
    assert all(normaliser(fixture.requete) for fixture in avis)


def test_une_url_nest_jamais_citee_deux_fois_sous_la_meme_requete(avis):
    """La contrainte `UNIQUE (requete_normalisee, url)` refuserait le doublon en base.

    Le laisser au chargement rendrait le symptôme tardif — `make seed` échouerait sur un
    message de contrainte, sans nommer la ligne. Ici, il nomme la clé.
    """
    vues = [(normaliser(fixture.requete), fixture.url) for fixture in avis]

    doublons = sorted({paire for paire in vues if vues.count(paire) > 1})

    assert not doublons, f"{FICHIER_SEED_AVIS.name} porte des doublons (requête, url) : {doublons}"


def test_aucun_extrait_ne_depasse_la_borne(avis):
    """Le schéma le refuse à la validation ; on le constate sur le contenu réel.

    Sans ce test, on saurait que la borne est **tenable**, pas qu'elle est **tenue** — et
    une fixture tronquée en base ne se lit pas dans le fichier.
    """
    assert all(len(fixture.extrait) <= EXTRAIT_MAX_CARACTERES for fixture in avis)


def test_les_urls_de_fixture_ne_pointent_sur_aucun_domaine_reel():
    """⚠️ **`.invalid` est réservé par la RFC 2606 : ces URL ne résoudront jamais.**

    Une fixture qui porterait une URL réelle inviterait à l'ouvrir pour « vérifier », et
    ferait croire que l'extrait vient de cette page — alors qu'il est écrit à la main. Le
    domaine réservé rend la fabrication visible à la lecture, sans commentaire.
    """
    lignes = [
        json.loads(ligne)
        for ligne in FICHIER_SEED_AVIS.read_text(encoding="utf-8").splitlines()
        if ligne.strip()
    ]

    hors_reserve = [ligne["url"] for ligne in lignes if ".invalid/" not in ligne["url"]]

    assert not hors_reserve, (
        f"des fixtures pointent hors du domaine réservé : {hors_reserve}. "
        "Une URL réelle ferait croire que l'extrait vient de cette page."
    )
