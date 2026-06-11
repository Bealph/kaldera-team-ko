"""Étapes métier du flux Kaldera et résolution depuis les scénarios."""
from __future__ import annotations

from enum import Enum


class Step(str, Enum):
    RESEARCH = "RESEARCH"
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    FINALIZE = "FINALIZE"


# Correspondance entre les libellés employés dans les scénarios et les membres
# de l'énumération.
STEP_BY_NAME: dict[str, Step] = {
    "RESEARCH": Step.RESEARCH,
    "DRAFT": Step.DRAFT,
    "PROOFREAD": Step.REVIEW,
    "FINALIZE": Step.FINALIZE,
}


def step_from_name(name: str) -> Step:
    return STEP_BY_NAME[name]
