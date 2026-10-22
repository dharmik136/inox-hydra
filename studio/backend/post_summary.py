"""
Per-post summary: who engaged with each post, and how it read at two days.
==========================================================================

Posts, Analytics, Patterns, Outbound and Today each answered "who engaged with
this post" by reading every row of lead_interactions into Python on every
load. On three years of one prolific creator (500,000 interactions, 49,142
leads, 1,417 posts) that was 0.4 to 1.9 s a screen, and it grows with every
reaction captured.

post_engagement holds one row per post: the people counts the screens show,
the first people the Posts screen lists, every lead's id (so a topic's people
can be counted once across its posts), the reading closest to two days old
and the latest reading. The screens read 1,417 rows instead of 500,000.

How it stays true to the raw rows:

- Triggers (migration 21) mark a post's row stale whenever anything it is
  computed from changes: an interaction added, removed or moved, a lead's
  name, score or status changed, a lead forgotten (its interactions go with
  it), a reading written. The triggers only mark; they are cheap, and they
  cover every writer, including direct SQL and the forget trigger.
- The writers that capture interactions refresh the rows they marked, in
  their own transaction, so a capture leaves the summary current.
- Every reader refreshes whatever is still marked before reading, so a path
  that only marked (a status change, a forget, a bulk archive) is caught up
  on the next read. If another writer holds the lock, the reader computes
  the stale rows for itself rather than wait, and leaves them marked.
- Migration 21 builds every row from scratch, and tests compare the table
  with a fresh computation from the raw rows.

Strict Invariants:
- Zero em-dashes.
- Every number here is computed from rows the studio holds; nothing is estimated.
"""

import json
import sqlite3
import threading
from typing import Any, Dict, Iterable, List, Optional

try:
    from . import results
except ImportError:
    import results

# The Posts screen lists this many people per post, commenters first.
TOP_PEOPLE = 12

# Posts are compared at the same age: the reading closest to two days old,
# within a window either side. Today reads these constants from here.
READING_AT_HOURS = 48.0
READING_WINDOW = (36.0, 72.0)

# The tier cut points and who counts as qualified are results.py's, which the
# CRM reads too, so the same person cannot be qualified on one screen and not
# on another. They were written out as numbers in four files.
VIP_SCORE = results.VIP_SCORE
QUALIFIED_SCORE = results.QUALIFIED_SCORE

# Lead statuses that mean the creator went on to talk to the person.
CONVERSATION_STATUSES = results.CONVERSATION_STATUSES

# Lead ids are joined with the unit separator, which splits far faster than
# JSON parses; a set of ids that contains it is stored as JSON after a record
# separator instead, so any id round-trips exactly.
_SEP = "\x1f"
_JSON_MARK = "\x1e"

COLUMNS = ("post_urn", "people", "commenters", "vip", "qualified", "icp_known", "icp_sum",
           "conversations", "folded_reactions", "people_json", "lead_ids", "reading_48h", "latest_reading")

# lead_interactions.lead_id is declared INTEGER and leads.id is TEXT, so a
# join written l.id = i.lead_id applies numeric affinity to leads.id and can
# use no index from the interaction side. CAST(... AS TEXT) has no affinity,
# so the comparison is made as TEXT and the leads primary key serves it. The
# column's type is fixed by the phase 3 rebuild of lead_interactions.
LEAD_JOIN = "JOIN leads l ON l.id = CAST(i.lead_id AS TEXT)"


# What a stale mark says needs recomputing. A capture marks the engagement of
# one post; reading a post's figures marks only its readings, which are much
# cheaper to recompute, so importing 1,417 posts' figures stays fast.
ENGAGEMENT = 1
READINGS = 2

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS post_engagement (
        post_urn TEXT PRIMARY KEY,
        people INTEGER NOT NULL DEFAULT 0,
        commenters INTEGER NOT NULL DEFAULT 0,
        vip INTEGER NOT NULL DEFAULT 0,
        qualified INTEGER NOT NULL DEFAULT 0,
        icp_known INTEGER NOT NULL DEFAULT 0,
        icp_sum REAL NOT NULL DEFAULT 0,
        conversations INTEGER NOT NULL DEFAULT 0,
        folded_reactions INTEGER NOT NULL DEFAULT 0,
        people_json TEXT,
        lead_ids TEXT,
        reading_48h TEXT,
        latest_reading TEXT,
        stale INTEGER NOT NULL DEFAULT 0
    ) WITHOUT ROWID
    """,
    # An interaction added, removed or moved to another post or person.
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_interaction_added AFTER INSERT ON lead_interactions
    WHEN NEW.post_urn IS NOT NULL AND NEW.post_urn != ''
    BEGIN
        INSERT INTO post_engagement (post_urn, stale) VALUES (NEW.post_urn, 1)
        ON CONFLICT(post_urn) DO UPDATE SET stale = stale | 1;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_interaction_removed AFTER DELETE ON lead_interactions
    WHEN OLD.post_urn IS NOT NULL AND OLD.post_urn != ''
    BEGIN
        UPDATE post_engagement SET stale = stale | 1 WHERE post_urn = OLD.post_urn AND (stale & 1) = 0;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_interaction_changed
    AFTER UPDATE OF post_urn, lead_id, interaction_type ON lead_interactions
    BEGIN
        UPDATE post_engagement SET stale = stale | 1 WHERE post_urn = OLD.post_urn AND (stale & 1) = 0;
        INSERT INTO post_engagement (post_urn, stale)
        SELECT NEW.post_urn, 1 WHERE NEW.post_urn IS NOT NULL AND NEW.post_urn != ''
        ON CONFLICT(post_urn) DO UPDATE SET stale = stale | 1;
    END
    """,
    # What the summary shows of a person: their name, score and status. The
    # capture rewrites name and score on every engagement, so only a real
    # change marks anything.
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_lead_changed
    AFTER UPDATE OF full_name, name, icp_score, lead_status ON leads
    WHEN OLD.full_name IS NOT NEW.full_name OR OLD.name IS NOT NEW.name
      OR OLD.icp_score IS NOT NEW.icp_score OR OLD.lead_status IS NOT NEW.lead_status
    BEGIN
        UPDATE post_engagement SET stale = stale | 1
        WHERE (stale & 1) = 0 AND post_urn IN (SELECT post_urn FROM lead_interactions WHERE lead_id = NEW.id);
    END
    """,
    # Readings of a post's figures.
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_reading_added AFTER INSERT ON post_metric_observations
    WHEN NEW.activity_urn != ''
    BEGIN
        INSERT INTO post_engagement (post_urn, stale) VALUES (NEW.activity_urn, 2)
        ON CONFLICT(post_urn) DO UPDATE SET stale = stale | 2;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_reading_changed AFTER UPDATE ON post_metric_observations
    BEGIN
        UPDATE post_engagement SET stale = stale | 2 WHERE post_urn = OLD.activity_urn AND (stale & 2) = 0;
        INSERT INTO post_engagement (post_urn, stale)
        SELECT NEW.activity_urn, 2 WHERE NEW.activity_urn != ''
        ON CONFLICT(post_urn) DO UPDATE SET stale = stale | 2;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_reading_removed AFTER DELETE ON post_metric_observations
    BEGIN
        UPDATE post_engagement SET stale = stale | 2 WHERE post_urn = OLD.activity_urn AND (stale & 2) = 0;
    END
    """,
)

_NO_ENGAGEMENT = {"people": 0, "commenters": 0, "vip": 0, "qualified": 0, "icp_known": 0, "icp_sum": 0.0,
                  "conversations": 0, "folded_reactions": 0, "people_json": None, "lead_ids": None}
_NO_READINGS = {"reading_48h": None, "latest_reading": None}

# ---------------------------------------------------------------------------
# Computing rows from the raw tables
# ---------------------------------------------------------------------------

def _encode_ids(ids: List[str]) -> str:
    if any(_SEP in i or _JSON_MARK in i for i in ids):
        return _JSON_MARK + json.dumps(ids)
    return _SEP.join(ids)


def lead_ids_of(row: Any) -> List[str]:
    """Every lead who engaged with the post, as leads.id values."""
    value = row["lead_ids"] if row is not None else None
    if not value:
        return []
    if value.startswith(_JSON_MARK):
        return json.loads(value[1:])
    return value.split(_SEP)


def people_of(row: Any) -> List[Dict[str, Any]]:
    """The people the Posts screen lists for the post, in its order."""
    value = row["people_json"] if row is not None else None
    if not value:
        return []
    return [{"lead_id": p[0], "name": p[1], "commented": bool(p[2]), "status": p[3]} for p in json.loads(value)]


def _rows(conn, sql, params=()):
    """Rows addressable by column name, whatever the connection's row factory."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    return cursor.execute(sql, params)


def _in_clause(keys: Optional[List[str]], column: str):
    if keys is None:
        return f"{column} IS NOT NULL AND {column} != ''", []
    return f"{column} IN (SELECT value FROM json_each(?))", [json.dumps(list(keys))]


def _people_rows(conn, keys: Optional[List[str]]):
    """One row per (post, person) for the posts asked for, grouped by post."""
    where, params = _in_clause(keys, "i.post_urn")
    return _rows(
        conn, f"""
        SELECT i.post_urn AS post_urn, l.id AS lead_id,
               MAX(i.interaction_type = 'COMMENT') AS commented,
               COALESCE(l.full_name, l.name) AS name, l.lead_status AS status, l.icp_score AS icp,
               l.rowid AS lead_row
        FROM lead_interactions i {LEAD_JOIN}
        WHERE {where}
        GROUP BY i.post_urn, l.id
        ORDER BY i.post_urn
        """, params)


def _engagement(people: List[sqlite3.Row]) -> Dict[str, Any]:
    known = [p["icp"] for p in people if p["icp"] is not None]
    # Commenters first, then by name. The tie on a name falls to the lead's
    # place in the leads table, which is the order the screen used to meet
    # them in when it read every interaction.
    ordered = sorted(people, key=lambda p: (not p["commented"], p["name"] or "", p["lead_row"]))
    return {
        "people": len(people),
        "commenters": sum(1 for p in people if p["commented"]),
        "vip": sum(1 for score in known if score >= VIP_SCORE),
        # By the one rule: a person the creator is talking to is qualified
        # whatever a keyword guess about their job title says. This counted
        # scores only, while the topic table counted scores or stages.
        "qualified": sum(1 for p in people if results.is_qualified(p["icp"], p["status"])),
        "icp_known": len(known),
        # Rounded so that the same scores give the same sum whichever order
        # they are added in, the fold's included.
        "icp_sum": round(sum(known), 6),
        "conversations": sum(1 for p in people if (p["status"] or "") in CONVERSATION_STATUSES),
        "folded_reactions": 0,
        "people_json": json.dumps([[str(p["lead_id"]), p["name"], 1 if p["commented"] else 0, p["status"]]
                                   for p in ordered[:TOP_PEOPLE]]),
        "lead_ids": _encode_ids([str(p["lead_id"]) for p in people]),
    }


READING_FIELDS = ("age_hours", "impressions", "reactions", "comments", "reposts", "source")


def _readings(conn, keys: Optional[List[str]]) -> Dict[str, Dict[str, Optional[str]]]:
    where, params = _in_clause(keys, "activity_urn")
    out: Dict[str, Dict[str, Optional[str]]] = {}
    # Closest to two days old; on a tie the earlier reading, which is the one
    # Today chose when it read them in observed order. Each reading carries
    # the page it was read from: the feed card and the post's own analytics
    # page count different things, and a figure that does not say which it
    # came from cannot be compared with another.
    for r in _rows(
            conn, f"SELECT activity_urn, {', '.join(READING_FIELDS)} FROM post_metric_observations "
            f"WHERE {where} AND age_hours BETWEEN ? AND ? ORDER BY activity_urn, observed_at, id",
            (*params, *READING_WINDOW)):
        entry = out.setdefault(r["activity_urn"], {"best": None, "latest": None})
        best = entry["best"]
        if best is None or abs(r["age_hours"] - READING_AT_HOURS) < abs(best["age_hours"] - READING_AT_HOURS):
            entry["best"] = {k: r[k] for k in READING_FIELDS}
    # The latest reading, which is the post's figures: results.figures draws
    # it the same way, preferring the post's own analytics page where two
    # pages were read in the same hour.
    urns = keys if keys is not None else [
        r[0] for r in conn.execute("SELECT DISTINCT activity_urn FROM post_metric_observations")]
    for urn in urns:
        r = _rows(
            conn, f"SELECT {', '.join(READING_FIELDS)}, observed_at FROM post_metric_observations "
            "WHERE activity_urn = ? ORDER BY observed_at DESC, "
            "CASE source WHEN 'post_analytics' THEN 2 ELSE 1 END DESC, id DESC LIMIT 1", (urn,)).fetchone()
        if r is not None:
            entry = out.setdefault(urn, {"best": None, "latest": None})
            entry["latest"] = {k: r[k] for k in READING_FIELDS + ("observed_at",)}
    return {urn: {"reading_48h": json.dumps(e["best"]) if e["best"] else None,
                  "latest_reading": json.dumps(e["latest"]) if e["latest"] else None}
            for urn, e in out.items()}



def _engagements(conn, keys: Optional[List[str]]) -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    current, people = None, []
    for r in _people_rows(conn, keys):
        if r["post_urn"] != current:
            if people:
                rows[current] = _engagement(people)
            current, people = r["post_urn"], []
        people.append(r)
    if people:
        rows[current] = _engagement(people)
    for urn, fold in folded(conn, keys).items():
        _add_folded(rows.setdefault(urn, dict(_NO_ENGAGEMENT)), fold)
    return rows


# What a fold adds to a post's own counts. The folded reactors who engaged
# with the post in no other way are its people still; the others are counted
# from their comment or repost, so nobody is counted twice.
FOLDED_TIERS = ("people", "vip", "qualified", "icp_known", "icp_sum", "conversations")


def _add_folded(row: Dict[str, Any], fold: Dict[str, Any]) -> None:
    for column in FOLDED_TIERS:
        row[column] = row[column] + (fold.get(column) or 0)
    row["icp_sum"] = round(row["icp_sum"], 6)
    row["folded_reactions"] = row["folded_reactions"] + int(fold.get("reactions") or 0)


def folded(conn, keys: Optional[Iterable[str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Reactions the retention job (retention.py, batch R4) folded into counts,
    per post, as retention.folded_counts() keeps them: reactions older than
    24 months, whose rows are gone but which still happened, and of the
    people who made them, those with no other engagement on the post and
    their tiers. Empty before the fold's migration has run.

    The fold deletes the reaction rows in the same transaction as it adds the
    counts, and deleting them marks the post's summary stale, so the counts
    are read again whenever they move.
    """
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'reaction_folds'").fetchone():
        return {}
    # Imported here: retention reads the CRM, which refreshes this summary.
    try:
        from . import retention
    except ImportError:
        import retention
    by_post = retention.folded_counts(conn, leads=False)["by_post"]
    wanted = None if keys is None else set(keys)
    return {urn: fold for urn, fold in by_post.items()
            if (wanted is None or urn in wanted) and (fold.get("reactions") or fold.get("people"))}


def compute(conn, keys: Optional[Iterable[str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Summary rows computed from the raw tables: for the posts named, or for
    every post when keys is None. A post with no engagement and no reading
    has no row.
    """
    keys = None if keys is None else [k for k in dict.fromkeys(keys) if k]
    if keys == []:
        return {}
    rows = _engagements(conn, keys)
    for urn, readings in _readings(conn, keys).items():
        rows.setdefault(urn, dict(_NO_ENGAGEMENT)).update(readings)
    for urn, row in rows.items():
        for column, empty in _NO_READINGS.items():
            row.setdefault(column, empty)
        row["post_urn"] = urn
    return rows


def combined(conn, keys: Iterable[str]) -> Dict[str, Any]:
    """
    One summary computed across several spellings of the same post, with
    each person counted once. For the rare post whose engagement was recorded
    under more than one URN; every other post reads its stored row.
    """
    people: Dict[str, Dict[str, Any]] = {}
    for r in _people_rows(conn, [k for k in keys if k]):
        person = people.get(r["lead_id"])
        if person is None:
            people[r["lead_id"]] = dict(zip(r.keys(), tuple(r)))
        elif r["commented"]:
            person["commented"] = 1
    engagement = _engagement(list(people.values()))
    for fold in folded(conn, [k for k in keys if k]).values():
        _add_folded(engagement, fold)
    return engagement



def _stored(conn, keys: Optional[List[str]]) -> Dict[str, Dict[str, Any]]:
    where, params = ("1", []) if keys is None else ("post_urn IN (SELECT value FROM json_each(?))",
                                                   [json.dumps(list(keys))])
    return {r["post_urn"]: {**{c: r[c] for c in COLUMNS}, "stale": r["stale"]}
            for r in _rows(conn, f"SELECT {', '.join(COLUMNS)}, stale FROM post_engagement WHERE {where}", params)}


def _recompute(conn, marked: Dict[str, Dict[str, Any]]) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    New values for the marked rows: only the parts their marks name are
    recomputed. None where the post no longer has anything to summarise.
    """
    engagement_keys = [urn for urn, row in marked.items() if row["stale"] & ENGAGEMENT]
    reading_keys = [urn for urn, row in marked.items() if row["stale"] & READINGS]
    engagements = _engagements(conn, engagement_keys) if engagement_keys else {}
    readings = _readings(conn, reading_keys) if reading_keys else {}
    out: Dict[str, Optional[Dict[str, Any]]] = {}
    for urn, row in marked.items():
        new = {c: row[c] for c in COLUMNS}
        if row["stale"] & ENGAGEMENT:
            new.update(engagements.get(urn, _NO_ENGAGEMENT))
        if row["stale"] & READINGS:
            new.update(readings.get(urn, _NO_READINGS))
        out[urn] = new if (new["people"] or new["folded_reactions"] or new["reading_48h"]
                           or new["latest_reading"]) else None
    return out


def _write(conn, rows: Dict[str, Optional[Dict[str, Any]]]) -> None:
    gone = [urn for urn, row in rows.items() if row is None]
    if gone:
        conn.execute("DELETE FROM post_engagement WHERE post_urn IN (SELECT value FROM json_each(?))",
                     (json.dumps(gone),))
    conn.executemany(
        f"INSERT OR REPLACE INTO post_engagement ({', '.join(COLUMNS)}, stale) "
        f"VALUES ({', '.join('?' for _ in COLUMNS)}, 0)",
        [tuple(row[c] for c in COLUMNS) for row in rows.values() if row is not None])


def rebuild(conn) -> int:
    """Every row from scratch, inside the caller's transaction. Returns the row count."""
    rows = compute(conn)
    conn.execute("DELETE FROM post_engagement")
    _write(conn, rows)
    return len(rows)


def _marked(conn, keys: Optional[List[str]] = None, limit: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    where, params = ("stale != 0", []) if keys is None else (
        "stale != 0 AND post_urn IN (SELECT value FROM json_each(?))", [json.dumps(list(keys))])
    if limit is not None:
        where += f" LIMIT {int(limit):d}"
    return {r["post_urn"]: {**{c: r[c] for c in COLUMNS}, "stale": r["stale"]}
            for r in _rows(conn, f"SELECT {', '.join(COLUMNS)}, stale FROM post_engagement WHERE {where}", params)}


# Rows recomputed per transaction when catching up. A changed name or score
# marks every post the person engaged with, 1,136 for the busiest lead of
# three years; recomputed in one transaction that held the write lock for
# 1.1 s, and the captures queued behind it failed with "database is locked".
CATCH_UP_BATCH = 50
_CATCH_UP_WAIT_MS = 250

# Set while a restore replaces the database file. The background catch-up
# holds a connection on that file, and Windows refuses to replace a file any
# handle holds, so the catch-up puts the database down and stays off it until
# the restore is through. Rows left marked are caught up by the next reader.
_stopping = threading.Event()


def catch_up(conn, batch: int = CATCH_UP_BATCH, pause: float = 0.0) -> int:
    """
    Recomputes every row marked stale, `batch` rows to a transaction, so a
    capture waiting for the lock waits for one batch at most. Stops early,
    leaving the rest marked, when another writer keeps the lock longer than
    a quarter of a second. `pause` seconds between batches leave the lock to
    writers that are waiting for it: SQLite's busy handler polls, so a loop
    that takes the lock again at once can starve them. Returns how many rows
    were recomputed.
    """
    import time
    if conn.in_transaction:
        return refresh(conn)
    done = 0
    rounds = conn.execute("SELECT COUNT(*) FROM post_engagement WHERE stale != 0").fetchone()[0] // batch + 2
    previous = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    conn.execute(f"PRAGMA busy_timeout = {_CATCH_UP_WAIT_MS:d}")
    try:
        for _ in range(rounds):
            # Looked for without the lock, so a catch-up with nothing to do
            # never takes it.
            if _stopping.is_set():
                break
            if not conn.execute("SELECT 1 FROM post_engagement WHERE stale != 0 LIMIT 1").fetchone():
                break
            conn.execute("BEGIN IMMEDIATE")
            marked = _marked(conn, limit=batch)
            if marked:
                _write(conn, _recompute(conn, marked))
            conn.commit()
            done += len(marked)
            if len(marked) < batch:
                break
            if pause:
                time.sleep(pause)
    except sqlite3.OperationalError:
        if conn.in_transaction:
            conn.rollback()
    finally:
        conn.execute(f"PRAGMA busy_timeout = {int(previous)}")
    return done


_catch_up_threads: Dict[str, Any] = {}
_catch_up_lock = None
_CATCH_UP_SETTLE_S = 0.3
_CATCH_UP_PAUSE_S = 0.03
_CATCH_UP_ROUNDS = 50


def catch_up_later(db_path: Optional[str] = None) -> None:
    """
    Catches up the rows a write marked, in the background, outside the
    writer's transaction. One worker per database; a second call while one
    runs leaves it to that one, which reads the marks until none are left.
    """
    import threading
    global _catch_up_lock
    try:
        from . import sqlite_open
        from .paths import get_db_path
    except ImportError:
        import sqlite_open
        from paths import get_db_path
    if db_path is None:
        db_path = get_db_path()
    if _catch_up_lock is None:
        _catch_up_lock = threading.Lock()
    if _stopping.is_set():
        return
    with _catch_up_lock:
        running = _catch_up_threads.get(db_path)
        if running is not None and running.is_alive():
            running.again = True
            return

        def work():
            import time
            me = threading.current_thread()
            try:
                # A moment first, so a burst of captures is caught up once,
                # after it, not between every two of them.
                if _stopping.wait(_CATCH_UP_SETTLE_S):
                    return
                for _ in range(_CATCH_UP_ROUNDS):
                    me.again = False
                    if _stopping.is_set():
                        return
                    conn = sqlite_open.connect(db_path, timeout=5.0)
                    try:
                        catch_up(conn, pause=_CATCH_UP_PAUSE_S)
                        left = conn.execute("SELECT 1 FROM post_engagement WHERE stale != 0 LIMIT 1").fetchone()
                    finally:
                        conn.close()
                    if not left:
                        return
                    # Writers kept the lock, or marked more: try again shortly.
                    if _stopping.wait(_CATCH_UP_SETTLE_S):
                        return
            except Exception:
                # A database removed or replaced underneath; the readers catch up.
                return

        worker = threading.Thread(target=work, name="inox-summary-catch-up", daemon=True)
        worker.again = False
        _catch_up_threads[db_path] = worker
        worker.start()


def stop_catch_up(timeout: float = 10.0) -> bool:
    """
    Asks the background catch-up to put the database down, and waits for it.

    Called before a restore replaces the database file: a connection open on
    that file is what Windows refuses to replace. Rows still marked stale are
    the restored database's problem, and its readers catch them up. True when
    no worker is left holding a connection.
    """
    _stopping.set()
    for worker in list(_catch_up_threads.values()):
        worker.join(timeout)
    return not any(worker.is_alive() for worker in _catch_up_threads.values())


def resume_catch_up() -> None:
    """Lets the background catch-up run again, after a restore."""
    _stopping.clear()


def wait_for_catch_up(timeout: float = 10.0) -> bool:
    """Waits for the background catch-up to finish. True when none is running."""
    for worker in list(_catch_up_threads.values()):
        worker.join(timeout)
    return not any(worker.is_alive() for worker in _catch_up_threads.values())


def refresh(conn, keys: Optional[Iterable[str]] = None) -> int:
    """
    Recomputes the rows marked stale (of the posts named, or all of them),
    inside the caller's transaction. For the writers, which already hold the
    write lock. Returns how many rows were recomputed.
    """
    marked = _marked(conn, None if keys is None else [k for k in keys if k])
    if marked:
        _write(conn, _recompute(conn, marked))
    return len(marked)


def ensure_row(conn, post_urn: str) -> None:
    """
    The summary row of a post that has just been published, so the screens
    have somewhere to read before anybody engages with it.

    Zero people and no reading is what the row says, which is the truth about
    a post that went out a moment ago. It is not marked stale: there is
    nothing to compute from yet. A later recompute drops it again once it is
    still empty, and every reader already treats a missing row as no
    engagement, so the two agree either way. Inside the caller's transaction.
    """
    if not post_urn:
        return
    conn.execute("INSERT INTO post_engagement (post_urn, stale) VALUES (?, 0) "
                 "ON CONFLICT(post_urn) DO NOTHING", (post_urn,))


def current(conn, keys: Optional[Iterable[str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    The summary rows a screen reads, keyed by post URN, every one current.

    Rows still marked stale are recomputed first and written back, a batch
    to a transaction (catch_up). When another writer holds the lock, the
    rest are computed for this read only and left marked, so a screen never
    waits on a capture in progress and a capture never waits long on it.
    """
    # The people's scores first, because the counts below are of qualified and
    # VIP people and a score whose inputs have changed is not one. Imported
    # here: the CRM reads this module. Writing a score marks the posts that
    # person engaged with, which the catch-up below then recomputes, so the
    # two run in this order and not the other.
    try:
        from . import crm
    except ImportError:
        import crm
    if not conn.in_transaction:
        crm.scores_current(conn)

    fresh: Dict[str, Optional[Dict[str, Any]]] = {}
    if conn.execute("SELECT 1 FROM post_engagement WHERE stale != 0 LIMIT 1").fetchone():
        if not conn.in_transaction:
            catch_up(conn)
        if conn.execute("SELECT 1 FROM post_engagement WHERE stale != 0 LIMIT 1").fetchone():
            fresh = _recompute(conn, _marked(conn))
    wanted = None if keys is None else [k for k in keys if k]
    out: Dict[str, Dict[str, Any]] = {}
    for urn, row in _stored(conn, wanted).items():
        if row["stale"]:
            if fresh.get(urn) is not None:
                out[urn] = fresh[urn]
            continue
        del row["stale"]
        out[urn] = row
    return out


def reading_of(row: Optional[Dict[str, Any]], which: str) -> Optional[Dict[str, Any]]:
    """The stored reading ("reading_48h" or "latest_reading") as a dict, or None."""
    value = row.get(which) if row else None
    return json.loads(value) if value else None


def differences(conn) -> List[str]:
    """
    Where the stored summary and a fresh computation from the raw rows
    disagree, after catching up anything marked stale. Empty when consistent.
    """
    stored = current(conn)
    fresh = compute(conn)
    problems = []
    for urn in sorted(set(stored) | set(fresh)):
        a, b = stored.get(urn), fresh.get(urn)
        if a is None or b is None:
            problems.append(f"{urn}: {'missing' if a is None else 'extra'} row")
            continue
        for column in COLUMNS:
            left, right = a[column], b[column]
            if column == "lead_ids":
                left, right = sorted(lead_ids_of(a)), sorted(lead_ids_of(b))
            if column == "icp_sum":
                left, right = round(left, 6), round(right, 6)
            if left != right:
                problems.append(f"{urn}: {column} stored {left!r}, raw rows say {right!r}")
    return problems
