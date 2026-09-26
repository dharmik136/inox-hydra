"""
The bot answers to its owner, and never writes its own key down.
================================================================

Two defects in the same module, both live in the configuration the
documentation tells people to use.

  The whitelist was optional. The check read
  `if self.authorized_chat_id and chat_id != ...`, and authorized_chat_id
  defaults to empty, while app.py starts the daemon on the bot token alone.
  So the shipped posture was: anyone who learns the bot's username can send it
  a message and have the text land in the creator's drafts and their posts
  table, on a product whose next step is publishing to LinkedIn. A bot
  username is not a secret; Telegram lists bots in search.

  The token was written into the error surface. The token is a path segment of
  the getUpdates URL, requests puts the URL in its exception message, and
  `str(err)` was assigned straight to last_error and logged. last_error is
  returned verbatim by GET /api/v1/ingress/status; the log goes to stderr,
  which under the desktop shell is redirected into the engine log, which
  support.py tails into a diagnostics bundle offered for a public issue. A
  misconfigured bot on a machine with no network was one support request away
  from publishing a credential that can read and send the creator's messages.

Both are refusals rather than warnings, because the safe direction here is to
accept nothing and say so.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from ingress import TelegramIngressDaemon

TOKEN = "123456789:AAFnotarealkeyZZZZZZZZZZZZZZZZZZZZZZZ"

OWNER = "555000111"
STRANGER = "999888777"


def _message(chat_id, text="Draft: a post I am writing"):
    # The id is passed through as given rather than coerced. Telegram sends an
    # integer, and the local simulate route sends a non-numeric placeholder, so
    # forcing int() here would make the helper unable to express the case that
    # matters most.
    return {
        "update_id": 1,
        "message": {"chat": {"id": chat_id}, "text": text},
    }


def _daemon(chat_id=OWNER, token=TOKEN, monkeypatch=None):
    # The environment is cleared explicitly: these two variables decide the
    # behaviour under test, and a developer machine that happens to have them
    # set would otherwise quietly change the answer.
    if monkeypatch is not None:
        for name in ("TELEGRAM_CHAT_ID", "PRUDENT_TELEGRAM_CHAT_ID",
                     "TELEGRAM_BOT_TOKEN", "PRUDENT_TELEGRAM_BOT_TOKEN"):
            monkeypatch.delenv(name, raising=False)
    return TelegramIngressDaemon(bot_token=token, authorized_chat_id=chat_id)


# ---------------------------------------------------------------------------
# The whitelist is not optional
# ---------------------------------------------------------------------------

def test_an_unconfigured_whitelist_accepts_nothing(monkeypatch):
    """
    The defect itself, in the documented configuration: a token and no chat id.
    Every other default in this product fails closed, and this one failed open.
    """
    daemon = _daemon(chat_id="", monkeypatch=monkeypatch)

    assert daemon.process_incoming_update(_message(STRANGER)) is None, (
        "a stranger's message was accepted because no chat id was configured"
    )
    assert daemon.process_incoming_update(_message(OWNER)) is None, (
        "with no chat id the daemon cannot tell the owner from anyone else, so "
        "it must refuse both rather than guess"
    )


def test_refusing_for_want_of_a_chat_id_says_so(monkeypatch):
    """
    Silence would read as "no messages arrived". The creator needs to know the
    difference between an idle bot and a bot refusing everything.
    """
    daemon = _daemon(chat_id="", monkeypatch=monkeypatch)
    daemon.process_incoming_update(_message(OWNER))

    assert daemon.last_error, "the refusal was silent"
    assert "TELEGRAM_CHAT_ID" in daemon.last_error, (
        "the message does not name the setting that would fix it"
    )


def test_a_stranger_is_refused_when_a_chat_id_is_set(monkeypatch):
    daemon = _daemon(monkeypatch=monkeypatch)
    assert daemon.process_incoming_update(_message(STRANGER)) is None


def test_the_owner_is_still_accepted(monkeypatch):
    """The guard must not have been bought by breaking the feature."""
    daemon = _daemon(monkeypatch=monkeypatch)
    record = daemon.process_incoming_update(_message(OWNER))

    assert record is not None, "the configured owner was refused"
    assert record["archetype"] == "Draft"


def test_the_environment_can_supply_the_chat_id(monkeypatch):
    """The documented way to configure it has to keep working."""
    monkeypatch.setenv("TELEGRAM_CHAT_ID", OWNER)
    daemon = TelegramIngressDaemon(bot_token=TOKEN)
    assert daemon.process_incoming_update(_message(OWNER)) is not None
    assert daemon.process_incoming_update(_message(STRANGER)) is None


# ---------------------------------------------------------------------------
# The token never reaches a surface anyone can read
# ---------------------------------------------------------------------------

def test_a_connection_error_does_not_carry_the_token(monkeypatch):
    """
    The real path. requests puts the request URL in its exception message, and
    the token is a path segment of that URL.
    """
    import ingress as ingress_module

    daemon = _daemon(monkeypatch=monkeypatch)

    def explode(*args, **kwargs):
        raise RuntimeError(
            "HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries "
            f"exceeded with url: /bot{TOKEN}/getUpdates"
        )

    monkeypatch.setattr(ingress_module.requests, "get", explode)
    monkeypatch.setattr(ingress_module._egress, "require", lambda *a, **k: None)

    with pytest.raises(RuntimeError):
        daemon.poll_once()

    assert daemon.last_error, "nothing was recorded at all"
    assert TOKEN not in daemon.last_error, (
        f"the bot token is in last_error, which GET /api/v1/ingress/status "
        f"returns verbatim: {daemon.last_error}"
    )
    assert "<redacted>" in daemon.last_error


def test_the_token_is_removed_from_both_spellings(monkeypatch):
    """
    It appears bare and as `bot<token>` in the path. Replacing only the bare
    form would leave the secret half of the path form behind.
    """
    daemon = _daemon(monkeypatch=monkeypatch)

    cleaned = daemon._redact(f"url: /bot{TOKEN}/getUpdates and bare {TOKEN} here")

    assert TOKEN not in cleaned
    assert "bot<redacted>" in cleaned


def test_an_http_error_body_is_redacted(monkeypatch):
    """
    Telegram echoes the request in some error bodies, and a proxy error page
    can carry the path. Every string that reaches last_error is cleaned, not
    just the exception one.
    """
    daemon = _daemon(monkeypatch=monkeypatch)
    assert TOKEN not in daemon._redact(f"HTTP 404: not found for /bot{TOKEN}/getUpdates")


def test_redaction_is_harmless_with_no_token_configured(monkeypatch):
    daemon = _daemon(token="", monkeypatch=monkeypatch)
    assert daemon._redact("an ordinary message") == "an ordinary message"
    assert daemon._redact("") == ""


def test_the_status_endpoint_never_exposes_the_token(monkeypatch):
    """
    The endpoint reports whether a token exists, which is what the interface
    needs, and never the token itself.
    """
    daemon = _daemon(monkeypatch=monkeypatch)
    status = daemon.get_daemon_status()

    assert status["has_token"] is True
    assert TOKEN not in str(status)


# ---------------------------------------------------------------------------
# The local route is a different trust path
# ---------------------------------------------------------------------------

def test_the_local_simulate_path_is_not_governed_by_the_telegram_whitelist(monkeypatch):
    """
    /api/v1/ingress/simulate reaches the same method, and its authorization
    already happened: the access middleware required a loopback Host, an
    allowed Origin and the session cookie. Someone at this keyboard is the
    creator.

    The two used to share one check, and the local route passed a made up chat
    id that the open whitelist happened to accept. That is how the hole stayed
    invisible: the local path looked authorized when nothing was.
    """
    daemon = _daemon(chat_id="", monkeypatch=monkeypatch)

    record = daemon.process_incoming_update(
        _message("local_creator_not_a_real_chat_id", text="Idea: from my own tray"),
        from_telegram=False,
    )

    assert record is not None, (
        "the creator's own tray was refused by a whitelist that exists to keep "
        "strangers out of Telegram"
    )
    assert record["archetype"] == "Raw Idea"


def test_telegram_is_the_default_so_a_missed_argument_fails_closed(monkeypatch):
    """
    A new caller that forgets the flag gets the strict path, not the lenient
    one. The safe direction has to be the one you get by saying nothing.
    """
    import inspect

    signature = inspect.signature(TelegramIngressDaemon.process_incoming_update)
    assert signature.parameters["from_telegram"].default is True

    daemon = _daemon(chat_id="", monkeypatch=monkeypatch)
    assert daemon.process_incoming_update(_message(OWNER)) is None


def test_the_simulate_route_still_works_end_to_end():
    """The route a creator actually uses, through the real app."""
    from fastapi.testclient import TestClient
    import app as app_module

    client = TestClient(app_module.app)
    res = client.post("/api/v1/ingress/simulate", json={
        "text": "Draft: a thought captured from the tray",
        "sender_name": "Creator",
    })

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success", body
    assert body["record"]["archetype"] == "Draft"
