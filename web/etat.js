/**
 * Le réducteur : **un événement, un état.** Aucune manipulation du DOM dans ce fichier.
 *
 * C'est la même frontière que `serialisation.py` / `app.py` côté serveur : ce qui peut
 * casser en silence vit dans un module qu'on peut lire seul. Ici, ce qui peut casser en
 * silence est l'ordre — un événement rangé au mauvais endroit du fil, ou un panneau qui
 * garde la valeur du tour précédent.
 *
 * ---
 *
 * ### Le fil de conversation porte les cartes produits (arbitrage C)
 *
 * `products_found` arrive **avant** la prose qui le commente. Les cartes sont donc rangées
 * dans le fil, à l'endroit où elles arrivent, et non dans le panneau : c'est ce qui rend
 * l'ordre réel visible — le code a trouvé, puis le modèle a écrit à propos de ce qu'on lui
 * a donné. §2 rendu observable sans une ligne d'explication.
 *
 * Le panneau porte donc **ce que le code a compris** et l'activité, jamais les résultats.
 *
 * ### Les événements masqués sont conservés, jamais jetés (arbitrage E)
 *
 * `text_rejected` entre dans le fil même quand le mode coulisses est fermé. C'est `rendu.js`
 * qui décide de l'afficher ou non, et c'est ce qui permet de basculer l'interrupteur **au
 * milieu** d'une conversation et de voir ce qui s'est déjà passé. Un mode qui ne montrerait
 * que la suite obligerait à refaire la conversation pour voir le rejet qu'on vient de rater.
 *
 * ### L'activité est le **dernier événement reçu**, et rien d'autre (arbitrage D)
 *
 * `activite` ne porte pas une étape de scénario, mais le nom du dernier événement du fil.
 * Inventer une progression que le fil ne dit pas serait, à l'échelle de l'interface,
 * exactement ce que le projet interdit au modèle.
 *
 * ### Tout montant reste une chaîne
 *
 * Aucun `parseFloat` dans ce fichier, ni ailleurs dans le front. `"129.99"` est affiché tel
 * quel, symbole ajouté. Un aller-retour par `Number` puis `toFixed(2)` réintroduirait une
 * approximation dans le seul projet qui compare des prix au caractère près.
 */

import { NOMS } from "./flux.js";

/** L'état d'ouverture : aucune conversation, aucun appel réseau encore fait. */
export function etatInitial() {
    return {
        identifiant: null,
        fil: [],
        cle: 0,
        besoin: null,
        sondage: null,
        suggestion: null,
        activite: null,
        enCours: false,
        coulisses: false,
        reprise: false,
        avis: null,
    };
}

/** Une entrée de fil, avec une clé stable — c'est elle qui permet un rendu incrémental. */
function ajouter(etat, entree) {
    return {
        ...etat,
        cle: etat.cle + 1,
        fil: [...etat.fil, { cle: etat.cle + 1, ...entree }],
    };
}

/**
 * Un événement du fil SSE, appliqué à l'état. **La seule fonction qui connaît les dix noms.**
 *
 * `done` est terminal : il est émis **après** que le tour a été persisté — la boucle `for`
 * du générateur épuise `session.tour()`, qui commite avant de rendre la main. Il signifie
 * donc « enregistré », pas seulement « fini », et c'est ce qui autorise à rouvrir la saisie
 * sans réserve.
 */
export function reduire(etat, { nom, donnees }) {
    const suite = { ...etat, activite: nom };
    switch (nom) {
        case NOMS.CRITERES:
            return { ...suite, besoin: donnees };
        case NOMS.SONDAGE:
            return { ...suite, sondage: donnees };
        case NOMS.QUESTION_SUGGEREE:
            return { ...suite, suggestion: donnees };
        case NOMS.PRODUITS:
            return ajouter(suite, { genre: "produits", donnees });
        case NOMS.QUESTION:
            return ajouter(suite, { genre: "question", donnees });
        case NOMS.MESSAGE:
            return ajouter(suite, { genre: "assistant", texte: donnees.texte });
        case NOMS.TEXTE_REJETE:
            return ajouter(suite, { genre: "rejet", donnees });
        case NOMS.REPLI:
            return ajouter(suite, { genre: "repli", donnees });
        case NOMS.ERREUR:
            return ajouter({ ...suite, enCours: false, activite: null }, {
                genre: "incident",
                texte: donnees.message,
            });
        case NOMS.FIN:
            return { ...suite, enCours: false, activite: null };
        default:
            // Un onzième nom que ce front ne connaît pas : il est ignoré, jamais affiché.
            // Le vocabulaire est fermé côté serveur (`NomEvenement`) et `assert_never` y
            // fait échouer `make typecheck` avant qu'un tel événement puisse exister.
            return etat;
    }
}

/**
 * Le message du client entre dans le fil, et la saisie se verrouille (arbitrage H).
 *
 * ⚠️ **`sondage` et `suggestion` sont remis à zéro, `besoin` non**, et la différence est
 * une différence de nature. Les critères sont l'**état de la session** : ils survivent au
 * tour, c'est même toute la règle de collant de §3.17. Une lecture du catalogue est une
 * **observation d'un instant** : la garder d'un tour à l'autre afficherait « 32 candidats »
 * à côté du zéro résultat du tour suivant, c'est-à-dire un chiffre vrai au mauvais moment.
 *
 * Un tour qui ne sonde pas laisse donc le bloc d'activité vide, et c'est exact : ce
 * tour-là n'a rien lu.
 */
export function avecMessageClient(etat, texte) {
    return ajouter(
        { ...etat, enCours: true, activite: null, avis: null, sondage: null, suggestion: null },
        { genre: "client", texte },
    );
}

/**
 * Une phrase de l'interface **sur elle-même** : session périmée, 409, réseau coupé.
 *
 * Elle n'est pas rangée avec la prose du modèle : ce n'est pas quelqu'un qui parle dans la
 * conversation, et l'afficher comme tel ferait croire à une réponse.
 */
export function avecAvis(etat, texte) {
    return { ...etat, avis: texte, enCours: false, activite: null };
}

/** Un échec réseau ou un refus avant le premier octet : la saisie se rouvre. */
export function avecEchec(etat, texte) {
    return ajouter({ ...etat, enCours: false, activite: null }, { genre: "incident", texte });
}

/**
 * Ce que `GET /sessions/{id}` rend : **l'état et la prose, jamais les événements**
 * (arbitrage J de l'étape 10).
 *
 * ⚠️ Une conversation rechargée n'a donc ni cartes produits, ni panneau d'activité — et
 * elle perd davantage : **les messages de repli ne sont pas persistés** (§7), donc un tour
 * clos par un `fallback` réapparaît sans sa réponse.
 *
 * L'interface le **dit** plutôt que de faire semblant. Fabriquer une carte produit à partir
 * de rien serait exactement ce que ce projet interdit au modèle.
 */
export function depuisLaSession(etat, session) {
    const reprise = { ...etatInitial(), coulisses: etat.coulisses, identifiant: session.id };
    const avecProse = session.prose.reduce(
        (courant, parole) =>
            ajouter(courant, {
                genre: parole.interlocuteur === "client" ? "client" : "assistant",
                texte: parole.texte,
            }),
        reprise,
    );
    return {
        ...avecProse,
        reprise: true,
        besoin: session.etat.categorie === null ? null : { ...session.etat, mouvements_refuses: [] },
    };
}
