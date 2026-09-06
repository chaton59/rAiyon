"""Le fournisseur Brave — **le seul module du dépôt qui sorte sur le réseau**.

Dernière pièce du sixième outil, et elle se branche derrière le `Protocol` sans qu'aucune
ligne d'appelant ne change : tout ce qui l'entoure — le cache, l'encadrement, l'exclusion
du `ContexteFourni`, la borne d'appels, le journal — a été construit et mesuré **avant**
elle, sur le cache pré-chargé.

---

### ⚠️ Ce module est le seul, et c'est une propriété tenue par un test

`tests/avis/test_isolation_reseau.py` vérifie qu'aucun **autre** module de `raiyon.avis` ne
charge de client HTTP, et `tests/avis/test_hors_ligne.py` vérifie qu'un chemin de campagne
n'en ouvre pas à l'exécution. Les deux ensemble disent : le réseau est joignable **ici**,
et nulle part ailleurs.

### La clé ne sort jamais d'ici

Elle est lue une fois par `cle_brave()`, posée dans un en-tête, et **n'apparaît dans aucun
log, aucun message d'erreur, aucune trace**. C'est pour cela que `_erreur_propre()` existe :
une exception `httpx` porte son `Request`, donc ses en-têtes, donc la clé — et une trace
d'exception non filtrée est le chemin le plus court d'un secret vers un fichier de log.
Aucune exception de `httpx` ne traverse ce module telle quelle.

### Ce qu'un résultat Brave devient

Le `Protocol` demande des `Avis` **déjà bornés**, pas une réponse d'API : la conversion vit
donc ici, et le jour d'un changement de fournisseur c'est ce fichier qu'on remplace, pas la
couche outils. Trois champs seulement sont retenus — `title`, `url`, `description` — parce
que ce sont les trois que `avis_produit` porte, et qu'un champ stocké sans lecteur est un
champ qui diverge.

### ⚠️ Ce que Brave rend n'est pas toujours un avis — observé, non corrigé

Premier tir réel, requête `avis MSI MAG 274CQF`, trois résultats : une fiche marchand
annonçant « 22 avis », une page de test, et un comparateur qui dit littéralement **« Aucun
avis n'a encore été déposé pour ce produit »**. Un moteur rend des pages **à propos**
d'avis, pas nécessairement des avis.

**Rien dans ce module ne distingue les deux, et rien ne le fera.** Trancher demanderait
d'encoder un jugement sémantique — « cette page contient-elle des opinions ? » — c'est-à-dire
exactement ce qui a été refusé pour la fourchette du guillemet (§7) et pour l'assainissement
qui « ne juge rien du contenu ». Une heuristique locale sur du texte libre n'en est pas
capable honnêtement, et une qui prétendrait l'être serait pire que son absence.

Ce qui a été observé, en revanche : le modèle **n'a pas relayé le vide**, sans qu'on le lui
dise. Ce n'est pas une garantie, c'est une observation à une occurrence — écrite ici pour
qu'elle ne devienne pas une hypothèse tacite. La consigne n'est pas allée dans le prompt :
on n'écrit pas une règle contre un cas qu'on a vu se résoudre seul une fois.

⚠️ **`recupere_le` est posé ici, à l'instant de la récupération**, et c'est ce qui rend le
TTL calculable. Le laisser au dépôt reviendrait à dater la ligne de son écriture en base,
qui peut arriver bien plus tard — la transaction n'est validée qu'en fin de tour.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from raiyon.avis.cache import Avis, tronquer_extrait
from raiyon.avis.fournisseur import RechercheImpossible

logueur = structlog.get_logger(__name__)

POINT_DENTREE = "https://api.search.brave.com/res/v1/web/search"
NOM = "brave"
"""La valeur écrite dans `avis_produit.source`. La même que `SOURCES_AVIS`, et un test le
vérifie : deux écritures d'une même chaîne finissent par en dire deux choses."""

COUT_PAR_REQUETE_USD = 0.005
"""5 $ pour mille requêtes, le tarif « Web Search » de Brave au 6 septembre 2026.

⚠️ **Un tarif figé dans le code est un chiffre qui périme en silence.** Il est ici parce que
le journal doit pouvoir dire ce qu'un tour a coûté **au moment où il l'a coûté**, et non le
recalculer plus tard à un tarif qui aura changé. C'est la même règle que les prix du
catalogue, figés à juillet 2025 et documentés comme tels."""

DELAI_MAX_S = 10.0
"""⚠️ **Une borne dure, et elle protège le tour, pas la requête.** Une recherche d'avis est
un complément : si elle traîne, le client attend une recommandation qu'il aurait eue sans
elle. Dix secondes est déjà long — au-delà, mieux vaut un tour sans avis qu'un tour lent."""


class FournisseurBrave:
    """L'implémentation du `Protocol` `Fournisseur`. Une méthode, un appel, zéro état.

    Le client `httpx` est créé par appel plutôt que gardé : un tour fait au plus une
    recherche (borne de §3.18), donc il n'y a pas de connexion à réutiliser, et un client
    de longue vie devrait être fermé par quelqu'un — ce que ni la couche outils ni le
    répartiteur ne savent faire.
    """

    nom = NOM
    """Ce que le journal écrit dans `AvisConsultes.source`. Lu par `chercher_des_avis()`
    sans que le `Protocol` l'impose : un fournisseur qui ne le porte pas est nommé par sa
    classe, ce qui reste lisible."""

    def __init__(self, cle: str, *, delai_s: float = DELAI_MAX_S) -> None:
        self._cle = cle
        self._delai = delai_s
        self.requetes = 0
        """Combien d'appels réseau ce fournisseur a faits. Lu par le journal."""

    @property
    def cout_usd(self) -> float:
        """Ce que les requêtes de ce fournisseur ont coûté. **Compté, pas estimé.**"""
        return self.requetes * COUT_PAR_REQUETE_USD

    def chercher(self, requete: str, *, limite: int) -> tuple[Avis, ...]:
        """Une recherche web, convertie en `Avis` bornés. Lève `RechercheImpossible`.

        ⚠️ **`requete_normalisee` est laissée vide exprès.** Le fournisseur reçoit la
        requête **libre** et ne connaît pas la normalisation ; c'est `chercher_des_avis()`
        qui réétiquette sous la clé du groupe. La poser ici obligerait le fournisseur à
        importer la normalisation, et le jour où elle change il faudrait y penser des deux
        côtés — `CleIncoherente` est là pour attraper l'oubli, mais mieux vaut ne pas
        créer l'occasion.
        """
        self.requetes += 1
        recupere_le = datetime.now(UTC)
        # 🔴 **Le motif est retenu, et la levée a lieu HORS du bloc `except`.** `from None`
        # ne suffit pas : il efface `__cause__` et laisse `__context__`, où Python attache
        # automatiquement l'exception en cours de traitement — donc l'erreur `httpx`, donc
        # son `Request`, donc les en-têtes, donc **la clé**. Le défaut a été trouvé par
        # `test_le_fournisseur_ne_met_jamais_la_cle_dans_son_erreur`, qui l'affirmait.
        motif: str | None = None
        charge: dict[str, Any] = {}
        try:
            reponse = httpx.get(
                POINT_DENTREE,
                params={"q": requete, "count": limite},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": self._cle,
                },
                timeout=self._delai,
            )
            reponse.raise_for_status()
            charge = reponse.json()
        except httpx.HTTPStatusError as erreur:
            motif = f"HTTP {erreur.response.status_code}"
        except httpx.HTTPError as erreur:
            motif = type(erreur).__name__
        except ValueError:
            motif = "réponse illisible (JSON invalide)"
        if motif is not None:
            raise _erreur_propre(motif)

        resultats = charge.get("web", {}).get("results", []) or []
        avis = tuple(
            _en_avis(resultat, recupere_le)
            for resultat in resultats[:limite]
            if _utilisable(resultat)
        )
        logueur.info(
            "brave.recherche",
            resultats=len(avis),
            rendus_par_lapi=len(resultats),
            cout_usd=COUT_PAR_REQUETE_USD,
        )
        return avis


def _utilisable(resultat: object) -> bool:
    """Un résultat sans URL ni titre n'est pas un avis. Écarté sans bruit.

    L'API rend parfois des entrées partielles (une réponse enrichie, un profil). Les
    laisser entrer produirait des lignes de cache que `AvisEnSeed` refuserait, mais qui
    passent par le chemin réseau où ce schéma ne s'applique pas.
    """
    return (
        isinstance(resultat, dict)
        and bool(str(resultat.get("url", "")).startswith(("http://", "https://")))
        and bool(str(resultat.get("title", "")).strip())
    )


def _en_avis(resultat: dict[str, object], recupere_le: datetime) -> Avis:
    """Un résultat Brave vers le type du domaine. **L'extrait est borné dès l'entrée.**"""
    return Avis(
        requete_normalisee="",
        url=str(resultat["url"]),
        titre=str(resultat["title"]),
        extrait=tronquer_extrait(str(resultat.get("description", ""))),
        source=NOM,
        recupere_le=recupere_le,
    )


def _erreur_propre(motif: str) -> RechercheImpossible:
    """Une exception **sans requête, sans en-têtes, donc sans clé**.

    ⚠️ **`from None` chez les appelants, et ce n'est pas cosmétique.** Chaîner l'exception
    d'origine (`from erreur`) remettrait le `Request` dans le `__cause__`, donc dans la
    trace, donc dans le journal JSONL. Le filtre ne vaut que si la chaîne est coupée.
    """
    logueur.warning(
        "brave.echec",
        motif=motif,
        consequence="l'outil refuse, la conversation continue sans avis",
    )
    return RechercheImpossible(f"la recherche d'avis a échoué ({motif}).")
