"""Point d'entrée : rejoue les scénarios fournis et affiche le résultat."""

from __future__ import annotations

import json
from pathlib import Path

from .runner import run_scenario

SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios" / "scenarios_test.json"


def main() -> None:
    data = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    for scenario in data["scenarios"]:
        state = run_scenario(scenario)
        print(
            f"[{scenario['id']}] status={state.status} "
            f"steps={state.step_count} artifacts={sorted(state.artifacts)}"
            + (f" stop_reason={state.stop_reason}" if state.stop_reason else "")
        )


if __name__ == "__main__":
    main()
