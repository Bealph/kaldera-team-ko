"""Agent de finalisation : assemble le résultat et clôt le flux."""
from __future__ import annotations

from ..state import TeamState
from ..steps import Step
from .base import Agent


class Finalizer(Agent):
    name = "finalizer"
    description = "Assemble le résultat final et clôt le traitement."
    handles = {Step.FINALIZE}

    def act(self, state: TeamState, step: Step) -> None:
        state.artifacts["final"] = f"final:{state.artifacts.get('review', '')}"
        state.status = "done"
