# Quel rôle clair attribuer à chaque sub-agent (frontières) ?

Brief Kaldera · Phase CONCEPTION, point 2 · 29/09/2026 · Code étudié : commit `37c2cb3`

---

## La réponse en bref

Chaque sub-agent reçoit **une fiche de poste** qui répond aux quatre questions du bon brief de notre
fiche : quoi, jusqu'où, sous quelle forme, quand s'arrêter. Il reçoit aussi **un badge**, qui limite
ce qu'il peut lire et écrire.

Trois règles rendent ces frontières solides :

1. **une étape, un seul agent** ;
2. **un artefact, un seul propriétaire** ;
3. **le rôle est déclaré à un seul endroit**.

Le chef, lui, ne produit rien. Il confie l'étape, **vérifie ce qu'on lui rend**, puis fait avancer
le flux ou l'arrête. Il ne relance jamais.

---

## 1. Les fiches de poste des sub-agents

**L'image :** le prestataire de notre fiche. Il a une mission précise, un badge qui n'ouvre que
certaines portes, il rend son travail puis s'en va.

Dans notre fiche, le badge limite les **outils**. Les agents de Kaldera n'ont pas d'outils : ils
lisent et écrivent des **artefacts** dans un état partagé. Le badge porte donc ici sur les
artefacts.

| Agent      | Quoi : l'étape (la seule) | Mission                                          | Lit                                                       | Forme : l'artefact écrit (seul propriétaire)           | Jusqu'où : ne fait jamais                              |
| ---------- | ------------------------- | ------------------------------------------------ | --------------------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------ |
| researcher | `RESEARCH`                | Collecter les informations sur le sujet          | le sujet de la demande                                    | `research`                                             | rédiger, relire, clore                                 |
| writer     | `DRAFT`                   | Rédiger un premier jet à partir de la recherche  | `research`                                                | `draft`                                                | relire, y compris son propre jet ; modifier `research` |
| reviewer   | `REVIEW`                  | Relire le jet et en produire la version corrigée | `draft`                                                   | `review`                                               | modifier `draft` ; renvoyer le jet au writer           |
| finalizer  | `FINALIZE`                | Assembler le résultat final et clore le flux     | `review`, à défaut `draft`, à défaut `research` (point 3) | `final`, et il est le seul à passer le statut à `done` | refaire une étape précédente                           |

**Quand s'arrêter ?** Dès que l'artefact est écrit, l'agent rend la main au chef. Il ne réessaie
pas de lui-même.

Chaque agent a aussi **une description qui lui est propre**. Aujourd'hui, le writer porte celle du
researcher (`agents/writer.py:11`). Une description doit dire ce qui distingue l'agent des autres.

---

## 2. Le rôle du chef

**L'image :** une cheffe de projet qui ne fait pas le travail elle-même, mais qui **signe le bon de
réception** avant de passer à la suite.

| Le chef fait                                                                          | Le chef ne fait jamais                            |
| ------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Lire l'étape courante et la confier à son unique propriétaire                         | Produire un artefact                              |
| Vérifier ce qui revient : l'artefact attendu est écrit, et aucun autre n'a été touché | Passer lui-même le statut à `done`                |
| Faire avancer l'étape, seulement après cette vérification                             | Relancer un agent ou confier son étape à un autre |
| Arrêter le flux dès qu'une frontière est franchie (section 4)                         | Redonner une étape déjà traitée                   |

**Changement par rapport au code actuel.** Aujourd'hui, c'est l'agent qui fait avancer l'étape
(`agents/base.py:44`), et le chef ne vérifie rien. Au point 1, on a vu que la boucle naît
justement là : un agent qui n'avance pas, sans que le chef s'en aperçoive. Désormais, le chef
réceptionne, puis avance ou arrête. Il ne relance jamais. La boucle « le chef redonne la même
tâche » n'a donc plus de chemin.

La fin normale du flux (limite `max_steps`, clôture par le finalizer, `END`) relève du point 3.

---

## 3. Les trois règles qui tiennent les frontières

### Règle 1 · Une étape, un seul agent

C'est ce qu'exige la spécification (`specs/flow_spec.md:27`). Chaque étape doit avoir **exactement
un** propriétaire :

- **pas deux**, comme aujourd'hui `REVIEW`, revendiquée par le writer et le reviewer ;
- **pas zéro**, comme aujourd'hui `FINALIZE`, dont l'agent n'est pas dans l'équipe.

Cette règle se vérifie **avant** de lancer le flux, en regardant la composition de l'équipe, comme
la règle d'or de notre fiche se vérifie sur le dessin.

### Règle 2 · Un artefact, un seul propriétaire

**L'image :** un seul stylo par document.

Chaque artefact n'est écrit que par son propriétaire, une seule fois. De même, seul le finalizer
peut passer le statut à `done`. C'est la parade que notre fiche donnait pour le schéma
parallèle : un seul agent écrit le document final. Elle vaut ici pour chaque artefact.

**Qui la fait respecter ?** Aujourd'hui, tous les agents écrivent dans le même état partagé, sans
aucun contrôle. Rien n'empêche le writer d'écrire `review`. C'est la **réception par le chef** qui
tient cette règle : il compare les artefacts avant et après le passage de l'agent. Seul l'artefact
attendu doit être apparu, et rien d'autre ne doit avoir changé.

Cette règle empêche le défaut vu au point 1 : le writer qui réécrit `draft` pendant l'étape
`REVIEW`.

### Règle 3 · Le rôle est déclaré à un seul endroit

Aujourd'hui, le rôle d'un agent est écrit à trois endroits : la table du chef, la liste `handles` de
l'agent et sa méthode `accepts`. Pour `REVIEW`, ces trois endroits se contredisent.

Pour le futur code : chaque agent déclare **une fois** son étape et l'artefact qu'il écrit. Tout le
reste en découle :

- la table du chef ;
- le refus hors du rôle ;
- la liste des artefacts que le chef vérifie à la réception ;
- le prompt système, déjà fabriqué à partir de `handles` (`agents/base.py:25-30`).

Aucun agent ne doit pouvoir contourner le refus, comme le fait aujourd'hui le writer, dont
`accepts` répond toujours oui (`writer.py:14-15`). Une contradiction devient ainsi **impossible par
construction**, au lieu de devoir être repérée.

---

## 4. Ce qui se passe à la frontière

Trois situations franchissent une frontière. Le chef y répond toujours de la même façon : il
**arrête le flux**, avec le statut `aborted` (déjà prévu par le code, `runner.py:41`) et la
**raison nommée**. Il ne relance pas et ne tente pas un autre agent.

| Situation                                                        | Raison nommée      | Artefact partiel               |
| ---------------------------------------------------------------- | ------------------ | ------------------------------ |
| L'agent reçoit une étape hors de son rôle                        | refus hors du rôle | aucun, l'agent n'a rien écrit  |
| L'agent dépasse son budget de tokens                             | budget dépassé     | conservé mais marqué incomplet |
| À la réception, l'artefact manque, ou un autre artefact a changé | réception refusée  | conservé mais marqué incomplet |

**Pourquoi arrêter plutôt que réessayer.** La table étant fixe, chacune de ces situations signale
une erreur réelle. Réessayer la masquerait et recréerait la boucle du point 1. Essayer un autre
agent recréerait le « renvoi de balle ».

**Pas de transfert d'agent à agent.** Chaque agent rend la main au chef : c'est notre distinction
« rendre la main » (sub-agent) contre « passer la main » (transfert). Le ping-pong **direct** entre
deux agents devient impossible. Le ping-pong **par le chef**, celui du point 1, est fermé à son tour
par la règle « le chef ne relance jamais ».

À noter : aujourd'hui, le budget de tokens est additionné mais jamais comparé
(`agents/base.py:39-40`). La deuxième ligne du tableau suppose donc que cette comparaison soit
ajoutée.

---

## 5. Ce que ces rôles corrigent du point 1

| Défaut constaté au point 1                              | Ce qui le corrige                                                      |
| ------------------------------------------------------- | ---------------------------------------------------------------------- |
| `REVIEW` revendiquée par deux agents, confiée au writer | Règles 1 et 3                                                          |
| Le writer accepte toutes les étapes                     | Règle 3 et refus effectif (section 4)                                  |
| Le writer réécrit son brouillon à l'étape `REVIEW`      | Règle 2, tenue par la réception du chef                                |
| Le finalizer absent de l'équipe                         | Règle 1 : aucune étape sans propriétaire                               |
| Writer et researcher ont la même description            | Fiches de poste distinctes (section 1)                                 |
| Le chef passe lui-même le statut à `done`               | Règle 2 : ce statut est réservé au finalizer                           |
| Un agent bloqué est relancé sans fin                    | Réception par le chef, puis arrêt, jamais de relance (sections 2 et 4) |

Restent pour le point 3 : la limite `max_steps` lue enfin, la fin de flux explicite et la lecture de
la demande. Pour vérifier « qui a fait quoi », le journal devra aussi enregistrer le nom de l'agent.

**Les tests fournis vérifient déjà une partie de ces rôles**, et échouent tous aujourd'hui :
`test_each_step_handled_by_exactly_one_agent`, `test_writer_refuses_foreign_step`,
`test_agent_descriptions_are_distinct`, `test_review_is_routed_to_reviewer`,
`test_finalizer_is_registered`. Aucun ne vérifie encore la règle 2, la réception par le chef ni
l'arrêt de la section 4 : ce sera le point 4.

---

## 6. Décisions prises, à valider

1. **Le reviewer produit la version corrigée** dans `review`, sans modifier `draft` et sans renvoyer
   le jet au writer.
   - *Pourquoi :* la spécification dit « relecture **et corrections** du jet ». Le flux est linéaire,
     sans retour au writer, et le finalizer assemble `final` à partir de `review`
     (`agents/finalizer.py:15`).
   - *À corriger en conséquence :* la description actuelle du reviewer, « signale les corrections à
     apporter » (`reviewer.py:11`). Elle laisse des corrections que personne n'appliquerait.
   - *L'autre option* était un aller-retour rédacteur-relecteur (évaluateur-optimiseur). Elle
     ajouterait un chemin de retour, donc un risque de boucle, que la spécification ne demande pas.
2. **L'avancement de l'étape passe de l'agent au chef**, après réception.
3. **Toute frontière franchie arrête le flux** (statut `aborted`, raison nommée). Aucune relance,
   aucun autre agent.
4. **La composition de l'équipe est vérifiée avant le lancement** : chaque étape a exactement un
   propriétaire. La spécification ne le demande pas, mais c'est la règle 1 appliquée au plus tôt.

**Question ouverte, renvoyée au point 3.** Le scénario `research_only` n'a pas de relecture. Sur
quoi le finalizer doit-il alors construire `final` ? Aujourd'hui, le flux plante avant d'y arriver.
Une fois les plantages levés, le finalizer produirait un résultat vide, faute de `review`.
