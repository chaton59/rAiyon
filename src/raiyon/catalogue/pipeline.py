"""Passe A — orchestration de la normalisation déterministe, et son rapport.

**Aucun modèle de langage ici, ni dans aucun module importé par celui-ci.** Tous les
faits — prix, marque, attributs, identifiant — sortent de cette passe et d'elle seule,
et depuis le retrait de la passe B (§3.4ter) il n'existe plus aucune autre source :
le seed ne contient rien qu'un modèle ait écrit. Un test le vérifie sur **tous** les
modules de `raiyon.catalogue`, en contrôlant qu'aucun ne charge le SDK Anthropic
(arbitrage B de l'étape 5).

**L'ordre des opérations n'est pas commutatif** et le code le suit littéralement :

1. lecture ; 2. filtrage sur le prix ; 3. normalisation ; 4. clé canonique et `id` ;
5. déduplication ; 6. grandeurs dérivées du prix ; 7. validation ; 8. sélection ;
9. écriture.

L'étape 6 vient **après** la 5 : c'est tout le piège de l'arbitrage D. Calculer
`price_per_gb` avant la déduplication le ferait entrer dans la clé, et deux
enregistrements identiques à prix différents ne se rejoindraient jamais.
"""

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from raiyon.catalogue.identite import (
    LigneNormalisee,
    StatsDeduplication,
    calculer_id,
    cle_canonique,
    dedupliquer,
)
from raiyon.catalogue.normalisation import (
    LigneEcartee,
    PipelineArrete,
    ajouter_grandeurs_derivees_du_prix,
    calculer_price_per_gb,
    construire_specs,
    en_decimal,
    extraire_marque,
    normaliser_prix,
)
from raiyon.catalogue.schemas import CATEGORIES, ProduitEnBase
from raiyon.catalogue.selection import (
    CHAMPS_DERIVES_DU_PRIX,
    CIBLE_PAR_CATEGORIE,
    GRAINE_TIRAGE,
    ResultatSelection,
    selectionner,
)

RACINE = Path(__file__).resolve().parents[3]
BRUT = RACINE / "data" / "raw"
SEED = RACINE / "data" / "seed"
FICHIER_SEED = SEED / "produits.jsonl"
FICHIER_RAPPORT = SEED / "rapport_seed.md"

CATEGORIE_RETIREE = "keyboard"
"""Retirée à l'étape 3 (§3.4bis) : 4 attributs discriminants, il en faut 5.

Ses lignes sont comptées dans l'entonnoir — sinon le total « lues » ne correspondrait
à aucun fichier réel — puis écartées immédiatement. Elle n'apparaît nulle part
ailleurs : ni dans les taux de remplissage, ni dans les marques, ni dans le seed.
"""

# Énumérations dont le rapport liste les valeurs distinctes. C'est ainsi qu'on voit
# qu'aucune forme inattendue n'est passée à travers la normalisation — en
# particulier sur `form_factor`, où deux types JSON différents ont fusionné en un.
ENUMERATIONS: dict[str, tuple[str, ...]] = {
    "cpu": ("microarchitecture",),
    "monitor": ("aspect_ratio", "panel_type"),
    "internal-hard-drive": ("type", "form_factor", "interface"),
    "memory": ("ddr_generation",),
    "video-card": (),
    "headphones": ("type", "enclosure_type"),
}

SEUIL_ECART_PRICE_PER_GB = Decimal("0.01")
"""1 % d'écart relatif, et 1 % de lignes au-delà : au-dessus, on s'arrête.

Si la source ne calculait pas ce qu'on croit, la transformation 6 serait fausse — et
c'est exactement le mode d'erreur que l'étape 3 a attrapé sur la documentation.
"""


# --------------------------------------------------------------------------- #
# Ce que l'on compte en chemin
# --------------------------------------------------------------------------- #


@dataclass
class Entonnoir:
    """Le décompte ligne à ligne, par catégorie. C'est le cœur du rapport."""

    lues: Counter[str] = field(default_factory=Counter)
    sans_prix: Counter[str] = field(default_factory=Counter)
    a_prix: Counter[str] = field(default_factory=Counter)
    normalisees: Counter[str] = field(default_factory=Counter)
    dedupliquees: Counter[str] = field(default_factory=Counter)
    validees: Counter[str] = field(default_factory=Counter)
    selectionnees: Counter[str] = field(default_factory=Counter)
    motifs: Counter[str] = field(default_factory=Counter)
    """Motifs de rejet, agrégés — `« categorie : motif »` → effectif."""


@dataclass(frozen=True)
class ControlePricePerGb:
    """Comparaison du recalcul à la valeur source, sur les lignes non dédupliquées."""

    categorie: str
    lignes_comparees: int
    ecart_median: Decimal
    ecart_p99: Decimal
    ecart_max: Decimal
    lignes_au_dela_du_seuil: int

    @property
    def part_au_dela(self) -> Decimal:
        """Part des lignes qui s'écartent de plus de 1 % — le chiffre qui décide."""
        if self.lignes_comparees == 0:
            return Decimal(0)
        return Decimal(self.lignes_au_dela_du_seuil) / Decimal(self.lignes_comparees)


@dataclass
class ResultatPasseA:
    """Tout ce que la passe A produit : le seed, et de quoi en rendre compte."""

    entonnoir: Entonnoir
    dedup: dict[str, StatsDeduplication]
    controles_price_per_gb: list[ControlePricePerGb]
    selection: ResultatSelection
    marques: Counter[str]
    genere_le: datetime


# --------------------------------------------------------------------------- #
# 1-3. Lecture, filtrage, normalisation
# --------------------------------------------------------------------------- #


def lire_categorie(chemin: Path) -> list[dict[str, Any]]:
    """Lit un fichier JSON du dataset brut."""
    if not chemin.is_file():
        raise FileNotFoundError(
            f"{chemin} est absent. `data/raw/` n'est pas versionné : la commande de "
            "récupération est dans data/raw/SOURCE.md, et l'intégrité se vérifie par "
            "`sha256sum -c data/raw/CHECKSUMS.sha256`."
        )
    contenu = json.loads(chemin.read_text(encoding="utf-8"))
    if not isinstance(contenu, list):
        raise PipelineArrete(f"{chemin} ne contient pas une liste JSON")
    return contenu


def _a_un_prix(ligne: dict[str, Any]) -> bool:
    """Le filtre de l'étape 2 : `price` présent et **strictement** positif.

    C'est ce filtre qui retire les 76 % de la source (seuls 24 % des produits portent
    un prix). Un produit sans prix ne peut pas entrer dans un moteur à contrainte
    budgétaire ; le garder fausserait tous les taux de remplissage.
    """
    prix = ligne.get("price")
    return isinstance(prix, int | float) and not isinstance(prix, bool) and prix > 0


def normaliser_ligne(categorie: str, ligne: dict[str, Any]) -> LigneNormalisee:
    """Étapes 3 et 4 sur une ligne : specs normalisées, clé canonique, identifiant.

    `price_per_gb` n'est **pas** calculé ici (arbitrage D) : la clé canonique se
    calcule juste après, et il la rendrait sensible au prix.
    """
    nom = ligne.get("name")
    if not isinstance(nom, str) or not nom.strip():
        raise PipelineArrete(f"produit sans nom exploitable dans {categorie} : {ligne!r}")

    specs = construire_specs(categorie, ligne, nom)
    cle = cle_canonique(nom, specs)
    source = ligne.get("price_per_gb")
    return LigneNormalisee(
        id=calculer_id(categorie, cle),
        cle=cle,
        categorie=categorie,
        nom=nom,
        marque=extraire_marque(nom),
        prix_usd=normaliser_prix(ligne["price"]),
        specs=specs,
        price_per_gb_source=None if source is None else en_decimal(source),
    )


# --------------------------------------------------------------------------- #
# 6. Contrôle de la transformation 6
# --------------------------------------------------------------------------- #


def controler_price_per_gb(
    lignes: Sequence[LigneNormalisee], tailles_groupes: Counter[str]
) -> list[ControlePricePerGb]:
    """Compare le recalcul à la valeur source, **sur les lignes non dédupliquées**.

    Restreint aux groupes d'une seule ligne : ailleurs, le prix retenu n'est pas celui
    qui a servi à la source, et l'écart mesurerait la déduplication au lieu de la
    formule.

    Si plus de 1 % des lignes s'écartent de plus de 1 %, on s'arrête : cela voudrait
    dire que la source ne calcule pas ce qu'on croit, et il faut le comprendre avant
    de continuer.
    """
    controles: list[ControlePricePerGb] = []
    for categorie in ("internal-hard-drive", "memory"):
        ecarts: list[Decimal] = []
        for ligne in lignes:
            if ligne.categorie != categorie or tailles_groupes[ligne.id] != 1:
                continue
            source = ligne.price_per_gb_source
            if source is None or source == 0:
                continue
            capacite = (
                ligne.specs["capacity"]
                if categorie == "internal-hard-drive"
                else ligne.specs["capacite_totale_gb"]
            )
            recalcul = calculer_price_per_gb(ligne.prix_usd, capacite)
            ecarts.append(abs(recalcul - source) / source)

        if not ecarts:
            continue
        ecarts.sort()
        au_dela = sum(1 for ecart in ecarts if ecart > SEUIL_ECART_PRICE_PER_GB)
        controle = ControlePricePerGb(
            categorie=categorie,
            lignes_comparees=len(ecarts),
            ecart_median=ecarts[len(ecarts) // 2],
            ecart_p99=ecarts[min(len(ecarts) - 1, int(len(ecarts) * 0.99))],
            ecart_max=ecarts[-1],
            lignes_au_dela_du_seuil=au_dela,
        )
        if controle.part_au_dela > SEUIL_ECART_PRICE_PER_GB:
            raise PipelineArrete(
                f"`price_per_gb` — {controle.part_au_dela:.2%} des lignes de {categorie} "
                f"s'écartent de plus de 1 % de la valeur source (seuil : 1 %). La source "
                "ne calcule pas ce que la transformation 6 suppose : à comprendre avant "
                "de continuer."
            )
        controles.append(controle)
    return controles


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def executer_passe_a(
    repertoire_brut: Path = BRUT,
    cible: int = CIBLE_PAR_CATEGORIE,
    graine: int = GRAINE_TIRAGE,
) -> ResultatPasseA:
    """Enchaîne les neuf opérations et rend de quoi écrire le seed et le rapport."""
    entonnoir = Entonnoir()

    # 1. Lecture. `keyboard` n'est lue que pour que le total « lues » corresponde à
    #    des fichiers réels ; elle est écartée avant toute normalisation.
    lignes_retirees = lire_categorie(repertoire_brut / f"{CATEGORIE_RETIREE}.json")
    entonnoir.lues[CATEGORIE_RETIREE] = len(lignes_retirees)
    entonnoir.motifs[f"{CATEGORIE_RETIREE} : catégorie retirée à l'étape 3 (§3.4bis)"] = len(
        lignes_retirees
    )

    normalisees: list[LigneNormalisee] = []
    for categorie in CATEGORIES:
        brutes = lire_categorie(repertoire_brut / f"{categorie}.json")
        entonnoir.lues[categorie] = len(brutes)

        # 2. Filtrage sur le prix.
        a_prix = [ligne for ligne in brutes if _a_un_prix(ligne)]
        entonnoir.a_prix[categorie] = len(a_prix)
        entonnoir.sans_prix[categorie] = len(brutes) - len(a_prix)

        # 3-4. Normalisation, clé canonique, identifiant.
        for ligne in a_prix:
            try:
                normalisees.append(normaliser_ligne(categorie, ligne))
            except LigneEcartee as ecart:
                entonnoir.motifs[f"{categorie} : {ecart.motif}"] += 1
            except PipelineArrete as arret:
                raise PipelineArrete(
                    f"{categorie} — {ligne.get('name', '<sans nom>')!r} : {arret}"
                ) from arret
        entonnoir.normalisees[categorie] = sum(
            1 for ligne in normalisees if ligne.categorie == categorie
        )

    # 5. Déduplication — regrouper par `id`, garder le prix le plus bas.
    tailles_groupes = Counter(ligne.id for ligne in normalisees)
    controles = controler_price_per_gb(normalisees, tailles_groupes)  # 6 (contrôle)
    retenues, stats_dedup = dedupliquer(normalisees)
    for retenue in retenues:
        entonnoir.dedupliquees[retenue.categorie] += 1

    # 6. Grandeurs dérivées du prix, sur le prix retenu. 7. Validation.
    valides: list[ProduitEnBase] = []
    for retenue in retenues:
        specs = ajouter_grandeurs_derivees_du_prix(
            retenue.categorie, retenue.specs, retenue.prix_usd
        )
        try:
            valides.append(
                ProduitEnBase(
                    id=retenue.id,
                    nom=retenue.nom,
                    marque=retenue.marque,
                    categorie=retenue.categorie,  # type: ignore[arg-type]
                    prix_usd=retenue.prix_usd,
                    specs=specs,  # type: ignore[arg-type]
                )
            )
            entonnoir.validees[retenue.categorie] += 1
        except ValidationError as erreur:
            # Une ligne rejetée est écartée et journalisée, **jamais réparée**.
            entonnoir.motifs[f"{retenue.categorie} : {_motif_de_validation(erreur)}"] += 1

    # 8. Sélection stratifiée et garanties de cas limites.
    selection = selectionner(valides, cible=cible, graine=graine)
    for produit in selection.produits:
        entonnoir.selectionnees[produit.categorie] += 1

    return ResultatPasseA(
        entonnoir=entonnoir,
        dedup=stats_dedup,
        controles_price_per_gb=controles,
        selection=selection,
        marques=Counter(produit.marque for produit in selection.produits),
        genere_le=datetime.now(UTC),
    )


def _motif_de_validation(erreur: ValidationError) -> str:
    """Réduit une `ValidationError` à un motif court et **stable**, agrégeable.

    Le message complet de Pydantic cite la valeur fautive, donc diffère d'une ligne à
    l'autre : agrégé tel quel, le rapport listerait une ligne par produit rejeté au
    lieu de compter les causes.
    """
    premiere = erreur.errors()[0]
    chemin = ".".join(str(morceau) for morceau in premiere["loc"] if morceau != "specs")
    return f"validation rejetée sur `{chemin or '<produit>'}` ({premiere['type']})"


# --------------------------------------------------------------------------- #
# 9. Écriture
# --------------------------------------------------------------------------- #


def serialiser_produit(produit: ProduitEnBase) -> str:
    """Rend la ligne JSONL d'un produit, triée et sans espace superflu.

    `categorie` est retirée de `specs` pour la même raison qu'en base : elle a déjà sa
    colonne, et deux copies d'un même fait peuvent diverger. La forme est celle de
    `specs_pour_base()`, ce qui rend le fichier committé directement comparable à ce
    que Postgres contient.
    """
    charge = produit.model_dump(mode="json", exclude={"specs": {"categorie"}})
    return json.dumps(charge, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ecrire_seed(produits: Sequence[ProduitEnBase], chemin: Path = FICHIER_SEED) -> None:
    """Écrit le JSONL, **trié par `id`**, une ligne par produit.

    Le tri n'est pas cosmétique : c'est lui qui fait qu'ajouter un produit produit un
    diff d'une ligne, et non un fichier entier réécrit.
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)
    lignes = [serialiser_produit(produit) for produit in sorted(produits, key=lambda p: p.id)]
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")


def lire_seed(chemin: Path = FICHIER_SEED) -> list[ProduitEnBase]:
    """Relit le seed committé en **revalidant** chaque ligne.

    Le fichier n'est pas digne de confiance du seul fait d'être committé — c'est la
    même raison qui a fait de `ProduitEnBase` la porte d'entrée unique de la table.
    """
    if not chemin.is_file():
        raise FileNotFoundError(f"{chemin} est absent — lancer `make seed-build`.")
    produits: list[ProduitEnBase] = []
    for numero, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), start=1):
        if not ligne.strip():
            continue
        try:
            produits.append(ProduitEnBase.model_validate(json.loads(ligne)))
        except (ValidationError, json.JSONDecodeError) as erreur:
            raise PipelineArrete(f"{chemin}:{numero} — ligne invalide : {erreur}") from erreur
    return produits


# --------------------------------------------------------------------------- #
# Le rapport
# --------------------------------------------------------------------------- #


def _pourcent(part: int, total: int) -> str:
    """Formate un pourcentage, ou un tiret si le dénominateur est nul."""
    return "—" if total == 0 else f"{100 * part / total:.1f} %"


def _mediane(valeurs: Sequence[Decimal]) -> Decimal:
    ordonnees = sorted(valeurs)
    milieu = len(ordonnees) // 2
    if len(ordonnees) % 2 == 1:
        return ordonnees[milieu]
    return (ordonnees[milieu - 1] + ordonnees[milieu]) / 2


def _cles_de_specs(produits: Sequence[ProduitEnBase]) -> list[str]:
    """Clés de `specs` d'une catégorie, dans l'ordre du modèle Pydantic."""
    return list(produits[0].specs_pour_base()) if produits else []


def construire_rapport(resultat: ResultatPasseA) -> str:
    """Rend le rapport de l'étape, en Markdown. C'est un livrable, pas un log."""
    e = resultat.entonnoir
    seed = resultat.selection.produits
    lignes: list[str] = [
        "# Rapport du seed — étape 5",
        "",
        "Généré par `make seed-build` (`scripts/seed_build.py`). Passe déterministe,",
        "sans le moindre appel à un modèle de langage. Committé : c'est un livrable de",
        "l'étape, pas une sortie de console.",
        "",
        "- Source : `docyx/pc-part-dataset`, commit `c52a04c` — voir `data/raw/SOURCE.md`",
        f"- Graine du tirage : `{GRAINE_TIRAGE}` (constante de code, cf. `selection.py`)",
        f"- Généré le : {resultat.genere_le:%Y-%m-%d %H:%M} UTC",
        "",
        "> ⚠️ **Toutes les statistiques de ce rapport portent sur le seed, pas sur la",
        "> source** (décision 3.1bis). L'échantillonnage stratifié conserve la forme de",
        "> la distribution des prix, mais les taux de remplissage y diffèrent",
        "> légèrement de ceux mesurés à l'étape 3.",
        "",
        "## Entonnoir",
        "",
        "| catégorie | lues | sans prix | à prix | normalisées | dédupliquées "
        "| validées | sélectionnées |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for categorie in CATEGORIES:
        lignes.append(
            f"| `{categorie}` | {e.lues[categorie]} | {e.sans_prix[categorie]} | "
            f"{e.a_prix[categorie]} | {e.normalisees[categorie]} | "
            f"{e.dedupliquees[categorie]} | {e.validees[categorie]} | "
            f"{e.selectionnees[categorie]} |"
        )
    lignes.append(
        f"| `{CATEGORIE_RETIREE}` *(retirée §3.4bis)* | {e.lues[CATEGORIE_RETIREE]} | — | — | "
        "— | — | — | — |"
    )
    total_lues = sum(e.lues.values())
    lignes += [
        f"| **total** | **{total_lues}** | **{sum(e.sans_prix.values())}** | "
        f"**{sum(e.a_prix.values())}** | **{sum(e.normalisees.values())}** | "
        f"**{sum(e.dedupliquees.values())}** | **{sum(e.validees.values())}** | "
        f"**{sum(e.selectionnees.values())}** |",
        "",
        f"Le filtre sur le prix retire **{sum(e.sans_prix.values())} lignes sur "
        f"{total_lues - e.lues[CATEGORIE_RETIREE]}** des six catégories retenues, soit "
        f"**{_pourcent(sum(e.sans_prix.values()), total_lues - e.lues[CATEGORIE_RETIREE])}**. "
        "C'est le chiffre des 76 % annoncé à l'étape 3 : un produit sans prix n'entre pas "
        "dans un moteur à contrainte budgétaire.",
        "",
        "## Motifs de rejet",
        "",
        "| motif | lignes |",
        "| --- | ---: |",
    ]
    for motif, effectif in sorted(e.motifs.items(), key=lambda item: (-item[1], item[0])):
        lignes.append(f"| {motif} | {effectif} |")
    lignes += [
        "",
        "Aucune de ces lignes n'a été réparée : une valeur manquante ou inattendue fait",
        "sortir la ligne du pipeline, elle n'est jamais comblée (§3.4quater).",
        "",
        "## Déduplication",
        "",
        "Une règle unique sur les six catégories : regrouper par `id`, garder le prix le",
        "plus bas. L'`id` **est** la clé de déduplication (arbitrage C), et il exclut le",
        "prix et toute grandeur qui en dérive (arbitrage D).",
        "",
        "| catégorie | lignes | groupes | absorbées | écart de prix max dans un groupe |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for categorie in CATEGORIES:
        stats = resultat.dedup.get(categorie)
        if stats is None:
            continue
        detail = f" (`{stats.id_ecart_max}`)" if stats.lignes_absorbees else ""
        lignes.append(
            f"| `{categorie}` | {stats.lignes_entrantes} | {stats.groupes} | "
            f"{stats.lignes_absorbees} | {stats.ecart_prix_max} USD{detail} |"
        )
    lignes += [
        "",
        "L'écart de prix maximal à l'intérieur d'un groupe est le chiffre qui révélerait",
        "une clé trop lâche : deux produits différents fusionnés se trahiraient par un",
        "écart que rien n'explique.",
        "",
        "## Contrôle de `price_per_gb` (transformation 6)",
        "",
        "Recalculé sur le prix retenu, jamais recopié. La comparaison à la valeur source",
        "porte sur les lignes **non dédupliquées** : ailleurs, le prix retenu n'est plus",
        "celui qui a servi à la source.",
        "",
        "| catégorie | lignes comparées | écart médian | 99ᵉ centile | max | > 1 % |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for controle in resultat.controles_price_per_gb:
        lignes.append(
            f"| `{controle.categorie}` | {controle.lignes_comparees} | "
            f"{controle.ecart_median:.4%} | {controle.ecart_p99:.4%} | "
            f"{controle.ecart_max:.4%} | {controle.lignes_au_dela_du_seuil} "
            f"({controle.part_au_dela:.2%}) |"
        )
    lignes += [
        "",
        "Seuil d'arrêt : plus de 1 % des lignes s'écartant de plus de 1 %. Il n'est pas",
        "atteint.",
        "",
        "## Le seed",
        "",
        "### Distribution des prix (USD)",
        "",
        "| catégorie | produits | min | médiane | max |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for categorie in CATEGORIES:
        du_seed = [p for p in seed if p.categorie == categorie]
        if not du_seed:
            continue
        prix = [p.prix_usd for p in du_seed]
        lignes.append(
            f"| `{categorie}` | {len(du_seed)} | {min(prix)} | {_mediane(prix):.2f} | {max(prix)} |"
        )
    lignes += [f"| **total** | **{len(seed)}** | | | |", ""]

    lignes += [
        "### Strates de prix et repêchages",
        "",
        "| catégorie | disponibles | cible | strates servies | repêchés G1 "
        "| repêchés G2 | repêchés G4 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rapport in resultat.selection.rapports:
        servies = sum(1 for strate in rapport.strates if strate.retenus > 0)
        lignes.append(
            f"| `{rapport.categorie}` | {rapport.disponibles} | {rapport.cible} | "
            f"{servies}/{len(rapport.strates)} | {len(rapport.repeches_g1)} | "
            f"{len(rapport.repeches_g2)} | {len(rapport.repeches_g4)} |"
        )

    lignes += ["", "### Taux de remplissage par attribut, sur le seed final", ""]
    for categorie in CATEGORIES:
        du_seed = [p for p in seed if p.categorie == categorie]
        if not du_seed:
            continue
        lignes += [
            f"**`{categorie}`** — {len(du_seed)} produits",
            "",
            "| attribut | renseignés | taux |",
            "| --- | ---: | ---: |",
        ]
        for cle in _cles_de_specs(du_seed):
            remplis = sum(1 for p in du_seed if p.specs_pour_base().get(cle) is not None)
            marque = " *(dérivé du prix)*" if cle in CHAMPS_DERIVES_DU_PRIX else ""
            lignes.append(f"| `{cle}`{marque} | {remplis} | {_pourcent(remplis, len(du_seed))} |")
        lignes.append("")

    lignes += ["### Valeurs distinctes des énumérations normalisées", ""]
    for categorie in CATEGORIES:
        du_seed = [p for p in seed if p.categorie == categorie]
        for champ in ENUMERATIONS[categorie]:
            valeurs = Counter(
                str(p.specs_pour_base().get(champ))
                for p in du_seed
                if p.specs_pour_base().get(champ) is not None
            )
            rendu = " · ".join(
                f"`{valeur}` {effectif}"
                for valeur, effectif in sorted(valeurs.items(), key=lambda i: (-i[1], i[0]))
            )
            lignes.append(f"- `{categorie}.{champ}` — {len(valeurs)} valeurs : {rendu}")
    lignes += [
        "",
        "`internal-hard-drive.form_factor` est celle qui compte : deux types JSON",
        'distincts de la source (`2.5` en nombre, `"M.2-2280"` en chaîne) y ont fusionné',
        "en une seule énumération textuelle. Aucune forme inattendue n'est passée.",
        "",
        "### Marques par volume",
        "",
        "Premier mot de `name`, corrigé par la table fermée de marques en plusieurs mots",
        "(`normalisation.MARQUES_MULTI_MOTS`). Aucune catégorie de la source ne porte de",
        "champ marque : c'est une transformation, pas une lecture (§3.4quater).",
        "",
        "| marque | produits |",
        "| --- | ---: |",
    ]
    for marque, effectif in resultat.marques.most_common(30):
        lignes.append(f"| {marque} | {effectif} |")
    lignes += [
        "",
        f"{len(resultat.marques)} marques distinctes au seed ; les 30 premières sont listées.",
        "",
        "## Cas limites pour l'étape 6",
        "",
        "Repêchés **parmi des produits réels**, jamais fabriqués : inventer un produit",
        "pour faire passer un test futur violerait §2 dans le fichier même qui sert de",
        "catalogue. Les identifiants ci-dessous sont ceux que les tests de l'étape 6",
        "citeront — s'ils changent, un test cassera, ce qui est le comportement souhaité.",
        "",
        "### G1 — budget frôlé",
        "",
        "Au moins un produit par catégorie dans `]seuil, seuil x 1,15]`, la zone de",
        "tolérance de §3.10.",
        "",
        "| catégorie | seuil | produit | prix | repêché ? |",
        "| --- | ---: | --- | ---: | --- |",
    ]
    for cas in resultat.selection.g1:
        lignes.append(
            f"| `{cas.categorie}` | {cas.seuil_usd} USD | `{cas.id_produit}` | "
            f"{cas.prix_usd} USD | {'oui' if cas.repeche else 'non — déjà tiré'} |"
        )

    lignes += ["", "### G2 — départage", ""]
    g2 = resultat.selection.g2
    if g2 is None:
        lignes.append("Aucun couple trouvé dans la source. À signaler, pas à fabriquer.")
    else:
        lignes += [
            f"Deux produits `{g2.categorie}` dont toutes les specs sont identiques, sauf le",
            f"prix et le champ d'affichage `{g2.champ_affichage}` :",
            "",
            f"- `{g2.id_a}` — {g2.prix_a} USD — {g2.champ_affichage} : {g2.valeur_a!r}",
            f"- `{g2.id_b}` — {g2.prix_b} USD — {g2.champ_affichage} : {g2.valeur_b!r}",
            "",
            f"Repêché : {'oui' if g2.repeche else 'non — déjà tiré'}. Un champ `affichage`",
            "n'entre ni dans un filtre ni dans un score : le moteur de l'étape 6 devra donc",
            "les départager sur le prix seul.",
        ]

    lignes += ["", "### G3 — zéro résultat", ""]
    g3 = resultat.selection.g3
    if g3 is None:
        lignes.append("Aucune combinaison vide trouvée sur le seed. À signaler.")
    else:
        criteres = " ET ".join(f"`{champ}` = {valeur!r}" for champ, valeur in g3.criteres.items())
        lignes += [
            f"Sur `{g3.categorie}` : {criteres} → **0 produit**.",
            "",
            "Chaque critère pris seul est pourtant servi par le seed — c'est ce qui rend la",
            "combinaison plausible plutôt qu'absurde :",
            "",
        ]
        for critere, effectif in g3.effectifs_isoles.items():
            lignes.append(f"- `{critere}` seul → {effectif} produits")
        lignes += [
            "",
            "Cette combinaison ne se place pas, elle **se constate**. C'est le scénario du",
            "critère d'acceptation nº6 : dire pourquoi il n'y a rien et proposer",
            "l'assouplissement du critère le plus coûteux.",
        ]

    lignes += [
        "",
        "### G4 — haut de gamme",
        "",
        "Le produit le plus cher de chaque catégorie est au seed. La stratification par",
        "décile conserve la **forme** de la distribution des prix, pas ses **extrêmes** :",
        "avec 17 tirages dans le dernier décile, le produit le plus cher a une chance sur",
        "huit d'être retenu. Sans cette garantie, le catalogue n'offrirait aucun cas",
        "« budget très large » et le haut de gamme réel du domaine serait absent.",
        "",
        "| catégorie | produit | prix | repêché ? |",
        "| --- | --- | ---: | --- |",
    ]
    for haut_de_gamme in resultat.selection.g4:
        lignes.append(
            f"| `{haut_de_gamme.categorie}` | `{haut_de_gamme.id_produit}` | "
            f"{haut_de_gamme.prix_usd} USD | "
            f"{'oui' if haut_de_gamme.repeche else 'non — déjà tiré'} |"
        )
    lignes += [
        "",
        "Aucune garantie symétrique sur le produit le moins cher : le premier décile est",
        "dense, son minimum y est déjà représenté, et une garantie qui ne repêche jamais",
        "rien serait du code mort qui se donne l'air d'une preuve.",
    ]

    lignes.append("")
    return "\n".join(lignes)


def ecrire_rapport(resultat: ResultatPasseA, chemin: Path = FICHIER_RAPPORT) -> None:
    """Écrit le rapport de l'étape à côté du seed."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(construire_rapport(resultat), encoding="utf-8")
