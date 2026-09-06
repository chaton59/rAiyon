"""Le schéma JSON est-il vraiment dérivé du registre — et rien qu'à partir de lui ?

Ces tests sont l'assurance que la description des outils **ne peut pas** mentir sur le
catalogue. Un schéma qui promet un champ que le moteur refuse fait échouer le modèle
tour après tour, sans que rien ne casse côté code : c'est un mode d'échec silencieux, et
c'est celui-ci qu'on ferme ici.
"""

import json

from outils_de_test import TOLERANCE  # noqa: F401  (garde le conftest local prioritaire)
from raiyon.catalogue.schemas import CATEGORIES
from raiyon.matching.attributs import ATTRIBUTS, Role
from raiyon.matching.criteres import CHAMPS_A_CHAMP_DEDIE, Importance, Operateur, Optimisation
from raiyon.tools.outils import (
    ArgumentsAvis,
    ArgumentsCle,
    ArgumentsCritere,
    ArgumentsEnregistrement,
    ArgumentsPrecision,
    ArgumentsSondage,
)
from raiyon.tools.schema_outils import (
    NOM_AVIS,
    NOM_ENREGISTRER,
    NOM_PRECISION,
    NOM_QUESTION,
    NOM_RECHERCHER,
    NOM_SONDER,
    champs_du_schema,
    champs_utilisables,
    glose,
    schema_des_outils,
)

SCHEMA = {outil["name"]: outil for outil in schema_des_outils()}


def champs_attendus() -> set[str]:
    """Les champs utilisables du registre, recalculés **sans passer par le module testé**.

    Le calcul est réécrit ici à partir de `ATTRIBUTS` : si le test appelait
    `champs_utilisables()`, il constaterait que la fonction est égale à elle-même.
    """
    return {
        champ
        for categorie in CATEGORIES
        for champ, attribut in ATTRIBUTS[categorie].items()
        if attribut.role is not Role.AFFICHAGE
        and not attribut.impose
        and champ not in CHAMPS_A_CHAMP_DEDIE
    }


def _enum_des_champs(schema: dict) -> list[str]:
    return schema["input_schema"]["properties"]["criteres"]["items"]["properties"]["champ"]["enum"]


# --------------------------------------------------------------------------- #
# La dérivation depuis le registre
# --------------------------------------------------------------------------- #


def test_lenum_couvre_exactement_les_champs_utilisables_du_registre():
    assert set(champs_du_schema()) == champs_attendus()


def test_aucun_champ_daffichage_nentre_dans_le_schema():
    """`color`, `nom` et `id` sont montrés au client, ils ne filtrent ni ne scorent."""
    assert {"color", "nom", "id"}.isdisjoint(champs_du_schema())


def test_aucun_champ_a_champ_dedie_nentre_dans_le_schema():
    """`prix_usd` a le budget, `categorie` a son argument, `disponible` est imposé."""
    assert CHAMPS_A_CHAMP_DEDIE.isdisjoint(champs_du_schema())


def test_chaque_champ_porte_le_libelle_francais_du_registre():
    """Les descriptions sont dérivées de `libelle_fr` et `unite`, jamais écrites."""
    for categorie in CATEGORIES:
        for champ, attribut in champs_utilisables(categorie).items():
            assert attribut.libelle_fr in glose(champ)
            if attribut.unite:
                assert attribut.unite in glose(champ) or attribut.unite in attribut.libelle_fr


def test_un_champ_homonyme_porte_ses_deux_sens_et_ses_categories():
    """`core_clock` est en GHz chez `cpu` et en MHz chez `video-card` : le taire ferait
    demander 2 400 MHz à un processeur."""
    description = glose("core_clock")
    assert "GHz" in description and "MHz" in description
    assert "cpu" in description and "video-card" in description


def test_lenum_est_triee_donc_stable_dun_demarrage_a_lautre():
    """Le schéma part dans le préfixe mis en cache (§3.13) : un ordre instable
    l'invaliderait sans rien apporter."""
    assert list(champs_du_schema()) == sorted(champs_du_schema())
    assert schema_des_outils() == schema_des_outils()


def test_les_enumerations_du_schema_viennent_des_enumeres_python():
    schema = SCHEMA[NOM_ENREGISTRER]["input_schema"]["properties"]
    assert schema["categorie"]["enum"] == list(CATEGORIES)
    assert schema["optimisation"]["enum"] == [membre.value for membre in Optimisation]
    critere = schema["criteres"]["items"]["properties"]
    assert critere["operateur"]["enum"] == [membre.value for membre in Operateur]
    assert critere["importance"]["enum"] == [membre.value for membre in Importance]


# --------------------------------------------------------------------------- #
# Les six outils, et ce qu'ils exposent
# --------------------------------------------------------------------------- #


def test_les_six_outils_portent_les_noms_du_paragraphe_3_7():
    """⚠️ **Cinq jusqu'à l'étape 27**, six depuis — §3.7 en décrivait quatre.

    Le compte est dans le nom du test exprès : c'est lui qui a échoué quand
    `search_reviews` est entré, et c'est ce qu'on veut d'un test de cadrage — il force à
    dire qu'un outil de plus est une décision, pas un ajout.
    """
    assert set(SCHEMA) == {
        NOM_ENREGISTRER,
        NOM_SONDER,
        NOM_QUESTION,
        NOM_RECHERCHER,
        NOM_PRECISION,
        NOM_AVIS,
    }
    assert NOM_SONDER == "probe_catalog"
    assert NOM_QUESTION == "suggest_next_question"
    assert NOM_RECHERCHER == "search_products"
    assert NOM_PRECISION == "ask_clarification"
    assert NOM_AVIS == "search_reviews"


def test_la_recherche_davis_ne_prend_quune_requete_libre():
    """Aucun `produit_id` : un lien produit serait un fait dont le modèle est seul auteur.

    Aucun `categorie` non plus — la recherche d'avis ne lit pas l'état des critères et
    n'a pas de sous-catalogue. C'est le seul outil du projet dans ce cas.
    """
    proprietes = SCHEMA[NOM_AVIS]["input_schema"]["properties"]

    assert set(proprietes) == {"requete"}
    assert SCHEMA[NOM_AVIS]["input_schema"]["required"] == ["requete"]


def test_les_outils_de_recherche_ne_prennent_aucun_critere():
    """L'arbitrage C, constaté sur le schéma : il n'existe pas d'argument par lequel
    passer un critère, un budget ou une catégorie."""
    for nom in (NOM_SONDER, NOM_QUESTION, NOM_RECHERCHER):
        proprietes = set(SCHEMA[nom]["input_schema"]["properties"])
        assert not proprietes & {"criteres", "budget_usd", "categorie", "retraits"}
    assert SCHEMA[NOM_QUESTION]["input_schema"]["properties"] == {}
    assert SCHEMA[NOM_RECHERCHER]["input_schema"]["properties"] == {}


def test_seul_lenregistrement_prend_une_categorie_et_un_budget():
    proprietes = SCHEMA[NOM_ENREGISTRER]["input_schema"]["properties"]
    assert {"categorie", "budget_usd", "retirer_le_budget"} <= set(proprietes)
    assert SCHEMA[NOM_ENREGISTRER]["input_schema"]["required"] == ["categorie"]


def test_la_valeur_dun_critere_est_typee_chaine():
    """Arbitrage F : une union `bool | number | string` est mal supportée en mode strict,
    et le projet sérialise déjà ses `Decimal` en chaînes pour la même raison."""
    critere = SCHEMA[NOM_ENREGISTRER]["input_schema"]["properties"]["criteres"]["items"]
    assert critere["properties"]["valeur"]["type"] == "string"


def test_le_schema_et_les_modeles_pydantic_declarent_les_memes_proprietes():
    """Les deux faces de l'interface sont dérivées séparément — l'une du registre,
    l'autre des signatures — et ce test est ce qui les empêche de diverger."""
    paires = [
        (NOM_ENREGISTRER, ArgumentsEnregistrement),
        (NOM_SONDER, ArgumentsSondage),
        (NOM_PRECISION, ArgumentsPrecision),
        (NOM_AVIS, ArgumentsAvis),
    ]
    for nom, modele in paires:
        assert set(SCHEMA[nom]["input_schema"]["properties"]) == set(modele.model_fields)

    critere = SCHEMA[NOM_ENREGISTRER]["input_schema"]["properties"]["criteres"]["items"]
    assert set(critere["properties"]) == set(ArgumentsCritere.model_fields)
    retrait = SCHEMA[NOM_ENREGISTRER]["input_schema"]["properties"]["retraits"]["items"]
    assert set(retrait["properties"]) == set(ArgumentsCle.model_fields)


# --------------------------------------------------------------------------- #
# Le mode strict, et ce qu'on a le droit d'en supposer
# --------------------------------------------------------------------------- #


def test_le_drapeau_strict_est_pose_et_se_replie():
    """Le repli existe **avant** l'étape 8 : le jour où l'API refuse une définition, la
    réponse est un argument, pas une séance de débogage."""
    assert all(outil["strict"] is True for outil in schema_des_outils())
    assert all(outil["strict"] is False for outil in schema_des_outils(strict=False))


def test_le_schema_reste_dans_un_sous_ensemble_pauvre_de_json_schema():
    """Le sous-ensemble admis sous `strict` n'est documenté nulle part dans le paquet
    installé, et l'étape 7 n'appelle pas l'API : on n'utilise donc que ce dont on est
    sûr. Ni `anyOf`, ni `oneOf`, ni `$ref`, ni `format`, ni type nullable."""
    interdits = {"anyOf", "oneOf", "allOf", "$ref", "format", "nullable", "patternProperties"}

    def parcourir(noeud: object) -> None:
        if isinstance(noeud, dict):
            assert interdits.isdisjoint(noeud), f"mot-clé hors sous-ensemble : {noeud.keys()}"
            for valeur in noeud.values():
                parcourir(valeur)
        elif isinstance(noeud, list):
            for element in noeud:
                parcourir(element)

    parcourir(list(schema_des_outils()))


def test_tout_objet_du_schema_ferme_ses_proprietes():
    def parcourir(noeud: object) -> None:
        if isinstance(noeud, dict):
            if noeud.get("type") == "object":
                assert noeud["additionalProperties"] is False
                assert "required" in noeud
            for valeur in noeud.values():
                parcourir(valeur)
        elif isinstance(noeud, list):
            for element in noeud:
                parcourir(element)

    parcourir(list(schema_des_outils()))


def test_le_schema_est_serialisable_tel_quel():
    """Il part dans un corps de requête HTTP : un `Decimal` ou un `StrEnum` égaré s'y
    verrait à l'étape 8, dans une trace d'exception peu bavarde."""
    json.dumps(schema_des_outils(), ensure_ascii=False)


def test_les_definitions_tiennent_dans_le_type_du_sdk():
    """Contre-épreuve : les clés produites sont bien celles que `ToolParam` accepte.

    ⚠️ Ce test **importe le SDK**, et c'est la seule chose de la suite des outils qui le
    fasse — mais c'est un test, pas un module de `raiyon.tools`, et il n'appelle rien.
    Sans lui, la conformité du schéma au type attendu resterait une supposition, et le
    projet en a déjà payé trois.
    """
    from anthropic.types import ToolParam

    admises = set(ToolParam.__annotations__)
    for outil in schema_des_outils():
        assert set(outil) <= admises, set(outil) - admises
        assert ToolParam.__required_keys__ <= set(outil)
