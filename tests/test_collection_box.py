"""
The collection box: everything sent to the bot lands in one place, live.
=======================================================================

Phase 3 of the Telegram bot (docs/quality/cycle4/collection-box.md, item 1).
Text, ideas, forwarded messages and links sent to the bot land in the
collection, not as drafts: each with when, its kind, its words, tags and a
local topic, a status (new, used, not now) and what it became. A link to
one of the creator's posts still asks Today to open it; a link to anyone
else's post is a bookmark, the address rebuilt from its id and never its
slug; a forwarded message keeps its text and never its origin. "Draft:"
still goes straight to a draft, recorded as used. Each arrival is published
on the change stream, so the studio shows it without a reload.

Driven end to end against the fake Bot API (tests/telegram_fake.py).

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, _drafts, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _own_post, _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES


def _items(**where):
    conn = get_db()
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM collection_items ORDER BY id")]
    finally:
        conn.close()
    for row in rows:
        row["tags"] = json.loads(row["tags"] or "[]")
    return [r for r in rows if all(r.get(k) == v for k, v in where.items())]


def _everything_stored():
    """Every string in every table, to show what is never kept."""
    conn = get_db()
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        found = []
        for table in tables:
            try:
                for row in conn.execute(f"SELECT * FROM [{table}]"):
                    found.extend(str(v) for v in tuple(row) if isinstance(v, str))
            except Exception:
                continue
        return " ".join(found)
    finally:
        conn.close()


def _send(bot, text, **message):
    before = len(_texts(bot))
    bot["fake"].push(OWNER, text, **message)
    assert _until(lambda: len(_texts(bot)) > before), _texts(bot)
    return _texts(bot)[-1]


def _labels(bot):
    sent = [m for m in bot["fake"].sent if m["chat_id"] == OWNER][-1]
    return [b["text"] for b in bot["fake"].buttons(sent["message_id"])]


def test_text_lands_in_the_collection_and_not_as_a_draft(bot):
    _saved(bot)
    answer = _send(bot, "a thought about pricing for small studios #Pricing")
    assert answer == SAID["collected"]
    assert _labels(bot)[-1] == "Undo"
    [item] = _items()
    assert (item["kind"], item["status"], item["text"]) == ("note", "new", "a thought about pricing for small studios #Pricing")
    assert item["tags"] == ["pricing"] and item["source"] == "telegram" and item["received_at"]
    assert _drafts() == [], "a phone message was saved as a draft"


def test_an_idea_by_command_or_by_prefix_is_an_idea(bot):
    _saved(bot)
    _send(bot, "/idea hiring loops for a team of three")
    _send(bot, "Idea: a story about the first client")
    assert [(i["kind"], i["text"]) for i in _items()] == [("idea", "hiring loops for a team of three"),
                                                          ("idea", "a story about the first client")]


def test_a_forwarded_message_keeps_its_text_and_never_its_origin(bot):
    _saved(bot)
    origin = {"type": "user", "date": 1761700000,
              "sender_user": {"id": 5551234, "is_bot": False, "first_name": "Priya", "last_name": "Originhart",
                              "username": "priya_originhart"}}
    answer = _send(bot, "Worth writing about: the cost of saying yes to everything",
                   forward_origin=origin, forward_date=1761700000,
                   forward_from={"id": 5551234, "first_name": "Priya", "username": "priya_originhart"},
                   forward_from_chat={"id": -1001234567, "type": "channel", "title": "Growthroom Weekly",
                                      "username": "growthroomweekly"},
                   forward_sender_name="Priya Originhart", forward_signature="Priya O.")
    assert answer == SAID["collected"]
    [item] = _items()
    assert (item["kind"], item["text"]) == ("forward", "Worth writing about: the cost of saying yes to everything")
    stored = _everything_stored()
    for origin_word in ("Priya", "Originhart", "priya_originhart", "Growthroom", "growthroomweekly", "5551234"):
        assert origin_word not in stored, f"a forward's origin was kept: {origin_word}"


def test_a_link_to_ones_own_post_asks_today_and_is_listed(bot):
    _saved(bot)
    mine = _own_post(bot)
    answer = _send(bot, f"https://www.linkedin.com/feed/update/{mine}/")
    assert answer == f"{SAID['collected']} {SAID['post']}"
    [item] = _items()
    assert (item["kind"], item["status"], item["activity_urn"]) == ("post", "used", mine)
    assert item["link"] == f"https://www.linkedin.com/feed/update/{mine}/"
    conn = get_db()
    try:
        request = conn.execute("SELECT id, state FROM desk_requests WHERE activity_urn = ?", (mine,)).fetchone()
    finally:
        conn.close()
    assert request["state"] == "open" and item["desk_request_id"] == request["id"], "Today was not asked to open it"


def test_a_short_link_asks_today_and_is_listed(bot):
    _saved(bot)
    answer = _send(bot, "https://lnkd.in/p/dXyZ4bQ7")
    assert answer == f"{SAID['collected']} {SAID['short']}"
    [item] = _items()
    assert (item["kind"], item["link"], item["status"]) == ("link", "https://lnkd.in/p/dXyZ4bQ7", "used")
    assert item["desk_request_id"]


def test_someone_elses_post_is_a_bookmark_kept_without_its_slug(bot):
    _saved(bot)
    link = ("https://www.linkedin.com/posts/jane-strangewood_pricing-secrets-nobody-tells-activity-"
            "7390000000000000777-AbCd?utm_source=share&utm_medium=member_desktop")
    answer = _send(bot, f"worth an answer from me {link}")
    assert answer == SAID["bookmarked"]
    [item] = _items()
    assert (item["kind"], item["status"], item["text"]) == ("bookmark", "new", "worth an answer from me")
    assert item["link"] == "https://www.linkedin.com/feed/update/urn:li:activity:7390000000000000777/"
    stored = _everything_stored()
    for slug_word in ("strangewood", "pricing-secrets", "nobody-tells", "utm_source", "member_desktop"):
        assert slug_word not in stored, f"a post's slug was kept: {slug_word}"


def test_draft_prefix_goes_straight_to_a_draft_and_is_recorded_as_used(bot):
    _saved(bot)
    answer = _send(bot, "Draft: a finished post I wrote on the train")
    assert answer == SAID["draft"]
    assert _drafts() == ["a finished post I wrote on the train"]
    [item] = _items()
    assert (item["status"], item["text"]) == ("used", "a finished post I wrote on the train")
    assert item["post_id"] and item["post_id"].startswith("post-draft-")


def test_undo_takes_back_a_new_item_and_keeps_one_already_used(bot):
    _saved(bot)
    _send(bot, "first thought")
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered] == [SAID["undone_item"]])
    assert _items() == []
    _send(bot, "second thought")
    [item] = _items()
    assert bot["client"].post(f"/api/v1/collection/{item['id']}/draft").status_code == 200
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: len(bot["fake"].answered) == 2)
    assert bot["fake"].answered[1]["text"] == SAID["undo_item_kept"]
    assert [i["text"] for i in _items()] == ["second thought"]


def test_undo_of_a_draft_takes_its_item_with_it(bot):
    _saved(bot)
    _send(bot, "Draft: taken back at once")
    assert len(_items()) == 1
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered] == [SAID["undone"]])
    assert _drafts() == [] and _items() == [], "the collection still lists a draft taken back"


def test_each_arrival_and_each_change_is_published_for_the_studio(bot, monkeypatch):
    import changes
    published = []
    real = changes.publish
    monkeypatch.setattr(changes, "publish", lambda kind, **ids: (published.append(kind), real(kind, **ids)))
    _saved(bot)
    _send(bot, "live from the phone")
    assert "collection" in published, "an arrival was not published"
    published.clear()
    [item] = _items()
    bot["client"].post(f"/api/v1/collection/{item['id']}/status", json={"status": "not_now"})
    assert "collection" in published, "a change in the studio was not published"


def test_the_collection_lists_newest_first_with_counts_and_filters(bot):
    _saved(bot)
    for text in ("about hiring", "Idea: about pricing", "about pricing again"):
        _send(bot, text)
    listed = bot["client"].get("/api/v1/collection").json()
    assert [i["text"] for i in listed["items"]] == ["about pricing again", "about pricing", "about hiring"]
    assert listed["counts"] == {"new": 3, "not_now": 0, "used": 0, "all": 3}
    assert [i["text"] for i in bot["client"].get("/api/v1/collection?kind=idea").json()["items"]] == ["about pricing"]
    assert [i["text"] for i in bot["client"].get("/api/v1/collection?q=hiring").json()["items"]] == ["about hiring"]
    first = listed["items"][0]
    assert first["kind_said"] and first["received_at"] and first["became"] is None


def test_not_now_back_to_new_and_remove(bot):
    _saved(bot)
    _send(bot, "maybe later")
    [item] = _items()
    client = bot["client"]
    assert client.post(f"/api/v1/collection/{item['id']}/status", json={"status": "not_now"}).status_code == 200
    assert client.get("/api/v1/collection").json()["items"] == []
    assert [i["text"] for i in client.get("/api/v1/collection?status=not_now").json()["items"]] == ["maybe later"]
    assert client.post(f"/api/v1/collection/{item['id']}/status", json={"status": "new"}).status_code == 200
    assert client.post(f"/api/v1/collection/{item['id']}/status", json={"status": "used"}).status_code == 400, (
        "an item was marked used without anything made from it")
    assert client.delete(f"/api/v1/collection/{item['id']}").status_code == 200
    assert _items() == []
    assert client.delete(f"/api/v1/collection/{item['id']}").status_code == 404


def test_use_as_a_draft_writes_the_words_as_they_are_and_says_what_it_became(bot):
    _saved(bot)
    _send(bot, "a note to turn into a post")
    [item] = _items()
    made = bot["client"].post(f"/api/v1/collection/{item['id']}/draft").json()
    assert made["content"] == "a note to turn into a post"
    conn = get_db()
    try:
        post = conn.execute("SELECT content, status FROM posts WHERE id = ?", (made["id"],)).fetchone()
    finally:
        conn.close()
    assert (post["content"], post["status"]) == ("a note to turn into a post", "draft")
    [used] = _items()
    assert (used["status"], used["post_id"]) == ("used", made["id"]) and used["used_at"]
    listed = bot["client"].get("/api/v1/collection?status=used").json()["items"]
    assert listed[0]["became"] == {"kind": "draft", "post_id": made["id"], "said": "A draft in the Composer"}


def test_a_topic_is_one_of_the_creators_own_topics_that_the_words_name(bot):
    _saved(bot)
    assert bot["client"].put("/api/v1/record/setup/topics", json={"text": "pricing, hiring loops"}).status_code == 200
    _send(bot, "what I learned about hiring loops this week")
    _send(bot, "nothing on topic #Founders")
    _send(bot, "nothing on topic at all")
    assert [i["topic"] for i in _items()] == ["hiring loops", "founders", None]


def test_drafts_counts_the_drafts_made_from_what_was_sent(bot):
    _saved(bot)
    _send(bot, "Draft: one straight to a draft")
    _send(bot, "an idea to use")
    item = _items(status="new")[0]
    bot["client"].post(f"/api/v1/collection/{item['id']}/draft")
    assert _send(bot, "/drafts") == SAID["drafts"].format(count=2)


def test_a_video_is_not_kept_and_says_so(bot):
    """A photo and a voice note are kept as they are since item 4 (tests/test_phone_media.py); a video is not."""
    _saved(bot)
    assert _send(bot, None, video={"file_id": "video-1", "duration": 4}) == SAID["no_text"]
    assert _items() == [] and _drafts() == [], "a video left a placeholder behind"


def test_the_maintainers_simulate_route_lands_in_the_collection_too(bot, monkeypatch):
    # Dev mode after the bot's fixture, which clears it.
    monkeypatch.setenv("INOX_DEV_MODE", "1")
    res = bot["client"].post("/api/v1/ingress/simulate", json={"text": "Idea: from the tray"})
    assert res.status_code == 200 and res.json()["record"]["archetype"] == "Raw Idea"
    assert [(i["kind"], i["text"], i["source"]) for i in _items()] == [("idea", "from the tray", "studio")]
