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

## Critères d'acceptation

| # | Critère | Seuil | Mesuré | Verdict |
|---|---|---|---|---|
| 1 | Aucun produit, prix ou spec inventé — **dans le texte livré** | 0 | 0 grief(s) | ✅ |
| 2 | Budget jamais dépassé sans présentation explicite | 0 | 0 violation(s) | ✅ |
| 3 | Délai avant première valeur — en **tours client** | médiane ≤ 2 | 1.0 tour(s) sur 30 prise(s) | ✅ |
| 4 | Le produit attendu est dans le top 3 | ≥ 80 % | 100 % — 12/12 prise(s) à réponse de référence | ✅ |
| 5 | Moteur de matching testable sans API | binaire | hors de ce rapport — `make check` | — |
| 6 | Cas zéro résultat traité proprement | binaire | 12/12 traité(s) | ✅ |

## Ce que le modèle a tenté, et ce qui a fini en repli

| Mesure | Valeur | Seuil |
|---|---|---|
| Taux de rejet du validateur | 1 grief(s) sur 87 tour(s) — 0.01/tour | publié |
| Taux de repli | 0 tour(s) sur 87 — 0 % | publié |
| Itérations par tour | 1 à 5 (médiane 3.0) | publié |
| Prises sans aucune valeur livrée | 9 sur 39 | publié |
| Questions posées avant la première valeur | médiane 0.0 sur 30 prise(s) | publié — mesure la règle « donner avant de demander », pas le critère nº3 |
| Règles du validateur jamais déclenchées | 5 sur 6 : `id_inconnu`, `prix_etranger_au_produit`, `nom_reecrit`, `ecart_non_dit`, `valeur_non_fournie` | publié — voir `tests/validateur/test_pieges.py` |
| Prises où `suggest_next_question` a signalé le budget manquant | 0 sur 39 | publié — **observation, pas exigence** |
| Appels au modèle par tour client (mesure nº7) | 213 appel(s) sur 87 tour(s) — 2.45 appel/tour | publié — **figé à l'enregistrement**, voir la note ci-dessous |
| Jetons d'entrée facturés (mesure nº7) | 517 911 facturés (504 833 hors cache + 13 078 de cache écrit) ; 2 772 536 lus du cache, à un autre tarif | publié — **figé à l'enregistrement**, voir la note ci-dessous |
| Jetons de sortie (mesure nº7) | 66 683 jetons | publié — **figé à l'enregistrement**, voir la note ci-dessous |

⚠️ **La mesure nº7 ne vient pas du rejeu.** Ce sont les seules lignes de ce fichier qui soient lues
dans l'en-tête des cassettes plutôt que recalculées : elles sont **figées à l'enregistrement** et ne
bougeront pas quand le moteur, le scoring ou le validateur changeront. Les autres chiffres, si.

⚠️ **Les appels et les jetons peuvent aller en sens contraire, et c'est arrivé.** La campagne
de l'étape 15 a mesuré une orchestration qui fait **moins d'appels par tour** que l'autre et qui
paie **près du double** en entrée facturée : deux appels par tour, mais chacun renvoie une
conversation qui grossit plus vite. Publier le compte d'appels seul dirait donc l'inverse de
la vérité, et c'est pourquoi les deux moitiés de la mesure nº7 sont écrites ensemble.
Les deux campagnes de l'étape 15 sont chiffrées côte à côte dans leur comparaison.

⚠️ **`Itérations` ne se compare pas d'une orchestration à l'autre.** Chez une machine à états,
c'est une **constante** décidée par le graphe, pas un résultat : sa variance nulle est une
propriété connue d'avance, et elle se lirait comme une stabilité gagnée si personne ne
l'écrivait. Posée au jalon 0 de l'étape 15, **avant** la campagne — pas quand le chiffre sortira.

### Rejets par origine et par code

| Origine | Code de grief | Rejets |
|---|---|---|
| texte | montant_non_fourni | 1 |

### Replis par motif

Aucun repli sur cette exécution.

## Par scénario

| Scénario | Prise | Tours | Tours avant valeur | Questions avant valeur | Attendu top 3 | Rejets | Replis | Itér. | Conforme |
|---|---|---|---|---|---|---|---|---|---|
| avis_du_web | 1 | 2 | 1 | 0 | — | 0 | 0 | 2 à 4 (médiane 3.0) | ✅ |
| avis_du_web | 2 | 2 | 1 | 0 | — | 0 | 0 | 2 à 4 (médiane 3.0) | ✅ |
| avis_du_web | 3 | 2 | 1 | 0 | — | 0 | 0 | 2 à 4 (médiane 3.0) | ✅ |
| besoin_flou | 1 | 3 | 2 | 0 | — | 0 | 0 | 2 à 3 (médiane 2.0) | ✅ |
| besoin_flou | 2 | 3 | 2 | 0 | — | 0 | 0 | 2 | ✅ |
| besoin_flou | 3 | 3 | 2 | 0 | — | 0 | 0 | 3 | ✅ |
| budget_absent | 1 | 2 | 1 | 0 | oui | 0 | 0 | 3 | ✅ |
| budget_absent | 2 | 2 | 1 | 0 | oui | 0 | 0 | 3 | ✅ |
| budget_absent | 3 | 2 | 1 | 0 | oui | 0 | 0 | 3 | ✅ |
| budget_serre | 1 | 2 | 1 | 0 | oui | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| budget_serre | 2 | 2 | 1 | 0 | oui | 0 | 0 | 1 à 2 (médiane 1.5) | ✅ |
| budget_serre | 3 | 2 | 1 | 0 | oui | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| categorie_efface_budget | 1 | 2 | 1 | 0 | — | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| categorie_efface_budget | 2 | 2 | 1 | 0 | — | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| categorie_efface_budget | 3 | 2 | 1 | 0 | — | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| changement_davis | 1 | 2 | 2 | 0 | oui | 0 | 0 | 3 | ✅ |
| changement_davis | 2 | 2 | 2 | 0 | oui | 0 | 0 | 3 | ✅ |
| changement_davis | 3 | 2 | 2 | 0 | oui | 1 | 0 | 3 à 4 (médiane 3.5) | ✅ |
| comparaison | 1 | 2 | 1 | 0 | oui | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| comparaison | 2 | 2 | 1 | 0 | oui | 0 | 0 | 1 à 4 (médiane 2.5) | ✅ |
| comparaison | 3 | 2 | 1 | 0 | oui | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| desserrage_refuse | 1 | 2 | 2 | 1 | — | 0 | 0 | 3 | ✅ |
| desserrage_refuse | 2 | 2 | 2 | 0 | — | 0 | 0 | 3 à 4 (médiane 3.5) | ✅ |
| desserrage_refuse | 3 | 2 | 2 | 0 | — | 0 | 0 | 3 | ✅ |
| hors_catalogue | 1 | 2 | — | — | — | 0 | 0 | 1 | ✅ |
| hors_catalogue | 2 | 2 | — | — | — | 0 | 0 | 1 | ✅ |
| hors_catalogue | 3 | 2 | — | — | — | 0 | 0 | 1 | ✅ |
| question_de_domaine | 1 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| question_de_domaine | 2 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| question_de_domaine | 3 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| question_de_domaine | 4 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| question_de_domaine | 5 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| question_de_domaine | 6 | 3 | 1 | 0 | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| sur_specifie | 1 | 2 | — | — | — | 0 | 0 | 2 à 4 (médiane 3.0) | ✅ |
| sur_specifie | 2 | 2 | — | — | — | 0 | 0 | 1 à 5 (médiane 3.0) | ✅ |
| sur_specifie | 3 | 2 | — | — | — | 0 | 0 | 2 à 4 (médiane 3.0) | ✅ |
| zero_budget_trop_bas | 1 | 2 | — | — | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
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
| avis_du_web | 3 | 1 | — |
| besoin_flou | 3 | 2 | — |
| budget_absent | 3 | 1 | 3/3 |
| budget_serre | 3 | 1 | 3/3 |
| categorie_efface_budget | 3 | 1 | — |
| changement_davis | 3 | 2 | 3/3 |
| comparaison | 3 | 1 | 3/3 |
| desserrage_refuse | 3 | 2 | — |
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
| changement_davis | 3 | 2 | texte | `montant_non_fourni` | 47 dollars | Le MSI est en 1440p, plus net, et son temps de réponse est plus rapide, pour 47 dollars de plus que l'ASRock qui reste en 1080p |

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

**55 valeur(s) chiffrée(s)** sur 12 tour(s) de domaine.

**question_de_domaine.1, tour 2** — 0 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.

**question_de_domaine.1, tour 2** — 2 chiffre(s)

> En revanche, sur ce qui reste dans votre budget avec vos critères actuels : 6 écrans en dalle VA, 3 en IPS.
>
> En gros, ce que je peux vous dire par expérience de vente, sans entrer dans la technique : le VA tient mieux le contraste (les noirs sont plus profonds), l'IPS a des couleurs plus stables selon l'angle de vue. Pour du jeu rapide, les deux se valent aujourd'hui, la différence se joue surtout sur le confort visuel personnel.
>
> Voulez-vous que je vous oriente vers l'un des deux types, ou on reste sur les trois modèles déjà proposés ?

**question_de_domaine.1, tour 3** — 14 chiffre(s)

> Je ne l'ai pas. Le catalogue ne contient pas de champ de contraste pour les écrans — je ne peux donc pas vous donner un chiffre, ni même approximatif. Je ne vais pas en inventer un.
>
> Ce que je peux vous confirmer, ce sont les trois modèles déjà sur la table, avec leurs vraies specs : le MSI MAG 274CQF (189,99 $, VA, 1440p, 180 Hz), le LG 27GP750-B (226,99 $, IPS, 1080p, 240 Hz) et l'Asus TUF Gaming VG279QM1A (229,00 $, IPS, 1080p, 280 Hz).
>
> Voulez-vous qu'on tranche entre ces trois-là, ou je regarde ce que disent des utilisateurs sur l'un d'eux en particulier ?

**question_de_domaine.2, tour 2** — 0 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles, ce serait au-delà de ce que je peux garantir.

**question_de_domaine.2, tour 2** — 8 chiffre(s)

> Ce que je peux vous dire, en revanche, c'est ce qu'il y a dans votre sélection actuelle : sur les 9 écrans qui correspondent à vos critères, 6 sont en dalle VA et 3 en dalle IPS.
>
> Dans les trois que je vous ai montrés, le MSI MAG 274CQF est en VA, tandis que le LG 27GP750-B et l'Asus TUF Gaming VG279QM1A sont en IPS. Si vous avez une préférence entre les deux technologies, dites-le-moi et je resserre la sélection dessus. Sinon, je peux aussi vous orienter selon l'usage : jeu compétitif, ou plutôt polyvalent.

**question_de_domaine.2, tour 3** — 0 chiffre(s)

> Je ne peux pas vous donner ce chiffre. Le contraste n'est pas un champ du catalogue que j'ai sous les yeux — je n'ai que la taille de dalle, la définition, la fréquence, le temps de réponse et le type de dalle pour chaque écran. Donner un chiffre de contraste "typique" serait une invention, même présentée comme approximative.
>
> Ce que je peux faire, c'est vous montrer les écrans VA de votre sélection avec leurs specs réelles, ou vous laisser choisir sur d'autres critères concrets. Vous voulez que je resserre sur le VA, l'IPS, ou que je vous montre autre chose ?

**question_de_domaine.3, tour 2** — 0 chiffre(s)

> Je ne vais pas vous inventer un cours sur les technologies de dalle, ce n'est pas ce que je maîtrise.

**question_de_domaine.3, tour 2** — 8 chiffre(s)

> Ce que je peux vous dire, c'est ce qu'il y a au catalogue sur vos critères actuels : sur les 9 écrans qui correspondent à votre demande, 6 sont en dalle VA et 3 en IPS.
>
> Parmi les trois que je vous ai montrés, le MSI MAG 274CQF est en VA, le LG 27GP750-B et l'Asus TUF Gaming VG279QM1A sont en IPS. Si vous avez une préférence entre les deux technologies, dites-le-moi et je resserre la sélection dessus.

**question_de_domaine.3, tour 3** — 3 chiffre(s)

> Ça, je ne peux pas vous le donner. Le contraste n'est pas une donnée que le catalogue fournit pour ces écrans, et un chiffre de contraste "typique" pour une dalle VA n'est fourni par personne ici — je ne vais pas l'inventer.
>
> Ce que je peux faire, c'est vous montrer ce qui est réellement dans les fiches produit : résolution, fréquence, temps de réponse, prix. Sur les trois écrans déjà cités, le MSI MAG 274CQF (VA) a un temps de réponse de 0,5 ms, contre 1 ms pour les deux modèles IPS. Voulez-vous que je reste sur cette base, ou qu'on regarde un autre critère ?

**question_de_domaine.4, tour 2** — 0 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.

**question_de_domaine.4, tour 2** — 3 chiffre(s)

> Ce que je peux vous dire, en revanche, c'est ce qu'il y a dans votre budget : sur les 9 écrans qui tiennent vos critères, 6 sont en dalle VA et 3 en dalle IPS.
>
> Les trois que je vous ai montrés tout à l'heure sont tous en VA. Si vous voulez comparer avec une des dalles IPS disponibles, je peux vous les sortir — dites-moi si c'est ce qui vous intéresse.

**question_de_domaine.4, tour 3** — 0 chiffre(s)

> Je n'ai pas cette information. Le catalogue me donne le type de dalle, la taille, la fréquence de rafraîchissement, le temps de réponse — mais pas de valeur de contraste. Je ne vais pas vous donner un chiffre "typique" trouvé ailleurs, ce serait vous fournir une donnée que je n'ai pas vérifiée sur nos produits.
>
> Si le contraste est un critère important pour vous, je peux chercher des avis d'utilisateurs sur un des écrans précis — ça vous donnerait un retour concret, pas une moyenne générique. Vous voulez que je regarde ça sur l'un des trois modèles proposés ?

**question_de_domaine.5, tour 2** — 0 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.
>
> Ce que je peux vous dire, c'est ce qu'il y a dans le rayon parmi les écrans qui correspondent à vos critères.

**question_de_domaine.5, tour 2** — 11 chiffre(s)

> Sur les 9 écrans qui tiennent dans vos critères (27 pouces, 144 Hz au moins, 250 $ maximum), il y a 6 dalles VA et 3 dalles IPS.
>
> Parmi les trois que je vous ai montrés, le MSI MAG 274CQF est en VA, le LG 27GP750-B et l'Asus TUF Gaming VG279QM1A sont en IPS. Si vous avez une préférence entre les deux technologies, ou si c'est un usage précis (jeu rapide, retouche photo) qui vous fait hésiter, dites-le-moi et je resserre la sélection.

**question_de_domaine.5, tour 3** — 1 chiffre(s)

> Je n'ai pas cette donnée. Le catalogue ne contient pas de champ de contraste pour les écrans — je ne vais donc pas vous donner un chiffre, même approximatif, ce serait inventé.
>
> Ce que je peux vous montrer, ce sont les caractéristiques réelles des écrans en VA de la sélection : résolution, fréquence de rafraîchissement, temps de réponse, prix. Voulez-vous que je vous détaille les 6 écrans en VA qui correspondent à vos critères, pour comparer sur ces points-là ?

**question_de_domaine.6, tour 2** — 0 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles, ce n'est pas mon rayon.
>
> Ce que je peux vous dire, c'est ce qu'il y a dans le catalogue actuel :

**question_de_domaine.6, tour 2** — 5 chiffre(s)

> Sur les 9 écrans qui tiennent vos critères (27 pouces, 144 Hz mini, dans votre budget), 6 sont en dalle VA et 3 en IPS.
>
> Les trois que je vous ai montrés plus tôt sont tous en VA. Si vous voulez, je peux vous sortir les modèles IPS pour comparer — dites-moi juste si c'est ce qui vous intéresse.

**question_de_domaine.6, tour 3** — 0 chiffre(s)

> Ça, je ne peux pas vous le donner. Le contraste n'est pas un champ du catalogue ici — je n'ai que la taille, la fréquence, la résolution, le format d'image, le temps de réponse et le type de dalle. Aucun chiffre de contraste, ni pour le VA ni pour l'IPS, n'est fourni nulle part dans mes données, donc je ne vais pas vous en inventer un, même approximatif.
>
> Ce que je sais en revanche, c'est ce que contient le catalogue : les trois écrans montrés plus tôt, tous en VA, avec leurs vraies specs. Voulez-vous que je regarde les modèles IPS pour comparer sur ce que j'ai réellement — résolution, fréquence, temps de réponse ?

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
| puce | 2 |
| liste numérotée | 0 |
| titre | 0 |
