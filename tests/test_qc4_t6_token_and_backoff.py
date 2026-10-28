"""
The Bot Token Stays Out of the Ledger, and an Error Answer Is Backed Off From.
==============================================================================

Two faults in the Telegram worker, found while building the bot's replies
(cycle 4, track 6) and carried back to 2.10.2 in their smallest form.

The egress ledger kept each request's address as its category's last
destination, and the Bot API carries the token in the address's path
(/bot<token>/getUpdates). public_destination() strips a query and a
user:password@ prefix but keeps the path, so after the first poll the Local
security tab and /api/v1/egress/status showed the whole token. The poll is
now counted under the address with the token masked; the request itself
still carries it.

An answer from Telegram that was an error (401 for a token it does not
know, 409 when a second program asks for the same bot, a 5xx) returned
normally, so the loop took the success path and asked again two seconds
later, forever. It now backs off as from a network fault.

Runs nothing on the network: requests.get is replaced by a fake.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import egress  # noqa: E402
import ingress  # noqa: E402

TOKEN = "123456789:AAFnotarealkeyQQQQQQQQQQQQQQQQQQQQQQQ"
SECRET_HALF = TOKEN.split(":", 1)[1]
CHAT = "555000111"


class _Answer:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {"ok": True, "result": []}
        self.text = str(self._body)

    def json(self):
        return self._body


@pytest.fixture
def telegram(monkeypatch):
    """getUpdates answered by `answer`, nothing on the network, the ledger counting for real."""
    monkeypatch.delenv(egress.MASTER_OFF_FLAG, raising=False)
    monkeypatch.setenv("INOX_ALLOW_INGRESS_EGRESS", "1")
    egress.reset_for_tests()
    state = {"answer": _Answer(), "urls": []}
    lock = threading.Lock()

    def fake_get(url, params=None, timeout=None):
        with lock:
            state["urls"].append(url)
        return state["answer"]

    monkeypatch.setattr(ingress.requests, "get", fake_get)
    yield state
    egress.reset_for_tests()


def _ingress_row():
    return next(c for c in egress.describe()["categories"] if c["name"] == "ingress")


def test_a_poll_is_counted_in_the_ledger_without_the_token(telegram, tmp_path, monkeypatch):
    daemon = ingress.TelegramIngressDaemon(bot_token=TOKEN, authorized_chat_id=CHAT)
    daemon.poll_once()

    assert telegram["urls"] == [f"https://api.telegram.org/bot{TOKEN}/getUpdates"], (
        "the request itself must still carry the token")
    row = _ingress_row()
    assert row["performed"] == 1
    assert row["last_destination"] == "https://api.telegram.org/bot<token>/getUpdates"
    ledger = repr(egress.describe())
    assert TOKEN not in ledger and SECRET_HALF not in ledger, "the bot's token is in the egress ledger"

    # What the Local security tab reads.
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    from database import init_db
    import app as app_module
    init_db()
    shown = TestClient(app_module.app).get("/api/v1/egress/status").text
    assert SECRET_HALF not in shown, "/api/v1/egress/status shows the bot's token"


def test_a_refused_poll_is_recorded_without_the_token_too(telegram, monkeypatch):
    monkeypatch.setenv("INOX_ALLOW_INGRESS_EGRESS", "0")
    daemon = ingress.TelegramIngressDaemon(bot_token=TOKEN, authorized_chat_id=CHAT)
    with pytest.raises(egress.EgressRefused):
        daemon.poll_once()
    assert telegram["urls"] == [], "a refused poll reached Telegram"
    assert _ingress_row()["refused"] == 1
    assert SECRET_HALF not in repr(egress.describe())


@pytest.mark.parametrize("answer", [
    _Answer(401, {"ok": False, "error_code": 401, "description": "Unauthorized"}),
    _Answer(409, {"ok": False, "error_code": 409, "description": "Conflict: terminated by other getUpdates request"}),
    _Answer(502, {"ok": False, "error_code": 502, "description": "Bad Gateway"}),
    _Answer(200, {"ok": False, "description": "Telegram said no"}),
], ids=["401", "409", "502", "ok-false"])
def test_an_error_answer_marks_the_poll_failed_and_a_good_one_clears_it(telegram, answer):
    daemon = ingress.TelegramIngressDaemon(bot_token=TOKEN, authorized_chat_id=CHAT)
    telegram["answer"] = answer
    assert daemon.poll_once() == []
    assert daemon.poll_failed is True
    assert SECRET_HALF not in (daemon.last_error or "")
    telegram["answer"] = _Answer()
    daemon.poll_once()
    assert daemon.poll_failed is False and daemon.last_error is None


def test_the_worker_backs_off_from_a_token_telegram_does_not_know(telegram):
    """
    Counted, not timed: a backed-off loop climbs consecutive_errors, and the
    success path resets it to zero on every poll, which is what a 401 used
    to take.
    """
    telegram["answer"] = _Answer(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})
    daemon = ingress.TelegramIngressDaemon(bot_token=TOKEN, authorized_chat_id=CHAT)
    daemon.base_delay = 0.01
    daemon.start_worker()
    try:
        deadline = time.monotonic() + 20.0
        while len(telegram["urls"]) < 4 and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        daemon.stop_worker()
    assert len(telegram["urls"]) >= 4, "the worker did not poll"
    assert daemon.consecutive_errors >= 3, (
        "a 401 was taken as a good poll, so the worker asked Telegram again at the base delay")
    assert daemon.current_delay > daemon.base_delay
