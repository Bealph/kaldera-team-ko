"""Classe de base des sous-agents."""
from __future__ import annotations

from .. import logging_utils
from ..state import TeamState
from ..steps import Step


class RoleViolation(RuntimeError):
    """Un agent a reçu une étape hors de son périmètre."""


class BudgetExceeded(RuntimeError):
    """Un agent a dépassé son budget de tokens."""


class Agent:
    name: str = "agent"
    description: str = ""
    handles: set[Step] = set()
    token_budget: int = 1000
    step_cost: int = 100

    @property
    def system_prompt(self) -> str:
        handled = ", ".join(sorted(s.value for s in self.handles))
        return (
            f"Tu es l'agent {self.name}. Tu traites uniquement : {handled}. "
            f"Ne traite pas les étapes des autres agents."
        )

    def accepts(self, step: Step | None) -> bool:
        return step in self.handles

    def run(self, state: TeamState) -> None:
        step = state.current_step()
        if not self.accepts(step):
            raise RoleViolation(f"{self.name} ne traite pas l'étape {step}")
        used = state.agent_tokens.get(self.name, 0) + self.step_cost
        state.agent_tokens[self.name] = used
        assert step is not None
        self.act(state, step)
        logging_utils.record(state, self.name, f"a traité {step.value}")
        state.advance()

    def act(self, state: TeamState, step: Step) -> None:
        raise NotImplementedError
