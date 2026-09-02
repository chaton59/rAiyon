# Comparaison v1-etape12 → v1-partielle

**Ce que cette comparaison cherche à savoir.** une **borne supérieure** de la dérive du modèle entre les deux enregistrements — jamais la dérive elle-même. L'écart confond ce que le modèle a changé entre les deux dates et le bruit d'échantillonnage que §7 documente ; il majore le premier sans le mesurer.

> ⚠️ **Ce que ces chiffres ne disent pas d'eux-mêmes.**
>
> - **v1-etape12/desserrage_refuse.1 est écartée de ce rapport** — divergence attendue au rejeu.
>   le correctif de validateur de l'étape 13 (jalon 1, point D) fait tomber 2 des 4 griefs de ce tour. La reprise empilée avant la régénération porte donc 2 lignes au lieu de 4, l'empreinte de requête du tour régénéré change, et la prise 7 n'est plus reconstituable. Le modèle aurait reçu une autre reprise : sa réponse enregistrée n'est pas celle qu'il aurait donnée.
>   Les tours et les griefs de cette prise ne sont donc comptés nulle part ci-dessous.

> ⚠️ **Comparaison sur les 7 scénarios communs.** Les deux jeux ne portent pas
> les mêmes scénarios. La comparaison est donc réduite à ceux présents des **deux**
> côtés — 11 prises de **v1-etape12** contre 21 de **v1-partielle**.
>
> ⚠️ **Les prises ne sont pas appariées, et elles ne peuvent pas l'être** : un numéro
> de prise est un index, pas une identité. La température n'est pas fixée, et la
> prise 2 d'une campagne n'a aucun lien avec la prise 2 de l'autre. Les valeurs
> comparées sont donc, par scénario, la **moyenne sur ses prises**, sommée sur les
> scénarios : ce qu'une passe complète produit en moyenne.
>
> Scénarios écartés : `categorie_efface_budget`, `question_de_domaine`, `zero_budget_trop_bas`.
> Absents de **v1-partielle** : `categorie_efface_budget`, `question_de_domaine`, `zero_budget_trop_bas`.
>
> ⚠️ **L'exclusion n'est pas neutre, et voici de combien** : les prises écartées
> portaient **1 des 7 rejets** de v1-etape12. La comparaison porte donc sur ses
> scénarios les plus **calmes**, où tout écart est mécaniquement plus petit. Ce qui
> est publié ici **sous-estime** vraisemblablement l'écart réel entre les deux
> campagnes ; ce n'est pas une borne inférieure démontrée, c'est une raison de ne
> pas lire un petit écart comme une absence d'effet.

> ⚠️ **Comment lire la colonne « Verdict ».** La dispersion est l'étendue `max - min`
> des prises de **v1-etape12**, scénario par scénario, sommée. C'est de combien le total
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
> ⚠️ **Dispersion inconnue, comptée pour zéro**, sur : `budget_absent`, `changement_davis`, `comparaison`, `hors_catalogue`, `sur_specifie`. Un seul tirage n'a pas d'étendue. Le verdict y est donc **trop généreux**.

## Les mesures qui bougent

| Mesure | v1-etape12 | v1-partielle | Écart | Dispersion | Verdict | Sens cherché |
|---|---|---|---|---|---|---|
| Rejets du validateur | 3.33 | 2.67 | -0.67 | ± 4.00 | dans le bruit | baisse |
| Tours repliés | 1.00 | 0.33 | -0.67 | ± 0.00 | au-delà | baisse |
| Chiffres sur les tours de domaine | 0.00 | 0.00 | +0.00 | ± 0.00 | identique | stable |
| Markdown non rendu par le front | 36.67 | 28.33 | -8.33 | ± 28.00 | dans le bruit | baisse |
| Itérations | 37.33 | 40.00 | +2.67 | ± 3.00 | dans le bruit | stable |

## Les critères, des deux côtés

| Critère | v1-etape12 | v1-partielle |
|---|---|---|
| nº1 — griefs livrés | 0 | 0 |
| nº2 — violations budget | 0 | 0 |
| nº3 — tours avant valeur (médiane) | 2.0 | 2.0 |
| nº4 — attendu en top 3 | 6/6 | 12/12 |
| nº6 — zéro résultat traité | 2/2 | 6/6 |
| Prises sans aucune valeur livrée | 2/11 | 5/21 |

⚠️ **La métrique nº3 est un garde-fou, pas une cible.** Elle compte les tours client
avant la première valeur : son minimum atteignable est **1**, et il est déjà atteint.
Ce qu'on surveille ici est qu'elle ne **monte** pas — un modèle rendu plus prudent
avec les chiffres sonde davantage et montre plus tard.

## Les codes de grief, des deux côtés

| Code de grief | v1-etape12 /passe | v1-partielle /passe | Écart | Bruts |
|---|---|---|---|---|
| `montant_non_fourni` | 2.67 | 2.67 | +0.00 | 4 → 8 |
| `valeur_non_fournie` | 0.67 | 0.00 | -0.67 | 2 → 0 |

⚠️ **Un code qui cesse de tirer n'est pas en soi une bonne nouvelle.** Si la forme
correspondante a disparu des appendices A des deux rapports, c'est le prompt ; si le
code cesse de tirer sans que rien n'ait changé dans la prose, c'est un trou. Les deux
se lisent en ouvrant les rapports, pas en lisant ce tableau.
