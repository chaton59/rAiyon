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

PROMPT_SYSTEME_PAR_DEFAUT = "systeme.v2"
"""La version de prompt servie quand rien n'est configuré. **Écrite ici et nulle part
ailleurs.**

Elle a d'abord été écrite deux fois — dans le champ ci-dessous et dans
`prompts.SYSTEME_PAR_DEFAUT` — et le jalon 3 de l'étape 13 a déplacé la seconde en
oubliant la première : la constante annonçait `systeme.v2` pendant que la configuration
servait `systeme.v1`, sans qu'aucun type ne s'en émeuve. `prompts.py` importe donc cette
valeur, et l'arbitrage qui l'a choisie est documenté là-bas, à côté de son usage.

Elle vit dans `config.py` parce que c'est **le défaut d'un champ de configuration**, et
que `config.py` est le point unique de lecture de l'environnement ; l'inverse créerait un
cycle, `prompts.py` important déjà `config.py`."""


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

    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    """**Optionnelle**, et déballée par `cle_api()` seule (étape 8, arbitrage 10).

    Elle était obligatoire au démarrage depuis l'étape 2 — « échouer tôt ». La décision
    était raisonnable tant que le pipeline appelait un modèle ; §3.4ter a supprimé ce
    seul appel, et `make seed`, `make seed-build` et `make calibrer` sont devenus du code
    déterministe qui réclamait une clé qu'il n'utilise jamais. Le principe ne change pas,
    son objet si : on échoue tôt **sur ce qui est réellement requis**, c'est-à-dire au
    premier appel API.

    *Alternative écartée — `SecretStr | None` déballé sur chaque site d'usage.* Elle
    répand un `| None` dans chaque appelant ; l'accesseur n'en laisse qu'un."""

    brave_search_api_key: SecretStr | None = Field(
        default=None, validation_alias="BRAVE_SEARCH_API_KEY"
    )
    """**Optionnelle**, et déballée par `cle_brave()` seule — même patron qu'`ANTHROPIC_API_KEY`.

    ⚠️ **Son absence n'est pas une panne, c'est le mode hors ligne** (§3.18). Sans elle,
    `search_reviews` sert le cache pré-chargé et refuse bruyamment ce qu'il n'y trouve pas ;
    aucune commande n'échoue au démarrage pour autant. C'est la différence avec
    `ANTHROPIC_API_KEY`, dont l'absence empêche `make api` d'exister.

    Sans préfixe `RAIYON_`, comme la clé Anthropic : c'est le nom que Brave documente."""

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

    # Régénérations accordées à un message dont le validateur de l'étape 9 a refusé le
    # texte — cf. PROJET.md §3.11 niveau 2. Une seule : au-delà, c'est le repli sur
    # template qui répond, parce qu'un modèle qui a manqué deux fois la même correction
    # n'a pas de raison de réussir la troisième, et que chaque tentative est un appel
    # API payé. `ge=0` : zéro est une valeur légitime — elle branche directement le
    # niveau 3, et c'est ce qui permettra à l'étape 12 de mesurer ce que la
    # régénération rattrape réellement.
    max_regenerations: int = Field(default=1, ge=0)

    # Version du prompt système en vigueur — cf. PROJET.md §3.14 et l'étape 13.
    # C'est une **sélection de fichier**, pas une interpolation : la valeur nomme un
    # fichier de `prompts/`, et rien n'entre dans le texte. La distinction n'est pas
    # rhétorique — §3.13 interdit qu'une variable entre dans le préfixe mis en cache,
    # et choisir lequel des trois fichiers envoyer laisse chacun identique octet pour
    # octet d'un appel à l'autre.
    #
    # Le motif refuse tout ce qui n'est pas un nom de fichier nu : sans lui,
    # `RAIYON_PROMPT_SYSTEME=../../etc/passwd` ferait lire un chemin arbitraire à
    # `prompts.charger()`, qui concatène sans vérifier.
    prompt_systeme: str = Field(
        default=PROMPT_SYSTEME_PAR_DEFAUT, pattern=r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$"
    )

    # Orchestration en vigueur — étape 15. `agent` est la boucle d'outils de l'étape 8
    # (§3.6) ; `machine` désignera la variante machine à états, mise en concurrence avec
    # elle sur les mêmes scénarios et le même tableau de métriques.
    #
    # ⚠️ **Le jalon 0 de l'étape 15 ajoute la variable et ne la consomme pas encore.**
    # `session.tour()` ne bascule sur rien, et c'est normal : il n'existe qu'une
    # orchestration au moment où ce champ est écrit. Il existe pour deux raisons, toutes
    # deux extérieures à la boucle — donner une source au champ `orchestration` de
    # l'en-tête de cassette, et éviter que le jalon qui écrira l'orchestrateur ait à
    # toucher `config.py` en même temps qu'il écrit du code d'exécution.
    #
    # Sans cette phrase, un relecteur qui cherche le `if` correspondant conclurait à un
    # branchement oublié.
    #
    # `Literal` plutôt qu'un motif : les deux valeurs sont **closes**, contrairement à
    # `prompt_systeme` qui nomme un fichier dont la liste s'allonge.
    orchestration: Literal["agent", "machine"] = "agent"

    validation: Literal["bloquante", "avertissement"] = "bloquante"
    """Ce que le validateur fait d'un grief — cf. PROJET.md §3.11, étape 25.

    * `bloquante` (défaut) : un grief déclenche une régénération, puis le repli sur
      template. C'est le niveau 2 de §3.11, et c'est le comportement depuis l'étape 9.
    * `avertissement` : **les règles tournent quand même**, produisent leurs griefs, les
      loguent et les écrivent dans `evenements_tour` — mais le texte part au client et
      aucune régénération n'est demandée.

    ⚠️ **`avertissement` ne désactive pas le validateur, il le rend observable sans le
    laisser agir.** La distinction est le tout : un validateur éteint ne produit aucune
    mesure, et c'est précisément la mesure qui a montré que deux des trois griefs de la
    campagne v3 étaient des défauts de règle et non des fautes du modèle.

    Le défaut reste `bloquante` **parce que la mesure le dit** : sur ces trois griefs, un
    seul était un vrai positif — une affirmation de connaissance générale qu'aucun outil ne
    fondait — et il justifie à lui seul de ne pas relâcher la garde. Le drapeau existe pour
    que l'arbitrage puisse se renverser sans commit, pas parce qu'il devrait l'être."""

    avis_ttl_heures: int = Field(default=24, ge=1)
    """Fraîcheur d'une ligne de `avis_produit` récupérée sur le web — étape 26.

    **24 h, et le chiffre vient d'une frontière, pas d'un taux de hit.** Ce cache sert la
    comparabilité de deux exécutions, pas l'économie d'appels : l'argument économique a été
    mesuré et il est faux — 81 recherches au pire par campagne, soit 0,40 $. Le TTL doit
    donc être plus long que l'écart entre les deux bras d'une comparaison, faute de quoi
    l'expiration tombe **au milieu de la mesure**. Une session de travail dure plus de
    quatre heures ; 24 h fait coïncider une génération de cache avec une journée.

    Le raisonnement complet est dans la docstring de `db.models.AvisProduit` — il vaut plus
    que le chiffre, parce que le chiffre se rediscute et le raisonnement non.

    `ge=1` : zéro n'est pas une valeur légitime ici, contrairement à `max_regenerations`.
    Il ferait périmer toute ligne récupérée à l'instant même, donc une récupération par
    recherche — pas un cache désactivé, un cache qui travaille pour rien. ⚠️ Il ne toucherait
    d'ailleurs **pas** les lignes `fabrique`, qui ne périment jamais : « TTL à zéro » ne
    veut même pas dire « pas de cache »."""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    """⚠️ **Déclarée depuis l'étape 2, et lue par personne jusqu'à l'étape 23.** Le dépôt
    n'appelait pas `structlog.configure()` : il tournait sur les défauts du paquet, qui ne
    filtrent rien. `raiyon.journal.configurer_journal()` la consomme désormais, et une
    variable de configuration cesse d'annoncer un effet qu'elle n'avait pas."""

    journal_jsonl: Path | None = None
    """Où écrire le journal JSONL, **en plus du terminal**. `None` : terminal seul.

    Un chemin relatif est résolu depuis le répertoire de lancement, comme tout le reste de
    la configuration. Le répertoire parent est créé s'il manque — un journal qui refuse de
    démarrer parce qu'un dossier n'existe pas ferait perdre précisément la session qu'on
    voulait observer."""

    app_env: Literal["dev", "test", "prod"] = "dev"
    """⚠️ **Depuis l'étape 23, elle décide aussi de l'existence des routes `/journal`.**
    Elles exposent des conversations entières : hors `dev`, elles rendent 404."""


def cle_brave() -> str | None:
    """La clé Brave, ou `None`. **Seul déballage, et il ne lève jamais.**

    ⚠️ **Contrairement à `cle_api()`, l'absence n'est pas une erreur de configuration.**
    Elle est un **mode de fonctionnement** : hors ligne, le sixième outil sert le cache et
    refuse le reste en le nommant. Lever ici obligerait chaque appelant à distinguer « pas
    de clé » de « clé invalide », et ferait échouer des commandes qui n'ont aucun besoin du
    réseau.

    Le `None` est donc la valeur de retour normale, et c'est l'appelant — un seul, celui qui
    construit le fournisseur — qui décide d'en faire un fournisseur ou rien.
    """
    cle = get_settings().brave_search_api_key
    return None if cle is None else cle.get_secret_value()


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
    # les champs sans défaut et il faut un `# type: ignore[call-arg]`.
    return Settings()


def cle_api() -> str:
    """La clé API, ou une `ConfigurationError` qui dit quoi faire. **Seul déballage.**

    Tout ce qui appelle l'API passe par ici. La conséquence est que le message d'absence
    est écrit une fois, qu'il nomme les commandes concernées, et qu'aucune autre partie
    du code n'a à connaître le fait que la clé puisse manquer.
    """
    cle = get_settings().anthropic_api_key
    if cle is None:
        raise ConfigurationError(
            "ANTHROPIC_API_KEY est absente, et cette commande appelle l'API Anthropic.\n"
            "La renseigner dans .env (voir .env.example) ou l'exporter dans le shell.\n"
            "Rappel : make seed, make seed-build et make calibrer n'en ont pas besoin — "
            "seules make chat, make api et make fumee appellent un modèle."
        )
    return cle.get_secret_value()
