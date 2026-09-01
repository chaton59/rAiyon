/**
 * Le câblage : la saisie, le fragment d'URL, le verrouillage, l'interrupteur des coulisses.
 *
 * Le seul module qui connaisse à la fois `flux.js` et `rendu.js` — donc le seul où le réseau
 * et le DOM se rencontrent. C'est délibéré : les trois autres modules se lisent seuls.
 *
 * ---
 *
 * ### F. L'identifiant de session vit dans le fragment d'URL
 *
 * `#<uuid>`. Un rechargement retrouve la conversation, l'URL se copie et se recolle, et
 * l'identifiant est **visible** — un atout de démonstration, pas un détail.
 *
 * *Alternative écartée — `localStorage`.* Invisible, non partageable, et elle rend la
 * seconde conversation impossible sans vider le stockage.
 *
 * Au chargement : fragment présent → `GET /sessions/{id}` pour réhydrater ; absent → aucun
 * appel, la session n'est créée qu'au premier message envoyé. ⚠️ Un `GET` sur une session
 * inconnue rend 404 — fragment périmé, base réinitialisée : le front repart alors sur une
 * conversation neuve **en le disant**, et n'affiche pas une page vide dont personne ne
 * comprendrait la cause.
 *
 * ### H. La saisie est verrouillée pendant un tour
 *
 * Un seul tour à la fois par session (arbitrage D de l'étape 10). Le champ et le bouton sont
 * désactivés dès l'envoi, réactivés sur `done`, sur `error`, ou sur un échec réseau.
 *
 * Le **409** reste traité : il arrive quand deux onglets partagent la même URL, ce que le
 * verrouillage local ne peut pas empêcher. Message humain, saisie réactivée.
 *
 * ### E. L'interrupteur des coulisses ne se persiste pas
 *
 * Une page rechargée repart en mode produit : c'est celui qu'un visiteur doit voir en
 * premier. Les événements masqués sont **reçus et conservés** dans l'état — basculer au
 * milieu d'une conversation affiche ce qui s'est déjà passé.
 */

import { CODES, creerUneSession, envoyerUnMessage, relireLaSession } from "./flux.js";
import { avecAvis, avecEchec, avecMessageClient, depuisLaSession, etatInitial, reduire } from "./etat.js";
import { rendre } from "./rendu.js";

const vue = {
    fil: document.getElementById("fil"),
    accueil: document.getElementById("accueil"),
    avis: document.getElementById("avis"),
    activite: document.getElementById("activite"),
    saisie: document.getElementById("saisie"),
    message: document.getElementById("message"),
    envoyer: document.getElementById("envoyer"),
    besoin: document.getElementById("besoin"),
    catalogue: document.getElementById("catalogue"),
    coulisses: document.getElementById("coulisses"),
    identifiant: document.getElementById("identifiant-session"),
    etiquette: document.getElementById("etiquette-session"),
    posees: new Set(),
};

let etat = etatInitial();

/** L'unique point d'écriture de l'état. Tout passe par ici, donc tout se rend. */
function poser(suivant, options) {
    etat = suivant;
    rendre(vue, etat, options);
}

// --------------------------------------------------------------------------- #
// Le tour
// --------------------------------------------------------------------------- #

/**
 * Un tour complet : le message part, les événements arrivent, la saisie se rouvre.
 *
 * ⚠️ **La boucle ne fait ni `break` ni `return` conditionnel**, exactement comme le
 * générateur côté serveur et comme la console : sortir avant `done` fermerait la connexion,
 * et une déconnexion tue le tour — `session.tour()` n'atteindrait pas son `commit()` et
 * **rien ne serait persisté, pas même le message du client** (arbitrage I de l'étape 10).
 */
async function jouerUnTour(texte) {
    poser(avecMessageClient(etat, texte));

    try {
        if (etat.identifiant === null) {
            const identifiant = await creerUneSession();
            location.hash = identifiant;
            poser({ ...etat, identifiant });
        }
        for await (const evenement of envoyerUnMessage(etat.identifiant, texte)) {
            poser(reduire(etat, evenement));
        }
    } catch (erreur) {
        poser(echec(erreur));
    }
}

/**
 * Un échec **avant le premier octet**, ou un réseau coupé. Après le premier octet, l'échec
 * arrive comme un événement `error` dans le fil et ne passe pas par ici (arbitrage E).
 *
 * Le 409 a sa propre phrase : la sienne, venue du serveur, ne dit pas *pourquoi* deux tours
 * se chevauchent, et le seul cas qui reste possible une fois la saisie verrouillée est celui
 * de deux onglets sur la même URL.
 */
function echec(erreur) {
    if (erreur.code === CODES.TOUR_EN_COURS) {
        return avecEchec(
            etat,
            `${erreur.message} Un autre onglet est probablement ouvert sur la même conversation.`,
        );
    }
    if (erreur.statut === 404) {
        return avecEchec(
            etat,
            "Cette conversation n'existe plus côté serveur. Rechargez la page pour en ouvrir une neuve.",
        );
    }
    if (erreur.statut) return avecEchec(etat, erreur.message);
    // Sans statut : la requête n'a pas abouti — serveur arrêté, réseau coupé, flux tronqué.
    // Rien n'a été persisté côté serveur, donc renvoyer le message est sans risque, et le
    // dire évite au client de se demander si son message est passé « à moitié ».
    return avecEchec(
        etat,
        "La connexion au serveur a été interrompue. Rien n'a été enregistré — vous pouvez renvoyer votre message.",
    );
}

// --------------------------------------------------------------------------- #
// Le câblage
// --------------------------------------------------------------------------- #

vue.saisie.addEventListener("submit", (evenement) => {
    evenement.preventDefault();
    const texte = vue.message.value.trim();
    if (texte === "" || etat.enCours) return;
    vue.message.value = "";
    jouerUnTour(texte);
});

vue.coulisses.addEventListener("change", () => {
    // Le fil est reconstruit : c'est le seul moment où il l'est, et c'est ce qui fait
    // apparaître les rejets déjà reçus plutôt que seulement les suivants (arbitrage E).
    poser({ ...etat, coulisses: vue.coulisses.checked }, { refaireLeFil: true });
});

/**
 * Le chargement. Fragment présent → réhydratation ; absent → **aucun appel réseau**.
 *
 * Une conversation reprise est marquée comme telle par `rendu.js` : elle n'a ni cartes
 * produits ni panneau d'activité, parce que `GET /sessions/{id}` rend l'état et la prose et
 * **jamais les événements**. Inventer une carte produit à partir de rien serait exactement
 * ce que ce projet interdit au modèle.
 */
async function demarrer() {
    const fragment = location.hash.slice(1);
    if (fragment === "") {
        rendre(vue, etat);
        vue.message.focus();
        return;
    }

    try {
        const session = await relireLaSession(fragment);
        if (session === null) {
            location.hash = "";
            poser(
                avecAvis(
                    etat,
                    "Cette conversation n'existe plus — l'identifiant a expiré ou la base a été " +
                        "réinitialisée. Vous repartez d'une conversation neuve.",
                ),
            );
        } else {
            poser(depuisLaSession(etat, session));
        }
    } catch (erreur) {
        poser(avecAvis(etat, `Impossible de reprendre cette conversation : ${erreur.message}`));
    }
    vue.message.focus();
}

demarrer();
