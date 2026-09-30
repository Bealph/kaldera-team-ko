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
    """Un sub-agent : une étape, un artefact, un budget.

    Le rôle est déclaré une seule fois, par `handles` et `produces` : la table du chef, le
    refus hors du rôle, la réception et le prompt système s'en déduisent. Un agent traite
    son étape puis rend la main ; c'est le chef, après réception, qui fait avancer le flux.
    """

    name: str = "agent"
    description: str = ""
    handles: frozenset[Step] = frozenset()
    produces: str = ""
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

    def run(self, state: TeamState, llm: object | None = None) -> None:
        step = state.current_step()
        if step is None or not self.accepts(step):
            raise RoleViolation(f"{self.name} ne traite pas l'étape {step}")
        used = state.agent_tokens.get(self.name, 0) + self.step_cost
        state.agent_tokens[self.name] = used
        if used > self.token_budget:
            raise BudgetExceeded(
                f"{self.name} a consommé {used} tokens pour un budget de {self.token_budget}"
            )
        if llm is not None:
            self.act_with_llm(state, step, llm)
        else:
            self.act(state, step)
        logging_utils.record(state, self.name, f"a traité {step.value}", step)

    def act(self, state: TeamState, step: Step) -> None:
        raise NotImplementedError

    def render_prompt(self, state: TeamState) -> str:
        context = "\n".join(f"- {key} : {value}" for key, value in sorted(state.artifacts.items()))
        return (
            f"{self.system_prompt}\n\n"
            f"Sujet : {state.topic}\n"
            f"Artefacts disponibles :\n{context or '(aucun)'}\n\n"
            f"Produis uniquement le contenu de l'artefact « {self.produces} »."
        )

    def act_with_llm(self, state: TeamState, step: Step, llm: object) -> None:
        response = llm.invoke(self.render_prompt(state))  # type: ignore[attr-defined]
        state.artifacts[self.produces] = response.content
