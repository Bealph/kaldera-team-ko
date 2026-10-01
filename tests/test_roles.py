"""Frontières et rôles des sous-agents."""
from kaldera.agents.finalizer import Finalizer
from kaldera.agents.researcher import Researcher
from kaldera.agents.reviewer import Reviewer
from kaldera.agents.writer import Writer
from kaldera.steps import Step

AGENTS = [Researcher(), Writer(), Reviewer(), Finalizer()]


def test_each_step_handled_by_exactly_one_agent():
    counts: dict[Step, int] = {}
    for agent in AGENTS:
        for step in agent.handles:
            counts[step] = counts.get(step, 0) + 1
    overlaps = {step: n for step, n in counts.items() if n > 1}
    assert overlaps == {}, f"étapes confiées à plusieurs agents : {overlaps}"


def test_writer_refuses_foreign_step():
    writer = Writer()
    assert writer.accepts(Step.RESEARCH) is False
    assert writer.accepts(Step.DRAFT) is True


def test_agent_descriptions_are_distinct():
    descriptions = [a.description for a in AGENTS]
    assert len(set(descriptions)) == len(descriptions)
