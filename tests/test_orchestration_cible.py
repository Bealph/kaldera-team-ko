"""Tests de l'orchestration cible : dessin de l'équipe, boucles, arrêts, conflits, invariants.

Conçus au point 4 de la conception (doc/conception_point_4_detection_par_les_tests.md) et
ajustés aux décisions validées le 30/09/2026 : relance unique après une réception refusée
(D3), FINALIZE non exigé au départ (D5). Les tests fournis ne sont pas modifiés.
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from kaldera import orchestrator
from kaldera.agents.base import Agent
from kaldera.agents.finalizer import Finalizer
from kaldera.agents.researcher import Researcher
from kaldera.agents.writer import Writer
from kaldera.orchestrator import AGENTS_BY_NAME, STEP_TO_AGENT, STEP_TO_ARTIFACT, SUPERVISOR
from kaldera.runner import run_scenario
from kaldera.state import TeamState
from kaldera.steps import Step

R, D, RV, F = Step.RESEARCH, Step.DRAFT, Step.REVIEW, Step.FINALIZE
SCENARIOS = {
    s["id"]: s
    for s in json.loads(
        (Path(__file__).resolve().parents[1] / "scenarios" / "scenarios_test.json").read_text(
            encoding="utf-8"
        )
    )["scenarios"]
}


# --------------------------------------------------------------------------- outils


def run(steps, *, topic="sujet", agents=None, registry=None, max_iterations=None, state=None):
    """Exécute une demande par un état fourni directement, avec une équipe éventuellement modifiée."""
    team = dict(AGENTS_BY_NAME) if registry is None else dict(registry)
    team.update(agents or {})
    state = state or TeamState(topic=topic, required_steps=list(steps))
    return run_scenario({}, max_iterations=max_iterations, agents_by_name=team, initial_state=state)


def chief(state, prefix):
    return [e for e in state.log if e["agent_id"] == SUPERVISOR and e["message"].startswith(prefix)]


def agent_actions(state):
    return [e for e in state.log if e["agent_id"] != SUPERVISOR]


def assert_invariants(state):
    """I1 à I6, vérifiés après n'importe quelle exécution, sur le seul travail accepté."""
    delegations = chief(state, "confie")
    relances = {e["step"] for e in chief(state, "réception refusée")}
    # I1 : une étape confiée au plus deux fois, la seconde seulement après un refus.
    for step, n in Counter(e["step"] for e in delegations).items():
        assert n <= 2, f"I1 : {step} confiée {n} fois"
        assert n == 1 or step in relances, f"I1 : {step} reconfiée sans refus préalable"
    # I2 : aucun agent n'agit sans délégation préalable du chef, à lui, pour cette étape.
    delegated = []
    for entry in state.log:
        if entry["agent_id"] == SUPERVISOR and entry["message"].startswith("confie"):
            delegated.append((entry["message"].rsplit(" ", 1)[-1], entry["step"]))
        elif entry["agent_id"] != SUPERVISOR:
            assert delegated and delegated[-1] == (entry["agent_id"], entry["step"]), (
                f"I2 : {entry['agent_id']} agit sur {entry['step']} sans délégation"
            )
    # I3 : chaque étape acceptée a été traitée par son propriétaire.
    for entry in chief(state, "réception acceptée"):
        step = Step(entry["step"])
        actors = [e["agent_id"] for e in agent_actions(state) if e["step"] == step.value]
        assert actors and actors[-1] == STEP_TO_AGENT[step], f"I3 : {step.value} par {actors}"
    # I4 : chaque artefact accepté est écrit une seule fois, par son propriétaire.
    owners = {artifact: STEP_TO_AGENT[step] for step, artifact in STEP_TO_ARTIFACT.items()}
    accepted = [w for w in state.artifacts.writes if not w.refused]
    for key, n in Counter(w.key for w in accepted).items():
        assert n == 1, f"I4 : {key} écrit {n} fois"
    for write in accepted:
        assert write.agent == owners.get(write.key), f"I4 : {write.key} écrit par {write.agent}"
    # I5 : le nombre d'étapes confiées ne dépasse pas la limite notée au départ.
    assert state.step_limit is not None and state.step_count <= state.step_limit, "I5"
    # I6 : done seulement après clôture par le finalizer ; aborted toujours motivé.
    assert state.status in {"done", "aborted"}, f"I6 : statut final {state.status}"
    if state.status == "done":
        assert state.stop_reason is None and chief(state, "fin : flux clos par le finalizer")
        assert agent_actions(state)[-1]["agent_id"] == STEP_TO_AGENT[F]
    else:
        assert state.stop_reason, "I6 : arrêt sans code"
    # I7 : un flux clos a accepté chaque étape demandée une fois, dans l'ordre de la demande.
    if state.status == "done":
        accepted_steps = [e["step"] for e in chief(state, "réception acceptée")]
        assert accepted_steps == [s.value for s in state.required_steps], f"I7 : {accepted_steps}"


# --------------------------------------------------------------- niveau 1 · dessin


def test_routing_table_matches_owners():
    for step in Step:
        owners = [a.name for a in AGENTS_BY_NAME.values() if step in a.handles]
        assert owners == [STEP_TO_AGENT[step]], f"{step.value} : propriétaires {owners}"


def test_every_agent_refuses_every_foreign_step():
    verdicts = [
        (agent.accepts(step), step in agent.handles)
        for agent in AGENTS_BY_NAME.values()
        for step in Step
    ]
    assert all(accepted == owned for accepted, owned in verdicts)
    assert sum(accepted for accepted, _ in verdicts) == 4
    assert sum(not accepted for accepted, _ in verdicts) == 12


# ------------------------------------------------------ niveau 2 · boucles et arrêts


class _StuckResearcher:
    """Rend la main sans rien écrire : la boucle du point 1."""

    name = "researcher"

    def __init__(self):
        self.calls = 0

    def run(self, state):
        self.calls += 1


def test_stuck_agent_is_stopped_after_one_retry():
    stuck = _StuckResearcher()
    state = run([R, F], agents={"researcher": stuck})
    assert (state.status, state.stop_reason) == ("aborted", "reception_refused")
    assert stuck.calls == 2 and state.step_count == 2
    assert_invariants(state)


def test_step_guard_stops_at_limit():
    state = TeamState(topic="sujet", required_steps=[R, F], step_count=2)
    state = run([], state=state, max_iterations=2)
    assert (state.status, state.stop_reason) == ("aborted", "step_limit_reached")
    assert agent_actions(state) == [] and dict(state.artifacts) == {}


class _SecondReviewer(Agent):
    """Deuxième agent qui revendique REVIEW : l'équipe n'a plus un seul propriétaire."""

    name = "second_reviewer"
    handles = frozenset({RV})
    produces = "review"


@pytest.mark.parametrize(
    ("motif", "steps", "kwargs"),
    [
        ("empty", [R, F], {"topic": ""}),
        ("empty", [], {}),
        ("duplicate_step", [R, R, F], {}),
        ("missing_input", [D, F], {}),
        ("too_many_steps", [R, D, RV, F], {"max_iterations": 3}),
        ("empty", [R, F], {"topic": "   "}),
        ("finalize_not_last", [R, F, D], {}),
        ("team_incomplete", [R, F], {"registry": {"researcher": Researcher()}}),
        ("team_incomplete", [R, D, F], {"agents": {"writer": Researcher()}}),
        ("team_incomplete", [R, D, RV, F], {"agents": {"second_reviewer": _SecondReviewer()}}),
        ("unknown_label", ["RESEARCH", "PROOFREAD"], {}),
    ],
)
def test_invalid_demands_are_refused(motif, steps, kwargs):
    state = run(steps, **kwargs)
    assert (state.status, state.stop_reason) == ("aborted", f"invalid_demand:{motif}")
    assert state.step_count == 0 and agent_actions(state) == []


def test_unknown_label_is_refused_at_reading():
    scenario = {"initial_context": {"topic": "sujet", "required_steps": ["RESEARCH", "PROOFREAD"]}}
    state = run_scenario(scenario)
    assert (state.status, state.stop_reason) == ("aborted", "invalid_demand:unknown_label")
    assert state.step_count == 0


class _LazyFinalizer(Finalizer):
    """Écrit `final` sans clore le flux."""

    def act(self, state, step):
        state.artifacts["final"] = "final:"


@pytest.mark.parametrize(
    ("steps", "agents"),
    [([R, F], {"finalizer": _LazyFinalizer()}), ([R], {})],
    ids=["finalizer_sans_cloture", "demande_sans_finalize"],
)
def test_missing_closure_is_detected(steps, agents):
    state = run(steps, agents=agents)
    assert (state.status, state.stop_reason) == ("aborted", "missing_closure")
    assert_invariants(state)


class _GreedyResearcher(Researcher):
    token_budget = 50


def test_budget_exceeded_stops_flow():
    state = run([R, F], agents={"researcher": _GreedyResearcher()})
    assert (state.status, state.stop_reason) == ("aborted", "budget_exceeded")
    assert agent_actions(state) == [] and dict(state.artifacts) == {}
    assert not chief(state, "confie FINALIZE")
    assert_invariants(state)


# ------------------------------------------------------------- niveau 3 · conflits


@pytest.mark.parametrize(
    ("scenario_id", "owners", "source"),
    [
        ("happy_path", ["researcher", "writer", "reviewer", "finalizer"], "review"),
        ("research_only", ["researcher", "finalizer"], "research"),
    ],
)
def test_each_step_is_done_by_its_owner(scenario_id, owners, source):
    scenario = SCENARIOS[scenario_id]
    state = run_scenario(scenario)
    assert state.status == "done"
    # Oracle indépendant de max_steps : ordre des agents, nombre exact d'étapes, source de final.
    assert [e["agent_id"] for e in agent_actions(state)] == owners
    assert state.step_count == len(scenario["initial_context"]["required_steps"])
    assert state.artifacts["final"] == f"final:{state.artifacts[source]}"
    assert_invariants(state)


class _IntruderWriter(Writer):
    """Écrit son brouillon, puis l'artefact du reviewer."""

    def act(self, state, step):
        super().act(state, step)
        state.artifacts["review"] = "review[writer]:intrus"


def test_intruder_agent_is_rejected():
    state = run([R, D, RV, F], agents={"writer": _IntruderWriter()})
    assert (state.status, state.stop_reason) == ("aborted", "reception_refused")
    assert not chief(state, "confie REVIEW")
    assert {"draft", "review"} <= state.incomplete
    assert_invariants(state)


class _TracingAgent(Agent):
    """Agent de repli qui note chaque appel : il ne doit jamais être sollicité."""

    name = "reviewer"
    handles = frozenset({RV})
    produces = "review"

    def __init__(self):
        self.calls = 0

    def act(self, state, step):
        self.calls += 1


def test_foreign_step_stops_flow_without_retry(monkeypatch):
    monkeypatch.setitem(orchestrator.STEP_TO_AGENT, RV, "writer")
    fallback = _TracingAgent()
    state = run([R, D, RV, F], agents={"reviewer": fallback})
    assert (state.status, state.stop_reason) == ("aborted", "role_violation")
    assert len(chief(state, "confie REVIEW")) == 1 and fallback.calls == 0
    assert "review" not in state.artifacts


def test_state_already_started_is_refused():
    for started in (
        TeamState(topic="t", required_steps=[R], status="done"),
        TeamState(topic="t", required_steps=[R, F], artifacts={"review": "ancien"}),
    ):
        state = run([], state=started)
        assert state.stop_reason == "invalid_demand:state_not_fresh"
        assert agent_actions(state) == []


def test_invalid_limit_is_refused():
    state = run_scenario(
        {
            "initial_context": {"topic": "t", "required_steps": ["RESEARCH"]},
            "expected": {"max_steps": "5"},
        }
    )
    assert (state.status, state.stop_reason) == ("aborted", "invalid_demand:invalid_limit")


# ---------------------------------------- réception : le chef garde la main sur l'état


class _SelfAdvancingWriter(Writer):
    """Fait avancer le flux lui-même, comme l'agent du code d'origine."""

    def act(self, state, step):
        super().act(state, step)
        state.advance()


class _CounterTamperingResearcher(Researcher):
    """Écrit correctement, puis recule l'état pour se faire rappeler sans fin."""

    def act(self, state, step):
        super().act(state, step)
        state.step_index -= 1
        state.step_count -= 1


@pytest.mark.parametrize(
    ("agents", "step"),
    [({"writer": _SelfAdvancingWriter()}, D), ({"researcher": _CounterTamperingResearcher()}, R)],
    ids=["agent_qui_avance", "agent_qui_recule"],
)
def test_agent_cannot_drive_progression(agents, step):
    state = run([R, D, RV, F], agents=agents)
    assert (state.status, state.stop_reason) == ("aborted", "reception_refused")
    assert len(chief(state, f"confie {step.value}")) == 2 and state.step_count <= 4
    assert_invariants(state)


class _OnceFlaky:
    """Mixin : le premier passage fait `sabotage`, le second se comporte normalement."""

    def __init__(self):
        self.calls = 0

    def act(self, state, step):
        self.calls += 1
        super().act(state, step)
        if self.calls == 1:
            self.sabotage(state)


class _PoisoningWriter(_OnceFlaky, Writer):
    def sabotage(self, state):
        state.artifacts["research"] = "POISON"


class _EarlyReviewWriter(_OnceFlaky, Writer):
    def sabotage(self, state):
        state.artifacts["review"] = "review[writer]:intrus"


def test_refused_writes_are_rolled_back():
    state = run([R, D, RV, F], agents={"writer": _PoisoningWriter()})
    assert state.status == "done"
    assert state.artifacts["research"] == "research:sujet"
    assert "POISON" not in state.artifacts["final"]
    assert_invariants(state)
    state = run([R, D, F], agents={"writer": _EarlyReviewWriter()})
    assert state.status == "done" and "review" not in state.artifacts
    assert state.artifacts["final"] == f"final:{state.artifacts['draft']}"
    assert_invariants(state)


class _ClosingResearcher(Researcher):
    def act(self, state, step):
        super().act(state, step)
        state.status = "done"


def test_only_finalizer_can_close():
    state = run([R, F], agents={"researcher": _ClosingResearcher()})
    assert (state.status, state.stop_reason) == ("aborted", "reception_refused")
    assert not chief(state, "confie FINALIZE")
    assert_invariants(state)


def _raw_write(state):
    dict.__setitem__(state.artifacts, "review", "brut")


def _or_write(state):
    state.artifacts |= {"review": "ior"}


def _delete(state):
    del state.artifacts["research"]


def _pop(state):
    state.artifacts.pop("research")


def _replace_store(state):
    state.artifacts = {"research": "remplacé", "draft": "draft:x"}


@pytest.mark.parametrize("tamper", [_raw_write, _or_write, _delete, _pop, _replace_store])
def test_writes_outside_the_role_are_detected(tamper):
    class _TamperingWriter(Writer):
        def act(self, state, step):
            super().act(state, step)
            tamper(state)

    state = run([R, D, F], agents={"writer": _TamperingWriter()})
    assert (state.status, state.stop_reason) == ("aborted", "reception_refused")
    assert dict(state.artifacts) == {"research": "research:sujet"}
    assert_invariants(state)


class _CrashingWriter(Writer):
    def act(self, state, step):
        state.artifacts["draft"] = "moitié"
        raise ValueError("panne")


def test_unexpected_agent_error_is_stopped():
    state = run([R, D, F], agents={"writer": _CrashingWriter()})
    assert (state.status, state.stop_reason) == ("aborted", "agent_error")
    assert "draft" not in state.artifacts and "draft" in state.incomplete
    assert_invariants(state)


class _FlakyResearcher(_OnceFlaky, Researcher):
    def sabotage(self, state):
        del state.artifacts["research"]


class _FlakyWriter(_OnceFlaky, Writer):
    def sabotage(self, state):
        del state.artifacts["draft"]


def test_retry_is_granted_once_per_step():
    agents = {"researcher": _FlakyResearcher(), "writer": _FlakyWriter()}
    state = run([R, D, RV, F], agents=agents)
    assert state.status == "done" and state.step_count == 6
    assert_invariants(state)


def test_step_guard_reached_by_real_retries():
    agents = {"researcher": _FlakyResearcher(), "writer": _FlakyWriter()}
    state = run([R, D, RV, F], agents=agents, max_iterations=5)
    assert (state.status, state.stop_reason) == ("aborted", "step_limit_reached")
    assert state.step_count == 5
    assert_invariants(state)
