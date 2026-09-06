/**
 * Le tableau de bord : la liste des sessions, et la chronologie de l'une d'elles.
 *
 * ---
 *
 * ### La même règle de sécurité que `rendu.js`, sans exception
 *
 * > On ne fait pas confiance au modèle pour les faits ; on ne lui fait pas davantage
 * > confiance pour le HTML.
 *
 * Cette page affiche **plus** de contenu non maîtrisé que l'interface produit : les
 * arguments bruts des appels d'outils, les `tool_result`, le résumé de raisonnement, le
 * texte refusé par le validateur. Tout entre par `textContent`. **Aucune affectation
 * d'`innerHTML` n'existe dans ce fichier.**
 *
 * ### Ce que la page ne fait pas, et c'est délibéré
 *
 * Pas de filtre, pas de graphique, pas de comparaison agent/machine. Un en-tête agrégé et
 * une chronologie. Ce qui manquera se verra à l'usage ; ce qu'on ajouterait par avance ne
 * se verrait jamais manquer.
 *
 * La seule concession visuelle est la **barre de latence** : une largeur proportionnelle
 * au plus lent appel de la session. Ce n'est pas un graphique, c'est ce qui fait qu'un
 * appel à 20 846 ms au milieu d'appels à 4 654 ms se voit sans qu'on lise les chiffres —
 * et c'est exactement le cas qui a motivé la page.
 *
 * ### Les quatre choses que cette page doit dire sans se tromper
 *
 * 1. **Un `stop_reason` interrompu est marqué**, et c'est le serveur qui le décide : le
 *    drapeau `mesure.interrompue` arrive calculé, parce que la liste des fins interrompues
 *    est déjà écrite une fois dans `orchestration/contrat.py`. La recopier ici en ferait
 *    une seconde liste que personne ne penserait à mettre à jour.
 * 2. **Un appel sans raisonnement est un état normal.** L'adaptatif décide appel par
 *    appel — 1 sur 5 en portait un sur la première conversation réelle. La page écrit
 *    « pas de raisonnement sur cet appel », jamais un tiret de donnée manquante.
 * 3. **Le raisonnement est un résumé produit par l'API**, jamais la trace brute du modèle,
 *    qu'aucun modèle n'expose. La page l'écrit à côté du texte, pas dans une note de bas
 *    de page.
 * 4. **Un texte refusé n'a jamais atteint le client.** Il est rendu à son rang réel, avec
 *    ses griefs, et marqué comme tel — sans quoi la chronologie se lirait comme si le
 *    client avait vu deux messages.
 *
 * ### « Non mesuré » n'est pas « zéro »
 *
 * Les tours d'avant l'étape 23 n'ont ni appel ni événement, et rien ne permet de les leur
 * fabriquer. Partout où le serveur rend `null`, la page écrit « non mesuré ». Afficher
 * `0` affirmerait qu'une conversation n'a rien coûté, ce qui est faux — c'est la même
 * distinction que celle entre une capacité absente et une capacité non mesurée, et c'est
 * le sujet de l'étape entière.
 */

const attente = document.getElementById("attente");
const vueListe = document.getElementById("liste");
const vueSession = document.getElementById("session");
const corpsSessions = document.getElementById("sessions");
const enteteSession = document.getElementById("entete-session");
const chronologie = document.getElementById("chronologie");

const NON_MESURE = "non mesuré";

/** Les libellés de l'interface. Ils ne parlent ni du catalogue ni du modèle. */
const LIBELLES = {
    criteria_updated: "critères mis à jour",
    catalog_probe: "sondage du catalogue",
    suggested_question: "question suggérée",
    products_found: "produits trouvés",
    question: "question posée",
    message: "message livré",
    text_rejected: "texte refusé par le validateur",
    fallback: "repli",
};

// --------------------------------------------------------------------------- //
// Fabriques de nœuds — mêmes conventions que `rendu.js`
// --------------------------------------------------------------------------- //

function noeud(balise, classe, texte) {
    const element = document.createElement(balise);
    if (classe) element.className = classe;
    if (texte !== undefined && texte !== null) element.textContent = String(texte);
    return element;
}

function ligneDeFait(cible, cle, valeur, classe) {
    const bloc = noeud("div", classe ? `fait ${classe}` : "fait");
    bloc.appendChild(noeud("span", "cle", cle));
    bloc.appendChild(noeud("span", "valeur", valeur));
    cible.appendChild(bloc);
    return bloc;
}

function milliers(nombre) {
    return Number(nombre).toLocaleString("fr-FR");
}

function horodatage(iso) {
    return new Date(iso).toLocaleString("fr-FR");
}

/** Le JSON d'un argument ou d'un résultat, indenté, dans un `<pre>` — jamais du HTML. */
function brut(valeur) {
    let texte;
    if (typeof valeur === "string") {
        // Un `tool_result` voyage en chaîne JSON : on la ré-indente si elle en est une,
        // et on la laisse telle quelle sinon. Jamais d'exception qui viderait le bloc.
        try {
            texte = JSON.stringify(JSON.parse(valeur), null, 2);
        } catch {
            texte = valeur;
        }
    } else {
        texte = JSON.stringify(valeur, null, 2);
    }
    return noeud("pre", "brut", texte);
}

// --------------------------------------------------------------------------- //
// La liste des sessions
// --------------------------------------------------------------------------- //

function rendreLaListe(sessions) {
    corpsSessions.replaceChildren();
    if (sessions.length === 0) {
        const ligne = noeud("tr");
        const cellule = noeud("td", "vide", "Aucune session.");
        cellule.colSpan = 8;
        ligne.appendChild(cellule);
        corpsSessions.appendChild(ligne);
        return;
    }
    for (const session of sessions) {
        const ligne = noeud("tr", session.mesuree ? null : "non-mesuree");
        const lien = noeud("a", null, horodatage(session.cree_le));
        lien.href = `#${session.id}`;
        const premiere = noeud("td");
        premiere.appendChild(lien);
        ligne.appendChild(premiere);

        // ⚠️ Une session d'avant l'étape 23 a des tours et zéro appel. Écrire `0` la
        // ferait passer pour gratuite ; on écrit donc ce qu'on sait, et rien de plus.
        const mesure = (valeur) => (session.mesuree ? milliers(valeur) : NON_MESURE);
        ligne.appendChild(noeud("td", "nombre", mesure(session.tours)));
        ligne.appendChild(noeud("td", "nombre", mesure(session.appels)));
        ligne.appendChild(noeud("td", "nombre", mesure(session.jetons_entree)));
        ligne.appendChild(noeud("td", "nombre", mesure(session.jetons_sortie)));
        ligne.appendChild(
            noeud("td", session.replis ? "nombre alerte" : "nombre", mesure(session.replis)),
        );
        ligne.appendChild(
            noeud("td", session.griefs ? "nombre alerte" : "nombre", mesure(session.griefs)),
        );
        ligne.appendChild(noeud("td", null, session.statut));
        corpsSessions.appendChild(ligne);
    }
}

// --------------------------------------------------------------------------- //
// L'en-tête d'une session — les chiffres sur lesquels on arbitre
// --------------------------------------------------------------------------- //

function rendreLEntete(donnees) {
    const entete = donnees.entete;
    enteteSession.replaceChildren();

    const titre = noeud("h2", null, `session ${donnees.id}`);
    enteteSession.appendChild(titre);
    enteteSession.appendChild(
        noeud("p", "sous-titre", `ouverte le ${horodatage(donnees.cree_le)} · ${donnees.statut}`),
    );

    if (!entete.mesuree) {
        enteteSession.appendChild(
            noeud(
                "p",
                "avertissement",
                "Conversation antérieure à l'instrumentation : ses tours sont là, ses " +
                    "appels et ses événements n'ont jamais été enregistrés. Les totaux " +
                    "ci-dessous sont absents, pas nuls.",
            ),
        );
    }

    const faits = noeud("div", "faits");
    ligneDeFait(faits, "tours", milliers(entete.tours));
    ligneDeFait(faits, "appels modèle", entete.mesuree ? milliers(entete.appels) : NON_MESURE);
    ligneDeFait(
        faits,
        "jetons entrée",
        entete.mesuree ? milliers(entete.jetons_entree) : NON_MESURE,
    );
    ligneDeFait(
        faits,
        "jetons sortie",
        entete.mesuree ? milliers(entete.jetons_sortie) : NON_MESURE,
    );
    // Les deux compteurs de cache sont la seule façon de constater que l'arbitrage 7
    // produit son effet. Un `cache_lu` qui s'effondre a repayé son préfixe.
    ligneDeFait(faits, "cache écrit", entete.mesuree ? milliers(entete.cache_ecrit) : NON_MESURE);
    ligneDeFait(
        faits,
        "cache lu",
        entete.mesuree ? milliers(entete.cache_lu) : NON_MESURE,
        entete.cache_lu > 0 ? "bon" : null,
    );
    ligneDeFait(
        faits,
        "coût estimé",
        entete.cout_estime_usd === null ? NON_MESURE : `${entete.cout_estime_usd} $`,
    );
    ligneDeFait(
        faits,
        "latence médiane",
        entete.latence_ms_mediane === null ? NON_MESURE : `${milliers(entete.latence_ms_mediane)} ms`,
    );
    ligneDeFait(
        faits,
        "latence max",
        entete.latence_ms_max === null ? NON_MESURE : `${milliers(entete.latence_ms_max)} ms`,
    );
    if (entete.budget_usd !== null) ligneDeFait(faits, "budget", `${entete.budget_usd} $`);
    if (entete.modeles.length) ligneDeFait(faits, "modèle", entete.modeles.join(", "));
    // `effort` et `display` sont dans la table pour rendre l'arbitrage décidable plus
    // tard ; les afficher est ce qui permettra de voir qu'une session a tourné sous une
    // configuration différente des autres.
    if (entete.efforts.length) ligneDeFait(faits, "effort", entete.efforts.join(", "));
    if (entete.displays.length) ligneDeFait(faits, "display", entete.displays.join(", "));
    enteteSession.appendChild(faits);

    rendreLesComptes(enteteSession, "replis par motif", entete.replis_par_motif, "alerte");
    rendreLesComptes(enteteSession, "griefs par code", entete.griefs_par_code, "refus");

    if (entete.cout_estime_usd !== null) {
        enteteSession.appendChild(
            noeud(
                "p",
                "note",
                "Coût estimé au tarif public relevé le 2026-09-04, hors remises. " +
                    "C'est un ordre de grandeur, pas une facture.",
            ),
        );
    }
}

function rendreLesComptes(cible, titre, comptes, classe) {
    const entrees = Object.entries(comptes);
    const bloc = noeud("div", "comptes");
    bloc.appendChild(noeud("h3", null, titre));
    if (entrees.length === 0) {
        bloc.appendChild(noeud("p", "doux", "aucun"));
    } else {
        const liste = noeud("ul", "puces");
        for (const [cle, compte] of entrees) {
            const item = noeud("li", classe);
            item.appendChild(noeud("code", null, cle));
            item.appendChild(noeud("span", "compte", ` × ${compte}`));
            liste.appendChild(item);
        }
        bloc.appendChild(liste);
    }
    cible.appendChild(bloc);
}

// --------------------------------------------------------------------------- //
// La chronologie
// --------------------------------------------------------------------------- //

function rendreLaChronologie(donnees) {
    chronologie.replaceChildren();
    // La référence de la barre de latence est le plus lent appel **de la session**, pas
    // du tour : comparer un tour à lui-même écraserait justement l'écart qu'on cherche.
    const reference = donnees.entete.latence_ms_max || 1;

    for (const tour of donnees.tours) {
        const bloc = noeud("section", "tour");
        const titre = noeud("h3", "titre-tour");
        titre.appendChild(noeud("span", "numero", `tour ${tour.tour_client}`));
        titre.appendChild(noeud("span", "doux", horodatage(tour.horodatage)));
        if (!tour.mesure) titre.appendChild(noeud("span", "etiquette", NON_MESURE));
        bloc.appendChild(titre);

        const client = noeud("div", "message client");
        client.appendChild(noeud("span", "qui", "client"));
        client.appendChild(noeud("p", "texte", tour.message_client));
        bloc.appendChild(client);

        for (const appel of tour.appels) bloc.appendChild(rendreUnAppel(appel, reference));

        // ⚠️ Seuls les replis sont rendus ici. Les `text_rejected` sont **rattachés à
        // l'appel qui les a produits** par le serveur : les afficher une seconde fois en
        // fin de tour obligerait à deviner de quel texte ils parlent, ce qui est
        // exactement ce que le rattachement supprime.
        const replis = tour.evenements.filter((evenement) => evenement.genre === "fallback");
        for (const evenement of replis) bloc.appendChild(rendreUnEvenement(evenement));

        chronologie.appendChild(bloc);
    }
}

function rendreUnAppel(appel, reference) {
    const bloc = noeud("article", "appel");

    const barre = noeud("header", "barre-appel");
    barre.appendChild(noeud("span", "iteration", `appel ${appel.iteration}`));
    if (appel.refuse) barre.appendChild(noeud("span", "jeton refuse", "texte refusé"));
    const mesure = appel.mesure;
    if (mesure === null) {
        barre.appendChild(noeud("span", "etiquette", NON_MESURE));
    } else {
        barre.appendChild(
            noeud(
                "span",
                mesure.interrompue ? "jeton stop interrompu" : "jeton stop",
                mesure.stop_reason,
            ),
        );
        barre.appendChild(
            noeud("span", "jeton", `${milliers(mesure.jetons_entree)} → ${milliers(mesure.jetons_sortie)} jetons`),
        );
        if (mesure.cache_lu > 0) {
            barre.appendChild(noeud("span", "jeton bon", `${milliers(mesure.cache_lu)} lus du cache`));
        }
        if (mesure.cache_ecrit > 0) {
            barre.appendChild(
                noeud("span", "jeton", `${milliers(mesure.cache_ecrit)} écrits au cache`),
            );
        }
        barre.appendChild(noeud("span", "jeton latence", `${milliers(mesure.latence_ms)} ms`));
    }
    bloc.appendChild(barre);

    if (mesure !== null) {
        // La barre : une largeur, pas un graphique. Elle existe pour qu'un appel à
        // 20 846 ms au milieu d'appels à 4 654 ms se voie sans lire les chiffres.
        const jauge = noeud("div", "jauge");
        const remplissage = noeud(
            "div",
            mesure.interrompue ? "remplissage interrompu" : "remplissage",
        );
        remplissage.style.width = `${Math.max(1, (mesure.latence_ms / reference) * 100)}%`;
        jauge.appendChild(remplissage);
        bloc.appendChild(jauge);
    }

    bloc.appendChild(rendreLeRaisonnement(appel));

    if (appel.texte) bloc.appendChild(rendreLaSortie(appel));

    for (const outil of appel.outils) bloc.appendChild(rendreUnOutil(outil));
    return bloc;
}

/**
 * Le texte produit par un appel — **et s'il a atteint le client ou non**.
 *
 * ⚠️ C'est le point où la page pouvait le plus facilement mentir. Un texte refusé est un
 * bloc `text` d'un message assistant, exactement comme un texte livré : rendus pareil, ils
 * se lisent comme deux messages que le client aurait reçus, alors que le premier n'a jamais
 * quitté le serveur. Le drapeau vient du serveur, qui applique la règle de `prose.py`.
 */
function rendreLaSortie(appel) {
    const bloc = noeud("div", appel.refuse ? "sortie refusee" : "sortie");
    bloc.appendChild(
        noeud("span", "qui", appel.refuse ? "texte refusé — jamais envoyé" : "texte du modèle"),
    );
    bloc.appendChild(noeud("p", "texte", appel.texte));
    if (!appel.refuse) return bloc;

    const grief = appel.grief;
    bloc.appendChild(
        noeud(
            "p",
            "note",
            grief
                ? `Refusé par le validateur (tentative ${grief.tentative}, origine « ${grief.origine} »). Ce texte n'a jamais atteint le client : une régénération a été demandée.`
                : "Refusé par le validateur. Ce texte n'a jamais atteint le client : une régénération a été demandée.",
        ),
    );
    if (grief) {
        const liste = noeud("ul", "puces");
        for (const detail of grief.griefs || []) {
            const item = noeud("li", "refus");
            item.appendChild(noeud("code", null, detail.code));
            if (detail.extrait) item.appendChild(noeud("span", "extrait", ` « ${detail.extrait} »`));
            if (detail.correction) item.appendChild(noeud("p", "doux", detail.correction));
            liste.appendChild(item);
        }
        bloc.appendChild(liste);
    }
    return bloc;
}

function rendreLeRaisonnement(appel) {
    const bloc = noeud("div", "raisonnement");
    if (appel.raisonnement === null) {
        // ⚠️ Un état **normal**, pas une donnée manquante : l'adaptatif décide appel par
        // appel. C'est écrit en toutes lettres pour qu'on ne lise pas un trou.
        bloc.appendChild(
            noeud("p", "doux", "Pas de raisonnement sur cet appel — le mode adaptatif décide appel par appel, c'est un état normal."),
        );
        return bloc;
    }
    if (appel.raisonnement === "") {
        bloc.appendChild(
            noeud(
                "p",
                "doux",
                "Raisonnement non affiché : cet appel est passé sous display « omitted », " +
                    "donc le bloc est signé mais son texte est vide.",
            ),
        );
        return bloc;
    }
    bloc.appendChild(noeud("span", "qui", "raisonnement"));
    bloc.appendChild(noeud("p", "texte", appel.raisonnement));
    // ⚠️ Écrit à l'écran, pas supposé : ce n'est pas la trace brute du modèle, qu'aucun
    // modèle n'expose. `summarized` est le maximum que l'API accorde — une autre valeur
    // rend un 400 qui énumère la liste close.
    bloc.appendChild(
        noeud(
            "p",
            "note",
            "Résumé produit par l'API (display « summarized »), et non la trace brute du " +
                "raisonnement — aucun modèle ne l'expose. C'est le maximum disponible.",
        ),
    );
    return bloc;
}

/**
 * ⚠️ **Un `tool_use` en base n'est pas un outil dont l'effet a atteint le client.** Le
 * répartiteur peut refuser l'appel et rendre un `tool_result` en erreur, que le modèle lit
 * pour corriger ; aucun événement ne part alors au client. Sans la marque, un
 * `record_criteria` refusé se lit comme un `record_criteria` réussi, et la timeline laisse
 * croire qu'un critère a été enregistré. Le drapeau vient de `is_error`, posé par le
 * protocole lui-même.
 */
function rendreUnOutil(outil) {
    const bloc = noeud("div", outil.refuse ? "outil refuse" : "outil");
    const barre = noeud("header", "barre-outil");
    barre.appendChild(noeud("code", "nom-outil", outil.nom));
    if (outil.refuse) barre.appendChild(noeud("span", "jeton refuse", "refusé — sans effet"));
    if (outil.refuse === null) barre.appendChild(noeud("span", "etiquette", "sans résultat"));
    barre.appendChild(noeud("span", "doux", outil.id));
    bloc.appendChild(barre);

    const arguments_ = noeud("div", "moitie");
    arguments_.appendChild(noeud("span", "qui", "arguments exacts"));
    arguments_.appendChild(brut(outil.arguments));
    bloc.appendChild(arguments_);

    const resultat = noeud("div", "moitie");
    resultat.appendChild(
        noeud("span", "qui", outil.refuse ? "refus rendu au modèle" : "résultat"),
    );
    if (outil.resultat === null || outil.resultat === undefined) {
        resultat.appendChild(noeud("p", "doux", "aucun résultat apparié"));
    } else {
        resultat.appendChild(brut(outil.resultat));
    }
    bloc.appendChild(resultat);
    if (outil.refuse) {
        const note = noeud(
            "p",
            "note",
            "Cet appel a été refusé : il n'a modifié aucun état et n'a produit aucun " +
                "événement pour le client. Le modèle a lu ce refus et a pu corriger au " +
                "message suivant.",
        );
        note.style.gridColumn = "1 / -1";
        bloc.appendChild(note);
    }
    return bloc;
}

/** Le repli : une phrase écrite en Python, à son rang, avec son motif. */
function rendreUnEvenement(evenement) {
    const bloc = noeud("article", "evenement repli");
    const barre = noeud("header", "barre-appel");
    barre.appendChild(noeud("span", "iteration", `rang ${evenement.rang}`));
    barre.appendChild(noeud("span", "jeton", LIBELLES[evenement.genre] || evenement.genre));
    bloc.appendChild(barre);
    bloc.appendChild(noeud("p", "texte", evenement.charge.message));
    // Un repli est la seule prose de la page que le modèle n'a pas écrite. Le dire est
    // ce qui empêche de lire un tour replié comme un tour réussi.
    bloc.appendChild(
        noeud(
            "p",
            "note",
            `Phrase écrite en Python, jamais produite par le modèle. Motif : ${evenement.charge.libelle_motif} (${evenement.charge.motif}).`,
        ),
    );
    return bloc;
}

// --------------------------------------------------------------------------- //
// Le routage — le fragment d'URL porte l'identifiant, et rien d'autre
// --------------------------------------------------------------------------- //

function montrer(vue) {
    attente.hidden = vue !== "attente";
    vueListe.hidden = vue !== "liste";
    vueSession.hidden = vue !== "session";
}

function echouer(message) {
    attente.textContent = message;
    montrer("attente");
}

async function lire(chemin) {
    const reponse = await fetch(chemin);
    if (reponse.status === 404) {
        // Deux causes, un seul code : la garde d'environnement et la session absente.
        // Le corps de la réponse dit laquelle, et c'est lui qu'on affiche.
        const corps = await reponse.json().catch(() => ({}));
        throw new Error(corps.detail || "introuvable");
    }
    if (!reponse.ok) throw new Error(`le serveur a répondu ${reponse.status}`);
    return reponse.json();
}

async function router() {
    const identifiant = location.hash.replace(/^#/, "");
    attente.textContent = "Chargement…";
    montrer("attente");
    try {
        if (identifiant) {
            const donnees = await lire(`/journal/${encodeURIComponent(identifiant)}`);
            rendreLEntete(donnees);
            rendreLaChronologie(donnees);
            montrer("session");
        } else {
            rendreLaListe(await lire("/journal"));
            montrer("liste");
        }
    } catch (erreur) {
        echouer(String(erreur.message || erreur));
    }
}

document.getElementById("retour").addEventListener("click", () => {
    location.hash = "";
});
window.addEventListener("hashchange", router);
router();
