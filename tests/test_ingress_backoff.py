"""
A Telegram 429 is an instruction, not an error to be forgotten.
===============================================================

poll_once computed the backoff and returned normally. The worker loop
therefore saw no exception, called calculate_next_poll_interval(has_error=
False), which reset consecutive_errors and overwrote current_delay with
base_delay. The daemon re-polled two seconds later while last_error read
"backing off 25.0s", which escalates the rate limit it claims to respect.

The wait is now a deadline on the monotonic clock, held separately from the
error ladder, and checked before every other branch including quiet hours.
Nothing below is allowed to shorten it.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import ingress
from ingress import TelegramIngressDaemon


class _Response:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


@pytest.fixture
def daemon(monkeypatch):
    return TelegramIngressDaemon(bot_token="probe-token", authorized_chat_id="1")


def _respond(monkeypatch, response):
    monkeypatch.setattr(ingress.requests, "get", lambda *a, **k: response)


def test_the_loop_waits_the_period_telegram_asked_for(monkeypatch, daemon):
    """
    The reported case. Telegram says 25 seconds; the loop used to wait 2.
    """
    _respond(monkeypatch, _Response(429, {"ok": False, "parameters": {"retry_after": 25}}))
    daemon.poll_once()

    # Exactly what start_worker does on the next iteration.
    waited = daemon.calculate_next_poll_interval(has_error=False)

    assert waited >= 24.0, (
        f"the worker would re-poll in {waited:.1f}s against an active rate "
        f"limit that asked for 25s"
    )


def test_the_reported_delay_matches_the_delay_actually_used(monkeypatch, daemon):
    """last_error claimed a backoff the daemon was not taking."""
    _respond(monkeypatch, _Response(429, {"ok": False, "parameters": {"retry_after": 30}}))
    daemon.poll_once()

    assert "30.0s" in daemon.last_error
    assert daemon.calculate_next_poll_interval(has_error=False) >= 29.0


def test_quiet_hours_cannot_shorten_a_rate_limit(monkeypatch, daemon):
    """
    Quiet hours lengthen the interval, so they are harmless here, but the
    ordering matters: the rate limit is checked first so no later branch can
    overwrite current_delay with something shorter.
    """
    _respond(monkeypatch, _Response(429, {"ok": False, "parameters": {"retry_after": 45}}))
    daemon.poll_once()

    monkeypatch.setattr(daemon, "is_quiet_hours", lambda *a, **k: True)
    assert daemon.calculate_next_poll_interval(has_error=False) >= 44.0


def test_a_429_without_a_retry_after_engages_the_ladder(monkeypatch, daemon):
    """
    Nothing told us how long to wait, which is the one case where doubling is
    the right answer. Previously consecutive_errors was never incremented by a
    429 at all, so the ladder never engaged.
    """
    _respond(monkeypatch, _Response(429, {"ok": False}))

    delays = []
    for _ in range(4):
        daemon.poll_once()
        delays.append(daemon.calculate_next_poll_interval(has_error=False))
        daemon.rate_limited_until = 0.0   # stand in for the wait elapsing

    assert delays == sorted(delays), f"the ladder did not increase: {delays}"
    assert delays[-1] > delays[0] * 2, f"backoff barely moved: {delays}"


def test_a_successful_poll_clears_the_limit(monkeypatch, daemon):
    """
    Once the window passes, normal pacing resumes rather than sticking.

    Quiet hours are pinned off. They also lengthen the interval, so leaving
    them live made this assertion depend on what time the suite ran: it passed
    in the afternoon and failed at 23:00 against a quiet_delay of 120s, which
    is correct behaviour and nothing to do with rate limiting.
    """
    monkeypatch.setattr(daemon, "is_quiet_hours", lambda *a, **k: False)

    _respond(monkeypatch, _Response(429, {"ok": False, "parameters": {"retry_after": 20}}))
    daemon.poll_once()

    daemon.rate_limited_until = 0.0
    _respond(monkeypatch, _Response(200, {"ok": True, "result": []}))
    daemon.poll_once()

    assert daemon.calculate_next_poll_interval(has_error=False) == daemon.base_delay


def test_a_malformed_429_body_still_backs_off(monkeypatch, daemon):
    """A response whose JSON cannot be read must not fall through to 2s."""
    class Broken(_Response):
        def json(self):
            raise ValueError("not json")

    _respond(monkeypatch, Broken(429))
    daemon.poll_once()

    assert daemon.calculate_next_poll_interval(has_error=False) > daemon.base_delay
