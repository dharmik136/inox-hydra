"""
"Seen working" says what this profile holds (phase 4, item 1).
===============================================================

The panel used to decide from one settings marker, set when a message from
the saved chat was saved. A studio that saved phone messages before the
marker existed never had it set, so the owner's panel said "no message from
your own chat has been saved here" beside a collection of messages from that
chat. Now anything saved here from Telegram since the chat was paired counts
(an item in the collection, a thing to remember, an ask), since only the
paired chat's messages are ever saved; found once, the marker is set, so the
answer stays when the item is removed. A chat paired before this build has no
recorded pairing moment, and then anything saved from Telegram counts.

docs/quality/cycle4/bot-phase4.md, item 1. The Telegram side is not reached:
the worker's thread is never started.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import ingress  # noqa: E402
from database import get_db  # noqa: E402
from test_qc4_t6_telegram_pairing import OWNER, STRANGER, TOKEN, studio  # noqa: E402,F401


def _panel(studio):
    return studio["client"].get("/api/v1/ingress/settings").json()


def _as_before_the_marker(studio):
    """
    The owner's studio: a bot saved with its chat, and what the phone sent kept
    in the collection, from before the marker (or the pairing moment) existed.
    """
    res = studio["client"].post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": OWNER})
    assert res.status_code == 200, res.text
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO collection_items (received_at, kind, text, status, source, origin_ref) "
                     "VALUES ('2026-10-28T14:05:00+00:00', 'note', 'my first idea from the phone', 'new', "
                     "'telegram', 'telegram:7:1761660300')")
        conn.execute("DELETE FROM settings WHERE key IN (?, ?)",
                     (ingress.SETTINGS_HEARD_KEY, getattr(ingress, "SETTINGS_PAIRED_KEY", "telegram_chat_paired_at")))
    conn.close()


def _marker():
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (ingress.SETTINGS_HEARD_KEY,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def test_a_profile_with_a_saved_telegram_item_and_no_marker_shows_as_seen_working(studio):
    _as_before_the_marker(studio)
    panel = _panel(studio)
    assert panel["tested_against_real_service"] is True, "the panel says the bot was never seen working"
    assert panel["not_yet_tested"] is None, panel["not_yet_tested"]


def test_found_once_the_marker_is_set_and_stays_when_the_item_is_removed(studio):
    _as_before_the_marker(studio)
    _panel(studio)
    assert _marker() == "2026-10-28T14:05:00+00:00", "the marker was not set to when the item arrived"
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM collection_items")
    conn.close()
    assert _panel(studio)["tested_against_real_service"] is True, "removing the item unsaid that it was seen"


def test_a_thing_to_remember_or_an_ask_from_the_phone_counts_too(studio):
    studio["client"].post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": OWNER})
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM settings WHERE key IN (?, ?)",
                     (ingress.SETTINGS_HEARD_KEY, getattr(ingress, "SETTINGS_PAIRED_KEY", "telegram_chat_paired_at")))
        conn.execute("INSERT INTO remembered (text, about, source, created_at, updated_at) VALUES "
                     "('I write for small studios', 'you', 'telegram', '2026-10-29T08:00:00+00:00', "
                     "'2026-10-29T08:00:00+00:00')")
    conn.close()
    assert _panel(studio)["tested_against_real_service"] is True


def test_what_was_typed_at_this_computer_does_not_count(studio):
    studio["client"].post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": OWNER})
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM settings WHERE key IN (?, ?)",
                     (ingress.SETTINGS_HEARD_KEY, getattr(ingress, "SETTINGS_PAIRED_KEY", "telegram_chat_paired_at")))
        conn.execute("INSERT INTO collection_items (received_at, kind, text, status, source) "
                     "VALUES ('2026-10-29T08:00:00+00:00', 'note', 'typed at the desk', 'new', 'studio')")
        conn.execute("INSERT INTO remembered (text, about, source, created_at, updated_at) VALUES "
                     "('typed in Brand', 'you', 'studio', '2026-10-29T08:00:00+00:00', '2026-10-29T08:00:00+00:00')")
    conn.close()
    panel = _panel(studio)
    assert panel["tested_against_real_service"] is False and panel["not_yet_tested"], (
        "something typed at this computer was taken as a message from the phone")


def test_after_a_change_of_chat_only_what_came_after_it_counts(studio):
    _as_before_the_marker(studio)
    assert _panel(studio)["tested_against_real_service"] is True
    # Another chat paired: the item from the chat before says nothing about it.
    studio["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": STRANGER})
    assert _panel(studio)["tested_against_real_service"] is False, (
        "an item from the chat paired before counted for the chat paired now")
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO collection_items (received_at, kind, text, status, source) "
                     "VALUES (?, 'note', 'from the new chat', 'new', 'telegram')",
                     ("2999-01-01T00:00:00+00:00",))
    conn.close()
    assert _panel(studio)["tested_against_real_service"] is True


def test_removing_the_bot_forgets_when_its_chat_was_paired(studio):
    studio["client"].post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": OWNER})
    key = getattr(ingress, "SETTINGS_PAIRED_KEY", "telegram_chat_paired_at")
    conn = get_db()
    held = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    assert held is not None, "pairing a chat did not record when"
    studio["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": ""})
    conn = get_db()
    gone = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    assert gone is None, "the bot was removed and its pairing moment stayed"
