"""Étapes métier du flux Kaldera et résolution depuis les scénarios."""

from __future__ import annotations

from enum import Enum


class Step(str, Enum):
    RESEARCH = "RESEARCH"
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    FINALIZE = "FINALIZE"


# Les libellés des scénarios sont exactement les noms de la spécification : la table se
# déduit de l'énumération, sans seconde déclaration qui pourrait diverger.
STEP_BY_NAME: dict[str, Step] = {step.value: step for step in Step}


def step_from_name(name: str) -> Step:
    return STEP_BY_NAME[name]
