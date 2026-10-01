"""Superviseur : routage des étapes vers les sous-agents et vérification de la demande."""

from __future__ import annotations

from collections.abc import Mapping

from .agents.finalizer import Finalizer
from .agents.researcher import Researcher
from .agents.reviewer import Reviewer
from .agents.writer import Writer
from .state import TeamState
from .steps import Step

END = "__end__"
SUPERVISOR = "supervisor"

AGENTS = [Researcher(), Writer(), Reviewer(), Finalizer()]
AGENTS_BY_NAME = {a.name: a for a in AGENTS}

# Table du chef et artefacts attendus, déduits des fiches de poste (une seule déclaration).
STEP_TO_AGENT: dict[Step, str] = {step: a.name for a in AGENTS for step in a.handles}
STEP_TO_ARTIFACT: dict[Step, str] = {step: a.produces for a in AGENTS for step in a.handles}

# Entrée de chaque étape : au moins une de ces étapes doit la précéder dans la demande.
STEP_INPUTS: dict[Step, frozenset[Step]] = {
    Step.DRAFT: frozenset({Step.RESEARCH}),
    Step.REVIEW: frozenset({Step.DRAFT}),
    Step.FINALIZE: frozenset({Step.RESEARCH, Step.DRAFT, Step.REVIEW}),
}


def route(state: TeamState) -> str:
    if state.step_index >= len(state.required_steps):
        return END
    current = state.required_steps[state.step_index]
    return STEP_TO_AGENT[current]


def check_demand(state: TeamState, registry: Mapping[str, object], limit: int) -> str | None:
    """Vérifie la demande, l'état et l'équipe avant tout travail ; renvoie le motif d'un refus."""
    steps = state.required_steps
    if not all(isinstance(step, Step) for step in steps):
        return "unknown_label"
    if not (state.topic or "").strip() or not steps:
        return "empty"
    if state.status != "pending" or state.step_index != 0 or state.artifacts:
        return "state_not_fresh"
    if len(set(steps)) != len(steps):
        return "duplicate_step"
    if Step.FINALIZE in steps and steps[-1] is not Step.FINALIZE:
        return "finalize_not_last"
    for index, step in enumerate(steps):
        inputs = STEP_INPUTS.get(step)
        if inputs is not None and not inputs & set(steps[:index]):
            return "missing_input"
    if len(steps) > limit:
        return "too_many_steps"
    for key, agent in registry.items():
        if getattr(agent, "name", key) != key:
            return "team_incomplete"
    for step in steps:
        declared = [key for key, a in registry.items() if step in getattr(a, "handles", ())]
        if STEP_TO_AGENT.get(step) not in registry or len(declared) > 1:
            return "team_incomplete"
    return None
