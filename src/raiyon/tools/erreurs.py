"""Les refus de la couche outils : un code, et un message écrit **pour le modèle**.

Deux natures d'issue, et elles ne se confondent pas (convention de l'étape 7) :

* **Un refus de jeton n'est pas une erreur.** `enregistrer_criteres` réussit, applique
  ce qui était légitime, et rend la liste des mouvements refusés. L'agent peut alors
  dire au client « je garde 144 Hz tant que tu ne me dis pas le contraire ». C'est une
  réponse, pas un incident.
* **`OutilRefuse` arrête l'outil.** Il est réservé à ce que le modèle doit
  **corriger** : champ inconnu, opérateur incompatible avec le genre, promotion
  interdite, deux catégories dans un tour. Son message dit **quoi faire**.

Cette seconde convention n'est pas inventée ici : `resoudre_critere()` rédige déjà ses
messages pour être lus par un modèle — « Repasser en 'important' ». La couche outils la
prolonge, et laisse passer verbatim les messages du registre plutôt que de les
reformuler : deux rédactions de la même règle finissent par en dire deux choses.

⚠️ **Ce module ne dépend de rien**, pas même du registre. C'est ce qui permet à
`etat.py` comme à `outils.py` de le charger sans créer de cycle, et de n'avoir qu'un
seul type d'erreur à traiter pour tout ce qui entre.
"""

from enum import StrEnum


class CodeRefus(StrEnum):
    """Ce que le modèle doit corriger. Un code par geste, pas un par message.

    L'étape 8 lira le code pour décider quoi faire (redemander, reformuler, séquencer)
    et le texte pour l'expliquer au client. Un code de plus se justifie quand la
    réaction attendue change ; pas quand seule la phrase change.
    """

    CATEGORIE_INCONNUE = "categorie_inconnue"
    """La catégorie demandée n'existe pas au catalogue."""

    CATEGORIE_ABSENTE = "categorie_absente"
    """Aucune catégorie n'a encore été enregistrée : il n'y a pas de sous-catalogue
    sur lequel sonder, questionner ou chercher. Un tour, une catégorie — et elle est
    obligatoire (arbitrage K de l'étape 6)."""

    DEUX_CATEGORIES_DANS_UN_TOUR = "deux_categories_dans_un_tour"
    """Deux recherches de produits sur deux catégories dans le même tour client. Le
    moteur garantit qu'un **appel** rend une seule catégorie ; il ne garantit rien sur
    un **tour**, et c'est ici que la garde vit (arbitrage E de l'étape 7)."""

    CHANGEMENT_DE_CATEGORIE_SANS_JETON = "changement_de_categorie_sans_jeton"
    """Le changement de catégorie efface le budget en vigueur (arbitrage D), ce qui est
    un desserrage — la ligne « budget qui passe à `None` » de l'arbitrage B — et le
    jeton du tour est déjà pris.

    Ce refus est **dur** et non un simple mouvement refusé : appliquer le changement
    sans effacer le budget ferait traverser une catégorie à une contrainte que le client
    n'a jamais posée pour elle, et l'appliquer en refusant l'effacement rattacherait les
    critères du tour à l'ancienne catégorie. Il n'y a pas de demi-changement de sujet."""

    CRITERE_INVALIDE = "critere_invalide"
    """Le registre refuse ce critère. Le message vient de `resoudre_critere()` ou de
    `RequeteMatching`, **verbatim** : champ inconnu, champ d'une autre catégorie, champ
    d'affichage, opérateur incompatible avec le genre, promotion interdite, doublon."""

    VALEUR_ILLISIBLE = "valeur_illisible"
    """La chaîne reçue ne se convertit pas dans le genre que le registre déclare.
    `valeur` est **toujours** une chaîne dans le schéma JSON (arbitrage F) : « 144 »
    devient un nombre, « true » un booléen, et « beaucoup » n'est rien."""

    CHAMP_INCONNU = "champ_inconnu"
    """Un champ cité hors critère — la projection d'un sondage, la cible d'une
    demande de précision — n'existe pas dans la catégorie courante."""

    OUTIL_INCONNU = "outil_inconnu"
    """Le nom d'outil appelé n'existe pas. Ajouté à l'étape 8 avec le répartiteur.

    La convention du module est « un code par geste », et corriger un nom d'outil n'est
    pas corriger un champ : le modèle doit relire la liste des outils, pas la valeur
    qu'il a écrite. En pratique le cas est rare — le mode `strict` de l'API garantit les
    noms d'outils — mais le répartiteur ne peut pas s'appuyer là-dessus, puisque le repli
    de l'arbitrage 11 retire précisément ce drapeau."""


class OutilRefuse(Exception):
    """Un appel d'outil que le modèle doit corriger avant de recommencer.

    Portée à l'étape 8 dans un `tool_result` marqué en erreur : le modèle lit le
    message, corrige, rappelle. Ce n'est donc pas une exception d'infrastructure — elle
    fait partie du dialogue avec le modèle, et son texte est du produit.
    """

    def __init__(self, code: CodeRefus, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
