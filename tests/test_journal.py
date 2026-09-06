"""Le journal JSONL : il écrit, il n'abîme rien, et il ne tombe pas quand le disque tombe.

Purs : ni base, ni conteneur, ni clé API. Ils écrivent dans un `tmp_path`.

⚠️ **Ces tests reconfigurent `structlog` pour le processus entier**, et `structlog` n'a pas
de portée par test. La fixture `journal_restaure` remet donc la configuration par défaut
après chaque cas — sans elle, le premier test d'ici laisserait un `EcrivainJSONL` pointant
sur un `tmp_path` détruit dans la chaîne de processeurs de toute la suite, et les trois
fichiers qui se servent de `capture_logs()` échoueraient à des kilomètres d'ici.
"""

import json
from decimal import Decimal

import pytest
import structlog

from raiyon.config import get_settings
from raiyon.journal import EcrivainJSONL, configurer_journal, processeurs


@pytest.fixture(autouse=True)
def journal_restaure():
    """Rend à `structlog` sa configuration par défaut après chaque cas."""
    yield
    structlog.reset_defaults()


def _lignes(chemin):
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines()]


def test_une_ligne_json_par_evenement(tmp_path):
    """Le besoin qui a fait écrire le module : les logs survivent au shell."""
    fichier = tmp_path / "j" / "raiyon.jsonl"
    configurer_journal(niveau="INFO", chemin=fichier)

    structlog.get_logger(__name__).info("essai.evenement", jetons=42, modele="claude-sonnet-5")

    (ligne,) = _lignes(fichier)
    assert ligne["event"] == "essai.evenement"
    assert ligne["jetons"] == 42
    assert ligne["modele"] == "claude-sonnet-5"
    assert ligne["level"] == "info"
    assert "timestamp" in ligne


def test_le_repertoire_parent_est_cree(tmp_path):
    """Un dossier manquant ne doit pas faire perdre la session qu'on voulait observer."""
    fichier = tmp_path / "pas" / "encore" / "la" / "raiyon.jsonl"
    configurer_journal(niveau="INFO", chemin=fichier)

    structlog.get_logger(__name__).info("essai.creation")

    assert fichier.is_file()


def test_le_terminal_recoit_le_meme_evenement_intact(tmp_path):
    """⚠️ **Le défaut que l'écrivain pourrait introduire, et le seul qui compte.**

    Le rendu console **consomme** `event`, `timestamp` et `level` en les retirant du
    dictionnaire. Un écrivain qui sérialiserait l'instance reçue au lieu d'une copie
    marcherait tant qu'il passe en premier, et rendrait des lignes amputées le jour où
    l'ordre des processeurs change. On constate donc que le dictionnaire ressort tel quel.
    """
    ecrivain = EcrivainJSONL(tmp_path / "raiyon.jsonl")
    evenement = {"event": "essai", "level": "info", "jetons": 7}

    rendu = ecrivain(None, "info", dict(evenement))

    assert rendu == evenement
    assert _lignes(tmp_path / "raiyon.jsonl") == [evenement]


def test_une_valeur_non_serialisable_ne_fait_pas_lever(tmp_path):
    """Un `Decimal` traverse tout le dépôt : le journal ne doit pas casser dessus.

    Un log qui interrompt le processus qu'il observe est pire que le log manquant.
    """
    fichier = tmp_path / "raiyon.jsonl"
    configurer_journal(niveau="INFO", chemin=fichier)

    structlog.get_logger(__name__).info("essai.decimal", prix=Decimal("399.99"))

    (ligne,) = _lignes(fichier)
    assert ligne["prix"] == "399.99"


def test_le_niveau_filtre_reellement(tmp_path):
    """`RAIYON_LOG_LEVEL` était déclarée depuis l'étape 2 et ne filtrait rien."""
    fichier = tmp_path / "raiyon.jsonl"
    configurer_journal(niveau="WARNING", chemin=fichier)

    logueur = structlog.get_logger(__name__)
    logueur.info("essai.ignore")
    logueur.warning("essai.retenu")

    assert [ligne["event"] for ligne in _lignes(fichier)] == ["essai.retenu"]


def test_sans_chemin_aucun_fichier_et_la_chaine_reste_courte():
    """`None` doit valoir « comme avant » : un terminal, et rien sur le disque."""
    chaine = processeurs(None)

    assert not any(isinstance(processeur, EcrivainJSONL) for processeur in chaine)
    assert configurer_journal(niveau="INFO", chemin=None) is None


def test_le_defaut_de_la_configuration_est_le_terminal_seul():
    """Un clone frais sans `RAIYON_JOURNAL_JSONL` se comporte comme avant l'étape 17."""
    assert get_settings().journal_jsonl is None


def test_un_echec_decriture_rend_le_journal_muet_sans_lever(tmp_path, capsys):
    """Un disque plein ne doit pas interrompre une conversation, ni se plaindre en boucle.

    Le fichier est remplacé par un répertoire : toute ouverture en écriture lève `OSError`,
    ce qui reproduit l'échec sans avoir à remplir un disque.
    """
    chemin = tmp_path / "raiyon.jsonl"
    ecrivain = EcrivainJSONL(chemin)
    chemin.mkdir()

    assert ecrivain(None, "info", {"event": "premier"}) == {"event": "premier"}
    assert ecrivain(None, "info", {"event": "second"}) == {"event": "second"}

    plaintes = [ligne for ligne in capsys.readouterr().err.splitlines() if "journal JSONL" in ligne]
    assert len(plaintes) == 1, "la plainte doit être dite une fois, pas à chaque ligne"
