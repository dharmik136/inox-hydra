"""
Inox Hydra: Smart Cadence & Native Scheduler Engine Test Suite
==============================================================
Validates:
- 12-Hour Cooldown & Anti-Cannibalization Protection
- Dynamic Smart Slot Allocation from Active Matrix
- Flexible Datetime Parsing (ISO-8601, UTC, Local offsets)
- On-Time Dispatch Loop (<= 5m overdue)
- Morning Grace Window Self-Healing Recovery (5m - 120m overdue)
- Stale Post Algorithmic Roll-Forward (> 120m overdue)
- REST API Queue Endpoints (/api/queue/* and /api/v1/scheduler/dispatch/now)
- Strict Zero Em-Dash Prohibition across all Scheduler Components
"""

import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import init_db, seed_initial_data, get_db
from scheduler import (
    native_scheduler,
    parse_datetime_flexible,
    normalize_datetime_to_utc_iso,
    MIN_COOLDOWN_HOURS,
    GRACE_WINDOW_MINUTES,
    ON_TIME_THRESHOLD_MINUTES,
    DAY_NAMES
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db_state():
    """Ensures database is initialized and seeded before each test."""
    init_db()
    seed_initial_data()
    yield
    init_db()
    seed_initial_data()


def test_parse_datetime_flexible():
    """Verifies that flexible datetime parsing handles multiple valid formats and rejects garbage."""
    # UTC with Z
    dt1 = parse_datetime_flexible("2026-09-22T08:30:00Z")
    assert dt1 is not None
    assert dt1.tzinfo is not None
    assert dt1.year == 2026 and dt1.month == 9 and dt1.day == 22

    # ISO without timezone
    dt2 = parse_datetime_flexible("2026-09-22T17:30:00")
    assert dt2 is not None
    assert dt2.hour == 17 and dt2.minute == 30

    # Space separator
    dt3 = parse_datetime_flexible("2026-09-22 14:00:00")
    assert dt3 is not None
    assert dt3.hour == 14 and dt3.minute == 0

    # Date only
    dt4 = parse_datetime_flexible("2026-09-22")
    assert dt4 is not None
    assert dt4.hour == 0 and dt4.minute == 0

    # Garbage formats return None
    assert parse_datetime_flexible("not-a-datetime") is None
    assert parse_datetime_flexible("") is None
    assert parse_datetime_flexible(None) is None


def test_next_smart_slot_calculation():
    """Verifies that next smart slot calculation returns a future slot with >= 12h cooldown clearance."""
    now = datetime.now(timezone.utc)
    slot = native_scheduler.calculate_next_smart_slot(from_time=now)

    assert "slot_datetime" in slot
    assert "day_name" in slot
    assert "time_slot" in slot
    assert "label" in slot
    assert slot["cooldown_satisfied"] is True

    slot_dt = parse_datetime_flexible(slot["slot_datetime"])
    assert slot_dt is not None
    assert slot_dt >= now


def test_12h_cooldown_collision_detection():
    """Verifies that scheduling within 12 hours of another scheduled post flags a collision."""
    conn = get_db()
    cursor = conn.cursor()
    target_dt = (datetime.now(timezone.utc) + timedelta(days=14)).replace(hour=10, minute=0, second=0, microsecond=0)
    post_a_time = target_dt.isoformat()
    post_a_id = f"test_a_{uuid.uuid4().hex[:6]}"

    cursor.execute("""
    INSERT INTO posts (id, content, status, scheduled_for)
    VALUES (?, 'Test Post A for Cooldown', 'scheduled', ?)
    """, (post_a_id, post_a_time))
    conn.commit()
    conn.close()

    try:
        # Check collision: post B scheduled 3 hours after post A (< 12 hours)
        post_b_colliding = (target_dt + timedelta(hours=3)).isoformat()
        val_colliding = native_scheduler.validate_schedule_cadence(post_b_colliding)
        assert val_colliding["valid"] is True
        assert val_colliding["has_collision"] is True
        assert val_colliding["cadence_health_score"] < 100
        assert val_colliding["conflicting_post_id"] == post_a_id
        assert "warning" in val_colliding

        # Check safe spacing: post C scheduled 20 hours after post A (>= 12 hours)
        post_c_safe = (target_dt + timedelta(hours=20)).isoformat()
        val_safe = native_scheduler.validate_schedule_cadence(post_c_safe)
        assert val_safe["valid"] is True
        assert val_safe["has_collision"] is False
        assert val_safe["cadence_health_score"] == 100
    finally:
        conn = get_db()
        conn.cursor().execute("DELETE FROM posts WHERE id = ?", (post_a_id,))
        conn.commit()
        conn.close()


def test_on_time_publishing():
    """Verifies that overdue posts within 5 minutes are dispatched as published on time."""
    conn = get_db()
    cursor = conn.cursor()
    test_id = f"test_ontime_{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc)
    due_time = (now - timedelta(minutes=2)).isoformat()

    cursor.execute("""
    INSERT INTO posts (id, content, status, scheduled_for)
    VALUES (?, 'On time test post', 'scheduled', ?)
    """, (test_id, due_time))
    conn.commit()
    conn.close()

    try:
        actions = native_scheduler.check_scheduled_queue()
        matching = [a for a in actions if a["post_id"] == test_id]
        assert len(matching) == 1
        assert matching[0]["action"] == "published_on_time"

        # Verify DB status updated
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT status, published_at FROM posts WHERE id = ?", (test_id,))
        row = cursor.fetchone()
        conn.close()

        assert row["status"] == "published"
        assert row["published_at"] is not None
    finally:
        conn = get_db()
        conn.cursor().execute("DELETE FROM posts WHERE id = ?", (test_id,))
        conn.commit()
        conn.close()


def test_morning_grace_window_recovery():
    """Verifies that posts overdue by 5 to 120 minutes are recovered and published via morning grace window."""
    conn = get_db()
    cursor = conn.cursor()
    test_id = f"test_grace_{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc)
    due_time = (now - timedelta(minutes=45)).isoformat()

    cursor.execute("""
    INSERT INTO posts (id, content, status, scheduled_for)
    VALUES (?, 'Grace window test post', 'scheduled', ?)
    """, (test_id, due_time))
    conn.commit()
    conn.close()

    try:
        actions = native_scheduler.check_scheduled_queue()
        matching = [a for a in actions if a["post_id"] == test_id]
        assert len(matching) == 1
        assert matching[0]["action"] == "grace_dispatched"
        assert matching[0]["overdue_minutes"] >= 40.0

        # Verify DB status
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT status, published_at FROM posts WHERE id = ?", (test_id,))
        row = cursor.fetchone()
        conn.close()

        assert row["status"] == "published"
        assert row["published_at"] is not None
    finally:
        conn = get_db()
        conn.cursor().execute("DELETE FROM posts WHERE id = ?", (test_id,))
        conn.commit()
        conn.close()


def test_stale_post_roll_forward_recovery():
    """Verifies that posts overdue by > 120 minutes are kept as scheduled and rolled forward to next smart slot."""
    conn = get_db()
    cursor = conn.cursor()
    test_id = f"test_stale_{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc)
    due_time = (now - timedelta(hours=4)).isoformat()

    cursor.execute("""
    INSERT INTO posts (id, content, status, scheduled_for)
    VALUES (?, 'Stale overdue test post', 'scheduled', ?)
    """, (test_id, due_time))
    conn.commit()
    conn.close()

    try:
        actions = native_scheduler.check_scheduled_queue()
        matching = [a for a in actions if a["post_id"] == test_id]
        assert len(matching) == 1
        assert matching[0]["action"] == "rolled_forward"
        assert "new_scheduled_for" in matching[0]

        # Verify DB status
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT status, scheduled_for, published_at FROM posts WHERE id = ?", (test_id,))
        row = cursor.fetchone()
        conn.close()

        assert row["status"] == "scheduled"
        assert row["published_at"] is None
        assert row["scheduled_for"] > now.isoformat()
    finally:
        conn = get_db()
        conn.cursor().execute("DELETE FROM posts WHERE id = ?", (test_id,))
        conn.commit()
        conn.close()


def test_cadence_overview_calculation():
    """Verifies that get_cadence_overview returns expected health score and queue counts."""
    overview = native_scheduler.get_cadence_overview()
    assert overview["status"] == "success"
    assert "total_scheduled" in overview
    assert "cadence_health_score" in overview
    assert "collision_count" in overview
    assert "next_smart_slot" in overview
    assert isinstance(overview["cadence_health_score"], (int, float))


def test_api_queue_endpoints():
    """Verifies all Smart Queue REST endpoints."""
    # 1. GET /api/queue/next-slot
    res1 = client.get("/api/queue/next-slot")
    assert res1.status_code == 200
    json1 = res1.json()
    assert json1["status"] == "success"
    assert "slot" in json1
    assert "slot_datetime" in json1["slot"]

    # 2. GET /api/queue/cadence-health
    res2 = client.get("/api/queue/cadence-health")
    assert res2.status_code == 200
    json2 = res2.json()
    assert json2["status"] == "success"
    assert "cadence_health_score" in json2

    # 3. POST /api/queue/validate-cadence (valid format)
    target_iso = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT08:30:00")
    res3 = client.post("/api/queue/validate-cadence", json={"scheduled_for": target_iso})
    assert res3.status_code == 200
    json3 = res3.json()
    assert json3["status"] == "success"
    assert json3["validation"]["valid"] is True

    # 4. POST /api/queue/validate-cadence (invalid format)
    res4 = client.post("/api/queue/validate-cadence", json={"scheduled_for": "invalid-datetime-string"})
    assert res4.status_code == 200
    json4 = res4.json()
    assert json4["status"] == "success"
    assert json4["validation"]["valid"] is False

    # 5. POST /api/v1/scheduler/dispatch/now
    res5 = client.post("/api/v1/scheduler/dispatch/now")
    assert res5.status_code == 200
    json5 = res5.json()
    assert json5["status"] == "success"
    assert "actions" in json5
    assert "executed_at" in json5


def test_post_creation_with_cadence():
    """Verifies that creating a post with invalid schedule returns HTTP 400."""
    # Invalid format returns 400
    bad_payload = {
        "content": "Testing invalid schedule format",
        "status": "scheduled",
        "scheduled_for": "unparseable-date"
    }
    bad_res = client.post("/api/posts", json=bad_payload)
    assert bad_res.status_code == 400

    # Valid format returns 200 and cadence metadata
    good_time = (datetime.now(timezone.utc) + timedelta(days=4)).strftime("%Y-%m-%dT08:30:00")
    good_payload = {
        "content": "Testing valid schedule format with cadence analysis",
        "status": "scheduled",
        "scheduled_for": good_time
    }
    good_res = client.post("/api/posts", json=good_payload)
    assert good_res.status_code == 200
    good_json = good_res.json()
    assert good_json["status"] == "success"
    assert "cadence" in good_json

    post_id = good_json["id"]
    client.delete(f"/api/posts/{post_id}")


def test_normalize_datetime_to_utc_iso():
    """Verifies that arbitrary datetime strings are canonicalized into UTC ISO-8601 strings."""
    # Positive offset (+05:30)
    iso_offset = normalize_datetime_to_utc_iso("2026-09-22T15:30:00+05:30")
    assert iso_offset is not None
    assert iso_offset == "2026-09-22T10:00:00+00:00"

    # UTC with Z
    iso_z = normalize_datetime_to_utc_iso("2026-09-22T10:00:00Z")
    assert iso_z is not None
    assert iso_z == "2026-09-22T10:00:00+00:00"

    # Space separated format
    iso_space = normalize_datetime_to_utc_iso("2026-09-22 14:00:00")
    assert iso_space is not None
    assert iso_space == "2026-09-22T14:00:00+00:00"

    # Invalid input
    assert normalize_datetime_to_utc_iso("invalid-date") is None
    assert normalize_datetime_to_utc_iso(None) is None


def test_duplicate_slot_collision_warning():
    """Verifies that scheduling within 5 minutes of another post generates a duplicate slot collision warning."""
    conn = get_db()
    cursor = conn.cursor()
    target_dt = datetime.now(timezone.utc) + timedelta(days=2)
    post_a_time = target_dt.strftime("%Y-%m-%dT10:00:00+00:00")
    post_a_id = f"test_dup_{uuid.uuid4().hex[:6]}"

    cursor.execute("""
    INSERT INTO posts (id, content, status, scheduled_for)
    VALUES (?, 'Test Post A for Duplicate Detection', 'scheduled', ?)
    """, (post_a_id, post_a_time))
    conn.commit()
    conn.close()

    try:
        # Schedule post B 2 minutes after post A (< 5m gap)
        post_b_time = (target_dt + timedelta(minutes=2)).strftime("%Y-%m-%dT10:02:00+00:00")
        val = native_scheduler.validate_schedule_cadence(post_b_time)
        assert val["valid"] is True
        assert val["has_collision"] is True
        assert "Duplicate slot collision" in val["warning"]
        assert "Simultaneous publishing" in val["warning"]
    finally:
        conn = get_db()
        conn.cursor().execute("DELETE FROM posts WHERE id = ?", (post_a_id,))
        conn.commit()
        conn.close()


def test_queue_status_and_toggle_pause_api():
    """Verifies emergency queue pause and resume functionality via API and daemon suppression."""
    # 1. Initial state should be active (not paused)
    res = client.get("/api/queue/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "queue_paused" in data
    assert data["queue_paused"] is False

    # 2. Pause the queue
    res_pause = client.post("/api/queue/toggle-pause", json={"paused": True})
    assert res_pause.status_code == 200
    assert res_pause.json()["status"] == "success"
    assert res_pause.json()["queue_paused"] is True
    assert native_scheduler.is_queue_paused() is True

    # 3. Insert an overdue scheduled post
    conn = get_db()
    cursor = conn.cursor()
    test_id = f"test_pause_{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc)
    due_time = (now - timedelta(minutes=2)).isoformat()

    cursor.execute("""
    INSERT INTO posts (id, content, status, scheduled_for)
    VALUES (?, 'Paused queue post', 'scheduled', ?)
    """, (test_id, due_time))
    conn.commit()
    conn.close()

    try:
        # Dispatch while paused should return empty list and leave post untouched
        actions = native_scheduler.check_scheduled_queue()
        assert actions == []

        # Post status must remain scheduled
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM posts WHERE id = ?", (test_id,))
        row = cursor.fetchone()
        conn.close()
        assert row["status"] == "scheduled"

        # 4. Resume queue
        res_resume = client.post("/api/queue/toggle-pause", json={"paused": False})
        assert res_resume.status_code == 200
        assert res_resume.json()["queue_paused"] is False
        assert native_scheduler.is_queue_paused() is False

        # Dispatch should now process the overdue post
        actions_after = native_scheduler.check_scheduled_queue()
        matching = [a for a in actions_after if a["post_id"] == test_id]
        assert len(matching) == 1
        assert matching[0]["action"] == "published_on_time"
    finally:
        conn = get_db()
        conn.cursor().execute("DELETE FROM posts WHERE id = ?", (test_id,))
        conn.commit()
        conn.close()
        native_scheduler.set_queue_paused(False)


def test_post_content_length_limit_5000_chars():
    """Verifies that posts exceeding the 5,000-character payload limit are rejected with HTTP 400."""
    # 5,001 characters should fail
    oversized_content = "X" * 5001
    res_bad = client.post("/api/posts", json={
        "content": oversized_content,
        "status": "draft"
    })
    assert res_bad.status_code == 400
    assert "character limit" in res_bad.json()["detail"].lower()

    # 5,000 characters should succeed
    valid_content = "Y" * 5000
    res_good = client.post("/api/posts", json={
        "content": valid_content,
        "status": "draft"
    })
    assert res_good.status_code == 200
    post_id = res_good.json()["id"]

    try:
        # Updating with oversized content should also return HTTP 400
        res_update_bad = client.put(f"/api/posts/{post_id}", json={
            "content": oversized_content,
            "status": "draft"
        })
        assert res_update_bad.status_code == 400
        assert "character limit" in res_update_bad.json()["detail"].lower()
    finally:
        client.delete(f"/api/posts/{post_id}")


def test_canonical_utc_db_storage():
    """Verifies scheduled_for is saved in canonical UTC format for exact SQLite lexicographical queries."""
    local_scheduled = "2026-11-15T18:45:00+05:30"
    res = client.post("/api/posts", json={
        "content": "Canonical UTC timestamp storage verification",
        "status": "scheduled",
        "scheduled_for": local_scheduled
    })
    assert res.status_code == 200
    post_id = res.json()["id"]

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT scheduled_for FROM posts WHERE id = ?", (post_id,))
        row = cursor.fetchone()
        conn.close()

        stored_time = row["scheduled_for"]
        # UTC equivalent of 18:45 +05:30 is 13:15 UTC
        assert "13:15:00+00:00" in stored_time

        # Verify SQLite text query works as expected
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM posts WHERE scheduled_for <= '2026-11-15T13:16:00+00:00' AND id = ?", (post_id,))
        matched = cursor.fetchone()
        conn.close()
        assert matched is not None
        assert matched["id"] == post_id
    finally:
        client.delete(f"/api/posts/{post_id}")


def test_reschedule_post_api():
    """Verifies direct rescheduling endpoint without altering post content or wiping composer."""
    init_time = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT09:00:00+00:00")
    create_res = client.post("/api/posts", json={
        "content": "Post to be rescheduled",
        "status": "scheduled",
        "scheduled_for": init_time
    })
    assert create_res.status_code == 200
    post_id = create_res.json()["id"]

    try:
        # Reschedule with valid future date
        new_time = (datetime.now(timezone.utc) + timedelta(days=6)).strftime("%Y-%m-%dT14:00:00+00:00")
        resched_res = client.post(f"/api/posts/{post_id}/reschedule", json={"scheduled_for": new_time})
        assert resched_res.status_code == 200
        resched_data = resched_res.json()
        assert resched_data["status"] == "success"
        assert resched_data["cadence_health_score"] == 100

        # Verify in database that scheduled_for was updated to the normalized UTC time
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT scheduled_for, status FROM posts WHERE id = ?", (post_id,))
        row = cursor.fetchone()
        conn.close()
        assert row["status"] == "scheduled"
        assert "14:00:00+00:00" in row["scheduled_for"]

        # Reschedule with invalid date format -> 400
        bad_res = client.post(f"/api/posts/{post_id}/reschedule", json={"scheduled_for": "garbage-date"})
        assert bad_res.status_code == 400

        # Reschedule non-existent post -> 404
        missing_res = client.post("/api/posts/non-existent-uuid/reschedule", json={"scheduled_for": new_time})
        assert missing_res.status_code == 404
    finally:
        client.delete(f"/api/posts/{post_id}")


def test_publish_post_now_endpoint():
    """Verifies that creators can immediately publish a queued post or draft via API."""
    sched_time = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT09:00:00+00:00")
    create_res = client.post("/api/posts", json={
        "content": "Post to publish immediately from queue",
        "status": "scheduled",
        "scheduled_for": sched_time
    })
    assert create_res.status_code == 200
    post_id = create_res.json()["id"]

    try:
        # Publish now succeeds
        pub_res = client.post(f"/api/posts/{post_id}/publish-now")
        assert pub_res.status_code == 200
        pub_data = pub_res.json()
        assert pub_data["status"] == "success"
        assert pub_data["post_id"] == post_id
        assert "published_at" in pub_data

        # Database record must now be published with published_at timestamp
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT status, published_at FROM posts WHERE id = ?", (post_id,))
        row = cursor.fetchone()
        conn.close()
        assert row["status"] == "published"
        assert row["published_at"] is not None

        # Publishing an already published post returns 400
        dup_res = client.post(f"/api/posts/{post_id}/publish-now")
        assert dup_res.status_code == 400
        assert "already published" in dup_res.json()["detail"].lower()

        # Publishing non-existent post returns 404
        missing_res = client.post("/api/posts/missing-id-xyz/publish-now")
        assert missing_res.status_code == 404
    finally:
        client.delete(f"/api/posts/{post_id}")


def test_zero_em_dashes_in_scheduler_module():
    """Ensures strict adherence to the Zero Em-Dash Rule across all scheduler components."""
    forbidden = "\u2014"
    files_to_check = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend", "scheduler.py")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend", "app.py")),
        os.path.abspath(__file__),
    ]

    for fpath in files_to_check:
        with open(fpath, "r", encoding="utf-8") as fh:
            content = fh.read()
            assert forbidden not in content, f"Forbidden em-dash found in {fpath}!"



def test_smart_slot_uses_local_wall_clock_times():
    """Verifies smart slots are interpreted as creator-local wall-clock times and returned as UTC instants."""
    slot = native_scheduler.calculate_next_smart_slot()

    slot_dt = parse_datetime_flexible(slot["slot_datetime"])
    assert slot_dt is not None
    assert slot_dt.tzinfo is not None
    assert "local_datetime" in slot

    slot_local = slot_dt.astimezone()
    if slot["label"] != "24-Hour Cooldown Buffer Slot":
        active_slots = native_scheduler.get_active_slots()
        matching = [
            s for s in active_slots
            if s["day_of_week"] == slot_local.weekday()
            and s["time_slot"] == slot_local.strftime("%H:%M")
        ]
        assert matching, (
            f"Returned slot {slot_local.isoformat()} does not correspond to any "
            f"active slot definition interpreted in local time"
        )
        assert slot["day_name"] == DAY_NAMES[slot_local.weekday()]
        assert slot["time_slot"] == slot_local.strftime("%H:%M")
