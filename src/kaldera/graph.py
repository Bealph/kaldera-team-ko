"""Construction du graphe d'agents (LangGraph) pour l'exécution « live ».

Le runner déterministe (`runner.py`) reste le point d'entrée des scénarios
rejouables ; ce module câble les mêmes agents dans un `StateGraph` pour
l'exécution branchée sur le LLM.
"""
from __future__ import annotations

from .orchestrator import END, AGENTS_BY_NAME, route
from .state import TeamState


def build_graph():
    from langgraph.graph import StateGraph

    graph = StateGraph(dict)

    def supervisor(state: dict) -> dict:
        return state

    graph.add_node("supervisor", supervisor)
    for name, agent in AGENTS_BY_NAME.items():
        graph.add_node(name, lambda s, a=agent: s)

    graph.set_entry_point("supervisor")
    return graph


__all__ = ["build_graph", "route", "END", "TeamState"]
