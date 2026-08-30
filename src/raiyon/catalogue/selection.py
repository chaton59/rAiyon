"""Sélection des ~1 000 produits du seed : strates de prix, graine fixe, cas limites.

**Échantillonnage stratifié par décile de prix, pas uniforme** (arbitrage E de
l'étape 5). Le catalogue garde ainsi la forme de la distribution réelle, y compris
sa queue haute. Alternative écartée — un tirage uniforme : plus simple, mais les
cartes graphiques à 7 516 USD et les moniteurs à 9 333 USD disparaissent presque
sûrement, et le moteur de l'étape 6 n'aurait plus rien pour exercer sa zone de
tolérance budgétaire (§3.10).

**Le biais est assumé et il doit être dit** (décision 3.1bis) : le seed n'est pas la
source. Les taux de remplissage y diffèrent légèrement, et toute statistique produite
ensuite porte sur le seed, jamais sur le dataset.

Le tirage n'utilise pas `random` : les candidats sont ordonnés par une empreinte
`sha256(graine:id)` et on prend les premiers. C'est un ordre pseudo-aléatoire
**reproductible indépendamment de la version de Python** — `random.sample` ne
garantit pas cela d'une version à l'autre, et le seed est un fichier committé dont
le diff doit rester vide quand rien ne change.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from raiyon.catalogue.schemas import CATEGORIES, ProduitEnBase

GRAINE_TIRAGE = 20260828
"""Graine du tirage — **constante de code, jamais une variable d'environnement**.

Une variable d'environnement se change par accident entre deux exécutions, et le seed
committé changerait alors sans qu'aucune décision n'ait été prise. La changer ici est
un commit, donc une relecture.
"""

NB_STRATES = 10
CIBLE_PAR_CATEGORIE = 170

SEUILS_RONDS_USD = (Decimal(100), Decimal(300), Decimal(500), Decimal(1000))
"""Budgets ronds qu'un client énonce réellement. G1 place un produit juste au-dessus."""

TOLERANCE_BUDGET = Decimal("1.15")
"""Zone de tolérance de §3.10 (+15 %). G1 garantit qu'il y a de quoi l'exercer."""

# Rôles lus dans `catalogue/schema_attributs.md`, et rien d'autre : ce module doit
# savoir quels attributs sont bloquants pour *constater* les garanties G2 et G3.
# Ce n'est pas le moteur de matching — il n'y a ici ni requête, ni score, ni critère
# client. Le moteur, c'est l'étape 6, et il relira ces rôles pour son compte.
CHAMPS_FILTRE_DUR: dict[str, tuple[str, ...]] = {
    "cpu": ("core_count", "tdp", "microarchitecture"),
    "monitor": ("screen_size", "largeur_px", "hauteur_px", "aspect_ratio", "refresh_rate"),
    "internal-hard-drive": ("capacity", "type", "form_factor", "interface"),
    "memory": ("ddr_generation", "nb_modules", "capacite_totale_gb"),
    "video-card": ("chipset", "memory", "length"),
    "headphones": ("type", "microphone", "wireless", "enclosure_type"),
}

CHAMPS_AFFICHAGE: dict[str, tuple[str, ...]] = {
    "cpu": (),
    "monitor": (),
    "internal-hard-drive": (),
    "memory": ("color",),
    "video-card": ("color",),
    "headphones": ("color",),
}
"""Champs `affichage` au sens de `schema_attributs.md` : montrés, jamais filtrés.

Trois catégories sur six n'en portent aucun. G2 se joue donc nécessairement sur
`memory`, `video-card` ou `headphones` — c'est une conséquence de la source, pas un
choix de ce module.
"""

CHAMPS_DERIVES_DU_PRIX = ("price_per_gb",)
"""Exclus de toute comparaison de specs : ils varient dès que le prix varie.

Deux produits « identiques sauf le prix » ont forcément des `price_per_gb` différents.
Les compter comme une différence rendrait G2 introuvable par construction.
"""


def empreinte_de_tirage(graine: int, categorie: str, identifiant: str) -> str:
    """Ordre pseudo-aléatoire stable : une empreinte par produit, triée ensuite.

    La catégorie entre dans l'empreinte pour que deux catégories ne tirent pas « les
    mêmes rangs », ce qui corrélerait leurs échantillons sans raison.
    """
    graine_complete = f"{graine}:{categorie}:{identifiant}".encode()
    return hashlib.sha256(graine_complete).hexdigest()


@dataclass(frozen=True)
class Strate:
    """Un décile de prix d'une catégorie, et ce qu'on y a pris."""

    rang: int
    effectif: int
    prix_min: Decimal
    prix_max: Decimal
    quota: int
    retenus: int


@dataclass
class RapportSelection:
    """Ce que la sélection a fait sur une catégorie."""

    categorie: str
    disponibles: int
    cible: int
    strates: list[Strate] = field(default_factory=list)
    repeches_g1: list[str] = field(default_factory=list)
    repeches_g2: list[str] = field(default_factory=list)
    repeches_g4: list[str] = field(default_factory=list)

    @property
    def retenus(self) -> int:
        """Effectif final, repêchages de cas limites compris."""
        return (
            sum(strate.retenus for strate in self.strates)
            + len(self.repeches_g1)
            + len(self.repeches_g2)
            + len(self.repeches_g4)
        )


def _decouper_en_strates(
    produits: Sequence[ProduitEnBase], nb_strates: int
) -> list[list[ProduitEnBase]]:
    """Découpe une catégorie en déciles de prix, par rang et non par intervalle de prix.

    Découper l'intervalle `[min, max]` en dix tranches égales donnerait des strates
    vides sur une distribution à queue longue — les prix des cartes graphiques vont de
    46 à 7 516 USD, neuf produits sur dix sont sous 1 100. Le découpage par rang donne
    dix strates d'effectifs égaux, ce qui est ce dont on a besoin : un quota par
    décile de **population**, pas par tranche de prix.
    """
    ordonnes = sorted(produits, key=lambda produit: (produit.prix_usd, produit.id))
    total = len(ordonnes)
    strates: list[list[ProduitEnBase]] = []
    for rang in range(nb_strates):
        debut = total * rang // nb_strates
        fin = total * (rang + 1) // nb_strates
        strates.append(ordonnes[debut:fin])
    return strates


def _repartir_les_quotas(effectifs: Sequence[int], cible: int) -> list[int]:
    """Quota égal par strate, **report des strates déficitaires sur les voisines**.

    Une strate qui n'a pas assez de produits ne fait pas rater la cible : sa place
    part vers la strate la plus proche qui a encore du stock, par distance croissante
    et à distance égale vers la strate inférieure d'abord. Le parcours est fixe, donc
    le résultat est le même à chaque exécution.
    """
    nb = len(effectifs)
    base, reste = divmod(cible, nb)
    quotas = [base + (1 if rang < reste else 0) for rang in range(nb)]
    retenus = [min(quota, effectif) for quota, effectif in zip(quotas, effectifs, strict=True)]

    for rang in range(nb):
        a_reporter = quotas[rang] - retenus[rang]
        for _ in range(a_reporter):
            accueil = _strate_voisine_avec_du_stock(rang, retenus, effectifs)
            if accueil is None:
                break  # toutes les strates sont pleines : la catégorie est plus petite que la cible
            retenus[accueil] += 1
    return retenus


def _strate_voisine_avec_du_stock(
    rang: int, retenus: Sequence[int], effectifs: Sequence[int]
) -> int | None:
    """Rend la strate la plus proche de `rang` qui peut encore accueillir un produit."""
    for distance in range(1, len(effectifs)):
        for voisin in (rang - distance, rang + distance):
            if 0 <= voisin < len(effectifs) and retenus[voisin] < effectifs[voisin]:
                return voisin
    return None


def selectionner_categorie(
    categorie: str,
    produits: Sequence[ProduitEnBase],
    cible: int = CIBLE_PAR_CATEGORIE,
    graine: int = GRAINE_TIRAGE,
) -> tuple[list[ProduitEnBase], RapportSelection]:
    """Tire `cible` produits d'une catégorie, par décile de prix, à graine fixe."""
    strates = _decouper_en_strates(produits, NB_STRATES)
    effectifs = [len(strate) for strate in strates]
    base, reste = divmod(cible, NB_STRATES)
    quotas = [base + (1 if rang < reste else 0) for rang in range(NB_STRATES)]
    retenus_par_strate = _repartir_les_quotas(effectifs, cible)

    rapport = RapportSelection(categorie=categorie, disponibles=len(produits), cible=cible)
    selection: list[ProduitEnBase] = []

    for rang, (strate, nombre) in enumerate(zip(strates, retenus_par_strate, strict=True)):
        tires = sorted(strate, key=lambda p: empreinte_de_tirage(graine, categorie, p.id))[:nombre]
        selection.extend(tires)
        rapport.strates.append(
            Strate(
                rang=rang + 1,
                effectif=len(strate),
                prix_min=min((p.prix_usd for p in strate), default=Decimal(0)),
                prix_max=max((p.prix_usd for p in strate), default=Decimal(0)),
                quota=quotas[rang],
                retenus=len(tires),
            )
        )
    return selection, rapport


# --------------------------------------------------------------------------- #
# Garanties de cas limites — repêchées parmi des produits réels, jamais fabriquées
# --------------------------------------------------------------------------- #


def _mediane(valeurs: Sequence[Decimal]) -> Decimal:
    """Médiane d'une liste non vide, sans dépendance externe."""
    ordonnees = sorted(valeurs)
    milieu = len(ordonnees) // 2
    if len(ordonnees) % 2 == 1:
        return ordonnees[milieu]
    return (ordonnees[milieu - 1] + ordonnees[milieu]) / 2


def seuil_plausible(prix: Sequence[Decimal]) -> Decimal:
    """Seuil budgétaire rond le plus proche de la médiane de la catégorie.

    « Un écran à moins de 300 » se dit ; « un écran à moins de 290 » ne se dit pas.
    Le seuil est donc choisi parmi des valeurs qu'un client énonce, pas calculé.
    """
    mediane = _mediane(prix)
    return min(SEUILS_RONDS_USD, key=lambda seuil: (abs(seuil - mediane), seuil))


def _dans_la_zone_de_tolerance(prix: Decimal, seuil: Decimal) -> bool:
    """`]seuil, seuil x 1,15]` — juste au-dessus d'un budget rond, mais dans la tolérance."""
    return seuil < prix <= seuil * TOLERANCE_BUDGET


@dataclass(frozen=True)
class CasLimiteG1:
    """Un produit dont le prix frôle un budget rond, par catégorie."""

    categorie: str
    seuil_usd: Decimal
    id_produit: str
    prix_usd: Decimal
    repeche: bool


@dataclass(frozen=True)
class CasLimiteG2:
    """Deux produits que seuls le prix et un champ d'affichage séparent."""

    categorie: str
    champ_affichage: str
    id_a: str
    id_b: str
    prix_a: Decimal
    prix_b: Decimal
    valeur_a: Any
    valeur_b: Any
    # Les marques sont portées ici depuis l'étape 6 : « toutes les specs identiques »
    # ne vaut que pour le JSONB, et le couple peut différer par des colonnes communes.
    # `marque` étant un filtre dur, le rapport doit le dire — sans quoi il laisse croire
    # à deux produits interchangeables.
    marque_a: str
    marque_b: str
    repeche: bool


@dataclass(frozen=True)
class CasLimiteG3:
    """Une combinaison de filtres durs plausible qui ne rend aucun produit du seed."""

    categorie: str
    criteres: dict[str, Any]
    effectifs_isoles: dict[str, int]
    """Effectif de chaque critère **pris seul**. C'est ce qui rend la combinaison
    plausible : chaque exigence existe au catalogue, c'est leur conjonction qui est
    vide. Une combinaison dont un critère serait déjà vide ne démontrerait rien."""


@dataclass(frozen=True)
class CasLimiteG4:
    """Le produit le plus cher d'une catégorie, dont on garantit la présence au seed."""

    categorie: str
    id_produit: str
    prix_usd: Decimal
    repeche: bool


def garantir_g1(
    selection: list[ProduitEnBase], pool: Sequence[ProduitEnBase]
) -> tuple[list[ProduitEnBase], list[CasLimiteG1]]:
    """G1 — budget frôlé : au moins un produit dans `]seuil, seuil x 1,15]` par catégorie.

    C'est la zone de tolérance de §3.10 qui s'y exercera à l'étape 6. Un produit
    manquant est **repêché du pool réel**, jamais fabriqué : inventer un produit pour
    faire passer un test futur violerait §2 dans le fichier même qui sert de catalogue.
    """
    ajouts: list[ProduitEnBase] = []
    cas: list[CasLimiteG1] = []

    for categorie in CATEGORIES:
        du_pool = [p for p in pool if p.categorie == categorie]
        if not du_pool:
            continue
        seuil = seuil_plausible([p.prix_usd for p in du_pool])
        deja = [
            p
            for p in selection
            if p.categorie == categorie and _dans_la_zone_de_tolerance(p.prix_usd, seuil)
        ]
        if deja:
            gagnant = min(deja, key=lambda p: (p.prix_usd, p.id))
            cas.append(CasLimiteG1(categorie, seuil, gagnant.id, gagnant.prix_usd, repeche=False))
            continue

        candidats = [p for p in du_pool if _dans_la_zone_de_tolerance(p.prix_usd, seuil)]
        if not candidats:
            continue  # la source n'a rien dans cette zone : le rapport le dira, on n'invente pas
        repeche = min(candidats, key=lambda p: (p.prix_usd, p.id))
        ajouts.append(repeche)
        cas.append(CasLimiteG1(categorie, seuil, repeche.id, repeche.prix_usd, repeche=True))

    return ajouts, cas


def garantir_g4(
    selection: list[ProduitEnBase], pool: Sequence[ProduitEnBase]
) -> tuple[list[ProduitEnBase], list[CasLimiteG4]]:
    """G4 — le produit le plus cher de chaque catégorie est au seed.

    **Pourquoi cette garantie existe.** La stratification par décile conserve la
    *forme* de la distribution des prix, pas ses *extrêmes* : avec 17 tirages dans le
    dernier décile, le produit le plus cher a une chance sur huit d'être retenu. Mesuré
    sur le seed livré avant ce correctif, le plus cher des moniteurs valait 2 699 USD
    au seed contre **9 333 USD** à la source, et la carte graphique la plus chère
    3 863 USD contre **7 516 USD**. Un moteur à contrainte budgétaire dont le catalogue
    s'arrête à 2 699 USD ne peut pas être exercé sur un budget large : le cas « je n'ai
    pas de limite de prix » n'aurait aucun produit à départager.

    Ce n'est pas un défaut de la stratification, c'est sa limite — d'où un **repêchage**
    et non un changement de tirage. La graine, les quotas et le découpage en strates ne
    bougent pas, et les produits déjà tirés restent tirés : le diff du seed est fait
    uniquement d'ajouts.

    Départage déterministe : prix maximal, puis `id` le plus petit — la même règle que
    `garantir_g1`, pour qu'un seul critère de tri gouverne toutes les garanties.

    **Aucune garantie symétrique sur le produit le moins cher**, et c'est délibéré : le
    premier décile est dense, son minimum y est déjà représenté, et une garantie qui ne
    repêche jamais rien est du code mort qui se donne l'air d'une preuve.
    """
    ajouts: list[ProduitEnBase] = []
    cas: list[CasLimiteG4] = []

    for categorie in CATEGORIES:
        du_pool = [p for p in pool if p.categorie == categorie]
        if not du_pool:
            continue
        # `-prix` puis `id` croissant : le plus cher gagne, le plus petit `id` départage.
        le_plus_cher = min(du_pool, key=lambda p: (-p.prix_usd, p.id))
        deja_tire = any(p.id == le_plus_cher.id for p in selection)
        if not deja_tire:
            ajouts.append(le_plus_cher)
        cas.append(
            CasLimiteG4(
                categorie=categorie,
                id_produit=le_plus_cher.id,
                prix_usd=le_plus_cher.prix_usd,
                repeche=not deja_tire,
            )
        )
    return ajouts, cas


def _specs_hors_prix(produit: ProduitEnBase) -> dict[str, Any]:
    """Specs du produit, privées des grandeurs qui dérivent du prix."""
    specs = produit.specs_pour_base()
    return {cle: valeur for cle, valeur in specs.items() if cle not in CHAMPS_DERIVES_DU_PRIX}


def _forment_un_couple_g2(a: ProduitEnBase, b: ProduitEnBase) -> str | None:
    """Rend le champ d'affichage qui sépare `a` et `b`, ou `None` s'ils ne forment pas un couple.

    Le couple recherché est « deux produits quasi identiques » : mêmes filtres durs,
    mêmes scores, prix différents, et **un seul** champ d'affichage qui diffère.
    """
    if a.prix_usd == b.prix_usd:
        return None
    specs_a, specs_b = _specs_hors_prix(a), _specs_hors_prix(b)
    differences = [cle for cle in specs_a if specs_a[cle] != specs_b[cle]]
    if len(differences) != 1:
        return None
    champ = differences[0]
    return champ if champ in CHAMPS_AFFICHAGE.get(a.categorie, ()) else None


def garantir_g2(
    selection: list[ProduitEnBase], pool: Sequence[ProduitEnBase]
) -> tuple[list[ProduitEnBase], CasLimiteG2 | None]:
    """G2 — départage : un couple identique sauf le prix et un champ d'affichage.

    Cherché d'abord dans la sélection ; à défaut, repêché du pool, les **deux**
    produits étant ajoutés pour que le couple soit entier dans le seed.
    """
    trouve = _chercher_couple(selection)
    if trouve is not None:
        a, b, champ = trouve
        return [], _construire_cas_g2(a, b, champ, repeche=False)

    trouve = _chercher_couple(pool)
    if trouve is None:
        return [], None
    a, b, champ = trouve
    deja_presents = {p.id for p in selection}
    ajouts = [p for p in (a, b) if p.id not in deja_presents]
    return ajouts, _construire_cas_g2(a, b, champ, repeche=True)


def _construire_cas_g2(
    a: ProduitEnBase, b: ProduitEnBase, champ: str, *, repeche: bool
) -> CasLimiteG2:
    """Range le couple dans l'ordre des prix pour que le rapport soit lisible."""
    bas, haut = (a, b) if a.prix_usd <= b.prix_usd else (b, a)
    return CasLimiteG2(
        categorie=bas.categorie,
        champ_affichage=champ,
        id_a=bas.id,
        id_b=haut.id,
        prix_a=bas.prix_usd,
        prix_b=haut.prix_usd,
        valeur_a=bas.specs_pour_base().get(champ),
        valeur_b=haut.specs_pour_base().get(champ),
        marque_a=bas.marque,
        marque_b=haut.marque,
        repeche=repeche,
    )


def _chercher_couple(
    produits: Sequence[ProduitEnBase],
) -> tuple[ProduitEnBase, ProduitEnBase, str] | None:
    """Cherche un couple G2, en groupant d'abord sur les specs hors affichage.

    La comparaison deux à deux sur 2 000 produits coûterait deux millions de tests.
    Les candidats sont donc regroupés par leurs specs privées des champs d'affichage :
    seuls les membres d'un même groupe peuvent former un couple.
    """
    groupes: dict[tuple[str, str], list[ProduitEnBase]] = {}
    for produit in sorted(produits, key=lambda p: p.id):
        affichage = CHAMPS_AFFICHAGE.get(produit.categorie, ())
        if not affichage:
            continue  # sans champ d'affichage, aucun couple G2 n'est possible
        specs = _specs_hors_prix(produit)
        signature = repr(sorted((c, v) for c, v in specs.items() if c not in affichage))
        groupes.setdefault((produit.categorie, signature), []).append(produit)

    for membres in groupes.values():
        for indice, a in enumerate(membres):
            for b in membres[indice + 1 :]:
                champ = _forment_un_couple_g2(a, b)
                if champ is not None:
                    return a, b, champ
    return None


def constater_g3(seed: Sequence[ProduitEnBase]) -> CasLimiteG3 | None:
    """G3 — zéro résultat : une combinaison de filtres durs plausible et pourtant vide.

    Elle n'ajoute rien au seed : elle **se constate**.

    **Le critère de choix est ce qui fait la valeur du cas.** Toutes les conjonctions
    de deux filtres durs sont énumérées, et l'on retient celle dont le critère le
    moins bien servi l'est le mieux possible. Sans cela, la première combinaison venue
    l'emporterait — par exemple « un processeur à 1 cœur et 105 W », vide parce qu'elle
    est physiquement absurde, ce qui ne démontre rien. Maximiser le plus faible des
    deux effectifs donne au contraire une demande dont **chaque moitié est banale** au
    catalogue : c'est le vrai cas d'échec du moteur, celui où le client ne comprendra
    pas pourquoi il n'y a rien et où il faudra le lui dire (critère d'acceptation nº6).
    """
    meilleur: CasLimiteG3 | None = None
    meilleur_score = (0, 0)

    for categorie in CATEGORIES:
        du_seed = [(produit, produit.specs_pour_base()) for produit in seed]
        du_seed = [couple for couple in du_seed if couple[0].categorie == categorie]
        if not du_seed:
            continue

        champs = CHAMPS_FILTRE_DUR[categorie]
        # Index inversé : (champ, valeur) → rangs des produits qui la portent. La
        # conjonction devient une intersection d'ensembles, donc quelques
        # microsecondes au lieu d'un balayage du seed par combinaison.
        index: dict[tuple[str, Any], set[int]] = {}
        for rang, (_, specs) in enumerate(du_seed):
            for champ in champs:
                valeur = specs.get(champ)
                if valeur is not None:
                    index.setdefault((champ, valeur), set()).add(rang)

        for indice, champ_a in enumerate(champs):
            for champ_b in champs[indice + 1 :]:
                valeurs_a = sorted((v for (c, v) in index if c == champ_a), key=repr)
                valeurs_b = sorted((v for (c, v) in index if c == champ_b), key=repr)
                for valeur_a in valeurs_a:
                    rangs_a = index[(champ_a, valeur_a)]
                    for valeur_b in valeurs_b:
                        rangs_b = index[(champ_b, valeur_b)]
                        if rangs_a & rangs_b:
                            continue
                        score = (min(len(rangs_a), len(rangs_b)), len(rangs_a) + len(rangs_b))
                        if score <= meilleur_score:
                            continue
                        meilleur_score = score
                        meilleur = CasLimiteG3(
                            categorie=categorie,
                            criteres={champ_a: valeur_a, champ_b: valeur_b},
                            effectifs_isoles={
                                f"{champ_a}={valeur_a}": len(rangs_a),
                                f"{champ_b}={valeur_b}": len(rangs_b),
                            },
                        )
    return meilleur


@dataclass
class ResultatSelection:
    """Le seed retenu et tout ce qu'il faut pour en rendre compte."""

    produits: list[ProduitEnBase]
    rapports: list[RapportSelection]
    g1: list[CasLimiteG1]
    g2: CasLimiteG2 | None
    g3: CasLimiteG3 | None
    g4: list[CasLimiteG4]


def selectionner(
    valides: Sequence[ProduitEnBase],
    cible: int = CIBLE_PAR_CATEGORIE,
    graine: int = GRAINE_TIRAGE,
) -> ResultatSelection:
    """Tire le seed complet, puis vérifie et complète les garanties de cas limites.

    L'ordre compte : G1, G2 et G4 s'appliquent **après** le tirage, et leurs repêchages
    peuvent porter l'effectif d'une catégorie légèrement au-dessus de la cible. C'est
    voulu — mieux vaut 172 produits dont les cas limites que 170 sans eux.

    G3 se calcule **en dernier**, sur la sélection complète : c'est la seule garantie
    qui se constate au lieu de s'ajouter, donc la seule que les repêchages des trois
    autres peuvent invalider en remplissant une intersection qui était vide.
    """
    selection: list[ProduitEnBase] = []
    rapports: list[RapportSelection] = []
    for categorie in CATEGORIES:
        du_pool = [p for p in valides if p.categorie == categorie]
        if not du_pool:
            continue
        tires, rapport = selectionner_categorie(categorie, du_pool, cible=cible, graine=graine)
        selection.extend(tires)
        rapports.append(rapport)

    par_categorie = {rapport.categorie: rapport for rapport in rapports}

    ajouts_g1, cas_g1 = garantir_g1(selection, valides)
    selection.extend(ajouts_g1)
    for produit in ajouts_g1:
        par_categorie[produit.categorie].repeches_g1.append(produit.id)

    ajouts_g2, cas_g2 = garantir_g2(selection, valides)
    selection.extend(ajouts_g2)
    for produit in ajouts_g2:
        par_categorie[produit.categorie].repeches_g2.append(produit.id)

    ajouts_g4, cas_g4 = garantir_g4(selection, valides)
    selection.extend(ajouts_g4)
    for produit in ajouts_g4:
        par_categorie[produit.categorie].repeches_g4.append(produit.id)

    # Trié par `id` : c'est l'ordre du JSONL committé, et c'est ce qui rend le diff
    # git lisible quand un seul produit change.
    selection.sort(key=lambda produit: produit.id)
    return ResultatSelection(
        produits=selection,
        rapports=rapports,
        g1=cas_g1,
        g2=cas_g2,
        g3=constater_g3(selection),
        g4=cas_g4,
    )
