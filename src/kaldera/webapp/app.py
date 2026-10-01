"""GUI Gradio : 3 onglets (Exécuter / Casser un garde-fou / Comparer). Un seul opérateur en
projection (pas d'auth, pas d'isolation de session — décidé au brainstorming du 30/09/2026)."""

from __future__ import annotations

from collections.abc import Iterator

import gradio as gr  # type: ignore[import-untyped]

from . import runners
from .broken_registries import DEFECTS
from .cost_guard import CostGuard

STEPS_CHOICES = ["RESEARCH", "DRAFT", "REVIEW", "FINALIZE"]
GUARDRAIL_LABELS = {
    "role_violation": "Rôle hors périmètre",
    "budget_exceeded": "Budget de tokens dépassé",
    "step_limit": "Limite d'étapes atteinte",
    "stuck_agent": "Agent bloqué (ne progresse pas)",
}

_cost_guard = CostGuard()


def _canonical_order(steps: list[str]) -> list[str]:
    # `gr.CheckboxGroup` renvoie les valeurs cochées dans l'ordre des clics, pas dans l'ordre
    # d'affichage des cases : une re-coche après décoche peut légitimement produire
    # ["FINALIZE", "RESEARCH"] alors que le formulaire affiche toujours RESEARCH avant FINALIZE.
    return [s for s in STEPS_CHOICES if s in steps]


def on_run_deterministic(topic: str, steps: list[str]) -> dict:
    return runners.run_deterministic(topic, _canonical_order(steps))


def on_run_scenario(scenario_id: str) -> dict:
    return runners.run_named_scenario(scenario_id)


def on_run_guardrail(defect: str) -> dict:
    return runners.run_guardrail(defect)


def on_run_live(topic: str, steps: list[str]) -> Iterator[dict]:
    if not _cost_guard.try_acquire():
        wait = round(_cost_guard.seconds_remaining(), 1)
        yield {
            "node": None,
            "status": "aborted",
            "step_count": 0,
            "artifacts": {},
            "stop_reason": "cooldown",
            "log": [],
            "message": f"Patiente encore {wait}s avant un nouveau vrai run.",
        }
        return
    yield from runners.stream_live(topic, _canonical_order(steps))


def _format_summary(result: dict) -> str:
    lines = [f"statut : {result['status']}", f"étapes : {result['step_count']}"]
    if result.get("stop_reason"):
        lines.append(f"stop_reason : {result['stop_reason']}")
    return "\n".join(lines)


def _format_live_chunk(chunk: dict) -> str:
    node = chunk.get("node") or "—"
    parts = [f"[{node}] statut={chunk['status']} étapes={chunk['step_count']}"]
    if chunk.get("stop_reason"):
        parts.append(f"stop_reason={chunk['stop_reason']}")
    if chunk.get("message"):
        parts.append(chunk["message"])
    return " ".join(parts)


def _run_deterministic_ui(topic: str, steps: list[str]) -> tuple[str, dict]:
    result = on_run_deterministic(topic, steps)
    return _format_summary(result), result["artifacts"]


def _run_scenario_ui(scenario_id: str) -> tuple[str, dict]:
    result = on_run_scenario(scenario_id)
    return _format_summary(result), result["artifacts"]


def _run_live_ui(topic: str, steps: list[str]):
    log_lines: list[str] = []
    artifacts: dict = {}
    for chunk in on_run_live(topic, steps):
        log_lines.append(_format_live_chunk(chunk))
        artifacts = chunk.get("artifacts", artifacts)
        yield "\n".join(log_lines), artifacts


def _run_guardrail_ui(defect: str) -> str:
    result = on_run_guardrail(defect)
    return _format_summary(result) + "\n\njournal :\n" + "\n".join(
        f"- {entry['agent_id']} : {entry['message']}" for entry in result["log"]
    )


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Kaldera — démo") as demo:
        gr.Markdown("# Kaldera — orchestration multi-agents, en direct")

        with gr.Tab("Exécuter"):
            topic_box = gr.Textbox(label="Sujet", value="lancement produit")
            steps_box = gr.CheckboxGroup(choices=STEPS_CHOICES, value=STEPS_CHOICES, label="Étapes")
            with gr.Row():
                det_button = gr.Button("Lancer (déterministe)")
                live_button = gr.Button("Lancer (vrai LLM)")

            scenario_ids = [s["id"] for s in runners.load_scenarios()]
            with gr.Row():
                scenario_dropdown = gr.Dropdown(
                    choices=scenario_ids,
                    value=scenario_ids[0] if scenario_ids else None,
                    label="Scénario prédéfini (scenarios/scenarios_test.json)",
                )
                scenario_button = gr.Button("Lancer le scénario")

            output_log = gr.Textbox(label="Déroulé", lines=10)
            output_artifacts = gr.JSON(label="Artefacts")

            det_button.click(_run_deterministic_ui, [topic_box, steps_box], [output_log, output_artifacts])
            live_button.click(_run_live_ui, [topic_box, steps_box], [output_log, output_artifacts])
            scenario_button.click(_run_scenario_ui, [scenario_dropdown], [output_log, output_artifacts])

        with gr.Tab("Casser un garde-fou"):
            gr.Markdown("Toujours déterministe : gratuit, instantané, rejouable à l'infini.")
            guardrail_output = gr.Textbox(label="Résultat", lines=12)
            for defect in DEFECTS:
                button = gr.Button(GUARDRAIL_LABELS[defect])
                button.click(lambda d=defect: _run_guardrail_ui(d), outputs=guardrail_output)

        with gr.Tab("Comparer"):
            cmp_topic = gr.Textbox(label="Sujet", value="lancement produit")
            cmp_steps = gr.CheckboxGroup(choices=STEPS_CHOICES, value=STEPS_CHOICES, label="Étapes")
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Déterministe")
                    cmp_det_button = gr.Button("Lancer")
                    cmp_det_output = gr.Textbox(label="Déroulé", lines=10)
                    cmp_det_artifacts = gr.JSON(label="Artefacts")
                with gr.Column():
                    gr.Markdown("### Vrai LLM")
                    cmp_live_button = gr.Button("Lancer")
                    cmp_live_output = gr.Textbox(label="Déroulé", lines=10)
                    cmp_live_artifacts = gr.JSON(label="Artefacts")

            cmp_det_button.click(_run_deterministic_ui, [cmp_topic, cmp_steps], [cmp_det_output, cmp_det_artifacts])
            cmp_live_button.click(_run_live_ui, [cmp_topic, cmp_steps], [cmp_live_output, cmp_live_artifacts])

    return demo


def main() -> None:
    build_app().launch(server_name="0.0.0.0", server_port=7860)


if __name__ == "__main__":
    main()
