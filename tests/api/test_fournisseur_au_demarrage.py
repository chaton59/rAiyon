"""Le serveur construit son fournisseur d'avis au démarrage, et **lui seul avec `essais.py`**.

### Le défaut que ce module ferme (étape 33)

Trois fichiers du dépôt ont affirmé, de l'étape 27 à l'étape 33, que « `--en-ligne`, la
console et l'API » construisaient un fournisseur. **Aucun des deux derniers ne le
faisait** : `raiyon.api.app` et `scripts/console.py` appelaient `tour()` sans
`fournisseur=`, donc avec le défaut `None`. En clair, `make api` refusait
`search_reviews` avec « aucune recherche en ligne n'est disponible dans cette exécution »
alors que la clé Brave était dans le `.env`, et trois docstrings juraient le contraire.

Le défaut n'était pas dans le câblage seul : il était dans le fait qu'**une phrase
d'architecture n'avait aucun lecteur**. C'est le §9.3 du journal — « une exigence dont la
seule vérification est chère sera violée en silence ». Le lecteur bon marché est ici.

### La règle, et son exception raisonnée

Les chemins de **mesure** restent hors ligne quoi qu'il arrive : `Reglages.fournisseur`
vaut `None` pour `make eval`, les cassettes et les tests, parce qu'un mode en ligne qui
s'activerait à la présence d'un secret ferait qu'installer une clé changerait ce qu'on
mesure. `make api` n'est pas une mesure, c'est le **produit** : une clé posée y sert, sans
drapeau de plus.
"""

import ast
from pathlib import Path

import pytest

from raiyon.api.app import _fournisseur_davis

CLE_FACTICE = "BSA-factice-qui-ne-sortira-jamais"

RACINE = Path(__file__).resolve().parents[2]

CONSTRUCTEURS_AUTORISES = frozenset(
    {
        "scripts/essais.py",
        "src/raiyon/api/app.py",
    }
)
"""🔴 **Les seuls fichiers qui ont le droit de construire un `FournisseurBrave`.**

Nommés ici comme `test_isolation_reseau` nomme `raiyon.avis.brave` : ce n'est pas une
observation, c'est une décision, et un fichier de plus doit faire échouer ce test pour
obliger quelqu'un à dire s'il a le droit de sortir sur le réseau.

⚠️ **`scripts/console.py` n'y est pas, et c'est délibéré** — la console reste hors ligne.
"""


def test_sans_cle_le_serveur_est_hors_ligne():
    """`None` veut dire hors ligne, et l'absence de clé **n'est pas une panne** (§3.18).

    `search_reviews` sert alors le cache et refuse bruyamment ce qu'il n'y trouve pas.
    """
    assert _fournisseur_davis() is None


def test_avec_une_cle_le_serveur_en_construit_un(monkeypatch):
    """La présence de la clé suffit — pas de drapeau, c'est le produit et non une mesure."""
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", CLE_FACTICE)

    from raiyon.config import get_settings

    get_settings.cache_clear()
    fournisseur = _fournisseur_davis()

    assert fournisseur is not None
    assert fournisseur.nom == "brave"


def test_la_cle_ne_sort_pas_du_fournisseur(monkeypatch):
    """**La contre-épreuve qui compte** : construire n'expose pas le secret.

    Un `repr()` de dataclass ou un `__dict__` recopié dans un log est le chemin le plus
    court d'une clé vers un fichier. On le constate ici plutôt que de le supposer.
    """
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", CLE_FACTICE)

    from raiyon.config import get_settings

    get_settings.cache_clear()
    fournisseur = _fournisseur_davis()

    assert CLE_FACTICE not in repr(fournisseur)


def fichiers_qui_construisent_le_fournisseur() -> set[str]:
    """Les fichiers du dépôt où `FournisseurBrave(...)` est **appelé**.

    Une lecture d'AST plutôt qu'un `grep` : un `grep` compterait la ligne d'import, les
    docstrings et les commentaires — c'est-à-dire précisément les endroits où le dépôt
    *parle* du fournisseur au lieu de le construire, et c'est cette confusion-là qui a
    laissé passer le défaut.
    """
    trouves: set[str] = set()
    for chemin in [*RACINE.glob("src/**/*.py"), *RACINE.glob("scripts/**/*.py")]:
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if (
                isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Name)
                and noeud.func.id == "FournisseurBrave"
            ):
                trouves.add(chemin.relative_to(RACINE).as_posix())
    return trouves


def test_deux_fichiers_construisent_un_fournisseur_et_deux_seulement():
    """La phrase d'architecture devient un test. **C'est tout l'objet de ce module.**

    Elle est écrite dans `agent/session.py`, `eval/executeur.py` et `.env.example` ; elle a
    été fausse pendant six étapes parce qu'aucun de ces trois endroits n'était exécutable.
    """
    assert fichiers_qui_construisent_le_fournisseur() == set(CONSTRUCTEURS_AUTORISES)


@pytest.mark.parametrize("fichier", sorted(CONSTRUCTEURS_AUTORISES))
def test_la_liste_ne_nomme_que_des_fichiers_qui_existent(fichier):
    """Sans elle, une entrée périmée rendrait le test précédent vert pour une mauvaise
    raison le jour où un fichier est renommé."""
    assert (RACINE / fichier).is_file()


def test_la_console_reste_hors_ligne():
    """Constaté plutôt que tu. La console est un outil de mise au point, pas le produit.

    Le §9.3 le demande : « un test qui **constate** un trou délibéré vaut mieux qu'un trou
    tu. » Le jour où la console doit sortir sur le réseau, c'est ce test qu'on change — donc
    quelqu'un l'aura décidé.
    """
    assert "scripts/console.py" not in fichiers_qui_construisent_le_fournisseur()
