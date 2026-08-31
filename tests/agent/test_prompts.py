"""Le chargement des prompts versionnés, et leur empreinte (§3.14).

Trois choses valent d'être vérifiées, et une seule est évidente :

1. le prompt en vigueur **existe** et se charge — un démarrage sans prompt n'est pas
   rattrapable, et l'erreur doit dire où chercher ;
2. l'empreinte est **stable** sur un même texte et **change** sur un texte différent —
   c'est ce sur quoi l'étape 12 s'appuiera pour détecter une cassette obsolète (§7) ;
3. le prompt v1 porte bien ses onze sections, et **rien de dynamique**. Ce dernier point
   est la conséquence de conception de l'arbitrage 7, et c'est le seul de ce fichier qui
   empêche un vrai défaut : une date ou une catégorie glissée dans le prompt système
   invaliderait le cache à chaque appel, en silence.
"""

import pytest

from raiyon.agent.prompts import (
    GRIEF_V1,
    MARQUE_DES_GRIEFS,
    REPERTOIRE,
    SYSTEME_V1,
    PromptIntrouvable,
    charger,
    empreinte,
    message_de_grief,
    prompt_systeme,
)


def test_le_prompt_systeme_en_vigueur_se_charge():
    texte, signature = prompt_systeme()

    assert texte.strip()
    assert len(signature) == 12


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
    marge de progression et rendrait chaque changement ultérieur non attribuable."""
    texte = charger(SYSTEME_V1)

    for numero in range(1, 12):
        assert f"\n## {numero}." in texte, f"section {numero} absente"
    assert "\n## 12." not in texte


def test_le_prompt_v1_ne_contient_rien_de_dynamique():
    """**La conséquence de conception de l'arbitrage 7**, vérifiée plutôt que rappelée.

    Le préfixe mis en cache est `tools` + `system` : il doit être identique octet pour
    octet d'un appel à l'autre. Une date, un budget, une catégorie courante ou un numéro
    de tour dans le prompt système invaliderait le cache à chaque appel — sans erreur,
    sans log, et sans que rien ne le signale avant la facture.

    Le contrôle est grossier — il cherche des marqueurs de gabarit — mais il attrape le
    geste par lequel la faute arrive : une `f`-string ou un `.format()` posé sur le
    fichier.
    """
    texte = charger(SYSTEME_V1)

    for gabarit in ("{", "}", "%s", "$("):
        assert gabarit not in texte, f"{gabarit!r} suggère une interpolation dans le prompt"


def test_le_prompt_v1_dit_la_regle_absolue_et_la_verbatim():
    """Deux règles sont des critères d'acceptation, pas des préférences de style :
    §2 (le LLM ne produit jamais un fait) et §3.4ter (les noms se citent verbatim).

    ⚠️ Ce test constate leur **présence**, pas leur **effet**. Rien ne mesure le prompt
    avant l'étape 12 — c'est au §7 des risques.
    """
    texte = charger(SYSTEME_V1)

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
