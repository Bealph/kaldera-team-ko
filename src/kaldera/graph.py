"""Construction et exécution du chemin « live » (LangGraph + vrai LLM).

Le runner déterministe (`runner.py`) reste le point d'entrée des scénarios rejouables ;
ce module câble les mêmes agents et les mêmes règles (`route`, `check_demand`) dans un
`StateGraph` réel, avec un vrai appel LLM par étape (`llm.py`).

ponytail: pas de relance après réception refusée ici (contrairement à runner.py) —
un rôle hors périmètre ou un budget dépassé arrête le flux directement. À ajouter si
le chemin live doit un jour rejouer une étape.
"""
from __future__ import annotations

from .agents.base import BudgetExceeded, RoleViolation
from .llm import build_llm
from .orchestrator import AGENTS_BY_NAME, END, SUPERVISOR, check_demand, route
from .state import TeamState
from .steps import step_from_name

HARD_CAP = 50


def build_graph(llm: object, limit: int = HARD_CAP):
    from langgraph.graph import END as LG_END
    from langgraph.graph import StateGraph

    def make_node(agent):
        def node(state: TeamState) -> TeamState:
            if state.step_count >= limit:
                state.status = "aborted"
                state.stop_reason = "step_limit_reached"
                return state
            try:
                agent.run(state, llm=llm)
            except RoleViolation:
                state.status = "aborted"
                state.stop_reason = "role_violation"
            except BudgetExceeded:
                state.status = "aborted"
                state.stop_reason = "budget_exceeded"
            else:
                state.step_count += 1
                state.advance()
            return state

        return node

    def supervisor(state: TeamState) -> TeamState:
        return state

    def route_from_state(state: TeamState) -> str:
        if state.status == "aborted":
            return "__end__"
        decision = route(state)
        if decision == END:
            if state.status != "done":
                state.status = "aborted"
                state.stop_reason = "missing_closure"
            return "__end__"
        return decision

    graph = StateGraph(TeamState)
    graph.add_node(SUPERVISOR, supervisor)
    for name, agent in AGENTS_BY_NAME.items():
        graph.add_node(name, make_node(agent))
        graph.add_edge(name, SUPERVISOR)

    graph.add_conditional_edges(
        SUPERVISOR,
        route_from_state,
        {**{name: name for name in AGENTS_BY_NAME}, "__end__": LG_END},
    )
    graph.set_entry_point(SUPERVISOR)
    return graph.compile()


def run_live(topic: str, required_steps: list[str], max_steps: int | None = None) -> TeamState:
    """Exécute un flux réel : vrai LLM, mêmes garde-fous que le chef déterministe."""
    state = TeamState(topic=topic, required_steps=[step_from_name(s) for s in required_steps])
    limit = max_steps if max_steps is not None else HARD_CAP
    state.step_limit = limit

    motif = check_demand(state, AGENTS_BY_NAME, limit)
    if motif is not None:
        state.status = "aborted"
        state.stop_reason = f"invalid_demand:{motif}"
        return state

    llm = build_llm()
    graph = build_graph(llm, limit)
    result = graph.invoke(state)
    return TeamState(**result) if isinstance(result, dict) else result


__all__ = ["build_graph", "run_live", "route", "END", "TeamState"]
