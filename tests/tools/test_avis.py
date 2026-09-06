"""Le sixième outil : le cache, la borne d'appels, et le miss bruyant.

Purs : ni base, ni conteneur, ni clé, ni réseau. Le dépôt est en mémoire et **il n'existe
aucun fournisseur** — c'est l'état nominal du projet, pas un montage de test.
"""

from datetime import timedelta

import pytest

from avis_de_test import QUAND, DepotAvisEnMemoire, avis_fabrique
from raiyon.avis.cache import Avis, EtatCache
from raiyon.tools.erreurs import CodeRefus, OutilRefuse
from raiyon.tools.etat import EtatSession, RecherchesDavis
from raiyon.tools.outils import ArgumentsAvis, ResultatAvis, chercher_des_avis_web, en_tool_result
from raiyon.tools.repartiteur import ContexteOutils, executer
from raiyon.tools.schema_outils import NOM_AVIS


def depot_charge(*avis: Avis) -> DepotAvisEnMemoire:
    depot = DepotAvisEnMemoire()
    depot.charger(avis)
    return depot


def appeler(
    depot: DepotAvisEnMemoire,
    requete: str = "avis ecran",
    *,
    etat: EtatSession | None = None,
    fournisseur: object = None,
    tour_client: int = 1,
) -> ResultatAvis:
    return chercher_des_avis_web(
        etat or EtatSession(),
        ArgumentsAvis(requete=requete),
        depot=depot,
        fournisseur=fournisseur,  # type: ignore[arg-type]  — `None` est le cas nominal
        tour_client=tour_client,
        maintenant=QUAND,
    )


class TestLeChemainNominal:
    """Le cache est chargé, l'outil sert."""

    def test_un_hit_rend_les_avis(self):
        resultat = appeler(depot_charge(avis_fabrique("a"), avis_fabrique("b")))

        assert len(resultat.avis) == 2
        assert resultat.depuis_le_cache

    def test_un_hit_nécrit_rien(self):
        """⚠️ **Ce qui rend une campagne hors ligne idempotente.**

        Un cache qui se réécrirait à chaque lecture ferait dériver `recupere_le`, donc la
        frontière de péremption — au milieu d'une comparaison, à terme.
        """
        depot = depot_charge(avis_fabrique("a"))

        appeler(depot)

        assert depot.ecritures == []

    def test_la_cle_rendue_est_la_cle_normalisee(self):
        """C'est elle que le journal trace, et elle qu'on écrit dans le seed."""
        resultat = appeler(depot_charge(avis_fabrique("a", requete="avis ecran")), "ÉCRAN Avis !")

        assert resultat.requete_normalisee == "avis ecran"

    def test_deux_formulations_voisines_touchent_le_meme_cache(self):
        """La normalisation vue depuis l'outil, pas depuis sa fonction."""
        depot = depot_charge(avis_fabrique("a", requete="avis ecran"))

        assert appeler(depot, "avis écran").avis
        assert appeler(depot, "écran avis", tour_client=2).avis


class TestLeMissBruyant:
    """🔴 Hors ligne, un miss n'est pas un résultat vide."""

    def test_un_miss_sans_fournisseur_est_un_refus(self):
        """⚠️ **La propriété qui rend « les mesures ne sortent jamais » sûre.**

        Un résultat vide se confondrait avec « cherché, rien trouvé » : le scénario
        continuerait et la campagne mesurerait autre chose que ce qu'elle annonce, sans
        erreur et sans message.
        """
        with pytest.raises(OutilRefuse) as refus:
            appeler(depot_charge(), "avis introuvable")

        assert refus.value.code is CodeRefus.AVIS_HORS_LIGNE

    def test_le_refus_nomme_la_cle_normalisee_a_ecrire(self):
        """Le message est autant un diagnostic qu'une consigne au modèle : il dit
        **exactement** ce qu'il faut mettre dans `data/seed/avis.jsonl`."""
        with pytest.raises(OutilRefuse) as refus:
            appeler(depot_charge(), "Avis ASRock PG27FRS1A ?")

        assert "asrock avis pg27frs1a" in refus.value.message

    def test_une_entree_perimee_est_aussi_un_miss_bruyant(self):
        """Un `PERIME` hors ligne se traite comme un `ABSENT` : rien à servir.

        Il ne peut pas arriver sur une fixture — elles ne périment jamais — donc s'il
        arrive, c'est qu'une ligne `brave` traîne dans une base de mesure. Le refus est le
        bon comportement : c'est exactement ce qu'on ne veut pas servir.
        """
        vieux = Avis(
            requete_normalisee="avis ecran",
            url="https://a.invalid/1",
            titre="titre",
            extrait="extrait",
            source="brave",
            recupere_le=QUAND - timedelta(days=3),
        )

        with pytest.raises(OutilRefuse) as refus:
            appeler(depot_charge(vieux))

        assert refus.value.code is CodeRefus.AVIS_HORS_LIGNE

    def test_une_requete_sans_mot_cherchable_est_refusee_a_part(self):
        """Code distinct : le geste attendu du modèle n'est pas le même.

        `AVIS_HORS_LIGNE` dit « la fixture manque » — rien à corriger côté modèle.
        `REQUETE_VIDE` dit « ta requête n'en est pas une ».
        """
        with pytest.raises(OutilRefuse) as refus:
            appeler(depot_charge(), "??? !!!")

        assert refus.value.code is CodeRefus.REQUETE_VIDE


class TestLaBorneParMessage:
    """Une recherche d'avis par message du client."""

    def test_le_second_appel_du_meme_tour_est_refuse(self):
        depot = depot_charge(avis_fabrique("a"))
        premier = appeler(depot)

        with pytest.raises(OutilRefuse) as refus:
            appeler(depot, etat=premier.etat, tour_client=1)

        assert refus.value.code is CodeRefus.TROP_DAVIS_DANS_UN_TOUR

    def test_le_tour_suivant_rouvre_la_borne(self):
        """⚠️ **La garde porte son tour, elle ne se remet pas à zéro.**

        Il n'existe pas de `nouveau_tour()` dans ce projet : un état d'un tour précédent
        est simplement ignoré, comme pour `recherche_du_tour`.
        """
        depot = depot_charge(avis_fabrique("a"))
        premier = appeler(depot)

        second = appeler(depot, etat=premier.etat, tour_client=2)

        assert second.avis

    def test_le_compteur_monte_meme_quand_lappel_echoue_en_aval(self):
        """🔴 **Sinon la borne serait gratuite** : un tour enchaînerait les refus.

        Le compteur compte ce que le modèle a **demandé**, pas ce qui a réussi.
        """
        depot = depot_charge()

        with pytest.raises(OutilRefuse):
            appeler(depot, "introuvable")

        # L'état n'est pas rendu sur un refus — c'est le contrat du répartiteur —, donc on
        # vérifie la propriété par le chemin réel, en repartant d'un état déjà consommé.
        etat = EtatSession(avis_du_tour=RecherchesDavis(tour_client=1, compte=1))
        with pytest.raises(OutilRefuse) as refus:
            appeler(depot_charge(avis_fabrique("a")), etat=etat, tour_client=1)
        assert refus.value.code is CodeRefus.TROP_DAVIS_DANS_UN_TOUR

    def test_le_compteur_est_un_nombre_et_pas_un_booleen(self):
        """Le journal doit pouvoir dire combien de fois le modèle a **essayé**."""
        depot = depot_charge(avis_fabrique("a"))

        resultat = appeler(depot)

        assert resultat.etat.avis_du_tour == RecherchesDavis(tour_client=1, compte=1)


class TestParLeRepartiteur:
    """Le câblage réel : c'est par là que les deux orchestrations passent."""

    def test_loutil_est_joignable_par_son_nom(self):
        contexte = ContexteOutils(
            depot=None,  # type: ignore[arg-type]  — la recherche d'avis n'y touche pas
            tour_client=1,
            depot_avis=depot_charge(avis_fabrique("a")),
            maintenant=QUAND,
        )

        etat, resultat = executer(NOM_AVIS, {"requete": "avis ecran"}, EtatSession(), contexte)

        assert isinstance(resultat, ResultatAvis)
        assert etat.avis_du_tour is not None

    def test_sans_depot_davis_loutil_refuse_au_lieu_de_lever(self):
        """Une session construite avant l'étape 27 ne casse pas parce qu'un outil existe."""
        contexte = ContexteOutils(depot=None, tour_client=1)  # type: ignore[arg-type]

        _, resultat = executer(NOM_AVIS, {"requete": "avis ecran"}, EtatSession(), contexte)

        assert isinstance(resultat, OutilRefuse)
        assert resultat.code is CodeRefus.AVIS_HORS_LIGNE

    def test_un_argument_invente_est_refuse(self):
        """`extra="forbid"` : le modèle ne glisse pas un `produit_id` par la bande."""
        contexte = ContexteOutils(
            depot=None,  # type: ignore[arg-type]
            tour_client=1,
            depot_avis=depot_charge(avis_fabrique("a")),
            maintenant=QUAND,
        )

        _, resultat = executer(
            NOM_AVIS,
            {"requete": "avis ecran", "produit_id": "monitor-0123456789"},
            EtatSession(),
            contexte,
        )

        assert isinstance(resultat, OutilRefuse)


class TestLaChargeUtile:
    """Ce que le `tool_result` porte, et ce qu'il ne porte pas."""

    def test_la_charge_porte_lavertissement_et_les_avis_encadres(self):
        resultat = appeler(depot_charge(avis_fabrique("a")))

        charge = en_tool_result(resultat)

        assert "texte-de-tiers" in str(charge["avertissement"])
        assert charge["nombre"] == 1

    def test_la_charge_ne_declare_pas_fournir_des_faits(self):
        """L'exclusion du §3.18, constatée sur la sortie de l'outil.

        Sa conséquence est testée à part, dans `tests/validateur/test_exclusion_du_web.py`.
        """
        charge = en_tool_result(appeler(depot_charge(avis_fabrique("a"))))

        assert "faits_du_catalogue" not in charge

    def test_la_charge_ne_porte_ni_produit_ni_prix_ni_comptage_de_catalogue(self):
        """**Sur le type**, comme `ResultatSondage` : une exécution ne prouve que son jeu."""
        interdits = {"produits", "au_dessus_du_budget", "prix_usd", "candidats", "budget_usd"}

        charge = en_tool_result(appeler(depot_charge(avis_fabrique("a"))))

        assert interdits.isdisjoint(charge)

    def test_zero_resultat_est_un_succes_et_pas_un_refus(self):
        """Un cache qui porte la clé avec un groupe vide est un fait, pas un incident.

        ⚠️ Ce cas ne se produit pas encore en base — voir la dette datée de
        `tests/integration/test_avis_cache.py` — mais l'outil, lui, sait déjà le porter.
        """
        depot = DepotAvisEnMemoire()
        depot.groupes["avis ecran"] = ()

        charge = en_tool_result(appeler(depot))

        assert charge["ok"] is True
        assert charge["nombre"] == 0

    def test_letat_du_cache_est_rendu_pour_le_journal(self):
        resultat = appeler(depot_charge(avis_fabrique("a")))

        assert resultat.depuis_le_cache is True
        assert resultat.latence_ms == 0


def test_un_hit_ne_consulte_jamais_le_fournisseur():
    """🔴 **La garantie « une campagne ne sort pas sur le réseau », côté exécution.**

    Les tests d'isolation de `tests/avis/test_isolation_reseau.py` prouvent qu'aucun
    module n'**importe** un client HTTP. Celui-ci prouve autre chose, et c'est la moitié
    qui manquait : sur un hit, le fournisseur n'est pas **appelé**. Un fournisseur qui
    lève sert de sonnette.
    """

    class FournisseurQuiSonne:
        def chercher(self, requete: str, *, limite: int) -> tuple[Avis, ...]:
            raise AssertionError("le fournisseur a été appelé alors que le cache avait la clé")

    resultat = appeler(depot_charge(avis_fabrique("a")), fournisseur=FournisseurQuiSonne())

    assert resultat.depuis_le_cache


def test_un_miss_avec_fournisseur_recupere_et_met_en_cache():
    """Le chemin en ligne, exercé **sans réseau** grâce au `Protocol`.

    C'est ce que le `Protocol` achète : l'implémentation Brave n'existe pas encore, et
    tout ce qui l'entoure est déjà testé.
    """

    class FournisseurDeTest:
        def __init__(self) -> None:
            self.appels: list[str] = []

        def chercher(self, requete: str, *, limite: int) -> tuple[Avis, ...]:
            self.appels.append(requete)
            # Il rend une clé **différente** : c'est le cas réel, il reçoit la requête
            # libre et ne connaît pas la normalisation.
            return (avis_fabrique("neuf", requete="autre chose"),)

    fournisseur = FournisseurDeTest()
    depot = DepotAvisEnMemoire()

    resultat = appeler(depot, "avis ecran", fournisseur=fournisseur)

    assert fournisseur.appels == ["avis ecran"]
    assert depot.ecritures == ["avis ecran"]
    assert not resultat.depuis_le_cache
    # ⚠️ Réétiqueté sous la clé du groupe : le fournisseur a reçu la requête **libre** et
    # ne connaît pas la normalisation. Sans ce réétiquetage, `ecrire()` lèverait
    # `CleIncoherente` — c'est le contrat trouvé à l'étape 26.
    assert depot.groupes["avis ecran"][0].requete_normalisee == "avis ecran"


def test_le_cache_est_relu_au_tour_suivant_apres_une_recuperation():
    """Une récupération sert le tour d'après sans repasser par le fournisseur."""

    class FournisseurUnique:
        def __init__(self) -> None:
            self.appels = 0

        def chercher(self, requete: str, *, limite: int) -> tuple[Avis, ...]:
            self.appels += 1
            return (avis_fabrique("neuf"),)

    fournisseur = FournisseurUnique()
    depot = DepotAvisEnMemoire()

    premier = appeler(depot, fournisseur=fournisseur)
    second = appeler(depot, etat=premier.etat, fournisseur=fournisseur, tour_client=2)

    assert fournisseur.appels == 1
    assert second.depuis_le_cache


def test_letat_du_cache_distingue_absent_et_perime():
    """La distinction que le journal comptera — voir `raiyon.avis.cache`."""
    depot = DepotAvisEnMemoire()

    assert depot.lire("jamais vue", maintenant=QUAND).etat is EtatCache.ABSENT
