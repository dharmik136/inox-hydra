"""
Remind me (phase 5, item 4).
============================

Under "Saved to your collection.", for an item with words, Remind me offers
the creator's own moments (this evening, tomorrow morning and next week by
default); one pressed keeps a reminder, which Your collection lists on the
item with Cancel. At that moment the bot brings the item back, with Write it
up and Not now: once, after quiet hours, after a restart, and never once the
item is removed. Its words go only with the words switch on.

docs/quality/cycle4/bot-phase5.md, item 4. Against the fake Bot API and the
fake provider.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import phone_plans  # noqa: E402
import phone_reminders  # noqa: E402
import telegram_bot  # noqa: E402
from ai_fake import FakeProvider  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, TOKEN, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
DRAFT = "Pricing is a design decision.\n\nWrite the price page first."


@pytest.fixture
def reminding(bot, monkeypatch):
    """The worker tells at every turn, and the bot's clock reads midday, so quiet hours hold nothing."""
    monkeypatch.setattr(telegram_bot, "NOTIFY_EVERY_SECONDS", 0.0)
    clock = {"now": datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)}
    monkeypatch.setattr(telegram_bot, "local_now", lambda: clock["now"])
    bot["clock"] = clock
    return bot


@pytest.fixture
def provider(bot):
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"draft": DRAFT}
    yield fake
    fake.close()


def _labels(bot, message_id):
    return [b["text"] for b in bot["fake"].buttons(message_id)]


def _shown(bot, message_id):
    return str(bot["fake"].message(message_id).get("text") or "")


def _saved_item(bot, words="pricing is a design decision"):
    """An idea from the phone: its answer's message id and its item's id, once a new answer has come."""
    def answers():
        return [m["message_id"] for m in bot["fake"].sent if m["text"] == SAID["collected"]]
    before = len(answers())
    bot["fake"].push(OWNER, f"Idea: {words}")
    assert _until(lambda: len(answers()) > before), _texts(bot)
    item = bot["client"].get("/api/v1/collection").json()["items"][0]
    return answers()[-1], item["id"]


def _moments_messages(bot):
    return [m["message_id"] for m in bot["fake"].sent if m["text"] == SAID["remind_ask"]]


def _moments_message(bot):
    found = _moments_messages(bot)
    return found[-1] if found else None


def _reminders():
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM item_reminders ORDER BY id")]
    finally:
        conn.close()


def _asked(bot, answer):
    """Remind me pressed: the moments message's id, once a new one has come."""
    before = len(_moments_messages(bot))
    bot["fake"].press_button("Remind me", OWNER, message_id=answer)
    assert _until(lambda: len(_moments_messages(bot)) > before), _texts(bot)
    return _moments_message(bot)


def _kept(bot, answer, label=None):
    """Remind me pressed and a moment picked (the first, or `label`): the moments message's id."""
    moments = _asked(bot, answer)
    label = label or bot["fake"].buttons(moments)[0]["text"]
    bot["fake"].press_button(label, OWNER, message_id=moments)
    assert _until(lambda: len(_reminders()) == 1), _texts(bot)
    return moments


def _due_now():
    """The reminder's moment has come."""
    conn = get_db()
    with conn:
        conn.execute("UPDATE item_reminders SET remind_at = ?",
                     ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),))
    conn.close()


def _told(bot):
    return [t for t in _texts(bot) if t.startswith("A reminder you asked for, for ")]


def test_remind_me_sits_under_what_you_send_when_it_has_words(bot):
    _saved(bot)
    answer, _item = _saved_item(bot)
    assert _labels(bot, answer) == ["Write it up", "3 angles", "Remind me", "Remember this", "Undo"]
    long_answer, _ = _saved_item(bot, "pricing " * 60)
    assert _labels(bot, long_answer) == ["Write it up", "3 angles", "Remind me", "Undo"]


def test_remind_me_offers_the_creators_moments_in_a_message_of_its_own(bot):
    _saved(bot)
    answer, item_id = _saved_item(bot)
    moments = _asked(bot, answer)
    now = datetime.now().astimezone()
    assert _labels(bot, moments) == [label for label, _when in phone_reminders.offered(now)]
    assert "Tomorrow morning" in _labels(bot, moments) and "Next week" in _labels(bot, moments)
    assert [a["text"] for a in bot["fake"].answered][-1] == SAID["remind_pick"]
    # Remind me stays on its message.
    assert "Remind me" in _labels(bot, answer)
    assert _reminders() == []


def test_a_moment_pressed_keeps_a_reminder_listed_on_the_item_with_cancel(bot):
    _saved(bot)
    answer, item_id = _saved_item(bot)
    moments = _kept(bot, answer, "Tomorrow morning")
    kept = _reminders()[0]
    when = datetime.fromisoformat(kept["remind_at"])
    tomorrow = datetime.combine(datetime.now().astimezone().date() + timedelta(days=1),
                                datetime.min.time().replace(hour=9)).astimezone()
    assert when == tomorrow and kept["item_id"] == item_id and kept["label"] == "Tomorrow morning"
    said = telegram_bot.REMIND_SET_WORDS.format(when=phone_plans.full_time(tomorrow), label="Tomorrow morning")
    assert _until(lambda: _shown(bot, moments) == said), _shown(bot, moments)
    assert _labels(bot, moments) == ["Cancel"]
    listed = bot["client"].get("/api/v1/collection").json()["items"][0]["reminders"]
    assert listed == [{"id": kept["id"], "remind_at": kept["remind_at"], "label": "Tomorrow morning"}]
    bot["fake"].press_button("Cancel", OWNER, message_id=moments)
    assert _until(lambda: _reminders() == [])
    assert [a["text"] for a in bot["fake"].answered][-1] == SAID["remind_cancelled"]


def test_at_its_moment_the_bot_brings_it_back_once_with_write_it_up_and_not_now(reminding, provider):
    bot = reminding
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})
    answer, item_id = _saved_item(bot)
    _kept(bot, answer, "Tomorrow morning")
    _due_now()
    assert _until(lambda: len(_told(bot)) == 1), _texts(bot)
    told = _told(bot)[0]
    assert told.endswith("\n\npricing is a design decision")
    message = [m for m in bot["fake"].sent if m["text"] == told][-1]["message_id"]
    assert _labels(bot, message) == ["Write it up", "Not now"]
    assert _reminders()[0]["told_at"]
    time.sleep(1.0)
    assert len(_told(bot)) == 1, "told twice"
    bot["fake"].press_button("Write it up", OWNER, message_id=message)
    assert _until(lambda: any(t.startswith(SAID["draft_ready_words"]) for t in _texts(bot))), _texts(bot)


def test_with_the_words_off_it_says_when_it_was_saved_and_none_of_its_words(reminding):
    bot = reminding
    _saved(bot)
    answer, item_id = _saved_item(bot)
    _kept(bot, answer, "Tomorrow morning")
    _due_now()
    assert _until(lambda: len(_told(bot)) == 1), _texts(bot)
    assert "pricing" not in _told(bot)[0]
    assert "an item in your collection, saved " in _told(bot)[0]


def test_not_now_sets_it_aside_while_it_is_new(reminding):
    bot = reminding
    _saved(bot)
    answer, item_id = _saved_item(bot)
    _kept(bot, answer, "Tomorrow morning")
    _due_now()
    assert _until(lambda: len(_told(bot)) == 1), _texts(bot)
    message = [m for m in bot["fake"].sent if m["text"] == _told(bot)[0]][-1]["message_id"]
    bot["fake"].press_button("Not now", OWNER, message_id=message)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered][-1:] == [SAID["set_aside"]])
    conn = get_db()
    assert conn.execute("SELECT status FROM collection_items WHERE id = ?", (item_id,)).fetchone()[0] == "not_now"
    conn.close()


def test_it_waits_through_quiet_hours(reminding):
    bot = reminding
    bot["clock"]["now"] = bot["clock"]["now"].replace(hour=2)
    _saved(bot)
    answer, item_id = _saved_item(bot)
    _kept(bot, answer, "Tomorrow morning")
    _due_now()
    time.sleep(1.0)
    assert _told(bot) == [] and _reminders()[0]["told_at"] is None
    bot["clock"]["now"] = bot["clock"]["now"].replace(hour=12)
    assert _until(lambda: len(_told(bot)) == 1), _texts(bot)


def test_it_survives_a_restart(reminding):
    bot = reminding
    _saved(bot)
    answer, item_id = _saved_item(bot)
    _kept(bot, answer, "Tomorrow morning")
    bot["daemon"].stop_worker()
    _due_now()
    assert bot["client"].post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": OWNER}).status_code == 200
    assert _until(lambda: len(_told(bot)) == 1), _texts(bot)


def test_it_goes_when_its_item_is_removed(reminding):
    bot = reminding
    _saved(bot)
    answer, item_id = _saved_item(bot)
    _kept(bot, answer, "Tomorrow morning")
    assert bot["client"].delete(f"/api/v1/collection/{item_id}").status_code == 200
    assert _reminders() == []
    # Undo on the phone, too.
    answer, item_id = _saved_item(bot, "another thought")
    _kept(bot, answer, "Tomorrow morning")
    bot["fake"].press_button("Undo", OWNER, message_id=answer)
    assert _until(lambda: _reminders() == []), _reminders()
    time.sleep(0.5)
    assert _told(bot) == []


def test_delete_everything_takes_every_reminder(bot):
    import onboarding
    _saved(bot)
    answer, item_id = _saved_item(bot)
    _kept(bot, answer, "Tomorrow morning")
    conn = get_db()
    with conn:
        onboarding.forget_phone_and_export(conn)
    conn.close()
    assert _reminders() == []


def test_cancel_in_the_box(bot):
    _saved(bot)
    answer, item_id = _saved_item(bot)
    _kept(bot, answer, "Tomorrow morning")
    reminder = _reminders()[0]["id"]
    assert bot["client"].delete(f"/api/v1/collection/reminders/{reminder}").status_code == 200
    assert _reminders() == []
    assert bot["client"].delete(f"/api/v1/collection/reminders/{reminder}").status_code == 404
    assert bot["client"].get("/api/v1/collection").json()["items"][0]["reminders"] == []


def test_the_moments_are_the_creators_preference(bot):
    described = bot["client"].get("/api/v1/ingress/settings").json()["options"]
    assert described["remind_moments"] == phone_reminders.MOMENTS_DEFAULT
    assert described["defaults"]["remind_moments"] == phone_reminders.MOMENTS_DEFAULT
    mine = [{"label": "After lunch", "days": 1, "at": "13:30"}, {"label": "In two days", "days": 2, "at": "08:00"}]
    res = bot["client"].post("/api/v1/ingress/options", json={"remind_moments": mine})
    assert res.status_code == 200 and res.json()["options"]["remind_moments"] == mine, res.text
    _saved(bot)
    answer, _item = _saved_item(bot)
    assert _labels(bot, _asked(bot, answer)) == ["After lunch", "In two days"]
    for wrong in ([], [{"label": "", "days": 1, "at": "09:00"}], [{"label": "x" * 25, "days": 1, "at": "09:00"}],
                  [{"label": "Late", "days": 15, "at": "09:00"}], [{"label": "Late", "days": 1, "at": "9pm"}],
                  [{"label": "Same", "days": 1, "at": "09:00"}, {"label": "same", "days": 2, "at": "09:00"}],
                  [{"label": f"M{n}", "days": 1, "at": "09:00"} for n in range(5)]):
        assert bot["client"].post("/api/v1/ingress/options", json={"remind_moments": wrong}).status_code == 400, wrong
    assert phone_reminders.moments() == mine


def test_a_moment_already_past_today_is_not_offered(bot):
    evening = datetime(2026, 11, 4, 20, 0).astimezone()
    labels = [label for label, _when in phone_reminders.offered(evening)]
    assert labels == ["Tomorrow morning", "Next week"], "This evening was offered after it passed"


def test_remind_me_is_in_the_tour(bot):
    assert "reminder" in telegram_bot.TOUR_EVIDENCE
    assert any("reminder" in steps for _title, steps in telegram_bot.TOUR_PARTS)


def test_the_table_is_kept_with_the_collection(bot):
    import retention
    import support
    assert "item_reminders" in support.EXPORTABLE_TABLES
    assert any("item_reminders" in tables for key, _label, tables in retention.CATEGORIES if key == "collection")


def _the_migration():
    import migrations
    found = [m for m in migrations.MIGRATIONS if m[2] is getattr(migrations, "_migrate_item_reminders", None)]
    assert len(found) == 1, "the reminders' migration is not in the ledger exactly once"
    return found[0]


def test_the_migration_is_named_for_what_it_changes_and_by_no_earlier_migrations_word():
    _version, description, _payload = _the_migration()
    assert "reminder" in description.lower() and "phone" in description.lower()
    for earlier in ("collection", "things to remember", "voice note", "short link", "forgotten"):
        assert earlier not in description.lower(), earlier


def test_an_older_database_gains_the_table_and_a_second_run_adds_nothing(tmp_path, monkeypatch):
    import sqlite3

    import migrations
    import paths
    from database import init_db
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    init_db()
    version, _description, payload = _the_migration()
    conn = sqlite3.connect(paths.get_db_path())
    try:
        conn.execute("DROP TABLE item_reminders")
        conn.execute(f"PRAGMA user_version = {version - 1}")
        conn.commit()
        report = migrations.ensure_schema(conn, take_backup=False)
        assert [a["version"] for a in report["applied"]] == list(range(version, migrations.SCHEMA_VERSION + 1))
        columns = {row[1] for row in conn.execute("PRAGMA table_info(item_reminders)")}
        assert {"id", "item_id", "remind_at", "label", "created_at", "told_at"} <= columns
        assert migrations.ensure_schema(conn, take_backup=False)["applied"] == []
        payload(conn.cursor())
        assert {row[1] for row in conn.execute("PRAGMA table_info(item_reminders)")} == columns
    finally:
        conn.close()
