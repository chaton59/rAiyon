"""Le décorateur d'observation : il compte, il ne change rien, et il voit à travers la pile.

Purs : ni base, ni conteneur, ni clé API. Le client enveloppé est un objet de trois lignes.

⚠️ **La propriété centrale n'est pas « il compte bien »**, c'est « la boucle ne s'en aperçoit
pas ». Un test la constate sur les deux orchestrations en comparant les issues produites avec
et sans décorateur ; c'est celui-là qu'il faut lire en premier.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest

from raiyon.agent.client import EFFORT_NON_FIXE, ReponseLLM, Usage
from raiyon.agent.evenements import MotifDeRepli, Repli, Texte
from raiyon.observation import (
    DISPLAY_PAR_DEFAUT,
    MODELE_INCONNU,
    ClientJournalisant,
    evenement_journalise,
)


@dataclass
class ClientMuet:
    """Un `ClientLLM` qui ne déclare ni modèle, ni coût, ni configuration.

    C'est la forme du faux client de l'étape 8 et du client de cassette : il répond, et il
    n'a rien à dire de ce qu'un appel a coûté.
    """

    reponses: list[ReponseLLM] = field(default_factory=list)
    vues: list[str] = field(default_factory=list)

    def repondre(self, *, systeme: str, outils: Any, messages: Any) -> ReponseLLM:
        self.vues.append(systeme)
        return self.reponses.pop(0)


@dataclass
class ClientBavard(ClientMuet):
    """Un `ClientLLM` qui expose ce que `ClientAnthropic` expose. Sans le SDK."""

    modele: str = "claude-sonnet-5"
    effort: str = EFFORT_NON_FIXE
    display: str = "summarized"
    dernier_usage: Usage | None = None

    def repondre(self, *, systeme: str, outils: Any, messages: Any) -> ReponseLLM:
        reponse = super().repondre(systeme=systeme, outils=outils, messages=messages)
        self.dernier_usage = Usage(
            appels=1, jetons_entree=100, jetons_sortie=42, cache_ecrit=0, cache_lu=9744
        )
        return reponse


@dataclass
class Enveloppe:
    """Un décorateur quelconque de `ClientLLM`, qui nomme `reel` ce qu'il enveloppe.

    C'est la forme de `ClientEnregistreur`, que `scripts/essais.py` empile déjà sous le
    journalisant. Il ne réexpose rien : c'est tout l'intérêt du cas.
    """

    reel: Any

    def repondre(self, *, systeme: str, outils: Any, messages: Any) -> ReponseLLM:
        return self.reel.repondre(systeme=systeme, outils=outils, messages=messages)


def _reponse(texte: str = "voilà", fin: str = "end_turn") -> ReponseLLM:
    return ReponseLLM(blocs=[{"type": "text", "text": texte}], fin=fin)


def test_la_reponse_traverse_le_decorateur_inchangee():
    """La frontière qui compte : la boucle reçoit exactement ce que le client a rendu."""
    attendue = _reponse()
    journalisant = ClientJournalisant(reel=ClientMuet(reponses=[attendue]))

    rendue = journalisant.repondre(systeme="s", outils=(), messages=[])

    assert rendue is attendue


def test_un_appel_journalise_par_appel_numerote_a_partir_de_un():
    """`iteration` situe l'appel **dans le tour**, et c'est le décorateur qui le compte."""
    journalisant = ClientJournalisant(
        reel=ClientBavard(reponses=[_reponse(), _reponse(), _reponse()])
    )

    for _ in range(3):
        journalisant.repondre(systeme="s", outils=(), messages=[])

    assert [appel.iteration for appel in journalisant.drainer()] == [1, 2, 3]


def test_drainer_vide_laccumulateur():
    """Un drainage qui laisserait ses lignes les compterait deux fois au suivant."""
    journalisant = ClientJournalisant(reel=ClientBavard(reponses=[_reponse()]))
    journalisant.repondre(systeme="s", outils=(), messages=[])

    assert len(journalisant.drainer()) == 1
    assert journalisant.drainer() == ()


def test_les_compteurs_viennent_du_client_enveloppe():
    """`dernier_usage` est lu par attribut, jamais par le `Protocol`."""
    journalisant = ClientJournalisant(reel=ClientBavard(reponses=[_reponse()]))
    journalisant.repondre(systeme="s", outils=(), messages=[])

    (appel,) = journalisant.drainer()
    assert (appel.jetons_entree, appel.jetons_sortie, appel.cache_lu) == (100, 42, 9744)
    assert appel.stop_reason == "end_turn"
    assert appel.latence_ms >= 0


def test_la_configuration_dappel_est_journalisee():
    """⚠️ **Ce qui rend l'arbitrage `effort` décidable plus tard.**

    Sans ces deux colonnes, une comparaison ultérieure ne pourrait pas séparer les
    populations d'une campagne, et on retomberait sur trois tirages sur un même message.
    """
    journalisant = ClientJournalisant(reel=ClientBavard(reponses=[_reponse()]))
    journalisant.repondre(systeme="s", outils=(), messages=[])

    (appel,) = journalisant.drainer()
    assert appel.modele == "claude-sonnet-5"
    assert appel.effort == EFFORT_NON_FIXE
    assert appel.display == "summarized"


def test_un_client_qui_ne_declare_rien_donne_des_valeurs_honnetes():
    """Zéro jeton pour un client de cassette est **exact** : un rejeu ne consomme rien.

    Et `display` retombe sur le défaut de l'API, pas sur `summarized` : écrire `summarized`
    supposerait une demande qui n'a pas été faite.
    """
    journalisant = ClientJournalisant(reel=ClientMuet(reponses=[_reponse()]))
    journalisant.repondre(systeme="s", outils=(), messages=[])

    (appel,) = journalisant.drainer()
    assert (appel.jetons_entree, appel.jetons_sortie) == (0, 0)
    assert appel.modele == MODELE_INCONNU
    assert appel.display == DISPLAY_PAR_DEFAUT


def test_les_attributs_sont_cherches_a_travers_une_pile_de_decorateurs():
    """⚠️ **Le défaut que `scripts/essais.py` aurait produit en silence.**

    Il empile un `ClientEnregistreur` sous le journalisant. Un `getattr` sur le premier cran
    aurait rendu des lignes à zéro jeton pour la seule commande qui joue de vraies
    conversations contre l'API — et cela ne se serait vu qu'au tableau de bord, en croyant
    à un cache parfait.
    """
    journalisant = ClientJournalisant(
        reel=Enveloppe(reel=ClientBavard(reponses=[_reponse()])),
    )

    journalisant.repondre(systeme="s", outils=(), messages=[])

    (appel,) = journalisant.drainer()
    assert appel.jetons_sortie == 42
    assert appel.modele == "claude-sonnet-5"


def test_un_appel_qui_leve_est_compte_puis_relance():
    """Un tableau de bord qui masque les appels échoués ment sur la latence et sur le compte."""

    class ClientQuiCasse(ClientMuet):
        def repondre(self, *, systeme: str, outils: Any, messages: Any) -> ReponseLLM:
            raise TimeoutError("l'API n'a pas répondu")

    journalisant = ClientJournalisant(reel=ClientQuiCasse())

    with pytest.raises(TimeoutError):
        journalisant.repondre(systeme="s", outils=(), messages=[])

    (appel,) = journalisant.drainer()
    assert appel.stop_reason == "erreur:TimeoutError"
    assert (appel.jetons_entree, appel.jetons_sortie) == (0, 0)


def test_lempreinte_est_celle_du_systeme_reellement_envoye():
    """Recalculée sur ce qui part, pas reçue de l'appelant : c'est ce qui ferme l'écart."""
    from raiyon.agent.prompts import empreinte

    journalisant = ClientJournalisant(reel=ClientBavard(reponses=[_reponse()]))
    journalisant.repondre(systeme="le prompt en vigueur", outils=(), messages=[])

    (appel,) = journalisant.drainer()
    assert appel.empreinte_systeme == empreinte("le prompt en vigueur")


def test_la_charge_dun_evenement_est_celle_du_fil_sse():
    """La timeline relue et le direct montrent la même chose, **par construction**."""
    from raiyon.api.serialisation import nom_et_donnees

    evenement = Texte("Voici trois écrans à moins de 400 $.")

    genre, charge = evenement_journalise(evenement)

    nom, donnees = nom_et_donnees(evenement)
    assert (genre, charge) == (nom.value, donnees)
    assert genre == "message"


def test_un_repli_est_journalise_avec_son_motif():
    """Un `Repli` n'est dans aucune autre table : c'est sa seule trace persistée."""
    genre, charge = evenement_journalise(
        Repli("Je m'y perds un peu.", 8, ("search_products",), MotifDeRepli.MAX_ITERATIONS)
    )

    assert genre == "fallback"
    assert charge["motif"] == "max_iterations"
    # Ni `iterations` ni `outils_appeles` : ce sont des métriques de boucle, et la charge
    # est celle du fil (arbitrage G de l'étape 10). Le compte d'appels vit dans l'autre
    # table, où il est exact.
    assert "iterations" not in charge


def test_la_charge_ne_porte_aucun_decimal_python():
    """Le JSONB doit recevoir des types JSON : un `Decimal` ne s'y sérialise pas.

    `serialisation.py` rend déjà les montants en chaînes — même convention
    qu'`en_tool_result()`. On le constate ici parce que la table est neuve et que c'est
    exactement le genre d'écart qui ne se voit qu'à l'insertion, en production.
    """
    _, charge = evenement_journalise(Texte("bonjour"))

    def sans_decimal(valeur: Any) -> bool:
        if isinstance(valeur, Decimal):
            return False
        if isinstance(valeur, dict):
            return all(sans_decimal(item) for item in valeur.values())
        if isinstance(valeur, list):
            return all(sans_decimal(item) for item in valeur)
        return True

    assert sans_decimal(charge)
