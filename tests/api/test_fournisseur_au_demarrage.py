"""Qui a le droit de construire un fournisseur d'avis, et la liste est une décision.

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
mesure. **Cette moitié-là ne se négocie pas.**

Les portes **interactives** — `make api` et `make chat` — ne sont pas des mesures : ce sont
des dialogues. Une clé posée y sert, sans drapeau de plus, et les deux se comportent de la
même façon. `scripts/essais.py`, qui sert à regarder des conversations plutôt qu'à en
mesurer, demande en plus `--en-ligne` : c'est le seul appelant où le drapeau subsiste, parce
qu'il est le plus proche d'une campagne.
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
        "scripts/console.py",
        "src/raiyon/api/app.py",
    }
)
"""🔴 **Les seuls fichiers qui ont le droit de construire un `FournisseurBrave`.**

Nommés ici comme `test_isolation_reseau` nomme `raiyon.avis.brave` : ce n'est pas une
observation, c'est une **décision**, et un fichier de plus doit faire échouer ce test pour
obliger quelqu'un à dire s'il a le droit de sortir sur le réseau.

**Trois, et le nombre s'est décidé deux fois.** L'API d'abord ; la console ensuite, parce
que deux portes interactives avec des postures réseau différentes fabriquent la fausse
alerte que ce dépôt documente partout ailleurs — « pourquoi `search_reviews` répond ici et
pas là ? ». Le rôle de référence sans réseau est déjà tenu, et mieux, par
`tests/avis/test_hors_ligne.py`, qui arrache `socket.socket`.

⚠️ **La duplication du branchement est assumée** : les trois fichiers portent les mêmes
quatre lignes plutôt qu'un helper partagé. Factoriser déplacerait la décision dans l'appel
du helper, où elle cesserait d'être visible ; ici, chaque porte d'entrée déclare sa posture
réseau dans son propre code, et ce test garde la liste.
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


def test_seuls_les_fichiers_autorises_construisent_un_fournisseur():
    """La phrase d'architecture devient un test. **C'est tout l'objet de ce module.**

    Elle est écrite dans `agent/session.py`, `eval/executeur.py` et `.env.example` ; elle a
    été fausse pendant six étapes parce qu'aucun de ces trois endroits n'était exécutable.
    """
    trouves = fichiers_qui_construisent_le_fournisseur()
    attendus = set(CONSTRUCTEURS_AUTORISES)
    assert trouves == attendus, (
        f"les constructeurs de FournisseurBrave sont {sorted(trouves)}, "
        f"la liste autorisée dit {sorted(attendus)}.\n"
        "⚠️ Ce nombre est une DÉCISION, pas un constat : il est passé de 1 à 2 puis à 3 "
        "(essais.py, l'API, la console), chaque fois parce que quelqu'un a arbitré qu'une "
        "porte d'entrée avait le droit de sortir sur le réseau. Les chemins de MESURE — "
        "make eval, les cassettes, les tests — n'en construisent aucun, et cette moitié-là "
        "ne se négocie pas. Si vous ajoutez un fichier, écrivez pourquoi dans "
        "CONSTRUCTEURS_AUTORISES avant de le lister."
    )


@pytest.mark.parametrize("fichier", sorted(CONSTRUCTEURS_AUTORISES))
def test_la_liste_ne_nomme_que_des_fichiers_qui_existent(fichier):
    """Sans elle, une entrée périmée rendrait le test précédent vert pour une mauvaise
    raison le jour où un fichier est renommé."""
    assert (RACINE / fichier).is_file()


def test_les_deux_portes_interactives_ont_la_meme_posture_reseau():
    """**L'API et la console, ensemble ou aucune des deux.**

    Deux points d'entrée interactifs aux comportements réseau différents fabriquent une
    fausse alerte : le même geste marche d'un côté et refuse de l'autre, et le rapport de
    bogue qui en sort désigne `search_reviews` plutôt que le câblage. Ce test lie les deux
    plutôt que de laisser l'un dériver.
    """
    constructeurs = fichiers_qui_construisent_le_fournisseur()

    assert ("src/raiyon/api/app.py" in constructeurs) == ("scripts/console.py" in constructeurs), (
        "l'API et la console doivent sortir sur le réseau dans les mêmes conditions"
    )
