"""Chargement du contexte et garde-fou de budget d'étapes."""
from kaldera.runner import load_context, run_scenario
from kaldera.state import TeamState
from kaldera.steps import Step


def test_load_context_populates_state():
    state = TeamState()
    scenario = {
        "initial_context": {
            "topic": "lancement produit",
            "required_steps": ["RESEARCH", "FINALIZE"],
        }
    }
    load_context(state, scenario)
    assert state.topic == "lancement produit"
    assert state.required_steps == [Step.RESEARCH, Step.FINALIZE]


class _StuckAgent:
    """Agent qui ne fait jamais avancer l'état (simule une boucle)."""

    name = "researcher"

    def run(self, state: TeamState) -> None:  # noqa: D401 - test double
        return


def test_step_budget_is_enforced():
    state = TeamState(topic="x", required_steps=[Step.RESEARCH])
    result = run_scenario(
        scenario={},
        max_iterations=3,
        agents_by_name={"researcher": _StuckAgent()},
        initial_state=state,
    )
    assert result.status == "aborted"
    assert result.step_count <= 4
