"""Le récupérateur réseau, **en `Protocol` et sans implémentation**. Étape 27.

Il n'existe aujourd'hui aucun fournisseur. C'est un état voulu, pas un chantier en cours :
tout le reste du sixième outil — le câblage, l'exclusion du `ContexteFourni`,
l'encadrement, la borne d'appels, le journal — se construit et se teste **sur le cache
pré-chargé**, sans clé et sans réseau. L'implémentation Brave est la dernière pièce, et
elle se branche derrière ce `Protocol` sans qu'aucune ligne d'appelant ne change.

---

### `None` veut dire hors ligne, et c'est le défaut

`ContexteOutils.fournisseur` vaut `None` tant que personne n'en construit un. Les tests,
les campagnes d'éval et `make check` sont donc hors ligne **par construction**, sans
drapeau à poser ni à se rappeler. Un mode hors ligne qui s'active par variable
d'environnement s'oublie ; un mode hors ligne qui est l'absence d'un objet ne s'oublie pas.

### 🔴 Hors ligne, un miss est **bruyant**

C'est la propriété qui rend la décision « les mesures ne sortent jamais sur le réseau »
sûre au-delà de son premier jour. Sans fournisseur, un miss n'est **pas** un résultat
vide : c'est `AVIS_HORS_LIGNE`, un refus d'outil qui nomme la clé manquante.

La différence n'est pas cosmétique. Un résultat vide se confond avec « cherché, rien
trouvé » : le scénario continue, le modèle rédige sans avis, et la campagne mesure autre
chose que ce qu'elle annonce — **sans erreur, sans message**. C'est le mode d'échec le plus
coûteux d'un harnais de mesure, et il a déjà été payé une fois dans ce dépôt (le TTL sur
les fixtures, étape 26). Un refus, lui, se compte par code dans le rapport d'éval, se voit
dans le journal, et **nomme la fixture à écrire**.

### ⚠️ Ce qu'un `ABSENT` compte — et le taux unique qu'il ne faut pas publier

L'étape 28 a rendu « 8 recherches, 4 miss, 50 % ». **Ce taux recouvre trois choses de
natures différentes, et les additionner ne veut rien dire :**

| Ce que le miss dit | Nature | Où ça se corrige |
|---|---|---|
| la fixture n'est pas au seed | **propriété du harnais** | écrire la fixture |
| deux formulations voisines d'un besoin | **défaut réel**, en ligne aussi | `SEUIL_RECOUVREMENT` |
| une requête qui nomme trois produits | **défaut de produit** | la description de l'outil |

Le premier cas ne coûte rien en ligne : le miss y déclenche simplement une vraie recherche.
Le deuxième en coûte toujours — deux recherches payées pour une, et deux entrées de cache
qui cassent la comparabilité que ce cache existe pour tenir. Le troisième ne se rattrape
par aucun appariement : aucune page d'avis ne traite trois références à la fois.

La première ligne ne doit **jamais** entrer dans le même compteur que les deux autres :
elle mesure la couverture d'un jeu de fixtures écrit à la main, ce qui n'a pas de sens
comme métrique de produit et qui ferait paraître le cache défaillant là où c'est le seed
qui est incomplet. Les deux autres sont des défauts, et elles se comptent séparément parce
qu'elles se corrigent à deux endroits opposés — l'appariement pour l'une, le prompt pour
l'autre.

*Alternative écartée — lever une exception et arrêter la campagne.* Plus bruyant encore,
et trop : une fixture manquante ferait perdre les mesures de tous les autres scénarios de
la passe. Le refus est visible sans être destructeur, et il laisse la conversation se
poursuivre — ce qui est d'ailleurs une information de plus : on voit ce que le modèle fait
quand la recherche échoue.
"""

from typing import Protocol

from raiyon.avis.cache import Avis


class Fournisseur(Protocol):
    """Ce qu'un moteur de recherche doit savoir faire, et rien de plus.

    ⚠️ **Il rend des `Avis` déjà bornés**, pas une réponse d'API : la conversion — champs,
    troncature de l'extrait, horodatage — appartient à l'implémentation. Un `Protocol` qui
    rendrait du JSON brut ferait remonter la forme de Brave dans la couche outils, et le
    jour du changement de fournisseur c'est l'outil qu'il faudrait réécrire.

    `limite` est passée par l'appelant plutôt que lue dans la configuration : c'est la
    couche outils qui sait combien de résultats un `tool_result` peut porter sans noyer le
    contexte, et un fournisseur n'a pas à connaître cette contrainte-là.
    """

    def chercher(self, requete: str, *, limite: int) -> tuple[Avis, ...]: ...
