"""
Make something out of the collection: Make a post, Combine, Angles.
==================================================================

Phase 3 of the Telegram bot, item 2, in the studio (docs/quality/cycle4/
collection-box.md). On an item: Make a post writes a draft from it in the
creator's voice through their own provider and puts it in the Composer;
Angles offers the creator's number of opening lines; on several: Combine
writes one draft from all of them. With no provider, each says so plainly
and nothing is written. Nothing invented: an answer carrying a figure or a
person known to the studio that is not in what was sent is refused, never
repaired.

Every choice a request makes is the creator's preference (the owner's
direction of 2026-10-29): each one changes what the provider is sent, and
a fresh profile gets its default. Command and Re-Hook read the same ones.

Against a fake provider on loopback (tests/ai_fake.py), through the model
gateway and its egress check.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

from ai_fake import FakeProvider  # noqa: E402

DASH = chr(0x2014)


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    monkeypatch.delenv("INOX_NO_EGRESS", raising=False)
    for key in ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    from database import init_db
    import app as app_module

    init_db()
    return TestClient(app_module.app)


@pytest.fixture
def provider(studio):
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"draft": "Pricing is a design decision.\n\nWrite the price page first."}
    yield fake
    fake.close()


def _item(text, kind="note"):
    import collection
    return collection.add(kind, text)["id"]


def _items():
    from database import get_db
    conn = get_db()
    try:
        return {r["id"]: dict(r) for r in conn.execute("SELECT * FROM collection_items")}
    finally:
        conn.close()


def _post(post_id):
    from database import get_db
    conn = get_db()
    try:
        row = conn.execute("SELECT content, status, tags FROM posts WHERE id = ?", (post_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def test_make_a_post_writes_a_draft_from_the_item_into_the_composer(studio, provider):
    item = _item("pricing is a design decision, not a finance one")
    other = _item("hiring loops for a team of three")
    res = studio.post("/api/v1/collection/write", json={"items": [item]})
    assert res.status_code == 200, res.text
    made = res.json()
    assert made["status"] == "drafted" and made["content"] == "Pricing is a design decision.\n\nWrite the price page first."
    assert _post(made["id"])["status"] == "draft"
    items = _items()
    assert (items[item]["status"], items[item]["post_id"]) == ("used", made["id"])
    assert items[other]["status"] == "new"
    sent = provider.sent()
    assert "pricing is a design decision, not a finance one" in sent
    assert "hiring loops" not in sent, "another item went with the request"


def test_combine_writes_one_draft_from_several_items(studio, provider):
    first, second = _item("pricing for small studios"), _item("Idea: the cost of saying yes", kind="idea")
    made = studio.post("/api/v1/collection/write", json={"items": [first, second]}).json()
    assert made["status"] == "drafted"
    items = _items()
    assert items[first]["post_id"] == items[second]["post_id"] == made["id"]
    sent = provider.sent()
    assert "pricing for small studios" in sent and "the cost of saying yes" in sent
    assert "together" in sent, "the request did not ask for one post from them all"


def test_combine_takes_at_most_ten(studio, provider):
    ids = [_item(f"note number {n}") for n in range(11)]
    res = studio.post("/api/v1/collection/write", json={"items": ids})
    assert res.status_code == 400 and "ten" in res.json()["detail"]


def test_angles_offers_the_creators_number_of_opening_lines_and_keeps_them(studio, provider):
    item = _item("pricing is a design decision")
    provider.answer = {"angles": ["Your price page is a design brief.", "Stop letting finance name your price.",
                                  "The cheapest page to write is the price."]}
    res = studio.post(f"/api/v1/collection/{item}/angles")
    assert res.status_code == 200, res.text
    assert res.json()["angles"] == provider.answer["angles"]
    assert "3 different opening lines" in provider.sent()
    assert json.loads(_items()[item]["angles"]) == provider.answer["angles"]
    assert _items()[item]["status"] == "new", "offering angles used the item"


def test_a_draft_from_an_angle_starts_from_it(studio, provider):
    item = _item("pricing is a design decision")
    studio.post("/api/v1/collection/write", json={"items": [item], "angle": "Your price page is a design brief."})
    assert "Your price page is a design brief." in provider.sent()


def test_with_no_provider_each_says_so_and_nothing_is_written(studio):
    item = _item("a thought with no provider")
    for res in (studio.post("/api/v1/collection/write", json={"items": [item]}),
                studio.post(f"/api/v1/collection/{item}/angles")):
        assert res.status_code == 200
        assert res.json()["status"] == "no_provider"
        assert "No AI provider is set up" in res.json()["said"] and "as it is" in res.json()["said"]
    assert _items()[item]["status"] == "new" and _items()[item]["post_id"] is None


@pytest.mark.parametrize("answer, what", [
    ("Pricing doubled our revenue to 42 percent in 3 weeks.", "figure"),
    ("Jane Strangewood taught me that pricing is design.", "name"),
])
def test_an_invented_figure_or_a_known_name_is_refused_never_repaired(studio, provider, answer, what):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO leads (id, name, full_name, lead_status) VALUES ('l1', 'Jane Strangewood', "
                     "'Jane Strangewood', 'NEW')")
    conn.close()
    item = _item("pricing is a design decision")
    provider.answer = {"draft": answer}
    made = studio.post("/api/v1/collection/write", json={"items": [item]}).json()
    assert made["status"] == "refused" and what in made["said"], made
    assert _items()[item]["status"] == "new" and _items()[item]["post_id"] is None, "a refused draft was kept"


def test_a_figure_the_note_gives_is_kept(studio, provider):
    item = _item("we cut our price page from 9 sections to 3")
    provider.answer = {"draft": "We cut our price page from 9 sections to 3. Sales calls got shorter."}
    assert studio.post("/api/v1/collection/write", json={"items": [item]}).json()["status"] == "drafted"


def test_em_dashes_are_cleaned_from_what_the_provider_wrote(studio, provider):
    item = _item("pricing is a design decision")
    provider.answer = {"draft": f"Pricing is design {DASH} not finance."}
    made = studio.post("/api/v1/collection/write", json={"items": [item]}).json()
    assert DASH not in made["content"]


def test_requests_are_counted_under_model_and_refused_with_no_egress(studio, provider, monkeypatch):
    import egress
    item = _item("pricing is a design decision")
    before = next(c for c in egress.describe()["categories"] if c["name"] == "model")["performed"]
    studio.post("/api/v1/collection/write", json={"items": [item]})
    after = next(c for c in egress.describe()["categories"] if c["name"] == "model")["performed"]
    assert after == before + 1
    monkeypatch.setenv("INOX_NO_EGRESS", "1")
    other = _item("refused here")
    res = studio.post("/api/v1/collection/write", json={"items": [other]})
    assert res.status_code == 503 and "off on this machine" in res.json()["detail"]
    assert len(provider.requests) == 1


def test_a_provider_that_refuses_is_said_in_plain_words_and_nothing_changes(studio, provider):
    item = _item("pricing is a design decision")
    provider.fail = 401
    res = studio.post("/api/v1/collection/write", json={"items": [item]})
    assert res.status_code == 502 and "refused the key" in res.json()["detail"]
    assert _items()[item]["status"] == "new"


# ---------------------------------------------------------------------------
# Every choice is the creator's preference
# ---------------------------------------------------------------------------

def test_a_fresh_profile_gets_every_default(studio):
    import writing
    described = studio.get("/api/v1/writing/preferences").json()
    assert described["values"] == writing.DEFAULTS
    assert described["defaults"] == writing.DEFAULTS


PREFERENCES = [
    ("length_words", 300, "About 300 words"),
    ("tone", "warm, plain and a little dry", "warm, plain and a little dry"),
    ("language", "Gujarati", "Write in Gujarati"),
    ("opening", "Hard Lesson", "Hard Lesson"),
    ("emojis", "few", "at most two emojis"),
    ("hashtags", "none", "no hashtags"),
    ("line_breaks", "one_per_line", "one sentence per line"),
    ("ending", "takeaway", "one clear takeaway"),
    ("avoid", ["synergy", "leverage"], "'synergy', 'leverage'"),
]


@pytest.mark.parametrize("field, value, words", PREFERENCES)
def test_each_preference_changes_what_the_provider_is_sent(studio, provider, field, value, words):
    import writing
    item = _item("pricing is a design decision")
    studio.post("/api/v1/collection/write", json={"items": [item]})
    fresh = provider.sent()
    default_words = writing.words_for(writing.DEFAULTS)[field]
    assert default_words in fresh, f"a fresh profile's request lacks the default {field}"
    assert words not in fresh
    res = studio.put("/api/v1/writing/preferences", json={field: value})
    assert res.status_code == 200, res.text
    assert res.json()["values"][field] == value
    studio.post("/api/v1/collection/write", json={"items": [_item("another note on pricing")]})
    assert words in provider.sent(), f"changing {field} did not change what the provider was sent"


def test_the_number_of_angles_is_the_creators(studio, provider):
    item = _item("pricing is a design decision")
    provider.answer = {"angles": ["One.", "Two.", "Three.", "Four."]}
    studio.put("/api/v1/writing/preferences", json={"angles": 4})
    assert len(studio.post(f"/api/v1/collection/{item}/angles").json()["angles"]) == 4
    assert "4 different opening lines" in provider.sent()


@pytest.mark.parametrize("change", [{"length_words": 7}, {"angles": 9}, {"emojis": "lots"}, {"tone": "x" * 300},
                                    {"opening": "Something Else"}, {"avoid": ["y" * 200]}])
def test_a_preference_outside_its_choices_is_refused_and_nothing_is_saved(studio, change):
    import writing
    res = studio.put("/api/v1/writing/preferences", json=change)
    assert res.status_code in (400, 422), res.text
    assert studio.get("/api/v1/writing/preferences").json()["values"] == writing.DEFAULTS


def test_command_reads_the_same_preferences(studio, provider):
    import writing
    provider.answer = "A rewritten post."
    studio.post("/api/ai/command", json={"command": "tighten this", "context": "my draft"})
    system = provider.system()
    for field in ("tone", "line_breaks", "opening", "ending"):
        assert writing.words_for(writing.DEFAULTS)[field] in system, field
    studio.put("/api/v1/writing/preferences", json={"tone": "warm and plain", "language": "Hindi",
                                                    "avoid": ["synergy"]})
    studio.post("/api/ai/command", json={"command": "tighten this", "context": "my draft"})
    system = provider.system()
    assert "warm and plain" in system and "Hindi" in system and "'synergy'" in system


def test_rehook_reads_tone_language_and_words_to_avoid(studio, provider):
    provider.answer = [{"archetype": "Hard Lesson", "hook": f"Hook {n}"} for n in range(10)]
    studio.put("/api/v1/writing/preferences", json={"tone": "warm and plain", "language": "Hindi",
                                                    "avoid": ["synergy"]})
    res = studio.post("/api/format/re-hook", json={"text": "pricing is a design decision"})
    assert res.status_code == 200, res.text
    sent = provider.sent()
    assert "warm and plain" in sent and "Hindi" in sent and "'synergy'" in sent


def test_what_the_model_is_told_names_the_words_to_avoid_from_the_preference(studio):
    studio.put("/api/v1/writing/preferences", json={"avoid": ["synergy", "delve"]})
    told = studio.get("/api/v1/composer/told").json()
    assert told["scar_tissue"]["named_in_command"] == ["synergy", "delve"]
