"""`.env.example` reflète le code, et il ne se relit jamais à la main.

Deux divergences ont déjà coûté ce dépôt, et elles se ressemblent : une valeur écrite
deux fois, corrigée une seule. `erreurs.py` d'abord, puis `SYSTEME_PAR_DEFAUT` contre
`Settings.prompt_systeme` — où le dépôt annonçait `systeme.v2` et servait `systeme.v1`.
`.env.example` est la troisième occurrence du motif, et la plus visible : c'est le
fichier que `make install` copie, donc celui qui décide de ce qu'un clone frais sert.

Purs : ni base, ni conteneur, ni clé API. Ils lisent un fichier de texte.
"""

import re
from pathlib import Path

from raiyon.config import PROMPT_SYSTEME_PAR_DEFAUT

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
"""Résolu depuis ce fichier, jamais depuis le `cwd` : un test qui ne trouve sa cible que
lancé du bon répertoire finit par être ignoré en silence."""


def _lignes() -> list[str]:
    return ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()


def test_la_version_de_prompt_de_lexemple_est_celle_du_code():
    """Sinon un clone frais sert une rédaction que le README ne décrit pas.

    `.env` **écrase** le défaut du code : une valeur périmée ici ne se voit nulle part
    ailleurs, et le dépôt livre silencieusement autre chose que ce qu'il annonce.
    """
    valeurs = [
        ligne.split("=", 1)[1].strip()
        for ligne in _lignes()
        if ligne.startswith("RAIYON_PROMPT_SYSTEME=")
    ]

    assert valeurs == [PROMPT_SYSTEME_PAR_DEFAUT], (
        f"{ENV_EXAMPLE.name} porte {valeurs} et config.py sert {PROMPT_SYSTEME_PAR_DEFAUT!r}."
    )


def test_la_cle_api_reste_commentee_pour_que_son_absence_soit_dite():
    """Une valeur factice rend un 401 du SDK ; seule une variable absente dit quoi faire.

    `cle_api()` ne lève que sur `None`. `make install` copiant ce fichier tel quel, une
    ligne décommentée — même factice — met un clone frais sur le chemin du traceback au
    lieu du message qui nomme les commandes concernées.
    """
    actives = [ligne for ligne in _lignes() if re.match(r"\s*ANTHROPIC_API_KEY\s*=", ligne)]

    assert actives == [], (
        f"{ENV_EXAMPLE.name} porte une ligne ANTHROPIC_API_KEY active : {actives}. "
        "La laisser commentée — voir le test pour la raison."
    )
