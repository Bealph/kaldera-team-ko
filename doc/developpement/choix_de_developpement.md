# Développement · corrections et choix

Brief Kaldera « L'équipe d'agents qui se marche dessus » · Phase DÉVELOPPEMENT · 30/09/2026
Point de départ : commit `37c2cb3` (14 tests fournis sur 14 en échec). Référence de conception :
`doc/livrable_conception/note_diagnostic_et_schema_cible.md` et ses décisions D1 à D9, validées le
30/09/2026.

---

## En bref

- **L'orchestration ne boucle plus.** Le chef réceptionne ce que chaque agent lui rend. Il avance,
  relance une seule fois si la réception est refusée, ou arrête. La limite d'étapes est enfin lue,
  et le chef tient son propre compte : aucun agent ne peut sauter une étape ni rallonger la boucle.
- **Les conflits sont résolus.** Chaque étape a un seul propriétaire, déclaré une seule fois ; la
  table du chef s'en déduit. Le writer ne revendique plus `REVIEW`, et le reviewer fait la relecture.
  Un agent qui écrit hors de son rôle est vu, et son passage est annulé.
- **Le flux respecte la spécification sur les scénarios fournis.** `happy_path` et `research_only`
  se terminent en `done`, dans le bon ordre, avec les bons artefacts.
- **C'est prouvé.**
  - Les 14 tests fournis passent, sans avoir été modifiés.
  - 37 cas de test nouveaux passent aussi.
  - Chacun des 21 défauts de la grille de preuve, réintroduit seul, fait échouer au moins un test
    désigné : les 13 du diagnostic et 8 propres à la cible.

---

## 1. Ce qui a été corrigé

| N° du diagnostic | Défaut                                                                      | Correction                                                                                            | Fichier                                  |
| ---------------- | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| ①                | la limite `max_steps` est calculée mais jamais lue                          | le chef compare ses délégations à la limite avant chacune                                             | `runner.py`                              |
| ①                | le chef ne vérifie pas que l'étape avance                                   | réception après chaque agent ; l'avancement passe de l'agent au chef                                  | `runner.py`, `agents/base.py`            |
| ②                | condition de fin décalée d'un cran (`>`)                                    | `>=` : le chef répond `END` après la dernière étape                                                   | `orchestrator.py`                        |
| ②                | le chef passe lui-même le statut à `done`                                   | seul le finalizer passe à `done` ; sinon `missing_closure`                                            | `runner.py`                              |
| ③                | `REVIEW` confiée au writer ; table, `handles` et `accepts` en contradiction | table déduite des fiches de poste ; le writer ne déclare que `DRAFT` ; `accepts` n'est plus contourné | `orchestrator.py`, `agents/writer.py`    |
| ③                | writer et researcher ont la même description                                | descriptions distinctes pour le writer et le reviewer                                                 | `agents/writer.py`, `agents/reviewer.py` |
| ④                | le journal n'enregistre pas l'agent                                         | chaque entrée porte `agent_id`, `step` et `message`, y compris pour le chef                           | `logging_utils.py`                       |
| ④                | le budget de tokens n'est jamais comparé                                    | un dépassement lève `BudgetExceeded`, et le chef arrête en `budget_exceeded`                          | `agents/base.py`, `runner.py`            |
| ⑤                | la demande n'est pas lue                                                    | `load_context` lit le sujet et les étapes                                                             | `runner.py`                              |
| ⑤                | `PROOFREAD` au lieu de `REVIEW`                                             | la table des libellés se déduit de l'énumération des étapes                                           | `steps.py`                               |
| ⑤                | le finalizer est absent de l'équipe                                         | le finalizer rejoint l'équipe                                                                         | `orchestrator.py`                        |

---

## 2. Comment les décisions D1 à D9 sont appliquées

| Décision | Ce qu'elle dit                                            | Où elle vit dans le code                                                              |
| -------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| D1       | le reviewer produit la version corrigée                   | `agents/reviewer.py` : écrit `review`, ne touche pas `draft`                          |
| D2       | le chef fait avancer l'étape, après réception             | `runner.py` : réception, puis `state.advance()` ; `agents/base.py` n'avance plus      |
| D3       | une relance unique, seulement après une réception refusée | `runner.py` : drapeau `retried`, remis à zéro à chaque étape acceptée                 |
| D4       | demande et équipe vérifiées avant tout travail            | `orchestrator.py` : `check_demand`, appelée aussi quand l'état est fourni directement |
| D5       | `FINALIZE` non exigé au départ                            | `runner.py` : à `END`, un statut autre que `done` donne `missing_closure`             |
| D6       | `max_steps` lu dans `expected`, `max_iterations` prime    | `runner.py` : limite notée dans `state.step_limit` ; 50 par défaut                    |
| D7       | `final` construit sur le plus abouti                      | `agents/finalizer.py` : `review`, sinon `draft`, sinon `research`                     |
| D8       | codes d'arrêt stables, journal du chef                    | `state.stop_reason` ; le chef journalise sous `supervisor`                            |
| D9       | tests fournis intacts, tests nouveaux à côté, grille      | `tests/test_orchestration_cible.py`, `scripts/grille_de_preuve.py`                    |

---

## 3. Ce que la revue du code a fait ajouter

Une revue indépendante du code, faite après la première version, a trouvé trois failles bloquantes.
Elles sont corrigées, et chacune est couverte par un test et par une ligne de la grille.

- **Un agent pouvait piloter le flux à la place du chef.** Un agent qui appelait lui-même `advance`
  faisait sauter une étape sans que rien ne le signale. Un agent qui reculait le compteur pouvait
  faire tourner le flux sans fin.
  - *Correction* : le chef tient son propre compte de délégations. Il vérifie après chaque agent
    que l'étape, le compteur et la demande n'ont pas bougé, puis il reprend la main sur l'état.
- **Les écritures refusées restaient dans l'état.** Un artefact écrit par un intrus pouvait finir
  dans `final`.
  - *Correction* : un passage refusé est **annulé**. L'état revient à ce qu'il était avant l'agent,
    et les écritures annulées restent au registre, marquées comme refusées.
- **Certaines écritures échappaient au registre** : suppression, `|=`, écriture directe sur le
  dictionnaire, remplacement du magasin.
  - *Correction* : le magasin trace aussi les suppressions. Le chef compare en plus le contenu
    avant et après chaque agent, ce qui voit toute écriture, même hors du registre.

Elle a aussi fait ajouter des vérifications et un code d'arrêt :

| Ajout                                     | Pourquoi                                                                     |
| ----------------------------------------- | ---------------------------------------------------------------------------- |
| motif `finalize_not_last`                 | `FINALIZE`, s'il est demandé, doit être la dernière étape : il clôt le flux  |
| motif `state_not_fresh`                   | un état déjà entamé (statut, étape courante, artefacts) ne doit pas démarrer |
| motif `invalid_limit`                     | une limite qui n'est pas un entier positif ou nul est refusée                |
| motif `unknown_label` pour un état fourni | les libellés sont vérifiés même sans passer par la lecture de la demande     |
| `team_incomplete` élargi                  | une étape revendiquée par deux agents, ou un agent mal nommé, est refusé     |
| code `agent_error`                        | un agent qui plante arrête le flux avec un code, et son passage est annulé   |
| invariant I7                              | un flux clos a accepté chaque étape demandée une fois, dans l'ordre          |

---

## 4. Vérification

| Contrôle                                    | Résultat                                                             |
| ------------------------------------------- | -------------------------------------------------------------------- |
| 14 tests fournis                            | 14 passent (0 au départ), sans modification                          |
| Tests nouveaux (`test_orchestration_cible`) | 37 cas passent, dans 20 fonctions                                    |
| Grille de preuve, 21 défauts réintroduits   | 21 attrapés sur 21 ; la référence sans défaut passe entièrement      |
| `ruff check` (src, tests, scripts)          | aucun défaut                                                         |
| `mypy src`                                  | aucun défaut                                                         |
| Scénarios via `python -m kaldera.cli`       | `happy_path` : `done`, 4 étapes ; `research_only` : `done`, 2 étapes |
| Chemin « live » (`graph.py`)                | se compile, avec les quatre agents et le superviseur                 |

**Les tests nouveaux**, rangés par niveau comme au point 4 de la conception :

- **dessin de l'équipe** : la table du chef correspond aux fiches de poste ; chaque agent refuse les
  étapes des autres (12 refus, 4 acceptations) ;
- **boucles et arrêts** :
  - un agent bloqué est appelé deux fois, puis le flux s'arrête en `reception_refused` ;
  - la relance est accordée une fois par étape ;
  - la limite est atteinte, soit par un état fourni, soit par de vraies relances ;
  - demandes invalides, un cas par motif ;
  - fin sans clôture ; budget dépassé ; agent qui plante ;
- **conflits** :
  - chaque étape est traitée par son propriétaire, dans l'ordre, avec le nombre exact d'étapes et
    `final` construit sur le bon artefact ;
  - un writer intrus est rejeté ;
  - un refus hors du rôle ne fait tenter aucun autre agent ;
  - seul le finalizer peut clore ;
  - aucun agent ne pilote la progression ;
  - les écritures refusées sont annulées ;
  - toute écriture hors du rôle est vue ;
- **invariants I1 à I7**, vérifiés à la fin de chaque test qui exécute un flux.

---

## 5. Écarts et limites

- **Deux décisions diffèrent de la note initiale**, D3 et D5. Elles ont été modifiées à la
  validation, et les notes de conception ont été mises à jour (encadré « Mise à jour du
  30/09/2026 »).
- **Un passage refusé est annulé**, alors que la conception prévoyait de le conserver en le marquant
  incomplet. C'est la revue du code qui a montré qu'un artefact conservé pouvait contaminer la suite.
  Les notes de conception le signalent.
- **Les tests fournis n'ont pas été reformatés.** `ruff format` propose d'ajouter une ligne vide dans
  des fichiers d'origine ; ce serait modifier les tests fournis, ce que D9 exclut. Seul un
  commentaire ajouté localement dans `tests/test_runner.py` diffère du commit d'origine.
- **Le chemin « live » (`graph.py`) est câblé.** Le `StateGraph` réutilise `route` et
  `check_demand` du chef déterministe : mêmes garde-fous (rôle, budget, limite d'étapes, clôture
  par le finalizer), mais chaque agent produit son artefact via un vrai appel LLM
  (`Agent.act_with_llm`, `llm.py`). Le runner déterministe (`runner.py`), lui, reste inchangé et
  reste le point d'entrée des scénarios rejouables. Voir `tests/test_graph.py`.
  - ponytail : contrairement au chef déterministe, une réception refusée sur ce chemin arrête le
    flux directement, sans relance unique. À ajouter si le chemin live doit un jour rejouer une
    étape.
- **Un vrai LLM est testé.** `tests/test_graph.py::test_run_live_completes_with_a_real_llm` appelle
  l'API Azure AI (endpoint compatible OpenAI, `langchain_openai.ChatOpenAI` — `langchain-azure-ai`
  cible l'API azure-ai-inference, incompatible avec cet endpoint, vérifié à la main). Le test se
  saute si les identifiants Azure AI (`AZURE_AI_ENDPOINT`, `AZURE_AI_API_KEY`, `AZURE_AI_MODEL`,
  via `.env` ou l'environnement) sont absents.
- **`max_steps` est maintenant lu dans la demande (`initial_context`) en priorité**, conformément à
  la spécification, avec repli sur `expected` puis sur `HARD_CAP` (`runner.py`). Les scénarios
  fournis ne sont pas modifiés : ils continuent de fonctionner via le repli.
- **Ce que le code ne peut pas empêcher.** En Python, un agent qui écrirait volontairement dans
  l'état en contournant toutes les interfaces n'est pas bloqué au moment où il écrit. Mais le chef
  voit l'écart à la réception, et il annule le passage.

---

## Rejouer

Depuis la racine du dépôt :

```bash
uv sync
uv run python -m pytest -p no:cacheprovider -q
uv run python scripts/grille_de_preuve.py
uv run python -m kaldera.cli
```

Sur ce poste, `pytest.exe` est bloqué par la stratégie de contrôle d'application : il faut passer
par `python -m pytest`. Sous PowerShell, définir `$env:PYTHONIOENCODING = 'utf-8'` avant la grille.
