"""
Remind me: an item of the collection brought back at a moment picked on the phone.
=================================================================================

Phase 5 of the Telegram bot, item 4 (docs/quality/cycle4/bot-phase5.md).
Under "Saved to your collection.", Remind me offers the creator's own
moments (by default this evening, tomorrow morning, next week); one pressed
keeps a reminder, a row of `item_reminders` (migration 43). Between polls the
bot brings the item back at that moment, with Write it up and Not now.

The rules, each held here or by the worker that tells them:

- told once: a reminder is claimed by one conditional update before it is
  handed over, so two checks never tell it twice;
- it survives a restart: it is a row, and one whose moment passed while the
  studio was off is told at the next check, saying the moment it was for;
- it goes with its item: removing an item (Remove, Undo, a Draft: taken
  back, Delete everything) removes its reminders in the same transaction;
- it waits through quiet hours, and only a paired chat is told (the worker,
  ingress.check_notifications, which claims under its check lock).

Strict Invariants:
- Zero em-dashes.
- Nothing here reaches the network.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from datetime import time as day_time
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from . import changes
    from .database import get_db
except ImportError:
    import changes
    from database import get_db

TABLE = "item_reminders"
# The creator's preference: the moments Remind me offers, each a label of
# their own, so many days from today, at a time on the computer's clock.
MOMENTS_KEY = "telegram_remind_moments"
MOMENTS_MAX = 4
LABEL_MAX = 24
DAYS_AHEAD = tuple(range(0, 15))
MOMENTS_DEFAULT: List[Dict[str, Any]] = [
    {"label": "This evening", "days": 0, "at": "18:00"},
    {"label": "Tomorrow morning", "days": 1, "at": "09:00"},
    {"label": "Next week", "days": 7, "at": "09:00"},
]
# A moment nearer than this is not offered, as Plan it's times are not
# (the Queue's own rule for its next open slot).
AHEAD_MINUTES = 15

_CLOCK = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class Refused(ValueError):
    """A preference not kept, with the sentence the panel shows."""


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


# ---------------------------------------------------------------------------
# The moments Remind me offers
# ---------------------------------------------------------------------------

def _valid_moment(entry: Any) -> bool:
    return (isinstance(entry, dict) and set(entry) == {"label", "days", "at"}
            and isinstance(entry["label"], str) and 0 < len(entry["label"].strip()) <= LABEL_MAX
            and entry["days"] in DAYS_AHEAD and not isinstance(entry["days"], bool)
            and isinstance(entry["at"], str) and bool(_CLOCK.match(entry["at"])))


def _valid(value: Any) -> bool:
    if not isinstance(value, list) or not 1 <= len(value) <= MOMENTS_MAX or not all(_valid_moment(m) for m in value):
        return False
    labels = [m["label"].strip().casefold() for m in value]
    return len(set(labels)) == len(labels)


def _clean(entry: Dict[str, Any]) -> Dict[str, Any]:
    hour, minute = entry["at"].split(":")
    return {"label": " ".join(entry["label"].split()), "days": entry["days"], "at": f"{int(hour):02d}:{minute}"}


def moments(conn=None) -> List[Dict[str, Any]]:
    """The moments Remind me offers in the open profile: the creator's, or the default."""
    own = conn is None
    conn = conn or get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (MOMENTS_KEY,)).fetchone()
    finally:
        if own:
            conn.close()
    try:
        held = json.loads(row[0]) if row and row[0] else None
    except (TypeError, ValueError):
        held = None
    return [_clean(m) for m in held] if _valid(held) else [dict(m) for m in MOMENTS_DEFAULT]


def check_moments(value: Any) -> List[Dict[str, Any]]:
    """The moments to keep, or Refused with the sentence the panel shows. Nothing is kept here."""
    if isinstance(value, list):
        value = [{"label": str(m.get("label") or ""), "days": m.get("days"), "at": str(m.get("at") or "").strip()}
                 if isinstance(m, dict) else m for m in value]
    if not _valid(value):
        raise Refused(f"Remind me offers 1 to {MOMENTS_MAX} moments, each with its own label of up to {LABEL_MAX} "
                      f"characters, a number of days from today (0 to {DAYS_AHEAD[-1]}) and a time such as 18:00. "
                      "Nothing was saved.")
    return [_clean(m) for m in value]


def offered(now: datetime) -> List[Tuple[str, datetime]]:
    """The moments offered now, as (label, when), soonest first; one past, or too near, is left out."""
    found = []
    today = now.astimezone().date()
    for entry in moments():
        hour, minute = (int(part) for part in entry["at"].split(":"))
        when = datetime.combine(today + timedelta(days=int(entry["days"])),
                                day_time(hour=hour, minute=minute)).astimezone()
        if when > now + timedelta(minutes=AHEAD_MINUTES):
            found.append((entry["label"], when))
    return sorted(found, key=lambda pair: pair[1])


# ---------------------------------------------------------------------------
# The reminders
# ---------------------------------------------------------------------------

def add(item_id: Any, when: Any, label: str) -> Dict[str, Any]:
    """
    A reminder for an item at a moment: {status: kept, id, at} or why not:
    gone (the item was removed), past (the moment passed before the press).
    """
    moment = _instant(when)
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return {"status": "gone"}
    if moment is None or moment <= _now():
        return {"status": "past"}
    at = moment.astimezone(timezone.utc).isoformat()
    conn = get_db()
    try:
        with conn:
            # The item and its reminder in one transaction: an item removed meanwhile keeps none.
            if conn.execute("SELECT 1 FROM collection_items WHERE id = ?", (item_id,)).fetchone() is None:
                return {"status": "gone"}
            reminder_id = conn.execute(
                f"INSERT INTO {TABLE} (item_id, remind_at, label, created_at) VALUES (?, ?, ?, ?)",
                (item_id, at, " ".join(str(label or "").split())[:LABEL_MAX], _now().isoformat())).lastrowid
    finally:
        conn.close()
    changes.publish("collection")
    return {"status": "kept", "id": reminder_id, "at": at}


def cancel(reminder_id: Any) -> bool:
    """Cancel, in the box or on the phone: a reminder not yet told is removed. Says whether there was one."""
    try:
        reminder_id = int(reminder_id)
    except (TypeError, ValueError):
        return False
    conn = get_db()
    try:
        with conn:
            gone = conn.execute(f"DELETE FROM {TABLE} WHERE id = ? AND told_at IS NULL", (reminder_id,)).rowcount
    finally:
        conn.close()
    if gone:
        changes.publish("collection")
    return bool(gone)


def waiting_for(conn, item_ids: Iterable[int]) -> Dict[int, List[Dict[str, Any]]]:
    """Each item's reminders not yet told, soonest first, as the box lists them with Cancel."""
    ids = [int(i) for i in item_ids]
    if not ids:
        return {}
    found: Dict[int, List[Dict[str, Any]]] = {}
    marks = ", ".join("?" for _ in ids)
    try:
        rows = conn.execute(f"SELECT id, item_id, remind_at, label FROM {TABLE} WHERE told_at IS NULL "
                            f"AND item_id IN ({marks}) ORDER BY remind_at, id", ids).fetchall()
    except Exception:
        # A database from before reminders were kept holds none.
        return {}
    for row in rows:
        found.setdefault(row["item_id"], []).append({"id": row["id"], "remind_at": row["remind_at"],
                                                     "label": row["label"]})
    return found


def waiting_items(conn) -> set:
    """The items with a reminder not yet told, which an idea brought back passes over (phase 6)."""
    try:
        return {row[0] for row in conn.execute(f"SELECT DISTINCT item_id FROM {TABLE} WHERE told_at IS NULL")}
    except Exception:
        # A database from before reminders were kept holds none.
        return set()


def claim_due(conn, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """
    The reminders whose moment has come, each claimed (told) by one
    conditional update, so it is handed over once whatever else checks;
    each with its item. A reminder whose item is gone was removed with it.
    """
    moment = (now or _now()).astimezone(timezone.utc).isoformat()
    claimed = []
    try:
        rows = conn.execute(f"SELECT r.id, r.item_id, r.remind_at, r.label FROM {TABLE} r "
                            "JOIN collection_items c ON c.id = r.item_id "
                            "WHERE r.told_at IS NULL AND r.remind_at <= ? ORDER BY r.remind_at, r.id",
                            (moment,)).fetchall()
    except Exception:
        return []
    for row in rows:
        with conn:
            done = conn.execute(f"UPDATE {TABLE} SET told_at = ? WHERE id = ? AND told_at IS NULL",
                                (_now().isoformat(), row["id"])).rowcount
        if done:
            claimed.append(dict(row))
    return claimed


def forget_items(conn, item_ids: Iterable[int]) -> None:
    """An item removed: its reminders go in the same transaction."""
    for item_id in item_ids:
        try:
            conn.execute(f"DELETE FROM {TABLE} WHERE item_id = ?", (int(item_id),))
        except Exception:
            return


def forget(conn) -> None:
    """Delete everything: every reminder."""
    try:
        conn.execute(f"DELETE FROM {TABLE}")
    except Exception:
        pass
