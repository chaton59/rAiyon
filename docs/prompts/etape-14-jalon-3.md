# Étape 14 · jalon 3 — la porte de sortie

## État

Jalons 0, 1 et 2 clos, commit `447e949`. `make check` vert à 906 tests,
`make test-int` vert à 98. Le README fait 681 lignes et porte désormais son
schéma, sa carte, son périmètre exclu, ses sept dettes, le coût d'une campagne et
sa licence.

**C'est le dernier jalon de la dernière étape.** Ce qu'il fait : quatre finitions,
un contrôle de sécurité, la porte de sortie, et la publication.

**Ce jalon vérifie, il ne découvre pas.** Le clone du jalon 0 a fait la
découverte, et ses deux défauts sont corrigés. Si celui-ci trouve du neuf, c'est
une information à part entière — dis-le fort plutôt que de la corriger en
passant.

## Contraintes non négociables

**Aucun changement de prompt, de schéma d'outils, de validateur ou de
catalogue.** Un correctif de ce genre est une ligne de §7, pas un commit — y
compris et surtout dans le dernier jalon, où la tentation de « juste finir » est
la plus forte.

---

# 1. Les quatre finitions

## 1.1 Le symptôme de la dette nº5

La ligne sur `flux.js` et `etat.js` a perdu son symptôme au jalon 2, jugé à tort
comme une justification. **Un symptôme est ce qui est** : il décrit à quoi
ressemble le défaut, il ne justifie aucune décision.

Le remettre, **en une seule phrase** — le défaut, puis son symptôme : une carte
produit qui manque une fois sur dix, et qui ne se verrait qu'en démonstration.
Le lien reste.

C'est la dette qu'un relecteur technique cherchera en premier ; la nommer soi-même
ne sert que si elle se comprend **sans cliquer**.

## 1.2 Supprimer l'inventaire

`docs/etape-14-inventaire.md` était un document de travail, annoncé jetable dès sa
première ligne. Il a été absorbé : les faits périmés sont corrigés, le coût est au
README, le défaut de `cle_api()` est en §7.

Le supprimer. **Vérifier d'abord qu'aucun fichier ne le référence** — README,
`PROJET.md`, les prompts de `docs/prompts/`. Un lien mort vers un document
supprimé est le genre de finition qu'une étape de finition ne peut pas se
permettre.

## 1.3 Fermer les étapes 13 et 14 dans §5

Les étapes 1 à 12 portent leur ✅ ; les étapes 13 et 14 ne l'ont pas. L'étape 13
est close depuis son jalon 3, l'étape 14 se clôt ici.

Ajouter les deux marques. **Rien d'autre dans `PROJET.md`** — pas de récit, pas de
bilan. §5 est un plan, il dit ce qui est fait.

## 1.4 Ce que `docs/prompts/` garde

Les quatre prompts de l'étape 14 restent committés, comme ceux des treize étapes
précédentes. Les lignes de clôture du README pointent maintenant vers ce dossier :
il fait partie de ce qui est montré.

---

# 2. Le contrôle avant publication

**Ce dépôt n'est jamais sorti de cette machine, et il va le faire.** Quatorze
étapes d'historique n'ont jamais été relues sous cet angle.

Avant tout `git push`, et **avant même de configurer le remote** :

1. **Chercher une clé dans tout l'historique**, pas seulement dans l'arbre de
   travail : `sk-ant-` sous toutes ses formes, un `ANTHROPIC_API_KEY=` suivi
   d'autre chose qu'une valeur factice, un `.env` qui aurait été committé une
   fois puis retiré. `git log --all -p` et `git rev-list --objects --all` sont les
   deux angles ; l'un rate ce que l'autre voit.
2. **Vérifier que `.gitignore` couvre `.env`**, et qu'il le couvrait déjà aux
   commits anciens.
3. Chercher aussi ce qui n'est pas une clé mais n'a rien à faire dehors : un
   chemin absolu personnel, une adresse, un identifiant de service.

⚠️ **Si quoi que ce soit est trouvé, arrête-toi et ne pousse pas.** Réécrire un
historique est une décision de l'utilisateur, pas une correction de finition.

⚠️ **Un dépôt privé se bascule public d'un seul clic.** « C'est privé » n'est pas
une raison de sauter ce contrôle, c'est la raison pour laquelle on peut encore le
faire tranquillement.

---

# 3. La porte de sortie

C'est la seule vérification qui compte pour un portfolio : **un `git clone` suivi
de la procédure du README aboutit à une conversation fonctionnelle. Elle
s'exécute, elle ne se relit pas.**

## Le protocole

Identique à celui du jalon 0, et pour la même raison — un protocole qui change
entre la découverte et la vérification ne vérifie rien.

1. `docker compose down` dans le dépôt d'origine ; vérifier que 5432 est libre.
   **Ne modifie pas `POSTGRES_PORT` pour contourner** : dévier de la procédure,
   c'est ne plus tester ce qu'on prétend tester.
2. `git clone` du dépôt local vers un répertoire temporaire hors de l'arbre de
   travail, **sur le commit final** — donc après les finitions de la partie 1.
3. **On ne lit que le `README.md` du clone, et ce que le README dit d'ouvrir.**
   Tout fichier ouvert sans y être invité est un constat, pas un détail.
4. Aller jusqu'à une **conversation fonctionnelle**, en console **et** par l'API.
5. **Lancer `make eval` depuis le clone.** Personne ne l'a jamais fait : il ne
   demande ni clé ni réseau, mais il demande la base et le seed, et c'est
   exactement le genre de dépendance qu'un clone révèle. Le README en fait une
   promesse — elle n'a jamais été éprouvée sur un dépôt fraîchement cloné.
6. Consigner commande par commande : la commande, son code de sortie, et le
   premier message d'erreur verbatim en cas d'échec.
7. Nettoyer : `docker compose down` dans le clone, supprimer le répertoire.

## Ce que ce clone est, et ce qu'il n'est pas

Ce n'est **pas** une machine vierge : le cache `uv`, l'image Docker et la clé API
sont partagés. Ce qu'il attrape — un fichier non committé dont le projet dépend,
une commande qui n'existe pas, un ordre faux, un message d'erreur muet. Ce qu'il
n'attrape pas — une dépendance système installée à la main il y a six semaines.

Le dire vaut mieux que la fausse assurance. C'est la règle que le README
s'applique déjà à `flux.js`.

## Si le clone échoue

Le périmètre de correction est celui de l'étape entière : `README.md`,
`.env.example`, la documentation. **Si le correctif touche `src/`, un prompt, le
schéma d'outils, le validateur ou le catalogue : arrête-toi et dis-le.** Ce sera
une ligne de §7, et l'étape se clôt avec cette ligne plutôt qu'avec un correctif
de produit glissé dans la dernière heure.

---

# 4. La publication, et le rendu

Le dépôt part sur **`https://github.com/chaton59/rAiyon`**, en **privé**.

## L'authentification

**Ne manipule aucun jeton, aucun mot de passe, aucune clé SSH.** Si le remote
existe déjà et que l'authentification est configurée sur cette machine, pousse.
Sinon — remote absent, dépôt inexistant côté GitHub, ou `git push` qui réclame des
identifiants — **arrête-toi et rends la main.** Créer le dépôt et s'authentifier
sont des gestes de l'utilisateur.

## Ce qu'on va regarder, une fois rendu

C'est la partie que rien de local ne remplace, et c'est pour elle qu'on pousse :

1. **Le schéma Mermaid s'affiche** — et pas un pavé d'erreur rouge. Le lire :
   les dix nœuds sont-ils lisibles, la porte du validateur se suit-elle du doigt,
   les arêtes de retour vers le modèle et la boucle sont-elles suivables ou le
   graphe est-il devenu un plat de spaghettis ? `flowchart TD` avec quatre arêtes
   de retour est le point où un schéma bascule.
2. **Le contraste des deux nœuds colorés**, en thème clair **et** en thème sombre.
   Les `classDef` épinglent fond, bordure et couleur de texte ; c'est censé tenir
   des deux côtés, et c'est censé se vérifier plutôt que se supposer.
3. **Les trois ancres internes se cliquent et atterrissent.** C'est le point le
   plus incertain du README : GitHub préfixe les `id` fournis par l'utilisateur,
   et le `<a id="lire-le-tableau">` posé au jalon 2 dépend de ce comportement.
   Cliquer les trois, sur la page rendue, et constater où elles arrivent.
4. **Tous les liens relatifs** — vers `PROJET.md`, `data/seed/rapport_seed.md`,
   `src/raiyon/db/models.py`, `docs/eval/`, `docs/prompts/`,
   `grande_echelle/architecture_cible.md`.
5. **Les tableaux se rendent**, en particulier celui des six critères et celui de
   la carte du dépôt.
6. **L'encart latéral affiche la licence MIT** — c'est là que la plupart des gens
   regardent, et c'est la seule preuve que le `LICENSE` est bien formé.

Si une de ces six choses casse, corrige et repousse. C'est le dernier jalon : une
correction de rendu y est à sa place, et c'est même précisément ce pour quoi il
existe.

---

# La porte de sortie de l'étape

- `make check`, `make test-int` et `make eval` verts sur le dépôt de travail ;
- le clone est allé jusqu'à une conversation, en console et par l'API, et
  `make eval` y a tourné ;
- l'historique ne porte aucun secret ;
- le README est poussé, rendu, et les six points ci-dessus sont **regardés**,
  pas supposés ;
- `docs/etape-14-inventaire.md` n'existe plus et rien ne le référence ;
- les étapes 13 et 14 portent leur ✅.

Commits : un pour les finitions
(`docs: le symptôme de la dette nº5, la clôture des étapes 13 et 14 (jalon 3)`),
un autre seulement si le rendu impose une correction.

Puis, pour clore l'étape, donne :

1. **le journal du clone**, commande par commande — c'est la porte de sortie, et
   c'est le seul artefact qui la prouve ;
2. **ce que le rendu a montré**, les six points un par un, et ce qui a dû être
   corrigé ;
3. **ce que ce clone n'a pas pu tester**, écrit comme une limite et non comme un
   détail ;
4. **ce qui reste ouvert au terme de l'étape 14** — les sept dettes du README,
   plus tout ce que ce jalon a trouvé et n'avait pas le droit de corriger.

Le point 4 est ce que quelqu'un lira en reprenant ce dépôt dans six mois. C'est le
dernier écrit de l'étape, et le seul qui parle à l'avenir.
