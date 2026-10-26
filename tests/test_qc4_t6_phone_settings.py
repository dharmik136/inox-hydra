"""
Decision D6: the Telegram ingress leaves dev mode behind a Settings surface.
===========================================================================

The bot token is sealed like the AI key, never answered back, and the
worker starts only when both the token and the chat id are set in the
profile. The help and the panel say plainly that this has not yet been
tested against the real Telegram service, and that the phone sends a link,
never a figure.

Strict Invariants:
- Zero em-dashes.
- Nothing reaches Telegram: the worker's start is recorded, not run.
"""

import io
import os
import re
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import ingress  # noqa: E402
import secret_settings  # noqa: E402
from database import get_db  # noqa: E402

TOKEN = "123456789:AAFnotarealkeyZZZZZZZZZZZZZZZZZZZZZZZ"
CHAT = "555000111"


def _read(path):
    with io.open(os.path.join(REPO_ROOT, path), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def studio(tmp_path, monkeypatch):
    """A fresh home, no dev mode, no token in the environment, the worker's start and stop recorded."""
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    for name in ("INOX_DEV_MODE", "TELEGRAM_BOT_TOKEN", "PRUDENT_TELEGRAM_BOT_TOKEN",
                 "TELEGRAM_CHAT_ID", "PRUDENT_TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
    started, stopped = [], []
    monkeypatch.setattr(ingress.ingress_daemon, "start_worker", lambda: started.append(True))
    monkeypatch.setattr(ingress.ingress_daemon, "stop_worker", lambda: stopped.append(True))
    monkeypatch.setattr(ingress.ingress_daemon, "bot_token", "")
    monkeypatch.setattr(ingress.ingress_daemon, "authorized_chat_id", "")
    monkeypatch.setattr(ingress.ingress_daemon, "configured_from", None)
    from database import init_db
    import app as app_module
    init_db()
    return TestClient(app_module.app), started, stopped


def _stored():
    conn = get_db()
    try:
        return {r["key"]: r["value"] for r in conn.execute(
            "SELECT key, value FROM settings WHERE key IN (?, ?)",
            (ingress.SETTINGS_TOKEN_KEY, ingress.SETTINGS_CHAT_KEY))}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The token is a secret
# ---------------------------------------------------------------------------

def test_the_bot_token_is_a_secret_setting():
    assert ingress.SETTINGS_TOKEN_KEY in secret_settings.SECRET_SETTING_KEYS
    assert ingress.SETTINGS_CHAT_KEY not in secret_settings.SECRET_SETTING_KEYS, "a chat id is not a secret"


def test_saving_seals_the_token_and_never_answers_it_back(studio):
    client, started, _stopped = studio
    res = client.post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": CHAT})
    assert res.status_code == 200, res.text
    held = _stored()
    assert secret_settings.is_sealed(held[ingress.SETTINGS_TOKEN_KEY])
    assert secret_settings.unseal(ingress.SETTINGS_TOKEN_KEY, held[ingress.SETTINGS_TOKEN_KEY]) == TOKEN
    assert held[ingress.SETTINGS_CHAT_KEY] == CHAT
    body = res.json()
    assert TOKEN not in res.text and body["has_token"] is True and body["chat_id"] == CHAT
    assert TOKEN not in client.get("/api/v1/ingress/settings").text


def test_a_plaintext_token_from_an_older_write_is_sealed_at_startup(studio):
    client, _started, _stopped = studio
    conn = get_db()
    with conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (ingress.SETTINGS_TOKEN_KEY, TOKEN))
    assert secret_settings.upgrade_plaintext(conn) == 1
    assert secret_settings.is_sealed(_stored()[ingress.SETTINGS_TOKEN_KEY])
    conn.close()


# ---------------------------------------------------------------------------
# The worker follows the settings
# ---------------------------------------------------------------------------

def test_saving_both_values_starts_asking_telegram(studio):
    client, started, _stopped = studio
    client.post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": CHAT})
    assert started == [True]
    assert ingress.ingress_daemon.bot_token == TOKEN
    assert ingress.ingress_daemon.authorized_chat_id == CHAT
    assert ingress.ingress_daemon.configured_from == "settings"
    assert client.get("/api/v1/ingress/settings").json()["configured"] is True


def test_removing_the_bot_stops_and_forgets(studio):
    client, started, stopped = studio
    client.post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": CHAT})
    res = client.post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": ""})
    assert res.status_code == 200
    assert stopped == [True]
    assert _stored() == {}
    assert ingress.ingress_daemon.bot_token == "" and ingress.ingress_daemon.configured_from is None
    assert res.json()["configured"] is False and res.json()["has_token"] is False


@pytest.mark.parametrize("payload", [
    {"bot_token": "not a token", "chat_id": CHAT},
    {"bot_token": TOKEN, "chat_id": "me"},
    {"bot_token": TOKEN, "chat_id": ""},
])
def test_a_value_of_the_wrong_shape_is_refused_with_a_sentence(studio, payload):
    client, started, _stopped = studio
    res = client.post("/api/v1/ingress/settings", json=payload)
    assert res.status_code == 400, res.text
    assert isinstance(res.json()["detail"], str) and len(res.json()["detail"]) > 20
    assert _stored() == {} and started == []


def test_the_studio_starts_asking_at_startup_when_a_bot_is_set_up(studio):
    client, started, _stopped = studio
    ingress.save_settings(TOKEN, CHAT)
    started.clear()
    import app as app_module
    with TestClient(app_module.app):
        pass
    assert started == [True], "a bot set up in Settings did not start at startup without dev mode"


def test_nothing_starts_at_startup_without_a_bot(studio):
    client, started, _stopped = studio
    import app as app_module
    with TestClient(app_module.app):
        pass
    assert started == []


def test_the_routes_are_for_the_creator_not_only_a_maintainer(studio):
    client, _started, _stopped = studio
    assert client.get("/api/v1/ingress/settings").status_code == 200


def test_the_answer_says_it_is_untested_against_the_real_service(studio):
    client, _started, _stopped = studio
    body = client.get("/api/v1/ingress/settings").json()
    assert body["tested_against_real_service"] is False
    assert "not yet been tested" in body["not_yet_tested"].lower() or "not yet tested" in body["not_yet_tested"].lower()
    assert "open_requests" in body and body["open_requests"] == 0


# ---------------------------------------------------------------------------
# What the creator reads
# ---------------------------------------------------------------------------

def test_the_panel_is_on_the_local_security_tab_and_says_what_the_phone_sends():
    surface = _read("studio/ui/src/components/BrandStudioSurface.tsx")
    assert "<TelegramIngressPanel />" in surface
    panel = _read("studio/ui/src/components/TelegramIngressPanel.tsx")
    assert "never a figure" in panel
    assert "not_yet_tested" in panel, "the untested sentence is not read from the server"
    assert 'type="password"' in panel, "the token field shows the token"
    assert "aria-label" in panel


def test_the_help_states_the_two_facts():
    article = _read("docs/help/send-a-post-idea-from-telegram.md")
    assert "has not yet been tested against the real Telegram service" in article
    assert "a link, never a figure" in article
    assert "Local security" in article and "Save and start" in article
    leaves = _read("docs/help/what-leaves-this-machine.md")
    assert "Your phone, through Telegram" in leaves


def test_the_policy_says_what_the_bridge_does_with_a_link():
    policy = _read("docs/PRIVACY_POLICY.md")
    row = next(line for line in policy.splitlines() if line.startswith("| `api.telegram.org` |"))
    assert "Local security" in row
    assert "link" in row and "never" in row and "figure" in row
    assert "Telegram's servers" in row


# ---------------------------------------------------------------------------
# A bot belongs to the profile it was set up in
# ---------------------------------------------------------------------------

def test_a_bots_messages_are_saved_in_its_own_profile_whichever_is_open(tmp_path, monkeypatch):
    """
    One worker runs per studio. Without the pin, a bot saved in the first
    profile filed the phone's drafts into whichever client's profile was
    open when the message arrived.
    """
    import base64
    import ed25519
    import licensing
    import paths

    secret = os.urandom(32)
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    for name in ("INOX_DEV_MODE", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", [base64.b64encode(ed25519.public_key(secret)).decode()])
    monkeypatch.setattr(ingress.ingress_daemon, "start_worker", lambda: None)
    monkeypatch.setattr(ingress.ingress_daemon, "stop_worker", lambda: None)
    monkeypatch.setattr(ingress.ingress_daemon, "bot_token", "")
    monkeypatch.setattr(ingress.ingress_daemon, "authorized_chat_id", "")
    monkeypatch.setattr(ingress.ingress_daemon, "configured_from", None)
    monkeypatch.setattr(ingress.ingress_daemon, "profile_id", None)
    from database import init_db
    import app as app_module
    init_db()
    client = TestClient(app_module.app)
    key = licensing.encode({"v": 1, "email": "buyer@example.com", "tier": "agency", "kind": "annual",
                            "profiles": 5, "issued_at": "2026-10-19", "expires_at": "2099-01-01",
                            "updates_until": "2099-01-01"}, lambda message: ed25519.sign(secret, message))
    assert client.post("/api/v1/licence", json={"key": key}).status_code == 200
    assert client.post("/api/v1/accounts", json={"name": "Client B", "id": "client-b"}).status_code == 200

    # The bot is saved in the first profile, then a client's profile is opened.
    assert client.post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": CHAT}).status_code == 200
    assert ingress.ingress_daemon.profile_id == paths.DEFAULT_PROFILE_ID
    assert client.post("/api/v1/accounts/switch", json={"account_id": "client-b"}).status_code == 200
    assert paths.get_active_profile_id() == "client-b"
    described = client.get("/api/v1/ingress/settings").json()
    assert described["running"] is False and described["configured"] is False

    record = ingress.ingress_daemon.process_incoming_update(
        {"update_id": 9, "message": {"chat": {"id": CHAT}, "text": "Idea: a post for my own studio"}})
    assert record is not None

    def drafts(profile_id):
        with paths.using_profile(profile_id):
            conn = get_db()
            try:
                return conn.execute("SELECT COUNT(*) FROM drafts WHERE tags LIKE '%mobile-ingress%'").fetchone()[0]
            finally:
                conn.close()

    assert drafts(paths.DEFAULT_PROFILE_ID) == 1, "the draft did not land in the bot's own profile"
    assert drafts("client-b") == 0, "the phone's draft was filed in another creator's profile"


def test_startup_finds_the_bot_in_the_first_profile_that_has_one(studio, monkeypatch):
    client, started, _stopped = studio
    ingress.save_settings(TOKEN, CHAT)
    started.clear()
    monkeypatch.setattr(ingress.ingress_daemon, "profile_id", None)
    assert ingress.apply_settings(at_startup=True) is True
    import paths
    assert ingress.ingress_daemon.profile_id == paths.DEFAULT_PROFILE_ID
    assert started == [True]


# ---------------------------------------------------------------------------
# Review round, SF-3: a new bot is polled from its own beginning
# ---------------------------------------------------------------------------

BOT_A = "111111:" + "A" * 35
BOT_B = "222222:" + "B" * 35


class _Answer:
    status_code = 200

    def __init__(self, result):
        self._result = result

    def json(self):
        return {"ok": True, "result": self._result}


def _fake_telegram(monkeypatch, answers, calls, during=None):
    """getUpdates answered from a list, nothing on the network; `during` runs while a request waits."""
    def fake_get(url, params=None, timeout=None):
        calls.append((url.split("/bot", 1)[1].split("/", 1)[0], dict(params or {})))
        if during:
            during(len(calls))
        return _Answer(answers.pop(0) if answers else [])
    monkeypatch.setattr(ingress.requests, "get", fake_get)
    monkeypatch.setattr(ingress._egress, "require", lambda url, category: None)


def test_a_new_bot_is_polled_from_its_own_beginning(monkeypatch):
    """
    The reviewer's case. Update ids are per bot, and Telegram treats every
    update below the offset as confirmed. Bot A had reached update
    900,000,000; carried over, that offset confirmed bot B's queue unread.
    """
    daemon = ingress.TelegramIngressDaemon(bot_token=BOT_A, authorized_chat_id=CHAT)
    calls = []
    _fake_telegram(monkeypatch, [[{"update_id": 900000000, "message": {"chat": {"id": 999}, "text": "x"}}]], calls)
    daemon.poll_once()
    assert daemon.last_update_id == 900000000
    daemon.configure(BOT_B, CHAT, origin="settings", profile_id="default")
    daemon.poll_once()
    assert calls[-1] == ("222222:" + "B" * 35, {"offset": 1, "timeout": 30}), (
        "the new bot was asked from the old bot's offset, which confirms its pending messages unread")


def test_the_same_bot_saved_again_keeps_its_place(monkeypatch):
    daemon = ingress.TelegramIngressDaemon(bot_token=BOT_A, authorized_chat_id=CHAT)
    daemon.last_update_id = 41
    daemon.configure(BOT_A, CHAT, origin="settings", profile_id="default")
    assert daemon.last_update_id == 41


def test_an_answer_for_a_bot_replaced_while_it_waited_is_neither_read_nor_confirmed(monkeypatch):
    """A long poll waits up to 30 seconds; if the bot changes meanwhile, its answer is the old bot's."""
    daemon = ingress.TelegramIngressDaemon(bot_token=BOT_A, authorized_chat_id=CHAT)
    calls = []
    handled = []
    monkeypatch.setattr(daemon, "process_incoming_update", lambda update, from_telegram=True: handled.append(update))
    _fake_telegram(monkeypatch, [[{"update_id": 77, "message": {"chat": {"id": int(CHAT)}, "text": "Idea: x"}}]],
                   calls, during=lambda n: daemon.configure(BOT_B, CHAT, origin="settings", profile_id="default"))
    assert daemon.poll_once() == []
    assert handled == [], "the old bot's message was handled under the new bot's settings"
    assert daemon.last_update_id == 0, "the old bot's message was confirmed under the new bot's offset"


def test_restarting_the_worker_leaves_one_thread_polling(monkeypatch):
    """
    Note N-6: a poll waiting on Telegram outlived stop_worker's join, and a
    start right after cleared the shared stop flag, so the old loop carried
    on beside the new one, and Telegram answers two pollers with 409.
    """
    import threading
    import time

    release = threading.Event()
    daemon = ingress.TelegramIngressDaemon(bot_token=BOT_A, authorized_chat_id=CHAT)
    monkeypatch.setattr(daemon, "STOP_JOIN_SECONDS", 0.05)
    monkeypatch.setattr(daemon, "poll_once", lambda: release.wait(5))
    monkeypatch.setattr(daemon, "calculate_next_poll_interval", lambda has_error=False: 0.01)
    daemon.start_worker()
    first = daemon._thread
    time.sleep(0.05)
    daemon.stop_worker()
    daemon.start_worker()
    second = daemon._thread
    release.set()
    first.join(2)
    try:
        assert not first.is_alive(), "the first loop is still polling beside the second"
        assert second.is_alive()
    finally:
        daemon.stop_worker()
        second.join(2)


# ---------------------------------------------------------------------------
# Review round, note N-7
# ---------------------------------------------------------------------------

def test_a_bot_whose_profile_is_gone_is_no_longer_asked(monkeypatch):
    """
    A deleted profile's bot was polled until restart, and each message was
    confirmed to Telegram and dropped. Now the worker stops asking before it
    polls, so nothing more is confirmed unread.
    """
    daemon = ingress.TelegramIngressDaemon(bot_token=BOT_A, authorized_chat_id=CHAT)
    daemon.configure(BOT_A, CHAT, origin="settings", profile_id="ghost-profile")
    calls = []
    _fake_telegram(monkeypatch, [], calls)
    assert daemon.poll_once() == []
    assert calls == [], "the gone profile's bot was still asked for messages"
    assert daemon.bot_token == "" and "closed or gone" in daemon.last_error


def test_a_groups_chat_id_is_refused(studio):
    """Any member of a group could file drafts through it; the help asks for your own chat id."""
    client, started, _stopped = studio
    res = client.post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": "-100123456789"})
    assert res.status_code == 400 and "group" in res.json()["detail"]
    assert _stored() == {} and started == []


def test_the_panel_does_not_claim_the_studio_stopped_asking_everyone():
    """The removal sentence was written by the client, and was false while another profile's bot ran."""
    panel = _read("studio/ui/src/components/TelegramIngressPanel.tsx")
    assert "The studio no longer asks Telegram for anything" not in panel
    assert "Removed from this profile" in panel


def test_the_egress_ledger_describes_the_category_as_it_now_is():
    source = _read("studio/backend/egress.py")
    line = next(l for l in source.splitlines() if l.strip().startswith("ingress "))
    assert "Local security" in line
