"""Un scénario rejoué de bout en bout, pour que le harnais ne pourrisse pas en silence.

**Mince exprès.** `make eval` mesure le produit ; ce test-ci mesure le **harnais** : que
les cassettes committées se relisent, que les empreintes correspondent encore, que
l'exécuteur consomme le générateur en entier et que les métriques tombent. Sans lui, un
harnais cassé ne se découvrirait qu'au prochain `make eval`, c'est-à-dire au moment où l'on
en a besoin.

Il porte le marqueur `integration` parce que le rejeu exige Postgres et le seed : c'est la
conséquence assumée de l'arbitrage A — les `tool_result` ne sont pas enregistrés, ils sont
**recalculés** par le vrai moteur. `make check` reste donc inchangé.

⚠️ **Un seul scénario, et un court.** Les seize prises sont l'affaire de `make eval` ; les
rejouer ici ferait de `make test-int` une commande de plusieurs minutes pour la même
garantie sur le harnais.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from eval import CASSETTES  # scripts/ est sur le pythonpath (pyproject)
from raiyon.agent.prompts import prompt_systeme
from raiyon.eval.cassette import depuis_json, empreinte_des_outils
from raiyon.eval.client import ClientCassette, verifier
from raiyon.eval.executeur import Reglages, jouer
from raiyon.eval.metriques import Attente, agreger, mesurer
from raiyon.eval.scenario import par_nom
from raiyon.matching.depot import DepotSql
from raiyon.tools.schema_outils import schema_des_outils

pytestmark = pytest.mark.integration

SCENARIO = "budget_serre"
PRISE = 1
"""Le plus court des scénarios à attendu unique : deux tours, cinq prises, et le produit
de référence est le **seul** du catalogue à satisfaire les contraintes."""


@pytest.fixture
def base_seedee(moteur_agregats: Engine) -> Iterator[Session]:
    """Une session sur le catalogue réel, dans une transaction annulée à la fin.

    `jouer()` appelle `commit()` : la session rejoint la transaction externe par un point
    de sauvegarde, et le `rollback` final défait tout — y compris la conversation écrite.
    Deux exécutions du test partent donc du même état, comme partout ailleurs.
    """
    connexion = moteur_agregats.connect()
    transaction = connexion.begin()
    session = Session(bind=connexion, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connexion.close()


def test_une_cassette_committee_se_rejoue_et_se_mesure(base_seedee):
    """Le harnais entier, sur un scénario : lecture, empreintes, rejeu, mesures."""
    scenario = par_nom(SCENARIO)
    systeme, empreinte_prompt = prompt_systeme()
    outils = schema_des_outils()

    chemin = CASSETTES / scenario.fichier(PRISE)
    assert chemin.is_file(), f"{chemin} est absente — lancer `make eval-enregistrer`."
    cassette = depuis_json(chemin.read_text(encoding="utf-8"))

    # ⚠️ **C'est cette ligne qui échouera le jour où quelqu'un touchera au prompt ou au
    # schéma d'outils sans réenregistrer.** Elle dit quoi taper (arbitrage C).
    verifier(
        cassette,
        prompt_empreinte=empreinte_prompt,
        outils_empreinte=empreinte_des_outils(outils),
    )

    client = ClientCassette(cassette, source=str(chemin.name))
    jouee = jouer(
        base_seedee,
        scenario,
        PRISE,
        client=client,
        depot=DepotSql(base_seedee),
        reglages=Reglages(systeme=systeme, outils=outils, max_iterations=8, max_regenerations=1),
    )

    # Toutes les prises ont été consommées : la conversation rejouée est bien celle qui a
    # été enregistrée, et aucune empreinte n'a divergé — sans quoi `repondre()` aurait levé.
    assert client.epuisee
    assert len(jouee.tours) == len(scenario.tours)

    mesures = agreger([mesurer(jouee)])
    assert mesures.critere_1 is True, "le validateur laisse passer un grief dans le livré"
    assert mesures.critere_2 is True
    assert mesures.critere_6 is True
    assert mesures.attendus_en_top3 == 1, (
        "le produit de référence a quitté le top 3 — relire la justification de "
        "l'attendu dans scenario.py avant d'accuser le moteur (arbitrage F)"
    )
    assert Attente.PRODUITS_CITES in mesures.prises[0].faits


def test_un_prompt_modifie_fait_echouer_le_rejeu_en_disant_de_regenerer(base_seedee):
    """La contre-épreuve de l'arbitrage C, sur une cassette **réelle**.

    Sans elle, le test du dessus passerait aussi bien avec un `verifier()` qui ne
    vérifierait rien — qui est le mode d'échec réel d'un contrôle d'empreinte.
    """
    from raiyon.eval.cassette import CassettePerimee

    cassette = depuis_json(
        (CASSETTES / par_nom(SCENARIO).fichier(PRISE)).read_text(encoding="utf-8")
    )
    with pytest.raises(CassettePerimee) as erreur:
        verifier(
            cassette,
            prompt_empreinte="0" * 12,
            outils_empreinte=empreinte_des_outils(schema_des_outils()),
        )
    assert f"make eval-enregistrer SCENARIO={SCENARIO}" in str(erreur.value)
