"""Le point de bascule : `RAIYON_ORCHESTRATION` décide qui conduit le tour. **Pur.**

Deux choses se vérifient ici, et la seconde est celle qui coûterait cher :

1. la variable sélectionne bien l'une ou l'autre ;
2. **les deux ensembles de noms coïncident** — ceux que `Settings.orchestration` accepte, et
   ceux que `orchestrations()` porte. Une valeur acceptée par la configuration et absente de
   la table lèverait un `KeyError` au **premier message** d'une conversation, c'est-à-dire
   après le `make up`, le `make seed` et la première frappe — le pire moment pour découvrir
   une faute de frappe.

C'est le même motif que `cles_reconnues()` dans `config.py` : la liste se **dérive**, elle
ne se recopie pas.
"""

import typing

import pytest

from raiyon.agent.boucle import repondre
from raiyon.config import Settings, get_settings
from raiyon.machine.orchestrateur import repondre_machine
from raiyon.orchestration import Orchestrateur, orchestrations, repondre_en_vigueur


def valeurs_acceptees() -> set[str]:
    """Les valeurs du `Literal` de `Settings.orchestration`, lues sur l'annotation."""
    return set(typing.get_args(Settings.model_fields["orchestration"].annotation))


def test_le_defaut_est_lagent():
    """L'orchestration existante reste celle qu'on sert sans rien configurer. La machine se
    demande, elle ne s'obtient pas par inadvertance."""
    assert repondre_en_vigueur() is repondre


def test_la_variable_bascule_sur_la_machine(monkeypatch):
    """`RAIYON_ORCHESTRATION=machine` et rien d'autre — pas de second interrupteur."""
    monkeypatch.setenv("RAIYON_ORCHESTRATION", "machine")

    assert repondre_en_vigueur() is repondre_machine


def test_la_bascule_ne_demande_quun_vidage_de_cache(monkeypatch):
    """`repondre_en_vigueur()` résout à chaque appel : `get_settings.cache_clear()` suffit.

    Un module qui mémoriserait l'orchestration à l'import ajouterait un second cache à
    invalider, et c'est le genre d'état qui survit à un test et fait échouer le suivant.
    """
    monkeypatch.setenv("RAIYON_ORCHESTRATION", "machine")
    assert repondre_en_vigueur() is repondre_machine

    get_settings.cache_clear()
    monkeypatch.setenv("RAIYON_ORCHESTRATION", "agent")

    assert repondre_en_vigueur() is repondre


def test_toute_valeur_acceptee_par_la_configuration_a_son_orchestration():
    """⚠️ Sinon la faute se découvre au **premier message** d'une conversation, sous la
    forme d'un `KeyError` sur un nom que la configuration avait pourtant validé."""
    assert set(orchestrations()) == valeurs_acceptees()


@pytest.mark.parametrize("nom", sorted(orchestrations()))
def test_chaque_orchestration_se_conforme_au_protocole(nom: str):
    """Le contrôle réel est celui de **mypy**, sur le type de retour d'`orchestrations()`.

    Ce test-ci ne le remplace pas : il constate seulement que la table porte des appelables,
    ce qui reste vrai si quelqu'un désactive le typage sur une ligne. La substituabilité,
    elle, est vérifiée à la compilation — c'est tout l'intérêt du `Protocol`.
    """
    orchestrateur: Orchestrateur = orchestrations()[nom]

    assert callable(orchestrateur)


def test_la_configuration_refuse_une_orchestration_inconnue(monkeypatch):
    """La garde est dans `config.py`, comme toutes les autres : c'est le point unique de
    lecture de l'environnement, et `repondre_en_vigueur()` n'a donc rien à valider."""
    from pydantic import ValidationError

    monkeypatch.setenv("RAIYON_ORCHESTRATION", "graphe")

    with pytest.raises(ValidationError):
        repondre_en_vigueur()
