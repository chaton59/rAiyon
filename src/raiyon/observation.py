"""Ce qu'un tour a coûté et ce qu'il a émis, **sans que l'orchestration en sache rien**.

Deux pièces, et une seule idée : observer un tour ne doit rien changer à ce qu'il produit.

| Pièce | Rôle |
|---|---|
| `ClientJournalisant` | enveloppe un `ClientLLM`, note un `AppelJournalise` par appel |
| `evenement_journalise()` | traduit un `Evenement` en ligne d'`evenements_tour` |

---

### Le décorateur, sur le modèle de `ClientEnregistreur` (étape 12)

Même geste, même frontière, et pour la même raison. `ClientEnregistreur` enveloppe un
client réel et note ses réponses pour en faire une cassette ; celui-ci enveloppe un client
réel et note ce que l'appel a coûté. Aucun des deux n'apprend quoi que ce soit à la boucle.

**La frontière « la boucle ignore le coût » ne bouge pas** (voir `Usage` dans
`agent/client.py`). `ReponseLLM` ne gagne pas un champ, le `Protocol` `ClientLLM` ne gagne
pas une méthode, et c'est ce qui fait que le décorateur marche **à l'identique sur les deux
orchestrations** : il est posé au-dessus du client, pas dedans, et ni `boucle.repondre` ni
`machine.repondre_machine` ne peuvent le distinguer d'un client nu.

⚠️ **C'est aussi ce qui interdit un raccourci qui semblerait plus simple** — faire remonter
l'`Usage` par `ReponseLLM`. Il obligerait le faux client de l'étape 8, le client de
cassette et les surcharges de l'API à fabriquer une valeur qu'aucun d'eux ne possède, pour
une information qu'aucun d'eux n'utilise. La décision date du jalon 0 de l'étape 13 et elle
tient toujours.

### `iteration` est compté par le décorateur, pas reçu de la boucle

Le décorateur voit passer les appels d'un tour dans l'ordre ; il les numérote. Demander le
numéro à la boucle voudrait dire l'élargir d'un paramètre pour un besoin qui n'est pas le
sien — et le faire deux fois, une par orchestration, avec deux occasions de compter faux.

**Une instance par tour**, construite par `session.tour()` autour du client qu'on lui a
passé. C'est ce qui fait que `iteration` repart de 1 sans qu'aucun compteur n'ait à être
remis à zéro — et le client réel, lui, reste bien construit une fois par processus, avec
sa mesure du mode `strict` intacte (arbitrage 11).

*Alternative écartée — une instance par processus, remise à zéro en début de tour.* Elle
demande un appel de plus, au bon endroit, dans les deux orchestrations ; l'oublier
donnerait un compteur d'appels depuis le démarrage du serveur, et rien ne le dirait.

*Alternative écartée — que l'appelant construise le décorateur et le passe à `tour()`.*
Elle obligerait l'API, la console et l'exécuteur d'éval à connaître l'observation pour que
`tour()` puisse la drainer, et un appelant qui oublie l'enveloppe produirait une session
sans mesure, silencieusement. `tour()` enveloppe donc lui-même : il n'existe pas de chemin
qui persiste un tour sans le compter.

### Les décorateurs s'empilent, et la lecture des attributs suit la pile

`scripts/essais.py` passe déjà un `ClientEnregistreur(ClientAnthropic())` à `tour()`, qui
l'enveloppe à son tour. `dernier_usage`, `modele`, `effort` et `display` sont donc portés
**deux crans plus bas** que le client immédiatement enveloppé.

`_dans_la_pile()` suit la chaîne des `.reel` jusqu'à trouver l'attribut. Sans cela, la
seule commande qui joue de vraies conversations contre l'API — celle dont on veut le plus
les mesures — écrirait des lignes à zéro jeton, ce qui ne se serait vu qu'en lisant le
tableau de bord et en croyant à un cache parfait.

### La latence est mesurée **autour** de l'appel, reprises du SDK comprises

`perf_counter` avant, après, quel que soit le chemin. Ce que la colonne porte est donc le
temps que l'appelant a attendu, pas celui que l'API déclare avoir passé — et c'est bien ce
qu'on veut observer : un appel repris deux fois par le SDK a réellement coûté ce temps-là
au client qui attendait sa réponse.

### Un appel qui lève est **compté**

C'est le point où ce décorateur diffère de `ClientEnregistreur`, qui n'enregistre que les
appels aboutis — et la différence est délibérée. Une cassette d'un appel qui a échoué ne se
rejoue pas ; un tableau de bord qui masque les appels échoués ment sur la latence et sur le
compte. La ligne est donc écrite avec `stop_reason` valant `erreur:<Classe>`, les compteurs
de jetons à zéro (l'API n'en a rendu aucun) et la latence réelle.

⚠️ **Elle ne sera pourtant pas persistée**, parce qu'un tour qui plante ne commit rien
(arbitrage 9). C'est assumé et c'est le JSONL qui couvre ce cas — la ligne existe donc pour
le drainage d'un tour qui *survit* à une erreur d'appel, ce qu'aucune orchestration ne fait
aujourd'hui mais que rien n'interdit demain. La compter coûte quatre lignes ; découvrir
qu'elle manque coûterait une campagne.

### Les événements : `nom_et_donnees()`, et pas une seconde sérialisation

`genre` et `charge` sont **exactement** ce que le fil SSE envoie. La timeline relue et le
direct montrent donc la même chose, par construction plutôt que par discipline — et
l'`assert_never` de `nom_et_donnees()` fait que l'exhaustivité est vérifiée par mypy.

⚠️ **La dépendance va de la persistance vers `raiyon.api`, et c'est inhabituel.**
`serialisation.py` est un module pur — il n'importe ni FastAPI ni le SDK, un test le
constate module par module — donc rien ne se charge de travers. Ce qui gêne est le **nom**
du paquet : `api` désigne aujourd'hui deux choses, le serveur HTTP et le vocabulaire des
événements. Le déplacer serait le bon geste ; il touche les routes, la console, le front et
quatre fichiers de tests, et il n'appartient pas à une étape qui ajoute deux tables.

### Faut-il persister les événements `Texte` ? **Oui, et c'est un arbitrage**

Ils dupliquent `tours_conversation` : le texte livré est déjà dans les blocs bruts, et
`api/prose.py` sait déjà l'en extraire pour un rechargement.

*Alternative écartée — filtrer `Texte` et `Repli` à l'écriture.* Elle économise quelques
kilo-octets par session et elle **casse la seule propriété que la table doit tenir** :
l'ordre réel. Une timeline dont on a retiré la prose ne dit plus si le texte est venu avant
ou après le sondage, ni combien de messages ont été livrés dans un tour à quatre
itérations. Elle obligerait le tableau de bord à recoller deux sources — les événements
pour la mécanique, les blocs pour la prose — en réinventant l'entrelacement qu'on venait
d'effacer. C'est-à-dire à écrire du code pour reconstruire une information qu'on avait.

Et la duplication est **moins forte qu'elle en a l'air dans les deux cas qui comptent** :

* un `Repli` n'est dans aucune autre table. C'est du texte écrit en Python, jamais produit
  par le modèle, et `IssueDuTour.tours` ne le porte pas — la limite connue de `GET
  /sessions/{id}`, qui perd les tours clos par un repli après un F5. Le filtrer perdrait
  la seule trace persistée d'un tour replié ;
* un `TexteRejete` porte un texte **qui n'atteint jamais le client** et qui n'est nulle
  part ailleurs sous cette forme. C'est le refus lui-même, et c'est la métrique de
  l'étape 12.

La règle « pas de seconde persistance » vise les blocs bruts, dont dépendent le rejeu et la
validation. Elle ne vise pas une projection ordonnée, dont l'ordre **est** l'information.
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog

from raiyon.agent.client import EFFORT_NON_FIXE, ClientLLM, ReponseLLM, Usage
from raiyon.agent.evenements import Evenement
from raiyon.api.serialisation import nom_et_donnees

logueur = structlog.get_logger(__name__)

MODELE_INCONNU = "inconnu"
"""Ce qu'on écrit quand aucun client de la pile ne nomme son modèle — un faux client de
`tests/agent/`, un client de cassette. Écrire le modèle configuré à sa place serait
affirmer qu'un appel a eu lieu contre lui, ce qui est faux."""

DISPLAY_PAR_DEFAUT = "omitted"
"""Ce qu'on écrit quand aucun client de la pile ne déclare son `display`.

C'est **le défaut de l'API**, pas une valeur de remplissage : un client qui n'envoie rien
obtient exactement ce mode-là. Écrire `summarized` supposerait une demande qui n'a pas été
faite — et c'est la forme même de la faute que l'étape 17 vient de consigner."""


def _dans_la_pile(client: object, nom: str, defaut: Any) -> Any:  # noqa: ANN401 — polymorphe
    """Cherche l'attribut sur le client, puis sur ce qu'il enveloppe, jusqu'au bout.

    Les décorateurs de `ClientLLM` s'empilent — `scripts/essais.py` passe déjà un
    `ClientEnregistreur(ClientAnthropic())` — et seul celui du fond connaît le modèle, le
    coût et la configuration d'appel. Un `getattr` sur le premier cran rendrait le défaut,
    donc des lignes à zéro jeton pour la seule commande qui joue de vraies conversations.

    La chaîne est suivie par le champ `reel`, que les deux décorateurs du dépôt nomment
    pareil. C'est une convention, et elle est tenue par le seul endroit qui compte : les
    deux classes sont dans ce dépôt, et un troisième décorateur qui la romprait ferait
    tomber les tests d'observation.
    """
    while client is not None:
        if (valeur := getattr(client, nom, None)) is not None:
            return valeur
        client = getattr(client, "reel", None)
    return defaut


@dataclass(frozen=True, slots=True)
class AppelJournalise:
    """Une ligne d'`appels_modele`, avant qu'elle ne connaisse sa session.

    `session_id` et `tour_client` manquent, et ce n'est pas un oubli : le décorateur ne les
    connaît pas et n'a aucune raison de les connaître. C'est `session.tour()` qui les pose
    au drainage, parce que c'est lui qui tient l'identifiant et le numéro de tour.
    """

    iteration: int
    modele: str
    empreinte_systeme: str
    effort: str
    display: str
    stop_reason: str
    jetons_entree: int
    jetons_sortie: int
    cache_ecrit: int
    cache_lu: int
    latence_ms: int


@dataclass
class ClientJournalisant:
    """Enveloppe un `ClientLLM` et accumule un `AppelJournalise` par appel. **Rien d'autre.**

    Il ne persiste pas, il ne loggue pas ce que le client loggue déjà, et il ne rend rien de
    différent : `repondre()` rend la `ReponseLLM` du client enveloppé, telle quelle.
    """

    reel: ClientLLM
    appels: list[AppelJournalise] = field(default_factory=list)
    _iteration: int = 0

    def drainer(self) -> tuple[AppelJournalise, ...]:
        """Rend les appels accumulés **et vide l'accumulateur**.

        `session.tour()` construit une instance par tour, donc le vidage ne rattrape aucun
        reste aujourd'hui. Il est là parce que c'est ce que « drainer » veut dire : un
        drainage qui laisserait les lignes derrière lui les réécrirait au drainage suivant,
        et une instance réutilisée compterait deux fois un appel qui n'a eu lieu qu'une.
        La méthode est le point de remise, et elle est sûre quelle que soit la durée de vie
        qu'on donnera à l'objet.
        """
        appels = tuple(self.appels)
        self.appels.clear()
        return appels

    def repondre(
        self,
        *,
        systeme: str,
        outils: Sequence[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> ReponseLLM:
        """L'appel du client enveloppé, chronométré, compté, et rendu inchangé."""
        self._iteration += 1
        debut = time.perf_counter()
        try:
            reponse = self.reel.repondre(systeme=systeme, outils=outils, messages=messages)
        except Exception as erreur:
            # Compté malgré tout : un tableau de bord qui masque les appels échoués ment
            # sur la latence et sur le compte. Voir la docstring du module.
            self._noter(systeme, _EN_ERREUR, f"erreur:{type(erreur).__name__}", debut)
            raise
        self._noter(systeme, self._usage_du_client(), reponse.fin, debut)
        return reponse

    def _usage_du_client(self) -> Usage:
        """Ce que le client enveloppé dit avoir consommé, ou zéro s'il ne dit rien.

        Lu par attribut, jamais par le `Protocol` — même geste que `ClientEnregistreur`.
        Un faux client ou un client de cassette n'expose rien, et zéro est alors **exact** :
        une cassette rejouée ne consomme rien.
        """
        usage = _dans_la_pile(self.reel, "dernier_usage", None)
        return usage if isinstance(usage, Usage) else _EN_ERREUR

    def _noter(self, systeme: str, usage: Usage, stop_reason: str, debut: float) -> None:
        """Empile la ligne. `empreinte()` est recalculée ici plutôt que reçue en paramètre.

        Le décorateur voit le `systeme` qui part réellement dans la requête ; le lui faire
        passer par l'appelant ajouterait un argument au `Protocol` et ouvrirait l'écart
        entre le prompt annoncé et le prompt envoyé — exactement ce que l'empreinte existe
        pour fermer.
        """
        from raiyon.agent.prompts import empreinte

        self.appels.append(
            AppelJournalise(
                iteration=self._iteration,
                modele=_dans_la_pile(self.reel, "modele", MODELE_INCONNU),
                empreinte_systeme=empreinte(systeme),
                effort=_dans_la_pile(self.reel, "effort", EFFORT_NON_FIXE),
                display=_dans_la_pile(self.reel, "display", DISPLAY_PAR_DEFAUT),
                stop_reason=stop_reason,
                jetons_entree=usage.jetons_entree,
                jetons_sortie=usage.jetons_sortie,
                cache_ecrit=usage.cache_ecrit,
                cache_lu=usage.cache_lu,
                latence_ms=int((time.perf_counter() - debut) * 1000),
            )
        )


_EN_ERREUR = Usage(appels=0, jetons_entree=0, jetons_sortie=0, cache_ecrit=0, cache_lu=0)
"""Les compteurs d'un appel qui n'a rien rendu. Nommé plutôt que `USAGE_NUL` réimporté :
ici, zéro veut dire « l'API n'a pas répondu », pas « le neutre d'un cumul »."""


TARIFS_USD_PAR_MILLION: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}
"""`(entrée, sortie)` en dollars par million de jetons. **Relevé le 2026-09-04.**

⚠️ **Un tarif codé en dur est une estimation, pas une facture**, et le nom de la fonction
qui s'en sert le dit. Il est public, il change sans prévenir, il ignore les remises et les
paliers d'un compte réel. Il est là parce qu'un tableau de bord qui montre 2 110 jetons de
sortie sans dire ce que ça vaut oblige son lecteur à faire la multiplication de tête, et
c'est précisément le geste qu'on veut lui épargner au moment d'arbitrer.

⚠️ **`raiyon.eval.cout` n'en porte pas, et ce n'est pas un oubli à corriger.** Ce module-là
publie un rapport d'éval : il compte des jetons et des appels par tour, et il refuse
explicitement de fabriquer « un total que personne ne doit à personne ». La distinction
tient : là-bas c'est une **mesure publiée**, ici c'est un **ordre de grandeur affiché**.
Les deux ne se remplacent pas.

Un modèle absent de la table rend `None`. Inventer un tarif moyen pour ne pas laisser une
case vide serait exactement la faute que cette étape a passé son temps à consigner."""

FACTEUR_CACHE_ECRIT = 1.25
FACTEUR_CACHE_LU = 0.10
"""Ce que l'écriture et la lecture de cache coûtent, rapportées au tarif d'entrée.

Le cache écrit se paie plus cher qu'une entrée normale, le cache lu bien moins. Ce sont les
deux multiplicateurs publics du cache éphémère ; ils font que l'arbitrage 7 se lit **en
dollars** et pas seulement en compteurs — ce qui est le seul langage dans lequel « le cache
sert à quelque chose » se démontre."""


def cout_estime_usd(
    *,
    modele: str,
    jetons_entree: int,
    jetons_sortie: int,
    cache_ecrit: int,
    cache_lu: int,
) -> float | None:
    """Le coût estimé d'un appel, ou `None` si le tarif du modèle n'est pas connu.

    Les quatre compteurs sont facturés séparément — c'est tout l'intérêt : additionner
    `cache_lu` à `jetons_entree` avant de multiplier ferait payer dix fois trop cher la
    partie que le cache a justement rendue bon marché.
    """
    tarif = TARIFS_USD_PAR_MILLION.get(modele)
    if tarif is None:
        return None
    entree, sortie = tarif
    return (
        jetons_entree * entree
        + cache_ecrit * entree * FACTEUR_CACHE_ECRIT
        + cache_lu * entree * FACTEUR_CACHE_LU
        + jetons_sortie * sortie
    ) / 1_000_000


def evenement_journalise(evenement: Evenement) -> tuple[str, dict[str, Any]]:
    """Le `genre` et la `charge` d'une ligne d'`evenements_tour`.

    Une seule ligne de corps, et c'est le but : **la table porte ce que le fil SSE porte**,
    par la même fonction. Ce module existe pour nommer ce fait et pour le documenter, pas
    pour transformer quoi que ce soit.
    """
    nom, donnees = nom_et_donnees(evenement)
    return nom.value, donnees


_: type[ClientLLM] = ClientJournalisant
"""Une annotation qui ne sert qu'à `mypy` : elle fait échouer `make typecheck` si le
décorateur cesse de satisfaire le `Protocol`. Même geste que les deux clients d'éval."""
