/**
 * L'état vers le DOM. **Ce module ne parle jamais au réseau**, et il n'écrit jamais de HTML.
 *
 * ---
 *
 * ### La règle de sécurité, et elle n'a pas d'exception
 *
 * > On ne fait pas confiance au modèle pour les faits ; on ne lui fait pas davantage
 * > confiance pour le HTML.
 *
 * Toute chaîne venue du fil — prose, question, nom de produit, extrait de grief, message de
 * repli — entre dans le DOM par `textContent` ou `createTextNode`. **Aucun `innerHTML` sur
 * une valeur du fil**, sans exception, y compris pour un nom de produit qui « ne peut pas »
 * contenir de balise. **Aucune affectation d'`innerHTML` n'existe dans ce fichier.**
 *
 * ### Deux formes de markdown, et pas une de plus
 *
 * Le modèle produit du markdown. `enNoeuds()` interprète le gras `**…**` et les sauts de
 * ligne, en **nœuds DOM** construits un par un — jamais une chaîne de HTML assemblée puis
 * injectée. Le reste (`# titres`, `- listes`, `` `code` ``) s'affiche tel quel.
 *
 * ⚠️ **C'est le prompt qu'on corrigera à l'étape 13, pas le front qu'on armera d'un
 * parseur.** Ajouter ici une dépendance markdown reviendrait à faire porter au front la
 * mise en forme d'un texte dont on maîtrise la production. La limite est écrite au §7.
 *
 * ### Le français vient du fil, jamais d'ici
 *
 * Aucun libellé d'attribut, aucune unité, aucun nom de catégorie n'est écrit dans ce
 * fichier : chaque champ voyage avec son `libelle_fr` et son `unite`, et `criteria_updated`
 * porte `libelle_categorie`. Une table de traduction dans le front rendrait fausse la règle
 * §3.4ter au moment précis où elle devient visible.
 *
 * Ce qui **est** écrit ici est le vocabulaire de l'interface elle-même — « budget »,
 * « candidats », « refusé » — qui ne parle pas du catalogue et ne vient donc d'aucun
 * registre. Les valeurs d'énumération affichées à un client font partie du fil, pas de
 * l'interface : `optimisation`, le motif d'un zéro résultat et celui d'un repli voyagent
 * chacun avec son `libelle_*`, et c'est l'étape 11 qui les y a fait ajouter — les afficher
 * bruts (« critere_trop_strict ») n'aurait pas été « le cas zéro résultat rendu lisible ».
 *
 * **Une seule exception, et elle a un précédent** : `operateur` est rendu par `≥ / ≤`,
 * c'est-à-dire par un symbole et non par du français. `scripts/console.py` fait exactement
 * le même geste depuis l'étape 8.
 *
 * ### Le rendu est ciblé, et il n'y a pas de micro-framework
 *
 * Le fil est **ajouté** entrée par entrée (les entrées portent une clé stable, et l'entrée
 * déjà posée n'est jamais reconstruite) ; le panneau, qui tient en vingt nœuds, est refait
 * en entier. C'est la conséquence assumée de l'arbitrage A : un rendu par événement, ciblé,
 * suffit largement à cette page.
 */

/** Les prix sont des chaînes, et le restent — voir l'en-tête d'`etat.js`. */
function montant(chaine) {
    return `${chaine} $`;
}

/** Un élément, son texte, sa classe. La brique de tout ce fichier. */
function noeud(balise, classe, texte) {
    const element = document.createElement(balise);
    if (classe) element.className = classe;
    if (texte !== undefined && texte !== null) element.textContent = String(texte);
    return element;
}

/**
 * Du markdown vers des nœuds : **le gras et les sauts de ligne, rien d'autre.**
 *
 * Une trentaine de lignes qui ne peuvent structurellement pas ouvrir d'injection : le
 * texte entre par `createTextNode`, et les seuls éléments créés le sont par nous.
 */
export function enNoeuds(texte) {
    const fragment = document.createDocumentFragment();
    texte.split("\n").forEach((ligne, indice) => {
        if (indice > 0) fragment.appendChild(document.createElement("br"));
        // Les segments d'indice impair sont ceux qui étaient entre `**` : un `**` non
        // apparié laisse donc son segment en clair, ce qui est le comportement voulu.
        ligne.split("**").forEach((segment, rang) => {
            if (segment === "") return;
            if (rang % 2 === 1) {
                fragment.appendChild(noeud("strong", null, segment));
            } else {
                fragment.appendChild(document.createTextNode(segment));
            }
        });
    });
    return fragment;
}

// --------------------------------------------------------------------------- #
// Le fil de conversation
// --------------------------------------------------------------------------- #

/**
 * Une entrée de fil vers son élément. `null` quand le mode produit la masque.
 *
 * ⚠️ **Masquer, ce n'est pas jeter** (arbitrage E) : l'entrée reste dans l'état, et une
 * bascule de l'interrupteur la fait apparaître avec tout ce qui l'a précédée.
 */
function entree(element, coulisses) {
    switch (element.genre) {
        case "client":
            return parole("client", "vous", element.texte);
        case "assistant":
            return parole("assistant", "rAiyon", element.texte);
        case "question":
            return parole("assistant", "rAiyon", element.donnees.question);
        case "produits":
            return cartes(element.donnees);
        case "repli":
            return repli(element.donnees);
        case "incident":
            return noeud("p", "incident", element.texte);
        case "rejet":
            return coulisses ? rejet(element.donnees) : null;
        default:
            return null;
    }
}

function parole(classe, qui, texte) {
    const bulle = noeud("div", `parole ${classe}`);
    bulle.appendChild(noeud("span", "qui", qui));
    const corps = noeud("p", "texte");
    corps.appendChild(enNoeuds(texte));
    bulle.appendChild(corps);
    return bulle;
}

/**
 * Un repli est du texte **écrit en Python**, que le modèle n'a jamais produit. Il est donc
 * marqué comme tel : le confondre avec une réponse du modèle ferait croire à une phrase que
 * personne n'a écrite, et c'est aussi celui qui disparaîtra au rechargement (§7).
 */
function repli(donnees) {
    const bloc = parole("assistant repli", "rAiyon", donnees.message);
    bloc.appendChild(noeud("p", "mention", `réponse écrite par le code — ${donnees.libelle_motif}`));
    return bloc;
}

/**
 * Les cartes produits, **dans le fil et à l'endroit où elles sont arrivées** (arbitrage C).
 *
 * `produits` et `au_dessus_du_budget` restent séparés, comme §3.10 l'exige : les confondre
 * ici rouvrirait à l'écran ce que le moteur a fermé. Le hors-budget porte son écart exact.
 */
function cartes(donnees) {
    const bloc = noeud("div", "resultats");

    // Sur un zéro résultat, « 0 trouvés sur 0 candidats » se lit comme une panne. C'est le
    // diagnostic qui dit le cas, et il le dit mieux : le compte ne s'affiche donc que
    // lorsqu'il y a quelque chose à compter.
    if (donnees.produits.length > 0) {
        bloc.appendChild(
            noeud(
                "p",
                "compte",
                `${donnees.produits.length} trouvés sur ${donnees.candidats_trouves} candidats`,
            ),
        );
        const liste = noeud("div", "grille");
        donnees.produits.forEach((produit) => liste.appendChild(carte(produit, null)));
        bloc.appendChild(liste);
    }

    if (donnees.au_dessus_du_budget.length > 0) {
        bloc.appendChild(noeud("p", "compte", "Au-dessus du budget, avec l'écart exact :"));
        const hors = noeud("div", "grille");
        donnees.au_dessus_du_budget.forEach((ligne) =>
            hors.appendChild(carte(ligne.produit, ligne.ecart_usd)),
        );
        bloc.appendChild(hors);
    }

    if (donnees.diagnostic !== null) bloc.appendChild(diagnostic(donnees.diagnostic));
    return bloc;
}

function carte(produit, ecart) {
    const element = noeud("article", ecart === null ? "carte" : "carte hors-budget");
    const tete = noeud("header");
    tete.appendChild(noeud("h3", null, produit.nom));
    tete.appendChild(noeud("span", "prix", montant(produit.prix_usd)));
    element.appendChild(tete);

    if (ecart !== null) {
        element.appendChild(noeud("p", "ecart", `+${montant(ecart)} au-dessus du budget`));
    }

    const specs = noeud("dl", "specs");
    produit.specs.forEach((spec) => {
        specs.appendChild(noeud("dt", null, spec.libelle_fr));
        specs.appendChild(noeud("dd", null, avecUnite(spec.valeur, spec.unite)));
    });
    element.appendChild(specs);
    element.appendChild(noeud("p", "identifiant", produit.id));
    return element;
}

/**
 * ⚠️ Une valeur booléenne reste un booléen sur le fil (`_valeur()` côté serveur teste `bool`
 * **avant** `int`, pour ne pas envoyer `1` là où le catalogue dit « avec micro »). Elle n'a
 * pas de libellé français au registre : l'interface le fournit, parce que c'est son propre
 * vocabulaire et non celui du catalogue.
 */
function avecUnite(valeur, unite) {
    if (valeur === true) return "oui";
    if (valeur === false) return "non";
    return unite ? `${valeur} ${unite}` : String(valeur);
}

/**
 * Le zéro résultat, dit et proposé — **critère d'acceptation nº6**, et c'est ici qu'il se
 * voit pour la première fois. Une proposition est formulée, jamais appliquée : desserrer
 * coûte une parole du client (§3.17).
 */
function diagnostic(donnees) {
    const bloc = noeud("div", "diagnostic");
    bloc.appendChild(noeud("p", "motif", `Aucun produit ne convient — ${donnees.libelle_motif}`));
    const liste = noeud("ul");
    donnees.propositions.forEach((proposition) => {
        const cible =
            proposition.valeur_atteignable === null
                ? ""
                : ` jusqu'à ${avecUnite(proposition.valeur_atteignable, proposition.unite)}`;
        liste.appendChild(
            noeud(
                "li",
                null,
                `relâcher ${proposition.libelle_fr}${cible} rouvrirait ` +
                    `${proposition.produits_rouverts} produit(s)`,
            ),
        );
    });
    bloc.appendChild(liste);
    return bloc;
}

/**
 * Un texte refusé par le validateur — **mode coulisses uniquement** (arbitrage E).
 *
 * C'est la seule preuve visible à l'écran que l'anti-hallucination est tenue par du **code**
 * et non par un prompt : le montant refusé n'a jamais atteint le client, et il est ici avec
 * son code de grief, son extrait et la correction demandée.
 */
function rejet(donnees) {
    const bloc = noeud("div", "rejet");
    bloc.appendChild(
        noeud(
            "p",
            "tete",
            `texte refusé (${donnees.origine}, tentative ${donnees.tentative}) — ` +
                `${donnees.griefs.length} grief(s)`,
        ),
    );
    donnees.griefs.forEach((grief) => {
        const ligne = noeud("div", "grief");
        ligne.appendChild(noeud("code", "code", grief.code));
        ligne.appendChild(noeud("q", "extrait", grief.extrait));
        ligne.appendChild(noeud("p", "correction", grief.correction));
        bloc.appendChild(ligne);
    });
    return bloc;
}

// --------------------------------------------------------------------------- #
// Le panneau — ce que le code a compris, et son activité
// --------------------------------------------------------------------------- #

function rendreLeBesoin(cible, besoin) {
    cible.replaceChildren();
    if (besoin === null) {
        cible.appendChild(noeud("p", "vide", "Rien encore — le panneau se remplit au premier message."));
        return;
    }

    cible.appendChild(noeud("p", "categorie", besoin.libelle_categorie));

    const liste = noeud("ul", "criteres");
    besoin.criteres.forEach((critere) => liste.appendChild(ligneDeCritere(critere)));
    if (besoin.criteres.length > 0) cible.appendChild(liste);

    const chiffres = noeud("ul", "chiffres");
    if (besoin.budget_usd !== null) {
        chiffres.appendChild(noeud("li", null, `budget ${montant(besoin.budget_usd)}`));
    }
    if (besoin.optimisation !== "aucune") {
        chiffres.appendChild(
            noeud("li", null, `optimise ${besoin.libelle_optimisation}`),
        );
    }
    if (chiffres.childElementCount > 0) cible.appendChild(chiffres);

    // ⚠️ `mouvements_refuses` porte ce qui **n'a pas** été appliqué. C'est ce qui permet
    // d'afficher « je garde 144 Hz » plutôt que de laisser le client croire qu'il a été
    // entendu (§3.17). Toujours visible, mode produit compris : c'est une information de
    // produit, pas une mécanique interne.
    besoin.mouvements_refuses.forEach((refuse) => {
        const ligne = noeud("p", "refus");
        ligne.appendChild(noeud("strong", null, refuse.libelle_fr));
        ligne.appendChild(document.createTextNode(` — non appliqué : ${refuse.motif}`));
        cible.appendChild(ligne);
    });
}

/** `≥ 144 Hz fréquence de rafraîchissement (bloquant)` — libellé et unité venus du fil. */
function ligneDeCritere(critere) {
    const prefixe = { au_moins: "≥ ", au_plus: "≤ ", egal: "" }[critere.operateur] ?? "";
    const ligne = noeud("li");
    ligne.appendChild(
        noeud("span", "valeur", `${prefixe}${avecUnite(critere.valeur, critere.unite)}`),
    );
    ligne.appendChild(noeud("span", "libelle", critere.libelle_fr));
    ligne.appendChild(noeud("span", `importance ${critere.importance}`, critere.importance));
    return ligne;
}

function rendreLeCatalogue(cible, etat) {
    cible.replaceChildren();
    const { sondage, suggestion, coulisses } = etat;

    if (sondage === null && suggestion === null) {
        cible.appendChild(noeud("p", "vide", "Aucune lecture du catalogue pour l'instant."));
        return;
    }

    if (sondage !== null) {
        const chiffres = noeud("ul", "chiffres");
        chiffres.appendChild(noeud("li", null, `${sondage.dans_le_budget} candidats dans le budget`));
        if (sondage.dans_la_zone_de_tolerance > 0) {
            chiffres.appendChild(
                noeud("li", null, `${sondage.dans_la_zone_de_tolerance} dans la zone de tolérance`),
            );
        }
        // ⚠️ `fourchette_prix` vaut parfois `null`, et **c'est une information** : le
        // sous-catalogue est vide. Un « 0 $ à 0 $ » dirait qu'il existe des produits
        // gratuits.
        chiffres.appendChild(
            noeud(
                "li",
                null,
                sondage.fourchette_prix === null
                    ? "aucun produit dans ce sous-catalogue"
                    : `${montant(sondage.fourchette_prix.plus_bas)} à ${montant(sondage.fourchette_prix.plus_haut)}`,
            ),
        );
        cible.appendChild(chiffres);

        if (coulisses) {
            sondage.champs.forEach((champ) => cible.appendChild(distribution(champ)));
        }
    }

    // ⚠️ En mode produit, une `suggested_question` seule ne montrait **rien** : le bloc
    // apparaissait vide. Or l'outil a bel et bien lu le catalogue, et son nombre de
    // candidats est un fait du code — pas une mécanique interne. Il s'affiche donc, et
    // c'est seulement le champ de plus fort gain et son score qui restent en coulisses.
    if (suggestion !== null) {
        if (sondage === null) {
            const chiffres = noeud("ul", "chiffres");
            chiffres.appendChild(noeud("li", null, `${suggestion.candidats} candidats`));
            cible.appendChild(chiffres);
        }
        if (coulisses) cible.appendChild(question(suggestion));
    }

    // Filet : aucune combinaison ne doit laisser un bloc vide à l'écran.
    if (cible.childElementCount === 0) {
        cible.appendChild(noeud("p", "vide", "Aucune lecture du catalogue pour l'instant."));
    }
}

/** Une distribution entière — **mode coulisses** : c'est ce que le catalogue contient. */
function distribution(champ) {
    const bloc = noeud("div", "distribution");
    bloc.appendChild(
        noeud("p", "tete", `${champ.libelle_fr} — ${champ.renseignes}/${champ.total} renseignés`),
    );
    const liste = noeud("ul");
    champ.valeurs.forEach((valeur) => {
        liste.appendChild(
            noeud("li", null, `${avecUnite(valeur.valeur, champ.unite)} · ${valeur.effectif}`),
        );
    });
    if (champ.tronque) liste.appendChild(noeud("li", "tronque", `… ${champ.total_distinct} valeurs`));
    bloc.appendChild(liste);
    return bloc;
}

/**
 * Le champ de plus fort gain d'information — **mode coulisses**. C'est une *suggestion*, pas
 * un ordre (§3.8) : le modèle reste libre de poser une autre question, et l'écart entre les
 * deux est précisément ce qu'on vient lire ici.
 */
function question(suggestion) {
    const bloc = noeud("div", "suggestion");
    if (suggestion.budget !== null) {
        bloc.appendChild(noeud("p", "tete", "budget inconnu — il passe devant"));
    } else if (suggestion.champ === null) {
        // ⚠️ `champ` à `null` **est une information** : plus rien ne discrimine.
        bloc.appendChild(noeud("p", "tete", "plus rien ne discrimine"));
    } else {
        bloc.appendChild(
            noeud("p", "tete", `question suggérée : ${suggestion.champ.libelle_fr} (${suggestion.champ.score})`),
        );
    }
    return bloc;
}

// --------------------------------------------------------------------------- #
// L'indicateur d'attente — le dernier événement reçu, et rien d'autre
// --------------------------------------------------------------------------- #

/**
 * ⚠️ **N'invente pas d'étapes que le fil ne dit pas** (arbitrage D).
 *
 * Chaque entrée décrit l'événement qui vient d'arriver, suivi de « … » pour dire qu'on
 * attend la suite. Il n'y a pas de scénario ici, pas de barre de progression, pas d'étape
 * « connexion » ou « réflexion » : la seule chose qu'on sache est ce que le fil a dit.
 *
 * `products_found` → « vérification de la réponse » est la seule entrée qui parle d'autre
 * chose que de son propre événement, et elle le peut : entre le dernier événement d'outil et
 * `message`, ce qui se passe **est** la relecture par le validateur. C'est ce que l'arbitrage
 * A de l'étape 9 a acheté, et c'est la seule chose qui bouge à ce moment-là.
 */
const ATTENTES = {
    criteria_updated: "critères enregistrés…",
    catalog_probe: "lecture du catalogue…",
    suggested_question: "recherche de la question la plus utile…",
    products_found: "vérification de la réponse…",
    text_rejected: "réponse refusée par le validateur — régénération…",
    question: "vérification de la question…",
    message: "…",
};

// --------------------------------------------------------------------------- #
// Le rendu complet
// --------------------------------------------------------------------------- #

/**
 * L'état vers l'écran. Appelée à chaque événement, et **seulement** ici.
 *
 * Le fil est ajouté entrée par entrée ; le panneau est refait. Quand l'interrupteur des
 * coulisses bascule, le fil est reconstruit en entier — c'est le seul moment où il l'est,
 * et c'est ce qui fait apparaître les rejets déjà reçus.
 */
export function rendre(vue, etat, { refaireLeFil = false } = {}) {
    const enBas = auBasDuFil(vue.fil);

    if (refaireLeFil) {
        vue.fil.replaceChildren();
        vue.posees = new Set();
    }

    etat.fil.forEach((element) => {
        if (vue.posees.has(element.cle)) return;
        const rendu = entree(element, etat.coulisses);
        if (rendu === null) return; // masqué par le mode produit — conservé dans l'état
        rendu.dataset.cle = element.cle;
        vue.fil.appendChild(rendu);
        vue.posees.add(element.cle);
    });

    vue.accueil.hidden = etat.fil.length > 0;
    rendreLavis(vue, etat);
    rendreLeBesoin(vue.besoin, etat.besoin);
    rendreLeCatalogue(vue.catalogue, etat);

    vue.activite.hidden = !etat.enCours;
    // `activite` vaut `null` au démarrage du tour, et le repli « … » est alors le seul
    // affichage honnête : rien n'est encore arrivé qui puisse être nommé.
    vue.activite.textContent = ATTENTES[etat.activite] ?? "…";

    vue.message.disabled = etat.enCours;
    vue.envoyer.disabled = etat.enCours;

    vue.identifiant.hidden = etat.identifiant === null;
    vue.identifiant.textContent = etat.identifiant ?? "";
    vue.etiquette.textContent = etat.identifiant === null ? "nouvelle conversation" : "session";

    // ⚠️ **Le défilement n'est pas inconditionnel** : on ne suit le fil que si l'on y était
    // déjà. Sinon, relire une réponse pendant que la suivante arrive devient impossible.
    if (enBas) vue.fil.scrollTop = vue.fil.scrollHeight;
}

function auBasDuFil(fil) {
    return fil.scrollHeight - fil.scrollTop - fil.clientHeight < 40;
}

/**
 * Ce que la réhydratation ne rejoue pas, dit plutôt que masqué (arbitrage G), et les avis de
 * l'interface sur elle-même — 409, session périmée, réseau coupé.
 */
function rendreLavis(vue, etat) {
    const phrases = [];
    if (etat.reprise) {
        phrases.push(
            "Conversation reprise : l'état et les paroles reviennent de la base, mais les " +
                "résultats détaillés ne sont pas rejoués — le serveur relit la prose, jamais " +
                "les événements. Un tour clos par une réponse de repli revient sans sa réponse.",
        );
    }
    if (etat.avis !== null) phrases.push(etat.avis);

    vue.avis.hidden = phrases.length === 0;
    vue.avis.replaceChildren();
    phrases.forEach((phrase) => vue.avis.appendChild(noeud("p", null, phrase)));
}
