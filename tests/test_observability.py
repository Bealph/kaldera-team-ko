"""Traçabilité des logs et budget de tokens par agent."""

import pytest

from kaldera import logging_utils
from kaldera.agents.base import Agent, BudgetExceeded
from kaldera.state import TeamState
from kaldera.steps import Step


def test_log_entry_carries_agent_id():
    state = TeamState()
    entry = logging_utils.record(state, "researcher", "a traité RESEARCH")
    assert entry["agent_id"] == "researcher"
    assert state.log[-1]["agent_id"] == "researcher"


class _GreedyAgent(Agent):
    name = "greedy"
    handles = {Step.RESEARCH}
    token_budget = 50
    step_cost = 100

    def act(self, state: TeamState, step: Step) -> None:
        state.artifacts["research"] = "ok"


def test_per_agent_token_budget_is_enforced():
    state = TeamState(topic="x", required_steps=[Step.RESEARCH])
    with pytest.raises(BudgetExceeded):
        _GreedyAgent().run(state)
