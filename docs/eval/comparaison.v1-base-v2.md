# Comparaison v1-base → v2

**Ce que cette comparaison cherche à savoir.** l'effet des trois cibles de systeme.v2 — la rédaction chiffrée, le périmètre de domaine, le markdown que le front ne rend pas. ⚠️ La base et v2 ne datent pas du même jour : l'écart majore la dérive du modèle sans la mesurer.

> ⚠️ **Ce que ces chiffres ne disent pas d'eux-mêmes.**
>
> - **v1-etape12/zero_budget_trop_bas.1 est écartée de ce rapport** — divergence attendue au rejeu.
>   **Le défaut de l'étape 18** : `regle_ecart_au_budget` exigeait l'écart dans la phrase qui nomme le produit, pendant que `regle_montants` refusait ce même écart dans une phrase sans produit — `hors_budget.values()` n'était pas dans les montants admis. Le nom sur une ligne, « il dépasse de X $ » sur la suivante, et les deux règles devenaient **conjointement insatisfaisables**. La section 14 du prompt, qui demande un produit par ligne, mène droit à ce découpage. Ici le grief tombé est un `ecart_non_dit` sur la phrase qui nomme l'ASRock Phantom Gaming PG27FRS1A sans dire de combien il dépasse — l'écart est écrit ailleurs dans le même message, ce que la règle 4 ne regardait pas. ⚠️ **Cette prise remplace `desserrage_refuse.1` dans cette liste**, qui y était depuis l'étape 13 et n'y est plus : le correctif fait tomber les deux griefs qui restaient à son dernier tour, le texte n'est plus refusé du tout, donc plus régénéré — la prise 7 n'est simplement plus consommée, et il n'y a plus de divergence à absorber.
>   Les tours et les griefs de cette prise ne sont donc comptés nulle part ci-dessous.
> - **Ce jeu est composé de plusieurs enregistrements**, donc de plusieurs dates. Un scénario vient
>   d'une seule source — jamais de deux — pour que la dispersion de ses prises reste celle d'un
>   tirage et non celle d'un écart entre deux enregistrements.
>   `v1-desserrage` : `desserrage_refuse`
>   `v1-etape12` : `categorie_efface_budget`, `question_de_domaine`, `zero_budget_trop_bas`
>   `v1-partielle` : `besoin_flou`, `budget_absent`, `budget_serre`, `changement_davis`, `comparaison`, `hors_catalogue`, `sur_specifie`
> - **Prédiction posée avant la campagne v2, sur la section 14 (le markdown).**
>   `SEPARATEURS_DE_PHRASE` traite le saut de ligne comme une fin de phrase. Les listes que
>   v2 interdit produisaient un produit et son prix **par ligne**, donc une phrase étroite par
>   produit — exactement le contexte dans lequel la règle 2 attribue un montant à un produit.
>   Basculer vers de la prose continue donnerait des phrases nommant trois produits et portant
>   trois prix : l'attribution se dégraderait, et les faux positifs deviendraient plus probables.
>   La cible 3 aurait alors une empreinte sur le taux de rejet, et son effet serait inséparable
>   de celui de la cible 1.
>   **Parade appliquée dans v2** : « une ligne par produit » est l'instruction, la prose continue
>   est retirée. Le saut de ligne reste, la règle 2 garde son contexte étroit.
>   **Si le taux de rejet bouge malgré cela, c'est de ce côté qu'il faut regarder d'abord** — et
>   l'appendice A dira si les phrases refusées se sont élargies.
> - **v2/categorie_efface_budget.3 est écartée de ce rapport** — divergence attendue au rejeu.
>   le correctif de `NOMBRE` de l'étape 17 fait tomber les **deux** griefs du tour 1 — les seuls de cette prise. « en 1920x1080 180 Hz » et « en 2560x1440 165 Hz » étaient lus comme 1 080 180 Hz et 1 440 165 Hz, deux valeurs qu'aucun produit ne déclare, et la règle 5 levait un `valeur_non_fournie` sur une phrase exacte. Le tour n'est donc plus refusé du tout : aucune reprise n'est empilée avant régénération, et le 4e appel de la cassette — qui **était** la régénération — devient le premier appel du tour 2, avec une liste de messages entièrement différente. D'où la divergence d'empreinte à cette prise. Le modèle aurait reçu l'historique d'une conversation où sa première réponse a été acceptée : sa réponse enregistrée, écrite sous une reprise qui n'existe plus, n'est pas celle qu'il aurait donnée. ⚠️ **Seule cassette touchée des quatre jeux du dépôt** — vérifié avant la campagne en rejouant les quatre motifs d'extraction, ancien contre nouveau, sur la prose de chaque prise enregistrée.
>   Les tours et les griefs de cette prise ne sont donc comptés nulle part ci-dessous.
> - **v2/zero_budget_trop_bas.3 est écartée de ce rapport** — divergence attendue au rejeu.
>   **Le défaut de l'étape 18** : `regle_ecart_au_budget` exigeait l'écart dans la phrase qui nomme le produit, pendant que `regle_montants` refusait ce même écart dans une phrase sans produit — `hors_budget.values()` n'était pas dans les montants admis. Le nom sur une ligne, « il dépasse de X $ » sur la suivante, et les deux règles devenaient **conjointement insatisfaisables**. La section 14 du prompt, qui demande un produit par ligne, mène droit à ce découpage. Ici le grief tombé est l'unique de la prise : un `montant_non_fourni` sur « 12,99 $ », qui est **l'écart au budget** de l'ASRock Phantom Gaming PG27FRS1A rendu par le moteur. Le message de grief disait « aucun outil n'a rendu ce montant » d'un chiffre que `search_products` avait rendu. Le tour n'est donc plus refusé, aucune reprise n'est empilée, et la suite de la conversation part sur un autre historique : sa réponse enregistrée, écrite sous une reprise qui n'existe plus, n'est pas celle que le modèle aurait donnée.
>   Les tours et les griefs de cette prise ne sont donc comptés nulle part ci-dessous.

**Couverture.** Les deux jeux portent les mêmes 11 scénarios — 30 prises contre 34. La comparaison est complète.

Les valeurs comparées sont, par scénario, la **moyenne sur ses prises**, sommée
sur les scénarios : ce qu'une passe complète produit en moyenne. Un total comparerait
des tailles d'échantillon.

> ⚠️ **Comment lire la colonne « Verdict ».** La dispersion est l'étendue `max - min`
> des prises de **v1-base**, scénario par scénario, sommée. C'est de combien le total
> aurait pu bouger par le seul tirage — la température n'est pas fixée, et une
> cassette est un tirage, pas une espérance.
>
> **Ce n'est ni un écart-type ni un test.** C'est une borne délibérément généreuse,
> estimée sur trois prises : elle déclare « au-delà » moins souvent qu'un test
> statistique, ce qui est le sens dans lequel ce dépôt préfère se tromper.
>
> ⚠️ **Un scénario vu trois fois à la même valeur ne compte pas zéro.** « Stable par
> construction » et « calme par chance » ne se distinguent pas à trois tirages : trois
> tirages identiques bornent l'étendue par en dessous, ils ne la mesurent pas. Chaque
> scénario contribue donc au moins **1 pas**. Sans ce plancher, un
> scénario jamais vu bouger rendrait n'importe quel écart significatif.
>
> ⚠️ **Dispersion inconnue, comptée pour zéro**, sur : `categorie_efface_budget`. Un seul tirage n'a pas d'étendue. Le verdict y est donc **trop généreux**.

## Les mesures qui bougent

| Mesure | v1-base | v2 | Écart | Dispersion | Verdict | Sens cherché |
|---|---|---|---|---|---|---|
| Rejets du validateur | 2.67 | 1.00 | -1.67 | ± 14.00 | dans le bruit | baisse |
| Tours repliés | 0.33 | 0.00 | -0.33 | ± 11.00 | dans le bruit | baisse |
| Chiffres sur les tours de domaine | 3.67 | 7.67 | +4.00 | ± 19.00 | dans le bruit | stable |
| Markdown non rendu par le front | 51.67 | 0.00 | -51.67 | ± 42.00 | au-delà | baisse |
| Itérations | 60.00 | 56.50 | -3.50 | ± 14.00 | dans le bruit | stable |
| Tours avant la première valeur (nº3) | 14.00 | 12.67 | -1.33 | ± 9.00 | dans le bruit | stable |

⚠️ **`Itérations` ne se compare pas d'une orchestration à l'autre.** Chez une machine à états,
c'est une **constante** décidée par le graphe, pas un résultat : sa variance nulle est une
propriété connue d'avance, et elle se lirait comme une stabilité gagnée si personne ne
l'écrivait. Posée au jalon 0 de l'étape 15, **avant** la campagne — pas quand le chiffre sortira.

## Le coût d'enregistrement

| Mesure | v1-base | v2 | Écart |
|---|---|---|---|
| Appels au modèle par tour client (nº7) | non disponible — 27 prise(s) sur 30 sans `usage` | 179 appel(s) sur 77 tour(s) — 2.32 appel/tour | non calculable — voir les deux cellules |
| Jetons d'entrée facturés (nº7) | non disponible — 27 prise(s) sur 30 sans `usage` | 342 154 facturés (332 410 hors cache + 9 744 de cache écrit) ; 1 734 432 lus du cache, à un autre tarif | non calculable — voir les deux cellules |
| Jetons de sortie (nº7) | non disponible — 27 prise(s) sur 30 sans `usage` | 42 679 jetons | non calculable — voir les deux cellules |

⚠️ **La mesure nº7 ne vient pas du rejeu.** Ce sont les seules lignes de ce fichier qui soient lues
dans l'en-tête des cassettes plutôt que recalculées : elles sont **figées à l'enregistrement** et ne
bougeront pas quand le moteur, le scoring ou le validateur changeront. Les autres chiffres, si.

⚠️ **Les appels et les jetons peuvent aller en sens contraire, et c'est arrivé.** La campagne
de l'étape 15 a mesuré une orchestration qui fait **moins d'appels par tour** que l'autre et qui
paie **près du double** en entrée facturée : deux appels par tour, mais chacun renvoie une
conversation qui grossit plus vite. Publier le compte d'appels seul dirait donc l'inverse de
la vérité, et c'est pourquoi les deux moitiés de la mesure nº7 sont écrites ensemble.
Les deux campagnes de l'étape 15 sont chiffrées côte à côte dans leur comparaison.

⚠️ **Cette ligne ne porte pas de verdict**, contrairement à toutes celles du tableau
précédent. La dispersion qui les départage est celle des prises d'un rejeu ; ce coût-ci
a été payé une fois, à l'enregistrement, et n'en a aucune. L'écart lui-même n'est pas calculé ici.

⚠️ **Elle décrit chaque jeu entier**, et non l'intersection sur laquelle portent les
tableaux ci-dessus : le coût se lit dans les en-têtes de cassettes, qui ne se réduisent
pas aux scénarios communs.

## Les critères, des deux côtés

| Critère | v1-base | v2 |
|---|---|---|
| nº1 — griefs livrés | 0 | 0 |
| nº2 — violations budget | 0 | 0 |
| nº3 — tours avant valeur (médiane) | 2.0 | 1.0 |
| nº4 — attendu en top 3 | 12/12 | 12/12 |
| nº6 — zéro résultat traité | 11/11 | 11/11 |
| Prises sans aucune valeur livrée | 7/30 | 9/34 |

⚠️ **La métrique nº3 est un garde-fou, pas une cible.** Elle compte les tours client
avant la première valeur : son minimum atteignable est **1**, et il est déjà atteint.
Ce qu'on surveille ici est qu'elle ne **monte** pas — un modèle rendu plus prudent
avec les chiffres sonde davantage et montre plus tard.

⚠️ **Elle porte sa dispersion comme les cinq autres mesures**, dans le tableau
ci-dessus. Publier une baisse de nº3 sans son étendue, après avoir appliqué
« au-delà / dans le bruit » partout ailleurs, serait un double standard sur la seule
métrique qui va dans le bon sens — c'est ce qu'un relecteur verrait en premier, et
il aurait raison.

## Les codes de grief, des deux côtés

| Code de grief | v1-base /passe | v2 /passe | Écart | Bruts |
|---|---|---|---|---|
| `montant_non_fourni` | 2.67 | 0.33 | -2.33 | 8 → 1 |
| `prix_etranger_au_produit` | 0.00 | 0.33 | +0.33 | 0 → 1 |
| `valeur_non_fournie` | 0.00 | 0.33 | +0.33 | 0 → 1 |

⚠️ **Un code qui cesse de tirer n'est pas en soi une bonne nouvelle.** Si la forme
correspondante a disparu des appendices A des deux rapports, c'est le prompt ; si le
code cesse de tirer sans que rien n'ait changé dans la prose, c'est un trou. Les deux
se lisent en ouvrant les rapports, pas en lisant ce tableau.
