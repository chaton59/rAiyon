# Prompt Claude Code — Correctif de l'étape 9 : la question d'`ask_clarification`

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

L'étape 9 est livrée et commitée : validateur, cinq règles, neuf pièges détectés, six
sorties légitimes acceptées, une régénération observée en production. Il reste **un trou
que tu as toi-même signalé au §7**, et on le ferme maintenant plutôt qu'à l'étape 12.

**La question d'`ask_clarification` n'est validée par rien.** Elle est un *argument
d'outil*, pas un bloc `text` : elle sort de `demander_precision`, la boucle la rend au
client verbatim, et `valider()` ne la voit jamais. Le modèle peut donc écrire
« le Samsung Odyssey G50A à 199 $ te conviendrait, ou tu préfères plus grand ? » et cette
phrase part telle quelle. C'est le critère nº1 percé sur son chemin le plus fréquent — une
conversation contient beaucoup plus de questions que de recommandations.

Trois choses à livrer, dans cet ordre. Les deux dernières sont petites, et elles ne sont
pas là par confort : **valider les questions rend leurs défauts plus probables**, parce
qu'une question mêle naturellement un produit, un budget et une fourchette dans la même
phrase.

## Avant d'écrire

Relis `src/raiyon/agent/boucle.py` (le chemin `question is not None`),
`src/raiyon/validateur/` en entier, et `PROJET.md` §5 étape 9 (arbitrages A à E) et §7.

---

## 1. Valider la question, avec les règles existantes et rien de neuf

### Où — dans la boucle, jamais dans l'outil

`demander_precision` reste pure et ignorante du contexte fourni. Lui passer un
`ContexteFourni` casserait l'arbitrage C de l'étape 7 (les outils ne prennent que ce
qu'ils lisent dans l'état) et le test d'isolation SDK. **La validation vit dans
`boucle.py`**, juste après `_executer_les_appels`, avant `yield QuestionPosee`.

### Contre quel contexte — le même instantané que le texte

Le contexte accumulé **avant** les `tool_result` du message courant. Raison : le modèle a
écrit sa question sans avoir vu ces résultats-là. Élargir le contexte à ce qu'il n'avait
pas sous les yeux validerait une affirmation qu'il ne pouvait pas fonder — c'est
exactement la règle déjà retenue pour le texte à l'arbitrage A, et **c'est la même règle,
pas une seconde**.

### Quelles règles — les cinq, telles quelles

La question est de la prose française qui peut nommer un produit, un prix, une spec. Rien
ne justifie un jeu de règles parallèle, et un second jeu finirait par diverger du premier
(le raisonnement de `erreurs.py`). N'en écris aucune de nouvelle.

### Texte et question sont validés **séparément**, contre le même instantané

*Alternative écartée — les concaténer et ne valider qu'une fois.* Ce serait plus proche de
ce que le client lit d'un seul tenant. Écartée parce qu'elle obligerait à retarder
l'émission du texte jusqu'**après** l'exécution des outils : le préambule arriverait après
`[critères]` et `[sondage]`, et l'arbitrage A perdrait la propriété qui le rendait
acceptable — les événements d'outils vivent pendant que la prose se fait attendre, pas
l'inverse.

⚠️ **Conséquence assumée, à écrire :** un produit hors budget nommé dans le texte dont
l'écart ne serait donné que dans la question déclencherait la règle 4. Le prompt système
ne demande jamais de citer un produit dans un préambule de question, donc le cas ne
devrait pas se produire ; s'il se produit, c'est un signal, pas un faux positif.

### La régénération — le mécanisme existe déjà, ne l'invente pas

Sur rejet, le tour **ne se clôt pas**. Le bloc `user` de reprise contient les
`tool_result` du message (celui d'`ask_clarification` compris — il est terminal, pas
absent) **puis** le grief, dans cet ordre : c'est l'arbitrage D, inchangé.

Le budget est **partagé avec celui du texte** : `max_regenerations` vaut pour le tour, pas
par nature de sortie. Un budget par nature doublerait le pire cas d'appels API et donnerait
deux compteurs à réconcilier à l'étape 12.

**Le repli d'une question rejetée deux fois est la phrase générique, jamais le template de
recommandation.** Répondre par un classement de produits à quelqu'un qu'on était en train
d'interroger n'a aucun sens ; `repli.py` choisit donc selon ce qui a été rejeté, pas
seulement selon l'existence d'une recherche en session.

### Traçabilité

`TexteRejete` gagne `origine: OrigineRejet` (`TEXTE` | `QUESTION`). Sans elle, l'étape 12
ne pourra pas dire *où* le modèle hallucine, et c'est précisément la métrique qui décide
quoi corriger dans le prompt à l'étape 13.

---

## 2. Le budget de session est admis dans une phrase qui nomme un produit

C'est le faux positif nº3 de ton rapport : « le X à 249,99 $, dans votre budget de 400 $ »
lève un grief. Aujourd'hui c'est rare ; **dès que les questions sont validées, ça devient
la formulation naturelle** — « le X à 249,99 $ rentre dans tes 400 $, tu veux que je
regarde plus grand ? ».

Correctif étroit, dans la branche « phrase à produit » de la règle 2 : outre le prix exact
du produit nommé et son `ecart_usd`, **le budget de la session** est admis.

Justification, et elle n'est pas de commodité : le budget n'est pas un fait du catalogue,
c'est **une parole du client**, entrée par `record_criteria` et rendue dans son
`tool_result`. Le §2 interdit au modèle d'inventer un fait ; répéter au client le montant
qu'il vient d'annoncer n'en est pas un.

⚠️ **N'élargis rien d'autre.** Les bornes d'agrégat restent interdites dans une phrase à
produit : c'est le piège nº6, et c'est le seul test de l'étape qui échoue si quelqu'un
aplatit le contexte. Le budget est un montant unique et attribuable ; une fourchette de
sondage ne l'est pas.

Ajoute `budget_usd: Decimal | None` à `ContexteFourni`, dérivé des `tool_result` de
`record_criteria` — **pas** de `EtatSession`. Le contexte fourni décrit ce que le modèle a
vu, et il se construit toujours depuis ce qui lui a été envoyé.

---

## 3. L'unité se propage dans « entre A et B *unité* »

Trou observé **en vrai** dans ta conversation : « entre 65 et 400 dollars » quand la borne
valait 64,98 $. « 400 dollars » a été vérifié, « 65 » non — c'est un entier nu, exempté.
Or 65 est un **arrondi**, c'est-à-dire une affirmation approximative sur le catalogue :
exactement ce que §7 reproche déjà aux paliers arrondis qu'on avait refusé de faire rendre
par `probe_catalog`. Le validateur laissait passer ce qu'un arbitrage de l'étape 7 avait
refusé de produire.

Correctif borné, dans `extraction.py` : dans un motif `entre A et B <unité>` (unité au sens
large : `$`, `dollars`, `Hz`, `Go`…), **A hérite de l'unité de B** et cesse d'être un
entier nu.

Ne va pas plus loin. L'exemption générale de l'entier nu **reste** — « je te propose trois
modèles » ne doit toujours pas lever de grief — et la ligne du §7 qui la documente reste
vraie, précisée d'une exception. Une seule forme est traitée parce qu'une seule a été
observée ; élargir à « de A à B », « A–B », « autour de A » serait de la théorie.

---

## Tests attendus

`tests/validateur/test_pieges.py` — trois pièges de plus, contre un contexte fixe :

10. Un prix inventé **dans une question** : « le Samsung Odyssey G50A à 199 $ te
    conviendrait ? » → `prix_etranger_au_produit`.
11. Un produit inventé **dans une question**.
12. « entre 65 et 400 dollars » quand la borne fournie vaut 64,98 → `montant_non_fourni`.
    C'est la reproduction du cas de terrain ; nomme le test d'après lui.

`tests/validateur/test_faux_positifs.py` — trois sorties légitimes de plus :

7. Une question qui nomme un produit réel avec son prix exact.
8. « le X à 249,99 $, dans ton budget de 400 $ » → **zéro grief** (correctif 2).
9. « entre 108 et 400 dollars » avec les deux bornes exactes → zéro grief. La propagation
   d'unité doit **valider** autant qu'elle refuse ; un test qui ne montre que le refus
   laisserait passer une propagation qui casse les cas justes.

`tests/agent/test_validation.py` — quatre cas de plus, avec le faux client :

1. Question rejetée → `TexteRejete(origine=QUESTION)`, un second appel, question valide →
   `QuestionPosee`. **Deux appels, pas trois.**
2. Question rejetée deux fois → `Repli(motif=VALIDATION)` avec la **phrase générique**, et
   **pas** le template de recommandation, même quand une recherche a eu lieu dans la
   session.
3. Le bloc `user` de reprise contient le `tool_result` d'`ask_clarification` **avant** le
   grief. L'assertion d'appairage de l'étape 8 reste verte.
4. Texte rejeté puis question rejetée dans le même tour → le budget est épuisé au premier,
   la question part au repli sans second appel. C'est le test qui prouve que le budget est
   partagé.
5. Aucune `QuestionPosee` n'est émise avant validation — le pendant du test « le texte
   n'est jamais émis avant d'être validé ».

## Porte de sortie

- `make check` vert, sans base ni clé. `make test-int` vert.
- Les douze pièges détectés, les neuf sorties légitimes acceptées.
- Une conversation console avec `--trace` où une question passe la validation. Si tu
  arrives à en faire rejeter une en vrai, colle-la : ça vaut plus qu'une fixture.

## Documentation

1. `PROJET.md` §5 étape 9 : une sous-section « correctif — la question d'ask_clarification
   est validée », avec les trois points et leurs alternatives écartées.
2. **§7** : la ligne « la question d'`ask_clarification` n'est validée par rien » est
   **éteinte**, marquée comme telle et non effacée. La ligne sur l'entier nu est
   **précisée** : l'exemption demeure, sauf dans un intervalle où l'unité se propage — et
   elle porte désormais sa preuve de terrain (« 65 » pour 64,98 $).
3. La ligne « la règle 2 crie sur une phrase que le prompt n'interdit pas » disparaît des
   points à surveiller : elle est fermée par le correctif 2. Dis pourquoi le budget est
   admis et pourquoi une fourchette de sondage ne l'est pas — c'est la même distinction
   que le piège nº6, et c'est ce qui empêchera quelqu'un d'élargir « pour faire pareil ».

## Méthode

Les correctifs 2 et 3 d'abord, avec leurs tests : ce sont des fonctions pures, et une fois
justes le correctif 1 n'est qu'un branchement. Ne touche ni au prompt système v1, ni à
`tools/`, ni au moteur. Ne commence pas l'étape 10.
