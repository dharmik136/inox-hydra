"""
What the creator asks is kept only when they ask for it to be, and their marks are the Library's writer.
=========================================================================================================

Cycle 4, track 7, batches 4 and 6 of the personalised daily ideas report,
and decisions 3 and 5. Nothing the creator asked of the studio used to
survive the answer. Now an ask is kept from explicit acts only: the Setup
fields, the section's ask box, a Composer instruction the creator ticked,
an "Idea:" from the phone, and More of this on a card. The marks (keep,
skip, hide, and the studio's used and posted) change which cards come back
and never a figure, and Kept, the section's second level, reads from the
keep marks: the writer the deferred Library lacked.
"""

import json
import os
import sqlite3
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

POSTS = [
    "Hiring is a product problem, not a recruiting problem. Here is what changed for us.",
    "Three things I learned hiring our first five engineers without a recruiter.",
    "Pricing is a design decision. Most teams treat it as a spreadsheet.",
    "We changed our hiring loop and the offers got better, not slower.",
    "Pricing pages lie less when the founder writes them herself.",
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    import results
    from database import init_db

    results.forget_cache()
    init_db()
    import app as app_module

    return TestClient(app_module.app)


def db():
    import paths

    conn = sqlite3.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def seed_posts():
    conn = db()
    for n, text in enumerate(POSTS):
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, first_seen_at, last_seen_at) "
                     "VALUES (?, ?, ?, 'archive', ?, ?)",
                     (f"urn:li:activity:7420000000000{n:06d}", text, f"2025-0{n + 1}-10T09:00:00+00:00", "2025-01-01", "2025-01-01"))
    conn.commit()
    conn.close()


def asks():
    conn = db()
    try:
        return [dict(r) for r in conn.execute("SELECT text, source, field, status FROM asks ORDER BY id")]
    finally:
        conn.close()


def build_today():
    import record_daily

    return record_daily.run_today()


def first_shown(client):
    cards = client.get("/api/v1/record").json()["cards"]
    return next(c for c in cards if c["status"] == "shown" and c["slot"] >= 1)


# ---------------------------------------------------------------------------
# Asks: explicit acts only
# ---------------------------------------------------------------------------

def test_the_ask_box_and_a_ticked_instruction_are_kept(client):
    assert client.post("/api/v1/record/asks", json={"text": "  pricing for a two person studio ", "source": "ask_box"}).status_code == 200
    assert client.post("/api/v1/record/asks", json={"text": "write about hiring loops", "source": "composer"}).status_code == 200
    assert asks() == [
        {"text": "pricing for a two person studio", "source": "ask_box", "field": None, "status": "open"},
        {"text": "write about hiring loops", "source": "composer", "field": None, "status": "open"},
    ]


@pytest.mark.parametrize("source", ["setup", "telegram", "archive_search", "more_of_this", "anything"])
def test_no_other_source_can_be_claimed_through_the_box(client, source):
    answer = client.post("/api/v1/record/asks", json={"text": "x marks the spot", "source": source})
    assert answer.status_code == 400
    assert asks() == []


def test_an_instruction_without_the_tick_keeps_nothing(client):
    """The Composer's route writes no ask by itself: the tick is the only way in."""
    answer = client.post("/api/ai/command", json={"command": "summarise my thinking on hiring loops"})
    assert answer.status_code == 200
    assert asks() == []
    panel = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "PromptPanel.tsx"), encoding="utf-8").read()
    assert "const [rememberAsk, setRememberAsk] = useState(false);" in panel, "the tick is not off by default"
    assert 'addRecordAsk(text, "composer")' in panel and "if (rememberAsk)" in panel


def test_the_same_ask_twice_is_one_ask(client):
    for _ in range(2):
        client.post("/api/v1/record/asks", json={"text": "pricing pages", "source": "ask_box"})
    assert len(asks()) == 1


def test_setup_fields_hold_one_answer_each_and_an_empty_one_retires_it(client):
    assert client.put("/api/v1/record/setup/topics", json={"text": "hiring, pricing"}).status_code == 200
    assert client.put("/api/v1/record/setup/topics", json={"text": "hiring, pricing, studios"}).status_code == 200
    assert client.put("/api/v1/record/setup/avoid", json={"text": "listicles"}).status_code == 200
    assert client.get("/api/v1/record/setup").json()["fields"] == {
        "topics": "hiring, pricing, studios", "audience": None, "avoid": "listicles"}
    assert client.put("/api/v1/record/setup/topics", json={"text": ""}).status_code == 200
    assert client.get("/api/v1/record/setup").json()["fields"]["topics"] is None
    assert client.put("/api/v1/record/setup/favourite_colour", json={"text": "blue"}).status_code == 400
    assert [a["status"] for a in asks() if a["field"] == "topics"] == ["retired"]


def test_an_ask_can_be_edited_retired_and_removed(client):
    client.post("/api/v1/record/asks", json={"text": "hiring loops", "source": "ask_box"})
    ask_id = client.get("/api/v1/record/knows").json()["asks"][0]["id"]
    assert client.put(f"/api/v1/record/asks/{ask_id}", json={"text": "hiring loops for small teams"}).status_code == 200
    assert client.put(f"/api/v1/record/asks/{ask_id}", json={"status": "retired"}).status_code == 200
    assert asks() == [{"text": "hiring loops for small teams", "source": "ask_box", "field": None, "status": "retired"}]
    assert client.put(f"/api/v1/record/asks/{ask_id}", json={"text": ""}).status_code == 400
    assert client.delete(f"/api/v1/record/asks/{ask_id}").status_code == 200
    assert asks() == []


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------

def test_the_creator_keeps_skips_and_hides_and_the_studio_writes_used_and_posted(client):
    seed_posts()
    build_today()
    card = first_shown(client)
    ref = {"day": card["day"], "card_id": card["card_id"]}
    for studio_mark in ("used", "posted"):
        assert client.post("/api/v1/record/marks", json={**ref, "mark": studio_mark}).status_code == 400
    assert "tomorrow" in client.post("/api/v1/record/marks", json={**ref, "mark": "keep"}).json()["message"]
    shown = next(c for c in client.get("/api/v1/record").json()["cards"] if c["card_id"] == card["card_id"])
    assert shown["marks"] == ["keep"]
    # Skip after keep is not two opinions: it replaces it.
    client.post("/api/v1/record/marks", json={**ref, "mark": "skip"})
    shown = next(c for c in client.get("/api/v1/record").json()["cards"] if c["card_id"] == card["card_id"])
    assert shown["marks"] == ["skip"]
    client.post("/api/v1/record/marks", json={**ref, "mark": "hide"})
    knows = client.get("/api/v1/record/knows").json()
    assert knows["marks"]["hide"] == 1 and knows["hidden"][0]["card_id"] == card["card_id"]
    assert client.post("/api/v1/record/unhide-all").json()["cards"] == 1
    assert client.get("/api/v1/record/knows").json()["marks"]["hide"] == 0


def test_a_mark_changes_no_figure(client):
    seed_posts()
    build_today()
    before = client.get("/api/v1/record").json()["cards"]
    for card in before:
        if card["status"] == "shown":
            client.post("/api/v1/record/marks", json={"day": card["day"], "card_id": card["card_id"], "mark": "keep"})
    after = client.get("/api/v1/record").json()["cards"]
    strip = lambda cards: [(c["card_id"], json.dumps(c["payload"], sort_keys=True)) for c in cards]  # noqa: E731
    assert strip(before) == strip(after)


def test_more_of_this_writes_the_cards_topic_as_an_ask(client):
    seed_posts()
    build_today()
    cards = client.get("/api/v1/record").json()["cards"]
    theme = next(c for c in cards if c["kind"] in ("theme", "on_this_day", "opener") and c["status"] == "shown")
    answer = client.post("/api/v1/record/more", json={"day": theme["day"], "card_id": theme["card_id"]})
    assert answer.status_code == 200, answer.text
    kept = asks()
    assert kept and kept[-1]["source"] == "more_of_this"
    assert kept[-1]["text"] in ("Hiring", "Pricing") or len(kept[-1]["text"]) > 10


def test_draft_from_this_records_the_card_and_posting_it_writes_posted(client):
    seed_posts()
    client.post("/api/v1/record/asks", json={"text": "hiring without a recruiter", "source": "ask_box"})
    build_today()
    card = next(c for c in client.get("/api/v1/record").json()["cards"] if c["kind"] == "ask")
    drafted = client.post("/api/v1/record/draft", json={"day": card["day"], "card_id": card["card_id"]})
    assert drafted.status_code == 200, drafted.text
    post_id = drafted.json()["id"]
    assert drafted.json()["content"] == "hiring without a recruiter"
    conn = db()
    row = conn.execute("SELECT status, origin_card_id, origin_day FROM posts WHERE id = ?", (post_id,)).fetchone()
    assert dict(row) == {"status": "draft", "origin_card_id": card["card_id"], "origin_day": card["day"]}
    marks = [dict(r) for r in conn.execute("SELECT mark, post_id FROM card_marks WHERE card_id = ?", (card["card_id"],))]
    assert marks == [{"mark": "used", "post_id": post_id}]
    # The post goes out by any path: the trigger writes the studio's mark.
    conn.execute("UPDATE posts SET status = 'published', published_at = '2026-10-26T10:00:00+00:00' WHERE id = ?", (post_id,))
    conn.commit()
    marks = sorted(r["mark"] for r in conn.execute("SELECT mark FROM card_marks WHERE card_id = ?", (card["card_id"],)))
    conn.close()
    assert marks == ["posted", "used"]
    # The draft opens like any other in the Composer.
    assert client.get("/api/posts?status=draft&limit=50").status_code == 200


def test_kept_reads_from_the_keep_marks_and_hides_what_is_hidden(client):
    seed_posts()
    build_today()
    card = first_shown(client)
    ref = {"day": card["day"], "card_id": card["card_id"]}
    assert client.get("/api/v1/record/kept").json()["kept"] == []
    client.post("/api/v1/record/marks", json={**ref, "mark": "keep"})
    kept = client.get("/api/v1/record/kept").json()["kept"]
    assert [k["card_id"] for k in kept] == [card["card_id"]]
    assert kept[0]["payload"] == card["payload"]
    client.post("/api/v1/record/marks", json={**ref, "mark": "hide"})
    assert client.get("/api/v1/record/kept").json()["kept"] == []


# ---------------------------------------------------------------------------
# The page that shows what the studio knows, and its settings
# ---------------------------------------------------------------------------

def test_what_the_studio_knows_lists_everything_the_section_holds(client):
    seed_posts()
    client.post("/api/v1/record/asks", json={"text": "pricing pages", "source": "ask_box"})
    client.put("/api/v1/record/setup/audience", json={"text": "founders of small studios"})
    build_today()
    knows = client.get("/api/v1/record/knows").json()
    assert [a["text"] for a in knows["asks"]] == ["founders of small studios", "pricing pages"] or \
        {a["text"] for a in knows["asks"]} == {"founders of small studios", "pricing pages"}
    assert knows["setup"]["audience"] == "founders of small studios"
    assert set(knows["marks"]) == {"keep", "skip", "hide", "used", "posted"}
    assert knows["batches"]["days"] == 1
    assert knows["settings"]["keep_days"] == "365" and knows["settings"]["cost_ceiling_usd"] == 0.10
    assert knows["job"]["today_built"] is True


@pytest.mark.parametrize("changes", [
    {"keep_days": "7"}, {"model_stage": "maybe"}, {"cost_ceiling_usd": -1}, {"cost_ceiling_usd": 99},
    {"cost_ceiling_usd": "ten cents"}, {"nonsense": 1},
])
def test_settings_refuse_what_they_do_not_offer(client, changes):
    assert client.put("/api/v1/record/settings", json={"changes": changes}).status_code == 400


def test_settings_keep_what_they_offer(client):
    answer = client.put("/api/v1/record/settings", json={"changes": {"keep_days": "90", "cost_ceiling_usd": 0.25,
                                                                         "model_stage": "off"}})
    assert answer.status_code == 200
    assert answer.json() | {} == {**answer.json(), "keep_days": "90", "cost_ceiling_usd": 0.25, "model_stage": "off"}


def test_reading_the_section_writes_nothing(client):
    seed_posts()
    client.get("/api/v1/record")
    client.get("/api/v1/record/knows")
    client.get("/api/v1/record/kept")
    conn = db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM daily_run").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM daily_view").fetchone()[0] == 0
    finally:
        conn.close()


def test_a_monthly_note_is_kept_and_removed(client):
    assert client.post("/api/v1/record/notes", json={"month": "2026-10", "text": "The pricing card helped."}).status_code == 200
    assert client.get("/api/v1/record/knows").json()["notes"][0]["text"] == "The pricing card helped."
    assert client.post("/api/v1/record/notes", json={"month": "2026-13", "text": "x"}).status_code in (400, 422)
    assert client.post("/api/v1/record/notes", json={"month": "2026-10", "text": ""}).status_code == 200
    assert client.get("/api/v1/record/knows").json()["notes"] == []


# ---------------------------------------------------------------------------
# The screen holds the shape the section promises
# ---------------------------------------------------------------------------

def test_the_screen_has_one_heading_three_levels_and_the_ask_box():
    ui = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")
    surface = open(os.path.join(ui, "RecordSurface.tsx"), encoding="utf-8").read()
    assert surface.count("<h1") == 1
    for level in ('"Today"', '"Kept"', '"What the studio knows"'):
        assert level in surface, f"the {level} level is missing"
    assert "Remember this ask" in surface and 'addRecordAsk(text.trim(), "ask_box")' in surface
    card = open(os.path.join(ui, "RecordCardView.tsx"), encoding="utf-8").read()
    for control in ("Keep", "Skip", "Hide", "More of this", "Draft from this", "Why this?"):
        assert control in card, f"the card has no {control}"
    setup = open(os.path.join(ui, "OnboardingSurface.tsx"), encoding="utf-8").read()
    assert "<RecordSetupFields />" in setup, "Setup does not offer the three questions"
    fields = open(os.path.join(ui, "RecordSetupFields.tsx"), encoding="utf-8").read()
    assert fields.count("why: \"") == 3 and "Skip" in fields
