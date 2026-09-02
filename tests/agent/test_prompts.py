"""Le chargement des prompts versionnés, leur empreinte, et **le choix de la version**.

Quatre choses valent d'être vérifiées, et une seule est évidente :

1. le prompt en vigueur **existe** et se charge — un démarrage sans prompt n'est pas
   rattrapable, et l'erreur doit dire où chercher ;
2. l'empreinte est **stable** sur un même texte et **change** sur un texte différent —
   c'est ce sur quoi l'étape 12 s'appuie pour détecter une cassette obsolète (§7) ;
3. **la sélection de version honore `RAIYON_PROMPT_SYSTEME`**, et son défaut vaut
   `systeme.v1` tant que le jalon 3 de l'étape 13 n'a pas tranché (§3.14) ;
4. **aucun** des prompts système ne porte de marqueur d'interpolation — pas seulement
   celui en vigueur. C'est la conséquence de conception de l'arbitrage 7, et c'est le
   seul point de ce fichier qui empêche un vrai défaut : une date ou une catégorie
   glissée dans le prompt système invaliderait le cache à chaque appel, en silence.

⚠️ **Le point 4 balaie les trois fichiers depuis l'étape 13.** Deux des trois prompts ne
sont sélectionnés par personne pendant la campagne du troisième : une interpolation
glissée dans un fichier au repos ne se verrait qu'au moment de lancer sa campagne,
c'est-à-dire au moment de dépenser trente-six prises.
"""

import pytest

from raiyon.agent.prompts import (
    GRIEF_V1,
    MARQUE_DES_GRIEFS,
    REPERTOIRE,
    SYSTEME_PAR_DEFAUT,
    PromptIntrouvable,
    charger,
    empreinte,
    message_de_grief,
    prompt_systeme,
    version_systeme,
    versions_systeme,
)
from raiyon.config import get_settings


@pytest.fixture
def sans_cache_de_config(monkeypatch):
    """`get_settings()` est mis en cache : sans purge, la variable n'aurait aucun effet."""
    get_settings.cache_clear()
    yield monkeypatch
    monkeypatch.undo()
    get_settings.cache_clear()


def test_le_prompt_systeme_en_vigueur_se_charge():
    prompt = prompt_systeme()

    assert prompt.texte.strip()
    assert len(prompt.empreinte) == 12
    assert prompt.version == version_systeme()


# --------------------------------------------------------------------------- #
# La sélection de version — étape 13, jalon 0, point C
# --------------------------------------------------------------------------- #


def test_la_version_par_defaut_reste_systeme_v1(sans_cache_de_config):
    """Le défaut ne bouge **que** quand le jalon 3 aura tranché quelle version passe en
    vigueur. Le vérifier ici évite qu'une campagne v2 laisse le défaut derrière elle."""
    sans_cache_de_config.delenv("RAIYON_PROMPT_SYSTEME", raising=False)

    assert version_systeme() == SYSTEME_PAR_DEFAUT == "systeme.v1"


def test_la_variable_denvironnement_choisit_le_fichier(sans_cache_de_config):
    """C'est **tout** ce que la variable fait : nommer un fichier. Rien n'entre dans le
    texte, et c'est ce qui la rend compatible avec le préfixe mis en cache (§3.13)."""
    sans_cache_de_config.setenv("RAIYON_PROMPT_SYSTEME", "grief.v1")

    prompt = prompt_systeme()

    assert prompt.version == "grief.v1"
    assert prompt.texte == charger("grief.v1")
    assert prompt.empreinte == empreinte(charger("grief.v1"))


def test_une_version_qui_ressemble_a_un_chemin_est_refusee(sans_cache_de_config):
    """`charger()` concatène sans vérifier : sans le motif de `Settings`, un `..` ferait
    lire un fichier arbitraire du disque. Le contrôle est en configuration, pas ici, parce
    que `config.py` est le point unique de lecture de l'environnement."""
    from pydantic import ValidationError

    sans_cache_de_config.setenv("RAIYON_PROMPT_SYSTEME", "../../etc/passwd")

    with pytest.raises(ValidationError):
        version_systeme()


def test_les_prompts_systeme_sont_decouverts_sur_le_disque():
    """Découverts et non listés : une `systeme.v4.md` ajoutée demain est balayée par le
    test d'interpolation sans que personne n'ait à s'en souvenir."""
    versions = versions_systeme()

    assert SYSTEME_PAR_DEFAUT in versions
    assert GRIEF_V1 not in versions, "le gabarit de grief n'est pas un prompt système"
    assert versions == tuple(sorted(versions))


def test_un_prompt_absent_leve_en_disant_ou_chercher():
    with pytest.raises(PromptIntrouvable) as erreur:
        charger("systeme.v99")

    message = str(erreur.value)
    assert "systeme.v99" in message
    assert str(REPERTOIRE) in message


def test_lempreinte_est_stable_et_discriminante():
    """Stable sur le même texte, différente au moindre caractère — c'est tout ce qu'on
    lui demande, et c'est tout ce que l'étape 12 en attendra."""
    assert empreinte("bonjour") == empreinte("bonjour")
    assert empreinte("bonjour") != empreinte("bonjour.")
    assert len(empreinte("bonjour")) == 12


def test_le_prompt_v1_porte_ses_onze_sections():
    """Onze sections numérotées, une idée chacune, pour que l'étape 13 puisse en déplacer
    **une** et mesurer. Un prompt v1 maximal laisserait les métriques nº3 et nº4 sans
    marge de progression et rendrait chaque changement ultérieur non attribuable.

    ⚠️ **Le test porte sur v1 seul, et il y reste.** v2 et v3 ajoutent des sections — c'est
    leur objet — et étendre ce compte à toutes les versions ferait de la longueur du prompt
    une contrainte, ce qu'elle n'est pas. Ce qui doit valoir pour les trois est
    l'interpolation, et c'est le test suivant.
    """
    texte = charger(SYSTEME_PAR_DEFAUT)

    for numero in range(1, 12):
        assert f"\n## {numero}." in texte, f"section {numero} absente"
    assert "\n## 12." not in texte


@pytest.mark.parametrize("version", versions_systeme())
def test_aucun_prompt_systeme_ne_contient_dinterpolation(version: str):
    """**La conséquence de conception de l'arbitrage 7**, vérifiée plutôt que rappelée.

    Le préfixe mis en cache est `tools` + `system` : il doit être identique octet pour
    octet d'un appel à l'autre. Une date, un budget, une catégorie courante ou un numéro
    de tour dans le prompt système invaliderait le cache à chaque appel — sans erreur,
    sans log, et sans que rien ne le signale avant la facture.

    Le contrôle est grossier — il cherche des marqueurs de gabarit — mais il attrape le
    geste par lequel la faute arrive : une `f`-string ou un `.format()` posé sur le
    fichier.
    """
    texte = charger(version)

    for gabarit in ("{", "}", "%s", "$("):
        assert gabarit not in texte, (
            f"{gabarit!r} suggère une interpolation dans {version}.md — le préfixe mis en "
            "cache cesserait d'être identique octet pour octet, sans erreur ni log"
        )


def test_le_prompt_v1_dit_la_regle_absolue_et_la_verbatim():
    """Deux règles sont des critères d'acceptation, pas des préférences de style :
    §2 (le LLM ne produit jamais un fait) et §3.4ter (les noms se citent verbatim).

    ⚠️ Ce test constate leur **présence**, pas leur **effet**. Rien ne mesure le prompt
    avant l'étape 12 — c'est au §7 des risques.
    """
    texte = charger(SYSTEME_PAR_DEFAUT)

    assert "search_products" in texte
    assert "verbatim" in texte
    assert "id" in texte


# --------------------------------------------------------------------------- #
# Le message de reprise de l'étape 9
# --------------------------------------------------------------------------- #


def test_le_message_de_grief_insere_les_griefs_a_leur_place():
    """Le gabarit vit dans `prompts/grief.v1.md`, versionné comme le prompt système.

    Il n'est **pas** dans le préfixe mis en cache — il voyage dans un bloc `user` — donc
    l'interdiction d'interpolation de l'arbitrage 7 ne le concerne pas. La marque est un
    commentaire markdown plutôt qu'un `{}` de `.format()` : le fichier peut contenir des
    accolades sans qu'il faille les échapper.
    """
    texte = message_de_grief(["- **id_inconnu** — « monitor-00000000ff »"])

    assert MARQUE_DES_GRIEFS not in texte
    assert "monitor-00000000ff" in texte


def test_le_gabarit_de_grief_porte_sa_marque_dinsertion():
    """Sans elle, le modèle recevrait une reprise sans motif — et la régénération
    n'aurait aucune chance d'aboutir. Le contrôle lève plutôt que de la laisser passer."""
    assert MARQUE_DES_GRIEFS in charger(GRIEF_V1)


def test_le_gabarit_de_grief_dit_les_trois_facons_dont_un_chiffre_juste_devient_faux():
    """Il est écrit **pour le modèle** — même convention que les messages d'`erreurs.py` :
    il dit quoi faire, pas « tu as halluciné »."""
    texte = charger(GRIEF_V1)

    assert "fourchette de sondage" in texte
    assert "distribution" in texte
    assert "au-dessus du budget" in texte
