"""`max_steps` doit être lu dans la demande (`initial_context`) en priorité sur `expected`,
conformément à la spécification (l. 29) — sans modifier `scenarios_test.json` (fourni, D9).
"""

from __future__ import annotations

from kaldera.runner import run_scenario


def test_initial_context_max_steps_takes_priority_over_expected():
    scenario = {
        "initial_context": {
            "topic": "x",
            "required_steps": ["RESEARCH"],
            "max_steps": 1,
        },
        "expected": {"max_steps": 5},
    }
    state = run_scenario(scenario)
    assert state.step_limit == 1


def test_expected_max_steps_is_still_used_as_fallback():
    scenario = {
        "initial_context": {"topic": "x", "required_steps": ["RESEARCH"]},
        "expected": {"max_steps": 3},
    }
    state = run_scenario(scenario)
    assert state.step_limit == 3
