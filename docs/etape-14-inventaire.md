# Inventaire de l'étape 14 — jalon 0

> ⚠️ **Document de travail, destiné à être supprimé.** Il alimente les jalons 1
> (dépérimer) et 2 (compléter), et il disparaît au jalon 3 une fois absorbé dans le
> `README.md`. Ce n'est pas une pièce de documentation du dépôt : ne pas y renvoyer.

**Établi le 2026-09-02**, sur `main` au commit `2c010da`, arbre propre.
**Aucune correction n'a été faite.** Chaque ligne ci-dessous est un constat.

---

## 1. Le clone

### Ce que ce clone est, et ce qu'il n'est pas

**Ce n'est pas une machine vierge.** Trois choses sont partagées avec l'environnement
courant, et elles retirent chacune une classe de défauts du champ de la mesure :

| Partagé | Ce que le clone ne peut donc pas attraper |
|---|---|
| Le cache `uv` | Un `uv sync` qui échouerait sur un réseau lent, un miroir, ou une roue absente pour la plateforme. `make install` a pris **0,67 s**, ce qui n'est pas la durée d'une installation réelle |
| L'image Docker `postgres` déjà tirée | Le `docker pull` de premier lancement, sa durée et son échec possible |
| La clé API, recopiée à la main depuis le `.env` du dépôt d'origine | Rien — mais c'est précisément le geste que le README ne décrit pas (voir 1.4) |

**Autres angles morts, nommés plutôt que tus** : une dépendance système installée à la
main il y a des semaines (`docker`, `git`, `curl`, `make` étaient là) ; une version de
Docker ou de `uv` trop ancienne ; un `~/.netrc` ou un proxy d'entreprise ; un système non
Linux ; un Python système absent — `uv` a réutilisé le CPython 3.12.3 de la machine.

**Ce qu'il a réellement attrapé** : un fichier non committé dont le projet dépendrait
(aucun), une commande du README qui n'existe pas (aucune), un ordre de commandes faux
(aucun), une étape manquante entre deux commandes (**une**, §1.4), un message d'erreur
qui ne dit pas quoi faire (**un**, §1.4), et une divergence de configuration qui change
le produit servi (**une**, §1.5).

### 1.1 Le protocole tel qu'il s'est déroulé

Préalable exécuté avant le clone, pour ne pas fabriquer un faux constat de port occupé :
`docker compose down` dans le dépôt d'origine, puis vérification que 5432 était libre.
Le clone a bien reçu son propre projet Compose (`raiyon-clone`) et son propre volume.

| # | Commande | Sortie | Durée | Note |
|---|---|---|---|---|
| 1 | `git clone <dépôt local> <tmp>/raiyon-clone` | **0** | 0,06 s | `data/raw/` absent, comme le README l'annonce |
| 2 | `make install` | **0** | 0,67 s | crée `.venv`, installe 62 paquets, pose le hook pre-commit, crée `.env` |
| 3 | `make up` | **0** | 5,68 s | volume neuf, healthcheck atteint en 5 points |
| 4 | `make migrate` | **0** | 1,30 s | révisions `0001` puis `0002` |
| 5 | `make seed` | **0** | 0,44 s | `1026 produits relus et revalidés · 0 supprimés · 1026 insérés` |
| 6 | `make check` | **0** | **17,08 s** | `904 passed, 98 deselected in 9.45s` |
| 7 | `make test-int` | **0** | 4,33 s | `98 passed, 904 deselected in 3.60s` |
| 8 | `make fumee` *(clé telle que `make install` la laisse)* | **2** | *non chronométré* | **échec** — voir 1.4 |
| 9 | `make fumee` *(vraie clé injectée)* | **0** | 2,97 s | `✓ Appel abouti · strict: true · outils envoyés : 5 · champs de l'enum : 36` |
| 10 | `make chat` *(un tour, sur stdin)* | **0** | 18,50 s | **conversation fonctionnelle** — 4 itérations, 3 produits + 2 hors budget, prose livrée |
| 11 | `make api` puis `curl -s .../health` | **200** | — | `{"base":true,"prompt":{"version":"systeme.v1","empreinte":"6da03a675684"},"strict":true}` |
| 12 | `curl -X POST .../sessions` | **201** | — | `{"id":"…"}` |
| 13 | `curl -N -X POST .../sessions/<id>/messages` | **200** | *non chronométré* | 5 trames : `criteria_updated` ×2, `products_found`, `message`, `done` |
| 14 | `make` *(sans cible)* | **0** | — | liste 25 cibles — voir 2.7 |

**La porte de sortie est franchie.** Un `git clone` suivi de la procédure du README
aboutit à une conversation fonctionnelle, en console **et** par l'API, sur une machine
qui n'a jamais vu ce dépôt. Le seul obstacle est celui du §1.4, et il se contourne en
une ligne.

### 1.2 Les fichiers ouverts sans y être invité

**Un seul : `.env`**, pour y écrire la vraie clé API.

C'est le cas prévu par la règle — `make install` copie `.env.example` en `.env` et il
faut y mettre la clé. **Ce qui est un constat, c'est que le README ne le dit nulle
part** (§1.4).

Aucun autre fichier n'a été ouvert dans le clone : ni `Makefile`, ni `PROJET.md`, ni
`docker-compose.yml`, ni un module de `src/`. La partie 2 de cet inventaire les lit,
mais dans le **dépôt d'origine** et pour mesurer, pas pour faire fonctionner le clone.

### 1.3 Les contournements

Un seul, déclaré : au point 8, `make fumee` a échoué avec la clé que `make install`
laisse en place. **Contournement** : recopie de la ligne `ANTHROPIC_API_KEY=` du `.env`
du dépôt d'origine dans le `.env` du clone. Les points 9 à 13 en dépendent.

Deux exécutions supplémentaires de `make fumee`, hors procédure, pour caractériser
l'échec plutôt que le constater (§1.4). Elles n'ont consommé aucun jeton : les deux
échouent avant l'appel réseau ou sur un 401.

### 1.4 🔴 Le défaut trouvé par le clone — la clé API factice

`make install` écrit un `.env` qui porte `ANTHROPIC_API_KEY=sk-ant-xxxxx`, la valeur
factice de `.env.example`. Le README, lui, ne dit **jamais** d'ouvrir ce fichier : il ne
nomme `.env` qu'une fois, en commentaire de `make install` (« création de .env »,
`README.md:116`), et il nomme `ANTHROPIC_API_KEY` une fois, pour dire quelles commandes
l'exigent (`README.md:124`). Un lecteur qui suit le README enchaîne donc sur
`make fumee` avec la clé factice.

Ce qu'il obtient — premier message d'erreur verbatim :

```
anthropic.AuthenticationError: Error code: 401 - {'type': 'error', 'error':
{'type': 'authentication_error', 'message': 'API key is invalid.'}, 'request_id': None}
make: *** [Makefile:68 : fumee] Erreur 1
```

précédé de vingt-quatre lignes de traceback Python — huit cadres de pile. En anglais,
sans un mot sur quoi faire.

Le README affirme pourtant (`README.md:127`) : *« Son absence est signalée au moment de
s'en servir, par un message qui dit quoi faire. »* C'est vrai, et c'est inatteignable par
le chemin documenté. Les trois états mesurés :

| État de `ANTHROPIC_API_KEY` dans `.env` | Comportement observé |
|---|---|
| **ligne absente** | ✅ `⛔ ANTHROPIC_API_KEY est absente…` — message français, nomme les commandes concernées, sortie 2 propre |
| `ANTHROPIC_API_KEY=` *(vide)* | ❌ traceback + `TypeError: "Could not resolve authentication method…"` (message du SDK) |
| `ANTHROPIC_API_KEY=sk-ant-xxxxx` **← ce que `make install` produit** | ❌ traceback + `AuthenticationError: 401` |

La garde de `cle_api()` (`src/raiyon/config.py:216-231`) ne teste que `cle is None`. Une
chaîne vide et une chaîne factice la traversent toutes les deux.

**Deux correctifs, et un seul est dans le périmètre de l'étape 14** — voir §6.

### 1.5 🔴 Le clone sert `systeme.v1`, pas le prompt en vigueur

Constat en trois lignes, toutes mesurées sur le clone :

* `make chat` a démarré sur `prompt : systeme.v1 (6da03a675684)` ;
* `GET /health` a rendu `{"prompt":{"version":"systeme.v1","empreinte":"6da03a675684"}}` ;
* la même requête, après avoir **commenté** `RAIYON_PROMPT_SYSTEME` dans le `.env`, rend
  `{"prompt":{"version":"systeme.v2","empreinte":"61b474af9184"}}`.

Cause : `.env.example:34` porte `RAIYON_PROMPT_SYSTEME=systeme.v1`, `make install` le
recopie, et la variable d'environnement l'emporte sur le défaut du code
(`config.py:21`, `PROMPT_SYSTEME_PAR_DEFAUT = "systeme.v2"`).

**La conséquence dépasse la cosmétique.** Le tableau des critères d'acceptation du
README décrit `systeme.v2` (36 prises, étape 13). Un lecteur qui suit le README obtient
un produit qui tourne sur `systeme.v1` — celui dont l'étape 13 a mesuré qu'il produit
51 occurrences de markdown non rendu et un taux de rejet plus élevé. Le dépôt livre
silencieusement autre chose que ce qu'il annonce, exactement comme au jalon 3 de
l'étape 13 où la constante annonçait v2 et la configuration servait v1.

**Effet de bord du correctif : aucun.** Vérifié — rien ne lit `.env.example` :
`Makefile:15` le **copie**, et `config.py:227` le **cite** dans un message d'erreur.
Aucun test, aucun script, aucun module ne l'ouvre. Corriger la ligne au jalon 1 ne peut
périmer aucune cassette.

**Aucun test ne garde cette cohérence.** `grep -rn "env.example" tests/` ne rend rien.
Ce serait la troisième occurrence du motif dans ce dépôt, après `erreurs.py` et le
quasi-accident `SYSTEME_PAR_DEFAUT` contre `Settings.prompt_systeme`.

### 1.6 Les frictions qui ne sont pas des échecs

* **Aucune durée n'est annoncée** par le README. `make up` prend 5,7 s (healthcheck),
  `make check` **17,1 s sur un dépôt neuf** — caches `ruff` et `mypy` vides — contre
  9,1 s sur le dépôt d'origine, caches chauds. Le README annonce 6,0 s (§2.1).
* **`make install` n'annonce pas sa propre durée réelle.** Ici 0,67 s parce que le cache
  `uv` était partagé ; sur une machine neuve ce sera un téléchargement de 62 paquets.
* **La seule instruction sur la clé API vient du `Makefile`, pas du README** :
  `→ .env créé depuis .env.example — y mettre la vraie clé API`. Elle défile au milieu
  de la sortie de `uv sync` et se perd.
* **`make chat` sur une entrée non interactive** affiche `À bientôt.` et sort en 0 —
  correct, mais le README ne dit pas que la console lit stdin ligne à ligne, donc qu'elle
  se scripte.

---

## 2. Les faits périmés

Mesurés le 2026-09-02 sur `2c010da`. **Rien n'a été corrigé.**

| # | Ce que le README affirme | Ce qui est mesuré | Où c'est mesuré |
|---|---|---|---|
| 2.1 | `make check` — **720** tests en **6,0 s** (`README.md:141`) | **904** tests ; pytest en **8,3 s**, cible entière en **9,1 s** caches chauds, **17,1 s** caches froids | `uv run pytest --collect-only` → `904/1002` ; `time make check` |
| 2.2 | `make test-int` — **84** (`README.md:142`) | **98**, en 3,4 s | `uv run pytest -m integration --collect-only` → `98/1002` |
| 2.3 | `GET /health` → `"systeme.v1"`, `"6da03a675684"` (`README.md:210`) | `"systeme.v2"`, `"61b474af9184"` (8 633 octets) avec le défaut du code | `curl -s .../health` sur `make api`, `RAIYON_PROMPT_SYSTEME` commentée. Voir §1.5 : l'exemple du README est exact **pour un clone**, et faux pour le dépôt |
| 2.4 | Taux de rejet **0,25 par tour sur v1**, 0,07 sur v2 (`README.md:46`) | v1 = **0,13/tour** (9 griefs / 68 tours) ; v2 = **0,07/tour** (6 / 81) ✅ | en-têtes de `docs/eval/rapport.v1-base.md:41` et `rapport.v2.md:44`. Le 0,25 est un chiffre de l'**étape 12** (`PROJET.md:3347`), pas de la ligne de base contre laquelle v2 est comparé. La **conclusion** du paragraphe reste juste : le verdict de `comparaison.v1-base-v2.md` sur cette mesure est bien « dans le bruit » |
| 2.5 | Trois bases jetables : `raiyon_test`, `raiyon_test_matching`, `raiyon_test_agregats` (`README.md:133`) | **Quatre** — `raiyon_test_migrations` en plus | `tests/integration/conftest.py:28,33,36` et `tests/matching/conftest.py:33` |
| 2.6 | `make eval` sort en code non nul si l'un des critères **1, 2 et 6** est violé (`README.md:25`) | Quatre conditions : `critere_1 and critere_2 and critere_6 and not attentes_manquees` | `src/raiyon/eval/metriques.py:484` |
| 2.7 | « `make` seul liste les autres cibles » (`README.md:130`) | 25 cibles listées sur **26** réelles : **`eval-etape12` manque**, son nom porte des chiffres et le motif du `help` est `^[a-zA-Z_-]+:` | `Makefile:9` ; `make` dans le clone. Le README documente pourtant `make eval-etape12` (`README.md:81`) |
| 2.8 | « Seuls **24 %** des produits de la source portent un prix » (`README.md:556`) | **24,6 %** — le filtre retire 27 220 lignes sur 36 083 — et cela porte sur les **six catégories retenues**, pas sur « la source », qui en compte 25 en amont et 7 figées | `data/seed/rapport_seed.md:29` ; `data/raw/SOURCE.md` |
| 2.9 | « le taux de repli est passé de **0 % à 5 %** sans qu'une cassette change » (`README.md:72`) | Vrai **historiquement** (2 tours sur 44, `PROJET.md:3360`), mais l'archive committée affiche aujourd'hui **2 %** — 1 tour sur 42 — depuis que `desserrage_refuse.1` ne se rejoue plus | `docs/eval/rapport.v1-etape12.md:36` ; `docs/eval/LISEZMOI.md:18-22` |

### Ce qui a été vérifié et qui est **exact**

Consigné parce qu'un jalon qui ne dit que ce qui est faux laisse croire que le reste
n'a pas été regardé.

| Affirmation | Vérification |
|---|---|
| 36 prises, 11 scénarios, **81 tours client** | Somme du tableau « Par scénario » de `rapport.v2.md` : 36 lignes, 11 scénarios distincts, 81 tours |
| 6 griefs refusés — 3 `valeur_non_fournie`, 2 `montant_non_fourni`, 1 `prix_etranger_au_produit` | `rapport.v2.md`, tableau « Rejets par origine et par code » ; somme de la colonne = 6 |
| Taux de repli **0 sur 81** | `rapport.v2.md:45` ; somme de la colonne Replis = 0 |
| Critères 3, 4, 6 : 1,0 tour sur 26 prises · 12/12 · 12/12 | `rapport.v2.md`, tableau des critères |
| Markdown **51 → 0**, dispersion **± 43**, verdict « au-delà » | `docs/eval/comparaison.v1-base-v2.md:59` |
| **3 codes de grief sur 6** ne tirent jamais — `id_inconnu`, `nom_reecrit`, `ecart_non_dit` | `CodeGrief` compte 6 valeurs ; `rapport.v2.md` les nomme |
| « Quatre autres rapports coexistent dans `docs/eval/` » | 6 fichiers `.md` = 1 LISEZMOI + 1 rapport v2 + 4 autres |
| Catalogue : **1 026 produits**, **6,4 Mo** de JSON brut, **38 traductions sur 38** | `wc -l data/seed/produits.jsonl` = 1026 ; `du -sh data/raw` = 6,4M ; `PROJET.md:324` |
| Calibration : **497,5 USD/Go**, borne haute **13,375** | `src/raiyon/matching/attributs.py:186` et `:214` |
| `tests/matching/` : **170** purs en **0,18 s**, **28** en intégration | `pytest tests/matching -m "not integration"` → `170 passed … in 0.18s` ; `-m integration` → 28. **Les deux compteurs locaux sont justes** |
| **5 outils** | `schema_des_outils()` → `outils=5 champs=36` |
| **10 événements dont 8 du domaine** | `NomEvenement` : 8 valeurs du domaine + `error` + `done` |
| **17 portes hostiles** | `tests/tools/test_hostile.py` : 20 fonctions, dont 3 affirment un **passage** légitime (contradiction diagnostiquée, bornes d'intervalle, deux assouplissements en deux messages) — restent **17** refus. Fichier inchangé depuis l'étape 7 (`4204b36`) |
| **4 modules ES** dans `web/`, aucun `package.json` | `ls web/*.js` = 4 |
| **Tous les liens relatifs** résolvent | `models.py`, `rapport_seed.md`, `SOURCE.md`, `attributs.py`, `PROJET.md` — 5 sur 5 |
| Toutes les commandes `make` citées existent | 16 cibles citées, toutes présentes dans le `Makefile` |
| La trame `curl` de la section API | Rejouée en direct : `criteria_updated` porte bien `categorie, libelle_categorie, criteres[champ, libelle_fr, unite, operateur, valeur, importance], budget_usd` ; `products_found` porte `categorie, candidats_trouves(=32), produits[id, nom, marque, prix_usd]` ; ordre et noms conformes |
| Les 4 identifiants produits de la trace console | `monitor-9d9e443e00` AOPEN 108.00 · `monitor-ee31fe1bb3` MSI MAG 255XFV 129.99 · `monitor-3e3a4798db` BenQ MOBIUZ EX240N 139.99 · `monitor-80e6d42e2f` Samsung Odyssey G50A 417.14 — les quatre existent, aux prix cités |
| `make eval` reproduit son rapport | Relancé : exit **0** en 2,5 s, `git status` inchangé — `rapport.v2.md` est **rejouable à l'octet** |

---

## 3. Les chiffres non sourçables

**Rien n'est proposé en remplacement.** Une valeur plausible inventée ici serait la faute
que ce jalon existe pour ne pas commettre.

### 3.1 Les deux trames « réelles » de la section API

`README.md:288` : *« Ces deux trames sont réelles : elles viennent d'une conversation de
recette. »* Il s'agit du `text_rejected` portant `montant_non_fourni` sur l'extrait
`230 $`, et du `message` qui suit (« …monter à 500 $ ne change rien… »).

**Aucun artefact du dépôt ne les porte.** Ni cassette, ni appendice de rapport, ni
`docs/`. Recherché sur `230 $`, `monter à 500`, `IPS 27` — zéro correspondance hors du
README lui-même. La conversation de recette n'a pas été enregistrée : `make eval-live`
n'écrit rien, et le README le dit lui-même (`README.md:103`).

C'est la seule affirmation du README présentée comme une **mesure** et qui ne se source
nulle part. Elle est probablement vraie ; elle n'est pas vérifiable.

### 3.2 Les deux durées

**6,0 s** pour `make check` et **0,16 s** pour `tests/matching/` : aucun artefact du
dépôt ne les enregistre, et aucun ne le pourrait — une durée dépend de la machine. La
seconde est reproduite à 0,18 s ; la première ne l'est pas (8,3 s). Ce sont des durées
recopiées, pas des mesures reconductibles : le jalon 1 devra décider s'il les remesure
ou s'il cesse d'en publier.

### 3.3 La ligne de sondage de la trace console

`[sondage] 32 candidats · 108.00 $ à 399.99 $ · 4 dans la zone de tolérance`
(`README.md:166`). Les 32 candidats sont confirmés en direct par
`products_found.candidats_trouves` ; **les bornes de prix et les 4 en zone de tolérance
ne sont attestés par aucun artefact.**

### 3.4 ✅ Le coût d'une campagne — il **est** sourçable, contrairement à ce qu'on croyait

Le chiffre de mémoire, 209, ne se trouve **ni** dans `docs/prompts/etape-13-revision.md`
**ni** nulle part ailleurs dans le dépôt. Mais il n'a pas besoin d'être cru : **chaque
cassette porte sa propre consommation**, dans `entete.usage`
(`src/raiyon/eval/cassette.py:133`), et il suffit de la sommer.

Mesuré sur les cassettes committées :

| Jeu | Cassettes | Appels au modèle | Jetons entrants | Jetons sortants | Cache écrit | Cache lu | Enregistré le |
|---|---|---|---|---|---|---|---|
| `systeme.v2` | 36 | **191** | 358 088 | 46 285 | 9 744 | 1 851 360 | 2026-09-02 |
| `systeme.v1-desserrage` | 3 | **18** | 32 639 | 5 594 | 8 076 | 137 292 | 2026-09-02 |
| **Campagne de l'étape 13** | **39** | **209** | **390 727** | **51 879** | **17 820** | **1 988 652** | |
| `systeme.v1-partielle` | 21 | *non mesuré* | — | — | — | — | 2026-09-02 |
| `systeme.v1-etape12` | 19 | *non mesuré* | — | — | — | — | 2026-09-01 |

**Le 209 est exact, et il se dérive.** C'est la somme des deux jeux enregistrés le
2026-09-02 : la campagne v2 (191) plus les trois prises de `desserrage_refuse`
réenregistrées sous v1 pour rendre la ligne de base comparable (18).

Deux réserves à porter avec le chiffre :
* `usage.appels` compte les appels de **l'agent** seul. Pendant `eval-enregistrer`, les
  tours du client sont **scriptés** (`scenario.tours`) et n'appellent aucun modèle : il
  n'y a donc rien d'autre à compter. Ce ne serait pas vrai de `make eval-live`.
* Les deux jeux antérieurs n'ont pas de compteur — `usage` est facultatif et absent de
  leurs en-têtes. Le coût de la campagne v1 interrompue n'est **pas** récupérable.

⚠️ **Aucun montant en dollars n'est calculé ici**, et aucun ne doit l'être : le dépôt ne
porte aucune grille tarifaire, et l'inventer serait le fait fabriqué que ce projet
s'interdit. Les jetons ci-dessus sont comptés, pas convertis.

📌 Le jalon 2 peut donc écrire un coût de campagne **mesuré**. Il devra en revanche
préciser que `rapport.v2.md` ne porte, lui, aucun compteur : l'information vit dans les
cassettes, et rien ne la remonte au rapport.

---

## 4. Les mentions chronologiques

Elles supposent que le lecteur a suivi la construction. **Ne pas les corriger ici** — le
jalon 1 réécrira chaque phrase au présent et autonome.

### 4.1 Dans le `README.md` — dix, plus une référence listée pour mémoire

| Ligne | Mention | Ce qu'elle suppose connu |
|---|---|---|
| 10 | « arrêtés à l'**étape 1** (PROJET.md §4) » | qu'il y a eu des étapes |
| 11 | « mesurés par le harnais d'éval depuis l'**étape 12** » | idem |
| 24 | « prompt `systeme.v2` (**étape 13**) » | idem |
| 31 | « garantis par construction depuis l'**étape 9** » | idem |
| 49 | « ce que la campagne de l'**étape 13** démontre » | idem |
| 57 | « écrites au **§7** de `PROJET.md` » | un document externe, non résumé ici |
| 63 | « exercées par `tests/validateur/test_pieges.py` » | *(rien — référence de fichier valide, listée pour qu'on ne la reprenne pas par erreur au jalon 1)* |
| 73 | « le **correctif de l'étape 12** lui a donné un motif » | idem |
| 81 | « `make eval-etape12` — rejoue le jeu archivé de l'**étape 12** » | le nom de la cible **est** chronologique ; le renommer périmerait le `Makefile` — arbitrage à poser au jalon 1 |
| 289 | « elles viennent d'une **conversation de recette** » | voir §3.1 |
| 451 | « le raisonnement complet est en `PROJET.md` **§3.4ter** » | une numérotation de section externe |

### 4.2 🔴 Les deux qui parlent au **futur** d'étapes franchies — elles sont fausses

| Ligne | Texte | Pourquoi c'est faux |
|---|---|---|
| **181** | « le prompt système en vigueur et son empreinte sont affichés au démarrage et logués à chaque appel : c'est ce qui **permettra, à l'étape 12**, de détecter une cassette enregistrée sur un prompt qui a changé depuis » | L'étape 12 est franchie. Le mécanisme **existe** : `entete.prompt_empreinte` est comparée au rejeu et fait échouer `make eval` en nommant la cassette |
| **411** | « le reste du markdown s'affiche tel quel, et c'est le **prompt qui sera corrigé à l'étape 13** — pas le front » | L'étape 13 est franchie et **le correctif a eu lieu** : la section 14 de `systeme.v2` interdit les listes, et la campagne mesure 51 occurrences → **0**. Le README annonce au futur un travail dont il publie déjà le résultat vingt lignes plus haut (ligne 49) |

### 4.3 Dans le `.env.example` — neuf

| Ligne | Mention |
|---|---|
| 11 | « **OPTIONNELLE depuis l'étape 8** » |
| 14 | « dirait son défaut au mauvais moment (**étape 10, piège nº4**) » |
| 16 | « (**PROJET.md, amendement du §5 étape 2**) » |
| 24 | « (**PROJET.md §3.14, étape 13**) » |
| 29 | « (**§3.13**, préfixe mis en cache) » |
| 36 | « Modèles (**PROJET.md §3.13**) » |
| 41 | « Zone de tolérance budget (**PROJET.md §3.10**) » |
| 44 | « Garde-fou anti-boucle (**PROJET.md §3.9**) » |
| 48 | « (**PROJET.md §3.11 niveau 2**) » |

### 4.4 🔴 Celle du `.env.example` qui parle au futur — elle est fausse aussi

`.env.example:50` : « 0 est une valeur légitime : elle branche directement le repli sur
template, ce qui **permettra à l'étape 12** de mesurer ce que la régénération rattrape
vraiment. » L'étape 12 est franchie, et l'étape 13 a publié deux campagnes.

---

## 5. Ce qui manque au regard de §5 étape 14

L'énoncé demande : *« Installation, lancement, exemples d'usage, tableau de métriques,
schéma d'architecture, et une section honnête sur ce qui est réel et ce qui est dérivé
dans le catalogue. »*

| Demandé | État | Constat |
|---|---|---|
| Installation | ✅ présent | `## Prérequis` + `## Démarrage`. Il manque l'étape « écrire la clé dans `.env` » (§1.4) |
| Lancement | ✅ présent | console, API, interface |
| Exemples d'usage | ✅ présent | trace console, trames `curl`, trames SSE — toutes vérifiées §2 |
| Tableau de métriques | ✅ présent | six critères + trois couches, à dépérimer |
| Ce qui est réel / dérivé dans le catalogue | ✅ présent | `## Le catalogue` + `## Données` |
| **Schéma d'architecture** | ❌ **absent** | Aucun schéma, aucun diagramme. Le mot « architecture » n'apparaît qu'en prose (lignes 157, 344, 563). ⚠️ `grande_echelle/architecture_cible.md` **n'est pas** ce schéma : il se déclare « exploratoire », « ne fait pas partie du MVP », et décrit une cible à l'échelle — pas le système livré |
| **Le périmètre exclu (§8)** | ❌ **absent** | Rien sur le paiement, le compte, le panier, le multilingue, ni sur « un tour, une catégorie » et le total non suivi à travers les tours — alors que c'est la limite la plus visible en démonstration |
| **Les dettes ouvertes (§7)** | ⚠️ **partiel** | Le README expose quatre limites (règles muettes, règle manquante indétectable, chiffre de domaine sans unité, repli à 5 %) et renvoie au §7. Il n'y a **pas de section de dettes** : §7 en porte une quarantaine, dont plusieurs ouvertes |
| **Le coût d'une campagne d'éval** | ❌ **absent** | Aucune mention. Mesurable — voir §3.4 |
| **Une carte du dépôt** | ❌ **absente** | Seul `web/` est cartographié (`README.md:324`) |

### La structure réelle de premier niveau

Relevée sur les fichiers **versionnés** :

```
alembic/          les migrations
catalogue/        ⚠️ jamais nommé au README — rapport_exploration.md,
                  schema_attributs.md, echantillons/ (7 JSON)
data/             raw/ (non versionné, SOURCE.md) · seed/ (produits.jsonl,
                  rapport_seed.md)
docs/             eval/ (5 rapports + LISEZMOI) · prompts/ (les énoncés d'étape)
evals/            cassettes/ — 4 jeux : systeme.v2, v1-etape12,
                  v1-partielle, v1-desserrage
grande_echelle/   ⚠️ jamais nommé au README — architecture_cible.md et .html
prompts/          les rédactions du prompt système
scripts/          console.py, eval.py, fumee.py, seed_build.py,
                  seed_charger.py, calibrer_bornes.py, explore_dataset.py
src/raiyon/       agent · api · catalogue · db · eval · matching · tools ·
                  validateur · config.py
tests/            agent · api · eval · integration · matching · tools ·
                  validateur + racine
web/              index.html, style.css, 4 modules ES
```

Plus, à la racine : `Makefile`, `PROJET.md`, `README.md`, `docker-compose.yml`,
`alembic.ini`, `pyproject.toml`, `uv.lock`, `.env.example`, `.python-version`,
`.pre-commit-config.yaml`, `.github/`.

**Deux répertoires versionnés ne sont nommés nulle part dans le README** :
`catalogue/` et `grande_echelle/`.

---

## 6. Ce qui exigerait de toucher au produit

Une seule entrée. Rédigée comme une ligne de §7 : le fait, sa gravité, ce qui l'atténue.

### La garde de `cle_api()` ne voit qu'une clé absente, pas une clé vide ou factice

**Le fait.** `src/raiyon/config.py:216-231` lève une `ConfigurationError` explicite
quand `anthropic_api_key` vaut `None`. Une chaîne vide et la chaîne factice
`sk-ant-xxxxx` la traversent, et l'échec remonte du SDK Anthropic : un `TypeError` en
anglais dans un cas, un `AuthenticationError: 401` dans l'autre, tous deux précédés d'un
traceback Python. Comme `make install` produit précisément l'état factice, **le chemin
documenté du README ne peut pas atteindre le message que le README promet.**

**Sa gravité.** Moyenne, et elle porte sur la seule chose qui compte pour un
portfolio — la première minute d'un lecteur qui clone. C'est aussi le seul endroit du
dépôt où la discipline « un message d'erreur dit quoi faire » est tenue en principe et
rompue en pratique.

**Ce qui l'atténue, et ce qui reste.** Le correctif de **surface** est dans le périmètre
de l'étape 14 : commenter la ligne dans `.env.example` (`#ANTHROPIC_API_KEY=sk-ant-…`)
rend la variable absente dans le `.env` que `make install` produit, ce qui fait tomber la
garde existante et rend le bon message. Il ne touche ni `src/`, ni un prompt, ni le
schéma d'outils, ni le validateur, ni le catalogue : **aucune cassette n'est périmée.**
Ajouter l'étape « écrire la clé dans `.env` » à la procédure du README est du même ordre.

Ce qui **reste ouvert** et tombe sous la contrainte non négociable : élargir la garde à
une valeur vide ou manifestement factice touche `src/raiyon/config.py`. Ce n'est pas un
correctif de l'étape 14. Il est écrit ici pour être repris tel quel dans §7.

---

## Ce que le jalon 0 n'a pas fait

* Aucune correction — ni `README.md`, ni `.env.example`, ni documentation.
* Aucun test ajouté, y compris celui de cohérence `.env.example` / `config.py` que le
  jalon 1 écrira.
* `make check` relancé après coup : **vert**, 904 tests — trivial puisque rien n'a bougé,
  et c'est justement ce qui est vérifié.
* Le clone est détruit : `docker compose down -v` puis suppression du répertoire
  temporaire. Le compte rendu ci-dessus lui survit ; le clone non.
