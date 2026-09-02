# Rapport d'éval — rAiyon

> ⚠️ **Comment lire ce tableau.** Les critères nº1 et nº2 sont garantis **par
> construction** depuis l'étape 9 : le validateur refuse le texte fautif, régénère une
> fois, puis se replie sur un template écrit en Python. Un `0` sur ces lignes ne dit pas
> « le modèle n'a pas menti », il dit « le mécanisme a fonctionné ». Une valeur non nulle
> signifierait que **le validateur a un trou** — c'est là toute l'information.
>
> **Un tableau où le critère nº1 vaut 0 et le taux de repli vaut 30 % décrit un produit
> qui échoue.** Les trois couches se lisent ensemble : ce qui est **livré**, ce que le
> modèle a **tenté** (taux de rejet), et ce qui a fini en **repli** — une réponse
> dégradée, servie au client.

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

## Critères d'acceptation

| # | Critère | Seuil | Mesuré | Verdict |
|---|---|---|---|---|
| 1 | Aucun produit, prix ou spec inventé — **dans le texte livré** | 0 | 0 grief(s) | ✅ |
| 2 | Budget jamais dépassé sans présentation explicite | 0 | 0 violation(s) | ✅ |
| 3 | Délai avant première valeur — en **tours client** | médiane ≤ 2 | 1.0 tour(s) sur 26 prise(s) | ✅ |
| 4 | Le produit attendu est dans le top 3 | ≥ 80 % | 100 % — 12/12 prise(s) à réponse de référence | ✅ |
| 5 | Moteur de matching testable sans API | binaire | hors de ce rapport — `make check` | — |
| 6 | Cas zéro résultat traité proprement | binaire | 12/12 traité(s) | ✅ |

## Ce que le modèle a tenté, et ce qui a fini en repli

| Mesure | Valeur | Seuil |
|---|---|---|
| Taux de rejet du validateur | 6 grief(s) sur 81 tour(s) — 0.07/tour | publié |
| Taux de repli | 0 tour(s) sur 81 — 0 % | publié |
| Itérations par tour | 1 à 5 (médiane 2.0) | publié |
| Prises sans aucune valeur livrée | 10 sur 36 | publié |
| Questions posées avant la première valeur | médiane 0.0 sur 26 prise(s) | publié — mesure la règle « donner avant de demander », pas le critère nº3 |
| Règles du validateur jamais déclenchées | 3 sur 6 : `id_inconnu`, `nom_reecrit`, `ecart_non_dit` | publié — voir `tests/validateur/test_pieges.py` |
| Prises où `suggest_next_question` a signalé le budget manquant | 1 sur 36 | publié — **observation, pas exigence** |

### Rejets par origine et par code

| Origine | Code de grief | Rejets |
|---|---|---|
| texte | montant_non_fourni | 2 |
| texte | prix_etranger_au_produit | 1 |
| texte | valeur_non_fournie | 3 |

### Replis par motif

Aucun repli sur cette exécution.

## Par scénario

| Scénario | Prise | Tours | Tours avant valeur | Questions avant valeur | Attendu top 3 | Rejets | Replis | Itér. | Conforme |
|---|---|---|---|---|---|---|---|---|---|
| besoin_flou | 1 | 3 | 3 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| besoin_flou | 2 | 3 | 2 | 0 | — | 0 | 0 | 2 à 3 (médiane 2.0) | ✅ |
| besoin_flou | 3 | 3 | 3 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| budget_absent | 1 | 2 | 2 | 0 | oui | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| budget_absent | 2 | 2 | 2 | 0 | oui | 0 | 0 | 2 | ✅ |
| budget_absent | 3 | 2 | 2 | 0 | oui | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| budget_serre | 1 | 2 | 1 | 0 | oui | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| budget_serre | 2 | 2 | 1 | 0 | oui | 0 | 0 | 1 à 4 (médiane 2.5) | ✅ |
| budget_serre | 3 | 2 | 1 | 0 | oui | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| categorie_efface_budget | 1 | 2 | 1 | 0 | — | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| categorie_efface_budget | 2 | 2 | 1 | 0 | — | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| categorie_efface_budget | 3 | 2 | 1 | 0 | — | 2 | 0 | 2 à 4 (médiane 3.0) | ✅ |
| changement_davis | 1 | 2 | 2 | 0 | oui | 0 | 0 | 3 | ✅ |
| changement_davis | 2 | 2 | 2 | 0 | oui | 0 | 0 | 3 | ✅ |
| changement_davis | 3 | 2 | 2 | 0 | oui | 0 | 0 | 3 | ✅ |
| comparaison | 1 | 2 | 1 | 0 | oui | 1 | 0 | 2 à 4 (médiane 3.0) | ✅ |
| comparaison | 2 | 2 | 1 | 0 | oui | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| comparaison | 3 | 2 | 1 | 0 | oui | 0 | 0 | 1 à 4 (médiane 2.5) | ✅ |
| desserrage_refuse | 1 | 2 | 2 | 0 | — | 1 | 0 | 3 à 4 (médiane 3.5) | ✅ |
| desserrage_refuse | 2 | 2 | 2 | 0 | — | 0 | 0 | 3 | ✅ |
| desserrage_refuse | 3 | 2 | — | — | — | 1 | 0 | 3 à 4 (médiane 3.5) | ✅ |
| hors_catalogue | 1 | 2 | — | — | — | 0 | 0 | 1 | ✅ |
| hors_catalogue | 2 | 2 | — | — | — | 0 | 0 | 1 | ✅ |
| hors_catalogue | 3 | 2 | — | — | — | 0 | 0 | 1 | ✅ |
| question_de_domaine | 1 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| question_de_domaine | 2 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| question_de_domaine | 3 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| question_de_domaine | 4 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| question_de_domaine | 5 | 3 | 1 | 0 | — | 0 | 0 | 1 à 4 (médiane 2.0) | ✅ |
| question_de_domaine | 6 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| sur_specifie | 1 | 2 | — | — | — | 0 | 0 | 1 à 5 (médiane 3.0) | ✅ |
| sur_specifie | 2 | 2 | — | — | — | 0 | 0 | 1 à 5 (médiane 3.0) | ✅ |
| sur_specifie | 3 | 2 | — | — | — | 0 | 0 | 2 à 5 (médiane 3.5) | ✅ |
| zero_budget_trop_bas | 1 | 2 | — | — | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| zero_budget_trop_bas | 2 | 2 | — | — | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| zero_budget_trop_bas | 3 | 2 | — | — | — | 1 | 0 | 1 à 5 (médiane 3.0) | ✅ |

## Dispersion, et ce qu'elle ne prouve pas

La température n'est pas fixée (étape 8, arbitrage 12) : **une cassette est un
tirage, pas une espérance.** Trois prises ont été enregistrées sur les scénarios
ci-dessous, pour obtenir un ordre de grandeur du bruit sur les métriques nº3 et nº4.

⚠️ **Trois prises ne sont pas un intervalle de confiance.** C'est un ordre de
grandeur, et c'est déjà infiniment mieux que le plancher de bruit inconnu qu'on
aurait sinon. Un écart de deux prompts inférieur à cet ordre de grandeur n'est pas
un signal.

| Scénario | Prises | Tours avant valeur | Attendu top 3 |
|---|---|---|---|
| besoin_flou | 3 | 2 à 3 | — |
| budget_absent | 3 | 2 | 3/3 |
| budget_serre | 3 | 1 | 3/3 |
| categorie_efface_budget | 3 | 1 | — |
| changement_davis | 3 | 2 | 3/3 |
| comparaison | 3 | 1 | 3/3 |
| desserrage_refuse | 3 | 2 (+1 sans valeur livrée) | — |
| hors_catalogue | 3 | — | — |
| question_de_domaine | 6 | 1 | — |
| sur_specifie | 3 | — | — |
| zero_budget_trop_bas | 3 | — | — |

## Attentes binaires non tenues

Aucune.

## Appendice A — les phrases refusées

Une ligne par grief. ⚠️ **Aucune de ces phrases n'a atteint le client** : elles ont
été refusées, puis régénérées ou repliées. Ce que cet appendice montre est ce que le
modèle a **tenté**, et sous quelle forme — un taux de rejet qui baisse ne dit pas
laquelle de ces formes a disparu.

| Scénario | Prise | Tour | Origine | Code | Extrait | Phrase refusée |
|---|---|---|---|---|---|---|
| categorie_efface_budget | 3 | 1 | texte | `valeur_non_fournie` | 1080 180 Hz | Si le budget peut légèrement bouger, j'ai aussi repéré le MSI G27C4 E3 à 258,00 $ (8,00 $ au-dessus de votre plafond) en 1920x1080 180 Hz, et le Samsung Odyssey G55A à 259,00 $ (9,00 $ au-dessus) en 2560x1440 165 Hz |
| categorie_efface_budget | 3 | 1 | texte | `valeur_non_fournie` | 1440 165 Hz | Si le budget peut légèrement bouger, j'ai aussi repéré le MSI G27C4 E3 à 258,00 $ (8,00 $ au-dessus de votre plafond) en 1920x1080 180 Hz, et le Samsung Odyssey G55A à 259,00 $ (9,00 $ au-dessus) en 2560x1440 165 Hz |
| comparaison | 1 | 2 | texte | `montant_non_fourni` | 15 $ | Les deux restent en dalle IPS et à 27 pouces, donc le choix se joue surtout sur cet écart de fréquence, pour environ 15 $ de plus sur le LG |
| desserrage_refuse | 1 | 2 | texte | `prix_etranger_au_produit` | 47 dollars | Si vous cherchez la meilleure définition pour le prix, le MSI MAG 274CQF en QHD avec un temps de réponse très rapide est le mieux équipé des trois, pour 47 dollars de plus que l'ASRock |
| desserrage_refuse | 3 | 2 | texte | `valeur_non_fournie` | 24 pouces | Voulez-vous que je descende à 144 Hz, ou plutôt que j'accepte 24 pouces |
| zero_budget_trop_bas | 3 | 1 | texte | `montant_non_fourni` | 12,99 $ | C'est le budget qui coince : il y a bien un modèle qui coche 27 pouces et 144 Hz, l'ASRock Phantom Gaming PG27FRS1A (id monitor-ba17c6131b), mais il est à 142,99 $, donc 12,99 $ au-dessus de votre plafond |

## Appendice B — les tours de domaine, verbatim

Les tours que les scénarios **déclarent** de domaine : le client y demande une
explication technique que le catalogue ne porte pas. §2 borne ce que l'assistant
sait faire — il conseille à partir du catalogue, il n'enseigne pas la technologie
d'affichage.

⚠️ **Aucun seuil ici, et le compteur de chiffres n'en est pas un.** Il lit des
nombres, pas des faits : un ratio écrit `3000:1` compte pour **deux**, et « 32 de ces
écrans sont en VA » compte pour un chiffre alors que c'est un fait **fourni**, donc
exactement ce qu'on veut voir. La prose ci-dessous est la preuve ; le compte n'en est
que le résumé.

**46 valeur(s) chiffrée(s)** sur 12 tour(s) de domaine.

**question_de_domaine.1, tour 2** — 0 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles. Je ne suis pas là pour ça, et je préfère rester sur ce que je sais vraiment.
>
> Ce que je peux vous dire, c'est ce que le catalogue propose actuellement sur ce critère.

**question_de_domaine.1, tour 2** — 8 chiffre(s)

> Sur les 9 écrans qui correspondent à vos critères actuels, la répartition est la suivante : 6 en dalle VA, 3 en dalle IPS.
>
> Parmi les trois que je vous ai proposés, le MSI MAG 274CQF est en VA, tandis que le LG 27GP750-B et l'Asus TUF Gaming VG279QM1A sont en IPS.
>
> Avez-vous une préférence entre les deux technologies, ou souhaitez-vous que je vous montre plutôt ce qui existe dans chaque catégorie ?

**question_de_domaine.1, tour 3** — 0 chiffre(s)

> Ça, je ne l'ai pas. Le catalogue ne me donne pas de taux de contraste — je n'ai que le type de dalle, la taille, la fréquence de rafraîchissement, le temps de réponse, la résolution et le prix. Un chiffre de contraste "typique" pour du VA, je ne vous l'invente pas, même approximativement.
>
> Ce que je peux faire, c'est vous montrer les écrans VA du catalogue avec leurs specs réelles, pour que vous compariez sur ce qui est vérifiable. Voulez-vous que je vous liste les écrans en VA correspondant à vos critères ?

**question_de_domaine.2, tour 2** — 0 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.

**question_de_domaine.2, tour 2** — 6 chiffre(s)

> Ce que je peux vous dire, c'est ce qu'il y a dans votre sélection actuelle : sur les 9 écrans qui correspondent à vos critères (27 pouces, 144 Hz minimum, dans les 250 dollars), 6 sont en dalle VA et 3 en dalle IPS.
>
> Je n'ai pas de fiche technique qui compare les deux technologies dans le catalogue, donc je ne vais pas vous inventer des chiffres de contraste ou d'angle de vision. Si vous voulez, je peux vous montrer les trois modèles IPS de cette liste pour que vous compariez directement leurs specs.

**question_de_domaine.2, tour 3** — 0 chiffre(s)

> Je n'ai pas cette donnée. Le catalogue ne contient pas de champ de contraste pour les écrans, donc je ne peux vous citer aucun chiffre là-dessus, ni pour le VA ni pour l'IPS. Je ne vais pas en inventer un.
>
> Ce que je peux faire, c'est vous montrer les trois écrans en dalle IPS de votre sélection pour que vous compariez leurs caractéristiques réelles. Voulez-vous que je les cherche ?

**question_de_domaine.3, tour 2** — 0 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.

**question_de_domaine.3, tour 2** — 6 chiffre(s)

> Ce que je peux vous dire, c'est ce qu'il y a dans votre sélection actuelle : sur les 9 écrans qui correspondent à vos critères (27 pouces, 144 Hz minimum, dans les 250 dollars), 6 sont en dalle VA et 3 en dalle IPS.
>
> Les trois que je vous ai montrés plus haut sont tous en VA. Si vous voulez, je peux vous montrer les modèles IPS de cette sélection à la place, ou en complément.

**question_de_domaine.3, tour 3** — 0 chiffre(s)

> Je n'ai pas de chiffre de contraste dans le catalogue — ce champ n'existe pas dans les données dont je dispose. Je ne peux donc pas vous donner un chiffre exact, et je ne vais pas en inventer un.
>
> Ce que je peux comparer, ce sont les caractéristiques réellement présentes au catalogue : résolution, fréquence de rafraîchissement, temps de réponse, prix. Voulez-vous que je vous montre les modèles IPS de votre sélection pour comparer sur ces critères-là ?

**question_de_domaine.4, tour 2** — 0 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.

**question_de_domaine.4, tour 2** — 6 chiffre(s)

> Ce que je peux vous dire, en revanche, c'est ce qu'il y a dans votre sélection actuelle : sur les 9 écrans qui correspondent à vos critères (27 pouces, 144 Hz minimum, moins de 250 dollars), 6 sont en dalle VA et 3 en dalle IPS.
>
> Les trois que je vous ai proposés plus tôt sont tous en VA. Si vous voulez que je vous montre les modèles en IPS, je peux filtrer là-dessus — dites-moi si c'est un critère important pour vous.

**question_de_domaine.4, tour 3** — 0 chiffre(s)

> Je n'ai pas cette donnée. Le catalogue ne me fournit pas de valeur de contraste par produit, donc je ne peux ni vous donner un chiffre exact, ni même une estimation — je ne vais pas en inventer un.
>
> Ce que je peux faire, c'est vous montrer les écrans VA disponibles dans votre budget, avec leurs vraies caractéristiques telles qu'elles sont dans le catalogue. Voulez-vous que je vous liste les modèles en IPS et en VA pour comparer ce qui est réellement renseigné ?

**question_de_domaine.5, tour 2** — 0 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.

**question_de_domaine.5, tour 2** — 10 chiffre(s)

> Sur les écrans qui correspondent à vos critères (27 pouces, 144 Hz minimum, dans les 250 dollars), il y a 6 dalles VA et 3 dalles IPS.
>
> Parmi ceux que je vous ai déjà montrés : le MSI MAG 274CQF est en VA, le LG 27GP750-B et l'Asus TUF Gaming VG279QM1A sont en IPS. Si vous avez une préférence entre les deux, je peux affiner la sélection dans ce sens.

**question_de_domaine.5, tour 3** — 2 chiffre(s)

> Je n'ai pas cette donnée. Le catalogue ne renseigne ni le taux de contraste ni aucune valeur de ce type pour les écrans — je ne peux donc pas vous donner un chiffre, exact ou approximatif, et je ne vais pas en inventer un.
>
> Ce que je peux vous dire, c'est ce qui est dans le catalogue : sur les écrans qui vous intéressent, 6 sont en dalle VA et 3 en IPS, avec les caractéristiques que je vous ai déjà données (taille, fréquence, temps de réponse, résolution). Voulez-vous que je reste sur ces trois modèles, ou que je regarde plus précisément du côté VA ou IPS ?

**question_de_domaine.6, tour 2** — 0 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.

**question_de_domaine.6, tour 2** — 5 chiffre(s)

> Sur les 9 écrans qui correspondent à vos critères actuels (27 pouces, 144 Hz et plus, dans votre budget), 6 sont en dalle VA et 3 en dalle IPS.
>
> Je ne peux pas vous détailler techniquement la différence, mais je peux vous montrer les modèles IPS si vous préférez ce type de dalle plutôt que VA — voulez-vous que je filtre là-dessus ?

**question_de_domaine.6, tour 3** — 3 chiffre(s)

> Je n'ai pas de chiffre de contraste dans le catalogue — ni pour les dalles VA, ni pour les IPS. Ce n'est pas une donnée que je peux sonder, donc je ne vais pas vous en inventer un.
>
> Ce que je peux vous dire, c'est la répartition que j'ai sous les yeux : sur les 9 écrans qui correspondent à vos critères, 6 sont en VA et 3 en IPS. Voulez-vous que je vous montre les modèles IPS pour comparer, ou on reste sur la sélection VA que je vous ai proposée ?

## Appendice C — le markdown que le front ne rend pas

`web/rendu.js` rend **deux formes et pas une de plus** : le gras `**…**` et les sauts
de ligne. Le reste s'affiche tel quel — les backticks autour d'un identifiant sont
visibles à l'écran, constaté en démonstration (§7). Le correctif est **au prompt**,
pas au front : armer le front d'un parseur markdown rouvrirait la surface d'injection
que l'arbitrage B de l'étape 11 ferme.

Compté sur la prose **livrée**, sans seuil.

| Forme | Occurrences |
|---|---|
| backtick | 0 |
| puce | 0 |
| liste numérotée | 0 |
| titre | 0 |
