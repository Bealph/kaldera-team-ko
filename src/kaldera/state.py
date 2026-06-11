"""État partagé d'une exécution de l'équipe."""
from __future__ import annotations

from dataclasses import dataclass, field

from .steps import Step


@dataclass
class TeamState:
    topic: str | None = None
    required_steps: list[Step] = field(default_factory=list)
    step_index: int = 0
    artifacts: dict[str, str] = field(default_factory=dict)
    status: str = "pending"
    step_count: int = 0
    agent_tokens: dict[str, int] = field(default_factory=dict)
    log: list[dict] = field(default_factory=list)

    def current_step(self) -> Step | None:
        if self.step_index >= len(self.required_steps):
            return None
        return self.required_steps[self.step_index]

    def advance(self) -> None:
        self.step_index += 1
