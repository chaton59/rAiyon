"""Modèles SQLAlchemy : `produits`, `sessions`, `tours_conversation`.

Le schéma applique la décision §3.3 : des colonnes typées et indexées pour ce qui
est commun à tout produit, un JSONB `specs` pour ce qui est propre a la catégorie.
Les garanties de contenu (types, bornes, cohérences croisées) vivent dans
`raiyon.catalogue.schemas` ; ce que l'on trouve ici sont les garanties que la base
tient **même si quelqu'un contourne Pydantic** : formes d'identifiants, positivité
des prix, listes de valeurs autorisées, unicité et cascades.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from raiyon.catalogue.schemas import CATEGORIES, MOTIF_ID, ProduitEnBase
from raiyon.db.base import Base

STATUTS_SESSION = ("en_cours", "recommandation_rendue", "abandonnee")
ROLES_TOUR = ("user", "assistant")


def _liste_sql(valeurs: tuple[str, ...]) -> str:
    """Rend `'a', 'b', 'c'` pour une clause `IN` écrite en SQL brut.

    Les listes de valeurs autorisées sont ainsi dérivées des constantes Python, et
    ne peuvent pas diverger d'elles au fil des migrations.
    """
    return ", ".join(f"'{valeur}'" for valeur in valeurs)


class Produit(Base):
    """Un produit du catalogue. Les faits que le LLM aura le droit de citer."""

    __tablename__ = "produits"

    # Identifiant synthétique `{categorie}-{10 hexadécimaux}`, jamais `name` :
    # 5 390 noms distincts pour 9 687 produits à prix, `name` n'est pas une clé.
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    nom: Mapped[str] = mapped_column(Text, nullable=False)
    # Traduction produite par la passe LLM de l'étape 5. Nul tant qu'elle n'a pas
    # tourné : le catalogue doit être exploitable sans elle.
    nom_fr: Mapped[str | None] = mapped_column(Text)
    # Premier mot de `name` (§3.4quater). N'existe comme champ dans aucune
    # catégorie de la source : c'est une transformation, pas une lecture.
    marque: Mapped[str] = mapped_column(Text, nullable=False)
    categorie: Mapped[str] = mapped_column(String(32), nullable=False)
    # Le prix de la source est en dollars. On stocke `prix_usd` et rien d'autre :
    # fabriquer un taux de change serait inventer un fait (§2). L'unité est dans le
    # nom de la colonne pour qu'aucune couche supérieure ne puisse l'oublier.
    prix_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # ⚠️ Champ **généré** (§3.4ter), donc non factuel : affichage seul. Il n'entre
    # jamais dans un filtre ni dans un score - le moteur de l'étape 6 ne doit pas
    # le lire. Aucune contrainte SQL ne peut faire respecter cela, seul ce
    # commentaire et la revue le peuvent.
    description: Mapped[str | None] = mapped_column(Text)
    # La source ne porte aucune quantité en stock. Un booléen dit ce que l'on sait ;
    # un entier dirait ce que l'on ne sait pas.
    disponible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    specs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    maj_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(f"id ~ '{MOTIF_ID}'", name="forme_id"),
        CheckConstraint(f"categorie IN ({_liste_sql(CATEGORIES)})", name="categorie_connue"),
        CheckConstraint("prix_usd > 0", name="prix_positif"),
        # Les deux filtres durs présents dans *toutes* les requêtes du moteur
        # (§3.10). La catégorie vient en tête parce qu'elle est toujours une
        # égalité, le prix ensuite parce qu'il est toujours une plage.
        Index("ix_produits_categorie_prix_usd", "categorie", "prix_usd"),
        # Filtre dur exprimé par les clients sur les 6 catégories (« je veux du
        # Intel »), et seule colonne qui porte la marque.
        Index("ix_produits_marque", "marque"),
        # `jsonb_path_ops` : deux fois plus compact que l'opérateur par défaut, et
        # suffisant ici puisqu'on ne cherche jamais l'existence d'une clé seule.
        # ⚠️ Sa limite est le compromis assumé de l'étape 4 (§3.3bis) : il sert
        # l'égalité et la containment, **pas** les comparaisons de plage du type
        # `(specs->>'capacity')::int >= 2000`, qui feront un balayage séquentiel.
        # À ~1 000 produits cela coûte quelques millisecondes ; l'échappatoire
        # connue, si le volume changeait, est un index d'expression B-tree par
        # champ numérique filtré.
        Index(
            "ix_produits_specs",
            "specs",
            postgresql_using="gin",
            postgresql_ops={"specs": "jsonb_path_ops"},
        ),
    )

    @classmethod
    def depuis_schema(cls, produit: ProduitEnBase) -> "Produit":
        """Construit la ligne à partir du modèle validé — seule voie d'insertion.

        `specs_pour_base()` retire la catégorie du JSONB : elle a déjà sa colonne, et
        la stocker deux fois autoriserait les deux copies à diverger.
        """
        return cls(
            id=produit.id,
            nom=produit.nom,
            nom_fr=produit.nom_fr,
            marque=produit.marque,
            categorie=produit.categorie,
            prix_usd=produit.prix_usd,
            description=produit.description,
            disponible=produit.disponible,
            specs=produit.specs_pour_base(),
        )


class SessionConversation(Base):
    """Une conversation avec un client, persistée pour survivre au redémarrage (§3.12)."""

    __tablename__ = "sessions"

    # Généré côté application (`uuid4`) et non par la base : l'API doit connaître
    # l'identifiant avant le premier flush pour l'émettre dans le flux SSE.
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    maj_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    # Le budget a sa propre colonne bien qu'il soit un critère comme les autres.
    # Raison : c'est lui que la couche outils lit pour borner la recherche (§3.6,
    # `session.budget`), et il porte l'invariant produit du §3.10. Le dupliquer dans
    # `criteres_valides` ouvrirait la possibilité que les deux divergent - soit
    # exactement le mode d'échec que le budget-filtre-dur cherche à rendre impossible.
    budget_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    criteres_valides: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    statut: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'en_cours'")
    )

    tours: Mapped[list["TourConversation"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="TourConversation.numero",
    )

    __table_args__ = (
        CheckConstraint("budget_usd > 0", name="budget_positif"),
        CheckConstraint(f"statut IN ({_liste_sql(STATUTS_SESSION)})", name="statut_connu"),
    )


class TourConversation(Base):
    """Un tour de parole, stocké sous sa forme brute d'origine."""

    __tablename__ = "tours_conversation"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    # ⚠️ Les `tool_result` portent le rôle `user` dans l'API Anthropic : deux valeurs
    # suffisent, il n'existe pas de rôle « outil ».
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # Blocs de contenu Anthropic **bruts** (`text`, `tool_use`, `tool_result`), pas un
    # texte aplati. Le harnais d'éval de l'étape 12 doit pouvoir rejouer une
    # conversation à l'identique, et le validateur de l'étape 9 a besoin des
    # `tool_result` pour savoir quels produits ont réellement été fournis au modèle.
    # Aplatir en texte détruirait les deux, et de façon irréversible.
    blocs: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped[SessionConversation] = relationship(back_populates="tours")

    __table_args__ = (
        CheckConstraint(f"role IN ({_liste_sql(ROLES_TOUR)})", name="role_connu"),
        # L'ordre des tours est une donnée, pas une convention d'insertion : un
        # numéro dupliqué rendrait la relecture d'une conversation ambiguë.
        UniqueConstraint("session_id", "numero", name="uq_tours_conversation_session_id_numero"),
        # Toutes les lectures partent d'une session ; la FK ne crée pas d'index
        # côté Postgres, et son absence ferait aussi ramer les DELETE en cascade.
        Index("ix_tours_conversation_session_id", "session_id"),
    )
