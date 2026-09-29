# Comment détecter une boucle ou un conflit par un test ?

Brief Kaldera · Phase CONCEPTION, point 4 · 29/09/2026 · Code étudié : commit `37c2cb3`

---

## La réponse en bref

Un test détecte une boucle ou un conflit s'il remplit trois conditions :

1. il **provoque** la situation, au lieu d'attendre qu'elle arrive ;
2. il l'**observe dans les traces** : qui a fait quoi, combien de fois, avec quel statut final ;
3. il **échoue pour la bonne raison** quand le défaut est présent, et passe quand il est corrigé.

On organise ces tests sur quatre niveaux :

- **le dessin de l'équipe**, vérifié sans rien exécuter ;
- **les boucles et les arrêts**, provoqués ;
- **les conflits**, provoqués ;
- **des invariants** : des règles qui doivent être vraies après chaque exécution.

Enfin, on **prouve** que chaque test détecte bien son défaut, en réintroduisant volontairement ce
défaut.

**L'image :** l'exercice d'incendie. On ne vérifie pas une alarme en attendant le feu : on produit de
la fumée, et on regarde si elle sonne. Un détecteur qu'on n'a jamais essayé avec de la fumée ne
prouve rien.

**Vocabulaire.**

- **Test fourni** : l'un des 14 tests du dépôt. On les garde intacts, comme **tests de
  non-régression**, c'est-à-dire comme preuve qu'une correction ne casse rien de ce qui marchait.
- **Test nouveau** : un test à écrire en phase Développement.
- **Réception** : la vérification, par le chef, de ce qu'un agent lui rend (point 2).
- **Oracle** : ce à quoi on compare le résultat pour décider s'il est juste.

Les deux scénarios fournis sont rejoués par `test_scenario_completes_within_budget`. Dans cette
note, « les deux scénarios » désigne ce test.

---

## 1. Les traces que les tests lisent

Un test ne voit que ce que le flux laisse derrière lui. Ces traces sont la **condition préalable**
de tout le reste. Les points 2 et 3 en ont fixé la plupart. Cette note en précise trois.

| Trace                                                   | Ce qu'elle permet de voir                      | Aujourd'hui                            |
| ------------------------------------------------------- | ---------------------------------------------- | -------------------------------------- |
| Journal des agents : agent, étape, action               | qui a traité chaque étape, dans quel ordre     | le nom de l'agent n'est pas enregistré |
| Journal du chef : délégation, réception, arrêt, clôture | chaque décision du chef, et qui a clos le flux | le chef ne journalise rien             |
| Registre d'écriture des artefacts                       | qui a écrit quel artefact, à quelle étape      | inexistant                             |
| Limite d'étapes retenue, notée au départ                | à quelle limite comparer le nombre d'étapes    | inexistant                             |
| Nombre d'étapes confiées                                | un passage de trop                             | disponible (`step_count`)              |
| Statut final et code de la raison d'arrêt               | pourquoi le flux s'est arrêté                  | statut seul, sans raison               |

**Pourquoi un registre d'écriture.** Comparer les artefacts avant et après un agent ne suffit pas.
Au point 1, le writer réécrit `draft` pendant l'étape `REVIEW` avec **la même valeur**, et aucune
différence n'apparaît. Il faut donc que chaque écriture d'artefact passe par l'état, qui note qui
écrit quoi et à quelle étape, même quand la valeur ne change pas.

**Les codes de raison.** Le champ qui porte la raison (point 3, décision 6) contient un code
stable, que les tests comparent. Ce n'est pas une phrase.

| Code                       | Sens                                                        | Défini au |
| -------------------------- | ----------------------------------------------------------- | --------- |
| `invalid_demand` (+ motif) | la demande a échoué à une vérification préalable            | point 3   |
| `role_violation`           | un agent a reçu une étape hors de son rôle                  | point 2   |
| `budget_exceeded`          | un agent a dépassé son budget de tokens                     | point 2   |
| `reception_refused`        | l'artefact attendu manque, ou un autre artefact a été écrit | point 2   |
| `step_limit_reached`       | la limite d'étapes est atteinte                             | point 3   |
| `missing_closure`          | fin atteinte sans clôture par le finalizer                  | point 3   |

Les motifs de `invalid_demand` sont les suivants :

| Motif             | Vérification en échec                                        |
| ----------------- | ------------------------------------------------------------ |
| `empty`           | la demande n'a pas de sujet, ou aucune étape                 |
| `unknown_label`   | un libellé ne correspond à aucune étape de la spécification  |
| `duplicate_step`  | une étape apparaît deux fois                                 |
| `not_finalized`   | la demande ne se termine pas par `FINALIZE`                  |
| `missing_input`   | une étape ne trouve pas son entrée dans une étape précédente |
| `too_many_steps`  | la demande dépasse la limite d'étapes                        |
| `team_incomplete` | une étape n'a pas exactement un agent dans l'équipe          |

---

## 2. Niveau 1 · Tests sur le dessin de l'équipe

**L'image :** la règle d'or de notre fiche du Livrable 1. Certains défauts se voient sur le dessin de
l'équipe, avant même de la faire tourner.

Ces tests n'exécutent aucun flux : ils lisent la composition de l'équipe. Les tests nouveaux lisent
l'équipe **réelle** du chef. Les tests fournis de `test_roles.py`, eux, construisent leur propre
liste d'agents (`tests/test_roles.py:8`). Ils ne verraient donc pas un agent absent de l'équipe
réelle. C'est `test_finalizer_is_registered` qui couvre ce cas.

| Test                                          | Statut  | Détecte                                             | Sur le code actuel, échoue parce que |
| --------------------------------------------- | ------- | --------------------------------------------------- | ------------------------------------ |
| `test_each_step_handled_by_exactly_one_agent` | fourni  | une étape avec deux propriétaires, ou aucun         | `REVIEW` a deux propriétaires        |
| `test_finalizer_is_registered`                | fourni  | un agent absent de l'équipe réelle                  | le finalizer n'y est pas             |
| `test_routing_table_matches_owners`           | nouveau | une table du chef qui contredit les fiches de poste | la table envoie `REVIEW` au writer   |
| `test_every_agent_refuses_every_foreign_step` | nouveau | un agent qui accepte une étape hors de son rôle     | le writer accepte les quatre étapes  |
| `test_agent_descriptions_are_distinct`        | fourni  | deux fiches de poste indiscernables                 | writer et researcher sont identiques |

**Sur `test_every_agent_refuses_every_foreign_step`.** Il généralise le test fourni
`test_writer_refuses_foreign_step`. Il croise les 4 agents avec les 4 étapes : 4 acceptations
(chaque agent, sur sa propre étape) et 12 refus.

**Sur `test_routing_table_matches_owners`.** Une fois la règle 3 du point 2 appliquée, la table se
déduit des fiches de poste, et ce test passe par construction. On le garde comme **garde-fou de
non-régression** : il échouera si quelqu'un réintroduit un jour une table écrite à part.

---

## 3. Niveau 2 · Boucles et arrêts, provoqués

**L'image :** on bloque exprès un poste de l'atelier, pour vérifier que la chaîne s'arrête au lieu
de tourner à vide.

**Point de départ commun.** Sauf mention contraire, chaque test part d'une **demande valide** : un
sujet, les étapes dans le bon ordre, `FINALIZE` en dernier. Il part aussi d'une **équipe
complète**. Sinon, la vérification préalable du point 3 arrêterait le flux avec le code
`invalid_demand`, et le test passerait pour une mauvaise raison.

| Test                                             | Statut  | Ce qu'il provoque                                                                 | Ce qu'il attend                                                                                    |
| ------------------------------------------------ | ------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `test_stuck_agent_is_stopped_at_first_reception` | nouveau | un researcher qui n'écrit rien                                                    | `aborted`, code `reception_refused`, researcher appelé **une seule** fois                          |
| `test_step_guard_stops_at_limit`                 | nouveau | demande `[RESEARCH, FINALIZE]`, limite 2, état fourni avec déjà 2 étapes comptées | `aborted`, code `step_limit_reached`, aucun agent appelé                                           |
| `test_invalid_demands_are_refused`               | nouveau | une demande invalide par motif (7 cas), y compris par un état fourni directement  | `aborted`, code `invalid_demand`, **motif exact attendu**, aucun agent appelé                      |
| `test_route_returns_end_once_all_steps_done`     | fourni  | toutes les étapes traitées                                                        | le chef répond `END`                                                                               |
| `test_missing_closure_is_detected`               | nouveau | un finalizer qui écrit `final` sans passer le statut à `done`                     | `aborted`, code `missing_closure`                                                                  |
| `test_budget_exceeded_stops_flow`                | nouveau | un researcher qui dépasse son budget de tokens                                    | `aborted`, code `budget_exceeded`, finalizer non appelé, aucun artefact écrit (coût fixe, point 3) |
| `test_per_agent_token_budget_is_enforced`        | fourni  | un agent au budget de 50 qui en consomme 100                                      | `BudgetExceeded` levée                                                                             |

- **`test_stuck_agent_is_stopped_at_first_reception` est le test de la boucle du point 1.** Sur le
  code actuel, l'agent bloqué est appelé 50 fois. C'est ce qu'a mesuré la sonde de diagnostic
  (`Livrable_3_Note_diagnostic_schema_cible/outils/sonde_diagnostic.py`).
- **`test_invalid_demands_are_refused` compare le motif exact**, pas seulement le code : les 7
  vérifications partagent le même code `invalid_demand`. Le cas `too_many_steps` remplace ainsi un
  test séparé. Pour le cas `unknown_label`, la demande passe par la lecture, puisque c'est la
  lecture qui reconnaît les libellés.
- **`test_step_guard_stops_at_limit` est le seul moyen d'éprouver le garde-fou.** La demande fournie
  est valide et tient dans sa limite, donc la vérification préalable la laisse passer. C'est l'état
  fourni, déjà à la limite, qui fait réagir le chef.

---

## 4. Niveau 3 · Conflits provoqués

**L'image :** on glisse un intrus dans l'atelier, qui écrit sur la fiche d'un collègue, pour vérifier
que le contrôle le repère.

Même point de départ que le niveau 2.

| Test                                         | Statut  | Ce qu'il provoque                                                   | Ce qu'il attend                                                                                    |
| -------------------------------------------- | ------- | ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `test_each_step_is_done_by_its_owner`        | nouveau | le scénario `happy_path`                                            | journal des agents : researcher, writer, reviewer, finalizer, dans cet ordre                       |
| `test_review_is_routed_to_reviewer`          | fourni  | lecture de la table                                                 | `REVIEW` va au reviewer                                                                            |
| `test_intruder_agent_is_rejected`            | nouveau | un writer qui écrit aussi `review`                                  | `aborted`, code `reception_refused`, reviewer non appelé, artefacts gardés mais marqués incomplets |
| `test_foreign_step_stops_flow_without_retry` | nouveau | la table remplacée de force dans le test (`REVIEW` → writer strict) | `aborted`, code `role_violation`, aucun autre agent tenté sur `REVIEW`, aucun artefact `review`    |
| `test_log_entry_carries_agent_id`            | fourni  | une entrée de journal                                               | l'identifiant de l'agent est présent                                                               |

- **`test_each_step_is_done_by_its_owner` est le test du conflit du point 1.** Sur le code actuel, il
  plante avant d'appeler un agent (`IndexError`), car la demande n'est pas lue. Une fois les
  plantages levés et le journal corrigé, il verrait **writer** à la place de reviewer.
- **Ce qui manquait.** Aucun test fourni ne vérifie **qui** a traité chaque étape : c'est le trou
  relevé au point 1.
- **`test_foreign_step_stops_flow_without_retry` simule une erreur de configuration.** Une fois la
  règle 3 appliquée, une table fausse ne peut pas naître d'elle-même : le test la force. Il vérifie
  ce que fait le chef devant un refus. Il ne doit pas « renvoyer la balle » à un autre agent.

---

## 5. Niveau 4 · Les invariants, vérifiés après chaque exécution

**L'image :** la check-list de sortie d'atelier. Quelle que soit la commande, elle est cochée avant
que la pièce parte.

Un **invariant** est une règle qui doit être vraie après **n'importe quelle** exécution. On l'écrit
une fois, dans une vérification commune, et on l'applique à la fin de chaque test qui exécute un
flux, les deux scénarios compris.

**Ce qu'ils couvrent exactement.** Les invariants portent sur le travail **accepté** par le chef.
Quand un test provoque volontairement une violation (un intrus, par exemple), l'artefact fautif est
marqué incomplet, donc exclu des invariants. Le test vérifie alors que la violation a été
**arrêtée avec le bon code**.

| Invariant                                                                                                                    | Se vérifie avec                         | Détecte                                                   |
| ---------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- | --------------------------------------------------------- |
| I1 · Aucune étape n'est confiée deux fois                                                                                    | journal du chef (délégations)           | la relance, et le ping-pong qui passe par le chef         |
| I2 · Aucun agent n'agit sur une étape sans délégation préalable du chef                                                      | journaux du chef et des agents          | le ping-pong direct, d'un agent à l'autre                 |
| I3 · Chaque étape acceptée a été traitée par son propriétaire                                                                | journal des agents                      | l'agent qui fait le travail d'un autre                    |
| I4 · Chaque artefact accepté est écrit une seule fois, par son propriétaire                                                  | registre d'écriture                     | le chevauchement sur un artefact, même à valeur identique |
| I5 · Le nombre d'étapes confiées ne dépasse pas la limite retenue                                                            | limite notée au départ, `step_count`    | un passage de trop                                        |
| I6 · `done` seulement si la clôture est attribuée au finalizer ; `aborted` toujours avec un code ; jamais `pending` à la fin | journal du chef (clôture), statut, code | la fausse fin, et l'arrêt sans raison                     |

- **Sur I5.** La limite est un paramètre : celle que le chef a notée au départ. I5 ne prouve pas à
  lui seul que `max_steps` est lu. Sur `happy_path`, 4 étapes restent sous une limite de 5, que la
  limite soit lue ou non. C'est `test_step_guard_stops_at_limit` qui le prouve.
- **Sur le ping-pong.** Au point 1, on n'a trouvé aucun vrai aller-retour entre deux agents dans le
  code. I1 et I2 sont donc des **préventions** : ils le détecteraient s'il apparaissait, par exemple
  une fois le chemin « live » branché sur un LLM. C'est la réponse au symptôme « se renvoient la
  balle », quelle que soit son origine exacte.

---

## 6. Les trois faiblesses héritées du point 3

| Faiblesse                                                                      | Réponse                                                                                                                                        |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Le garde-fou du budget d'étapes ne se déclenche plus en fonctionnement normal  | `test_step_guard_stops_at_limit` fournit un état déjà à la limite : c'est un test du garde-fou lui-même                                        |
| `test_step_budget_is_enforced` passerait pour une autre raison                 | on le garde tel quel, et `test_stuck_agent_is_stopped_at_first_reception` vise la bonne raison, avec une demande valide et une équipe complète |
| Le test de bout en bout juge le flux sur la limite qu'il s'est lui-même donnée | on ajoute un oracle indépendant de `max_steps`, détaillé ci-dessous                                                                            |

L'oracle indépendant comprend trois vérifications :

- **le nombre d'étapes** confiées est exactement celui de la demande : 4 pour `happy_path`, 2 pour
  `research_only` ;
- **l'ordre des agents** dans le journal suit celui de la demande (`test_each_step_is_done_by_its_owner`) ;
- **`final`** est construit sur le bon artefact : `review` pour `happy_path`, `research` pour
  `research_only` (décision 5 du point 3).

---

## 7. Prouver que les tests détectent vraiment

**L'image :** on vérifie le détecteur de fumée avec de la fumée.

**Où en sont les tests fournis.** Sur les 14 tests fournis, 12 échouent sur le défaut qu'ils visent :
sur leur propre vérification, ou dans la fonction qu'ils testent. Les 2 autres, les deux cas de
`test_scenario_completes_within_budget`, plantent pour une raison sans rapport (`IndexError` dans
`route`, la demande n'étant pas lue). Les tests nouveaux n'existent pas encore.

Un échec constaté sur le code actuel ne suffit donc pas : il faut vérifier la raison de chaque
échec.

**Le protocole.** Une fois le code corrigé, et pour chaque défaut :

1. on réintroduit **ce seul défaut** ;
2. on relance les tests ;
3. au moins un test doit échouer **sur sa propre vérification**, avec un message qui nomme le défaut ;
4. on retire le défaut, et tout doit repasser.

Un défaut qu'aucun test n'attrape est un trou de la suite, à combler avant de conclure.

| Défaut (relevé aux points 1 à 3)                        | Tests qui doivent l'attraper                                                                                                         |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| La limite `max_steps` n'est pas lue                     | `test_step_guard_stops_at_limit`                                                                                                     |
| La condition de fin est décalée d'un cran (`>`)         | `test_route_returns_end_once_all_steps_done`, les deux scénarios                                                                     |
| Le chef passe lui-même le statut à `done`               | `test_missing_closure_is_detected`, invariant I6                                                                                     |
| `REVIEW` confiée au writer, qui y réécrit son brouillon | `test_review_is_routed_to_reviewer`, `test_routing_table_matches_owners`, `test_each_step_is_done_by_its_owner`, invariants I3 et I4 |
| Le writer déclare aussi `REVIEW`                        | `test_each_step_handled_by_exactly_one_agent`                                                                                        |
| Le writer accepte toutes les étapes                     | `test_every_agent_refuses_every_foreign_step`, `test_writer_refuses_foreign_step`                                                    |
| Writer et researcher ont la même description            | `test_agent_descriptions_are_distinct`                                                                                               |
| Le finalizer est absent de l'équipe                     | `test_finalizer_is_registered`, les deux scénarios                                                                                   |
| Le journal n'enregistre pas l'agent                     | `test_log_entry_carries_agent_id`, invariant I3                                                                                      |
| Le budget de tokens n'est jamais comparé                | `test_per_agent_token_budget_is_enforced`, `test_budget_exceeded_stops_flow`                                                         |
| La demande n'est pas lue                                | `test_load_context_populates_state`, les deux scénarios                                                                              |
| `PROOFREAD` au lieu de `REVIEW`                         | `test_review_label_resolves_to_review_step`, `test_all_business_labels_resolve`                                                      |
| Un agent bloqué est relancé sans fin                    | `test_stuck_agent_is_stopped_at_first_reception`, invariant I1                                                                       |

**Deux précisions sur cette grille.**

- **Deux défauts du point 1 n'y forment qu'une ligne** : « `REVIEW` confiée au writer » et « le
  writer réécrit son brouillon ». Une fois `REVIEW` confiée au reviewer, le writer n'est plus appelé
  à cette étape. On ne peut donc pas réintroduire le second défaut sans le premier.
- **Le chef passe lui-même le statut à `done`** : sur les scénarios, le finalizer passe aussi le
  statut à `done`, donc le statut seul ne trahit pas ce défaut. I6 ne l'attrape que parce que le
  journal attribue la clôture (section 1). Sans cette trace, seul `test_missing_closure_is_detected`
  le verrait.

La grille compte 13 lignes : 12 défauts des points 1 à 3, plus la relance sans fin. Elle devient la
**grille de preuve** de la phase Développement.

---

## 8. Correspondance avec les critères de réussite du brief

| Critère du brief                                            | Tests qui le démontrent                                                                                 |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| L'orchestration ne boucle plus                              | `test_stuck_agent_is_stopped_at_first_reception`, `test_step_guard_stops_at_limit`, invariants I1 et I5 |
| Les conflits sont résolus                                   | niveau 3, invariants I3 et I4 ; I2 en prévention du ping-pong direct                                    |
| Chaque sub-agent tient son rôle, sans empiéter              | niveau 1, `test_intruder_agent_is_rejected`, invariants I3 et I4                                        |
| Le flux respecte la spécification sur les scénarios de test | les deux scénarios, l'oracle indépendant (section 6), `test_invalid_demands_are_refused`, invariant I6  |

---

## 9. Décisions prises, à valider

1. **Les tests et les scénarios fournis ne sont pas modifiés.** Ils servent de non-régression. Les
   tests nouveaux sont ajoutés à côté, dans des fichiers séparés.
2. **Les situations provoquées sont construites dans le code des tests** : agent bloqué, intrus,
   table forcée, demandes invalides. `scenarios_test.json` reste inchangé.
3. **Trois traces s'ajoutent** à celles des points 2 et 3 : le registre d'écriture des artefacts,
   la clôture attribuée dans le journal du chef, et la limite d'étapes notée au départ.
4. **Les raisons d'arrêt sont des codes stables**, et la demande invalide précise son motif.
5. **Les invariants I1 à I6 sont écrits une fois** et appliqués à la fin de chaque test qui exécute
   un flux, sur le seul travail accepté.
6. **Le protocole de la section 7 est obligatoire** avant de déclarer la phase Développement
   terminée. Son résultat est consigné défaut par défaut.
