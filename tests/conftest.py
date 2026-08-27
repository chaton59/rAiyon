"""Isolation de l'environnement pour toute la suite de tests.

Sans cette fixture, un `.env` présent sur la machine (celui que `make install`
crée) ou une variable exportée dans le shell ferait passer ou échouer les tests
selon le poste. Les deux sources sont donc neutralisées :

* les variables `RAIYON_*` et `ANTHROPIC_API_KEY` sont retirées de l'environnement ;
* le répertoire courant devient un dossier temporaire vide, donc le chemin
  relatif `.env` déclaré dans `Settings.model_config` ne résout sur rien.
"""

import pytest

from raiyon.config import Settings, get_settings

ENV_VARS = ("ANTHROPIC_API_KEY", *(f"RAIYON_{f.upper()}" for f in Settings.model_fields))


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Vide le cache et l'environnement avant et après chaque test."""
    get_settings.cache_clear()
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    yield
    get_settings.cache_clear()
