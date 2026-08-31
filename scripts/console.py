"""Console de conversation — `make chat`. La porte de sortie de l'étape 8.

Lecture de stdin ligne à ligne, une session créée au démarrage, `Ctrl-D` pour sortir.
`--session` reprend une conversation existante : c'est la preuve que `depuis_jsonb()`
fait un aller-retour réel, et pas seulement que le code compile.

### Deux niveaux d'affichage, et le premier est le produit

Par défaut : le dialogue, **plus une ligne compacte par événement non textuel**.

```
[critères] écran · 144 Hz bloquant · budget 400 $
[sondage]  32 candidats · 180 à 395 $
[produits] 3 trouvés
```

C'est le panneau « voici ce que j'ai compris de ton besoin » de §3.12 en version
terminal, et c'est ce qui rend l'architecture visible : le client voit que le code a
compris, cherché et trouvé, indépendamment de ce que le modèle raconte.

`--trace` ajoute la trace d'explication produit par produit, les distributions du
sondage, et — en fin de tour — **les blocs bruts échangés avec le modèle** : arguments
d'appel et `tool_result` tels qu'ils sont persistés. C'est le mode dans lequel on lit un
défaut de conduite du dialogue, et le seul endroit où l'on voit ce que le modèle a
réellement reçu.

### La console consomme le générateur en entier, et ce n'est pas négociable

`session.tour()` n'écrit en base **qu'à la fin** : un abandon en cours d'itération ne
persisterait rien. La boucle d'affichage ne fait donc jamais de `break`.
"""

import argparse
import json
import sys
import uuid
from collections.abc import Generator, Iterator
from decimal import Decimal

import structlog

from raiyon.agent.boucle import IssueDuTour
from raiyon.agent.client_anthropic import ClientAnthropic
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
from raiyon.agent.session import SessionIntrouvable, creer_session, lire_session, tour
from raiyon.catalogue.schemas import LIBELLES_CATEGORIE, Categorie
from raiyon.config import ConfigurationError, get_settings
from raiyon.db.engine import get_sessionmaker
from raiyon.db.models import SessionConversation
from raiyon.matching.attributs import ATTRIBUTS
from raiyon.matching.criteres import Critere
from raiyon.matching.depot import DepotSql
from raiyon.tools.etat import valeur_en_texte
from raiyon.tools.schema_outils import schema_des_outils

logueur = structlog.get_logger(__name__)


def main() -> int:
    """Ouvre une session, dialogue jusqu'à `Ctrl-D`. Rend 1 sur configuration absente."""
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--session", type=uuid.UUID, help="reprendre une session existante")
    analyseur.add_argument(
        "--trace", action="store_true", help="affiche les arguments d'appel et les tool_result"
    )
    arguments = analyseur.parse_args()

    try:
        client = ClientAnthropic()
        systeme, signature = prompt_systeme()
        reglages = get_settings()
    except ConfigurationError as erreur:
        print(f"\n⛔ {erreur}\n", file=sys.stderr)
        return 1

    outils = schema_des_outils()
    fabrique = get_sessionmaker()

    with fabrique() as base:
        try:
            conversation = (
                lire_session(base, arguments.session)
                if arguments.session is not None
                else creer_session(base)
            )
        except SessionIntrouvable as erreur:
            print(f"\n⛔ {erreur}\n", file=sys.stderr)
            return 1
        if arguments.session is None:
            base.commit()

        depot = DepotSql(base)
        _entete(conversation.id, signature, client.strict, reprise=arguments.session is not None)
        _rappeler_letat(conversation)

        for ligne in _lignes_de_stdin():
            evenements = tour(
                base,
                conversation,
                client=client,
                systeme=systeme,
                outils=outils,
                message_client=ligne,
                depot=depot,
                max_iterations=reglages.max_agent_iterations,
                max_regenerations=reglages.max_regenerations,
            )
            issue = _afficher(evenements, trace=arguments.trace)
            if arguments.trace:
                _afficher_les_blocs_bruts(issue)

    print("\nÀ bientôt.")
    return 0


def _lignes_de_stdin() -> Iterator[str]:
    """Les messages du client, invite comprise. Une ligne vide ne coûte pas un appel API."""
    while True:
        print("\n\033[1mvous >\033[0m ", end="", flush=True)
        ligne = sys.stdin.readline()
        if not ligne:  # Ctrl-D
            return
        ligne = ligne.strip()
        if ligne:
            yield ligne


def _afficher(evenements: Generator[Evenement, None, IssueDuTour], *, trace: bool) -> IssueDuTour:
    """Consomme le générateur **en entier** et rend son issue — voir la docstring du module.

    La boucle `for` ordinaire jetterait la valeur de retour du générateur, et avec elle
    les blocs bruts que `--trace` affiche. Le `while` explicite la récupère par
    `StopIteration.value` ; c'est la même mécanique que `yield from` côté `session.py`.
    """
    print()
    while True:
        try:
            evenement = next(evenements)
        except StopIteration as arret:
            issue: IssueDuTour = arret.value
            return issue

        if isinstance(evenement, Texte):
            print(evenement.texte)
        elif isinstance(evenement, CriteresMisAJour):
            print(_ligne_criteres(evenement))
            for refuse in evenement.mouvements_refuses:
                print(f"  \033[33m↯ refusé\033[0m {refuse.champ} : {refuse.motif}")
        elif isinstance(evenement, Sondage):
            print(_ligne_sondage(evenement))
            if trace:
                for distribution in evenement.champs:
                    valeurs = " · ".join(
                        f"{valeur.valeur} ({valeur.effectif})" for valeur in distribution.valeurs
                    )
                    suite = " …" if distribution.tronque else ""
                    print(f"    {distribution.champ} : {valeurs}{suite}")
        elif isinstance(evenement, QuestionSuggeree):
            print(_ligne_suggestion(evenement))
        elif isinstance(evenement, ProduitsTrouves):
            _afficher_produits(evenement, trace=trace)
        elif isinstance(evenement, QuestionPosee):
            print(f"\n{evenement.question}")
        elif isinstance(evenement, TexteRejete):
            # ⚠️ **Sous `--trace` seulement.** Un texte rejeté est une mécanique interne :
            # le client n'a pas à voir la phrase qu'on ne lui envoie pas, ni la raison
            # pour laquelle on la refuse. C'est en revanche ce qu'on vient lire quand on
            # met le nez dans une conversation, et ce que l'étape 12 comptera.
            if trace:
                print(
                    f"\n\033[33m[texte rejeté]\033[0m tentative {evenement.tentative} — "
                    f"{len(evenement.griefs)} grief(s)"
                )
                for grief in evenement.griefs:
                    print(f"    \033[33m{grief.code.value}\033[0m « {grief.extrait} »")
        elif isinstance(evenement, Repli):
            print(
                f"\n\033[33m[repli]\033[0m {evenement.motif.value} "
                f"après {evenement.iterations} itération(s)"
            )
            print(evenement.message)


def _afficher_les_blocs_bruts(issue: IssueDuTour) -> None:
    """Les arguments d'appel et les `tool_result`, **tels qu'ils sont persistés**.

    C'est le seul endroit de la console qui montre ce que le modèle a réellement reçu,
    plutôt que ce que le code en a dérivé. Deux choses s'y lisent que rien d'autre
    n'expose : l'appairage `tool_use` / `tool_result` — le piège technique nº1 de
    l'étape 8 — et le contenu exact d'un refus, qui est du texte écrit **pour le modèle**.
    """
    print(f"\n\033[90m--- blocs bruts ({issue.iterations} itération(s)) ---\033[0m")
    for numero, tour_produit in enumerate(issue.tours, start=1):
        for bloc in tour_produit.blocs:
            genre = bloc.get("type")
            if genre == "tool_use":
                print(
                    f"\033[90m{numero:>2} tool_use\033[0m {bloc['id']} {bloc['name']} "
                    f"{json.dumps(bloc.get('input', {}), ensure_ascii=False)}"
                )
            elif genre == "tool_result":
                marque = "ERREUR " if bloc.get("is_error") else ""
                contenu = str(bloc.get("content", ""))
                if len(contenu) > 600:
                    contenu = contenu[:600] + f"… (+{len(contenu) - 600} caractères)"
                print(
                    f"\033[90m{numero:>2} tool_result\033[0m {bloc['tool_use_id']} "
                    f"{marque}{contenu}"
                )
            elif genre == "text":
                print(f"\033[90m{numero:>2} text\033[0m {len(bloc.get('text', ''))} caractères")


def _ligne_criteres(evenement: CriteresMisAJour) -> str:
    """`[critères] écran · 144 Hz bloquant · budget 400 $`"""
    morceaux = [LIBELLES_CATEGORIE[evenement.categorie]]
    morceaux += [_critere(critere, evenement.categorie) for critere in evenement.criteres]
    if evenement.budget_usd is not None:
        morceaux.append(f"budget {_montant(evenement.budget_usd)}")
    if evenement.optimisation.value != "aucune":
        morceaux.append(evenement.optimisation.value)
    return "\033[36m[critères]\033[0m " + " · ".join(morceaux)


def _critere(critere: Critere, categorie: Categorie) -> str:
    """Le critère tel qu'il a été enregistré, unité et libellé pris **au registre**.

    `Critere` ne porte ni libellé ni unité : c'est ce que le client a dit, pas ce que le
    catalogue en sait. Les deux viennent donc d'`ATTRIBUTS`, comme partout ailleurs — le
    français est du vocabulaire dérivé, jamais recopié (arbitrage I de l'étape 6).
    """
    attribut = ATTRIBUTS[categorie][critere.champ]
    valeur = valeur_en_texte(critere.valeur)
    unite = f" {attribut.unite}" if attribut.unite else ""
    prefixe = {"au_moins": "≥ ", "au_plus": "≤ ", "egal": ""}[critere.operateur.value]
    return f"{prefixe}{valeur}{unite} {attribut.libelle_fr} ({critere.importance.value})"


def _ligne_sondage(evenement: Sondage) -> str:
    """`[sondage] 32 candidats · 180 à 395 $ · 7 dans la zone de tolérance`"""
    morceaux = [f"{evenement.dans_le_budget} candidats"]
    bornes = evenement.fourchette_prix
    if bornes is not None:
        morceaux.append(f"{_montant(bornes.plus_bas)} à {_montant(bornes.plus_haut)}")
    if evenement.dans_la_zone_de_tolerance:
        morceaux.append(f"{evenement.dans_la_zone_de_tolerance} dans la zone de tolérance")
    return "\033[36m[sondage]\033[0m  " + " · ".join(morceaux)


def _ligne_suggestion(evenement: QuestionSuggeree) -> str:
    """`[question] refresh_rate suggéré · 32 candidats` — ou le budget, qui passe devant."""
    if evenement.budget is not None:
        return f"\033[36m[question]\033[0m budget inconnu · {evenement.candidats} candidats"
    if evenement.champ is None:
        return (
            f"\033[36m[question]\033[0m plus rien ne discrimine · {evenement.candidats} candidats"
        )
    return (
        f"\033[36m[question]\033[0m {evenement.champ.champ} suggéré "
        f"({evenement.champ.libelle_fr}) · {evenement.candidats} candidats"
    )


def _afficher_produits(evenement: ProduitsTrouves, *, trace: bool) -> None:
    """`[produits] 3 trouvés` — et sous `--trace`, la trace critère par critère."""
    resultat = evenement.resultat
    print(
        f"\033[36m[produits]\033[0m {len(resultat.produits)} trouvés "
        f"sur {resultat.candidats_trouves} candidats"
        + (
            f" · {len(resultat.au_dessus_du_budget)} au-dessus du budget"
            if resultat.au_dessus_du_budget
            else ""
        )
    )
    for produit in resultat.produits:
        print(f"    {produit.id}  {produit.nom}  {_montant(produit.prix_usd)}")
    for hors in resultat.au_dessus_du_budget:
        print(
            f"    \033[33m+{_montant(hors.ecart_usd)}\033[0m {hors.produit.id}  "
            f"{hors.produit.nom}  {_montant(hors.produit.prix_usd)}"
        )
    if resultat.diagnostic is not None:
        diagnostic = resultat.diagnostic
        print(f"    \033[33m[zéro résultat]\033[0m {diagnostic.motif.value}")
        for proposition in diagnostic.propositions:
            cible = (
                ""
                if proposition.valeur_atteignable is None
                else f" → {proposition.valeur_atteignable}"
            )
            print(
                f"      relâcher {proposition.libelle_fr}{cible} "
                f"rouvrirait {proposition.produits_rouverts} produit(s)"
            )
    if trace:
        for ligne in resultat.traces:
            # ⚠️ `score=0` n'est **pas** un défaut, et l'afficher seul le laisserait
            # croire : sans aucun critère scoré, le score vaut zéro et le classement se
            # joue entièrement sur le départage (`agreger()`, scénario G2 de l'étape 6).
            # C'est le cas nominal quand le client n'a posé que des filtres durs.
            # `criteres_evalues` est ce qui distingue « rien à scorer » de « tout raté »,
            # et c'est aussi ce que §7 dit que la trace expose contre le biais de
            # l'arbitrage F.
            print(
                f"    trace {ligne.produit_id} score={ligne.score} rang={ligne.rang} "
                f"(scorés {ligne.criteres_evalues}, indisponibles "
                f"{ligne.criteres_indisponibles}, rang sans le prix {ligne.rang_sans_le_prix})"
            )
            for critere in ligne.lignes:
                sous_score = "" if critere.sous_score is None else f" → {critere.sous_score}"
                print(
                    f"      {critere.champ} [{critere.role_applique.value}]: "
                    f"{critere.statut.value} (demandé {critere.valeur_demandee}, "
                    f"produit {critere.valeur_produit}){sous_score}"
                )


def _rappeler_letat(conversation: SessionConversation) -> None:
    """Sur une reprise, montre ce que la base a rendu. **C'est la preuve de l'étape.**

    Une session reprise qui réafficherait un état vide voudrait dire que `en_jsonb()` et
    `depuis_jsonb()` ne se répondent pas — et le défaut resterait invisible jusqu'à ce
    qu'un client, deux jours plus tard, retrouve une conversation amnésique.
    """
    criteres = conversation.criteres_valides or {}
    if not criteres.get("categorie_courante") and conversation.budget_usd is None:
        return
    categorie = criteres.get("categorie_courante")
    libelle = LIBELLES_CATEGORIE.get(categorie, categorie) if categorie else "—"
    nombre = len(criteres.get("criteres", {}).get(categorie, [])) if categorie else 0
    budget = "—" if conversation.budget_usd is None else _montant(conversation.budget_usd)
    print(f"\033[36m[repris]\033[0m {libelle} · {nombre} critère(s) · budget {budget}")


def _entete(identifiant: uuid.UUID, signature: str, strict: bool, *, reprise: bool) -> None:
    mode = "strict" if strict else "repli sans strict"
    print(f"\n\033[1mrAiyon\033[0m — {'session reprise' if reprise else 'nouvelle session'}")
    print(f"session : {identifiant}")
    print(f"prompt  : systeme.v1 ({signature}) · outils : {mode}")
    print(f'Ctrl-D pour sortir. Pour reprendre : make chat ARGS="--session {identifiant}"')


def _montant(valeur: Decimal) -> str:
    """Les prix sont des `Decimal` typés que **le code formate** (§2)."""
    return f"{valeur:.2f} $"


if __name__ == "__main__":
    raise SystemExit(main())
