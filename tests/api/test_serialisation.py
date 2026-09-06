"""Le contrat de fil, champ par champ. **Purs : ni base, ni conteneur, ni clé API.**

Ces tests sont écrits **avant** les routes, et c'est délibéré : si le contrat est faux,
tout ce qui se branche dessus est à refaire, et l'étape 11 le paie deux fois.

Trois d'entre eux ne portent pas sur une valeur mais sur une **propriété** :

* `test_un_texte_multiligne_tient_sur_une_seule_trame` — le défaut classique du SSE écrit
  à la main, invisible en revue et fatal en production ;
* `test_products_found_ne_porte_pas_la_trace` — l'arbitrage G, en assertion négative ;
* `test_aucun_francais_nest_ecrit_en_dur_dans_le_serialiseur` — l'arbitrage H, vérifié
  sur la source du module plutôt que sur son résultat.
"""

import json
from decimal import Decimal

import pytest

from produits_de_test import fabriquer
from raiyon.agent.evenements import (
    LIBELLES_MOTIF_DE_REPLI,
    CriteresMisAJour,
    MotifDeRepli,
    ProduitsTrouves,
    QuestionPosee,
    QuestionSuggeree,
    Repli,
    Sondage,
    Texte,
    TexteRejete,
)
from raiyon.api.serialisation import (
    CodeErreur,
    NomEvenement,
    criteres_serialises,
    nom_et_donnees,
    trame,
    trame_de,
    trame_de_fin,
    trame_derreur,
)
from raiyon.matching.attributs import Role
from raiyon.matching.criteres import (
    LIBELLES_OPTIMISATION,
    Critere,
    Importance,
    Operateur,
    Optimisation,
)
from raiyon.matching.depot import BornesPrix
from raiyon.matching.moteur import ProduitHorsBudget, ResultatMatching
from raiyon.matching.relachement import LIBELLES_MOTIF, Diagnostic, Motif, Proposition
from raiyon.matching.sondage import ChampDiscriminant, Distribution, ValeurComptee
from raiyon.matching.trace import LigneTrace, Statut, TraceProduit
from raiyon.tools.etat import MouvementRefuse
from raiyon.tools.outils import BesoinDeBudget
from raiyon.validateur.regles import CodeGrief, Grief
from raiyon.validateur.validateur import OrigineRejet

# --------------------------------------------------------------------------- #
# Les décors — un de chaque, construits une fois
# --------------------------------------------------------------------------- #

CRITERE_144 = Critere(
    champ="refresh_rate",
    operateur=Operateur.AU_MOINS,
    valeur=Decimal("144"),
    importance=Importance.BLOQUANT,
)

DISTRIBUTION_DALLE = Distribution(
    champ="panel_type",
    libelle_fr="type de dalle",
    unite=None,
    valeurs=(ValeurComptee("IPS", 19), ValeurComptee("VA", 8)),
    total_distinct=3,
    tronque=True,
    renseignes=27,
    total=32,
)


def _ecran(numero: int = 1, prix: str = "329.99"):
    return fabriquer("monitor", numero, prix=prix, marque="Acer")


def _donnees(evenement) -> dict:
    """Le corps de la trame, décodé — c'est ce que le front reçoit réellement."""
    return json.loads(trame_de(evenement).split("data: ", 1)[1])


# --------------------------------------------------------------------------- #
# 1. Les huit événements du domaine, un par un
# --------------------------------------------------------------------------- #


def test_criteria_updated_porte_le_libelle_de_categorie_et_les_criteres():
    evenement = CriteresMisAJour(
        categorie="monitor",
        criteres=(CRITERE_144,),
        budget_usd=Decimal("400.00"),
        optimisation=Optimisation.MOINS_CHER,
        mouvements_refuses=(
            MouvementRefuse("prix_usd", Operateur.AU_PLUS, "un seul desserrage par message"),
        ),
    )

    nom, donnees = nom_et_donnees(evenement)

    assert nom is NomEvenement.CRITERES
    assert donnees == {
        "categorie": "monitor",
        "libelle_categorie": "écran",
        "criteres": [
            {
                "champ": "refresh_rate",
                "libelle_fr": "fréquence de rafraîchissement",
                "unite": "Hz",
                "operateur": "au_moins",
                "valeur": "144",
                "importance": "bloquant",
            }
        ],
        "budget_usd": "400.00",
        "optimisation": "moins_cher",
        "libelle_optimisation": "le moins cher",
        "mouvements_refuses": [
            {
                "champ": "prix_usd",
                "libelle_fr": "prix",
                "unite": "USD",
                "operateur": "au_plus",
                "motif": "un seul desserrage par message",
            }
        ],
    }


def test_catalog_probe_porte_la_distribution_entiere():
    evenement = Sondage(
        categorie="monitor",
        dans_le_budget=32,
        dans_la_zone_de_tolerance=7,
        fourchette_prix=BornesPrix(Decimal("180.00"), Decimal("395.00")),
        champs=(DISTRIBUTION_DALLE,),
    )

    nom, donnees = nom_et_donnees(evenement)

    assert nom is NomEvenement.SONDAGE
    assert donnees["dans_le_budget"] == 32
    assert donnees["dans_la_zone_de_tolerance"] == 7
    assert donnees["fourchette_prix"] == {"plus_bas": "180.00", "plus_haut": "395.00"}
    # ⚠️ Ce n'est pas la trace : c'est ce qui permet au panneau de dire ce que le
    # catalogue contient, y compris ce qu'il ne montre pas (`tronque`).
    assert donnees["champs"] == [
        {
            "champ": "panel_type",
            "libelle_fr": "type de dalle",
            "unite": None,
            "valeurs": [
                {"valeur": "IPS", "effectif": 19},
                {"valeur": "VA", "effectif": 8},
            ],
            "total_distinct": 3,
            "tronque": True,
            "renseignes": 27,
            "total": 32,
        }
    ]


def test_suggested_question_porte_le_champ_et_son_score():
    evenement = QuestionSuggeree(
        categorie="monitor",
        candidats=32,
        budget=None,
        champ=ChampDiscriminant(
            champ="panel_type",
            libelle_fr="type de dalle",
            unite=None,
            score=Decimal("0.7300"),
            distribution=DISTRIBUTION_DALLE,
        ),
    )

    nom, donnees = nom_et_donnees(evenement)

    assert nom is NomEvenement.QUESTION_SUGGEREE
    assert donnees["candidats"] == 32
    assert donnees["budget"] is None
    assert donnees["champ"]["champ"] == "panel_type"
    assert donnees["champ"]["score"] == "0.7300"
    assert donnees["champ"]["distribution"]["total"] == 32


def test_suggested_question_met_le_budget_devant_quand_il_manque():
    """`budget` n'est renseigné que s'il est inconnu — et c'est presque toujours la
    question de plus fort gain."""
    evenement = QuestionSuggeree(
        categorie="monitor",
        candidats=140,
        budget=BesoinDeBudget(BornesPrix(Decimal("108.00"), Decimal("1299.99"))),
        champ=None,
    )

    _, donnees = nom_et_donnees(evenement)

    assert donnees["budget"] == {"fourchette_prix": {"plus_bas": "108.00", "plus_haut": "1299.99"}}
    # `None` quand plus rien ne discrimine : c'est une réponse, pas un incident.
    assert donnees["champ"] is None


def test_products_found_separe_les_produits_du_hors_budget():
    evenement = ProduitsTrouves(
        ResultatMatching(
            categorie="monitor",
            produits=(_ecran(1, "329.99"),),
            traces=(),
            au_dessus_du_budget=(ProduitHorsBudget(_ecran(2, "437.00"), Decimal("37.00")),),
            candidats_trouves=12,
        )
    )

    nom, donnees = nom_et_donnees(evenement)

    assert nom is NomEvenement.PRODUITS
    assert donnees["candidats_trouves"] == 12
    assert [produit["prix_usd"] for produit in donnees["produits"]] == ["329.99"]
    # §3.10 : les deux ensembles ne se mélangent pas, et l'écart est exact.
    assert donnees["au_dessus_du_budget"][0]["ecart_usd"] == "37.00"
    assert donnees["au_dessus_du_budget"][0]["produit"]["prix_usd"] == "437.00"
    assert donnees["diagnostic"] is None


def test_products_found_porte_le_diagnostic_du_zero_resultat():
    """Critère d'acceptation nº6 : dire pourquoi, et proposer l'assouplissement."""
    evenement = ProduitsTrouves(
        ResultatMatching(
            categorie="monitor",
            produits=(),
            traces=(),
            candidats_trouves=0,
            diagnostic=Diagnostic(
                motif=Motif.CRITERE_TROP_STRICT,
                propositions=(
                    Proposition(
                        champ="refresh_rate",
                        libelle_fr="fréquence de rafraîchissement",
                        unite="Hz",
                        importance=Importance.BLOQUANT,
                        operateur=Operateur.AU_MOINS,
                        valeur_demandee=Decimal("240"),
                        valeur_atteignable=Decimal("165"),
                        produits_rouverts=9,
                        motif=Motif.CRITERE_TROP_STRICT,
                        dernier_recours=False,
                    ),
                ),
            ),
        )
    )

    _, donnees = nom_et_donnees(evenement)

    # ⚠️ Le motif voyage avec sa phrase : `critere_trop_strict` affiché tel quel à un
    # client ne serait pas « le cas zéro résultat rendu lisible » (critère nº6), et le
    # front n'a pas le droit de fabriquer ce français lui-même (arbitrage H).
    assert donnees["diagnostic"] == {
        "motif": "critere_trop_strict",
        "libelle_motif": "un critère est trop strict pour le catalogue",
        "propositions": [
            {
                "champ": "refresh_rate",
                "libelle_fr": "fréquence de rafraîchissement",
                "unite": "Hz",
                "valeur_atteignable": "165",
                "produits_rouverts": 9,
                "motif": "critere_trop_strict",
                "libelle_motif": "un critère est trop strict pour le catalogue",
                "dernier_recours": False,
            }
        ],
    }


def test_question_porte_la_question_et_le_champ_vise():
    nom, donnees = nom_et_donnees(QuestionPosee("Tu joues plutôt à quoi ?", "panel_type"))

    assert nom is NomEvenement.QUESTION
    assert donnees == {"question": "Tu joues plutôt à quoi ?", "champ_vise": "panel_type"}


def test_message_porte_le_texte_entier():
    nom, donnees = nom_et_donnees(Texte("Voici trois écrans."))

    assert nom is NomEvenement.MESSAGE
    assert donnees == {"texte": "Voici trois écrans."}


def test_text_rejected_porte_les_griefs_et_lorigine():
    evenement = TexteRejete(
        texte="Le monitor-0000000000 vous conviendrait-il ?",
        griefs=(Grief(CodeGrief.ID_INCONNU, "monitor-0000000000", "citer un id fourni"),),
        tentative=1,
        origine=OrigineRejet.QUESTION,
    )

    nom, donnees = nom_et_donnees(evenement)

    assert nom is NomEvenement.TEXTE_REJETE
    assert donnees == {
        "origine": "question",
        "tentative": 1,
        # Vrai par défaut : un `TexteRejete` construit sans préciser décrit un refus
        # bloquant, comme depuis l'étape 9.
        "bloquant": True,
        "griefs": [
            {
                "code": "id_inconnu",
                "extrait": "monitor-0000000000",
                "correction": "citer un id fourni",
                # Instrumentation de la tolérance d'arrondi écartée : elle ne décide de
                # rien, elle voyage pour être comptée dans `evenements_tour`.
                "arrondi": False,
            }
        ],
    }


def test_fallback_porte_le_message_et_le_motif_mais_pas_les_compteurs():
    """`iterations` et `outils_appeles` sont des métriques de boucle (arbitrage G)."""
    evenement = Repli("Je m'y perds un peu.", 8, ("search_products",), MotifDeRepli.MAX_ITERATIONS)

    nom, donnees = nom_et_donnees(evenement)

    assert nom is NomEvenement.REPLI
    assert donnees == {
        "message": "Je m'y perds un peu.",
        "motif": "max_iterations",
        "libelle_motif": "l'agent a atteint sa garde d'itérations",
    }


# --------------------------------------------------------------------------- #
# 2. Le piège du SSE : une trame reste une ligne
# --------------------------------------------------------------------------- #


def test_un_texte_multiligne_tient_sur_une_seule_trame():
    """⚠️ **Le défaut classique du SSE écrit à la main.**

    Un saut de ligne non échappé coupe la trame en deux : le client reçoit un `data:`
    tronqué suivi de déchets, et le flux se désynchronise au milieu d'un message. Le test
    est écrit sur les trois formes qui se rencontrent — `\\n`, `\\r\\n`, et un retour seul.
    """
    texte = "Trois écrans :\n- Acer XV272U\r\n- Dell S2721DGF\r- fin"

    rendu = trame_de(Texte(texte))

    lignes = rendu.split("\n")

    assert lignes[0] == "event: message"
    assert lignes[1].startswith("data: ")
    # Deux champs, puis la ligne vide qui termine la trame — et rien après.
    assert lignes[2:] == ["", ""]
    assert json.loads(lignes[1].removeprefix("data: "))["texte"] == texte


def test_le_json_du_fil_nechappe_pas_les_accents():
    """`ensure_ascii=False` : le fil est en UTF-8, `\\u00e9` le rendrait illisible en curl."""
    rendu = trame_de(Texte("écran à 144 Hz"))

    assert "écran à 144 Hz" in rendu


# --------------------------------------------------------------------------- #
# 3. Les conventions de valeur
# --------------------------------------------------------------------------- #


def test_tout_decimal_sort_en_chaine_jamais_en_nombre_json():
    """Un flottant JSON perdrait des décimales sur un prix, et §2 se joue au caractère."""
    evenement = ProduitsTrouves(
        ResultatMatching(
            categorie="monitor",
            produits=(_ecran(1, "108.00"),),
            traces=(),
            candidats_trouves=1,
        )
    )

    donnees = _donnees(evenement)
    produit = donnees["produits"][0]

    assert produit["prix_usd"] == "108.00"
    assert isinstance(produit["prix_usd"], str)
    # Les specs numériques aussi : `screen_size` vaut 27 en `Decimal`.
    tailles = [spec for spec in produit["specs"] if spec["champ"] == "screen_size"]
    assert tailles[0]["valeur"] == "27"


def test_une_fourchette_absente_sort_en_null_et_nest_pas_omise():
    """`null` est une **information** — le sous-catalogue est vide — pas un zéro."""
    evenement = Sondage(
        categorie="monitor",
        dans_le_budget=0,
        dans_la_zone_de_tolerance=0,
        fourchette_prix=None,
        champs=(),
    )

    donnees = _donnees(evenement)

    assert "fourchette_prix" in donnees
    assert donnees["fourchette_prix"] is None


def test_un_booleen_de_spec_reste_un_booleen():
    """⚠️ `True` est un `int` en Python : un test d'`int` posé avant celui de `bool`
    enverrait `1` là où le catalogue dit « avec micro »."""
    casque = fabriquer("headphones", 1, prix="99.00")
    evenement = ProduitsTrouves(
        ResultatMatching(categorie="headphones", produits=(casque,), traces=(), candidats_trouves=1)
    )

    specs = {spec["champ"]: spec["valeur"] for spec in _donnees(evenement)["produits"][0]["specs"]}

    assert specs["microphone"] is True
    assert specs["wireless"] is False


# --------------------------------------------------------------------------- #
# 4. Ce que le fil ne porte pas — arbitrage G, en assertions négatives
# --------------------------------------------------------------------------- #


def test_products_found_ne_porte_pas_la_trace():
    """**Arbitrage G.** Ce qui prouve un invariant sort ; ce qui explique un classement
    reste. La trace est du volume et du débogage de moteur : elle passerait par un
    endpoint dédié, pas par un élargissement de `products_found`."""
    trace = TraceProduit(
        produit_id="monitor-0123456789",
        score=Decimal("0.8100"),
        criteres_evalues=2,
        criteres_indisponibles=0,
        rang=1,
        rang_sans_le_prix=2,
        lignes=(
            LigneTrace(
                champ="refresh_rate",
                libelle_fr="fréquence de rafraîchissement",
                unite="Hz",
                role_applique=Role.FILTRE_DUR,
                statut=Statut.MATCHE,
                valeur_produit=Decimal("165"),
                valeur_demandee=Decimal("144"),
                ecart=Decimal("21"),
                poids=None,
                sous_score=None,
                retrograde=False,
            ),
        ),
    )
    evenement = ProduitsTrouves(
        ResultatMatching(
            categorie="monitor",
            produits=(_ecran(),),
            traces=(trace,),
            candidats_trouves=1,
            ecartes_faute_de_donnee={"response_time": 4},
        )
    )

    rendu = trame_de(evenement)
    donnees = json.loads(rendu.split("data: ", 1)[1])

    assert "traces" not in donnees
    assert "ecartes_faute_de_donnee" not in donnees
    # Et rien de la trace n'entre par la petite porte : le rang non plus.
    assert "rang_sans_le_prix" not in rendu
    assert "0.8100" not in rendu


def test_aucun_evenement_ne_porte_letat_de_session():
    """La règle est posée par `evenements.py`, et elle vaut encore une fois ici : ces
    objets sont sérialisés **vers le client**."""
    evenement = CriteresMisAJour(
        categorie="monitor",
        criteres=(CRITERE_144,),
        budget_usd=None,
        optimisation=Optimisation.AUCUNE,
        mouvements_refuses=(),
    )

    _, donnees = nom_et_donnees(evenement)

    assert "etat" not in donnees
    assert "tour_du_dernier_desserrage" not in trame_de(evenement)


# --------------------------------------------------------------------------- #
# 5. Le français vient du registre — arbitrage H
# --------------------------------------------------------------------------- #


def test_le_libelle_et_lunite_dun_critere_viennent_du_registre():
    """`Critere` ne porte ni libellé ni unité : c'est ce que le client a dit, pas ce que
    le catalogue en sait. Les deux viennent d'`ATTRIBUTS`, comme dans la console."""
    rendu = criteres_serialises("monitor", (CRITERE_144,))

    assert rendu[0]["libelle_fr"] == "fréquence de rafraîchissement"
    assert rendu[0]["unite"] == "Hz"


def test_un_champ_sans_unite_sort_avec_une_unite_nulle_et_non_absente():
    critere = Critere(
        champ="panel_type", operateur=Operateur.EGAL, valeur="IPS", importance=Importance.SOUHAIT
    )

    rendu = criteres_serialises("monitor", (critere,))

    assert rendu[0]["libelle_fr"] == "type de dalle"
    assert "unite" in rendu[0]
    assert rendu[0]["unite"] is None


def test_le_meme_champ_dans_deux_categories_rend_deux_unites():
    """`core_clock` est en GHz chez `cpu` et en MHz chez `video-card` — un index plat les
    confondrait, et c'est pour cela que le registre est indexé par catégorie **puis** par
    champ."""
    critere = Critere(
        champ="core_clock",
        operateur=Operateur.AU_MOINS,
        valeur=Decimal("3"),
        importance=Importance.SOUHAIT,
    )

    assert criteres_serialises("cpu", (critere,))[0]["unite"] == "GHz"
    assert criteres_serialises("video-card", (critere,))[0]["unite"] == "MHz"


def test_les_specs_dun_produit_sont_derivees_du_registre_et_non_du_jsonb():
    """Les champs inconnus du registre sont ignorés **par construction** : le parcours
    part du registre. Et les colonnes communes n'y entrent pas — elles ont leur place au
    premier niveau."""
    evenement = ProduitsTrouves(
        ResultatMatching(categorie="monitor", produits=(_ecran(),), traces=(), candidats_trouves=1)
    )

    produit = _donnees(evenement)["produits"][0]
    champs = [spec["champ"] for spec in produit["specs"]]

    assert "refresh_rate" in champs
    assert {spec["libelle_fr"] for spec in produit["specs"] if spec["champ"] == "refresh_rate"} == {
        "fréquence de rafraîchissement"
    }
    # `categorie` est injectée dans les specs par `ProduitEnBase`, et elle a sa colonne :
    # la porter deux fois autoriserait les deux copies à diverger.
    assert "categorie" not in champs
    assert "prix_usd" not in champs
    assert "nom" not in champs


def test_une_spec_absente_ne_produit_pas_de_ligne():
    """Un champ affiché à vide n'est pas une information sur le produit."""
    ecran = fabriquer("monitor", 1, prix="199.00", panel_type=None, response_time=None)
    evenement = ProduitsTrouves(
        ResultatMatching(categorie="monitor", produits=(ecran,), traces=(), candidats_trouves=1)
    )

    champs = [spec["champ"] for spec in _donnees(evenement)["produits"][0]["specs"]]

    assert "panel_type" not in champs
    assert "response_time" not in champs
    assert "refresh_rate" in champs


@pytest.mark.parametrize(
    ("enumeration", "libelles"),
    [
        (Optimisation, LIBELLES_OPTIMISATION),
        (Motif, LIBELLES_MOTIF),
        (MotifDeRepli, LIBELLES_MOTIF_DE_REPLI),
    ],
    ids=["optimisation", "motif_de_zero_resultat", "motif_de_repli"],
)
def test_chaque_valeur_denumeration_affichee_a_son_libelle(enumeration, libelles):
    """⚠️ **Un membre ajouté sans libellé lèverait un `KeyError` au milieu d'un flux.**

    C'est-à-dire un tour perdu, appel API compris, pour un mot d'affichage — le mode
    d'échec que `_champ()` évite par un repli et que ces trois tables évitent par
    l'exhaustivité. Le repli n'est pas possible ici : le nom technique d'un motif de zéro
    résultat n'a rien à faire sous les yeux d'un client, et le rendre reviendrait à ne pas
    avoir fait l'étape.

    L'exhaustivité de ces trois tables n'est pas tenue par `mypy` — un `dict` peut être
    partiel — donc elle l'est ici.
    """
    assert set(libelles) == set(enumeration)
    assert all(libelle and libelle == libelle.lower() for libelle in libelles.values()), (
        "c'est de la donnée, pas du rendu : la mise en forme appartient au front"
    )


def test_aucun_francais_nest_ecrit_en_dur_dans_le_serialiseur():
    """**Arbitrage H, vérifié sur la source.** Le seul français admis dans le module est
    celui des docstrings et des noms de clés du protocole ; aucun libellé d'attribut ni
    nom de catégorie n'y est recopié.

    Sans ce test, la règle tiendrait par discipline : rien n'empêcherait d'écrire
    `"fréquence de rafraîchissement"` en dur le jour où le registre paraît de trop.

    ⚠️ Les usages en **clé** sont retirés avant la recherche. `"marque"` est à la fois le
    libellé français d'un attribut et le nom d'une clé du protocole : une clé JSON qui
    ressemble à un mot français est un nom de champ, pas un libellé montré au client.
    """
    from pathlib import Path

    import raiyon.api.serialisation as module
    from raiyon.catalogue.schemas import LIBELLES_CATEGORIE
    from raiyon.matching.attributs import ATTRIBUTS

    source = Path(module.__file__).read_text(encoding="utf-8")
    libelles = {
        attribut.libelle_fr for champs in ATTRIBUTS.values() for attribut in champs.values()
    }
    libelles |= set(LIBELLES_CATEGORIE.values())

    ecrits_en_dur = sorted(
        libelle for libelle in libelles if f'"{libelle}"' in source.replace(f'"{libelle}":', "")
    )

    assert ecrits_en_dur == []


# --------------------------------------------------------------------------- #
# 6. L'encadrement, l'erreur, la fin
# --------------------------------------------------------------------------- #


def test_la_trame_a_la_forme_exacte_du_protocole():
    rendu = trame(NomEvenement.MESSAGE, {"texte": "bonjour"})

    assert rendu == 'event: message\ndata: {"texte": "bonjour"}\n\n'


def test_lerreur_porte_un_code_ferme_et_un_message_en_francais():
    """⚠️ Le message est écrit **pour le client** : une trace SQLAlchemy sur une page web
    est une fuite (arbitrage E)."""
    rendu = trame_derreur(CodeErreur.INTERNE, "Une erreur interne a interrompu ce tour.")

    nom, corps = rendu.split("\n")[0], json.loads(rendu.split("data: ", 1)[1])

    assert nom == "event: error"
    assert corps == {"code": "interne", "message": "Une erreur interne a interrompu ce tour."}


def test_la_fin_est_une_trame_a_charge_vide():
    """`done` est terminal et obligatoire : sans lui, le front ne distingue pas « tour
    terminé » de « connexion tombée »."""
    assert trame_de_fin() == "event: done\ndata: {}\n\n"


@pytest.mark.parametrize(
    "code",
    [CodeErreur.TOUR_EN_COURS, CodeErreur.INTERNE],
)
def test_les_codes_derreur_sont_des_chaines_stables(code):
    """Le front les compare littéralement : ce sont des identifiants, pas des libellés."""
    assert code.value in {"tour_en_cours", "interne"}


def test_lexhaustivite_de_lunion_est_tenue_par_mypy():
    """**Ce test ne teste rien, et c'est son objet.**

    La branche finale de `nom_et_donnees()` appelle `typing.assert_never`. Un neuvième
    type ajouté à l'union `Evenement` fait échouer `make typecheck`, pas cette suite —
    un test qui prétendrait le vérifier au runtime devrait énumérer les types à la main,
    c'est-à-dire recopier l'union et la laisser diverger d'elle-même.

    Ce qui se vérifie ici est plus modeste et suffit : les huit événements connus ont
    chacun leur nom de fil, et deux d'entre eux ne le partagent pas.
    """
    noms = {
        nom_et_donnees(evenement)[0]
        for evenement in (
            CriteresMisAJour("monitor", (), None, Optimisation.AUCUNE, ()),
            Sondage("monitor", 0, 0, None, ()),
            QuestionSuggeree("monitor", 0, None, None),
            ProduitsTrouves(ResultatMatching("monitor", (), ())),
            QuestionPosee("?", None),
            Texte("."),
            TexteRejete("", (), 1, OrigineRejet.TEXTE),
            Repli(".", 1, (), MotifDeRepli.VALIDATION),
        )
    }

    assert len(noms) == 8
    assert NomEvenement.ERREUR not in noms
    assert NomEvenement.FIN not in noms


def test_le_texte_refuse_ne_part_jamais_au_client():
    """**Un texte refusé n'a pas atteint le client, et il ne doit pas l'atteindre ici.**

    `TexteRejete` porte le texte refusé depuis l'étape 13 : c'est ce qui permet au rapport
    d'éval de publier *quelle forme* de phrase le validateur a repoussée, au lieu d'un code
    seul. Le fil SSE, lui, n'a rien à en faire — et le lui donner ressusciterait exactement
    le défaut que le correctif de l'étape 11 a fermé : le dernier refus d'un tour ne revient
    pas au client, pas même par une porte dérobée.

    `_texte_rejete` choisit ses champs un par un, donc l'ajout ne fuit pas. Ce test le
    **constate**, parce qu'un jour quelqu'un remplacera cette fonction par un `asdict()`.
    """
    secret = "Celui-ci est à 230 $, une affaire que personne n'a fournie."
    _, donnees = nom_et_donnees(
        TexteRejete(
            texte=secret,
            griefs=(Grief(CodeGrief.MONTANT_NON_FOURNI, "230 $", "reprendre `prix_usd`"),),
            tentative=1,
            origine=OrigineRejet.TEXTE,
        )
    )

    assert set(donnees) == {"origine", "tentative", "bloquant", "griefs"}
    assert secret not in json.dumps(donnees, ensure_ascii=False)


def test_text_rejected_dit_si_le_grief_a_bloque():
    """⚠️ **Le même événement décrit deux situations opposées selon le mode.**

    En `bloquante`, le texte n'a jamais atteint le client. En `avertissement`, il l'a
    atteint et le grief n'est qu'un signalement. Le tableau de bord marque « jamais lu par
    le client » : sans ce champ, il le dirait à tort une fois sur deux.

    ⚠️ Le texte refusé reste **absent du fil dans les deux modes**. Ce n'est pas une
    incohérence : le fil transporte la mécanique du refus, jamais son objet, et un texte
    livré est déjà parti par son propre événement `message`.
    """
    signale = "Celui-ci est à 230 $."
    _, donnees = nom_et_donnees(
        TexteRejete(
            texte=signale,
            griefs=(Grief(CodeGrief.MONTANT_NON_FOURNI, "230 $", "reprendre `prix_usd`"),),
            tentative=0,
            origine=OrigineRejet.TEXTE,
            bloquant=False,
        )
    )

    assert donnees["bloquant"] is False
    assert signale not in json.dumps(donnees, ensure_ascii=False)
