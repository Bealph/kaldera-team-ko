"""Superviseur : routage des étapes vers les sous-agents."""
from __future__ import annotations

from .agents.finalizer import Finalizer
from .agents.researcher import Researcher
from .agents.reviewer import Reviewer
from .agents.writer import Writer
from .state import TeamState
from .steps import Step

END = "__end__"

AGENTS = [Researcher(), Writer(), Reviewer()]
AGENTS_BY_NAME = {a.name: a for a in AGENTS}

STEP_TO_AGENT: dict[Step, str] = {
    Step.RESEARCH: "researcher",
    Step.DRAFT: "writer",
    Step.REVIEW: "writer",
    Step.FINALIZE: "finalizer",
}


def route(state: TeamState) -> str:
    if state.step_index > len(state.required_steps):
        return END
    current = state.required_steps[state.step_index]
    return STEP_TO_AGENT[current]
