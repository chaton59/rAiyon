"""Configuration typée du projet.

Point unique de lecture de l'environnement : aucune autre partie du code ne lit
`os.environ` ni ne contient de clé en dur. Toute nouvelle variable d'environnement
se déclare ici, avec son type et sa validation.
"""

import difflib
import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PREFIXE_ENV = "RAIYON_"
FICHIER_ENV = ".env"


class ConfigurationError(Exception):
    """Configuration invalide détectée avant la validation Pydantic.

    Sert au cas que Pydantic ne peut pas voir : une variable d'environnement
    dont le nom ne correspond à aucun champ. Pydantic l'ignore silencieusement
    (`extra="ignore"`), ce qui rend une faute de frappe indétectable.
    """


class Settings(BaseSettings):
    """Configuration du processus, lue depuis l'environnement puis depuis `.env`.

    Les variables portent le préfixe `RAIYON_` (par exemple
    `RAIYON_BUDGET_TOLERANCE`). Seule exception : `ANTHROPIC_API_KEY`, lue sans
    préfixe parce que c'est le nom conventionnel attendu par le SDK Anthropic.
    """

    model_config = SettingsConfigDict(
        env_file=FICHIER_ENV,
        env_prefix=PREFIXE_ENV,
        frozen=True,
        # `extra="forbid"` serait le réflexe, mais il est inutilisable ici :
        # combiné à `env_file` et à un `validation_alias`, il fait échouer la
        # validation de tous les champs lus depuis le fichier. Le contrôle des
        # noms est donc fait explicitement par `verifier_cles_inconnues()`.
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


def cles_reconnues() -> frozenset[str]:
    """Noms de variables d'environnement que `Settings` sait réellement consommer.

    Dérivé des champs, jamais écrit à la main : la liste ne peut pas diverger du
    modèle. Un champ portant un `validation_alias` est lu sous ce seul nom — le
    préfixe ne s'y applique pas. C'est pourquoi `ANTHROPIC_API_KEY` est accepté
    et `RAIYON_ANTHROPIC_API_KEY` ne l'est pas.
    """
    cles: set[str] = set()
    for nom, champ in Settings.model_fields.items():
        alias = champ.validation_alias
        if isinstance(alias, str):
            cles.add(alias)
        elif isinstance(alias, AliasChoices):
            cles.update(choix for choix in alias.choices if isinstance(choix, str))
        else:
            cles.add(f"{PREFIXE_ENV}{nom.upper()}")
    return frozenset(cles)


def _cles_du_fichier(chemin: Path) -> set[str]:
    """Noms de variables déclarés dans un fichier `.env`, valeurs non interprétées."""
    if not chemin.is_file():
        return set()
    cles: set[str] = set()
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        nue = ligne.strip().removeprefix("export ").strip()
        if not nue or nue.startswith("#") or "=" not in nue:
            continue
        cles.add(nue.split("=", 1)[0].strip())
    return cles


def verifier_cles_inconnues(
    env: Mapping[str, str] | None = None,
    chemin_env: Path | None = None,
) -> None:
    """Refuse toute variable `RAIYON_*` qui ne correspond à aucun champ.

    Sans ce contrôle, `RAIYON_BUDGET_TOLERANC=0.4` (un `E` manquant) laisse la
    tolérance à sa valeur par défaut sans le moindre signal. Sur une valeur qui
    porte un invariant produit (cf. PROJET.md §3.10), l'échec silencieux est le
    pire des comportements.

    Seul le préfixe du projet est inspecté : les variables tierces de la machine,
    y compris les `POSTGRES_*` que lit `docker-compose.yml`, ne sont pas
    concernées.
    """
    reconnues = cles_reconnues()
    presentes = set(os.environ if env is None else env)
    presentes |= _cles_du_fichier(Path(FICHIER_ENV) if chemin_env is None else chemin_env)

    inconnues = sorted(
        cle for cle in presentes if cle.startswith(PREFIXE_ENV) and cle not in reconnues
    )
    if not inconnues:
        return

    lignes = []
    for cle in inconnues:
        proche = difflib.get_close_matches(cle, sorted(reconnues), n=1, cutoff=0.6)
        suggestion = f"  — vouliez-vous dire {proche[0]} ?" if proche else ""
        lignes.append(f"  - {cle}{suggestion}")

    raise ConfigurationError(
        "Variable(s) d'environnement non reconnue(s) :\n"
        + "\n".join(lignes)
        + "\n\nElles auraient été ignorées en silence. Corrigez le nom, ou "
        "retirez-les de l'environnement et de "
        f"{FICHIER_ENV}.\nNoms acceptés : " + ", ".join(sorted(reconnues))
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Rend la configuration du processus, construite une seule fois.

    Le cache est vidable par `get_settings.cache_clear()` — c'est ce dont les
    tests se servent pour isoler chaque cas.
    """
    verifier_cles_inconnues()
    # Aucun argument : `BaseSettings` lit tout dans l'environnement. Le plugin
    # mypy de Pydantic sait que cet appel est légitime — sans lui, mypy réclame
    # `anthropic_api_key` et il faut un `# type: ignore[call-arg]`.
    # L'absence de clé reste détectée à l'exécution, par une ValidationError
    # (cf. tests/test_config.py).
    return Settings()
