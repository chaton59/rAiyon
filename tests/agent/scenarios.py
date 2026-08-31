"""Ce que `test_boucle.py` et `test_terminal.py` partagent : le pilote et les décors.

⚠️ **Surtout pas dans `conftest.py`.** `tests/tools/` en a déjà un ; les deux se
chargeraient sous le même nom de module `conftest`, et `pytest tests/agent tests/tools`
échouerait à l'import selon l'ordre de collecte. Le piège est documenté dans
`tests/outils_de_test.py` — il s'est déclenché ici aussi, à l'écriture de ces tests.

`conftest.py` ne garde donc que ce que pytest résout tout seul : les fixtures.
"""

from outils_de_test import critere, etat_avec
from raiyon.agent.boucle import repondre
from raiyon.matching.criteres import Importance, Operateur
from raiyon.tools.etat import EtatSession

SYSTEME = "Tu es un vendeur conseil. (prompt de test, court exprès)"
"""Un faux prompt : ces tests portent sur la mécanique de la boucle, pas sur la conduite
du dialogue — que rien ne mesure avant l'étape 12, et c'est écrit au §7 des risques."""

ECRAN_144 = {
    "categorie": "monitor",
    "criteres": [
        {
            "champ": "refresh_rate",
            "operateur": "au_moins",
            "valeur": "144",
            "importance": "bloquant",
        }
    ],
    "budget_usd": "400",
}


def etat_ecran() -> EtatSession:
    """Un état construit par la porte normale : un écran 144 Hz bloquant, 400 USD."""
    return etat_avec(
        "monitor",
        critere("refresh_rate", Operateur.AU_MOINS, "144", Importance.BLOQUANT),
        budget="400",
    )


def jouer(client, contexte, outils, *, etat=None, max_iterations=8, message_client="Bonjour"):
    """Consomme le générateur **en entier** et rend `(événements, issue)`.

    Le générateur ne produit son issue qu'à la fin : un test qui s'arrêterait au premier
    événement ne verrait ni l'état final ni les tours à persister. C'est la même
    contrainte que celle que `session.py` impose à la console.
    """
    generateur = repondre(
        client=client,
        systeme=SYSTEME,
        outils=outils,
        historique=[],
        message_client=message_client,
        etat=etat if etat is not None else EtatSession(),
        contexte=contexte,
        max_iterations=max_iterations,
    )
    evenements = []
    while True:
        try:
            evenements.append(next(generateur))
        except StopIteration as arret:
            return evenements, arret.value
