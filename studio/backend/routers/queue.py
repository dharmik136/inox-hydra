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

from fastapi import APIRouter
from pydantic import BaseModel, Field

try:
    from ..database import get_db
    from ..scheduler import native_scheduler, parse_datetime_flexible
    from ..event_bus import event_bus
except ImportError:
    from database import get_db
    from scheduler import native_scheduler, parse_datetime_flexible
    from event_bus import event_bus

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
async def toggle_queue_pause(payload: Optional[QueuePausePayload] = None):
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

    await event_bus.publish("queue_status_changed", {"queue_paused": actual_state})
    msg = "Publishing queue paused." if actual_state else "Publishing queue resumed."
    return {
        "status": "success",
        "queue_paused": actual_state,
        "message": msg,
    }
