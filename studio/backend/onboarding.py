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

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from .database import get_db
except ImportError:
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

_VANITY = re.compile(r"^[a-z0-9][a-z0-9\-_%]{1,99}$")
_ACTIVITY_URN = re.compile(r"^urn:li:activity:(\d{10,25})$")

# Evidence a profile page belongs to the person viewing it. Named so the
# onboarding screen can say why the studio thinks this is you, and so an
# unknown label from a newer extension is refused rather than trusted.
KNOWN_SELF_EVIDENCE = {
    "owner_edit_controls": "Edit controls only you see were on the page",
    "me_redirect": "LinkedIn sent /in/me/ to this profile",
    "nav_profile_link": "Your own navigation menu links to this profile",
}


class RefusedCapture(ValueError):
    """A capture this module will not store, with a reason the caller can show."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_vanity(raw: Any) -> str:
    """
    The public identifier from `/in/<vanity>/`, in one canonical spelling.

    Accepts a bare vanity or any LinkedIn profile URL. Lowercased, without
    query string or trailing slash. Returns "" for anything that is not one.
    """
    if not isinstance(raw, str):
        return ""
    value = raw.strip()
    match = re.search(r"linkedin\.com/in/([^/?#]+)", value, re.IGNORECASE)
    if match:
        value = match.group(1)
    value = value.strip("/").lower()
    return value if _VANITY.match(value) else ""


def _text(value: Any, limit: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value[:limit] if value else None


def _count(value: Any) -> Optional[int]:
    """A count from a capture, or None when the page did not show one."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


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
}

CAPTURE_RETENTION = timedelta(days=7)


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
            conn.execute("DELETE FROM captures WHERE observed_at < ?", ((now - CAPTURE_RETENTION).isoformat(),))
    finally:
        conn.close()
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

    if clean.get("positions") is not None:
        conn.execute("DELETE FROM creator_positions")
        for i, p in enumerate(clean["positions"]):
            conn.execute(
                "INSERT INTO creator_positions (ordinal, title, company, date_range, location, description, observed_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (i, p["title"], p["company"], p["date_range"], p["location"], p["description"], now),
            )
    if clean.get("education") is not None:
        conn.execute("DELETE FROM creator_education")
        for i, e in enumerate(clean["education"]):
            conn.execute(
                "INSERT INTO creator_education (ordinal, school, degree, date_range, observed_at) VALUES (?,?,?,?,?)",
                (i, e["school"], e["degree"], e["date_range"], now),
            )
    if clean.get("skills") is not None:
        conn.execute("DELETE FROM creator_skills")
        conn.executemany(
            "INSERT INTO creator_skills (skill, observed_at) VALUES (?,?)",
            [(s, now) for s in clean["skills"]],
        )


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
    profile_url = f"https://www.linkedin.com/in/{vanity}/"

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
    for key, source in (("name", "display_name"), ("headline", "headline"), ("company", "current_company")):
        if not (profile.get(key) or "").strip() and clean.get(source):
            profile[key] = clean[source]
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('creator_profile', ?)",
        (json.dumps(profile),),
    )


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
            _write_profile(conn, wanted, f"https://www.linkedin.com/in/{wanted}/", clean)
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
                          "creator_skills", "own_posts", "outbound_engagements", "self_import_requests"):
                conn.execute(f"DELETE FROM {table}")
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
                if not _ACTIVITY_URN.match(urn) or normalise_vanity(item.get("actor")) != me:
                    skipped += 1
                    continue
                counts = {k: _count(item.get(k)) for k in ("reactions", "comments", "reposts", "impressions")}
                conn.execute(
                    """
                    INSERT INTO own_posts (activity_urn, text, published_at, published_at_source,
                                           reactions, comments, reposts, impressions, first_seen_at, last_seen_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(activity_urn) DO UPDATE SET
                        text = COALESCE(excluded.text, own_posts.text),
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
                how = _bind_to_studio(conn, urn, _text(item.get("text"), 10000), published_at_from_urn(urn))
                if how:
                    bound[how] += 1
    finally:
        conn.close()
    return {"status": "success", "written": written, "skipped": skipped,
            "bound_to_posts": bound["post"], "bound_to_drafts": bound["draft"]}


def _bind_to_studio(conn, activity_urn: str, text: Optional[str], published_at: Optional[str]) -> Optional[str]:
    """
    Connects one of the creator's LinkedIn posts to the studio record it came
    from. Returns how it bound ("post", "draft"), or None.

    Binding used to have one route: inject a draft through the composer
    button, which stored a fingerprint, then open the permalink. A post marked
    as published, handed to LinkedIn's scheduler, or retyped on LinkedIn never
    bound, so "which of my posts brought which people" had no answer for most
    of what the creator actually published.

    An imported own post is already proven to be the creator's, by its actor.
    What remains is which studio record it is, and that is decided by the text:

      1. an unbound posts row whose opening matches, else
      2. a draft whose opening matches, which gets a posts row created for it.

    Exactly one match binds. Two or more bind nothing, because a wrong binding
    credits one post's engagers to another and is very hard to notice. The
    fingerprint is the same deliberately loose one the permalink binding uses,
    which survives LinkedIn's rewriting of whitespace and characters.
    """
    try:
        from . import post_identity
    except ImportError:
        import post_identity

    if not text or post_identity.content_fingerprint(text) is None:
        return None
    if conn.execute("SELECT 1 FROM posts WHERE activity_urn = ?", (activity_urn,)).fetchone():
        return None

    def matches(stored_fingerprint, content):
        fingerprint = stored_fingerprint or post_identity.content_fingerprint(content or "")
        return bool(fingerprint) and post_identity.fingerprint_matches(text, fingerprint)

    posts = [r for r in conn.execute(
        "SELECT id, content, content_fingerprint, status, published_at FROM posts "
        "WHERE activity_urn IS NULL AND COALESCE(content, '') != ''")
        if matches(r["content_fingerprint"], r["content"])]
    if len(posts) == 1:
        row = posts[0]
        conn.execute(
            "UPDATE posts SET activity_urn = ?, "
            "content_fingerprint = COALESCE(content_fingerprint, ?), "
            "status = 'published', published_at = COALESCE(?, published_at) WHERE id = ?",
            (activity_urn, post_identity.content_fingerprint(row["content"]), published_at, row["id"]),
        )
        return "post"
    if len(posts) > 1:
        return None

    drafts = [r for r in conn.execute(
        "SELECT id, raw_content FROM drafts WHERE COALESCE(raw_content, '') != '' "
        "AND id NOT IN (SELECT draft_id FROM posts WHERE draft_id IS NOT NULL)")
        if matches(None, r["raw_content"])]
    if len(drafts) == 1:
        conn.execute(
            "INSERT INTO posts (id, content, status, published_at, content_fingerprint, draft_id, activity_urn) "
            "VALUES (?, ?, 'published', ?, ?, ?, ?)",
            (f"post-{hashlib.sha256(activity_urn.encode()).hexdigest()[:12]}", text, published_at,
             post_identity.content_fingerprint(text), drafts[0]["id"], activity_urn),
        )
        return "draft"
    return None


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
        return "confirm your profile in Setup first, so the studio can tell your posts from other people's"
    if normalise_vanity(engager_profile) == me:
        return "that is you"
    if normalise_vanity(post_author) == me:
        return None
    wanted = _activity_id(post_urn)
    if wanted:
        conn = get_db()
        try:
            for row in conn.execute("SELECT activity_urn FROM own_posts"):
                if _activity_id(row["activity_urn"]) == wanted:
                    return None
        finally:
            conn.close()
    return "not on one of your posts"


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

def _own_activity_ids(conn) -> set:
    ids = {_activity_id(r["activity_urn"]) for r in conn.execute("SELECT activity_urn FROM own_posts")}
    ids |= {_activity_id(r["activity_urn"]) for r in conn.execute(
        "SELECT activity_urn FROM posts WHERE activity_urn IS NOT NULL")}
    ids.discard("")
    return ids


def post_history_complete(conn) -> bool:
    """True once an import of the creator's posts has run to the end of the list."""
    return conn.execute(
        "SELECT 1 FROM self_import_requests WHERE kind = 'posts' AND outcome = 'completed' LIMIT 1"
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
        item["post_excerpt"] = " ".join(text.split())[:140] if text else None
    return interactions


def lead_review() -> Dict[str, Any]:
    """
    Every lead sorted by whether their engagement was on the creator's posts.

    A lead is "yours" if any interaction was on your post, "not_yours" only if
    every interaction names a post and none of them is yours (and your history
    is complete), and "unknown" otherwise, including leads added by hand, which
    have no captured interaction at all.
    """
    conn = get_db()
    try:
        own_ids = _own_activity_ids(conn)
        complete = post_history_complete(conn)
        leads = {r["id"]: dict(r) for r in conn.execute(
            "SELECT id, COALESCE(full_name, name) AS name, headline, created_at FROM leads")}
        origins: Dict[str, List[str]] = {lead_id: [] for lead_id in leads}
        for row in conn.execute("SELECT lead_id, post_urn FROM lead_interactions"):
            key = str(row["lead_id"])
            if key in origins:
                origins[key].append(_origin(row["post_urn"], own_ids, complete))
    finally:
        conn.close()

    groups = {"yours": [], "not_yours": [], "unknown": []}
    for lead_id, seen in origins.items():
        if "yours" in seen:
            verdict = "yours"
        elif seen and all(o == "not_yours" for o in seen):
            verdict = "not_yours"
        else:
            verdict = "unknown"
        groups[verdict].append({**leads[lead_id], "interactions": len(seen)})

    return {
        "status": "success",
        "history_complete": complete,
        "counts": {k: len(v) for k, v in groups.items()},
        "not_yours": sorted(groups["not_yours"], key=lambda l: l.get("created_at") or ""),
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
    finally:
        conn.close()
    return {"status": "success", "removed": len(chosen), "kept": len(lead_ids) - len(chosen)}


# ---------------------------------------------------------------------------
# History imports: the creator asks, the extension scrolls
# ---------------------------------------------------------------------------

def request_import(kind: Any) -> Dict[str, Any]:
    """
    The creator clicked "import my posts" (or comments, or reactions).

    The extension scrolls an activity page only when a request like this is
    pending, so scrolling always traces back to a click in the studio.
    """
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
            "open_url": f"https://www.linkedin.com/in/{confirmed_vanity()}/recent-activity/{_activity_tab(kind)}/"}


def _activity_tab(kind: str) -> str:
    return {"posts": "all", "comments": "comments", "reactions": "reactions"}[kind]


def pending_import(kind: Any) -> Optional[Dict[str, Any]]:
    """The live request for this kind, if the creator made one recently."""
    if kind not in IMPORT_KINDS:
        return None
    cutoff = (datetime.now(timezone.utc) - IMPORT_REQUEST_TTL).isoformat()
    conn = get_db()
    try:
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
    if event not in ("started", "finished"):
        raise RefusedCapture("event must be started or finished")
    conn = get_db()
    try:
        with conn:
            if event == "started":
                conn.execute(
                    "UPDATE self_import_requests SET started_at = COALESCE(started_at, ?) "
                    "WHERE id = ? AND finished_at IS NULL", (_now(), request_id),
                )
            else:
                conn.execute(
                    "UPDATE self_import_requests SET finished_at = ?, items_seen = ?, outcome = ? "
                    "WHERE id = ? AND finished_at IS NULL",
                    (_now(), _count(items_seen), _text(outcome, 40) or "completed", request_id),
                )
    finally:
        conn.close()
    return {"status": "success"}


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
    return {
        "health": capture_health(),
        "session": session,
        "status": "success",
        "bridge": bridge,
        "candidate": candidate,
        "identity": identity,
        "counts": {
            "posts": post_count,
            "comments": outbound.get("comment", 0),
            "reactions": outbound.get("reaction", 0),
        },
        "imports": imports,
        "steps": {
            "bridge": bool(bridge["last_seen_at"]),
            "identity": confirmed,
            "posts": post_count > 0,
            "activity": sum(outbound.values()) > 0,
        },
    }
