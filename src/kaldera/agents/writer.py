"""Agent de rédaction."""

from __future__ import annotations

from ..state import TeamState
from ..steps import Step
from .base import Agent


class Writer(Agent):
    name = "writer"
    description = "Rédige un premier jet à partir de la recherche, sans le relire."
    handles = frozenset({Step.DRAFT})
    produces = "draft"

    def act(self, state: TeamState, step: Step) -> None:
        state.artifacts["draft"] = f"draft:{state.artifacts.get('research', '')}"
