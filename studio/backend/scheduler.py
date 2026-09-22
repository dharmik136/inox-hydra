"""
LinkedIn Native Scheduler & Self-Healing Cadence Dispatch Engine
===============================================================
Operationalizes Module 02 enterprise publishing cadence:
1. 12-Hour Cooldown Collision Engine: Guarantees post spacing to prevent
   algorithmic reach cannibalization.
2. Smart Engagement Slot Allocator: Calculates optimal windows based on
   local peak slots (Mon-Fri 08:30 / 17:30).
3. Self-Healing Morning Grace Window Recovery:
   - Within 2-hour grace window (<= 120m overdue): Dispatches immediately and
     notifies via SSE.
   - Beyond grace window (> 120m overdue): Safely rolls forward to next
     optimal peak engagement window and alerts creator.
4. Real-time SSE stream integration (schedule_recovery event).

Strict Invariant: Zero em-dashes in all code, comments, and strings.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import json
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

try:
    from .database import get_db, SEEDED_DEMO_POST_IDS
    from .event_bus import event_bus
except ImportError:
    from database import get_db, SEEDED_DEMO_POST_IDS
    from event_bus import event_bus

logger = logging.getLogger("studio.scheduler")

MIN_COOLDOWN_HOURS = 12.0
GRACE_WINDOW_MINUTES = 120.0
ON_TIME_THRESHOLD_MINUTES = 5.0

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
        """Fetches active queue slots from SQLite with fallback to enterprise defaults."""
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
            logger.warning("Could not query queue_slots: %s", e)
            slots = []
        finally:
            conn.close()

        if not slots:
            # Standard enterprise default slots: Mon-Fri 08:30 & 17:30
            slots = [
                {"day_of_week": 0, "time_slot": "08:30", "label": "Monday Morning Kickoff", "is_active": 1},
                {"day_of_week": 0, "time_slot": "17:30", "label": "Monday Evening Read", "is_active": 1},
                {"day_of_week": 1, "time_slot": "08:30", "label": "Tuesday Peak Hook", "is_active": 1},
                {"day_of_week": 1, "time_slot": "17:30", "label": "Tuesday Evening Thought", "is_active": 1},
                {"day_of_week": 2, "time_slot": "08:30", "label": "Wednesday Midweek Deep-Dive", "is_active": 1},
                {"day_of_week": 2, "time_slot": "17:30", "label": "Wednesday Systems Review", "is_active": 1},
                {"day_of_week": 3, "time_slot": "08:30", "label": "Thursday Architecture Playbook", "is_active": 1},
                {"day_of_week": 3, "time_slot": "17:30", "label": "Thursday Evening Pulse", "is_active": 1},
                {"day_of_week": 4, "time_slot": "09:00", "label": "Friday Weekly Retrospective", "is_active": 1},
                {"day_of_week": 5, "time_slot": "10:30", "label": "Saturday Deep Thinking", "is_active": 1},
                {"day_of_week": 6, "time_slot": "11:00", "label": "Sunday Career & Strategy", "is_active": 1},
            ]

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
            cursor.execute(
                "SELECT id, status, scheduled_for, published_at FROM posts "
                "WHERE status IN ('scheduled', 'published')"
            )
            rows = cursor.fetchall()
            for r in rows:
                p_id = r["id"]
                if exclude_post_id and p_id == exclude_post_id:
                    continue
                dt_raw = r["scheduled_for"] if r["status"] == "scheduled" else r["published_at"]
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
        - On-time (<= 5m overdue): Dispatches as published.
        - Grace window (5m to 120m overdue): Dispatches as published with recovery alert.
        - Stale (> 120m overdue): Safely rolls forward to next optimal window to protect reach.
        """
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

                # Case 1: On-time or within 2-hour morning grace window
                if overdue_minutes <= self.grace_window_minutes:
                    # Claim the post, do not just write to it.
                    #
                    # The APScheduler thread and the manual dispatch endpoint
                    # both run this. They each SELECT the same due row, each
                    # UPDATE it, and each publish a post_published event, so a
                    # creator's post goes to LinkedIn twice. Neither sees the
                    # other's uncommitted write, so nothing upstream catches
                    # it.
                    #
                    # Repeating the status in the WHERE clause turns the write
                    # into a compare and swap: the first one to commit changes
                    # the row, the second matches nothing. rowcount is how we
                    # learn which one we were. This holds across processes as
                    # well as threads, which a lock in this file would not.
                    cursor.execute(
                        "UPDATE posts SET status = 'published', published_at = ? "
                        "WHERE id = ? AND status = 'scheduled'",
                        (now_iso, post_id)
                    )
                    conn.commit()

                    if cursor.rowcount == 0:
                        logger.info(
                            "Post %s was already dispatched by another cycle. Skipping.",
                            post_id
                        )
                        continue

                    if overdue_minutes <= ON_TIME_THRESHOLD_MINUTES:
                        logger.info("Post %s dispatched on time at %s.", post_id, now_iso)
                        event_bus.publish_sync("post_published", {
                            "post_id": post_id,
                            "published_at": now_iso
                        })
                        actions.append({
                            "post_id": post_id,
                            "action": "published_on_time",
                            "overdue_minutes": round(overdue_minutes, 1)
                        })
                    else:
                        # Grace window recovery
                        logger.info(
                            "Post %s recovered and published within %.1fm grace window at %s.",
                            post_id, overdue_minutes, now_iso
                        )
                        recovery_payload = {
                            "type": "grace_dispatched",
                            "post_id": post_id,
                            "overdue_minutes": round(overdue_minutes, 1),
                            "message": f"Recovered and published post within {int(overdue_minutes)}m morning grace window."
                        }
                        event_bus.publish_sync("schedule_recovery", recovery_payload)
                        actions.append({
                            "post_id": post_id,
                            "action": "grace_dispatched",
                            "overdue_minutes": round(overdue_minutes, 1)
                        })

                # Case 2: Stale post (> 2 hours late, workstation was shut down/asleep)
                else:
                    next_slot = self.calculate_next_smart_slot(from_time=now, exclude_post_id=post_id)
                    new_time = next_slot["slot_datetime"]

                    # The same claim. Two cycles rolling the same stale post
                    # forward would compute two different next slots and each
                    # announce its own, so the creator is told twice where
                    # their post went, to two different places.
                    cursor.execute(
                        "UPDATE posts SET scheduled_for = ?, status = 'scheduled' "
                        "WHERE id = ? AND status = 'scheduled' AND scheduled_for = ?",
                        (new_time, post_id, post["scheduled_for"])
                    )
                    conn.commit()

                    if cursor.rowcount == 0:
                        logger.info(
                            "Post %s was already rolled forward by another cycle. Skipping.",
                            post_id
                        )
                        continue

                    logger.warning(
                        "Post %s missed window by %.1fm. Rolled forward to %s (%s).",
                        post_id, overdue_minutes, next_slot["label"], new_time
                    )
                    recovery_payload = {
                        "type": "rolled_forward",
                        "post_id": post_id,
                        "original_scheduled_for": sched_dt.isoformat(),
                        "new_scheduled_for": new_time,
                        "slot_label": next_slot["label"],
                        "overdue_minutes": round(overdue_minutes, 1),
                        "message": (
                            f"Post missed window by {round(overdue_minutes / 60.0, 1)}h. "
                            f"Safely rolled forward to {next_slot['label']} ({new_time})."
                        )
                    }
                    event_bus.publish_sync("schedule_recovery", recovery_payload)
                    actions.append({
                        "post_id": post_id,
                        "action": "rolled_forward",
                        "overdue_minutes": round(overdue_minutes, 1),
                        "new_scheduled_for": new_time
                    })

        finally:
            conn.close()

        return actions

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

    def start(self):
        """Starts the APScheduler background thread."""
        if not self.scheduler.running:
            self.scheduler.add_job(
                self.check_scheduled_queue,
                "interval",
                seconds=30,
                id="queue_checker",
                replace_existing=True
            )
            self.scheduler.start()
            logger.info("Local background cadence scheduler started.")

    def shutdown(self):
        """Stops the APScheduler thread gracefully."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Local cadence scheduler stopped.")


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
