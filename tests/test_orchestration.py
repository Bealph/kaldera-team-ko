"""Routage du superviseur et table de routage."""

from kaldera.orchestrator import END, AGENTS_BY_NAME, STEP_TO_AGENT, route
from kaldera.state import TeamState
from kaldera.steps import Step


def test_route_returns_end_once_all_steps_done():
    state = TeamState(required_steps=[Step.RESEARCH], step_index=1)
    assert route(state) == END


def test_review_is_routed_to_reviewer():
    assert STEP_TO_AGENT[Step.REVIEW] == "reviewer"


def test_finalizer_is_registered():
    assert "finalizer" in AGENTS_BY_NAME
