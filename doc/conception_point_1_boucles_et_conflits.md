# Où l'orchestration boucle-t-elle ou entre-t-elle en conflit, et pourquoi ?

Brief Kaldera · Phase CONCEPTION, point 1 · 29/09/2026 · Code étudié : commit `37c2cb3`

---

## La réponse en bref

L'équipe Kaldera est un **superviseur** : un chef confie chaque étape à un sub-agent, qui lui rend
ensuite la main. Ce schéma a un chemin de retour vers le chef, donc il peut tourner en rond et
exige un frein.

L'orchestration **boucle** dans la boucle du chef (`runner.py`) : le frein prévu n'est jamais
utilisé, et le chef ne sait pas reconnaître la fin du travail.

Elle **entre en conflit** sur l'étape `REVIEW` : deux agents la revendiquent, et le chef la confie
au mauvais.

Le point commun : **les règles de la spécification sont écrites, mais le code ne les applique
pas**.

---

## 1. Où ça boucle

### Le chef redonne la même tâche sans limite réelle

**L'image :** une cheffe de projet à qui l'on a dit « trois essais au plus », et qui recommence
cinquante fois.

- **Où :** `src/kaldera/runner.py:26-31`.
- **Ce qui se passe :** la limite de la demande (`max_steps`) est calculée dans la variable
  `limit`, puis jamais lue. La boucle tourne sur un filet de secours fixé à 50 tours. Et le chef
  ne vérifie pas que l'étape a avancé : si un agent ne progresse pas, il la lui redonne.
- **Preuve :** le test `test_step_budget_is_enforced` demande 3 tours et en obtient **50**.

Sur les scénarios fournis, cette boucle reste **latente**. Les agents actuels font toujours avancer
l'étape, mais un agent branché sur un vrai LLM qui échouerait la déclencherait.

### Le chef ne sait pas finir

**L'image :** un chef arrivé au bas de sa liste, qui cherche la ligne suivante au lieu de dire
« c'est fini ».

- **Où :** `src/kaldera/orchestrator.py:25`, qui teste « strictement plus grand » au lieu de « plus
  grand ou égal ».
- **Ce qui se passe :** après la dernière étape, le chef ne répond pas `END` et plante
  (`IndexError`). Par ailleurs, `runner.py:33-35` inscrit « terminé » de lui-même, même si le
  finalizer n'a pas clos le travail.
- **Preuve :** le test `test_route_returns_end_once_all_steps_done` échoue.

Ce sont les deux faces du risque n° 1 du superviseur dans notre fiche : **il redonne sans cesse la
même tâche, et il ne sait pas quand s'arrêter**.

---

## 2. Où ça entre en conflit

### Deux agents pour la même étape, et le chef choisit le mauvais

**L'image :** deux collègues ont « relecture » dans leur fiche de poste. Le planning l'envoie au
rédacteur, qui réécrit son brouillon. Le relecteur n'est jamais appelé, et le document part sans
avoir été relu.

| Source                                           | Ce qu'elle dit pour `REVIEW`            |
| ------------------------------------------------ | --------------------------------------- |
| Spécification (`specs/flow_spec.md:19`)          | seul le `reviewer` traite `REVIEW`      |
| Table du chef (`orchestrator.py:19`)             | `REVIEW` va au `writer`                 |
| Fiche du writer (`agents/writer.py:12`)          | le writer traite `DRAFT` et `REVIEW`    |
| Refus hors du rôle du writer (`writer.py:14-15`) | le writer accepte **toutes** les étapes |

- **Ce qui se passe :** à l'étape `REVIEW`, le writer refait un brouillon. L'artefact `review`
  n'existe jamais, et le résultat final est assemblé sur une relecture vide.
- **Preuves :** les tests `test_each_step_handled_by_exactly_one_agent` (REVIEW compté deux fois),
  `test_review_is_routed_to_reviewer` et `test_writer_refuses_foreign_step` échouent.

Ce conflit réunit les risques n° 2 et n° 3 du superviseur dans notre fiche : **deux sub-agents dont
les missions se chevauchent, et un sub-agent qui sort de son rôle**.

---

## 3. Pourquoi

1. **Les freins existent à moitié.** La limite d'étapes est calculée mais pas lue. Le budget de
   tokens est additionné mais jamais comparé (`agents/base.py:39-40`). Le refus hors du rôle
   existe, mais le writer le contourne.
2. **Le rôle de chaque agent est déclaré à trois endroits du code** (la table du chef, `handles` et
   `accepts`), sans rien qui vérifie qu'ils concordent. Pour `REVIEW`, ils se contredisent.
3. **Le chef délègue sans réceptionner.** Il ne vérifie ni que l'étape a avancé, ni que l'artefact
   attendu a été produit, ni qui a travaillé.
4. **Les traces ne disent pas qui a fait quoi.** Le journal reçoit le nom de l'agent mais ne
   l'enregistre pas (`logging_utils.py:10-13`). Il affiche « a traité REVIEW » sans dire que c'est
   le writer : le conflit est invisible dans les traces. Tests en échec :
   `test_log_entry_carries_agent_id` et, pour le budget, `test_per_agent_token_budget_is_enforced`.

---

## 4. Et les symptômes du brief ?

| Symptôme du brief                         | Où il naît                                                              |
| ----------------------------------------- | ----------------------------------------------------------------------- |
| Deux sub-agents se renvoient la balle     | Le conflit sur `REVIEW` : responsabilité floue entre writer et reviewer |
| L'orchestration boucle                    | La limite non lue et la fin non reconnue (section 1)                    |
| Un sub-agent fait le travail d'un autre   | Le writer occupe le poste `REVIEW` et accepte toutes les étapes         |
| Le flux ne respecte plus la spécification | Notamment la relecture absente et le statut « terminé » forcé           |

**Sur « se renvoient la balle » :** on le lit au sens de l'expression française, se rejeter une
responsabilité, et non comme un ping-pong technique A → B → A. Dans un superviseur, deux sub-agents
ne se parlent jamais directement : la balle ne peut revenir que par le chef. C'est ce qui se passe
ici. Le writer rend son brouillon, et le chef le lui renvoie pour `REVIEW` au lieu de l'envoyer au
reviewer. Un ping-pong strict entre deux agents n'existe pas dans ce code. Ce point reste à
confirmer avec le formateur.

---

## Rejouer les preuves

Depuis la racine du dépôt :

```bash
uv sync
uv run python -m pytest -rA --tb=line
```

Au commit `37c2cb3`, les 14 tests échouent. Les 7 tests cités ci-dessus concernent les boucles, les
conflits, la traçabilité et le budget. Les 7 autres relèvent des
rôles (`test_agent_descriptions_are_distinct`) et de la conformité à la spécification (point 3 de
la conception).
