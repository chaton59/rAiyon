"""Le tableau d'une ligne de base : ce que le journal sait des sessions qu'on lui nomme.

### Pourquoi un script et pas une lecture à l'œil du tableau de bord

Le tableau de bord de l'étape 17 rend **une** session à la fois, et il est fait pour être
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
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from raiyon.db.engine import get_sessionmaker
from raiyon.db.models import AppelModele, EvenementTour
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


def main() -> int:
    """Rend le tableau des sessions nommées. Un `label=uuid` par argument."""
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

    entetes = (
        "scénario",
        "tours",
        "appels",
        "j.sortie",
        "→reco",
        "lat.méd",
        "coût $",
        "griefs",
        "replis",
    )
    print(
        f"| {entetes[0]:<26} | {entetes[1]:>5} | {entetes[2]:>6} | {entetes[3]:>8} | "
        f"{entetes[4]:>5} | {entetes[5]:>7} | {entetes[6]:>7} | {entetes[7]:<34} | {entetes[8]}"
    )
    largeurs = (28, 7, 8, 10, 7, 9, 9, 36, 20)
    print("|".join("-" * largeur for largeur in largeurs))
    for label, _, mesure in lignes:
        griefs = ", ".join(f"{code} x{compte}" for code, compte in mesure["griefs"].items()) or "—"
        replis = (
            ", ".join(f"{motif} x{compte}" for motif, compte in mesure["replis"].items()) or "—"
        )
        reco = "—" if mesure["recommande"] is None else str(mesure["recommande"])
        cout = "—" if mesure["cout"] is None else f"{mesure['cout']:.4f}"
        print(
            f"| {label:<26} | {mesure['tours']:>5} | {mesure['appels']:>6} | "
            f"{mesure['jetons_sortie']:>8} | {reco:>5} | {mesure['latence_mediane']:>7} | "
            f"{cout:>7} | {griefs:<34} | {replis}"
        )

    total_sortie = sum(mesure["jetons_sortie"] for _, _, mesure in lignes)
    total_cout = sum(mesure["cout"] or 0 for _, _, mesure in lignes)
    tous_griefs: Counter[str] = Counter()
    tous_replis: Counter[str] = Counter()
    for _, _, mesure in lignes:
        tous_griefs.update(mesure["griefs"])
        tous_replis.update(mesure["replis"])
    print(
        f"\nTOTAL : {total_sortie} jetons sortie · {total_cout:.4f} $ estimés · "
        f"griefs {dict(tous_griefs) or '—'} · replis {dict(tous_replis) or '—'}"
    )
    print("\nURLs :")
    for label, identifiant, _ in lignes:
        print(f"  {label:<26} http://127.0.0.1:8000/journal.html#{identifiant}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
