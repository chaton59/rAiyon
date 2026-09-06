"""La porte d'entrée unique de `avis_produit` : `AvisEnSeed`. **Aucun appel réseau.**

Même dispositif que `catalogue.schemas.ProduitEnBase`, et pour la même raison : un fichier
committé n'est pas digne de confiance du seul fait d'être committé. Il se modifie à la
main — c'est même son usage ici, puisque les fixtures sont écrites à la main —, il se
résout à la main après un conflit, et un `git checkout` d'une branche ancienne le remplace.

⚠️ **Ce schéma n'accepte que `source="fabrique"`, et c'est une garde, pas un défaut.** Le
seed est le seul chemin par lequel un contenu entre au dépôt git ; y laisser passer une
ligne `brave` en ferait une redistribution de résultats de recherche, interdite par le
§3(b) des conditions Brave. La règle est donc portée par le type, où on ne peut pas
l'oublier, plutôt que par une consigne dans un README.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from raiyon.avis.cache import SOURCE_FABRIQUE, Avis, tronquer_extrait
from raiyon.avis.normalisation import normaliser
from raiyon.catalogue.schemas import MOTIF_ID
from raiyon.db.models import EXTRAIT_MAX_CARACTERES

DATE_DES_FIXTURES = datetime(2026, 1, 1, tzinfo=UTC)
"""L'horodatage donné à toute ligne du seed. **Arbitraire, et sans effet.**

Une ligne `fabrique` ne périme jamais : cette date n'entre dans aucune décision. Elle est
fixe et non `now()` pour une seule raison — deux chargements du même seed doivent produire
la même base, sans quoi comparer deux exécutions reviendrait à comparer deux horodatages.
"""


class AvisEnSeed(BaseModel):
    """Une ligne de `data/seed/avis.jsonl`, validée avant d'atteindre la base.

    `requete` est la requête **en clair**, telle qu'un humain l'écrirait ; la clé est
    dérivée par `normaliser()` à la construction. Écrire la clé normalisée à la main dans
    le fichier serait demander à l'auteur d'appliquer un algorithme de tête, donc garantir
    qu'une fixture finisse un jour rangée sous une clé que rien ne produit.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    requete: str = Field(min_length=1)
    url: str = Field(min_length=1)
    titre: str = Field(min_length=1)
    extrait: str = Field(min_length=1, max_length=EXTRAIT_MAX_CARACTERES)
    produit_id: str | None = Field(default=None, pattern=MOTIF_ID)

    @field_validator("requete")
    @classmethod
    def _la_requete_doit_produire_une_cle(cls, valeur: str) -> str:
        """Une requête qui se normalise en chaîne vide n'a pas de clé.

        « ??? » passerait `min_length=1` et rangerait sa fixture sous `""`, où toutes les
        autres la rejoindraient. Le refus est ici plutôt qu'en base parce que le message
        peut nommer la ligne fautive.
        """
        if not normaliser(valeur):
            raise ValueError(f"« {valeur} » ne produit aucune clé de cache une fois normalisée")
        return valeur

    @field_validator("url")
    @classmethod
    def _lurl_doit_etre_http(cls, valeur: str) -> str:
        """Une URL de fixture reste une URL : le front l'affichera comme un lien."""
        if not valeur.startswith(("http://", "https://")):
            raise ValueError(f"« {valeur} » n'est pas une URL http(s)")
        return valeur

    def en_avis(self) -> Avis:
        """Le type du domaine. **`source` est posée ici, jamais lue du fichier.**

        Le JSONL ne porte pas de colonne `source` : la lui donner ouvrirait la porte que
        la docstring du module ferme. Toute ligne de seed est `fabrique` par construction.
        """
        return Avis(
            requete_normalisee=normaliser(self.requete),
            url=self.url,
            titre=self.titre,
            extrait=tronquer_extrait(self.extrait),
            source=SOURCE_FABRIQUE,
            recupere_le=DATE_DES_FIXTURES,
            produit_id=self.produit_id,
        )
