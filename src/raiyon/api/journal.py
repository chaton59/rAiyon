"""La lecture du tableau de bord : la liste des sessions, et la chronologie d'une session.

**Ce module lit, il n'écrit jamais.** Il ne connaît ni FastAPI ni le SDK ; il prend une
`Session` SQLAlchemy et rend des dictionnaires JSON. Les routes qui l'exposent — et leur
404 hors `dev` — vivent dans `app.py`.

---

### La colonne vertébrale est `tours_conversation`, pas les tables neuves

C'est la décision structurante, et elle vient de la contrainte 3.4 : **les 71 860 tours
déjà en base n'ont ni appel ni événement**, et rien ne permet de les leur fabriquer après
coup. Une chronologie bâtie sur `appels_modele` rendrait donc une page vide pour toute
conversation antérieure à l'étape 23 — c'est-à-dire pour la totalité de l'historique, le
jour où l'on ouvre la page.

La chronologie se construit donc à partir des **lignes de conversation**, qui existent
depuis l'étape 8 :

| Ce qu'on lit | D'où ça vient | Absent avant l'étape 23 ? |
|---|---|---|
| message du client, blocs assistants, `tool_result` | `tours_conversation` | non |
| raisonnement (résumé) | blocs `thinking` | vide, mais présent |
| `stop_reason`, jetons, latence, effort, display | `appels_modele` | **oui** |
| griefs, repli, texte livré, ordre d'émission | `evenements_tour` | **oui** |

Les deux tables neuves **enrichissent** cette colonne vertébrale. Là où elles manquent, la
page dit « non mesuré » — pas zéro, pas rien : la distinction est tout ce qui sépare une
mesure de son absence, et c'est le sujet même de cette étape.

### Une ligne assistant = un appel modèle

L'appairage n'a pas besoin d'être stocké : la n-ième ligne de rôle `assistant` d'un tour
est le résultat du n-ième appel. `appels_modele.iteration` compte exactement pareil, donc
la jointure se fait sur ce rang, sans colonne supplémentaire ni supposition.

⚠️ **Ce qui rendrait cet appairage faux**, et qu'il faut donc surveiller : une orchestration
qui produirait deux lignes assistant pour un appel, ou qui en jetterait une. La machine
**jette des blocs** (`_sans(reponse.blocs, "text")` à l'extraction) mais garde une ligne
par appel, et un appel dont il ne resterait aucun bloc ne poserait pas de ligne du tout.
Le décalage se verrait alors comme un appel sans métriques en fin de tour, ce que la page
affiche au lieu de le taire.

### Le raisonnement affiché est un **résumé produit par l'API**

Jamais la trace brute du modèle, qui n'est exposée par aucun modèle. `display:
"summarized"` est le maximum que `claude-sonnet-5` accorde — mesuré, une autre valeur rend
un 400 qui énumère la liste close. Les résumés observés font 130 à 175 caractères.

L'interface l'écrit à l'écran ; ce module porte le champ `resume_produit_par_lapi` à `true`
pour que la page n'ait pas à le supposer.

### L'appel dont le texte a été refusé est **marqué**, et son grief lui est rattaché

C'est la chose qu'on veut pouvoir relire dans deux semaines, et c'est celle qui se serait
le plus facilement rendue à l'envers : un texte refusé est un bloc `text` d'un message
assistant, **exactement comme un texte livré**. Rendus pareil, ils se lisent comme deux
messages que le client aurait reçus — alors que le premier n'a jamais quitté le serveur.

La règle qui les sépare n'est pas inventée ici : c'est celle de `prose.py`, « un message
assistant suivi d'une reprise a été refusé », rendue publique sous le nom
`porte_une_reprise()`. Deux lecteurs, une seule implémentation — l'écrire deux fois
donnerait deux réponses le jour où le gabarit de grief change.

Le rattachement du grief se fait **par le rang** : le k-ième appel refusé du tour porte le
k-ième `text_rejected`. Les deux suites sont produites dans le même ordre par la même
boucle — un `TexteRejete` est émis à chaque refus, et chaque refus empile exactement une
reprise. C'est ce qui permet d'afficher le code du grief à côté du texte qu'il a fait
tomber, plutôt qu'en fin de tour où il faudrait deviner de quoi il parle.

### Un outil refusé par le répartiteur est **marqué**, comme un texte refusé

⚠️ **Même faute que celle du texte refusé, au même endroit, et elle a bien failli rester.**
Un bloc `tool_use` présent en base n'est pas la preuve que son effet a atteint quoi que ce
soit : le répartiteur peut refuser l'appel — arguments illisibles, catégorie absente,
seconde recherche dans le même tour — et rendre un `tool_result` en erreur que le modèle
lit pour corriger. Aucun événement ne part au client dans ce cas, **par décision** :
`evenements.py` écrit qu'« un refus d'outil n'est pas un événement ».

Le contenu du refus était déjà à l'écran, noyé dans le JSON du résultat — il fallait
repérer `"ok": false` pour le voir. Un `record_criteria` refusé se lisait donc comme un
`record_criteria` réussi, et la timeline laissait croire qu'un critère avait été
enregistré alors que rien ne l'avait été.

`is_error` est posé par `bloc_tool_result()` sur **chaque** `tool_result`, et vaut
exactement `isinstance(resultat, OutilRefuse)`. La distinction n'a donc rien à recalculer :
elle est déjà dans la donnée, il suffisait de la porter jusqu'à l'écran.

### Un appel sans raisonnement est un **état normal**

L'adaptatif décide, appel par appel. Sur la première conversation réelle de l'étape 23,
1 appel sur 5 portait un bloc `thinking`. La page ne doit donc pas rendre l'absence comme
une donnée manquante — `raisonnement` vaut `None` et la page dit « pas de raisonnement sur
cet appel », ce qui est un fait, pas un trou.

### Le coût est **estimé**, et le mot est dans le nom du champ

Le tarif vit dans `raiyon.observation`, à côté du décorateur qui compte les jetons — pas
dans `raiyon.eval.cout`, qui n'en porte aucun et refuse explicitement de convertir ses
compteurs en dollars. La distinction tient : le rapport d'éval publie une **mesure**, cette
page affiche un **ordre de grandeur**. Le champ s'appelle `cout_estime_usd` parce qu'un
tarif public codé en dur est une estimation, pas une facture — et un modèle dont le tarif
est inconnu rend `None` plutôt qu'un chiffre inventé pour remplir la case.
"""

import uuid
from collections.abc import Callable, Mapping, Sequence
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from raiyon.api.prose import prefixe_de_reprise
from raiyon.db.models import AppelModele, EvenementTour, SessionConversation, TourConversation
from raiyon.observation import cout_estime_usd

ROLE_ASSISTANT = "assistant"
ROLE_CLIENT = "user"

GENRES_DE_GRIEF = frozenset({"text_rejected"})
GENRES_DE_REPLI = frozenset({"fallback"})
GENRE_MESSAGE = "message"


def sessions(base: Session, *, limite: int = 50) -> list[dict[str, Any]]:
    """La liste des sessions, les plus récentes d'abord. **Une requête par agrégat.**

    Trois sous-requêtes plutôt qu'une jointure unique : joindre trois tables filles à
    `sessions` multiplierait les lignes entre elles, et les compteurs sortiraient
    silencieusement faux — un `COUNT` sur un produit cartésien est le mode d'échec
    classique de ce genre de page, et il ne se voit qu'en comparant à la main.
    """
    tours = (
        select(
            TourConversation.session_id.label("session_id"),
            func.count().filter(TourConversation.role == ROLE_CLIENT).label("lignes_client"),
        )
        .group_by(TourConversation.session_id)
        .subquery()
    )
    appels = (
        select(
            AppelModele.session_id.label("session_id"),
            func.count().label("appels"),
            func.coalesce(func.sum(AppelModele.jetons_entree), 0).label("jetons_entree"),
            func.coalesce(func.sum(AppelModele.jetons_sortie), 0).label("jetons_sortie"),
            func.count(func.distinct(AppelModele.tour_client)).label("tours"),
        )
        .group_by(AppelModele.session_id)
        .subquery()
    )
    evenements = (
        select(
            EvenementTour.session_id.label("session_id"),
            func.count().filter(EvenementTour.genre.in_(GENRES_DE_REPLI)).label("replis"),
            func.count().filter(EvenementTour.genre.in_(GENRES_DE_GRIEF)).label("griefs"),
        )
        .group_by(EvenementTour.session_id)
        .subquery()
    )

    lignes = base.execute(
        select(
            SessionConversation.id,
            SessionConversation.cree_le,
            SessionConversation.statut,
            SessionConversation.budget_usd,
            tours.c.lignes_client,
            appels.c.appels,
            appels.c.jetons_entree,
            appels.c.jetons_sortie,
            appels.c.tours,
            evenements.c.replis,
            evenements.c.griefs,
        )
        .outerjoin(tours, tours.c.session_id == SessionConversation.id)
        .outerjoin(appels, appels.c.session_id == SessionConversation.id)
        .outerjoin(evenements, evenements.c.session_id == SessionConversation.id)
        .order_by(SessionConversation.cree_le.desc())
        .limit(limite)
    ).all()

    return [
        {
            "id": str(ligne.id),
            "cree_le": ligne.cree_le.isoformat(),
            "statut": ligne.statut,
            "budget_usd": None if ligne.budget_usd is None else str(ligne.budget_usd),
            # Le nombre de tours **client**, compté sur les lignes de rôle `user` qui ne
            # sont pas des `tool_result` — c'est-à-dire ici sur `appels_modele` quand elle
            # est renseignée, et sur les lignes sinon. Voir `_tours_client()`.
            "tours": ligne.tours or 0,
            "lignes_client": ligne.lignes_client or 0,
            "appels": ligne.appels or 0,
            "jetons_entree": ligne.jetons_entree or 0,
            "jetons_sortie": ligne.jetons_sortie or 0,
            "replis": ligne.replis or 0,
            "griefs": ligne.griefs or 0,
            # ⚠️ **Le drapeau qui empêche la page de mentir.** Une session d'avant
            # l'étape 23 a des tours et zéro appel ; sans lui, la liste afficherait « 0
            # appel » comme si la conversation n'avait rien coûté.
            "mesuree": bool(ligne.appels),
        }
        for ligne in lignes
    ]


def chronologie(base: Session, identifiant: uuid.UUID) -> dict[str, Any] | None:
    """Une session entière : son en-tête agrégé et ses tours. `None` si elle n'existe pas."""
    conversation = base.get(SessionConversation, identifiant)
    if conversation is None:
        return None

    lignes = list(
        base.scalars(
            select(TourConversation)
            .where(TourConversation.session_id == identifiant)
            .order_by(TourConversation.numero)
        )
    )
    appels = list(
        base.scalars(
            select(AppelModele)
            .where(AppelModele.session_id == identifiant)
            .order_by(AppelModele.tour_client, AppelModele.iteration)
        )
    )
    evenements = list(
        base.scalars(
            select(EvenementTour)
            .where(EvenementTour.session_id == identifiant)
            .order_by(EvenementTour.tour_client, EvenementTour.rang)
        )
    )

    tours = _tours(lignes, appels, evenements)
    return {
        "id": str(identifiant),
        "cree_le": conversation.cree_le.isoformat(),
        "statut": conversation.statut,
        "entete": _entete(conversation, appels, evenements, tours),
        "tours": tours,
    }


# --------------------------------------------------------------------------- #
# L'en-tête : les chiffres sur lesquels on arbitre
# --------------------------------------------------------------------------- #


def _entete(
    conversation: SessionConversation,
    appels: Sequence[AppelModele],
    evenements: Sequence[EvenementTour],
    tours: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Les totaux de la session. **C'est la partie qui sert à décider**, pas à décorer.

    Les replis sont comptés **par motif** et les griefs **par code** : un total agrégé
    dirait qu'il y a eu six rejets sans dire si c'est six fois la même règle — or c'est
    exactement la question qu'un relâchement du validateur pose.
    """
    latences = [appel.latence_ms for appel in appels]
    return {
        "criteres_valides": conversation.criteres_valides,
        "budget_usd": None if conversation.budget_usd is None else str(conversation.budget_usd),
        "tours": len(tours),
        "appels": len(appels),
        "jetons_entree": sum(appel.jetons_entree for appel in appels),
        "jetons_sortie": sum(appel.jetons_sortie for appel in appels),
        "cache_ecrit": sum(appel.cache_ecrit for appel in appels),
        "cache_lu": sum(appel.cache_lu for appel in appels),
        "cout_estime_usd": _cout(appels),
        "latence_ms_mediane": int(median(latences)) if latences else None,
        "latence_ms_max": max(latences, default=None),
        "replis_par_motif": _compter(evenements, GENRES_DE_REPLI, _motif_du_repli),
        "griefs_par_code": _compter(evenements, GENRES_DE_GRIEF, _codes_du_grief),
        "modeles": sorted({appel.modele for appel in appels}),
        "efforts": sorted({appel.effort for appel in appels}),
        "displays": sorted({appel.display for appel in appels}),
        "mesuree": bool(appels),
    }


def _cout(appels: Sequence[AppelModele]) -> str | None:
    """Le coût estimé de la session, ou `None`. **Deux absences distinctes, une valeur.**

    `None` quand la session n'a aucun appel mesuré — une conversation d'avant l'étape 23 a
    coûté quelque chose, et afficher `0.00` affirmerait le contraire. `None` aussi si un
    seul appel porte un modèle dont le tarif est inconnu : un total partiel se lirait comme
    un total, et c'est la règle du tout ou rien que `raiyon.eval.cout` applique déjà à ses
    propres chiffres.
    """
    if not appels:
        return None
    couts = [
        cout_estime_usd(
            modele=appel.modele,
            jetons_entree=appel.jetons_entree,
            jetons_sortie=appel.jetons_sortie,
            cache_ecrit=appel.cache_ecrit,
            cache_lu=appel.cache_lu,
        )
        for appel in appels
    ]
    if any(cout is None for cout in couts):
        return None
    return f"{sum(cout for cout in couts if cout is not None):.4f}"


def _compter(
    evenements: Sequence[EvenementTour],
    genres: frozenset[str],
    cles: Callable[[Mapping[str, Any]], list[str]],
) -> dict[str, int]:
    """Compte les charges d'un genre par la ou les clés qu'une fonction en extrait."""
    compte: dict[str, int] = {}
    for evenement in evenements:
        if evenement.genre not in genres:
            continue
        for cle in cles(evenement.charge):
            compte[cle] = compte.get(cle, 0) + 1
    return dict(sorted(compte.items(), key=lambda paire: (-paire[1], paire[0])))


def _motif_du_repli(charge: Mapping[str, Any]) -> list[str]:
    return [str(charge.get("motif", "inconnu"))]


def _codes_du_grief(charge: Mapping[str, Any]) -> list[str]:
    """Un rejet peut porter plusieurs griefs : chacun compte pour son code."""
    return [str(grief.get("code", "inconnu")) for grief in charge.get("griefs", [])]


# --------------------------------------------------------------------------- #
# La chronologie : un tour = un message client, des appels, des événements
# --------------------------------------------------------------------------- #


def _tours(
    lignes: Sequence[TourConversation],
    appels: Sequence[AppelModele],
    evenements: Sequence[EvenementTour],
) -> list[dict[str, Any]]:
    """Découpe les lignes en tours clients, puis enrichit chacun.

    Un tour commence à une ligne de rôle `user` qui n'est **pas** un bloc de `tool_result`
    ni un message de reprise. C'est la même règle que `prose.py`, et pour la même raison :
    les `tool_result` portent le rôle `user` dans l'API Anthropic, et le message de grief
    aussi — les compter comme des tours clients ferait un tableau de bord qui invente des
    messages que personne n'a écrits.
    """
    par_tour_appels: dict[int, list[AppelModele]] = {}
    for appel in appels:
        par_tour_appels.setdefault(appel.tour_client, []).append(appel)
    par_tour_evenements: dict[int, list[EvenementTour]] = {}
    for evenement in evenements:
        par_tour_evenements.setdefault(evenement.tour_client, []).append(evenement)

    tours: list[dict[str, Any]] = []
    courant: dict[str, Any] | None = None
    for ligne in lignes:
        if _est_un_message_client(ligne):
            courant = {
                "tour_client": ligne.numero,
                "horodatage": ligne.cree_le.isoformat(),
                "message_client": _texte_des_blocs(ligne.blocs),
                "_lignes": [],
            }
            tours.append(courant)
        elif courant is not None:
            courant["_lignes"].append(ligne)

    for tour in tours:
        numero = tour["tour_client"]
        internes = tour.pop("_lignes")
        tour["appels"] = _appels_du_tour(
            internes,
            par_tour_appels.get(numero, []),
            [
                evenement.charge
                for evenement in par_tour_evenements.get(numero, [])
                if evenement.genre in GENRES_DE_GRIEF
            ],
        )
        tour["evenements"] = [
            {"rang": evenement.rang, "genre": evenement.genre, "charge": evenement.charge}
            for evenement in par_tour_evenements.get(numero, [])
        ]
        tour["mesure"] = bool(par_tour_appels.get(numero))
    return tours


def _est_un_message_client(ligne: TourConversation) -> bool:
    """Un vrai message du client : rôle `user`, aucun `tool_result`, pas une reprise."""
    if ligne.role != ROLE_CLIENT:
        return False
    blocs = ligne.blocs or []
    if any(bloc.get("type") == "tool_result" for bloc in blocs if isinstance(bloc, dict)):
        return False
    return not _texte_des_blocs(blocs).startswith(prefixe_de_reprise())


def _appels_du_tour(
    lignes: Sequence[TourConversation],
    mesures: Sequence[AppelModele],
    griefs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Un appel par ligne assistant, apparié à sa mesure par le rang.

    Les `tool_result` de la ligne `user` **suivante** sont rattachés aux `tool_use` de la
    ligne assistant courante, par identifiant. L'appairage par `tool_use_id` plutôt que par
    position : c'est ce que l'API garantit, et une exécution qui rendrait ses résultats dans
    un autre ordre n'inventerait pas de correspondances fausses.

    ⚠️ **`refuse` est le champ qui empêche la page de mentir sur ce qui a été livré.** Un
    texte refusé est un bloc `text` d'un message assistant, exactement comme un texte
    livré ; sans ce drapeau ils se rendraient à l'identique, et la chronologie se lirait
    comme si le client avait reçu deux messages.
    """
    resultats = _resultats_par_id(lignes)
    refuses = _appels_refuses(lignes)
    appels: list[dict[str, Any]] = []
    for ligne in lignes:
        if ligne.role != ROLE_ASSISTANT:
            continue
        rang = len(appels) + 1
        mesure = mesures[rang - 1] if rang <= len(mesures) else None
        refuse = rang in refuses
        # Le k-ième appel refusé porte le k-ième `text_rejected` : deux suites produites
        # dans le même ordre par la même boucle. Voir la docstring du module.
        classement = sorted(refuses).index(rang) if refuse else None
        blocs = [bloc for bloc in (ligne.blocs or []) if isinstance(bloc, dict)]
        appels.append(
            {
                "iteration": rang,
                "refuse": refuse,
                "grief": (
                    griefs[classement]
                    if classement is not None and classement < len(griefs)
                    else None
                ),
                "horodatage": ligne.cree_le.isoformat(),
                # ⚠️ `None` quand l'adaptatif n'a pas raisonné — un état **normal**, pas un
                # trou. Chaîne vide quand le bloc existe mais que `display` valait
                # `omitted` : deux situations différentes, deux valeurs différentes.
                "raisonnement": _raisonnement(blocs),
                "resume_produit_par_lapi": True,
                "texte": _texte_des_blocs(blocs) or None,
                "outils": [
                    _outil(bloc, resultats) for bloc in blocs if bloc.get("type") == "tool_use"
                ],
                "mesure": None if mesure is None else _mesure(mesure),
            }
        )
    return appels


def _appels_refuses(lignes: Sequence[TourConversation]) -> set[int]:
    """Les rangs des appels dont le texte a été refusé par le validateur.

    La règle est celle de `prose.py` — « un message assistant suivi d'une reprise a été
    refusé » — et elle est **importée**, pas réécrite : `porte_une_reprise()` est publique
    depuis l'étape 23 pour que ces deux lecteurs n'en aient qu'une.
    """
    from raiyon.api.prose import porte_une_reprise

    refuses: set[int] = set()
    rang = 0
    for indice, ligne in enumerate(lignes):
        if ligne.role != ROLE_ASSISTANT:
            continue
        rang += 1
        suivante = lignes[indice + 1] if indice + 1 < len(lignes) else None
        if suivante is not None and suivante.role == ROLE_CLIENT:
            blocs = [bloc for bloc in (suivante.blocs or []) if isinstance(bloc, dict)]
            if porte_une_reprise(blocs):
                refuses.add(rang)
    return refuses


def _outil(bloc: Mapping[str, Any], resultats: Mapping[str, Any]) -> dict[str, Any]:
    """Un appel d'outil, son résultat apparié, **et s'il a été refusé**.

    `refuse` vient de `is_error`, que `bloc_tool_result()` pose sur chaque `tool_result`.
    Il n'est pas recalculé depuis le contenu du résultat : le protocole porte déjà la
    réponse, et la relire depuis le JSON en ferait une seconde interprétation à tenir.
    """
    identifiant = str(bloc.get("id", ""))
    resultat = resultats.get(identifiant)
    return {
        "nom": str(bloc.get("name", "")),
        "id": identifiant,
        "arguments": bloc.get("input") or {},
        "resultat": None if resultat is None else resultat["contenu"],
        # ⚠️ `None` et `False` ne disent pas la même chose : `None` = aucun `tool_result`
        # apparié (un tour interrompu avant l'exécution), `False` = exécuté et accepté.
        "refuse": None if resultat is None else resultat["refuse"],
    }


def _mesure(appel: AppelModele) -> dict[str, Any]:
    """Ce que `appels_modele` sait de cet appel. Aplati, prêt pour l'affichage."""
    return {
        "modele": appel.modele,
        "empreinte_systeme": appel.empreinte_systeme,
        "effort": appel.effort,
        "display": appel.display,
        "stop_reason": appel.stop_reason,
        # ⚠️ Le drapeau qui décide de la mise en évidence à l'écran. Il est calculé ici et
        # pas dans le JavaScript : le vocabulaire des `stop_reason` interrompus est déjà
        # écrit une fois, dans `orchestration/contrat.py`, et le recopier au front en
        # ferait une seconde liste que personne ne penserait à mettre à jour.
        "interrompue": _est_interrompue(appel.stop_reason),
        "jetons_entree": appel.jetons_entree,
        "jetons_sortie": appel.jetons_sortie,
        "cache_ecrit": appel.cache_ecrit,
        "cache_lu": appel.cache_lu,
        "latence_ms": appel.latence_ms,
    }


def _est_interrompue(stop_reason: str) -> bool:
    """Vrai pour `max_tokens`, `refusal`, et pour toute erreur d'appel journalisée."""
    from raiyon.orchestration.contrat import FINS_INTERROMPUES

    return stop_reason in FINS_INTERROMPUES or stop_reason.startswith("erreur:")


def _resultats_par_id(lignes: Sequence[TourConversation]) -> dict[str, dict[str, Any]]:
    """Tous les `tool_result` du tour, indexés par l'identifiant du `tool_use` appairé.

    Chaque entrée porte le contenu **et** `is_error` : c'est le protocole lui-même qui
    distingue un outil exécuté d'un outil refusé, et rien d'autre n'a à le deviner.
    """
    resultats: dict[str, dict[str, Any]] = {}
    for ligne in lignes:
        for bloc in ligne.blocs or []:
            if isinstance(bloc, dict) and bloc.get("type") == "tool_result":
                resultats[str(bloc.get("tool_use_id", ""))] = {
                    "contenu": bloc.get("content"),
                    "refuse": bool(bloc.get("is_error")),
                }
    return resultats


def _raisonnement(blocs: Sequence[Mapping[str, Any]]) -> str | None:
    """Le texte des blocs `thinking`, ou `None` s'il n'y en a aucun.

    ⚠️ **`None` et `""` ne veulent pas dire la même chose.** `None` : l'adaptatif n'a pas
    raisonné sur cet appel, ce qui est normal — 1 appel sur 5 en portait un sur la première
    conversation réelle. `""` : un bloc existe mais son texte est vide, c'est-à-dire un
    appel passé sous `display: "omitted"` — tout l'historique d'avant l'étape 23.
    """
    morceaux = [str(bloc.get("thinking", "")) for bloc in blocs if bloc.get("type") == "thinking"]
    return None if not morceaux else "\n".join(morceaux)


def _texte_des_blocs(blocs: Sequence[Mapping[str, Any]]) -> str:
    """La concaténation des blocs `text`. Rien d'autre — pas de `tool_use`, pas de résumé."""
    return "".join(
        str(bloc.get("text", ""))
        for bloc in blocs
        if isinstance(bloc, dict) and bloc.get("type") == "text"
    )
