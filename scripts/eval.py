"""Le harnais d'éval en ligne de commande — `make eval`, `eval-enregistrer`, `eval-live`.

Trois modes, trois besoins différents, et c'est **ce qu'ils exigent** qui les sépare :

| Mode | Base | Clé API | Écrit |
|---|---|---|---|
| `rejouer` | oui | **non** | `docs/eval/rapport.md`, et le code de sortie |
| `enregistrer` | oui | oui | `evals/cassettes/*.json` |
| `live` | oui | oui | rien |

Le rejeu n'a pas besoin de clé : c'est la propriété que `raiyon/eval/client.py` achète, et
un test d'isolation la vérifie sur le disque. Il a en revanche besoin de la base et du
seed, et c'est **assumé** (arbitrage A) : les `tool_result` ne sont pas enregistrés, ils
sont recalculés par le vrai moteur. Un scoring cassé se voit donc au rejeu suivant, sans
rien réenregistrer.

⚠️ **`live` n'enregistre rien.** Ces conversations ne sont pas reproductibles par
construction — les deux côtés sont non déterministes. Elles servent à *lire* un dialogue
que dix scénarios scriptés ne produisent pas, pas à mesurer.
"""

import argparse
import datetime as dt
import sys
from collections.abc import Iterator
from pathlib import Path

import structlog
from sqlalchemy.orm import Session

from raiyon.agent.client import ClientLLM
from raiyon.agent.prompts import SYSTEME_V1, prompt_systeme
from raiyon.agent.session import creer_session
from raiyon.config import ConfigurationError, get_settings
from raiyon.db.engine import get_sessionmaker
from raiyon.eval.cassette import (
    COMMANDE_DE_REGENERATION,
    Cassette,
    EnTete,
    depuis_json,
    empreinte_des_outils,
    en_json,
)
from raiyon.eval.client import ClientCassette, ClientEnregistreur, verifier
from raiyon.eval.client_simule import (
    PERSONAS,
    ClientSimule,
    a_termine,
    sans_le_mot_de_fin,
)
from raiyon.eval.executeur import Reglages, jouer, jouer_un_tour, prose_livree
from raiyon.eval.metriques import MesuresDunePrise, agreger, mesurer
from raiyon.eval.rapport import rendre
from raiyon.eval.scenario import SCENARIOS, Scenario, ScenarioInconnu, par_nom
from raiyon.matching.depot import DepotSql
from raiyon.tools.schema_outils import schema_des_outils

logueur = structlog.get_logger(__name__)

RACINE = Path(__file__).resolve().parents[1]
CASSETTES = RACINE / "evals" / "cassettes"
RAPPORT = RACINE / "docs" / "eval" / "rapport.md"

MAX_TOURS_LIVE = 8
"""Un client simulé qui ne dit jamais `FIN` coûterait des jetons jusqu'à l'ennui."""


class CassetteAbsente(Exception):
    """Le fichier n'existe pas. Le message dit la commande qui le crée."""


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    sous = analyseur.add_subparsers(dest="mode", required=True)

    rejouer = sous.add_parser("rejouer", help="rejoue les cassettes, écrit le rapport (aucune clé)")
    rejouer.add_argument(
        "--scenario",
        default=None,
        help=(
            "n'en rejouer qu'un, par son nom. Le rapport est alors affiché mais **non "
            "écrit** : un docs/eval/rapport.md partiel serait un faux."
        ),
    )

    enregistrer = sous.add_parser("enregistrer", help="(ré)enregistre les cassettes — clé requise")
    enregistrer.add_argument("--scenario", default=None, help="n'en refaire qu'un, par son nom")

    live = sous.add_parser("live", help="conversations avec le client simulé — rien n'est écrit")
    live.add_argument("--personas", nargs="*", default=None, help="par leur nom ; tous par défaut")

    arguments = analyseur.parse_args()
    try:
        if arguments.mode == "rejouer":
            return _rejouer(arguments.scenario)
        if arguments.mode == "enregistrer":
            return _enregistrer(arguments.scenario)
        return _live(arguments.personas)
    except (ConfigurationError, ScenarioInconnu, CassetteAbsente) as erreur:
        print(f"\n⛔ {erreur}\n", file=sys.stderr)
        return 1


# --------------------------------------------------------------------------- #
# Le socle commun : prompt, outils, empreintes, réglages
# --------------------------------------------------------------------------- #


def _reglages() -> tuple[Reglages, str, str]:
    """Les réglages de la boucle, l'empreinte du prompt et celle du schéma d'outils.

    Les deux empreintes sont calculées **ici et une seule fois** : les recalculer par
    cassette ferait dépendre le contrôle de l'arbitrage C du fait que personne n'édite
    `prompts/` pendant l'exécution.
    """
    systeme, empreinte_prompt = prompt_systeme()
    outils = schema_des_outils()
    reglage = get_settings()
    return (
        Reglages(
            systeme=systeme,
            outils=outils,
            max_iterations=reglage.max_agent_iterations,
            max_regenerations=reglage.max_regenerations,
        ),
        empreinte_prompt,
        empreinte_des_outils(outils),
    )


def _prises(scenarios: tuple[Scenario, ...]) -> Iterator[tuple[Scenario, int]]:
    for scenario in scenarios:
        for prise in range(1, scenario.prises + 1):
            yield scenario, prise


def _chemin(scenario: Scenario, prise: int) -> Path:
    return CASSETTES / scenario.fichier(prise)


# --------------------------------------------------------------------------- #
# `make eval` — rejeu, rapport, code de sortie
# --------------------------------------------------------------------------- #


def _rejouer(nom: str | None = None) -> int:
    """Rejoue les seize prises, écrit le rapport, et **sort en non nul si un critère
    bloquant est violé**.

    Le code de sortie est la porte de sortie de l'étape : un rapport qu'il faudrait lire
    pour savoir s'il est vert n'est pas une porte, c'est un document.
    """
    scenarios = SCENARIOS if nom is None else (par_nom(nom),)
    reglages, empreinte_prompt, empreinte_outils = _reglages()
    fabrique = get_sessionmaker()
    mesures: list[MesuresDunePrise] = []

    for scenario, prise in _prises(scenarios):
        chemin = _chemin(scenario, prise)
        if not chemin.is_file():
            raise CassetteAbsente(
                f"{chemin.relative_to(RACINE)} est absente.\nEnregistrer :\n    "
                + COMMANDE_DE_REGENERATION.format(scenario=scenario.nom)
            )
        cassette = depuis_json(chemin.read_text(encoding="utf-8"))
        verifier(cassette, prompt_empreinte=empreinte_prompt, outils_empreinte=empreinte_outils)
        client = ClientCassette(cassette, source=str(chemin.relative_to(RACINE)))

        with fabrique() as base:
            jouee = jouer(
                base,
                scenario,
                prise,
                client=client,
                depot=DepotSql(base),
                reglages=reglages,
            )
        if not client.epuisee:
            # Le rejeu a consommé moins de prises qu'enregistré : la conversation s'est
            # arrêtée plus tôt qu'à l'enregistrement, sans qu'aucune empreinte n'ait
            # divergé. Un signal, pas une erreur — mais il ne doit pas passer inaperçu.
            print(
                f"  ⚠️  {scenario.nom}.{prise} : {client.index} prise(s) consommée(s) sur "
                f"{len(cassette.prises)} — la conversation rejouée est plus courte."
            )
        mesures.append(mesurer(jouee))
        print(f"  · {scenario.nom}.{prise}")

    agregat = agreger(mesures)
    texte = rendre(agregat)
    if nom is None:
        RAPPORT.parent.mkdir(parents=True, exist_ok=True)
        RAPPORT.write_text(texte, encoding="utf-8")
        print(f"\n→ {RAPPORT.relative_to(RACINE)}\n")
    else:
        print(f"\n(rapport partiel — {RAPPORT.relative_to(RACINE)} n'est pas réécrit)\n")
    print(texte)

    if agregat.bloquants_tenus:
        return 0
    print(
        "\n⛔ Un critère bloquant est violé — voir les lignes ❌ ci-dessus.",
        file=sys.stderr,
    )
    return 1


# --------------------------------------------------------------------------- #
# `make eval-enregistrer` — la seule commande qui consomme des jetons pour mesurer
# --------------------------------------------------------------------------- #


def _enregistrer(nom: str | None) -> int:
    """Enregistre ou réenregistre les cassettes. **Consomme la clé et des jetons.**

    L'import du SDK vit ici et pas dans `raiyon.eval` : c'est ce qui permet au harnais de
    rester importable sans clé, et au rejeu de tourner en CI.
    """
    from raiyon.agent.client_anthropic import ClientAnthropic

    scenarios = SCENARIOS if nom is None else (par_nom(nom),)
    reglages, empreinte_prompt, empreinte_outils = _reglages()
    reel = ClientAnthropic()
    fabrique = get_sessionmaker()
    date = dt.date.today().isoformat()
    CASSETTES.mkdir(parents=True, exist_ok=True)

    for scenario, prise in _prises(scenarios):
        enregistreur = ClientEnregistreur(reel)
        with fabrique() as base:
            jouer(
                base,
                scenario,
                prise,
                client=enregistreur,
                depot=DepotSql(base),
                reglages=reglages,
            )
        cassette = enregistreur.en_cassette(
            EnTete(
                scenario=scenario.nom,
                prise=prise,
                modele=get_settings().model_agent,
                prompt_version=SYSTEME_V1,
                prompt_empreinte=empreinte_prompt,
                outils_empreinte=empreinte_outils,
                enregistree_le=date,
            )
        )
        chemin = _chemin(scenario, prise)
        chemin.write_text(en_json(cassette), encoding="utf-8")
        print(
            f"  · {chemin.relative_to(RACINE)} — {len(cassette.prises)} prise(s), "
            f"{chemin.stat().st_size} octets"
        )
    return 0


def relire(scenario: Scenario, prise: int) -> Cassette:
    """Une cassette du dépôt, par son scénario. Sert aux tests d'intégration du harnais."""
    chemin = _chemin(scenario, prise)
    if not chemin.is_file():
        raise CassetteAbsente(f"{chemin} est absente.")
    return depuis_json(chemin.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# `make eval-live` — le client simulé, hors CI, et rien n'est enregistré
# --------------------------------------------------------------------------- #


def _live(noms: list[str] | None) -> int:
    """Deux ou trois conversations avec le client joué par Haiku. **Rien n'est écrit.**

    Le client ne voit que la prose livrée et les produits (arbitrage H) : sans cette
    cloison il devient un oracle, et la mesure serait flatteuse et fausse.
    """
    from raiyon.agent.client_anthropic import ClientAnthropic

    personas = (
        PERSONAS if not noms else tuple(persona for persona in PERSONAS if persona.nom in set(noms))
    )
    if not personas:
        print(
            "Aucun persona ne correspond. Disponibles : "
            + ", ".join(persona.nom for persona in PERSONAS),
            file=sys.stderr,
        )
        return 1

    reglages, _, _ = _reglages()
    reel = ClientAnthropic()
    fabrique = get_sessionmaker()

    for persona in personas:
        print(f"\n{'=' * 78}\n=== {persona.nom} — {persona.description[:60]}…\n{'=' * 78}")
        simule = ClientSimule(persona)
        with fabrique() as base:
            _conversation(base, persona.ouverture, simule, reel, reglages)
    print(
        "\n⚠️  Rien n'a été enregistré : ces conversations ne sont pas reproductibles "
        "par construction.\n"
    )
    return 0


def _conversation(
    base: Session,
    ouverture: str,
    simule: ClientSimule,
    reel: ClientLLM,
    reglages: Reglages,
) -> None:
    """Un dialogue complet, jusqu'à `FIN` ou `MAX_TOURS_LIVE`.

    Le scénario est fabriqué à la volée, un tour à la fois : contrairement aux dix
    scénarios déterministes, le message suivant **dépend** de ce que l'assistant a
    répondu. C'est exactement ce que l'arbitrage G interdit aux scénarios scriptés, et
    c'est la raison d'être de ce mode.
    """
    conversation = creer_session(base)
    base.commit()
    depot = DepotSql(base)
    message = ouverture
    print(f"\n\033[1mclient  >\033[0m {message}")

    for numero in range(1, MAX_TOURS_LIVE + 1):
        evenements, issue = jouer_un_tour(
            base, conversation, message, client=reel, depot=depot, reglages=reglages
        )
        for ligne in prose_livree(evenements):
            print(f"\033[36mvendeur >\033[0m {ligne}")
        print(f"\033[90m          ({issue.iterations} itération(s))\033[0m")

        reponse = simule.repondre_a(evenements)
        if a_termine(reponse):
            reste = sans_le_mot_de_fin(reponse)
            if reste:
                print(f"\n\033[1mclient  >\033[0m {reste}")
            print(f"\033[90m          (le client a mis fin au tour {numero})\033[0m")
            return
        message = sans_le_mot_de_fin(reponse) or reponse
        print(f"\n\033[1mclient  >\033[0m {message}")

    print(f"\033[90m          (arrêt à {MAX_TOURS_LIVE} tours — le client n'a pas dit FIN)\033[0m")


if __name__ == "__main__":
    raise SystemExit(main())
