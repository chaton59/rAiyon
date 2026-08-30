"""Ce que le registre accepte, ce qu'il refuse, et ce qu'il requalifie.

La rétrogradation et la promotion ne sont **pas symétriques**, et c'est tout l'objet
de ce fichier : un souhait sur un filtre dur gradué s'assouplit, un bloquant sur un
attribut de rôle `score` lève.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from raiyon.matching.attributs import Role
from raiyon.matching.criteres import (
    Critere,
    CritereInvalide,
    Importance,
    Operateur,
    RequeteMatching,
    resoudre_critere,
)


def critere(champ, operateur=Operateur.EGAL, valeur="x", importance=Importance.BLOQUANT):
    return Critere(champ=champ, operateur=operateur, valeur=valeur, importance=importance)


def test_champ_inconnu_refuse():
    with pytest.raises(CritereInvalide, match="champ inconnu"):
        resoudre_critere("monitor", critere("nombre_de_pixels_magiques"))


def test_champ_dune_autre_categorie_refuse():
    """`screen_size` existe — sur les écrans. Le registre est indexé par catégorie."""
    with pytest.raises(CritereInvalide, match="champ inconnu"):
        resoudre_critere("cpu", critere("screen_size", Operateur.AU_MOINS, 27))


def test_operateur_incompatible_avec_le_genre_refuse():
    """« Au moins une interface SATA » n'a pas de sens : une énumération n'est pas ordonnée."""
    with pytest.raises(CritereInvalide, match="incompatible"):
        resoudre_critere(
            "internal-hard-drive", critere("interface", Operateur.AU_MOINS, "SATA 6.0 Gb/s")
        )


def test_champ_daffichage_refuse():
    """`color` est montré au client ; il n'entre jamais dans le matching."""
    with pytest.raises(CritereInvalide, match="affichage"):
        resoudre_critere("memory", critere("color", valeur="Black"))


def test_champ_impose_refuse():
    """`disponible` est appliqué par le moteur, il ne se négocie pas."""
    with pytest.raises(CritereInvalide, match="imposé"):
        resoudre_critere("memory", critere("disponible", valeur=True))


def test_bloquant_sur_un_attribut_de_role_score_leve():
    """Arbitrage D : la promotion est interdite, et bruyante.

    Promouvoir `boost_clock` — 66,1 % de remplissage — en filtre dur exclurait un tiers
    du catalogue sur une absence de donnée. Le message le dit avec le chiffre.
    """
    with pytest.raises(CritereInvalide, match=r"33\.9%"):
        resoudre_critere("cpu", critere("boost_clock", Operateur.AU_MOINS, Decimal("5")))


def test_important_sur_un_attribut_de_role_score_est_accepte():
    """La nuance existe : c'est le bloquant qui est refusé, pas l'insistance."""
    resolu = resoudre_critere(
        "cpu",
        critere("boost_clock", Operateur.AU_MOINS, Decimal("5"), Importance.IMPORTANT),
    )
    assert resolu.role_applique is Role.SCORE
    assert resolu.poids == Decimal("2")
    assert not resolu.retrograde


@pytest.mark.parametrize(
    ("categorie", "champ", "valeur"),
    [
        ("monitor", "refresh_rate", 144),
        ("monitor", "screen_size", 27),
        ("internal-hard-drive", "capacity", 2000),
        ("memory", "capacite_totale_gb", 32),
        ("video-card", "memory", 12),
        ("video-card", "length", 300),
        ("cpu", "core_count", 8),
        ("cpu", "tdp", 65),
    ],
)
def test_souhait_sur_un_filtre_dur_gradue_est_retrograde_et_signale(categorie, champ, valeur):
    """« Plutôt 144 Hz » devient un score, et la trace le dira."""
    resolu = resoudre_critere(
        categorie, critere(champ, Operateur.AU_MOINS, valeur, Importance.SOUHAIT)
    )
    assert resolu.role_applique is Role.SCORE
    assert resolu.retrograde
    assert resolu.poids == Decimal("1")


@pytest.mark.parametrize(
    ("categorie", "champ", "valeur"),
    [
        ("memory", "ddr_generation", 5),
        ("internal-hard-drive", "interface", "SATA 6.0 Gb/s"),
        ("internal-hard-drive", "form_factor", "M.2-2280"),
        ("monitor", "prix_usd", Decimal("300")),
        ("monitor", "categorie", "monitor"),
    ],
)
def test_souhait_sur_un_critere_de_compatibilite_reste_bloquant(categorie, champ, valeur):
    """De la DDR4 n'entre pas dans un socket DDR5, même « plutôt »."""
    operateur = Operateur.AU_PLUS if champ == "prix_usd" else Operateur.EGAL
    resolu = resoudre_critere(categorie, critere(champ, operateur, valeur, Importance.SOUHAIT))
    assert resolu.role_applique is Role.FILTRE_DUR
    assert not resolu.retrograde
    assert resolu.poids is None


def test_une_valeur_du_mauvais_type_est_refusee():
    with pytest.raises(CritereInvalide, match="booléen"):
        resoudre_critere("headphones", critere("microphone", valeur="oui"))
    with pytest.raises(CritereInvalide, match="nombre"):
        resoudre_critere("monitor", critere("refresh_rate", Operateur.AU_MOINS, "beaucoup"))
    with pytest.raises(CritereInvalide, match="chaîne"):
        resoudre_critere("internal-hard-drive", critere("interface", valeur=6))


def test_un_booleen_ne_devient_pas_un_nombre():
    """`True` est un `int` en Python. `microphone=True` ne doit pas valoir 1."""
    resolu = resoudre_critere("headphones", critere("microphone", valeur=True))
    assert resolu.valeur is True


def test_la_requete_refuse_les_champs_a_champ_dedie():
    """Deux chemins vers le budget finiraient par diverger (§3.10).

    Pydantic enveloppe l'exception d'un validateur dans une `ValidationError` : le
    motif reste lisible, et l'étape 7 n'aura qu'un seul type d'erreur à attraper pour
    tout ce qui entre par un schéma d'outil.
    """
    with pytest.raises(ValidationError, match="champs propres"):
        RequeteMatching(
            categorie="monitor",
            criteres=(critere("prix_usd", Operateur.AU_PLUS, Decimal("300")),),
        )


def test_la_requete_refuse_deux_criteres_identiques():
    with pytest.raises(ValidationError, match="deux critères"):
        RequeteMatching(
            categorie="monitor",
            criteres=(
                critere("refresh_rate", Operateur.AU_MOINS, 144),
                critere("refresh_rate", Operateur.AU_MOINS, 240),
            ),
        )


def test_deux_operateurs_differents_sur_le_meme_champ_sont_admis():
    """« Entre 24 et 32 pouces » s'exprime avec deux critères, et c'est légitime."""
    requete = RequeteMatching(
        categorie="monitor",
        criteres=(
            critere("screen_size", Operateur.AU_MOINS, 24),
            critere("screen_size", Operateur.AU_PLUS, 32),
        ),
    )
    assert len(requete.resolus()) == 2


def test_une_requete_invalide_ne_peut_pas_exister():
    """La validation est à la construction : le moteur n'a jamais à s'en assurer."""
    with pytest.raises(ValidationError, match="champ inconnu"):
        RequeteMatching(categorie="cpu", criteres=(critere("refresh_rate", valeur="x"),))
