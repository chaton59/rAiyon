# Prompt Claude Code — Étape 7 : couche outils et invariants

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`. Les étapes 1 à 6 sont franchies : le catalogue
est en base (1 026 produits, seed committé et déterministe) et le moteur de matching
est écrit, calibré et testé — 310 tests purs, 47 d'intégration, **aucun appel LLM nulle
part dans le projet à ce jour**. Tu vas réaliser **l'étape 7 et rien d'autre**.

## Avant d'écrire quoi que ce soit

Lis, dans cet ordre :

1. `PROJET.md` — §2 (contrainte non négociable), §3.6 (orchestration : les garanties
   vivent dans les outils), §3.7 (les outils exposés), §3.9 (le nombre de questions),
   §3.10 (budget et zone de tolérance), §3.12 (événements typés), §3.15, §3.16
   (frontière SQL/Python), §4 (critères d'acceptation), §5 étape 6 — en particulier
   les arbitrages **D, E, J, K, L** et la section « Pour l'étape 7 — l'importance d'un
   critère est collante » —, §5 étape 7, §6, §7, §8.
2. `catalogue/schema_attributs.md` — source de vérité des rôles.
3. `src/raiyon/matching/attributs.py` puis `moteur.py`. **Ta couche est leur seule
   cliente.** Lis aussi `criteres.py`, `depot.py`, `relachement.py`, `trace.py`.
4. `src/raiyon/db/models.py` — `SessionConversation` (colonnes `budget_usd` et
   `criteres_valides` JSONB) et `TourConversation`. **Tu ne les modifies pas** et tu
   n'écris rien en base à cette étape ; tu arrêtes seulement la **forme** du JSONB.
5. `src/raiyon/config.py`, `tests/conftest.py`, `tests/test_isolation_passe_a.py`
   (tu vas en reprendre le mécanisme), `Makefile`.

Trois constats de lecture déjà faits, que tu n'as pas à redécouvrir :

- `Critere` interdit les doublons sur `(champ, opérateur)` mais **autorise `au_moins`
  et `au_plus` sur le même champ**. Un critère de session peut donc être un
  intervalle : la fusion travaille sur la clé `(champ, opérateur)`, jamais sur le
  champ seul.
- `resoudre_critere()` lève déjà des messages **rédigés pour être lus par le modèle**
  (« Repasser en 'important' »). Tu prolonges cette convention, tu ne l'inventes pas.
- **Les vocabulaires fermés ne sont pas dans le code.** `schemas.py` ne porte en
  `Literal` que `type` (disque, casque) et `enclosure_type`. `chipset` (241 valeurs),
  `microarchitecture`, `interface`, `panel_type`, `form_factor`, `ddr_generation` ne
  vivent que dans les données. Le schéma JSON **ne peut donc pas** les énumérer, et
  c'est ce qui rend `sonder_catalogue` structurellement indispensable : l'agent
  découvre les valeurs, puis choisit dedans.

## Périmètre — ce que tu livres

- **A. Un état de session pur** : `EtatSession`, la fusion des critères, la règle de
  collant, la forme JSONB de `criteres_valides`.
- **B. Les cinq outils**, en fonctions Python testables, plus leur sérialisation en
  `tool_result`.
- **C. Le schéma JSON des outils**, **dérivé du registre d'attributs**, jamais écrit
  à la main.
- **D. L'extension du dépôt aux agrégats** (comptages, fourchettes, distributions),
  côté SQL, et le calcul du champ le plus discriminant, côté Python pur.
- **E. Les tests hostiles**, et la mise à jour de `PROJET.md`.

**Explicitement hors périmètre, à ne pas commencer :** la boucle agent et le prompt
système (étape 8), le validateur (étape 9), l'API et la persistance (étape 10).
Aucun appel LLM. **Aucune écriture SQLAlchemy** : `EtatSession` est une dataclass
pure, la persistance est le travail de l'étape 10 — mais la forme du JSONB est
arrêtée maintenant, pour qu'aucune migration ne soit nécessaire alors.

Ne modifie ni `schemas.py`, ni `models.py`, ni les migrations, ni les modules de
`matching/` — **sauf** `depot.py`, que tu étends par de nouvelles méthodes sans
toucher aux existantes, et le `Protocol` `DepotProduits` qui les déclare.

## Arbitrages déjà rendus — applique-les, ne les rediscute pas

Chacun a été pesé contre son alternative. Tu recopies la décision **et** l'alternative
écartée dans la docstring du module concerné, comme le fait déjà `matching/`.

### A. La règle de collant est portée par un **jeton de parole par tour client**

La couche outils reçoit un `tour_client: int`, **fourni par l'appelant** (l'étape 8),
jamais calculé par elle : elle n'a ainsi aucune notion d'horloge et les tests injectent
des entiers.

Un mouvement qui **desserre** consomme le jeton du tour. Un second desserrage dans le
même tour est **refusé**. L'état mémorise `tour_du_dernier_desserrage: int | None`.

*Alternative écartée — exiger une citation verbatim d'un message `user`.* Elle donne
l'illusion d'une preuve : le modèle peut citer « je peux monter un peu », prononcé à
propos du budget, pour desserrer la fréquence. Le jeton ne prouve pas que le client a
parlé **de ce critère**, mais il borne le nombre de desserrages par parole, ce qui tue
l'essai-erreur — le vrai mode d'échec que §3.6 cherche à empêcher.

⚠️ **La faiblesse est réelle et va au §7 des risques :** rien ne détecte qu'un
desserrage autorisé par une parole a été appliqué à un autre critère que celui dont le
client parlait. Un desserrage par tour au lieu de zéro contrôle est un progrès, pas une
garantie.

### B. Une règle unique : **desserrer consomme, resserrer est libre**

Le texte de l'étape 6 ne parlait que de l'importance. C'était insuffisant : après un
zéro résultat, passer `au_moins 144` à `au_moins 120` obtient exactement ce que la
rétrogradation obtenait, sans toucher à l'importance. Retirer le critère fait pire.

Écris **une seule fonction pure** :

```python
def desserre(avant: Critere | None, apres: Critere | None, attribut: Attribut) -> bool
```

> Un mouvement desserre s'il peut faire remonter un produit qui ne remontait pas.

Elle se dérive de l'opérateur et du registre, jamais d'une liste écrite à la main :

| mouvement | verdict |
| --- | --- |
| ajout d'un critère sur un champ libre | resserre — **libre** |
| retrait d'un critère | **desserre** |
| baisse d'importance (`bloquant` > `important` > `souhait`) | **desserre** |
| hausse d'importance | resserre — libre |
| `au_moins` : valeur qui baisse | **desserre** |
| `au_plus` : valeur qui monte | **desserre** |
| `egal` : toute valeur différente | **desserre** (on ne peut pas savoir) |
| changement d'opérateur sur le même champ | traité comme retrait + ajout → **desserre** |
| budget qui monte, ou qui passe à `None` | **desserre** |
| budget qui baisse, ou posé depuis `None` | resserre — libre |

### C. Les outils de recherche ne prennent **aucun critère**

C'est l'arbitrage structurant de l'étape. Les critères entrent par **une seule porte**,
`enregistrer_criteres`. `sonder_catalogue`, `question_suivante` et `rechercher_produits`
ne prennent **aucun argument de critère, ni de budget, ni de catégorie** : ils lisent
l'état de session.

*Alternative écartée — les outils prennent des critères et le code les clampe contre la
session (l'esquisse de §3.6).* Un tour de moins, mais l'invariant redevient une garde à
écrire, à tester et à ne jamais oublier sur un futur outil. Le raisonnement retenu est
celui de §3.10 sur le budget : **une contrainte qui n'a qu'un seul chemin ne peut pas
diverger d'elle-même.** La porte de sortie de l'étape change alors de nature — « les
arguments hostiles ne franchissent pas l'invariant » devient « il n'existe pas
d'argument par lequel passer ».

⚠️ À dire honnêtement dans `PROJET.md` : on ne supprime pas la garde, on la **concentre**
dans `enregistrer_criteres`, qui devient le seul endroit où la règle de collant mord.

**Conséquence sur §3.7 : les quatre outils deviennent cinq.** Écris l'amendement.

### D. L'état est **indexé par catégorie**, le budget est global et **remis à `None`** au changement de catégorie

Forme de `criteres_valides` en JSONB :

```json
{
  "categorie_courante": "monitor",
  "criteres": {
    "monitor": [{"champ": "refresh_rate", "operateur": "au_moins",
                 "valeur": "144", "importance": "bloquant"}],
    "video-card": []
  },
  "optimisation": "aucune",
  "tour_du_dernier_desserrage": 3
}
```

Un client qui revient à l'écran retrouve ce qu'il avait dit. Cela ne crée **aucun
panier** : aucune somme n'est suivie, l'invariant « un tour, une catégorie » tient, et
§8 reste vrai mot pour mot.

Le budget garde sa **colonne** (`sessions.budget_usd`) et n'est pas dupliqué dans le
JSONB — c'est la raison écrite au §3.10 et dans `models.py`, deux copies divergent. Il
est **global à la session**, et **le changement de catégorie le remet à `None`**.

*Alternative écartée — le budget survit au changement de catégorie.* Une question de
moins à poser, donc une métrique nº3 flattée ; mais un client qui a dit « 300 $ pour
l'écran » verrait cette contrainte s'appliquer à son SSD, c'est-à-dire une contrainte
qu'il n'a jamais posée. C'est exactement ce que §2 interdit, appliqué à un critère au
lieu d'un fait.

*Alternative écartée — un état plat vidé à chaque changement de catégorie.* Plus simple
d'une ligne, mais il perd ce que le client a déjà dit et forcerait une migration du
JSONB dès que le besoin apparaîtrait.

### E. Un tour, une catégorie — la garde vit ici

Le moteur garantit qu'**un appel** rend une seule catégorie. Il ne garantit rien sur
**un tour** : rien n'empêche l'agent d'appeler `rechercher_produits` deux fois dans le
même tour sur deux catégories et de rédiger la « config gaming » que §8 met hors
périmètre.

`rechercher_produits` **refuse** une recherche sur une catégorie différente de celle
déjà cherchée dans le même `tour_client`, avec un message qui dit à l'agent de
séquencer. `sonder_catalogue` et `question_suivante` restent libres : ils ne rendent
aucun produit, donc ils ne peuvent rien faire citer.

C'est ce qui rend le critère d'acceptation nº2 vérifiable **produit par produit**, sans
notion de panier.

### F. Un schéma JSON **unique**, et `valeur` est **toujours une chaîne**

- **Un seul schéma pour tous les outils, pas un par catégorie.** L'`enum` des champs est
  l'**union** des champs utilisables des six catégories (~40 entrées) ; la validation
  par catégorie se fait à l'exécution, avec le message du registre. *Alternative
  écartée — un schéma par catégorie* : l'`enum` serait plus courte et le modèle se
  tromperait moins, mais la définition des outils changerait en cours de conversation,
  ce qui **casse le cache de prompt** (§3.13) à chaque fois que le client change de
  sujet.
- **`valeur` est typée `string` dans le schéma, toujours**, et convertie par le code
  selon le genre que le registre déclare. *Alternative écartée — une union
  `bool | number | string`* : elle est mal supportée par le sous-ensemble de JSON Schema
  admis en mode `strict`. Le précédent existe déjà dans le projet — le JSONB sérialise
  les `Decimal` en chaînes pour la même raison — et `_convertir()` est déjà écrit.
  Ajoute la conversion depuis le texte (`"true"`/`"false"`, `Decimal(str(...))`) et
  laisse `_convertir()` faire le reste.
- Les descriptions des champs du schéma sont **dérivées** de `libelle_fr` et `unite`
  du registre. Aucune n'est écrite à la main : un test vérifie que le schéma couvre
  **exactement** les champs utilisables du registre (rôle ≠ `affichage`, `impose` faux,
  hors `CHAMPS_A_CHAMP_DEDIE`).

⚠️ **Avant d'écrire quoi que ce soit sur `strict`** : vérifie ce que la version du SDK
`anthropic` **réellement installée** (`uv pip show anthropic`) accepte, et lis sa
documentation locale. Le projet s'est fait piéger trois fois par une capacité supposée
disponible et jamais vérifiée — `smt` à l'étape 3, `temperature=0` à l'étape 5,
`nom_fr` à l'étape 5. Si `strict` n'est pas disponible tel qu'attendu, **écris-le dans
`PROJET.md`** au lieu de contourner en silence. Tu n'appelles évidemment pas l'API.

### G. `sonder_catalogue` : agrégats exacts, troncature déclarée, budget appliqué

C'est ici que la leçon de l'étape 6 mord — **du code qui décide de ce qui sera affirmé
au client.**

- **Le budget s'applique**, sinon « il te reste 12 modèles » désigne des produits que le
  client ne peut pas acheter. Par symétrie avec §3.10, le sondage rend **deux comptes
  séparés** : dans le budget, et dans la zone de tolérance.
- **La troncature se déclare.** 241 chipsets ne rentrent pas. L'outil rend les 15
  valeurs les plus fréquentes, **et** `total_distinct` **et** `tronque: bool`. Ces deux
  champs sont **toujours présents**, y compris quand il n'y a rien à dire — même
  contrat que `ecartes_faute_de_donnee` au §3.16. Sans eux, l'agent écrirait « les
  chipsets disponibles sont… » et ce serait faux par omission.
- **L'ordre est total** : fréquence décroissante, puis valeur croissante. Aucune réponse
  client ne doit dépendre de l'ordre de retour de Postgres.
- **Les agrégats comptent comme contexte fourni**, et l'étape 9 les vérifiera comme
  tels. *Alternative écartée — rendre des paliers arrondis pour empêcher l'agent de
  déduire un prix exact.* ⚠️ Le risque est réel et va au §7 : avec deux ou trois
  sondages resserrés, l'agent connaît le prix d'un produit qu'on ne lui a jamais donné,
  sans identifiant. Mais un arrondi est lui-même une affirmation approximative sur le
  catalogue, et il en fabrique une pour en éviter une autre. La contrainte est portée
  par le prompt de l'étape 8 (« une fourchette de sondage n'est jamais le prix d'un
  produit ») et vérifiable à l'étape 9.
- **`sonder_catalogue` ne peut structurellement pas rendre de produit** : son type de
  retour ne porte ni identifiant, ni nom, ni ligne de catalogue. Un test le constate sur
  le type, pas sur une exécution.

### H. `question_suivante` : entropie pondérée par la couverture, et le budget en cas spécial

- **Elle ne rend aucune phrase.** Champ, libellé, unité, valeurs atteignables (même
  contrat de troncature qu'en G), et le score. C'est l'agent qui écrit la question
  (§3.14 arbitrage I de l'étape 6 : le français est du vocabulaire, pas des phrases).
  Nomme la fonction interne `champ_le_plus_discriminant()` ; le nom exposé au modèle
  reste `suggest_next_question`.
- **Mesure : entropie de Shannon normalisée** sur la distribution des valeurs du
  sous-catalogue courant, **multipliée par le taux de couverture réel du
  sous-catalogue** (produits déclarant la valeur / total). Sans cette pondération,
  l'outil proposerait de demander une vitesse de rotation à un client dont 66 % des
  candidats sont des SSD, et la réponse écarterait des produits sur une **absence de
  donnée**. *Alternative écartée — « le champ qui coupe le plus près de la moitié »* :
  correct sur un booléen, inutilisable au-delà de deux valeurs.
- ⚠️ **Limite à écrire, pas à masquer** : l'entropie sur les valeurs distinctes est
  grossière pour un champ numérique continu (`price_per_gb`, `core_clock`), où chaque
  produit a presque sa propre valeur et l'entropie est donc maximale. Écarte du calcul
  les champs dont le nombre de valeurs distinctes dépasse la moitié du nombre de
  candidats — un champ que personne ne partage ne discrimine rien d'utile à demander.
  Le découpage en classes est hors périmètre.
- **Cas spécial du budget** : si `budget_usd is None`, l'outil rend le budget **en
  tête**, dans un champ typé distinct (pas déguisé en attribut — `prix_usd` est dans
  `CHAMPS_A_CHAMP_DEDIE`), avec la fourchette de prix du sous-catalogue. C'est presque
  toujours la question à plus fort gain, et c'est celle que le client attend.
- **Répartition §3.16** : `GROUP BY` en SQL, entropie et classement en **Python pur**,
  sur des comptages injectables — comme `relachement.py`.

### I. `demander_precision` est un outil **terminal**

*Alternative écartée — le garder tel que §3.7 le décrit, un outil qui ne rend rien et
n'existe que pour être tracé.* Il force un aller-retour API supplémentaire et invite le
modèle à appeler l'outil **puis** à réécrire la question en texte : la question est
posée deux fois.

`demander_precision(question: str, champ_vise: str | None)` rend `{"ok": true,
"terminal": true}` et **marque le tour comme clos**. L'étape 8 renverra le texte de
l'argument au client au lieu de relancer une génération. La question devient une donnée
typée — utile aussi pour l'événement SSE de §3.12 et pour la métrique nº3, qui est un
critère d'acceptation.

Tu écris la convention et le drapeau ; c'est l'étape 8 qui les consommera.

### J. `rechercher_produits` rend le **produit entier**

Toutes les specs, plus la trace. *Alternative écartée — réduire le produit aux champs
cités par la trace, plus les champs d'affichage.* Elle rendrait **impossible**
d'affirmer une spec dont la pertinence n'a jamais été établie, et coûterait moins de
jetons. Elle est écartée parce qu'elle coupe la comparaison spontanée (« celui-ci a en
plus du HDMI 2.1 »), qui est un bon comportement de vendeur, et parce que l'étape 9
valide de toute façon ce qui est **cité**. Décision assumée avec sa contrepartie, pas
restriction par prudence.

## Structure attendue

```
src/raiyon/tools/
    etat.py            # EtatSession, Mouvement, desserre(), fusionner() — pur
    schema_outils.py   # génération du schéma JSON depuis le registre — pur
    outils.py          # les cinq outils + leur sérialisation en tool_result
    erreurs.py         # OutilRefuse, avec un code et un message lisible par le modèle
src/raiyon/matching/
    depot.py           # étendu : agrégats, distributions, couverture
    sondage.py         # entropie, classement, champ le plus discriminant — pur
tests/tools/
    test_etat.py  test_collant.py  test_schema.py  test_outils.py  test_hostile.py
tests/matching/test_sondage.py          # pur, comptages injectés
tests/integration/test_agregats.py      # marqueur `integration`
```

## Conventions à tenir

- **Aucun module de `raiyon.tools` ne charge le SDK `anthropic`.** Reprends le
  mécanisme de `tests/test_isolation_passe_a.py` : découverte des modules **sur le
  disque** et non écrite à la main, un interpréteur neuf par module, et la
  contre-épreuve qui importe `anthropic` directement. La couche outils doit être
  testable sans clé, et il ne faut pas que ça dépende de la discipline.
- **`rechercher()` appelle `get_settings()` pour la tolérance**, donc exige une clé.
  Les outils propagent le paramètre `tolerance` injectable jusqu'aux tests. Aucun test
  de `tests/tools/` ne doit avoir besoin de `.env`.
- **Un refus de jeton n'est pas une erreur.** `enregistrer_criteres` réussit, applique
  ce qui était légitime, et rend `mouvements_refuses: [{champ, motif}]` dans son
  résultat. L'agent peut alors dire au client « je garde 144 Hz tant que tu ne me dis
  pas le contraire ». Une erreur, elle, arrête l'outil : c'est `OutilRefuse`, réservé à
  ce que le modèle doit **corriger** (champ inconnu, opérateur incompatible, promotion
  interdite, deux catégories dans un tour). Son message est pédagogique et dit quoi
  faire — la convention de `resoudre_critere()`.
- **Les outils rendent des dataclasses typées**, et **une seule fonction** les sérialise
  en dictionnaire pour le `tool_result`. Les tests assertionnent sur les objets, pas
  sur du JSON.
- Docstrings dans le style du dépôt : la décision, sa raison, et l'alternative écartée.
  Français partout, `mypy --strict` propre, `ruff` propre.

## Tests attendus — les arguments hostiles, un par un

`tests/tools/test_hostile.py` couvre au minimum, chacun nommé d'après ce qu'il empêche :

1. Le modèle tente d'élargir le budget en cours de tour → refusé (jeton déjà consommé,
   ou refus si aucune parole).
2. Catégorie inexistante.
3. Champ d'une autre catégorie (`screen_size` sur un `cpu`).
4. Champ d'affichage (`color`, `nom`, `id`) posé en critère.
5. `prix_usd`, `categorie` ou `disponible` posés en critère.
6. Promotion `bloquant` sur un attribut de rôle `score` (`boost_clock`).
7. Rétrogradation `bloquant` → `souhait` sans nouvelle parole.
8. **Desserrage de valeur après un zéro résultat** (`au_moins 144` → `au_moins 120`
   dans le même tour) — le test le plus important de l'étape.
9. Retrait d'un critère bloquant dans le même tour.
10. Deux catégories cherchées dans le même tour.
11. Critères contradictoires (`au_moins 200` et `au_plus 100`) : **pas d'erreur**, zéro
    résultat et un diagnostic. Une contradiction est une réponse, pas un bug.
12. Opérateur incompatible avec le genre (`au_moins` sur `interface`).
13. Valeur non convertible (`"beaucoup"` sur un numérique, `"peut-être"` sur un
    booléen).
14. Doublon `(champ, opérateur)`.
15. `sonder_catalogue` ne peut pas rendre de produit — vérifié **sur le type de
    retour**, pas sur une exécution.
16. Deux desserrages légitimes dans **deux tours différents** passent tous les deux —
    la règle borne l'essai-erreur, elle ne gèle pas la conversation.

## Porte de sortie

- `make check` vert : lint, `mypy --strict`, et la suite pure — **sans base, sans
  conteneur, sans clé API**.
- `make test-int` vert pour les agrégats.
- Les seize tests hostiles passent.
- Le test d'isolation confirme qu'aucun module de `raiyon.tools` ne charge le SDK.

C'est le critère d'acceptation nº2 franchi **au niveau structurel, avant même qu'un LLM
existe dans le projet**.

## Documentation — à écrire dans le même commit

1. `PROJET.md` §5 étape 7 passe en ✅, avec les arbitrages **A à J** ci-dessus, chacun
   avec son alternative écartée, dans le style des treize arbitrages de l'étape 6.
2. **Amendement du §3.7** : les quatre outils deviennent **cinq**, et `ask_clarification`
   devient terminal. Écris pourquoi, ne réécris pas l'histoire.
3. **Nouvelle décision §3.17 — la règle de collant et le jeton de parole.** C'est une
   décision d'architecture, pas un détail d'implémentation : elle mérite son numéro.
4. **Quatre lignes au §7 (risques)**, et aucune n'est cosmétique :
   - le jeton de parole ne vérifie pas que le client a parlé **de ce critère** ;
   - `sonder_catalogue` est un oracle à prix : l'agent peut connaître un prix sans
     identifiant, et le prompt de l'étape 8 est la seule atténuation ;
   - l'entropie sur un champ numérique continu est grossière, et l'exclusion par
     nombre de valeurs distinctes est un seuil, pas une théorie ;
   - la garde de l'arbitrage C **concentre** l'invariant dans `enregistrer_criteres` au
     lieu de le supprimer.
5. Une section « ce que l'étape a appris, et qui n'était pas prévu » — le dépôt en a une
   à chaque étape, et elle a trois fois valu plus que le code livré.

## Méthode

Un jalon à la fois. Montre-moi le résultat de A (l'état pur et la règle de collant)
avant d'écrire les outils : c'est la partie où une erreur se propage partout. À chaque
décision structurante que je n'ai pas déjà tranchée ci-dessus, expose l'alternative et
le compromis **avant** de trancher, et dis-moi explicitement quand un choix est risqué
ou fragile.

Ne commence pas l'étape 8. Aucun prompt système, aucune boucle d'agent, aucun appel API.
