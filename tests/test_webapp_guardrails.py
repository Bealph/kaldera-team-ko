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
