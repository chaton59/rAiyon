"""Modèles SQLAlchemy : `produits`, `sessions`, `tours_conversation`, les deux tables
d'observation de l'étape 23 — `appels_modele`, `evenements_tour` — et le cache d'avis web
de l'étape 26, `avis_produit`.

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


# --------------------------------------------------------------------------- #
# Le cache d'avis web — étape 26
# --------------------------------------------------------------------------- #

SOURCES_AVIS = ("brave", "fabrique")
"""D'où vient la ligne. **Deux provenances, et la distinction porte tout le jalon.**

* `brave` — récupérée d'une vraie recherche. Elle est datée, donc elle périme.
* `fabrique` — **écrite à la main**, committée dans `data/seed/avis.jsonl`. Elle n'a
  jamais été un instantané du web, donc elle n'a pas de fraîcheur à perdre : elle ne
  périme **jamais**. Voir `AvisProduit.recupere_le`.

⚠️ **Aucune ligne `brave` n'entre dans le dépôt git**, et ce n'est pas une politique de
propreté : les conditions Brave §3(b) interdisent de *« redistribute, resell, or
sublicense the Search Results »*. Un `avis.jsonl` committé contenant de vrais résultats de
recherche serait exactement cela. Le seed est donc **fabriqué**, et la colonne rend le
fait vérifiable par une requête au lieu de le laisser à une intention.

---

### 🔴 Le droit de persister ces lignes dépend du plan, et le plan n'est pas connu

**Plan effectif : à compléter.** Les deux branches sont écrites ici plutôt qu'attendues,
parce que le code, lui, écrit déjà.

* **Sous un plan accordant des droits de stockage** — Brave en propose un explicitement —
  la persistance de `source='brave'` est un droit accordé, et cette table est en règle
  telle qu'elle est.
* **Sous le plan standard**, elle est une **zone grise**. Le §3(b) interdit de *« store,
  cache, or create a database of Search Results […] other than transient storage required
  for operation »*, sans jamais chiffrer « transient ». Un cache à 24 h remplacé en bloc et
  jamais redistribué est **défendable** comme stockage opérationnel ; ce n'est pas une
  permission écrite, et ce dépôt ne présente pas une interprétation comme un droit.

**Ce qui a été observé, et qui rend la question concrète** (premier run en ligne, étape
31) : trois lignes `source='brave'` ont été écrites en base, puis effacées par le
`make seed` de restauration — et elles **seront réécrites à chaque exécution en ligne**.
Ce n'est donc pas une hypothèse sur un usage futur : le chemin est emprunté.

⚠️ **Rien de tout cela ne concerne les campagnes**, qui ne sortent jamais sur le réseau
(§3.18) et ne lisent que des fixtures fabriquées. La zone grise porte sur l'usage produit
— console et API — et sur lui seul."""

EXTRAIT_MAX_CARACTERES = 500
"""Longueur maximale d'un extrait. ⚠️ **Une borne, pas une mesure** — rien ne l'a calibrée.

Elle existe pour deux raisons, aucune des deux esthétique : un extrait est du **texte de
tiers** qui part dans le contexte du modèle, donc de la surface d'injection et du jeton
facturé. 500 caractères font environ 125 jetons ; cinq résultats par recherche en font
625, ce qui reste petit devant un historique de conversation.

Elle est tenue à **deux endroits** : `tronquer_extrait()` coupe à l'écriture, la
contrainte SQL refuse ce qui passerait outre. La couche haute tronque plutôt qu'elle ne
rejette — perdre un résultat entier parce qu'une page est bavarde serait pire —, et la
troncature est **marquée** pour que le modèle voie qu'elle a eu lieu.

À recalibrer sur les longueurs réellement rendues, une fois qu'il en existe."""


class AvisProduit(Base):
    """Un résultat web mis en cache : ce qu'une page dit, d'où ça vient, et quand.

    ### Ce cache n'est pas un cache d'économie, et ça change son dimensionnement

    ⚠️ **C'est le point à ne pas perdre, parce qu'il a été trouvé en tuant l'argument
    inverse.** Le réflexe est de justifier un cache par les appels qu'il évite. Sur cette
    charge, l'argument est faux et il a été mesuré : une campagne complète, c'est **81
    tours client**, donc au pire 81 recherches, soit **0,40 $** au tarif Brave de 5 $ pour
    mille. Le crédit mensuel offert en paie douze. **Le cache n'économise rien qui compte.**

    Ce qu'il achète, c'est la **comparabilité**. Comparer deux versions de prompt suppose
    que les deux exécutions aient vu le **même** contenu web ; sinon la différence mesurée
    mélange l'effet du prompt et l'effet d'une page qui a bougé, et rien à l'écran ne les
    sépare.

    **Un cache d'économie et un cache de comparabilité ne se dimensionnent pas pareil.** Le
    premier se règle sur un taux de hit : plus il est haut, mieux c'est, et un TTL court
    qui attrape déjà 90 % des répétitions suffit. Le second se règle sur une **frontière** :
    le TTL doit être plus long que l'écart entre les deux bras d'une comparaison, **sinon
    l'expiration tombe au milieu de la mesure**. Une frontière à 4 h attrape pourtant
    presque tous les hits — et coupe en deux une session de travail qui dure six heures.
    Ce défaut-là ne se voit dans aucun taux de hit ; il ne se voit qu'en se demandant ce
    que le cache sert.

    D'où **24 h** (`RAIYON_AVIS_TTL_HEURES`) : c'est le plus court TTL qui fait coïncider
    une génération de cache avec une journée de travail, l'unité réelle de ce projet. Plus
    long ne rattrape presque rien sur cette charge et transforme le cache en corpus ; plus
    court rouvre la frontière au milieu de la mesure.

    ⚠️ **Le risque résiduel est nommé** : une comparaison à cheval sur minuit. Il ne se
    ferme pas par un TTL plus long, il se **rend visible** — `recupere_le` est dans la
    ligne, et l'étape 27 trace hit/miss par recherche, donc une mesure contaminée se
    constate au lieu de passer.

    ### La clé est la requête seule ; `produit_id` est un lien, pas une clé

    La recherche est libre — le modèle formule ce qu'il veut —, donc il n'y a pas toujours
    un produit sous lequel ranger. `produit_id` est renseigné quand la recherche portait
    sur un produit identifié, et sert à relire le cache d'un produit ; il **n'entre pas**
    dans l'identité de la ligne. Une même page peut donc être trouvée par deux requêtes
    différentes, et elle y sera deux fois : ce sont deux faits de cache distincts.

    ### `ON DELETE CASCADE`, et la conséquence sur `make seed`

    ⚠️ **`make seed` vide la table `produits` avant de la remplir** (`charger_en_base`).
    La cascade emporte donc les avis liés à un produit, à chaque chargement de catalogue.
    Ce n'est pas un défaut à contourner : un avis sur un produit qui n'existe plus n'est
    pas un fait. La conséquence est tenue à l'endroit où elle se produit — **`make seed`
    charge les deux**, catalogue puis avis, dans cet ordre et dans la même commande.

    *Alternative écartée — `ON DELETE SET NULL`.* La ligne survivrait en perdant son lien,
    donc un avis sur « ce produit » deviendrait un avis sur rien, sans que rien ne le dise.
    Une perte silencieuse vaut moins qu'une suppression franche.
    """

    __tablename__ = "avis_produit"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    requete_normalisee: Mapped[str] = mapped_column(Text, nullable=False)
    """La clé, telle que `raiyon.avis.normalisation.normaliser()` la produit.

    Stockée normalisée et **jamais** la requête d'origine : garder les deux inviterait à
    lire l'une en croyant lire l'autre. Ce que la requête d'origine aurait apporté — savoir
    ce que le modèle a réellement écrit — est du ressort du journal, qui l'enregistre
    dans `evenements_tour` sans en faire une clé."""

    produit_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("produits.id", ondelete="CASCADE"), nullable=True
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    titre: Mapped[str] = mapped_column(Text, nullable=False)
    extrait: Mapped[str] = mapped_column(Text, nullable=False)
    """Ce que la page dit, borné à `EXTRAIT_MAX_CARACTERES`.

    ⚠️ **Du texte brut de tiers, jamais une synthèse.** Aucun octet de cette colonne ne
    vient d'un modèle de langage — c'est la même règle que pour `produits`, et pour la même
    raison : on ne met pas du texte de LLM dans la base de faits (§2)."""

    source: Mapped[str] = mapped_column(String(16), nullable=False)
    recupere_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    """Quand la ligne a été récupérée. **Le TTL se lit dessus, à la lecture.**

    Pas de tâche de fond qui purge : une ligne périmée reste en base et c'est la lecture
    qui la refuse. Un purgeur ajouterait un ordonnanceur, donc un composant qui tourne, à
    un projet dont toutes les garanties sont vérifiables par une requête.

    ⚠️ **Une ligne `fabrique` ne périme jamais, quelle que soit cette date.** Elle n'a pas
    été prise sur le web à un instant : elle a été écrite. Sans cette exception, le seed
    d'avis deviendrait périmé vingt-quatre heures après `make seed`, et `make eval`
    cesserait de trouver quoi que ce soit — **silencieusement, un jour plus tard**, ce qui
    est la pire forme de panne pour un harnais de mesure."""

    __table_args__ = (
        CheckConstraint(f"source IN ({_liste_sql(SOURCES_AVIS)})", name="source_connue"),
        CheckConstraint("requete_normalisee <> ''", name="requete_non_vide"),
        CheckConstraint(f"char_length(extrait) <= {EXTRAIT_MAX_CARACTERES}", name="extrait_borne"),
        # Une page n'apparaît qu'une fois par requête. C'est ce qui rend l'écriture
        # concurrente sûre sans verrou : deux processus qui remplissent la même clé au
        # même instant ne peuvent pas produire de doublon — le second se heurte à cette
        # contrainte, et `DepotAvisSql.ecrire()` en fait une relecture plutôt qu'une erreur.
        UniqueConstraint("requete_normalisee", "url", name="uq_avis_produit_requete_url"),
        # Toutes les lectures partent de la clé. L'index la porte seule : `recupere_le`
        # n'y ajouterait rien, le groupe rendu par une clé tenant en quelques lignes.
        Index("ix_avis_produit_requete", "requete_normalisee"),
        # La relecture « les avis de ce produit », qui ne passe pas par la clé.
        Index("ix_avis_produit_produit_id", "produit_id"),
    )
