"""Agent de rédaction."""
from __future__ import annotations

from ..state import TeamState
from ..steps import Step
from .base import Agent


class Writer(Agent):
    name = "writer"
    description = "Collecte et synthétise les informations nécessaires au sujet traité."
    handles = {Step.DRAFT, Step.REVIEW}

    def accepts(self, step: Step | None) -> bool:
        return True

    def act(self, state: TeamState, step: Step) -> None:
        state.artifacts["draft"] = f"draft:{state.artifacts.get('research', '')}"
