"""
The "/" menu: the bot's commands registered with Telegram for the paired chat (phase 4, item 3).
================================================================================================

setMyCommands, scoped to the paired chat (BotCommandScopeChat), through the
egress check under `ingress` and counted without the token. Registered when
pairing completes and when the command list changes; a fingerprint of what
Telegram took is kept, so it is not sent again at every start, and a refusal
is tried again later, never at every poll. Each description is in plain
words, and /help's lines about the commands are written from the same list.
Another chat paired takes the menu away from the chat before; removing the
bot takes its menu away.

docs/quality/cycle4/bot-phase4.md, item 3. Against the fake Bot API
(tests/telegram_fake.py), which holds Telegram's limits.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import ingress  # noqa: E402
import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, STRANGER, TOKEN, _until, bot  # noqa: E402,F401
from test_telegram_bot_notifications import _settle  # noqa: E402
from test_telegram_bot_replies import _saved  # noqa: E402


def _sets(bot):
    return bot["fake"].calls_of("setMyCommands")


def _scope_of(call):
    scope = call["params"].get("scope")
    return json.loads(scope) if isinstance(scope, str) else scope


def test_pairing_registers_the_menu_for_the_paired_chat_only(bot):
    _saved(bot)
    assert _until(lambda: len(bot["fake"].menu(OWNER)) > 0), "the paired chat's menu was never registered"
    [call] = _sets(bot)
    assert _scope_of(call) == {"type": "chat", "chat_id": int(OWNER)}
    assert bot["fake"].menu() == [], "the menu went to every chat, not the paired one"
    names = [c["command"] for c in bot["fake"].menu(OWNER)]
    assert names == [name for name, _words in telegram_bot.BOT_COMMANDS]
    assert "help" in names and "idea" in names and "status" in names


def test_each_description_is_the_one_help_gives(bot):
    for name, words in telegram_bot.BOT_COMMANDS:
        assert re.fullmatch(r"[a-z0-9_]{1,32}", name), name
        assert 1 <= len(words) <= 256, name
        line = f"- /{name}: {words[0].lower()}{words[1:]}"
        assert line in telegram_bot.HELP, f"/help does not say {name} as the menu does: {line!r}"


def test_it_is_not_sent_again_at_every_start(bot):
    _saved(bot)
    assert _until(lambda: len(_sets(bot)) == 1)
    daemon = bot["daemon"]
    daemon.stop_worker()
    daemon.is_running = False
    ingress.apply_settings(at_startup=True)
    _settle(bot)
    assert len(_sets(bot)) == 1, "the same menu was sent again at a start"


def test_a_changed_command_list_is_registered_once(bot, monkeypatch):
    _saved(bot)
    assert _until(lambda: len(_sets(bot)) == 1)
    monkeypatch.setattr(telegram_bot, "BOT_COMMANDS",
                        telegram_bot.BOT_COMMANDS + (("newcommand", "A command a later build added"),))
    assert _until(lambda: len(_sets(bot)) == 2)
    _settle(bot)
    assert len(_sets(bot)) == 2
    assert "newcommand" in [c["command"] for c in bot["fake"].menu(OWNER)]


def test_a_refusal_is_tried_again_later_never_at_every_poll(bot, monkeypatch):
    bot["fake"].plan("setMyCommands", ("status", 500, "Internal Server Error"))
    _saved(bot)
    assert _until(lambda: len(_sets(bot)) == 1)
    _settle(bot)
    assert len(_sets(bot)) == 1, "a refused menu was asked again at every poll"
    assert bot["fake"].menu(OWNER) == []
    monkeypatch.setattr(telegram_bot, "MENU_RETRY_SECONDS", 0.0)
    assert _until(lambda: bot["fake"].menu(OWNER) != []), "the menu was never tried again"


def test_another_chat_paired_takes_the_menu_from_the_chat_before(bot):
    _saved(bot)
    assert _until(lambda: bot["fake"].menu(OWNER) != [])
    bot["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": STRANGER})
    assert _until(lambda: bot["fake"].menu(STRANGER) != [])
    assert _until(lambda: bot["fake"].menu(OWNER) == []), "the chat paired before kept the bot's menu"


def test_removing_the_bot_takes_its_menu_away(bot):
    _saved(bot)
    assert _until(lambda: bot["fake"].menu(OWNER) != [])
    bot["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": ""})
    assert bot["fake"].menu(OWNER) == [], "the removed bot's menu stayed in the chat"
    conn = get_db()
    held = conn.execute("SELECT 1 FROM settings WHERE key = ?", (telegram_bot.MENU_KEY,)).fetchone()
    conn.close()
    assert held is None


def test_the_menu_is_counted_without_the_token(bot):
    import egress
    _saved(bot)
    assert _until(lambda: len(_sets(bot)) == 1)
    ledger = repr(egress.describe())
    assert TOKEN.split(":")[1] not in ledger


def test_the_panel_says_once_telegram_took_it(bot):
    _saved(bot)
    assert _until(lambda: bot["client"].get("/api/v1/ingress/settings").json().get("menu") is True)
