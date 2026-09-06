"""Chercher des avis : le cache d'abord, le fournisseur ensuite — s'il existe.

Le cœur du sixième outil, **sans dépendance à la couche outils** : cette fonction prend un
dépôt, un fournisseur optionnel et une requête, et rend ce qu'elle a trouvé avec l'état du
cache. C'est `raiyon.tools.outils` qui en fait un `tool_result`, et `raiyon.tools.repartiteur`
qui pose la borne d'appels.

Le découpage suit §3.16 : ce qui décide est ici, testable avec un dépôt en mémoire ; ce qui
parle au réseau est derrière `Fournisseur`, et n'existe pas encore.
"""

from dataclasses import dataclass
from datetime import datetime

import structlog

from raiyon.avis.cache import Avis, DepotAvis, EtatCache
from raiyon.avis.fournisseur import Fournisseur
from raiyon.avis.normalisation import normaliser

logueur = structlog.get_logger(__name__)

RESULTATS_MAX = 3
"""Combien d'avis un `tool_result` porte au plus.

⚠️ **Une borne de contexte, pas une borne de pertinence.** Chaque avis fait entrer du
texte de tiers dans la fenêtre : trois extraits de 500 caractères font ~375 jetons, ce qui
reste petit devant un historique et laisse au modèle de quoi voir une convergence — un
seul avis ne dit pas si un reproche est isolé ou général, et c'est exactement ce qu'on
demande au web. Au-delà de trois, on paie du jeton et de la surface d'injection pour des
pages de moins en moins pertinentes.

À rediscuter sur les longueurs réelles, une fois qu'il en existe."""


class AvisHorsLigne(Exception):
    """Le cache n'a pas la clé et aucun fournisseur n'existe. **Un miss bruyant.**

    Porte la clé normalisée : c'est elle qu'il faut écrire dans `data/seed/avis.jsonl`
    pour que le scénario cesse de mesurer autre chose que ce qu'il annonce. Le message est
    lu par un humain qui répare une campagne, pas par le modèle — `repartiteur` le
    retraduit en `OutilRefuse` avant qu'il n'atteigne la conversation.

    ⚠️ **Elle porte aussi la formulation d'origine, et ce n'est pas de la décoration**
    (étape 28). La clé normalisée dit quoi écrire ; la formulation dit **ce que le modèle a
    réellement tapé**, et c'est elle qui décidera un jour du seuil d'un appariement par
    recouvrement. Sans les deux, on saurait qu'un miss a eu lieu sans savoir de combien de
    mots on est passé à côté — donc sans pouvoir calibrer autre chose qu'à l'intuition.
    """

    def __init__(self, requete_normalisee: str, requete: str) -> None:
        super().__init__(requete_normalisee)
        self.requete_normalisee = requete_normalisee
        self.requete = requete


@dataclass(frozen=True, slots=True)
class Trouvaille:
    """Ce que la recherche a rendu, et **par quel chemin**.

    `etat_cache` n'est pas de la décoration : c'est ce que le journal trace (étape 27) et
    ce qui distingue un trou du seed d'une frontière de TTL. Voir `raiyon.avis.cache`.
    """

    requete_normalisee: str
    avis: tuple[Avis, ...]
    etat_cache: EtatCache
    latence_ms: int

    @property
    def depuis_le_cache(self) -> bool:
        """Vrai quand rien n'a été récupéré. C'est le `hit` du journal."""
        return self.etat_cache is EtatCache.TROUVE


class RequeteVide(Exception):
    """La requête ne produit aucune clé — « ??? » n'est pas une recherche.

    Refusée ici plutôt qu'en base : la contrainte `requete_non_vide` est le filet, mais
    elle rendrait un message de contrainte SQL là où le modèle a besoin de savoir quoi
    corriger.
    """


def chercher_des_avis(
    requete: str,
    *,
    depot: DepotAvis,
    fournisseur: Fournisseur | None,
    maintenant: datetime,
    limite: int = RESULTATS_MAX,
) -> Trouvaille:
    """Le cache d'abord. Le fournisseur seulement s'il y a un miss **et** un fournisseur.

    ⚠️ **Un hit n'écrit rien.** C'est ce qui rend une campagne hors ligne idempotente : la
    table sort d'une passe exactement comme elle y est entrée, donc deux passes comparées
    ont bien vu la même chose. Un cache qui se réécrirait à chaque lecture ferait dériver
    `recupere_le` et, à terme, la frontière de péremption au milieu d'une comparaison.

    Sur un miss hors ligne, lève `AvisHorsLigne` — voir `raiyon.avis.fournisseur` pour
    pourquoi c'est un refus et non un résultat vide.
    """
    cle = normaliser(requete)
    if not cle:
        raise RequeteVide(requete)

    lecture = depot.lire(cle, maintenant=maintenant)
    if lecture.utilisable:
        logueur.info(
            "avis.cache_lu",
            requete=cle,
            resultats=len(lecture.avis),
            etat=lecture.etat.value,
        )
        return Trouvaille(cle, lecture.avis, lecture.etat, latence_ms=0)

    if fournisseur is None:
        # 🔴 Le miss bruyant. La ligne porte **les deux** formes : la clé dit quoi écrire
        # dans le seed, la formulation dit ce que le modèle a tapé. C'est le jeu de données
        # du seuil de recouvrement (étape 28), et il ne se collecte qu'ici.
        logueur.error(
            "avis.hors_ligne",
            requete=cle,
            formulation=requete,
            etat=lecture.etat.value,
            consequence="refus d'outil — la fixture manque dans data/seed/avis.jsonl",
        )
        raise AvisHorsLigne(cle, requete)

    depart = _horloge()
    recuperes = fournisseur.chercher(requete, limite=limite)
    latence = _horloge() - depart
    ranges = depot.ecrire(cle, [_sous_la_cle(un_avis, cle) for un_avis in recuperes[:limite]])
    logueur.info(
        "avis.recupere",
        requete=cle,
        resultats=len(ranges),
        etat=lecture.etat.value,
        latence_ms=latence,
    )
    return Trouvaille(cle, ranges, lecture.etat, latence_ms=latence)


def _sous_la_cle(avis: Avis, cle: str) -> Avis:
    """L'avis rangé sous la clé du groupe qu'on écrit.

    ⚠️ **Ce n'est pas de la précaution défensive, c'est le contrat de `ecrire()`.** Un
    fournisseur rend des avis dont la `requete_normalisee` est ce qu'il veut — il a reçu la
    requête **libre**, pas la clé. Les ranger sans les réétiqueter lèverait `CleIncoherente`,
    et c'est la couche qui connaît la clé qui doit la poser.
    """
    from dataclasses import replace

    return replace(avis, requete_normalisee=cle)


def _horloge() -> int:
    """Millisecondes monotones. Isolé pour être remplaçable dans un test."""
    import time

    return time.monotonic_ns() // 1_000_000
