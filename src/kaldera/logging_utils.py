"""Journalisation des actions des agents."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import TeamState


def record(state: "TeamState", agent_id: str, message: str) -> dict:
    entry = {"message": message}
    state.log.append(entry)
    return entry
