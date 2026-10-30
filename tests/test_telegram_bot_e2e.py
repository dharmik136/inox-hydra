"""
The Telegram bot, end to end, against a fake Bot API on loopback.
================================================================

The studio's own worker runs as it does at home: the bot is saved through
the Local security panel's route, which starts the real polling loop; the
loop asks the fake (tests/telegram_fake.py) for updates over HTTP, through
the egress check, and the messages land in the database. Telegram's
failures are planned on the fake: a 429 with retry_after, a dropped
connection, a store that fails. Nothing reaches the network.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import ingress  # noqa: E402
import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from telegram_fake import FakeTelegram  # noqa: E402

TOKEN = "123456789:AAFnotarealkeyZZZZZZZZZZZZZZZZZZZZZZZ"
OWNER = "487215963"
STRANGER = "731004218"


@pytest.fixture
def bot(tmp_path, monkeypatch):
    """A fresh home, the fake Bot API, and the studio's own worker pointed at it."""
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    for name in ("INOX_DEV_MODE", "TELEGRAM_BOT_TOKEN", "PRUDENT_TELEGRAM_BOT_TOKEN",
                 "TELEGRAM_CHAT_ID", "PRUDENT_TELEGRAM_CHAT_ID", "INOX_NO_EGRESS", "INOX_ALLOW_INGRESS_EGRESS"):
        monkeypatch.delenv(name, raising=False)
    fake = FakeTelegram(TOKEN).start()
    monkeypatch.setattr(telegram_bot, "API_BASE", fake.url)
    daemon = ingress.ingress_daemon
    daemon.stop_worker()
    for attribute, value in (("bot_token", ""), ("authorized_chat_id", ""), ("configured_from", None),
                             ("profile_id", None), ("is_running", False), ("last_update_id", 0),
                             ("_failed_updates", {}), ("refused_chats", {}), ("total_messages_processed", 0),
                             ("consecutive_errors", 0), ("rate_limited_until", 0.0), ("last_error", None),
                             ("base_delay", 0.05), ("max_delay", 2.0)):
        monkeypatch.setattr(daemon, attribute, value)
    monkeypatch.setattr(daemon, "is_quiet_hours", lambda current_time=None: False)
    from database import init_db
    import app as app_module
    init_db()
    client = TestClient(app_module.app)
    yield {"client": client, "fake": fake, "daemon": daemon}
    daemon.stop_worker()
    thread = daemon._thread
    if thread is not None:
        thread.join(3)
    fake.stop()


def _save(bot, chat=OWNER):
    res = bot["client"].post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": chat})
    assert res.status_code == 200, res.text
    assert bot["daemon"].is_running, "saving the bot did not start the studio's worker"


def _drafts():
    conn = get_db()
    try:
        return [r[0] for r in conn.execute("SELECT raw_content FROM drafts WHERE tags LIKE '%mobile-ingress%' ORDER BY id")]
    finally:
        conn.close()


def _collected():
    """What the paired chat's messages became: since phase 3, items in the collection."""
    conn = get_db()
    try:
        return [r[0] for r in conn.execute("SELECT text FROM collection_items ORDER BY id")]
    finally:
        conn.close()


def _until(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_a_message_from_the_paired_chat_is_saved_and_then_confirmed(bot):
    _save(bot)
    bot["fake"].push(OWNER, "Idea: the first post idea from my phone")
    assert _until(lambda: _collected() == ["the first post idea from my phone"]), "the message was never collected"
    # Confirmed by the next poll's offset, after it was handled: Telegram then never sends it again.
    assert _until(lambda: bot["fake"].waiting() == []), "the handled update was never confirmed"


def test_a_strangers_message_is_refused_end_to_end(bot):
    _save(bot)
    bot["fake"].push(STRANGER, "Idea: let me in")
    assert _until(lambda: bot["fake"].waiting() == [])
    assert _drafts() == [] and _collected() == []
    chats = bot["client"].get("/api/v1/ingress/settings").json()["refused_chats"]
    assert [c["chat_id"] for c in chats] == [STRANGER]


def test_an_update_is_never_confirmed_before_it_is_handled(bot, monkeypatch):
    """A store that fails leaves the update with Telegram, asked again, then stepped over after three tries."""
    attempts = []

    def failing(*args, **kwargs):
        attempts.append(True)
        raise RuntimeError("the disk is full")

    monkeypatch.setattr(ingress.collection, "add", failing)
    _save(bot)
    update = bot["fake"].push(OWNER, "Idea: will not fit")
    assert _until(lambda: len(attempts) >= 1)
    offsets = [int(c["params"].get("offset", 0)) for c in bot["fake"].calls_of("getUpdates")]
    assert update in bot["fake"].waiting() or len(attempts) >= ingress.MAX_UPDATE_ATTEMPTS
    assert _until(lambda: len(attempts) >= ingress.MAX_UPDATE_ATTEMPTS), "a failed update was not asked for again"
    assert _until(lambda: bot["fake"].waiting() == []), "an update that can never be stored blocked the queue"
    offsets = [int(c["params"].get("offset", 0)) for c in bot["fake"].calls_of("getUpdates")]
    assert offsets.count(update) >= ingress.MAX_UPDATE_ATTEMPTS - 1, (
        "the update was confirmed before it was handled: " + repr(offsets))


def test_a_429_is_waited_out_for_as_long_as_telegram_asked(bot):
    bot["fake"].plan("getUpdates", ("429", 1))
    _save(bot)
    assert _until(lambda: len(bot["fake"].calls_of("getUpdates")) >= 2, timeout=6.0)
    first, second = bot["fake"].calls_of("getUpdates")[:2]
    assert second["at"] - first["at"] >= 0.9, "the worker asked again before Telegram's retry_after had passed"
    bot["fake"].push(OWNER, "Idea: after the wait")
    assert _until(lambda: _collected() == ["after the wait"])


def test_a_dropped_connection_is_retried_with_backoff_and_recovers(bot, monkeypatch):
    # A base wait whose doubling outgrows a slow runner's jitter: at 0.05 s the
    # 0.1 s of growth was lost in macOS's noise on CI.
    monkeypatch.setattr(bot["daemon"], "base_delay", 0.25)
    bot["fake"].plan("getUpdates", ("drop",), ("drop",))
    _save(bot)
    assert _until(lambda: len(bot["fake"].calls_of("getUpdates")) >= 3, timeout=6.0)
    calls = bot["fake"].calls_of("getUpdates")
    gaps = [b["at"] - a["at"] for a, b in zip(calls, calls[1:3])]
    assert gaps[1] > gaps[0], f"the wait after a second failure did not grow: {gaps}"
    bot["fake"].push(OWNER, "Idea: back online")
    assert _until(lambda: _collected() == ["back online"]), "the worker did not recover after the network came back"


def test_the_token_never_reaches_the_egress_ledger(bot):
    """
    Found while building the replies: the ledger kept each request's address
    as its last destination, and a Bot API address carries the bot's token in
    its path, so Local security showed the token after the first poll.
    """
    import egress
    _save(bot)
    bot["fake"].push(OWNER, "Idea: counted, not shown")
    assert _until(lambda: _collected() == ["counted, not shown"])
    assert _until(lambda: len(bot["fake"].calls_of("sendMessage")) >= 1)
    ledger = repr(egress.describe())
    assert TOKEN not in ledger and TOKEN.split(":")[1] not in ledger, "the bot's token is in the egress ledger"
    shown = bot["client"].get("/api/v1/egress/status").text
    assert TOKEN.split(":")[1] not in shown
    ingress_row = next(c for c in egress.describe()["categories"] if c["name"] == "ingress")
    assert ingress_row["performed"] >= 2 and "/bot" in (ingress_row["last_destination"] or "")
