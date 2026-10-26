"""
Who the creator is, and what their own LinkedIn shows.
======================================================

Onboarding in one sentence: the creator opens their own profile in the bridge
browser, the studio asks "is this you?", and from then on it can tell the
creator's pages, posts and activity apart from everybody else's.

That last clause is the point. Before this module every capture read "a
LinkedIn page" and never "my LinkedIn page". The profile page was excluded
entirely because a stranger's and the creator's look the same to code that does
not know the difference, the creator's own posts were never recognised, and the
creator liking someone else's post was stored as the creator being that
person's lead.

The rule this file enforces, in one place:

  Nothing is stored as the creator's until the creator has confirmed who they
  are, and after that nothing is stored as theirs unless it carries the
  confirmed identity.

A capture before confirmation is held as a candidate, which the onboarding
screen shows for a yes or no. A capture of somebody else's profile after
confirmation is refused, not stored and not merged.

Strict Invariants:
- Zero em-dashes.
- A count never read is NULL, never 0. Zero is a measurement.
- Nothing here makes a network request. The extension reads pages the creator
  has open; this module only decides what to keep.
"""

import bisect
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote

try:
    from .text_cut import clip
except ImportError:
    from text_cut import clip

try:
    from . import post_summary
    from . import ingest_contract
    from . import changes
    from .database import get_db
except ImportError:
    import post_summary
    import ingest_contract
    import changes
    from database import get_db

# How recently the extension must have been heard from to count as connected.
# It beats every 60 seconds while a LinkedIn tab is open, so two missed beats
# is a fair definition of gone.
BRIDGE_FRESH_SECONDS = 150

# A history import the creator asked for is picked up by the extension the next
# time an activity page is open. After this long it is treated as abandoned, so
# a click from last week cannot start a scroll today.
IMPORT_REQUEST_TTL = timedelta(minutes=30)

HEARTBEAT_RETENTION = timedelta(days=7)

IMPORT_KINDS = ("posts", "comments", "reactions")

_ACTIVITY_URN = re.compile(r"^urn:li:activity:(\d{10,25})$")

# Evidence a profile page belongs to the person viewing it. Named so the
# onboarding screen can say why the studio thinks this is you, and so an
# unknown label from a newer extension is refused rather than trusted.
KNOWN_SELF_EVIDENCE = {
    "self_profile_flag": "LinkedIn marked the page as your own profile",
    "owner_edit_controls": "Edit controls only you see were on the page",
    "me_redirect": "LinkedIn sent /in/me/ to this profile",
    "nav_profile_link": "Your own navigation menu links to this profile",
}


class RefusedCapture(ValueError):
    """A capture this module will not store, with a reason the caller can show."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_vanity(value: str) -> bool:
    """
    Letters, marks and digits of any script, '-' and '_', starting with a
    letter or digit, 2 to 100 long.

    The pattern was a-z and 0-9 only, so a creator whose address carries an
    e-acute, a u-umlaut, or Chinese, Cyrillic, Arabic or Devanagari letters had
    every profile capture refused and could never pass step 2. Marks are
    allowed because Devanagari and other scripts write vowels with them.
    """
    if not 2 <= len(value) <= 100 or unicodedata.category(value[0])[0] not in "LN":
        return False
    return all(ch in "-_" or unicodedata.category(ch)[0] in "LMN" for ch in value)


def normalise_vanity(raw: Any) -> str:
    """
    The public identifier from `/in/<vanity>/`, in one canonical spelling.

    Accepts a bare vanity or any LinkedIn profile URL. Percent-decoded, in NFC,
    lowercased, without query string or trailing slash, so `jos%C3%A9-x` and
    `josé-x` are one person, which is how the extension reads them. Returns ""
    for anything that is not one.
    """
    if not isinstance(raw, str):
        return ""
    value = raw.strip()
    match = re.search(r"linkedin\.com/in/([^/?#]+)", value, re.IGNORECASE)
    if match:
        value = match.group(1)
    try:
        value = unquote(value, errors="strict")
    except UnicodeDecodeError:
        return ""
    value = unicodedata.normalize("NFC", value.strip("/")).lower()
    return value if _is_vanity(value) else ""


def profile_url_for(vanity: str) -> str:
    """The profile address for a vanity, percent-encoded so a browser can be handed it."""
    return f"https://www.linkedin.com/in/{quote(vanity, safe='-_')}/"


def _text(value: Any, limit: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return clip(value, limit) if value else None


def _count(value: Any) -> Optional[int]:
    """A count from a capture, or None when the page did not show one."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def find_archive_twin(conn, urn: str, text: str, archive_only: bool = True) -> Optional[str]:
    try:
        from .archive_import import find_twin
    except ImportError:
        from archive_import import find_twin
    return find_twin(conn, urn, text, archive_only=archive_only)


def forget_archive(conn) -> None:
    try:
        from .archive_import import forget
    except ImportError:
        from archive_import import forget
    forget(conn)


def published_at_from_urn(activity_urn: str) -> Optional[str]:
    """
    When a post was published, read from its activity id.

    LinkedIn activity ids are time-ordered: the high bits are milliseconds since
    the Unix epoch, so `id >> 22` is the publish time. This is the one date the
    page never needs to show for the studio to know it, which matters because
    the feed prints "3w" and "1mo" rather than a date.

    The result is refused when it lands outside LinkedIn's lifetime, so an id
    that does not follow the scheme yields None rather than a nonsense date.
    """
    match = _ACTIVITY_URN.match(activity_urn or "")
    if not match:
        return None
    millis = int(match.group(1)) >> 22
    moment = datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
    if moment.year < 2003 or moment > datetime.now(timezone.utc) + timedelta(days=1):
        return None
    return moment.isoformat()


# ---------------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------------

def record_heartbeat(extension_version: Any = None, page_kind: Any = None) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO bridge_heartbeats (seen_at, extension_version, page_kind) VALUES (?,?,?)",
                (now.isoformat(), _text(extension_version, 40), _text(page_kind, 40)),
            )
            conn.execute(
                "DELETE FROM bridge_heartbeats WHERE seen_at < ?",
                ((now - HEARTBEAT_RETENTION).isoformat(),),
            )
    finally:
        conn.close()
    return {"status": "success", "seen_at": now.isoformat()}


def bridge_status() -> Dict[str, Any]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT seen_at, extension_version, page_kind FROM bridge_heartbeats "
            "ORDER BY seen_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {"connected": False, "last_seen_at": None, "seconds_ago": None,
                "extension_version": None, "page_kind": None}

    seen = datetime.fromisoformat(row["seen_at"])
    ago = max(0, int((datetime.now(timezone.utc) - seen).total_seconds()))
    return {
        "connected": ago <= BRIDGE_FRESH_SECONDS,
        "last_seen_at": row["seen_at"],
        "seconds_ago": ago,
        "extension_version": row["extension_version"],
        "page_kind": row["page_kind"],
    }


# ---------------------------------------------------------------------------
# Capture health
# ---------------------------------------------------------------------------

# The extractors the extension reports on, in the words the Setup screen uses.
EXTRACTORS = {
    "engagers": "Comments and reactions on your posts",
    "profile": "Your profile",
    "activity_posts": "Your posts",
    "activity_comments": "Your comments",
    "activity_reactions": "Your reactions",
    "analytics": "Creator analytics",
    "post_analytics": "Your posts' analytics pages",
    "voyager_feed_updates": "Network reading: your posts' figures",
    "voyager_creator_analytics": "Network reading: creator analytics",
}

# Network reading is off unless the creator switches it on in the extension's
# popup, so these parts never run for most people. Setup lists them only once
# they have: listed always, they read NOT SEEN YET for everyone, and the help's
# advice for that, open the matching page, does nothing for them.
OPT_IN_EXTRACTORS = ("voyager_feed_updates", "voyager_creator_analytics")

CAPTURE_RETENTION = timedelta(days=7)
# Every capture prunes the log, and the prune does not look at which extractor
# a row belongs to, so the engagers reader (twenty six runs in a week on this
# install) was deleting the only row the profile reader had. capture_health
# then reported that reader as never run, and the Setup screen said NOT SEEN
# YET about a reader that had read the creator's profile seven days earlier.
#
# The rarer the reader the sooner it lied: the profile is read once at setup
# and seldom after, so a week into every install that row said the bridge had
# never seen it. Creator analytics is weekly. The readers a creator most needs
# to ask about were the ones the screen was least able to answer for.
#
# So the two rows the screen reads are kept whatever their age: the latest run
# of each extractor, and the latest run of each that read something without
# drift, which is the LAST WORKED date shown beside a drifting reader. Rows
# the screen does not read still age out at the window above.
PRUNE_CAPTURES = """
DELETE FROM captures
 WHERE observed_at < ?
   AND id NOT IN (
         SELECT keep.id FROM captures AS keep
          WHERE keep.observed_at = (SELECT MAX(observed_at) FROM captures
                                     WHERE extractor = keep.extractor)
   )
   AND id NOT IN (
         SELECT keep.id FROM captures AS keep
          WHERE keep.drift IS NULL AND COALESCE(keep.items_seen, 0) > 0
            AND keep.observed_at = (SELECT MAX(observed_at) FROM captures
                                     WHERE extractor = keep.extractor
                                       AND drift IS NULL
                                       AND COALESCE(items_seen, 0) > 0)
   )
"""
DRIFT_RETENTION = timedelta(days=30)


def record_capture(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    One extractor run on one page, as the extension saw it.

    drift names the required fields the extractor could not read on a page
    that plainly had the thing it looks for: comment cards with no readable
    name, a profile with no readable heading. That is the signature of LinkedIn
    changing its markup, and the one failure a creator cannot see for
    themselves, because it looks exactly like nobody engaging.
    """
    if not isinstance(payload, dict) or payload.get("extractor") not in EXTRACTORS:
        raise RefusedCapture("unknown extractor")
    drift = [d for d in (payload.get("drift") or []) if isinstance(d, str)][:10]
    now = datetime.now(timezone.utc)
    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO captures (observed_at, extractor, page_kind, items_seen, items_kept, drift, extension_version) "
                "VALUES (?,?,?,?,?,?,?)",
                (now.isoformat(), payload["extractor"], _text(payload.get("page_kind"), 40),
                 _count(payload.get("items_seen")), _count(payload.get("items_kept")),
                 json.dumps([_text(d, 60) for d in drift]) if drift else None,
                 _text(payload.get("extension_version"), 40)),
            )
            conn.execute(PRUNE_CAPTURES, ((now - CAPTURE_RETENTION).isoformat(),))
    finally:
        conn.close()
    changes.publish("capture", extractor=payload["extractor"], drift=bool(drift))
    return {"status": "success"}


def capture_health() -> List[Dict[str, Any]]:
    """
    Per extractor: when it last read something, and whether its latest run
    drifted. Extractors that have never run are listed too, as never run,
    because an absent row is the question the creator is asking.
    """
    conn = get_db()
    try:
        rows = {}
        for extractor in EXTRACTORS:
            latest = conn.execute(
                "SELECT observed_at, items_seen, items_kept, drift FROM captures "
                "WHERE extractor = ? ORDER BY observed_at DESC LIMIT 1", (extractor,)).fetchone()
            last_good = conn.execute(
                "SELECT observed_at FROM captures WHERE extractor = ? AND drift IS NULL "
                "AND COALESCE(items_seen, 0) > 0 ORDER BY observed_at DESC LIMIT 1", (extractor,)).fetchone()
            rows[extractor] = (latest, last_good)
    finally:
        conn.close()

    health = []
    for extractor, label in EXTRACTORS.items():
        latest, last_good = rows[extractor]
        drift = json.loads(latest["drift"]) if latest and latest["drift"] else []
        health.append({
            "extractor": extractor,
            "label": label,
            "last_run_at": latest["observed_at"] if latest else None,
            "last_good_at": last_good["observed_at"] if last_good else None,
            "drift": drift,
            "state": "never_run" if not latest else ("drifting" if drift else "working"),
        })
    return health


def record_schema_drift(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Records one schema drift event from the extension's Voyager interceptor."""
    if not isinstance(payload, dict):
        raise RefusedCapture("payload must be an object")
    schema_name = _text(payload.get("schema_name"), 80)
    schema_version = _text(payload.get("schema_version"), 40)
    if not schema_name or not schema_version:
        raise RefusedCapture("schema_name and schema_version required")
    drift_fields = payload.get("drift_fields") or []
    top_keys = payload.get("response_top_keys") or []
    now = datetime.now(timezone.utc)
    conn = get_db()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO schema_drift_events
                    (observed_at, schema_name, schema_version, drift_fields, confidence,
                     success, source_url, response_top_keys, extension_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now.isoformat(),
                    schema_name,
                    schema_version,
                    json.dumps(drift_fields) if drift_fields else None,
                    float(payload.get("confidence", 0.0)),
                    1 if payload.get("success") else 0,
                    _text(payload.get("source_url"), 500),
                    json.dumps(top_keys) if top_keys else None,
                    _text(payload.get("extension_version"), 40),
                )
            )
            conn.execute(
                "DELETE FROM schema_drift_events WHERE observed_at < ?",
                ((now - DRIFT_RETENTION).isoformat(),)
            )
    finally:
        conn.close()
    return {"status": "success"}


def record_voyager_ingest(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ingests structured data captured directly from LinkedIn Voyager network responses.
    Updates post metric observations, creator analytics, and records capture health.
    """
    if not isinstance(payload, dict):
        raise RefusedCapture("payload must be an object")
    schema_name = payload.get("schema_name")
    data = payload.get("data")
    if not schema_name or data is None:
        raise RefusedCapture("schema_name and data are required")

    items_seen = len(data) if isinstance(data, list) else (1 if isinstance(data, dict) else 0)
    items_kept = 0
    now = datetime.now(timezone.utc)

    conn = get_db()
    try:
        with conn:
            if schema_name == "feed_updates" and isinstance(data, list):
                for item in data:
                    urn = item.get("urn")
                    if not urn or not _ACTIVITY_URN.match(urn):
                        continue
                    metrics = {
                        "impressions": item.get("impressions"),
                        "reactions": item.get("likes"),
                        "comments": item.get("comments"),
                    }
                    if _record_observation(conn, urn, "voyager_network", metrics):
                        items_kept += 1
                        if metrics.get("impressions") is not None:
                            conn.execute(
                                "UPDATE own_posts SET impressions = ?, last_seen_at = ? WHERE activity_urn = ?",
                                (metrics["impressions"], now.isoformat(), urn)
                            )
            elif schema_name == "creator_analytics" and isinstance(data, list) and data:
                # Only the follower count is kept. It is a reading of one moment,
                # so it is today's figure whatever range the page was showing.
                # impressionAggregate is a total over a window the response does
                # not name, and storing it as today's impressions is the defect
                # migration 5 exists to stop. It stays in the capture log only.
                #
                # The response does not say whose analytics these are, so the
                # bridge names the account signed in to LinkedIn, and a reading
                # from any other account (or none) is refused. It was filed
                # under whichever profile was open in the studio.
                _require_me(conn, payload.get("vanity"))
                entry = data[0] if data else {}
                followers = _count(entry.get("followers"))
                if followers is not None:
                    today = now.strftime("%Y-%m-%d")
                    conn.execute(
                        """
                        INSERT INTO analytics_daily (
                            date, followers, precision, period_label, source,
                            impressions, unique_members_reached, reactions, comments, shares, engagement_rate
                        )
                        -- The figures this reading did not carry are NULL, not
                        -- the schema's DEFAULT 0, which would read as measured.
                        VALUES (?, ?, 'exact', '1d', 'observed', NULL, NULL, NULL, NULL, NULL, NULL)
                        ON CONFLICT(date) DO UPDATE SET
                            followers = excluded.followers
                        """,
                        (today, followers)
                    )
                    items_kept += 1

            # Log to captures table for health visibility
            conn.execute(
                """
                INSERT INTO captures (observed_at, extractor, page_kind, items_seen, items_kept, drift, extension_version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now.isoformat(),
                    f"voyager_{schema_name}",
                    "voyager_api",
                    items_seen,
                    items_kept,
                    None,
                    _text(payload.get("extension_version"), 40)
                )
            )
    finally:
        conn.close()
    changes.publish("account" if schema_name == "creator_analytics" else "readings")

    return {"status": "success", "items_seen": items_seen, "items_kept": items_kept}


def extension_health() -> Dict[str, Any]:
    """Aggregated health report of the Chrome extension, Voyager capture, and drift."""
    conn = get_db()
    try:
        drift_rows = conn.execute(
            """
            SELECT schema_name, schema_version, drift_fields, confidence, success, observed_at
            FROM schema_drift_events
            ORDER BY observed_at DESC LIMIT 20
            """
        ).fetchall()
        recent_drift = [
            {
                "schema_name": r["schema_name"],
                "schema_version": r["schema_version"],
                "drift_fields": json.loads(r["drift_fields"]) if r["drift_fields"] else [],
                "confidence": r["confidence"],
                "success": bool(r["success"]),
                "observed_at": r["observed_at"]
            }
            for r in drift_rows
        ]
        voyager_captures = conn.execute(
            """
            SELECT COUNT(*) FROM captures
            WHERE extractor LIKE 'voyager_%' AND observed_at > ?
            """,
            ((datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),)
        ).fetchone()[0]
    finally:
        conn.close()

    return {
        "bridge": bridge_status(),
        "extractors": capture_health(),
        "voyager_active": voyager_captures > 0,
        "voyager_24h_captures": voyager_captures,
        "recent_drift": recent_drift,
        "schema_version": "2026.10.1"
    }


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def _identity_row(conn) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM creator_identity WHERE id = 1").fetchone()
    return dict(row) if row else None


def confirmed_vanity() -> str:
    conn = get_db()
    try:
        row = _identity_row(conn)
    finally:
        conn.close()
    if row and row.get("confirmed_at"):
        return row.get("vanity") or ""
    return ""


# Fields the extension sends only from /in/<you>/, never from a details page.
PROFILE_PAGE_FIELDS = ("display_name", "headline", "location", "about", "follower_count", "connection_count")


def _clean_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    """The fields of a profile capture this module keeps, cleaned and bounded."""
    contact = payload.get("contact") if isinstance(payload.get("contact"), dict) else None
    websites = None
    if contact and isinstance(contact.get("websites"), list):
        websites = [w for w in (_text(x, 300) for x in contact["websites"][:10]) if w]

    def entries(key, fields, limit=40):
        raw = payload.get(key)
        if not isinstance(raw, list):
            return None  # absent: the section was not on the page, keep what we have
        cleaned = []
        for item in raw[:limit]:
            if isinstance(item, dict):
                entry = {f: _text(item.get(f), n) for f, n in fields}
                if any(entry.values()):
                    cleaned.append(entry)
        return cleaned

    skills = payload.get("skills")
    if isinstance(skills, list):
        skills = sorted({s for s in (_text(x, 120) for x in skills[:200]) if s})
    else:
        skills = None

    return {
        # A read of the profile page itself, which always carries the top
        # card. Its roles, schools and skills are the first few of each, so
        # they add to the stored lists; only a details page replaces one.
        "lists_partial": any(key in payload for key in PROFILE_PAGE_FIELDS),
        "display_name": _text(payload.get("display_name"), 200),
        "headline": _text(payload.get("headline"), 400),
        "location": _text(payload.get("location"), 200),
        "about": _text(payload.get("about"), 5000),
        "current_company": _text(payload.get("current_company"), 200),
        "follower_count": _count(payload.get("follower_count")),
        "connection_count": _count(payload.get("connection_count")),
        "positions": entries("positions", [("title", 200), ("company", 200), ("date_range", 120),
                                           ("location", 200), ("description", 3000)]),
        "education": entries("education", [("school", 200), ("degree", 300), ("date_range", 120)]),
        "skills": skills,
        "contact": None if contact is None else {
            "email": _text(contact.get("email"), 320),
            "phone": _text(contact.get("phone"), 60),
            "birthday": _text(contact.get("birthday"), 60),
            "websites": websites,
        },
    }


def _write_profile(conn, vanity: str, profile_url: Optional[str], clean: Dict[str, Any]) -> None:
    """Writes a confirmed capture over the stored profile, section by section."""
    now = _now()
    scalar = ("display_name", "headline", "location", "about", "current_company",
              "follower_count", "connection_count")
    # A field the page did not show is left as it was. A profile read with the
    # About section collapsed must not erase the About text read last week.
    updates = {k: clean[k] for k in scalar if clean.get(k) is not None}
    updates["profile_observed_at"] = now
    if profile_url:
        updates["profile_url"] = profile_url
    updates["vanity"] = vanity

    contact = clean.get("contact")
    if contact is not None:
        # Contact info comes from its own panel, so a read of it is a complete
        # read: a field missing from an open panel is genuinely absent.
        updates["email"] = contact.get("email")
        updates["phone"] = contact.get("phone")
        updates["birthday"] = contact.get("birthday")
        updates["websites"] = json.dumps(contact.get("websites") or [])
        updates["contact_observed_at"] = now

    assignments = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE creator_identity SET {assignments} WHERE id = 1", tuple(updates.values()))

    # A details page holds the whole list and replaces it. The profile page
    # shows the first few with "Show all", and replacing from it turned 40
    # skills into 2 and 6 roles into 2 each time the creator opened their own
    # profile, so its entries are merged in: matched ones refreshed, new ones
    # added ahead of the rest, nothing removed.
    partial = bool(clean.get("lists_partial"))
    if clean.get("positions") is not None:
        _write_entries(conn, "creator_positions", ("title", "company"), ("date_range", "location", "description"),
                       clean["positions"], partial, now)
    if clean.get("education") is not None:
        _write_entries(conn, "creator_education", ("school", "degree"), ("date_range",),
                       clean["education"], partial, now)
    if clean.get("skills") is not None:
        if not partial:
            conn.execute("DELETE FROM creator_skills")
        conn.executemany(
            "INSERT OR REPLACE INTO creator_skills (skill, observed_at) VALUES (?,?)",
            [(s, now) for s in clean["skills"]],
        )


def _write_entries(conn, table: str, key: tuple, rest: tuple, entries: List[Dict[str, Any]],
                   partial: bool, now: str) -> None:
    """Writes roles or schools: replacing the list from a full read, merging into it from a partial one."""
    columns = key + rest
    insert = (f"INSERT INTO {table} (ordinal, {', '.join(columns)}, observed_at) "
              f"VALUES (?, {', '.join('?' for _ in columns)}, ?)")
    if not partial:
        conn.execute(f"DELETE FROM {table}")
        for i, entry in enumerate(entries):
            conn.execute(insert, (i, *[entry[c] for c in columns], now))
        return
    match = " AND ".join(f"COALESCE({c}, '') = ?" for c in key)
    first = conn.execute(f"SELECT COALESCE(MIN(ordinal), 0) FROM {table}").fetchone()[0]
    new = [e for e in entries
           if not conn.execute(f"SELECT 1 FROM {table} WHERE {match}", [e[c] or "" for c in key]).fetchone()]
    for entry in entries:
        if entry in new:
            continue
        conn.execute(
            f"UPDATE {table} SET {', '.join(f'{c} = COALESCE(?, {c})' for c in rest)}, observed_at = ? WHERE {match}",
            (*[entry[c] for c in rest], now, *[entry[c] or "" for c in key]),
        )
    for i, entry in enumerate(new):
        conn.execute(insert, (first - len(new) + i, *[entry[c] for c in columns], now))


def observe_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    A profile page the extension believes may be the creator's.

    Before confirmation: held as a candidate for the onboarding screen, and only
    when the page carried at least one recognised sign that it belongs to the
    viewer. After confirmation: applied when the vanity matches, refused when it
    does not.
    """
    if not isinstance(payload, dict):
        raise RefusedCapture("the capture was not an object")
    vanity = normalise_vanity(payload.get("vanity") or payload.get("profile_url"))
    if not vanity:
        raise RefusedCapture("the capture carried no profile identifier")

    evidence = [e for e in (payload.get("self_evidence") or []) if e in KNOWN_SELF_EVIDENCE]
    clean = _clean_profile(payload)
    profile_url = profile_url_for(vanity)

    conn = get_db()
    try:
        with conn:
            row = _identity_row(conn)
            if row is None:
                conn.execute("INSERT INTO creator_identity (id) VALUES (1)")
                row = _identity_row(conn)

            if row.get("confirmed_at"):
                if vanity != row.get("vanity"):
                    return {"status": "ignored",
                            "reason": "this profile is not the confirmed creator's"}
                _write_profile(conn, vanity, profile_url, clean)
                return {"status": "updated", "vanity": vanity}

            if not evidence:
                # A profile with no sign that the viewer owns it is somebody
                # else's. It is not held, even as a candidate, so the screen
                # can never ask "is this you?" about a stranger.
                return {"status": "ignored", "reason": "no sign this profile belongs to the viewer"}

            conn.execute(
                "UPDATE creator_identity SET candidate_vanity = ?, candidate_evidence = ?, "
                "candidate_observed_at = ? WHERE id = 1",
                (vanity, json.dumps({"evidence": evidence, "profile": clean}), _now()),
            )
            return {"status": "candidate", "vanity": vanity, "evidence": evidence}
    finally:
        conn.close()


def _fill_creator_settings(conn, clean: Dict[str, Any]) -> None:
    """
    Fills the Brand Studio name, headline and company, where they are empty.

    What the creator typed wins. The capture only fills blanks, so confirming
    your identity cannot quietly replace a headline you chose to write
    differently in the studio.
    """
    row = conn.execute("SELECT value FROM settings WHERE key = 'creator_profile'").fetchone()
    profile = json.loads(row["value"]) if row and row["value"] else {}
    filled = {}
    for key, source in (("name", "display_name"), ("headline", "headline"), ("company", "current_company")):
        if not (profile.get(key) or "").strip() and clean.get(source):
            profile[key] = filled[key] = clean[source]
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('creator_profile', ?)",
        (json.dumps(profile),),
    )
    # What was filled, kept apart from the profile, which Brand Studio rewrites
    # whole on every save. Forgetting takes back exactly these.
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (FILLED_PROFILE_KEY, json.dumps(filled)),
    )


FILLED_PROFILE_KEY = "identity_filled_profile"


def _unfill_creator_settings(conn) -> None:
    """
    Clears the Brand Studio fields confirming filled, where they still hold
    the value it put there.

    Forgetting the wrong account used to leave its name, headline and company
    in Brand Studio, and the next confirmation fills only blanks, so carousel
    bylines and the watermark went on signing as the forgotten person. A field
    the creator has since changed is theirs and stays.
    """
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (FILLED_PROFILE_KEY,)).fetchone()
    filled = json.loads(row["value"]) if row and row["value"] else {}
    stored = conn.execute("SELECT value FROM settings WHERE key = 'creator_profile'").fetchone()
    if filled and stored and stored["value"]:
        profile = json.loads(stored["value"])
        for key, value in filled.items():
            if profile.get(key) == value:
                profile[key] = ""
        conn.execute("UPDATE settings SET value = ? WHERE key = 'creator_profile'", (json.dumps(profile),))
    conn.execute("DELETE FROM settings WHERE key = ?", (FILLED_PROFILE_KEY,))


def confirm_identity(vanity: Any) -> Dict[str, Any]:
    """The creator says the candidate is them. The only way identity is set."""
    wanted = normalise_vanity(vanity)
    conn = get_db()
    try:
        with conn:
            row = _identity_row(conn)
            if not row or not row.get("candidate_vanity"):
                raise RefusedCapture("there is no captured profile to confirm yet")
            if wanted != row["candidate_vanity"]:
                raise RefusedCapture("that is not the profile the studio captured")
            held = json.loads(row.get("candidate_evidence") or "{}")
            clean = held.get("profile") or {}
            conn.execute(
                "UPDATE creator_identity SET vanity = ?, confirmed_at = ?, candidate_vanity = NULL, "
                "candidate_evidence = NULL, candidate_observed_at = NULL WHERE id = 1",
                (wanted, _now()),
            )
            _write_profile(conn, wanted, profile_url_for(wanted), clean)
            _fill_creator_settings(conn, clean)
    finally:
        conn.close()
    return {"status": "confirmed", "vanity": wanted}


def reject_candidate() -> Dict[str, Any]:
    """The creator says the candidate is not them."""
    conn = get_db()
    try:
        with conn:
            conn.execute(
                "UPDATE creator_identity SET candidate_vanity = NULL, candidate_evidence = NULL, "
                "candidate_observed_at = NULL WHERE id = 1"
            )
    finally:
        conn.close()
    return {"status": "rejected"}


def forget_identity() -> Dict[str, Any]:
    """
    Removes everything this module holds about the creator.

    Their own data, so they can delete it, and the next profile capture starts
    onboarding again from the question.
    """
    conn = get_db()
    try:
        with conn:
            for table in ("creator_identity", "creator_positions", "creator_education",
                          "creator_skills", "own_posts", "outbound_engagements", "self_import_requests",
                          "post_metric_observations"):
                conn.execute(f"DELETE FROM {table}")
            # And what LinkedIn's archive brought: connections and the record of each import.
            forget_archive(conn)
            _unfill_creator_settings(conn)
            # The import requests it waited on are gone, and their ids can be
            # issued again, so a chain left behind could take a new one for its own.
            _save_chain(conn, None)
    finally:
        conn.close()
    return {"status": "forgotten"}


# ---------------------------------------------------------------------------
# The creator's posts and activity
# ---------------------------------------------------------------------------

def _require_me(conn, claimed: Any) -> str:
    row = _identity_row(conn)
    if not row or not row.get("confirmed_at"):
        raise RefusedCapture("the creator has not confirmed who they are yet")
    if normalise_vanity(claimed) != row["vanity"]:
        raise RefusedCapture("these items do not belong to the confirmed creator")
    return row["vanity"]


def ingest_own_posts(author: Any, posts: Any) -> Dict[str, Any]:
    """
    Posts from the creator's own activity pages.

    Each item names its actor, and an item whose actor is not the creator is
    skipped. Activity pages include reposts, and a repost is somebody else's
    writing.
    """
    if not isinstance(posts, list):
        raise RefusedCapture("posts must be a list")
    now = _now()
    written = skipped = 0
    bound = {"post": 0, "draft": 0}
    conn = get_db()
    try:
        with conn:
            me = _require_me(conn, author)
            for item in posts[:200]:
                if not isinstance(item, dict):
                    skipped += 1
                    continue
                urn = _text(item.get("activity_urn"), 80) or ""
                actor = normalise_vanity(item.get("actor"))
                if not _ACTIVITY_URN.match(urn) or (actor != me and actor != "me"):
                    skipped += 1
                    continue
                counts = {k: _count(item.get(k)) for k in ("reactions", "comments", "reposts", "impressions")}
                # LinkedIn's archive names a post by its share or ugcPost id;
                # the page names it by its activity id. If the archive brought
                # this post in already, that row becomes this one, so the post
                # is one row with the archive's date and full text and the
                # page's figures, not two.
                if not conn.execute("SELECT 1 FROM own_posts WHERE activity_urn = ?", (urn,)).fetchone():
                    twin = find_archive_twin(conn, urn, _text(item.get("text"), 10000) or "", archive_only=True)
                    if twin:
                        conn.execute("UPDATE own_posts SET activity_urn = ? WHERE activity_urn = ?", (urn, twin))
                conn.execute(
                    """
                    INSERT INTO own_posts (activity_urn, text, published_at, published_at_source,
                                           reactions, comments, reposts, impressions, first_seen_at, last_seen_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(activity_urn) DO UPDATE SET
                        text = CASE
                            WHEN own_posts.published_at_source = 'archive' AND own_posts.text IS NOT NULL
                                 AND (excluded.text IS NULL OR length(own_posts.text) >= length(excluded.text))
                            THEN own_posts.text
                            ELSE COALESCE(excluded.text, own_posts.text) END,
                        reactions = COALESCE(excluded.reactions, own_posts.reactions),
                        comments = COALESCE(excluded.comments, own_posts.comments),
                        reposts = COALESCE(excluded.reposts, own_posts.reposts),
                        impressions = COALESCE(excluded.impressions, own_posts.impressions),
                        last_seen_at = excluded.last_seen_at
                    """,
                    (urn, _text(item.get("text"), 10000), published_at_from_urn(urn),
                     "urn_decode" if published_at_from_urn(urn) else None,
                     counts["reactions"], counts["comments"], counts["reposts"], counts["impressions"],
                     now, now),
                )
                written += 1
                # The counts shown on the activity page are a reading too.
                _record_observation(conn, urn, "activity_page", counts)
                how = _bind_to_studio(conn, urn, _text(item.get("text"), 10000), published_at_from_urn(urn))
                if how:
                    bound[how] += 1
    finally:
        conn.close()
    changes.publish("posts")
    return {"status": "success", "written": written, "skipped": skipped,
            "bound_to_posts": bound["post"], "bound_to_drafts": bound["draft"]}


METRIC_FIELDS = ("impressions", "members_reached", "reactions", "comments", "reposts", "saves", "sends")


def _record_observation(conn, activity_urn: str, source: str, metrics: Dict[str, Any]) -> bool:
    """
    Keeps one reading of a post's figures, with the post's age at that moment.

    One per post per source per hour: re-reading a page within the hour
    refreshes that hour's reading rather than adding another, so scrolling
    the activity page twice does not double the history.
    """
    values = {k: _count(metrics.get(k)) for k in METRIC_FIELDS}
    if all(v is None for v in values.values()):
        return False
    now = datetime.now(timezone.utc)
    published = published_at_from_urn(activity_urn)
    age = round((now - datetime.fromisoformat(published)).total_seconds() / 3600.0, 2) if published else None
    conn.execute(
        f"""
        INSERT INTO post_metric_observations
            (activity_urn, observed_at, observed_hour, age_hours, source, {", ".join(METRIC_FIELDS)})
        VALUES (?, ?, ?, ?, ?, {", ".join("?" for _ in METRIC_FIELDS)})
        ON CONFLICT(activity_urn, source, observed_hour) DO UPDATE SET
            observed_at = excluded.observed_at, age_hours = excluded.age_hours,
            {", ".join(f"{k} = COALESCE(excluded.{k}, post_metric_observations.{k})" for k in METRIC_FIELDS)}
        """,
        (activity_urn, now.isoformat(), now.strftime("%Y-%m-%dT%H"), age, source,
         *[values[k] for k in METRIC_FIELDS]),
    )
    # The post's summary row keeps its two day and latest readings; the
    # trigger marked them, and they are recomputed here, in this transaction.
    post_summary.refresh(conn, [activity_urn])
    return True


def ingest_post_analytics(author: Any, activity_urn: Any, metrics: Any) -> Dict[str, Any]:
    """
    Figures from one of the creator's posts' own analytics page.

    That page shows more than the activity feed does (members reached, saves,
    sends), and only to the post's author, so the extension sends it only from
    the creator's own post. It is refused unless the URN is one of the
    creator's recorded posts: a post analytics page for anyone else's post is
    not something the creator can open, and a URN the studio has never seen as
    theirs is not evidence that it is.
    """
    if not isinstance(metrics, dict):
        raise RefusedCapture("metrics must be an object")
    urn = _text(activity_urn, 80) or ""
    if not _ACTIVITY_URN.match(urn):
        raise RefusedCapture("not an activity URN")
    conn = get_db()
    try:
        with conn:
            _require_me(conn, author)
            if not conn.execute("SELECT 1 FROM own_posts WHERE activity_urn = ?", (urn,)).fetchone():
                raise RefusedCapture("this post is not one of your recorded posts; import your posts first")
            recorded = _record_observation(conn, urn, "post_analytics", metrics)
            impressions = _count(metrics.get("impressions"))
            if impressions is not None:
                conn.execute("UPDATE own_posts SET impressions = ?, last_seen_at = ? WHERE activity_urn = ?",
                             (impressions, _now(), urn))
    finally:
        conn.close()
    changes.publish("readings", post=urn)
    return {"status": "success", "recorded": recorded}


def post_readings(activity_urn: str) -> List[Dict[str, Any]]:
    """Every reading of one post, oldest first."""
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(
            f"SELECT observed_at, age_hours, source, {', '.join(METRIC_FIELDS)} "
            "FROM post_metric_observations WHERE activity_urn = ? ORDER BY observed_at", (activity_urn,))]
    finally:
        conn.close()


def _bind_to_studio(conn, activity_urn: str, text: Optional[str], published_at: Optional[str]) -> Optional[str]:
    """
    Connects one of the creator's LinkedIn posts to the studio record it came
    from. Returns how it bound ("post", "draft"), or None.

    An imported own post is already proven to be the creator's, by its actor,
    so any writing of theirs may be its source. Which record it is is decided
    by post_identity.bind_activity_urn, the one binder: this used to be a
    second implementation of that rule, with a different candidate set and a
    different tie break from the permalink route's, so a post could bind one
    way and not the other.
    """
    try:
        from . import post_identity
    except ImportError:
        import post_identity

    result = post_identity.bind_activity_urn(
        conn, activity_urn, text, published_at=published_at, from_history=True)
    return result.get("how") if result.get("bound") else None


def ingest_outbound(actor: Any, items: Any) -> Dict[str, Any]:
    """
    The creator's reactions and comments on other people's posts.

    Stored here and never as leads. The creator liking a post is a fact about
    the creator's attention, not about the post author wanting to talk to them.
    """
    if not isinstance(items, list):
        raise RefusedCapture("items must be a list")
    now = _now()
    written = skipped = 0
    conn = get_db()
    try:
        with conn:
            _require_me(conn, actor)
            for item in items[:300]:
                if not isinstance(item, dict):
                    skipped += 1
                    continue
                urn = _text(item.get("target_activity_urn"), 80) or ""
                kind = item.get("kind")
                if not _ACTIVITY_URN.match(urn) or kind not in ("reaction", "comment"):
                    skipped += 1
                    continue
                my_text = _text(item.get("my_text"), 5000) if kind == "comment" else None
                if kind == "comment" and not my_text:
                    skipped += 1
                    continue
                key = hashlib.sha256(" ".join(my_text.split()).lower().encode()).hexdigest()[:24] if my_text else ""
                conn.execute(
                    """
                    INSERT INTO outbound_engagements (target_activity_urn, target_author, target_excerpt, kind,
                                                      reaction_kind, my_text, my_text_key, first_seen_at, last_seen_at)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(target_activity_urn, kind, my_text_key) DO UPDATE SET
                        target_author = COALESCE(excluded.target_author, outbound_engagements.target_author),
                        target_excerpt = COALESCE(excluded.target_excerpt, outbound_engagements.target_excerpt),
                        reaction_kind = COALESCE(excluded.reaction_kind, outbound_engagements.reaction_kind),
                        last_seen_at = excluded.last_seen_at
                    """,
                    (urn, _text(item.get("target_author"), 200), _text(item.get("target_excerpt"), 400), kind,
                     _text(item.get("reaction_kind"), 40) if kind == "reaction" else None,
                     my_text, key, now, now),
                )
                written += 1
    finally:
        conn.close()
    changes.publish("outbound")
    return {"status": "success", "written": written, "skipped": skipped}


# ---------------------------------------------------------------------------
# Who counts as a lead
# ---------------------------------------------------------------------------

def _activity_id(urn: Any) -> str:
    """The numeric id of an activity, share or ugcPost URN, or ""."""
    match = re.search(r"urn:li:(?:activity|share|ugcPost):(\d+)", urn or "")
    return match.group(1) if match else ""


def engagement_gate(engager_profile: Any, post_urn: Any, post_author: Any) -> Optional[str]:
    """
    Whether a captured engager may be stored as a lead. None means yes; a
    string is the reason not.

    A lead is someone who engaged with the creator's post. The capture used to
    accept anyone engaging with anything on the feed, which filled the CRM with
    other creators' audiences and listed the creator as their own lead. Drafts
    then told those strangers "thanks for commenting on my post".

    The post is the creator's when its author is the confirmed vanity, or when
    its URN is one the studio has already recorded as theirs. Before the
    creator is confirmed neither can be known, so nothing is accepted, and the
    reason says where to fix that.
    """
    me = confirmed_vanity()
    if not me:
        return ingest_contract.GATE_SETUP_FIRST
    if normalise_vanity(engager_profile) == me:
        return ingest_contract.GATE_THAT_IS_YOU
    if normalise_vanity(post_author) == me:
        return None
    wanted = _activity_id(post_urn)
    conn = get_db()
    try:
        if wanted:
            # One indexed lookup of the post's own key. This read every row of
            # own_posts into Python and ran a regex on each, 0.63 ms per
            # capture on three years of posts against 0.011 ms, before any
            # write, and it grew with the creator's history. The three
            # spellings are the three LinkedIn names a post goes by, and both
            # writers store the key as "urn:li:<kind>:<digits>".
            if conn.execute(
                    "SELECT 1 FROM own_posts WHERE activity_urn IN "
                    "('urn:li:activity:' || ?, 'urn:li:share:' || ?, 'urn:li:ugcPost:' || ?) LIMIT 1",
                    (wanted, wanted, wanted)).fetchone():
                return None
        # A post whose author could be read and is somebody else is somebody
        # else's, whatever has been imported. Only when the author could not
        # be read does the answer depend on the creator's own history, and a
        # creator who has imported nothing then has something to do about it:
        # "not on one of your posts" was both wrong and unactionable there.
        if not normalise_vanity(post_author) and not conn.execute(
                "SELECT 1 FROM own_posts LIMIT 1").fetchone():
            return ingest_contract.GATE_IMPORT_FIRST
    finally:
        conn.close()
    return ingest_contract.GATE_NOT_YOUR_POST


# ---------------------------------------------------------------------------
# Whether an engagement was on one of the creator's posts
# ---------------------------------------------------------------------------
#
# The engagement gate decides this for new captures. Leads captured before it
# existed were taken from any post on the feed, so some are the creator's
# audience and some are other creators'. The same question sorts them, with one
# condition: "not on your post" can only be said once the creator's post
# history has been read to the end. Before that, a post missing from own_posts
# may simply be older than what was imported, so the answer is "unknown", and
# nothing is ever offered for removal on an unknown.

# A post known only from LinkedIn's archive is named by its share or ugcPost id,
# and engagement on it is captured under its activity id, so comparing the bare
# numbers never matched it: the people who commented on an archive post were
# called strangers and offered for deletion. Both ids carry the moment the post
# was made in their high bits, and for one post those moments are a heartbeat
# apart. Two minutes, as archive_import.find_twin allows two ids without text.
SAME_POST_WINDOW_MS = 2 * 60 * 1000


class _OwnPostIds(set):
    """
    The numeric ids of the creator's posts. Membership also holds for an
    activity id made within SAME_POST_WINDOW_MS of a post the studio knows only
    from the archive, which is the same post under its other name.
    """

    def __init__(self, ids, archive_moments):
        super().__init__(ids)
        self.archive_moments = sorted(archive_moments)

    def __contains__(self, post_id) -> bool:
        if set.__contains__(self, post_id):
            return True
        if not self.archive_moments or not str(post_id or "").isdigit():
            return False
        moment = int(post_id) >> 22
        i = bisect.bisect_left(self.archive_moments, moment - SAME_POST_WINDOW_MS)
        return i < len(self.archive_moments) and self.archive_moments[i] <= moment + SAME_POST_WINDOW_MS


def _own_activity_ids(conn) -> set:
    rows = [r["activity_urn"] for r in conn.execute("SELECT activity_urn FROM own_posts")]
    ids = {_activity_id(urn) for urn in rows}
    ids |= {_activity_id(r["activity_urn"]) for r in conn.execute(
        "SELECT activity_urn FROM posts WHERE activity_urn IS NOT NULL")}
    ids.discard("")
    # Rows still under an archive id: the bridge has not read these posts, so
    # nothing has given them their activity id yet.
    archive_moments = [int(_activity_id(urn)) >> 22 for urn in rows
                       if _activity_id(urn) and not (urn or "").startswith("urn:li:activity:")]
    return _OwnPostIds(ids, archive_moments)


# How a posts import ended, as the extension reports it. Only the first is the
# end of the list; the others read part of it.
IMPORT_OUTCOMES = ("end_of_list", "stalled", "round_limit", "stopped", "left_page")

# Not an ending: what an open import holds while the extension waits for its
# hidden LinkedIn tab to come to the front. Cleared when it resumes.
IMPORT_PAUSED_HIDDEN = "paused_hidden"


def _import_outcome(outcome: Any, items_seen: Optional[int]) -> str:
    """
    The outcome to record for a finished import.

    An older extension said "completed" whenever the list stopped growing for
    twenty seconds, which a slow "Show more", a button in another language or
    the round cap all produce, and said it even after reading nothing. Whether
    such an import reached the end is not known, so it is recorded as
    "old_extension": not the whole history, and not claimed to have missed
    the end either. A browser keeps running the old extension until it is
    reloaded, so importing again only repeats this; Setup and Today say to
    reload it. A list that ended with nothing read is "nothing_read".
    """
    said = (_text(outcome, 40) or "").lower()
    if said == "end_of_list":
        return "end_of_list" if items_seen else "nothing_read"
    return said if said in IMPORT_OUTCOMES else "old_extension"


# Outcomes from an extension that did not say how an import ended: what an older
# extension sent, and what earlier studios stored for it.
OLD_EXTENSION_OUTCOMES = ("old_extension", "completed", "partial")


def extension_outdated(conn) -> bool:
    """
    True when the latest finished posts import came from an older extension,
    which cannot say whether it reached the end of the list. The fix is to
    reload the extension, not to import again.
    """
    row = conn.execute(
        "SELECT outcome FROM self_import_requests WHERE kind = 'posts' AND finished_at IS NOT NULL "
        "AND outcome NOT IN ('superseded', 'expired', 'not_opened') ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return bool(row) and row["outcome"] in OLD_EXTENSION_OUTCOMES


def post_history_complete(conn) -> bool:
    """
    True once an import of the creator's posts has read something and run to
    the end of the list. Only then can a lead be called "not on your posts",
    and offered for deletion on that strength.
    """
    return conn.execute(
        "SELECT 1 FROM self_import_requests WHERE kind = 'posts' AND outcome = 'end_of_list' "
        "AND COALESCE(items_seen, 0) > 0 LIMIT 1"
    ).fetchone() is not None


def _origin(post_urn, own_ids, complete) -> str:
    wanted = _activity_id(post_urn)
    if wanted and wanted in own_ids:
        return "yours"
    if wanted and complete:
        return "not_yours"
    return "unknown"


def annotate_interactions(interactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Adds, to each interaction, whether it was on the creator's post and the
    opening of that post, so the dossier can say where someone engaged rather
    than leaving the creator to guess which post to mention.
    """
    conn = get_db()
    try:
        own_ids = _own_activity_ids(conn)
        complete = post_history_complete(conn)
        texts = {}
        for row in conn.execute("SELECT activity_urn, text FROM own_posts WHERE text IS NOT NULL"):
            texts[_activity_id(row["activity_urn"])] = row["text"]
        for row in conn.execute("SELECT activity_urn, content FROM posts WHERE activity_urn IS NOT NULL"):
            texts.setdefault(_activity_id(row["activity_urn"]), row["content"])
    finally:
        conn.close()

    for item in interactions:
        item["post_origin"] = _origin(item.get("post_urn"), own_ids, complete)
        text = texts.get(_activity_id(item.get("post_urn")))
        item["post_excerpt"] = clip(" ".join(text.split()), 140) if text else None
    return interactions


def lead_review() -> Dict[str, Any]:
    """
    Every lead sorted by whether their engagement was on the creator's posts.

    A lead is "yours" if any interaction was on your post, "not_yours" only if
    every interaction names a post and none of them is yours (and your history
    is complete), and "unknown" otherwise, including leads added by hand, which
    have no captured interaction at all.
    """
    # Whose a post is depends on the post alone, so each post is classified
    # once, from the per-post summary and its lead ids, and only the leads
    # that could be "not_yours" have their interactions read. Reading and
    # classifying all 500,000 interactions took 0.6 s on three years of data.
    conn = get_db()
    try:
        own_ids = _own_activity_ids(conn)
        complete = post_history_complete(conn)
        total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        yours, elsewhere = set(), set()
        for urn, row in post_summary.current(conn).items():
            if not row["people"]:
                continue
            origin = _origin(urn, own_ids, complete)
            if origin == "yours":
                yours.update(post_summary.lead_ids_of(row))
            elif origin == "not_yours":
                elsewhere.update(post_summary.lead_ids_of(row))
        # Reactions older than 24 months that retention folded are no longer
        # rows but are still engagements, each with whose post it was on when
        # it was folded (retention.folded_counts).
        try:
            from . import retention
        except ImportError:
            import retention
        folded = retention.folded_counts(conn)["by_lead"]
        for key, fold in folded.items():
            if int(fold.get("yours") or 0):
                yours.add(key)
            elif int(fold.get("not_yours") or 0):
                elsewhere.add(key)
        candidates = elsewhere - yours
        seen: Dict[str, List[str]] = {lead_id: [] for lead_id in candidates}
        if candidates:
            for row in conn.execute("SELECT CAST(lead_id AS TEXT) AS lead_id, post_urn FROM lead_interactions "
                                    "WHERE lead_id IN (SELECT value FROM json_each(?))",
                                    (json.dumps(sorted(candidates)),)):
                if row["lead_id"] in seen:
                    seen[row["lead_id"]].append(_origin(row["post_urn"], own_ids, complete))
            for key in candidates:
                fold = folded.get(key) or {}
                for verdict in ("yours", "not_yours", "unknown"):
                    seen[key].extend([verdict] * int(fold.get(verdict) or 0))
        not_yours = [lead_id for lead_id, origins in seen.items()
                     if origins and all(o == "not_yours" for o in origins)]
        listed = [dict(r) for r in conn.execute(
            "SELECT id, COALESCE(full_name, name) AS name, headline, created_at FROM leads "
            "WHERE id IN (SELECT value FROM json_each(?)) ORDER BY rowid", (json.dumps(not_yours),))]
    finally:
        conn.close()

    for lead in listed:
        lead["interactions"] = len(seen[lead["id"]])
    counts = {"yours": len(yours), "not_yours": len(listed)}
    counts["unknown"] = total - counts["yours"] - counts["not_yours"]
    return {
        "status": "success",
        "history_complete": complete,
        "counts": {k: counts[k] for k in ("yours", "not_yours", "unknown")},
        "not_yours": sorted(listed, key=lambda l: l.get("created_at") or ""),
    }


def remove_leads_not_on_your_posts(lead_ids: Any) -> Dict[str, Any]:
    """
    Deletes the named leads, each only if it is still classified not_yours.

    The creator confirms a list they have seen. Re-checking each id at delete
    time means a lead that became "yours" in between, because a new comment
    arrived on one of the creator's posts, is kept even if it was on that list.
    """
    if not isinstance(lead_ids, list) or not lead_ids:
        raise RefusedCapture("name the leads to remove")
    allowed = {l["id"] for l in lead_review()["not_yours"]}
    chosen = [str(i) for i in lead_ids[:1000] if str(i) in allowed]
    conn = get_db()
    try:
        with conn:
            for lead_id in chosen:
                conn.execute("DELETE FROM lead_interactions WHERE lead_id = ?", (lead_id,))
                conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
            # The per-post summary lists people by name: recompute the posts
            # these deletes marked, so no removed name stays behind in it.
            post_summary.refresh(conn)
    finally:
        conn.close()
    return {"status": "success", "removed": len(chosen), "kept": len(lead_ids) - len(chosen)}


# ---------------------------------------------------------------------------
# History imports: the creator asks, the extension scrolls
# ---------------------------------------------------------------------------

# Import all three, one after another: the chain Sync All starts. It is kept in
# the profile's own database, not in server memory, where a studio restart
# halfway through the posts dropped the comments and reactions without a word,
# and where one chain was shared by every creator profile.
SYNC_CHAIN_KEY = "history_sync_chain"


def _load_chain(conn) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (SYNC_CHAIN_KEY,)).fetchone()
    try:
        chain = json.loads(row["value"]) if row and row["value"] else None
    except ValueError:
        return None
    return chain if isinstance(chain, dict) and chain.get("sequence") else None


def _save_chain(conn, chain: Optional[Dict[str, Any]]) -> None:
    if chain is None:
        conn.execute("DELETE FROM settings WHERE key = ?", (SYNC_CHAIN_KEY,))
    else:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (SYNC_CHAIN_KEY, json.dumps(chain)))


def start_sync_chain(sequence: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Sync All: imports posts, then comments, then reactions, each one asked
    for when the one before it finishes.
    """
    vanity = confirmed_vanity()
    if not vanity:
        raise RefusedCapture("confirm your profile before importing history")

    seq = [k for k in (sequence or ["posts", "comments", "reactions"]) if k in IMPORT_KINDS]
    if not seq:
        seq = ["posts", "comments", "reactions"]

    first_kind = seq[0]
    res = request_import(first_kind, is_chain=True)
    conn = get_db()
    try:
        with conn:
            _save_chain(conn, {"sequence": seq, "current_index": 0, "active": True, "started_at": _now(),
                               "vanity": vanity, "request_id": res["id"]})
    finally:
        conn.close()
    return {
        "status": "started",
        "current_kind": first_kind,
        "open_url": res["open_url"],
        "id": res["id"],
        "sequence": seq,
    }


def cancel_sync_chain(withdraw: bool = False) -> None:
    """
    Ends the chain. With withdraw, also closes the request it was waiting on,
    as "not_opened", for when Sync All could not open a page that would carry
    it out, so Setup does not show it waiting.
    """
    conn = get_db()
    try:
        with conn:
            chain = _load_chain(conn)
            if withdraw and chain:
                conn.execute(
                    "UPDATE self_import_requests SET finished_at = ?, outcome = 'not_opened' "
                    "WHERE id = ? AND finished_at IS NULL", (_now(), chain.get("request_id")),
                )
            _save_chain(conn, None)
    finally:
        conn.close()


def get_active_sync_chain() -> Optional[Dict[str, Any]]:
    """
    The chain under way, or None. A chain whose current request is closed
    (expired, replaced, or finished without a next step) is over.
    """
    conn = get_db()
    try:
        with conn:
            chain = _load_chain(conn)
            if chain is None:
                return None
            row = conn.execute("SELECT finished_at FROM self_import_requests WHERE id = ?",
                               (chain.get("request_id"),)).fetchone()
            if not row or row["finished_at"]:
                _save_chain(conn, None)
                return None
    finally:
        conn.close()
    chain["current_kind"] = chain["sequence"][min(chain.get("current_index", 0), len(chain["sequence"]) - 1)]
    return chain


def request_import(kind: Any, is_chain: bool = False) -> Dict[str, Any]:
    """
    The creator clicked "import my posts" (or comments, or reactions).

    The extension scrolls an activity page only when a request like this is
    pending, so scrolling always traces back to a click in the studio.
    """
    if not is_chain:
        cancel_sync_chain()

    if kind not in IMPORT_KINDS:
        raise RefusedCapture(f"unknown import: {kind}")
    conn = get_db()
    try:
        with conn:
            if not (_identity_row(conn) or {}).get("confirmed_at"):
                raise RefusedCapture("confirm your profile before importing history")
            conn.execute(
                "UPDATE self_import_requests SET finished_at = ?, outcome = 'superseded' "
                "WHERE kind = ? AND finished_at IS NULL", (_now(), kind),
            )
            cur = conn.execute(
                "INSERT INTO self_import_requests (kind, requested_at) VALUES (?, ?)", (kind, _now())
            )
            request_id = cur.lastrowid
    finally:
        conn.close()
    return {"status": "requested", "id": request_id, "kind": kind,
            "open_url": f"{profile_url_for(confirmed_vanity())}recent-activity/{_activity_tab(kind)}/"}


def _activity_tab(kind: str) -> str:
    return {"posts": "all", "comments": "comments", "reactions": "reactions"}[kind]


def _expire_requests(conn) -> None:
    """
    Closes requests the extension will no longer take, as "expired".

    Left open, Setup went on saying WAITING FOR THE PAGE TO OPEN for a request
    nothing would ever pick up. Only requests that never started: an import
    that is scrolling, paused in a hidden tab, still finishes.
    """
    cutoff = (datetime.now(timezone.utc) - IMPORT_REQUEST_TTL).isoformat()
    conn.execute(
        "UPDATE self_import_requests SET finished_at = ?, outcome = 'expired' "
        "WHERE finished_at IS NULL AND started_at IS NULL AND requested_at < ?", (_now(), cutoff),
    )


def pending_import(kind: Any) -> Optional[Dict[str, Any]]:
    """The live request for this kind, if the creator made one recently."""
    if kind not in IMPORT_KINDS:
        return None
    cutoff = (datetime.now(timezone.utc) - IMPORT_REQUEST_TTL).isoformat()
    conn = get_db()
    try:
        with conn:
            _expire_requests(conn)
        row = conn.execute(
            "SELECT id, kind, requested_at, started_at FROM self_import_requests "
            "WHERE kind = ? AND finished_at IS NULL AND requested_at >= ? ORDER BY id DESC LIMIT 1",
            (kind, cutoff),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def update_import(request_id: Any, event: Any, items_seen: Any = None, outcome: Any = None) -> Dict[str, Any]:
    try:
        request_id = int(request_id)
    except (TypeError, ValueError):
        raise RefusedCapture("unknown import request")
    if event not in ("started", "paused", "resumed", "finished"):
        raise RefusedCapture("event must be started, paused, resumed or finished")
    conn = get_db()
    chain = None
    try:
        with conn:
            chain = _load_chain(conn)
            if event == "started":
                conn.execute(
                    "UPDATE self_import_requests SET started_at = COALESCE(started_at, ?) "
                    "WHERE id = ? AND finished_at IS NULL", (_now(), request_id),
                )
            elif event in ("paused", "resumed"):
                # The extension stops scrolling while its LinkedIn tab is
                # hidden. Held in outcome while the import is open, which
                # nothing else reads before it finishes, so Setup can say it
                # is paused and why rather than SCROLLING NOW.
                conn.execute(
                    "UPDATE self_import_requests SET outcome = ?, items_seen = COALESCE(?, items_seen) "
                    "WHERE id = ? AND finished_at IS NULL",
                    (IMPORT_PAUSED_HIDDEN if event == "paused" else None, _count(items_seen), request_id),
                )
            else:
                conn.execute(
                    "UPDATE self_import_requests SET finished_at = ?, items_seen = ?, outcome = ? "
                    "WHERE id = ? AND finished_at IS NULL",
                    (_now(), _count(items_seen), _import_outcome(outcome, _count(items_seen)), request_id),
                )
    finally:
        conn.close()

    res: Dict[str, Any] = {"status": "success"}
    # The chain moves on only when the request it is waiting for finishes.
    if event == "finished" and chain and chain.get("request_id") == request_id:
        norm_outcome = (outcome or "").strip().lower()
        seq = chain["sequence"]
        next_idx = chain.get("current_index", 0) + 1
        if norm_outcome in ("stopped", "left_page"):
            cancel_sync_chain()
        elif next_idx < len(seq):
            next_kind = seq[next_idx]
            next_req = request_import(next_kind, is_chain=True)
            chain.update(current_index=next_idx, request_id=next_req["id"])
            conn = get_db()
            try:
                with conn:
                    _save_chain(conn, chain)
            finally:
                conn.close()
            res["next_kind"] = next_kind
            res["next_url"] = next_req["open_url"]
            res["next_id"] = next_req["id"]
            res["is_chain"] = True
        else:
            cancel_sync_chain()
            res["all_completed"] = True
            res["is_chain"] = True

    changes.publish("imports")
    return res


# ---------------------------------------------------------------------------
# What the onboarding screen reads
# ---------------------------------------------------------------------------

def onboarding_state() -> Dict[str, Any]:
    conn = get_db()
    try:
        row = _identity_row(conn) or {}
        positions = [dict(r) for r in conn.execute(
            "SELECT title, company, date_range, location FROM creator_positions ORDER BY ordinal")]
        education = [dict(r) for r in conn.execute(
            "SELECT school, degree, date_range FROM creator_education ORDER BY ordinal")]
        skills = [r["skill"] for r in conn.execute("SELECT skill FROM creator_skills ORDER BY skill")]
        post_count = conn.execute("SELECT COUNT(*) FROM own_posts").fetchone()[0]
        outbound = {r["kind"]: r["n"] for r in conn.execute(
            "SELECT kind, COUNT(*) AS n FROM outbound_engagements GROUP BY kind")}
        # What deleting everything would also remove, so Setup can say so first.
        readings = conn.execute("SELECT COUNT(*) FROM post_metric_observations").fetchone()[0]
        connections = conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
        history_read = post_history_complete(conn)
        outdated = extension_outdated(conn)
        with conn:
            _expire_requests(conn)
        imports = [dict(r) for r in conn.execute(
            "SELECT id, kind, requested_at, started_at, finished_at, items_seen, outcome "
            "FROM self_import_requests ORDER BY id DESC LIMIT 6")]
    finally:
        conn.close()

    confirmed = bool(row.get("confirmed_at"))
    candidate = None
    if not confirmed and row.get("candidate_vanity"):
        held = json.loads(row.get("candidate_evidence") or "{}")
        profile = held.get("profile") or {}
        candidate = {
            "vanity": row["candidate_vanity"],
            "display_name": profile.get("display_name"),
            "headline": profile.get("headline"),
            "location": profile.get("location"),
            "evidence": [KNOWN_SELF_EVIDENCE[e] for e in held.get("evidence", []) if e in KNOWN_SELF_EVIDENCE],
            "observed_at": row.get("candidate_observed_at"),
        }

    identity = None
    if confirmed:
        identity = {k: row.get(k) for k in (
            "vanity", "profile_url", "display_name", "headline", "location", "about", "current_company",
            "follower_count", "connection_count", "email", "phone", "birthday",
            "profile_observed_at", "contact_observed_at", "confirmed_at")}
        identity["websites"] = json.loads(row.get("websites") or "[]")
        identity["positions"] = positions
        identity["education"] = education
        identity["skills"] = skills

    # Whether a LinkedIn session is held, and since when. Read here rather than
    # through linkedin_client so this module stays free of anything that could
    # reach the network. Never the value itself.
    conn = get_db()
    try:
        held = {r["key"]: r["value"] for r in conn.execute(
            "SELECT key, value FROM settings WHERE key IN ('li_at', 'last_token_update')")}
    finally:
        conn.close()
    session = {"stored": bool(held.get("li_at")), "saved_at": held.get("last_token_update")}

    bridge = bridge_status()
    try:
        from .archive_import import archive_state
    except ImportError:
        from archive_import import archive_state
    archive = archive_state(look=False)
    chain = get_active_sync_chain()
    return {
        "archive": archive,
        "health": [h for h in capture_health()
                   if h["extractor"] not in OPT_IN_EXTRACTORS or h["state"] != "never_run"],
        "session": session,
        "status": "success",
        "bridge": bridge,
        "candidate": candidate,
        "identity": identity,
        "counts": {
            "posts": post_count,
            "comments": outbound.get("comment", 0),
            "reactions": outbound.get("reaction", 0),
            "readings": readings,
            "connections": connections,
        },
        "imports": imports,
        # Import all three, while one is under way: which, and what comes next.
        "sync_chain": {"sequence": chain["sequence"], "current_kind": chain["current_kind"]} if chain else None,
        # The latest posts import came from an older extension: reload it.
        "extension_outdated": outdated,
        "steps": {
            "bridge": bool(bridge["last_seen_at"]),
            "identity": confirmed,
            # Step 5 is done when Today can use it: your posts read to the end
            # of the list. Rows from the archive alone are not that.
            "history": confirmed and history_read,
            "posts": post_count > 0,
            "activity": sum(outbound.values()) > 0,
            # Done when the posts are in, not at LinkedIn's first, basic part.
            "archive": archive["complete"],
        },
    }
