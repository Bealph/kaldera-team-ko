"""Exécution de bout en bout des scénarios fournis."""

import json
from pathlib import Path

import pytest

from kaldera.runner import run_scenario

SCENARIOS = json.loads(
    (Path(__file__).resolve().parents[1] / "scenarios" / "scenarios_test.json").read_text(
        encoding="utf-8"
    )
)["scenarios"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_scenario_completes_within_budget(scenario):
    state = run_scenario(scenario)
    expected = scenario["expected"]
    assert state.status == expected["final_status"]
    assert state.step_count <= expected["max_steps"]
    for key in expected["artifacts"]:
        assert key in state.artifacts, f"artefact manquant : {key}"
