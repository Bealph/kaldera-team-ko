"""Fonctions pures qui enveloppent l'orchestrateur pour la GUI (aucun import de `gradio` ici,
testables sans lancer de serveur). Zéro changement à runner.py/graph.py/orchestrator.py."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

from ..graph import HARD_CAP, build_graph
from ..llm import build_llm
from ..orchestrator import AGENTS_BY_NAME, SUPERVISOR, check_demand
from ..runner import run_scenario
from ..state import TeamState
from ..steps import step_from_name
from . import broken_registries

_logger = logging.getLogger(__name__)
_SCENARIOS_PATH = Path(__file__).resolve().parents[3] / "scenarios" / "scenarios_test.json"


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


def load_scenarios() -> list[dict]:
    return json.loads(_SCENARIOS_PATH.read_text())["scenarios"]


def run_named_scenario(scenario_id: str) -> dict:
    scenarios = {s["id"]: s for s in load_scenarios()}
    state = run_scenario(scenarios[scenario_id])
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

    last: dict = {
        "node": None,
        "status": state.status,
        "step_count": state.step_count,
        "artifacts": dict(state.artifacts),
        "stop_reason": state.stop_reason,
        "log": list(state.log),
    }

    try:
        client = llm if llm is not None else build_llm()
        graph = build_graph(client, limit)
        for chunk in graph.stream(state):
            node_name, node_state = next(iter(chunk.items()))
            if node_name == SUPERVISOR:
                continue
            last = {
                "node": node_name,
                "status": node_state["status"],
                "step_count": node_state["step_count"],
                "artifacts": dict(node_state["artifacts"]),
                "stop_reason": node_state["stop_reason"],
                "log": list(node_state["log"]),
            }
            yield last
    except Exception:
        _logger.exception("échec du run live (topic=%r, steps=%r)", topic, steps)
        yield {
            "node": None,
            "status": "aborted",
            "step_count": last["step_count"],
            "artifacts": last["artifacts"],
            "stop_reason": "llm_error",
            "log": last["log"],
        }
        return

    # LangGraph ne conserve pas les changements d'état faits dans `route_from_state`
    # (fonction de routage) : un chemin qui s'arrête sans clôture (ex. FINALIZE non demandé)
    # laisse le dernier chunk "pending" au lieu de "aborted"/"missing_closure", contrairement
    # au chemin déterministe (`run_scenario`). Rattrapé ici plutôt que dans graph.py (contrainte
    # du plan : aucun changement à graph.py/runner.py/orchestrator.py).
    if last["status"] not in ("done", "aborted"):
        yield {
            **last,
            "node": None,
            "status": "aborted",
            "stop_reason": "missing_closure",
        }
