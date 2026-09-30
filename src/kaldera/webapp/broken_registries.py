"""Registres d'agents cassés en mémoire, pour rejouer en direct les 4 défauts historiques de
l'onglet « Casser un garde-fou » de la GUI. Jamais de modification de fichier source : chaque
sous-classe garde un `name`/`handles` cohérents avec son poste (sinon `check_demand` refuse la
demande avant même de démarrer), seul `act()` (ou `token_budget`) est cassé."""

from __future__ import annotations

from ..agents.base import RoleViolation
from ..agents.finalizer import Finalizer
from ..agents.researcher import Researcher
from ..agents.reviewer import Reviewer
from ..agents.writer import Writer
from ..state import TeamState
from ..steps import Step

DEFECTS: tuple[str, ...] = ("role_violation", "budget_exceeded", "step_limit", "stuck_agent")

_SCENARIO = {
    "initial_context": {
        "topic": "démo garde-fou",
        "required_steps": ["RESEARCH", "FINALIZE"],
    }
}


class _RoleViolationResearcher(Researcher):
    """Refuse toujours son étape, directement (contourne son propre `accepts()`, resté correct)."""

    def act(self, state: TeamState, step: Step) -> None:
        raise RoleViolation(f"{self.name} cassé pour la démo : refuse toujours son étape")


class _NoBudgetResearcher(Researcher):
    token_budget = 0


class _StuckResearcher(Researcher):
    """N'écrit jamais l'artefact attendu : refusé à chaque tentative."""

    def act(self, state: TeamState, step: Step) -> None:
        return


class _RetryOnceResearcher(Researcher):
    """Échoue une fois (rien n'est écrit, refusé), réussit normalement à la relance — consomme
    2 délégations pour 1 étape, ce qui ne laisse plus de marge si `max_iterations` est réglé
    exactement sur le nombre d'étapes requises."""

    def __init__(self) -> None:
        super().__init__()
        self._attempts = 0

    def act(self, state: TeamState, step: Step) -> None:
        self._attempts += 1
        if self._attempts == 1:
            return
        super().act(state, step)


def _registry(researcher: Researcher) -> dict[str, object]:
    return {
        "researcher": researcher,
        "writer": Writer(),
        "reviewer": Reviewer(),
        "finalizer": Finalizer(),
    }


def scenario_for(defect: str) -> tuple[dict, dict[str, object] | None, int | None]:
    """Renvoie `(scénario, agents_by_name, max_iterations)` prêts pour `run_scenario(**kwargs)`.

    `agents_by_name=None` signifie l'équipe normale (le défaut ne vient pas du registre) ;
    `max_iterations=None` signifie pas de limite forcée par ce défaut.
    """
    if defect == "role_violation":
        return _SCENARIO, _registry(_RoleViolationResearcher()), None
    if defect == "budget_exceeded":
        return _SCENARIO, _registry(_NoBudgetResearcher()), None
    if defect == "step_limit":
        # 2 étapes requises, limite réglée exactement à 2 : la relance de _RetryOnceResearcher
        # consomme les 2 délégations sur la seule étape RESEARCH, il n'en reste aucune pour
        # FINALIZE → step_limit_reached à la délégation suivante.
        return _SCENARIO, _registry(_RetryOnceResearcher()), 2
    if defect == "stuck_agent":
        return _SCENARIO, _registry(_StuckResearcher()), None
    raise ValueError(f"défaut inconnu : {defect!r} (attendu l'un de {DEFECTS})")
