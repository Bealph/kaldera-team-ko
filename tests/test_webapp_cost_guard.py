"""Verrou de fréquence pour le bouton « vrai LLM » : un seul déclenchement par fenêtre de
cooldown, résiste à un double-clic ou un F5 (l'état vit côté serveur, pas dans le bouton)."""

from __future__ import annotations

from kaldera.webapp.cost_guard import CostGuard


def _clock(*values: float):
    it = iter(values)
    return lambda: next(it)


def test_first_call_is_always_allowed():
    guard = CostGuard(cooldown_seconds=15.0, now=_clock(0.0))
    assert guard.try_acquire() is True


def test_second_call_within_cooldown_is_denied():
    guard = CostGuard(cooldown_seconds=15.0, now=_clock(0.0, 5.0))
    assert guard.try_acquire() is True
    assert guard.try_acquire() is False


def test_call_after_cooldown_elapsed_is_allowed_again():
    guard = CostGuard(cooldown_seconds=15.0, now=_clock(0.0, 20.0))
    assert guard.try_acquire() is True
    assert guard.try_acquire() is True


def test_denied_call_does_not_reset_the_window():
    guard = CostGuard(cooldown_seconds=15.0, now=_clock(0.0, 5.0, 10.0))
    assert guard.try_acquire() is True
    assert guard.try_acquire() is False  # t=5, refusé, ne doit pas repartir de 5
    assert guard.try_acquire() is False  # t=10 : 10-0=10 < 15, encore refusé


def test_seconds_remaining_reports_the_wait():
    guard = CostGuard(cooldown_seconds=15.0, now=_clock(0.0, 5.0))
    guard.try_acquire()
    assert guard.seconds_remaining() == 10.0


def test_seconds_remaining_is_zero_before_first_call():
    guard = CostGuard(cooldown_seconds=15.0, now=_clock(0.0))
    assert guard.seconds_remaining() == 0.0
