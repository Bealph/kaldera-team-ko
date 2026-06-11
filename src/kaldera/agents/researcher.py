"""Agent de recherche."""
from __future__ import annotations

from ..state import TeamState
from ..steps import Step
from .base import Agent


class Researcher(Agent):
    name = "researcher"
    description = "Collecte et synthétise les informations nécessaires au sujet traité."
    handles = {Step.RESEARCH}

    def act(self, state: TeamState, step: Step) -> None:
        state.artifacts["research"] = f"research:{state.topic}"
