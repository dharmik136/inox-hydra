"""
Plan it from the phone: when a draft comes back.
================================================

Phase 5 of the Telegram bot, item 2 (docs/quality/cycle4/bot-phase5.md).
Under "Draft ready" the bot offers Plan it: a few times, a press, and the
draft is in the Queue at that time. Planning only says when the creator wants
the post back: at that time the Queue's own scheduler marks it due, as for any
queued post, and the bot's due reminder brings it back, with Send me the
whole post while the words switch is on.

What this never does: post anything, call Send to LinkedIn or anything that
reaches LinkedIn, move a post the Composer queued, or move a post LinkedIn
holds (a post handed over with Send to LinkedIn, recorded as
`linkedin_holds:<id>`, which LinkedIn publishes itself). It reads the
scheduler's slots and its spacing rule and changes nothing of it: a plan is
the post's status and queue time, written in one conditional update, and a
note on the draft's made_with saying it was planned from the phone.

The times offered are the creator's preference (PLAN_KEY), with a plain
default: the Queue's next open slots, found as the Queue finds its next open
slot (at least AHEAD_MINUTES ahead, and the Queue's own cooldown from any
other queued, due or published post), or, with none, the creator's own times,
by default tomorrow at 09:00 and at 18:00.

Strict Invariants:
- Zero em-dashes.
- Nothing here reaches the network.
"""

import json
import re
from datetime import date, datetime, timedelta, timezone
from datetime import time as day_time
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import changes
    from .database import get_db
except ImportError:
    import changes
    from database import get_db

# The creator's preference: what Plan it offers. {from, slots, times}.
PLAN_KEY = "telegram_plan"
SLOT_COUNTS = (1, 2, 3, 4)
TIMES_MAX = 4
DAYS_AHEAD = tuple(range(0, 15))
PLAN_DEFAULT: Dict[str, Any] = {
    "from": "slots",
    "slots": 3,
    "times": [{"days": 1, "at": "09:00"}, {"days": 1, "at": "18:00"}],
}
# How many lines a list on the bot shows (/plan, and /recall from item 3).
LIST_KEY = "telegram_list_at_most"
LIST_DEFAULT = 5
LIST_CHOICES = tuple(range(1, 11))
# The Queue's own rule for its next open slot (scheduler.calculate_next_smart_slot):
# at least this far ahead. A time nearer than that is not offered.
AHEAD_MINUTES = 15
# How far ahead the Queue's slots are walked, as the Queue walks them.
SLOT_DAYS = 14
# A post handed to LinkedIn's own scheduler (scheduler.LINKEDIN_HOLDS_KEY).
HOLDS_PREFIX = "linkedin_holds:"

_CLOCK = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class Refused(ValueError):
    """A preference the bot will not keep, with the sentence that says why."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _instant(text: Any) -> Optional[datetime]:
    if not text:
        return None
    try:
        when = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def said_time(when: datetime, now: datetime) -> str:
    """A moment as a button and a message say it, on the computer's clock: "Today 17:30", "Wed 4 Nov, 08:30"."""
    local, today = when.astimezone(), now.astimezone().date()
    clock = local.strftime("%H:%M")
    if local.date() == today:
        return f"Today {clock}"
    if local.date() == today + timedelta(days=1):
        return f"Tomorrow {clock}"
    return f"{local.strftime('%a')} {local.day} {local.strftime('%b')}, {clock}"


def full_time(when: datetime) -> str:
    """A moment as a confirmation says it, whole: "Tue 3 Nov, 08:30"."""
    local = when.astimezone()
    return f"{local.strftime('%a')} {local.day} {local.strftime('%b')}, {local.strftime('%H:%M')}"


# ---------------------------------------------------------------------------
# The preferences
# ---------------------------------------------------------------------------

def _setting(conn, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _valid_time(entry: Any) -> bool:
    return (isinstance(entry, dict) and set(entry) == {"days", "at"} and entry["days"] in DAYS_AHEAD
            and not isinstance(entry["days"], bool) and isinstance(entry["at"], str)
            and bool(_CLOCK.match(entry["at"])))


def _valid_plan(value: Any) -> bool:
    return (isinstance(value, dict) and set(value) == {"from", "slots", "times"} and value["from"] in ("slots", "times")
            and value["slots"] in SLOT_COUNTS and not isinstance(value["slots"], bool)
            and isinstance(value["times"], list) and 1 <= len(value["times"]) <= TIMES_MAX
            and all(_valid_time(t) for t in value["times"]))


def _clean_time(entry: Dict[str, Any]) -> Dict[str, Any]:
    hour, minute = entry["at"].split(":")
    return {"days": entry["days"], "at": f"{int(hour):02d}:{minute}"}


def plan_offers(conn=None) -> Dict[str, Any]:
    """What Plan it offers, in the open profile: the creator's choice, or the default."""
    own = conn is None
    conn = conn or get_db()
    try:
        raw = _setting(conn, PLAN_KEY)
    finally:
        if own:
            conn.close()
    try:
        held = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        held = None
    if not _valid_plan(held):
        return json.loads(json.dumps(PLAN_DEFAULT))
    return {"from": held["from"], "slots": held["slots"], "times": [_clean_time(t) for t in held["times"]]}


def check_plan_offers(value: Any) -> Dict[str, Any]:
    """The value to keep, or Refused with the sentence the panel shows. Nothing is kept here."""
    if isinstance(value, dict) and isinstance(value.get("times"), list):
        value = {**value, "times": [{"days": t.get("days"), "at": str(t.get("at") or "").strip()}
                                    if isinstance(t, dict) else t for t in value["times"]]}
    if not _valid_plan(value):
        raise Refused(f"Plan it offers your Queue's next {SLOT_COUNTS[0]} to {SLOT_COUNTS[-1]} open slots, or 1 to "
                      f"{TIMES_MAX} times of your own, each a number of days from today (0 to {DAYS_AHEAD[-1]}) and a "
                      "time such as 09:00. Nothing was saved.")
    return {"from": value["from"], "slots": value["slots"], "times": [_clean_time(t) for t in value["times"]]}


def list_at_most(conn=None) -> int:
    """How many lines /plan's and /recall's lists show, in the open profile."""
    own = conn is None
    conn = conn or get_db()
    try:
        raw = _setting(conn, LIST_KEY)
    finally:
        if own:
            conn.close()
    try:
        value = int(raw) if raw is not None else LIST_DEFAULT
    except (TypeError, ValueError):
        value = LIST_DEFAULT
    return value if value in LIST_CHOICES else LIST_DEFAULT


def check_list_at_most(value: Any) -> int:
    if isinstance(value, bool) or value not in LIST_CHOICES:
        raise Refused(f"A list on the bot shows {LIST_CHOICES[0]} to {LIST_CHOICES[-1]} lines at most. Nothing was "
                      "saved.")
    return int(value)


# ---------------------------------------------------------------------------
# The times offered
# ---------------------------------------------------------------------------

def _existing(post_id: Optional[str]) -> List[datetime]:
    """The times of every other queued, due or published post, as the Queue's spacing rule reads them."""
    try:
        from .scheduler import native_scheduler
    except ImportError:
        from scheduler import native_scheduler
    return [when for when, other, _status in native_scheduler.get_existing_post_datetimes(exclude_post_id=post_id)]


def _cooldown_hours() -> float:
    try:
        from .scheduler import MIN_COOLDOWN_HOURS
    except ImportError:
        from scheduler import MIN_COOLDOWN_HOURS
    return float(MIN_COOLDOWN_HOURS)


def _open_slots(post_id: Optional[str], now: datetime, wanted: int) -> List[datetime]:
    """
    The Queue's next open slots, up to `wanted`: each of the creator's weekly
    slots on the coming days, on the computer's clock, at least AHEAD_MINUTES
    ahead and the Queue's cooldown from any other post, as the Queue finds
    its next open slot. They are alternatives, so they need no room between
    them.
    """
    try:
        from .scheduler import native_scheduler
    except ImportError:
        from scheduler import native_scheduler
    slots = native_scheduler.get_active_slots()
    others = _existing(post_id)
    cooldown = _cooldown_hours()
    found: List[datetime] = []
    today = now.astimezone().date()
    for offset in range(SLOT_DAYS):
        day = today + timedelta(days=offset)
        for slot in sorted((s for s in slots if s.get("day_of_week") == day.weekday()),
                           key=lambda s: str(s.get("time_slot"))):
            try:
                hour, minute = (int(part) for part in str(slot["time_slot"]).split(":")[:2])
            except (KeyError, TypeError, ValueError):
                continue
            when = datetime(day.year, day.month, day.day, hour, minute).astimezone()
            if when <= now + timedelta(minutes=AHEAD_MINUTES):
                continue
            if any(abs((when - other).total_seconds()) / 3600.0 < cooldown for other in others):
                continue
            found.append(when)
            if len(found) >= wanted:
                return found
    return found


def _own_times(times: List[Dict[str, Any]], now: datetime) -> List[datetime]:
    """The creator's own times, each so many days from today at its time; one already past, or too near, is left out."""
    found = []
    today = now.astimezone().date()
    for entry in times:
        hour, minute = (int(part) for part in entry["at"].split(":"))
        day = today + timedelta(days=int(entry["days"]))
        when = datetime.combine(day, day_time(hour=hour, minute=minute)).astimezone()
        if when > now + timedelta(minutes=AHEAD_MINUTES) and when not in found:
            found.append(when)
    return sorted(found)


def offered_times(post_id: Optional[str], now: datetime) -> Tuple[List[datetime], str]:
    """
    The times Plan it offers now, and where they came from: "slots" (the
    Queue's next open slots), "times" (the creator's own), or "instead" (the
    creator's own, because the Queue had no open slot to offer).
    """
    offers = plan_offers()
    if offers["from"] == "slots":
        found = _open_slots(post_id, now, offers["slots"])
        if found:
            return found, "slots"
        return _own_times(offers["times"], now), "instead"
    return _own_times(offers["times"], now), "times"


# ---------------------------------------------------------------------------
# A plan: the post in the Queue at a time, in one conditional update
# ---------------------------------------------------------------------------

def _made(raw: Any) -> Dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        value = {}
    return value if isinstance(value, dict) else {}


def _held_by_linkedin(conn, post_id: str) -> bool:
    return conn.execute("SELECT 1 FROM settings WHERE key = ?", (HOLDS_PREFIX + post_id,)).fetchone() is not None


def state_of(post_id: Any) -> Dict[str, Any]:
    """
    Whether a post can be planned from the phone: {status: draft | planned
    (queued from the phone at its planned time, so it may be planned again)
    | queued | posted | gone, at}.
    """
    conn = get_db()
    try:
        return _state(conn, str(post_id or ""))
    finally:
        conn.close()


def _state(conn, post_id: str) -> Dict[str, Any]:
    row = conn.execute("SELECT status, scheduled_for, published_at, activity_urn, made_with FROM posts WHERE id = ?",
                       (post_id,)).fetchone()
    if row is None:
        return {"status": "gone"}
    if row["published_at"] or row["activity_urn"] or row["status"] in ("published", "sent"):
        return {"status": "posted"}
    if _held_by_linkedin(conn, post_id):
        return {"status": "queued", "at": row["scheduled_for"]}
    if row["status"] == "draft" and not row["scheduled_for"]:
        return {"status": "draft"}
    planned = _made(row["made_with"]).get("planned")
    if (row["status"] == "scheduled" and isinstance(planned, dict) and planned.get("for")
            and planned.get("for") == row["scheduled_for"]):
        return {"status": "planned", "at": row["scheduled_for"]}
    return {"status": "queued", "at": row["scheduled_for"]}


def plan(post_id: Any, when: Any) -> Dict[str, Any]:
    """
    Puts a draft in the Queue at `when`, from the phone: one conditional
    update, so a draft queued, published, handed to LinkedIn or changed in
    the meantime is left as it is. A draft planned from the phone may be
    planned again while it is still queued at its planned time. Returns
    {status: planned | past | gone | posted | queued | changed, for,
    near (another post within the Queue's cooldown), paused}.
    """
    moment = _instant(when)
    post_id = str(post_id or "")
    if moment is None:
        return {"status": "changed"}
    if moment <= _now():
        return {"status": "past"}
    at = moment.astimezone(timezone.utc).isoformat()
    conn = get_db()
    try:
        state = _state(conn, post_id)
        if state["status"] not in ("draft", "planned"):
            return {"status": state["status"]}
        made = _made(conn.execute("SELECT made_with FROM posts WHERE id = ?", (post_id,)).fetchone()[0])
        made["planned"] = {"for": at, "at": _now().isoformat(), "from": "telegram"}
        with conn:
            if state["status"] == "draft":
                done = conn.execute(
                    "UPDATE posts SET status = 'scheduled', scheduled_for = ?, made_with = ? WHERE id = ? "
                    "AND status = 'draft' AND scheduled_for IS NULL AND published_at IS NULL AND activity_urn IS NULL "
                    "AND NOT EXISTS (SELECT 1 FROM settings WHERE key = ?)",
                    (at, json.dumps(made), post_id, HOLDS_PREFIX + post_id)).rowcount
            else:
                done = conn.execute(
                    "UPDATE posts SET scheduled_for = ?, made_with = ? WHERE id = ? AND status = 'scheduled' "
                    "AND scheduled_for = ? AND published_at IS NULL AND activity_urn IS NULL "
                    "AND NOT EXISTS (SELECT 1 FROM settings WHERE key = ?)",
                    (at, json.dumps(made), post_id, state["at"], HOLDS_PREFIX + post_id)).rowcount
    finally:
        conn.close()
    if not done:
        return {"status": "changed"}
    changes.publish("queue")
    return {"status": "planned", "for": at, **_around(post_id, at)}


def _around(post_id: str, at: str) -> Dict[str, Any]:
    """What is true about a planned time worth saying: another post near it, a paused Queue."""
    try:
        from .scheduler import native_scheduler
    except ImportError:
        from scheduler import native_scheduler
    try:
        near = bool(native_scheduler.validate_schedule_cadence(at, post_id=post_id).get("has_collision"))
    except Exception:
        near = False
    return {"near": near, "paused": bool(native_scheduler.is_queue_paused())}


def series_slots(post_ids: List[str], now: datetime) -> List[datetime]:
    """
    The Queue's next open slots for a series (phase 6, item 5), one a part, in
    order: each of the creator's weekly slots on the coming days, at least
    AHEAD_MINUTES ahead, after the part before, and the Queue's cooldown from
    every other queued, due or published post and from every part before it.
    Fewer than the parts when the Queue has no more room in SLOT_DAYS.
    """
    try:
        from .scheduler import native_scheduler
    except ImportError:
        from scheduler import native_scheduler
    slots = native_scheduler.get_active_slots()
    mine = set(post_ids)
    others = [when for when, other, _status in native_scheduler.get_existing_post_datetimes()
              if other not in mine]
    cooldown = _cooldown_hours()
    found: List[datetime] = []
    today = now.astimezone().date()
    for offset in range(SLOT_DAYS):
        day = today + timedelta(days=offset)
        for slot in sorted((s for s in slots if s.get("day_of_week") == day.weekday()),
                           key=lambda s: str(s.get("time_slot"))):
            try:
                hour, minute = (int(part) for part in str(slot["time_slot"]).split(":")[:2])
            except (KeyError, TypeError, ValueError):
                continue
            when = datetime(day.year, day.month, day.day, hour, minute).astimezone()
            if when <= now + timedelta(minutes=AHEAD_MINUTES) or (found and when <= found[-1]):
                continue
            if any(abs((when - other).total_seconds()) / 3600.0 < cooldown for other in others + found):
                continue
            found.append(when)
            if len(found) >= len(post_ids):
                return found
    return found


def plan_series(post_ids: List[str], now: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Plan the series (phase 6): each part into the Queue's next open slots, in
    order, through plan(), as Plan it plans one draft; nothing is posted and
    nothing reaches LinkedIn. Every part must still be a draft. Too few open
    slots in SLOT_DAYS plans nothing ("short"); a part that changed meanwhile
    takes back what was planned ("changed"). Returns {status: planned |
    short | changed, times}.
    """
    post_ids = [str(post_id) for post_id in post_ids if post_id]
    if not post_ids or any(state_of(post_id)["status"] != "draft" for post_id in post_ids):
        return {"status": "changed"}
    times = series_slots(post_ids, (now or datetime.now()).astimezone())
    if len(times) < len(post_ids):
        return {"status": "short", "found": len(times)}
    done: List[Tuple[str, str]] = []
    for post_id, when in zip(post_ids, times):
        result = plan(post_id, when.astimezone(timezone.utc).isoformat())
        if result["status"] != "planned":
            for planned_id, planned_for in done:
                unplan(planned_id, planned_for)
            return {"status": "changed"}
        done.append((post_id, result["for"]))
    return {"status": "planned", "times": [planned_for for _post_id, planned_for in done]}


def unplan_series(post_ids: List[str], planned_for: List[str]) -> str:
    """Undo under a planned series: each part a draft again while it is still queued at its time from the phone."""
    keys = [unplan(post_id, when) for post_id, when in zip(post_ids or [], planned_for or [])]
    return "series_unplanned" if keys and all(key == "unplanned" for key in keys) else "series_unplan_changed"


def unplan(post_id: Any, planned_for: Any) -> str:
    """
    Undo under a plan: the post a draft again, while it is still queued at
    that time from the phone and no one handed it to LinkedIn. One
    conditional update. A key of telegram_bot.SENTENCES.
    """
    post_id = str(post_id or "")
    conn = get_db()
    try:
        row = conn.execute("SELECT made_with FROM posts WHERE id = ?", (post_id,)).fetchone()
        if row is None:
            return "plan_gone"
        made = _made(row[0])
        made.pop("planned", None)
        with conn:
            done = conn.execute(
                "UPDATE posts SET status = 'draft', scheduled_for = NULL, made_with = ? WHERE id = ? "
                "AND status = 'scheduled' AND scheduled_for = ? AND published_at IS NULL AND activity_urn IS NULL "
                "AND NOT EXISTS (SELECT 1 FROM settings WHERE key = ?)",
                (json.dumps(made), post_id, str(planned_for or ""), HOLDS_PREFIX + post_id)).rowcount
    finally:
        conn.close()
    if done:
        changes.publish("queue")
    return "unplanned" if done else "unplan_changed"


def planned_due(conn) -> set:
    """The due posts that were planned from the phone: told when due even with the due notification off."""
    found = set()
    for row in conn.execute("SELECT id, made_with FROM posts WHERE status = 'due' AND made_with IS NOT NULL"):
        if isinstance(_made(row["made_with"]).get("planned"), dict):
            found.add(row["id"])
    return found


# ---------------------------------------------------------------------------
# /plan <day> <time>, read as a person writes it
# ---------------------------------------------------------------------------

_DAYS = {"mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1, "wed": 2, "weds": 2, "wednesday": 2,
         "thu": 3, "thur": 3, "thurs": 3, "thursday": 3, "fri": 4, "friday": 4, "sat": 5, "saturday": 5,
         "sun": 6, "sunday": 6}
_TYPED = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$")


def read_when(text: str, now: datetime) -> Optional[datetime]:
    """
    A day and a time as /plan takes them, on the computer's clock: today,
    tomorrow or a weekday (the next one; today while the time is ahead),
    then 9, 09:00, 9:30, 6pm or 18:30. None for anything else.
    """
    words = (text or "").strip().lower().replace(",", " ").split()
    if len(words) == 3 and words[2] in ("am", "pm"):
        words = [words[0], words[1] + words[2]]
    if len(words) != 2:
        return None
    day_word, clock_word = words
    found = _TYPED.match(clock_word)
    if not found:
        return None
    hour, minute, half = int(found.group(1)), int(found.group(2) or 0), found.group(3)
    if half:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if half == "pm" else 0)
    if hour > 23 or minute > 59:
        return None
    local_now = now.astimezone()
    today: date = local_now.date()
    if day_word == "today":
        day = today
    elif day_word == "tomorrow":
        day = today + timedelta(days=1)
    elif day_word in _DAYS:
        day = today + timedelta(days=(_DAYS[day_word] - today.weekday()) % 7)
    else:
        return None
    when = datetime.combine(day, day_time(hour=hour, minute=minute)).astimezone()
    if day_word in _DAYS and when <= local_now:
        when = datetime.combine(day + timedelta(days=7), day_time(hour=hour, minute=minute)).astimezone()
    return when


# ---------------------------------------------------------------------------
# /plan alone: what is planned
# ---------------------------------------------------------------------------

def upcoming(limit: int) -> Dict[str, Any]:
    """The next queued posts, soonest first, up to `limit`, and how many are due now."""
    conn = get_db()
    try:
        rows = conn.execute("SELECT id, content, scheduled_for FROM posts WHERE status = 'scheduled' "
                            "AND scheduled_for IS NOT NULL ORDER BY scheduled_for LIMIT ?", (int(limit),)).fetchall()
        due = conn.execute("SELECT COUNT(*) FROM posts WHERE status = 'due'").fetchone()[0]
        posts = [{"id": r["id"], "content": r["content"] or "", "at": r["scheduled_for"],
                  "linkedin": _held_by_linkedin(conn, r["id"])} for r in rows]
    finally:
        conn.close()
    return {"posts": posts, "due": int(due or 0)}
