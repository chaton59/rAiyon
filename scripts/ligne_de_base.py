"""Le tableau d'une ligne de base : ce que le journal sait des sessions qu'on lui nomme.

### Pourquoi un script et pas une lecture à l'œil du tableau de bord

Le tableau de bord de l'étape 23 rend **une** session à la fois, et il est fait pour être
lu. Comparer deux versions de prompt demande l'inverse : huit sessions, cinq colonnes, et
la même définition appliquée aux huit. La lire huit fois à l'écran, c'est huit occasions
de compter autrement.

⚠️ **Ce script ne mesure rien de neuf.** Il agrège `appels_modele` et `evenements_tour`,
écrites par `session.tour()` pendant les conversations. Il n'appelle aucune API, ne
persiste rien, et peut être relancé sur les mêmes sessions autant de fois qu'on veut.

### La seule définition non évidente : « tours jusqu'à une recommandation »

Un tour **recommande** quand il émet un `products_found` **et** un `message`. Les deux
sont nécessaires et aucun ne suffit :

* `products_found` seul — la recherche a eu lieu, mais le tour s'est clos sur une question
  ou un repli ; le client n'a pas reçu de conseil ;
* `message` seul — l'assistant a parlé sans avoir cherché ; c'est du dialogue, pas une
  recommandation.

Le chiffre rendu est le **rang du tour client**, à partir de 1 — pas son `tour_client`,
qui compte aussi les lignes de `tool_result`. `—` veut dire qu'aucun tour de la
conversation n'a recommandé, ce qui est une information et non une donnée manquante.
"""

import argparse
import sys
import uuid
from collections import Counter
from collections.abc import Sequence
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from raiyon.db.engine import get_sessionmaker
from raiyon.db.models import AppelModele, EvenementTour
from raiyon.eval.metriques import Attente, attentes_du_journal
from raiyon.eval.scenario import ScenarioInconnu, par_nom
from raiyon.observation import cout_estime_usd

GENRE_PRODUITS = "products_found"
GENRE_MESSAGE = "message"
GENRE_REJET = "text_rejected"
GENRE_REPLI = "fallback"


def _mesurer(base: Session, identifiant: uuid.UUID) -> dict[str, Any]:
    """Les cinq colonnes, plus ce qui aide à les lire."""
    appels = list(
        base.scalars(
            select(AppelModele)
            .where(AppelModele.session_id == identifiant)
            .order_by(AppelModele.tour_client, AppelModele.iteration)
        )
    )
    evenements = list(
        base.scalars(
            select(EvenementTour)
            .where(EvenementTour.session_id == identifiant)
            .order_by(EvenementTour.tour_client, EvenementTour.rang)
        )
    )

    par_tour: dict[int, set[str]] = {}
    for evenement in evenements:
        par_tour.setdefault(evenement.tour_client, set()).add(evenement.genre)

    tours = sorted({appel.tour_client for appel in appels} | set(par_tour))
    recommande = None
    for rang, numero in enumerate(tours, start=1):
        genres = par_tour.get(numero, set())
        if GENRE_PRODUITS in genres and GENRE_MESSAGE in genres:
            recommande = rang
            break

    griefs: Counter[str] = Counter()
    replis: Counter[str] = Counter()
    for evenement in evenements:
        if evenement.genre == GENRE_REJET:
            griefs.update(str(grief.get("code")) for grief in evenement.charge.get("griefs", []))
        elif evenement.genre == GENRE_REPLI:
            replis.update([str(evenement.charge.get("motif"))])

    latences = [appel.latence_ms for appel in appels]
    couts = [
        cout_estime_usd(
            modele=appel.modele,
            jetons_entree=appel.jetons_entree,
            jetons_sortie=appel.jetons_sortie,
            cache_ecrit=appel.cache_ecrit,
            cache_lu=appel.cache_lu,
        )
        for appel in appels
    ]
    return {
        "tours": len(tours),
        "attentes_tenues": attentes_du_journal(
            [(evenement.tour_client, evenement.genre, evenement.charge) for evenement in evenements]
        ),
        "appels": len(appels),
        "jetons_sortie": sum(appel.jetons_sortie for appel in appels),
        "jetons_entree": sum(appel.jetons_entree for appel in appels),
        "cache_lu": sum(appel.cache_lu for appel in appels),
        "griefs": dict(griefs),
        "replis": dict(replis),
        "recommande": recommande,
        "latence_mediane": int(median(latences)) if latences else None,
        "cout": None if any(cout is None for cout in couts) else sum(couts),  # type: ignore[misc]
    }


# --------------------------------------------------------------------------- #
# Les prises multiples — étape 30
# --------------------------------------------------------------------------- #


def _amplitude(valeurs: Sequence[float | None]) -> str:
    """`min/méd/max` sur les prises, ou la valeur seule s'il n'y en a qu'une.

    🔴 **C'est le correctif du défaut le plus important mesuré sur ce projet.** Trois
    exécutions identiques des mêmes quatre scénarios ont rendu 3, 0 puis 2 griefs. Un
    tableau qui publie un compte sans son amplitude ne dit donc pas « voilà le
    comportement », il dit « voilà un tirage » — et laisse le lecteur croire le premier.

    Les `None` sont écartés et non comptés comme zéro : une prise qui n'a jamais recommandé
    n'a pas « recommandé au tour 0 », elle n'a pas de rang. Même raison que
    `tours_avant_valeur` dans le harnais d'éval.
    """
    connues = [valeur for valeur in valeurs if valeur is not None]
    if not connues:
        return "—"
    if len(connues) == 1:
        return _nombre(connues[0])
    plus_bas, plus_haut = min(connues), max(connues)
    if plus_bas == plus_haut:
        return f"={_nombre(plus_bas)}"
    return f"{_nombre(plus_bas)}/{_nombre(median(connues))}/{_nombre(plus_haut)}"


def _nombre(valeur: float) -> str:
    """Un entier reste un entier ; une médiane paire peut tomber sur un demi."""
    return str(int(valeur)) if float(valeur).is_integer() else f"{valeur:.1f}"


def _conformite(label: str, mesures: Sequence[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    """La conformité aux attentes du scénario que le label nomme, prise par prise.

    ### ⚠️ Pourquoi cette colonne existe (étape 32)

    `Scenario.attentes` n'avait **qu'un lecteur**, `make eval`, et une exigence dont la
    seule vérification demande un jeu de cassettes enregistré sera violée en silence — pas
    par négligence, par économie. Elle l'a été : l'intention de `budget_absent`
    (« demander le budget avant de chercher », 2026-09-01) contredisait §6 de `systeme.v3`
    (« cherchez et montrez », 2026-09-06) pendant cinq jours, et il a fallu une campagne à
    3,08 $ pour que quiconque lise le champ.

    ⚠️ **Le liage se fait par le label**, et c'est délibérément faible : un label qui ne
    nomme aucun scénario rend `—`, jamais une conformité inventée. Le `—` est **le
    résultat le plus important de cette colonne** — il dit « cette conversation n'est
    adossée à aucune exigence », ce qui est précisément l'état dans lequel les vingt-quatre
    conversations d'essai ont toujours été, sans que rien ne le dise. Un scénario qui
    porterait une attente qu'aucun harnais n'exerce se verrait de la même manière ; le
    contrôle statique, lui, est dans `tests/eval/test_scenarios.py`.

    Rend le libellé de colonne et le compte des attentes non tenues, par nom.
    """
    try:
        exigees = par_nom(label).attentes
    except ScenarioInconnu:
        return "—", {}
    if not exigees:
        return "0 exig.", {}
    manquees: dict[str, int] = {}
    conformes = 0
    for mesure in mesures:
        tenues: frozenset[Attente] = mesure["attentes_tenues"]
        absentes = exigees - tenues
        if absentes:
            for attente in absentes:
                manquees[attente.value] = manquees.get(attente.value, 0) + 1
        else:
            conformes += 1
    marque = "✅" if conformes == len(mesures) else "❌"
    return f"{conformes}/{len(mesures)}{marque}", manquees


def _grouper(lignes: Sequence[tuple[str, uuid.UUID, dict[str, Any]]]) -> dict[str, list[dict]]:
    """Les mesures par label, dans l'ordre d'apparition. Un label répété = plusieurs prises."""
    groupes: dict[str, list[dict[str, Any]]] = {}
    for label, _, mesure in lignes:
        groupes.setdefault(label, []).append(mesure)
    return groupes


def main() -> int:
    """Rend le tableau des sessions nommées. Un `label=uuid` par argument.

    **Un label répété est un scénario à plusieurs prises** : les mesures sont alors
    publiées en `min/méd/max` au lieu d'un nombre seul.
    """
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument(
        "sessions",
        nargs="+",
        metavar="LABEL=UUID",
        help="une session par argument, préfixée d'un libellé lisible",
    )
    arguments = analyseur.parse_args()

    fabrique = get_sessionmaker()
    lignes = []
    with fabrique() as base:
        for entree in arguments.sessions:
            if "=" not in entree:
                print(f"⛔ « {entree} » n'est pas au format LABEL=UUID", file=sys.stderr)
                return 1
            label, brut = entree.split("=", 1)
            lignes.append((label, uuid.UUID(brut), _mesurer(base, uuid.UUID(brut))))

    # ⚠️ **L'ordre des colonnes est une décision, pas une mise en page** (étape 30). Ce
    # qu'un lecteur voit en premier est ce qu'il retient : les deux premières colonnes
    # après le nom sont donc celles qui décrivent **ce que le client a vécu** — a-t-il eu
    # une recommandation, a-t-il reçu un repli. Le compte de griefs vient en dernier,
    # comme diagnostic, parce qu'un grief est un événement interne que le système absorbe.
    entetes = (
        "scénario",
        "prises",
        "→reco",
        "replis",
        "attentes",
        "$/reco",
        "coût $",
        "appels",
        "lat.méd",
        "griefs",
        "détail (diagnostic)",
    )
    print(
        f"| {entetes[0]:<24} | {entetes[1]:>5} | {entetes[2]:>10} | {entetes[3]:>6} | "
        f"{entetes[4]:>8} | {entetes[5]:>6} | {entetes[6]:>6} | {entetes[7]:>8} | "
        f"{entetes[8]:>11} | {entetes[9]:>7} | {entetes[10]}"
    )
    print("  (min/méd/max sur les prises ; « = » quand toutes les prises s'accordent)")
    print("  ⚠️ $/reco est le coût normalisé : une version qui ne recommande pas est toujours")
    print("     moins chère, et le coût brut seul dit alors l'inverse de ce qui s'est passé.")
    print("  ⚠️ attentes : « — » veut dire que le label ne nomme aucun scénario, donc que")
    print("     cette conversation n'est adossée à aucune exigence. C'est une information.")
    largeurs = (26, 7, 12, 8, 10, 8, 8, 10, 13, 9, 26)
    print("|".join("-" * largeur for largeur in largeurs))
    manquements: dict[str, dict[str, int]] = {}
    sans_scenario: list[str] = []
    for label, mesures in _grouper(lignes).items():
        griefs_cumules: Counter[str] = Counter()
        for mesure in mesures:
            griefs_cumules.update(mesure["griefs"])
        # ⚠️ Les griefs sont publiés en **amplitude par prise** et non en total : un total
        # de 6 sur 3 prises peut être « 2, 2, 2 » ou « 6, 0, 0 », et ces deux comportements
        # n'appellent pas la même lecture. Le détail par code suit, cumulé.
        par_prise = [float(sum(mesure["griefs"].values())) for mesure in mesures]
        detail = ", ".join(f"{code} x{n}" for code, n in griefs_cumules.items()) or "—"
        replis_cumules: Counter[str] = Counter()
        for mesure in mesures:
            replis_cumules.update(mesure["replis"])
        recos = [
            None if mesure["recommande"] is None else float(mesure["recommande"])
            for mesure in mesures
        ]
        sans_reco = sum(1 for reco in recos if reco is None)
        reco = _amplitude(recos) + (f" ({sans_reco}∅)" if sans_reco else "")
        cout = sum(mesure["cout"] or 0 for mesure in mesures)
        livrees = len(mesures) - sans_reco
        par_reco = "—" if not livrees else f"{cout / livrees:.4f}"
        replis = sum(sum(mesure["replis"].values()) for mesure in mesures)
        conformite, manquees = _conformite(label, mesures)
        if manquees:
            manquements[label] = manquees
        elif conformite == "—":
            sans_scenario.append(label)
        print(
            f"| {label:<24} | {len(mesures):>5} | {reco:>10} | {replis:>6} | "
            f"{conformite:>8} | {par_reco:>6} | {cout:>6.3f} | "
            f"{_amplitude([float(m['appels']) for m in mesures]):>8} | "
            f"{_amplitude([m['latence_mediane'] for m in mesures]):>11} | "
            f"{_amplitude(par_prise):>7} | {detail}"
        )

    total_sortie = sum(mesure["jetons_sortie"] for _, _, mesure in lignes)
    total_cout = sum(mesure["cout"] or 0 for _, _, mesure in lignes)
    tous_griefs: Counter[str] = Counter()
    tous_replis: Counter[str] = Counter()
    for _, _, mesure in lignes:
        tous_griefs.update(mesure["griefs"])
        tous_replis.update(mesure["replis"])
    prises_totales = len(lignes)
    livrees_totales = sum(1 for _, _, mesure in lignes if mesure["recommande"] is not None)
    par_reco = "—" if not livrees_totales else f"{total_cout / livrees_totales:.4f} $"
    print(
        f"\nTOTAL : {livrees_totales}/{prises_totales} prises ont recommandé · "
        f"replis {sum(tous_replis.values())} · {total_cout:.4f} $ dont **{par_reco} par "
        f"recommandation livrée** · {total_sortie} jetons sortie"
    )
    print(f"        griefs (diagnostic) : {dict(tous_griefs) or '—'}")
    if tous_replis:
        print(f"        replis par motif    : {dict(tous_replis)}")
    if manquements:
        print("\n⛔ ATTENTES NON TENUES — une exigence du dépôt qu'une conversation a violée :")
        for label, manquees in manquements.items():
            detail_attentes = ", ".join(f"{nom} x{n}" for nom, n in sorted(manquees.items()))
            print(f"        {label:<26} {detail_attentes}")
    if sans_scenario:
        # ⚠️ Écrit même quand tout est vert : une conversation qu'aucune exigence ne
        # couvre ne peut pas échouer, et c'est exactement ce qui la rend invisible.
        print(
            f"\n⚠️  {len(sans_scenario)} conversation(s) adossée(s) à aucun scénario, donc "
            f"à aucune attente : {', '.join(sans_scenario)}"
        )
    print("\nURLs :")
    for label, identifiant, _ in lignes:
        print(f"  {label:<26} http://127.0.0.1:8000/journal.html#{identifiant}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
