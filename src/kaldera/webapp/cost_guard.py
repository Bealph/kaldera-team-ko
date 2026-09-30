"""Garde-fou de coût : impose un délai minimal entre deux vrais appels LLM déclenchés depuis la
GUI. L'état vit côté serveur (pas dans l'état du bouton) : résiste à un double-clic ou un F5."""

from __future__ import annotations

import time
from collections.abc import Callable

DEFAULT_COOLDOWN_SECONDS = 15.0


class CostGuard:
    def __init__(
        self,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cooldown = cooldown_seconds
        self._now = now
        self._last_call: float | None = None

    def try_acquire(self) -> bool:
        current = self._now()
        if self._last_call is not None and current - self._last_call < self._cooldown:
            return False
        self._last_call = current
        return True

    def seconds_remaining(self) -> float:
        if self._last_call is None:
            return 0.0
        return max(0.0, self._cooldown - (self._now() - self._last_call))
