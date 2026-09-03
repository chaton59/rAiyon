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

## Critères d'acceptation

| # | Critère | Seuil | Mesuré | Verdict |
|---|---|---|---|---|
| 1 | Aucun produit, prix ou spec inventé — **dans le texte livré** | 0 | 0 grief(s) | ✅ |
| 2 | Budget jamais dépassé sans présentation explicite | 0 | 0 violation(s) | ✅ |
| 3 | Délai avant première valeur — en **tours client** | médiane ≤ 2 | 1.0 tour(s) sur 29 prise(s) | ✅ |
| 4 | Le produit attendu est dans le top 3 | ≥ 80 % | 92 % — 11/12 prise(s) à réponse de référence | ✅ |
| 5 | Moteur de matching testable sans API | binaire | hors de ce rapport — `make check` | — |
| 6 | Cas zéro résultat traité proprement | binaire | 14/14 traité(s) | ✅ |

## Ce que le modèle a tenté, et ce qui a fini en repli

| Mesure | Valeur | Seuil |
|---|---|---|
| Taux de rejet du validateur | 51 grief(s) sur 81 tour(s) — 0.63/tour | publié |
| Taux de repli | 8 tour(s) sur 81 — 10 % | publié |
| Itérations par tour | 2 à 3 (médiane 2.0) | publié |
| Prises sans aucune valeur livrée | 7 sur 36 | publié |
| Questions posées avant la première valeur | médiane 0.0 sur 29 prise(s) | publié — mesure la règle « donner avant de demander », pas le critère nº3 |
| Règles du validateur jamais déclenchées | 3 sur 6 : `id_inconnu`, `prix_etranger_au_produit`, `nom_reecrit` | publié — voir `tests/validateur/test_pieges.py` |
| Prises où `suggest_next_question` a signalé le budget manquant | 5 sur 36 | publié — **observation, pas exigence** |
| Appels au modèle par tour client (mesure nº7) | 176 appel(s) sur 81 tour(s) — 2.17 appel/tour | publié — **figé à l'enregistrement**, voir la note ci-dessous |
| Jetons d'entrée facturés (mesure nº7) | 663 347 facturés (657 010 hors cache + 6 337 de cache écrit) ; 1 108 975 lus du cache, à un autre tarif | publié — **figé à l'enregistrement**, voir la note ci-dessous |
| Jetons de sortie (mesure nº7) | 65 958 jetons | publié — **figé à l'enregistrement**, voir la note ci-dessous |

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
| texte | ecart_non_dit | 24 |
| texte | montant_non_fourni | 19 |
| texte | valeur_non_fournie | 8 |

### Replis par motif

| Motif | Tours repliés |
|---|---|
| reponse_vide | 2 |
| validation | 6 |

## Par scénario

| Scénario | Prise | Tours | Tours avant valeur | Questions avant valeur | Attendu top 3 | Rejets | Replis | Itér. | Conforme |
|---|---|---|---|---|---|---|---|---|---|
| besoin_flou | 1 | 3 | 2 | 0 | — | 1 | 0 | 2 à 3 (médiane 2.0) | ✅ |
| besoin_flou | 2 | 3 | 2 | 0 | — | 0 | 0 | 2 | ✅ |
| besoin_flou | 3 | 3 | 2 | 0 | — | 0 | 0 | 2 | ✅ |
| budget_absent | 1 | 2 | 2 | 1 | oui | 0 | 0 | 2 | ✅ |
| budget_absent | 2 | 2 | 2 | 1 | oui | 0 | 0 | 2 | ✅ |
| budget_absent | 3 | 2 | 2 | 1 | oui | 0 | 0 | 2 | ✅ |
| budget_serre | 1 | 2 | 1 | 0 | oui | 0 | 0 | 2 | ✅ |
| budget_serre | 2 | 2 | 1 | 0 | oui | 0 | 0 | 2 | ✅ |
| budget_serre | 3 | 2 | 1 | 0 | oui | 0 | 0 | 2 | ✅ |
| categorie_efface_budget | 1 | 2 | 1 | 0 | — | 0 | 0 | 2 | ✅ |
| categorie_efface_budget | 2 | 2 | 1 | 0 | — | 0 | 0 | 2 | ❌ |
| categorie_efface_budget | 3 | 2 | 1 | 0 | — | 0 | 0 | 2 | ✅ |
| changement_davis | 1 | 2 | 2 | 0 | oui | 8 | 1 | 2 à 3 (médiane 2.5) | ✅ |
| changement_davis | 2 | 2 | 2 | 0 | oui | 1 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| changement_davis | 3 | 2 | 2 | 0 | oui | 9 | 1 | 3 | ✅ |
| comparaison | 1 | 2 | 1 | 0 | non | 3 | 1 | 2 à 3 (médiane 2.5) | ✅ |
| comparaison | 2 | 2 | 1 | 0 | oui | 0 | 0 | 2 | ✅ |
| comparaison | 3 | 2 | 1 | 0 | oui | 0 | 0 | 2 | ✅ |
| desserrage_refuse | 1 | 2 | 2 | 0 | — | 10 | 2 | 3 | ✅ |
| desserrage_refuse | 2 | 2 | 2 | 0 | — | 8 | 1 | 2 à 3 (médiane 2.5) | ✅ |
| desserrage_refuse | 3 | 2 | 2 | 0 | — | 2 | 1 | 2 à 3 (médiane 2.5) | ✅ |
| hors_catalogue | 1 | 2 | — | — | — | 0 | 0 | 2 | ✅ |
| hors_catalogue | 2 | 2 | — | — | — | 0 | 0 | 2 | ✅ |
| hors_catalogue | 3 | 2 | — | — | — | 0 | 0 | 2 | ✅ |
| question_de_domaine | 1 | 3 | 1 | 0 | — | 0 | 0 | 2 | ✅ |
| question_de_domaine | 2 | 3 | 1 | 0 | — | 0 | 0 | 2 | ✅ |
| question_de_domaine | 3 | 3 | 1 | 0 | — | 0 | 0 | 2 | ✅ |
| question_de_domaine | 4 | 3 | 1 | 0 | — | 0 | 0 | 2 | ✅ |
| question_de_domaine | 5 | 3 | 1 | 0 | — | 0 | 0 | 2 | ✅ |
| question_de_domaine | 6 | 3 | 1 | 0 | — | 0 | 0 | 2 | ✅ |
| sur_specifie | 1 | 2 | 1 | 0 | — | 2 | 1 | 2 à 3 (médiane 2.5) | ✅ |
| sur_specifie | 2 | 2 | — | — | — | 3 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| sur_specifie | 3 | 2 | 2 | 0 | — | 4 | 0 | 3 | ❌ |
| zero_budget_trop_bas | 1 | 2 | — | — | — | 0 | 0 | 2 | ✅ |
| zero_budget_trop_bas | 2 | 2 | — | — | — | 0 | 0 | 2 | ✅ |
| zero_budget_trop_bas | 3 | 2 | — | — | — | 0 | 0 | 2 | ✅ |

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
| besoin_flou | 3 | 2 | — |
| budget_absent | 3 | 2 | 3/3 |
| budget_serre | 3 | 1 | 3/3 |
| categorie_efface_budget | 3 | 1 | — |
| changement_davis | 3 | 2 | 3/3 |
| comparaison | 3 | 1 | 2/3 |
| desserrage_refuse | 3 | 2 | — |
| hors_catalogue | 3 | — | — |
| question_de_domaine | 6 | 1 | — |
| sur_specifie | 3 | 1 à 2 (+1 sans valeur livrée) | — |
| zero_budget_trop_bas | 3 | — | — |

## Attentes binaires non tenues

| Scénario | Prise | Ce qui manque |
|---|---|---|
| categorie_efface_budget | 2 | attente `budget_efface` |
| sur_specifie | 3 | attente `zero_resultat` |
| sur_specifie | 3 | diagnostic attendu `critere_trop_strict` |

## Appendice A — les phrases refusées

Une ligne par grief. ⚠️ **Aucune de ces phrases n'a atteint le client** : elles ont
été refusées, puis régénérées ou repliées. Ce que cet appendice montre est ce que le
modèle a **tenté**, et sous quelle forme — un taux de rejet qui baisse ne dit pas
laquelle de ces formes a disparu.

| Scénario | Prise | Tour | Origine | Code | Extrait | Phrase refusée |
|---|---|---|---|---|---|---|
| besoin_flou | 1 | 2 | texte | `valeur_non_fournie` | 25 pouces | Et une taille d'écran en tête, plutôt du 24-25 pouces ou du 27 pouces (c'est la taille la plus représentée, avec 20 modèles) |
| changement_davis | 1 | 1 | texte | `ecart_non_dit` | **Asus TUF Gaming VG279QM1A** (id monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz | **Asus TUF Gaming VG279QM1A** (id monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz |
| changement_davis | 1 | 1 | texte | `ecart_non_dit` | **Asus TUF Gaming VG279QM1A** (id monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz | **Asus TUF Gaming VG279QM1A** (id monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz |
| changement_davis | 1 | 1 | texte | `ecart_non_dit` | **LG 27GP750-B** (id monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz | **LG 27GP750-B** (id monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz |
| changement_davis | 1 | 1 | texte | `ecart_non_dit` | **LG 27GP750-B** (id monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz | **LG 27GP750-B** (id monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz |
| changement_davis | 1 | 1 | texte | `montant_non_fourni` | 26,99 $ | **LG 27GP750-B** (id monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz |
| changement_davis | 1 | 1 | texte | `montant_non_fourni` | 26,99 $ | **LG 27GP750-B** (id monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz |
| changement_davis | 1 | 1 | texte | `montant_non_fourni` | 29,00 $ | **Asus TUF Gaming VG279QM1A** (id monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz |
| changement_davis | 1 | 1 | texte | `montant_non_fourni` | 29,00 $ | **Asus TUF Gaming VG279QM1A** (id monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz |
| changement_davis | 2 | 2 | texte | `ecart_non_dit` | Pour information, les deux écrans à 240 Hz et plus restent disponibles si vous changez d'avis : le LG 27GP750-B à 226.99 dollars et l'Asus TUF Gaming VG279QM1A à 229.00 dollars, mais tous deux dépassent votre budget, respectivement de 26.99 et 29.00 dollars | Pour information, les deux écrans à 240 Hz et plus restent disponibles si vous changez d'avis : le LG 27GP750-B à 226.99 dollars et l'Asus TUF Gaming VG279QM1A à 229.00 dollars, mais tous deux dépassent votre budget, respectivement de 26.99 et 29.00 dollars |
| changement_davis | 3 | 1 | texte | `ecart_non_dit` | **Asus TUF Gaming VG279QM1A** (monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz, dalle IPS | **Asus TUF Gaming VG279QM1A** (monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz, dalle IPS |
| changement_davis | 3 | 1 | texte | `ecart_non_dit` | **Asus TUF Gaming VG279QM1A** (monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz, dalle IPS | **Asus TUF Gaming VG279QM1A** (monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz, dalle IPS |
| changement_davis | 3 | 1 | texte | `ecart_non_dit` | **LG 27GP750-B** (monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz, dalle IPS | **LG 27GP750-B** (monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz, dalle IPS |
| changement_davis | 3 | 1 | texte | `ecart_non_dit` | **LG 27GP750-B** (monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz, dalle IPS | **LG 27GP750-B** (monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz, dalle IPS |
| changement_davis | 3 | 1 | texte | `montant_non_fourni` | 26,99 $ | **LG 27GP750-B** (monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz, dalle IPS |
| changement_davis | 3 | 1 | texte | `montant_non_fourni` | 26,99 $ | **LG 27GP750-B** (monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz, dalle IPS |
| changement_davis | 3 | 1 | texte | `montant_non_fourni` | 29,00 $ | **Asus TUF Gaming VG279QM1A** (monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz, dalle IPS |
| changement_davis | 3 | 1 | texte | `montant_non_fourni` | 29,00 $ | **Asus TUF Gaming VG279QM1A** (monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz, dalle IPS |
| changement_davis | 3 | 2 | texte | `ecart_non_dit` | Si vous vouliez vraiment du 240 Hz ou plus, il y avait aussi le LG 27GP750-B à 226,99 $ et l'Asus TUF Gaming VG279QM1A à 229,00 $, mais tous les deux dépassent votre budget de 200 dollars | Si vous vouliez vraiment du 240 Hz ou plus, il y avait aussi le LG 27GP750-B à 226,99 $ et l'Asus TUF Gaming VG279QM1A à 229,00 $, mais tous les deux dépassent votre budget de 200 dollars |
| comparaison | 1 | 2 | texte | `ecart_non_dit` | Pour du jeu compétitif, c'est le taux de rafraîchissement qui compte le plus : le MSI G27C4 E3 monte à 180 Hz, contre 165 Hz pour le Samsung Odyssey G55A | Pour du jeu compétitif, c'est le taux de rafraîchissement qui compte le plus : le MSI G27C4 E3 monte à 180 Hz, contre 165 Hz pour le Samsung Odyssey G55A |
| comparaison | 1 | 2 | texte | `ecart_non_dit` | Pour du jeu compétitif, c'est le taux de rafraîchissement qui compte le plus : le MSI G27C4 E3 monte à 180 Hz, contre 165 Hz pour le Samsung Odyssey G55A | Pour du jeu compétitif, c'est le taux de rafraîchissement qui compte le plus : le MSI G27C4 E3 monte à 180 Hz, contre 165 Hz pour le Samsung Odyssey G55A |
| comparaison | 1 | 2 | texte | `montant_non_fourni` | 8,00 $ | Sur ce critère, le MSI est mieux placé, mais il dépasse votre budget de 8,00 $ |
| desserrage_refuse | 1 | 1 | texte | `ecart_non_dit` | **Asus TUF Gaming VG279QM1A**, id monitor-9b319219eb, à 229,00 dollars, 27 pouces, 280 Hz, dalle IPS | **Asus TUF Gaming VG279QM1A**, id monitor-9b319219eb, à 229,00 dollars, 27 pouces, 280 Hz, dalle IPS |
| desserrage_refuse | 1 | 1 | texte | `ecart_non_dit` | **Asus TUF Gaming VG279QM1A**, id monitor-9b319219eb, à 229,00 dollars, 27 pouces, même 280 Hz, dalle IPS | **Asus TUF Gaming VG279QM1A**, id monitor-9b319219eb, à 229,00 dollars, 27 pouces, même 280 Hz, dalle IPS |
| desserrage_refuse | 1 | 1 | texte | `ecart_non_dit` | **LG 27GP750-B**, id monitor-fab2487414, à 226,99 dollars, 27 pouces, 240 Hz, dalle IPS | **LG 27GP750-B**, id monitor-fab2487414, à 226,99 dollars, 27 pouces, 240 Hz, dalle IPS |
| desserrage_refuse | 1 | 1 | texte | `ecart_non_dit` | **LG 27GP750-B**, id monitor-fab2487414, à 226,99 dollars, 27 pouces, 240 Hz, dalle IPS | **LG 27GP750-B**, id monitor-fab2487414, à 226,99 dollars, 27 pouces, 240 Hz, dalle IPS |
| desserrage_refuse | 1 | 1 | texte | `montant_non_fourni` | 26,99 dollars | **LG 27GP750-B**, id monitor-fab2487414, à 226,99 dollars, 27 pouces, 240 Hz, dalle IPS |
| desserrage_refuse | 1 | 1 | texte | `montant_non_fourni` | 26.99 $ | Il dépasse votre budget de 26.99 $ |
| desserrage_refuse | 1 | 1 | texte | `montant_non_fourni` | 29,00 dollars | **Asus TUF Gaming VG279QM1A**, id monitor-9b319219eb, à 229,00 dollars, 27 pouces, même 280 Hz, dalle IPS |
| desserrage_refuse | 1 | 1 | texte | `montant_non_fourni` | 29.00 $ | Il dépasse votre budget de 29.00 $ |
| desserrage_refuse | 1 | 2 | texte | `ecart_non_dit` | **Asus TUF Gaming VG279QM1A**, id monitor-9b319219eb, à 229,00 dollars, 27 pouces, 280 Hz, dalle IPS | **Asus TUF Gaming VG279QM1A**, id monitor-9b319219eb, à 229,00 dollars, 27 pouces, 280 Hz, dalle IPS |
| desserrage_refuse | 1 | 2 | texte | `ecart_non_dit` | **LG 27GP750-B**, id monitor-fab2487414, à 226,99 dollars, 27 pouces, 240 Hz, dalle IPS | **LG 27GP750-B**, id monitor-fab2487414, à 226,99 dollars, 27 pouces, 240 Hz, dalle IPS |
| desserrage_refuse | 2 | 1 | texte | `ecart_non_dit` | **Asus TUF Gaming VG279QM1A** (monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz, dalle IPS | **Asus TUF Gaming VG279QM1A** (monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz, dalle IPS |
| desserrage_refuse | 2 | 1 | texte | `ecart_non_dit` | **Asus TUF Gaming VG279QM1A** (monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz, dalle IPS | **Asus TUF Gaming VG279QM1A** (monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz, dalle IPS |
| desserrage_refuse | 2 | 1 | texte | `ecart_non_dit` | **LG 27GP750-B** (monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz, dalle IPS | **LG 27GP750-B** (monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz, dalle IPS |
| desserrage_refuse | 2 | 1 | texte | `ecart_non_dit` | **LG 27GP750-B** (monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz, dalle IPS | **LG 27GP750-B** (monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz, dalle IPS |
| desserrage_refuse | 2 | 1 | texte | `montant_non_fourni` | 26,99 $ | **LG 27GP750-B** (monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz, dalle IPS |
| desserrage_refuse | 2 | 1 | texte | `montant_non_fourni` | 26,99 $ | **LG 27GP750-B** (monitor-fab2487414) — 226,99 $, 27 pouces, 240 Hz, dalle IPS |
| desserrage_refuse | 2 | 1 | texte | `montant_non_fourni` | 29,00 $ | **Asus TUF Gaming VG279QM1A** (monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz, dalle IPS |
| desserrage_refuse | 2 | 1 | texte | `montant_non_fourni` | 29,00 $ | **Asus TUF Gaming VG279QM1A** (monitor-9b319219eb) — 229,00 $, 27 pouces, 280 Hz, dalle IPS |
| desserrage_refuse | 3 | 2 | texte | `ecart_non_dit` | **Asus TUF Gaming VG279QM1A** — 229,00 $ | **Asus TUF Gaming VG279QM1A** — 229,00 $ |
| desserrage_refuse | 3 | 2 | texte | `ecart_non_dit` | **LG 27GP750-B** — 226,99 $ | **LG 27GP750-B** — 226,99 $ |
| sur_specifie | 1 | 1 | texte | `valeur_non_fournie` | 500 Hz | Ensuite, et c'est plus embêtant : 500 Hz n'existe pas dans ce catalogue d'écrans |
| sur_specifie | 1 | 1 | texte | `valeur_non_fournie` | 500 Hz | Ensuite, sur les 500 Hz que vous demandez : en sondant les fréquences de rafraîchissement disponibles dans ce catalogue, je ne vois rien qui s'en approche |
| sur_specifie | 2 | 1 | texte | `montant_non_fourni` | 400 dollars | Les autres critères sont bien notés : 27 pouces minimum, 500 Hz minimum, et un budget de 400 dollars, tous bloquants |
| sur_specifie | 2 | 1 | texte | `valeur_non_fournie` | 27 pouces | Les autres critères sont bien notés : 27 pouces minimum, 500 Hz minimum, et un budget de 400 dollars, tous bloquants |
| sur_specifie | 2 | 1 | texte | `valeur_non_fournie` | 500 Hz | Les autres critères sont bien notés : 27 pouces minimum, 500 Hz minimum, et un budget de 400 dollars, tous bloquants |
| sur_specifie | 3 | 1 | texte | `montant_non_fourni` | 400 dollars | J'ai bien noté vos critères : un écran d'au moins 27 pouces et 500 Hz, avec un budget maximum de 400 dollars |
| sur_specifie | 3 | 1 | texte | `valeur_non_fournie` | 27 pouces | J'ai bien noté vos critères : un écran d'au moins 27 pouces et 500 Hz, avec un budget maximum de 400 dollars |
| sur_specifie | 3 | 1 | texte | `valeur_non_fournie` | 500 Hz | J'ai bien noté vos critères : un écran d'au moins 27 pouces et 500 Hz, avec un budget maximum de 400 dollars |
| sur_specifie | 3 | 2 | texte | `valeur_non_fournie` | 500 Hz | Je viens de vérifier la répartition des fréquences de rafraîchissement dans le catalogue des écrans, et je dois être honnête avec vous : aucun écran n'atteint 500 Hz |

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

**69 valeur(s) chiffrée(s)** sur 12 tour(s) de domaine.

**question_de_domaine.1, tour 2** — 7 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.
>
> Ce que je peux vous dire, c'est ce que contient le catalogue correspondant à votre recherche : sur les 9 écrans dans votre budget, 6 sont en dalle VA et 3 en dalle IPS. Les trois que je vous ai recommandés — l'ASRock Phantom Gaming PG27FRS1A, l'Acer Nitro EDA270U P et le MSI MAG 274CQF — sont tous les trois en VA.
>
> Si vous voulez comparer avec une dalle IPS, je peux vous chercher les modèles correspondants et vous donner leurs prix et caractéristiques exactes.

**question_de_domaine.1, tour 3** — 3 chiffre(s)

> Je n'ai pas de chiffre de contraste dans le catalogue. Le sondage me donne le type de dalle et la fréquence de rafraîchissement, pas le taux de contraste : aucun produit de la liste ne porte cette donnée. Je ne vais donc pas vous avancer un chiffre "typique", ce ne serait pas fourni par le catalogue.
>
> Ce que je peux vous confirmer, c'est la répartition parmi les 9 écrans de votre recherche : 6 en dalle VA, 3 en dalle IPS. Si vous voulez, je peux vous détailler les modèles IPS pour comparer prix et fréquence de rafraîchissement avec les VA déjà proposés.

**question_de_domaine.2, tour 2** — 8 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.
>
> Ce que je peux vous dire, c'est ce qu'il y a dans votre sélection actuelle : sur les 9 écrans de 27 pouces et plus qui correspondent à votre recherche, 6 sont en dalle VA et 3 en dalle IPS.
>
> Parmi les trois écrans que je vous ai proposés, les trois sont en VA : l'ASRock Phantom Gaming PG27FRS1A, l'Acer Nitro EDA270U P et le MSI MAG 274CQF. Si vous voulez comparer avec une dalle IPS dans votre budget, je peux creuser ce côté-là, dites-moi.

**question_de_domaine.2, tour 3** — 3 chiffre(s)

> Je n'ai pas de chiffre de contraste dans le catalogue. Ce n'est pas une caractéristique que je peux vous sortir, et je ne vais pas vous donner un chiffre "typique" inventé.
>
> Ce que j'ai sous les yeux, c'est le type de dalle, pas son contraste : sur les 9 écrans de votre sélection, 6 sont en VA et 3 en IPS. C'est tout ce que je peux affirmer avec certitude.

**question_de_domaine.3, tour 2** — 3 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.
>
> Ce que je peux vous dire, c'est ce qu'il y a dans votre sélection actuelle : sur les 9 écrans qui correspondent à votre recherche, 6 sont en dalle VA et 3 en dalle IPS. Sur les trois que je vous ai proposés, tous sont en VA.
>
> Si le type de dalle compte pour vous, dites-le-moi et je peux filtrer là-dessus.

**question_de_domaine.3, tour 3** — 3 chiffre(s)

> Je ne peux pas vous donner un chiffre de contraste pour les dalles VA. Le catalogue que j'ai sous les yeux ne contient pas cette donnée : je vois le type de dalle (panel_type), la taille, la résolution, la fréquence de rafraîchissement, le temps de réponse pour certains modèles — mais pas de valeur de contraste. Je ne vais pas vous donner un chiffre "typique" trouvé ailleurs, ce ne serait pas fiable.
>
> Ce que je peux vous confirmer, c'est la répartition dans votre sélection : 6 écrans en dalle VA, 3 en dalle IPS, sur les 9 qui correspondent à vos critères actuels.

**question_de_domaine.4, tour 2** — 9 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.
>
> Ce que je peux vous dire, c'est ce qu'il y a dans le catalogue correspondant à votre recherche : sur les 9 écrans de 27 pouces et 144 Hz minimum dans votre budget, 6 sont en dalle VA et 3 en dalle IPS.
>
> Parmi les trois que je vous ai proposés, l'ASRock Phantom Gaming PG27FRS1A, l'Acer Nitro EDA270U P et le MSI MAG 274CQF sont tous les trois en VA. Si vous préférez une dalle IPS, je peux vous chercher les modèles correspondants.

**question_de_domaine.4, tour 3** — 3 chiffre(s)

> Je ne peux pas vous donner un chiffre de contraste. Le catalogue ne contient pas cette information, pour aucun écran, VA ou IPS. Je ne vais pas vous inventer une valeur "typique", ce serait vous induire en erreur.
>
> Ce que le catalogue me donne, c'est le type de dalle et la répartition : sur les 9 écrans de votre recherche, 6 sont en VA et 3 en IPS. Rien de plus précis sur le contraste n'est disponible.
>
> Si le contraste est un critère important pour vous, je ne pourrai pas filtrer dessus faute de données. En revanche, je peux continuer à comparer les écrans sur ce que j'ai réellement : résolution, fréquence de rafraîchissement, temps de réponse, prix.

**question_de_domaine.5, tour 2** — 9 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.
>
> Ce que je peux vous dire, c'est ce que contient le catalogue correspondant à votre recherche : sur les 9 écrans de 27 pouces et plus à 144 Hz et plus, 6 sont en dalle VA et 3 en dalle IPS.
>
> Parmi les trois que je vous ai proposés dans votre budget, l'ASRock Phantom Gaming PG27FRS1A, l'Acer Nitro EDA270U P et le MSI MAG 274CQF sont tous les trois en VA. Si la dalle IPS vous intéresse en particulier, je peux regarder ce que le catalogue propose dans ce type-là, dites-moi.

**question_de_domaine.5, tour 3** — 5 chiffre(s)

> Le catalogue ne donne pas de chiffre de contraste pour les dalles. Ce champ n'existe pas dans les fiches produits que j'ai sous les yeux.
>
> Je ne peux donc pas vous donner un chiffre pour le contraste d'une dalle VA, ni en général ni pour un modèle précis. Ce que je sais dire, c'est la répartition par type de dalle parmi les écrans qui correspondent à votre recherche : 6 en VA, 3 en IPS, sur les 9 écrans de 27 pouces et plus à 144 Hz et plus.
>
> Si vous voulez, je peux vous montrer les modèles en IPS pour comparer, mais je ne pourrai pas vous donner de chiffre de contraste dessus non plus.

**question_de_domaine.6, tour 2** — 8 chiffre(s)

> Je ne vais pas vous inventer un cours sur les dalles.
>
> Ce que je peux vous dire, c'est ce qu'il y a dans votre sélection actuelle : sur les 9 écrans qui correspondent à votre recherche, 6 sont en dalle VA et 3 en dalle IPS.
>
> Parmi les trois écrans que je vous ai proposés, l'ASRock Phantom Gaming PG27FRS1A, l'Acer Nitro EDA270U P et le MSI MAG 274CQF sont tous les trois en VA. Si la dalle IPS vous intéresse particulièrement, je peux vous montrer les modèles correspondants, mais je vérifie d'abord s'ils tiennent dans votre budget et vos 144 Hz minimum avant de vous les citer.

**question_de_domaine.6, tour 3** — 8 chiffre(s)

> Le contraste n'est pas une donnée que j'ai dans le catalogue. Je ne vais pas vous donner un chiffre qui n'en vient pas.
>
> Ce que je peux vous dire, c'est ce que le catalogue contient réellement : type de dalle, taille, résolution, fréquence de rafraîchissement, temps de réponse, prix. Le contraste n'y figure pas, donc je ne peux ni vous le confirmer ni vous l'approcher.
>
> Si vous voulez, on reste sur les critères que j'ai sous les yeux pour trancher entre vos trois écrans en VA : l'ASRock Phantom Gaming PG27FRS1A à 142.99 $, l'Acer Nitro EDA270U P à 179.99 $, et le MSI MAG 274CQF à 189.99 $, ce dernier avec un temps de réponse de 0.5 ms, le seul renseigné parmi les trois.

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
| puce | 12 |
| liste numérotée | 0 |
| titre | 0 |
