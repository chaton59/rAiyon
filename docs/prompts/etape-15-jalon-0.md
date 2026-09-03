# Prompt Claude Code — Étape 15, jalon 0 : l'instrument, et aucun modèle n'est appelé

> À coller tel quel dans Claude Code, à la racine du dépôt `rAiyon`.
> Point de départ : `main`, commit `fc10e3d`, arbre propre.
> **Ce jalon ne consomme aucun jeton et n'appelle aucune API.** Si une commande te
> demande `ANTHROPIC_API_KEY`, c'est que tu es sorti du périmètre.

---

## Où on en est

L'étape 14 est close. `make check` vert à 906, `make test-int` à 98, `make eval` vert.
L'étape 15 construit une **variante machine à états**, mise en concurrence avec l'agent
sur les mêmes scénarios et le même tableau de métriques. Elle ne remplace pas l'agent :
les deux doivent rester lançables et mesurables après l'étape.

Le fait qui rend cette étape possible aujourd'hui, et qui n'était pas prévu : **le harnais
d'éval est déjà agnostique à l'orchestration.** `raiyon/eval/executeur.py` ne connaît que
la signature de `session.tour()` — `Generator[Evenement, None, IssueDuTour]` — et tout ce
que `metriques.py` mesure se dérive de deux choses : la suite d'`Evenement` et les
`messages` persistés. Aucune mesure ne lit `boucle.py`.

Ce jalon **modifie le harnais et prouve que la modification est neutre**, avant que quoi
que ce soit d'autre bouge. C'est le motif du jalon 0 de l'étape 13, repris parce qu'il a
fonctionné.

---

## Le périmètre, en négatif — à lire avant d'écrire une ligne

**Ne touche pas** : `src/raiyon/matching/`, `src/raiyon/tools/`, `src/raiyon/validateur/`,
`src/raiyon/agent/boucle.py`, `src/raiyon/agent/session.py`, `prompts/`, `alembic/`,
`data/`, `catalogue/`.

**Ne réécris aucune cassette.** Aucun fichier sous `evals/cassettes/` ne doit apparaître
dans `git status` à la fin de ce jalon. C'est la vérification principale de la porte de
sortie, et elle est absolue.

**N'écris pas la machine à états.** Elle est le jalon 1 et le jalon 2. Ici, on prépare
l'instrument qui la mesurera, et rien d'autre.

---

## A. `RAIYON_ORCHESTRATION` dans `config.py`

Ajoute à `Settings` un champ `orchestration`, valeurs `agent` ou `machine`, **défaut
`agent`**, validé par un `Literal` ou un motif comme l'est déjà `prompt_systeme`.

`config.py` est le **point unique de lecture de l'environnement** dans ce projet — la
variable ne se lit nulle part ailleurs, et surtout pas par un `os.environ` opportuniste
dans `scripts/eval.py`.

⚠️ **Ce jalon ajoute la variable et ne la consomme pas encore.** `session.tour()` ne
bascule sur rien : il n'existe qu'une orchestration. La variable existe pour que le champ
d'en-tête du point B ait une source, et pour que le jalon 2 n'ait pas à toucher
`config.py` en même temps qu'il écrit un orchestrateur. Écris-le dans le commentaire du
champ, sans quoi un relecteur croira à un branchement oublié.

---

## B. `EnTete.orchestration` — un fait enregistré, jamais réécrit

Ajoute `orchestration: str | None = None` à `EnTete` dans `raiyon/eval/cassette.py`.

**Le précédent existe et il faut le suivre à la lettre : `usage`.** Il est optionnel,
absent n'est pas une erreur, présent-mais-mal-formé est refusé, et — c'est le point
essentiel — **`en_json()` l'omet quand il vaut `None`**. Applique exactement le même
traitement :

* `_entete()` ne l'ajoute pas à la liste des champs obligatoires ; `brut.get(...)` rend
  `None` quand il est absent ;
* `en_json()` n'écrit la clé **que** si elle n'est pas `None`, via le même motif de
  dictionnaire conditionnel que `usage` ;
* la valeur `None` **reste `None` en mémoire**. Elle ne devient jamais la chaîne `"agent"`
  dans la dataclass.

⚠️ **C'est la contrainte non négociable de ce point, et elle a une raison écrite.** §7 dit
que `make eval-etape12` « échoue le jour où quelqu'un modifie v1 en place » : cette cible
existe pour attraper une modification de l'archive. Un défaut qui se matérialiserait dans
la dataclass finirait par être **réécrit** au premier aller-retour de sérialisation, et on
aurait modifié l'archive en croyant la lire — sans que personne l'ait décidé.

La lecture « une cassette sans `orchestration` est une cassette d'agent » est donc faite
**là où on s'en sert** — la garde du point C, l'en-tête du rapport — et jamais dans la
structure. Elle est vraie : les 79 cassettes du dépôt sont toutes des cassettes d'agent.

Écris-la à l'endroit où elle est faite, avec sa date, pas comme une évidence.

Côté écriture : `scripts/eval.py`, sur le chemin `enregistrer`, renseigne le champ depuis
`get_settings().orchestration`. Toute cassette produite à partir de maintenant le porte.

---

## C. La garde de contamination à l'enregistrement, et son angle mort

`enregistrer` **refuse** si le jeu visé contient déjà des cassettes dont l'`orchestration`
diffère de celle en cours. Le message nomme le jeu, les deux valeurs, et la variable à
poser — même forme que les messages de péremption d'empreinte, qui donnent la commande à
taper.

Pour la comparaison, une cassette sans champ compte comme `agent`.

**Ce que la garde protège** : les réenregistrements et les `SCENARIO=` partiels, qui sont
précisément là où la variable se rate. Le Makefile porte déjà l'avertissement jumeau pour
`RAIYON_PROMPT_SYSTEME` — « sans elle, une campagne v2 écrirait dans
`evals/cassettes/systeme.v1/` » —, et c'est le même mode d'échec.

⚠️ **Ce qu'elle ne protège pas, et écris-le dans son commentaire** : la **première**
campagne d'un jeu. Le répertoire est vide, il n'y a rien à comparer, la garde ne tire pas
— et c'est l'enregistrement le plus cher du projet et le plus susceptible de partir avec
la mauvaise variable. Ce qui couvre ce cas est le **tir d'essai du jalon 4** : douze
appels sur `hors_catalogue` seul, dont la porte de sortie vérifie que l'en-tête porte bien
`orchestration: machine`. Les deux mécanismes sont complémentaires, et le commentaire doit
le dire pour que personne ne croie la garde plus large qu'elle n'est et ne saute le tir
d'essai en s'appuyant dessus.

Un test pur couvre les trois cas : jeu vide (passe), jeu homogène (passe), jeu mélangé
(refuse en nommant les deux valeurs).

---

## D. La mesure nº7 — le coût par tour

C'est une propriété réelle d'une orchestration que les six critères d'acceptation ne
capturent pas du tout, et elle est déjà sur le disque : `entete.usage.appels`.

**Ce qu'elle vaut** : la somme des `appels` des prises du jeu, divisée par le nombre de
tours client. `Mesures.tours` porte déjà ce dénominateur. Pour `v2` : 191 appels pour 102
tours, soit **1,87 appel par tour**.

`mesurer_le_jeu()` lit déjà chaque cassette par `depuis_json()` — l'en-tête est sous la
main dans la boucle, il n'y a aucune plomberie à inventer.

### Trois décisions à écrire, pas à deviner

**1. Le coût ne va pas dans `Mesures`.** Rends-le dans une structure à part, collectée
dans `mesurer_le_jeu()` et rendue à côté de l'agrégat.

*Raison, et c'est l'arbitrage du point* : tout ce que porte `Mesures` est **recalculé à
chaque rejeu** par le vrai moteur, la vraie couche outils et le vrai validateur — c'est
l'arbitrage A de l'étape 12, et c'est ce qui fait qu'un scoring qui change se voit sans
rien réenregistrer. Le coût, lui, est **figé à l'enregistrement** et ne bougera plus
jamais. Poser un nombre de provenance gelée au milieu de nombres qui se recalculent est
exactement le genre de confusion que ce dépôt écrit des paragraphes pour éviter.

*Alternative écartée — l'ajouter à `Mesures`* : moins de plomberie, et la provenance
devient invisible à la lecture du type.

**2. Le rapport dit que ce chiffre a une autre provenance.** Une ligne, à côté du chiffre :
c'est la seule mesure du rapport qui ne vient pas du rejeu mais de l'enregistrement, et
elle ne bouge pas quand le moteur change.

**3. Tout ou rien, jamais une moyenne sur un sous-ensemble.** Publie le coût **seulement
si toutes les prises du jeu portent `usage`**. Sinon, une ligne explicite : « non
disponible — *k* prises sur *n* sans `usage` », et aucun chiffre.

*Raison* : l'état du disque aujourd'hui rend ce cas immédiat, ce n'est pas de la théorie.

| Jeu | Prises avec `usage` | Coût publiable |
|---|---|---|
| `v2` | 36 / 36 | oui — 191 appels |
| `v1-desserrage` | 3 / 3 | oui |
| `v1-etape12` | 0 / 19 | **non** |
| `v1-base` (composé) | 3 / 31 | **non** |

Une moyenne calculée sur 3 prises de `v1-base` et comparée aux 36 de `v2` comparerait des
tailles d'échantillon — c'est la faute que `LISEZMOI.md` interdit déjà pour les totaux.

⚠️ **Et c'est sans conséquence pour l'étape 15** : la comparaison qui compte est `v2`
contre `machine.v1`, et les deux porteront `usage` sur toutes leurs prises. La mesure nº7
fonctionne exactement là où on en a besoin. La ligne « non disponible » n'apparaît que sur
les rapports rétrospectifs, où elle est la vérité.

`comparaison.py` publie l'écart quand les deux jeux le portent, et la ligne « non
disponible » sinon — sans verdict `au-delà` / `dans le bruit` dans ce cas : la dispersion
d'un coût gelé n'a pas de sens, et un verdict calculé dessus serait faux.

---

## E. La réserve sur `iterations`

`rapport.py` publie `iterations`. Chez une machine à états, c'est une **constante**, et sa
variance nulle n'est pas un résultat — c'est une propriété de l'orchestration, connue
d'avance, qui se lirait comme une victoire de stabilité si personne ne l'écrivait.

Ajoute la réserve à côté du tableau où `iterations` apparaît, dans `rapport.py` et dans
`comparaison.py`. Une phrase suffit ; elle doit être là **avant** la campagne, pas ajoutée
quand le chiffre sortira.

---

## F. `PROJET.md` — la propriété rétrospective

Écris dans §5 étape 15 (qui devient une étape en cours, pas une liste d'envies) ce que
`executeur.py` a de particulier :

> Le harnais est agnostique à l'orchestration, et **personne ne l'a conçu pour ça**.
> `executeur.py` ne connaît que la signature de `session.tour()` ; `metriques.py` ne lit
> que les `Evenement` et les `messages` persistés. La propriété vient de ce que trois
> consommateurs indépendants — la console, le fil SSE, l'exécuteur d'éval — ont été écrits
> contre un même générateur, chacun pour sa propre raison.

⚠️ **Écris-la comme une propriété rétrospective, jamais comme une intention.** Le dépôt a
plusieurs précédents de choix relus comme s'ils avaient été prémédités, et c'est
exactement ce qu'il faut ne pas ajouter. La phrase honnête est « on s'en aperçoit à
l'étape 15 », pas « on l'avait prévu ».

Ajoute aussi, dans §4 ou juste après le tableau des critères d'acceptation, la **mesure
nº7** — en disant qu'elle n'est pas un critère d'acceptation : elle n'a pas de seuil, elle
décrit une orchestration, elle ne la valide pas.

---

## G. Une confirmation à faire, pas une modification

`systeme.machine.v1` satisfait le motif de `Settings.prompt_systeme`
(`^[a-z0-9]+(?:[.-][a-z0-9]+)*$`). Vérifie que `jeu_en_vigueur(None, "systeme.machine.v1")`
en dérive bien :

* jeu `machine.v1` ;
* cassettes `evals/cassettes/systeme.machine.v1/` ;
* rapport `docs/eval/rapport.machine.v1.md`.

**Si c'est le cas — et la lecture du code dit que oui — n'écris rien.** L'axe d'identité
des cassettes reste la version de prompt, la machine se désigne par la sienne, et aucune
ligne de `scripts/eval.py` ne change. Rapporte-le simplement dans ton compte rendu.

Si ce n'est pas le cas, **arrête-toi et dis-le** plutôt que d'adapter le code : cela
voudrait dire que l'arbitrage d'axe d'identité de l'étape reposait sur une lecture fausse,
et c'est une décision à reprendre, pas un défaut à contourner.

---

## Porte de sortie

Dans cet ordre.

```bash
make check                    # vert, ≥ 906, plus les tests de la garde du point C
make up && make migrate && make seed
unset ANTHROPIC_API_KEY       # ce jalon ne doit rien appeler
make eval
make eval-etape12
make eval-comparer AVANT=v1-base APRES=v2 Q="contrôle de neutralité du jalon 0"
git status --short
git diff --stat
```

**Ce que le diff doit montrer, et rien d'autre :**

1. **Zéro fichier sous `evals/cassettes/`.** Absolu. Une cassette touchée invalide le
   jalon, quelle que soit la raison invoquée.
2. Les trois rapports et la comparaison modifiés **uniquement** par les lignes du point D
   (le coût par tour, ou son « non disponible ») et la réserve du point E. Aucun autre
   chiffre ne bouge.
3. `make eval` et `make eval-etape12` tournent **sans clé** — c'est la propriété que
   `raiyon/eval/client.py` achète, et le `unset` la vérifie pour de bon plutôt que de la
   supposer.

Un chiffre de rapport qui bouge ailleurs que sur la nouvelle ligne veut dire que le jalon
n'est pas neutre, et c'est précisément ce qu'il est là pour prouver.

Commit à la fin, message qui dit que l'instrument est préparé et qu'aucune orchestration
n'a encore été écrite.

---

## Ce que ce jalon ne décide pas

Quatre arbitrages restent ouverts et **ne se tranchent pas ici**, même si le code semble
en appeler un :

* ce que `decider()` reçoit en entrée — jalon 1 ;
* si l'appel de rédaction voit l'historique — jalon 2 (la réponse est oui, et elle sera
  motivée là-bas) ;
* où va la note de double application du prompt dérivé — jalon 3 ;
* la dérivation de `systeme.machine.v1.md` elle-même — jalon 3.

Si l'un d'eux te paraît nécessaire pour finir ce jalon, **c'est le signe que tu débordes**.
Arrête-toi et dis-le.
