"""`RAIYON_VALIDATION` : ce que le mode `avertissement` change, et ce qu'il ne change pas.

⚠️ **La propriété qui compte n'est pas « le texte passe ».** C'est que **les règles tournent
quand même** : elles produisent leurs griefs, les loguent et les émettent en `TexteRejete`,
donc le journal les compte. Un validateur éteint ne mesure rien — et c'est la mesure qui a
montré que deux des trois griefs de la campagne v3 étaient des défauts de règle et non des
fautes du modèle.

Un mode qui se contenterait de sauter l'appel à `valider()` passerait le test « le texte est
livré » et perdrait tout le reste. Les cas ci-dessous sont écrits contre cette version-là.

Les deux orchestrations sont couvertes : le drapeau vit sur le `Verdict`, donc résolu une
seule fois, mais chacune a sa propre boucle de régénération et pourrait ignorer `bloque`.

Purs : ni base, ni conteneur, ni clé API.
"""

import pytest
import structlog
from faux_client import FauxClient, message, texte
from scenarios import SYSTEME, etat_ecran

from raiyon.agent.boucle import repondre
from raiyon.agent.evenements import Repli, Texte, TexteRejete
from raiyon.config import get_settings
from raiyon.machine.orchestrateur import repondre_machine

ORCHESTRATIONS = pytest.mark.parametrize(
    "orchestration", [repondre, repondre_machine], ids=["agent", "machine"]
)

FAUTIF = "Le moins cher est à 47 $, une affaire."
"""Un montant qu'aucun `tool_result` n'a fourni : `montant_non_fourni`, sans dépendre du
catalogue ni d'un produit particulier."""

SAIN = "Voici trois écrans."


def _script(orchestration, *reponses: str) -> FauxClient:
    """Le même dialogue, écrit pour l'orchestration qui le joue.

    ⚠️ **Les deux ne consomment pas leurs réponses au même rang, et l'ignorer donne un test
    qui passe sans rien prouver.** La machine fait deux appels par tour : le premier est une
    **extraction**, dont le texte est jeté sans être validé (`_sans(reponse.blocs, "text")`)
    ; c'est le second, la rédaction, qui parle au client et passe au validateur.

    Un script écrit pour l'agent met donc le texte fautif en face de l'extraction de la
    machine, où il est jeté — et le test « aucun grief » réussit pour la mauvaise raison.
    D'où le préambule inséré ici, et d'où l'absence d'assertion sur le nombre d'appels : il
    vaut 1 pour l'agent et 2 pour la machine, par construction, et n'est pas ce qu'on teste.
    """
    prealables = ("Je regarde ça.",) if orchestration is repondre_machine else ()
    return FauxClient(reponses=[message(texte(morceau)) for morceau in (*prealables, *reponses)])


@pytest.fixture
def en_avertissement(monkeypatch):
    monkeypatch.setenv("RAIYON_VALIDATION", "avertissement")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _jouer(client, orchestration, contexte, outils):
    generateur = orchestration(
        client=client,
        systeme=SYSTEME,
        outils=outils,
        historique=[],
        message_client="Bonjour",
        etat=etat_ecran(),
        contexte=contexte,
        max_iterations=8,
        max_regenerations=1,
    )
    evenements = []
    while True:
        try:
            evenements.append(next(generateur))
        except StopIteration as arret:
            return evenements, arret.value


def test_le_defaut_est_bloquant():
    """Le drapeau existe pour pouvoir renverser l'arbitrage, pas parce qu'il devrait l'être."""
    assert get_settings().validation == "bloquante"


@ORCHESTRATIONS
def test_en_avertissement_le_texte_fautif_part_au_client(
    en_avertissement, orchestration, contexte, outils
):
    """Le texte fautif est livré tel quel : aucune régénération n'a été demandée."""
    client = _script(orchestration, FAUTIF)

    evenements, _ = _jouer(client, orchestration, contexte, outils)

    livres = [evenement.texte for evenement in evenements if isinstance(evenement, Texte)]
    assert livres[-1] == FAUTIF
    assert not [evenement for evenement in evenements if isinstance(evenement, Repli)]


@ORCHESTRATIONS
def test_en_avertissement_les_griefs_sont_quand_meme_emis(
    en_avertissement, orchestration, contexte, outils
):
    """⚠️ **La propriété centrale.** Sans `TexteRejete`, le mode n'observerait rien.

    `bloquant=False` est ce qui empêche le tableau de bord de marquer « jamais lu par le
    client » un texte que le client a lu.
    """
    client = _script(orchestration, FAUTIF)

    evenements, _ = _jouer(client, orchestration, contexte, outils)

    (rejet,) = [evenement for evenement in evenements if isinstance(evenement, TexteRejete)]
    assert rejet.bloquant is False
    assert [grief.code.value for grief in rejet.griefs] == ["montant_non_fourni"]
    assert rejet.texte == FAUTIF


@ORCHESTRATIONS
def test_en_avertissement_le_grief_est_logue(en_avertissement, orchestration, contexte, outils):
    """Le journal JSONL doit voir passer ce que le validateur a trouvé, mode compris."""
    client = _script(orchestration, FAUTIF)

    with structlog.testing.capture_logs() as journal:
        _jouer(client, orchestration, contexte, outils)

    signales = [ligne for ligne in journal if ligne["event"].endswith("grief_signale")]
    assert len(signales) == 1
    assert signales[0]["log_level"] == "warning"
    assert signales[0]["codes"] == ["montant_non_fourni"]


@ORCHESTRATIONS
def test_en_bloquante_le_meme_texte_declenche_une_regeneration(orchestration, contexte, outils):
    """Le pendant : sans lui, un mode `avertissement` permanent passerait aussi les tests."""
    client = _script(orchestration, FAUTIF, SAIN)

    evenements, _ = _jouer(client, orchestration, contexte, outils)

    (rejet,) = [evenement for evenement in evenements if isinstance(evenement, TexteRejete)]
    assert rejet.bloquant is True
    assert rejet.tentative == 1
    # Le texte fautif n'a **pas** été livré : c'est le régénéré qui part au client.
    livres = [evenement.texte for evenement in evenements if isinstance(evenement, Texte)]
    assert livres[-1] == SAIN
    assert FAUTIF not in livres


@ORCHESTRATIONS
def test_en_avertissement_un_texte_sain_ne_produit_aucun_grief(
    en_avertissement, orchestration, contexte, outils
):
    """Le mode ne fabrique pas de signalement : il n'en retire que l'effet."""
    client = _script(orchestration, SAIN)

    evenements, _ = _jouer(client, orchestration, contexte, outils)

    assert not [evenement for evenement in evenements if isinstance(evenement, TexteRejete)]
