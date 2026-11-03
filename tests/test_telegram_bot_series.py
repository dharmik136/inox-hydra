"""
A series from a group (phase 6, item 5).
========================================

Write it as a series, under /recall's answer for a word and in Your
collection's group: one request to the creator's own provider for their
number of posts as a series from the group's unused items, each checked as a
draft is and all kept or none, each saved as its own draft recording its
part. Plan the series puts the parts into the Queue's next open slots, in
order, each the Queue's cooldown from every other post and after the part
before, through Plan it's own path, with Undo; too few open slots plans
nothing and says so. Nothing is posted and nothing reaches LinkedIn.

docs/quality/cycle4/bot-phase6.md, item 5. Against the fake Bot API and the
fake provider.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import phone_plans  # noqa: E402
import telegram_bot  # noqa: E402
import writing  # noqa: E402
from ai_fake import FakeProvider  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
SERIES = "Write it as a series"
PARTS = ["Pricing starts with the page.\n\nPart one.", "The page is a brief.\n\nPart two.",
         "Write the page first.\n\nPart three."]


@pytest.fixture
def provider(bot):
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"posts": list(PARTS)}
    yield fake
    fake.close()


def _seed(*texts):
    import collection
    ids = []
    for n, text in enumerate(texts):
        ids.append(collection.add("note", text, source="studio")["id"])
        conn = get_db()
        with conn:
            conn.execute("UPDATE collection_items SET received_at = ? WHERE id = ?",
                         (f"2026-10-{10 + n:02d}T08:00:00+00:00", ids[-1]))
        conn.close()
    return ids


def _slots(*entries):
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM queue_slots")
        for day, at in entries:
            conn.execute("INSERT INTO queue_slots (day_of_week, time_slot, label, is_active) VALUES (?, ?, 'x', 1)",
                         (day, at))
    conn.close()


def _every_day_at(*clocks):
    _slots(*[(day, at) for day in range(7) for at in clocks])


def _recalled(bot, word="pricing"):
    def found():
        return [m for m in bot["fake"].sent if " items in your collection hold that word." in str(m["text"] or "")]
    before = len(found())
    bot["fake"].push(OWNER, f"/recall {word}")
    assert _until(lambda: len(found()) > before), _texts(bot)
    return found()[-1]["message_id"]


def _labels(bot, message_id):
    return [b["text"] for b in bot["fake"].buttons(message_id)]


def _notices(bot):
    return [a["text"] for a in bot["fake"].answered]


def _posts():
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT id, content, status, scheduled_for, made_with FROM posts "
                                              "WHERE made_with IS NOT NULL ORDER BY rowid")]
    finally:
        conn.close()


def _series_ready(bot):
    return [m for m in bot["fake"].sent if str(m["text"] or "").startswith(
        SAID["series_ready"].format(count=3).rstrip("."))]


def test_recall_offers_write_it_as_a_series_and_it_writes_one_draft_a_part(bot, provider):
    _saved(bot)
    ids = _seed("pricing is a design decision", "pricing pages lie", "hiring loops", "pricing for agencies")
    message = _recalled(bot)
    assert _labels(bot, message) == ["Write one post from these", SERIES]
    bot["fake"].press_button(SERIES, OWNER, message_id=message)
    assert _until(lambda: _notices(bot)[-1:] == [SAID["series_from"].format(count=3)]), _notices(bot)
    assert _until(lambda: len(_series_ready(bot)) == 1), _texts(bot)
    ready = _series_ready(bot)[0]
    assert ready["text"] == SAID["series_ready"].format(count=3)
    assert _labels(bot, ready["message_id"]) == ["Plan the series"]
    sent = provider.sent()
    assert "a series of 3 posts" in sent and "pricing pages lie" in sent and "hiring" not in sent
    posts = _posts()
    assert [p["content"] for p in posts] == PARTS and all(p["status"] == "draft" for p in posts)
    made = [json.loads(p["made_with"]) for p in posts]
    assert [m["series"]["part"] for m in made] == [1, 2, 3] and {m["series"]["of"] for m in made} == {3}
    assert len({m["series"]["id"] for m in made}) == 1 and all(m["via"] == "telegram" for m in made)
    conn = get_db()
    statuses = [conn.execute("SELECT status FROM collection_items WHERE id = ?", (i,)).fetchone()[0] for i in ids]
    conn.close()
    assert statuses == ["used", "used", "new", "used"]


def test_with_the_words_on_each_parts_first_line_comes(bot, provider):
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})
    _seed("pricing is a design decision", "pricing pages lie")
    message = _recalled(bot)
    bot["fake"].press_button(SERIES, OWNER, message_id=message)
    words = telegram_bot.SERIES_READY_WORDS.format(count=3)
    assert _until(lambda: any(str(t).startswith(words) for t in _texts(bot))), _texts(bot)
    text = [t for t in _texts(bot) if str(t).startswith(words)][-1]
    assert text == (words + "\n\n1. Pricing starts with the page.\n2. The page is a brief.\n3. Write the page first.")


def test_one_part_with_a_figure_not_sent_keeps_none(bot, provider):
    _saved(bot)
    provider.answer = {"posts": [PARTS[0], "We grew 40 percent.", PARTS[2]]}
    _seed("pricing is a design decision", "pricing pages lie")
    message = _recalled(bot)
    bot["fake"].press_button(SERIES, OWNER, message_id=message)
    assert _until(lambda: SAID["write_refused"] in _texts(bot)), _texts(bot)
    assert _posts() == []


def test_the_number_of_parts_is_the_creators(bot, provider):
    _saved(bot)
    assert writing.preferences()["series_parts"] == 3
    assert bot["client"].put("/api/v1/writing/preferences", json={"series_parts": 2}).status_code == 200
    provider.answer = {"posts": PARTS[:2]}
    _seed("pricing is a design decision", "pricing pages lie")
    message = _recalled(bot)
    bot["fake"].press_button(SERIES, OWNER, message_id=message)
    assert _until(lambda: any(str(t).startswith("A series of 2 drafts") for t in _texts(bot))), _texts(bot)
    assert "a series of 2 posts" in provider.sent() and len(_posts()) == 2
    for wrong in (1, 6, "three"):
        assert bot["client"].put("/api/v1/writing/preferences", json={"series_parts": wrong}).status_code in (400, 422)
    assert writing.preferences()["series_parts"] == 2


def test_a_single_matching_item_offers_no_series(bot, provider):
    _saved(bot)
    _seed("pricing is a design decision", "hiring loops")
    def found():
        return [m for m in bot["fake"].sent if str(m["text"] or "") == SAID["recall_one"]]
    bot["fake"].push(OWNER, "/recall pricing")
    assert _until(lambda: found()), _texts(bot)
    assert SERIES not in _labels(bot, found()[-1]["message_id"])


def test_plan_the_series_puts_the_parts_into_the_queues_next_open_slots_in_order(bot, provider):
    _saved(bot)
    _every_day_at("09:00", "18:00")
    _seed("pricing is a design decision", "pricing pages lie")
    message = _recalled(bot)
    bot["fake"].press_button(SERIES, OWNER, message_id=message)
    assert _until(lambda: len(_series_ready(bot)) == 1), _texts(bot)
    ready = _series_ready(bot)[0]["message_id"]
    import egress
    before = {c["name"]: c["performed"] for c in egress.describe()["categories"]}.get("linkedin", 0)
    bot["fake"].press_button("Plan the series", OWNER, message_id=ready)
    assert _until(lambda: _notices(bot)[-1:] == [SAID["series_planned"]]), _notices(bot)
    posts = _posts()
    times = [datetime.fromisoformat(p["scheduled_for"]) for p in posts]
    assert all(p["status"] == "scheduled" for p in posts) and times == sorted(times)
    assert all((b - a).total_seconds() >= phone_plans._cooldown_hours() * 3600 for a, b in zip(times, times[1:]))
    assert times[0] > datetime.now(timezone.utc) + timedelta(minutes=phone_plans.AHEAD_MINUTES)
    assert all(isinstance(json.loads(p["made_with"]).get("planned"), dict) for p in posts)
    shown = str(bot["fake"].message(ready)["text"])
    assert shown.startswith(telegram_bot.SERIES_PLANNED_HEAD)
    for when in times:
        assert phone_plans.full_time(when) in shown
    assert _labels(bot, ready) == ["Undo"]
    after = {c["name"]: c["performed"] for c in egress.describe()["categories"]}.get("linkedin", 0)
    assert after == before, "planning reached LinkedIn"
    conn = get_db()
    assert conn.execute("SELECT COUNT(*) FROM settings WHERE key LIKE 'linkedin_holds:%'").fetchone()[0] == 0
    conn.close()
    bot["fake"].press_button("Undo", OWNER, message_id=ready)
    assert _until(lambda: _notices(bot)[-1:] == [SAID["series_unplanned"]]), _notices(bot)
    assert all(p["status"] == "draft" and p["scheduled_for"] is None for p in _posts())


def test_too_few_open_slots_plans_nothing_and_says_so(bot, provider):
    _saved(bot)
    _slots()
    _seed("pricing is a design decision", "pricing pages lie")
    message = _recalled(bot)
    bot["fake"].press_button(SERIES, OWNER, message_id=message)
    assert _until(lambda: len(_series_ready(bot)) == 1), _texts(bot)
    ready = _series_ready(bot)[0]["message_id"]
    bot["fake"].press_button("Plan the series", OWNER, message_id=ready)
    assert _until(lambda: _notices(bot)[-1:] == [SAID["series_short"]]), _notices(bot)
    assert all(p["status"] == "draft" for p in _posts())
    assert "Plan the series" in _labels(bot, ready), "Plan the series went though nothing was planned"


def test_your_collection_writes_a_series_from_a_group(bot, provider):
    _saved(bot)
    ids = _seed("pricing page founders one", "pricing page two", "pricing page founders newest")
    res = bot["client"].post("/api/v1/collection/write", json={"items": [ids[2], ids[0], ids[1]], "series": True})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "drafted" and len(body["ids"]) == 3 and body["content"] == PARTS[0]
    assert [p["content"] for p in _posts()] == PARTS
    one = bot["client"].post("/api/v1/collection/write", json={"items": [ids[0]], "series": True})
    assert one.status_code == 400


def test_it_is_in_the_tour_and_the_panel_lists_a_series_from_the_phone(bot, provider):
    _saved(bot)
    assert any("series" in steps for _title, steps in telegram_bot.TOUR_PARTS)

    def seen():
        return {s["key"]: s["seen"] for s in bot["client"].get("/api/v1/ingress/settings").json()["tour"]}
    assert seen()["series"] is False
    _seed("pricing is a design decision", "pricing pages lie")
    message = _recalled(bot)
    bot["fake"].press_button(SERIES, OWNER, message_id=message)
    assert _until(lambda: len(_series_ready(bot)) == 1), _texts(bot)
    assert _until(lambda: seen()["series"]), seen()
