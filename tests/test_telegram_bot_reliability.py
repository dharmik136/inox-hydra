"""
Reliability and what the panel says: a test message, plain words, quiet logs.
=============================================================================

"Send a test message" in the Telegram panel sends one fixed sentence to the
paired chat at once and says whether Telegram took it. The panel's last
problem reaching Telegram is said in plain words: a token Telegram does not
know, a second program asking for the same bot, no connection, a rate limit.
No message's words reach a log line, and neither does the token.

Driven end to end against the fake Bot API (tests/telegram_fake.py); the
backoff on 429 and on network faults, and an update never confirmed before
it is handled, are in tests/test_telegram_bot_e2e.py and
tests/test_telegram_bot_replies.py.

Strict Invariants:
- Zero em-dashes.
"""

import logging
import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import ingress  # noqa: E402
import telegram_bot  # noqa: E402
from test_telegram_bot_e2e import OWNER, STRANGER, TOKEN, _drafts, _save, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved  # noqa: E402

SAID = telegram_bot.SENTENCES


def _settings(bot):
    return bot["client"].get("/api/v1/ingress/settings").json()


def test_the_test_message_goes_to_the_paired_chat_and_says_it_was_taken(bot):
    _saved(bot)
    res = bot["client"].post("/api/v1/ingress/test-message")
    assert res.status_code == 200, res.text
    assert res.json()["sent"] is True and "phone" in res.json()["said"]
    assert [m["text"] for m in bot["fake"].sent if m["chat_id"] == OWNER][-1] == SAID["test"]


def test_the_test_message_needs_a_paired_chat(bot):
    bot["client"].post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": ""})
    res = bot["client"].post("/api/v1/ingress/test-message")
    assert res.status_code == 200 and res.json()["sent"] is False
    assert "This is me" in res.json()["said"]
    assert bot["fake"].calls_of("sendMessage") == []


def test_a_test_message_telegram_refuses_says_why_in_plain_words(bot):
    _saved(bot)
    bot["fake"].blocked_chats.add(OWNER)
    answer = bot["client"].post("/api/v1/ingress/test-message").json()
    assert answer["sent"] is False and "blocked" in answer["said"] and TOKEN not in answer["said"]


def test_a_test_message_with_egress_off_is_refused_here_and_never_sent(bot, monkeypatch):
    _saved(bot)
    before = len(bot["fake"].calls_of("sendMessage"))
    monkeypatch.setenv("INOX_ALLOW_INGRESS_EGRESS", "0")
    answer = bot["client"].post("/api/v1/ingress/test-message").json()
    assert answer["sent"] is False and answer["said"] == telegram_bot.EGRESS_OFF
    assert len(bot["fake"].calls_of("sendMessage")) == before


@pytest.mark.parametrize("failure, words", [
    (("status", 409, "Conflict: terminated by other getUpdates request"), "Another program is asking Telegram"),
    (("status", 502, "Bad Gateway"), "Telegram's service answered with an error"),
    (("drop",), "could not reach Telegram"),
])
def test_the_last_problem_is_said_in_plain_words(bot, failure, words):
    bot["fake"].plan("getUpdates", *([failure] * 30))
    _save(bot)
    assert _until(lambda: words in (_settings(bot).get("last_error") or "")), _settings(bot).get("last_error")
    assert TOKEN not in _settings(bot)["last_error"] and "/bot" not in _settings(bot)["last_error"]


def test_a_token_telegram_does_not_know_is_said_in_plain_words(bot):
    res = bot["client"].post("/api/v1/ingress/settings",
                             json={"bot_token": "222222222:" + "B" * 35, "chat_id": OWNER})
    assert res.status_code == 200
    assert _until(lambda: "does not recognise this bot's token" in (_settings(bot).get("last_error") or ""))


def test_no_message_words_and_no_token_reach_the_logs(bot, caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    for name in ("studio.ingress", "studio.telegram"):
        caplog.set_level(logging.DEBUG, logger=name)
    _saved(bot)
    bot["fake"].push(OWNER, "Idea: a private thought about Acme pricing")
    bot["fake"].push(STRANGER, "a stranger's private words")
    assert _until(lambda: _drafts() == ["a private thought about Acme pricing"])

    def failing(*args, **kwargs):
        raise ValueError("could not store: a secret plan for Zenith")

    monkeypatch.setattr(ingress, "create_draft", failing)
    bot["fake"].push(OWNER, "Idea: a secret plan for Zenith")
    assert _until(lambda: bot["fake"].waiting() == [], timeout=10.0)
    for private in ("Acme", "stranger's private", "Zenith", TOKEN, TOKEN.split(":")[1]):
        assert private not in caplog.text, f"{private!r} reached the logs"
    assert f"chat_id: {STRANGER}" in caplog.text, "the refusal is no longer logged at all"


def test_the_panel_has_the_test_message_button():
    panel = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "TelegramIngressPanel.tsx"),
                 encoding="utf-8").read()
    assert "Send a test message" in panel and "sendIngressTestMessage" in panel


def test_an_error_answer_is_backed_off_from_like_a_network_fault(bot):
    """A 409 or a 502 used to count as a good poll, so the worker asked again every two seconds."""
    bot["fake"].plan("getUpdates", *([("status", 409, "Conflict: terminated by other getUpdates request")] * 6))
    _save(bot)
    assert _until(lambda: len(bot["fake"].calls_of("getUpdates")) >= 4, timeout=8.0)
    calls = bot["fake"].calls_of("getUpdates")
    gaps = [b["at"] - a["at"] for a, b in zip(calls, calls[1:4])]
    assert gaps[2] > gaps[0] * 1.5, f"the wait after repeated errors did not grow: {gaps}"
