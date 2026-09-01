/**
 * Le réseau et le fil SSE — **aucune ligne de DOM dans ce fichier.**
 *
 * C'est la même séparation que `serialisation.py` / `app.py` côté serveur, et elle sert
 * la même chose : ce qui peut casser en silence vit dans un module qu'on peut lire seul.
 *
 * ---
 *
 * ### Pourquoi un parseur écrit à la main
 *
 * `EventSource` ne sait faire que du GET, et le message du client ne peut pas partir en
 * query string — longueur, encodage, et un message de client dans les logs d'accès. Le
 * coût était annoncé à l'étape 10 (arbitrage B), il se paie ici : `fetch` +
 * `ReadableStream`, et le cadrage lu à la main.
 *
 * ### ⚠️ Ce parseur implémente le cadrage **du projet**, pas la spécification SSE
 *
 * Le producteur — `raiyon.api.serialisation.trame()` — émet exactement :
 *
 *     event: <nom>\n
 *     data: <JSON sur une seule ligne>\n
 *     \n
 *
 * Un `data:` unique, jamais plusieurs ; pas d'`id:`, pas de `retry:`, pas de commentaire
 * `:` — il n'y a **aucun heartbeat** (arbitrage C de l'étape 10). Écrire ici un parseur
 * SSE générique serait plus long, jamais exercé, et faussement rassurant : il
 * prétendrait accepter des formes que ce producteur ne produit pas et que rien ne
 * vérifierait. La limite est donc écrite plutôt que tue, et c'est ce qui la rend
 * vérifiable le jour où le producteur changerait.
 *
 * ### L'algorithme vient de `tests/api/test_cadrage_sse.py`
 *
 * `recomposer()` y est écrit en Python, testé sous quatre découpages d'octets (1, 7, 64,
 * 4096), et ce module le **transcrit**. C'est l'atténuation nommée au §7 : le parseur du
 * front n'est vérifié par rien automatiquement, et sa seule défense est de tenir en un
 * module sans DOM dont l'algorithme est écrit et testé ailleurs.
 *
 * Deux pièges y sont fermés, et aucun des deux ne se voit en relecture :
 *
 * 1. **le décodage est incrémental** — `{ stream: true }` à chaque `decode()`. Sans lui,
 *    un caractère multi-octets coupé entre deux morceaux réseau produit un `�` au milieu
 *    d'un mot. La prose est en français : ce n'est pas un cas limite, c'est une phrase
 *    sur deux, et le défaut est **intermittent** ;
 * 2. **la queue est conservée** — les morceaux ne s'alignent pas sur les trames. On
 *    traite les segments complets et on garde le dernier pour le tour suivant. Son
 *    symptôme est un événement perdu de temps en temps, donc une carte produit qui
 *    manque une fois sur dix.
 */

/** Les dix noms du fil. **Fermé** — c'est `NomEvenement` côté Python, et rien d'autre. */
export const NOMS = Object.freeze({
    CRITERES: "criteria_updated",
    SONDAGE: "catalog_probe",
    QUESTION_SUGGEREE: "suggested_question",
    PRODUITS: "products_found",
    QUESTION: "question",
    MESSAGE: "message",
    TEXTE_REJETE: "text_rejected",
    REPLI: "fallback",
    ERREUR: "error",
    FIN: "done",
});

/** Les deux codes d'erreur de l'API — `CodeErreur` côté Python. */
export const CODES = Object.freeze({
    TOUR_EN_COURS: "tour_en_cours",
    INTERNE: "interne",
});

const SEPARATEUR = "\n\n";

/**
 * Une erreur décidée **avant le premier octet** : un code HTTP, et une phrase à afficher.
 *
 * `code` n'est renseigné que pour les échecs qui portent un `CodeErreur` — aujourd'hui le
 * seul 409. Le 404 et le 422 n'en portent pas : ils gardent la forme de FastAPI, et leur
 * en inventer un ajouterait au vocabulaire fermé des valeurs qui ne diraient rien de plus
 * que le code HTTP.
 */
export class ErreurDeLApi extends Error {
    constructor(statut, message, code = null) {
        super(message);
        this.name = "ErreurDeLApi";
        this.statut = statut;
        this.code = code;
    }
}

/**
 * La charge utile d'une trame. **Deux lignes exactement, et rien d'autre.**
 *
 * Rejeter une troisième ligne plutôt que l'ignorer : une trame que ce producteur ne peut
 * pas avoir écrite doit s'arrêter ici, et non se propager sous une forme à demi lue.
 */
function lireTrame(segment) {
    const lignes = segment.split("\n");
    if (lignes.length !== 2 || !lignes[0].startsWith("event: ") || !lignes[1].startsWith("data: ")) {
        throw new Error(`trame hors cadrage : ${segment}`);
    }
    return {
        nom: lignes[0].slice("event: ".length),
        donnees: JSON.parse(lignes[1].slice("data: ".length)),
    };
}

/**
 * Le corps d'une réponse en flux, vers des événements typés. **Accumuler, découper,
 * garder la queue.**
 *
 * La transcription de `recomposer()` — voir l'en-tête du module.
 */
export async function* evenementsDe(reponse) {
    const lecteur = reponse.body.getReader();
    const decodeur = new TextDecoder("utf-8");
    let tampon = "";
    try {
        for (;;) {
            const { value, done } = await lecteur.read();
            if (done) break;
            // ⚠️ `{ stream: true }`, toujours — voir le piège nº1 de l'en-tête.
            tampon += decodeur.decode(value, { stream: true });
            const segments = tampon.split(SEPARATEUR);
            tampon = segments.pop(); // la queue : un morceau de trame incomplet
            for (const segment of segments) {
                yield lireTrame(segment);
            }
        }
    } finally {
        // ⚠️ `cancel()`, pas `releaseLock()` : si l'appelant sort de la boucle avant la
        // fin, il faut **fermer la connexion**. Côté serveur, une déconnexion tue le tour
        // (arbitrage I de l'étape 10) ; la laisser ouverte ferait tourner un tour que
        // plus personne ne lit, appel au modèle compris.
        await lecteur.cancel().catch(() => {});
    }
    if (tampon !== "") {
        // La connexion a coupé au milieu d'une trame. Le dire plutôt que la jeter : `done`
        // est justement ce qui sépare « tour terminé » de « connexion tombée », et une
        // queue non vide sans `done` est la seconde.
        throw new Error(`trame tronquée en fin de flux : ${tampon}`);
    }
}

/**
 * L'échec d'une requête avant le flux, lu **une seule fois** quelle que soit sa forme.
 *
 * Depuis le jalon 0 de l'étape 11, un échec porteur d'un `CodeErreur` sort à plat —
 * `{code, message}` — exactement comme l'événement `error`. Le 404 et le 422 gardent le
 * `detail` de FastAPI et n'ont pas de phrase pour le client : elle est donc écrite ici.
 *
 * ⚠️ **Ce n'est pas une entorse à « le français vient du fil ».** Cette règle porte sur le
 * vocabulaire dérivé du registre d'attributs — libellés de champs, unités, catégories —
 * que le front n'a pas le droit de retraduire. Un 404 ne parle pas du catalogue.
 */
async function erreurDe(reponse, repli) {
    let corps = null;
    try {
        corps = await reponse.json();
    } catch {
        corps = null;
    }
    if (corps && typeof corps.code === "string" && typeof corps.message === "string") {
        return new ErreurDeLApi(reponse.status, corps.message, corps.code);
    }
    return new ErreurDeLApi(reponse.status, repli);
}

/** Ouvre une conversation vide et rend son identifiant. */
export async function creerUneSession() {
    const reponse = await fetch("/sessions", { method: "POST" });
    if (!reponse.ok) {
        throw await erreurDe(reponse, "Impossible d'ouvrir une conversation.");
    }
    return (await reponse.json()).id;
}

/**
 * L'état et la prose d'une session existante. **Jamais ses événements** (arbitrage J de
 * l'étape 10) : une conversation rechargée n'a ni cartes produits ni panneau d'activité.
 *
 * Rend `null` sur un 404 — fragment d'URL périmé, base réinitialisée. C'est un cas normal
 * de démonstration, pas une panne, et l'appelant repart sur une conversation neuve **en le
 * disant**.
 */
export async function relireLaSession(identifiant) {
    const reponse = await fetch(`/sessions/${identifiant}`);
    if (reponse.status === 404) return null;
    if (!reponse.ok) {
        throw await erreurDe(reponse, "Impossible de relire cette conversation.");
    }
    return await reponse.json();
}

/**
 * Un tour : le message part, les événements arrivent. **Générateur asynchrone.**
 *
 * Les trois refus d'avant le premier octet — 404, 409, 422 — lèvent une `ErreurDeLApi`
 * avant que la moindre trame ne soit lue ; après, plus rien ne peut changer le code HTTP
 * et l'échec arrive comme un événement `error` dans le fil (arbitrage E de l'étape 10).
 * L'appelant n'a donc qu'un `try` autour de la boucle, et une branche `error` dedans.
 */
export async function* envoyerUnMessage(identifiant, message) {
    const reponse = await fetch(`/sessions/${identifiant}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
    });
    if (!reponse.ok) {
        throw await erreurDe(reponse, "Le serveur a refusé ce message.");
    }
    yield* evenementsDe(reponse);
}
