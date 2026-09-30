# GUI pédagogique Kaldera, déploiement Azure, CI/CD — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une GUI Gradio publique (déterministe / vrai LLM / garde-fous cassés en direct),
déployée sur Azure Container Apps, redéployée automatiquement par GitHub Actions (OIDC, sans
secret longue durée) — le 4e livrable du brief (URL de test fonctionnel).

**Architecture:** Trois modules purs et testables sans Gradio
(`broken_registries.py` réutilise les agents existants avec un `act()` cassé,
`runners.py` enveloppe `run_scenario`/`build_graph().stream()` en fonctions simples,
`cost_guard.py` limite la fréquence des vrais appels LLM), câblés dans `app.py` (Gradio Blocks, 3
onglets). Zéro changement à `runner.py`/`graph.py`/`orchestrator.py`. Conteneurisé
(`Dockerfile.web`), déployé sur Azure Container Apps (scale-to-zero), image poussée sur
`ghcr.io`, pipeline GitHub Actions authentifié en OIDC fédéré vers Azure.

**Tech Stack:** Python 3.11, Gradio (`>=5,<6`), LangGraph (déjà présent), Docker, Azure Container
Apps, GitHub Actions (`astral-sh/setup-uv`, `docker/login-action`, `docker/build-push-action`,
`azure/login`, `azure/CLI`).

**Spec:** `doc/superpowers/specs/2026-09-30-webapp-azure-cicd-design.md`

## Global Constraints

- Python `>=3.11,<3.12` (contrainte existante de `pyproject.toml`, inchangée).
- `gradio>=5,<6` en dépendance optionnelle (`[project.optional-dependencies] webapp`), jamais dans
  les dépendances du cœur de la bibliothèque.
- Aucune modification de `src/kaldera/runner.py`, `src/kaldera/graph.py`,
  `src/kaldera/orchestrator.py` (validé dans la spec, section 3).
- Port Gradio fixe : `7860`, identique dans `app.py` (`server_port`), `Dockerfile.web` (`EXPOSE`)
  et la cible d'ingress du Container App.
- Noms de ressources Azure fixes et identiques partout (guides, workflow) :
  groupe de ressources `rg-kaldera-demo`, environnement `env-kaldera-demo`, Container App
  `kaldera-webapp-demo`.
- Image : `ghcr.io/sofiane-git/kaldera-webapp` (`sofiane-git` = propriétaire du dépôt de base,
  résolu automatiquement en CI par `github.repository_owner` — le déploiement tourne depuis ce
  dépôt, pas depuis un fork).
- Versions d'actions GitHub épinglées : `actions/checkout@v4`, `astral-sh/setup-uv@v3`,
  `docker/login-action@v3`, `docker/build-push-action@v6`, `azure/login@v2`, `azure/CLI@v2`.
- Authentification GitHub → Azure : OIDC fédéré uniquement (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
  `AZURE_SUBSCRIPTION_ID` en secrets GitHub — jamais de secret client, jamais de JSON
  `AZURE_CREDENTIALS`).

## Review Focus

- Sujet vide ou étapes vides soumis via le formulaire → `run_deterministic`/`run_guardrail` ne
  doivent pas planter, doivent renvoyer `stop_reason="invalid_demand:empty"` (Task 2).
- Étapes dupliquées soumises (cas improbable côté `CheckboxGroup`, mais l'API `runners.py` doit
  rester sûre si un appelant futur les envoie) → `stop_reason="invalid_demand:duplicate_step"`,
  pas d'exception (Task 2).
- Panne réseau/API pendant `.stream()` (vrai LLM) → capturée dans `stream_live`, jamais propagée
  telle quelle jusqu'à la callback Gradio ; dernier chunk `stop_reason="llm_error"` (Task 2).
- Double déclenchement rapide du bouton « vrai LLM » (double-clic, ou F5 puis reclic) avant la fin
  du délai → le deuxième appel n'invoque jamais `runners.stream_live`/`build_llm` (donc aucun coût
  réel), et l'utilisateur voit un message de délai plutôt qu'un silence (Task 3 pour le verrou,
  Task 4 pour vérifier que la callback le respecte réellement).
- Défaut inconnu passé à `run_guardrail` (bouton mal câblé, faute de frappe) → erreur explicite
  (`ValueError`) plutôt qu'un comportement silencieux incorrect (Task 1).

---

## Task 1 : Registres d'agents cassés (`broken_registries.py`)

**Files:**
- Create: `src/kaldera/webapp/__init__.py`
- Create: `src/kaldera/webapp/broken_registries.py`
- Test: `tests/test_webapp_guardrails.py`

**Interfaces:**
- Consumes : `kaldera.agents.base.RoleViolation`, `kaldera.agents.researcher.Researcher`,
  `kaldera.agents.writer.Writer`, `kaldera.agents.reviewer.Reviewer`,
  `kaldera.agents.finalizer.Finalizer`, `kaldera.runner.run_scenario`.
- Produces : `DEFECTS: tuple[str, ...]` (les 4 clés valides), et
  `scenario_for(defect: str) -> tuple[dict, dict | None, int | None]` — renvoie
  `(scénario, agents_by_name, max_iterations)`. `agents_by_name=None` signifie l'équipe normale ;
  `max_iterations=None` signifie pas de limite forcée (le `run_scenario` appelant utilise son
  défaut). Lève `ValueError` si `defect` n'est pas dans `DEFECTS`.

Un point technique vérifié à la main sur `runner.py` avant d'écrire ce plan, parce que le
mécanisme esquissé dans la spec pour « limite d'étapes » (`max_iterations=0`) ne fonctionne pas :
avec `limit=0`, `check_demand()` refuse la demande *avant* même de démarrer
(`len(steps) > limit` → `invalid_demand:too_many_steps`), on n'atteint jamais
`step_limit_reached`. Le vrai mécanisme : un agent qui échoue une fois puis réussit à la relance
consomme 2 délégations pour 1 étape ; avec `max_iterations` réglé exactement au nombre d'étapes
requises (aucune marge), la délégation suivante déclenche `step_limit_reached`. Trace complète
dans le journal de la session de brainstorming, section 6 du fichier `broken_registries.py`
ci-dessous reproduit cette mécanique.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_webapp_guardrails.py
"""Les 4 boutons « casser un garde-fou » de la GUI rejouent en direct les défauts historiques,
via des registres d'agents substitués en mémoire — jamais de modification de fichier source."""

from __future__ import annotations

import pytest

from kaldera.runner import run_scenario
from kaldera.webapp import broken_registries as br


def _run(defect: str):
    scenario, registry, max_iterations = br.scenario_for(defect)
    return run_scenario(scenario, agents_by_name=registry, max_iterations=max_iterations)


def test_role_violation_defect_stops_with_role_violation():
    state = _run("role_violation")
    assert state.status == "aborted"
    assert state.stop_reason == "role_violation"


def test_budget_exceeded_defect_stops_with_budget_exceeded():
    state = _run("budget_exceeded")
    assert state.status == "aborted"
    assert state.stop_reason == "budget_exceeded"


def test_step_limit_defect_stops_with_step_limit_reached():
    state = _run("step_limit")
    assert state.status == "aborted"
    assert state.stop_reason == "step_limit_reached"


def test_stuck_agent_defect_stops_with_reception_refused():
    state = _run("stuck_agent")
    assert state.status == "aborted"
    assert state.stop_reason == "reception_refused"


def test_unknown_defect_raises_value_error():
    with pytest.raises(ValueError):
        br.scenario_for("does_not_exist")


def test_defects_tuple_matches_the_four_buttons():
    assert set(br.DEFECTS) == {
        "role_violation",
        "budget_exceeded",
        "step_limit",
        "stuck_agent",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_webapp_guardrails.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kaldera.webapp'`

- [ ] **Step 3: Write `src/kaldera/webapp/__init__.py`**

```python
"""GUI pédagogique Kaldera : démo déterministe/vrai LLM et garde-fous, hors du cœur de la
bibliothèque (dépend de `gradio`, installé via l'extra `webapp`)."""
```

- [ ] **Step 4: Write `src/kaldera/webapp/broken_registries.py`**

```python
"""Registres d'agents cassés en mémoire, pour rejouer en direct les 4 défauts historiques de
l'onglet « Casser un garde-fou » de la GUI. Jamais de modification de fichier source : chaque
sous-classe garde un `name`/`handles` cohérents avec son poste (sinon `check_demand` refuse la
demande avant même de démarrer), seul `act()` (ou `token_budget`) est cassé."""

from __future__ import annotations

from ..agents.base import RoleViolation
from ..agents.finalizer import Finalizer
from ..agents.researcher import Researcher
from ..agents.reviewer import Reviewer
from ..agents.writer import Writer
from ..state import TeamState
from ..steps import Step

DEFECTS: tuple[str, ...] = ("role_violation", "budget_exceeded", "step_limit", "stuck_agent")

_SCENARIO = {
    "initial_context": {
        "topic": "démo garde-fou",
        "required_steps": ["RESEARCH", "FINALIZE"],
    }
}


class _RoleViolationResearcher(Researcher):
    """Refuse toujours son étape, directement (contourne son propre `accepts()`, resté correct)."""

    def act(self, state: TeamState, step: Step) -> None:
        raise RoleViolation(f"{self.name} cassé pour la démo : refuse toujours son étape")


class _NoBudgetResearcher(Researcher):
    token_budget = 0


class _StuckResearcher(Researcher):
    """N'écrit jamais l'artefact attendu : refusé à chaque tentative."""

    def act(self, state: TeamState, step: Step) -> None:
        return


class _RetryOnceResearcher(Researcher):
    """Échoue une fois (rien n'est écrit, refusé), réussit normalement à la relance — consomme
    2 délégations pour 1 étape, ce qui ne laisse plus de marge si `max_iterations` est réglé
    exactement sur le nombre d'étapes requises."""

    def __init__(self) -> None:
        super().__init__()
        self._attempts = 0

    def act(self, state: TeamState, step: Step) -> None:
        self._attempts += 1
        if self._attempts == 1:
            return
        super().act(state, step)


def _registry(researcher: Researcher) -> dict[str, object]:
    return {
        "researcher": researcher,
        "writer": Writer(),
        "reviewer": Reviewer(),
        "finalizer": Finalizer(),
    }


def scenario_for(defect: str) -> tuple[dict, dict[str, object] | None, int | None]:
    """Renvoie `(scénario, agents_by_name, max_iterations)` prêts pour `run_scenario(**kwargs)`.

    `agents_by_name=None` signifie l'équipe normale (le défaut ne vient pas du registre) ;
    `max_iterations=None` signifie pas de limite forcée par ce défaut.
    """
    if defect == "role_violation":
        return _SCENARIO, _registry(_RoleViolationResearcher()), None
    if defect == "budget_exceeded":
        return _SCENARIO, _registry(_NoBudgetResearcher()), None
    if defect == "step_limit":
        # 2 étapes requises, limite réglée exactement à 2 : la relance de _RetryOnceResearcher
        # consomme les 2 délégations sur la seule étape RESEARCH, il n'en reste aucune pour
        # FINALIZE → step_limit_reached à la délégation suivante.
        return _SCENARIO, _registry(_RetryOnceResearcher()), 2
    if defect == "stuck_agent":
        return _SCENARIO, _registry(_StuckResearcher()), None
    raise ValueError(f"défaut inconnu : {defect!r} (attendu l'un de {DEFECTS})")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_webapp_guardrails.py -v`
Expected: 6 passed

- [ ] **Step 6: Lint and typecheck**

Run: `uv run ruff check src/kaldera/webapp tests/test_webapp_guardrails.py && uv run mypy src`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/kaldera/webapp/__init__.py src/kaldera/webapp/broken_registries.py tests/test_webapp_guardrails.py
git commit -m "feat(webapp): registres d'agents cassés pour rejouer les 4 garde-fous en direct"
```

---

## Task 2 : Fonctions d'exécution (`runners.py`)

**Files:**
- Create: `src/kaldera/webapp/runners.py`
- Test: `tests/test_webapp_runners.py`

**Interfaces:**
- Consumes : `kaldera.runner.run_scenario`, `kaldera.graph.build_graph`, `kaldera.graph.HARD_CAP`,
  `kaldera.orchestrator.AGENTS_BY_NAME`, `kaldera.orchestrator.check_demand`,
  `kaldera.state.TeamState`, `kaldera.steps.step_from_name`,
  `kaldera.webapp.broken_registries.scenario_for` (Task 1).
- Produces :
  - `run_deterministic(topic: str, steps: list[str]) -> dict` — clés
    `status, step_count, artifacts (dict[str,str]), stop_reason (str|None), log (list[dict])`.
  - `stream_live(topic: str, steps: list[str], llm: object | None = None, max_steps: int | None = None) -> Iterator[dict]`
    — chaque élément a les mêmes clés que ci-dessus **plus** `"node": str | None` (nom du dernier
    agent exécuté, `None` sur le premier élément si la demande est refusée d'emblée). `llm=None`
    construit un vrai client (`kaldera.llm.build_llm()`) ; un appelant de test injecte un double.
  - `run_guardrail(defect: str) -> dict` — mêmes clés que `run_deterministic`, défaut inconnu
    propage le `ValueError` de `broken_registries.scenario_for`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_webapp_runners.py
"""Fonctions pures (sans Gradio) qui enveloppent run_scenario/build_graph pour la GUI."""

from __future__ import annotations

from kaldera.webapp import runners


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def __init__(self, fail_on: int | None = None) -> None:
        self.calls = 0
        self.fail_on = fail_on

    def invoke(self, prompt: str) -> _FakeResponse:
        self.calls += 1
        if self.fail_on is not None and self.calls == self.fail_on:
            raise RuntimeError("panne réseau simulée")
        return _FakeResponse(f"fake-{self.calls}")


def test_run_deterministic_happy_path():
    result = runners.run_deterministic("lancement produit", ["RESEARCH", "DRAFT", "REVIEW", "FINALIZE"])
    assert result["status"] == "done"
    assert result["step_count"] == 4
    assert sorted(result["artifacts"]) == ["draft", "final", "research", "review"]
    assert result["stop_reason"] is None


def test_run_deterministic_empty_topic_is_refused_not_raised():
    result = runners.run_deterministic("", ["RESEARCH"])
    assert result["status"] == "aborted"
    assert result["stop_reason"] == "invalid_demand:empty"


def test_run_deterministic_empty_steps_is_refused_not_raised():
    result = runners.run_deterministic("sujet valide", [])
    assert result["status"] == "aborted"
    assert result["stop_reason"] == "invalid_demand:empty"


def test_run_deterministic_duplicate_steps_is_refused_not_raised():
    result = runners.run_deterministic("sujet", ["RESEARCH", "RESEARCH", "FINALIZE"])
    assert result["status"] == "aborted"
    assert result["stop_reason"] == "invalid_demand:duplicate_step"


def test_stream_live_yields_one_chunk_per_step():
    fake = _FakeLLM()
    chunks = list(runners.stream_live("sujet", ["RESEARCH", "FINALIZE"], llm=fake, max_steps=5))

    assert len(chunks) == 2
    assert chunks[0]["node"] == "researcher"
    assert chunks[-1]["node"] == "finalizer"
    assert chunks[-1]["status"] == "done"
    assert sorted(chunks[-1]["artifacts"]) == ["final", "research"]


def test_stream_live_invalid_demand_yields_single_refusal_chunk():
    fake = _FakeLLM()
    chunks = list(runners.stream_live("", [], llm=fake))

    assert len(chunks) == 1
    assert chunks[0]["node"] is None
    assert chunks[0]["status"] == "aborted"
    assert chunks[0]["stop_reason"].startswith("invalid_demand:")
    assert fake.calls == 0


def test_stream_live_llm_failure_yields_llm_error_instead_of_raising():
    fake = _FakeLLM(fail_on=1)
    chunks = list(runners.stream_live("sujet", ["RESEARCH", "FINALIZE"], llm=fake, max_steps=5))

    assert chunks[-1]["status"] == "aborted"
    assert chunks[-1]["stop_reason"] == "llm_error"


def test_run_guardrail_role_violation():
    result = runners.run_guardrail("role_violation")
    assert result["status"] == "aborted"
    assert result["stop_reason"] == "role_violation"


def test_run_guardrail_step_limit():
    result = runners.run_guardrail("step_limit")
    assert result["status"] == "aborted"
    assert result["stop_reason"] == "step_limit_reached"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_webapp_runners.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kaldera.webapp.runners'`

- [ ] **Step 3: Write `src/kaldera/webapp/runners.py`**

```python
"""Fonctions pures qui enveloppent l'orchestrateur pour la GUI (aucun import de `gradio` ici,
testables sans lancer de serveur). Zéro changement à runner.py/graph.py/orchestrator.py."""

from __future__ import annotations

from collections.abc import Iterator

from ..graph import HARD_CAP, build_graph
from ..llm import build_llm
from ..orchestrator import AGENTS_BY_NAME, check_demand
from ..runner import run_scenario
from ..state import TeamState
from ..steps import step_from_name
from . import broken_registries


def _summarize(state: TeamState) -> dict:
    return {
        "status": state.status,
        "step_count": state.step_count,
        "artifacts": dict(state.artifacts),
        "stop_reason": state.stop_reason,
        "log": list(state.log),
    }


def run_deterministic(topic: str, steps: list[str]) -> dict:
    scenario = {"initial_context": {"topic": topic, "required_steps": steps}}
    state = run_scenario(scenario)
    return _summarize(state)


def run_guardrail(defect: str) -> dict:
    scenario, registry, max_iterations = broken_registries.scenario_for(defect)
    state = run_scenario(scenario, agents_by_name=registry, max_iterations=max_iterations)
    return _summarize(state)


def stream_live(
    topic: str,
    steps: list[str],
    llm: object | None = None,
    max_steps: int | None = None,
) -> Iterator[dict]:
    state = TeamState(topic=topic, required_steps=[step_from_name(s) for s in steps])
    limit = max_steps if max_steps is not None else HARD_CAP
    state.step_limit = limit

    motif = check_demand(state, AGENTS_BY_NAME, limit)
    if motif is not None:
        state.status = "aborted"
        state.stop_reason = f"invalid_demand:{motif}"
        yield {"node": None, **_summarize(state)}
        return

    client = llm if llm is not None else build_llm()
    graph = build_graph(client, limit)

    try:
        for chunk in graph.stream(state):
            node_name, node_state = next(iter(chunk.items()))
            yield {
                "node": node_name,
                "status": node_state["status"],
                "step_count": node_state["step_count"],
                "artifacts": dict(node_state["artifacts"]),
                "stop_reason": node_state["stop_reason"],
                "log": list(node_state["log"]),
            }
    except Exception:
        yield {
            "node": None,
            "status": "aborted",
            "step_count": state.step_count,
            "artifacts": dict(state.artifacts),
            "stop_reason": "llm_error",
            "log": list(state.log),
        }
```

Note : `topic=""` et `steps=[]` déclenchent tous les deux `check_demand`'s `"empty"` (le
`or` de `not (state.topic or "").strip() or not steps` dans `orchestrator.check_demand`) — les
deux tests dédiés (`empty_topic`, `empty_steps`) documentent chacun un côté du `or`, pas une
duplication.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_webapp_runners.py -v`
Expected: 9 passed

- [ ] **Step 5: Run the full existing suite to confirm zero regression**

Run: `uv run pytest -p no:cacheprovider -q`
Expected: all tests pass (59 précédents + les nouveaux des tasks 1 et 2)

- [ ] **Step 6: Lint and typecheck**

Run: `uv run ruff check src/kaldera/webapp tests/test_webapp_runners.py && uv run mypy src`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/kaldera/webapp/runners.py tests/test_webapp_runners.py
git commit -m "feat(webapp): fonctions d'exécution déterministe/live/garde-fou pour la GUI"
```

---

## Task 3 : Garde-fou de coût (`cost_guard.py`)

**Files:**
- Create: `src/kaldera/webapp/cost_guard.py`
- Test: `tests/test_webapp_cost_guard.py`

**Interfaces:**
- Produces : `class CostGuard` avec `__init__(self, cooldown_seconds: float = 15.0, now: Callable[[], float] = time.monotonic)`,
  `try_acquire(self) -> bool` (renvoie `True` et enregistre l'instant si le délai est écoulé,
  `False` sinon — n'avance jamais l'horloge interne sur un refus), et
  `seconds_remaining(self) -> float` (0.0 si jamais déclenché ou délai écoulé).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_webapp_cost_guard.py
"""Verrou de fréquence pour le bouton « vrai LLM » : un seul déclenchement par fenêtre de
cooldown, résiste à un double-clic ou un F5 (l'état vit côté serveur, pas dans le bouton)."""

from __future__ import annotations

from kaldera.webapp.cost_guard import CostGuard


def _clock(*values: float):
    it = iter(values)
    return lambda: next(it)


def test_first_call_is_always_allowed():
    guard = CostGuard(cooldown_seconds=15.0, now=_clock(0.0))
    assert guard.try_acquire() is True


def test_second_call_within_cooldown_is_denied():
    guard = CostGuard(cooldown_seconds=15.0, now=_clock(0.0, 5.0))
    assert guard.try_acquire() is True
    assert guard.try_acquire() is False


def test_call_after_cooldown_elapsed_is_allowed_again():
    guard = CostGuard(cooldown_seconds=15.0, now=_clock(0.0, 20.0))
    assert guard.try_acquire() is True
    assert guard.try_acquire() is True


def test_denied_call_does_not_reset_the_window():
    guard = CostGuard(cooldown_seconds=15.0, now=_clock(0.0, 5.0, 10.0))
    assert guard.try_acquire() is True
    assert guard.try_acquire() is False  # t=5, refusé, ne doit pas repartir de 5
    assert guard.try_acquire() is False  # t=10 : 10-0=10 < 15, encore refusé


def test_seconds_remaining_reports_the_wait():
    guard = CostGuard(cooldown_seconds=15.0, now=_clock(0.0, 5.0))
    guard.try_acquire()
    assert guard.seconds_remaining() == 10.0


def test_seconds_remaining_is_zero_before_first_call():
    guard = CostGuard(cooldown_seconds=15.0, now=_clock(0.0))
    assert guard.seconds_remaining() == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_webapp_cost_guard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kaldera.webapp.cost_guard'`

- [ ] **Step 3: Write `src/kaldera/webapp/cost_guard.py`**

```python
"""Garde-fou de coût : impose un délai minimal entre deux vrais appels LLM déclenchés depuis la
GUI. L'état vit côté serveur (pas dans l'état du bouton) : résiste à un double-clic ou un F5."""

from __future__ import annotations

import time
from collections.abc import Callable

DEFAULT_COOLDOWN_SECONDS = 15.0


class CostGuard:
    def __init__(
        self,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cooldown = cooldown_seconds
        self._now = now
        self._last_call: float | None = None

    def try_acquire(self) -> bool:
        current = self._now()
        if self._last_call is not None and current - self._last_call < self._cooldown:
            return False
        self._last_call = current
        return True

    def seconds_remaining(self) -> float:
        if self._last_call is None:
            return 0.0
        return max(0.0, self._cooldown - (self._now() - self._last_call))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_webapp_cost_guard.py -v`
Expected: 6 passed

- [ ] **Step 5: Lint and typecheck**

Run: `uv run ruff check src/kaldera/webapp tests/test_webapp_cost_guard.py && uv run mypy src`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/kaldera/webapp/cost_guard.py tests/test_webapp_cost_guard.py
git commit -m "feat(webapp): garde-fou de coût pour le bouton vrai LLM"
```

---

## Task 4 : Application Gradio (`app.py`)

**Files:**
- Modify: `pyproject.toml` (ajout du groupe `[project.optional-dependencies] webapp`)
- Create: `src/kaldera/webapp/app.py`
- Test: `tests/test_webapp_app.py`

**Interfaces:**
- Consumes : `runners.run_deterministic`, `runners.stream_live`, `runners.run_guardrail`
  (Task 2), `cost_guard.CostGuard` (Task 3), `broken_registries.DEFECTS` (Task 1).
- Produces : `build_app() -> gradio.Blocks` (construit l'app sans la lancer — testable sans
  ouvrir de port), et les callbacks nommées `on_run_deterministic`, `on_run_live`,
  `on_run_guardrail`, exposées au niveau du module pour être appelées directement dans les tests
  sans passer par le runtime Gradio. `main()` appelle `build_app().launch(server_name="0.0.0.0", server_port=7860)`.

- [ ] **Step 1: Add the `webapp` optional dependency group**

Modifier `pyproject.toml`, juste après le bloc `dependencies` existant :

```toml
[project.optional-dependencies]
webapp = ["gradio>=5,<6"]
```

- [ ] **Step 2: Sync and verify gradio installs**

Run: `uv sync --extra webapp`
Expected: `gradio` et ses dépendances s'installent sans conflit avec `langchain`/`langgraph`
existants (aucune erreur de résolution `uv`).

- [ ] **Step 3: Write the failing tests**

```python
# tests/test_webapp_app.py
"""L'app Gradio se construit sans erreur, et ses callbacks (fonctions Python nues, appelables
sans passer par le runtime Gradio) se comportent correctement — y compris le respect du
garde-fou de coût par la callback « vrai LLM »."""

from __future__ import annotations

import gradio as gr

from kaldera.webapp import app as webapp_app


def test_build_app_returns_a_blocks_instance():
    demo = webapp_app.build_app()
    assert isinstance(demo, gr.Blocks)


def test_on_run_deterministic_returns_a_summary_dict():
    result = webapp_app.on_run_deterministic("sujet", ["RESEARCH", "FINALIZE"])
    assert result["status"] == "done"


def test_on_run_guardrail_returns_the_expected_stop_reason():
    result = webapp_app.on_run_guardrail("budget_exceeded")
    assert result["stop_reason"] == "budget_exceeded"


def test_on_run_live_respects_the_cost_guard(monkeypatch):
    calls = {"n": 0}

    def fake_stream_live(topic, steps, llm=None, max_steps=None):
        calls["n"] += 1
        yield {"node": "researcher", "status": "done", "step_count": 1, "artifacts": {}, "stop_reason": None, "log": []}

    monkeypatch.setattr(webapp_app.runners, "stream_live", fake_stream_live)
    webapp_app._cost_guard._last_call = None  # état propre entre tests

    first_output = list(webapp_app.on_run_live("sujet", ["RESEARCH"]))
    assert calls["n"] == 1
    assert first_output  # au moins un chunk streamé

    second_output = list(webapp_app.on_run_live("sujet", ["RESEARCH"]))
    assert calls["n"] == 1  # pas de second appel réel : le garde-fou de coût a bloqué
    assert second_output[0]["stop_reason"] == "cooldown"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_webapp_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kaldera.webapp.app'`

- [ ] **Step 5: Write `src/kaldera/webapp/app.py`**

```python
"""GUI Gradio : 3 onglets (Exécuter / Casser un garde-fou / Comparer). Un seul opérateur en
projection (pas d'auth, pas d'isolation de session — décidé au brainstorming du 30/09/2026)."""

from __future__ import annotations

from collections.abc import Iterator

import gradio as gr

from . import runners
from .broken_registries import DEFECTS
from .cost_guard import CostGuard

STEPS_CHOICES = ["RESEARCH", "DRAFT", "REVIEW", "FINALIZE"]
GUARDRAIL_LABELS = {
    "role_violation": "Rôle hors périmètre",
    "budget_exceeded": "Budget de tokens dépassé",
    "step_limit": "Limite d'étapes atteinte",
    "stuck_agent": "Agent bloqué (ne progresse pas)",
}

_cost_guard = CostGuard()


def on_run_deterministic(topic: str, steps: list[str]) -> dict:
    return runners.run_deterministic(topic, steps)


def on_run_guardrail(defect: str) -> dict:
    return runners.run_guardrail(defect)


def on_run_live(topic: str, steps: list[str]) -> Iterator[dict]:
    if not _cost_guard.try_acquire():
        wait = round(_cost_guard.seconds_remaining(), 1)
        yield {
            "node": None,
            "status": "aborted",
            "step_count": 0,
            "artifacts": {},
            "stop_reason": "cooldown",
            "log": [],
            "message": f"Patiente encore {wait}s avant un nouveau vrai run.",
        }
        return
    yield from runners.stream_live(topic, steps)


def _format_summary(result: dict) -> str:
    lines = [f"statut : {result['status']}", f"étapes : {result['step_count']}"]
    if result.get("stop_reason"):
        lines.append(f"stop_reason : {result['stop_reason']}")
    return "\n".join(lines)


def _format_live_chunk(chunk: dict) -> str:
    node = chunk.get("node") or "—"
    parts = [f"[{node}] statut={chunk['status']} étapes={chunk['step_count']}"]
    if chunk.get("stop_reason"):
        parts.append(f"stop_reason={chunk['stop_reason']}")
    return " ".join(parts)


def _run_deterministic_ui(topic: str, steps: list[str]) -> tuple[str, dict]:
    result = on_run_deterministic(topic, steps)
    return _format_summary(result), result["artifacts"]


def _run_live_ui(topic: str, steps: list[str]):
    log_lines: list[str] = []
    artifacts: dict = {}
    for chunk in on_run_live(topic, steps):
        log_lines.append(_format_live_chunk(chunk))
        artifacts = chunk.get("artifacts", artifacts)
        yield "\n".join(log_lines), artifacts


def _run_guardrail_ui(defect: str) -> str:
    result = on_run_guardrail(defect)
    return _format_summary(result) + "\n\njournal :\n" + "\n".join(
        f"- {entry['agent_id']} : {entry['message']}" for entry in result["log"]
    )


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Kaldera — démo") as demo:
        gr.Markdown("# Kaldera — orchestration multi-agents, en direct")

        with gr.Tab("Exécuter"):
            topic_box = gr.Textbox(label="Sujet", value="lancement produit")
            steps_box = gr.CheckboxGroup(choices=STEPS_CHOICES, value=STEPS_CHOICES, label="Étapes")
            with gr.Row():
                det_button = gr.Button("Lancer (déterministe)")
                live_button = gr.Button("Lancer (vrai LLM)")
            output_log = gr.Textbox(label="Déroulé", lines=10)
            output_artifacts = gr.JSON(label="Artefacts")

            det_button.click(_run_deterministic_ui, [topic_box, steps_box], [output_log, output_artifacts])
            live_button.click(_run_live_ui, [topic_box, steps_box], [output_log, output_artifacts])

        with gr.Tab("Casser un garde-fou"):
            gr.Markdown("Toujours déterministe : gratuit, instantané, rejouable à l'infini.")
            guardrail_output = gr.Textbox(label="Résultat", lines=12)
            for defect in DEFECTS:
                button = gr.Button(GUARDRAIL_LABELS[defect])
                button.click(lambda d=defect: _run_guardrail_ui(d), outputs=guardrail_output)

        with gr.Tab("Comparer"):
            cmp_topic = gr.Textbox(label="Sujet", value="lancement produit")
            cmp_steps = gr.CheckboxGroup(choices=STEPS_CHOICES, value=STEPS_CHOICES, label="Étapes")
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Déterministe")
                    cmp_det_button = gr.Button("Lancer")
                    cmp_det_output = gr.Textbox(label="Déroulé", lines=10)
                    cmp_det_artifacts = gr.JSON(label="Artefacts")
                with gr.Column():
                    gr.Markdown("### Vrai LLM")
                    cmp_live_button = gr.Button("Lancer")
                    cmp_live_output = gr.Textbox(label="Déroulé", lines=10)
                    cmp_live_artifacts = gr.JSON(label="Artefacts")

            cmp_det_button.click(_run_deterministic_ui, [cmp_topic, cmp_steps], [cmp_det_output, cmp_det_artifacts])
            cmp_live_button.click(_run_live_ui, [cmp_topic, cmp_steps], [cmp_live_output, cmp_live_artifacts])

    return demo


def main() -> None:
    build_app().launch(server_name="0.0.0.0", server_port=7860)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_webapp_app.py -v`
Expected: 4 passed

- [ ] **Step 7: Run the full suite to confirm zero regression**

Run: `uv run pytest -p no:cacheprovider -q`
Expected: all tests pass (base existante + tasks 1-4)

- [ ] **Step 8: Lint and typecheck**

Run: `uv run ruff check src/kaldera/webapp tests/test_webapp_app.py && uv run mypy src`
Expected: no errors (si `mypy` râle sur les types de `gradio`, absents de stubs : ajouter
`# type: ignore[import-untyped]` sur la ligne `import gradio as gr`, rien d'autre)

- [ ] **Step 9: Smoke-test the app locally**

Run: `uv run python -m kaldera.webapp.app`
Expected: le serveur démarre, affiche une URL locale (`http://0.0.0.0:7860`) ; l'ouvrir dans un
navigateur, vérifier que les 3 onglets s'affichent, lancer un run déterministe sur l'onglet
« Exécuter », vérifier que le résultat s'affiche. Arrêter avec Ctrl+C.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml src/kaldera/webapp/app.py tests/test_webapp_app.py
git commit -m "feat(webapp): GUI Gradio à 3 onglets (exécuter / garde-fous / comparer)"
```

---

## Task 5 : Conteneurisation (`Dockerfile.web`)

**Files:**
- Create: `Dockerfile.web`

**Interfaces:**
- Consumes : `pyproject.toml` (extra `webapp`, Task 4), `src/kaldera/webapp/app.py` (Task 4).
- Produces : une image Docker qui lance la GUI sur le port `7860`, consommée par Task 6 (CI/CD)
  et le guide de déploiement (Task 7).

- [ ] **Step 1: Write `Dockerfile.web`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY src ./src
COPY scenarios ./scenarios
COPY specs ./specs

RUN uv sync --no-dev --extra webapp

EXPOSE 7860

CMD ["uv", "run", "python", "-m", "kaldera.webapp.app"]
```

- [ ] **Step 2: Build the image locally**

Run: `docker build -f Dockerfile.web -t kaldera-webapp:local .`
Expected: build réussit sans erreur.

- [ ] **Step 3: Run the container and verify the GUI responds**

Run: `docker run --rm -p 7860:7860 -e AZURE_AI_ENDPOINT=x -e AZURE_AI_API_KEY=x -e AZURE_AI_MODEL=x kaldera-webapp:local`

Puis, dans un autre terminal : `curl -sf http://localhost:7860 > /dev/null && echo OK`
Expected: `OK` (l'onglet « Exécuter » en déterministe ne nécessite pas de vrai LLM ; les 3
variables factices suffisent à ce que `build_llm()` ne lève pas d'erreur si jamais l'onglet
vrai-LLM est cliqué par erreur pendant le test — sans que l'appel réseau réel n'ait lieu tant que
le bouton n'est pas cliqué). Arrêter le conteneur (Ctrl+C).

- [ ] **Step 4: Commit**

```bash
git add Dockerfile.web
git commit -m "feat(webapp): conteneur dédié à la GUI, port 7860"
```

---

## Task 6 : Pipeline CI/CD (`.github/workflows/ci-cd.yml`)

**Files:**
- Create: `.github/workflows/ci-cd.yml`

**Interfaces:**
- Consumes : `Dockerfile.web` (Task 5), les 3 secrets GitHub `AZURE_CLIENT_ID`,
  `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` (créés manuellement via le guide de Task 8, pas par
  ce fichier), les ressources Azure `rg-kaldera-demo`/`kaldera-webapp-demo` (créées manuellement
  via le guide de Task 7).
- Produces : job `test` (PR + push), job `deploy` (push sur `main` uniquement, après `test`).

- [ ] **Step 1: Write `.github/workflows/ci-cd.yml`**

```yaml
name: CI/CD

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

env:
  IMAGE_NAME: ghcr.io/${{ github.repository_owner }}/kaldera-webapp
  RESOURCE_GROUP: rg-kaldera-demo
  CONTAINER_APP: kaldera-webapp-demo

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v3

      - name: Installer les dépendances (cœur + webapp)
        run: uv sync --extra webapp

      - name: Lint
        run: uv run ruff check .

      - name: Typecheck
        run: uv run mypy src

      - name: Tests (le test vrai-LLM se saute sans identifiants Azure AI)
        run: uv run pytest -q

      - name: Vérifie que l'image se construit
        run: docker build -f Dockerfile.web -t kaldera-webapp:ci .

  deploy:
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Connexion à ghcr.io
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build et push de l'image
        uses: docker/build-push-action@v6
        with:
          context: .
          file: Dockerfile.web
          push: true
          tags: |
            ${{ env.IMAGE_NAME }}:${{ github.sha }}
            ${{ env.IMAGE_NAME }}:latest

      - name: Connexion à Azure (OIDC fédéré, aucun secret longue durée)
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Redéploie le Container App avec la nouvelle image
        uses: azure/CLI@v2
        with:
          inlineScript: |
            az containerapp update \
              --name ${{ env.CONTAINER_APP }} \
              --resource-group ${{ env.RESOURCE_GROUP }} \
              --image ${{ env.IMAGE_NAME }}:${{ github.sha }}
```

- [ ] **Step 2: Validate the YAML syntax**

Run: `python3 -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci-cd.yml').read_text())"`
Expected: aucune sortie, code de sortie 0 (le YAML est syntaxiquement valide). Si `pyyaml` n'est
pas disponible dans l'environnement local : `uv run python -c "..."` avec la même commande.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci-cd.yml
git commit -m "ci: pipeline GitHub Actions (tests sur PR, build+déploiement sur main, OIDC)"
```

Note : ce job `deploy` échouera tant que les guides des Tasks 7 et 8 n'ont pas été suivis
manuellement (ressources Azure et secrets GitHub inexistants avant ça) — attendu, ce n'est pas un
bug du workflow. Le job `test`, lui, fonctionne dès ce commit, y compris sur les PR de forks.

---

## Task 7 : Guide pas-à-pas — créer les ressources Azure via le portail

**Files:**
- Create: `doc/guides/deploiement_azure_portail.md`

**Interfaces:**
- Consumes : les noms fixés dans Global Constraints (`rg-kaldera-demo`, `env-kaldera-demo`,
  `kaldera-webapp-demo`, port `7860`), l'image `ghcr.io/sofiane-git/kaldera-webapp` (Task 6).
- Produces : la marche à suivre que l'utilisateur (débutant Azure) exécute une fois, à la main,
  avant que le job `deploy` de Task 6 puisse réussir.

- [ ] **Step 1: Write `doc/guides/deploiement_azure_portail.md`**

```markdown
# Déployer Kaldera sur Azure — pas à pas dans le portail

Guide pour un compte Azure déjà actif (abonnement avec carte liée ou crédits). Les noms de menus
sont ceux du portail à la date de rédaction (30/09/2026) ; l'interface Azure change de temps en
temps, mais les ressources et leur logique restent les mêmes si un libellé a bougé.

Ressources créées : un groupe de ressources, un environnement Container Apps, un Container App.
Tout se fait en une seule fois via l'assistant de création du Container App.

## 1. Groupe de ressources

1. Aller sur [portal.azure.com](https://portal.azure.com).
2. Barre de recherche en haut → taper « Groupes de ressources » → ouvrir.
3. **+ Créer**.
4. Abonnement : le tien. Nom du groupe de ressources : `rg-kaldera-demo`. Région : une région
   proche (ex. « France Central »).
5. **Vérifier + créer**, puis **Créer**.

## 2. Container App (et son environnement, créé au même moment)

1. Barre de recherche → « Container Apps » → ouvrir le service (pas une ressource existante).
2. **+ Créer** → **Container App**.
3. Onglet **Bases (Basics)** :
   - Abonnement : le tien. Groupe de ressources : `rg-kaldera-demo`.
   - Nom du Container App : `kaldera-webapp-demo`.
   - Région : la même que le groupe de ressources.
   - Environnement Container Apps : **Créer nouveau** → nom `env-kaldera-demo` → Créer (ferme la
     sous-fenêtre, revient à l'assistant).
4. Onglet **Conteneur (Container)** :
   - Décocher/désélectionner l'option d'image de démonstration (« Utiliser une image
     d'exemple ») si elle est cochée par défaut.
   - Nom du conteneur : `kaldera-webapp`.
   - Source de l'image : **Autres registres de conteneurs** (ou « Docker Hub ou autre registre »
     selon le libellé affiché).
   - URL de l'image : `ghcr.io/sofiane-git/kaldera-webapp:latest`.
   - Type d'authentification du registre : si le package `ghcr.io` a été rendu **public** (voir
     Task 8 du plan, dernière étape), choisir « Aucune » / laisser vide — pas d'identifiant
     nécessaire. S'il reste privé, il faudra un identifiant de registre (non couvert ici : rendre
     le package public évite cette complication).
   - Ressources : 0.25 vCPU / 0.5 Gi suffisent largement pour cette démo.
5. Onglet **Ingress** :
   - Activer l'ingress : **Activé**.
   - Trafic accepté : **Anywhere / N'importe où** (ingress externe).
   - Port cible (Target port) : `7860`.
6. Onglet **Mise à l'échelle (Scale)** (si présent séparément, sinon dans l'onglet Bases) :
   - Nombre de réplicas minimal : `0` (scale-to-zero — c'est ce qui garde le coût quasi nul entre
     deux démos).
   - Nombre de réplicas maximal : `1`.
7. **Vérifier + créer**, vérifier qu'aucune erreur n'est signalée, puis **Créer**. La création
   prend une à deux minutes.

## 3. Ajouter les secrets Azure AI

Une fois la ressource créée, l'ouvrir (« Accéder à la ressource » ou la retrouver dans le groupe
de ressources `rg-kaldera-demo`).

1. Menu de gauche → **Secrets** (sous la section Paramètres/Settings).
2. **+ Ajouter** trois fois, pour créer :
   - `azure-ai-endpoint` → valeur : l'URL de l'endpoint Azure AI (celle de ton fichier `.env`
     local, `AZURE_AI_ENDPOINT`).
   - `azure-ai-api-key` → valeur : la clé (`AZURE_AI_API_KEY`).
   - `azure-ai-model` → valeur : le nom du modèle (`AZURE_AI_MODEL`).
3. Menu de gauche → **Variables d'environnement et conteneurs** (« Containers » → onglet
   « Variables d'environnement »).
4. Ajouter trois variables, chacune en mode **Référence à un secret** :
   - `AZURE_AI_ENDPOINT` → référence le secret `azure-ai-endpoint`.
   - `AZURE_AI_API_KEY` → référence le secret `azure-ai-api-key`.
   - `AZURE_AI_MODEL` → référence le secret `azure-ai-model`.
5. **Enregistrer** (ou **Créer**) : ceci déclenche une nouvelle révision du Container App, qui
   redémarre avec les variables en place — normal, attendre que le statut redevienne « En cours
   d'exécution » (30 secondes à 1 minute).

## 4. Retrouver l'URL publique

Menu de gauche → **Vue d'ensemble (Overview)** → champ **URL de l'application (Application
URL)**. C'est l'adresse `https://kaldera-webapp-demo.<suffixe-aléatoire>.<région>.azurecontainerapps.io`
à ouvrir dans un navigateur et à projeter en classe.

## 5. Lire les logs en cas de souci

Menu de gauche → **Flux de journal (Log stream)** : affiche la sortie du conteneur en direct (ce
que `uv run python -m kaldera.webapp.app` écrit sur la sortie standard). Utile si la GUI ne
répond pas ou si un déploiement récent a cassé quelque chose.

## 6. Rappel : démarrage à froid

Le scale-to-zero veut dire que si personne n'a utilisé la GUI depuis un moment, le conteneur est
arrêté. La première requête après une inactivité prend quelques secondes de plus (le temps que le
conteneur redémarre). **Avant de présenter en classe, ouvrir l'URL une minute à l'avance** pour
« réveiller » le conteneur.
```

- [ ] **Step 2: Read-through checklist**

Relire le fichier écrit à l'étape 1 et vérifier :
- Les 3 noms de ressources (`rg-kaldera-demo`, `env-kaldera-demo`, `kaldera-webapp-demo`)
  correspondent exactement à ceux utilisés dans `.github/workflows/ci-cd.yml` (Task 6).
- Le port `7860` correspond à celui de `Dockerfile.web`/`app.py` (Task 4/5).
- Aucune clé ou valeur réelle n'apparaît dans le guide (uniquement des noms de champs à
  remplir).

- [ ] **Step 3: Commit**

```bash
git add doc/guides/deploiement_azure_portail.md
git commit -m "docs: guide pas-à-pas pour créer les ressources Azure (portail)"
```

---

## Task 8 : Guide pas-à-pas — connecter GitHub Actions à Azure (OIDC)

**Files:**
- Create: `doc/guides/github_actions_azure_oidc_portail.md`

**Interfaces:**
- Consumes : le groupe de ressources `rg-kaldera-demo` (Task 7), les 3 secrets GitHub attendus
  par `.github/workflows/ci-cd.yml` (Task 6) : `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
  `AZURE_SUBSCRIPTION_ID`.
- Produces : la marche à suivre pour que le job `deploy` de Task 6 puisse s'authentifier auprès
  d'Azure sans secret longue durée.

- [ ] **Step 1: Write `doc/guides/github_actions_azure_oidc_portail.md`**

```markdown
# Connecter GitHub Actions à Azure — sans mot de passe (OIDC), pas à pas

Suivre ce guide **après** `deploiement_azure_portail.md` (le groupe de ressources
`rg-kaldera-demo` doit déjà exister). Objectif : que la CI GitHub Actions puisse déployer sur
Azure sans qu'aucun secret longue durée (mot de passe, clé, JSON de credentials) ne soit stocké
dans GitHub. GitHub prouve son identité à chaque exécution via un jeton signé (OIDC), Azure le
vérifie, et n'accorde l'accès qu'à la branche `main` de ce dépôt précis.

## 1. Créer l'inscription d'application (App Registration)

1. [portal.azure.com](https://portal.azure.com) → barre de recherche → « Microsoft Entra ID »
   (anciennement Azure Active Directory) → ouvrir.
2. Menu de gauche → **Inscriptions d'applications (App registrations)**.
3. **+ Nouvelle inscription**.
4. Nom : `kaldera-github-actions`. Types de comptes pris en charge : « Comptes dans cet annuaire
   organisationnel uniquement ». URI de redirection : laisser vide.
5. **Inscrire**.
6. Sur la page qui s'ouvre (Vue d'ensemble), noter deux valeurs affichées en haut :
   - **ID d'application (client)** → ce sera `AZURE_CLIENT_ID`.
   - **ID d'annuaire (locataire)** → ce sera `AZURE_TENANT_ID`.

## 2. Ajouter l'identité fédérée (Federated credential)

1. Toujours sur cette App Registration → menu de gauche → **Certificats et secrets**.
2. Onglet **Informations d'identification fédérées (Federated credentials)**.
3. **+ Ajouter des informations d'identification**.
4. Scénario : **GitHub Actions déployant des ressources Azure**.
5. Organisation : `sofiane-git`. Dépôt : `kaldera-team-ko`.
   Type d'entité : **Branch**. Nom de la branche : `main`.
6. Nom de l'information d'identification : `kaldera-main-deploy`.
7. **Ajouter**.

Ceci autorise *uniquement* les workflows qui s'exécutent sur la branche `main` de ce dépôt précis
à s'authentifier en tant que cette App Registration — pas les PR, pas les autres branches, pas
les autres dépôts.

## 3. Donner à l'App Registration le droit de déployer

1. Aller sur le groupe de ressources `rg-kaldera-demo` (barre de recherche → « Groupes de
   ressources » → l'ouvrir).
2. Menu de gauche → **Contrôle d'accès (IAM)**.
3. **+ Ajouter** → **Ajouter une attribution de rôle**.
4. Rôle : **Contributor** (Contributeur) → Suivant.
5. Attribuer l'accès à : **Utilisateur, groupe ou principal de service**.
6. **+ Sélectionner des membres** → rechercher `kaldera-github-actions` (le nom donné à l'étape
   1) → le sélectionner.
7. **Vérifier + attribuer**.

## 4. Récupérer l'ID d'abonnement

1. Barre de recherche → « Abonnements (Subscriptions) » → ouvrir ton abonnement.
2. Copier la valeur **ID abonnement (Subscription ID)** → ce sera `AZURE_SUBSCRIPTION_ID`.

## 5. Ajouter les 3 secrets dans GitHub

1. Sur github.com, ouvrir le dépôt `kaldera-team-ko` → **Settings** → **Secrets and variables**
   → **Actions**.
2. **New repository secret**, trois fois :
   - `AZURE_CLIENT_ID` → la valeur notée à l'étape 1.
   - `AZURE_TENANT_ID` → la valeur notée à l'étape 1.
   - `AZURE_SUBSCRIPTION_ID` → la valeur notée à l'étape 4.

Aucun de ces trois secrets n'est un mot de passe : ce sont des identifiants publics (l'App
Registration ne peut rien faire sans le jeton OIDC signé que GitHub génère à chaque run, jamais
stocké nulle part).

## 6. Rendre l'image ghcr.io publique (évite un secret de registre en plus)

Une fois que le workflow `.github/workflows/ci-cd.yml` a tourné au moins une fois avec succès sur
`main` (il aura poussé une image vers `ghcr.io`) :

1. Sur github.com → compte `sofiane-git` → onglet **Packages**.
2. Ouvrir le package `kaldera-webapp`.
3. **Package settings** (en bas de la page du package).
4. **Change visibility** → **Public** → confirmer en tapant le nom du package.

Ceci évite d'avoir à configurer un identifiant de registre côté Container App (Task 7, étape 2) :
une image publique se tire sans authentification.

## Vérification finale

Faire un commit vide sur `main` (ou merger une PR) pour déclencher le workflow, puis :
github.com → onglet **Actions** du dépôt → ouvrir le run le plus récent → vérifier que le job
`deploy` passe au vert. En cas d'échec sur l'étape « Connexion à Azure », revérifier que les 3
secrets GitHub (étape 5) correspondent exactement aux valeurs des étapes 1 et 4, et que
l'identité fédérée (étape 2) cible bien `refs/heads/main` de ce dépôt.
```

- [ ] **Step 2: Read-through checklist**

Relire le fichier écrit à l'étape 1 et vérifier :
- Les 3 noms de secrets (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`)
  correspondent exactement à ceux lus par `.github/workflows/ci-cd.yml` (Task 6).
- Le nom du dépôt (`kaldera-team-ko`) et de la branche (`main`) correspondent au repo réel.
- Aucune valeur réelle (ID, clé) n'apparaît dans le guide.

- [ ] **Step 3: Commit**

```bash
git add doc/guides/github_actions_azure_oidc_portail.md
git commit -m "docs: guide pas-à-pas pour l'authentification OIDC GitHub Actions → Azure"
```

---

## Task 9 : Documenter la GUI dans le README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes : tout ce qui précède (Tasks 1-8).

- [ ] **Step 1: Add a "GUI de démo" section to `README.md`**

Ajouter, après la section `## Known issues` existante, avant `## License` :

```markdown
## GUI de démo

Une GUI Gradio pédagogique (déterministe / vrai LLM / casser un garde-fou / comparer les deux)
tourne en local et sur Azure Container Apps.

**En local :**

```bash
uv sync --extra webapp
uv run python -m kaldera.webapp.app
```

Ouvre `http://localhost:7860`.

**En production :** `<URL Azure Container Apps — à renseigner après le premier déploiement, voir
doc/guides/deploiement_azure_portail.md>`. Démarrage à froid possible (scale-to-zero) : ouvrir
l'URL une minute avant une démo.

**Déployer/relire l'infrastructure :**
- `doc/guides/deploiement_azure_portail.md` — créer les ressources Azure (portail, pas à pas).
- `doc/guides/github_actions_azure_oidc_portail.md` — connecter la CI à Azure sans secret
  longue durée.
- `.github/workflows/ci-cd.yml` — tests sur chaque PR, build + déploiement automatique sur `main`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: documente la GUI de démo et son déploiement dans le README"
```

---

## Après l'implémentation

Une fois les 9 tasks terminées : `uv run pytest -p no:cacheprovider -q`, `uv run ruff check .`,
`uv run mypy src` doivent tous passer sur l'ensemble du dépôt (base existante + webapp). Suivre
ensuite les Tasks 7 et 8 **à la main**, dans l'ordre (Azure d'abord, puis OIDC), avant de merger
vers `main` — le job `deploy` de la CI échouera sinon faute de ressources/secrets.
