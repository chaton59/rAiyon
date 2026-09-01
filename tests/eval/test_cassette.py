"""Le format, les empreintes qui périment, et la divergence qui nomme le tour.

Ces tests sont **purs** : aucune base, aucune clé, aucun conteneur. C'est la propriété
que `make check` demande depuis l'étape 6, et le harnais d'éval ne la dégrade pas.
"""

import json

import pytest

from raiyon.eval.cassette import (
    FORMAT,
    Cassette,
    CassetteEpuisee,
    CassetteInvalide,
    CassettePerimee,
    DivergenceDeRequete,
    EnTete,
    Prise,
    ValeurNonSerialisable,
    apercu_de_requete,
    depuis_json,
    empreinte_de_requete,
    empreinte_des_outils,
    en_json,
)
from raiyon.eval.client import ClientCassette, ClientEnregistreur, verifier

SYSTEME = "Tu es un vendeur conseil. (prompt de test, court exprès)"
OUTILS = [{"name": "search_products", "description": "cherche", "input_schema": {}}]


def entete(**remplacements) -> EnTete:
    champs = {
        "scenario": "budget_serre",
        "prise": 1,
        "modele": "claude-sonnet-5",
        "prompt_version": "systeme.v1",
        "prompt_empreinte": "aaaaaaaaaaaa",
        "outils_empreinte": "bbbbbbbbbbbb",
        "enregistree_le": "2026-09-01",
    }
    champs.update(remplacements)
    return EnTete(**champs)


def messages(*textes):
    return [{"role": "user", "content": [{"type": "text", "text": texte}]} for texte in textes]


def prise_pour(*textes, blocs=None, rang=1):
    """Une prise dont l'empreinte correspond réellement à `messages(*textes)`."""
    conversation = messages(*textes)
    return Prise(
        requete=empreinte_de_requete(systeme=SYSTEME, outils=OUTILS, messages=conversation),
        apercu=apercu_de_requete(conversation),
        blocs=blocs if blocs is not None else [{"type": "text", "text": f"réponse {rang}"}],
        fin="end_turn",
    )


# --------------------------------------------------------------------------- #
# 1. L'aller-retour
# --------------------------------------------------------------------------- #


def test_une_cassette_ecrite_puis_relue_est_identique():
    """La propriété centrale du format : rien ne se perd et rien ne se convertit."""
    cassette = Cassette(
        entete=entete(),
        prises=(
            prise_pour("bonjour", rang=1),
            Prise(
                requete="cafecafecafe",
                apercu=(" 1 user text «bonjour»", " 2 assistant tool_use search_products {}"),
                blocs=[
                    {"type": "text", "text": "Voici trois écrans — dont un à 142,99 $."},
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "search_products",
                        "input": {"limite": 3, "actif": True, "seuil": None},
                    },
                ],
                fin="tool_use",
            ),
        ),
    )

    assert depuis_json(en_json(cassette)) == cassette


def test_le_fichier_est_du_json_indente_termine_par_un_saut_de_ligne():
    """Il est committé : un fichier sans saut de ligne final produit un diff sale."""
    texte = en_json(Cassette(entete=entete(), prises=(prise_pour("bonjour"),)))
    assert texte.endswith("\n")
    assert json.loads(texte)["format"] == FORMAT


def test_une_valeur_non_serialisable_est_refusee_et_nommee():
    """Écrire un `Decimal` en chaîne le relirait en chaîne — **silencieusement de travers**.

    Une cassette n'écrit que ce qu'elle relirait à l'identique. Le refus nomme le type et
    la valeur, plutôt que de convertir dans le seul fichier dont la fidélité fait la valeur.
    """
    from decimal import Decimal

    cassette = Cassette(
        entete=entete(),
        prises=(
            Prise(
                requete="a",
                apercu=(),
                blocs=[{"type": "text", "prix": Decimal("142.99")}],
                fin="end_turn",
            ),
        ),
    )
    with pytest.raises(ValeurNonSerialisable) as erreur:
        en_json(cassette)
    assert "Decimal" in str(erreur.value)
    assert "142.99" in str(erreur.value)


@pytest.mark.parametrize(
    ("charge", "attendu"),
    [
        ('{"format": 99, "entete": {}, "prises": []}', "format 99"),
        ('{"format": 1, "prises": []}', "`entete` absent"),
        ('{"format": 1, "entete": {"scenario": "x"}, "prises": []}', "champs absents"),
        ('{"format": 1, "entete": null, "prises": null}', "`entete` absent"),
        ("pas du json", "JSON illisible"),
    ],
)
def test_une_cassette_mal_formee_est_refusee_en_disant_quoi(charge, attendu):
    with pytest.raises(CassetteInvalide) as erreur:
        depuis_json(charge)
    assert attendu in str(erreur.value)


# --------------------------------------------------------------------------- #
# 2 et 3. Les empreintes qui périment — arbitrage C
# --------------------------------------------------------------------------- #


def test_une_empreinte_de_prompt_qui_ne_correspond_plus_fait_echouer_le_rejeu():
    """Le cas que le §5 nommait « hash du prompt ». Le message dit quoi taper."""
    cassette = Cassette(entete=entete(scenario="besoin_flou"), prises=())
    with pytest.raises(CassettePerimee) as erreur:
        verifier(cassette, prompt_empreinte="zzzzzzzzzzzz", outils_empreinte="bbbbbbbbbbbb")

    message = str(erreur.value)
    assert "besoin_flou" in message
    assert "prompt système systeme.v1" in message
    assert "make eval-enregistrer SCENARIO=besoin_flou" in message


def test_une_empreinte_de_schema_doutils_modifiee_fait_echouer_aussi():
    """**Le cas que la formulation « hash du prompt » laissait échapper.**

    Le schéma d'outils fait partie du préfixe mis en cache (§3.13) et détermine ce que le
    modèle peut faire : un outil dont la description change rend la cassette aussi périmée
    qu'un prompt modifié.
    """
    cassette = Cassette(entete=entete(scenario="comparaison"), prises=())
    with pytest.raises(CassettePerimee) as erreur:
        verifier(cassette, prompt_empreinte="aaaaaaaaaaaa", outils_empreinte="zzzzzzzzzzzz")

    message = str(erreur.value)
    assert "schéma d'outils" in message
    assert "make eval-enregistrer SCENARIO=comparaison" in message


def test_les_deux_empreintes_correspondantes_passent_sans_rien_dire():
    verifier(
        Cassette(entete=entete(), prises=()),
        prompt_empreinte="aaaaaaaaaaaa",
        outils_empreinte="bbbbbbbbbbbb",
    )


def test_lempreinte_des_outils_change_quand_une_description_change():
    """Contre-épreuve : sans elle, le test du dessus passerait sur une empreinte constante."""
    autre = [{**OUTILS[0], "description": "cherche des produits"}]
    assert empreinte_des_outils(OUTILS) != empreinte_des_outils(autre)


def test_lempreinte_de_requete_ignore_lordre_des_cles():
    """`sort_keys` : ni le SDK ni `json` ne garantissent l'ordre d'un dictionnaire."""
    gauche = [{"role": "user", "content": "a"}]
    droite = [{"content": "a", "role": "user"}]
    assert empreinte_de_requete(
        systeme=SYSTEME, outils=OUTILS, messages=gauche
    ) == empreinte_de_requete(systeme=SYSTEME, outils=OUTILS, messages=droite)


# --------------------------------------------------------------------------- #
# 4. La divergence — elle nomme le tour, et elle ne rend pas la mauvaise réponse
# --------------------------------------------------------------------------- #


def test_une_divergence_au_tour_deux_echoue_en_nommant_deux():
    """Une cassette de trois prises, et un `tool_result` modifié au deuxième tour.

    C'est le mode d'échec que l'arbitrage B ferme : sans le contrôle d'empreinte, la
    boucle recevrait ici la réponse du tour 3, la conversation partirait ailleurs, et les
    métriques décriraient un dialogue qui n'a jamais eu lieu. **Des chiffres au lieu d'une
    erreur.**
    """
    cassette = Cassette(
        entete=entete(),
        prises=(
            prise_pour("bonjour", rang=1),
            prise_pour("bonjour", "resultat: 3 produits", rang=2),
            prise_pour("bonjour", "resultat: 3 produits", "et alors ?", rang=3),
        ),
    )
    client = ClientCassette(cassette, source="budget_serre.1.json")

    # Le premier tour passe : la requête est celle qui a été enregistrée.
    premiere = client.repondre(systeme=SYSTEME, outils=OUTILS, messages=messages("bonjour"))
    assert premiere.blocs[0]["text"] == "réponse 1"

    # Le second diverge : le moteur rend désormais 2 produits, pas 3.
    with pytest.raises(DivergenceDeRequete) as erreur:
        client.repondre(
            systeme=SYSTEME,
            outils=OUTILS,
            messages=messages("bonjour", "resultat: 2 produits"),
        )

    message = str(erreur.value)
    assert "budget_serre.1.json" in message
    assert "divergé au tour 2" in message
    assert "resultat: 3 produits" in message  # l'attendu, dans le diff
    assert "resultat: 2 produits" in message  # le reçu
    # ⚠️ La propriété qui compte : l'index **n'a pas avancé**. Rendre la prise 2 puis la 3
    # à une conversation qui a bifurqué est exactement ce qu'on refuse.
    assert client.index == 1


def test_une_cassette_epuisee_le_dit_au_lieu_de_repeter_la_derniere():
    """`FauxClient` répète sa dernière réponse ; une cassette **ne le fait pas**.

    Répéter est le bon comportement pour tester `max_iterations` avec un script écrit à la
    main. C'est le mauvais ici : une conversation plus longue que celle enregistrée veut
    dire que le moteur, la couche outils ou le validateur ont changé — donc que la cassette
    est à régénérer, pas à étirer.
    """
    cassette = Cassette(entete=entete(), prises=(prise_pour("bonjour"),))
    client = ClientCassette(cassette, source="budget_serre.1.json")
    client.repondre(systeme=SYSTEME, outils=OUTILS, messages=messages("bonjour"))

    with pytest.raises(CassetteEpuisee) as erreur:
        client.repondre(systeme=SYSTEME, outils=OUTILS, messages=messages("bonjour"))
    assert "1 prise(s)" in str(erreur.value)
    assert "make eval-enregistrer SCENARIO=budget_serre" in str(erreur.value)


# --------------------------------------------------------------------------- #
# L'enregistreur — il note la requête **avant** l'appel
# --------------------------------------------------------------------------- #


class _ClientQuiAllongeLhistorique:
    """Imite ce que fait la boucle : elle continue d'empiler dans `messages` après coup."""

    def repondre(self, *, systeme, outils, messages):
        from raiyon.agent.client import ReponseLLM

        messages.append({"role": "assistant", "content": [{"type": "text", "text": "ok"}]})
        return ReponseLLM(blocs=[{"type": "text", "text": "ok"}], fin="end_turn")


def test_lenregistreur_note_la_requete_davant_lappel_pas_celle_dapres():
    """Sinon la cassette porterait la requête du tour **suivant**, et ne se rejouerait jamais."""
    conversation = messages("bonjour")
    attendue = empreinte_de_requete(systeme=SYSTEME, outils=OUTILS, messages=conversation)

    enregistreur = ClientEnregistreur(_ClientQuiAllongeLhistorique())
    enregistreur.repondre(systeme=SYSTEME, outils=OUTILS, messages=conversation)

    assert len(conversation) == 2, "le faux client doit bien avoir allongé l'historique"
    assert enregistreur.prises[0].requete == attendue


def test_une_cassette_enregistree_se_rejoue():
    """L'aller-retour complet : enregistrer, écrire, relire, rejouer."""
    conversation = messages("bonjour")
    enregistreur = ClientEnregistreur(_ClientQuiAllongeLhistorique())
    enregistreur.repondre(systeme=SYSTEME, outils=OUTILS, messages=list(conversation))

    relue = depuis_json(en_json(enregistreur.en_cassette(entete())))
    rejoueur = ClientCassette(relue, source="t.json")
    reponse = rejoueur.repondre(systeme=SYSTEME, outils=OUTILS, messages=list(conversation))

    assert reponse.blocs == [{"type": "text", "text": "ok"}]
    assert rejoueur.epuisee
