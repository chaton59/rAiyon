"""Un message qui ne porte ni texte ni appel d'outil clôt le tour par un repli.

**Le défaut que ce fichier ferme a été trouvé en conversation réelle**, à
`make eval-live` (correctif de l'étape 12) : `claude-sonnet-5` émet des blocs `thinking`
sans qu'on les demande, et il lui est arrivé de n'en émettre **que** un — juste après un
repli de validation. `_depouiller()` ignore les types de blocs qu'il ne connaît pas, ce
qui est voulu ; mais il ne restait alors ni texte ni appel, et la boucle rendait son
`IssueDuTour` **sans avoir émis un seul événement**.

Le client recevait `done` et rien d'autre. Le client simulé a répondu « Euh… vous êtes
là ? », ce qui est la meilleure description du défaut qu'on puisse donner.

⚠️ **Le bloc inconnu de ces tests n'est pas `thinking` par hasard, et il n'est pas
`thinking` non plus.** Les cas sont écrits sur un type de bloc **quelconque** : ce que la
boucle doit garantir n'est pas « je sais traiter le thinking », c'est « je ne me tais
jamais ». Un `thinking` explicite figure dans un seul cas, pour dire d'où vient l'histoire.
"""

from faux_client import FauxClient, appel_outil, message, texte, verifier_appairage
from scenarios import ECRAN_144, jouer

from raiyon.agent.boucle import PHRASE_REPONSE_VIDE
from raiyon.agent.evenements import MotifDeRepli, Repli, Texte
from raiyon.tools.schema_outils import NOM_ENREGISTRER


def bloc_inconnu(genre: str = "thinking") -> dict:
    """Un bloc que `_depouiller()` ignore. Le contenu n'a aucune importance."""
    return {"type": genre, "thinking": "", "signature": "opaque"}


# --------------------------------------------------------------------------- #
# 1. Le tour est clos par un repli, et il émet exactement un événement
# --------------------------------------------------------------------------- #


def test_un_message_qui_ne_porte_quun_bloc_thinking_clot_le_tour_par_un_repli(contexte, outils):
    """Le cas observé en vrai. **Exactement un événement**, et c'est le repli."""
    client = FauxClient([message(bloc_inconnu())])

    evenements, issue = jouer(client, contexte, outils)

    assert len(evenements) == 1, (
        "le tour doit émettre un événement et un seul — sans lui le client reçoit `done` "
        f"et rien d'autre ; obtenu : {evenements}"
    )
    repli = evenements[0]
    assert isinstance(repli, Repli)
    assert repli.motif is MotifDeRepli.REPONSE_VIDE
    assert repli.message == PHRASE_REPONSE_VIDE
    assert issue.iterations == 1


def test_le_repli_vaut_pour_un_type_de_bloc_quelconque(contexte, outils):
    """La garantie n'est pas « je sais traiter le thinking », c'est « je ne me tais jamais ».

    Un type de bloc inventé de toutes pièces doit donner exactement le même résultat : la
    boucle ne connaît pas la liste des types que l'API peut produire, et elle n'a pas à la
    connaître.
    """
    client = FauxClient([message({"type": "un_bloc_de_2027", "charge": 42})])

    evenements, _ = jouer(client, contexte, outils)

    assert [type(evenement) for evenement in evenements] == [Repli]


def test_un_message_a_blocs_vides_clot_aussi_le_tour(contexte, outils):
    """Cas dégénéré : aucun bloc du tout. Même conclusion, pour la même raison."""
    evenements, _ = jouer(FauxClient([message()]), contexte, outils)

    assert [type(evenement) for evenement in evenements] == [Repli]


def test_un_texte_vide_nest_pas_du_texte(contexte, outils):
    """`_Message.texte` fait un `.strip()` : un bloc `text` blanc ne livre rien non plus.

    Sans cette ligne, un message `text` réduit à un saut de ligne passerait par la branche
    « fin de tour normale » et le client recevrait un `Texte` vide — un silence déguisé en
    réponse, ce qui est pire qu'un silence.
    """
    evenements, _ = jouer(FauxClient([message(texte("   \n  "))]), contexte, outils)

    assert [type(evenement) for evenement in evenements] == [Repli]


def test_un_message_avec_texte_ne_se_replie_pas(contexte, outils):
    """Contre-épreuve. Sans elle, la branche pourrait replier **tous** les tours."""
    evenements, _ = jouer(FauxClient([message(texte("Voici trois écrans."))]), contexte, outils)

    assert [type(evenement) for evenement in evenements] == [Texte]


def test_un_bloc_inconnu_accompagne_de_texte_ne_se_replie_pas(contexte, outils):
    """Le cas nominal de `claude-sonnet-5` : `thinking` **puis** `text`. Rien ne change."""
    client = FauxClient([message(bloc_inconnu(), texte("Voici trois écrans."))])

    evenements, _ = jouer(client, contexte, outils)

    assert [type(evenement) for evenement in evenements] == [Texte]


def test_un_bloc_inconnu_accompagne_dun_appel_doutil_ne_se_replie_pas(contexte, outils):
    """L'autre cas nominal : `thinking` **puis** `tool_use`. La boucle continue."""
    client = FauxClient(
        [
            message(bloc_inconnu(), appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(texte("C'est noté.")),
        ]
    )

    evenements, _ = jouer(client, contexte, outils)

    assert [type(evenement).__name__ for evenement in evenements] == ["CriteresMisAJour", "Texte"]


# --------------------------------------------------------------------------- #
# 2. L'historique reste celui que l'API accepte
# --------------------------------------------------------------------------- #


def test_le_message_vide_reste_dans_lhistorique_persiste(contexte, outils):
    """Il **reste**, et c'est voulu — comme le message fautif d'un rejet de validation.

    Le retirer donnerait un historique qui ne décrit pas la conversation qui a eu lieu, et
    le modèle relirait au tour suivant une suite de messages dont un manque. Le repli, lui,
    n'y entre pas : c'est du texte écrit en Python, que le modèle n'a jamais produit
    (§7, « les messages de repli ne sont pas persistés »).
    """
    client = FauxClient([message(bloc_inconnu())])

    _, issue = jouer(client, contexte, outils)

    assert len(issue.tours) == 1
    assert issue.tours[0].role == "assistant"
    assert issue.tours[0].blocs == [bloc_inconnu()]
    assert all(PHRASE_REPONSE_VIDE not in str(tour.blocs) for tour in issue.tours)


def test_lhistorique_reste_appaire_meme_quand_un_message_est_vide(contexte, outils):
    """Le piège technique nº1, sur ce chemin-là aussi.

    Un message vide ne porte aucun `tool_use`, donc il n'y a rien à appairer — mais les
    appels des itérations **précédentes** doivent toujours avoir leur `tool_result`, sans
    quoi c'est le tour client **suivant** que l'API refuserait.
    """
    client = FauxClient(
        [
            message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(bloc_inconnu()),
        ]
    )

    _, issue = jouer(client, contexte, outils)

    verifier_appairage(issue.tours)
    assert issue.iterations == 2


def test_letat_acquis_avant_le_message_vide_est_conserve(contexte, outils):
    """Un tour replié n'est pas un tour perdu : ce que les outils ont écrit est persisté.

    Sans cette propriété, un `thinking` seul au mauvais moment effacerait les critères que
    le client venait de donner — le repli deviendrait une amnésie.
    """
    client = FauxClient(
        [
            message(appel_outil(NOM_ENREGISTRER, ECRAN_144, id="tu_1")),
            message(bloc_inconnu()),
        ]
    )

    _, issue = jouer(client, contexte, outils)

    assert issue.etat.categorie_courante == "monitor"
    assert [critere.champ for critere in issue.etat.criteres_de("monitor")] == ["refresh_rate"]
