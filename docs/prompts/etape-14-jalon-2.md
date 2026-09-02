# Étape 14 · jalon 2 — ajouter ce que §5 étape 14 demande

## État

Le jalon 1 est clos : `README.md` et `.env.example` dépérimés, la chronologie
effacée, la garde `tests/test_env_example.py` en place, `make` liste
`eval-etape12`. `make check` vert à 906 tests, `make test-int` vert.

**Lis `docs/etape-14-inventaire.md`** — il reste la source des mesures.
⚠️ **Sauf son §3.3**, qui est désormais faux : la ligne `[sondage]` a été
recalculée par `probe_catalog` contre le seed et elle est **exacte** aux trois
valeurs. Ne reprends pas ce constat.

Ce jalon **ajoute**. C'est le seul de l'étape qui a le droit d'écrire des sections
neuves, et c'est aussi celui où un README grossit de trois cents lignes sans que
personne s'en aperçoive.

## Les deux règles qui gouvernent tout ce jalon

**1. Chaque section neuve se justifie par §5 étape 14, et aucune autre.** Cinq
manques sont recensés : le schéma, la carte du dépôt, le périmètre exclu, les
dettes ouvertes, le coût d'une campagne. Plus la licence et les lignes de
clôture, arbitrées séparément. Si tu écris une sixième section, tu es hors sujet.

**2. Le README dit ce qui est ; `PROJET.md` dit pourquoi.** Une limite se nomme
en **une phrase avec son lien**, jamais avec sa justification. Deux phrases pour
une limite, c'est une justification déguisée — coupe.

Cette règle ne doit pas amputer l'honnêteté du fichier, qui est sa meilleure
qualité. Elle déplace l'argument, elle ne le supprime pas.

⚠️ **Section protégée, elle ne se déporte pas** : « Comment lire ce tableau, et
pourquoi il ne dit pas ce qu'il a l'air de dire ». Elle a l'air d'une
justification et n'en est pas une — c'est le mode d'emploi du tableau qui la
précède, et sans elle un `0` au critère nº1 se lit à l'envers. Elle reste
entière, à sa place.

## Contraintes non négociables

**Aucun changement de prompt, de schéma d'outils, de validateur ou de
catalogue.** Si un correctif de ce genre semble nécessaire, c'est une ligne de §7,
pas un commit.

Fichiers touchables : `README.md`, `PROJET.md` (§7, une ligne), `Makefile`
(la chaîne d'écho de `install`), et un `LICENSE` neuf.

---

# 1. Le schéma

**Un seul schéma, et c'est celui du chemin d'un message.** Quatre schémas dont
trois redisent le README est la façon habituelle de rater cette section.

**Placement** : juste après le paragraphe d'introduction, **avant** le tableau
des six critères. Le lecteur voit l'architecture et la porte du validateur avant
les chiffres, et « 0 grief » atterrit alors sur quelque chose.

**Forme** : Mermaid dans le README. GitHub le rend nativement, le dépôt a déjà le
précédent (`grande_echelle/architecture_cible.md`), et rien de binaire n'entre au
dépôt.

**Ce qu'il montre** : le trajet d'un message client jusqu'à la réponse affichée —
la boucle agent, l'appel d'outil, la couche outils, le moteur, SQL, le retour, la
prose, **le validateur dessiné comme une porte à trois issues** (le texte passe /
une régénération est demandée, retour au modèle / repli sur un texte écrit en
Python), puis le flux d'événements et l'interface.

La porte est le cœur du dessin. C'est là que « le LLM n'invente rien » cesse
d'être une phrase et devient un mécanisme qu'on peut suivre du doigt.

**Le groupement, si et seulement s'il reste lisible** : les nœuds où le LLM parle
visuellement distincts des nœuds déterministes — `classDef` ou `subgraph`, c'est
gratuit en Mermaid. Le lecteur voit alors le chemin, la porte, **et où le LLM
n'est pas**, sans un second dessin. ⚠️ **Si le groupement alourdit le schéma au
point de le rendre illisible, abandonne-le** : la lisibilité passe avant, et le
schéma seul suffit.

**Ce qu'il ne montre pas**, et c'est ce qui le garde lisible : les cinq outils un
par un (un nœud « couche outils » suffit), les modules internes de `web/` (la
section Interface le fait mieux), le harnais d'éval (ce n'est pas le chemin d'un
message), la persistance de session ailleurs qu'en une arête.

**Vérifie la syntaxe** avant de committer — un bloc Mermaid invalide s'affiche
sur GitHub comme un pavé d'erreur rouge, c'est-à-dire pire que pas de schéma. Le
jalon 3 le regardera rendu.

# 2. La carte du dépôt

**Placement** : juste après « Démarrage ». Une carte sert à s'orienter, donc elle
sert avant.

**Premier niveau seulement.** Une ligne de glose par entrée, et **elle s'arrête à
`web/` sans le détailler** — la section Interface porte déjà l'arbre des quatre
modules et leur discipline, et le redire serait le doublon que ce jalon doit
éviter.

Elle nomme **`catalogue/` et `grande_echelle/`**, qui n'apparaissent nulle part
dans le README aujourd'hui.

# 3. Le périmètre exclu

Une section courte, adossée à §8 de `PROJET.md` : paiement, compte utilisateur,
multilingue, panier, historique inter-sessions, et **la composition
multi-catégories**.

Cette dernière est la seule qui mérite plus qu'un mot, parce qu'elle se constate
en démonstration : un client peut, en trois tours, se voir recommander trois
composants dont la somme dépasse ce qu'il avait annoncé. **Une phrase, et le lien
vers §8** — la mécanique du panier, du budget alloué et du critère nº2 redéfini
est écrite là-bas et n'a rien à faire ici.

# 4. Ce qui reste ouvert

**Le critère de coupe s'écrit dans la section**, en tête : ce sont les dettes
qu'un relecteur trouverait de toute façon. Annoncer le critère vaut mieux que
laisser croire à une liste exhaustive.

Sept lignes, **une phrase et un lien chacune** :

1. la **dette nº1** — les descriptions d'outils redisent des règles du prompt ;
2. le **découpage v2/v3** qui n'a pas eu lieu, donc une attribution par
   inspection plutôt que par isolation ;
3. la **fuite possible des exemples chiffrés** du prompt système ;
4. le **correctif de `NOMBRE`**, écrit et différé ;
5. le **parseur SSE et le réducteur du front**, seul code du projet sans test ;
6. l'**entier nu** sans unité, que le validateur ne vérifie pas ;
7. le **critère nº1 qui ne détecte pas une règle manquante**.

⚠️ Deux de ces sept — le 6 et le 7 — sont **déjà développés** dans « Comment lire
ce tableau ». Ils s'y renvoient par **ancre interne**, ils ne s'y répètent pas.

Le nº5 est celui à ne pas laisser tomber : c'est le seul code du projet sans
test, et c'est exactement ce qu'un relecteur technique va chercher. Mieux vaut le
nommer soi-même.

**Une phrase de clôture** qui renonce à l'exhaustivité en le disant, et renvoie à
§7 — qui en compte une trentaine, toutes écrites.

## La ligne de §7 à écrire

`PROJET.md` §7 gagne **une ligne** : la garde de `cle_api()` ne voit qu'une clé
absente, pas une clé vide ou factice. Le format du tableau : le fait, la gravité,
l'atténuation. L'atténuation existe depuis le jalon 1 — `.env.example` ne livre
plus de clé factice, donc le chemin documenté atteint le bon message — et ce qui
reste ouvert est qu'une clé **mal recopiée** produit toujours un 401 brut.

Écris-la **en même temps** que la section ci-dessus, pour que les deux disent la
même chose. Elle n'entre pas dans les sept du README : un relecteur ne la
trouverait pas sans ouvrir `config.py`, et le critère de coupe est celui-là.

# 5. Le coût d'une campagne

**Placement** : dans « Le harnais », accolé à `make eval-enregistrer` — c'est là
qu'on se demande ce que ça coûte.

**Ce qui se publie** : une campagne, c'est **36 prises et 191 appels au modèle**,
plus les jetons entrants et sortants. Le +18 de la ligne de base v1 ne se raconte
pas : ce serait de l'archéologie d'étape 13 dans un fichier qu'on vient d'en
purger, et un lecteur qui relancerait une campagne n'obtiendrait pas 209.

**Remesure** depuis `entete.usage` des cassettes plutôt que de recopier
l'inventaire.

⚠️ **Aucune conversion en dollars.** Le dépôt ne porte aucune grille tarifaire, et
l'inventer serait le fait fabriqué que ce projet s'interdit. Les jetons sont
comptés, pas convertis.

Une clause dit où vit l'information : `rapport.v2.md` ne porte **aucun** compteur,
le coût est dans les cassettes.

Et le pendant, qui est le plus utile au lecteur : **rejouer ne coûte rien** — ni
clé, ni jeton. Le README le dit déjà ailleurs ; ici c'est le contraste qui porte
l'information.

# 6. Les lignes de clôture

**Placement** : avant les sections Données et licence. Deux ou trois lignes, pas
une note de bas de page.

Ce qu'elles nomment, parce que c'est ce qui distingue ce dépôt : chaque décision
d'architecture est écrite **avec ses alternatives écartées** ; les prompts qui ont
produit chaque étape sont **committés** dans `docs/prompts/` ; et
`grande_echelle/architecture_cible.md` répond à « et si ça passait à l'échelle ? »
— **en se déclarant exploratoire et hors MVP**, ce qui doit rester lisible dans la
phrase qui l'annonce.

C'est la seule mention de la construction du projet que le README s'autorise.
Elle ne réintroduit **aucune** référence à une étape numérotée.

# 7. La licence

Aucun `LICENSE` n'existe, et sans licence explicite tout est réservé par défaut —
ce qui est probablement l'inverse de l'intention pour un portfolio.

Créer un `LICENSE` **MIT** à la racine, et une ligne au README. MIT est déjà la
licence du dataset : aucun conflit à instruire.

Le titulaire et l'année se prennent dans `git config user.name` et la date du
dépôt, **jamais devinés**. Si `git config user.name` est vide, arrête-toi et
demande plutôt que d'inscrire un nom inventé dans un fichier juridique.

# 8. Le fil laissé par le jalon 1

`Makefile:15` — l'écho de `install` dit « y mettre la vraie clé API » sans dire de
**décommenter**. Depuis le jalon 1, `.env.example` livre la ligne commentée : le
message contredit donc le fichier qu'il vient de copier. Corrige la chaîne d'écho,
et elle seule.

# 9. Une cohérence à vérifier, créée par le jalon 1

Deux taux de repli coexistent maintenant dans le README : **2 %** dans les trois
couches du rapport (campagne v2) et **5 %** dans le quatrième point de « Comment
lire ce tableau » (les seize cassettes de l'étape 12, avant/après le motif
`REPONSE_VIDE`).

La chronologie étant effacée, plus rien ne dit au lecteur que ce sont **deux
mesures différentes** — il lit deux chiffres contradictoires sur la même grandeur.

Vérifie, et si l'ambiguïté existe, lève-la **sans réintroduire d'étape** : chaque
chiffre nomme le jeu qu'il mesure et pointe son rapport. C'est une correction de
fait, pas une justification.

---

# La porte de sortie du jalon

- `make check` vert, `make test-int` vert ;
- le bloc Mermaid est **syntaxiquement valide** ;
- **cinq manques de §5 étape 14 comblés**, plus licence et clôture, et **aucune
  sixième section** ;
- **aucune limite écrite en deux phrases** — relis la section « Ce qui reste
  ouvert » ligne à ligne avec cette seule question ;
- « Comment lire ce tableau » est **intacte** ;
- plus une seule occurrence d'« étape N » dans `README.md`, y compris dans ce que
  tu viens d'écrire ;
- les deux taux de repli sont distinguables par un lecteur qui arrive de zéro.

Un commit, message
`docs: le schéma, la carte, le périmètre, les dettes et le coût (étape 14, jalon 2)`.

Puis arrête-toi, et donne :

1. le rendu du schéma tel que tu l'as écrit, et ce que le groupement a coûté en
   lisibilité — s'il a été abandonné, dis-le et dis pourquoi ;
2. les sept lignes de dettes, telles quelles, pour qu'on les relise ensemble ;
3. ce que tu as dû couper pour tenir la règle « une phrase, un lien ».
