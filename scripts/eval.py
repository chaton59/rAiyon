"""Le harnais d'éval en ligne de commande — `make eval`, `eval-enregistrer`, `eval-live`.

Trois modes, trois besoins différents, et c'est **ce qu'ils exigent** qui les sépare :

| Mode | Base | Clé API | Écrit |
|---|---|---|---|
| `rejouer` | oui | **non** | `docs/eval/rapport.<jeu>.md`, et le code de sortie |
| `enregistrer` | oui | oui | `evals/cassettes/systeme.<jeu>/*.json` |
| `live` | oui | oui | rien |

### Un **jeu** par version de prompt (étape 13, jalon 0, point B)

Trois prompts coexistent, et comparer deux versions suppose de garder les deux jeux de
cassettes — pas seulement les deux rapports. Un jeu porte un nom court (`v1`, `v2`, `v3`,
`v1-etape12`), ses cassettes vivent sous `evals/cassettes/systeme.<nom>/` et son rapport
s'écrit dans `docs/eval/rapport.<nom>.md`.

*Alternative écartée — n'écraser et ne garder que les rapports.* Moins cher. Écartée parce
qu'elle fait décrire par §7 et par le correctif de l'étape 12 un **tirage qui n'existerait
plus nulle part**, et parce qu'un changement de moteur ultérieur ne se rejouerait plus
contre v1 : la comparaison cesserait d'être reproductible, ce qui est précisément la
propriété que l'arbitrage A achète en ne figeant pas les `tool_result`.

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
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import structlog
from sqlalchemy.orm import Session

from raiyon.agent.client import USAGE_NUL, ClientLLM
from raiyon.agent.prompts import (
    PREFIXE_SYSTEME,
    SystemeEnVigueur,
    charger,
    empreinte,
    prompt_systeme,
)
from raiyon.agent.session import creer_session
from raiyon.config import ConfigurationError, get_settings
from raiyon.db.engine import get_sessionmaker
from raiyon.eval import comparaison
from raiyon.eval.cassette import (
    COMMANDE_DE_REGENERATION,
    Cassette,
    DivergenceDeRequete,
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
from raiyon.eval.executeur import Reglages, jouer, jouer_un_tour
from raiyon.eval.metriques import Mesures, MesuresDunePrise, agreger, mesurer, prose_livree
from raiyon.eval.rapport import rendre
from raiyon.eval.scenario import SCENARIOS, Scenario, ScenarioInconnu, par_nom
from raiyon.matching.depot import DepotSql
from raiyon.tools.schema_outils import schema_des_outils

logueur = structlog.get_logger(__name__)

RACINE = Path(__file__).resolve().parents[1]
CASSETTES = RACINE / "evals" / "cassettes"
RAPPORTS = RACINE / "docs" / "eval"

DIVERGENCES_ATTENDUES: dict[tuple[str, str, int], str] = {
    ("v1-etape12", "desserrage_refuse", 1): (
        "le correctif de validateur de l'étape 13 (jalon 1, point D) fait tomber 2 des 4 "
        "griefs de ce tour. La reprise empilée avant la régénération porte donc 2 lignes "
        "au lieu de 4, l'empreinte de requête du tour régénéré change, et la prise 7 n'est "
        "plus reconstituable. Le modèle aurait reçu une autre reprise : sa réponse "
        "enregistrée n'est pas celle qu'il aurait donnée."
    ),
}
"""Les cassettes dont on **sait** qu'elles divergent, et pourquoi. **Une assertion, pas un skip.**

⚠️ **Une tolérance à la divergence serait le début du mode d'échec que l'arbitrage B
ferme.** Le jour d'une vraie régression du moteur, elle serait écartée et mentionnée dans
une ligne que personne ne lit — c'est-à-dire qu'on produirait des chiffres au lieu d'une
erreur, exactement ce que le contrôle d'empreinte existe pour empêcher.

Cette liste ne tolère rien : elle **affirme**. Trois choses la font échouer, et la
deuxième est celle qui compte :

1. une divergence **non listée** — le contrôle d'empreinte se comporte comme avant ;
2. une cassette listée qui **cesse** de diverger — le correctif a été annulé sans que
   personne ne retire la ligne, et la liste décrirait un monde qui n'existe plus ;
3. une ligne qui nomme une cassette **absente** — la liste pointe dans le vide.

⚠️ **Elle est tenue à la main, et c'est un choix.** *Alternative écartée — une empreinte
de validateur dans l'en-tête de cassette*, qui rendrait la péremption automatique comme
pour le prompt et le schéma d'outils. Écartée parce qu'il faudrait hacher du **code
source** : un commentaire reformulé périmerait les quarante cassettes du dépôt, et une
péremption qui se déclenche pour rien est une péremption qu'on finit par contourner.
Voir la ligne de §7 sur la quatrième chose qui périme une cassette."""

PREDICTIONS: dict[str, str] = {
    "v2": (
        "**Prédiction posée avant la campagne v2, sur la section 14 (le markdown).**\n"
        "`SEPARATEURS_DE_PHRASE` traite le saut de ligne comme une fin de phrase. Les "
        "listes que\nv2 interdit produisaient un produit et son prix **par ligne**, donc "
        "une phrase étroite par\nproduit — exactement le contexte dans lequel la règle 2 "
        "attribue un montant à un produit.\nBasculer vers de la prose continue donnerait "
        "des phrases nommant trois produits et portant\ntrois prix : l'attribution se "
        "dégraderait, et les faux positifs deviendraient plus probables.\n"
        "La cible 3 aurait alors une empreinte sur le taux de rejet, et son effet serait "
        "inséparable\nde celui de la cible 1.\n"
        "**Parade appliquée dans v2** : « une ligne par produit » est l'instruction, la "
        "prose continue\nest retirée. Le saut de ligne reste, la règle 2 garde son "
        "contexte étroit.\n"
        "**Si le taux de rejet bouge malgré cela, c'est de ce côté qu'il faut regarder "
        "d'abord** — et\nl'appendice A dira si les phrases refusées se sont élargies."
    ),
}
"""Ce qu'on **attend** d'une campagne, écrit avant de la lancer. Publié dans son rapport.

⚠️ **Une prédiction posée d'avance vaut infiniment mieux qu'une explication trouvée
après.** Sans elle, une métrique qui bouge se raconte : on cherche une cause, on en
trouve une, et rien ne distingue l'explication juste de celle qui arrange. Une hypothèse
datée, elle, se confirme ou s'infirme.

Le dépôt a déjà payé ce défaut : le correctif de l'étape 12 a montré qu'un diagnostic
plausible sur le taux de repli — « les scénarios ne posent pas de questions de domaine » —
était **faux**, et que la vraie cause était ailleurs. Il avait été formulé après coup.

La clé est le **nom du jeu** : la prédiction accompagne la campagne qu'elle vise, et elle
apparaît dans son rapport, pas dans un fichier annexe qu'on ne rouvre pas."""

JEU_ETAPE_12 = "v1-etape12"
"""Le jeu archivé : les dix-neuf cassettes de l'étape 12, **intactes**.

Il est nommé ici parce que c'est le seul jeu dont le nom ne se déduit pas d'une version en
vigueur. `systeme.v1.md` ne changeant pas, il reste rejouable : le tirage que §7 et le
correctif de l'étape 12 citent reste **reconstituable**, et pas seulement lisible."""


@dataclass(frozen=True, slots=True)
class Jeu:
    """Où vivent les cassettes d'une campagne, et où va son rapport.

    Le nom est court (`v1`, `v2`, `v3`, `v1-etape12`) et la version de prompt est celle
    **en vigueur** : les deux ne coïncident pas toujours, et `v1-etape12` est exactement
    ce cas — un jeu enregistré contre `systeme.v1`, rangé à part parce qu'il date d'une
    autre campagne. C'est pourquoi le nom du répertoire n'est pas dérivé de l'en-tête des
    cassettes : c'est un **rangement**, pas une empreinte, et l'empreinte reste le seul
    contrôle de péremption.
    """

    nom: str
    version: str
    sources: tuple[str, ...] = ()
    """Les jeux qui composent celui-ci, **par ordre de priorité**. Vide = lui-même.

    ### Un scénario vient d'**une seule** source, la première qui le porte

    C'est la règle, et elle n'est pas arbitraire : composer prise à prise mélangerait la
    prise 1 d'une date avec les prises 2 et 3 d'une autre **à l'intérieur d'un même
    scénario**, et la dispersion mesurée sur ces trois prises confondrait le tirage et
    l'écart entre deux dates. Un scénario entier vient donc d'un seul enregistrement.

    ### Pourquoi une composition existe

    La ligne de base du jalon 2 et l'archive de l'étape 12 sont **deux objets
    différents**, et les confondre rendait le choix binaire. L'archive existe pour que §7
    cite un tirage qui existe : elle est **gelée**, jamais réenregistrée. La ligne de base
    existe pour comparer v2 : rien ne l'oblige à être exactement l'archive.

    Concrètement, aucun jeu unique ne fait une bonne base. L'archive a les onze scénarios
    mais `desserrage_refuse` n'y est plus rejouable (voir `DIVERGENCES_ATTENDUES`), et ce
    scénario porte **4 des 11 griefs** — le perdre biaiserait la base vers ses tours
    calmes. `v1-partielle` a des prises fraîches mais seulement sept scénarios, dont pas
    `question_de_domaine`, qui est la cible entière du périmètre de domaine.

    ⚠️ **Une base composée se déclare telle**, avec ses dates et le scénario concerné —
    c'est ce que `rapport.py` et `comparaison.py` publient. Une base hybride tue n'est pas
    une base, c'est un chiffre dont personne ne connaît la provenance."""

    @property
    def composants(self) -> tuple[str, ...]:
        """Les répertoires à lire, dans l'ordre. Un jeu simple ne lit que le sien."""
        return self.sources or (self.nom,)

    @property
    def compose(self) -> bool:
        return len(self.composants) > 1

    @property
    def cassettes(self) -> Path:
        """Le répertoire d'un jeu **simple**. Un jeu composé n'en a pas un seul."""
        return CASSETTES / f"{PREFIXE_SYSTEME}{self.composants[0]}"

    @property
    def rapport(self) -> Path:
        return RAPPORTS / f"rapport.{self.nom}.md"

    def repertoire(self, source: str) -> Path:
        return CASSETTES / f"{PREFIXE_SYSTEME}{source}"

    def source_du_scenario(self, scenario: str) -> str | None:
        """La première source qui porte ce scénario, ou `None` si aucune ne le porte."""
        for source in self.composants:
            if any(self.repertoire(source).glob(f"{scenario}.*.json")):
                return source
        return None

    def chemin(self, scenario: str, prise: int) -> Path:
        """Le fichier d'une prise, cherché dans les sources **par ordre de priorité**."""
        source = self.source_du_scenario(scenario)
        base = self.repertoire(source if source is not None else self.composants[0])
        return base / f"{scenario}.{prise}.json"


LIGNE_DE_BASE = Jeu(
    nom="v1-base",
    version="systeme.v1",
    sources=("v1-desserrage", "v1-partielle", "v1-etape12"),
)
"""La base contre laquelle v2 se compare. **Composée, et elle le dit.**

Trois sources, par priorité décroissante de fraîcheur :

* `v1-desserrage` — les trois prises de `desserrage_refuse` réenregistrées sous
  `systeme.v1` avec la campagne v2. Elles ne réparent pas l'archive et ne remplacent pas
  son tirage : elles rendent à la base le scénario qui porte **4 des 11 griefs** et que
  l'archive ne sait plus rejouer ;
* `v1-partielle` — les vingt et une prises payées de la campagne v1 interrompue, sept
  scénarios à trois prises ;
* `v1-etape12` — l'archive gelée, pour les scénarios que les deux autres ne portent pas,
  dont `question_de_domaine`.

⚠️ **Deux dates, et la réserve de dérive déjà publiée devient explicite** pour les
scénarios qui viennent de l'archive. Le rapport et la comparaison nomment, scénario par
scénario, d'où il vient."""


JEUX_DECLARES: dict[str, Jeu] = {LIGNE_DE_BASE.nom: LIGNE_DE_BASE}
"""Les jeux qui ne se déduisent pas de leur nom. **Un seul aujourd'hui**, et c'est bien.

Un jeu ordinaire est un répertoire ; son nom suffit à le trouver. Un jeu **composé** n'a
pas de répertoire, et rien dans son nom ne dit de quoi il est fait — il doit donc être
écrit quelque part, une seule fois, avec sa raison."""


def jeu_en_vigueur(nom: str | None, version: str) -> Jeu:
    """Le jeu visé. Par défaut, celui de la version de prompt en vigueur.

    `systeme.v2` → le jeu `v2`. Nommer un jeu explicitement sert à rejouer une campagne
    archivée sans changer de prompt — `--jeu v1-etape12` avec `systeme.v1` en vigueur.

    ⚠️ **Elle consulte `JEUX_DECLARES` comme `_jeu_nomme`, et il a fallu deux passages
    pour le faire aux deux endroits.** Un jeu composé n'a pas de répertoire : le construire
    depuis son nom donnait `evals/cassettes/systeme.v1-base/` et un « aucune cassette » qui
    désigne un chemin n'ayant jamais dû exister. Le défaut avait été corrigé sur le chemin
    de `comparer` et laissé sur celui de `rejouer` — deux portes vers la même donnée, une
    seule refermée, ce qui est le mode d'échec ordinaire de ce genre de résolution.
    """
    if nom is not None and (declare := JEUX_DECLARES.get(nom)) is not None:
        return declare
    return Jeu(nom=nom or version.removeprefix(PREFIXE_SYSTEME), version=version)


MAX_TOURS_LIVE = 8
"""Un client simulé qui ne dit jamais `FIN` coûterait des jetons jusqu'à l'ennui."""


class CassetteAbsente(Exception):
    """Le fichier n'existe pas. Le message dit la commande qui le crée."""


class DivergenceAttendueAbsente(Exception):
    """`DIVERGENCES_ATTENDUES` décrit une divergence qui n'a pas eu lieu, ou une cassette
    qui n'existe pas. **La liste affirme ; une liste qui n'affirme plus rien est morte.**"""


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    sous = analyseur.add_subparsers(dest="mode", required=True)

    rejouer = sous.add_parser("rejouer", help="rejoue les cassettes, écrit le rapport (aucune clé)")
    rejouer.add_argument(
        "--scenario",
        default=None,
        help=(
            "n'en rejouer qu'un, par son nom. Le rapport est alors affiché mais **non "
            "écrit** : un rapport partiel serait un faux."
        ),
    )
    rejouer.add_argument(
        "--jeu",
        default=None,
        help=(
            "le jeu de cassettes à rejouer. Par défaut celui de la version de prompt en "
            f"vigueur ; `--jeu {JEU_ETAPE_12}` rejoue la campagne archivée de l'étape 12."
        ),
    )

    enregistrer = sous.add_parser("enregistrer", help="(ré)enregistre les cassettes — clé requise")
    enregistrer.add_argument("--scenario", default=None, help="n'en refaire qu'un, par son nom")
    enregistrer.add_argument(
        "--jeu",
        default=None,
        help=(
            "où écrire les cassettes. Par défaut le jeu de la version en vigueur ; le "
            "nommer sert à enregistrer un complément sans toucher au jeu principal — "
            "`--jeu v1-desserrage` sous `systeme.v1`, par exemple."
        ),
    )

    comparer = sous.add_parser("comparer", help="deux jeux côte à côte, avec la dispersion")
    comparer.add_argument("avant", help="le jeu de référence — c'est lui qui donne la dispersion")
    comparer.add_argument("apres", help="le jeu comparé")
    comparer.add_argument(
        "--question",
        required=True,
        help="ce que cette comparaison cherche à savoir — écrit dans le fichier produit",
    )

    live = sous.add_parser("live", help="conversations avec le client simulé — rien n'est écrit")
    live.add_argument("--personas", nargs="*", default=None, help="par leur nom ; tous par défaut")

    arguments = analyseur.parse_args()
    try:
        if arguments.mode == "rejouer":
            return _rejouer(arguments.scenario, arguments.jeu)
        if arguments.mode == "enregistrer":
            return _enregistrer(arguments.scenario, arguments.jeu)
        if arguments.mode == "comparer":
            return _comparer(arguments.avant, arguments.apres, arguments.question)
        return _live(arguments.personas)
    except (
        ConfigurationError,
        ScenarioInconnu,
        CassetteAbsente,
        DivergenceAttendueAbsente,
    ) as erreur:
        print(f"\n⛔ {erreur}\n", file=sys.stderr)
        return 1


# --------------------------------------------------------------------------- #
# Le socle commun : prompt, outils, empreintes, réglages
# --------------------------------------------------------------------------- #


def _reglages() -> tuple[Reglages, SystemeEnVigueur, str]:
    """Les réglages de la boucle pour le prompt **en vigueur**, son identité, les outils."""
    return _reglages_pour(prompt_systeme())


def _reglages_pour(prompt: SystemeEnVigueur) -> tuple[Reglages, SystemeEnVigueur, str]:
    """Les mêmes, pour une version **nommée** plutôt que pour celle en vigueur.

    C'est ce que `comparer` exige : deux campagnes se rejouent dans le **même processus**,
    contre deux prompts différents. Lire la version dans l'environnement à cet endroit
    obligerait à relancer un processus par jeu, donc à recomposer la comparaison à la main —
    et c'est justement le geste que l'étape 13 fait trois fois.

    Les empreintes sont calculées **ici et une seule fois par jeu** : les recalculer par
    cassette ferait dépendre le contrôle de l'arbitrage C du fait que personne n'édite
    `prompts/` pendant l'exécution.
    """
    outils = schema_des_outils()
    reglage = get_settings()
    return (
        Reglages(
            systeme=prompt.texte,
            outils=outils,
            max_iterations=reglage.max_agent_iterations,
            max_regenerations=reglage.max_regenerations,
        ),
        prompt,
        empreinte_des_outils(outils),
    )


def systeme_du_jeu(jeu: Jeu) -> SystemeEnVigueur:
    """Le prompt d'un jeu, chargé par son nom de version — **sans passer par l'environnement**."""
    texte = charger(jeu.version)
    return SystemeEnVigueur(version=jeu.version, texte=texte, empreinte=empreinte(texte))


def _prises(scenarios: tuple[Scenario, ...]) -> Iterator[tuple[Scenario, int]]:
    for scenario in scenarios:
        for prise in range(1, scenario.prises + 1):
            yield scenario, prise


# --------------------------------------------------------------------------- #
# `make eval` — rejeu, rapport, code de sortie
# --------------------------------------------------------------------------- #


def prises_du_jeu(jeu: Jeu, nom: str | None = None) -> list[tuple[Scenario, int]]:
    """Les prises que ce jeu porte **sur le disque**, triées, filtrées par scénario.

    ⚠️ **Découvertes, et non déduites de `SCENARIOS`**, et c'est une décision de l'étape 13
    plutôt qu'une facilité. Les campagnes n'ont pas toutes le même nombre de prises : celle
    de l'étape 12 en compte dix-neuf, celles de l'étape 13 trente-six. Déduire la liste des
    prises du code ferait réclamer trente-six cassettes au jeu archivé, et « conservé »
    cesserait de vouloir dire « rejouable ».

    Ce que le disque ne peut pas dire — *ce jeu est-il complet ?* — est vérifié ailleurs, à
    l'endroit qui le sait : un test compte les cassettes du jeu en vigueur contre
    `prises_attendues()`.
    """
    trouvees: list[tuple[Scenario, int]] = []
    vus: set[str] = set()
    for source in jeu.composants:
        for chemin in sorted(jeu.repertoire(source).glob("*.json")):
            scenario_nom, _, reste = chemin.stem.partition(".")
            if nom is not None and scenario_nom != nom:
                continue
            # Un scénario vient d'**une seule** source : la première qui le porte. Voir
            # `Jeu.sources` — mélanger deux dates dans les trois prises d'un scénario
            # ferait confondre le tirage et l'écart entre deux enregistrements.
            if jeu.source_du_scenario(scenario_nom) != source:
                continue
            if (cle := f"{scenario_nom}.{reste}") in vus:
                continue
            vus.add(cle)
            trouvees.append((par_nom(scenario_nom), int(reste)))
    return sorted(trouvees, key=lambda paire: (paire[0].nom, paire[1]))


def mesurer_le_jeu(
    jeu: Jeu,
    prises: Sequence[tuple[Scenario, int]],
    reglages: Reglages,
    prompt: SystemeEnVigueur,
    empreinte_outils: str,
) -> Mesures:
    """Rejoue les prises d'un jeu et rend l'agrégat. **Aucune écriture.**

    Extrait de `_rejouer` pour que `comparer` puisse en faire tourner deux dans le même
    processus : sans cela, la comparaison des trois jalons se recomposerait à la main, à
    partir de deux fichiers markdown, ce qui est exactement le genre de geste qu'une
    campagne à trente-six prises ne mérite pas.
    """
    print(f"jeu {jeu.nom} — prompt {prompt.version} ({prompt.empreinte}), {len(prises)} prise(s)")
    if jeu.compose:
        print("  composé : " + ", ".join(jeu.composants) + " (un scénario, une source)")
    fabrique = get_sessionmaker()
    mesures: list[MesuresDunePrise] = []
    divergences_vues: set[tuple[str, str, int]] = set()

    for scenario, prise in prises:
        chemin = jeu.chemin(scenario.nom, prise)
        cassette = depuis_json(chemin.read_text(encoding="utf-8"))
        source = str(chemin.relative_to(RACINE))
        verifier(
            cassette,
            prompt_version=prompt.version,
            prompt_empreinte=prompt.empreinte,
            outils_empreinte=empreinte_outils,
            source=source,
        )
        client = ClientCassette(cassette, source=source)

        cle = (jeu.source_du_scenario(scenario.nom) or jeu.nom, scenario.nom, prise)
        try:
            with fabrique() as base:
                jouee = jouer(
                    base,
                    scenario,
                    prise,
                    client=client,
                    depot=DepotSql(base),
                    reglages=reglages,
                )
        except DivergenceDeRequete:
            # ⚠️ **Une divergence non listée remonte**, exactement comme avant : c'est le
            # contrôle de l'arbitrage B, et il ne se relâche pas. Une divergence listée est
            # **attendue** — on la constate, on la compte, et on continue sans cette prise.
            if cle not in DIVERGENCES_ATTENDUES:
                raise
            divergences_vues.add(cle)
            print(f"  ⊘ {scenario.nom}.{prise} — divergence attendue, prise écartée")
            continue

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

    _verifier_les_divergences_attendues(jeu, prises, divergences_vues)
    return agreger(mesures)


def reserves_du_jeu(jeu: Jeu, prises: Sequence[tuple[Scenario, int]]) -> tuple[str, ...]:
    """Ce que le rapport de ce jeu doit dire de lui-même avant d'afficher un chiffre.

    Trois choses, et aucune ne se lit dans les tableaux : la **prédiction** posée avant la
    campagne, les prises **écartées** pour divergence attendue, et la **composition** d'un
    jeu qui vient de plusieurs enregistrements. Un rapport qui les tait affiche ses totaux
    avec l'autorité d'un rapport complet.
    """
    lignes: list[str] = []
    if prediction := PREDICTIONS.get(jeu.nom):
        lignes.append(prediction)
    ecartees = [
        (cle, raison)
        for cle, raison in sorted(DIVERGENCES_ATTENDUES.items())
        if cle[0] in jeu.composants
        and any(scenario.nom == cle[1] and prise == cle[2] for scenario, prise in prises)
    ]
    for (source, scenario, prise), raison in ecartees:
        lignes.append(
            f"**{source}/{scenario}.{prise} est écartée de ce rapport** — divergence "
            f"attendue au rejeu.\n{raison}\nLes tours et les griefs de cette prise ne "
            "sont donc comptés nulle part ci-dessous."
        )
    if jeu.compose:
        origines = {scenario.nom: jeu.source_du_scenario(scenario.nom) for scenario, _ in prises}
        par_source: dict[str, list[str]] = {}
        for nom_scenario, source in sorted(origines.items()):
            par_source.setdefault(source or jeu.nom, []).append(nom_scenario)
        lignes.append(
            "**Ce jeu est composé de plusieurs enregistrements**, donc de plusieurs "
            "dates. Un scénario vient\nd'une seule source — jamais de deux — pour que la "
            "dispersion de ses prises reste celle d'un\ntirage et non celle d'un écart "
            "entre deux enregistrements.\n"
            + "\n".join(
                f"`{source}` : " + ", ".join(f"`{nom}`" for nom in noms)
                for source, noms in sorted(par_source.items())
            )
        )
    return tuple(lignes)


def _verifier_les_divergences_attendues(
    jeu: Jeu,
    prises: Sequence[tuple[Scenario, int]],
    vues: set[tuple[str, str, int]],
) -> None:
    """La liste **affirme**, elle ne tolère pas. Deux façons de la prendre en défaut.

    Une divergence non listée a déjà remonté plus haut. Restent les deux qui font d'une
    liste d'exceptions une liste morte :

    * une cassette listée qui **cesse** de diverger — le correctif a été annulé, ou la
      cassette réenregistrée, et la liste décrit un monde qui n'existe plus. Sans ce
      contrôle, elle continuerait d'excuser une divergence qui n'a plus lieu, et le jour
      où une vraie divergence apparaîtrait au même endroit, elle serait excusée aussi ;
    * une ligne qui nomme une cassette **absente** du jeu — elle pointe dans le vide, et
      une ligne qui ne s'applique à rien est une ligne qu'on ne relit plus.
    """
    presentes = {
        (jeu.source_du_scenario(scenario.nom) or jeu.nom, scenario.nom, prise)
        for scenario, prise in prises
    }
    attendues = {cle for cle in DIVERGENCES_ATTENDUES if cle[0] in jeu.composants}

    fantomes = sorted(cle for cle in attendues if cle in presentes and cle not in vues)
    if fantomes:
        raise DivergenceAttendueAbsente(
            "ces cassettes sont listées comme divergentes et se rejouent pourtant sans "
            "divergence :\n"
            + "\n".join(f"  - {source}/{nom}.{prise}" for source, nom, prise in fantomes)
            + "\n\nLa liste décrit un monde qui n'existe plus. Retirer la ligne de "
            "DIVERGENCES_ATTENDUES\n(scripts/eval.py), ou comprendre pourquoi le "
            "correctif qui la justifiait a cessé d'agir."
        )

    orphelines = sorted(
        cle
        for cle in attendues
        if cle not in presentes and cle[0] in {jeu.source_du_scenario(n) for _, n, _ in attendues}
    )
    introuvables = sorted(cle for cle in attendues if not jeu.repertoire(cle[0]).is_dir())
    manquantes = sorted(set(orphelines) | set(introuvables))
    if manquantes:
        raise DivergenceAttendueAbsente(
            "ces cassettes sont listées comme divergentes et n'existent pas dans le jeu "
            f"{jeu.nom} :\n"
            + "\n".join(f"  - {source}/{nom}.{prise}" for source, nom, prise in manquantes)
            + "\n\nUne ligne qui ne s'applique à rien est une ligne qu'on ne relit plus."
        )


def _prises_manquantes(jeu: Jeu, prises: Sequence[tuple[Scenario, int]]) -> str:
    """Ce qui manque au jeu **en vigueur** pour être complet, ou une chaîne vide.

    ⚠️ **Un rapport écrit depuis un jeu incomplet est un faux**, et il ne s'annonce pas
    comme tel : le tableau a la même forme, les critères sont verts, et rien ne dit que
    quatre scénarios sur onze n'ont pas été joués. C'est un fichier committé, comparé à
    trois autres, et lu dans six mois.

    **Trouvé en le vivant**, à l'étape 13 : la campagne v1 s'est arrêtée à 21 prises sur
    36, l'API ayant refusé le vingt-deuxième appel. Rien dans le harnais ne l'aurait dit
    au rejeu suivant.

    Un jeu **archivé** en est exempt : `v1-etape12` porte dix-neuf prises parce que
    l'étape 12 en a enregistré dix-neuf, et il est complet pour ce qu'il est. Le contrôle
    ne porte donc que sur le jeu de la version en vigueur, dont `SCENARIOS` décrit
    exactement ce qu'il doit contenir.

    §5 étape 13, point 8 : si une campagne doit être réduite, ce qui se coupe est le
    **nombre de scénarios**, et cela **s'écrit**. Le silence n'est pas une option ; le
    rapport reste affiché à l'écran, il n'est simplement pas committé sous un nom qui
    prétendrait décrire la campagne entière.
    """
    if jeu.nom != jeu.version.removeprefix(PREFIXE_SYSTEME):
        return ""
    attendues = {
        (scenario.nom, prise) for scenario in SCENARIOS for prise in range(1, scenario.prises + 1)
    }
    manquantes = attendues - {(scenario.nom, prise) for scenario, prise in prises}
    if not manquantes:
        return ""
    par_scenario: dict[str, int] = {}
    for scenario_nom, _ in manquantes:
        par_scenario[scenario_nom] = par_scenario.get(scenario_nom, 0) + 1
    return (
        f"⛔ {jeu.rapport.relative_to(RACINE)} n'est **pas** écrit : le jeu {jeu.nom} est "
        f"incomplet.\n   {len(prises)} prise(s) sur {len(attendues)} — il manque "
        + ", ".join(f"{nom} x{compte}" for nom, compte in sorted(par_scenario.items()))
        + "\n\n   Un rapport écrit depuis un jeu incomplet a la même forme qu'un rapport "
        "complet et ne dit pas\n   ce qui manque. Le tableau ci-dessus est affiché, pas "
        "committé.\n\n   Compléter :\n       "
        + "\n       ".join(
            COMMANDE_DE_REGENERATION.format(version=jeu.version, scenario=nom)
            for nom in sorted(par_scenario)
        )
    )


def _rejouer(nom: str | None = None, jeu_nomme: str | None = None) -> int:
    """Rejoue les cassettes d'un jeu, écrit son rapport, et **sort en non nul si un critère
    bloquant est violé**.

    Le code de sortie est la porte de sortie de l'étape : un rapport qu'il faudrait lire
    pour savoir s'il est vert n'est pas une porte, c'est un document.
    """
    reglages, prompt, empreinte_outils = _reglages()
    jeu = jeu_en_vigueur(jeu_nomme, prompt.version)
    prises = prises_du_jeu(jeu, nom)
    if not prises:
        raise CassetteAbsente(
            f"aucune cassette dans {jeu.cassettes.relative_to(RACINE)}"
            + (f" pour le scénario {nom!r}" if nom else "")
            + ".\nEnregistrer :\n    "
            + COMMANDE_DE_REGENERATION.format(
                version=prompt.version, scenario=nom or "<nom du scénario>"
            )
        )

    agregat = mesurer_le_jeu(jeu, prises, reglages, prompt, empreinte_outils)
    texte = rendre(agregat, reserves=reserves_du_jeu(jeu, prises))
    if nom is not None:
        print(f"\n(rapport partiel — {jeu.rapport.relative_to(RACINE)} n'est pas réécrit)\n")
    elif partiel := _prises_manquantes(jeu, prises):
        print(f"\n{partiel}\n", file=sys.stderr)
    else:
        jeu.rapport.parent.mkdir(parents=True, exist_ok=True)
        jeu.rapport.write_text(texte, encoding="utf-8")
        print(f"\n→ {jeu.rapport.relative_to(RACINE)}\n")
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


def _enregistrer(nom: str | None, jeu_nomme: str | None = None) -> int:
    """Enregistre ou réenregistre les cassettes. **Consomme la clé et des jetons.**

    L'import du SDK vit ici et pas dans `raiyon.eval` : c'est ce qui permet au harnais de
    rester importable sans clé, et au rejeu de tourner en CI.
    """
    from raiyon.agent.client_anthropic import ClientAnthropic

    scenarios = SCENARIOS if nom is None else (par_nom(nom),)
    reglages, prompt, empreinte_outils = _reglages()
    jeu = jeu_en_vigueur(jeu_nomme, prompt.version)
    reel = ClientAnthropic()
    fabrique = get_sessionmaker()
    date = dt.date.today().isoformat()
    jeu.cassettes.mkdir(parents=True, exist_ok=True)
    print(
        f"jeu {jeu.nom} → {jeu.cassettes.relative_to(RACINE)} — "
        f"prompt {prompt.version} ({prompt.empreinte})"
    )

    total = USAGE_NUL
    attendues = sum(scenario.prises for scenario in scenarios)
    faites = 0

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
        total = total + enregistreur.usage
        faites += 1
        cassette = enregistreur.en_cassette(
            EnTete(
                scenario=scenario.nom,
                prise=prise,
                modele=get_settings().model_agent,
                prompt_version=prompt.version,
                prompt_empreinte=prompt.empreinte,
                outils_empreinte=empreinte_outils,
                enregistree_le=date,
            )
        )
        chemin = jeu.chemin(scenario.nom, prise)
        chemin.write_text(en_json(cassette), encoding="utf-8")
        # ⚠️ **Le cumul s'affiche à chaque prise, pas à la fin.** La campagne v1 de
        # l'étape 13 s'est arrêtée au milieu, crédits épuisés, et un récapitulatif de fin
        # n'aurait jamais été atteint. Ce qu'on veut savoir d'une campagne interrompue,
        # c'est ce qu'elle avait consommé **jusque-là**.
        print(
            f"  · [{faites}/{attendues}] {chemin.relative_to(RACINE)} — "
            f"{len(cassette.prises)} prise(s), {chemin.stat().st_size} octets\n"
            f"      cette prise : {enregistreur.usage.en_ligne()}\n"
            f"      cumul      : {total.en_ligne()}",
            flush=True,
        )
    print(f"\n{faites} prise(s) enregistrée(s) dans {jeu.cassettes.relative_to(RACINE)}")
    print(f"Consommation totale : {total.en_ligne()}\n")
    return 0


def relire(jeu: Jeu, scenario: Scenario, prise: int) -> Cassette:
    """Une cassette d'un jeu, par son scénario. Sert aux tests d'intégration du harnais."""
    chemin = jeu.chemin(scenario.nom, prise)
    if not chemin.is_file():
        raise CassetteAbsente(f"{chemin} est absente.")
    return depuis_json(chemin.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# `make eval-comparer` — deux jeux côte à côte, sans clé
# --------------------------------------------------------------------------- #


def _comparer(avant: str, apres: str, question: str) -> int:
    """Rejoue deux jeux **dans le même processus** et écrit leur comparaison.

    Le même processus, parce que la version de prompt de chaque jeu est chargée par son
    **nom** et non lue dans l'environnement (`systeme_du_jeu`). Deux processus rendraient
    deux markdown qu'il faudrait recomposer à la main, et l'étape 13 fait ce geste trois
    fois — v1-étape12/v1, v1/v2, v2/v3.

    ⚠️ **Aucune clé API.** C'est un rejeu, comme `make eval`.
    """
    jeux = [_jeu_nomme(avant), _jeu_nomme(apres)]
    agregats = []
    reserves: list[str] = []
    for jeu in jeux:
        prises = prises_du_jeu(jeu)
        reserves.extend(reserves_du_jeu(jeu, prises))
        if not prises:
            raise CassetteAbsente(
                f"aucune cassette dans {jeu.cassettes.relative_to(RACINE)} — "
                "la comparaison porterait sur rien."
            )
        prompt = systeme_du_jeu(jeu)
        reglages, _, empreinte_outils = _reglages_pour(prompt)
        agregats.append(mesurer_le_jeu(jeu, prises, reglages, prompt, empreinte_outils))

    # Chaque jeu est rejoué **en entier**, puis réduit à l'intersection. L'ordre compte :
    # la réserve d'échantillon se chiffre sur la référence complète — « les prises
    # écartées portaient N des M rejets » n'est calculable que si on a mesuré les M.
    couverture, reduit_avant, reduit_apres = comparaison.couvrir(agregats[0], agregats[1])
    if not couverture.scenarios:
        raise CassetteAbsente(
            f"{jeux[0].nom} et {jeux[1].nom} n'ont aucun scénario en commun : il n'y a "
            "rien à comparer."
        )

    texte = comparaison.rendre(
        reduit_avant,
        reduit_apres,
        nom_avant=jeux[0].nom,
        nom_apres=jeux[1].nom,
        question=question,
        couverture=couverture,
        reserves=tuple(reserves),
    )
    chemin = RAPPORTS / f"comparaison.{jeux[0].nom}-{jeux[1].nom}.md"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")
    print(f"\n→ {chemin.relative_to(RACINE)}\n")
    print(texte)
    return 0


def _jeu_nomme(nom: str) -> Jeu:
    """Un jeu par son nom court, **déclaré s'il l'est**, sinon simple.

    Un jeu composé n'a pas de répertoire à lui : le construire à la volée depuis son nom
    donnerait `evals/cassettes/systeme.v1-base/`, qui n'existe pas, et la comparaison
    échouerait sur « aucune cassette » en désignant un chemin qui n'a jamais dû exister.
    Les compositions sont donc **déclarées**, et `JEUX_DECLARES` est le seul endroit où
    elles le sont.

    Pour les autres, la version de prompt se déduit du nom — `v1-etape12` et
    `v1-partielle` tournent tous deux sous `systeme.v1`.
    """
    if (declare := JEUX_DECLARES.get(nom)) is not None:
        return declare
    return Jeu(nom=nom, version=f"{PREFIXE_SYSTEME}{nom.split('-')[0]}")


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
