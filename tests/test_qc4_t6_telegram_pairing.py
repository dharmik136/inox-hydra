"""
Pairing the phone in one press: the studio learns your chat id from your first message.
======================================================================================

Found on the owner's install on 2026-10-28, the first time the ingress met the
real Telegram service: polling worked and the bot received both of the
owner's messages, and both were refused, because the panel had been saved
with chat id "2" while the owner's chat is a nine-digit number. Telegram
never shows a creator their chat id, and the log said only "Unauthorized
ingress attempt from chat_id: N".

So the bot can be saved with its token alone. While no chat id is saved, every
message is refused, as before, and the ingress remembers the last few chats it
refused, in memory only: the chat id, how many, when, and the first 60
characters of the first message. The panel asks "Is that you?" and "This is
me" saves that chat id through the same save path and its shape check. A
stranger's chat is refused and never paired without the press.

The Telegram side is simulated: requests.get answers from a list, and nothing
reaches the network.

Strict Invariants:
- Zero em-dashes.
"""

import io
import logging
import os
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import ingress  # noqa: E402
import secret_settings  # noqa: E402
from database import get_db  # noqa: E402

TOKEN = "123456789:AAFnotarealkeyZZZZZZZZZZZZZZZZZZZZZZZ"
OWNER = "487215963"          # nine digits, as the owner's chat is
STRANGER = "731004218"
FIRST = "Hello from my phone, this is me trying the studio for the very first time today"


def _read(path):
    with io.open(os.path.join(REPO_ROOT, path), encoding="utf-8") as handle:
        return handle.read()


class _Answer:
    status_code = 200

    def __init__(self, result):
        self._result = result

    def json(self):
        return {"ok": True, "result": self._result}


@pytest.fixture
def studio(tmp_path, monkeypatch):
    """A fresh home and the studio's own worker, its thread never started, Telegram answered from a list."""
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    for name in ("INOX_DEV_MODE", "TELEGRAM_BOT_TOKEN", "PRUDENT_TELEGRAM_BOT_TOKEN",
                 "TELEGRAM_CHAT_ID", "PRUDENT_TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
    daemon = ingress.ingress_daemon
    started = []
    monkeypatch.setattr(daemon, "start_worker", lambda: started.append(True) or setattr(daemon, "is_running", True))
    monkeypatch.setattr(daemon, "stop_worker", lambda: setattr(daemon, "is_running", False))
    for attribute, value in (("bot_token", ""), ("authorized_chat_id", ""), ("configured_from", None),
                             ("profile_id", None), ("is_running", False), ("last_update_id", 0),
                             ("_failed_updates", {}), ("refused_chats", {}), ("total_messages_processed", 0)):
        monkeypatch.setattr(daemon, attribute, value)
    waiting = []
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _Answer(waiting.pop(0) if waiting else [])

    monkeypatch.setattr(ingress.requests, "get", fake_get)
    monkeypatch.setattr(ingress._egress, "require", lambda url, category: None)
    # The bot answers each message (2.11.0): sendMessage is simulated too.
    replies = []

    class Sent:
        status_code = 200

        def json(self):
            return {"ok": True, "result": {"message_id": len(replies)}}

    def fake_post(url, json=None, timeout=None):
        replies.append(json)
        return Sent()

    import telegram_bot
    monkeypatch.setattr(telegram_bot.requests, "post", fake_post)
    from database import init_db
    import app as app_module
    init_db()
    return {"client": TestClient(app_module.app), "daemon": daemon, "started": started, "telegram": waiting,
            "calls": calls, "replies": replies}


def _send(studio, *messages):
    """Telegram holds these messages; the worker asks once, as its loop does."""
    base = studio["daemon"].last_update_id
    studio["telegram"].append([{"update_id": base + n + 1, "message": {"chat": {"id": int(chat), "type": "private"},
                                                                        "text": text}}
                               for n, (chat, text) in enumerate(messages)])
    return studio["daemon"].poll_once()


def _held():
    conn = get_db()
    try:
        return {r["key"]: r["value"] for r in conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE 'telegram%'")}
    finally:
        conn.close()


def _drafts():
    conn = get_db()
    try:
        return [r[0] for r in conn.execute("SELECT raw_content FROM drafts WHERE tags LIKE '%mobile-ingress%'")]
    finally:
        conn.close()


def _everything_stored():
    """Every text value in the database, to show a refused message is kept nowhere."""
    conn = get_db()
    try:
        found = []
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
            for row in conn.execute(f'SELECT * FROM "{table}"'):
                found += [value for value in row if isinstance(value, str)]
        return "\n".join(found)
    finally:
        conn.close()


def _pair_with_token(studio):
    res = studio["client"].post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": ""})
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# Saving the bot before you know your chat id
# ---------------------------------------------------------------------------

def test_a_token_alone_is_kept_and_the_studio_listens_for_your_chat(studio):
    body = _pair_with_token(studio)
    held = _held()
    assert secret_settings.unseal(ingress.SETTINGS_TOKEN_KEY, held[ingress.SETTINGS_TOKEN_KEY]) == TOKEN
    assert ingress.SETTINGS_CHAT_KEY not in held
    assert studio["started"] == [True], "the studio did not start asking Telegram with the token alone"
    assert studio["daemon"].bot_token == TOKEN and studio["daemon"].authorized_chat_id == ""
    assert body["pairing"] is True and body["configured"] is False and body["refused_chats"] == []


def test_your_first_message_is_refused_and_remembered_in_memory_only(studio, caplog):
    _pair_with_token(studio)
    caplog.set_level(logging.DEBUG)
    assert _send(studio, (OWNER, FIRST)) == []
    assert _send(studio, (OWNER, "and a second one")) == []
    assert _drafts() == [], "a message was saved before its chat was paired"
    chats = studio["client"].get("/api/v1/ingress/settings").json()["refused_chats"]
    assert len(chats) == 1
    chat = chats[0]
    assert chat["chat_id"] == OWNER and chat["count"] == 2 and chat["own_chat"] is True
    assert chat["first"] == FIRST[:60] and len(chat["first"]) == 60
    assert chat["first_at"] and chat["last_at"] >= chat["first_at"]
    assert FIRST[:20] not in _everything_stored(), "the refused message was written to the database"
    assert FIRST[:20] not in caplog.text, "the refused message was written to the log"
    assert f"chat_id: {OWNER}" in caplog.text, "the refusal is no longer logged at all"


def test_this_is_me_pairs_that_chat_and_its_next_message_is_saved(studio):
    _pair_with_token(studio)
    _send(studio, (OWNER, FIRST))
    before = studio["client"].get("/api/v1/ingress/settings").json()
    assert before["tested_against_real_service"] is False and before["not_yet_tested"]
    # "This is me": the panel saves the chat id alone; the token held is kept.
    res = studio["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": OWNER})
    assert res.status_code == 200, res.text
    held = _held()
    assert held[ingress.SETTINGS_CHAT_KEY] == OWNER
    assert secret_settings.unseal(ingress.SETTINGS_TOKEN_KEY, held[ingress.SETTINGS_TOKEN_KEY]) == TOKEN
    assert studio["daemon"].authorized_chat_id == OWNER
    body = res.json()
    assert body["configured"] is True and body["pairing"] is False
    assert [c["chat_id"] for c in body["refused_chats"]] == [], "the paired chat is still asked about"
    saved = _send(studio, (OWNER, "Idea: the first post idea from my phone"))
    assert len(saved) == 1 and _drafts() == ["the first post idea from my phone"]
    after = studio["client"].get("/api/v1/ingress/settings").json()
    assert after["tested_against_real_service"] is True
    assert after["not_yet_tested"] is None, "the untested sentence stayed after a message from the paired chat"


def test_the_tested_line_survives_a_restart_and_goes_with_the_chat(studio):
    studio["client"].post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": OWNER})
    _send(studio, (OWNER, "Idea: one"))
    studio["daemon"].refused_chats.clear()
    assert studio["client"].get("/api/v1/ingress/settings").json()["tested_against_real_service"] is True
    studio["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": STRANGER})
    assert studio["client"].get("/api/v1/ingress/settings").json()["tested_against_real_service"] is False, (
        "a message from the chat saved before says nothing about the chat saved now")


def test_a_strangers_chat_is_refused_and_never_paired_without_the_press(studio):
    _pair_with_token(studio)
    _send(studio, (STRANGER, "let me in"), (STRANGER, "please"), (OWNER, FIRST))
    held = _held()
    assert ingress.SETTINGS_CHAT_KEY not in held and studio["daemon"].authorized_chat_id == ""
    chats = {c["chat_id"]: c for c in studio["client"].get("/api/v1/ingress/settings").json()["refused_chats"]}
    assert chats[STRANGER]["count"] == 2 and chats[OWNER]["count"] == 1
    studio["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": OWNER})
    _send(studio, (STRANGER, "Idea: a draft in your studio"))
    assert _drafts() == [], "a stranger's message was saved"
    assert _held()[ingress.SETTINGS_CHAT_KEY] == OWNER
    still = [c["chat_id"] for c in studio["client"].get("/api/v1/ingress/settings").json()["refused_chats"]]
    assert still == [STRANGER]


def test_the_paired_chat_is_the_only_one_that_is_saved(studio):
    """Falsified: with the whitelist skipped, the stranger's message becomes a draft and this fails."""
    studio["client"].post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": OWNER})
    _send(studio, (STRANGER, "Idea: not yours"), (OWNER, "Idea: yours"))
    assert _drafts() == ["yours"]


def test_this_is_me_without_a_token_is_refused_with_a_sentence(studio):
    res = studio["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": OWNER})
    assert res.status_code == 400 and "token" in res.json()["detail"].lower()
    assert _held() == {} and studio["started"] == []


def test_a_groups_chat_is_listed_without_this_is_me_and_cannot_be_saved(studio):
    _pair_with_token(studio)
    _send(studio, ("-100123456789", "hello group"))
    chat = studio["client"].get("/api/v1/ingress/settings").json()["refused_chats"][0]
    assert chat["chat_id"] == "-100123456789" and chat["own_chat"] is False
    res = studio["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": "-100123456789"})
    assert res.status_code == 400 and "group" in res.json()["detail"]
    assert ingress.SETTINGS_CHAT_KEY not in _held()


def test_the_refused_chats_are_few_and_go_with_the_bot(studio):
    _pair_with_token(studio)
    _send(studio, *[(str(700000000 + n), f"message {n}") for n in range(8)])
    chats = studio["client"].get("/api/v1/ingress/settings").json()["refused_chats"]
    assert len(chats) == ingress.REFUSED_CHATS_KEPT
    assert chats[0]["chat_id"] == "700000007", "the newest refused chat is not first"
    studio["client"].post("/api/v1/ingress/settings",
                          json={"bot_token": "222222:" + "B" * 35, "chat_id": ""})
    assert studio["client"].get("/api/v1/ingress/settings").json()["refused_chats"] == [], (
        "another bot's refused chats were offered for this one")


def test_another_profiles_bot_shows_no_refused_chats_here(studio):
    _pair_with_token(studio)
    _send(studio, (OWNER, FIRST))
    studio["daemon"].profile_id = "another-profile"
    assert studio["client"].get("/api/v1/ingress/settings").json()["refused_chats"] == []


# ---------------------------------------------------------------------------
# What the creator reads
# ---------------------------------------------------------------------------

def test_the_panel_asks_is_that_you_and_offers_this_is_me():
    panel = _read("studio/ui/src/components/TelegramIngressPanel.tsx")
    assert "refused_chats" in panel and "Is that you?" in panel and "This is me" in panel
    assert "not_yet_tested" in panel


def test_the_help_says_to_pair_by_pressing_this_is_me_and_when_it_was_tested():
    article = " ".join(_read("docs/help/send-a-post-idea-from-telegram.md").split())
    assert "This is me" in article and "message the bot once" in article.lower()
    assert "tested against the real Telegram service on 2026-10-28" in article
    assert "has not yet been tested against the real Telegram service" not in article
