"""Registre des attributs : rôles, genres, opérateurs admis, bornes, libellés français.

Écrit **à la main** depuis `catalogue/schema_attributs.md`, qui reste la source de
vérité des rôles. Ce module en est la traduction exécutable : ce que le document dit
en prose, le moteur doit pouvoir le lire.

Trois raisons de ne pas annoter `schemas.py` à la place (alternative écartée) :

1. une seule source supprimerait toute divergence, mais chargerait le miroir du
   schéma SQL d'une préoccupation de matching — `schemas.py` cesserait d'être lisible
   comme ce qu'il est ;
2. le test de couverture (`tests/matching/test_attributs.py`) donne l'essentiel du
   bénéfice : il vérifie que les clés d'ici **couvrent exactement** les champs de
   `schemas.py`, catégorie par catégorie ;
3. les champs `affichage` (`color`, `nom`, `id`) figurent ici **avec leur rôle**
   plutôt qu'omis. C'est ce qui permet de prouver qu'ils ne filtrent ni ne scorent,
   au lieu de constater qu'on les a oubliés — le cas G2 du rapport de seed exerce
   précisément ce point.

**Le français de ce fichier est de la donnée, pas du rendu.** Un libellé dérivé d'un
**champ** — et non d'un produit — est déterministe (§3.4ter) : « fréquence de
rafraîchissement » ne dépend d'aucun modèle. Le repli sur template de §3.11 niveau 3
en aura besoin ; le laisser hors du registre reviendrait à le redécouvrir à l'étape 9.
Aucun libellé n'est mis en forme ici : ni majuscule, ni article, ni pluriel.
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

from raiyon.catalogue.schemas import CATEGORIES, Categorie, ProduitEnBase


class Role(StrEnum):
    """Les trois rôles de `schema_attributs.md`, exclusifs et définis une fois."""

    FILTRE_DUR = "filtre_dur"
    """Critère bloquant, traduisible en `WHERE` : ce qui ne le satisfait pas ne
    remonte jamais."""

    SCORE = "score"
    """Critère souple : produit un sous-score 0-1, pondère le classement, n'exclut
    rien."""

    AFFICHAGE = "affichage"
    """Montré au client, **n'entre jamais** dans le matching."""


class Genre(StrEnum):
    """Nature de la valeur, qui commande les opérateurs admis et la rétrogradation."""

    NUMERIQUE = "numerique"
    """Gradué : `>=` et `<=` ont un sens, et « plutôt 144 Hz » est une nuance
    exprimable."""

    ENUMERE = "enumere"
    """Vocabulaire fermé issu du catalogue. Égalité stricte, jamais de `contains` :
    « RTX 4070 » ne doit pas attraper « RTX 4070 Ti » (§3.7 — `probe_catalog` rendra
    les valeurs distinctes, l'agent choisira dedans)."""

    BOOLEEN = "booleen"
    """Vrai ou faux, sans milieu."""

    TEXTE = "texte"
    """Saisie libre du client. Seule `marque` en relève : la comparaison passe par une
    clé normalisée, écrite **une fois, en SQL** (`depot.py`)."""


class Sens(StrEnum):
    """Direction du mérite d'un attribut numérique, indépendamment de toute demande.

    Sert quand aucun critère technique n'oriente le calcul : c'est le cas du score
    technique de repli de `rapport_qualite_prix` (« le meilleur rapport qualité/prix »
    demandé seul). Quand le client pose un seuil, c'est **l'opérateur** du critère qui
    donne la direction, pas ce champ — sinon « un écran d'au plus 24 pouces » classerait
    le 65 pouces en tête.
    """

    PLUS_HAUT_MIEUX = "plus_haut_mieux"
    PLUS_BAS_MIEUX = "plus_bas_mieux"


COMPLET = Decimal("1")
"""Taux de remplissage de 100 % sur le seed. Nommé pour que les entrées se lisent."""


@dataclass(frozen=True, slots=True)
class Attribut:
    """Un champ du catalogue, tel que le moteur a le droit de s'en servir."""

    champ: str
    role: Role
    genre: Genre
    libelle_fr: str
    unite: str | None = None

    taux_remplissage: Decimal = COMPLET
    """Mesuré **sur le seed** (`data/seed/rapport_seed.md`), jamais sur la source :
    `internal-hard-drive.type` est à 99,6 % sur la source et à 100 % ici, l'étape 5
    ayant écarté les 8 lignes concernées. C'est ce taux qui décide si le moteur émet
    une requête de comptage des exclusions faute de donnée — à 100 %, il n'en émet
    aucune, donc surcoût nul sur la quasi-totalité des critères."""

    retrogradable: bool = False
    """Un `souhait` posé dessus devient un score au lieu de rester un filtre dur.
    Vrai uniquement sur les filtres durs **gradués** ; fermé sur la compatibilité,
    qui est binaire — « plutôt de la DDR5 » n'est pas un souhait, c'est un
    malentendu : de la DDR4 n'entre pas dans le socket."""

    sens: Sens | None = None
    borne_basse: Decimal | None = None
    borne_haute: Decimal | None = None
    """Bornes de normalisation **absolues et constantes** (arbitrage G), calibrées par
    `scripts/calibrer_bornes.py` sur le seed committé. Jamais un min-max du lot
    candidat : le score d'un produit ne doit pas dépendre des produits présents à
    côté de lui, sans quoi deux conversations le classeraient différemment."""

    dans_les_specs: bool = True
    """Faux pour les colonnes communes de la table (`prix_usd`, `marque`…), qui ne
    passent pas par le JSONB. Le dépôt en a besoin pour choisir la forme du prédicat,
    et `valeur_du_produit()` pour savoir où lire.

    ⚠️ **Ce drapeau n'est pas écrit à la main sur les entrées de `_COMMUNS`** : il est
    posé par la construction du registre, pour tout ce qui vient de là. L'écrire six
    fois ouvrirait la possibilité de l'oublier une fois — et un oubli est silencieux :
    la containment JSONB cherche alors une clé qui n'existe pas et rend zéro produit,
    sans erreur."""

    impose: bool = False
    """Appliqué par le moteur à chaque requête, donc jamais reçu comme critère.
    `disponible = true` est le seul cas."""

    explique_par: str | None = None
    """Colonne qui **explique** l'absence de cet attribut, quand une autre colonne le
    fait.

    ⚠️ **Ce n'est pas une opinion sur le taux de remplissage.** Le drapeau se pose quand
    l'absence est déterminée par une autre valeur du produit, ce qui est vérifiable par
    la machine : `rpm` est absent **si et seulement si** `type == "SSD"`, invariant que
    `SpecsDisqueInterne._coherence_type_rpm` impose déjà à l'insertion, et que
    `test_attributs.py` revérifie sur le seed committé.

    `cpu.boost_clock`, à 66,1 %, ne le porte **pas** : son absence est *corrélée* à la
    génération du processeur, aucune colonne ne la *détermine*. La distinction est
    exactement celle de §3.4quater — calcul déterministe contre supposition — et un test
    la rend exécutable plutôt que documentaire."""

    @property
    def absence_structurelle(self) -> bool:
        """L'absence de valeur dit quelque chose du produit, pas de la donnée.

        Un SSD sans vitesse de rotation n'est pas un disque dont on ignore la vitesse :
        il n'en a pas. Conséquence pour le moteur — cet attribut ne rentre pas dans
        `ecartes_faute_de_donnee`, et le zéro résultat qu'il provoque porte son propre
        motif de diagnostic.
        """
        return self.explique_par is not None

    @property
    def est_scorable(self) -> bool:
        """Un critère posé dessus peut-il produire un sous-score ?"""
        return self.role is not Role.AFFICHAGE and not self.impose

    @property
    def est_de_compatibilite(self) -> bool:
        """Filtre dur non gradué : il ne se relâche pas par degré, il s'abandonne.

        C'est ce qui le fait proposer **en dernier** dans le traitement du zéro
        résultat (arbitrage J) : abandonner « interface SATA » n'est pas assouplir un
        seuil, c'est renoncer à une contrainte de branchement.
        """
        return self.role is Role.FILTRE_DUR and not self.retrogradable and not self.impose


# --------------------------------------------------------------------------- #
# Bornes de normalisation — sortie de `scripts/calibrer_bornes.py`
# --------------------------------------------------------------------------- #

# Calibré le 2026-08-30 sur les 1 026 lignes de `data/seed/produits.jsonl`, par :
#
#     uv run python scripts/calibrer_bornes.py
#
# Percentiles 5 et 95, méthode du **rang le plus proche** — sans interpolation, donc
# chaque borne est une valeur réellement observée dans le catalogue et non une valeur
# calculée qui n'y existe pas. La winsorisation au 95ᵉ est ce qui empêche les queues
# lourdes d'écraser le classement : `memory.price_per_gb` monte à 497,5 USD/GB sur des
# modules minuscules, et une normalisation sur le maximum réel donnerait un sous-score
# indiscernable de zéro à 99 % du catalogue.
#
# ⚠️ Ces constantes sont du **code**, pas un cache : elles ne sont jamais recalculées au
# runtime. Le faire rendrait le score dépendant du lot, c'est-à-dire exactement le
# min-max relatif que l'arbitrage G écarte. `test_calibration.py` vérifie que le script
# les redonne à l'identique sur le seed committé.
BORNES_CALIBREES: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    ("cpu", "boost_clock"): (Decimal("3.3"), Decimal("5.6")),
    ("cpu", "core_clock"): (Decimal("2.1"), Decimal("4.1")),
    ("cpu", "core_count"): (Decimal("2"), Decimal("20")),
    ("cpu", "prix_usd"): (Decimal("49"), Decimal("769.27")),
    ("cpu", "tdp"): (Decimal("35"), Decimal("165")),
    ("headphones", "freq_max_khz"): (Decimal("20"), Decimal("40")),
    ("headphones", "freq_min_hz"): (Decimal("5"), Decimal("20")),
    ("headphones", "prix_usd"): (Decimal("14.95"), Decimal("449.99")),
    ("internal-hard-drive", "cache"): (Decimal("8"), Decimal("512")),
    ("internal-hard-drive", "capacity"): (Decimal("120"), Decimal("16000")),
    ("internal-hard-drive", "price_per_gb"): (Decimal("0.021"), Decimal("1.149")),
    ("internal-hard-drive", "prix_usd"): (Decimal("29.99"), Decimal("465.38")),
    ("internal-hard-drive", "rpm"): (Decimal("5400"), Decimal("7200")),
    ("memory", "capacite_totale_gb"): (Decimal("4"), Decimal("96")),
    ("memory", "cas_latency"): (Decimal("9"), Decimal("40")),
    ("memory", "ddr_generation"): (Decimal("3"), Decimal("5")),
    ("memory", "first_word_latency"): (Decimal("9.194"), Decimal("16.504")),
    ("memory", "frequence_mhz"): (Decimal("1333"), Decimal("7200")),
    ("memory", "nb_modules"): (Decimal("1"), Decimal("4")),
    ("memory", "price_per_gb"): (Decimal("2.17"), Decimal("13.375")),
    ("memory", "prix_usd"): (Decimal("20.42"), Decimal("385.07")),
    ("memory", "taille_module_gb"): (Decimal("4"), Decimal("32")),
    ("monitor", "hauteur_px"): (Decimal("1080"), Decimal("2160")),
    ("monitor", "largeur_px"): (Decimal("1920"), Decimal("3840")),
    ("monitor", "prix_usd"): (Decimal("108"), Decimal("1299.99")),
    ("monitor", "refresh_rate"): (Decimal("60"), Decimal("240")),
    ("monitor", "response_time"): (Decimal("0.03"), Decimal("8")),
    ("monitor", "screen_size"): (Decimal("21.5"), Decimal("34")),
    ("video-card", "boost_clock"): (Decimal("1335"), Decimal("2970")),
    ("video-card", "core_clock"): (Decimal("775"), Decimal("2410")),
    ("video-card", "length"): (Decimal("164"), Decimal("339")),
    ("video-card", "memory"): (Decimal("1"), Decimal("24")),
    ("video-card", "prix_usd"): (Decimal("108.99"), Decimal("2590")),
}

# Plafond du ratio « score technique ÷ prix » pour `rapport_qualite_prix`, sur les
# catégories que la source ne dote pas d'un `price_per_gb`. Vaut `1 / P5(prix)` : un
# produit techniquement parfait, au prix du 5ᵉ centile de sa catégorie, atteint 1.
# Constant lui aussi — sinon le « meilleur rapport qualité/prix » cesse d'être
# reproductible d'une conversation à l'autre.
PLAFONDS_RATIO: dict[str, Decimal] = {
    "cpu": Decimal("0.02040816"),
    "headphones": Decimal("0.06688963"),
    "monitor": Decimal("0.00925926"),
    "video-card": Decimal("0.00917515"),
}


# --------------------------------------------------------------------------- #
# Les attributs, catégorie par catégorie
# --------------------------------------------------------------------------- #

# Colonnes communes de la table `produits`. Elles existent sur les six catégories et
# ne passent pas par le JSONB.
#
# `prix_usd` et `categorie` sont **fermés à la rétrogradation** : un budget n'est pas
# un souhait, et on ne propose pas un clavier à qui demande un écran. Ils ne sont pas
# non plus des critères ordinaires — `RequeteMatching` les porte en champs dédiés,
# pour la même raison que `sessions.budget_usd` a sa colonne (§3.10) : deux chemins
# vers la même contrainte finissent par diverger.
_COMMUNS: tuple[Attribut, ...] = (
    Attribut("id", Role.AFFICHAGE, Genre.TEXTE, "identifiant"),
    Attribut("nom", Role.AFFICHAGE, Genre.TEXTE, "nom du produit"),
    Attribut("marque", Role.FILTRE_DUR, Genre.TEXTE, "marque"),
    Attribut("categorie", Role.FILTRE_DUR, Genre.ENUMERE, "catégorie"),
    Attribut("prix_usd", Role.FILTRE_DUR, Genre.NUMERIQUE, "prix", "USD", sens=Sens.PLUS_BAS_MIEUX),
    Attribut("disponible", Role.FILTRE_DUR, Genre.BOOLEEN, "disponibilité", impose=True),
)

# `core_count` et `tdp` sont gradués, donc rétrogradables : « plutôt 8 cœurs » se
# comprend. `microarchitecture` ne l'est pas — c'est le seul vecteur de la marque et
# de la génération dans la source, donc une contrainte de socket.
_CPU: tuple[Attribut, ...] = (
    Attribut(
        "core_count",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "nombre de cœurs",
        "cœurs",
        retrogradable=True,
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut(
        "core_clock",
        Role.SCORE,
        Genre.NUMERIQUE,
        "fréquence de base",
        "GHz",
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut(
        "tdp",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "enveloppe thermique",
        "W",
        retrogradable=True,
        sens=Sens.PLUS_BAS_MIEUX,
    ),
    Attribut("microarchitecture", Role.FILTRE_DUR, Genre.ENUMERE, "microarchitecture"),
    Attribut(
        "boost_clock",
        Role.SCORE,
        Genre.NUMERIQUE,
        "fréquence turbo",
        "GHz",
        taux_remplissage=Decimal("0.661"),
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut(
        "graphics",
        Role.SCORE,
        Genre.ENUMERE,
        "circuit graphique intégré",
        taux_remplissage=Decimal("0.532"),
    ),
)

# `largeur_px` et `hauteur_px` sont numériques mais **non rétrogradables**, et c'est
# `schema_attributs.md` qui le dit : « du 4K » désigne un seuil exact (3840x2160) ;
# proposer du 1440p à qui demande du 4K est un échec, pas une approximation. La règle
# « numérique donc gradué » ne s'applique pas à une résolution.
_MONITOR: tuple[Attribut, ...] = (
    Attribut(
        "screen_size",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "taille de dalle",
        "pouces",
        retrogradable=True,
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut(
        "largeur_px",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "largeur d'image",
        "pixels",
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut(
        "hauteur_px",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "hauteur d'image",
        "pixels",
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut("aspect_ratio", Role.FILTRE_DUR, Genre.ENUMERE, "format d'image"),
    Attribut(
        "panel_type",
        Role.SCORE,
        Genre.ENUMERE,
        "type de dalle",
        taux_remplissage=Decimal("0.977"),
    ),
    Attribut(
        "refresh_rate",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "fréquence de rafraîchissement",
        "Hz",
        taux_remplissage=Decimal("0.959"),
        retrogradable=True,
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut(
        "response_time",
        Role.SCORE,
        Genre.NUMERIQUE,
        "temps de réponse",
        "ms",
        taux_remplissage=Decimal("0.749"),
        sens=Sens.PLUS_BAS_MIEUX,
    ),
)

# `rpm` est un filtre dur gradué (« du 7 200 tours minimum »), donc rétrogradable, mais
# son taux de 33,9 % ne mesure pas une donnée manquante : il vaut exactement la part de
# HDD du seed (58 sur 171). Un SSD n'a pas de vitesse de rotation, et
# `SpecsDisqueInterne._coherence_type_rpm` impose déjà l'équivalence — d'où
# `explique_par="type"`.
#
# Ce que ce drapeau change, et c'est le point : sans lui, « 7 200 tr/min en M.2 PCIe »
# rendait zéro produit, le compteur d'exclusions égalait le nombre de produits rouverts,
# et le diagnostic concluait `donnee_absente`. L'étape 8 aurait alors dit « ces disques
# ne déclarent pas leur vitesse de rotation », alors que la vérité est « ce sont des SSD,
# ils n'en ont pas ». Le moteur fabriquait une affirmation fausse sur le catalogue, dans
# le module dont c'est précisément la raison d'être (§2).
_DISQUE: tuple[Attribut, ...] = (
    Attribut(
        "capacity",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "capacité",
        "Go",
        retrogradable=True,
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut("form_factor", Role.FILTRE_DUR, Genre.ENUMERE, "format"),
    Attribut("interface", Role.FILTRE_DUR, Genre.ENUMERE, "interface"),
    Attribut("type", Role.FILTRE_DUR, Genre.ENUMERE, "technologie de stockage"),
    Attribut(
        "rpm",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "vitesse de rotation",
        "tr/min",
        taux_remplissage=Decimal("0.339"),
        retrogradable=True,
        sens=Sens.PLUS_HAUT_MIEUX,
        explique_par="type",
    ),
    Attribut(
        "price_per_gb",
        Role.SCORE,
        Genre.NUMERIQUE,
        "prix au gigaoctet",
        "USD/Go",
        sens=Sens.PLUS_BAS_MIEUX,
    ),
    Attribut(
        "cache",
        Role.SCORE,
        Genre.NUMERIQUE,
        "mémoire cache",
        "Mo",
        taux_remplissage=Decimal("0.368"),
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
)

# `ddr_generation` est numérique et **fermé** à la rétrogradation : c'est le filtre dur
# le plus net du catalogue, de la DDR4 ne s'insère pas dans un socket DDR5.
# `nb_modules` est fermé lui aussi, mais pour une autre raison : le client qui le pose
# compte ses emplacements libres, ce qui est une contrainte physique et non un degré.
# `frequence_mhz` porte le rôle `score` de `schema_attributs.md` — « c'est la génération
# qui est bloquante » — donc la rétrogradation n'a rien à y faire.
_MEMOIRE: tuple[Attribut, ...] = (
    Attribut(
        "ddr_generation",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "génération DDR",
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut(
        "frequence_mhz",
        Role.SCORE,
        Genre.NUMERIQUE,
        "fréquence",
        "MHz",
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut(
        "nb_modules",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "nombre de barrettes",
        "barrettes",
        sens=Sens.PLUS_BAS_MIEUX,
    ),
    Attribut(
        "taille_module_gb",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "capacité par barrette",
        "Go",
        retrogradable=True,
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut(
        "capacite_totale_gb",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "capacité totale",
        "Go",
        retrogradable=True,
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut(
        "cas_latency",
        Role.SCORE,
        Genre.NUMERIQUE,
        "latence CAS",
        "cycles",
        sens=Sens.PLUS_BAS_MIEUX,
    ),
    Attribut(
        "first_word_latency",
        Role.SCORE,
        Genre.NUMERIQUE,
        "latence du premier mot",
        "ns",
        sens=Sens.PLUS_BAS_MIEUX,
    ),
    Attribut(
        "price_per_gb",
        Role.SCORE,
        Genre.NUMERIQUE,
        "prix au gigaoctet",
        "USD/Go",
        sens=Sens.PLUS_BAS_MIEUX,
    ),
    Attribut("color", Role.AFFICHAGE, Genre.ENUMERE, "couleur", taux_remplissage=Decimal("0.959")),
)

_CARTE_GRAPHIQUE: tuple[Attribut, ...] = (
    Attribut("chipset", Role.FILTRE_DUR, Genre.ENUMERE, "processeur graphique"),
    Attribut(
        "memory",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "mémoire vidéo",
        "Go",
        retrogradable=True,
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut(
        "length",
        Role.FILTRE_DUR,
        Genre.NUMERIQUE,
        "longueur",
        "mm",
        taux_remplissage=Decimal("0.965"),
        retrogradable=True,
        sens=Sens.PLUS_BAS_MIEUX,
    ),
    Attribut(
        "core_clock",
        Role.SCORE,
        Genre.NUMERIQUE,
        "fréquence de base",
        "MHz",
        taux_remplissage=Decimal("0.977"),
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut(
        "boost_clock",
        Role.SCORE,
        Genre.NUMERIQUE,
        "fréquence turbo",
        "MHz",
        taux_remplissage=Decimal("0.789"),
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut("color", Role.AFFICHAGE, Genre.ENUMERE, "couleur", taux_remplissage=Decimal("0.988")),
)

# ⚠️ `freq_min_hz` et `freq_max_khz` sont dans **deux unités différentes** : le champ
# source `frequency_response` mélange les hertz et les kilohertz (§ « piège d'unité »
# de `schema_attributs.md`). Leurs bornes n'ont donc pas le même ordre de grandeur, et
# c'est normal.
_CASQUE: tuple[Attribut, ...] = (
    Attribut("type", Role.FILTRE_DUR, Genre.ENUMERE, "type de casque"),
    Attribut("microphone", Role.FILTRE_DUR, Genre.BOOLEEN, "microphone"),
    Attribut("wireless", Role.FILTRE_DUR, Genre.BOOLEEN, "liaison sans fil"),
    Attribut("enclosure_type", Role.FILTRE_DUR, Genre.ENUMERE, "type d'isolation"),
    Attribut(
        "freq_min_hz",
        Role.SCORE,
        Genre.NUMERIQUE,
        "borne basse de réponse en fréquence",
        "Hz",
        taux_remplissage=Decimal("0.825"),
        sens=Sens.PLUS_BAS_MIEUX,
    ),
    Attribut(
        "freq_max_khz",
        Role.SCORE,
        Genre.NUMERIQUE,
        "borne haute de réponse en fréquence",
        "kHz",
        taux_remplissage=Decimal("0.825"),
        sens=Sens.PLUS_HAUT_MIEUX,
    ),
    Attribut("color", Role.AFFICHAGE, Genre.ENUMERE, "couleur"),
)

_PAR_CATEGORIE: dict[Categorie, tuple[Attribut, ...]] = {
    "cpu": _CPU,
    "monitor": _MONITOR,
    "internal-hard-drive": _DISQUE,
    "memory": _MEMOIRE,
    "video-card": _CARTE_GRAPHIQUE,
    "headphones": _CASQUE,
}


def _monter(categorie: Categorie, attribut: Attribut, *, commun: bool) -> Attribut:
    """Greffe les bornes calibrées et le rangement de l'attribut.

    Les bornes sont écrites à part parce qu'elles sont **produites par un script** :
    les mêler aux entrées écrites à la main ferait perdre de vue laquelle des deux
    fait foi quand elles divergent (c'est le script, et un test le vérifie).
    """
    bornes = BORNES_CALIBREES.get((categorie, attribut.champ), (None, None))
    return replace(
        attribut,
        borne_basse=bornes[0],
        borne_haute=bornes[1],
        dans_les_specs=not commun,
    )


ATTRIBUTS: dict[Categorie, dict[str, Attribut]] = {
    categorie: {
        attribut.champ: _monter(categorie, attribut, commun=commun)
        for attributs, commun in ((_COMMUNS, True), (_PAR_CATEGORIE[categorie], False))
        for attribut in attributs
    }
    for categorie in CATEGORIES
}
"""Le registre. Indexé par catégorie **puis** par champ, et pas seulement par champ :
`memory` est une catégorie et un attribut de `video-card`, `type` désigne une
technologie de stockage ici et une forme de casque là, `core_clock` est en GHz chez
`cpu` et en MHz chez `video-card`. Un index plat les confondrait."""


def attribut(categorie: Categorie, champ: str) -> Attribut | None:
    """Rend l'attribut, ou `None` si le champ n'existe pas dans cette catégorie."""
    return ATTRIBUTS[categorie].get(champ)


def champs_incomplets(categorie: Categorie) -> frozenset[str]:
    """Champs dont le seed ne renseigne pas 100 % des produits.

    Constat de **mesure**, recopié du rapport de seed. Ce n'est pas la liste que le
    moteur interroge : voir `champs_a_compter()`.
    """
    return frozenset(
        champ for champ, attr in ATTRIBUTS[categorie].items() if attr.taux_remplissage < COMPLET
    )


def champs_a_compter(categorie: Categorie) -> frozenset[str]:
    """Champs pour lesquels le moteur compte les produits écartés **faute de donnée**.

    Les incomplets, moins ceux dont l'absence est structurelle. Deux exclusions, deux
    raisons :

    * un attribut à 100 % n'a rien à dire, et aucune requête n'est émise pour lui —
      d'où un surcoût nul sur la quasi-totalité des critères ;
    * un attribut à absence structurelle n'a **pas** de donnée manquante : les SSD ne
      sont pas des disques dont on ignore la vitesse de rotation. Les compter ici ferait
      dire au diagnostic une phrase fausse sur le catalogue.
    """
    return frozenset(
        champ
        for champ in champs_incomplets(categorie)
        if not ATTRIBUTS[categorie][champ].absence_structurelle
    )


def valeur_du_produit(produit: ProduitEnBase, attribut: Attribut) -> object:
    """Lit la valeur d'un attribut sur un produit, où qu'elle soit rangée.

    Le registre est le seul endroit qui sache si un champ vit dans une colonne commune
    ou dans le JSONB (`dans_les_specs`) ; le score, la trace et la calibration lui
    posent donc la question plutôt que de la trancher chacun de leur côté.
    """
    porteur: object = produit if not attribut.dans_les_specs else produit.specs
    return getattr(porteur, attribut.champ, None)
