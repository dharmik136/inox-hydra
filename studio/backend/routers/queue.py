"""
Smart Queue and Native Scheduler Router.
========================================
Handles peak engagement scheduling, smart slots calculation, cadence validation,
and automated publishing queue pause/resume controls.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
- 100% local SQLite state with zero cloud egress.
"""

from datetime import date, datetime, timedelta, timezone
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

try:
    from ..database import get_db, neutral_slot_label
    from ..scheduler import native_scheduler, parse_datetime_flexible, DAY_NAMES
    from .. import today as today_module
    from ..text_cut import clip
except ImportError:
    from database import get_db, neutral_slot_label
    from scheduler import native_scheduler, parse_datetime_flexible, DAY_NAMES
    import today as today_module
    from text_cut import clip

router = APIRouter()


class CadenceValidationPayload(BaseModel):
    scheduled_for: str
    post_id: Optional[str] = None


class QueuePausePayload(BaseModel):
    paused: Optional[bool] = None


@router.get("/api/queue/smart-slots", tags=["Smart Queue"])
def get_smart_slots():
    """Returns active queue slots and upcoming scheduled posts."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM queue_slots WHERE is_active = 1 ORDER BY day_of_week, time_slot")
        slots = [dict(r) for r in cursor.fetchall()]

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for s in slots:
            s["day_name"] = day_names[s["day_of_week"]]

        cursor.execute(
            "SELECT id, content, scheduled_for FROM posts WHERE status = 'scheduled' ORDER BY scheduled_for ASC"
        )
        scheduled_posts = [dict(r) for r in cursor.fetchall()]
        excerpts = {r["id"]: r["content"] for r in conn.execute(
            "SELECT id, content FROM posts WHERE status IN ('scheduled', 'due', 'published')")}
    finally:
        conn.close()
    # Each queued post's nearest neighbour inside the cadence rule, by the
    # rule the publish dialog warns with (validate_schedule_cadence): which
    # post, when, and how far apart. None when nothing is that close.
    for post in scheduled_posts:
        post["collision"] = None
        if not post["scheduled_for"]:
            continue
        check = native_scheduler.validate_schedule_cadence(post["scheduled_for"], post_id=post["id"])
        nearest = check.get("nearest_conflict")
        distance = check.get("distance_to_nearest_hours")
        if nearest and distance is not None and distance < native_scheduler.min_cooldown_hours:
            post["collision"] = {
                "other_id": nearest.get("id"),
                "other_excerpt": clip(" ".join((excerpts.get(nearest.get("id")) or "").split()), 80) or None,
                "other_status": nearest.get("status"),
                "other_at": nearest.get("datetime"),
                "distance_hours": round(distance, 1),
                "kind": "duplicate" if distance < 0.08 else "cadence",
            }
    return {
        "status": "success",
        "slots": slots,
        "scheduled_posts": scheduled_posts,
    }


class SlotPayload(BaseModel):
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    time_slot: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    label: Optional[str] = Field(None, max_length=80)


def _slot(conn, slot_id: int) -> Dict[str, Any]:
    row = conn.execute("SELECT * FROM queue_slots WHERE id = ?", (slot_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="There is no such slot. Reload the Queue.")
    return dict(row)


def _refuse_duplicate(conn, day: int, time_slot: str, slot_id: Optional[int] = None) -> None:
    row = conn.execute(
        "SELECT id FROM queue_slots WHERE day_of_week = ? AND time_slot = ? AND is_active = 1 AND id IS NOT ?",
        (day, time_slot, slot_id),
    ).fetchone()
    if row:
        raise HTTPException(
            status_code=409,
            detail=f"There is already a slot on {DAY_NAMES[day]} at {time_slot}.",
        )


@router.post("/api/queue/slots", tags=["Smart Queue"])
def add_queue_slot(payload: SlotPayload):
    """
    Adds a weekly slot, a local wall-clock time on one day of the week. With
    no label it is named for the day and the part of the day.
    """
    if payload.day_of_week is None or payload.time_slot is None:
        raise HTTPException(status_code=400, detail="A slot needs a day and a time, such as Tuesday 08:30.")
    label = (payload.label or "").strip() or neutral_slot_label(payload.day_of_week, payload.time_slot)
    conn = get_db()
    try:
        with conn:
            _refuse_duplicate(conn, payload.day_of_week, payload.time_slot)
            cursor = conn.execute(
                "INSERT INTO queue_slots (day_of_week, time_slot, label, is_active) VALUES (?, ?, ?, 1)",
                (payload.day_of_week, payload.time_slot, label),
            )
            slot = _slot(conn, cursor.lastrowid)
    finally:
        conn.close()
    slot["day_name"] = DAY_NAMES[slot["day_of_week"]]
    return {"status": "success", "slot": slot}


@router.put("/api/queue/slots/{slot_id}", tags=["Smart Queue"])
def update_queue_slot(slot_id: int, payload: SlotPayload):
    """Changes a slot's day, time or name. Posts already queued keep their times."""
    conn = get_db()
    try:
        with conn:
            slot = _slot(conn, slot_id)
            day = slot["day_of_week"] if payload.day_of_week is None else payload.day_of_week
            time_slot = slot["time_slot"] if payload.time_slot is None else payload.time_slot
            label = slot["label"] if payload.label is None else (payload.label.strip() or neutral_slot_label(day, time_slot))
            _refuse_duplicate(conn, day, time_slot, slot_id)
            conn.execute(
                "UPDATE queue_slots SET day_of_week = ?, time_slot = ?, label = ? WHERE id = ?",
                (day, time_slot, label, slot_id),
            )
            slot = _slot(conn, slot_id)
    finally:
        conn.close()
    slot["day_name"] = DAY_NAMES[slot["day_of_week"]]
    return {"status": "success", "slot": slot}


@router.delete("/api/queue/slots/{slot_id}", tags=["Smart Queue"])
def delete_queue_slot(slot_id: int):
    """Removes a weekly slot. Posts already queued for it keep their times."""
    conn = get_db()
    try:
        with conn:
            _slot(conn, slot_id)
            conn.execute("DELETE FROM queue_slots WHERE id = ?", (slot_id,))
    finally:
        conn.close()
    return {"status": "success", "deleted": slot_id}


@router.get("/api/queue/next-slot", tags=["Smart Queue"])
def get_next_smart_slot(from_time: Optional[str] = None):
    """Calculates the chronologically next optimal smart slot with 12h cooldown clearance."""
    cursor_dt = parse_datetime_flexible(from_time) if from_time else None
    slot = native_scheduler.calculate_next_smart_slot(from_time=cursor_dt)
    return {"status": "success", "slot": slot}


@router.get("/api/queue/due", tags=["Smart Queue"])
def get_due_posts():
    """
    Queued posts whose time has come, with why one was missed when it was.

    today.due_posts is the one place that reads the due status; Today and the
    Queue both call it, so the Queue no longer builds its own list from the
    generic posts endpoint, which carried no missed note at all. Today shows
    the first ten; this screen's job is to show what is due, so it asks for
    every one. Both callers took the same limit of ten, and a creator with
    eleven due posts saw ten here with nothing saying one was held back.
    """
    conn = get_db()
    try:
        return {"status": "success", "due": today_module.due_posts(conn, limit=None)}
    finally:
        conn.close()


def _local_day(moment: Optional[str]) -> Optional[str]:
    """The creator's own calendar day of a stored time, on this machine's clock."""
    parsed = parse_datetime_flexible(moment) if moment else None
    return parsed.astimezone().date().isoformat() if parsed else None


@router.get("/api/queue/calendar", tags=["Smart Queue"])
def get_queue_calendar(month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")):
    """
    A month of your posts by your own calendar day: published (from what the
    bridge read of your posts), scheduled, due, and missed, which the queue
    now keeps after a missed post moves on (queue_dispatches). With your own
    counts by weekday for the month and by month for the last twelve, and no
    best day: the counts are what you did, not a recommendation.
    """
    year, number = (int(part) for part in month.split("-"))
    first = date(year, number, 1)
    after = date(year + (number == 12), number % 12 + 1, 1)
    # The month's bounds on this machine's clock, read a day wider in UTC so
    # every time that falls on one of its local days is in reach.
    low = (datetime(first.year, first.month, first.day) - timedelta(days=1)).isoformat()
    high = (datetime(after.year, after.month, after.day) + timedelta(days=1)).isoformat()
    days: Dict[str, List[Dict[str, Any]]] = {}

    def add(kind: str, at: Optional[str], words: Optional[str], ref: str, **extra: Any) -> None:
        day = _local_day(at)
        if not day or not (first.isoformat() <= day < after.isoformat()):
            return
        days.setdefault(day, []).append({"kind": kind, "at": at, "ref": ref,
                                         "excerpt": clip(" ".join((words or "").split()), 80) or None, **extra})

    conn = get_db()
    try:
        for r in conn.execute("SELECT activity_urn, text, published_at FROM own_posts "
                              "WHERE published_at >= ? AND published_at < ?", (low, high)):
            add("published", r["published_at"], r["text"], r["activity_urn"])
        for r in conn.execute("SELECT id, content, status, scheduled_for FROM posts "
                              "WHERE status IN ('scheduled', 'due') AND scheduled_for >= ? AND scheduled_for < ?",
                              (low, high)):
            add(r["status"], r["scheduled_for"], r["content"], r["id"])
        texts = {r["id"]: r["content"] for r in conn.execute("SELECT id, content FROM posts")}
        for r in conn.execute("SELECT post_id, scheduled_for, late_minutes, resolution FROM queue_dispatches "
                              "WHERE outcome = 'missed_due' AND scheduled_for >= ? AND scheduled_for < ?",
                              (low, high)):
            add("missed", r["scheduled_for"], texts.get(r["post_id"]), r["post_id"],
                late_minutes=r["late_minutes"], resolution=r["resolution"])
        months: List[Dict[str, Any]] = []
        for back in range(11, -1, -1):
            index = year * 12 + number - 1 - back
            start = date(index // 12, index % 12 + 1, 1)
            end = date((index + 1) // 12, (index + 1) % 12 + 1, 1)
            count = sum(1 for (at,) in conn.execute(
                "SELECT published_at FROM own_posts WHERE published_at >= ? AND published_at < ?",
                ((datetime(start.year, start.month, start.day) - timedelta(days=1)).isoformat(),
                 (datetime(end.year, end.month, end.day) + timedelta(days=1)).isoformat()))
                if start.isoformat() <= (_local_day(at) or "") < end.isoformat())
            months.append({"month": start.strftime("%Y-%m"), "published": count})
    finally:
        conn.close()
    for items in days.values():
        items.sort(key=lambda item: item["at"] or "")
    counts = {kind: sum(1 for items in days.values() for item in items if item["kind"] == kind)
              for kind in ("published", "scheduled", "due", "missed")}
    by_weekday = [0] * 7
    for day, items in days.items():
        by_weekday[date.fromisoformat(day).weekday()] += sum(1 for item in items if item["kind"] == "published")
    return {"status": "success", "month": month, "first_weekday": first.weekday(),
            "days_in_month": (after - first).days, "days": days, "counts": counts,
            "by_weekday": by_weekday, "months": months}


@router.get("/api/queue/cadence-health", tags=["Smart Queue"])
def get_cadence_health():
    """Returns global cadence health score (0-100%) and queue collision analysis."""
    overview = native_scheduler.get_cadence_overview()
    return overview


@router.post("/api/queue/validate-cadence", tags=["Smart Queue"])
def validate_queue_cadence(payload: CadenceValidationPayload):
    """Validates proposed scheduling timestamp against the 12-hour cooldown rule."""
    result = native_scheduler.validate_schedule_cadence(payload.scheduled_for, post_id=payload.post_id)
    return {"status": "success", "validation": result}


@router.post("/api/v1/scheduler/dispatch/now", tags=["LinkedIn Native Scheduler"])
def trigger_scheduler_dispatch():
    """Forces an immediate on-demand evaluation of the scheduled queue and grace window recovery."""
    actions = native_scheduler.check_scheduled_queue()
    return {
        "status": "success",
        "actions": actions,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/queue/status", tags=["Smart Queue"])
def get_queue_status():
    """Returns whether the automated publishing queue is active or paused."""
    return {
        "status": "success",
        "queue_paused": native_scheduler.is_queue_paused(),
    }


@router.post("/api/queue/toggle-pause", tags=["Smart Queue"])
def toggle_queue_pause(payload: Optional[QueuePausePayload] = None):
    """Toggles or sets the automated publishing queue pause state."""
    current = native_scheduler.is_queue_paused()
    new_state = payload.paused if (payload and payload.paused is not None) else not current

    wrote = native_scheduler.set_queue_paused(new_state)
    actual_state = native_scheduler.is_queue_paused()

    if not wrote or actual_state != new_state:
        return {
            "status": "error",
            "queue_paused": actual_state,
            "message": (
                "Could not change the queue state. It is still "
                + ("paused" if actual_state else "running")
                + ". Check studio/logs for the database error."
            ),
        }

    msg = "Publishing queue paused." if actual_state else "Publishing queue resumed."
    return {
        "status": "success",
        "queue_paused": actual_state,
        "message": msg,
    }
