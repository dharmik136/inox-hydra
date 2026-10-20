"""
Weekly slots the creator can change, with neutral names.
========================================================

FRONTEND D-4: Queue it offered one time, the next free slot, and the 13 fixed
slots carried the original author's labels for every creator ("Thursday
Architecture Playbook", "Wednesday Systems Review", "Sunday Career &
Strategy"). Slots could not be added, changed or removed, and the seeder
deleted and re-seeded the whole table whenever it held fewer than eight, so a
creator who trimmed their week would have had it put back on the next start.

Owner decision (D5): neutral defaults. Slots are editable from the Queue.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module  # noqa: E402
import database  # noqa: E402
import scheduler  # noqa: E402
from database import get_db  # noqa: E402

client = TestClient(app_module.app)

AUTHOR_WORDS = ("Architecture", "Systems", "Playbook", "Career", "Strategy", "Deep-Dive", "Kickoff",
                "Retrospective", "Peak Hook", "Pulse", "Thought", "Deep Thinking")


@pytest.fixture
def saved_slots():
    """The slots table as it was, put back afterwards."""
    conn = get_db()
    rows = [tuple(r) for r in conn.execute("SELECT day_of_week, time_slot, label, is_active FROM queue_slots")]
    flag = conn.execute("SELECT value FROM settings WHERE key = 'queue_slots_seeded'").fetchone()
    conn.close()
    yield
    conn = get_db()
    conn.execute("DELETE FROM queue_slots")
    conn.executemany("INSERT INTO queue_slots (day_of_week, time_slot, label, is_active) VALUES (?,?,?,?)", rows)
    if flag is None:
        conn.execute("DELETE FROM settings WHERE key = 'queue_slots_seeded'")
    conn.commit()
    conn.close()


def _labels():
    conn = get_db()
    try:
        return [r["label"] for r in conn.execute("SELECT label FROM queue_slots ORDER BY day_of_week, time_slot")]
    finally:
        conn.close()


def test_the_seeded_slots_carry_neutral_names(saved_slots):
    conn = get_db()
    conn.execute("DELETE FROM queue_slots")
    conn.execute("DELETE FROM settings WHERE key = 'queue_slots_seeded'")
    conn.commit()
    conn.close()
    database.seed_initial_data()

    labels = _labels()
    assert labels, "no slots were seeded on a new install"
    for label in labels:
        assert not any(word in label for word in AUTHOR_WORDS), label
    assert "Monday morning" in labels and "Monday evening" in labels


def test_the_old_default_names_are_renamed_in_place(saved_slots):
    conn = get_db()
    conn.execute("DELETE FROM queue_slots")
    conn.execute("DELETE FROM settings WHERE key = 'queue_slots_seeded'")
    conn.executemany(
        "INSERT INTO queue_slots (day_of_week, time_slot, label, is_active) VALUES (?,?,?,1)",
        [(d, "08:30", label) for d, label in enumerate(
            ["Monday Morning Kickoff", "Tuesday Peak Hook", "Wednesday Midweek Deep-Dive",
             "Thursday Architecture Playbook"])]
        + [(0, "17:30", "Monday Evening Read"), (1, "17:30", "Tuesday Evening Thought"),
           (2, "17:30", "Wednesday Systems Review"), (3, "17:30", "Thursday Evening Pulse"),
           (6, "07:00", "My own Sunday slot")],
    )
    conn.commit()
    conn.close()

    database.seed_initial_data()

    labels = _labels()
    assert "Thursday morning" in labels and "Wednesday evening" in labels
    assert "My own Sunday slot" in labels, "a label the creator wrote was changed"
    assert not [label for label in labels if any(word in label for word in AUTHOR_WORDS)]
    assert len(labels) == 9


def test_a_trimmed_week_is_not_put_back_on_the_next_start(saved_slots):
    conn = get_db()
    conn.execute("DELETE FROM queue_slots")
    conn.execute("INSERT INTO queue_slots (day_of_week, time_slot, label, is_active) VALUES (2, '12:00', 'Wednesday lunch', 1)")
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('queue_slots_seeded', '1')")
    conn.commit()
    conn.close()

    database.seed_initial_data()

    assert _labels() == ["Wednesday lunch"]


def test_the_scheduler_fallback_names_nobody():
    for label in (s["label"] for s in scheduler.DEFAULT_SLOTS):
        assert not any(word in label for word in AUTHOR_WORDS), label


def test_a_slot_can_be_added_changed_and_removed(saved_slots):
    added = client.post("/api/queue/slots", json={"day_of_week": 5, "time_slot": "07:15"})
    assert added.status_code == 200, added.text
    slot = added.json()["slot"]
    assert slot["label"] == "Saturday morning", "a new slot got no neutral name"

    changed = client.put(f"/api/queue/slots/{slot['id']}", json={"time_slot": "19:45", "label": "Weekend read"})
    assert changed.status_code == 200, changed.text
    rows = client.get("/api/queue/smart-slots").json()["slots"]
    mine = [s for s in rows if s["id"] == slot["id"]]
    assert mine and mine[0]["time_slot"] == "19:45" and mine[0]["label"] == "Weekend read"

    removed = client.delete(f"/api/queue/slots/{slot['id']}")
    assert removed.status_code == 200
    assert not [s for s in client.get("/api/queue/smart-slots").json()["slots"] if s["id"] == slot["id"]]
    assert client.delete(f"/api/queue/slots/{slot['id']}").status_code == 404


@pytest.mark.parametrize("body", [
    {"day_of_week": 7, "time_slot": "08:00"},
    {"day_of_week": 1, "time_slot": "25:00"},
    {"day_of_week": 1, "time_slot": "8am"},
    {"day_of_week": 1, "time_slot": "08:00", "label": "x" * 81},
])
def test_a_slot_that_is_not_a_weekly_time_is_refused(saved_slots, body):
    response = client.post("/api/queue/slots", json=body)
    assert response.status_code in (400, 422)


def test_two_slots_at_the_same_time_are_refused(saved_slots):
    first = client.post("/api/queue/slots", json={"day_of_week": 4, "time_slot": "06:10"})
    assert first.status_code == 200
    again = client.post("/api/queue/slots", json={"day_of_week": 4, "time_slot": "06:10"})
    assert again.status_code == 409
    assert "already" in again.json()["detail"]


def test_the_next_slot_follows_an_edited_week(saved_slots):
    conn = get_db()
    conn.execute("DELETE FROM queue_slots")
    conn.commit()
    conn.close()
    assert client.post("/api/queue/slots", json={"day_of_week": 3, "time_slot": "06:05", "label": "Only slot"}).status_code == 200
    slot = client.get("/api/queue/next-slot").json()["slot"]
    assert slot["label"] == "Only slot" and slot["time_slot"] == "06:05"
