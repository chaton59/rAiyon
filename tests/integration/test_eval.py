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


JEU_ANCRE = Jeu(nom=JEU_ETAPE_12, version="systeme.v1")
"""Le jeu sur lequel les tests de harnais s'appuient, et **pourquoi celui-là**.

Ils visaient le jeu de la version en vigueur jusqu'à l'étape 13. Ça ne tient plus : les
jeux vont et viennent au fil des campagnes — `systeme.v1/` a existé le temps d'une
campagne interrompue, puis a été archivé sous un autre nom —, et un test de harnais qui
dépend d'un jeu en cours échoue pour une raison qui n'a rien à voir avec le harnais.

Le jeu archivé de l'étape 12, lui, est **committé et permanent**. Il tourne sous
`systeme.v1`, dont l'empreinte ne change pas : le contrôle de péremption y est donc
exercé pour de vrai, ce qui est tout ce qu'on demande à ces tests.

⚠️ **La complétude du jeu en cours n'est pas vérifiée ici** — c'est `_prises_manquantes`
qui la vérifie, au moment d'écrire le rapport, c'est-à-dire à l'endroit où elle compte."""


def _jeu_courant() -> Jeu:
    return jeu_en_vigueur(None, prompt_systeme().version)


def test_une_cassette_committee_se_rejoue_et_se_mesure(base_seedee):
    """Le harnais entier, sur un scénario : lecture, empreintes, rejeu, mesures.

    ⚠️ **Le prompt vient du jeu, pas de la version en vigueur.** Les deux coïncidaient tant
    que `systeme.v1` était le défaut ; depuis que le jalon 3 a mis v2 en vigueur, rejouer un
    jeu v1 avec le prompt en vigueur le déclarerait périmé — ce qui serait vrai, et sans
    rapport avec ce que ce test mesure.
    """
    from eval import systeme_du_jeu

    scenario = par_nom(SCENARIO)
    prompt = systeme_du_jeu(JEU_ANCRE)
    outils = schema_des_outils()

    chemin = JEU_ANCRE.chemin(SCENARIO, PRISE)
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

    chemin = JEU_ANCRE.chemin(SCENARIO, PRISE)
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


def test_les_vingt_et_une_prises_payees_restent_rejouables(base_seedee):
    """**Le jeu partiel de l'étape 13, et pourquoi il est committé plutôt que jeté.**

    La campagne v1 s'est arrêtée à 21 prises sur 36, crédits épuisés. Ces 21 prises sont
    payées, et elles ne sont pas perdues : elles couvrent sept scénarios que le jeu de
    l'étape 12 couvre aussi, ce qui suffit à borner la dérive du modèle entre les deux
    dates. **Une mesure de dérive n'a pas besoin d'un jeu complet, elle a besoin de
    scénarios comparables.**

    Le jour où quelqu'un modifierait `systeme.v1.md` en place, c'est ici que ça se
    verrait — et c'est exactement ce que la contrainte « v1 ne se modifie pas en place »
    protège. Le jeu est archivé sous un nom qui dit ce qu'il est : `v1-partielle`.
    """
    from eval import systeme_du_jeu

    scenario = par_nom(SCENARIO)
    archive = Jeu(nom="v1-partielle", version="systeme.v1")
    prompt = systeme_du_jeu(archive)
    outils = schema_des_outils()

    assert len(prises_du_jeu(archive)) == 21
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


# --------------------------------------------------------------------------- #
# La liste des divergences attendues — elle affirme, elle ne tolère pas
# --------------------------------------------------------------------------- #


def test_la_divergence_attendue_a_bien_lieu(base_seedee):
    """**Le premier des trois contrôles : la ligne décrit un fait.**

    `v1-etape12/desserrage_refuse.1` doit diverger sous le validateur courant. Si elle
    cesse de diverger, le correctif du jalon 1 a été annulé — et la liste continuerait
    d'excuser une divergence qui n'a plus lieu, y compris le jour où une **vraie**
    divergence apparaîtrait au même endroit.
    """
    from raiyon.eval.cassette import DivergenceDeRequete

    archive = Jeu(nom=JEU_ETAPE_12, version="systeme.v1")
    prompt = prompt_systeme()
    outils = schema_des_outils()
    chemin = archive.chemin("desserrage_refuse", 1)
    cassette = depuis_json(chemin.read_text(encoding="utf-8"))

    with pytest.raises(DivergenceDeRequete):
        jouer(
            base_seedee,
            par_nom("desserrage_refuse"),
            1,
            client=ClientCassette(cassette, source=str(chemin)),
            depot=DepotSql(base_seedee),
            reglages=Reglages(
                systeme=prompt.texte, outils=outils, max_iterations=8, max_regenerations=1
            ),
        )


def test_une_divergence_non_listee_remonte_toujours():
    """**Le contrôle ne se relâche pas.** Une tolérance à la divergence serait le début du
    mode d'échec que l'arbitrage B ferme : le jour d'une vraie régression du moteur, elle
    serait écartée et nommée dans une ligne que personne ne lit.

    Le code n'attrape `DivergenceDeRequete` que pour une clé **listée** ; toute autre
    remonte. Ce test lit la condition dans la source plutôt que de provoquer une
    divergence réelle, qui coûterait un enregistrement.
    """
    from pathlib import Path

    import eval as module

    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "if cle not in DIVERGENCES_ATTENDUES:\n                raise" in source, (
        "la seule porte de sortie d'une divergence doit rester la liste ; un `continue` "
        "inconditionnel ici transformerait une régression moteur en chiffre silencieux"
    )


def test_chaque_ligne_de_la_liste_nomme_une_cassette_qui_existe():
    """**Le troisième contrôle.** Une ligne qui ne s'applique à rien est une ligne qu'on ne
    relit plus — et qui reste là quand la cassette qu'elle excusait a été renommée."""
    from eval import DIVERGENCES_ATTENDUES, Jeu

    for source, scenario, prise in DIVERGENCES_ATTENDUES:
        chemin = Jeu(nom=source, version="systeme.v1").chemin(scenario, prise)
        assert chemin.is_file(), (
            f"DIVERGENCES_ATTENDUES nomme {source}/{scenario}.{prise}, absente du dépôt"
        )


def test_une_ligne_qui_ne_diverge_plus_fait_echouer_le_rejeu(monkeypatch, base_seedee):
    """La contre-épreuve du premier contrôle, **à travers le rejeu réel**.

    ⚠️ **La première rédaction de ce test appelait `_verifier_les_divergences_attendues`
    directement, et c'était insuffisant** : la neutralisation du jalon 3 l'a montré en
    retirant l'appel de `mesurer_le_jeu`, ce qui n'a fait tomber aucun test. La garde
    existait et n'était branchée à rien de vérifié — précisément le mode d'échec qu'une
    garde de ce genre présente.

    Il passe donc par `mesurer_le_jeu`. On déclare divergente une cassette qui se rejoue
    parfaitement (`budget_serre.1`) : le rejeu doit s'arrêter en le disant.
    """
    import eval as module
    from eval import DivergenceAttendueAbsente, Jeu, _reglages_pour, mesurer_le_jeu, systeme_du_jeu

    archive = Jeu(nom=JEU_ETAPE_12, version="systeme.v1")
    monkeypatch.setitem(
        module.DIVERGENCES_ATTENDUES,
        (JEU_ETAPE_12, SCENARIO, PRISE),
        "ligne inventée par le test : cette cassette se rejoue en réalité très bien.",
    )
    prompt = systeme_du_jeu(archive)
    reglages, _, empreinte_outils = _reglages_pour(prompt)

    with pytest.raises(DivergenceAttendueAbsente) as erreur:
        mesurer_le_jeu(
            archive,
            [(par_nom(SCENARIO), PRISE)],
            reglages,
            prompt,
            empreinte_outils,
        )

    message = str(erreur.value)
    assert "se rejouent pourtant sans divergence" in message
    assert f"{JEU_ETAPE_12}/{SCENARIO}.{PRISE}" in message
    assert "DIVERGENCES_ATTENDUES" in message


def test_le_rapport_du_jeu_archive_declare_la_prise_ecartee():
    """Un rapport dont une cassette a été écartée affiche ses totaux avec **exactement la
    même autorité** qu'un rapport complet. La prise écartée portait 4 des 11 griefs de
    l'étape 12 : la taire ferait lire « 7 griefs » comme une amélioration."""
    from eval import Jeu, prises_du_jeu, reserves_du_jeu

    archive = Jeu(nom=JEU_ETAPE_12, version="systeme.v1")

    reserves = reserves_du_jeu(archive, prises_du_jeu(archive))

    assert any("desserrage_refuse.1 est écartée" in reserve for reserve in reserves)
    assert archive.rapport.read_text(encoding="utf-8").count("est écartée de ce rapport") == 1


# --------------------------------------------------------------------------- #
# La ligne de base composée
# --------------------------------------------------------------------------- #


def test_un_scenario_de_la_ligne_de_base_vient_dune_seule_source():
    """**La règle de composition, et elle n'est pas arbitraire.**

    Mélanger la prise 1 d'une date avec les prises 2 et 3 d'une autre, dans un même
    scénario, ferait confondre la dispersion du tirage avec l'écart entre deux
    enregistrements — c'est-à-dire exactement ce que la comparaison cherche à distinguer.
    """
    from eval import LIGNE_DE_BASE, prises_du_jeu

    prises = prises_du_jeu(LIGNE_DE_BASE)
    sources = {}
    for scenario, prise in prises:
        chemin = LIGNE_DE_BASE.chemin(scenario.nom, prise)
        sources.setdefault(scenario.nom, set()).add(chemin.parent.name)

    for nom, repertoires in sources.items():
        assert len(repertoires) == 1, f"{nom} vient de deux sources : {repertoires}"


def test_la_ligne_de_base_prefere_les_prises_fraiches_a_larchive():
    """L'archive de l'étape 12 ne sert qu'aux scénarios que les enregistrements plus
    récents ne portent pas — `question_de_domaine` au premier chef, qui est la cible
    entière du périmètre de domaine et que la campagne interrompue n'a pas atteint."""
    from eval import LIGNE_DE_BASE

    assert LIGNE_DE_BASE.compose
    assert LIGNE_DE_BASE.composants.index("v1-partielle") < LIGNE_DE_BASE.composants.index(
        JEU_ETAPE_12
    )
    assert LIGNE_DE_BASE.source_du_scenario("budget_serre") == "v1-partielle"
    assert LIGNE_DE_BASE.source_du_scenario("question_de_domaine") == JEU_ETAPE_12


def test_un_jeu_compose_se_resout_par_son_nom():
    """Un jeu composé n'a **pas** de répertoire à lui. Le construire à la volée depuis son
    nom donnerait `evals/cassettes/systeme.v1-base/`, qui n'existe pas, et la comparaison
    échouerait sur « aucune cassette » en désignant un chemin qui n'a jamais dû exister.

    C'est un défaut que le typage ne voit pas : `Jeu("v1-base", "systeme.v1")` est
    parfaitement valide, il ne pointe simplement nulle part.
    """
    from eval import LIGNE_DE_BASE, _jeu_nomme

    assert _jeu_nomme(LIGNE_DE_BASE.nom) is LIGNE_DE_BASE
    assert _jeu_nomme("v1-etape12").composants == ("v1-etape12",)
    assert _jeu_nomme("v1-partielle").version == "systeme.v1"
