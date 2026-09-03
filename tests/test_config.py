"""Tests de la configuration typée.

Aucun de ces tests ne touche le réseau ni Postgres.
"""

import pytest
from pydantic import ValidationError

from raiyon.config import ConfigurationError, Settings, cle_api, get_settings

CLE_FACTICE = "sk-ant-test-0123456789"


def test_valeurs_par_defaut(monkeypatch):
    """Avec la seule clé API fournie, tous les défauts sont ceux attendus."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLE_FACTICE)

    settings = get_settings()

    assert settings.model_agent == "claude-sonnet-5"
    assert settings.model_extraction == "claude-haiku-4-5-20251001"
    assert settings.model_eval_client == "claude-haiku-4-5-20251001"
    assert settings.budget_tolerance == 0.15
    assert settings.max_agent_iterations == 8
    assert settings.max_regenerations == 1
    assert settings.orchestration == "agent"
    assert settings.log_level == "INFO"
    assert settings.app_env == "dev"
    assert settings.database_url.scheme == "postgresql+psycopg"
    assert settings.database_url.hosts()[0]["host"] == "localhost"
    assert settings.database_url.hosts()[0]["port"] == 5432
    assert settings.database_url.path == "/raiyon"


def test_cle_api_absente_ne_bloque_plus_le_demarrage():
    """La clé est **optionnelle** depuis l'étape 8 (arbitrage 10), et c'est un renversement.

    Elle était obligatoire depuis l'étape 2, au nom d'« échouer tôt ». La décision était
    raisonnable tant que le pipeline appelait un modèle ; §3.4ter a supprimé ce seul
    appel, et `make seed`, `make seed-build` et `make calibrer` réclamaient depuis lors
    une clé qu'ils n'utilisent jamais — un mensonge sur la dépendance, celui-là même que
    la suppression de la passe LLM avait fait disparaître ailleurs.

    Le principe ne change pas, son objet si : on échoue tôt **sur ce qui est réellement
    requis**, c'est-à-dire au premier appel API — voir le test suivant.
    """
    settings = get_settings()

    assert settings.anthropic_api_key is None
    assert settings.model_agent == "claude-sonnet-5"


def test_cle_api_absente_echoue_bruyamment_au_moment_de_lutiliser():
    """`cle_api()` est le **seul** site de déballage, et il dit quoi faire.

    L'alternative — un `SecretStr | None` déballé sur chaque site d'usage — répandrait un
    `| None` dans chaque appelant. L'accesseur n'en laisse qu'un, et c'est lui qui porte
    le message.
    """
    with pytest.raises(ConfigurationError) as erreur:
        cle_api()

    message = str(erreur.value)
    assert "ANTHROPIC_API_KEY" in message
    # Le message nomme les commandes concernées plutôt que de dire « clé manquante ».
    assert "make chat" in message
    assert "make seed" in message


def test_cle_api_presente_est_rendue_deballee(monkeypatch):
    """Contre-épreuve : sans elle, un `cle_api()` qui lèverait toujours passerait."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLE_FACTICE)

    assert cle_api() == CLE_FACTICE


def test_budget_tolerance_hors_bornes_est_refuse(monkeypatch):
    """La borne haute de `budget_tolerance` (0.5) est bien appliquée."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLE_FACTICE)
    monkeypatch.setenv("RAIYON_BUDGET_TOLERANCE", "0.9")

    with pytest.raises(ValidationError) as erreur:
        get_settings()

    assert "budget_tolerance" in str(erreur.value)


def test_lorchestration_accepte_ses_deux_valeurs_et_refuse_les_autres(monkeypatch):
    """Étape 15, jalon 0, point A. **La variable existe et n'est pas encore consommée** :
    aucune ligne de `session.tour()` ne la lit, parce qu'il n'existe qu'une orchestration
    au moment où le champ est écrit. Elle donne sa source au champ `orchestration` de
    l'en-tête de cassette et à la garde de `make eval-enregistrer`, rien de plus.

    `Literal` plutôt qu'un motif comme `prompt_systeme` : les deux valeurs sont **closes**,
    là où une version de prompt nomme un fichier dont la liste s'allonge.
    """
    monkeypatch.setenv("RAIYON_ORCHESTRATION", "machine")
    assert get_settings().orchestration == "machine"

    get_settings.cache_clear()
    monkeypatch.setenv("RAIYON_ORCHESTRATION", "graphe")

    with pytest.raises(ValidationError) as erreur:
        get_settings()

    assert "orchestration" in str(erreur.value)


def test_la_cle_ne_fuit_pas_dans_les_representations(monkeypatch):
    """Ni `repr(settings)` ni `str(la clé)` ne doivent laisser voir le secret."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLE_FACTICE)

    settings = get_settings()

    assert CLE_FACTICE not in repr(settings)
    assert CLE_FACTICE not in str(settings)
    assert CLE_FACTICE not in str(settings.anthropic_api_key)
    # La valeur reste évidemment accessible quand on la demande explicitement.
    assert settings.anthropic_api_key.get_secret_value() == CLE_FACTICE


def test_le_cache_est_vidable(monkeypatch):
    """`get_settings` est mis en cache, et ce cache est vidable pour les tests."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLE_FACTICE)

    premier = get_settings()
    assert get_settings() is premier

    get_settings.cache_clear()
    monkeypatch.setenv("RAIYON_APP_ENV", "test")
    second = get_settings()

    assert second is not premier
    assert second.app_env == "test"


def test_variable_mal_orthographiee_est_refusee(monkeypatch):
    """Une faute de frappe sur un nom de variable ne doit pas passer en silence."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLE_FACTICE)
    monkeypatch.setenv("RAIYON_BUDGET_TOLERANC", "0.4")  # E manquant

    with pytest.raises(ConfigurationError) as erreur:
        get_settings()

    message = str(erreur.value)
    assert "RAIYON_BUDGET_TOLERANC" in message
    assert "RAIYON_BUDGET_TOLERANCE" in message  # la suggestion est proposée


def test_variable_inconnue_dans_le_fichier_env_est_refusee(monkeypatch, tmp_path):
    """Le contrôle porte aussi sur `.env`, où la faute de frappe est la plus probable."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLE_FACTICE)
    (tmp_path / ".env").write_text("# commentaire\nRAIYON_MAX_ITERATIONS=12\n", encoding="utf-8")

    with pytest.raises(ConfigurationError) as erreur:
        get_settings()

    assert "RAIYON_MAX_ITERATIONS" in str(erreur.value)


def test_la_cle_api_prefixee_est_refusee(monkeypatch):
    """`RAIYON_ANTHROPIC_API_KEY` n'existe pas : le validation_alias annule le préfixe.

    C'est la faute de frappe la plus plausible du projet — le préfixe est la règle
    partout ailleurs. Sans ce contrôle, la clé n'était tout simplement pas lue.
    """
    monkeypatch.setenv("RAIYON_ANTHROPIC_API_KEY", CLE_FACTICE)

    with pytest.raises(ConfigurationError) as erreur:
        get_settings()

    message = str(erreur.value)
    assert "RAIYON_ANTHROPIC_API_KEY" in message
    assert "RAIYON_ANTHROPIC_API_KEY" not in message.split("Noms acceptés :")[1]


def test_les_variables_hors_prefixe_sont_ignorees(monkeypatch, tmp_path):
    """`POSTGRES_PORT` et consorts sont lus par docker-compose, pas par Settings."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLE_FACTICE)
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("EDITOR", "vim")
    (tmp_path / ".env").write_text("POSTGRES_PORT=5433\n", encoding="utf-8")

    assert get_settings().app_env == "dev"


def test_la_configuration_est_immuable(monkeypatch):
    """`frozen=True` : une valeur de configuration ne se modifie pas à chaud."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLE_FACTICE)

    settings = get_settings()

    with pytest.raises(ValidationError):
        settings.max_agent_iterations = 99  # type: ignore[misc]

    assert Settings.model_config["frozen"] is True
