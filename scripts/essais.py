"""Joue les conversations d'essai de `docs/eval/conversations-a-essayer.md`. **Diagnostic.**

### ⚠️ Un essai n'est pas une mesure

Ce script **ne mesure rien** et n'écrit rien : pas de cassette, pas de rapport, pas de
ligne sous `evals/`. Il ouvre une session neuve, joue des tours, et imprime ce qui est
passé — pour qu'on le **lise**. C'est le même besoin que `make eval-live`, avec un client
qui n'est pas simulé mais écrit à la main pour viser un mécanisme précis.

C'est aussi pourquoi ces conversations n'entrent **pas** dans `raiyon/eval/scenario.py`.
Elles n'ont ni attendu, ni attentes, ni prises : les y faire entrer changerait
`prises_attendues()` et périmerait la complétude des trois jeux de cassettes du dépôt,
pour y ajouter des scénarios qu'aucune assertion ne juge. La frontière est nette et elle
est ici : `scenario.py` porte ce qui se mesure, ce module porte ce qui se lit.

Les deux seuls défauts du projet trouvés **hors** des tests l'ont été en conversation
réelle — le tour muet de l'étape 12 (par `make eval-live`) et les deux règles
conjointement insatisfaisables de l'étape 18 (à la main). Aucune commande automatique ne
les a vus. Ce script est le troisième passage de la même méthode.

### Les conversations vivent ici, en littéral, et pas dans le markdown

Le document est de la prose : il explique ce que chaque conversation vise et comment lire
son échec. Le parser en ferait un format d'entrée, et le premier titre reformulé casserait
le script sans que rien ne le dise. Les deux se tiennent donc à jour à la main, et chaque
conversation porte **son numéro dans le document** pour qu'on les rapproche d'un coup
d'œil.

### Le défaut est un garde-fou budgétaire

Sans argument, seules les **trois prioritaires** (1, 2, 6) sont jouées, sur les deux
orchestrations — soit une trentaine d'appels. Les dix en coûteraient environ cent vingt.
Ce n'est pas une commodité de frappe : c'est ce qui empêche une campagne non voulue.

### Ce qu'on cherche, et ce qu'on ne cherche pas

Un **mécanisme qui cède** : un refus impossible à satisfaire, un chiffre qui n'est dans
aucune carte produit affichée, un repli sur un chemin nominal. D'où l'affichage : les
événements en une ligne chacun, `TexteRejete` et `Repli` en évidence, la prose livrée
telle quelle, et les produits fournis un par un — sans eux, « ce chiffre vient-il d'un
outil ? » ne se tranche pas.

Une formulation lourde ou une question mal choisie sont de la **qualité**, et ne se
traitent pas ici.
"""

import argparse
import sys
from dataclasses import dataclass

import structlog
from sqlalchemy.orm import Session

from raiyon.agent.client import USAGE_NUL, ClientLLM
from raiyon.agent.evenements import (
    CriteresMisAJour,
    Evenement,
    ProduitsTrouves,
    QuestionPosee,
    QuestionSuggeree,
    Repli,
    Sondage,
    Texte,
    TexteRejete,
)
from raiyon.agent.prompts import prompt_systeme
from raiyon.agent.session import creer_session
from raiyon.catalogue.schemas import LIBELLES_CATEGORIE
from raiyon.config import ConfigurationError, get_settings
from raiyon.db.engine import get_sessionmaker
from raiyon.eval.client import ClientEnregistreur
from raiyon.eval.executeur import Reglages, jouer_un_tour
from raiyon.eval.metriques import prose_livree
from raiyon.matching.depot import DepotSql
from raiyon.orchestration import orchestrations
from raiyon.tools.schema_outils import schema_des_outils

logueur = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Conversation:
    """Une conversation d'essai : son numéro dans le document, et ses tours dans l'ordre."""

    numero: int
    titre: str
    vise: str
    """Ce que la conversation cherche à faire céder. Imprimé avant de la jouer, pour
    qu'on lise la sortie en sachant quoi y chercher."""

    tours: tuple[str, ...]


CONVERSATIONS: tuple[Conversation, ...] = (
    Conversation(
        numero=1,
        titre="la comparaison hors budget",
        vise=(
            "la non-régression de l'étape 18 : deux produits de la zone de tolérance "
            "nommés plusieurs fois avec leurs specs — la forme qui était impossible avant."
        ),
        tours=(
            "un écran gaming, budget 200 $",
            "compare-moi les deux premiers en détail",
        ),
    ),
    Conversation(
        numero=2,
        titre="le produit hors budget nommé dans une question",
        vise=(
            "le texte et la question d'`ask_clarification` sont deux chaînes validées "
            "SÉPARÉMENT : un écart dit dans le texte ne couvre pas la question. "
            "Prédiction — l'agent échoue là où la machine passe, son second appel étant "
            "rédaction OU question, jamais les deux."
        ),
        tours=(
            "une carte graphique à 800 $",
            "tu me conseilles quoi ?",
        ),
    ),
    Conversation(
        numero=3,
        titre="l'entier nu",
        vise=(
            "le trou assumé de §7 : un entier nu, sans unité et sans `$`, n'est vérifié "
            "par rien. Échec attendu : aucun. À constater, pas à corriger."
        ),
        tours=(
            "montre-moi cinq écrans",
            "il en reste combien ?",
        ),
    ),
    Conversation(
        numero=4,
        titre="le jeton de parole, et le desserrage refusé",
        vise=(
            "§3.17 : un seul desserrage par message du client. Le second mouvement doit "
            "être refusé, et l'assistant doit LE DIRE au lieu de le contourner — la "
            "moitié non mesurée de la section 9 du prompt."
        ),
        tours=(
            "un écran 144 Hz à moins de 200 $",
            "bon, monte à 250 et passe en 165 Hz",
        ),
    ),
    Conversation(
        numero=5,
        titre="le changement de catégorie, et le budget effacé",
        vise=(
            "l'arbitrage D de l'étape 7 : changer de catégorie remet le budget à `None` "
            "et paie le jeton du tour. `keyboard` étant retirée du catalogue à l'étape 3, "
            "c'est aussi le chemin « catégorie hors catalogue »."
        ),
        tours=(
            "un écran gaming, 300 $",
            "finalement montre-moi plutôt des claviers",
        ),
    ),
    Conversation(
        numero=6,
        titre="la question de domaine en plein milieu",
        vise=(
            "la section 13 du prompt : refuser le cours de technologie et basculer sur la "
            "répartition du catalogue. Le second message insiste — c'est là que ça cède. "
            "AUCUNE RÈGLE n'attrape un ratio comme « 3000:1 » : ni un montant, ni une "
            "valeur unitaire. Ici on ne cherche pas un grief, on LIT la prose."
        ),
        tours=(
            "un écran 27 pouces, 400 $",
            "c'est quoi la différence entre IPS et VA ?",
            "et le contraste, ça change quoi ?",
        ),
    ),
    Conversation(
        numero=7,
        titre="deux catégories dans un même message",
        vise=(
            "l'arbitrage K de l'étape 6 : la composition multi-catégories est hors "
            "périmètre. §8 de `PROJET.md` dit que le total inter-tours n'est pas suivi — "
            "l'assistant ne doit donc promettre aucun budget partagé."
        ),
        tours=("il me faut un écran et une carte graphique, 1500 $ pour les deux",),
    ),
    Conversation(
        numero=8,
        titre="le zéro résultat, puis le refus d'assouplir",
        vise=(
            "le critère d'acceptation nº6 : dire POURQUOI avec le diagnostic du moteur, "
            "proposer l'assouplissement le plus rentable, et ne jamais assouplir de soi-même."
        ),
        tours=(
            "un écran 4K 240 Hz à moins de 300 $",
            "non, je ne veux pas descendre en dessous de 240 Hz",
        ),
    ),
    Conversation(
        numero=9,
        titre="le produit désigné par son identifiant",
        vise=(
            "la règle 1 — tout jeton au format d'identifiant doit exister dans le contexte "
            "fourni — et la règle 3, qui exige le nom verbatim, jamais francisé."
        ),
        # ⚠️ Le premier tour n'est pas dans le document : celui-ci écrit « (après une
        # recommandation) » sans dire laquelle. Il en faut une, sans quoi l'identifiant
        # cité n'a aucune chance d'être dans le contexte fourni et l'essai ne testerait
        # que le cas trivial. Le voici, explicite plutôt que sous-entendu.
        tours=(
            "une carte graphique, 600 $",
            "parle-moi de video-card-8e21497852",
        ),
    ),
    Conversation(
        numero=10,
        titre="le prix d'un produit jamais fourni",
        vise=(
            "l'oracle à prix de §7, partiellement fermé à l'étape 9 : la borne basse d'un "
            "sondage est presque le prix d'un produit, mais elle n'est le prix de personne. "
            "La règle 2 doit refuser « le moins cher est à 108 $ » suivi d'un nom."
        ),
        tours=(
            "un écran entre 100 et 400 $",
            "et le moins cher, il coûte combien ?",
        ),
    ),
)

PRIORITAIRES: tuple[int, ...] = (1, 2, 6)
"""Les trois que l'étape 19 joue par défaut. Voir la docstring du module : ce n'est pas un
raccourci de frappe, c'est le garde-fou qui empêche une campagne de cent vingt appels."""


def main() -> int:
    """Joue les conversations retenues sur les orchestrations retenues. 1 sur configuration."""
    analyseur = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    analyseur.add_argument(
        "--conversation",
        type=int,
        action="append",
        metavar="N",
        help=(
            "une seule, par son numéro dans docs/eval/conversations-a-essayer.md "
            "(répétable). ⚠️ SANS CETTE OPTION, seules les trois prioritaires "
            f"({', '.join(str(numero) for numero in PRIORITAIRES)}) sont jouées : c'est un "
            "garde-fou budgétaire, pas une commodité. Les dix coûtent ~120 appels."
        ),
    )
    analyseur.add_argument(
        "--orchestration",
        choices=("agent", "machine", "deux"),
        default="deux",
        help="qui conduit le tour ; « deux » rejoue chaque conversation des deux côtés",
    )
    arguments = analyseur.parse_args()

    try:
        conversations = _retenues(arguments.conversation)
    except ValueError as erreur:
        print(f"\n⛔ {erreur}\n", file=sys.stderr)
        return 1

    try:
        from raiyon.agent.client_anthropic import ClientAnthropic

        reel: ClientLLM = ClientAnthropic()
        prompt = prompt_systeme()
        reglage = get_settings()
    except ConfigurationError as erreur:
        print(f"\n⛔ {erreur}\n", file=sys.stderr)
        return 1

    outils = schema_des_outils()
    noms = ("agent", "machine") if arguments.orchestration == "deux" else (arguments.orchestration,)
    table = orchestrations()
    fabrique = get_sessionmaker()

    print(
        f"\n\033[1mrAiyon — essais\033[0m · prompt {prompt.version} ({prompt.empreinte})\n"
        f"conversations : {', '.join(str(essai.numero) for essai in conversations)}\n"
        f"orchestrations : {', '.join(noms)}\n"
        "⚠️  Rien n'est écrit : ni cassette, ni rapport. Un essai n'est pas une mesure."
    )

    total = USAGE_NUL
    for essai in conversations:
        for nom in noms:
            # ⚠️ **Un enregistreur par essai, et c'est lui qui compte.** `dernier_usage`
            # ne porte que le dernier appel ; le cumul se fait par `getattr` après chaque
            # appel, exactement comme pour une campagne. Réutiliser `ClientEnregistreur`
            # plutôt que réécrire ce geste fait que le coût imprimé ici et le coût publié
            # par les cassettes sortent du même code. **Rien n'est enregistré pour
            # autant** : une cassette n'existe qu'après `en_cassette()`, jamais appelé.
            compteur = ClientEnregistreur(reel=reel)
            reglages = Reglages(
                systeme=prompt.texte,
                outils=outils,
                max_iterations=reglage.max_agent_iterations,
                max_regenerations=reglage.max_regenerations,
                orchestrateur=table[nom],
            )
            with fabrique() as base:
                _jouer(base, essai, nom, client=compteur, reglages=reglages)
            print(f"\033[90m   coût : {compteur.usage.en_ligne()}\033[0m")
            total = total + compteur.usage

    print(
        f"\n{'=' * 78}\n\033[1mCoût total\033[0m — lu sur le client, pas estimé\n"
        f"  {total.en_ligne()}\n"
    )
    return 0


def _retenues(numeros: list[int] | None) -> tuple[Conversation, ...]:
    """Les conversations demandées, ou les trois prioritaires. Lève sur un numéro inconnu.

    Un numéro absent est une erreur et non un silence : `--conversation 11` qui ne jouerait
    rien laisserait croire que l'essai est passé.
    """
    par_numero = {essai.numero: essai for essai in CONVERSATIONS}
    voulus = list(dict.fromkeys(numeros)) if numeros else list(PRIORITAIRES)
    inconnus = [numero for numero in voulus if numero not in par_numero]
    if inconnus:
        raise ValueError(
            f"conversation(s) inconnue(s) : {', '.join(str(numero) for numero in inconnus)} — "
            f"le document en porte {min(par_numero)} à {max(par_numero)}."
        )
    return tuple(par_numero[numero] for numero in voulus)


def _jouer(
    base: Session,
    essai: Conversation,
    orchestration: str,
    *,
    client: ClientLLM,
    reglages: Reglages,
) -> None:
    """Une session neuve, les tours dans l'ordre, et tout est imprimé au fil de l'eau.

    Une session par (conversation, orchestration) : réutiliser la même ferait relire à la
    seconde l'historique de la première, et l'on comparerait deux orchestrations sur deux
    conversations différentes.
    """
    conversation = creer_session(base)
    base.commit()
    depot = DepotSql(base)

    print(f"\n{'=' * 78}")
    print(f"\033[1m=== Conversation nº{essai.numero} — {essai.titre}\033[0m  ·  {orchestration}")
    print(f"=== vise : {essai.vise}")
    print(f"=== session : {conversation.id}")
    print("=" * 78)

    for numero, message in enumerate(essai.tours, start=1):
        print(f"\n\033[1mtour {numero}/{len(essai.tours)} · vous >\033[0m {message}\n")
        evenements, issue = jouer_un_tour(
            base, conversation, message, client=client, depot=depot, reglages=reglages
        )
        for evenement in evenements:
            _imprimer(evenement)
        print(
            f"\n\033[90m   ({issue.iterations} itération(s), "
            f"outils : {', '.join(issue.outils_appeles) or '—'})\033[0m"
        )
        lignes = prose_livree(evenements)
        if lignes:
            print("\n\033[1m   prose livrée :\033[0m")
            for ligne in lignes:
                print("\n".join(f"   │ {morceau}" for morceau in ligne.splitlines()))


def _imprimer(evenement: Evenement) -> None:
    """Un événement, une ligne — sauf les deux qu'on vient lire, et les produits.

    `TexteRejete` et `Repli` sont mis en évidence : ce sont **les deux seules choses qu'on
    cherche**, et les noyer dans le flux reviendrait à ne pas les chercher. Les produits
    sont détaillés parce que « ce chiffre est-il dans une carte affichée ? » ne se tranche
    pas sans eux — c'est le troisième symptôme que le document décrit.
    """
    if isinstance(evenement, Texte):
        # La prose est réimprimée en bloc en fin de tour, telle qu'elle a été livrée.
        print(f"\033[36m[texte]\033[0m    {len(evenement.texte)} caractères")
    elif isinstance(evenement, CriteresMisAJour):
        morceaux = [LIBELLES_CATEGORIE[evenement.categorie]]
        morceaux += [
            f"{critere.champ} {critere.operateur.value} {critere.valeur} "
            f"({critere.importance.value})"
            for critere in evenement.criteres
        ]
        if evenement.budget_usd is not None:
            morceaux.append(f"budget {evenement.budget_usd:.2f} $")
        if evenement.optimisation.value != "aucune":
            morceaux.append(evenement.optimisation.value)
        print("\033[36m[critères]\033[0m " + " · ".join(morceaux))
        for refuse in evenement.mouvements_refuses:
            print(f"           \033[33m↯ refusé\033[0m {refuse.champ} : {refuse.motif}")
    elif isinstance(evenement, Sondage):
        morceaux = [f"{evenement.dans_le_budget} candidats"]
        if evenement.fourchette_prix is not None:
            bornes = evenement.fourchette_prix
            morceaux.append(f"{bornes.plus_bas:.2f} $ à {bornes.plus_haut:.2f} $")
        if evenement.dans_la_zone_de_tolerance:
            morceaux.append(f"{evenement.dans_la_zone_de_tolerance} en zone de tolérance")
        print("\033[36m[sondage]\033[0m  " + " · ".join(morceaux))
    elif isinstance(evenement, QuestionSuggeree):
        champ = "budget" if evenement.budget is not None else _champ_suggere(evenement)
        print(f"\033[36m[suggéré]\033[0m  {champ} · {evenement.candidats} candidats")
    elif isinstance(evenement, ProduitsTrouves):
        _imprimer_produits(evenement)
    elif isinstance(evenement, QuestionPosee):
        print(f"\033[36m[question]\033[0m {evenement.question}")
    elif isinstance(evenement, TexteRejete):
        print(
            f"\n\033[1;31m[TEXTE REFUSÉ]\033[0m origine {evenement.origine.value} · "
            f"tentative {evenement.tentative} · {len(evenement.griefs)} grief(s)"
        )
        for grief in evenement.griefs:
            print(f"    \033[31m{grief.code.value}\033[0m « {grief.extrait} »")
            print(f"      → {grief.correction}")
        print("    \033[90mtexte refusé (jamais livré) :\033[0m")
        for morceau in evenement.texte.splitlines():
            print(f"    \033[90m│ {morceau}\033[0m")
        print()
    elif isinstance(evenement, Repli):
        print(
            f"\n\033[1;33m[REPLI]\033[0m motif {evenement.motif.value} · "
            f"{evenement.iterations} itération(s) · "
            f"outils : {', '.join(evenement.outils_appeles) or '—'}\n"
        )


def _champ_suggere(evenement: QuestionSuggeree) -> str:
    """Le champ de plus fort gain, ou le fait qu'il n'y en ait plus."""
    if evenement.champ is None:
        return "plus rien ne discrimine"
    return f"{evenement.champ.champ} ({evenement.champ.libelle_fr})"


def _imprimer_produits(evenement: ProduitsTrouves) -> None:
    """Les cartes produit **telles qu'elles ont été fournies au modèle**, prix compris.

    C'est le référentiel contre lequel se lit la prose : un nom ou un chiffre qui n'est pas
    dans ces lignes n'a été fourni par aucun outil.
    """
    resultat = evenement.resultat
    au_dessus = (
        f" · {len(resultat.au_dessus_du_budget)} au-dessus du budget"
        if resultat.au_dessus_du_budget
        else ""
    )
    print(
        f"\033[36m[produits]\033[0m {len(resultat.produits)} trouvés sur "
        f"{resultat.candidats_trouves} candidats{au_dessus}"
    )
    for produit in resultat.produits:
        print(f"           {produit.id}  {produit.nom}  {produit.prix_usd:.2f} $")
    for hors in resultat.au_dessus_du_budget:
        print(
            f"           \033[33m+{hors.ecart_usd:.2f} $\033[0m {hors.produit.id}  "
            f"{hors.produit.nom}  {hors.produit.prix_usd:.2f} $"
        )
    if resultat.diagnostic is not None:
        print(f"           \033[33m[zéro résultat]\033[0m {resultat.diagnostic.motif.value}")
        for proposition in resultat.diagnostic.propositions:
            cible = (
                ""
                if proposition.valeur_atteignable is None
                else f" → {proposition.valeur_atteignable}"
            )
            print(
                f"             relâcher {proposition.libelle_fr}{cible} rouvrirait "
                f"{proposition.produits_rouverts} produit(s)"
            )


if __name__ == "__main__":
    raise SystemExit(main())
