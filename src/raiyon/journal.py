"""La configuration de `structlog` : le terminal comme avant, **et un fichier JSONL**.

### Ce que ça corrige, et ce n'est pas du confort

Le dépôt n'a jamais appelé `structlog.configure()`. Il tournait donc sur les défauts du
paquet — ce qui rendait bien un terminal lisible, et **rien d'autre** : les logs
s'évaporaient à la fermeture du shell. Trois conséquences constatées :

* `RAIYON_LOG_LEVEL` était déclarée dans `Settings` et **n'était lue par personne**. Une
  variable de configuration sans consommateur est un mensonge de `.env.example`.
* Le correctif de l'étape 12 (`boucle.reponse_vide`) a demandé de relire des cassettes à
  la main, parce que le `WARNING` qui nommait le défaut était parti avec le terminal.
* Une campagne d'éval de deux cents appels ne laissait derrière elle que son rapport.

### Deux sorties, un seul chemin de processeurs

Le fichier n'est pas un second logueur : c'est un **processeur** posé avant le rendu
terminal, qui sérialise l'événement en une ligne JSON et le laisse passer inchangé. Le
terminal rend donc exactement ce qu'il rendait, et le fichier voit exactement ce que le
terminal voit — y compris les champs que le rendu console abrège.

*Alternative écartée — passer par `logging` de la bibliothèque standard et deux handlers.*
C'est la façon canonique, et elle ferait entrer une seconde configuration (niveaux,
formatteurs, propagation) pour un besoin qui tient en dix lignes. Le dépôt n'utilise
`logging` nulle part ; l'y faire entrer par la porte du journal serait payer une
abstraction qu'aucun autre module ne consomme.

### La ligne JSONL est écrite **entière ou pas du tout**

Un `write()` unique par ligne, sous verrou, sur un fichier ouvert en ajout et vidé à
chaque écriture. C'est ce qui fait qu'un `tail -f` pendant une campagne ne rend jamais une
demi-ligne, et qu'un `jq` sur le fichier d'une campagne interrompue lit tout ce qui a été
écrit avant l'interruption.

⚠️ **Une erreur d'écriture ne fait pas échouer l'appelant.** Un disque plein ne doit pas
interrompre une conversation en cours pour un journal ; l'échec part sur `stderr`, une
fois, et le processus continue sans fichier. L'inverse ferait du journal une dépendance
plus dure que la base de données.

### Ce que le fichier contient, et ce qu'il ne contient pas

Il contient ce que les logs contiennent déjà : des événements nommés, avec leurs champs.
Il ne contient **pas** de prose de conversation — celle-là vit en base, et le dashboard de
l'étape 23 la lit là-bas. Le fichier est un journal d'exploitation, pas une seconde
persistance.
"""

import json
import sys
import threading
from pathlib import Path
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

NIVEAUX = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
"""Les quatre valeurs du `Literal` de `Settings.log_level`, en numérotation `logging`.

Écrites ici plutôt que dérivées de `logging.getLevelName()` : `structlog` attend un entier,
et un aller-retour par la bibliothèque standard ferait dépendre le journal d'un module que
le reste du dépôt n'importe pas."""


class EcrivainJSONL:
    """Le processeur qui double le terminal vers un fichier. **Il ne modifie rien.**

    Il rend son `event_dict` tel qu'il l'a reçu : le rendu console qui le suit dans la
    chaîne doit voir exactement ce qu'il aurait vu sans lui. Un processeur qui consomme des
    clés — ce que fait le rendu final — ne peut pas être posé ici.
    """

    def __init__(self, chemin: Path) -> None:
        self._chemin = chemin
        self._verrou = threading.Lock()
        self._muet = False
        """Vrai après un premier échec d'écriture. On ne répète pas la plainte à chaque
        ligne : un disque plein produirait alors plus de bruit que le journal lui-même."""

        chemin.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, _: WrappedLogger, __: str, evenement: EventDict) -> EventDict:
        if self._muet:
            return evenement
        ligne = json.dumps(
            # Une copie, jamais l'original : le rendu console qui suit dans la chaîne
            # **consomme** des clés (`event`, `timestamp`, `level`) en les retirant du
            # dictionnaire. Écrire sur la même instance marcherait par accident tant que
            # l'écrivain passe en premier, et casserait le jour où l'ordre change.
            dict(evenement),
            ensure_ascii=False,
            # Une valeur non sérialisable (un `Decimal`, un `UUID`, une exception) devient
            # sa chaîne plutôt que de faire lever le journal. Un log qui casse le processus
            # qu'il observe est pire que le log manquant.
            default=str,
        )
        try:
            with self._verrou, self._chemin.open("a", encoding="utf-8") as fichier:
                fichier.write(ligne + "\n")
        except OSError as erreur:  # pragma: no cover — disque plein, droits, montage perdu
            self._muet = True
            print(
                f"⚠️  journal JSONL désactivé ({self._chemin}) : {erreur}",
                file=sys.stderr,
            )
        return evenement


def processeurs(chemin: Path | None) -> list[Any]:
    """La chaîne, dans l'ordre. Le rendu console est **toujours** le dernier.

    L'horodatage vient en tête parce que c'est l'instant de l'événement, pas celui de son
    écriture — un fichier relu après coup ne peut pas reconstituer la différence.
    """
    chaine: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.processors.StackInfoRenderer(),
        # `format_exc_info` avant l'écrivain : sans lui, un `logueur.exception()` mettrait
        # un objet exception dans le JSON, que `default=str` réduirait à son message — la
        # trace, qui est l'information, serait perdue.
        structlog.processors.format_exc_info,
    ]
    if chemin is not None:
        chaine.append(EcrivainJSONL(chemin))
    chaine.append(structlog.dev.ConsoleRenderer())
    return chaine


def configurer_journal(*, niveau: str | None = None, chemin: Path | None = None) -> Path | None:
    """Configure `structlog` pour ce processus et rend le chemin retenu, s'il y en a un.

    Les deux arguments valent `None` pour « ce que la configuration dit », et sont là pour
    ce que l'environnement ne peut pas faire : un test qui vise un fichier temporaire, et
    un script qui force un niveau depuis sa ligne de commande.

    ⚠️ **Appelée par les points d'entrée, jamais à l'import d'un module de `src/`.** Une
    configuration posée à l'import s'appliquerait à `pytest`, qui a la sienne, et le
    `capture_logs()` de trois fichiers de tests cesserait de voir ce qu'il attend.
    """
    from raiyon.config import get_settings

    reglages = get_settings()
    retenu = chemin if chemin is not None else reglages.journal_jsonl
    structlog.configure(
        processors=processeurs(retenu),
        wrapper_class=structlog.make_filtering_bound_logger(
            NIVEAUX[niveau if niveau is not None else reglages.log_level]
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        # Le premier `get_logger()` fige la configuration ; sans cela, un point d'entrée
        # qui importe un module avant de configurer garderait les défauts du paquet.
        cache_logger_on_first_use=False,
    )
    return retenu
