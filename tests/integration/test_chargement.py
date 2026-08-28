"""Chargement du seed committé en base — `make seed`. Nécessite un Postgres joignable.

Marqueur `integration`, donc hors de `make check` et lancés par `make test-int`.

Ce qu'ils vérifient et qu'aucun test unitaire ne peut voir : que les ~1 000 produits
du seed entrent réellement dans le schéma de l'étape 4, que les `Decimal` et les clés
de `specs` reviennent à l'identique après l'aller-retour JSONB, et que **deux
exécutions laissent la table dans le même état** — l'idempotence est la propriété qui
autorise à relancer `make seed` sans réfléchir.

Ils tournent, eux aussi, **sans aucun appel API** : depuis le retrait de la passe B
(§3.4ter), le chargement n'a plus rien à fusionner et la table plus aucune colonne
générée.
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from raiyon.catalogue.chargement import charger_en_base
from raiyon.catalogue.pipeline import FICHIER_SEED, lire_seed
from raiyon.catalogue.schemas import CATEGORIES, ProduitEnBase
from raiyon.db.models import Produit

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def seed() -> list[ProduitEnBase]:
    """Le seed committé, revalidé. Portée module : il est relu une fois pour tous."""
    if not FICHIER_SEED.is_file():
        pytest.skip(f"{FICHIER_SEED} est absent — lancer `make seed-build`.")
    return lire_seed(FICHIER_SEED)


def test_le_seed_complet_entre_en_base(session: Session, seed):
    supprimes, inseres = charger_en_base(session, seed)
    session.flush()

    assert supprimes == 0  # la table est vide au début de chaque test
    assert inseres == len(seed)
    assert session.scalar(select(func.count()).select_from(Produit)) == len(seed)


def test_les_six_categories_sont_en_base(session: Session, seed):
    charger_en_base(session, seed)
    session.flush()
    presentes = set(session.scalars(select(Produit.categorie).distinct()))
    assert presentes == set(CATEGORIES)


def test_un_produit_relu_rend_ses_decimaux_et_ses_specs_a_lidentique(session: Session, seed):
    """L'aller-retour JSONB ne doit rien changer, pas même une décimale de queue.

    Les `Decimal` transitent en **chaînes** dans le JSONB (décision de l'étape 4) : un
    flottant JSON ne rendrait pas `0.087` à l'identique. Ce test est ce qui empêche
    quelqu'un de « simplifier » cette sérialisation un jour.
    """
    attendu = next(p for p in seed if p.categorie == "internal-hard-drive")
    charger_en_base(session, [attendu])
    session.flush()
    session.expunge_all()

    relu = session.get(Produit, attendu.id)
    assert relu is not None
    assert relu.prix_usd == attendu.prix_usd
    assert str(relu.prix_usd) == str(attendu.prix_usd)  # `numeric(10,2)`, précision comprise
    assert relu.specs == attendu.specs_pour_base()
    assert relu.marque == attendu.marque
    assert relu.nom == attendu.nom


def test_la_categorie_nest_pas_dupliquee_dans_le_jsonb(session: Session, seed):
    charger_en_base(session, seed[:5])
    session.flush()
    for ligne in session.scalars(select(Produit)):
        assert "categorie" not in ligne.specs


def test_une_seconde_execution_laisse_la_table_dans_le_meme_etat(session: Session, seed):
    """Idempotence : `DELETE` puis insertion, dans la même transaction."""
    charger_en_base(session, seed)
    session.flush()
    premier_compte = session.scalar(select(func.count()).select_from(Produit))
    premiers_ids = sorted(session.scalars(select(Produit.id)))

    supprimes, inseres = charger_en_base(session, seed)
    session.flush()

    assert supprimes == len(seed)
    assert inseres == len(seed)
    assert session.scalar(select(func.count()).select_from(Produit)) == premier_compte
    assert sorted(session.scalars(select(Produit.id))) == premiers_ids


def test_aucun_attribut_en_base_nest_hors_de_sa_plage_declaree(session: Session, seed):
    """La porte de sortie de l'étape 5, vérifiée sur ce qui est réellement en base.

    Relire chaque ligne à travers `ProduitEnBase` rejoue toutes les bornes du schéma
    de l'étape 4 — y compris les cohérences croisées `type`/`rpm` et
    `capacite_totale_gb`, qu'aucune contrainte SQL ne porte.
    """
    charger_en_base(session, seed)
    session.flush()
    session.expunge_all()

    for ligne in session.scalars(select(Produit)):
        ProduitEnBase(
            id=ligne.id,
            nom=ligne.nom,
            marque=ligne.marque,
            categorie=ligne.categorie,  # type: ignore[arg-type]
            prix_usd=ligne.prix_usd,
            disponible=ligne.disponible,
            specs=ligne.specs,  # type: ignore[arg-type]
        )


def test_aucune_colonne_generee_ne_subsiste_dans_la_table(session: Session, seed):
    """La migration `0002` a retiré `nom_fr` et `description` (§3.4ter).

    Le mapping SQLAlchemy ne les connaît plus, ce qui ne prouve rien sur la base : une
    colonne oubliée par la migration survivrait sans qu'aucun test unitaire la voie.
    C'est cette table-là qu'on inspecte, pas le modèle Python.
    """
    charger_en_base(session, seed[:1])
    session.flush()
    colonnes = {colonne["name"] for colonne in inspect(session.get_bind()).get_columns("produits")}
    assert "nom_fr" not in colonnes
    assert "description" not in colonnes
    # Contre-épreuve : sans elle, ce test passerait aussi sur une table absente.
    assert {"id", "nom", "marque", "categorie", "prix_usd", "specs"} <= colonnes


def test_les_prix_sont_tous_positifs_en_base(session: Session, seed):
    charger_en_base(session, seed)
    session.flush()
    minimum = session.scalar(select(func.min(Produit.prix_usd)))
    assert minimum is not None and minimum > Decimal(0)
