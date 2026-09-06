"""Le cache d'avis sur une vraie base : hit, miss, péremption, écriture concurrente.

**Aucun appel modèle, aucun appel réseau.** Ce qui exige Postgres ici, c'est le SQL et —
pour le dernier cas — le fait que deux transactions se disputent réellement une contrainte
d'unicité. Le reste de la logique est pur et vit dans `tests/avis/`, dans `make check`.

⚠️ **Le cas concurrent ne peut pas être simulé.** Une fausse base rendrait
l'`IntegrityError` que le code attend, et prouverait donc que le code gère l'exception
qu'on a décidé qu'il recevrait — pas qu'il reçoit celle que Postgres envoie. C'est
exactement la nuance qui a fait écrire ce fichier plutôt qu'un `unittest.mock`. Il ne se
teste pas non plus en un seul test : voir `TestLecritureConcurrente`, qui dit pourquoi.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from raiyon.avis.cache import (
    SOURCE_FABRIQUE,
    Avis,
    CleIncoherente,
    DepotAvisSql,
    EtatCache,
    vers_ligne,
)
from raiyon.db.models import AvisProduit, Produit

TTL = timedelta(hours=24)
MIDI = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
CLE = "asrock avis pg27frs1a"


def avis_de(
    url: str,
    *,
    source: str = "brave",
    recupere_le: datetime = MIDI,
    cle: str = CLE,
    produit_id: str | None = None,
) -> Avis:
    """Un avis minimal sous `CLE`. Sans lien produit par défaut — la recherche est libre."""
    return Avis(
        requete_normalisee=cle,
        url=url,
        titre=f"titre {url}",
        extrait="Fixture de test.",
        source=source,
        recupere_le=recupere_le,
        produit_id=produit_id,
    )


@pytest.fixture
def depot(session: Session) -> DepotAvisSql:
    """Le dépôt branché sur la session transactionnelle du conftest."""
    return DepotAvisSql(session, ttl=TTL)


def _un_produit(session: Session) -> Produit:
    """Un produit minimal, créé ici plutôt que lu du catalogue.

    ⚠️ La base `raiyon_test` porte le **schéma** et pas le seed — c'est
    `raiyon_test_agregats` qui est chargée. Ces tests-ci n'ont besoin que d'une cible de
    clé étrangère, donc la fabriquer coûte moins qu'en dépendre.
    """
    produit = Produit(
        id="monitor-0123456789",
        nom="Écran de test",
        marque="Test",
        categorie="monitor",
        prix_usd=Decimal("199.99"),
        disponible=True,
        specs={},
    )
    session.add(produit)
    session.flush()
    return produit


class TestLireEtEcrire:
    """Les trois états, sur du vrai SQL."""

    def test_une_cle_jamais_remplie_est_absente(self, depot):
        """`ABSENT`, pas `PERIME` : la distinction est ce que le journal comptera."""
        lecture = depot.lire(CLE, maintenant=MIDI)

        assert lecture.etat is EtatCache.ABSENT
        assert lecture.avis == ()
        assert not lecture.utilisable

    def test_ce_qui_a_ete_ecrit_se_relit(self, depot):
        depot.ecrire(CLE, [avis_de("https://a.invalid/1"), avis_de("https://a.invalid/2")])

        lecture = depot.lire(CLE, maintenant=MIDI)

        assert lecture.etat is EtatCache.TROUVE
        assert [un_avis.url for un_avis in lecture.avis] == [
            "https://a.invalid/1",
            "https://a.invalid/2",
        ]

    def test_une_recherche_sans_resultat_se_met_en_cache(self, depot):
        """⚠️ **« Rien trouvé » est un fait, et il doit tenir.**

        Sans lui, une requête sans résultat serait refaite à chaque tour — et pendant une
        campagne hors ligne, refaite pour rien. Le groupe vide est donc `ABSENT` en base…
        ce qui est précisément la limite : voir le test suivant.
        """
        depot.ecrire(CLE, [])

        assert depot.lire(CLE, maintenant=MIDI).etat is EtatCache.ABSENT

    def test_un_groupe_vide_est_indistinguable_dune_cle_jamais_remplie(self, depot):
        """🔴 **La limite du schéma, constatée plutôt que découverte.**

        `Lecture` sait dire « trouvé, zéro avis » ; la **table**, elle, ne sait pas — une
        recherche qui n'a rien rendu n'écrit aucune ligne, donc rien ne la distingue d'une
        clé jamais remplie. Le cache d'un résultat vide n'existe donc pas encore.

        Ce n'est pas un oubli, c'est une dette datée : la fermer demande une ligne
        sentinelle ou une table de clés, c'est-à-dire un second concept pour un cas dont
        on ne connaît pas encore la fréquence. L'étape 27 tracera les `ABSENT` ; si les
        requêtes stériles s'y voient, ce test est l'endroit où revenir.
        """
        depot.ecrire(CLE, [])
        vide = depot.lire(CLE, maintenant=MIDI)

        jamais = depot.lire("une cle jamais vue", maintenant=MIDI)

        assert vide.etat is jamais.etat is EtatCache.ABSENT

    def test_ecrire_deux_fois_remplace_le_groupe_au_lieu_de_le_fusionner(self, depot, session):
        """⚠️ **Le motif du remplacement en bloc**, et il se voit ici.

        Si la première récupération rend `{a, b}` et la seconde `{a, c}`, fusionner
        laisserait `{a, b, c}` — un groupe qu'aucune recherche n'a jamais rendu. Un cache
        dont le contenu n'a jamais existé côté fournisseur ne sert plus à comparer.
        """
        depot.ecrire(CLE, [avis_de("https://a.invalid/a"), avis_de("https://a.invalid/b")])

        depot.ecrire(CLE, [avis_de("https://a.invalid/a"), avis_de("https://a.invalid/c")])

        urls = [un_avis.url for un_avis in depot.lire(CLE, maintenant=MIDI).avis]
        assert urls == ["https://a.invalid/a", "https://a.invalid/c"]

    def test_lordre_rendu_est_stable_et_ne_suit_pas_la_sequence(self, depot):
        """Trié par URL, jamais par `id` : deux chargements doivent rendre le même ordre.

        Sinon une campagne comparée à une autre verrait des résultats permutés sans que
        rien n'ait bougé — le bruit exact que ce cache existe pour supprimer.
        """
        depot.ecrire(CLE, [avis_de("https://a.invalid/z"), avis_de("https://a.invalid/a")])

        urls = [un_avis.url for un_avis in depot.lire(CLE, maintenant=MIDI).avis]

        assert urls == sorted(urls)

    def test_deux_cles_ne_se_melangent_pas(self, depot):
        depot.ecrire(CLE, [avis_de("https://a.invalid/1")])
        depot.ecrire("autre cle", [avis_de("https://a.invalid/2", cle="autre cle")])

        lecture = depot.lire(CLE, maintenant=MIDI)

        assert [un_avis.url for un_avis in lecture.avis] == ["https://a.invalid/1"]

    def test_ecrire_refuse_des_avis_portant_une_autre_cle(self, depot):
        """🔴 **Le défaut que ce fichier a trouvé en visant autre chose.**

        Le test du dessus a d'abord échoué parce que son aide construisait des avis sous
        `CLE` tout en les rangeant sous « autre cle ». Le code les acceptait : le `DELETE`
        visait le groupe demandé, l'`INSERT` écrivait sous l'autre, et **deux groupes
        étaient corrompus d'un seul appel** — sans qu'aucune contrainte SQL bronche, chaque
        ligne prise isolément étant valide.

        C'est la fusion que le remplacement en bloc existe pour empêcher, entrée par la
        porte de l'appelant. La faute de test était donc une faute de code, et le refus est
        maintenant explicite.
        """
        with pytest.raises(CleIncoherente):
            depot.ecrire("une cle", [avis_de("https://a.invalid/1", cle="une autre")])


class TestLaCascade:
    """La conséquence de `ON DELETE CASCADE`, vérifiée au lieu d'être annoncée."""

    def test_supprimer_un_produit_emporte_ses_avis(self, depot, session):
        """⚠️ **C'est ce qui impose l'ordre de `make seed`**, et c'était une affirmation.

        `charger_en_base()` vide `produits` avant de le remplir : la cascade emporte donc
        les avis liés à chaque chargement de catalogue. `executer_passe_c()` charge les
        avis **après** pour cette raison précise, et une docstring qui l'explique ne vaut
        que si le comportement est constaté.
        """
        produit = _un_produit(session)
        depot.ecrire(CLE, [avis_de("https://a.invalid/1", produit_id=produit.id)])
        assert depot.lire(CLE, maintenant=MIDI).utilisable

        session.execute(delete(Produit).where(Produit.id == produit.id))
        session.flush()

        assert depot.lire(CLE, maintenant=MIDI).etat is EtatCache.ABSENT

    def test_un_avis_sans_produit_survit_au_rechargement_du_catalogue(self, depot, session):
        """La contrepartie : la recherche est libre, donc tous les avis ne sont pas liés.

        Un avis générique — « IPS ou VA pour jouer » — ne cite aucun produit et n'a donc
        aucune raison de disparaître avec le catalogue. C'est ce que `produit_id` nullable
        achète, au-delà de la commodité.
        """
        depot.ecrire(CLE, [avis_de("https://a.invalid/1")])

        session.execute(delete(Produit))
        session.flush()

        assert depot.lire(CLE, maintenant=MIDI).utilisable


class TestLaPeremption:
    """Le TTL, lu à la lecture — aucune tâche de fond ne purge."""

    def test_une_ligne_fraiche_est_servie(self, depot):
        depot.ecrire(CLE, [avis_de("https://a.invalid/1")])

        assert depot.lire(CLE, maintenant=MIDI + timedelta(hours=23)).utilisable

    def test_une_ligne_perimee_nest_pas_servie(self, depot):
        depot.ecrire(CLE, [avis_de("https://a.invalid/1")])

        lecture = depot.lire(CLE, maintenant=MIDI + timedelta(hours=25))

        assert lecture.etat is EtatCache.PERIME
        assert lecture.avis == ()

    def test_une_ligne_perimee_reste_en_base(self, depot, session):
        """La lecture refuse, elle ne supprime pas. **Pas d'ordonnanceur dans ce projet.**"""
        depot.ecrire(CLE, [avis_de("https://a.invalid/1")])

        depot.lire(CLE, maintenant=MIDI + timedelta(days=30))

        assert session.scalar(select(func.count()).select_from(AvisProduit)) == 1

    def test_un_groupe_perime_en_bloc(self, depot):
        """⚠️ Une seule ligne périmée suffit à refuser le groupe entier.

        Servir les fraîches d'un groupe partiellement expiré rendrait un sous-ensemble
        qu'aucune recherche n'a jamais rendu — la faute que le remplacement en bloc évite
        par ailleurs. Le cas ne se produit qu'après une écriture concurrente perdue, et il
        se tranche du côté sûr.
        """
        vieille = avis_de("https://a.invalid/1", recupere_le=MIDI - timedelta(days=3))
        depot.ecrire(CLE, [vieille, avis_de("https://a.invalid/2")])

        assert depot.lire(CLE, maintenant=MIDI).etat is EtatCache.PERIME

    def test_une_fixture_ne_perime_jamais_meme_apres_un_an(self, depot):
        """🔴 **La propriété qui rend `make eval` hors ligne tenable au-delà du premier jour.**"""
        depot.ecrire(
            CLE,
            [avis_de("https://a.invalid/1", source=SOURCE_FABRIQUE, recupere_le=MIDI)],
        )

        assert depot.lire(CLE, maintenant=MIDI + timedelta(days=365)).utilisable


class TestLecritureConcurrente:
    """Deux transactions, une clé.

    ⚠️ **La première version de ces tests ne testait rien, et l'échec l'a dit.** Elle
    validait la première transaction *avant* que la seconde n'écrive. Sous `READ
    COMMITTED`, le `DELETE` de la seconde voit alors la ligne validée et l'efface : il n'y
    a **aucune course**, seulement un remplacement ordinaire — c'est d'ailleurs le
    comportement voulu, et il a son test ci-dessous.

    La vraie course demande que la seconde transaction **ait déjà pris son instantané**
    quand la première valide. `REPEATABLE READ` le produit sans thread ni barrière : la
    seconde ne verra jamais la ligne de la première, son `DELETE` n'efface rien, et son
    `INSERT` se heurte à l'index unique — les index ne sont pas soumis à l'instantané.

    *Alternative écartée — deux threads et une barrière.* Elle reproduit la vraie
    séquence, au prix d'un test qui peut se bloquer : l'`INSERT` du second attend que le
    premier valide, et un ordre d'exécution différent suspend la suite au lieu de la faire
    échouer. Un test qui pend est pire qu'un test approximatif.
    """

    def test_sequentiellement_le_second_remplace_simplement_le_premier(self, moteur: Engine):
        """Pas une course : le second voit le groupe validé, l'efface, et écrit le sien."""
        with Session(moteur) as premiere, Session(moteur) as seconde:
            try:
                DepotAvisSql(premiere, ttl=TTL).ecrire(CLE, [_partagee("écrit en premier")])
                premiere.commit()

                DepotAvisSql(seconde, ttl=TTL).ecrire(CLE, [_partagee("écrit en second")])
                seconde.commit()

                with Session(moteur) as lecture:
                    (rendu,) = DepotAvisSql(lecture, ttl=TTL).lire(CLE, maintenant=MIDI).avis
                assert rendu.titre == "écrit en second"
            finally:
                _vider(moteur)

    def test_la_course_est_absorbee_et_naucune_exception_ne_remonte(self, moteur: Engine):
        """🔴 **La moitié que ce montage peut prouver : la collision a bien lieu.**

        La perdante prend son instantané, la gagnante valide, puis la perdante écrit :
        `UNIQUE (requete_normalisee, url)` la rejette — les index ne sont pas soumis à
        l'instantané — et `ecrire()` défait son point de sauvegarde au lieu de laisser
        remonter l'`IntegrityError`. Sans le point de sauvegarde, la transaction entière
        serait avortée et le tour perdrait sa conversation avec son cache.
        """
        with Session(moteur) as gagnante, Session(moteur) as perdante:
            try:
                _figer_linstantane(perdante)
                DepotAvisSql(gagnante, ttl=TTL).ecrire(CLE, [_partagee("écrit par le gagnant")])
                gagnante.commit()

                DepotAvisSql(perdante, ttl=TTL).ecrire(CLE, [_partagee("écrit par le perdant")])

                # La transaction de la perdante est encore utilisable : c'est ce que le
                # point de sauvegarde achète, et c'est ce qui se vérifie ici.
                assert perdante.scalar(select(func.count()).select_from(AvisProduit)) == 0
            finally:
                perdante.rollback()
                _vider(moteur)

    def test_apres_la_course_la_base_porte_le_contenu_du_gagnant_et_lui_seul(self, moteur: Engine):
        """🔴 **L'autre moitié : ce que la base porte réellement une fois la course finie.**

        ⚠️ **Pourquoi deux tests et non un seul, alors que la production fait les deux d'un
        coup.** La collision ne se produit, sans thread, que sous `REPEATABLE READ` — et
        sous `REPEATABLE READ` la relecture de `ecrire()` reste prisonnière de l'instantané
        gelé, donc rend vide. En production, les deux transactions sont en `READ COMMITTED` :
        la relecture prend un instantané neuf et **voit** le contenu de la gagnante.

        Un seul test montrerait donc l'un ou l'autre, jamais les deux, et le forcer
        reviendrait à écrire une assertion qui décrit le montage plutôt que le produit. La
        relecture se vérifie donc ici, dans une transaction neuve — c'est exactement ce que
        fait `ecrire()` en `READ COMMITTED`.
        """
        with Session(moteur) as gagnante, Session(moteur) as perdante:
            try:
                _figer_linstantane(perdante)
                DepotAvisSql(gagnante, ttl=TTL).ecrire(CLE, [_partagee("écrit par le gagnant")])
                gagnante.commit()
                DepotAvisSql(perdante, ttl=TTL).ecrire(CLE, [_partagee("écrit par le perdant")])
                perdante.commit()

                with Session(moteur) as lecture:
                    lus = DepotAvisSql(lecture, ttl=TTL).lire(CLE, maintenant=MIDI).avis

                assert [un_avis.titre for un_avis in lus] == ["écrit par le gagnant"], (
                    "le perdant ne doit rien laisser : sinon deux campagnes concurrentes "
                    "liraient un cache dont le contenu dépend de qui a fini le dernier"
                )
            finally:
                _vider(moteur)


def _figer_linstantane(session: Session) -> None:
    """Passe la session en `REPEATABLE READ` et lui fait prendre son instantané.

    La lecture est ce qui **ouvre** la transaction : sans elle, l'instantané serait pris
    plus tard, après le `commit()` de l'autre, et il n'y aurait aucune course.
    """
    session.connection(execution_options={"isolation_level": "REPEATABLE READ"}).execute(
        select(func.count()).select_from(AvisProduit)
    )


def _partagee(titre: str) -> Avis:
    """Deux écrivains, la **même** URL sous la même clé — la collision par construction."""
    return Avis(
        requete_normalisee=CLE,
        url="https://a.invalid/partagee",
        titre=titre,
        extrait="Fixture de test.",
        source="brave",
        recupere_le=MIDI,
    )


def _vider(moteur: Engine) -> None:
    """Ces tests valident hors de la transaction du conftest : le ménage est explicite."""
    with Session(moteur) as menage:
        menage.query(AvisProduit).delete()
        menage.commit()


class TestLaBorneDeLextrait:
    """La borne est tenue par la couche haute **et** par la contrainte SQL."""

    def test_un_extrait_trop_long_est_tronque_a_lecriture(self, depot, session):
        """`vers_ligne()` borne à la porte de la table, quelle que soit la provenance."""
        bavard = Avis(
            requete_normalisee=CLE,
            url="https://a.invalid/1",
            titre="titre",
            extrait="a" * 2000,
            source="brave",
            recupere_le=MIDI,
        )

        depot.ecrire(CLE, [bavard])

        (stocke,) = depot.lire(CLE, maintenant=MIDI).avis
        assert len(stocke.extrait) <= 500

    def test_la_contrainte_sql_est_le_filet_sous_la_troncature(self, session):
        """⚠️ Contre-épreuve : en contournant `vers_ligne()`, la base refuse quand même.

        Sans ce test, on saurait que la couche haute tronque — pas que la borne est tenue
        si quelqu'un écrit dans la table par un autre chemin.
        """
        ligne = AvisProduit(
            requete_normalisee=CLE,
            url="https://a.invalid/1",
            titre="titre",
            extrait="a" * 2000,
            source="brave",
            recupere_le=MIDI,
        )
        session.add(ligne)

        with pytest.raises(Exception, match="extrait_borne"):
            session.flush()


def test_vers_ligne_borne_lextrait_quelle_que_soit_la_source():
    """Pur, mais gardé ici : c'est le contrat que les deux tests ci-dessus supposent."""
    long = Avis(
        requete_normalisee=CLE,
        url="https://a.invalid/1",
        titre="titre",
        extrait="a" * 2000,
        source=SOURCE_FABRIQUE,
        recupere_le=MIDI,
    )

    assert len(vers_ligne(long).extrait) <= 500
