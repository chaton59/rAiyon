"""Tests d'intégration du schéma — nécessitent un Postgres joignable (`make up`).

Marqueur `integration`, donc hors de `make check` et lancés par `make test-int`.
Ils vérifient ce qu'aucun test unitaire ne peut voir : que la migration s'applique
et se défait, que la base tient ses garanties **même si quelqu'un contourne
Pydantic**, et que les objets déclarés dans les modèles existent réellement.
"""

import uuid
from decimal import Decimal

import pytest
from alembic import command
from pydantic import ValidationError
from sqlalchemy import create_engine, delete, insert, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from raiyon.catalogue.schemas import ProduitEnBase
from raiyon.db.models import Produit, SessionConversation, TourConversation

pytestmark = pytest.mark.integration

TABLES_ATTENDUES = {"produits", "sessions", "tours_conversation"}


def produit_valide() -> ProduitEnBase:
    """Un disque dur réaliste, avec des `Decimal` et un booléen à faire revenir intacts."""
    return ProduitEnBase(
        id="internal-hard-drive-9f8e7d6c5b",
        nom="Samsung 990 Pro 2 TB",
        marque="Samsung",
        categorie="internal-hard-drive",
        prix_usd=Decimal("169.99"),
        specs={
            "capacity": 2000,
            "form_factor": "M.2-2280",
            "interface": "M.2 PCIe 4.0 X4",
            "type": "SSD",
            "price_per_gb": Decimal("0.085"),
        },
    )


def test_la_migration_sapplique_et_se_defait_entierement(base_jetable):
    """`upgrade head` puis `downgrade base` : le downgrade est vérifié, pas supposé.

    Un `downgrade()` cassé ne se voit jamais tant que personne ne le lance, et se
    découvre au pire moment - quand il faut revenir en arrière.
    """
    url, config = base_jetable
    moteur = create_engine(url)
    try:
        command.upgrade(config, "head")
        with moteur.connect() as connexion:
            tables = set(inspect(connexion).get_table_names())
        assert tables >= TABLES_ATTENDUES

        command.downgrade(config, "base")
        with moteur.connect() as connexion:
            restantes = set(inspect(connexion).get_table_names())
        # `alembic_version` survit : c'est la table de suivi d'Alembic, pas du schéma.
        assert restantes - {"alembic_version"} == set()
    finally:
        moteur.dispose()


def test_insertion_et_relecture_dun_produit(session: Session):
    """Aller-retour complet : `Decimal`, booléen et clés de `specs` reviennent identiques."""
    attendu = produit_valide()
    session.add(Produit.depuis_schema(attendu))
    session.commit()

    ligne = session.get(Produit, attendu.id)
    assert ligne is not None
    assert ligne.nom == "Samsung 990 Pro 2 TB"  # nom source, jamais traduit (§3.4ter)
    assert ligne.marque == "Samsung"
    # Le `Numeric` revient en `Decimal` exact : c'est ce qui autorise le code à
    # formater un prix sans jamais le faire transiter par un flottant (§2).
    assert ligne.prix_usd == Decimal("169.99")
    assert isinstance(ligne.prix_usd, Decimal)
    assert ligne.disponible is True
    assert ligne.cree_le is not None

    # Les `Decimal` de `specs` sont stockés en chaînes dans le JSONB. C'est le choix
    # de `specs_pour_base()` : une chaîne revient au caractère près là où un flottant
    # JSON ne le garantit pas. La relecture repasse donc par Pydantic, qui rend les
    # `Decimal` d'origine - et c'est cette voie-là que le code utilisera.
    assert ligne.specs["price_per_gb"] == "0.085"
    relu = ProduitEnBase(
        id=ligne.id,
        nom=ligne.nom,
        marque=ligne.marque,
        categorie=ligne.categorie,
        prix_usd=ligne.prix_usd,
        disponible=ligne.disponible,
        specs=ligne.specs,
    )
    assert relu == attendu


def test_un_produit_malforme_est_rejete_avant_datteindre_la_base(session: Session):
    """La première barrière est Pydantic : rien de malformé n'arrive jusqu'au SQL."""
    with pytest.raises(ValidationError):
        ProduitEnBase(
            id="internal-hard-drive-9f8e7d6c5b",
            nom="Disque impossible",
            marque="Samsung",
            categorie="internal-hard-drive",
            prix_usd=Decimal("169.99"),
            # Un SSD ne tourne pas a 7 200 tours par minute.
            specs={
                "capacity": 2000,
                "form_factor": "M.2-2280",
                "interface": "M.2 PCIe 4.0 X4",
                "type": "SSD",
                "rpm": 7200,
            },
        )
    assert session.execute(select(Produit)).first() is None


def test_un_prix_nul_est_rejete_par_la_base_meme_sans_pydantic(session: Session):
    """La garantie doit tenir si quelqu'un écrit en base sans passer par le modèle.

    L'insertion se fait ici en SQL Core, donc sans validation applicative : c'est le
    `CHECK` de la migration qui refuse, et c'est le seul filet à ce niveau-là.
    """
    with pytest.raises(IntegrityError, match="ck_produits_prix_positif"):
        session.execute(
            insert(Produit).values(
                id="cpu-3f9a2c7b1d",
                nom="Processeur gratuit",
                marque="Intel",
                categorie="cpu",
                prix_usd=Decimal("0"),
                specs={},
            )
        )


def test_une_categorie_inconnue_est_rejetee_par_la_base(session: Session):
    """`keyboard` a été retirée (§3.4bis) : la base doit la refuser, pas seulement le code."""
    with pytest.raises(IntegrityError, match="ck_produits_categorie_connue"):
        session.execute(
            insert(Produit).values(
                id="keyboard-3f9a2c7b1d",
                nom="Clavier retire du perimetre",
                marque="Logitech",
                categorie="keyboard",
                prix_usd=Decimal("92.32"),
                specs={},
            )
        )


def test_un_identifiant_mal_forme_est_rejete_par_la_base(session: Session):
    """La forme de l'ID est une contrainte SQL, pas seulement une règle Pydantic."""
    with pytest.raises(IntegrityError, match="ck_produits_forme_id"):
        session.execute(
            insert(Produit).values(
                id="ID-INVENTE-PAR-UN-LLM",
                nom="Produit imaginaire",
                marque="Acme",
                categorie="cpu",
                prix_usd=Decimal("199.99"),
                specs={},
            )
        )


def _session_avec_trois_tours(session: Session) -> SessionConversation:
    """Une conversation de trois tours, telle que l'API la persistera."""
    conversation = SessionConversation(id=uuid.uuid4(), budget_usd=Decimal("200.00"))
    session.add(conversation)
    session.flush()
    for numero, (role, blocs) in enumerate(
        [
            ("user", [{"type": "text", "text": "Je cherche un SSD de 2 To."}]),
            (
                "assistant",
                [{"type": "tool_use", "name": "search_products", "input": {"capacity": 2000}}],
            ),
            # Un `tool_result` porte le rôle `user` dans l'API Anthropic.
            (
                "user",
                [{"type": "tool_result", "content": [{"type": "text", "text": "3 produits"}]}],
            ),
        ],
        start=1,
    ):
        session.add(
            TourConversation(session_id=conversation.id, numero=numero, role=role, blocs=blocs)
        )
    session.commit()
    return conversation


def test_supprimer_une_session_supprime_ses_tours(session: Session):
    """Cascade côté base, testée sans l'aide de l'ORM.

    La suppression passe par un `DELETE` SQL direct : si la cascade n'était portée
    que par la relation SQLAlchemy, ce test échouerait - et une suppression faite en
    SQL laisserait des tours orphelins.
    """
    conversation = _session_avec_trois_tours(session)
    tours = session.execute(
        select(TourConversation).where(TourConversation.session_id == conversation.id)
    ).all()
    assert len(tours) == 3

    session.execute(delete(SessionConversation).where(SessionConversation.id == conversation.id))
    session.commit()

    restants = session.execute(
        select(TourConversation).where(TourConversation.session_id == conversation.id)
    ).all()
    assert restants == []


def test_un_numero_de_tour_en_double_est_refuse(session: Session):
    """L'ordre des tours est une donnée : un doublon rendrait la relecture ambiguë."""
    conversation = _session_avec_trois_tours(session)
    session.add(
        TourConversation(
            session_id=conversation.id,
            numero=1,
            role="user",
            blocs=[{"type": "text", "text": "doublon"}],
        )
    )
    with pytest.raises(IntegrityError, match="uq_tours_conversation_session_id_numero"):
        session.commit()


def test_les_blocs_anthropic_reviennent_sans_etre_aplatis(session: Session):
    """Le harnais d'éval (étape 12) doit pouvoir rejouer une conversation à l'identique."""
    conversation = _session_avec_trois_tours(session)
    tours = (
        session.execute(
            select(TourConversation)
            .where(TourConversation.session_id == conversation.id)
            .order_by(TourConversation.numero)
        )
        .scalars()
        .all()
    )
    assert [tour.role for tour in tours] == ["user", "assistant", "user"]
    assert tours[1].blocs[0]["type"] == "tool_use"
    assert tours[1].blocs[0]["input"] == {"capacity": 2000}


def test_lindex_gin_sur_specs_existe_reellement(session: Session):
    """La migration a pu l'oublier sans que rien d'autre ne le signale.

    Un index GIN manquant ne casse aucun test : les requêtes rendent les mêmes
    résultats, simplement plus lentement. Il faut donc l'interroger nommément.
    """
    definition = session.execute(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_produits_specs'")
    ).scalar_one_or_none()
    assert definition is not None, "l'index GIN sur `specs` n'a pas été créé"
    assert "USING gin" in definition
    assert "jsonb_path_ops" in definition


def test_les_index_de_filtres_durs_existent(session: Session):
    """Les deux index qui servent les filtres présents dans toutes les requêtes."""
    noms = set(
        session.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'produits'")
        ).scalars()
    )
    assert {"ix_produits_categorie_prix_usd", "ix_produits_marque"} <= noms
