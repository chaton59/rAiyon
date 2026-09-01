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
| 3 | Délai avant première valeur | médiane ≤ 2 | 0.0 sur 11 prise(s) | ✅ |
| 4 | Le produit attendu est dans le top 3 | ≥ 80 % | 100 % — 6/6 prise(s) à réponse de référence | ✅ |
| 5 | Moteur de matching testable sans API | binaire | hors de ce rapport — `make check` | — |
| 6 | Cas zéro résultat traité proprement | binaire | 6/6 traité(s) | ✅ |

## Ce que le modèle a tenté, et ce qui a fini en repli

| Mesure | Valeur | Seuil |
|---|---|---|
| Taux de rejet du validateur | 11 grief(s) sur 35 tour(s) — 0.31/tour | publié |
| Taux de repli | 0 tour(s) sur 35 — 0 % | publié |
| Itérations par tour | 1 à 4 (médiane 3.0) | publié |
| Prises sans aucune valeur livrée | 5 sur 16 | publié |
| Prises où `suggest_next_question` a signalé le budget manquant | 2 sur 16 | publié — **observation, pas exigence** |

### Rejets par origine et par code

| Origine | Code de grief | Rejets |
|---|---|---|
| texte | ecart_non_dit | 1 |
| texte | montant_non_fourni | 7 |
| texte | valeur_non_fournie | 3 |

### Replis par motif

Aucun repli sur cette exécution.

## Par scénario

| Scénario | Prise | Tours | Questions avant valeur | Attendu top 3 | Rejets | Replis | Itér. | Conforme |
|---|---|---|---|---|---|---|---|---|
| besoin_flou | 1 | 3 | 0 | — | 0 | 0 | 2 à 3 (médiane 3.0) | ✅ |
| besoin_flou | 2 | 3 | 0 | — | 0 | 0 | 3 | ✅ |
| besoin_flou | 3 | 3 | 0 | — | 2 | 0 | 2 à 3 (médiane 3.0) | ✅ |
| budget_absent | 1 | 2 | 0 | oui | 0 | 0 | 2 | ✅ |
| budget_serre | 1 | 2 | 0 | oui | 2 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| budget_serre | 2 | 2 | 0 | oui | 0 | 0 | 2 à 4 (médiane 3.0) | ✅ |
| budget_serre | 3 | 2 | 0 | oui | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| categorie_efface_budget | 1 | 2 | 0 | — | 0 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| changement_davis | 1 | 2 | 0 | oui | 2 | 0 | 3 à 4 (médiane 3.5) | ✅ |
| comparaison | 1 | 2 | 0 | oui | 0 | 0 | 1 à 4 (médiane 2.5) | ✅ |
| desserrage_refuse | 1 | 2 | 0 | — | 4 | 0 | 3 à 4 (médiane 3.5) | ✅ |
| hors_catalogue | 1 | 2 | — | — | 0 | 0 | 1 | ✅ |
| sur_specifie | 1 | 2 | — | — | 0 | 0 | 2 à 4 (médiane 3.0) | ✅ |
| zero_budget_trop_bas | 1 | 2 | — | — | 1 | 0 | 2 à 3 (médiane 2.5) | ✅ |
| zero_budget_trop_bas | 2 | 2 | — | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |
| zero_budget_trop_bas | 3 | 2 | — | — | 0 | 0 | 1 à 3 (médiane 2.0) | ✅ |

## Dispersion, et ce qu'elle ne prouve pas

La température n'est pas fixée (étape 8, arbitrage 12) : **une cassette est un
tirage, pas une espérance.** Trois prises ont été enregistrées sur les scénarios
ci-dessous, pour obtenir un ordre de grandeur du bruit sur les métriques nº3 et nº4.

⚠️ **Trois prises ne sont pas un intervalle de confiance.** C'est un ordre de
grandeur, et c'est déjà infiniment mieux que le plancher de bruit inconnu qu'on
aurait sinon. Un écart de deux prompts inférieur à cet ordre de grandeur n'est pas
un signal.

| Scénario | Prises | Questions avant valeur | Attendu top 3 |
|---|---|---|---|
| besoin_flou | 3 | 0 | — |
| budget_serre | 3 | 0 | 3/3 |
| zero_budget_trop_bas | 3 | — | — |

## Attentes binaires non tenues

Aucune.
