# Comment le flux doit-il se conformer à la spécification métier ?

Brief Kaldera · Phase CONCEPTION, point 3 · 29/09/2026 · Code étudié : commit `37c2cb3`

---

## La réponse en bref

La spécification (`specs/flow_spec.md`) est un **contrat**. Un flux conforme la respecte en trois
temps :

1. **Avant** : le chef lit la demande et la **vérifie**. Si elle est invalide, rien ne démarre.
2. **Pendant** : une étape à la fois, **dans l'ordre de la demande**, dans le budget, et chaque
   action est journalisée au nom de son auteur.
3. **À la fin** : **seul le finalizer clôt** le travail, puis le chef termine explicitement (`END`).

**L'image :** un atelier qui reçoit un bon de commande. On vérifie le bon avant de lancer la
fabrication. La pièce passe les postes dans l'ordre prévu, sans en sauter. Et seul le contrôle final
signe le bon de livraison.

Le point 2 a fixé les rôles et les frontières. Ce point-ci fixe le **déroulé** du flux.

**Deux mots de vocabulaire.** Le flux finit toujours avec l'un de deux **statuts** :

- `done` : terminé normalement, clos par le finalizer ;
- `aborted` : arrêté, avec une **raison** qui dit pourquoi.

Le code actuel n'a pas de champ pour cette raison (`state.py:10-18`) : il faudra en créer un.

---

## 1. Ce que la spécification exige, et ce que fait le code aujourd'hui

| N° | Exigence de la spécification                                 | Ligne | Aujourd'hui                                                    | Traité en |
| -- | ------------------------------------------------------------ | ----- | -------------------------------------------------------------- | --------- |
| E1 | Enchaîner les étapes dans l'ordre fourni par la demande      | 3-4   | la demande n'est jamais lue (`runner.py:12-13`)                | section 2 |
| E2 | Reconnaître les quatre étapes métier                         | 8-13  | `REVIEW` inconnu, remplacé par `PROOFREAD` (`steps.py:19`)     | section 2 |
| E3 | Confier l'étape à l'agent de la table, un seul par étape     | 26-27 | `REVIEW` confiée au writer                                     | point 2   |
| E4 | Chaque agent refuse une étape hors de son périmètre          | 22    | le writer accepte tout                                         | point 2   |
| E5 | Ne jamais dépasser le budget d'étapes `max_steps`            | 29    | calculé, jamais lu : 50 tours possibles (`runner.py:26-31`)    | section 3 |
| E6 | Un dépassement du budget de tokens interrompt l'agent        | 33-34 | additionné, jamais comparé (`agents/base.py:39-40`)            | section 3 |
| E7 | Journaliser chaque action avec l'identifiant de l'agent      | 35-36 | nom de l'agent reçu, pas enregistré (`logging_utils.py:10-13`) | section 3 |
| E8 | Le finalizer assemble `final` et clôt le flux                | 20    | finalizer absent de l'équipe (`orchestrator.py:13`)            | section 4 |
| E9 | Quand toutes les étapes sont traitées, fin explicite (`END`) | 28    | plantage après la dernière étape, `done` forcé par le chef     | section 4 |

---

## 2. Avant : lire et vérifier la demande

**L'image :** le bon de commande est relu avant de lancer la fabrication. Une commande incomplète
repart chez le client : on ne la découvre pas à mi-chemin.

### Lire la demande (E1)

Le chef lit dans la demande le **sujet** (`topic`) et la **liste des étapes** (`required_steps`).
Aujourd'hui, la fonction chargée de cette lecture ne fait rien (`runner.py:12-13`). Le chef part donc
avec une liste vide et plante aussitôt.

### Reconnaître les étapes (E2)

Les libellés acceptés sont **exactement** les noms de la spécification : `RESEARCH`, `DRAFT`,
`REVIEW`, `FINALIZE`. Aujourd'hui, une table de traduction à part attend `PROOFREAD` au lieu de
`REVIEW` (`steps.py:19`). Dès que la lecture sera écrite, la demande standard plantera
(`KeyError: 'REVIEW'`), comme le montre déjà `test_review_label_resolves_to_review_step`.

C'est la règle 3 du point 2 appliquée aux libellés : le nom de l'étape est déclaré **une seule
fois**, dans la liste des étapes (`steps.py:7-11`). Il n'est pas recopié dans une seconde table qui
pourrait diverger.

### Vérifier la demande avant tout travail

| Vérification                                                                                       | Origine                                                                        |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| La demande contient un sujet non vide et au moins une étape                                        | choix de conception : sans sujet, la recherche n'a pas d'objet                 |
| Chaque libellé est une étape de la spécification                                                   | spécification, l. 8-13                                                         |
| Aucune étape n'apparaît deux fois                                                                  | choix de conception : chaque artefact n'est écrit qu'une fois (point 2)        |
| La demande se termine par `FINALIZE`                                                               | choix de conception, voir décision 2                                           |
| `DRAFT` est précédé de `RESEARCH`, `REVIEW` de `DRAFT`, `FINALIZE` d'au moins une étape de contenu | spécification, l. 11-12 (« à partir de la recherche », « corrections du jet ») |
| Le nombre d'étapes ne dépasse pas `max_steps`                                                      | spécification, l. 29                                                           |
| Chaque étape a exactement un agent dans l'équipe                                                   | spécification, l. 27, et décision 4 du point 2                                 |

**Si une vérification échoue**, le flux ne démarre pas. Il s'arrête en `aborted`, avec la raison
« demande invalide » et le détail de la vérification en échec. Aucun agent n'est appelé. C'est la
même règle d'arrêt qu'au point 2 : pas de tentative, pas de correction silencieuse.

**Dans tous les cas.** La vérification porte sur l'état prêt à démarrer. Elle s'applique donc aussi
quand un test fournit directement cet état (`initial_state`, `runner.py:22-24`), sans passer par la
lecture de la demande.

---

## 3. Pendant : une étape à la fois, dans l'ordre, dans le budget

### L'ordre (E1)

**L'image :** la pièce passe les postes de l'atelier dans l'ordre prévu. Personne ne saute de poste
ni n'en ajoute.

Le chef traite les étapes **dans l'ordre exact de la demande**. Il n'en réordonne aucune, n'en
saute aucune, n'en ajoute aucune. L'étape suivante n'est confiée qu'après la réception de la
précédente (point 2).

### Le budget d'étapes (E5)

**L'image :** le nombre de passages en atelier est plafonné sur le bon de commande.

- **D'où vient la limite.** Le paramètre `max_iterations` passé par l'appelant prime, comme
  aujourd'hui (`runner.py:26-30`). À défaut, la limite est `max_steps`. À défaut encore, c'est le
  filet `HARD_CAP = 50` (`runner.py:9`).
- **La vraie garantie est prise avant le départ.** La demande ne démarre que si elle tient dans son
  budget (section 2). Chaque étape n'est confiée qu'une fois, et le chef ne relance jamais
  (point 2). Le nombre d'étapes confiées ne peut donc pas dépasser la limite.
- **Le contrôle pendant le flux reste, en garde-fou.** Avant chaque délégation, le chef compare le
  nombre d'étapes déjà confiées à la limite. Si elle est atteinte, il arrête en `aborted`, avec la
  raison « budget d'étapes atteint ». Avec les règles ci-dessus, ce contrôle **ne se déclenche
  jamais** sur une demande normale. On le garde pour le cas où une autre règle serait cassée par une
  modification future.

**Un écart à signaler.** La spécification parle du budget « de la demande » (l. 29). Dans les
scénarios, `max_steps` ne se trouve pas dans la demande (`initial_context`), mais dans le résultat
attendu (`expected`, `scenarios_test.json:11` et `:23`). C'est là que le code actuel va le chercher
(`runner.py:29`). Nous proposons de continuer à le lire là, sans modifier les scénarios fournis, et
de signaler l'écart.

Il a une conséquence. Le test de bout en bout vérifie que le flux respecte `max_steps`, alors que
le flux s'est lui-même arrêté sur cette limite. Ce test ne peut donc pas prouver seul qu'on la
respecte.

### Le budget de tokens (E6)

**L'image :** l'enveloppe allouée à un prestataire. Dès qu'elle est dépassée, il s'arrête.

Dès que la consommation d'un agent dépasse son budget, l'agent s'interrompt (`BudgetExceeded`) et le
chef arrête le flux (point 2, section 4). Dans le modèle de coût actuel (un coût fixe par étape,
`agents/base.py:22`), le dépassement se voit **avant** que l'agent travaille : aucun artefact n'est
écrit. Avec un vrai LLM, il pourra survenir en cours de travail : c'est le cas de l'artefact partiel
prévu au point 2.

### Le journal (E7)

**L'image :** le registre de l'atelier. Chaque ligne dit qui, à quel poste, et ce qui a été fait.

Chaque entrée du journal porte **l'identifiant de l'agent**, **l'étape** et **l'action**. Le chef
journalise aussi ses propres décisions, sous son nom :

- la délégation ;
- la réception acceptée ou refusée ;
- l'arrêt, avec sa raison.

---

## 4. À la fin : le finalizer clôt, puis le chef termine

**L'image :** seul le contrôle final signe le bon de livraison. Le chef d'atelier ne le signe pas à
sa place.

### Qui clôt (E8)

Le finalizer rejoint l'équipe. Aujourd'hui, il est absent de la liste des agents
(`orchestrator.py:13`). Il assemble `final`, puis passe le statut à `done`. Personne d'autre ne peut
le faire (règle 2 du point 2).

**Sur quoi il construit `final`** (question laissée ouverte au point 2) : sur l'artefact de contenu
**le plus abouti** présent, c'est-à-dire `review`, à défaut `draft` (le premier jet), à défaut
`research`. Aujourd'hui, il ne lit que `review` (`agents/finalizer.py:15`). Dans le scénario
`research_only`, il produirait donc `final:` sans contenu.

Aucun test fourni n'exige ce choix : le scénario vérifie seulement que `final` existe. C'est une
décision de conception (décision 5). La fiche de poste du finalizer, au point 2, est mise à jour en
conséquence.

### Comment le flux se termine (E9)

Quand toutes les étapes de la demande sont traitées, le chef répond `END`. Aujourd'hui, la
condition de fin est décalée d'un cran : `orchestrator.py:25` utilise « strictement plus grand » au
lieu de « plus grand ou égal », et le chef plante. Il passe aussi le statut à `done` de lui-même
(`runner.py:33-35`) : ce comportement disparaît.

Comme la demande se termine toujours par `FINALIZE` (section 2), le chef arrive à `END` juste après
le finalizer. Si le statut n'est pas `done` à ce moment-là, le flux s'arrête en `aborted`, avec la
raison « fin sans clôture ». C'est un garde-fou : il ne doit jamais se déclencher.

---

## 5. Le parcours attendu sur les scénarios fournis

Ce que le flux conforme doit produire. Les limites viennent de `scenarios_test.json`.

| Scénario        | Parcours attendu                                   | Étapes confiées | Limite `max_steps` | Statut final | Artefacts                      | `final` construit sur |
| --------------- | -------------------------------------------------- | --------------- | ------------------ | ------------ | ------------------------------ | --------------------- |
| `happy_path`    | researcher → writer → reviewer → finalizer → `END` | 4               | 5                  | `done`       | research, draft, review, final | `review`              |
| `research_only` | researcher → finalizer → `END`                     | 2               | 4                  | `done`       | research, final                | `research`            |

Les tests fournis qui vérifient ces exigences échouent tous aujourd'hui :

- **E1** : `test_load_context_populates_state` ;
- **E2** : `test_review_label_resolves_to_review_step`, `test_all_business_labels_resolve` ;
- **E5** : `test_step_budget_is_enforced` ;
- **E6** : `test_per_agent_token_budget_is_enforced` ;
- **E7** : `test_log_entry_carries_agent_id` ;
- **E8** : `test_finalizer_is_registered` ;
- **E9** : `test_route_returns_end_once_all_steps_done` ;
- **tout le parcours** : les deux cas de `test_scenario_completes_within_budget`.

**Une conséquence à connaître.** Avec la vérification de la section 2, `test_step_budget_is_enforced`
passerait **pour une autre raison** que celle qu'il vise. Sa demande (`[RESEARCH]`) ne se termine
pas par `FINALIZE`, et son équipe n'a pas de finalizer. Le flux serait refusé avant de démarrer,
sans que le budget d'étapes soit mis à l'épreuve.

---

## 6. Hors du flux des scénarios

Le chemin « live » (`graph.py`) est aujourd'hui une coquille vide. Le superviseur renvoie l'état tel
quel, et les nœuds des agents ne font rien (`graph.py:18-23`). S'il est câblé, il doit **réutiliser
le même chef** : même lecture, mêmes vérifications, mêmes arrêts. Il ne doit pas en être une
seconde version, qui divergerait comme les trois déclarations de rôle du point 2.

---

## 7. Décisions prises, à valider

1. **La demande est vérifiée avant tout travail** (section 2), y compris quand l'état est fourni
   directement. Une demande invalide ne démarre pas.
2. **Une demande doit se terminer par `FINALIZE`.**
   - *C'est un choix de conception*, pas une exigence écrite de la spécification. La spécification
     dit que le finalizer clôt (l. 20) et que la fin est explicite (l. 28), mais pas qu'il doit
     figurer dans chaque demande.
   - *Pourquoi ce choix :* sans finalizer, personne ne peut clore, et le statut `done` n'aurait plus
     d'auteur.
   - *Ce qu'il coûte :* il rejette la demande `[RESEARCH]` du test `test_step_budget_is_enforced`.
   - Les deux scénarios fournis s'y conforment.
3. **Chaque étape trouve son entrée dans une étape précédente** (spécification, l. 11-12).
   L'absence de doublon et le sujet non vide sont des choix de conception.
4. **`max_steps` est lu dans `expected`**, comme aujourd'hui, et `max_iterations` prime quand il est
   fourni. L'écart avec la spécification est signalé.
5. **`final` est construit sur l'artefact le plus abouti** : `review`, à défaut `draft`, à défaut
   `research`.
   - *L'autre option* était de concaténer tous les artefacts. Nous l'écartons : `review` est déjà la
     version corrigée de `draft` (décision 1 du point 2), qui découle lui-même de `research`.
6. **Le chef journalise ses propres décisions**, et la raison d'un arrêt est conservée dans un champ
   dédié de l'état.

---

## Et ensuite

Le point 4 traitera la question « comment détecter une boucle ou un conflit par un test ? ». Ce
point-ci lui laisse trois constats :

- le garde-fou du budget d'étapes ne se déclenche plus en fonctionnement normal ;
- `test_step_budget_is_enforced` passerait pour une autre raison que celle qu'il vise ;
- le test de bout en bout juge le flux sur la limite que le flux s'est lui-même donnée.
