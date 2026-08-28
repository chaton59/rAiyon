"""Script jetable — étape 3. Mesure le dataset brut, n'écrit rien dans src/.

Usage : python scripts/explore_dataset.py
Sorties : catalogue/rapport_exploration.md et catalogue/echantillons/<categorie>.json
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
BRUT = RACINE / "data" / "raw"
SORTIE = RACINE / "catalogue"

CATEGORIES = [
    "cpu",
    "monitor",
    "internal-hard-drive",
    "memory",
    "video-card",
    "headphones",
    "keyboard",
]

SEUILS_PRIX = [100, 200, 300, 500, 1000]

# Attributs annoncés par API.md (commit c52a04c) — sert à détecter les champs
# promis par la documentation mais absents des données.
PROMIS = {
    "cpu": [
        "core_count",
        "core_clock",
        "boost_clock",
        "microarchitecture",
        "tdp",
        "graphics",
        "smt",
    ],
    "monitor": [
        "screen_size",
        "resolution",
        "refresh_rate",
        "response_time",
        "panel_type",
        "aspect_ratio",
    ],
    "internal-hard-drive": [
        "capacity",
        "price_per_gb",
        "type",
        "cache",
        "form_factor",
        "interface",
    ],
    "memory": ["speed", "modules", "price_per_gb", "color", "first_word_latency", "cas_latency"],
    "video-card": ["chipset", "memory", "core_clock", "boost_clock", "color", "length"],
    "headphones": [
        "type",
        "frequency_response",
        "microphone",
        "wireless",
        "enclosure_type",
        "color",
    ],
    "keyboard": ["style", "switches", "backlit", "tenkeyless", "connection_type", "color"],
}
TAILLE_ECHANTILLON = 20


# --------------------------------------------------------------------------- #
# Typage et agrégation
# --------------------------------------------------------------------------- #
def nom_type(valeur: object) -> str:
    if isinstance(valeur, bool):
        return "bool"
    if isinstance(valeur, (int, float)):
        return "number"
    if isinstance(valeur, str):
        return "string"
    if isinstance(valeur, list):
        types = sorted({nom_type(v) for v in valeur})
        return "[" + ", ".join(types) + "]"
    return type(valeur).__name__


def est_renseigne(valeur: object) -> bool:
    if valeur is None:
        return False
    if isinstance(valeur, list):
        return any(v is not None for v in valeur)
    if isinstance(valeur, str):
        return valeur.strip() != ""
    return True


def quantiles(valeurs: list[float]) -> dict[str, float]:
    tri = sorted(valeurs)
    n = len(tri)

    def q(p: float) -> float:
        if n == 1:
            return tri[0]
        i = p * (n - 1)
        bas, haut = int(i), min(int(i) + 1, n - 1)
        return tri[bas] + (tri[haut] - tri[bas]) * (i - bas)

    return {
        "min": tri[0],
        "p25": q(0.25),
        "med": statistics.median(tri),
        "p75": q(0.75),
        "max": tri[-1],
    }


def fmt(x: float) -> str:
    if isinstance(x, float) and x != int(x):
        return f"{x:,.3f}".rstrip("0").rstrip(".").replace(",", " ")
    return f"{int(x):,}".replace(",", " ")


def echappe(x: object) -> str:
    return str(x).replace("|", "\\|")


# --------------------------------------------------------------------------- #
# Mesure d'un attribut
# --------------------------------------------------------------------------- #
def mesure_attribut(produits: list[dict], champ: str) -> dict:
    valeurs = [p.get(champ) for p in produits]
    renseignes = [v for v in valeurs if est_renseigne(v)]
    types = Counter(nom_type(v) for v in renseignes)

    res: dict = {
        "champ": champ,
        "n_renseignes": len(renseignes),
        "taux": 100.0 * len(renseignes) / len(produits) if produits else 0.0,
        "types": types,
        "heterogene": len(types) > 1,
    }

    # composantes numériques : soit la valeur elle-même, soit chaque case de liste
    scalaires = [v for v in renseignes if isinstance(v, (int, float)) and not isinstance(v, bool)]
    listes = [v for v in renseignes if isinstance(v, list)]
    non_numeriques = [v for v in renseignes if isinstance(v, (str, bool))]

    res["stats"] = quantiles([float(v) for v in scalaires]) if scalaires else None

    res["composantes"] = []
    if listes:
        largeur = max(len(v) for v in listes)
        for i in range(largeur):
            comp = [
                float(v[i])
                for v in listes
                if len(v) > i and isinstance(v[i], (int, float)) and not isinstance(v[i], bool)
            ]
            if comp:
                res["composantes"].append((f"{champ}[{i}]", len(comp), quantiles(comp)))

    # cardinalité : sur les valeurs non numériques (string/bool) et sur les listes courtes
    enumerables = [str(v) for v in non_numeriques]
    if listes and not scalaires:
        enumerables += [json.dumps(v) for v in listes]
    if enumerables:
        compte = Counter(enumerables)
        res["cardinalite"] = len(compte)
        res["top"] = compte.most_common(10)
    else:
        res["cardinalite"] = None
        res["top"] = []

    return res


# --------------------------------------------------------------------------- #
# Rapport
# --------------------------------------------------------------------------- #
def section(categorie: str, lignes: list[str]) -> list[dict]:
    produits = json.loads((BRUT / f"{categorie}.json").read_text(encoding="utf-8"))
    total = len(produits)
    avec_prix = [p for p in produits if isinstance(p.get("price"), (int, float))]
    n = len(avec_prix)

    champs: list[str] = []
    for p in produits:
        for k in p:
            if k not in champs:
                champs.append(k)
    attributs = [c for c in champs if c not in ("name", "price")]

    lignes.append(f"\n## `{categorie}`\n")
    lignes.append(f"- Produits au total : **{total}**")
    lignes.append(
        f"- Produits avec un `price` non nul : **{n}** "
        f"({100 * n / total:.1f} % du fichier) — c'est la base de toutes les mesures qui suivent"
    )
    lignes.append(f"- Champs présents dans le fichier : `{'`, `'.join(champs)}`")

    absents = [c for c in PROMIS[categorie] if c not in champs]
    if absents:
        lignes.append(
            f"- ⚠️ Champs annoncés par `API.md` et **absents du fichier** : `{'`, `'.join(absents)}`"
        )

    noms = Counter(p.get("name") for p in avec_prix)
    doublons = {n: c for n, c in noms.items() if c > 1}
    identiques = 0
    par_nom: dict[str, list[str]] = {}
    for p in avec_prix:
        if noms[p.get("name")] > 1:
            empreinte = json.dumps(
                {k: v for k, v in p.items() if k not in ("name", "price")}, sort_keys=True
            )
            par_nom.setdefault(p["name"], []).append(empreinte)
    identiques = sum(1 for v in par_nom.values() if len(set(v)) == 1)
    lignes.append(
        f"- Noms distincts : **{len(noms)}** — {len(doublons)} noms portés par plusieurs "
        f"entrées, dont **{identiques}** où les attributs hors prix sont strictement "
        f"identiques (le reste sont des variantes réelles)"
    )
    lignes.append("")

    # --- prix
    prix = [float(p["price"]) for p in avec_prix]
    qp = quantiles(prix)
    lignes.append("### Distribution des prix (USD, snapshot juillet 2025)\n")
    lignes.append("| min | p25 | médiane | p75 | max |")
    lignes.append("| --- | --- | --- | --- | --- |")
    cellules = " | ".join(f"{qp[k]:.2f}" for k in ("min", "p25", "med", "p75", "max"))
    lignes.append(f"| {cellules} |\n")
    lignes.append("| seuil | produits en dessous | part |")
    lignes.append("| --- | --- | --- |")
    for s in SEUILS_PRIX:
        c = sum(1 for x in prix if x < s)
        lignes.append(f"| < {s} USD | {c} | {100 * c / n:.1f} % |")
    lignes.append("")

    # --- remplissage
    mesures = [mesure_attribut(avec_prix, c) for c in attributs]
    lignes.append("### Taux de remplissage (sur les produits à prix)\n")
    lignes.append("| attribut | renseignés | taux | types rencontrés |")
    lignes.append("| --- | --- | --- | --- |")
    for m in sorted(mesures, key=lambda m: -m["taux"]):
        types = ", ".join(f"`{t}` ({c})" for t, c in m["types"].most_common())
        drapeau = " ⚠️" if m["heterogene"] else ""
        lignes.append(
            f"| `{m['champ']}` | {m['n_renseignes']} | **{m['taux']:.1f} %** | {types}{drapeau} |"
        )
    lignes.append("")

    hetero = [m for m in mesures if m["heterogene"]]
    if hetero:
        lignes.append("**Champs à type hétérogène** (⚠️ ci-dessus) :\n")
        for m in hetero:
            detail = " · ".join(
                f"`{t}` : {c} ({100 * c / m['n_renseignes']:.1f} %)"
                for t, c in m["types"].most_common()
            )
            lignes.append(f"- `{m['champ']}` → {detail}")
        lignes.append("")

    # --- numériques
    numeriques = [m for m in mesures if m["stats"] or m["composantes"]]
    if numeriques:
        lignes.append("### Attributs numériques\n")
        lignes.append("| attribut | n | min | p25 | médiane | p75 | max |")
        lignes.append("| --- | --- | --- | --- | --- | --- | --- |")
        for m in numeriques:
            if m["stats"]:
                s = m["stats"]
                nn = sum(c for t, c in m["types"].items() if t == "number")
                lignes.append(
                    f"| `{m['champ']}` | {nn} | {fmt(s['min'])} | {fmt(s['p25'])} | "
                    f"{fmt(s['med'])} | {fmt(s['p75'])} | {fmt(s['max'])} |"
                )
            for nom, cnt, s in m["composantes"]:
                lignes.append(
                    f"| `{nom}` | {cnt} | {fmt(s['min'])} | {fmt(s['p25'])} | "
                    f"{fmt(s['med'])} | {fmt(s['p75'])} | {fmt(s['max'])} |"
                )
        lignes.append("")

    # --- énumérables
    enumerables = [m for m in mesures if m["cardinalite"]]
    if enumerables:
        lignes.append("### Attributs énumérables — cardinalité et 10 valeurs les plus fréquentes\n")
        for m in enumerables:
            base = m["n_renseignes"]
            lignes.append(
                f"**`{m['champ']}`** — cardinalité **{m['cardinalite']}** "
                f"sur {base} valeurs renseignées\n"
            )
            lignes.append("| valeur | effectif | part |")
            lignes.append("| --- | --- | --- |")
            for v, c in m["top"]:
                lignes.append(f"| `{echappe(v)}` | {c} | {100 * c / base:.1f} % |")
            lignes.append("")

    return avec_prix


def echantillon(categorie: str, avec_prix: list[dict]) -> None:
    """20 produits couvrant la gamme de prix : positions régulières sur le tri par prix."""
    tri = sorted(avec_prix, key=lambda p: (float(p["price"]), p.get("name") or ""))
    n = len(tri)
    k = min(TAILLE_ECHANTILLON, n)
    idx = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)}) if k > 1 else [0]
    extrait = [tri[i] for i in idx]
    chemin = SORTIE / "echantillons" / f"{categorie}.json"
    chemin.write_text(json.dumps(extrait, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"{categorie:22s} échantillon {len(extrait)} produits "
        f"({extrait[0]['price']} → {extrait[-1]['price']} USD)"
    )


def main() -> None:
    (SORTIE / "echantillons").mkdir(parents=True, exist_ok=True)
    lignes = [
        "# Rapport d'exploration du dataset — étape 3",
        "",
        "Mesure brute, sans interprétation. Généré par `scripts/explore_dataset.py`.",
        "Source : `docyx/pc-part-dataset`, commit `c52a04ca9465c83997ed335f7767b09a2005dd26`",
        "(voir `data/raw/SOURCE.md`).",
        "",
        "Les taux de remplissage sont calculés **sur les produits ayant un prix**, pas sur",
        "le fichier entier : un produit sans prix ne peut pas entrer dans un moteur à",
        "contrainte budgétaire.",
        "",
        "## Vue d'ensemble",
        "",
        "| catégorie | produits | avec prix | part exploitable |",
        "| --- | --- | --- | --- |",
    ]

    resume = []
    for c in CATEGORIES:
        produits = json.loads((BRUT / f"{c}.json").read_text(encoding="utf-8"))
        n = sum(1 for p in produits if isinstance(p.get("price"), (int, float)))
        resume.append((c, len(produits), n))
        lignes.append(f"| `{c}` | {len(produits)} | {n} | {100 * n / len(produits):.1f} % |")

    total, total_prix = sum(r[1] for r in resume), sum(r[2] for r in resume)
    lignes.append(
        f"| **total** | **{total}** | **{total_prix}** | **{100 * total_prix / total:.1f} %** |"
    )

    for c in CATEGORIES:
        avec_prix = section(c, lignes)
        echantillon(c, avec_prix)

    (SORTIE / "rapport_exploration.md").write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print(f"\n→ {SORTIE / 'rapport_exploration.md'}")


if __name__ == "__main__":
    main()
