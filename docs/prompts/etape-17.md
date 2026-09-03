# Prompt Claude Code — Étape 17 : le correctif de `NOMBRE`, et une dette reclassée

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.
> Point de départ : étape 16 close et committée, `make check` vert à 1008.
> **Zéro appel API.** Si tu te retrouves à vouloir réenregistrer une cassette, arrête-toi :
> c'est le signe que le pari de cette étape est faux, et c'est une information, pas un
> obstacle.

---

## Le pari de l'étape, écrit avant de le vérifier

`NOMBRE` a été différé à l'étape 13 avec ce motif :

> « C'est un changement de validateur, il modifie des listes de griefs, donc des reprises,
> donc des empreintes de requête — il périmerait des cassettes. **À livrer avec la prochaine
> campagne, jamais entre deux.** »

**Ce motif a été écrit avant que le mécanisme qui le dispense existe.** `DIVERGENCES_ATTENDUES`
a été construit au jalon 1 de l'étape 13, pour exactement ce cas, et il sert déjà à ça :
le correctif de `valeurs_refusees` a fait diverger `v1-etape12/desserrage_refuse.1`, et la
liste **assertée** l'absorbe depuis.

Le reste est gratuit par construction : l'arbitrage A de l'étape 12 fait relire la prose
par le validateur **courant** à chaque rejeu. Un correctif de validateur se mesure donc sans
qu'une cassette soit réenregistrée — c'est la propriété que le README vend.

⚠️ **Écris ce raisonnement dans `PROJET.md`**, parce que c'est le même motif que la trouvaille
de l'étape 15 sur l'agnosticisme du harnais : une promesse écrite avant l'outil qui la
dispense. Deux occurrences, c'est un motif du parcours, pas une anecdote.

---

## A. Le correctif, déjà rédigé et déjà vérifié

Il est dans `PROJET.md` §7, ligne « `NOMBRE` lit une résolution collée à une fréquence
comme un seul nombre ». **Ne le réinvente pas, applique-le.**

`src/raiyon/validateur/extraction.py`, ligne 74 :

```python
NOMBRE = rf"\d+(?:[{ESPACES}]\d{{3}})*(?:[.,]\d+)?"
```

devient une **alternance** entre la forme séparée et la forme nue :

```python
NOMBRE = rf"(?:\d{{1,3}}(?:[{ESPACES}]\d{{3}})+|\d+)(?:[.,]\d+)?"
```

Le principe : un séparateur de milliers ne suit jamais un groupe de quatre chiffres.
« en 1920x1080 180 Hz » cesse d'être lu comme **1 080 180 Hz**.

⚠️ **La rédaction évidente `\d{1,3}(?:[ESPACES]\d{3})*` est fausse**, et §7 le dit avec ses
contre-exemples : sur `9333` elle lit `933` puis `3`, sur `1080 180` elle lit `108` puis
`0 180`. C'est l'alternance qui garde `1 299,99` **et** `9333` intacts tout en séparant
`1080` de `180`.

`NOMBRE` est composé dans `MOTIF_MONTANT`, `MOTIF_UNITE` et les deux motifs d'intervalle.
Le groupe de capture des motifs composés doit rester **celui qu'il était** — l'alternance
introduit un groupe, et il est non capturant. Vérifie-le sur les quatre motifs, pas
seulement sur `MOTIF_NOMBRE`.

### Les tests

Un test par forme, sur les six que §7 nomme, et il énonce le cas plutôt que le motif :
`1 299,99`, `9333`, `1920x1080 180 Hz`, `417.14`, `1080 180`, `144`. Ce sont les six qui ont
servi à valider la rédaction avant qu'elle soit écrite dans §7 ; les rejouer ici les rend
opposables.

---

## B. Ce qu'il faut constater, dans cet ordre

```bash
unset ANTHROPIC_API_KEY
make check
make eval                                          # v2 — la ligne de base de l'étape 15
RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval # machine.v1
make eval-etape12
```

Trois choses à relever, **avant** de commiter quoi que ce soit :

1. **Combien de cassettes divergent, et lesquelles.** §7 situe les deux griefs concernés
   dans `categorie_efface_budget.3` : une seule cassette v2 est attendue.
2. **De combien le compte de griefs baisse, jeu par jeu.** C'est l'effet du correctif, et il
   se lit sans rien réenregistrer.
3. **Le jeu `machine.v1` est le point de vigilance.** Ses 17 rejets par passe sont dominés
   par `ecart_non_dit`, pas par `valeur_non_fournie`, donc le risque est faible — mais il
   n'est pas nul, et il n'a pas été mesuré.

### ⛔ La règle d'arrêt

> **Si plus de deux cassettes de `machine.v1` divergent, arrête-toi et rapporte sans
> commiter.**

La comparaison `v2` / `machine.v1` est l'artefact principal du projet. Un correctif de faux
positif ne vaut pas de l'éroder, et le motif de renoncement est écrit d'avance pour ne pas
être négocié devant le résultat.

---

## C. `DIVERGENCES_ATTENDUES`

Une entrée par cassette qui diverge, avec sa raison **complète** : quel grief tombe,
pourquoi la reprise change, pourquoi la réponse enregistrée n'est pas celle que le modèle
aurait donnée. Prends l'entrée existante comme modèle — elle est de la bonne longueur.

⚠️ **C'est une assertion, pas un skip.** La liste échoue si une divergence annoncée n'a pas
lieu, si une cassette listée n'existe pas, ou si une divergence non listée survient. Ne la
relâche pas.

---

## D. La dette nº1 est reclassée, pas reportée une troisième fois

**Ne la commence pas.** Ce jalon la **ferme comme non fermée**, avec son chiffre.

Réécris sa ligne de §7. Ce qu'elle doit dire :

* le correctif est écrit et tient en une suppression : `DESCRIPTION_SONDER` et
  `DESCRIPTION_PRECISION` portent des règles de dialogue que le prompt système redit ;
* `schema_outils.py` est dans le préfixe mis en cache, et `outils_empreinte` se calcule sur
  `schema_des_outils()` — **les cinq définitions, y compris pour la machine**, qui n'en
  expose qu'une (découvert au jalon 4 de l'étape 15). Toucher une description périme donc
  **les deux jeux** ;
* le coût de fermeture est de **~366 appels** — ~190 pour v2, ~176 pour `machine.v1` — soit
  plus que l'étape 15 entière ;
* **le report l'a rendue deux fois plus chère.** Quand elle a été différée à l'étape 13, il
  y avait un jeu ; il y en a deux. Rien n'a rendu le défaut plus grave ;
* la dette elle-même dit qu'« on ne savait pas laquelle des deux rédactions portait
  l'effet » : on paierait ~366 appels pour un effet que personne ne sait prédire.

**Conclusion à écrire telle quelle** : dette connue, correctif écrit, **coût de fermeture
supérieur au coût du défaut, non fermée pour cette raison**. C'est une décision datée, pas
un renvoi — et la différence est qu'un renvoi se reconduit tout seul, une décision se
rouvre en la contredisant.

⚠️ Retire la ligne de la liste de ce que le dépôt « s'est engagé à traiter », partout où
elle y figure — README compris. Un engagement qu'on a décidé de ne pas tenir et qu'on
continue d'afficher est pire que pas d'engagement du tout.

---

## E. Le défaut de quoting du Makefile, qui roule avec

Deux fois en deux étapes, et les deux sont de moi. Après le `\` sur les lignes `@#`, les
apostrophes : `make eval-comparer AVANT=v1-base APRES=v2 Q="l'effet…"` casse, parce que la
recette passe `--question '$(Q)'` et que l'apostrophe ferme la chaîne.

Passe à `--question "$(Q)"`. La limite se déplace vers les guillemets doubles, incomparablement
plus rares qu'une apostrophe en français. **Écris la limite résiduelle en commentaire** plutôt
que de laisser croire que c'est réglé.

---

## Porte de sortie

```bash
make check                              # vert, ≥ 1008 + les six tests de forme
make test-int                           # 98
unset ANTHROPIC_API_KEY
make eval && make eval-etape12
RAIYON_PROMPT_SYSTEME=systeme.machine.v1 make eval
make eval-comparer AVANT=v2 APRES=machine.v1 Q="ce que la comparaison committée demande"
git status --short
```

1. **Aucun fichier sous `evals/cassettes/`.** Le pari de l'étape est là : un correctif de
   validateur se livre sans réenregistrer.
2. Les rapports bougent — c'est **voulu**, c'est l'effet mesuré du correctif — et le compte
   de griefs baisse. Dis de combien, jeu par jeu, dans le compte rendu.
3. Au plus **deux** cassettes de `machine.v1` divergent, sinon rien n'est committé (point B).
4. §7 porte la ligne `NOMBRE` **fermée** et la ligne dette nº1 **reclassée avec son
   chiffre**.
5. Le README ne promet plus la dette nº1.

⚠️ **Relance `make eval-comparer` avec la question déjà committée dans
`comparaison.v2-machine.v1.md`**, pas avec une nouvelle. La question est un input du
fichier : la changer ferait bouger une ligne qui n'a rien à voir avec le correctif. C'est
la règle que tu as appliquée d'toi-même à l'étape 16, et elle vaut ici aussi.

Commit à la fin.

---

## Ce qui reste après, et qui n'est plus une dette

* `orchestration/blocs.py` importe encore `agent.evenements` et `agent.prompts` — reste de
  nommage, pas de couplage, écrit dans la ligne §7 fermée à l'étape 16 ;
* `systeme.machine.v2`, si l'extraction atomique valait qu'on y revienne ;
* la recherche hybride `pgvector` (§3.5), hors périmètre du produit livrable.
