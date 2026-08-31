"""Un tour à la fois par session — un verrou consultatif Postgres, à portée de transaction.

### Pourquoi pas un `dict` en mémoire (arbitrage D)

**Le verrou en mémoire est interdit par une décision déjà écrite.** §3.12 justifie la
persistance des sessions par « autorise le multi-worker » ; un dictionnaire de verrous par
processus rendrait cette phrase fausse dès `uvicorn --workers 2`, et le défaut serait
invisible en développement — un seul worker, donc un seul dictionnaire.

### Pourquoi `pg_try_advisory_xact_lock`, et sur **la** session du tour

Le verrou est pris sur la **même `Session` SQLAlchemy** que celle qui servira le tour, et
**avant** `session.tour()`. `tour()` commite exactement une fois, en fin de tour : la
portée `xact` du verrou coïncide donc au caractère près avec la portée du tour, et il n'y
a **aucune libération à oublier** — ni sur le chemin nominal, ni sur une exception, ni sur
une déconnexion client, où le `rollback()` du `finally` le relâche tout autant.

⚠️ **Un verrou pris sur une autre connexion que celle qui écrit ne sert à rien.** Le
vérifier par relecture ne prouve rien : c'est un test d'intégration à deux tours
concurrents qui le constate.

*Alternative écartée — `SELECT … FOR UPDATE NOWAIT` sur la ligne de session.* Même effet,
mais elle verrouille une ligne qu'on écrit de toute façon, et son message d'erreur parle
de la ligne, pas du tour. Le verrou consultatif dit ce qu'il protège.

### La clé : 64 bits d'un UUID, et la collision est tarifée

`pg_try_advisory_xact_lock` prend un `bigint`. Un UUID en fait 128 : on garde les huit
premiers octets, lus en entier signé.

Deux sessions distinctes peuvent donc, en théorie, partager une clé. La probabilité est
celle d'un anniversaire sur 2⁶⁴ — négligeable devant tout ce que ce projet manipule — et
sa **conséquence** est bénigne : deux conversations sans rapport ne pourraient pas tourner
en même temps, et la seconde recevrait un 409 qu'un simple renvoi résout. Aucun risque de
corruption : le verrou ne garde pas une donnée, il sérialise un tour.
"""

import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

logueur = structlog.get_logger(__name__)

_VERROU = text("SELECT pg_try_advisory_xact_lock(:cle)")


def cle_de(identifiant: uuid.UUID) -> int:
    """Les 64 premiers bits de l'UUID, en entier signé — ce que Postgres attend."""
    return int.from_bytes(identifiant.bytes[:8], "big", signed=True)


def verrouiller_le_tour(base: Session, identifiant: uuid.UUID) -> bool:
    """Prend le verrou du tour, ou rend `False` **sans attendre**.

    `try` et non l'attente bloquante : un second tour qui patienterait tiendrait une
    connexion et une requête HTTP ouvertes pendant tout le premier, pour finir par servir
    une réponse que le client n'attend plus. Un 409 immédiat dit la vérité — ce tour-là
    n'aura pas lieu.
    """
    obtenu = bool(base.scalar(_VERROU, {"cle": cle_de(identifiant)}))
    if not obtenu:
        logueur.info("api.tour_deja_en_cours", session_id=str(identifiant))
    return obtenu
