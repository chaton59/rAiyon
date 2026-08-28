"""Transformations déterministes du dataset brut — des fonctions pures, une par cas.

Aucune I/O, aucun état, aucune dépendance au reste du pipeline : c'est ce qui rend
chaque règle testable isolément, et c'est aussi ce qui garantit que la passe A ne
peut pas appeler un modèle de langage — le SDK Anthropic n'est importé nulle part
dans ce fichier ni dans ceux qu'il importe (`tests/test_isolation_passe_a.py`).

**Trois issues, et trois seulement, pour une ligne source** (arbitrage A de l'étape 5) :

1. elle se normalise ;
2. elle lève `LigneEcartee`, et l'orchestrateur la compte au rapport sous son motif ;
3. elle lève `PipelineArrete`, et tout s'arrête en nommant le produit fautif.

Il n'existe pas de quatrième issue. Une valeur inattendue rabotée pour « passer »
serait un bug plus grave que l'arrêt : elle ferait entrer en base un fait que la
source ne dit pas, ce que §2 de PROJET.md interdit.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

# --------------------------------------------------------------------------- #
# Les deux issues d'échec
# --------------------------------------------------------------------------- #


class LigneEcartee(Exception):
    """La ligne ne peut pas être normalisée sans inventer : on la retire, on la compte.

    Le motif est une chaîne courte et **stable** : c'est la clé d'agrégation du
    rapport, pas un message d'erreur destiné à être relu à l'œil.
    """

    def __init__(self, motif: str) -> None:
        super().__init__(motif)
        self.motif = motif


class PipelineArrete(Exception):
    """La règle de normalisation est fausse sur cette ligne — on s'arrête, bruyamment.

    Réservé aux cas où continuer signifierait que l'on a mal compris la source, pas
    qu'une valeur manque. L'étape 3 a montré que la documentation du dataset ment
    (le `smt` promis pour `cpu`, les unités de `frequency_response`) : le seul
    garde-fou qui tienne est un pipeline qui refuse d'avancer sur une surprise.
    """


# --------------------------------------------------------------------------- #
# Marques — §3.4quater
# --------------------------------------------------------------------------- #

MARQUES_MULTI_MOTS: tuple[str, ...] = (
    # Mesurées avant d'être écrites : premiers mots du corpus par fréquence, puis
    # second mot par premier mot (voir « ce que l'étape a appris » dans PROJET.md).
    # Critère d'entrée dans la table, appliqué une par une : le **premier mot seul
    # n'est pas une marque du catalogue**, et le nom complet est celui du fabricant.
    # Un premier mot qui est déjà une marque valide n'entre pas ici, même quand il
    # est toujours suivi du même second mot — « Sabrent Rocket », « JBL Quantum »,
    # « ATI FirePro », « Adesso Xtream », « Anker Soundcore » et « Creative Labs »
    # sont des gammes ou des filiales, pas des marques distinctes.
    "Western Digital",  # 391 lignes — « Western » seul ne désigne rien
    "Silicon Power",  # 87 — « Silicon » seul ne désigne rien
    "Cyber Acoustics",  # 12 — « Cyber » seul ne désigne rien
    "Cooler Master",  # 9 — « Cooler » seul ne désigne rien
    "Turtle Beach",  # 9 — « Turtle » seul ne désigne rien
    "SK Hynix",  # 8 — « SK » seul ne désigne rien
    "Oyen Digital",  # 6 — raison sociale complète du fabricant
    "Titanium Micro",  # 5 — « Titanium » seul ne désigne rien
    "Mad Catz",  # 5 — « Mad » seul ne désigne rien
    "Altec Lansing",  # 4 — « Altec » seul ne désigne rien
    "Etymotic Research",  # 4 — raison sociale complète du fabricant
    "Bang & Olufsen",  # 3 — « Bang » seul ne désigne rien
    "Fantom Drives",  # 3 — « Fantom » seul ne désigne rien
    "Fractal Design",  # 2 — « Fractal » seul ne désigne rien
    "Harman Kardon",  # 2 — « Harman » seul ne désigne rien
    "Pyle Audio",  # 2 — « Pyle » seul est ambigu, « Pyle Audio » est la marque
    "Titan Army",  # 2 — « Titan » seul ne désigne rien
    "Gear Head",  # 1 — « Gear » seul ne désigne rien
    "Meze Audio",  # 1 — « Meze » seul ne désigne rien
)
"""Table **fermée** de marques en plusieurs mots, écrite à la main après mesure.

Fermée veut dire : un nom dont le début ne figure pas ici rend son premier mot, sans
invention et sans repli heuristique. C'est un parsing déterministe documenté, pas une
supposition sur une valeur absente — la distinction est celle de §3.4quater.

⚠️ La règle brute « premier mot de `name` » produirait `Western` pour
« Western Digital Blue » et `Silicon` pour « Silicon Power UD90 ». C'est ce que la
mesure a révélé et que cette table corrige.

Les deux rangs cités ailleurs sont vrais tous les deux, sur deux ensembles différents :
Western Digital est la **6ᵉ marque des 8 863 lignes à prix de la source** (391 lignes)
et la **9ᵉ du seed** (30 produits) — l'échantillonnage stratifié par prix ne conserve
pas les parts de marché. Nommer l'ensemble à chaque chiffre n'est pas de la pédanterie
ici : c'est la confusion des deux qui a produit la prédiction fausse de « 51 lignes
dédupliquées » (cf. PROJET.md, étape 5).
"""

_MARQUES_MULTI_MOTS_EN_JETONS: tuple[tuple[tuple[str, ...], int], ...] = tuple(
    sorted(
        ((tuple(m.lower().split()), len(m.split())) for m in MARQUES_MULTI_MOTS),
        key=lambda entree: -entree[1],
    )
)
# Trié par longueur décroissante : si deux entrées se chevauchaient un jour, c'est la
# plus spécifique qui doit gagner. Aucun chevauchement aujourd'hui, mais l'ordre de
# la table ne doit pas devenir une dépendance cachée du résultat.


def extraire_marque(nom: str) -> str:
    """Rend la marque d'un produit à partir de son nom source (§3.4quater).

    La marque n'existe comme champ dans **aucune** catégorie de la source : c'est une
    transformation, pas une lecture. La règle est « premier mot, casse source
    conservée », corrigée par `MARQUES_MULTI_MOTS`.

    La comparaison à la table est insensible à la casse, mais la valeur rendue est
    **celle du nom source**, jamais l'orthographe de la table : le pipeline ne
    réécrit pas ce que la source a écrit.
    """
    jetons = nom.split()
    if not jetons:
        raise PipelineArrete(f"nom vide ou blanc : {nom!r}")

    minuscules = tuple(jeton.lower() for jeton in jetons)
    for marque, longueur in _MARQUES_MULTI_MOTS_EN_JETONS:
        if minuscules[:longueur] == marque:
            return " ".join(jetons[:longueur])
    return jetons[0]


# --------------------------------------------------------------------------- #
# Conversions numériques
# --------------------------------------------------------------------------- #


def en_decimal(valeur: float | int | str) -> Decimal:
    """Convertit une valeur JSON en `Decimal` sous une forme **canonique**.

    Le passage par `str` évite l'erreur classique `Decimal(0.1)` ; la canonicalisation
    des zéros de queue, elle, est ce qui rend l'identifiant stable : la source écrit
    `5` pour un `boost_clock` et `5.0` pour un autre, et `Decimal("5") != Decimal("5.0")`
    une fois sérialisés en chaînes dans la clé de déduplication — deux identifiants
    différents pour la même valeur physique.

    `quantize(Decimal(1))` plutôt que `normalize()` sur les entiers : `normalize()`
    rendrait `Decimal("1E+2")` pour 100, ce qui casserait la sérialisation.
    """
    nombre = Decimal(str(valeur))
    if nombre == nombre.to_integral_value():
        return nombre.quantize(Decimal(1))
    return nombre.normalize()


def normaliser_prix(valeur: object) -> Decimal:
    """Rend le prix en USD à la précision de la colonne `numeric(10,2)`.

    Écrire le seed à la précision de stockage rend l'aller-retour base exact : sans
    cela, `451.5` en JSONL revient `451.50` de Postgres, et le test d'intégration
    d'idempotence compare deux écritures différentes du même nombre.

    Aucun arrondi n'a lieu en pratique — les 9 687 prix de la source ont au plus deux
    décimales — et s'il en survenait un, c'est qu'on aurait mal lu la source : arrêt.
    """
    if not isinstance(valeur, int | float) or isinstance(valeur, bool):
        raise PipelineArrete(f"prix de type inattendu : {valeur!r}")
    exact = Decimal(str(valeur))
    arrondi = exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if arrondi != exact:
        raise PipelineArrete(
            f"prix à plus de deux décimales : {exact} — la colonne est numeric(10,2), "
            "arrondir ici modifierait un fait"
        )
    return arrondi


def calculer_price_per_gb(prix_usd: Decimal, capacite_gb: int) -> Decimal:
    """Recalcule le prix au gigaoctet à partir du **prix retenu** (arbitrage D).

    Jamais recopié de la source : la déduplication garde le prix le plus bas d'un
    groupe, donc la valeur source peut décrire un prix qui n'est plus celui du
    produit. Deux champs qui disent des choses différentes du même fait sont
    exactement ce que §3.10 cherche à rendre impossible ailleurs.

    `Decimal` et `ROUND_HALF_UP`, jamais de flottant : `0.1 + 0.2` n'est pas `0.3`, et
    un rapport capacité/prix est un critère de décision réel du domaine.
    """
    if capacite_gb <= 0:
        raise PipelineArrete(f"capacité nulle ou négative : {capacite_gb}")
    return (prix_usd / Decimal(capacite_gb)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# `internal-hard-drive`
# --------------------------------------------------------------------------- #


def normaliser_type_disque(valeur: object) -> tuple[Literal["SSD", "HDD"], int | None]:
    """`"SSD"` ou un entier de tours/minute → `(type, rpm)`.

    La source code deux informations dans un champ unique : la chaîne `"SSD"` (1 398
    lignes) ou la vitesse de rotation d'un disque à plateaux (697 lignes).

    **Les 8 lignes sans `type` (0,4 %) sont écartées**, et c'est une décision, pas un
    oubli : `type` est un filtre dur et le premier arbitrage du domaine. Un produit
    dont on ignore s'il est SSD ou HDD ne peut pas être filtré correctement, et un
    client qui demande un SSD ne doit pas recevoir un doute. L'écarter n'invente rien,
    le combler oui (§3.4quater). Alternative écartée — le garder avec `type=None` : le
    moteur de l'étape 6 devrait alors porter une troisième branche pour l'inconnu, sur
    8 produits.
    """
    if valeur is None:
        raise LigneEcartee("type de disque absent")
    if valeur == "SSD":
        return "SSD", None
    if isinstance(valeur, int | float) and not isinstance(valeur, bool):
        rpm = int(valeur)
        if rpm != valeur or rpm <= 0:
            raise PipelineArrete(f"vitesse de rotation non entière ou négative : {valeur!r}")
        return "HDD", rpm
    raise PipelineArrete(
        f"valeur de `type` inattendue : {valeur!r} — la source n'écrit que "
        '"SSD" ou un entier de tours/minute'
    )


_FORM_FACTORS_NUMERIQUES = {Decimal("2.5"): '2.5"', Decimal("3.5"): '3.5"'}


def normaliser_form_factor(valeur: object) -> str:
    """`2.5` / `3.5` en nombre ou `"M.2-2280"` en chaîne → une seule énumération textuelle.

    Les nombres deviennent des pouces explicites (`2.5"`), les chaînes passent
    inchangées. Sans le guillemet, `2.5` et `"2.5"` cohabiteraient dans la même
    colonne sous deux types JSON différents, et un filtre d'égalité en manquerait la
    moitié.
    """
    if isinstance(valeur, str):
        if not valeur.strip():
            raise PipelineArrete("`form_factor` est une chaîne vide")
        return valeur
    if isinstance(valeur, int | float) and not isinstance(valeur, bool):
        pouces = Decimal(str(valeur))
        if pouces in _FORM_FACTORS_NUMERIQUES:
            return _FORM_FACTORS_NUMERIQUES[pouces]
        raise PipelineArrete(
            f"format numérique inattendu : {valeur!r} — seuls 2.5 et 3.5 sont mesurés"
        )
    raise PipelineArrete(f"valeur de `form_factor` inattendue : {valeur!r}")


# --------------------------------------------------------------------------- #
# `memory`
# --------------------------------------------------------------------------- #


def eclater_speed_memoire(valeur: object) -> tuple[int, int]:
    """`[gen, mhz]` → `(ddr_generation, frequence_mhz)`.

    `speed[0]` code la génération DDR (2 à 5 dans la source), `speed[1]` la fréquence
    en MHz. La génération est le filtre dur le plus net du catalogue : de la DDR4 ne
    s'insère pas physiquement dans un socket DDR5.
    """
    generation, frequence = _paire_entiere(valeur, "speed")
    return generation, frequence


def eclater_modules_memoire(valeur: object) -> tuple[int, int, int]:
    """`[nb, taille]` → `(nb_modules, taille_module_gb, capacite_totale_gb)`.

    La capacité totale est **calculée ici et nulle part ailleurs** : le validateur
    croisé de `SpecsMemoire` la recalcule et refuse le produit si les deux ne
    concordent pas. La lire à un autre endroit ferait diverger deux copies du même
    fait — et c'est cette colonne que le client interroge (« il me faut 32 Go »).
    """
    nb_modules, taille_module = _paire_entiere(valeur, "modules")
    return nb_modules, taille_module, nb_modules * taille_module


def _paire_entiere(valeur: object, champ: str) -> tuple[int, int]:
    """Lit un couple d'entiers `[a, b]`, et refuse tout le reste."""
    if not isinstance(valeur, list) or len(valeur) != 2:
        raise PipelineArrete(f"`{champ}` n'est pas un couple : {valeur!r}")
    entiers: list[int] = []
    for composante in valeur:
        if not isinstance(composante, int | float) or isinstance(composante, bool):
            raise PipelineArrete(f"`{champ}` porte une composante non numérique : {valeur!r}")
        entier = int(composante)
        if entier != composante:
            raise PipelineArrete(f"`{champ}` porte une composante non entière : {valeur!r}")
        entiers.append(entier)
    return entiers[0], entiers[1]


# --------------------------------------------------------------------------- #
# `headphones` — le piège d'unité
# --------------------------------------------------------------------------- #

PLAGE_CONTROLE_FREQ_MIN_HZ = (Decimal(1), Decimal(1000))
PLAGE_CONTROLE_FREQ_MAX_KHZ = (Decimal("0.5"), Decimal(200))


def eclater_frequency_response(valeur: object, nom_produit: str) -> tuple[int, Decimal]:
    """`[a, b]` → `(freq_min_hz, freq_max_khz)`. **Par position, jamais par min/max.**

    `API.md` annonce les deux composantes en kHz. C'est faux pour la première :
    `["HP HyperX Cloud II", [15, 25]]` se lit 15 **Hz** - 25 **kHz**. Les 32 cas où
    `fr[0] > fr[1]` ne sont donc pas des inversions — `[100, 10]` est un casque de
    communication à 100 Hz - 10 kHz — et un correctif `min`/`max` détruirait la
    donnée sur ces 32 produits.

    **Contrôle par ordre de grandeur.** La composante 0 doit tomber dans
    `[1, 1000]` Hz et la composante 1 dans `[0,5, 200]` kHz. Une valeur hors plage
    signifierait que la règle de position est fausse sur cet enregistrement : c'est
    précisément le mode d'erreur que l'étape 3 a attrapé sur la documentation de la
    source. On s'arrête et on nomme le produit, on ne devine pas.
    """
    if not isinstance(valeur, list) or len(valeur) != 2:
        raise PipelineArrete(f"`frequency_response` n'est pas un couple : {valeur!r}")

    composantes: list[Decimal] = []
    for composante in valeur:
        if not isinstance(composante, int | float) or isinstance(composante, bool):
            raise PipelineArrete(
                f"`frequency_response` non numérique sur {nom_produit!r} : {valeur!r}"
            )
        composantes.append(en_decimal(composante))

    minimum_hz, maximum_khz = composantes
    _verifier_plage(minimum_hz, PLAGE_CONTROLE_FREQ_MIN_HZ, "composante 0 (Hz)", nom_produit)
    _verifier_plage(maximum_khz, PLAGE_CONTROLE_FREQ_MAX_KHZ, "composante 1 (kHz)", nom_produit)

    if minimum_hz != minimum_hz.to_integral_value():
        raise PipelineArrete(
            f"`frequency_response[0]` non entier sur {nom_produit!r} : {minimum_hz} — "
            "la colonne cible est un entier de hertz"
        )
    return int(minimum_hz), maximum_khz


def _verifier_plage(
    valeur: Decimal, plage: tuple[Decimal, Decimal], quoi: str, nom_produit: str
) -> None:
    """Arrête le pipeline si une composante sort de son ordre de grandeur attendu."""
    bas, haut = plage
    if not (bas <= valeur <= haut):
        raise PipelineArrete(
            f"`frequency_response` — {quoi} vaut {valeur} sur {nom_produit!r}, hors de "
            f"la plage de contrôle [{bas}, {haut}]. La règle de position est donc "
            "fausse sur cet enregistrement : à comprendre avant de continuer, pas à corriger."
        )


# --------------------------------------------------------------------------- #
# `monitor`
# --------------------------------------------------------------------------- #


def eclater_resolution(valeur: object) -> tuple[int, int]:
    """`[largeur, hauteur]` → `(largeur_px, hauteur_px)`."""
    return _paire_entiere(valeur, "resolution")


# --------------------------------------------------------------------------- #
# Assemblage des specs, catégorie par catégorie
# --------------------------------------------------------------------------- #


def _entier(valeur: object, champ: str) -> int:
    """Lit un entier, et refuse un flottant qui n'en est pas un."""
    if not isinstance(valeur, int | float) or isinstance(valeur, bool):
        raise PipelineArrete(f"`{champ}` non numérique : {valeur!r}")
    entier = int(valeur)
    if entier != valeur:
        raise PipelineArrete(f"`{champ}` non entier : {valeur!r}")
    return entier


def _texte(valeur: object, champ: str) -> str:
    """Lit une chaîne non vide."""
    if not isinstance(valeur, str) or not valeur.strip():
        raise PipelineArrete(f"`{champ}` n'est pas une chaîne exploitable : {valeur!r}")
    return valeur


def _booleen(valeur: object, champ: str) -> bool:
    """Lit un booléen strict — `0` et `1` ne sont pas des booléens ici."""
    if not isinstance(valeur, bool):
        raise PipelineArrete(f"`{champ}` n'est pas un booléen : {valeur!r}")
    return valeur


def _optionnel(ligne: dict[str, Any], champ: str, lecture: Any) -> Any:  # noqa: ANN401
    """Applique `lecture` si la valeur est présente, rend `None` sinon.

    **Aucune transformation ne remplit un champ vide**, quelle que soit la
    vraisemblance de la valeur : une absence traverse le pipeline en restant une
    absence (§3.4quater).
    """
    valeur = ligne.get(champ)
    return None if valeur is None else lecture(valeur)


def specs_cpu(ligne: dict[str, Any]) -> dict[str, Any]:
    """Specs d'un processeur. Aucun champ source hétérogène ici."""
    return {
        "core_count": _entier(ligne.get("core_count"), "core_count"),
        "core_clock": en_decimal(ligne["core_clock"]),
        "tdp": _entier(ligne.get("tdp"), "tdp"),
        "microarchitecture": _texte(ligne.get("microarchitecture"), "microarchitecture"),
        "boost_clock": _optionnel(ligne, "boost_clock", en_decimal),
        "graphics": _optionnel(ligne, "graphics", lambda v: _texte(v, "graphics")),
    }


def specs_moniteur(ligne: dict[str, Any]) -> dict[str, Any]:
    """Specs d'un écran. `resolution` est le seul champ éclaté."""
    largeur, hauteur = eclater_resolution(ligne.get("resolution"))
    return {
        "screen_size": en_decimal(ligne["screen_size"]),
        "largeur_px": largeur,
        "hauteur_px": hauteur,
        "aspect_ratio": _texte(ligne.get("aspect_ratio"), "aspect_ratio"),
        "panel_type": _optionnel(ligne, "panel_type", lambda v: _texte(v, "panel_type")),
        "refresh_rate": _optionnel(ligne, "refresh_rate", lambda v: _entier(v, "refresh_rate")),
        "response_time": _optionnel(ligne, "response_time", en_decimal),
    }


def specs_disque_interne(ligne: dict[str, Any]) -> dict[str, Any]:
    """Specs d'un disque interne. `price_per_gb` est **absent** : il vient après la dédup.

    C'est le piège central de l'étape (arbitrage D). `price_per_gb` est une fonction
    du prix ; le laisser ici le ferait entrer dans la clé de déduplication, et deux
    enregistrements identiques à prix différents ne se rejoindraient jamais.
    """
    type_disque, rpm = normaliser_type_disque(ligne.get("type"))
    return {
        "capacity": _entier(ligne.get("capacity"), "capacity"),
        "form_factor": normaliser_form_factor(ligne.get("form_factor")),
        "interface": _texte(ligne.get("interface"), "interface"),
        "type": type_disque,
        "rpm": rpm,
        "cache": _optionnel(ligne, "cache", lambda v: _entier(v, "cache")),
    }


def specs_memoire(ligne: dict[str, Any]) -> dict[str, Any]:
    """Specs d'un module mémoire. `price_per_gb` vient après la dédup (arbitrage D)."""
    generation, frequence = eclater_speed_memoire(ligne.get("speed"))
    nb_modules, taille_module, capacite_totale = eclater_modules_memoire(ligne.get("modules"))
    return {
        "ddr_generation": generation,
        "frequence_mhz": frequence,
        "nb_modules": nb_modules,
        "taille_module_gb": taille_module,
        "capacite_totale_gb": capacite_totale,
        "cas_latency": _entier(ligne.get("cas_latency"), "cas_latency"),
        "first_word_latency": en_decimal(ligne["first_word_latency"]),
        "color": _optionnel(ligne, "color", lambda v: _texte(v, "color")),
    }


def specs_carte_graphique(ligne: dict[str, Any]) -> dict[str, Any]:
    """Specs d'une carte graphique."""
    return {
        "chipset": _texte(ligne.get("chipset"), "chipset"),
        "memory": en_decimal(ligne["memory"]),
        "length": _optionnel(ligne, "length", lambda v: _entier(v, "length")),
        "core_clock": _optionnel(ligne, "core_clock", lambda v: _entier(v, "core_clock")),
        "boost_clock": _optionnel(ligne, "boost_clock", lambda v: _entier(v, "boost_clock")),
        "color": _optionnel(ligne, "color", lambda v: _texte(v, "color")),
    }


def specs_casque(ligne: dict[str, Any], nom_produit: str) -> dict[str, Any]:
    """Specs d'un casque. Porte le piège d'unité de `frequency_response`."""
    reponse = ligne.get("frequency_response")
    freq_min_hz, freq_max_khz = (
        (None, None) if reponse is None else eclater_frequency_response(reponse, nom_produit)
    )
    return {
        "type": _texte(ligne.get("type"), "type"),
        "microphone": _booleen(ligne.get("microphone"), "microphone"),
        "wireless": _booleen(ligne.get("wireless"), "wireless"),
        "enclosure_type": _texte(ligne.get("enclosure_type"), "enclosure_type"),
        "freq_min_hz": freq_min_hz,
        "freq_max_khz": freq_max_khz,
        "color": _optionnel(ligne, "color", lambda v: _texte(v, "color")),
    }


def construire_specs(categorie: str, ligne: dict[str, Any], nom_produit: str) -> dict[str, Any]:
    """Aiguille vers le constructeur de specs de la catégorie.

    Les grandeurs dérivées du prix ne sont **jamais** produites ici : elles sont
    calculées après la déduplication, sur le prix retenu (arbitrage D, transformation 6).
    """
    if categorie == "cpu":
        return specs_cpu(ligne)
    if categorie == "monitor":
        return specs_moniteur(ligne)
    if categorie == "internal-hard-drive":
        return specs_disque_interne(ligne)
    if categorie == "memory":
        return specs_memoire(ligne)
    if categorie == "video-card":
        return specs_carte_graphique(ligne)
    if categorie == "headphones":
        return specs_casque(ligne, nom_produit)
    raise PipelineArrete(f"catégorie hors périmètre : {categorie!r}")


def ajouter_grandeurs_derivees_du_prix(
    categorie: str, specs: dict[str, Any], prix_usd: Decimal
) -> dict[str, Any]:
    """Ajoute `price_per_gb` **après** la déduplication, sur le prix retenu.

    Rend un nouveau dictionnaire plutôt que de muter celui reçu : la clé canonique a
    déjà été calculée sur `specs`, et une mutation en place rendrait l'ordre des
    opérations du pipeline invisible à la relecture.
    """
    if categorie == "internal-hard-drive":
        return {**specs, "price_per_gb": calculer_price_per_gb(prix_usd, specs["capacity"])}
    if categorie == "memory":
        return {
            **specs,
            "price_per_gb": calculer_price_per_gb(prix_usd, specs["capacite_totale_gb"]),
        }
    return dict(specs)
