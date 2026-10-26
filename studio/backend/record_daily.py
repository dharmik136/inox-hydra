"""
From your record: the daily job.
================================
The batch is built once a day, the first time the studio runs that day, and
the screen only ever reads it. The studio has no clock outside its own
process: nothing runs while the machine is off, close hides to the tray,
and autostart is opt-in. So "daily" is worded the way the backup schedule
words it: updated the first time the studio runs each day.

  when      an hourly check, beside the backup's, decides whether today has
            a batch yet (run_for_every_profile, scheduler.py); it takes the
            maintenance turn and tries again next hour when a backup, an
            import or a cleanup holds it
  what      stage 1 (record_cards.py), the slot the library or the model
            fills, and the day's run row with its input signature and seed
  never     a model call. The model stage runs on the creator's first open
            of the section, as its own request (record_model.py), so the
            policy's "only at the moment you use the feature" stays true
  carry     when nothing the batch is built from has changed since the last
            batch, its cards are carried forward unchanged and the day says
            "nothing new since" that day, as a sentence, never a reshuffle.
            The one part allowed to move is the date's own: the on-this-day
            or resurfaced opener slot, and the Monday card

The input signature covers what the batch is built from: the creator's
posts, readings, comments and reactions, asks, marks, archive records, the
library bundle, the configured provider and model, and the card format.

Strict Invariants:
- Zero em-dashes.
- Zero egress: the job imports no client; the model stage is not called here.
- The screen's read is a SELECT (read_today); nothing here runs on screen load.
"""

import hashlib
import json
import logging
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from . import paths, record_cards, support
    from .database import get_db
    from .migrations import SCHEMA_VERSION
except ImportError:  # top-level import mode
    import paths
    import record_cards
    import support
    from database import get_db
    from migrations import SCHEMA_VERSION

logger = logging.getLogger("studio.record")

# The card format. A change to what a card carries is a change the signature
# must see, or a carried-forward batch would keep yesterday's shape.
CARD_FORMAT = 1

# How long a dated batch is kept: the creator's choice on the section's
# "What the studio knows" page. A batch a mark or a draft refers to is kept.
KEEP_DAYS_KEY = "record_keep_days"
KEEP_DAYS_OPTIONS = ("90", "365", "forever")
KEEP_DAYS_DEFAULT = "365"
# Batches are scrollable on screen for this many days back.
VISIBLE_DAYS = 14

# The slot the model stage or the library fills, and the kinds that follow the date.
OPEN_SLOT = 5
DATED_KINDS = ("on_this_day", "opener", "monday")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def local_today() -> date:
    """The creator's day: this machine's local date, which is when "the first run of the day" turns over."""
    return datetime.now().astimezone().date()


def _scalar(conn, sql: str, params=()) -> Any:
    try:
        row = conn.execute(sql, params).fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def _setting(conn, key: str) -> Optional[str]:
    return _scalar(conn, "SELECT value FROM settings WHERE key = ?", (key,))


# ---------------------------------------------------------------------------
# The input signature
# ---------------------------------------------------------------------------

def signature(conn) -> str:
    """
    A digest of everything the batch is built from. Equal to the last run's,
    the batch is carried forward unchanged.
    """
    parts: List[Any] = [CARD_FORMAT, SCHEMA_VERSION]
    for sql in (
        "SELECT COUNT(*), MAX(last_seen_at), TOTAL(LENGTH(text)), MAX(published_at) FROM own_posts",
        "SELECT COUNT(*), MAX(observed_at) FROM post_metric_observations",
        "SELECT COUNT(*), MAX(last_seen_at) FROM outbound_engagements",
        "SELECT COUNT(*), MAX(updated_at) FROM asks WHERE status != 'retired' AND hidden_at IS NULL",
        "SELECT COUNT(*), MAX(at) FROM card_marks",
        "SELECT COUNT(*), MAX(imported_at) FROM archive_records",
        "SELECT COUNT(*), MAX(bundle_version), MAX(fetched_at) FROM library_entries",
    ):
        try:
            parts.append(list(conn.execute(sql).fetchone()))
        except sqlite3.OperationalError:
            parts.append(None)
    for key in ("ai_provider", "ai_model", "record_model_stage"):
        parts.append(_setting(conn, key))
    return hashlib.sha256(json.dumps(parts, default=str).encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Asks the creator made elsewhere: Telegram ideas
# ---------------------------------------------------------------------------

def sync_telegram_ideas(conn) -> int:
    """
    An "Idea:" message from the creator's phone lands as a draft tagged
    mobile-ingress and idea (ingress.py). It is an explicit act, so it is an
    ask as well, recorded once, with the draft it came from.
    """
    try:
        rows = conn.execute(
            "SELECT id, content, created_at FROM posts WHERE tags LIKE '%\"idea\"%' AND tags LIKE '%\"mobile-ingress\"%' "
            "AND id NOT IN (SELECT origin_ref FROM asks WHERE source = 'telegram' AND origin_ref IS NOT NULL)").fetchall()
    except sqlite3.OperationalError:
        return 0
    now = _now().isoformat()
    added = 0
    for row in rows:
        text = " ".join((row[1] or "").split())[:2000]
        if not text:
            continue
        conn.execute("INSERT INTO asks (text, source, origin_ref, status, created_at, updated_at) "
                     "VALUES (?, 'telegram', ?, 'open', ?, ?)", (text, row[0], row[2] or now, now))
        added += 1
    return added


# ---------------------------------------------------------------------------
# The open slot: the library's match, or the sentence that says what fills it
# ---------------------------------------------------------------------------

def _model_configured(conn) -> bool:
    provider = _setting(conn, "ai_provider")
    return bool(provider) and provider != "local_deterministic" and (_setting(conn, "record_model_stage") or "on") == "on"


def open_slot_card(conn, day: date, seed: int) -> Dict[str, Any]:
    """
    Slot 5 at the time the job runs. The library's curated match when a
    signed bundle is stored and one of its entries matches the creator's
    topics (record_library.py, on this machine); otherwise a sentence. The
    model's idea, when it arrives on the creator's first open, replaces it.
    """
    try:
        from . import library_bundle
    except ImportError:
        import library_bundle
    card = library_bundle.match_card(conn, day, seed)
    if card is not None:
        return card
    if _model_configured(conn):
        sentence = ("An idea from your own AI provider arrives here the first time you open this section today. "
                    "Nothing is sent before you do.")
        kind = "model_pending"
    else:
        sentence = ("This slot fills with an idea from your own AI provider once you connect one in the Composer's "
                    "Prompt tab, or with a form from the Inox library once you fetch it on What the studio knows.")
        kind = "open_slot"
    return record_cards._abstained(OPEN_SLOT, "model", kind, sentence,
                                   "the model stage on your first open, or the signed Inox library matched here")


# ---------------------------------------------------------------------------
# One day's run
# ---------------------------------------------------------------------------

def _last_run(conn, day: date) -> Optional[Dict[str, Any]]:
    try:
        row = conn.execute("SELECT * FROM daily_run WHERE day < ? AND local_ok = 1 ORDER BY day DESC LIMIT 1",
                           (day.isoformat(),)).fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(row) if row else None


def _today_run(conn, day: date) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM daily_run WHERE day = ?", (day.isoformat(),)).fetchone()
    return dict(row) if row else None


def _carry_forward(conn, last: Dict[str, Any], day: date, seed: int) -> List[Dict[str, Any]]:
    """
    The last batch's cards, unchanged, for every slot the date does not move;
    the dated slot and the Monday card are drawn for today by their own rule.
    """
    carried = []
    for card in record_cards.read_batch(conn, date.fromisoformat(last["day"])):
        if card["kind"] in DATED_KINDS or card["status"] in ("dropped", "replaced"):
            continue
        carried.append({"card_id": card["card_id"], "slot": card["slot"], "block": card["block"], "kind": card["kind"],
                        "label": card["label"], "method": card["method"], "status": card["status"],
                        "payload": card["payload"], "provenance": card["provenance"]})
    fresh = record_cards.compute_local(conn, day, seed)
    for card in fresh["cards"]:
        if card["kind"] in DATED_KINDS or (card["slot"] == 2 and not any(c["slot"] == 2 for c in carried)):
            carried.append(card)
    return [record_cards.verify(conn, card) for card in carried]


def run_today(day: Optional[date] = None, conn=None, reroll: bool = False) -> Dict[str, Any]:
    """
    Builds today's batch once, or says it already exists.

    `reroll` is the creator's "Suggest new": today's batch is drawn again
    with the next seed, once a day, and the run row records that it was.
    """
    day = day or local_today()
    own = conn is None
    conn = conn or get_db()
    try:
        existing = _today_run(conn, day)
        if existing and existing["local_ok"] and not reroll:
            return {"status": "already", "day": day.isoformat(), "run": existing}
        if reroll:
            if not existing or not existing["local_ok"]:
                return {"status": "refused", "day": day.isoformat(),
                        "message": "Today's cards have not been built yet, so there is nothing to draw again."}
            if existing.get("rerolled_at"):
                return {"status": "refused", "day": day.isoformat(),
                        "message": "Today's cards were already drawn again once. New cards come tomorrow."}
        started = _now().isoformat()
        # An idea sent from the phone is an ask, written in a transaction of
        # its own so the batch below is built from it.
        telegram = sync_telegram_ideas(conn)
        conn.commit()
        # Read and build holding no write lock: on three years this is the
        # long part, and a capture arriving meanwhile must not wait for it.
        current = signature(conn)
        last = _last_run(conn, day)
        seed = record_cards.seed_for(day, 1 if reroll else 0)
        carried_from = None
        if last and last.get("input_signature") == current and not reroll:
            cards = _carry_forward(conn, last, day, seed)
            carried_from = last["day"]
            note = f"nothing new since {carried_from}"
        else:
            cards = record_cards.compute_local(conn, day, seed)["cards"]
            cards.append(record_cards.verify(conn, open_slot_card(conn, day, seed)))
            note = "built from your record" if not reroll else "drawn again at your request"
        dropped = sum(1 for card in cards if card["status"] == "dropped")
        # Then one short write. A run that landed meanwhile, from another
        # window's "Suggest new" or a second process, is kept.
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = _today_run(conn, day)
            if existing and existing["local_ok"] and not reroll:
                conn.execute("ROLLBACK")
                return {"status": "already", "day": day.isoformat(), "run": existing}
            if reroll:
                # What was shown before stays readable, so a keep made on it
                # still has a card to show in Kept; it is no longer shown today.
                conn.execute("UPDATE daily_view SET status = 'replaced' WHERE day = ? AND status IN ('shown', 'abstained')",
                             (day.isoformat(),))
            record_cards.store_batch(conn, day, {"cards": cards}, replace=not reroll)
            finished = _now().isoformat()
            if existing:
                conn.execute(
                    "UPDATE daily_run SET input_signature = ?, finished_at = ?, local_ok = 1, seed = ?, "
                    "rerolled_at = ?, dropped_cards = ?, note = ?, carried_from = ? WHERE day = ?",
                    (current, finished, seed, finished if reroll else existing.get("rerolled_at"), dropped, note,
                     carried_from, day.isoformat()))
            else:
                conn.execute(
                    "INSERT INTO daily_run (day, input_signature, started_at, finished_at, local_ok, local_note, "
                    "carried_from, seed, model_status, dropped_cards, note) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)",
                    (day.isoformat(), current, started, finished,
                     f"{telegram} ideas from Telegram became asks" if telegram else None,
                     carried_from, seed, "not_run", dropped, note))
            removed = prune(conn, day)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        run = _today_run(conn, day)
        return {"status": "built" if not carried_from else "carried", "day": day.isoformat(), "run": run,
                "cards": len(cards), "pruned_days": removed}
    finally:
        if own:
            conn.close()


def prune(conn, day: date) -> int:
    """
    Removes dated batches older than the creator's choice, except a batch a
    mark or a draft still refers to. Returns how many days went.
    """
    keep = _setting(conn, KEEP_DAYS_KEY) or KEEP_DAYS_DEFAULT
    if keep not in KEEP_DAYS_OPTIONS or keep == "forever":
        return 0
    cutoff = (day - timedelta(days=int(keep))).isoformat()
    referenced = "(SELECT day FROM card_marks UNION SELECT origin_day FROM posts WHERE origin_day IS NOT NULL)"
    try:
        days = [r[0] for r in conn.execute(
            f"SELECT day FROM daily_run WHERE day < ? AND day NOT IN {referenced}", (cutoff,))]
        conn.execute(f"DELETE FROM daily_view WHERE day < ? AND day NOT IN {referenced}", (cutoff,))
        conn.execute(f"DELETE FROM daily_run WHERE day < ? AND day NOT IN {referenced}", (cutoff,))
    except sqlite3.OperationalError:
        return 0
    return len(days)


def preview_prune(day: Optional[date] = None) -> Dict[str, Any]:
    """What prune would remove today, for the page that sets the rule. Removes nothing."""
    day = day or local_today()
    conn = get_db()
    try:
        keep = _setting(conn, KEEP_DAYS_KEY) or KEEP_DAYS_DEFAULT
        if keep == "forever" or keep not in KEEP_DAYS_OPTIONS:
            return {"keep": keep, "days": 0, "cards": 0}
        cutoff = (day - timedelta(days=int(keep))).isoformat()
        referenced = "(SELECT day FROM card_marks UNION SELECT origin_day FROM posts WHERE origin_day IS NOT NULL)"
        days = _scalar(conn, f"SELECT COUNT(*) FROM daily_run WHERE day < ? AND day NOT IN {referenced}", (cutoff,)) or 0
        cards = _scalar(conn, f"SELECT COUNT(*) FROM daily_view WHERE day < ? AND day NOT IN {referenced}", (cutoff,)) or 0
        return {"keep": keep, "days": days, "cards": cards, "older_than": cutoff}
    finally:
        conn.close()


def run_scheduled() -> Dict[str, Any]:
    """The active profile's check: under the maintenance turn, never waiting for it."""
    try:
        with support.maintenance_turn():
            return run_today()
    except support.MaintenanceBusy as busy:
        logger.info("From your record: skipped (%s); tried again next hour.", busy)
        return {"status": "skipped", "message": f"{busy}; tried again next hour"}


def run_for_every_profile() -> List[Dict[str, Any]]:
    """
    The scheduled job: today's batch for every profile the studio can open
    whose database is at this build's schema. Off where
    INOX_SCHEDULED_MAINTENANCE says so, as the backup job is (tests/conftest.py).
    """
    if os.environ.get("INOX_SCHEDULED_MAINTENANCE") == "off":
        return []
    reports = []
    for profile_id in paths.profile_ids():
        try:
            database = os.path.join(paths.get_profile_home(profile_id), "data", paths.DB_FILENAME)
            if not os.path.exists(database):
                continue
            reader = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            try:
                version = reader.execute("PRAGMA user_version").fetchone()[0]
            finally:
                reader.close()
            if version != SCHEMA_VERSION:
                continue
            with paths.using_profile(profile_id):
                reports.append({"profile_id": profile_id, **run_scheduled()})
        except Exception:
            logger.warning("From your record: the daily batch failed for profile %s.", profile_id, exc_info=True)
    return reports


# ---------------------------------------------------------------------------
# What the screen reads
# ---------------------------------------------------------------------------

def _said_time(stamp: Optional[str]) -> str:
    if not stamp:
        return "at a time not recorded"
    try:
        moment = datetime.fromisoformat(stamp).astimezone()
    except ValueError:
        return "at a time not recorded"
    return moment.strftime("%H:%M")


def read_today(day: Optional[date] = None) -> Dict[str, Any]:
    """
    Today's batch, or the newest one before it with the sentence that says
    today's run has not happened yet. A SELECT: nothing is computed here.
    """
    day = day or local_today()
    conn = get_db()
    try:
        run = _today_run(conn, day)
        shown_day = day if run and run["local_ok"] else None
        if shown_day is None:
            last = _last_run(conn, day)
            shown_day = date.fromisoformat(last["day"]) if last else None
            run = last
        cards = record_cards.read_batch(conn, shown_day) if shown_day else []
        if shown_day == day:
            when = f"computed today at {_said_time(run.get('finished_at'))}"
        elif shown_day == day - timedelta(days=1):
            when = (f"computed yesterday at {_said_time(run.get('finished_at'))}; "
                    "today's run has not happened yet")
        elif shown_day:
            when = (f"computed on {shown_day.isoformat()} at {_said_time(run.get('finished_at'))}; "
                    "today's run has not happened yet")
        else:
            when = ("nothing computed yet: the first batch is built the first time the studio runs each day, "
                    "within a few minutes of starting")
        carried = run.get("carried_from") if run else None
        marks: Dict[str, List[str]] = {}
        if shown_day:
            for row in conn.execute("SELECT card_id, mark FROM card_marks WHERE day = ?", (shown_day.isoformat(),)):
                marks.setdefault(row[0], []).append(row[1])
        days = [r[0] for r in conn.execute(
            "SELECT day FROM daily_run WHERE local_ok = 1 AND day <= ? ORDER BY day DESC LIMIT ?",
            (day.isoformat(), VISIBLE_DAYS))]
        return {
            "day": day.isoformat(),
            "batch_day": shown_day.isoformat() if shown_day else None,
            "computed": when,
            "nothing_new": (f"Nothing new since {carried}: your posts, readings, comments, asks and marks are as they "
                            f"were, so the cards are the same, and only the date's own card moved.") if carried else None,
            "run": {key: run.get(key) for key in ("day", "finished_at", "seed", "rerolled_at", "model_status",
                                                  "model_note", "dropped_cards", "note", "carried_from",
                                                  "estimated_cost_usd", "price_date")} if run else None,
            "cards": [dict(card, marks=sorted(marks.get(card["card_id"], []))) for card in cards],
            "days": days,
        }
    finally:
        conn.close()


def read_day(day: date) -> Dict[str, Any]:
    """An earlier day's batch, as it was, with the marks made on it."""
    conn = get_db()
    try:
        run = conn.execute("SELECT * FROM daily_run WHERE day = ?", (day.isoformat(),)).fetchone()
        marks: Dict[str, List[str]] = {}
        for row in conn.execute("SELECT card_id, mark FROM card_marks WHERE day = ?", (day.isoformat(),)):
            marks.setdefault(row[0], []).append(row[1])
        return {"day": day.isoformat(), "run": dict(run) if run else None,
                "cards": [dict(card, marks=sorted(marks.get(card["card_id"], [])))
                          for card in record_cards.read_batch(conn, day)]}
    finally:
        conn.close()


def status() -> Dict[str, Any]:
    """The job's state, for a Health row: the last run, and whether today's has happened."""
    day = local_today()
    conn = get_db()
    try:
        today = _today_run(conn, day)
        last = today if today and today["local_ok"] else _last_run(conn, day)
        return {
            "job": "record_daily_batch",
            "checked": "hourly, while the studio runs; the first check a minute after it starts",
            "today": day.isoformat(),
            "today_built": bool(today and today["local_ok"]),
            "last_run": {key: last.get(key) for key in ("day", "finished_at", "note", "carried_from", "model_status",
                                                        "dropped_cards")} if last else None,
        }
    finally:
        conn.close()
