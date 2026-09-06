"""Contrôle de fumée — `make fumee`. **Le premier appel API du projet.**

Un appel jetable qui envoie les cinq définitions d'outils avec un message trivial, et dit
quel mode a été retenu : `strict: true`, ou le repli de l'arbitrage 11.

**Pourquoi cette cible existe alors que la boucle la couvrirait.** Le drapeau `strict`
est porté par `schema_des_outils()` depuis l'étape 7, mais le sous-ensemble de JSON
Schema qu'il admet n'est écrit nulle part dans le paquet installé : l'`enum` de 36 champs
et les propriétés optionnelles hors `required` sont des paris non mesurés. Le dépôt en a
déjà perdu trois — `smt` à l'étape 3, `temperature=0` et `nom_fr` à l'étape 5 — et chaque
fois la découverte s'est faite au milieu d'autre chose. Ici, elle se fait seule, en un
appel, avant que la boucle existe.

C'est aussi le seul endroit où l'on constate que la clé, le modèle configuré et le réseau
fonctionnent, sans base de données ni prompt système.
"""

import argparse
import sys

from raiyon.agent.client_anthropic import ClientAnthropic
from raiyon.config import ConfigurationError
from raiyon.journal import configurer_journal
from raiyon.tools.schema_outils import champs_du_schema, schema_des_outils

MESSAGE = (
    "Bonjour. Réponds uniquement par le mot OK, sans appeler d'outil : "
    "ceci est un contrôle de fumée."
)


def main() -> int:
    """Appelle le modèle une fois. Rend 1 si la clé manque ou si l'API refuse."""
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument(
        "--sans-strict",
        action="store_true",
        help="envoie d'emblée les définitions sans le drapeau strict (contre-épreuve)",
    )
    arguments = analyseur.parse_args()

    configurer_journal()
    outils = schema_des_outils(strict=not arguments.sans_strict)
    try:
        client = ClientAnthropic()
        reponse = client.repondre(
            systeme="Tu es un contrôle de fumée. Réponds par OK.",
            outils=outils,
            messages=[{"role": "user", "content": MESSAGE}],
        )
    except ConfigurationError as erreur:
        print(f"\n⛔ {erreur}\n", file=sys.stderr)
        return 1

    # Le mode **demandé** et le mode **effectif** sont affichés séparément, et ce n'est
    # pas de la coquetterie : `client.strict` dit seulement que le repli ne s'est pas
    # déclenché. Sous `--sans-strict`, il vaut donc vrai alors que les définitions
    # envoyées ne portaient pas le drapeau. Une seule ligne aurait affirmé « strict:
    # true » sur un appel qui ne l'était pas — exactement le genre de mesure fausse que
    # cette cible existe pour empêcher.
    demande = "strict: true" if not arguments.sans_strict else "sans le drapeau strict"
    effectif = demande if client.strict else "repli — définitions sans strict"
    textes = [bloc.get("text", "") for bloc in reponse.blocs if bloc.get("type") == "text"]
    print(
        f"\n✓ Appel abouti.\n"
        f"  mode demandé     : {demande}\n"
        f"  repli déclenché  : {'non' if client.strict else 'OUI'}\n"
        f"  mode effectif    : {effectif}\n"
        f"  outils envoyés   : {len(outils)}\n"
        f"  champs de l'enum : {len(champs_du_schema())}\n"
        f"  stop_reason      : {reponse.fin}\n"
        f"  réponse          : {' '.join(textes).strip()!r}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
