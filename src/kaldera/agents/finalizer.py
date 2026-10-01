"""Agent de finalisation : assemble le résultat et clôt le flux."""

from __future__ import annotations

from ..state import TeamState
from ..steps import Step
from .base import Agent

# Du plus abouti au moins abouti : la relecture corrige le jet, qui part de la recherche.
CONTENT_BY_MATURITY = ("review", "draft", "research")


class Finalizer(Agent):
    name = "finalizer"
    description = "Assemble le résultat final et clôt le traitement."
    handles = frozenset({Step.FINALIZE})
    produces = "final"

    def act(self, state: TeamState, step: Step) -> None:
        source = next((key for key in CONTENT_BY_MATURITY if key in state.artifacts), None)
        content = state.artifacts[source] if source is not None else ""
        state.artifacts["final"] = f"final:{content}"
        state.status = "done"

    def act_with_llm(self, state: TeamState, step: Step, llm: object) -> None:
        super().act_with_llm(state, step, llm)
        state.status = "done"
