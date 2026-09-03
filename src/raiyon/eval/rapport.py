"""`Mesures` vers un tableau markdown. **Pur, et stable octet pour octet.**

`docs/eval/rapport.md` est committé : deux exécutions sur les mêmes mesures doivent
produire exactement le même fichier, sans quoi chaque `make eval` produirait un diff qui
ne dit rien. Toutes les listes sont donc triées, et rien n'est daté ici — la date d'un
enregistrement vit dans l'en-tête des cassettes, pas dans le rapport.

---

### Le rapport doit se défendre contre une lecture qui s'arrêterait à la première ligne

C'est la raison d'être d'`AVERTISSEMENT`, et il n'est pas décoratif.

Les critères nº1 et nº2 sont garantis **par construction** depuis l'étape 9 : le validateur
refuse le texte fautif, régénère une fois, puis se replie sur un template écrit en Python.
Un tableau qui affiche `0` sur ces deux lignes ne dit donc pas « le modèle n'a pas menti » —
il dit « le mécanisme a fonctionné ».

> **Un tableau où le critère nº1 vaut 0 et le taux de repli vaut 30 % décrit un produit
> qui échoue.**

Sans cette phrase dans le fichier lui-même, quelqu'un lira la première ligne et s'arrêtera
là — et ce quelqu'un, dans six mois, c'est l'auteur.

### Trois lignes n'ont pas de seuil, et ce sont les plus intéressantes

Taux de rejet, taux de repli, itérations par tour. Ce sont elles qui **bougent** quand un
prompt change, et elles que l'étape 13 cherchera à faire descendre. Les critères binaires,
eux, sont déjà tenus par du code et ne bougeront pas.
"""

import statistics
from collections.abc import Sequence

from raiyon.eval.cout import POURQUOI_LES_DEUX_MOITIES, PROVENANCE, Cout
from raiyon.eval.metriques import (
    RESERVE_ITERATIONS,
    SEUIL_TOP3,
    SEUIL_TOURS,
    Attente,
    Mesures,
    MesuresDunePrise,
    chiffres_de_la_prose,
)

TITRE = "# Rapport d'éval — rAiyon"

LARGEUR_DE_CELLULE = 400
"""Au-delà, une phrase est tronquée dans un tableau markdown. C'est haut exprès : une
prose de recommandation entière doit tenir, et seul un texte manifestement anormal est
coupé. La prose des tours de domaine, elle, n'est **jamais** tronquée — elle est publiée
en bloc de citation, hors tableau, parce qu'elle est la preuve."""

AVERTISSEMENT = """> ⚠️ **Comment lire ce tableau.** Les critères nº1 et nº2 sont garantis **par
> construction** depuis l'étape 9 : le validateur refuse le texte fautif, régénère une
> fois, puis se replie sur un template écrit en Python. Un `0` sur ces lignes ne dit pas
> « le modèle n'a pas menti », il dit « le mécanisme a fonctionné ». Une valeur non nulle
> signifierait que **le validateur a un trou** — c'est là toute l'information.
>
> **Un tableau où le critère nº1 vaut 0 et le taux de repli vaut 30 % décrit un produit
> qui échoue.** Les trois couches se lisent ensemble : ce qui est **livré**, ce que le
> modèle a **tenté** (taux de rejet), et ce qui a fini en **repli** — une réponse
> dégradée, servie au client."""

TENU = "✅"
VIOLE = "❌"
SANS_OBJET = "—"


def rendre(mesures: Mesures, *, reserves: Sequence[str] = (), cout: Cout | None = None) -> str:
    """Le rapport entier. Une seule fonction publique : c'est un fichier, pas une API.

    `cout` porte la **mesure nº7** — les appels au modèle par tour client. Il est séparé de
    `mesures` parce que sa provenance l'est : voir `raiyon.eval.cout`. `None` veut dire que
    ce rendu ne vient d'aucun jeu enregistré — c'est le cas des tests purs de ce module —
    et la ligne nº7 n'est alors pas écrite. Sur le chemin de `make eval` il est toujours
    renseigné : `mesurer_le_jeu()` le construit à chaque fois, publiable ou non.

    `reserves` porte ce que les chiffres ne disent pas d'eux-mêmes — une prise écartée,
    une base composée de deux enregistrements. **Elles vont en tête, avant les tableaux** :
    une réserve lue après les chiffres arrive trop tard, la conclusion est déjà prise.

    Sans elles, un rapport dont une cassette a été écartée affiche « 7 griefs sur 42
    tours » avec exactement la même autorité qu'un rapport complet, et rien ne dit que la
    prise manquante en portait quatre. C'est le mode d'échec que ce fichier existe pour
    empêcher, appliqué à lui-même.
    """
    sections = [
        TITRE,
        "",
        AVERTISSEMENT,
        "",
        *_reserves(reserves),
        "## Critères d'acceptation",
        "",
        *_tableau_des_criteres(mesures),
        "",
        "## Ce que le modèle a tenté, et ce qui a fini en repli",
        "",
        *_tableau_des_couches(mesures, cout),
        "",
        *_notes_des_couches(cout),
        "### Rejets par origine et par code",
        "",
        *_tableau_des_rejets(mesures),
        "",
        "### Replis par motif",
        "",
        *_tableau_des_replis(mesures),
        "",
        "## Par scénario",
        "",
        *_tableau_des_prises(mesures),
        "",
        *_ecarts(mesures),
        "",
        *_manquements(mesures),
        "",
        *_appendice_des_refus(mesures),
        "",
        *_appendice_du_domaine(mesures),
        "",
        *_appendice_du_markdown(mesures),
    ]
    return "\n".join(sections).rstrip("\n") + "\n"


# --------------------------------------------------------------------------- #
# Les tableaux
# --------------------------------------------------------------------------- #


def _tableau(entetes: Sequence[str], lignes: Sequence[Sequence[str]]) -> list[str]:
    """Un tableau markdown sans alignement de colonnes.

    Aligner à la largeur du contenu produirait un diff sur **toutes** les lignes dès
    qu'une valeur s'allonge d'un caractère. Le fichier est committé : la lisibilité du
    diff prime sur celle de la source, et le markdown rendu est identique.
    """
    return [
        "| " + " | ".join(entetes) + " |",
        "|" + "|".join("---" for _ in entetes) + "|",
        *["| " + " | ".join(ligne) + " |" for ligne in lignes],
    ]


def _reserves(reserves: Sequence[str]) -> list[str]:
    """Ce que les chiffres ne disent pas d'eux-mêmes, en tête et en évidence."""
    if not reserves:
        return []
    return [
        "> ⚠️ **Ce que ces chiffres ne disent pas d'eux-mêmes.**",
        ">",
        *[ligne for reserve in reserves for ligne in _en_citation(reserve)],
        "",
    ]


def _en_citation(reserve: str) -> list[str]:
    """Une réserve en bloc de citation markdown, tiret sur la première ligne.

    ⚠️ **Une ligne vide d'une réserve rend `">"` nu, jamais `">   "`.** Le préfixe de citation
    appliqué à une chaîne vide laisserait trois espaces en fin de ligne : le crochet
    `trailing-whitespace` les retire au commit, le rendu les remet au `make eval` suivant, et
    le fichier committé produit un diff permanent — celui qu'on cesse de lire. Découvert à
    l'étape 15, jalon 5, sur la première réserve à plusieurs paragraphes.
    """
    return [
        (f"> - {ligne}" if rang == 0 else f">   {ligne}").rstrip()
        for rang, ligne in enumerate(reserve.splitlines())
    ]


def _tableau_des_criteres(mesures: Mesures) -> list[str]:
    """Les six critères du §4, dans l'ordre du §4. Le nº5 n'est pas mesuré ici."""
    return _tableau(
        ("#", "Critère", "Seuil", "Mesuré", "Verdict"),
        (
            (
                "1",
                "Aucun produit, prix ou spec inventé — **dans le texte livré**",
                "0",
                f"{mesures.griefs_livres} grief(s)",
                _verdict(mesures.critere_1),
            ),
            (
                "2",
                "Budget jamais dépassé sans présentation explicite",
                "0",
                f"{mesures.violations_budget} violation(s)",
                _verdict(mesures.critere_2),
            ),
            (
                "3",
                "Délai avant première valeur — en **tours client**",
                f"médiane ≤ {SEUIL_TOURS}",
                _mediane(mesures),
                _verdict(mesures.critere_3),
            ),
            (
                "4",
                "Le produit attendu est dans le top 3",
                f"≥ {SEUIL_TOP3:.0%}".replace("%", " %"),
                _part_top3(mesures),
                _verdict(mesures.critere_4),
            ),
            (
                "5",
                "Moteur de matching testable sans API",
                "binaire",
                "hors de ce rapport — `make check`",
                SANS_OBJET,
            ),
            (
                "6",
                "Cas zéro résultat traité proprement",
                "binaire",
                f"{mesures.zero_resultats_traites}/{mesures.zero_resultats} traité(s)",
                _verdict(mesures.critere_6),
            ),
        ),
    )


def _tableau_des_couches(mesures: Mesures, cout: Cout | None = None) -> list[str]:
    """Les trois lignes sans seuil. Ce sont elles que l'étape 13 fera bouger.

    La mesure nº7 s'y ajoute en dernier, sur **trois** lignes depuis l'étape 16 — les
    appels, l'entrée facturée, la sortie —, et chacune **porte sa provenance dans sa colonne
    de droite** : ce sont les seules lignes du tableau qui ne soient pas recalculées au
    rejeu. Les trois vont ensemble parce que les deux premières peuvent aller en sens
    contraire, ce que la note du dessous dit avec les chiffres qui l'ont montré.
    """
    iterations = mesures.iterations
    return _tableau(
        ("Mesure", "Valeur", "Seuil"),
        (
            (
                "Taux de rejet du validateur",
                f"{len(mesures.rejets)} grief(s) sur {mesures.tours} tour(s) "
                f"— {mesures.taux_de_rejet:.2f}/tour",
                "publié",
            ),
            (
                "Taux de repli",
                f"{mesures.tours_replies} tour(s) sur {mesures.tours} "
                f"— {mesures.taux_de_repli:.0%}".replace("%", " %"),
                "publié",
            ),
            (
                "Itérations par tour",
                _distribution(iterations),
                "publié",
            ),
            (
                "Prises sans aucune valeur livrée",
                f"{mesures.prises_sans_valeur} sur {len(mesures.prises)}",
                "publié",
            ),
            (
                "Questions posées avant la première valeur",
                _mediane_des_questions(mesures),
                "publié — mesure la règle « donner avant de demander », pas le critère nº3",
            ),
            (
                "Règles du validateur jamais déclenchées",
                _regles_muettes(mesures),
                "publié — voir `tests/validateur/test_pieges.py`",
            ),
            (
                "Prises où `suggest_next_question` a signalé le budget manquant",
                f"{mesures.prises_ou_loutil_a_signale_le_budget} sur {len(mesures.prises)}",
                "publié — **observation, pas exigence**",
            ),
            *(
                ()
                if cout is None
                else (
                    (
                        "Appels au modèle par tour client (mesure nº7)",
                        cout.en_ligne(),
                        "publié — **figé à l'enregistrement**, voir la note ci-dessous",
                    ),
                    (
                        "Jetons d'entrée facturés (mesure nº7)",
                        cout.en_ligne_entree(),
                        "publié — **figé à l'enregistrement**, voir la note ci-dessous",
                    ),
                    (
                        "Jetons de sortie (mesure nº7)",
                        cout.en_ligne_sortie(),
                        "publié — **figé à l'enregistrement**, voir la note ci-dessous",
                    ),
                )
            ),
        ),
    )


def _notes_des_couches(cout: Cout | None) -> list[str]:
    """Les deux réserves que ce tableau ne porte pas dans ses colonnes.

    La provenance de la mesure nº7, **pourquoi elle a deux moitiés**, et le fait
    qu'`iterations` cesse d'être comparable dès qu'on change d'orchestration. Toutes trois
    sont écrites **une seule fois** dans le dépôt, à côté de ce qu'elles qualifient —
    `raiyon.eval.cout` pour les deux premières, `raiyon.eval.metriques` pour la troisième.
    """
    return [
        *((PROVENANCE, "", POURQUOI_LES_DEUX_MOITIES, "") if cout is not None else ()),
        RESERVE_ITERATIONS,
        "",
    ]


def _tableau_des_rejets(mesures: Mesures) -> list[str]:
    """Par origine **et** par code : un taux global masquerait lequel des deux fuit."""
    if not mesures.rejets:
        return ["Aucun texte refusé par le validateur sur cette exécution."]
    comptes: dict[tuple[str, str], int] = {}
    for rejet in mesures.rejets:
        cle = (rejet.origine.value, rejet.code.value)
        comptes[cle] = comptes.get(cle, 0) + 1
    return _tableau(
        ("Origine", "Code de grief", "Rejets"),
        [(origine, code, str(comptes[(origine, code)])) for origine, code in sorted(comptes)],
    )


def _tableau_des_replis(mesures: Mesures) -> list[str]:
    """Un repli est une réponse **dégradée livrée au client**, pas un incident interne."""
    if not mesures.replis:
        return ["Aucun repli sur cette exécution."]
    comptes: dict[str, int] = {}
    for motif in mesures.replis:
        comptes[motif.value] = comptes.get(motif.value, 0) + 1
    return _tableau(
        ("Motif", "Tours repliés"),
        [(motif, str(comptes[motif])) for motif in sorted(comptes)],
    )


def _tableau_des_prises(mesures: Mesures) -> list[str]:
    """Une ligne par prise. Trois prises d'un même scénario se lisent côte à côte.

    C'est ce qui donne la **fourchette** de l'arbitrage D : trois valeurs alignées, dont
    on lit l'écart à l'œil. Ce n'est pas un intervalle de confiance et le rapport ne le
    présente jamais comme tel — voir `_ecarts()`.
    """
    return _tableau(
        (
            "Scénario",
            "Prise",
            "Tours",
            "Tours avant valeur",
            "Questions avant valeur",
            "Attendu top 3",
            "Rejets",
            "Replis",
            "Itér.",
            "Conforme",
        ),
        [
            (
                prise.scenario,
                str(prise.prise),
                str(prise.tours),
                _entier(prise.tours_avant_valeur),
                _entier(prise.questions_avant_valeur),
                _booleen(prise.attendu_en_top3),
                str(len(prise.rejets)),
                str(len(prise.replis)),
                _distribution(prise.iterations),
                TENU if prise.conforme else VIOLE,
            )
            for prise in sorted(mesures.prises, key=lambda prise: (prise.scenario, prise.prise))
        ],
    )


def _ecarts(mesures: Mesures) -> list[str]:
    """Ce que trois prises disent, et ce qu'elles ne disent pas (arbitrage D)."""
    lignes = [
        "## Dispersion, et ce qu'elle ne prouve pas",
        "",
        "La température n'est pas fixée (étape 8, arbitrage 12) : **une cassette est un",
        "tirage, pas une espérance.** Trois prises ont été enregistrées sur les scénarios",
        "ci-dessous, pour obtenir un ordre de grandeur du bruit sur les métriques nº3 et nº4.",
        "",
        "⚠️ **Trois prises ne sont pas un intervalle de confiance.** C'est un ordre de",
        "grandeur, et c'est déjà infiniment mieux que le plancher de bruit inconnu qu'on",
        "aurait sinon. Un écart de deux prompts inférieur à cet ordre de grandeur n'est pas",
        "un signal.",
        "",
    ]
    multiples = _scenarios_a_plusieurs_prises(mesures.prises)
    if not multiples:
        return [*lignes, "Aucun scénario n'a plus d'une prise sur cette exécution."]
    return [
        *lignes,
        *_tableau(
            ("Scénario", "Prises", "Tours avant valeur", "Attendu top 3"),
            [
                (
                    nom,
                    str(len(prises)),
                    _fourchette([prise.tours_avant_valeur for prise in prises]),
                    _fourchette_booleenne([prise.attendu_en_top3 for prise in prises]),
                )
                for nom, prises in multiples
            ],
        ),
    ]


def _manquements(mesures: Mesures) -> list[str]:
    """Les attentes binaires non tenues, nommées. Vide, la section dit qu'elle est vide."""
    lignes = ["## Attentes binaires non tenues", ""]
    if not mesures.attentes_manquees and not mesures.diagnostics_manques:
        return [*lignes, "Aucune."]
    rangs: list[tuple[str, str, str]] = [
        (scenario, str(prise), f"attente `{attente.value}`")
        for scenario, prise, attente in mesures.attentes_manquees
    ]
    rangs += [
        (scenario, str(prise), f"diagnostic attendu `{motif.value}`")
        for scenario, prise, motif in mesures.diagnostics_manques
    ]
    return [*lignes, *_tableau(("Scénario", "Prise", "Ce qui manque"), sorted(rangs))]


# --------------------------------------------------------------------------- #
# Les trois appendices — étape 13, jalon 0
# --------------------------------------------------------------------------- #


def _appendice_des_refus(mesures: Mesures) -> list[str]:
    """Une ligne par grief, **avec la phrase que le validateur a refusée** (point A).

    Sans cet appendice, l'étape 13 itérerait sur des compteurs : un taux qui descend de 11
    à 5 ne dit pas **quelle forme** a disparu, et c'est la seule chose qu'on veuille savoir
    d'un changement de prompt.

    ⚠️ **Il est dérivé du verdict du validateur, jamais d'une liste écrite ici.** Un
    sixième code de `CodeGrief` y apparaît sans qu'on touche à ce fichier — même raison
    qu'à la ligne « règles jamais déclenchées », et le même mode d'échec évité : un
    appendice qui mentirait par omission sur exactement ce qu'il existe pour montrer.

    ⚠️ **Ces phrases n'ont jamais atteint le client.** Elles ont été refusées, puis
    régénérées ou repliées. Les publier ici mesure ce que le modèle a **tenté**.
    """
    lignes = [
        "## Appendice A — les phrases refusées",
        "",
        "Une ligne par grief. ⚠️ **Aucune de ces phrases n'a atteint le client** : elles ont",
        "été refusées, puis régénérées ou repliées. Ce que cet appendice montre est ce que le",
        "modèle a **tenté**, et sous quelle forme — un taux de rejet qui baisse ne dit pas",
        "laquelle de ces formes a disparu.",
        "",
    ]
    if not mesures.refus:
        return [*lignes, "Aucun texte refusé par le validateur sur cette exécution."]
    return [
        *lignes,
        *_tableau(
            ("Scénario", "Prise", "Tour", "Origine", "Code", "Extrait", "Phrase refusée"),
            [
                (
                    refus.scenario,
                    str(refus.prise),
                    str(refus.tour),
                    refus.origine.value,
                    f"`{refus.code.value}`",
                    _cellule(refus.extrait),
                    _cellule(refus.phrase),
                )
                for refus in mesures.refus
            ],
        ),
    ]


def _appendice_du_domaine(mesures: Mesures) -> list[str]:
    """La prose **entière** des tours déclarés de domaine, et son compte de chiffres.

    C'est le point D du jalon 0, et sa moitié la plus importante : **l'appendice verbatim
    est la preuve, le compteur n'en est que le résumé.** La cible « ne pas affirmer un fait
    de domaine » se compare en lisant, sur un artefact committé que n'importe qui peut
    relire ; un compteur seul ne tranche rien.

    ⚠️ **Aucun seuil, et c'est délibéré.** L'attente évidente — « aucun chiffre sur un tour
    de domaine » — a été écrite puis refusée : elle est vraie sur v1 et deviendrait fausse
    dès qu'on demande au modèle de basculer sur ce que le catalogue contient, ce qui est
    précisément le bon comportement. Elle pénaliserait le changement qu'elle évalue. Voir
    la docstring de `scenario.py`.
    """
    lignes = [
        "## Appendice B — les tours de domaine, verbatim",
        "",
        "Les tours que les scénarios **déclarent** de domaine : le client y demande une",
        "explication technique que le catalogue ne porte pas. §2 borne ce que l'assistant",
        "sait faire — il conseille à partir du catalogue, il n'enseigne pas la technologie",
        "d'affichage.",
        "",
        "⚠️ **Aucun seuil ici, et le compteur de chiffres n'en est pas un.** Il lit des",
        "nombres, pas des faits : un ratio écrit `3000:1` compte pour **deux**, et « 32 de ces",
        "écrans sont en VA » compte pour un chiffre alors que c'est un fait **fourni**, donc",
        "exactement ce qu'on veut voir. La prose ci-dessous est la preuve ; le compte n'en est",
        "que le résumé.",
        "",
        f"**{mesures.chiffres_de_domaine} valeur(s) chiffrée(s)** sur "
        f"{mesures.tours_de_domaine} tour(s) de domaine.",
        "",
    ]
    blocs = [
        (prise.scenario, prise.prise, rang, ligne)
        for prise in sorted(mesures.prises, key=lambda prise: (prise.scenario, prise.prise))
        for rang, prose in prise.prose_de_domaine
        for ligne in prose
    ]
    if not blocs:
        return [*lignes, "Aucun scénario ne déclare de tour de domaine sur cette exécution."]
    for scenario, numero, rang, ligne in blocs:
        lignes.append(
            f"**{scenario}.{numero}, tour {rang}** — {chiffres_de_la_prose((ligne,))} chiffre(s)"
        )
        lignes.append("")
        lignes.extend(f"> {morceau}" if morceau else ">" for morceau in ligne.split("\n"))
        lignes.append("")
    return lignes[:-1]


def _appendice_du_markdown(mesures: Mesures) -> list[str]:
    """Les formes que le front n'interprète pas, comptées dans la prose **livrée** (point E).

    Mesuré sur v1 **avant** que v3 y touche : sans le point de départ, la baisse ne se lit
    pas. Publié sans seuil — c'est de l'affichage, pas un critère d'acceptation.
    """
    return [
        "## Appendice C — le markdown que le front ne rend pas",
        "",
        "`web/rendu.js` rend **deux formes et pas une de plus** : le gras `**…**` et les sauts",
        "de ligne. Le reste s'affiche tel quel — les backticks autour d'un identifiant sont",
        "visibles à l'écran, constaté en démonstration (§7). Le correctif est **au prompt**,",
        "pas au front : armer le front d'un parseur markdown rouvrirait la surface d'injection",
        "que l'arbitrage B de l'étape 11 ferme.",
        "",
        "Compté sur la prose **livrée**, sans seuil.",
        "",
        *_tableau(
            ("Forme", "Occurrences"),
            [(nom, str(compte)) for nom, compte in mesures.formes_markdown],
        ),
    ]


# --------------------------------------------------------------------------- #
# Formatage — chaque fonction rend la **même** chaîne pour la même entrée
# --------------------------------------------------------------------------- #


def _cellule(texte: str) -> str:
    """Un texte libre dans une cellule de tableau markdown, sans casser le tableau.

    Trois gestes, et chacun ferme un défaut réel du rendu : les sauts de ligne deviennent
    des espaces (un `\n` couperait la ligne du tableau en deux), les barres verticales sont
    échappées (une barre non échappée ouvrirait une colonne fantôme), et un texte
    manifestement anormal est tronqué.

    ⚠️ **La troncature ne s'applique pas à l'appendice B**, dont la prose est publiée en
    bloc de citation, hors tableau. Une preuve tronquée n'est plus une preuve.
    """
    plat = " ".join(texte.split()).replace("|", "\\|")
    return plat if len(plat) <= LARGEUR_DE_CELLULE else plat[:LARGEUR_DE_CELLULE] + "…"


def _verdict(tenu: bool | None) -> str:
    if tenu is None:
        return SANS_OBJET
    return TENU if tenu else VIOLE


def _booleen(valeur: bool | None) -> str:
    if valeur is None:
        return SANS_OBJET
    return "oui" if valeur else "non"


def _entier(valeur: int | None) -> str:
    return SANS_OBJET if valeur is None else str(valeur)


def _mediane(mesures: Mesures) -> str:
    """Le critère nº3 compte des **tours client** depuis le correctif de l'étape 12."""
    mediane = mesures.mediane_des_tours
    if mediane is None:
        return "aucune prise n'a livré de valeur"
    return f"{mediane:.1f} tour(s) sur {len(mesures.tours_par_prise)} prise(s)"


def _mediane_des_questions(mesures: Mesures) -> str:
    mediane = mesures.mediane_des_questions
    if mediane is None:
        return SANS_OBJET
    return f"médiane {mediane:.1f} sur {len(mesures.questions_par_prise)} prise(s)"


def _part_top3(mesures: Mesures) -> str:
    """Le rapport dit **sur combien de scénarios** la métrique porte (arbitrage F)."""
    part = mesures.part_attendus_en_top3
    if part is None:
        return "aucun scénario ne porte d'attendu"
    return (
        f"{part:.0%} ".replace("%", " %")
        + f"— {mesures.attendus_en_top3}/{mesures.prises_avec_attendu} prise(s) "
        "à réponse de référence"
    )


def _regles_muettes(mesures: Mesures) -> str:
    """Les codes de grief qu'aucun texte n'a levés. **Dérivé de `CodeGrief`.**

    ⚠️ **Six codes pour cinq règles** : `regle_montants` en lève deux —
    `prix_etranger_au_produit` quand la phrase nomme un produit,
    `montant_non_fourni` sinon. On compte donc les codes, qui sont les gestes de
    correction demandés au modèle, et pas les fonctions qui les produisent.

    Sans cette ligne, « 0,31 grief/tour » se lit comme une couverture. Avec elle, on sait
    sur quoi le chiffre porte — et à l'étape 13, un taux qui descend cesse d'être ambigu :
    on saura **quelles** règles ont cessé de tirer.
    """
    muets = mesures.codes_jamais_declenches
    if not muets:
        return "aucun — les six codes ont été levés au moins une fois"
    return f"{len(muets)} sur {len(muets) + len(mesures.codes_declenches)} : " + ", ".join(
        f"`{code.value}`" for code in muets
    )


def _distribution(valeurs: Sequence[int]) -> str:
    """`min à max (médiane N)`, ou la valeur seule quand il n'y en a qu'une."""
    if not valeurs:
        return SANS_OBJET
    bas, haut = min(valeurs), max(valeurs)
    if bas == haut:
        return str(bas)
    return f"{bas} à {haut} (médiane {statistics.median(valeurs):.1f})"


def _fourchette(valeurs: Sequence[int | None]) -> str:
    connus = [valeur for valeur in valeurs if valeur is not None]
    if not connus:
        return SANS_OBJET
    bas, haut = min(connus), max(connus)
    manquants = len(valeurs) - len(connus)
    suite = f" (+{manquants} sans valeur livrée)" if manquants else ""
    return (str(bas) if bas == haut else f"{bas} à {haut}") + suite


def _fourchette_booleenne(valeurs: Sequence[bool | None]) -> str:
    connus = [valeur for valeur in valeurs if valeur is not None]
    if not connus:
        return SANS_OBJET
    return f"{sum(connus)}/{len(connus)}"


def _scenarios_a_plusieurs_prises(
    prises: Sequence[MesuresDunePrise],
) -> list[tuple[str, list[MesuresDunePrise]]]:
    groupes: dict[str, list[MesuresDunePrise]] = {}
    for prise in prises:
        groupes.setdefault(prise.scenario, []).append(prise)
    return [
        (nom, sorted(groupe, key=lambda prise: prise.prise))
        for nom, groupe in sorted(groupes.items())
        if len(groupe) > 1
    ]


__all__ = ["AVERTISSEMENT", "Attente", "rendre"]
