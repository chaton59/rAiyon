"""Un scénario rejoué de bout en bout, pour que le harnais ne pourrisse pas en silence.

**Mince exprès.** `make eval` mesure le produit ; ce test-ci mesure le **harnais** : que
les cassettes committées se relisent, que les empreintes correspondent encore, que
l'exécuteur consomme le générateur en entier et que les métriques tombent. Sans lui, un
harnais cassé ne se découvrirait qu'au prochain `make eval`, c'est-à-dire au moment où l'on
en a besoin.

Il porte le marqueur `integration` parce que le rejeu exige Postgres et le seed : c'est la
conséquence assumée de l'arbitrage A — les `tool_result` ne sont pas enregistrés, ils sont
**recalculés** par le vrai moteur. `make check` reste donc inchangé.

⚠️ **Un seul scénario, et un court.** Les trente-six prises sont l'affaire de `make eval` ;
les rejouer ici ferait de `make test-int` une commande de plusieurs minutes pour la même
garantie sur le harnais.

### Le jeu archivé de l'étape 12 est rejoué ici, et c'est ce qui rend « conservé » vrai

Étape 13, jalon 0, point B : les dix-neuf cassettes de l'étape 12 sont conservées sous
`evals/cassettes/systeme.v1-etape12/`. **Sans un rejeu, « conservé » voudrait seulement
dire « pas effacé ».** Ce qui est promis est plus fort : `systeme.v1.md` ne changeant pas,
le tirage que §7 et le correctif de l'étape 12 citent reste **reconstituable**, et un
changement de moteur ultérieur se rejouera contre lui.

Le contrôle porte sur une prise, pour la même raison que ci-dessus. Le rejeu complet du jeu
archivé est `make eval-etape12`, et c'est lui qui réécrit `docs/eval/rapport.v1-etape12.md`.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from eval import JEU_ETAPE_12, Jeu, jeu_en_vigueur, prises_du_jeu  # scripts/ sur le pythonpath
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


def _jeu_courant() -> Jeu:
    return jeu_en_vigueur(None, prompt_systeme().version)


def test_une_cassette_committee_se_rejoue_et_se_mesure(base_seedee):
    """Le harnais entier, sur un scénario : lecture, empreintes, rejeu, mesures."""
    scenario = par_nom(SCENARIO)
    prompt = prompt_systeme()
    outils = schema_des_outils()

    chemin = _jeu_courant().chemin(SCENARIO, PRISE)
    assert chemin.is_file(), f"{chemin} est absente — lancer `make eval-enregistrer`."
    cassette = depuis_json(chemin.read_text(encoding="utf-8"))

    # ⚠️ **C'est cette ligne qui échouera le jour où quelqu'un touchera au prompt ou au
    # schéma d'outils sans réenregistrer.** Elle dit quoi taper (arbitrage C).
    verifier(
        cassette,
        prompt_version=prompt.version,
        prompt_empreinte=prompt.empreinte,
        outils_empreinte=empreinte_des_outils(outils),
        source=str(chemin),
    )
    systeme = prompt.texte

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

    chemin = _jeu_courant().chemin(SCENARIO, PRISE)
    cassette = depuis_json(chemin.read_text(encoding="utf-8"))
    with pytest.raises(CassettePerimee) as erreur:
        verifier(
            cassette,
            prompt_version="systeme.v1",
            prompt_empreinte="0" * 12,
            outils_empreinte=empreinte_des_outils(schema_des_outils()),
            source=str(chemin),
        )
    message = str(erreur.value)
    assert f"make eval-enregistrer SCENARIO={SCENARIO}" in message
    assert str(chemin) in message, "le message nomme le fichier, pas seulement le scénario"


# --------------------------------------------------------------------------- #
# Le jeu archivé de l'étape 12 — « conservé » veut dire « rejouable »
# --------------------------------------------------------------------------- #


def test_le_jeu_archive_de_letape_12_porte_bien_ses_dix_neuf_prises():
    """**Pur, mais il vit ici** : c'est la moitié de la promesse du point B, et la placer
    à côté du rejeu évite qu'on l'oublie en déplaçant l'autre."""
    archive = Jeu(nom=JEU_ETAPE_12, version="systeme.v1")

    assert archive.cassettes.is_dir(), f"{archive.cassettes} a disparu"
    assert len(prises_du_jeu(archive)) == 19
    assert archive.rapport.is_file(), f"{archive.rapport} a disparu"


def test_une_cassette_du_jeu_archive_se_rejoue_encore(base_seedee):
    """**Ce qui fait que « conservé » ne veut pas dire « pas effacé ».**

    `systeme.v1.md` ne change pas de l'étape 13 : le jeu de l'étape 12 reste donc
    rejouable, et le tirage que §7 cite reste reconstituable. Le jour où quelqu'un
    modifierait v1 en place, c'est ici que ça se verrait — et c'est exactement ce que la
    contrainte « v1 ne se modifie pas en place » protège.
    """
    scenario = par_nom(SCENARIO)
    prompt = prompt_systeme()
    outils = schema_des_outils()
    archive = Jeu(nom=JEU_ETAPE_12, version="systeme.v1")

    chemin = archive.chemin(SCENARIO, PRISE)
    cassette = depuis_json(chemin.read_text(encoding="utf-8"))
    verifier(
        cassette,
        prompt_version=prompt.version,
        prompt_empreinte=prompt.empreinte,
        outils_empreinte=empreinte_des_outils(outils),
        source=str(chemin),
    )

    client = ClientCassette(cassette, source=str(chemin.name))
    jouee = jouer(
        base_seedee,
        scenario,
        PRISE,
        client=client,
        depot=DepotSql(base_seedee),
        reglages=Reglages(
            systeme=prompt.texte, outils=outils, max_iterations=8, max_regenerations=1
        ),
    )

    assert client.epuisee
    assert agreger([mesurer(jouee)]).bloquants_tenus is True


def test_un_jeu_incomplet_ne_produit_pas_de_rapport_committe():
    """**Trouvé en le vivant, jalon 0 de l'étape 13.**

    La campagne v1 s'est arrêtée à 21 prises sur 36 — l'API a refusé le vingt-deuxième
    appel. Rien dans le harnais ne l'aurait dit au rejeu suivant : un rapport écrit depuis
    un jeu incomplet a la **même forme** qu'un rapport complet, ses critères sont verts, et
    aucune ligne ne dit que quatre scénarios sur onze n'ont pas été joués. C'est un fichier
    committé, comparé à trois autres, et relu dans six mois.

    Le message doit nommer **ce qui manque** et **la commande qui le complète** — sans
    quoi il déplace le problème au lieu de le résoudre.
    """
    from eval import _prises_manquantes

    jeu = jeu_en_vigueur(None, "systeme.v1")
    incomplet = [(par_nom(SCENARIO), 1)]

    message = _prises_manquantes(jeu, incomplet)

    assert "est incomplet" in message
    assert "question_de_domaine x6" in message, "il nomme le scénario et le compte manquant"
    assert "RAIYON_PROMPT_SYSTEME=systeme.v1 make eval-enregistrer" in message
    assert _prises_manquantes(jeu, prises_du_jeu(jeu)) == "" or "incomplet" in _prises_manquantes(
        jeu, prises_du_jeu(jeu)
    )


def test_un_jeu_archive_nest_jamais_declare_incomplet():
    """`v1-etape12` porte dix-neuf prises parce que l'étape 12 en a enregistré dix-neuf :
    il est **complet pour ce qu'il est**. Le contrôle ne porte que sur le jeu de la version
    en vigueur, dont `SCENARIOS` décrit exactement ce qu'il doit contenir — sans cette
    distinction, `make eval-etape12` refuserait d'écrire le rapport qu'il existe pour
    produire."""
    from eval import _prises_manquantes

    archive = Jeu(nom=JEU_ETAPE_12, version="systeme.v1")

    assert _prises_manquantes(archive, prises_du_jeu(archive)) == ""
