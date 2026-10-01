"""L'app Gradio se construit sans erreur, et ses callbacks (fonctions Python nues, appelables
sans passer par le runtime Gradio) se comportent correctement — y compris le respect du
garde-fou de coût par la callback « vrai LLM »."""

from __future__ import annotations

import pytest

gr = pytest.importorskip("gradio")

from kaldera.webapp import app as webapp_app  # noqa: E402


def test_build_app_returns_a_blocks_instance():
    demo = webapp_app.build_app()
    assert isinstance(demo, gr.Blocks)


def test_on_run_deterministic_returns_a_summary_dict():
    result = webapp_app.on_run_deterministic("sujet", ["RESEARCH", "FINALIZE"])
    assert result["status"] == "done"


def test_on_run_deterministic_reorders_steps_clicked_out_of_order():
    # Gradio's CheckboxGroup appends a re-checked box at the end of the value list, in click
    # order, not in the order the boxes are displayed — so a demo click sequence can legitimately
    # produce ["FINALIZE", "RESEARCH"] even though the form still shows RESEARCH above FINALIZE.
    result = webapp_app.on_run_deterministic("sujet", ["FINALIZE", "RESEARCH"])
    assert result["status"] == "done"
    assert result["stop_reason"] is None


def test_on_run_live_reorders_steps_before_calling_stream_live(monkeypatch):
    received: dict = {}

    def fake_stream_live(topic, steps, llm=None, max_steps=None):
        received["steps"] = steps
        yield {"node": "researcher", "status": "done", "step_count": 1, "artifacts": {}, "stop_reason": None, "log": []}

    monkeypatch.setattr(webapp_app.runners, "stream_live", fake_stream_live)
    list(webapp_app.on_run_live("sujet", ["FINALIZE", "RESEARCH"]))

    assert received["steps"] == ["RESEARCH", "FINALIZE"]


def test_format_live_chunk_shows_the_cooldown_message_when_present():
    chunk = {
        "node": None,
        "status": "aborted",
        "step_count": 0,
        "stop_reason": "cooldown",
        "message": "Patiente encore 10.0s avant un nouveau vrai run.",
    }
    assert "Patiente encore 10.0s" in webapp_app._format_live_chunk(chunk)


def test_on_run_guardrail_returns_the_expected_stop_reason():
    result = webapp_app.on_run_guardrail("budget_exceeded")
    assert result["stop_reason"] == "budget_exceeded"


def test_on_run_live_respects_the_cost_guard(monkeypatch):
    calls = {"n": 0}

    def fake_stream_live(topic, steps, llm=None, max_steps=None):
        calls["n"] += 1
        yield {"node": "researcher", "status": "done", "step_count": 1, "artifacts": {}, "stop_reason": None, "log": []}

    monkeypatch.setattr(webapp_app.runners, "stream_live", fake_stream_live)
    webapp_app._cost_guard._last_call = None  # état propre entre tests

    first_output = list(webapp_app.on_run_live("sujet", ["RESEARCH"]))
    assert calls["n"] == 1
    assert first_output  # au moins un chunk streamé

    second_output = list(webapp_app.on_run_live("sujet", ["RESEARCH"]))
    assert calls["n"] == 1  # pas de second appel réel : le garde-fou de coût a bloqué
    assert second_output[0]["stop_reason"] == "cooldown"
