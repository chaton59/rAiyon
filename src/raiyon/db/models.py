"""Modèles SQLAlchemy : `produits`, `sessions`, `tours_conversation`, et les deux tables
d'observation de l'étape 23 — `appels_modele`, `evenements_tour`.

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
    """Un produit du catalogue. Les faits que le LLM aura le droit de citer.

    **Aucune colonne de cette table ne contient une sortie de modèle de langage.**
    `nom_fr` et `description` en portaient une ; la mesure de la passe B a montré
    qu'elles étaient l'une inutile et l'autre redondante avec la réponse de l'étape 8,
    et la migration `0002` les a retirées (§3.4ter). C'est ce qui rend « le LLM ne
    produit jamais un fait » lisible dans le schéma, et non seulement dans le README.
    """

    __tablename__ = "produits"

    # Identifiant synthétique `{categorie}-{10 hexadécimaux}`, jamais `name` :
    # 5 390 noms distincts pour 9 687 produits à prix, `name` n'est pas une clé.
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    # Nom source, en anglais, cité **verbatim** par l'agent de l'étape 8 : la base
    # est en anglais, c'est la phrase de recommandation qui porte le français
    # (§3.4ter). Un nom jamais réécrit est vérifiable au caractère près par le
    # validateur de l'étape 9.
    nom: Mapped[str] = mapped_column(Text, nullable=False)
    # Premier mot de `name` (§3.4quater). N'existe comme champ dans aucune
    # catégorie de la source : c'est une transformation, pas une lecture.
    marque: Mapped[str] = mapped_column(Text, nullable=False)
    categorie: Mapped[str] = mapped_column(String(32), nullable=False)
    # Le prix de la source est en dollars. On stocke `prix_usd` et rien d'autre :
    # fabriquer un taux de change serait inventer un fait (§2). L'unité est dans le
    # nom de la colonne pour qu'aucune couche supérieure ne puisse l'oublier.
    prix_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
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
            marque=produit.marque,
            categorie=produit.categorie,
            prix_usd=produit.prix_usd,
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


# --------------------------------------------------------------------------- #
# L'observation — étape 23. Deux tables qui décrivent un tour sans le rejouer
# --------------------------------------------------------------------------- #

DISPLAY_THINKING = ("summarized", "omitted")
"""Les deux seules valeurs que l'API accepte pour `thinking.display`. **Mesuré**, pas lu.

Une valeur inventée rend un 400 qui les énumère lui-même :
`thinking.adaptive.display: Input should be 'summarized', 'omitted'`. La liste est donc
close du côté de l'API, et la contrainte le dit du côté de la base — c'est ce qui empêche
qu'un `raw` ou un `full` supposé s'installe dans la colonne sans jamais avoir été envoyé.
"""


class AppelModele(Base):
    """Un appel au modèle : ce qu'il a coûté, combien de temps, et **sous quelle config**.

    ### Une ligne par appel, pas une par tour (§3.9)

    Un tour client fait entre un et huit appels — la garde d'itérations en décide. Cumuler
    au tour perdrait exactement ce qu'on cherche : quelle **itération** a coûté cher, quelle
    itération a été tronquée, à quel moment le cache a cessé d'être lu. `tour_client` et
    `iteration` rendent la ligne replaçable dans la conversation sans jointure.

    ### `effort` et `display` sont dans la table, et ce n'est pas de la décoration

    ⚠️ **C'est ce qui rend l'arbitrage `effort` décidable plus tard.** Il n'est pas fixé
    aujourd'hui, et il ne pouvait pas l'être : trois tirages `low`/`medium`/`high` sur un
    même message ont rendu 165, 280 et 187 jetons — du bruit. Fixer sur cette base referait
    la faute que l'étape 23 vient de consigner.

    Sans ces deux colonnes, la question resterait indécidable pour toujours : on ne pourrait
    pas séparer les populations d'une campagne, et on retomberait sur trois tirages. Avec
    elles, la comparaison devient une requête sur du trafic réel.

    `effort` vaut `defaut` quand la requête ne le fixe pas — la chaîne, pas `NULL`. Un
    `NULL` dirait « on ne sait pas », alors qu'on sait très bien : on n'a rien envoyé, et le
    modèle a appliqué son défaut. Les deux états sont différents et la distinction est
    précisément l'objet de la colonne.

    ### Ce que la table ne porte pas

    Ni prompt, ni messages, ni blocs de réponse. Ils vivent déjà dans `tours_conversation`,
    et les recopier ici ferait une seconde persistance de la conversation — avec deux
    copies libres de diverger. `empreinte_systeme` suffit à dire *quel préfixe* a été
    envoyé, ce qui est la seule question qu'on pose vraiment à un appel passé.
    """

    __tablename__ = "appels_modele"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    tour_client: Mapped[int] = mapped_column(Integer, nullable=False)
    """Le `numero` de la ligne du message client, comme le jeton de parole du §3.17."""

    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    """Le rang de l'appel **dans le tour**, à partir de 1. Borné par `max_agent_iterations`."""

    modele: Mapped[str] = mapped_column(Text, nullable=False)
    empreinte_systeme: Mapped[str] = mapped_column(String(64), nullable=False)
    """L'empreinte du prompt système envoyé. La même que celle de `/health` et des cassettes.

    Elle répond à la seule question qu'on pose à un appel vieux d'une semaine : « est-ce
    que celui-là tournait sur le prompt d'aujourd'hui ? ». Stocker le texte y répondrait
    aussi, en multipliant 8,6 Ko par appel."""

    effort: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'defaut'"))
    display: Mapped[str] = mapped_column(String(16), nullable=False)
    stop_reason: Mapped[str] = mapped_column(String(32), nullable=False)

    jetons_entree: Mapped[int] = mapped_column(Integer, nullable=False)
    jetons_sortie: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_ecrit: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_lu: Mapped[int] = mapped_column(Integer, nullable=False)
    """Les quatre compteurs d'`Usage`, à plat. Aplatis plutôt qu'en JSONB : ce sont
    exactement les colonnes qu'on agrège (`sum`, `avg`), et un JSONB obligerait chaque
    requête du tableau de bord à les extraire une par une."""

    latence_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    """Le temps de l'appel, mesuré **autour** de lui par le décorateur. Il inclut donc les
    reprises internes du SDK — c'est ce qu'on veut : c'est le temps que le client a attendu,
    pas celui que l'API déclare."""

    horodatage: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("iteration >= 1", name="iteration_positive"),
        CheckConstraint("latence_ms >= 0", name="latence_positive"),
        CheckConstraint(f"display IN ({_liste_sql(DISPLAY_THINKING)})", name="display_connu"),
        # Toutes les lectures du tableau de bord partent d'une session et lisent dans
        # l'ordre du tour. L'index porte donc les deux colonnes, dans cet ordre.
        Index("ix_appels_modele_session_tour", "session_id", "tour_client", "iteration"),
    )


class EvenementTour(Base):
    """Un événement émis par l'orchestration, **dans l'ordre où il a été émis**.

    ### `rang` porte l'ordre, et il n'est pas déductible

    L'horodatage ne suffit pas : deux événements d'un même message d'outils tombent dans la
    même milliseconde, et un `ORDER BY horodatage` rendrait alors un ordre arbitraire — donc
    une timeline qui montre le sondage avant les critères une fois sur deux. `rang` est
    compté par le drainage, à partir de 1, sur le tour.

    ### `genre` et `charge` sont **exactement** ce que le fil SSE envoie

    Ils viennent de `nom_et_donnees()`, la fonction que `raiyon.api.serialisation` emploie
    déjà pour fabriquer une trame. Ce n'est pas seulement de la réutilisation de code : cela
    fait que **la timeline relue et le direct montrent la même chose**. Une seconde
    sérialisation aurait fini par diverger de la première, et le tableau de bord aurait
    décrit une conversation légèrement différente de celle qui a eu lieu.

    C'est aussi ce qui donne l'exhaustivité gratuitement : `nom_et_donnees()` se termine par
    un `assert_never`, donc un neuvième type d'événement fera échouer `make typecheck` avant
    d'être silencieusement absent de la table.

    ⚠️ **`genre` n'a pas de contrainte de liste**, contrairement à `role` ou à `statut`. Le
    vocabulaire est fermé côté Python (`NomEvenement`) et vérifié par mypy ; le recopier en
    SQL créerait une seconde liste à tenir à jour, et le jour où elles divergeraient c'est
    la migration qui gagnerait contre le type — l'inverse de ce qu'on veut.
    """

    __tablename__ = "evenements_tour"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    tour_client: Mapped[int] = mapped_column(Integer, nullable=False)
    rang: Mapped[int] = mapped_column(Integer, nullable=False)
    genre: Mapped[str] = mapped_column(String(32), nullable=False)
    charge: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    horodatage: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("rang >= 1", name="rang_positif"),
        UniqueConstraint("session_id", "tour_client", "rang", name="uq_evenements_tour_rang"),
        Index("ix_evenements_tour_session_tour", "session_id", "tour_client", "rang"),
    )
