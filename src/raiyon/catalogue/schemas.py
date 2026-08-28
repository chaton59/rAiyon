"""Modèles Pydantic miroirs du schéma SQL — le point d'entrée unique de l'insertion.

Rien n'entre en base sans passer par `ProduitEnBase`. Les colonnes communes y sont
typées, et `specs` est validé par un modèle **par catégorie**, réunis en union
discriminée : un produit `cpu` porteur d'un `screen_size` est rejeté ici, avant
d'atteindre SQL. C'est ce qui donne un sens à « rien n'entre en base sans avoir été
typé et validé » — sans `extra="forbid"`, une clé inconnue dormirait dans le JSONB.

Deux règles gouvernent ce fichier, et elles viennent de la **mesure** de l'étape 3
(`catalogue/schema_attributs.md`), jamais de la documentation de la source — celle-ci
a menti au moins une fois : le champ `smt` qu'elle promet pour `cpu` n'existe dans
aucun enregistrement.

1. **Obligatoire si et seulement si le taux de remplissage mesuré vaut 100 %.**
   Sans exception, y compris pour un attribut conceptuellement essentiel :
   `internal-hard-drive.type` est à 99,6 %, il est donc `| None` ici. Écarter les
   0,4 % restants est une décision de pipeline (étape 5) ; la prendre à ce niveau
   reviendrait à combler une absence, ce que PROJET.md §3.4quater interdit.
2. **Les bornes numériques sont physiquement plausibles, pas mesurées.** Elles
   englobent largement la plage observée : un produit qui bat un record ne doit pas
   être rejeté par le schéma. La plage observée, avec son unité, est en commentaire
   à côté de chaque borne.
"""

from decimal import Decimal
from typing import Annotated, Any, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

Categorie = Literal[
    "cpu",
    "monitor",
    "internal-hard-drive",
    "memory",
    "video-card",
    "headphones",
]

CATEGORIES: tuple[Categorie, ...] = get_args(Categorie)
"""Les 6 catégories retenues (PROJET.md §3.4bis). `keyboard` a été retirée : elle
n'atteint 5 attributs discriminants qu'en lisant `switches = null` comme
« membrane », ce qui est un comblement d'absence."""

MOTIF_ID = r"^[a-z-]+-[0-9a-f]{10}$"
"""Forme de l'identifiant synthétique : `{categorie}-{10 hexadécimaux}`.

Les 10 caractères sont un préfixe de `sha256` de la clé de déduplication ; le calcul
est écrit à l'étape 5, on ne contrôle ici que la forme. Deux raisons à ce format :
rejouer le pipeline redonne les mêmes identifiants, donc le diff du seed reste
lisible ; et un ID inventé par le LLM est trivialement détectable par le validateur
de l'étape 9, ce qui ne serait pas le cas d'un slug reconstituable depuis le nom."""


class _SpecsBase(BaseModel):
    """Base commune aux specs de catégorie.

    `extra="forbid"` n'est pas un réglage de confort : c'est lui qui transforme
    « le pipeline s'est trompé de catégorie » d'un silence en une erreur.
    """

    model_config = ConfigDict(extra="forbid")


class SpecsCpu(_SpecsBase):
    """Processeurs — 547 produits à prix. 4 attributs à 100 %, plus la marque."""

    categorie: Literal["cpu"]

    core_count: int = Field(ge=1, le=256)  # cœurs — observé 1-64 (méd. 4)
    core_clock: Decimal = Field(gt=0, le=10, max_digits=5, decimal_places=3)  # GHz — 1,60-4,70
    tdp: int = Field(ge=1, le=1000)  # W — observé 35-280 (méd. 72)
    microarchitecture: str = Field(min_length=1)  # 33 valeurs — `Kaby Lake` … `Zen 5`

    # 65,1 % de remplissage : l'absence est corrélée à la génération (Pentium E5700,
    # Core i7-3770…), elle n'est pas aléatoire. Optionnelle, donc.
    boost_clock: Decimal | None = Field(default=None, gt=0, le=10, max_digits=5, decimal_places=3)
    graphics: str | None = None  # 51,6 % — 35 valeurs


class SpecsMoniteur(_SpecsBase):
    """Écrans — 1 367 produits à prix. Le champ source `resolution` est éclaté en deux."""

    categorie: Literal["monitor"]

    screen_size: Decimal = Field(gt=0, le=200, max_digits=5, decimal_places=2)  # pouces — 14-65
    largeur_px: int = Field(ge=1, le=32768)  # px — observé 1024-7680
    hauteur_px: int = Field(ge=1, le=32768)  # px — observé 768-4320
    aspect_ratio: str = Field(min_length=1)  # 11 valeurs, dont 83,5 % de `16:9`

    panel_type: str | None = None  # 96,5 % — `IPS` 61,2 %, `VA` 24,0 %, `TN` 6,3 %
    refresh_rate: int | None = Field(default=None, ge=1, le=2000)  # Hz — 60-600 — 95,2 %
    # 78,3 %, et la valeur descend à 0,01 ms (dalle OLED annoncée par le constructeur,
    # pas une mesure). Bornée bas par `gt=0`, pas par la plus petite valeur vue.
    response_time: Decimal | None = Field(
        default=None, gt=0, le=1000, max_digits=6, decimal_places=2
    )  # ms — observé 0,01-20


class SpecsDisqueInterne(_SpecsBase):
    """Stockage interne — 2 103 produits à prix. Deux champs sources hétérogènes normalisés."""

    categorie: Literal["internal-hard-drive"]

    capacity: int = Field(ge=1, le=1_000_000)  # GB — observé 32-26 000 (méd. 1 000)
    form_factor: str = Field(min_length=1)  # énum. normalisée — `M.2-2280`, `2.5"`, `3.5"`…
    interface: str = Field(min_length=1)  # 18 valeurs — `SATA 6.0 Gb/s` 44,8 %

    # 99,6 % : obligatoire au niveau du domaine, optionnel au niveau du modèle.
    # C'est l'étape 5 qui décidera d'écarter ou non les lignes concernées ; trancher
    # ici reviendrait à combler l'absence (§3.4quater).
    type: Literal["SSD", "HDD"] | None = None
    rpm: int | None = Field(default=None, ge=1, le=100_000)  # tr/min — 5 400 / 7 200 / 15 000
    price_per_gb: Decimal | None = Field(
        default=None, gt=0, le=100_000, max_digits=9, decimal_places=3
    )  # USD/GB — observé 0,015-4,530 — 97,4 %, grandeur dérivée de `price` et `capacity`
    cache: int | None = Field(default=None, ge=0, le=1_048_576)  # MB — 8-8 192 — 36,5 %

    @model_validator(mode="after")
    def _coherence_type_rpm(self) -> Self:
        """Un SSD n'a pas de tours par minute, un HDD en a forcément un.

        La source code les deux dans un champ unique (`"SSD"` ou un entier de
        tours/minute). Si la normalisation de l'étape 5 se trompe de branche, c'est
        ici que ça se voit — et pas trois étapes plus loin dans un score.
        """
        if self.type == "SSD" and self.rpm is not None:
            raise ValueError("un SSD n'a pas de vitesse de rotation : `rpm` doit rester absent")
        if self.type == "HDD" and self.rpm is None:
            raise ValueError("un HDD sans `rpm` : la vitesse de rotation a été perdue")
        return self


class SpecsMemoire(_SpecsBase):
    """Mémoire vive — 2 907 produits à prix. `speed` et `modules` éclatés en quatre colonnes."""

    categorie: Literal["memory"]

    ddr_generation: int = Field(ge=1, le=9)  # génération DDR — observé DDR2 à DDR5
    frequence_mhz: int = Field(ge=1, le=100_000)  # MHz — observé 400-8 400 (méd. 3 600)
    nb_modules: int = Field(ge=1, le=64)  # barrettes — observé 1-8
    taille_module_gb: int = Field(ge=1, le=4096)  # GB par barrette — observé 1-64
    capacite_totale_gb: int = Field(ge=1, le=262_144)  # GB — dérivée, cf. validateur ci-dessous
    cas_latency: int = Field(ge=1, le=1000)  # cycles — observé 3-52 (méd. 19)
    first_word_latency: Decimal = Field(gt=0, le=10_000, max_digits=8, decimal_places=3)  # ns

    # 98,1 %. Monte à 497,5 USD/GB sur des modules de très faible capacité : valeur
    # réelle, conservée telle quelle. C'est le sous-score de l'étape 6 qui devra être
    # borné, pas la donnée qui doit être corrigée.
    price_per_gb: Decimal | None = Field(
        default=None, gt=0, le=100_000, max_digits=9, decimal_places=3
    )  # USD/GB — observé 1,059-497,500
    color: str | None = None  # 94,4 % — rôle `affichage`, n'entre jamais dans le matching

    @model_validator(mode="after")
    def _coherence_capacite_totale(self) -> Self:
        """`capacite_totale_gb` est une grandeur dérivée : elle doit se recalculer.

        Si l'égalité ne tient pas, la donnée est corrompue — et c'est précisément
        cette colonne que le client interroge (« il me faut 32 Go »).
        """
        attendu = self.nb_modules * self.taille_module_gb
        if self.capacite_totale_gb != attendu:
            raise ValueError(
                f"capacite_totale_gb={self.capacite_totale_gb} ne vaut pas "
                f"nb_modules x taille_module_gb = {attendu}"
            )
        return self


class SpecsCarteGraphique(_SpecsBase):
    """Cartes graphiques — 1 275 produits à prix."""

    categorie: Literal["video-card"]

    chipset: str = Field(min_length=1)  # 241 valeurs — `GeForce RTX 5060 Ti`…
    memory: Decimal = Field(gt=0, le=1024, max_digits=6, decimal_places=3)  # GB VRAM — 0,25-48

    length: int | None = Field(default=None, ge=1, le=2000)  # mm — observé 115-360 — 97,5 %
    core_clock: int | None = Field(default=None, ge=1, le=100_000)  # MHz — 115-2 740 — 98,4 %
    # 80,3 %, soit 0,3 point au-dessus du seuil de la porte de sortie : 4 produits de
    # moins et la catégorie basculait. Ce n'est pas une marge, c'est une coïncidence.
    boost_clock: int | None = Field(default=None, ge=1, le=100_000)  # MHz — observé 876-3 320
    color: str | None = None  # 98,5 % — rôle `affichage`


class SpecsCasque(_SpecsBase):
    """Casques — 664 produits à prix. Porte le piège d'unité le plus dangereux du dataset."""

    categorie: Literal["headphones"]

    type: Literal["Circumaural", "Supra-aural", "In Ear", "Earbud"]
    microphone: bool
    wireless: bool
    enclosure_type: Literal["Closed", "Open", "Semi-open"]

    # ⚠️ `frequency_response` mélange deux unités dans un même champ source :
    # `[15, 25]` se lit 15 **Hz** - 25 **kHz**. D'où deux colonnes d'unités
    # différentes, et des bornes qui n'ont pas le même ordre de grandeur.
    freq_min_hz: int | None = Field(default=None, ge=1, le=100_000)  # Hz — observé 4-150
    freq_max_khz: Decimal | None = Field(
        default=None, gt=0, le=1000, max_digits=6, decimal_places=2
    )  # kHz — observé 2-75
    color: str | None = None  # 98,6 % — rôle `affichage`

    # ⛔ N'ajoute pas ici de validateur `freq_min <= freq_max`. Les deux champs sont
    # dans des unités différentes : `freq_min_hz=100` avec `freq_max_khz=10` est un
    # casque de communication MSI parfaitement valide (100 Hz - 10 kHz). Les 32
    # « inversions » du dataset s'expliquent toutes par là, il n'y a aucune inversion
    # réelle, et un correctif `min`/`max` détruirait la donnée sur ces 32 produits.
    # Le test `test_casque_frequences_en_unites_differentes_acceptees` garde ce point.


Specs = Annotated[
    SpecsCpu
    | SpecsMoniteur
    | SpecsDisqueInterne
    | SpecsMemoire
    | SpecsCarteGraphique
    | SpecsCasque,
    Field(discriminator="categorie"),
]
"""Union discriminée sur `categorie`. Pydantic route vers le bon modèle sans essayer
les six à la suite : le message d'erreur désigne la catégorie concernée au lieu de
lister six échecs."""


class ProduitEnBase(BaseModel):
    """Un produit validé, prêt pour l'insertion. Seule porte d'entrée de la table.

    Le pipeline de l'étape 5 construit ce modèle ; `Produit.depuis_schema()` le
    convertit en ligne SQL. Aucune autre voie n'est prévue.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=MOTIF_ID)
    nom: str = Field(min_length=1)  # nom source, en anglais
    nom_fr: str | None = None  # rempli par la passe LLM de l'étape 5
    marque: str = Field(min_length=1)  # premier mot de `name` (§3.4quater)
    categorie: Categorie
    prix_usd: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    # ⚠️ Champ **généré** par le LLM (§3.4ter) : il n'est pas factuel. Il ne doit
    # jamais servir de critère de filtrage ni entrer dans un score — c'est un piège
    # que le moteur de l'étape 6 peut tendre, parce que le texte y est tentant.
    description: str | None = None
    disponible: bool = True
    specs: Specs

    @model_validator(mode="before")
    @classmethod
    def _propager_la_categorie(cls, donnees: Any) -> Any:  # noqa: ANN401
        """Injecte `categorie` dans `specs` pour rendre la discrimination possible.

        La catégorie vit dans une colonne de `produits`. La stocker **aussi** dans le
        JSONB ouvrirait la possibilité que les deux divergent — exactement le mode
        d'échec que §3.10 cherche à rendre impossible sur le budget. Elle est donc
        injectée juste avant la discrimination, et retirée par `specs_pour_base()`
        juste avant l'écriture. Les deux opérations sont voisines dans ce fichier
        pour qu'on ne puisse pas toucher à l'une en oubliant l'autre.
        """
        if isinstance(donnees, dict):
            specs = donnees.get("specs")
            categorie = donnees.get("categorie")
            if isinstance(specs, dict) and categorie is not None and "categorie" not in specs:
                return {**donnees, "specs": {**specs, "categorie": categorie}}
        return donnees

    @model_validator(mode="after")
    def _coherence_categorie_et_id(self) -> Self:
        """La catégorie, le préfixe de l'identifiant et les specs disent la même chose."""
        if self.specs.categorie != self.categorie:
            raise ValueError(
                f"specs de catégorie {self.specs.categorie!r} sur un produit {self.categorie!r}"
            )
        if not self.id.startswith(f"{self.categorie}-"):
            raise ValueError(
                f"l'identifiant {self.id!r} ne porte pas le préfixe de sa catégorie "
                f"{self.categorie!r} — format attendu : {{categorie}}-{{10 hexadécimaux}}"
            )
        return self

    def specs_pour_base(self) -> dict[str, Any]:
        """Rend `specs` sous la forme écrite dans la colonne JSONB.

        `mode="json"` sérialise les `Decimal` en **chaînes**, pas en flottants. C'est
        voulu : `0.087` en flottant ne revient pas exact d'un aller-retour JSON, alors
        qu'une chaîne revient au caractère près. Les filtres de plage n'y perdent rien,
        `specs->>'price_per_gb'` rendant du texte dans les deux cas, et le cast
        `::numeric` fonctionnant à l'identique. Conséquence à connaître : une
        containment `@>` sur une valeur numérique doit comparer une **chaîne**.

        Les clés absentes sont conservées à `null` plutôt que retirées : la forme du
        JSONB reste constante par catégorie, ce dont le rapport de remplissage de
        l'étape 5 et le validateur de l'étape 9 ont besoin.
        """
        return self.specs.model_dump(mode="json", exclude={"categorie"})
