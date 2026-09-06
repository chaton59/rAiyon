"""Le TTL : ce qui périme, ce qui ne périme pas, et la borne.

Purs : ni base, ni conteneur, ni clé API, ni réseau. C'est le découpage de §3.16 appliqué
au cache — la règle qui décide est une fonction, le SQL est ailleurs.
"""

from datetime import UTC, datetime, timedelta

import pytest

from raiyon.avis.cache import (
    MARQUE_DE_TRONCATURE,
    SOURCE_FABRIQUE,
    Avis,
    EtatCache,
    Lecture,
    est_perime,
    tronquer_extrait,
)
from raiyon.db.models import EXTRAIT_MAX_CARACTERES, SOURCES_AVIS

TTL = timedelta(hours=24)
MIDI = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def un_avis(*, source: str = "brave", recupere_le: datetime = MIDI) -> Avis:
    """Un avis minimal. Seuls `source` et `recupere_le` comptent pour la péremption."""
    return Avis(
        requete_normalisee="asrock avis pg27frs1a",
        url="https://exemple-fixtures.invalid/a",
        titre="titre",
        extrait="extrait",
        source=source,
        recupere_le=recupere_le,
    )


class TestUneLigneRecuperee:
    """`brave` est daté, donc `brave` périme."""

    def test_fraiche_avant_le_ttl(self):
        assert not est_perime(un_avis(), maintenant=MIDI + timedelta(hours=23), ttl=TTL)

    def test_perimee_apres_le_ttl(self):
        assert est_perime(un_avis(), maintenant=MIDI + timedelta(hours=25), ttl=TTL)

    def test_le_bord_exact_est_encore_frais(self):
        """⚠️ **La comparaison est stricte, et le bord tombe du côté généreux.**

        Une campagne lancée à la seconde près ne doit pas se comporter autrement qu'une
        lancée une seconde plus tôt. Le bord doit tomber d'un côté ; il tombe de celui-là.
        """
        assert not est_perime(un_avis(), maintenant=MIDI + TTL, ttl=TTL)

    def test_une_microseconde_apres_le_bord_perime(self):
        apres = MIDI + TTL + timedelta(microseconds=1)

        assert est_perime(un_avis(), maintenant=apres, ttl=TTL)


class TestUneFixture:
    """🔴 L'exception qui rend tenable « les mesures ne sortent jamais sur le réseau »."""

    def test_une_fixture_ne_perime_jamais(self):
        """Sans elle, le seed expirerait 24 h après `make seed` — **silencieusement**.

        Le symptôme serait une campagne qui ne trouve plus rien, sans erreur et sans
        message, un jour après le chargement. C'est la pire forme de panne pour un harnais
        de mesure : elle ne casse pas, elle change ce qui est mesuré.
        """
        vieille = un_avis(source=SOURCE_FABRIQUE, recupere_le=datetime(2020, 1, 1, tzinfo=UTC))

        assert not est_perime(vieille, maintenant=MIDI, ttl=TTL)

    def test_une_fixture_ne_perime_pas_meme_avec_un_ttl_minuscule(self):
        """« TTL à zéro » ne veut même pas dire « pas de cache » — voir `avis_ttl_heures`."""
        fixture = un_avis(source=SOURCE_FABRIQUE)

        assert not est_perime(fixture, maintenant=MIDI + timedelta(days=365), ttl=timedelta(0))

    def test_la_source_fabrique_appartient_au_vocabulaire_du_schema(self):
        """La constante vit dans deux modules ; ce test interdit qu'elles divergent.

        `cache.py` déclare celle des deux provenances qui a un comportement à part,
        `models.py` déclare le vocabulaire clos. Une valeur écrite deux fois est le motif
        que ce dépôt a déjà payé trois fois.
        """
        assert SOURCE_FABRIQUE in SOURCES_AVIS


class TestLaBorneDeLextrait:
    """La borne est explicite, et elle ne se dépasse pas — pas même de sa propre marque."""

    def test_un_extrait_court_traverse_intact(self):
        assert tronquer_extrait("trois mots courts") == "trois mots courts"

    def test_un_extrait_a_la_borne_exacte_traverse_intact(self):
        pile = "a" * EXTRAIT_MAX_CARACTERES

        assert tronquer_extrait(pile) == pile

    def test_un_extrait_trop_long_est_coupe_dans_la_borne(self):
        """⚠️ **La marque part dans le budget.** Une borne qu'on peut dépasser n'en est pas."""
        trop = "a" * (EXTRAIT_MAX_CARACTERES + 200)

        coupe = tronquer_extrait(trop)

        assert len(coupe) <= EXTRAIT_MAX_CARACTERES

    def test_la_coupe_est_marquee(self):
        """Un extrait tronqué sans marque se lit comme une phrase finie."""
        trop = "mot " * EXTRAIT_MAX_CARACTERES

        assert tronquer_extrait(trop).endswith(MARQUE_DE_TRONCATURE)


class TestLaLecture:
    """`utilisable` est ce que la couche outils testera, et il n'y a qu'un état vrai."""

    @pytest.mark.parametrize("etat", [EtatCache.ABSENT, EtatCache.PERIME])
    def test_un_miss_nest_pas_utilisable(self, etat):
        assert not Lecture((), etat).utilisable

    def test_un_groupe_vide_mais_trouve_est_utilisable(self):
        """⚠️ **« La recherche n'a rien rendu » est un fait, et il se met en cache.**

        Sans cet état, une requête sans résultat serait refaite indéfiniment — et pendant
        une campagne hors ligne, refaite pour rien à chaque tour.
        """
        assert Lecture((), EtatCache.TROUVE).utilisable
