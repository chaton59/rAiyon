"""La trace : structurée, dérivée du registre, sans une seule phrase rédigée.

Le test central de ce fichier est le dernier : **toute chaîne présente dans une trace
vient du registre, d'une énumération du module, ou du catalogue.** Rien n'y est
composé. C'est ce qui rend la trace utilisable par le repli sur template de §3.11
niveau 3 sans qu'un texte figé s'y soit glissé.
"""

from decimal import Decimal

from conftest import fabriquer
from raiyon.matching.attributs import ATTRIBUTS, Role
from raiyon.matching.criteres import (
    Critere,
    Importance,
    Operateur,
    Optimisation,
    RequeteMatching,
)
from raiyon.matching.score import evaluer_lot
from raiyon.matching.trace import Statut


def test_un_champ_daffichage_napparait_jamais_dans_la_trace():
    """`color` ne peut pas être un critère, donc il ne peut pas produire de ligne.

    C'est le cas G2 : deux casques dont seuls le prix et la couleur diffèrent ne
    peuvent pas être départagés par la couleur, parce qu'elle n'entre nulle part.
    """
    noir = fabriquer("headphones", 1, "23.47", color="Black / Silver")
    autre = fabriquer("headphones", 2, "41.99", color="Black")
    requete = RequeteMatching(
        categorie="headphones",
        criteres=(
            Critere(
                champ="type",
                operateur=Operateur.EGAL,
                valeur="Circumaural",
                importance=Importance.BLOQUANT,
            ),
        ),
    )
    for evaluation in evaluer_lot((noir, autre), requete):
        assert all(ligne.champ != "color" for ligne in evaluation.lignes)
        assert evaluation.score == 0


def test_une_retrogradation_appliquee_est_presente_et_marquee():
    """« Plutôt 144 Hz » : le rôle appliqué est `score`, et la trace le dit."""
    requete = RequeteMatching(
        categorie="monitor",
        criteres=(
            Critere(
                champ="refresh_rate",
                operateur=Operateur.AU_MOINS,
                valeur=144,
                importance=Importance.SOUHAIT,
            ),
        ),
    )
    (evaluation,) = evaluer_lot((fabriquer("monitor", 1, "300"),), requete)
    (ligne,) = evaluation.lignes
    assert ligne.retrograde
    assert ligne.role_applique is Role.SCORE
    assert ligne.poids is not None


def test_un_filtre_dur_ne_porte_ni_poids_ni_sous_score():
    """Il conditionne l'entrée ; il ne pondère pas le classement."""
    requete = RequeteMatching(
        categorie="monitor",
        criteres=(
            Critere(
                champ="aspect_ratio",
                operateur=Operateur.EGAL,
                valeur="16:9",
                importance=Importance.BLOQUANT,
            ),
        ),
    )
    (evaluation,) = evaluer_lot((fabriquer("monitor", 1, "300"),), requete)
    (ligne,) = evaluation.lignes
    assert ligne.role_applique is Role.FILTRE_DUR
    assert ligne.statut is Statut.MATCHE
    assert ligne.poids is None
    assert ligne.sous_score is None


def test_la_trace_porte_le_libelle_francais_et_lunite_du_registre():
    """Le repli sur template de l'étape 9 les trouvera ici, pas dans un dictionnaire à part."""
    requete = RequeteMatching(
        categorie="monitor",
        criteres=(
            Critere(
                champ="refresh_rate",
                operateur=Operateur.AU_MOINS,
                valeur=144,
                importance=Importance.IMPORTANT,
            ),
        ),
    )
    (evaluation,) = evaluer_lot((fabriquer("monitor", 1, "300"),), requete)
    (ligne,) = evaluation.lignes
    assert ligne.libelle_fr == "fréquence de rafraîchissement"
    assert ligne.unite == "Hz"


def test_aucune_chaine_de_la_trace_nest_composee():
    """Tout texte de la trace se retrouve tel quel dans le registre ou dans le produit.

    Une phrase rédigée — « la fréquence est un peu basse » — échouerait ici, et c'est
    le but : la mise en mots appartient à l'étape 8, la mise en forme à l'étape 11.
    """
    produit = fabriquer("monitor", 1, "300", panel_type="IPS")
    requete = RequeteMatching(
        categorie="monitor",
        criteres=(
            Critere(
                champ="refresh_rate",
                operateur=Operateur.AU_MOINS,
                valeur=144,
                importance=Importance.SOUHAIT,
            ),
            Critere(
                champ="panel_type",
                operateur=Operateur.EGAL,
                valeur="IPS",
                importance=Importance.IMPORTANT,
            ),
        ),
        optimisation=Optimisation.MOINS_CHER,
    )
    (evaluation,) = evaluer_lot((produit,), requete)

    admises = {attribut.champ for attribut in ATTRIBUTS["monitor"].values()}
    admises |= {attribut.libelle_fr for attribut in ATTRIBUTS["monitor"].values()}
    admises |= {attribut.unite for attribut in ATTRIBUTS["monitor"].values() if attribut.unite}
    admises |= {statut.value for statut in Statut} | {role.value for role in Role}
    admises |= {valeur for valeur in produit.specs.model_dump().values() if isinstance(valeur, str)}

    for ligne in evaluation.lignes:
        for valeur in (
            ligne.champ,
            ligne.libelle_fr,
            ligne.unite,
            ligne.statut.value,
            ligne.role_applique.value,
            ligne.valeur_produit,
            ligne.valeur_demandee,
        ):
            if isinstance(valeur, str):
                assert valeur in admises, f"chaîne composée dans la trace : {valeur!r}"


def test_le_sous_score_dun_prix_demande_apparait_en_derniere_ligne():
    """Toute position gagnée par le prix doit pouvoir se lire : elle a sa ligne."""
    requete = RequeteMatching(categorie="monitor", optimisation=Optimisation.MOINS_CHER)
    (evaluation,) = evaluer_lot((fabriquer("monitor", 1, "108"),), requete)
    assert evaluation.avec_ligne_de_prix
    assert evaluation.lignes[-1].champ == "prix_usd"
    assert evaluation.lignes[-1].sous_score == Decimal(1)
