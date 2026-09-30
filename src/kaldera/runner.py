"""Boucle d'exécution d'un scénario par l'équipe : le chef confie, réceptionne, avance ou arrête."""

from __future__ import annotations

from .agents.base import BudgetExceeded, RoleViolation
from .logging_utils import record
from .orchestrator import AGENTS_BY_NAME, END, STEP_TO_ARTIFACT, SUPERVISOR, check_demand, route
from .state import ArtifactStore, TeamState
from .steps import Step, step_from_name

# Limite par défaut quand ni l'appelant ni le scénario n'en fixent une.
HARD_CAP = 50
_ABSENT = object()


def load_context(state: TeamState, scenario: dict) -> None:
    """Lit le sujet et les étapes de la demande ; un libellé inconnu lève `KeyError`."""
    context = scenario.get("initial_context", {})
    state.topic = context.get("topic")
    state.required_steps = [step_from_name(name) for name in context.get("required_steps", [])]


def _stop(state: TeamState, code: str, step: Step | None = None) -> TeamState:
    state.status = "aborted"
    state.stop_reason = code
    record(state, SUPERVISOR, f"arrêt : {code}", step)
    return state


def _artifacts_ok(
    store: ArtifactStore, snapshot: dict[str, str], first_write: int, step: Step
) -> bool:
    """Seul l'artefact attendu a été écrit, et il est présent.

    Le registre voit les réécritures à l'identique ; la comparaison avec l'instantané voit
    les écritures qui contourneraient le registre.
    """
    expected = STEP_TO_ARTIFACT[step]
    written = {w.key for w in store.writes[first_write:]}
    changed = {
        key
        for key in set(snapshot) | set(store)
        if snapshot.get(key, _ABSENT) != store.get(key, _ABSENT)
    }
    return expected in written and expected in store and written | changed == {expected}


def run_scenario(
    scenario: dict,
    max_iterations: int | None = None,
    agents_by_name: dict | None = None,
    initial_state: TeamState | None = None,
) -> TeamState:
    state = initial_state if initial_state is not None else TeamState()
    registry = agents_by_name if agents_by_name is not None else AGENTS_BY_NAME
    limit = (
        max_iterations
        if max_iterations is not None
        else scenario.get("expected", {}).get("max_steps")
    )
    if limit is None:
        limit = HARD_CAP
    state.step_limit = limit
    record(state, SUPERVISOR, f"limite d'étapes : {limit}")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        state.step_limit = 0
        return _stop(state, "invalid_demand:invalid_limit")
    if initial_state is None:
        try:
            load_context(state, scenario)
        except KeyError:
            return _stop(state, "invalid_demand:unknown_label")

    motif = check_demand(state, registry, limit)
    if motif is not None:
        return _stop(state, f"invalid_demand:{motif}")

    # Le chef tient son propre compte : un agent qui toucherait à l'état ne peut ni sauter une
    # étape ni rallonger la boucle. Chaque tour confie une étape ou termine.
    delegations = state.step_count
    retried = False
    while True:
        decision = route(state)
        if decision == END:
            if state.status != "done":
                return _stop(state, "missing_closure")
            record(state, SUPERVISOR, "fin : flux clos par le finalizer")
            return state
        step = state.current_step()
        assert step is not None
        if delegations >= limit:
            return _stop(state, "step_limit_reached", step)

        agent = registry[decision]
        record(state, SUPERVISOR, f"confie {step.value} à {decision}", step)
        store = state.artifacts
        snapshot, first_write = dict(store), len(store.writes)
        index, steps, status = state.step_index, list(state.required_steps), state.status
        delegations += 1
        state.step_count = delegations
        store.writer = (decision, step)
        failure: str | None = None
        try:
            agent.run(state)
        except RoleViolation:
            failure = "role_violation"
        except BudgetExceeded:
            failure = "budget_exceeded"
        except Exception:
            failure = "agent_error"
        finally:
            store.writer = None

        progression_ok = (
            state.artifacts is store
            and state.step_index == index
            and state.step_count == delegations
            and state.required_steps == steps
        )
        # Le chef reprend la main sur l'état, quoi qu'ait fait l'agent.
        state.artifacts, state.step_index, state.required_steps = store, index, steps
        state.step_count = delegations
        accepted = (
            failure is None
            and progression_ok
            and _artifacts_ok(store, snapshot, first_write, step)
            and (state.status == status or step is Step.FINALIZE)
        )
        if accepted:
            record(state, SUPERVISOR, f"réception acceptée : {step.value}", step)
            state.advance()
            retried = False
            continue

        # Passage refusé : ses écritures sont annulées et restent tracées comme refusées.
        for write in store.writes[first_write:]:
            write.refused = True
        store.restore(snapshot)
        state.status = status
        if failure is not None:
            return _stop(state, failure, step)
        if retried:
            return _stop(state, "reception_refused", step)
        record(state, SUPERVISOR, f"réception refusée : {step.value}, relance unique", step)
        retried = True
