"""
LinkedIn Native Scheduler & Self-Healing Cadence Dispatch Engine
===============================================================
Operationalizes Module 02 enterprise publishing cadence:
1. 12-Hour Cooldown Collision Engine: Guarantees post spacing to prevent
   algorithmic reach cannibalization.
2. Smart Engagement Slot Allocator: Calculates optimal windows based on
   local peak slots (Mon-Fri 08:30 / 17:30).
3. Self-Healing Morning Grace Window Recovery:
   - Within 2-hour grace window (<= 120m overdue): Marks the post due, for the
     creator to post it. Nothing is posted from here.
   - Beyond grace window (> 120m overdue): Marks the post due at its own
     time and records that it was missed. Nothing moves it; Today offers
     Post now and Move to next slot.
4. What the dispatch did is returned to its caller and written to the log.
   Every screen reads the posts table; nothing is pushed.

Strict Invariant: Zero em-dashes in all code, comments, and strings.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import json
import logging
import os
import sqlite3

from apscheduler.schedulers.background import BackgroundScheduler

try:
    from . import paths, changes
    from .database import get_db, init_db, SEEDED_DEMO_POST_IDS, DEFAULT_QUEUE_SLOTS, neutral_slot_label
    from .migrations import SCHEMA_VERSION
except ImportError:
    import paths
    import changes
    from database import get_db, init_db, SEEDED_DEMO_POST_IDS, DEFAULT_QUEUE_SLOTS, neutral_slot_label
    from migrations import SCHEMA_VERSION

logger = logging.getLogger("studio.scheduler")

MIN_COOLDOWN_HOURS = 12.0

# How late a background run may be and still be taken. None means however
# late: a laptop that sleeps across the hour stops the clock, and with
# APScheduler's default of one second every run that came due in the sleep
# was skipped, the hourly backup for a whole hour at a time. Both jobs here
# are checks that decide for themselves whether there is work to do, so a
# late run is always better than no run.
MISFIRE_GRACE = None

# A settings key, per post, for a post handed to LinkedIn's own scheduler with
# Send to LinkedIn. LinkedIn publishes that one itself at its time, so it is
# the one queued post that really is published when its time comes.
LINKEDIN_HOLDS_KEY = "linkedin_holds:"
GRACE_WINDOW_MINUTES = 120.0

# A settings key, per post, for a queued post that was missed: more than the
# grace window late, usually because the machine was asleep. It holds the time
# the post was due and how late it was noticed, for Today's notice.
MISSED_POST_KEY = "missed_post:"
ON_TIME_THRESHOLD_MINUTES = 5.0

# The default week, as slots, for when the creator's cannot be read.
DEFAULT_SLOTS = [
    {"day_of_week": day, "time_slot": time, "label": neutral_slot_label(day, time), "is_active": 1}
    for day, time in DEFAULT_QUEUE_SLOTS
]

DAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday"
]


def parse_datetime_flexible(dt_str: str) -> Optional[datetime]:
    """Parses ISO or common string datetime representations into timezone-aware UTC datetime."""
    if not dt_str:
        return None
    cleaned = str(dt_str).strip().replace("Z", "+00:00")
    if "T" in cleaned:
        try:
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc).astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def normalize_datetime_to_utc_iso(dt_str: str) -> Optional[str]:
    """Parses any valid datetime representation and normalizes it to canonical UTC ISO format."""
    dt = parse_datetime_flexible(dt_str)
    if not dt:
        return None
    return dt.astimezone(timezone.utc).isoformat()


class NativeScheduler:
    """Enterprise cadence management and self-healing local dispatch daemon."""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self._checked_profiles: set = set()
        self.min_cooldown_hours = MIN_COOLDOWN_HOURS
        self.grace_window_minutes = GRACE_WINDOW_MINUTES

    def is_queue_paused(self) -> bool:
        """Checks if automated queue dispatch is paused by creator."""
        # get_db() is inside the try. It was outside, so a failure to open the
        # database escaped past the handler written for exactly that case, and
        # the caller got an exception instead of the safe default below.
        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'queue_status'")
            row = cursor.fetchone()
            return bool(row and row["value"] == "paused")
        except Exception as e:
            # Fail closed, not open.
            #
            # This returned False on a read failure, which means "not paused",
            # which means the dispatcher publishes. A locked database therefore
            # decided on the creator's behalf that their queue was running.
            # Publishing to someone's professional network when the studio
            # cannot tell whether they asked it to is the worse of the two
            # errors, so an unreadable setting counts as paused.
            logger.warning("Could not read queue_status setting, treating the queue as paused: %s", e)
            return True
        finally:
            # conn is None when get_db() itself raised.
            if conn is not None:
                conn.close()

    def set_queue_paused(self, paused: bool) -> bool:
        """
        Sets automated queue dispatch status. Returns whether the write landed.

        This used to return `paused` on success and False on failure, which
        made the two indistinguishable for set_queue_paused(False): the caller
        could not tell "resumed" from "could not write". It now answers the
        only question a caller has, which is whether the setting changed.
        """
        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            val = "paused" if paused else "active"
            cursor.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES ('queue_status', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """, (val,))
            conn.commit()
            logger.info("Queue dispatch status set to %s.", val)
            return True
        except Exception as e:
            logger.error("Failed to update queue_status setting: %s", e)
            return False
        finally:
            # conn is None when get_db() itself raised.
            if conn is not None:
                conn.close()

    def get_active_slots(self) -> List[Dict[str, Any]]:
        """The creator's active weekly slots, or the default week when they cannot be read."""
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT day_of_week, time_slot, label, is_active FROM queue_slots "
                "WHERE is_active = 1 ORDER BY day_of_week, time_slot"
            )
            rows = cursor.fetchall()
            slots = [dict(r) for r in rows]
        except Exception as e:
            # Only when the table cannot be read. An empty week is the
            # creator's choice once slots can be edited, so it stays empty.
            logger.warning("Could not query queue_slots, using the default week: %s", e)
            slots = [dict(slot) for slot in DEFAULT_SLOTS]
        finally:
            conn.close()

        for s in slots:
            dow = s["day_of_week"]
            s["day_name"] = DAY_NAMES[dow] if 0 <= dow < 7 else "Unknown"

        return slots

    def get_existing_post_datetimes(self, exclude_post_id: Optional[str] = None) -> List[Tuple[datetime, str, str]]:
        """
        Returns list of (datetime, post_id, status) for all scheduled posts
        and published posts in the last 48 hours.
        """
        conn = get_db()
        results = []
        try:
            cursor = conn.cursor()
            # A due post is about to be posted by the creator, at its time.
            cursor.execute(
                "SELECT id, status, scheduled_for, published_at FROM posts "
                "WHERE status IN ('scheduled', 'due', 'published')"
            )
            rows = cursor.fetchall()
            for r in rows:
                p_id = r["id"]
                if exclude_post_id and p_id == exclude_post_id:
                    continue
                dt_raw = r["scheduled_for"] if r["status"] in ("scheduled", "due") else r["published_at"]
                dt = parse_datetime_flexible(dt_raw)
                if dt:
                    results.append((dt, p_id, r["status"]))
        finally:
            conn.close()

        results.sort(key=lambda item: item[0])
        return results

    def validate_schedule_cadence(
        self,
        proposed_dt_str: str,
        post_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validates proposed schedule datetime against the 12-hour cooldown rule.
        Returns collision status, nearest conflict details, and cadence health score.
        """
        target_dt = parse_datetime_flexible(proposed_dt_str)
        if not target_dt:
            return {
                "valid": False,
                "error": f"Invalid datetime format: '{proposed_dt_str}'. Use ISO format YYYY-MM-DDTHH:MM:SS.",
                "has_collision": False,
                "cadence_health_score": 0
            }

        now = datetime.now(timezone.utc)
        if target_dt <= now:
            return {
                "valid": False,
                "error": "Scheduled time must be in the future.",
                "has_collision": False,
                "cadence_health_score": 0
            }

        existing_posts = self.get_existing_post_datetimes(exclude_post_id=post_id)
        closest_distance_hours: Optional[float] = None
        closest_post: Optional[Dict[str, Any]] = None

        for dt, p_id, status in existing_posts:
            diff_hours = abs((target_dt - dt).total_seconds()) / 3600.0
            if closest_distance_hours is None or diff_hours < closest_distance_hours:
                closest_distance_hours = diff_hours
                closest_post = {
                    "id": p_id,
                    "status": status,
                    "datetime": dt.isoformat(),
                    "distance_hours": round(diff_hours, 1)
                }

        if closest_distance_hours is not None and closest_distance_hours < self.min_cooldown_hours:
            cadence_health = max(10, int((closest_distance_hours / self.min_cooldown_hours) * 100))
            if closest_distance_hours < 0.08:
                warning_msg = (
                    f"Duplicate slot collision. Another post ({closest_post['id']}) is scheduled "
                    f"at {closest_post['datetime']} (within {int(closest_distance_hours * 60)} minutes). "
                    f"Simultaneous publishing triggers severe distribution penalties."
                )
            else:
                warning_msg = (
                    f"Cadence collision detected. Another post ({closest_post['id']}) is scheduled or published "
                    f"at {closest_post['datetime']}, only {closest_post['distance_hours']}h apart. "
                    f"LinkedIn algorithm evaluates reach on a 12-hour cycle."
                )
            return {
                "valid": True,
                "has_collision": True,
                "warning": warning_msg,
                "cadence_health_score": cadence_health,
                "distance_to_nearest_hours": closest_distance_hours,
                "nearest_conflict": closest_post,
                "conflicting_post_id": closest_post["id"] if closest_post else None,
                "scheduled_datetime": target_dt.isoformat()
            }

        return {
            "valid": True,
            "has_collision": False,
            "warning": None,
            "cadence_health_score": 100,
            "distance_to_nearest_hours": closest_distance_hours,
            "nearest_conflict": closest_post,
            "conflicting_post_id": None,
            "scheduled_datetime": target_dt.isoformat()
        }

    def calculate_next_smart_slot(
        self,
        from_time: Optional[datetime] = None,
        exclude_post_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculates the chronologically next optimal smart slot from active queue_slots
        that respects the 12-hour cooldown buffer relative to other scheduled/published posts.
        """
        now = datetime.now(timezone.utc)
        cursor_dt = from_time if from_time and from_time > now else now
        slots = self.get_active_slots()
        existing_posts = self.get_existing_post_datetimes(exclude_post_id=exclude_post_id)

        # Look ahead up to 14 days to find the best collision-free slot.
        # Slot times are creator-local wall-clock times: walk local calendar
        # days and convert each candidate to UTC. astimezone() on a naive
        # datetime applies the machine timezone, including DST for that date.
        cursor_local_date = cursor_dt.astimezone().date()
        for day_offset in range(14):
            target_date = cursor_local_date + timedelta(days=day_offset)
            weekday = target_date.weekday()

            matching_slots = [s for s in slots if s["day_of_week"] == weekday]
            for s in matching_slots:
                try:
                    hh, mm = map(int, str(s["time_slot"]).split(":")[:2])
                except (TypeError, ValueError):
                    continue
                candidate_dt = datetime(
                    target_date.year, target_date.month, target_date.day,
                    hh, mm, 0
                ).astimezone(timezone.utc)

                # Candidate must be at least 15 minutes into the future
                if candidate_dt <= now + timedelta(minutes=15):
                    continue

                # Check 12-hour cooldown distance from all existing posts
                is_collision_free = True
                min_distance = 999.0
                for ex_dt, _, _ in existing_posts:
                    diff_hours = abs((candidate_dt - ex_dt).total_seconds()) / 3600.0
                    if diff_hours < min_distance:
                        min_distance = diff_hours
                    if diff_hours < self.min_cooldown_hours:
                        is_collision_free = False
                        break

                if is_collision_free:
                    return {
                        "slot_datetime": candidate_dt.isoformat(),
                        "local_datetime": candidate_dt.astimezone().isoformat(),
                        "day_name": s["day_name"],
                        "time_slot": s["time_slot"],
                        "label": s["label"],
                        "cooldown_satisfied": True,
                        "hours_clearance": round(min_distance, 1) if min_distance < 900 else None
                    }

        # Fallback: exactly 24 hours from the cursor when every slot inside the
        # 14 day window collides.
        #
        # The clearance is measured, not asserted. This used to return
        # cooldown_satisfied True and hours_clearance 24.0 without consulting a
        # single post, so with a congested calendar it handed back a time that
        # had a post sitting on it while reporting a full day of room. The
        # "Use Next Smart Slot" button fills the picker with this value, so the
        # creator was being told a colliding time was clear.
        #
        # 24 hours is the distance from the CURSOR, which says nothing about
        # the distance from the nearest post. Those are different numbers and
        # only one of them is the cooldown.
        fallback_dt = cursor_dt + timedelta(hours=24)
        fallback_local = fallback_dt.astimezone()

        fallback_distance = 999.0
        for ex_dt, _, _ in existing_posts:
            diff_hours = abs((fallback_dt - ex_dt).total_seconds()) / 3600.0
            if diff_hours < fallback_distance:
                fallback_distance = diff_hours

        satisfied = fallback_distance >= self.min_cooldown_hours

        return {
            "slot_datetime": fallback_dt.isoformat(),
            "local_datetime": fallback_local.isoformat(),
            "day_name": DAY_NAMES[fallback_local.weekday()],
            "time_slot": fallback_local.strftime("%H:%M"),
            "label": (
                "24-Hour Cooldown Buffer Slot" if satisfied
                else "24-Hour Buffer Slot (still inside the cooldown)"
            ),
            "cooldown_satisfied": satisfied,
            "hours_clearance": (
                round(fallback_distance, 1) if fallback_distance < 900 else None
            ),
        }

    def check_scheduled_queue(self) -> List[Dict[str, Any]]:
        """
        Periodic dispatch and self-healing recovery loop.
        Evaluates scheduled posts against the current timestamp:
        - On-time (<= 5m overdue): Marks the post due.
        - Grace window (5m to 120m overdue): Marks the post due, with a recovery alert.
        - Missed (> 120m overdue): Marks the post due at its own time, noted as missed.

        Due, not published. Nothing here posts anything, and this used to write
        status 'published' with the slot's time: the post left the Queue,
        Analytics listed it as one of the creator's published posts, and it
        was never on LinkedIn. A due post waits on the Queue for the creator to
        post it and press "I posted it", which is publish-now. The exception
        is a post handed to LinkedIn's own scheduler with Send to LinkedIn:
        LinkedIn publishes that one itself, so it is recorded as published at
        its time.
        """
        # What became of each decision, whether or not the queue is paused:
        # a post posted or moved while paused is still no longer due.
        self.resolve_dispatches()
        if self.is_queue_paused():
            logger.info("Scheduler cycle skipped: Publishing queue is currently paused by creator.")
            return []
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        conn = get_db()
        actions = []
        try:
            cursor = conn.cursor()
            seeded_placeholders = ",".join("?" for _ in SEEDED_DEMO_POST_IDS)
            cursor.execute(
                "SELECT id, content, media_urls, scheduled_for FROM posts "
                "WHERE status = 'scheduled' AND scheduled_for <= ? "
                f"AND id NOT IN ({seeded_placeholders}) "
                "ORDER BY scheduled_for ASC",
                (now_iso, *SEEDED_DEMO_POST_IDS)
            )
            due_posts = cursor.fetchall()

            for post in due_posts:
                post_id = post["id"]
                sched_dt = parse_datetime_flexible(post["scheduled_for"])
                if not sched_dt:
                    sched_dt = now

                overdue_minutes = max(0.0, (now - sched_dt).total_seconds() / 60.0)

                # LinkedIn published this one at its time, whether or not this
                # machine was awake, so it is recorded as published then, and
                # never rolled forward to a slot it will not be posted in.
                if cursor.execute(
                    "SELECT 1 FROM settings WHERE key = ?", (LINKEDIN_HOLDS_KEY + post_id,)
                ).fetchone():
                    cursor.execute(
                        "UPDATE posts SET status = 'published', published_at = ? "
                        "WHERE id = ? AND status = 'scheduled'",
                        (sched_dt.isoformat(), post_id)
                    )
                    claimed = cursor.rowcount
                    cursor.execute("DELETE FROM settings WHERE key = ?", (LINKEDIN_HOLDS_KEY + post_id,))
                    if claimed:
                        self._record_dispatch(cursor, post_id, post["scheduled_for"], now_iso, overdue_minutes,
                                              "published_by_linkedin", resolved="published")
                    conn.commit()
                    if claimed == 0:
                        continue
                    actions.append({
                        "post_id": post_id,
                        "action": "published_by_linkedin",
                        "overdue_minutes": round(overdue_minutes, 1)
                    })
                    continue

                # Case 1: On-time or within 2-hour morning grace window
                if overdue_minutes <= self.grace_window_minutes:
                    # Claim the post, do not just write to it.
                    #
                    # The APScheduler thread and the manual dispatch endpoint
                    # both run this. They each SELECT the same due row, each
                    # UPDATE it, and each announce it, so a creator is told
                    # twice. Neither sees the
                    # other's uncommitted write, so nothing upstream catches
                    # it.
                    #
                    # Repeating the status in the WHERE clause turns the write
                    # into a compare and swap: the first one to commit changes
                    # the row, the second matches nothing. rowcount is how we
                    # learn which one we were. This holds across processes as
                    # well as threads, which a lock in this file would not.
                    cursor.execute(
                        "UPDATE posts SET status = 'due' WHERE id = ? AND status = 'scheduled'",
                        (post_id,)
                    )
                    claimed = cursor.rowcount
                    if claimed:
                        self._record_dispatch(
                            cursor, post_id, post["scheduled_for"], now_iso, overdue_minutes,
                            "due_on_time" if overdue_minutes <= ON_TIME_THRESHOLD_MINUTES else "due_within_grace")
                    conn.commit()

                    if claimed == 0:
                        logger.info(
                            "Post %s was already dispatched by another cycle. Skipping.",
                            post_id
                        )
                        continue

                    if overdue_minutes <= ON_TIME_THRESHOLD_MINUTES:
                        logger.info("Post %s is due, on time, at %s.", post_id, now_iso)
                        actions.append({
                            "post_id": post_id,
                            "action": "due_on_time",
                            "overdue_minutes": round(overdue_minutes, 1)
                        })
                    else:
                        # Grace window recovery
                        logger.info(
                            "Post %s is due, %.1fm late, inside the grace window, at %s.",
                            post_id, overdue_minutes, now_iso
                        )
                        actions.append({
                            "post_id": post_id,
                            "action": "due_within_grace",
                            "overdue_minutes": round(overdue_minutes, 1)
                        })

                # Case 2: missed. More than two hours late, because the
                # machine was asleep or the studio closed at its time.
                #
                # Due at its own time, never moved. This used to roll the post
                # forward to the next free slot, so a creator who opened the
                # studio at 11:00 for an 08:30 post found it quietly re-timed
                # for the evening or another day, told only by a log line. The
                # post now waits as due with
                # the time they chose, and a note that it was missed, which
                # Today shows with Post now and Move to next slot.
                else:
                    cursor.execute(
                        "UPDATE posts SET status = 'due' "
                        "WHERE id = ? AND status = 'scheduled' AND scheduled_for = ?",
                        (post_id, post["scheduled_for"])
                    )
                    claimed = cursor.rowcount
                    if claimed:
                        cursor.execute(
                            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                            (MISSED_POST_KEY + post_id, json.dumps({
                                "scheduled_for": post["scheduled_for"],
                                "noticed_at": now_iso,
                                "late_minutes": round(overdue_minutes, 1),
                            })),
                        )
                        self._record_dispatch(cursor, post_id, post["scheduled_for"], now_iso, overdue_minutes,
                                              "missed_due")
                    conn.commit()

                    if claimed == 0:
                        logger.info("Post %s was already marked missed by another cycle. Skipping.", post_id)
                        continue

                    logger.warning(
                        "Post %s missed its time by %.1fm. It is due, at its own time, for the creator to decide.",
                        post_id, overdue_minutes
                    )
                    actions.append({
                        "post_id": post_id,
                        "action": "missed_due",
                        "overdue_minutes": round(overdue_minutes, 1)
                    })

            # A note about a post that is no longer due says nothing true, so
            # it goes once the post is posted, moved or back in the drafts.
            cursor.execute(
                "DELETE FROM settings WHERE key LIKE ? AND substr(key, ?) NOT IN "
                "(SELECT id FROM posts WHERE status = 'due')",
                (MISSED_POST_KEY + "%", len(MISSED_POST_KEY) + 1)
            )
            conn.commit()

        finally:
            conn.close()
        if actions:
            changes.publish("queue")

        return actions

    @staticmethod
    def _record_dispatch(cursor, post_id: str, scheduled_for: Optional[str], noticed_at: str,
                         overdue_minutes: float, outcome: str, resolved: Optional[str] = None) -> None:
        """
        One decision about a post whose time came, kept (queue_dispatches):
        how late, by which rule. Written in the claim's own transaction, so a
        decision another cycle won is never recorded twice.
        """
        cursor.execute(
            "INSERT INTO queue_dispatches (post_id, scheduled_for, noticed_at, late_minutes, outcome, "
            "resolved_at, resolution) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (post_id, scheduled_for, noticed_at, round(overdue_minutes, 1), outcome,
             noticed_at if resolved else None, resolved))

    def resolve_dispatches(self) -> int:
        """
        Says what became of each decision whose post is no longer due: its
        status when the studio saw it ("published", "scheduled", "draft"), or
        "deleted". The note that a post was missed is deleted at that point;
        this row is what stays. Returns how many it resolved.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        try:
            with conn:
                return conn.execute(
                    "UPDATE queue_dispatches SET resolved_at = ?, resolution = COALESCE("
                    "(SELECT status FROM posts WHERE posts.id = queue_dispatches.post_id), 'deleted') "
                    "WHERE resolved_at IS NULL AND post_id NOT IN (SELECT id FROM posts WHERE status = 'due')",
                    (now_iso,)).rowcount
        finally:
            conn.close()

    def open_dispatches(self, conn, post_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """The newest unresolved decision for each of these posts: how late, by which rule."""
        if not post_ids:
            return {}
        marks = ",".join("?" for _ in post_ids)
        out: Dict[str, Dict[str, Any]] = {}
        for row in conn.execute(
                f"SELECT post_id, scheduled_for, noticed_at, late_minutes, outcome FROM queue_dispatches "
                f"WHERE resolved_at IS NULL AND post_id IN ({marks}) ORDER BY noticed_at", list(post_ids)):
            out[row["post_id"]] = dict(row)
        return out

    def missed_notes(self, conn) -> Dict[str, Dict[str, Any]]:
        """The missed note of every due post that has one, by post id."""
        notes: Dict[str, Dict[str, Any]] = {}
        for row in conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE ?", (MISSED_POST_KEY + "%",)
        ).fetchall():
            try:
                value = json.loads(row["value"] or "")
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict) and value.get("scheduled_for"):
                notes[row["key"][len(MISSED_POST_KEY):]] = value
        return notes

    def move_to_next_slot(self, post_id: str) -> Dict[str, Any]:
        """
        Queues a due post again, at the next free slot, on the creator's word.

        The one way a missed post changes time: the creator chose Move to next
        slot. Returns the slot, or raises LookupError for no such post and
        ValueError for a post that is not due.
        """
        conn = get_db()
        try:
            row = conn.execute("SELECT status, scheduled_for FROM posts WHERE id = ?", (post_id,)).fetchone()
            if not row:
                raise LookupError(post_id)
            if row["status"] != "due":
                raise ValueError(row["status"])
            slot = self.calculate_next_smart_slot(exclude_post_id=post_id)
            with conn:
                cursor = conn.execute(
                    "UPDATE posts SET status = 'scheduled', scheduled_for = ? WHERE id = ? AND status = 'due'",
                    (slot["slot_datetime"], post_id),
                )
                if cursor.rowcount == 0:
                    raise ValueError("changed")
                conn.execute("DELETE FROM settings WHERE key = ?", (MISSED_POST_KEY + post_id,))
        finally:
            conn.close()
        return slot

    def get_cadence_overview(self) -> Dict[str, Any]:
        """Calculates global cadence health score and queue summary."""
        existing_posts = self.get_existing_post_datetimes()
        scheduled_posts = [p for p in existing_posts if p[2] == "scheduled"]

        min_gap_hours = 999.0
        collision_count = 0

        for i in range(len(scheduled_posts)):
            for j in range(i + 1, len(scheduled_posts)):
                gap = abs((scheduled_posts[i][0] - scheduled_posts[j][0]).total_seconds()) / 3600.0
                if gap < min_gap_hours:
                    min_gap_hours = gap
                if gap < self.min_cooldown_hours:
                    collision_count += 1

        next_slot = self.calculate_next_smart_slot()
        cadence_health = 100 if collision_count == 0 else max(20, 100 - (collision_count * 25))

        return {
            "status": "success",
            "total_scheduled": len(scheduled_posts),
            "cadence_health_score": cadence_health,
            "collision_count": collision_count,
            "min_spacing_hours": round(min_gap_hours, 1) if min_gap_hours < 900 else None,
            "next_smart_slot": next_slot,
            "queue_paused": self.is_queue_paused()
        }

    def check_every_profile(self) -> List[Dict[str, Any]]:
        """
        One pass over every creator profile's queue, each in its own database.

        A post scheduled in a profile that is not the active one is still due
        when it is due, so the background job cannot look at the active
        profile alone.
        """
        actions: List[Dict[str, Any]] = []
        for profile_id in paths.profile_ids():
            try:
                database = os.path.join(paths.get_profile_home(profile_id), "data", paths.DB_FILENAME)
                if not os.path.exists(database) or not self._schema_ready(profile_id, database):
                    continue
                with paths.using_profile(profile_id):
                    for action in self.check_scheduled_queue() or []:
                        actions.append({**action, "profile_id": profile_id})
            except Exception:
                logger.warning("Scheduler pass failed for profile %s.", profile_id, exc_info=True)
        return actions

    def _schema_ready(self, profile_id: str, database: str) -> bool:
        """
        Whether a profile's database is at this build's schema, upgrading it if older.

        A profile that is not active was never opened at start-up, so its
        database may be older than this build, or newer if a later version
        ran and was rolled back. Writing to it unchecked could hit a column
        that is not there, or change data a newer schema means differently.
        """
        if profile_id in self._checked_profiles:
            return True
        reader = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            version = reader.execute("PRAGMA user_version").fetchone()[0]
        finally:
            reader.close()
        if version > SCHEMA_VERSION:
            logger.warning("Profile %s was written by a newer build (schema %s); its queue is left alone.",
                           profile_id, version)
            return False
        if version < SCHEMA_VERSION:
            with paths.using_profile(profile_id):
                init_db()
        self._checked_profiles.add(profile_id)
        return True

    def start(self):
        """Starts the APScheduler background thread."""
        if not self.scheduler.running:
            self.scheduler.add_job(
                self.check_every_profile,
                "interval",
                seconds=30,
                id="queue_checker",
                replace_existing=True,
                # Run it however late it is, and once for a whole sleep. See
                # the hourly job below: the same default skipped this check
                # too, so a post that came due while the machine slept waited
                # another 30 seconds after the wake to be noticed.
                misfire_grace_time=MISFIRE_GRACE,
                coalesce=True,
            )
            # The daily backup, its rotation and the retention cleanups, for
            # every profile. Checked hourly, so a studio opened for an hour a
            # day still gets its backup; the first check waits ten minutes so
            # starting up stays quick. retention.py decides what is due.
            try:
                from . import retention
            except ImportError:
                import retention
            self.scheduler.add_job(
                retention.run_for_every_profile,
                "interval",
                hours=1,
                next_run_time=datetime.now() + timedelta(minutes=10),
                id="daily_backup_and_retention",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                # The run is taken however late it is. APScheduler's default
                # grace is one second, so a run that came due while the
                # machine was asleep was dropped with "was missed by ..." and
                # the next one was a full hour later: a creator who opened the
                # studio, slept the laptop and woke it an hour later got no
                # backup, no reaction folding and no retention cleanup. With
                # coalesce a sleep of any length is caught up by one run, and
                # retention.py still decides what is actually due.
                misfire_grace_time=MISFIRE_GRACE,
            )
            # From your record (cycle 4, track 7): the day's batch of cards,
            # built the first time the studio runs each day and only read by
            # the screen. Hourly like the backup, the first check a minute
            # after start; record_daily decides whether today has a batch yet.
            # It never calls a model: that runs on the creator's first open.
            try:
                from . import record_daily
            except ImportError:
                import record_daily
            self.scheduler.add_job(
                record_daily.run_for_every_profile,
                "interval",
                hours=1,
                next_run_time=datetime.now() + timedelta(minutes=1),
                id="record_daily_batch",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=MISFIRE_GRACE,
            )
            self.scheduler.start()
            logger.info("Local background cadence scheduler started.")

    def shutdown(self):
        """Stops the APScheduler thread gracefully, ready to be started again."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Local cadence scheduler stopped.")
            # A stopped APScheduler cannot be started again: shutdown closes
            # its thread pool for good, and start() does not open a new one,
            # so every later queue check failed to be submitted with
            # "cannot schedule new futures after shutdown", every 30 seconds,
            # and nothing checked the queue or took the daily backup. A second
            # start in the same process now gets a scheduler that can run.
            self.scheduler = BackgroundScheduler()


# Global Singleton Instance
native_scheduler = NativeScheduler()


# Top-level API bindings for backward compatibility
def start_scheduler():
    native_scheduler.start()


def shutdown_scheduler():
    native_scheduler.shutdown()


def check_scheduled_queue():
    return native_scheduler.check_scheduled_queue()


def is_queue_paused() -> bool:
    return native_scheduler.is_queue_paused()


def set_queue_paused(paused: bool) -> bool:
    return native_scheduler.set_queue_paused(paused)
