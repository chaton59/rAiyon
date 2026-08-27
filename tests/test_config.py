"""Tests de la configuration typée.

Aucun de ces tests ne touche le réseau ni Postgres.
"""

import pytest
from pydantic import ValidationError

from raiyon.config import Settings, get_settings

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
    assert settings.log_level == "INFO"
    assert settings.app_env == "dev"
    assert settings.database_url.scheme == "postgresql+psycopg"
    assert settings.database_url.hosts()[0]["host"] == "localhost"
    assert settings.database_url.hosts()[0]["port"] == 5432
    assert settings.database_url.path == "/raiyon"


def test_cle_api_absente_echoue_bruyamment():
    """`ANTHROPIC_API_KEY` absente doit lever, pas se rabattre sur un défaut."""
    with pytest.raises(ValidationError) as erreur:
        get_settings()

    assert "ANTHROPIC_API_KEY" in str(erreur.value)


def test_budget_tolerance_hors_bornes_est_refuse(monkeypatch):
    """La borne haute de `budget_tolerance` (0.5) est bien appliquée."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLE_FACTICE)
    monkeypatch.setenv("RAIYON_BUDGET_TOLERANCE", "0.9")

    with pytest.raises(ValidationError) as erreur:
        get_settings()

    assert "budget_tolerance" in str(erreur.value)


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


def test_la_configuration_est_immuable(monkeypatch):
    """`frozen=True` : une valeur de configuration ne se modifie pas à chaud."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLE_FACTICE)

    settings = get_settings()

    with pytest.raises(ValidationError):
        settings.max_agent_iterations = 99  # type: ignore[misc]

    assert Settings.model_config["frozen"] is True
