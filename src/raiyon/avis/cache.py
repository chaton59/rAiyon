"""Lire et écrire le cache d'avis. **La règle de péremption est pure ; le SQL est à part.**

Même découpage que le moteur de matching (§3.16) : ce qui décide se teste sans conteneur,
ce qui interroge Postgres vit derrière un `Protocol`. `est_perime()` et `tronquer_extrait()`
tournent dans `make check` ; `DepotAvisSql` demande une base et vit dans `make test-int`.

---

### Trois états, pas deux

Un cache se raconte d'habitude en hit / miss. Il en faut **trois** ici, parce que le
journal doit pouvoir répondre à deux questions différentes :

| État | Ce qu'il dit |
|---|---|
| `TROUVE` | la clé est là et fraîche — l'outil sert le cache |
| `ABSENT` | la clé n'a jamais été remplie |
| `PERIME` | la clé a été remplie, et sa fraîcheur est passée |

`ABSENT` et `PERIME` déclenchent tous deux une récupération, donc les confondre serait
tentant. Ils ne disent pourtant pas la même chose d'une campagne : un `ABSENT` sur un
scénario d'éval est un **trou du seed** — la requête que le modèle a formulée n'a pas
d'entrée fabriquée, et le scénario mesure autre chose que ce qu'il annonce. Un `PERIME`
est une frontière de TTL, donc un réglage. Le premier se corrige en écrivant une fixture,
le second en discutant le TTL. Un compteur unique les mélangerait, et c'est précisément
le mélange que l'étape 26 refuse.

### L'écriture concurrente : la contrainte d'unicité tient lieu de verrou

Deux processus qui remplissent la même clé au même instant, c'est le cas nominal d'une
campagne parallèle, pas un cas d'école. La table porte `UNIQUE (requete_normalisee, url)`,
et `ecrire()` s'en sert plutôt que de poser un verrou : le second écrivain se heurte à la
contrainte, **relit**, et rend ce que le premier a écrit.

*Alternative écartée — un verrou consultatif Postgres (`pg_advisory_xact_lock`).* Il
sérialiserait proprement, au prix d'un mécanisme de plus à comprendre et d'un chemin où
un processus attend. Ici il n'y a rien à attendre : les deux écrivains ont récupéré la
même chose, donc le perdant n'a rien à perdre.

*Alternative écartée — `ON CONFLICT DO UPDATE` ligne à ligne.* Elle évite l'erreur, et
elle laisse **fusionner deux récupérations** : si la première a rendu `{a, b, c}` et la
seconde `{a, b, d}`, la table finit avec `{a, b, c, d}` — un groupe qu'aucune recherche
n'a jamais rendu. Un cache dont le contenu n'a jamais existé côté fournisseur ne sert plus
à comparer quoi que ce soit, ce qui est sa seule raison d'être.

Le groupe est donc **remplacé en bloc** : `DELETE` de la clé puis `INSERT`, dans la
transaction de l'appelant. Ce que le cache rend a été rendu ensemble.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

import structlog
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from raiyon.db.models import EXTRAIT_MAX_CARACTERES, AvisProduit

logueur = structlog.get_logger(__name__)

SOURCE_FABRIQUE = "fabrique"
"""La provenance qui ne périme pas. Écrite ici **et** dans `SOURCES_AVIS`, parce que le
schéma déclare le vocabulaire et que cette couche déclare celle des deux qui a un
comportement à part. Un test vérifie que la valeur appartient bien à la liste du schéma."""

MARQUE_DE_TRONCATURE = " […]"
"""Ce qui est ajouté quand l'extrait a été coupé. **Visible pour le modèle**, exprès : un
extrait tronqué sans marque se lit comme une phrase finie, et le modèle en tirerait une
conclusion que la page ne porte pas."""


class CleIncoherente(Exception):
    """Une écriture range sous une clé des avis qui en portent une autre.

    ⚠️ **Une faute de programmation, jamais une donnée invalide.** Aucune entrée
    utilisateur ni aucun résultat de fournisseur ne peut la produire : la clé du groupe et
    celle des avis sortent toutes deux de `normaliser()`, appelée par le même appelant. Se
    rattraper serait donc masquer un défaut de code, et le masquer là où il corrompt
    silencieusement deux groupes de cache d'un seul appel.
    """


class EtatCache(StrEnum):
    """Ce que la lecture a trouvé. Voir la docstring du module pour les trois états."""

    TROUVE = "trouve"
    ABSENT = "absent"
    PERIME = "perime"


@dataclass(frozen=True, slots=True)
class Avis:
    """Un résultat web. **Aucun champ n'est produit par un modèle de langage.**

    `recupere_le` est obligatoire et sans défaut : une ligne de cache sans date n'a pas de
    fraîcheur, donc pas de péremption calculable, et le défaut serait toujours faux.
    """

    requete_normalisee: str
    url: str
    titre: str
    extrait: str
    source: str
    recupere_le: datetime
    produit_id: str | None = None


@dataclass(frozen=True, slots=True)
class Lecture:
    """Ce que le cache rend : des avis, et **pourquoi** il en rend ou non.

    `avis` est vide dès que `etat` n'est pas `TROUVE`. Les deux champs pourraient donc
    sembler redondants ; ils ne le sont pas, puisque `TROUVE` avec zéro avis est un état
    légitime — une recherche a eu lieu et n'a rien rendu, ce qui est un fait à mettre en
    cache comme un autre. Sans lui, une requête sans résultat serait refaite indéfiniment.
    """

    avis: tuple[Avis, ...]
    etat: EtatCache

    @property
    def utilisable(self) -> bool:
        """Vrai quand l'appelant peut servir ce contenu sans rien récupérer."""
        return self.etat is EtatCache.TROUVE


class DepotAvis(Protocol):
    """La porte du cache. En `Protocol` pour la même raison que `DepotProduits` (§3.16).

    ⚠️ **Aucune méthode ne récupère quoi que ce soit.** Un dépôt lit et écrit ; il ne sait
    pas qu'un fournisseur existe. C'est ce qui fait qu'un dépôt rempli par le seed est
    indiscernable d'un dépôt rempli par une recherche, et donc qu'une campagne tourne hors
    ligne sans code de branchement.
    """

    def lire(self, requete_normalisee: str, *, maintenant: datetime) -> Lecture: ...

    def ecrire(self, requete_normalisee: str, avis: Sequence[Avis]) -> tuple[Avis, ...]: ...


def est_perime(avis: Avis, *, maintenant: datetime, ttl: timedelta) -> bool:
    """Cette ligne a-t-elle passé sa fraîcheur ? **Pur, et c'est la règle entière.**

    ⚠️ **Une ligne `fabrique` ne périme jamais.** Elle n'a pas été prise sur le web à un
    instant : elle a été écrite à la main pour que les mesures soient reproductibles. Lui
    appliquer un TTL ferait expirer le seed vingt-quatre heures après `make seed`, et les
    campagnes se mettraient à ne plus rien trouver — sans erreur, sans message, un jour
    plus tard. C'est l'exception qui rend la décision « les mesures ne sortent jamais sur
    le réseau » tenable au-delà du premier jour.

    La comparaison est **stricte** : une ligne exactement à `recupere_le + ttl` est encore
    fraîche. Le bord doit tomber d'un côté, et le côté généreux évite qu'une campagne
    lancée à la seconde près se comporte autrement qu'une lancée une seconde plus tôt.
    """
    if avis.source == SOURCE_FABRIQUE:
        return False
    return maintenant > avis.recupere_le + ttl


def tronquer_extrait(texte: str, *, maximum: int = EXTRAIT_MAX_CARACTERES) -> str:
    """L'extrait borné, **marqué s'il a été coupé**. Pur.

    On tronque plutôt qu'on ne rejette : perdre un résultat entier parce que la page est
    bavarde serait échanger un défaut visible contre un trou invisible. La marque part
    dans le budget, sans quoi la sortie dépasserait la borne d'exactement sa longueur —
    une borne qu'on peut dépasser n'est pas une borne.
    """
    if len(texte) <= maximum:
        return texte
    return texte[: maximum - len(MARQUE_DE_TRONCATURE)].rstrip() + MARQUE_DE_TRONCATURE


class DepotAvisSql:
    """Le cache sur Postgres. Il **ne commite pas** : la transaction est à l'appelant.

    Même contrat que `DepotSql` : la couche de persistance de ce dépôt écrit dans la
    session qu'on lui donne, et c'est `session.tour()` — ou un test — qui décide quand
    valider. C'est ce qui permet à l'écriture du cache d'hériter de l'atomicité du tour.
    """

    def __init__(self, session: Session, *, ttl: timedelta) -> None:
        self._session = session
        self._ttl = ttl

    def lire(self, requete_normalisee: str, *, maintenant: datetime) -> Lecture:
        """Le groupe rangé sous cette clé, ou pourquoi il n'est pas servi.

        ⚠️ **Le groupe périme en bloc.** Si une seule ligne est périmée, la lecture rend
        `PERIME` et **rien** — servir les lignes fraîches d'un groupe partiellement expiré
        rendrait un sous-ensemble qu'aucune recherche n'a jamais rendu, ce qui est
        exactement ce que le remplacement en bloc de `ecrire()` évite par ailleurs. Les
        lignes d'un groupe partagent leur `recupere_le` de toute façon ; le cas ne se
        produit qu'après une écriture concurrente perdue, et il se tranche du côté sûr.
        """
        lignes = self._groupe(requete_normalisee)
        if not lignes:
            return Lecture((), EtatCache.ABSENT)
        avis = tuple(_depuis_ligne(ligne) for ligne in lignes)
        if any(est_perime(un_avis, maintenant=maintenant, ttl=self._ttl) for un_avis in avis):
            return Lecture((), EtatCache.PERIME)
        return Lecture(avis, EtatCache.TROUVE)

    def ecrire(self, requete_normalisee: str, avis: Sequence[Avis]) -> tuple[Avis, ...]:
        """Remplace le groupe. Rend ce qui est en cache après coup — pas ce qu'on a passé.

        La distinction est le tout du cas concurrent : quand un autre processus a rempli la
        même clé entre-temps, la contrainte d'unicité rejette l'insertion, et **c'est le
        contenu de l'autre qui est rendu**. Un appelant qui supposerait récupérer ses
        propres lignes servirait un contenu absent de la base.

        ⚠️ **Chaque avis doit porter la clé qu'on remplace, et c'est vérifié.** Sans cette
        garde, `ecrire("k1", [avis_sous_k2])` supprime le groupe `k1` et écrit sous `k2` :
        deux groupes corrompus d'un seul appel, et aucune contrainte SQL ne s'y oppose,
        puisque chaque ligne prise isolément est valide. C'est exactement la fusion que le
        remplacement en bloc existe pour empêcher, entrée par la porte de l'appelant.
        Trouvé par un test qui visait autre chose — voir
        `test_deux_cles_ne_se_melangent_pas`.
        """
        etrangers = sorted(
            {
                un_avis.requete_normalisee
                for un_avis in avis
                if un_avis.requete_normalisee != requete_normalisee
            }
        )
        if etrangers:
            raise CleIncoherente(
                f"écriture sous « {requete_normalisee} » d'avis portant {etrangers}"
            )
        point = self._session.begin_nested()
        try:
            self._session.execute(
                delete(AvisProduit).where(AvisProduit.requete_normalisee == requete_normalisee)
            )
            self._session.add_all(vers_ligne(un_avis) for un_avis in avis)
            self._session.flush()
        except IntegrityError:
            point.rollback()
            # ⚠️ Le `rollback` du point de sauvegarde a défait notre `DELETE` **et** notre
            # `INSERT` : ce qui reste en base est ce que l'autre écrivain a validé. On le
            # relit plutôt que de rejouer, parce que rejouer relancerait la même course.
            logueur.info(
                "avis.ecriture_concurrente",
                requete=requete_normalisee,
                consequence="l'autre écrivain a gagné, son contenu est relu et rendu",
            )
            return tuple(_depuis_ligne(ligne) for ligne in self._groupe(requete_normalisee))
        point.commit()
        return tuple(avis)

    def _groupe(self, requete_normalisee: str) -> Sequence[AvisProduit]:
        """Les lignes de cette clé, dans un ordre stable — par URL, jamais par `id`.

        L'`id` est une séquence : deux chargements du même seed rendraient le même contenu
        dans un ordre différent, et une campagne comparée à une autre verrait des résultats
        permutés sans que rien n'ait bougé.
        """
        requete = (
            select(AvisProduit)
            .where(AvisProduit.requete_normalisee == requete_normalisee)
            .order_by(AvisProduit.url)
        )
        return list(self._session.scalars(requete))


def _depuis_ligne(ligne: AvisProduit) -> Avis:
    """La ligne SQLAlchemy vers le type du domaine. Une seule direction, un seul endroit."""
    return Avis(
        requete_normalisee=ligne.requete_normalisee,
        url=ligne.url,
        titre=ligne.titre,
        extrait=ligne.extrait,
        source=ligne.source,
        recupere_le=ligne.recupere_le,
        produit_id=ligne.produit_id,
    )


def vers_ligne(avis: Avis) -> AvisProduit:
    """Le type du domaine vers la ligne. **L'extrait est borné ici**, pas chez l'appelant.

    Le mettre à la porte de la table plutôt que dans le fournisseur fait que la borne tient
    quelle que soit la provenance — un seed écrit à la main la respecte comme une
    récupération réseau, et la contrainte SQL n'a jamais à trancher.
    """
    return AvisProduit(
        requete_normalisee=avis.requete_normalisee,
        produit_id=avis.produit_id,
        url=avis.url,
        titre=avis.titre,
        extrait=tronquer_extrait(avis.extrait),
        source=avis.source,
        recupere_le=avis.recupere_le,
    )
