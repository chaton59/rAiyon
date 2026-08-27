"""Configuration typée du projet.

Point unique de lecture de l'environnement : aucune autre partie du code ne lit
`os.environ` ni ne contient de clé en dur. Toute nouvelle variable d'environnement
se déclare ici, avec son type et sa validation.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration du processus, lue depuis l'environnement puis depuis `.env`.

    Les variables portent le préfixe `RAIYON_` (par exemple
    `RAIYON_BUDGET_TOLERANCE`). Seule exception : `ANTHROPIC_API_KEY`, lue sans
    préfixe parce que c'est le nom conventionnel attendu par le SDK Anthropic.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RAIYON_",
        frozen=True,
        extra="ignore",
        validate_default=True,
        # Les champs `model_agent` / `model_extraction` / `model_eval_client`
        # entrent en collision avec l'espace de noms protégé `model_` de Pydantic.
        # Le désactiver est sans effet de bord ici : aucun de ces champs ne
        # surcharge une API de BaseModel.
        protected_namespaces=(),
    )

    anthropic_api_key: SecretStr = Field(validation_alias="ANTHROPIC_API_KEY")

    database_url: PostgresDsn = PostgresDsn(
        "postgresql+psycopg://raiyon:raiyon@localhost:5432/raiyon"
    )

    # Modèles — cf. PROJET.md §3.13 (Sonnet porte le dialogue, Haiku les tâches
    # fermées à sortie structurée).
    model_agent: str = "claude-sonnet-5"
    model_extraction: str = "claude-haiku-4-5-20251001"
    model_eval_client: str = "claude-haiku-4-5-20251001"

    # Zone de tolérance budget — cf. PROJET.md §3.10. Les produits situés entre
    # le budget et `budget * (1 + budget_tolerance)` sont rendus dans un champ
    # distinct, jamais mélangés au classement principal.
    budget_tolerance: float = Field(default=0.15, ge=0.0, le=0.5)

    # Garde-fou anti-boucle de la boucle d'agent — cf. PROJET.md §3.9. C'est une
    # protection technique, pas une règle d'expérience utilisateur.
    max_agent_iterations: int = Field(default=8, ge=1)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    app_env: Literal["dev", "test", "prod"] = "dev"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Rend la configuration du processus, construite une seule fois.

    Le cache est vidable par `get_settings.cache_clear()` — c'est ce dont les
    tests se servent pour isoler chaque cas.
    """
    # mypy synthétise un __init__ à partir des champs et réclame donc
    # `anthropic_api_key`. C'est faux ici : BaseSettings lit la valeur dans
    # l'environnement. L'absence de clé reste détectée — à l'exécution, par une
    # ValidationError (cf. tests/test_config.py).
    return Settings()  # type: ignore[call-arg]
