"""Fonctions pures qui enveloppent l'orchestrateur pour la GUI (aucun import de `gradio` ici,
testables sans lancer de serveur). Zéro changement à runner.py/graph.py/orchestrator.py."""

from __future__ import annotations

from collections.abc import Iterator

from ..graph import HARD_CAP, build_graph
from ..llm import build_llm
from ..orchestrator import AGENTS_BY_NAME, SUPERVISOR, check_demand
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
            if node_name == SUPERVISOR:
                continue
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
