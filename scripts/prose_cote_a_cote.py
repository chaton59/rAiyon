"""Deux sessions, la même conversation, les proses en regard. **Lu depuis Postgres.**

### Pourquoi ce script existe, et ce qu'il corrige

Il a été écrit après une faute, et la faute vaut d'être nommée : la comparaison v2/v3 de
l'étape 21 a d'abord été assemblée **à la main**, en recopiant la sortie terminale de
`scripts/essais.py` dans un rapport. Plusieurs fragments en sont ressortis corrompus au
niveau du caractère — « vous voulez qus », « du 144 Hzge » — et il a fallu requêter la base
pour établir que la prose stockée, elle, était intacte.

La leçon n'est pas « mieux recopier ». C'est qu'une comparaison qui décide d'une version de
prompt ne doit pas passer par une transcription : **elle se lit là où la donnée est**.

⚠️ **Ce script ne parse aucune sortie de terminal**, et c'est tout son intérêt. Les deux
étapes fragiles de la première tentative — capturer un flux ANSI, puis en extraire des
lignes préfixées par `│` — ont disparu. Il lit la base, comme le tableau de bord.

### Il lit `evenements_tour`, et surtout **il ne re-dérive rien**

Première version de ce script : reconstruire la prose depuis les blocs de
`tours_conversation` — le texte des lignes `assistant`, plus l'argument `question` des
`tool_use` nommés `ask_clarification`. Elle a immédiatement produit une question affichée
**deux fois**, et il a fallu ouvrir la base pour comprendre : le premier
`ask_clarification` du tour avait été **refusé par le répartiteur** (`categorie_absente`),
le modèle avait enregistré la catégorie puis reposé la même question. Le client n'en avait
vu qu'une ; mon script en montrait deux.

C'est la même faute que celle qui a motivé ce fichier, d'un cran plus subtile : **un bloc
`tool_use` présent en base n'est pas une preuve que son effet a atteint le client.** Un
outil peut refuser, un texte peut être rejeté par le validateur, une question peut ne
jamais partir.

La correction n'est pas de rajouter des cas. C'est de cesser de re-dériver : la table
`evenements_tour` porte **exactement** ce qui est parti au client, dans l'ordre où il l'a
reçu, parce que c'est la sérialisation du fil SSE lui-même. Trois genres y suffisent :

| genre | ce que c'est |
|---|---|
| `message` | le texte d'un message assistant, validé et livré |
| `question` | la question d'`ask_clarification`, une fois qu'elle est réellement partie |
| `fallback` | le repli, écrit en Python, que le client lit comme le reste |

`text_rejected` n'y figure pas dans la prose livrée, par construction : il porte ce qui a
été refusé. `--refuses` le montre à part, marqué comme jamais lu.

⚠️ **Une session antérieure à l'instrumentation n'a pas d'événements** et ce script le dit
au lieu de reconstruire quelque chose d'approchant. C'est le même refus : mieux vaut
« je ne sais pas » qu'une prose plausible.

### La lecture passe par `api/journal.chronologie()`

Le tableau de bord assemble déjà les tours — message du client, appels, événements — et il
est testé. En écrire une seconde version ici donnerait deux vérités sur la même donnée,
qui est précisément ce que ce script existe pour éviter.
"""

import argparse
import uuid
from typing import Any

from sqlalchemy.orm import Session

from raiyon.api import journal
from raiyon.db.engine import get_sessionmaker

GENRES_LIVRES = ("message", "question", "fallback")
"""Les trois genres que le client a réellement lus. **Fermé, et dérivé du fil SSE.**

`text_rejected` en est absent : il porte un texte que le validateur a refusé avant l'envoi.
Les cinq autres genres décrivent la mécanique (critères, sondage, produits) et sont rendus
par l'interface autrement que par de la prose."""


def prose_de(base: Session, identifiant: uuid.UUID) -> list[dict[str, Any]]:
    """Les tours d'une session : le message du client, et ce qu'il a lu en retour."""
    chronologie = journal.chronologie(base, identifiant)
    if chronologie is None:
        raise SystemExit(f"⛔ aucune session {identifiant}.")
    tours = []
    for tour in chronologie["tours"]:
        livre = [
            _prose(evenement)
            for evenement in tour["evenements"]
            if evenement["genre"] in GENRES_LIVRES
        ]
        tours.append(
            {
                "client": tour["message_client"],
                "livre": livre,
                "refuses": [
                    appel["texte"] for appel in tour["appels"] if appel["refuse"] and appel["texte"]
                ],
                "mesure": tour["mesure"],
            }
        )
    return tours


def _prose(evenement: dict[str, Any]) -> str:
    """Le texte d'un événement livré. Une clé par genre, sans repli silencieux sur `str()`."""
    charge = evenement["charge"]
    if evenement["genre"] == "question":
        return str(charge["question"])
    return str(charge["message" if evenement["genre"] == "fallback" else "texte"])


def _citer(texte: str) -> None:
    """Un bloc de citation markdown, ligne à ligne — les lignes vides comprises."""
    for ligne in texte.splitlines() or [""]:
        print(f"> {ligne}" if ligne.strip() else ">")


def main() -> int:
    """Rend les deux conversations en regard, tour par tour, en markdown citable."""
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("gauche", metavar="LABEL=UUID", help="la session de référence")
    analyseur.add_argument("droite", metavar="LABEL=UUID", help="la session comparée")
    analyseur.add_argument(
        "--refuses",
        action="store_true",
        help="montre aussi les textes que le validateur a refusés (jamais lus par le client)",
    )
    arguments = analyseur.parse_args()

    cotes = []
    with get_sessionmaker()() as base:
        for entree in (arguments.gauche, arguments.droite):
            label, brut = entree.split("=", 1)
            cotes.append((label, prose_de(base, uuid.UUID(brut))))

    (label_g, gauche), (label_d, droite) = cotes
    # `strict=False` : deux versions de prompt peuvent clore la conversation à des tours
    # différents. On compare ce qui se compare, et le compte des tours est dans le tableau.
    for rang, (tour_g, tour_d) in enumerate(zip(gauche, droite, strict=False), start=1):
        # ⚠️ Deux sessions qui n'ont pas reçu le même message ne se comparent pas. Le dire
        # plutôt que d'aligner deux colonnes qui n'ont rien à voir.
        if tour_g["client"] != tour_d["client"]:
            print(f"\n⚠️ tour {rang} : les deux sessions n'ont pas reçu le même message.\n")
        print(f"\n**Tour {rang}** — client > {tour_g['client']}\n")
        for label, tour in ((label_g, tour_g), (label_d, tour_d)):
            print(f"> **{label}**")
            if not tour["mesure"]:
                _citer("(session antérieure à l'instrumentation : aucun événement enregistré)")
            elif not tour["livre"]:
                _citer("(aucune prose livrée)")
            else:
                for indice, morceau in enumerate(tour["livre"]):
                    if indice:
                        print(">")
                    _citer(morceau)
            if arguments.refuses:
                for refuse in tour["refuses"]:
                    print(">")
                    print("> *(refusé par le validateur, jamais lu par le client)*")
                    _citer(refuse)
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
