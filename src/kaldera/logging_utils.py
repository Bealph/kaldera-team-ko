"""Journalisation des actions des agents et des décisions du chef."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import TeamState
    from .steps import Step


def record(state: TeamState, agent_id: str, message: str, step: Step | None = None) -> dict:
    entry = {
        "agent_id": agent_id,
        "step": step.value if step is not None else None,
        "message": message,
    }
    state.log.append(entry)
    return entry
