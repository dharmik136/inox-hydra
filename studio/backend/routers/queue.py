"""
Smart Queue and Native Scheduler Router.
========================================
Handles peak engagement scheduling, smart slots calculation, cadence validation,
and automated publishing queue pause/resume controls.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
- 100% local SQLite state with zero cloud egress.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from ..database import get_db, neutral_slot_label
    from ..scheduler import native_scheduler, parse_datetime_flexible, DAY_NAMES
except ImportError:
    from database import get_db, neutral_slot_label
    from scheduler import native_scheduler, parse_datetime_flexible, DAY_NAMES

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

        return {
            "status": "success",
            "slots": slots,
            "scheduled_posts": scheduled_posts,
        }
    finally:
        conn.close()


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
