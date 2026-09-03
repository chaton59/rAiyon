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
> - **v1-etape12/desserrage_refuse.1 est écartée de ce rapport** — divergence attendue au rejeu.
>   le correctif de validateur de l'étape 13 (jalon 1, point D) fait tomber 2 des 4 griefs de ce tour. La reprise empilée avant la régénération porte donc 2 lignes au lieu de 4, l'empreinte de requête du tour régénéré change, et la prise 7 n'est plus reconstituable. Le modèle aurait reçu une autre reprise : sa réponse enregistrée n'est pas celle qu'il aurait donnée.
>   Les tours et les griefs de cette prise ne sont donc comptés nulle part ci-dessous.
> - **Ce jeu est composé de plusieurs enregistrements**, donc de plusieurs dates. Un scénario vient
>   d'une seule source — jamais de deux — pour que la dispersion de ses prises reste celle d'un
>   tirage et non celle d'un écart entre deux enregistrements.
>   `v1-desserrage` : `desserrage_refuse`
>   `v1-etape12` : `categorie_efface_budget`, `question_de_domaine`, `zero_budget_trop_bas`
>   `v1-partielle` : `besoin_flou`, `budget_absent`, `budget_serre`, `changement_davis`, `comparaison`, `hors_catalogue`, `sur_specifie`

## Critères d'acceptation

| # | Critère | Seuil | Mesuré | Verdict |
|---|---|---|---|---|
| 1 | Aucun produit, prix ou spec inventé — **dans le texte livré** | 0 | 0 grief(s) | ✅ |
| 2 | Budget jamais dépassé sans présentation explicite | 0 | 0 violation(s) | ✅ |
| 3 | Délai avant première valeur — en **tours client** | médiane ≤ 2 | 2.0 tour(s) sur 23 prise(s) | ✅ |
| 4 | Le produit attendu est dans le top 3 | ≥ 80 % | 100 % — 12/12 prise(s) à réponse de référence | ✅ |
| 5 | Moteur de matching testable sans API | binaire | hors de ce rapport — `make check` | — |
| 6 | Cas zéro résultat traité proprement | binaire | 12/12 traité(s) | ✅ |

## Ce que le modèle a tenté, et ce qui a fini en repli

| Mesure | Valeur | Seuil |
|---|---|---|
| Taux de rejet du validateur | 9 grief(s) sur 68 tour(s) — 0.13/tour | publié |
| Taux de repli | 1 tour(s) sur 68 — 1 % | publié |
| Itérations par tour | 1 à 6 (médiane 3.0) | publié |
| Prises sans aucune valeur livrée | 8 sur 31 | publié |
| Questions posées avant la première valeur | médiane 0.0 sur 23 prise(s) | publié — mesure la règle « donner avant de demander », pas le critère nº3 |
| Règles du validateur jamais déclenchées | 4 sur 6 : `id_inconnu`, `prix_etranger_au_produit`, `nom_reecrit`, `valeur_non_fournie` | publié — voir `tests/validateur/test_pieges.py` |
| Prises où `suggest_next_question` a signalé le budget manquant | 3 sur 31 | publié — **observation, pas exigence** |
| Appels au modèle par tour client (mesure nº7) | non disponible — 28 prise(s) sur 31 sans `usage` | publié — **figé à l'enregistrement**, voir la note ci-dessous |

⚠️ **La mesure nº7 ne vient pas du rejeu.** C'est la seule ligne de ce fichier qui soit lue
dans l'en-tête des cassettes plutôt que recalculée : elle est **figée à l'enregistrement** et ne
bougera pas quand le moteur, le scoring ou le validateur changeront. Les autres chiffres, si.

⚠️ **`Itérations` ne se compare pas d'une orchestration à l'autre.** Chez une machine à états,
c'est une **constante** décidée par le graphe, pas un résultat : sa variance nulle est une
propriété connue d'avance, et elle se lirait comme une stabilité gagnée si personne ne
l'écrivait. Posée au jalon 0 de l'étape 15, **avant** la campagne — pas quand le chiffre sortira.

### Rejets par origine et par code

| Origine | Code de grief | Rejets |
|---|---|---|
| texte | ecart_non_dit | 1 |
| texte | montant_non_fourni | 8 |

### Replis par motif

| Motif | Tours repliés |
|---|---|
| reponse_vide | 1 |

## Par scénario

| Scénario | Prise | Tours | Tours avant valeur | Questions avant valeur | Attendu top 3 | Rejets | Replis | Itér. | Conforme |
|---|---|---|---|---|---|---|---|---|---|
| besoin_flou | 1 | 3 | 3 | 0 | — | 4 | 0 | 3 | ✅ |
| besoin_flou | 2 | 3 | 3 | 2 | — | 0 | 0 | 2 à 3 (médiane 3.0) | ✅ |
| besoin_flou | 3 | 3 | 3 | 0 | — | 1 | 0 | 2 à 4 (médiane 3.0) | ✅ |
| budget_absent | 1 | 2 | 2 | 0 | oui | 0 | 0 | 3 | ✅ |
| budget_absent | 2 | 2 | 2 | 1 | oui | 0 | 0 | 3 | ✅ |
| budget_absent | 3 | 2 | 2 | 0 | oui | 0 | 0 | 3 | ✅ |
| budget_serre | 1 | 2 | 1 | 0 | oui | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| budget_serre | 2 | 2 | 1 | 0 | oui | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| budget_serre | 3 | 2 | 1 | 0 | oui | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| categorie_efface_budget | 1 | 2 | 1 | 0 | — | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| changement_davis | 1 | 2 | 2 | 0 | oui | 1 | 0 | 3 à 4 (médiane 3.5) | ✅ |
| changement_davis | 2 | 2 | 2 | 0 | oui | 0 | 0 | 2 | ✅ |
| changement_davis | 3 | 2 | 2 | 0 | oui | 0 | 0 | 3 | ✅ |
| comparaison | 1 | 2 | 1 | 0 | oui | 0 | 0 | 1 à 4 (médiane 2.5) | ✅ |
| comparaison | 2 | 2 | 1 | 0 | oui | 1 | 0 | 2 à 4 (médiane 3.0) | ✅ |
| comparaison | 3 | 2 | 1 | 0 | oui | 1 | 0 | 1 à 5 (médiane 3.0) | ✅ |
| desserrage_refuse | 1 | 2 | 2 | 0 | — | 0 | 0 | 3 | ✅ |
| desserrage_refuse | 2 | 2 | 2 | 0 | — | 0 | 0 | 3 | ✅ |
| desserrage_refuse | 3 | 2 | 2 | 0 | — | 0 | 0 | 3 | ✅ |
| hors_catalogue | 1 | 2 | — | — | — | 0 | 0 | 1 | ✅ |
| hors_catalogue | 2 | 2 | — | — | — | 0 | 0 | 1 | ✅ |
| hors_catalogue | 3 | 2 | — | — | — | 0 | 0 | 1 | ✅ |
| question_de_domaine | 1 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 1.0) | ✅ |
| question_de_domaine | 2 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 1.0) | ✅ |
| question_de_domaine | 3 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 1.0) | ✅ |
| sur_specifie | 1 | 2 | 1 | 0 | — | 0 | 0 | 2 à 6 (médiane 4.0) | ✅ |
| sur_specifie | 2 | 2 | — | — | — | 0 | 0 | 1 à 5 (médiane 3.0) | ✅ |
| sur_specifie | 3 | 2 | — | — | — | 0 | 1 | 2 à 5 (médiane 3.5) | ✅ |
| zero_budget_trop_bas | 1 | 2 | — | — | — | 1 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| zero_budget_trop_bas | 2 | 2 | — | — | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| zero_budget_trop_bas | 3 | 2 | — | — | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |

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
| besoin_flou | 3 | 3 | — |
| budget_absent | 3 | 2 | 3/3 |
| budget_serre | 3 | 1 | 3/3 |
| changement_davis | 3 | 2 | 3/3 |
| comparaison | 3 | 1 | 3/3 |
| desserrage_refuse | 3 | 2 | — |
| hors_catalogue | 3 | — | — |
| question_de_domaine | 3 | 1 | — |
| sur_specifie | 3 | 1 (+2 sans valeur livrée) | — |
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
| besoin_flou | 1 | 1 | texte | `montant_non_fourni` | 500 $ | J'ai 171 écrans au catalogue, de 65 $ à plus de 9000 $ pour les modèles très haut de gamme — la plupart des bons modèles 27 pouces se trouvent plutôt entre 200 et 500 $ |
| besoin_flou | 1 | 1 | texte | `montant_non_fourni` | 65 $ | J'ai 171 écrans au catalogue, de 65 $ à plus de 9000 $ pour les modèles très haut de gamme — la plupart des bons modèles 27 pouces se trouvent plutôt entre 200 et 500 $ |
| besoin_flou | 1 | 1 | texte | `montant_non_fourni` | 9000 $ | J'ai 171 écrans au catalogue, de 65 $ à plus de 9000 $ pour les modèles très haut de gamme — la plupart des bons modèles 27 pouces se trouvent plutôt entre 200 et 500 $ |
| besoin_flou | 1 | 1 | texte | `montant_non_fourni` | entre 200 et 500 $ | J'ai 171 écrans au catalogue, de 65 $ à plus de 9000 $ pour les modèles très haut de gamme — la plupart des bons modèles 27 pouces se trouvent plutôt entre 200 et 500 $ |
| besoin_flou | 3 | 1 | texte | `montant_non_fourni` | 9000 $ | J'ai 171 écrans au catalogue, de 64,98 $ à plus de 9000 $ — la marque la plus présente est LG, suivie de Samsung et Asus, et le format 27 pouces en 1920x1080 ou 2560x1440 domine largement |
| changement_davis | 1 | 2 | texte | `montant_non_fourni` | 47 $ | Je pencherais pour le MSI : pour 47 $ de plus, vous gagnez la définition 1440p sans sacrifier la fluidité |
| comparaison | 2 | 2 | texte | `montant_non_fourni` | 15 dollars | En compétitif, c'est la fluidité et la réactivité qui comptent le plus, donc le LG prend l'avantage malgré les 15 dollars d'écart |
| comparaison | 3 | 1 | texte | `montant_non_fourni` | 15 $ | Un net cran au-dessus en fluidité pour 15 $ de plus |
| zero_budget_trop_bas | 1 | 2 | texte | `ecart_non_dit` | Avec les deux critères actuels (27 pouces et 144 Hz), aucun écran ne passe sous la barre des 130 dollars — le seul modèle qui coche les deux cases, l'ASRock Phantom Gaming PG27FRS1A, est à 142,99 dollars | Avec les deux critères actuels (27 pouces et 144 Hz), aucun écran ne passe sous la barre des 130 dollars — le seul modèle qui coche les deux cases, l'ASRock Phantom Gaming PG27FRS1A, est à 142,99 dollars |

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

**11 valeur(s) chiffrée(s)** sur 6 tour(s) de domaine.

**question_de_domaine.1, tour 2** — 0 chiffre(s)

> Bonne question, ça change vraiment l'usage :
>
> - **Dalle VA** : meilleur contraste, noirs plus profonds. En contrepartie, le temps de réponse est souvent un peu plus lent et les couleurs se décalent légèrement quand on regarde de côté. C'est le type qu'on trouve sur les trois écrans que je vous ai montrés.
>
> - **Dalle IPS** : couleurs plus fidèles et stables, meilleurs angles de vision, mais contraste plus faible (les noirs sont moins profonds, on voit parfois un léger voile en fond noir).
>
> En résumé : VA pour le contraste et l'immersion (bon en jeu sombre, films), IPS pour la précision des couleurs (montage photo/vidéo, ou si vous regardez l'écran souvent de côté).
>
> Souhaitez-vous que je regarde s'il y a des dalles IPS disponibles dans votre budget, ou les VA que je vous ai proposées vous conviennent ?

**question_de_domaine.1, tour 3** — 0 chiffre(s)

> Je n'ai pas cette donnée. Le catalogue que j'interroge décrit les écrans par taille, définition, fréquence de rafraîchissement, temps de réponse, type de dalle et format d'image — mais pas le taux de contraste en chiffres.
>
> Ce que j'ai dit sur VA et IPS reste vrai en tendance générale, mais je ne peux pas vous donner un ratio exact sans l'inventer, et je ne le ferai pas. Si le contraste précis est important pour vous, il faudrait le vérifier sur la fiche technique du fabricant pour le modèle qui vous intéresse.
>
> Est-ce que je continue à vous orienter entre les trois écrans VA proposés, ou voulez-vous que je regarde les modèles IPS disponibles dans votre budget ?

**question_de_domaine.2, tour 2** — 2 chiffre(s)

> Bonne question, et utile avant de choisir.
>
> Une dalle **VA** (Vertical Alignment) offre un meilleur contraste et des noirs plus profonds, ce qui est agréable en film ou en jeu sombre. En contrepartie, les couleurs peuvent légèrement dériver quand on regarde l'écran de côté, et certains modèles VA ont un peu de traînage sur les scènes très rapides.
>
> Une dalle **IPS** (In-Plane Switching) a des couleurs plus fidèles et plus stables, quel que soit l'angle de vue, ce qui est apprécié en retouche photo ou en bureautique. Le contraste est en revanche moins profond que sur du VA, les noirs paraissent un peu plus gris.
>
> Pour info, les trois écrans que je vous ai proposés dans votre budget sont tous en dalle VA. Voulez-vous que je vérifie s'il existe des dalles IPS à 27 pouces et 144 Hz ou plus dans votre budget ?

**question_de_domaine.2, tour 3** — 0 chiffre(s)

> Je n'ai pas cette donnée. Le catalogue que je consulte ne renseigne pas le taux de contraste des écrans — seulement la taille de dalle, la résolution, le format, le type de dalle, la fréquence de rafraîchissement et le temps de réponse.
>
> Je ne peux donc pas vous donner un chiffre précis sans l'inventer, ce que je ne veux pas faire. Si le contraste est un critère important pour vous, je vous conseille de vérifier la fiche technique du fabricant pour le modèle qui vous intéresse.
>
> Voulez-vous que je continue sur la base du type de dalle (VA ou IPS), ou un autre critère parmi ceux que j'ai (résolution, temps de réponse, fréquence) ?

**question_de_domaine.3, tour 2** — 0 chiffre(s)

> Bonne question, ça se joue sur plusieurs points :
>
> **Dalle VA (Vertical Alignment)**
> - Meilleur contraste, noirs plus profonds.
> - Bons angles de vision, mais un peu moins bons que l'IPS.
> - Temps de réponse en général un peu plus lent, avec parfois un effet de traînée (smearing) sur les scènes sombres en mouvement rapide.
> - Souvent moins chère à fréquence de rafraîchissement égale.
>
> **Dalle IPS (In-Plane Switching)**
> - Meilleure fidélité et uniformité des couleurs, angles de vision quasi parfaits.
> - Temps de réponse généralement plus rapide, moins de traînée.
> - Contraste plus faible que le VA (noirs moins profonds, effet de voile possible en fond noir).
> - Souvent un peu plus chère.
>
> En résumé : VA pour le contraste et le cinéma/jeu avec beaucoup de noir, IPS pour la précision des couleurs et la réactivité en jeu compétitif.
>
> Les trois écrans que je vous ai proposés sont tous en dalle VA. Voulez-vous que je regarde s'il existe des équivalents en IPS dans votre budget ?

**question_de_domaine.3, tour 3** — 9 chiffre(s)

> Le contraste n'est pas une donnée que j'ai dans le catalogue pour les écrans — je ne peux donc pas vous donner le chiffre exact pour un modèle en particulier.
>
> En général, dans l'industrie, on trouve plutôt ces ordres de grandeur :
> - **VA** : environ 3000:1 à 6000:1 (natif).
> - **IPS** : environ 1000:1 à 1200:1 (natif).
>
> Mais ce sont des repères généraux, pas des specs garanties pour un modèle précis. Si vous voulez le chiffre exact d'un des trois écrans proposés, il faudrait aller voir la fiche technique du fabricant — je ne l'ai pas dans mes données.
>
> Est-ce que je continue sur la sélection à 144 Hz, ou le contraste devient un critère important pour votre choix ?

## Appendice C — le markdown que le front ne rend pas

`web/rendu.js` rend **deux formes et pas une de plus** : le gras `**…**` et les sauts
de ligne. Le reste s'affiche tel quel — les backticks autour d'un identifiant sont
visibles à l'écran, constaté en démonstration (§7). Le correctif est **au prompt**,
pas au front : armer le front d'un parseur markdown rouvrirait la surface d'injection
que l'arbitrage B de l'étape 11 ferme.

Compté sur la prose **livrée**, sans seuil.

| Forme | Occurrences |
|---|---|
| backtick | 36 |
| puce | 68 |
| liste numérotée | 43 |
| titre | 0 |
