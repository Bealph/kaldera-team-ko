"""Agent de relecture."""
from __future__ import annotations

from ..state import TeamState
from ..steps import Step
from .base import Agent


class Reviewer(Agent):
    name = "reviewer"
    description = "Relit le premier jet et signale les corrections à apporter."
    handles = {Step.REVIEW}

    def act(self, state: TeamState, step: Step) -> None:
        state.artifacts["review"] = f"review[{self.name}]:{state.artifacts.get('draft', '')}"
