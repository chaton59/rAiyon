# Prompt Claude Code — Étape 9 : validateur anti-hallucination

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.

---

Tu travailles sur le dépôt `rAiyon`. Les étapes 1 à 8 sont franchies : catalogue en base,
moteur de matching calibré, couche outils portant les invariants, et depuis l'étape 8 une
boucle d'agent qui tourne pour de vrai — 514 tests purs, 67 d'intégration, une
conversation console de bout en bout qui aboutit à des produits réels.

**Aujourd'hui, le §2 du projet — « le LLM ne produit jamais un fait » — ne repose que sur
le prompt système.** §3.11 promet trois niveaux cumulés ; seul le premier existe. C'est la
ligne de risque la plus grave du §7, et c'est ce que tu fermes.

Tu vas réaliser **l'étape 9 et rien d'autre**.

## Avant d'écrire quoi que ce soit

Lis, dans cet ordre :

1. `PROJET.md` — §2, §3.10, §3.11, §3.12, §3.13, §3.14, §4 (critères 1, 2 et 6), §5
   étapes 7, 8 et 9, §6, §7 (les lignes « `probe_catalog` est un oracle à prix » et « le
   texte sortant n'est validé par rien »), §8.
2. `src/raiyon/agent/boucle.py` en entier, puis `evenements.py`, `session.py`,
   `prompts.py`. **Tu vas modifier `boucle.py`** : c'est le seul module de l'étape 8 que
   tu touches en profondeur.
3. `src/raiyon/tools/outils.py` — surtout `en_tool_result()` : c'est **le format exact**
   que ton validateur relira.
4. `src/raiyon/matching/moteur.py` (`ResultatMatching`, `ProduitHorsBudget`) et
   `trace.py` (`TraceProduit`, `LigneTrace`, `Statut`) — le repli sur template s'écrit à
   partir d'eux.
5. `src/raiyon/catalogue/schemas.py` — `MOTIF_ID`, `ProduitEnBase`, `LIBELLES_CATEGORIE`.
6. `prompts/systeme.v1.md`.

### Constats de lecture déjà faits

1. `MOTIF_ID = r"^[a-z-]+-[0-9a-f]{10}$"`. Les identifiants sont donc **reconnaissables
   par motif** dans un texte libre, sans ambiguïté avec du français.
2. `en_tool_result()` sérialise tous les `Decimal` **en chaînes** (`"108.00"`). Les
   comparaisons du validateur se font en `Decimal`, jamais en flottant.
3. `ResultatSondage` porte `fourchette_prix`, `dans_le_budget`,
   `dans_la_zone_de_tolerance` et les valeurs distinctes par champ. **Ce sont des faits
   fournis**, mais ils ne sont attribuables à aucun produit — c'est tout l'enjeu de la
   règle 2.
4. `ProduitHorsBudget` porte `ecart_usd` exact. Le prompt système exige déjà de dire « de
   combien » : la règle 4 rend cette exigence vérifiable.
5. Dans `boucle.py`, le texte est aujourd'hui émis **avant** l'exécution des outils, et un
   commentaire dit que c'est ce qui rend le streaming substituable à l'étape 10. Cet
   arbitrage est **renversé** par l'arbitrage A ci-dessous. Ne le supprime pas : réécris-le
   en disant qu'il a été renversé et pourquoi.

## Périmètre — ce que tu livres

- **A.** Le contexte fourni, **typé par provenance**, accumulé sur la session.
- **B.** L'extraction : identifiants, montants, valeurs unitaires, découpage en phrases.
- **C.** Les cinq règles, chacune rendant un grief lisible.
- **D.** La régénération (une seule) et le repli sur template.
- **E.** Le branchement dans `boucle.py`, texte bufferisé.
- **F.** Les fixtures piégeuses, les fixtures légitimes, et `PROJET.md`.

**Hors périmètre :** l'API FastAPI et le SSE (étape 10), le front (étape 11), le harnais
d'éval et les cassettes (étape 12). **Tu ne modifies pas** `matching/`, `catalogue/`,
`tools/`, ni `db/models.py`, ni les migrations. Tu ne changes **pas** le prompt système
v1 : son évaluation appartient à l'étape 13, et le modifier maintenant rendrait
incomparable ce que l'étape 12 mesurera.

---

## Arbitrages déjà rendus — applique-les, ne les rediscute pas

### A. Le texte est bufferisé, validé, puis émis. §3.11 gagne contre §3.12.

**Valider après génération et streamer le texte au client sont incompatibles** : on ne
rattrape pas une phrase déjà affichée. Personne ne l'avait écrit, et c'est l'arbitrage
structurant de cette étape.

Retenu : dans `boucle.py`, le texte d'un message assistant est **concaténé, validé, puis
émis**. Les événements d'outils (`CriteresMisAJour`, `Sondage`, `QuestionSuggeree`,
`ProduitsTrouves`) continuent d'arriver au fil de l'eau : le panneau de §3.12 vit pendant
l'attente, seule la prose arrive d'un bloc.

*Alternative écartée — streamer le texte et corriger à l'écran après coup.* Meilleure
latence perçue, mais le client voit une affirmation puis sa rétractation : c'est §2 pris à
l'envers, et une démonstration qui montrerait un prix faux pendant deux secondes ne
démontrerait rien.

⚠️ **Deux conséquences à écrire, pas à taire :**

1. À l'étape 10, `Texte` reste **un** événement et non une suite de deltas. La promesse de
   l'arbitrage 1 de l'étape 8 — « l'étape 10 remplace le producteur sans que le
   consommateur bouge » — reste vraie pour tous les autres événements et **devient fausse
   pour celui-là**. Dis-le dans `PROJET.md` §5 étape 8, en amendement.
2. La raison nº1 de la docstring de `QuestionPosee` (« le préambule n'est pas connu au
   moment où le texte est lu, en streaming ») **n'est plus vraie** : le texte est
   désormais connu en entier avant d'être émis. La raison nº2 (le double affichage) suffit
   à elle seule et reste valable. Corrige la docstring plutôt que de la laisser
   s'appuyer sur un fait renversé.

### B. Le contexte fourni est typé par **provenance**, pas aplati en sac de nombres

C'est le piège de l'étape, et il est déjà visible dans la conversation de l'étape 8 : le
sondage a rendu la fourchette `108.00 $ – 399.99 $`, et l'AOPEN vaut `108.00 $`. Un
validateur qui vérifie « tout nombre cité apparaît quelque part dans un `tool_result` »
**accepterait** « l'AOPEN est à 108 $ » même si aucune recherche n'avait eu lieu.

```python
@dataclass(frozen=True, slots=True)
class ContexteFourni:
    produits: Mapping[str, ProduitEnBase]        # id → produit, depuis search_products
    hors_budget: Mapping[str, Decimal]           # id → ecart_usd exact
    prix: Mapping[str, Decimal]                  # id → prix, dérivé de produits
    valeurs_de_specs: frozenset[str]             # toute valeur de spec fournie, en texte
    agregats: frozenset[Decimal]                 # bornes de prix et comptages des sondages
```

Il se construit **depuis les `tool_result` de la session**, pas depuis un état interne :
c'est ce qui garantit qu'il décrit ce que le modèle a réellement vu.

**Il est cumulatif sur la session, pas sur le tour.** Un produit rendu au tour 3 et cité
au tour 6 (« je prends le premier ») est légitime. Un contexte par tour rejetterait la
moitié des conversations réelles.

*Alternative écartée — un ensemble plat de tous les nombres fournis.* Vingt lignes de
moins, et il ferme les trois quarts des cas ; mais il laisse ouvert exactement celui que
§7 nomme, et il rendrait fausse la phrase « l'oracle à prix est vérifiable à l'étape 9 ».

### C. Les cinq règles, et ce que chacune ferme

Chaque règle est une fonction pure `(texte, ContexteFourni) -> tuple[Grief, ...]`.
`Grief` porte un code, l'extrait fautif et une phrase qui dit **quoi corriger** — même
convention que `OutilRefuse` : elle sera lue par le modèle.

| # | Règle | Ferme |
|---|---|---|
| 1 | Tout jeton conforme à `MOTIF_ID` doit exister dans `contexte.produits`. | Le produit inventé, l'`id` approximatif |
| 2 | Tout montant en $ **dans une phrase qui nomme un produit** (par son `id` ou son nom) doit être le prix exact de **ce** produit, ou son `ecart_usd`. Un montant dans une phrase sans produit doit être un prix fourni ou une borne d'agrégat fournie. | Le prix modifié, **et le prix de sondage attribué à un produit** |
| 3 | Tout nom de produit fourni qui apparaît dans le texte y apparaît **verbatim** — casse et espaces compris. | La francisation, la réécriture (§3.4ter) |
| 4 | Un produit de `hors_budget` cité doit l'être dans une phrase qui contient son `ecart_usd` exact. | **Le critère d'acceptation nº2, rendu vérifiable par machine** |
| 5 | Tout nombre suivi d'une unité connue (`Hz`, `Go`, `To`, `GHz`, `MHz`, `W`, `"`, `pouces`…) doit être une valeur de spec fournie ou une valeur d'agrégat fournie. | La spec transformée, la spec déduite d'un sondage |

Le découpage en phrases est un `split` sur `.`, `!`, `?` et le saut de ligne. **C'est une
heuristique, pas une analyse syntaxique** — écris-le, et mets-la dans un seul endroit pour
qu'elle soit remplaçable.

**Trou connu et assumé, à écrire au §7 :** un entier nu, sans unité et sans `$`, n'est
vérifié par rien. Sans cette exemption, « je te propose trois modèles » déclencherait un
grief, et un validateur qui crie sur du français correct finit par être débranché. La
conséquence est réelle : « 32 candidats » pourrait être faux sans être détecté.

### D. Une régénération, puis le repli. Et la façon de la demander.

`max_regenerations = 1` dans `config.py` (`RAIYON_MAX_REGENERATIONS`, `ge=0`).

Le grief part **dans le même bloc `user` que les `tool_result`**, après eux :

```python
{"role": "user", "content": [*resultats, {"type": "text", "text": grief}]}
```

C'est ce qui rend la régénération possible même quand le message fautif portait aussi des
`tool_use` : l'API exige les `tool_result` appairés avant tout autre contenu utilisateur.
Quand le message ne portait que du texte, le bloc `user` ne contient que le grief.

Le texte du grief vit dans `prompts/grief.v1.md`, chargé par `agent/prompts.py` comme le
prompt système, avec son empreinte loguée. Il dit ce qui a été détecté, sur quel extrait,
et **quoi faire** — pas « tu as halluciné ».

**Le message fautif reste dans l'historique.** Le retirer casserait l'appairage des
`tool_result` et rendrait le grief incompréhensible. Le modèle voit donc sa propre sortie
rejetée au tour suivant ; c'est acceptable et ça se dit.

Second échec → **repli sur template** : `validateur/repli.py` rédige la recommandation en
Python à partir du dernier `ResultatMatching` de la session — nom verbatim, `id`, prix, et
le « pourquoi » construit depuis les `LigneTrace` de statut satisfait. Texte sec, risque
nul. Si aucune recherche n'a eu lieu dans la session, le repli est la phrase d'excuse
générique, comme celle de `max_iterations`.

`Repli` gagne un champ `motif: MotifDeRepli` (`MAX_ITERATIONS` | `VALIDATION`) — la
métrique de l'étape 12 devra les distinguer, et un `Repli` sans motif l'en empêcherait.

### E. Le validateur est pur, et testable sans clé ni base

Même posture que `matching/` et `tools/` : `ContexteFourni` se construit à partir de
dictionnaires — les `tool_result` déjà sérialisés — et `valider()` ne prend que du texte
et un contexte. Aucun module de `raiyon.validateur` n'importe `anthropic` ni SQLAlchemy,
et le test d'isolation par découverte sur disque doit le couvrir : **étends-le à
`raiyon.validateur`**.

---

## Ce que tu livres, fichier par fichier

```
src/raiyon/validateur/
    contexte.py      # ContexteFourni, construit depuis les tool_result — pur
    extraction.py    # ids, montants, valeurs unitaires, phrases — pur
    regles.py        # les cinq règles, chacune rendant des Grief
    validateur.py    # valider(texte, contexte) -> Verdict ; Grief ; CodeGrief
    repli.py         # rédaction par template depuis ResultatMatching
src/raiyon/agent/
    boucle.py        # texte bufferisé, validé, régénéré une fois, puis repli
    evenements.py    # Repli gagne `motif` ; nouvel événement TexteRejete (trace)
src/raiyon/config.py # max_regenerations
prompts/
    grief.v1.md
tests/validateur/
    test_extraction.py  test_regles.py  test_pieges.py
    test_faux_positifs.py  test_repli.py
tests/agent/
    test_validation.py   # le branchement : régénération, repli, historique valide
```

`TexteRejete(griefs, tentative)` n'est pas du confort : sans lui, `--trace` ne montrerait
pas qu'une régénération a eu lieu, et l'étape 12 devrait deviner un taux qu'on peut
compter. La console l'affiche en `--trace` seulement.

---

## Tests attendus

### Les fixtures piégeuses — `test_pieges.py`

Sorties LLM écrites à la main, chacune contre un contexte fourni fixe. **Toutes
détectées**, et le test est nommé d'après ce qu'il empêche :

1. Prix modifié de 10 $ sur un produit fourni.
2. `id` inexistant, au bon format.
3. Produit entièrement inventé, avec un nom plausible et un prix plausible.
4. Spec transformée : 165 Hz annoncés sur un produit qui en porte 144.
5. **Nom francisé** : « l'Odyssée de Samsung » pour `Samsung Odyssey G50A`.
6. **Le prix du sondage attribué à un produit** — la borne basse d'une fourchette
   présentée comme le prix d'un modèle nommé. C'est le test le plus important de l'étape :
   il échoue si le contexte a été aplati.
7. Produit de `au_dessus_du_budget` cité sans son écart.
8. Produit hors budget cité avec un écart **faux** (« 15 $ de plus » au lieu de 17,14).
9. Une spec déduite d'un sondage : une valeur qui existe dans la distribution rendue par
   `probe_catalog` mais pas chez le produit cité.

### Les faux positifs — `test_faux_positifs.py`, aussi important

Sorties **légitimes** qui doivent passer sans un seul grief :

1. Une recommandation de trois produits, prix et specs exacts, écarts exacts.
2. Un produit du tour 3 cité au tour 6 — le contexte est cumulatif.
3. « Je te propose trois modèles entre 108 et 400 $ » après un sondage : bornes exactes,
   aucun produit nommé dans la phrase.
4. Une phrase sans aucun chiffre.
5. Un entier nu (« trois modèles », « 32 candidats ») — l'exemption assumée.
6. Un prix écrit `417,14 $` à la française quand le contexte porte `"417.14"` — la
   normalisation doit tenir les deux séparateurs.

### Le branchement — `tests/agent/test_validation.py`, avec le faux client

1. Texte valide → un `Texte`, aucun appel supplémentaire.
2. Texte invalide → un `TexteRejete`, un second appel, texte valide → un `Texte`. **Deux
   appels API, pas trois.**
3. Deux échecs → `Repli(motif=VALIDATION)`, tour clos, aucun troisième appel.
4. Le message fautif portait des `tool_use` → le bloc `user` de reprise contient les
   `tool_result` **puis** le grief, dans cet ordre. L'assertion d'appairage de l'étape 8
   reste verte.
5. Repli sans recherche dans la session → la phrase générique, pas une exception.
6. Le texte n'est **jamais** émis avant d'être validé : sur le scénario 3, aucun `Texte`
   n'a été produit.

## Porte de sortie

- `make check` vert — lint, `mypy --strict`, suite pure, **sans base, sans conteneur,
  sans clé**.
- `make test-int` vert.
- Les neuf pièges détectés, les six sorties légitimes acceptées.
- Le test d'isolation couvre `raiyon.validateur`.
- **Une conversation console de bout en bout, avec `--trace`**, qui aboutit à une
  recommandation validée. Colle-m'en la transcription.

C'est le **critère nº1 franchi au niveau du mécanisme**, et le critère nº2 qui cesse
d'être une propriété structurelle du moteur pour devenir aussi une vérification sur la
phrase.

## Documentation — dans le même commit

1. `PROJET.md` §5 étape 9 en ✅, avec les arbitrages A à E et leurs alternatives écartées.
2. **Amendement du §3.11** : les trois niveaux sont là, et le niveau 2 vérifie la
   **provenance**, pas l'appartenance. Écris pourquoi la version « ensemble plat » aurait
   laissé passer l'oracle à prix.
3. **Amendement du §3.12 et du §5 étape 8** : le texte n'est pas streamé, et pourquoi —
   §3.11 et §3.12 étaient en contradiction, personne ne l'avait vu, et c'est §3.11 qui
   gagne.
4. **Mise à jour du §7** : la ligne « le texte sortant n'est validé par rien » est
   **éteinte** (marquée comme telle, pas effacée). La ligne « `probe_catalog` est un
   oracle à prix » passe de « atténuation : le prompt » à « atténuation : la règle 2 ».
   Deux lignes **nouvelles** : le découpage en phrases est une heuristique ; l'entier nu
   sans unité n'est vérifié par rien.
5. Une section « ce que l'étape a appris, et qui n'était pas prévu ».

## Méthode

Un jalon à la fois.

1. **A + B + C d'abord** — contexte, extraction, règles, et leurs tests. Montre-moi les
   neuf pièges et les six faux positifs **avant** de toucher à `boucle.py` : c'est un
   validateur qui crie sur du français correct qui tue le mécanisme, pas un qui en laisse
   passer.
2. Puis **D + E**, le branchement.
3. Puis la conversation de bout en bout.

Expose l'alternative avant de trancher ce que je n'ai pas tranché, et dis-moi
explicitement quand un choix est risqué. Ne commence pas l'étape 10 : aucune route
FastAPI, aucun SSE.
