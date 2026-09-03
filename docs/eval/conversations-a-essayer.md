# Conversations à essayer à la main — les chemins que la suite ne produit pas

> Écrit après l'étape 18. Les deux seuls défauts trouvés hors des tests l'ont été en
> **conversation réelle** : le tour muet de l'étape 12 (par `make eval-live`) et les deux
> règles insatisfaisables de l'étape 18 (par une conversation manuelle). Aucune commande
> automatique ne les a vus.
>
> Ce document ne remplace pas les onze scénarios : il vise ce qu'ils ne couvrent pas.

## Comment lire un échec

Ce qui compte n'est pas qu'une réponse soit maladroite — c'est qu'un **mécanisme** cède.
Trois symptômes valent un rapport :

* un encadré rouge **TEXTE REFUSÉ** suivi d'un repli — le modèle n'a pas pu écrire quelque
  chose de valide, et il faut regarder si c'était **possible** ;
* une réponse écrite par le code (bandeau orange) — repli, tour muet, ou message générique ;
* un chiffre ou un nom qui **n'est dans aucune carte produit** affichée.

Le reste — une formulation lourde, une question mal choisie — est de la qualité, pas un
défaut de mécanisme.

Lancer les deux orchestrations sur la même conversation dit laquelle tient :

```bash
make api                                  # agent
RAIYON_ORCHESTRATION=machine make api     # machine à états
```

---

## 1. La comparaison hors budget — la régression de l'étape 18

> — un écran gaming, budget 200 $
> — *(après la recommandation)* compare-moi en détail les deux qui dépassent mon budget

**Vise** : deux produits de la zone de tolérance nommés plusieurs fois, avec leurs specs.
C'est la forme exacte qui était impossible avant l'étape 18.

**Échec** : `ecart_non_dit` + `montant_non_fourni` sur le même écart, deux refus, repli.

⚠️ **Le second tour disait « compare-moi les deux premiers en détail », et cette
conversation ratait sa cible** (corrigé à l'étape 20). Le modèle a lu « les deux premiers »
comme les deux premiers **dans le budget** — 64,98 $ et 74,98 $ — et a comparé deux
produits que rien n'obligeait à citer avec un écart. La conversation testait une
comparaison détaillée, pas une comparaison **hors budget** : elle passait sur les deux
orchestrations sans rien prouver de l'étape 18. Une conversation d'essai qui passe sans
atteindre son mécanisme est pire qu'absente — elle rassure.

*La forme visée a bien été observée à l'étape 19, mais ailleurs* : au tour 1 de la nº2 côté
machine, et au tour 1 de la nº6 des deux côtés. Trois fois nommée avec son écart, trois
fois acceptée.

---

## 2. Le produit hors budget nommé dans une question

> — une carte graphique à 800 $
> — *(quand il propose un modèle légèrement au-dessus)* tu me conseilles quoi ?

**Vise** le seul point que l'audit de l'étape 18 laisse ouvert, et **uniquement chez
l'agent** : le texte et la question d'`ask_clarification` sont deux chaînes validées
**séparément**. Un écart dit dans le texte ne couvre pas la question.

**Échec** : un refus d'origine `QUESTION` portant `ecart_non_dit`, alors que le texte
livré, lui, disait bien l'écart.

**La machine ne devrait pas l'avoir** — son second appel est rédaction *ou* question,
jamais les deux. Comparer les deux orchestrations ici est le test.

---

## 3. L'entier nu — le trou connu et assumé

> — montre-moi cinq écrans
> — il en reste combien ?

**Vise** le trou que §7 documente : « un entier nu, sans unité et sans `$`, n'est vérifié
par rien ». La règle 5 ne mord que sur un nombre suivi d'une unité connue.

**Échec attendu : aucun.** Un compte inventé (« il en reste douze » quand le panneau en
montre neuf) passerait le validateur. C'est **assumé** — un validateur qui crie sur « je
vous propose trois modèles » finit débranché. À constater, pas à corriger.

---

## 4. Le jeton de parole, et le desserrage refusé

> — un écran 144 Hz à moins de 200 $
> — *(après la réponse)* bon, monte à 250 et passe en 165 Hz

**Vise** §3.17 : un seul desserrage par message du client. Le second mouvement doit être
refusé, et l'assistant doit **le dire** au lieu de le contourner.

**Échec** : les deux critères bougent, ou l'assistant applique le refus en silence.

⚠️ C'est la moitié non mesurée de la section 9 du prompt — §7 dit qu'aucune attente ne
constate que l'agent *dit* le refus. Ici tu le lis toi-même, ce que le harnais ne sait pas
faire.

---

## 5. Le changement de catégorie, et le budget effacé

> — un écran gaming, 300 $
> — finalement montre-moi plutôt des claviers

**Vise** l'arbitrage D de l'étape 7 : changer de catégorie remet le budget à `None` et paie
le jeton du tour. L'assistant doit **redemander** le budget.

**Échec** : il cherche dans la nouvelle catégorie en reportant les 300 $ en silence. C'est
la seconde source de vérité que §3.10 ferme.

⚠️ `keyboard` a été **retirée du catalogue** à l'étape 3 : c'est aussi un test du chemin
« catégorie hors catalogue ». Pour tester le budget effacé seul, demande plutôt un SSD ou
un processeur.

---

## 6. La question de domaine en plein milieu

> — un écran 27 pouces, 400 $
> — *(après la recommandation)* c'est quoi la différence entre IPS et VA ?
> — et le contraste, ça change quoi ?

**Vise** la section 13 du prompt : refuser le cours de technologie, basculer sur la
répartition du catalogue. Le second message insiste — c'est là que ça cède.

**Échec** : un chiffre de spécification générale (« un contraste typique de 3000:1 »).
⚠️ **Aucune règle ne l'attrape** — un ratio n'est ni un montant ni une valeur unitaire.
C'est la ligne ouverte de §7, et seule ta lecture la voit.

---

## 7. Deux catégories dans un même message

> — il me faut un écran et une carte graphique, 1500 $ pour les deux

**Vise** l'arbitrage K de l'étape 6 : la composition multi-catégories est **hors
périmètre**. L'assistant doit l'annoncer et séquencer, pas bricoler.

**Échec** : il recommande dans les deux catégories, ou promet un budget partagé qu'aucun
code ne suit. §8 de `PROJET.md` dit que le total inter-tours n'est pas suivi — il ne doit
donc rien promettre de tel.

---

## 8. Le zéro résultat, puis le refus d'assouplir

> — un écran 4K 240 Hz à moins de 300 $
> — non, je ne veux pas descendre en dessous de 240 Hz

**Vise** le critère d'acceptation nº6 : dire **pourquoi** avec le diagnostic du moteur,
proposer l'assouplissement le plus rentable, et **ne jamais assouplir de soi-même**.

**Échec** : il assouplit tout seul au second message, ou il recommande quelque chose qui ne
respecte pas le critère tenu.

---

## 9. Le produit désigné par son identifiant

> — *(après une recommandation)* parle-moi de video-card-8e21497852

**Vise** la règle 1 : tout jeton au format d'identifiant doit exister dans le contexte
fourni. Et la règle 3 : le nom se cite **verbatim**, jamais francisé.

**Échec** : un `id` approximatif, ou un nom traduit (« l'Odyssée de Samsung »).

---

## 10. Le prix d'un produit jamais fourni

> — un écran entre 100 et 400 $
> — *(après un sondage, avant toute recommandation)* et le moins cher, il coûte combien ?

**Vise** l'oracle à prix de §7, partiellement fermé à l'étape 9 : un sondage rend une
fourchette exacte, et la borne basse est *presque* le prix d'un produit — mais elle n'est
le prix de personne.

**Échec** : « le moins cher est à 108 $ » en nommant un modèle. La règle 2 doit refuser.
⚠️ Ce qui reste ouvert : un nom **inventé** dans cette phrase passerait, la règle ne
sachant pas qu'un nom qu'elle ne connaît pas est un nom de produit.

---

## Et l'instrument prévu pour ça

```bash
make eval-live                        # 2-3 conversations avec un client simulé
make eval-live PERSONAS="nom nom"     # en choisir
```

Non reproductible — les deux côtés sont non déterministes — et **lancé par aucune commande
automatique**. Il ne mesure rien : il donne à **lire** un dialogue que des scénarios
scriptés ne produisent pas. C'est lui qui a trouvé le tour muet de l'étape 12.
