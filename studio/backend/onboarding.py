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
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote

try:
    from .text_cut import clip
except ImportError:
    from text_cut import clip

# Track 5: the one sightings sentence (results.py) and the phase 2 readers'
# storage of the creator's own reposts and edited posts (own_insights.py).
try:
    from . import own_insights, results
except ImportError:
    import own_insights
    import results

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


def _post_identity():
    try:
        from . import post_identity
    except ImportError:
        import post_identity
    return post_identity


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


def forget_phone_and_export(conn) -> None:
    """
    The phone's desk requests, what the Telegram bot has told (which names
    the creator's posts, 2.11.0), what its buttons do and the reminders asked
    for with them (which name the creator's drafts and posts), and the
    analytics export's record of its imports (cycle 4, track 6).
    """
    try:
        from . import analytics_export, desk_requests, telegram_bot
    except ImportError:
        import analytics_export
        import desk_requests
        import telegram_bot
    desk_requests.forget(conn)
    conn.execute("DELETE FROM settings WHERE key IN (?, ?, ?)",
                 (telegram_bot.TOLD_KEY, telegram_bot.BUTTONS_KEY, telegram_bot.REMIND_KEY))
    analytics_export.forget(conn)


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

# Network reading, retired in 2.10.2
# -----------------------------------
# The extension read LinkedIn's /voyager/api/ responses while the creator had
# network reading switched on: an interceptor that wrapped the page's fetch,
# a schema registry it matched responses against, and an observer of the
# page's data requests. LinkedIn's 2026 web app makes no such calls (a
# Resource Timing list from the owner's own feed tab, 28 October 2026): its
# data arrives through React Server Component actions in an internal
# streaming format, which nothing here can read or re-key. So the reader is
# gone from the extension, and the studio writes nothing for it any more:
# not the readings, not the drift events, not the heartbeat's state. The
# tables keep what they hold, forward only. An extension not yet reloaded
# still calls the two routes; each answers this, plainly, so it does not
# retry in a loop.
NETWORK_READING_RETIRED = "Network reading was retired in 2.10.2: LinkedIn's site no longer sends the data it read."


def network_reading_retired_answer() -> Dict[str, Any]:
    """What a retired network reading call is answered: stored nothing, and why."""
    return {"status": "retired", "outcome": "nothing_new", "reason": "network_reading_retired",
            "message": NETWORK_READING_RETIRED}


def network_reading_retired(conn=None) -> Optional[str]:
    """
    The sentence, where it is useful: only in a studio network reading once
    ran in, or was switched on for, so a creator who never turned it on is
    not told about a switch they never saw.
    """
    own = conn is None
    conn = conn or get_db()
    try:
        ran = (conn.execute("SELECT 1 FROM captures WHERE extractor LIKE 'voyager_%' LIMIT 1").fetchone()
               or conn.execute("SELECT 1 FROM capture_days WHERE extractor LIKE 'voyager_%' LIMIT 1").fetchone()
               or conn.execute("SELECT 1 FROM schema_drift_events LIMIT 1").fetchone()
               or conn.execute("SELECT 1 FROM post_metric_observations WHERE source = 'voyager_network' "
                               "LIMIT 1").fetchone()
               or conn.execute("SELECT 1 FROM bridge_heartbeats WHERE network_reading LIKE '%\"switch\": true%' "
                               "LIMIT 1").fetchone())
    except sqlite3.Error:
        ran = None
    finally:
        if own:
            conn.close()
    return NETWORK_READING_RETIRED if ran else None


# ---------------------------------------------------------------------------
# One bridge per browser (cycle 4, track 1, phase 2)
# ---------------------------------------------------------------------------
#
# The worker stamps every capture it relays with where it came from: an id it
# mints once per browser install, the browser's name, the tab, window and
# document, and the LinkedIn account the browser is signed in to, which is
# the creator's own. The studio groups heartbeats and capture rows by the
# browser id and the minute, routes a capture to the creator profile of that
# account, and hands a history import to one tab.
_INSTANCE_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_DOCUMENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def clean_stamp(raw: Any) -> Dict[str, Any]:
    """
    The stamp the worker put on a relayed body, kept only where its shape is
    right, or {} when there is none. Ids are opaque: a browser instance id is
    random, and tab, window and document ids are the browser's own numbers.
    """
    if not isinstance(raw, dict):
        return {}
    stamp: Dict[str, Any] = {}
    instance = raw.get("browser_instance_id")
    if isinstance(instance, str) and _INSTANCE_ID.match(instance):
        stamp["browser_instance_id"] = instance
    browser = _text(raw.get("browser"), 40)
    if browser:
        stamp["browser"] = browser
    for field in ("tab_id", "window_id", "frame_id"):
        value = raw.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            stamp[field] = value
    document = raw.get("document_id")
    if isinstance(document, str) and _DOCUMENT_ID.match(document):
        stamp["document_id"] = document
    if isinstance(raw.get("tab_active"), bool):
        stamp["tab_active"] = raw["tab_active"]
    vanity = normalise_vanity(raw.get("signed_in_vanity"))
    if vanity:
        stamp["signed_in_vanity"] = vanity
    return stamp


def claimant_of(stamp: Dict[str, Any]) -> Optional[str]:
    """Who is asking for a history import: one tab of one browser, or None for an older extension."""
    if stamp.get("browser_instance_id") and stamp.get("tab_id") is not None:
        return f"{stamp['browser_instance_id']}:{stamp['tab_id']}"
    return None


def _counts_by_name(raw: Any, name_limit: int = 60, limit: int = 40) -> Optional[Dict[str, int]]:
    """{name: count} as the worker sent it (open page kinds, held captures per account), or None."""
    if not isinstance(raw, dict):
        return None
    clean: Dict[str, int] = {}
    for key, value in list(raw.items())[:limit]:
        name = _text(key, name_limit)
        if name and isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            clean[name] = value
    return clean


def _utc_moment(raw: Any) -> Optional[str]:
    """A moment the browser stated (toISOString), as UTC ISO text, or None for anything else."""
    text = _text(raw, 40)
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(timezone.utc).isoformat()


def record_heartbeat(extension_version: Any = None, page_kind: Any = None,
                     browser_instance_id: Any = None, browser: Any = None, signed_in_vanity: Any = None,
                     contract_version: Any = None, open_pages: Any = None, held: Any = None,
                     tabs_needing_reload: Any = None, self_reload: Any = None,
                     files_version: Any = None, files_readable: Any = None,
                     files_checked_at: Any = None) -> Dict[str, Any]:
    """
    One heartbeat. From a worker that names its browser, one row per browser
    per minute, the newest beat replacing the minute's earlier one: ten tabs,
    or a worker beating on every change, still write one row a minute. From
    an extension older than the stamp, one row per beat, as before. An older
    extension's network reading state is not kept: network reading was
    retired in 2.10.2.
    """
    now = datetime.now(timezone.utc)
    stamp = clean_stamp({"browser_instance_id": browser_instance_id, "browser": browser,
                         "signed_in_vanity": signed_in_vanity})
    values = {
        "seen_at": now.isoformat(),
        "extension_version": _text(extension_version, 40),
        "page_kind": _text(page_kind, 40),
        "browser_instance_id": stamp.get("browser_instance_id"),
        "minute": now.isoformat()[:16] if stamp.get("browser_instance_id") else None,
        "browser": stamp.get("browser"),
        "signed_in_vanity": stamp.get("signed_in_vanity"),
        "contract_version": contract_version if isinstance(contract_version, int)
        and not isinstance(contract_version, bool) else None,
        "open_pages": json.dumps(_counts_by_name(open_pages, 40)) if _counts_by_name(open_pages, 40) is not None else None,
        "held": json.dumps(_counts_by_name(held, 100)) if _counts_by_name(held, 100) is not None else None,
        "tabs_needing_reload": _count(tabs_needing_reload),
        "self_reload": (1 if self_reload else 0) if isinstance(self_reload, bool) else None,
        "files_version": _text(files_version, 40),
        "files_readable": (1 if files_readable else 0) if isinstance(files_readable, bool) else None,
        "files_checked_at": _utc_moment(files_checked_at),
    }
    names = list(values)
    sql = (f"INSERT INTO bridge_heartbeats ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})")
    if values["browser_instance_id"]:
        sql += (" ON CONFLICT(browser_instance_id, minute) DO UPDATE SET "
                + ", ".join(f"{n} = excluded.{n}" for n in names if n not in ("browser_instance_id", "minute")))
    conn = get_db()
    try:
        with conn:
            conn.execute(sql, tuple(values[n] for n in names))
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
                "extension_version": None, "page_kind": None, "bridges": []}

    seen = datetime.fromisoformat(row["seen_at"])
    ago = max(0, int((datetime.now(timezone.utc) - seen).total_seconds()))
    return {
        "connected": ago <= BRIDGE_FRESH_SECONDS,
        "last_seen_at": row["seen_at"],
        "seconds_ago": ago,
        "extension_version": row["extension_version"],
        "page_kind": row["page_kind"],
        "bridges": bridges(),
    }


def bridges() -> List[Dict[str, Any]]:
    """
    Each browser the bridge runs in, newest first, from its own latest
    heartbeat: which browser, which LinkedIn account it is signed in to, when
    it was last heard from, the LinkedIn pages it has open, the captures it
    is holding for an account no profile here holds, the tabs that still
    carry an older copy of its readers, and what it last found in its own
    folder. An extension from before the stamp is one bridge whose browser
    is not known.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT h.* FROM bridge_heartbeats AS h JOIN ("
            "  SELECT COALESCE(browser_instance_id, '') AS instance, MAX(seen_at) AS newest "
            "  FROM bridge_heartbeats GROUP BY COALESCE(browser_instance_id, '')"
            ") AS latest ON COALESCE(h.browser_instance_id, '') = latest.instance AND h.seen_at = latest.newest "
            "ORDER BY h.seen_at DESC").fetchall()
    finally:
        conn.close()
    now = datetime.now(timezone.utc)
    found = []
    for row in rows:
        row = dict(row)
        ago = max(0, int((now - datetime.fromisoformat(row["seen_at"])).total_seconds()))
        found.append({
            "browser_instance_id": row.get("browser_instance_id"),
            "browser": row.get("browser"),
            "signed_in_vanity": row.get("signed_in_vanity"),
            "connected": ago <= BRIDGE_FRESH_SECONDS,
            "last_seen_at": row["seen_at"],
            "seconds_ago": ago,
            "extension_version": row.get("extension_version"),
            "contract_version": row.get("contract_version"),
            "open_pages": json.loads(row["open_pages"]) if row.get("open_pages") else None,
            "held": json.loads(row["held"]) if row.get("held") else None,
            "tabs_needing_reload": row.get("tabs_needing_reload"),
            "self_reload": None if row.get("self_reload") is None else bool(row["self_reload"]),
            "files_version": row.get("files_version"),
            "files_readable": None if row.get("files_readable") is None else bool(row["files_readable"]),
            "files_checked_at": row.get("files_checked_at"),
        })
    return found


# ---------------------------------------------------------------------------
# Capture health
# ---------------------------------------------------------------------------

# The extractors the extension reports on, in the words the Setup screen uses.
EXTRACTORS = {
    "engagers": "Comments and reactions on your posts",
    "card_urns": "Post ids on feed cards",
    "profile": "Your profile",
    "activity_posts": "Your posts",
    "activity_comments": "Your comments",
    "activity_reactions": "Your reactions",
    "analytics": "Creator analytics",
    "post_analytics": "Your posts' analytics pages",
    # The two network readers (voyager_feed_updates, voyager_creator_analytics)
    # were retired in 2.10.2 with network reading; their old runs stay in the
    # capture log and are no longer listed.
}

# What network reading kept, per schema, while it ran: readings of the
# creator's own posts, and their follower count. Kept here because cycle 4's
# migration (_migrate_reader_timing_and_network_reading) runs
# forget_other_members_readings, which removes anything else it once kept,
# and needs the list and clean_voyager_path below to do it.
VOYAGER_KEPT = {
    "feed_updates": "readings of your own posts",
    "creator_analytics": "your follower count",
}

# The words LinkedIn's data API puts in its paths. A path is kept only as
# these words, compared without regard to case and written as listed; every
# other segment, whoever or whatever it names, becomes "_id_", and so does the
# segment after a collection that takes one. An unknown word costs a less
# specific path, never a person. Used now only by the migration's clean-up of
# the drift events network reading wrote.
VOYAGER_PATH_WORDS = (
    "voyager", "api", "graphql", "me", "identity", "dash", "profiles", "miniProfiles", "profileView",
    "profileContactInfo", "publicContactInfo", "networkinfo", "memberBadges", "memberIdentity",
    "profileActions", "feed", "updates", "updatesV2", "social", "socialActions", "socialDetails", "comments",
    "reactions", "likes", "followerInfo", "hashtags", "contentcreation", "normShares", "shares", "posts",
    "activities", "creatorAnalytics", "analytics", "messaging", "conversations", "events", "messages",
    "threads", "notifications", "badges", "relationships", "memberRelationships", "connections",
    "invitations", "invitationViews", "search", "clusters", "blended", "typeahead", "hitsV2", "hits",
    "organization", "organizations", "companies", "entities", "jobs", "jobPostings", "premium", "growth",
    "legoWidgets", "pageContent", "settings", "highlights", "recommendations", "skills", "positions",
    "educations", "featured", "followers", "following", "people", "members", "groups", "schools",
)
VOYAGER_ID_AFTER = (
    "profiles", "miniProfiles", "profileContactInfo", "publicContactInfo", "networkinfo", "memberBadges",
    "profileActions", "updates", "updatesV2", "social", "socialActions", "socialDetails", "comments",
    "reactions", "likes", "followerInfo", "hashtags", "shares", "posts", "activities", "conversations",
    "events", "messages", "threads", "connections", "invitations", "organizations", "companies", "jobs",
    "jobPostings", "people", "members", "groups", "schools",
)
_PATH_WORD = {word.lower(): word for word in VOYAGER_PATH_WORDS}
_ID_AFTER_WORD = {word.lower() for word in VOYAGER_ID_AFTER}
# A GraphQL query name has one shape: "voyager" and a capitalised name.
VOYAGER_QUERY_NAME = re.compile(r"^voyager[A-Z][A-Za-z0-9]{1,78}$")


def clean_voyager_path(path: Any) -> str:
    """A Voyager path as the words of its address, every other segment "_id_"; no query, no host."""
    text = str(path or "")
    text = re.sub(r"^[a-z]+://[^/]*", "", text).split("?", 1)[0].split("#", 1)[0]
    out, previous = [], ""
    for segment in [s for s in text.split("/") if s][:8]:
        word = None if previous in _ID_AFTER_WORD else _PATH_WORD.get(segment.lower())
        if word is None and previous == "api" and VOYAGER_QUERY_NAME.match(segment):
            word = segment
        out.append(word or "_id_")
        # What the segment was taken as, not the text it held: an identifier
        # that happens to spell a collection's name takes no identifier after it.
        previous = (word or "_id_").lower()
    return "/" + "/".join(out)

# The states a reader's latest run can put it in. One list, so a screen
# cannot meet a state it does not draw.
#   never_run     no row at all
#   working       the latest run read something and named no drift
#   read_nothing  the latest run ran, named no drift, and saw nothing: an
#                 empty page, or a page the reader no longer recognises. It
#                 used to read WORKING, which was the lie the sections report
#                 measured at onboarding.py:359
#   drifting      the latest run named fields it could not read
#   refused       the studio refused the latest run, and says why
CAPTURE_STATES = ("never_run", "working", "read_nothing", "drifting", "refused")

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
# of each extractor, and the latest good run of each, which is the LAST WORKED
# date shown beside a drifting or refused reader. Rows the screen does not
# read still age out at the window above.
#
# A good run read something, missed nothing it expected, and was not refused.
# One rule, asked by capture_health and by the prune, unqualified so that it
# reads the table of whichever query it sits in. Without the refused clause a
# reader refused for identity every day since it last worked lost that day to
# the prune, because its newest refused row looked like the good run to keep.
#
# A run read something if it saw items or kept any: a run that sent people to
# the studio has read them, whatever it counted as seen. The engagers reader
# counted only comments as seen, so a reactions list read on its own was READ
# NOTHING beside the reactors it had just filed.
READ_SOMETHING = "(COALESCE(items_seen, 0) > 0 OR COALESCE(items_kept, 0) > 0)"
GOOD_RUN = f"drift IS NULL AND refused IS NULL AND {READ_SOMETHING}"
PRUNE_CAPTURES = f"""
DELETE FROM captures
 WHERE observed_at < ?
   AND id NOT IN (
         SELECT keep.id FROM captures AS keep
          WHERE keep.observed_at = (SELECT MAX(observed_at) FROM captures
                                     WHERE extractor = keep.extractor)
   )
   AND id NOT IN (
         SELECT keep.id FROM captures AS keep
          WHERE {GOOD_RUN}
            AND keep.observed_at = (SELECT MAX(observed_at) FROM captures
                                     WHERE extractor = keep.extractor
                                       AND {GOOD_RUN})
   )
"""


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
    conn = get_db()
    try:
        with conn:
            # The row's own drift and moment, which the change below names: the
            # write moved into _write_capture (track 1), and the change's line
            # (track 2) still needs both.
            drift, now = _write_capture(conn, payload["extractor"], payload)
    finally:
        conn.close()
    changes.publish("capture", extractor=payload["extractor"], drift=bool(drift), minute=now.isoformat()[:16])
    return {"status": "success"}


def _millis(value: Any) -> Optional[float]:
    """A duration in milliseconds, or None when it is not one. Never negative."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0 or value != value or value > 3_600_000:
        return None
    return round(float(value), 1)


def _write_capture(conn, extractor: str, payload: Dict[str, Any],
                   refused: Optional[str] = None) -> Tuple[List[str], datetime]:
    """
    One row of the capture log, inside the caller's transaction.

    The reader's own timing rides on the row: how long this run took, how
    many reads it made since it last reported, how many of them took over
    50 ms, and the long tasks the page's timeline showed during them. A
    reader that sent none is not measured, which the row says with NULL.

    Returns the fields the run could not read and the moment it was written,
    which record_capture's change names once the write has committed.
    """
    drift = [d for d in (payload.get("drift") or []) if isinstance(d, str)][:10]
    now = datetime.now(timezone.utc)
    # One row per browser, reader and minute when the worker stamped the run:
    # ten tabs reading one post report one run a minute, the newest report
    # standing for the minute. A run from an older extension is a row each.
    instance = clean_stamp(payload.get("stamp")).get("browser_instance_id")
    values = {
        "observed_at": now.isoformat(), "extractor": extractor, "page_kind": _text(payload.get("page_kind"), 40),
        "items_seen": _count(payload.get("items_seen")), "items_kept": _count(payload.get("items_kept")),
        "drift": json.dumps([_text(d, 60) for d in drift]) if drift else None,
        "extension_version": _text(payload.get("extension_version"), 40),
        "duration_ms": _millis(payload.get("duration_ms")), "reads": _count(payload.get("reads")),
        "slow_reads": _count(payload.get("slow_reads")), "long_tasks": _count(payload.get("long_tasks")),
        "long_task_ms": _millis(payload.get("long_task_ms")), "refused": _text(refused, 40),
        "items_dropped": _count(payload.get("items_dropped")),
        "browser_instance_id": instance, "minute": now.isoformat()[:16] if instance else None,
    }
    names = list(values)
    sql = f"INSERT INTO captures ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})"
    if instance:
        sql += (" ON CONFLICT(browser_instance_id, extractor, minute) DO UPDATE SET "
                + ", ".join(f"{n} = excluded.{n}" for n in names
                            if n not in ("browser_instance_id", "extractor", "minute")))
    conn.execute(sql, tuple(values[n] for n in names))
    conn.execute(PRUNE_CAPTURES, ((now - CAPTURE_RETENTION).isoformat(),))
    return drift, now


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
                "SELECT observed_at, items_seen, items_kept, drift, refused, duration_ms, reads, slow_reads, "
                f"long_tasks, long_task_ms, {READ_SOMETHING} AS read_something FROM captures "
                "WHERE extractor = ? ORDER BY observed_at DESC LIMIT 1", (extractor,)).fetchone()
            last_good = conn.execute(
                f"SELECT observed_at FROM captures WHERE extractor = ? AND {GOOD_RUN} "
                "ORDER BY observed_at DESC LIMIT 1", (extractor,)).fetchone()
            # A run the studio refused stored nothing, so it is not a capture.
            last_capture = conn.execute(
                "SELECT observed_at FROM captures WHERE extractor = ? AND refused IS NULL "
                "ORDER BY observed_at DESC LIMIT 1", (extractor,)).fetchone()
            rows[extractor] = (latest, last_good, last_capture)
    finally:
        conn.close()

    health = []
    for extractor, label in EXTRACTORS.items():
        latest, last_good, last_capture = rows[extractor]
        drift = json.loads(latest["drift"]) if latest and latest["drift"] else []
        if not latest:
            state = "never_run"
        elif latest["refused"]:
            state = "refused"
        elif drift:
            state = "drifting"
        elif latest["read_something"]:
            state = "working"
        else:
            state = "read_nothing"
        health.append({
            "extractor": extractor,
            "label": label,
            "last_run_at": latest["observed_at"] if latest else None,
            "last_good_at": last_good["observed_at"] if last_good else None,
            "last_capture_at": last_capture["observed_at"] if last_capture else None,
            "drift": drift,
            "refused": latest["refused"] if latest else None,
            "state": state,
            # The reader's own timing on its latest run; None is not measured.
            "duration_ms": latest["duration_ms"] if latest else None,
            "reads": latest["reads"] if latest else None,
            "slow_reads": latest["slow_reads"] if latest else None,
            "long_tasks": latest["long_tasks"] if latest else None,
            "long_task_ms": latest["long_task_ms"] if latest else None,
        })
    return health


def _creators_post(conn, urn: str) -> bool:
    """
    Whether a post is one of the creator's own: a publication of theirs or a
    post the studio carries, in any of LinkedIn's three spellings of its id,
    each looked up by its index.
    """
    spellings = _post_identity()._spellings(urn)
    if not spellings:
        return False
    if conn.execute("SELECT 1 FROM own_posts WHERE activity_urn IN (?, ?, ?) LIMIT 1", spellings).fetchone():
        return True
    return conn.execute("SELECT 1 FROM posts WHERE activity_urn IN (?, ?, ?) LIMIT 1", spellings).fetchone() is not None


def forget_other_members_readings(conn) -> Dict[str, int]:
    """
    What network reading kept about other members before it kept the
    creator's own posts only: readings of posts that are not the creator's,
    the summaries built from them, and drift events whose schema carries
    other members. Kept drift events keep a path that names nobody. Run by
    this track's migration (_migrate_reader_timing_and_network_reading), after
    the ledger's backup, inside its transaction.
    """
    gone = {"readings": 0, "drift_events": 0}
    others = [row[0] for row in conn.execute("SELECT DISTINCT activity_urn FROM post_metric_observations")
              if not _creators_post(conn, row[0] or "")]
    for urn in others:
        gone["readings"] += conn.execute("DELETE FROM post_metric_observations WHERE activity_urn = ?",
                                         (urn,)).rowcount
    if others:
        # The deletes marked their summaries; recomputed, an empty one goes.
        post_summary.refresh(conn, others)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_drift_events'").fetchone():
        gone["drift_events"] = conn.execute(
            f"DELETE FROM schema_drift_events WHERE schema_name NOT IN ({', '.join('?' for _ in VOYAGER_KEPT)})",
            tuple(VOYAGER_KEPT)).rowcount
        for rowid, url in conn.execute("SELECT rowid, source_url FROM schema_drift_events "
                                       "WHERE source_url IS NOT NULL").fetchall():
            cleaned = clean_voyager_path(url)
            if cleaned != url:
                conn.execute("UPDATE schema_drift_events SET source_url = ? WHERE rowid = ?", (cleaned, rowid))
    return gone


def extension_health() -> Dict[str, Any]:
    """
    The bridge and its readers. What network reading added here (whether it
    was active, its captures in the last day, its drift events and its schema
    version) went with it in 2.10.2.
    """
    return {"bridge": bridge_status(), "extractors": capture_health()}


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


def _record_account_point(conn, clean: Dict[str, Any]) -> bool:
    """
    The profile's follower and connection counts as a point in the daily
    series, on the day they were read.

    creator_identity held one follower count, overwritten by every read, so
    the monthly profile visit left no history and Analytics could not plot
    followers unless the creator also opened the analytics page. The counts
    go through the same path that page's follower card uses: a row for the
    day with nothing but the two counts, or the day's row with its counts
    filled in and every other figure left as it was. A count the page did not
    show keeps the earlier one. creator_identity still carries the latest
    count; this is where "over time" lives.
    """
    followers, connections = clean.get("follower_count"), clean.get("connection_count")
    if followers is None and connections is None:
        return False
    conn.execute(
        """
        INSERT INTO analytics_daily (
            date, followers, connections, precision, period_label, source,
            impressions, unique_members_reached, reactions, comments, shares, engagement_rate
        )
        VALUES (?, ?, ?, NULL, '1d', 'observed', NULL, NULL, NULL, NULL, NULL, NULL)
        ON CONFLICT(date) DO UPDATE SET
            followers = COALESCE(excluded.followers, analytics_daily.followers),
            connections = COALESCE(excluded.connections, analytics_daily.connections)
        """,
        (datetime.now(timezone.utc).strftime("%Y-%m-%d"), followers, connections),
    )
    return True


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
                _record_account_point(conn, clean)
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
    _accounts_changed()
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
            # The posts made from the creator's publications go with them,
            # where nothing in the studio has touched them: they hold the
            # creator's post text and LinkedIn id and nothing written here.
            _post_identity().forget_reconstructions(conn)
            for table in ("creator_identity", "creator_positions", "creator_education",
                          "creator_skills", "own_posts", "outbound_engagements", "self_import_requests",
                          "post_metric_observations",
                          "audience_demographic_readings",
                          # From your record (cycle 4, track 7): what they asked, the
                          # batches built for them, their marks and their notes.
                          "asks", "daily_view", "daily_run", "card_marks", "record_notes",
                          "own_reposts"):
                conn.execute(f"DELETE FROM {table}")
            # And what LinkedIn's archive brought: connections and the record of each import.
            forget_archive(conn)
            # What the phone asked the desk to read, and the analytics export's record (cycle 4, track 6).
            forget_phone_and_export(conn)
            _unfill_creator_settings(conn)
            # The import requests it waited on are gone, and their ids can be
            # issued again, so a chain left behind could take a new one for its own.
            _save_chain(conn, None)
    finally:
        conn.close()
    _accounts_changed()
    return {"status": "forgotten"}


def _accounts_changed() -> None:
    """Which profile holds which account changed: routing reads it again (bridge_routing)."""
    try:
        from . import bridge_routing
    except ImportError:
        import bridge_routing
    bridge_routing.forget()


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
    written = skipped = reposts = 0
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
                # The creator's own repost (track 5, phase 2): that it is one, its
                # date and its own figures only; never the original's (own_insights.py).
                if item.get("own_repost") is True and _ACTIVITY_URN.match(urn):
                    reposts += own_insights.record_own_repost(conn, urn, item)
                    continue
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
                own_insights.record_edited(conn, urn, item)
                # The counts shown on the activity page are a reading too.
                _record_observation(conn, urn, "activity_page", counts)
                how = _bind_to_studio(conn, urn, _text(item.get("text"), 10000), published_at_from_urn(urn))
                if how:
                    bound[how] += 1
    finally:
        conn.close()
    changes.publish("posts")
    return {"status": "success", "written": written, "skipped": skipped, "reposts_recorded": reposts,
            "bound_to_posts": bound["post"], "bound_to_drafts": bound["draft"]}


# The counts the post analytics page shows. The first seven have been read
# since cycle 2; the rest are LinkedIn's own per-post figures from the same
# page (migration 28): followers gained from this post, profile viewers from
# this post, link visits, and the article and video figures a post of that
# kind carries. Never derived from analytics_daily.followers: two posts in
# one week share that window.
METRIC_FIELDS = ("impressions", "members_reached", "reactions", "comments", "reposts", "saves", "sends",
                 "followers_gained", "profile_viewers", "link_visits", "article_views", "video_views",
                 # A video's watch time and average watch time, in seconds (phase 2).
                 "watch_time_seconds", "average_watch_seconds")
# The share of impressions from inside and outside the creator's network, as
# the percentage LinkedIn printed (0 to 100). A share is not a count: it is
# stored as read and never summed.
SHARE_FIELDS = ("in_network_pct", "out_of_network_pct")
READING_FIELDS = METRIC_FIELDS + SHARE_FIELDS


def _share(value: Any) -> Optional[float]:
    """A percentage from a capture, 0 to 100, or None when the page did not show one."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 2) if 0.0 <= number <= 100.0 else None

# How precisely a reading was read, as migration 5 records it for the
# analytics page: 'exact' when every figure was written out, 'rounded' when
# LinkedIn abbreviated one (12K), and None when the reader did not say. The
# activity page's card reader sends no flag, so its readings are None, which
# claims nothing either way.
PRECISIONS = ("exact", "rounded")


def _precision(value: Any) -> Optional[str]:
    return value if value in PRECISIONS else None


def _record_observation(conn, activity_urn: str, source: str, metrics: Dict[str, Any]) -> bool:
    """
    Keeps one reading of a post's figures, with the post's age at that moment.

    One per post per source per hour: re-reading a page within the hour
    refreshes that hour's reading rather than adding another, so scrolling
    the activity page twice does not double the history. A reading refreshed
    within the hour is rounded if either read was: a rounded figure cannot
    become exact by being read again.
    """
    values = {k: _count(metrics.get(k)) for k in METRIC_FIELDS}
    values.update({k: _share(metrics.get(k)) for k in SHARE_FIELDS})
    if all(v is None for v in values.values()):
        return False
    now = datetime.now(timezone.utc)
    published = published_at_from_urn(activity_urn)
    age = round((now - datetime.fromisoformat(published)).total_seconds() / 3600.0, 2) if published else None
    conn.execute(
        f"""
        INSERT INTO post_metric_observations
            (activity_urn, observed_at, observed_hour, age_hours, source, precision, {", ".join(READING_FIELDS)})
        VALUES (?, ?, ?, ?, ?, ?, {", ".join("?" for _ in READING_FIELDS)})
        ON CONFLICT(activity_urn, source, observed_hour) DO UPDATE SET
            observed_at = excluded.observed_at, age_hours = excluded.age_hours,
            precision = CASE
                WHEN excluded.precision = 'rounded' OR post_metric_observations.precision = 'rounded' THEN 'rounded'
                ELSE COALESCE(excluded.precision, post_metric_observations.precision) END,
            {", ".join(f"{k} = COALESCE(excluded.{k}, post_metric_observations.{k})" for k in READING_FIELDS)}
        """,
        (activity_urn, now.isoformat(), now.strftime("%Y-%m-%dT%H"), age, source, _precision(metrics.get("precision")),
         *[values[k] for k in READING_FIELDS]),
    )
    # The post's summary row keeps its two day and latest readings; the
    # trigger marked them, and they are recomputed here, in this transaction.
    post_summary.refresh(conn, [activity_urn])
    return True


# One reading of the viewer demographics block holds at most this many
# entries: six dimensions of a top five each is thirty.
DEMOGRAPHIC_ENTRIES = 60


def _record_demographics(conn, activity_urn: str, source: str, entries: Any) -> int:
    """
    The top viewer demographics as the page showed them, dated.

    One row per day per dimension and label (migration 28): a second read
    the same day refreshes the percentage, a read on another day adds a
    point, so "LinkedIn's top five on date D against date E" can be asked.
    audience_demographics, which has no date, is left as it was.
    """
    if not isinstance(entries, list):
        return 0
    now = datetime.now(timezone.utc)
    recorded = 0
    for entry in entries[:DEMOGRAPHIC_ENTRIES]:
        if not isinstance(entry, dict):
            continue
        dimension = _text(entry.get("dimension"), 40)
        label = _text(entry.get("label"), 120)
        percentage = _share(entry.get("percentage"))
        if not dimension or not label or percentage is None:
            continue
        conn.execute(
            """
            INSERT INTO audience_demographic_readings
                (observed_at, observed_on, activity_urn, source, dimension, label, percentage)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(observed_on, activity_urn, source, dimension, label) DO UPDATE SET
                observed_at = excluded.observed_at, percentage = excluded.percentage
            """,
            (now.isoformat(), now.strftime("%Y-%m-%d"), activity_urn, source, dimension.lower(), label, percentage),
        )
        recorded += 1
    return recorded


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
            # A publication recorded before every path gave it its post (an
            # archive import, or the bridge before cycle 4) is given it here.
            _post_identity().ensure_post(conn, urn)
            recorded = _record_observation(conn, urn, "post_analytics", metrics)
            demographics = _record_demographics(conn, urn, "post_analytics", metrics.get("demographics"))
            impressions = _count(metrics.get("impressions"))
            if impressions is not None:
                conn.execute("UPDATE own_posts SET impressions = ?, last_seen_at = ? WHERE activity_urn = ?",
                             (impressions, _now(), urn))
    finally:
        conn.close()
    changes.publish("readings", post=urn)
    return {"status": "success", "recorded": recorded, "demographics_recorded": demographics}


def post_readings(activity_urn: str) -> List[Dict[str, Any]]:
    """Every reading of one post, oldest first, with how precisely each was read."""
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(
            f"SELECT observed_at, age_hours, source, precision, {', '.join(READING_FIELDS)} "
            "FROM post_metric_observations WHERE activity_urn = ? ORDER BY observed_at", (activity_urn,))]
    finally:
        conn.close()


def post_demographics(activity_urn: str) -> List[Dict[str, Any]]:
    """Every dated demographics entry read for one post, oldest day first, largest share first within a day."""
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT observed_on, observed_at, source, dimension, label, percentage "
            "FROM audience_demographic_readings WHERE activity_urn = ? "
            "ORDER BY observed_on, dimension, percentage DESC, label", (activity_urn,))]
    finally:
        conn.close()


# The figures the post analytics reader added in cycle 4, in the words a
# sentence uses. Their labels are unverified against a 2026 page, and by the
# owner's decision of 2026-10-26 an absent one is not drift: nothing is
# stored for it and the reader stays working. So that a label which never
# appears is still visible, post_analytics_sightings says how long each has
# gone unread, from the readings alone.
UNVERIFIED_FIELDS = (
    ("followers_gained", "followers gained from this post"),
    ("profile_viewers", "profile viewers from this post"),
    ("link_visits", "link visits"),
    ("article_views", "article views"),
    ("video_views", "video views"),
    ("in_network_pct", "the share of impressions from your network"),
    ("out_of_network_pct", "the share of impressions from outside your network"),
    ("demographics", "viewer demographics"),
    ("watch_time_seconds", "a video's watch time"),
    ("average_watch_seconds", "a video's average watch time"),
)
SIGHTINGS_MEANING = ("LinkedIn may not show this figure to every member or on every post. "
                     "If it never appears, the label may have changed.")


def post_analytics_sightings() -> Dict[str, Any]:
    """
    Per figure the post analytics reader added in cycle 4: when one of the
    creator's post analytics pages last carried it, and how many post
    analytics readings have been taken since, in a sentence such as
    "followers gained from this post: not read on any of the last 12 post
    analytics pages". Readings from the activity page carry none of these
    figures and are not counted. The roll-up thins readings older than its
    window, so a count that reaches back past it counts the readings kept.
    """
    conn = get_db()
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM post_metric_observations WHERE source = 'post_analytics'").fetchone()[0]
        fields = []
        for field, label in UNVERIFIED_FIELDS:
            if field == "demographics":
                last = conn.execute("SELECT MAX(observed_at) FROM audience_demographic_readings "
                                    "WHERE source = 'post_analytics'").fetchone()[0]
            else:
                last = conn.execute(f"SELECT MAX(observed_at) FROM post_metric_observations "
                                    f"WHERE source = 'post_analytics' AND {field} IS NOT NULL").fetchone()[0]
            since = total if last is None else conn.execute(
                "SELECT COUNT(*) FROM post_metric_observations WHERE source = 'post_analytics' AND observed_at > ?",
                (last,)).fetchone()[0]
            fields.append({"field": field, "label": label,
                           **results.sighting(label, total, last, since, ("post analytics page", "post analytics pages"))})
    finally:
        conn.close()
    return {"status": "success", "post_analytics_readings": total, "fields": fields, "meaning": SIGHTINGS_MEANING}


def _bind_to_studio(conn, activity_urn: str, text: Optional[str], published_at: Optional[str]) -> Optional[str]:
    """
    Connects one of the creator's LinkedIn posts to the studio record it came
    from, and gives it one when there is none. Returns how it bound ("post",
    "draft"), or None when it was already bound or a post was made for it.

    An imported own post is already proven to be the creator's, by its actor,
    so any writing of theirs may be its source. Which record it is is decided
    by post_identity.bind_activity_urn, the one binder, called through
    post_identity.ensure_post, the one rule for a publication's post: this
    used to bind only, so a post that matched no studio draft was left with
    no posts row and its engagers route answered 404.
    """
    try:
        from . import post_identity
    except ImportError:
        import post_identity

    result = post_identity.ensure_post(conn, activity_urn, text, published_at=published_at)
    how = result.get("how") if result else None
    return how if how in ("post", "draft") else None


def note_own_post(post_urn: Any) -> Optional[str]:
    """
    The creator's post an engager was read on, made known to the studio.

    The engagement gate lets an engager through when the post's author is the
    confirmed creator, and a post the studio had never recorded was then left
    holding people it could not answer for: no publication, no posts row, and
    the engagers route said 404 (found by cycle 4's track 3 on 2.7.0). Its
    publication is recorded here, with no words, which the page did not
    send, and a date read from its id; an archive record of the same post is
    joined rather than repeated; and its post comes from
    post_identity.ensure_post, the one rule. Returns the post's id, or None
    for a URN that is not an activity of the creator's to record.

    Only an activity URN is recorded: a share or ugcPost id read off a feed
    card cannot be told apart from the activity the bridge will later read
    the same post under, so recording it would make one post two.
    """
    try:
        from . import post_identity
    except ImportError:
        import post_identity

    urn = post_identity.canonical_urn(post_urn) if isinstance(post_urn, str) else None
    if not urn:
        return None
    conn = get_db()
    wrote = False
    try:
        with conn:
            known = post_identity._publication_by_urn(conn, urn)
            if known is None:
                # A post a studio record already carries is known, and its
                # engagers already resolve to it: nothing is written.
                carried = post_identity.bound_post(conn, urn)
                if carried:
                    return carried[0]["id"]
            if known is None and not _ACTIVITY_URN.match(urn):
                return None
            if known is None:
                twin = find_archive_twin(conn, urn, "", archive_only=True)
                if twin:
                    conn.execute("UPDATE own_posts SET activity_urn = ? WHERE activity_urn = ?", (urn, twin))
                else:
                    now = _now()
                    published = published_at_from_urn(urn)
                    conn.execute(
                        "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, "
                        "first_seen_at, last_seen_at) VALUES (?, NULL, ?, ?, ?, ?)",
                        (urn, published, "urn_decode" if published else None, now, now))
                wrote = True
            result = post_identity.ensure_post(conn, urn)
            wrote = wrote or bool(result and result.get("how") != "existing")
    finally:
        conn.close()
    # A post the studio did not hold before, said once the write has
    # committed (studio/backend/changes.py), as the creator's posts ingest
    # says it; the engagement that brought it here says "people" after.
    if wrote:
        changes.publish("posts")
    return result["post_id"] if result else None


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
    reload the extension, not to import again, unless the bridge heard from
    since needs no reload (state() asks ingest_contract.heard_current()).
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


# A history import is claimed by one tab of one browser. Two visible tabs on
# one activity page both used to scroll it, and the import is the one place
# the extension acts on LinkedIn, so it must never run twice. The holder
# renews its claim with every event it sends (a progress event while it
# scrolls); a claim not renewed for this long is free for another tab, so a
# tab that went hidden, was discarded or closed does not hold it for ever.
IMPORT_CLAIM_TTL = timedelta(seconds=90)
IMPORT_EVENTS = ("started", "paused", "resumed", "progress", "released", "finished")
CLAIMED_ELSEWHERE = "claimed_elsewhere"


def _claim_is_live(row: Dict[str, Any], now: datetime) -> bool:
    claimed_at = row.get("claimed_at")
    if not row.get("claimed_by") or not claimed_at:
        return False
    try:
        return now - datetime.fromisoformat(claimed_at) < IMPORT_CLAIM_TTL
    except ValueError:
        return False


def pending_import(kind: Any, claimant: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    The live request for this kind, if the creator made one recently. Named
    by a tab (`claimant`), it is that tab's to run: handed to it when no
    other tab holds a live claim, and claimed for it; another tab asking
    meanwhile is answered None. An extension that names no tab is answered
    as before.
    """
    if kind not in IMPORT_KINDS:
        return None
    now = datetime.now(timezone.utc)
    cutoff = (now - IMPORT_REQUEST_TTL).isoformat()
    conn = get_db()
    try:
        with conn:
            _expire_requests(conn)
            row = conn.execute(
                "SELECT id, kind, requested_at, started_at, claimed_by, claimed_at FROM self_import_requests "
                "WHERE kind = ? AND finished_at IS NULL AND requested_at >= ? ORDER BY id DESC LIMIT 1",
                (kind, cutoff),
            ).fetchone()
            if row and claimant:
                held = dict(row)
                if held["claimed_by"] not in (None, claimant) and _claim_is_live(held, now):
                    return None
                conn.execute("UPDATE self_import_requests SET claimed_by = ?, claimed_at = ? WHERE id = ?",
                             (claimant, now.isoformat(), held["id"]))
    finally:
        conn.close()
    if not row:
        return None
    found = dict(row)
    found.pop("claimed_by", None)
    found.pop("claimed_at", None)
    return found


def update_import(request_id: Any, event: Any, items_seen: Any = None, outcome: Any = None,
                  claimant: Optional[str] = None) -> Dict[str, Any]:
    try:
        request_id = int(request_id)
    except (TypeError, ValueError):
        raise RefusedCapture("unknown import request")
    if event not in IMPORT_EVENTS:
        raise RefusedCapture("event must be started, paused, resumed, progress, released or finished")
    conn = get_db()
    chain = None
    try:
        with conn:
            if claimant:
                # Only the holder of a live claim moves the import: a tab whose
                # claim went quiet and was taken over is told so, and stops.
                now = datetime.now(timezone.utc)
                held = conn.execute("SELECT claimed_by, claimed_at FROM self_import_requests WHERE id = ?",
                                    (request_id,)).fetchone()
                if held and held["claimed_by"] not in (None, claimant) and _claim_is_live(dict(held), now):
                    return {"status": CLAIMED_ELSEWHERE}
                if event == "released":
                    conn.execute("UPDATE self_import_requests SET claimed_by = NULL, claimed_at = NULL "
                                 "WHERE id = ? AND claimed_by = ?", (request_id, claimant))
                    return {"status": "success"}
                conn.execute("UPDATE self_import_requests SET claimed_by = ?, claimed_at = ? "
                             "WHERE id = ? AND finished_at IS NULL", (claimant, now.isoformat(), request_id))
            elif event == "released":
                return {"status": "success"}
            chain = _load_chain(conn)
            if event == "progress":
                conn.execute("UPDATE self_import_requests SET items_seen = COALESCE(?, items_seen) "
                             "WHERE id = ? AND finished_at IS NULL", (_count(items_seen), request_id))
            elif event == "started":
                # A tab starting an import someone paused and gave back is
                # scrolling it now, so it no longer reads as paused.
                conn.execute(
                    "UPDATE self_import_requests SET started_at = COALESCE(started_at, ?), "
                    "outcome = CASE WHEN outcome = ? THEN NULL ELSE outcome END "
                    "WHERE id = ? AND finished_at IS NULL", (_now(), IMPORT_PAUSED_HIDDEN, request_id),
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
    # The last posts import was read by an older extension. Reloading is the
    # fix only while the browser still runs one: once the bridge heard from
    # needs no reload (it reloaded itself, or was reloaded), the advice is to
    # import again, and "reload" is not said.
    current = ingest_contract.heard_current()
    if outdated and current:
        outdated = False

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
        "health": capture_health(),
        # Said once, only where network reading ran (network_reading_retired).
        "network_reading_retired": network_reading_retired(),
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
        # The bridge heard from needs no reload, so an import an older
        # extension read is imported again, not preceded by a reload.
        "extension_current": current,
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
