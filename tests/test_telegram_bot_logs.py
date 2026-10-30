"""
One log line per failed check, and a timed-out long poll is a warning (phase 4, item 12).
=========================================================================================

A failed check was logged twice: "Polling error" by the check itself, then
"Worker loop error" by the loop around it. And a long poll that timed out
while Wi-Fi reconnected (hourly on the owner's machine), or a connection that
dropped, was logged as an error. Now each failed check is one line; a network
fault (a read timeout, a dropped or refused connection) is a warning, and
anything else an error. The token is never in a line.

docs/quality/cycle4/bot-phase4.md, item 12. Against the fake Bot API, which
drops a connection when told to, and a read timeout raised where requests
raises one.

Strict Invariants:
- Zero em-dashes.
"""

import logging
import os
import sys

import requests

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import ingress  # noqa: E402
from test_telegram_bot_e2e import TOKEN, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved  # noqa: E402


def _check_lines(caplog):
    """What the worker logged about failed checks: its own two phrasings, one record each."""
    return [r for r in caplog.records if r.name == "studio.ingress"
            and ("Polling error" in r.getMessage() or "Worker loop error" in r.getMessage()
                 or "check of Telegram" in r.getMessage())]


def test_a_dropped_connection_is_one_warning(bot, caplog):
    caplog.set_level(logging.INFO, logger="studio.ingress")
    _saved(bot)
    polls = len(bot["fake"].calls_of("getUpdates"))
    bot["fake"].plan("getUpdates", ("drop",))
    assert _until(lambda: len(bot["fake"].calls_of("getUpdates")) >= polls + 3)
    lines = _check_lines(caplog)
    assert len(lines) == 1, [r.getMessage() for r in lines]
    assert lines[0].levelno == logging.WARNING
    assert TOKEN not in caplog.text and TOKEN.split(":")[1] not in caplog.text


def test_a_long_poll_that_timed_out_is_one_warning_without_the_token(bot, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="studio.ingress")
    _saved(bot)
    real = ingress.requests.get
    timed_out = []

    def once(url, *args, **kwargs):
        if not timed_out and "getUpdates" in url:
            timed_out.append(True)
            raise requests.exceptions.ReadTimeout(
                f"HTTPSConnectionPool(host='api.telegram.org', port=443): Read timed out. "
                f"(read timeout=35) /bot{TOKEN}/getUpdates")
        return real(url, *args, **kwargs)

    monkeypatch.setattr(ingress.requests, "get", once)
    assert _until(lambda: timed_out and len(_check_lines(caplog)) >= 1)
    polls = len(bot["fake"].calls_of("getUpdates"))
    assert _until(lambda: len(bot["fake"].calls_of("getUpdates")) >= polls + 2)
    lines = _check_lines(caplog)
    assert len(lines) == 1, [r.getMessage() for r in lines]
    assert lines[0].levelno == logging.WARNING
    assert TOKEN not in caplog.text and "<redacted>" in caplog.text


def test_anything_else_is_one_error(bot, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="studio.ingress")
    _saved(bot)
    real = ingress.requests.get
    failed = []

    def once(url, *args, **kwargs):
        if not failed and "getUpdates" in url:
            failed.append(True)
            raise RuntimeError(f"something unexpected at /bot{TOKEN}/getUpdates")
        return real(url, *args, **kwargs)

    monkeypatch.setattr(ingress.requests, "get", once)
    assert _until(lambda: failed and len(_check_lines(caplog)) >= 1)
    polls = len(bot["fake"].calls_of("getUpdates"))
    assert _until(lambda: len(bot["fake"].calls_of("getUpdates")) >= polls + 2)
    lines = _check_lines(caplog)
    assert len(lines) == 1, [r.getMessage() for r in lines]
    assert lines[0].levelno == logging.ERROR
    assert TOKEN not in caplog.text
