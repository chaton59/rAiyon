# Comparaison v1-base → v2

**Ce que cette comparaison cherche à savoir.** l'effet des trois cibles de v2 — la rédaction chiffrée, le périmètre de domaine, le markdown que le front ne rend pas. ⚠️ La base et v2 ne datent pas du même jour : l'écart majore la dérive du modèle sans la mesurer.

> ⚠️ **Ce que ces chiffres ne disent pas d'eux-mêmes.**
>
> - **v1-etape12/desserrage_refuse.1 est écartée de ce rapport** — divergence attendue au rejeu.
>   le correctif de validateur de l'étape 13 (jalon 1, point D) fait tomber 2 des 4 griefs de ce tour. La reprise empilée avant la régénération porte donc 2 lignes au lieu de 4, l'empreinte de requête du tour régénéré change, et la prise 7 n'est plus reconstituable. Le modèle aurait reçu une autre reprise : sa réponse enregistrée n'est pas celle qu'il aurait donnée.
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

**Couverture.** Les deux jeux portent les mêmes 11 scénarios — 31 prises contre 36. La comparaison est complète.

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
> ⚠️ **Une dispersion nulle ne veut pas dire « stable ».** Elle veut dire qu'on n'a
> pas vu ce scénario bouger sur trois prises — « stable par construction » et « calme
> par chance » ne se distinguent pas à ce nombre de tirages.
>
> ⚠️ **Dispersion inconnue, comptée pour zéro**, sur : `categorie_efface_budget`. Un seul tirage n'a pas d'étendue. Le verdict y est donc **trop généreux**.

## Les mesures qui bougent

| Mesure | v1-base | v2 | Écart | Dispersion | Verdict | Sens cherché |
|---|---|---|---|---|---|---|
| Rejets du validateur | 3.00 | 2.00 | -1.00 | ± 7.00 | dans le bruit | baisse |
| Tours repliés | 0.33 | 0.00 | -0.33 | ± 1.00 | dans le bruit | baisse |
| Chiffres sur les tours de domaine | 3.67 | 7.67 | +4.00 | ± 9.00 | dans le bruit | stable |
| Markdown non rendu par le front | 51.00 | 0.00 | -51.00 | ± 40.00 | au-delà | baisse |
| Itérations | 60.33 | 57.50 | -2.83 | ± 8.00 | dans le bruit | stable |

## Les critères, des deux côtés

| Critère | v1-base | v2 |
|---|---|---|
| nº1 — griefs livrés | 0 | 0 |
| nº2 — violations budget | 0 | 0 |
| nº3 — tours avant valeur (médiane) | 2.0 | 1.0 |
| nº4 — attendu en top 3 | 12/12 | 12/12 |
| nº6 — zéro résultat traité | 12/12 | 12/12 |
| Prises sans aucune valeur livrée | 8/31 | 10/36 |

⚠️ **La métrique nº3 est un garde-fou, pas une cible.** Elle compte les tours client
avant la première valeur : son minimum atteignable est **1**, et il est déjà atteint.
Ce qu'on surveille ici est qu'elle ne **monte** pas — un modèle rendu plus prudent
avec les chiffres sonde davantage et montre plus tard.

## Les codes de grief, des deux côtés

| Code de grief | v1-base /passe | v2 /passe | Écart | Bruts |
|---|---|---|---|---|
| `ecart_non_dit` | 0.33 | 0.00 | -0.33 | 1 → 0 |
| `montant_non_fourni` | 2.67 | 0.67 | -2.00 | 8 → 2 |
| `prix_etranger_au_produit` | 0.00 | 0.33 | +0.33 | 0 → 1 |
| `valeur_non_fournie` | 0.00 | 1.00 | +1.00 | 0 → 3 |

⚠️ **Un code qui cesse de tirer n'est pas en soi une bonne nouvelle.** Si la forme
correspondante a disparu des appendices A des deux rapports, c'est le prompt ; si le
code cesse de tirer sans que rien n'ait changé dans la prose, c'est un trou. Les deux
se lisent en ouvrant les rapports, pas en lisant ce tableau.
