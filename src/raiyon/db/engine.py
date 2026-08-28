"""Moteur SQLAlchemy et portée de session.

**Le moteur est synchrone, et c'est un arbitrage.** Le moteur de matching (étape 6)
et le pipeline (étape 5) restent ainsi des fonctions pures, testables sans boucle
asyncio - ce qui est la condition du critère d'acceptation nº5 (« la suite tourne
hors ligne »). L'API FastAPI de l'étape 10 enveloppera ses appels base dans
`asyncio.to_thread` : un saut de thread par requête, contre une contamination
`async` de toute la couche métier. Alternative écartée : un engine asyncio, qui
aurait imposé `async def` jusque dans les tests du moteur.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from raiyon.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Rend le moteur du processus, construit une seule fois.

    `pool_pre_ping` coûte un aller-retour par emprunt de connexion et évite l'erreur
    classique d'une connexion coupée par le redémarrage du conteneur Postgres, que
    le pool croit encore vivante.
    """
    return create_engine(str(get_settings().database_url), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    """Fabrique de sessions.

    `expire_on_commit=False` : sans ce réglage, lire un attribut après un commit
    déclenche un SELECT, et lever la même valeur hors de la portée de session lève.
    Or la couche outils de l'étape 7 rend des produits que l'agent lit après coup.
    """
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Ouvre une session, commit à la sortie, rollback à la moindre exception.

    Écrit une fois ici pour que le `rollback` ne puisse pas être oublié ailleurs :
    une session laissée en transaction avortée fait échouer toutes les requêtes
    suivantes avec une erreur qui ne désigne pas la vraie cause.
    """
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
