# Comparaison v2 → machine.v1

**Ce que cette comparaison cherche à savoir.** l'orchestration seule : agent avec outils contre machine à états, à catalogue, moteur, couche outils et validateur identiques

> ⚠️ **Ce que ces chiffres ne disent pas d'eux-mêmes.**
>
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
> - **Sept prédictions posées le 3 septembre 2026, avant la campagne de la machine à états.**
>   ⚠️ **Trois d'entre elles ont été révisées — par le tir d'essai du jalon 4, jamais par la
>   campagne.** Une prédiction corrigée avant la mesure est honnête ; corrigée après, elle ne
>   vaut rien. Les versions antérieures sont citées avec leur correction.
>
>   **1 — Le coût ne va pas dans le même sens selon qu'on compte les appels ou les jetons.**
>   La machine a un plancher mécanique de 2,00 appel par tour ; l'agent est à 2,36 sur v2.
>   Prédiction : machine dans **[2,00 ; 2,20]**, donc **moins d'appels**. Et **en même temps**
>   une entrée facturée **supérieure, entre 1,3 et 2,0 fois** — deux appels par tour sur une
>   conversation qui grossit plus vite, trois paires `tool_use`/`tool_result` par tour.
>   *Version antérieure, fausse, corrigée au jalon 4* : « deux préfixes de cache distincts ».
>   Il n'y en a qu'un, et il est **plus petit** que celui de l'agent — un test l'assert.
>
>   **2 — Critère nº4 (attendu en top 3) : égal, ou légèrement inférieur, et l'écart ne vient
>   pas du moteur.** Le moteur, le scoring et le catalogue sont les mêmes. Tout écart trace
>   vers l'**extraction**, jamais vers le matching.
>   *Révisée après le tir d'essai* : disait « identique ». `budget_serre.3` a montré une extraction
>   manquée, donc une recherche sur un état incomplet. Le mécanisme existe ; sa fréquence est
>   inconnue, et c'est ce que la campagne mesure.
>
>   **3 — Taux de rejet du validateur : égal ou supérieur chez la machine.** Deux mécanismes
>   le poussent vers le haut : la garde de contexte met **plus** de chiffres sous les yeux du
>   modèle, et une extraction manquée fait rédiger sur des produits hors sujet.
>   *Révisée, et elle disait l'inverse* : une baisse était prédite, la rédaction ne voyant que ce
>   que le moteur vient de rendre. Le tir d'essai a montré les deux forces contraires, et un
>   refus dès le premier échantillon.
>
>   **4 — Critère nº6 (zéro résultat) : la machine tient.** C'est une branche codée, pas une
>   conduite apprise.
>
>   **5 — Critère nº3 (délai avant première valeur) : égal, médiane à 1,0 tour.** Le code force
>   l'ordre que l'agent suivait déjà spontanément.
>
>   **6 — Là où la machine perd, et c'est là que le verdict doit chercher** : `comparaison`
>   (« entre les deux premiers » — aucun état ne retient ce qui a été montré),
>   `changement_davis`, `question_de_domaine` (18 tours sur 81), et **tout tour dont les critères
>   sont formulés d'une façon que l'extraction en un coup manque**. Ce dernier est **nouveau** :
>   il vient du tir d'essai, pas d'une intuition.
>
>   **7 — Le résultat d'ensemble le plus probable** : aucun écart au-delà de la dispersion sur
>   les six critères, **sauf le coût**. C'est un verdict **valide**, accepté d'avance, et il ne
>   clôt pas l'étape — les mesures nº7 et nº8 la closent.

**Couverture.** Les deux jeux portent les mêmes 11 scénarios — 35 prises contre 36. La comparaison est complète.

Les valeurs comparées sont, par scénario, la **moyenne sur ses prises**, sommée
sur les scénarios : ce qu'une passe complète produit en moyenne. Un total comparerait
des tailles d'échantillon.

> ⚠️ **Comment lire la colonne « Verdict ».** La dispersion est l'étendue `max - min`
> des prises de **v2**, scénario par scénario, sommée. C'est de combien le total
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

## Les mesures qui bougent

| Mesure | v2 | machine.v1 | Écart | Dispersion | Verdict | Sens cherché |
|---|---|---|---|---|---|---|
| Rejets du validateur | 1.33 | 17.00 | +15.67 | ± 11.00 | au-delà | baisse |
| Tours repliés | 0.00 | 2.67 | +2.67 | ± 11.00 | dans le bruit | baisse |
| Chiffres sur les tours de domaine | 7.67 | 11.50 | +3.83 | ± 16.00 | dans le bruit | stable |
| Markdown non rendu par le front | 0.00 | 4.00 | +4.00 | ± 11.00 | dans le bruit | baisse |
| Itérations | 57.17 | 52.67 | -4.50 | ± 13.00 | dans le bruit | stable |
| Tours avant la première valeur (nº3) | 12.67 | 13.50 | +0.83 | ± 8.00 | dans le bruit | stable |

⚠️ **`Itérations` ne se compare pas d'une orchestration à l'autre.** Chez une machine à états,
c'est une **constante** décidée par le graphe, pas un résultat : sa variance nulle est une
propriété connue d'avance, et elle se lirait comme une stabilité gagnée si personne ne
l'écrivait. Posée au jalon 0 de l'étape 15, **avant** la campagne — pas quand le chiffre sortira.

## Le coût d'enregistrement

| Mesure | v2 | machine.v1 | Écart |
|---|---|---|---|
| Appels au modèle par tour client (nº7) | 185 appel(s) sur 79 tour(s) — 2.34 appel/tour | 176 appel(s) sur 81 tour(s) — 2.17 appel/tour | -0.17 appel/tour |
| Jetons d'entrée facturés (nº7) | 349 903 facturés (340 159 hors cache + 9 744 de cache écrit) ; 1 792 896 lus du cache, à un autre tarif | 663 347 facturés (657 010 hors cache + 6 337 de cache écrit) ; 1 108 975 lus du cache, à un autre tarif | +313 444 jetons — facteur 1,90 |
| Jetons de sortie (nº7) | 44 743 jetons | 65 958 jetons | +21 215 jetons — facteur 1,47 |

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
a été payé une fois, à l'enregistrement, et n'en a aucune.

⚠️ **Elle décrit chaque jeu entier**, et non l'intersection sur laquelle portent les
tableaux ci-dessus : le coût se lit dans les en-têtes de cassettes, qui ne se réduisent
pas aux scénarios communs.

## Les critères, des deux côtés

| Critère | v2 | machine.v1 |
|---|---|---|
| nº1 — griefs livrés | 0 | 0 |
| nº2 — violations budget | 0 | 0 |
| nº3 — tours avant valeur (médiane) | 1.0 | 1.0 |
| nº4 — attendu en top 3 | 12/12 | 11/12 |
| nº6 — zéro résultat traité | 12/12 | 14/14 |
| Prises sans aucune valeur livrée | 10/35 | 7/36 |

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

| Code de grief | v2 /passe | machine.v1 /passe | Écart | Bruts |
|---|---|---|---|---|
| `ecart_non_dit` | 0.00 | 8.00 | +8.00 | 0 → 24 |
| `montant_non_fourni` | 0.67 | 6.33 | +5.67 | 2 → 19 |
| `prix_etranger_au_produit` | 0.33 | 0.00 | -0.33 | 1 → 0 |
| `valeur_non_fournie` | 0.33 | 2.67 | +2.33 | 1 → 8 |

⚠️ **Un code qui cesse de tirer n'est pas en soi une bonne nouvelle.** Si la forme
correspondante a disparu des appendices A des deux rapports, c'est le prompt ; si le
code cesse de tirer sans que rien n'ait changé dans la prose, c'est un trou. Les deux
se lisent en ouvrant les rapports, pas en lisant ce tableau.
