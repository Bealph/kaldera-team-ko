"""Tests du chemin « live » (`graph.py`) : câblage réel du graphe, plus un vrai appel LLM.

Résout les limites connues de la PR #3 : `graph.py` n'est plus une coquille, et un vrai
LLM est exercé (test gardé par la présence des identifiants Azure AI — sans réseau sinon).
"""

from __future__ import annotations

import pytest

from kaldera import llm as llm_module
from kaldera.graph import build_graph, run_live
from kaldera.state import TeamState
from kaldera.steps import Step


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    """Double sans réseau : renvoie un contenu déterministe et dérivé du prompt."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def invoke(self, prompt: str) -> _FakeResponse:
        self.calls.append(prompt)
        return _FakeResponse(f"fake-output-{len(self.calls)}")


def test_build_graph_runs_full_flow_with_fake_llm():
    fake = _FakeLLM()
    state = TeamState(
        topic="lancement produit",
        required_steps=[Step.RESEARCH, Step.DRAFT, Step.REVIEW, Step.FINALIZE],
    )
    result = build_graph(fake, limit=10).invoke(state)

    assert result["status"] == "done"
    assert result["step_count"] == 4
    assert sorted(result["artifacts"]) == ["draft", "final", "research", "review"]
    assert len(fake.calls) == 4


def test_build_graph_stops_at_step_limit():
    fake = _FakeLLM()
    state = TeamState(topic="x", required_steps=[Step.RESEARCH, Step.DRAFT])
    result = build_graph(fake, limit=1).invoke(state)

    assert result["status"] == "aborted"
    assert result["stop_reason"] == "step_limit_reached"
    assert result["step_count"] == 1


def test_build_graph_rejects_role_violation():
    """Un agent hors périmètre (finalizer forcé sur RESEARCH) arrête le flux, pas de crash."""
    from kaldera.agents.finalizer import Finalizer
    from kaldera.orchestrator import AGENTS_BY_NAME

    fake = _FakeLLM()
    broken_registry = dict(AGENTS_BY_NAME)
    broken_registry["researcher"] = Finalizer()
    state = TeamState(topic="x", required_steps=[Step.RESEARCH])

    import kaldera.graph as graph_module

    original = graph_module.AGENTS_BY_NAME
    graph_module.AGENTS_BY_NAME = broken_registry
    try:
        result = build_graph(fake, limit=10).invoke(state)
    finally:
        graph_module.AGENTS_BY_NAME = original

    assert result["status"] == "aborted"
    assert result["stop_reason"] == "role_violation"


@pytest.mark.skipif(not llm_module.available(), reason="identifiants Azure AI absents")
def test_run_live_completes_with_a_real_llm():
    state = run_live("test automatisé", ["RESEARCH", "FINALIZE"], max_steps=5)

    assert state.status == "done"
    assert state.step_count == 2
    assert set(state.artifacts) == {"research", "final"}
    assert state.artifacts["research"].strip() != ""
    assert state.artifacts["final"].strip() != ""
