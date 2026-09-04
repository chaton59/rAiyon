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
> - **v2/zero_budget_trop_bas.3 est écartée de ce rapport** — divergence attendue au rejeu.
>   **Le défaut de l'étape 18** : `regle_ecart_au_budget` exigeait l'écart dans la phrase qui nomme le produit, pendant que `regle_montants` refusait ce même écart dans une phrase sans produit — `hors_budget.values()` n'était pas dans les montants admis. Le nom sur une ligne, « il dépasse de X $ » sur la suivante, et les deux règles devenaient **conjointement insatisfaisables**. La section 14 du prompt, qui demande un produit par ligne, mène droit à ce découpage. Ici le grief tombé est l'unique de la prise : un `montant_non_fourni` sur « 12,99 $ », qui est **l'écart au budget** de l'ASRock Phantom Gaming PG27FRS1A rendu par le moteur. Le message de grief disait « aucun outil n'a rendu ce montant » d'un chiffre que `search_products` avait rendu. Le tour n'est donc plus refusé, aucune reprise n'est empilée, et la suite de la conversation part sur un autre historique : sa réponse enregistrée, écrite sous une reprise qui n'existe plus, n'est pas celle que le modèle aurait donnée.
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
> - **3 prises sont écartées de ce rapport** — `machine.v1/besoin_flou.1`, `machine.v1/besoin_flou.2`, `machine.v1/besoin_flou.3` — divergence attendue au rejeu.
>   **La garde d'extraction de l'étape 21.** L'appel nº1 de ce tour a rendu un `record_criteria` posant une catégorie **sans aucun critère** : la machine relance désormais l'extraction une fois, ce qui insère un appel modèle et une consigne dans `messages`. L'empreinte de la requête suivante change, la cassette ne se rejoue plus. ⚠️ **La divergence est le comportement correct** — c'est l'arbitrage A de l'étape 12 : le modèle aurait reçu une conversation où on lui redemande de relire le message du client, et sa réponse enregistrée n'est pas celle qu'il aurait donnée. **Aucun critère n'était perdu ici** : au tour 2, le client dit « c'est surtout pour jouer, et j'ai environ 250 dollars ». L'usage n'énonce aucun champ du registre et le budget a sa propre colonne (§3.10) — l'extraction était juste, et la garde paie un appel pour le confirmer. C'est le prix assumé de son imprécision.
>   Les tours et les griefs de ces prises ne sont donc comptés nulle part ci-dessous.
> - **3 prises sont écartées de ce rapport** — `machine.v1/budget_absent.1`, `machine.v1/budget_absent.2`, `machine.v1/budget_absent.3` — divergence attendue au rejeu.
>   **La garde d'extraction de l'étape 21.** L'appel nº1 de ce tour a rendu un `record_criteria` posant une catégorie **sans aucun critère** : la machine relance désormais l'extraction une fois, ce qui insère un appel modèle et une consigne dans `messages`. L'empreinte de la requête suivante change, la cassette ne se rejoue plus. ⚠️ **La divergence est le comportement correct** — c'est l'arbitrage A de l'étape 12 : le modèle aurait reçu une conversation où on lui redemande de relire le message du client, et sa réponse enregistrée n'est pas celle qu'il aurait donnée. **Aucun critère n'était perdu ici** : au tour 2, le client donne son plafond et rien d'autre — « mon plafond est de 145 dollars ». Un budget n'est pas un critère du registre, l'extraction était juste, et la garde paie un appel pour le confirmer.
>   Les tours et les griefs de ces prises ne sont donc comptés nulle part ci-dessous.
> - **2 prises sont écartées de ce rapport** — `machine.v1/categorie_efface_budget.1`, `machine.v1/categorie_efface_budget.3` — divergence attendue au rejeu.
>   **La garde d'extraction de l'étape 21.** L'appel nº1 de ce tour a rendu un `record_criteria` posant une catégorie **sans aucun critère** : la machine relance désormais l'extraction une fois, ce qui insère un appel modèle et une consigne dans `messages`. L'empreinte de la requête suivante change, la cassette ne se rejoue plus. ⚠️ **La divergence est le comportement correct** — c'est l'arbitrage A de l'étape 12 : le modèle aurait reçu une conversation où on lui redemande de relire le message du client, et sa réponse enregistrée n'est pas celle qu'il aurait donnée. **Aucun critère n'était perdu ici** : au tour 2, le client change de catégorie et rien de plus — « en fait je vais commencer par le processeur ». Une catégorie neuve sans critère est le chemin nominal de ce scénario, et la garde paie un appel pour le confirmer.
>   Les tours et les griefs de ces prises ne sont donc comptés nulle part ci-dessous.
> - **6 prises sont écartées de ce rapport** — `machine.v1/changement_davis.1`, `machine.v1/changement_davis.2`, `machine.v1/changement_davis.3`, `machine.v1/desserrage_refuse.1`, `machine.v1/desserrage_refuse.2`, `machine.v1/desserrage_refuse.3` — divergence attendue au rejeu.
>   **Le défaut de l'étape 18** : `regle_ecart_au_budget` exigeait l'écart dans la phrase qui nomme le produit, pendant que `regle_montants` refusait ce même écart dans une phrase sans produit — `hors_budget.values()` n'était pas dans les montants admis. Le nom sur une ligne, « il dépasse de X $ » sur la suivante, et les deux règles devenaient **conjointement insatisfaisables**. La section 14 du prompt, qui demande un produit par ligne, mène droit à ce découpage. Cette prise de `machine.v1` en porte la forme complète et répétée : `ecart_non_dit` sur les lignes qui nomment le LG 27GP750-B et l'Asus TUF Gaming VG279QM1A, **et** `montant_non_fourni` sur « 26,99 $ » et « 29,00 $ » — qui sont exactement leurs écarts au budget de 200 $, écrits une ligne plus bas. Le tour n'est plus refusé, la reprise disparaît, l'empreinte du tour suivant change. ⚠️ **Ces prises portent 22 des 24 `ecart_non_dit` de la campagne de la machine** — l'unique écart au-delà de la dispersion de l'étape 15. En sortant du rejeu, elles sortent aussi de toute mesure : le rapport ne dit **pas** que ces 22 étaient des faux positifs, il dit qu'on ne peut plus les compter. `comparaison.1` portait les 2 autres et a tranché à l'étape 18 — elles ont disparu ; elle est sortie du rejeu à l'étape 21 à son tour, et c'est donc un verdict acquis, plus un verdict rejouable. Voir §5 étape 15, verdict suspendu, et §7.
>   Les tours et les griefs de ces prises ne sont donc comptés nulle part ci-dessous.
> - **machine.v1/comparaison.1 est écartée de ce rapport** — divergence attendue au rejeu.
>   **La garde d'extraction de l'étape 21.** L'appel nº1 de ce tour a rendu un `record_criteria` posant une catégorie **sans aucun critère** : la machine relance désormais l'extraction une fois, ce qui insère un appel modèle et une consigne dans `messages`. L'empreinte de la requête suivante change, la cassette ne se rejoue plus. ⚠️ **La divergence est le comportement correct** — c'est l'arbitrage A de l'étape 12 : le modèle aurait reçu une conversation où on lui redemande de relire le message du client, et sa réponse enregistrée n'est pas celle qu'il aurait donnée. 🔴 **Et ici un critère était bien perdu** — l'un des deux cas du recensement. Au tour 1, le client demande « 27 pouces au minimum, 144 Hz au moins, 250 dollars maximum, et plutôt une dalle IPS » ; l'extraction n'enregistre que la catégorie et le budget. Les deux autres prises du même scénario, elles, enregistrent les trois critères : le défaut est intermittent, et c'est ce que la garde vise. ⚠️ **Cette prise était la dernière de `changement_davis`/`desserrage_refuse`/`comparaison` à rester rejouable** après l'étape 18 — c'est elle qui avait tranché pour 2 des 24 `ecart_non_dit`. Le verdict reste acquis ; il n'est plus reproductible par un rejeu.
>   Les tours et les griefs de cette prise ne sont donc comptés nulle part ci-dessous.
> - **machine.v1/sur_specifie.3 est écartée de ce rapport** — divergence attendue au rejeu.
>   **La garde d'extraction de l'étape 21.** L'appel nº1 de ce tour a rendu un `record_criteria` posant une catégorie **sans aucun critère** : la machine relance désormais l'extraction une fois, ce qui insère un appel modèle et une consigne dans `messages`. L'empreinte de la requête suivante change, la cassette ne se rejoue plus. ⚠️ **La divergence est le comportement correct** — c'est l'arbitrage A de l'étape 12 : le modèle aurait reçu une conversation où on lui redemande de relire le message du client, et sa réponse enregistrée n'est pas celle qu'il aurait donnée. 🔴 **Et ici un critère était bien perdu** — le second cas du recensement, et c'est le tirage que l'étape 20 a reproduit en vivant. Au tour 1, l'extraction pose `panel_type` en `bloquant`, la couche outils refuse (§3.4quater), et **l'appel étant atomique la taille, la fréquence et le budget partent avec** : la session entre au tour 2 sans aucun critère. Au tour 2, le client insiste — « le 500 Hz est vraiment ce qui compte pour moi » — et l'extraction n'enregistre que la catégorie et le budget de 400 $. La recherche part alors sur 115 candidats au lieu de 37, et les deux attentes non tenues de cette prise (`zero_resultat`, diagnostic `critere_trop_strict`) sont la conséquence de ce seul tour. ⚠️ **Elle sort du rejeu sans que la garde ait été mesurée** : que la relance aurait rattrapé les 500 Hz est plausible — les prises 1 et 2 les enregistrent — et n'est pas su.
>   Les tours et les griefs de cette prise ne sont donc comptés nulle part ci-dessous.

> ⚠️ **Comparaison sur les 7 scénarios communs.** Les deux jeux ne portent pas
> les mêmes scénarios. La comparaison est donc réduite à ceux présents des **deux**
> côtés — 22 prises de **v2** contre 20 de **machine.v1**.
>
> ⚠️ **Les prises ne sont pas appariées, et elles ne peuvent pas l'être** : un numéro
> de prise est un index, pas une identité. La température n'est pas fixée, et la
> prise 2 d'une campagne n'a aucun lien avec la prise 2 de l'autre. Les valeurs
> comparées sont donc, par scénario, la **moyenne sur ses prises**, sommée sur les
> scénarios : ce qu'une passe complète produit en moyenne.
>
> Scénarios écartés : `besoin_flou`, `budget_absent`, `changement_davis`, `desserrage_refuse`.
> Absents de **machine.v1** : `besoin_flou`, `budget_absent`, `changement_davis`, `desserrage_refuse`.
>
> ⚠️ **L'exclusion n'est pas neutre, et voici de combien** : les prises écartées
> portaient **2 des 3 rejets** de v2. La comparaison porte donc sur ses
> scénarios les plus **calmes**, où tout écart est mécaniquement plus petit. Ce qui
> est publié ici **sous-estime** vraisemblablement l'écart réel entre les deux
> campagnes ; ce n'est pas une borne inférieure démontrée, c'est une raison de ne
> pas lire un petit écart comme une absence d'effet.

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
| Rejets du validateur | 0.33 | 2.50 | +2.17 | ± 7.00 | dans le bruit | baisse |
| Tours repliés | 0.00 | 0.50 | +0.50 | ± 7.00 | dans le bruit | baisse |
| Chiffres sur les tours de domaine | 7.67 | 11.50 | +3.83 | ± 12.00 | dans le bruit | stable |
| Markdown non rendu par le front | 0.00 | 1.00 | +1.00 | ± 7.00 | dans le bruit | baisse |
| Itérations | 32.83 | 31.00 | -1.83 | ± 8.00 | dans le bruit | stable |
| Tours avant la première valeur (nº3) | 4.00 | 5.00 | +1.00 | ± 4.00 | dans le bruit | stable |

⚠️ **`Itérations` ne se compare pas d'une orchestration à l'autre.** Chez une machine à états,
c'est une **constante** décidée par le graphe, pas un résultat : sa variance nulle est une
propriété connue d'avance, et elle se lirait comme une stabilité gagnée si personne ne
l'écrivait. Posée au jalon 0 de l'étape 15, **avant** la campagne — pas quand le chiffre sortira.

## Le coût d'enregistrement

| Mesure | v2 | machine.v1 | Écart |
|---|---|---|---|
| Appels au modèle par tour client (nº7) | 179 appel(s) sur 77 tour(s) — 2.32 appel/tour | 94 appel(s) sur 46 tour(s) — 2.04 appel/tour | -0.28 appel/tour |
| Jetons d'entrée facturés (nº7) | 342 154 facturés (332 410 hors cache + 9 744 de cache écrit) ; 1 734 432 lus du cache, à un autre tarif | 362 702 facturés (356 365 hors cache + 6 337 de cache écrit) ; 589 341 lus du cache, à un autre tarif | +20 548 jetons — facteur 1,06 |
| Jetons de sortie (nº7) | 42 679 jetons | 31 005 jetons | -11 674 jetons — facteur 0,73 |

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
| nº4 — attendu en top 3 | 6/6 | 5/5 |
| nº6 — zéro résultat traité | 5/5 | 8/8 |
| Prises sans aucune valeur livrée | 8/22 | 7/20 |

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
| `montant_non_fourni` | 0.33 | 0.50 | +0.17 | 1 → 1 |
| `valeur_non_fournie` | 0.00 | 2.00 | +2.00 | 0 → 4 |

⚠️ **Un code qui cesse de tirer n'est pas en soi une bonne nouvelle.** Si la forme
correspondante a disparu des appendices A des deux rapports, c'est le prompt ; si le
code cesse de tirer sans que rien n'ait changé dans la prose, c'est un trou. Les deux
se lisent en ouvrant les rapports, pas en lisant ce tableau.
