"""
Post Identity
=============
Binding a post the creator wrote to the post LinkedIn published.

Every attribution surface in this product joins on that binding, and none of
them have ever worked, because nothing recorded it. lead_interactions.post_id is
populated on 0 of 842 rows in the install this was written for, and post_urn on
336, all of which hold one of two test fixtures and join to nothing.

The chain has three links:

  1. The creator injects a draft into LinkedIn's composer. The studio caused
     that event, so it can record it: a posts row with a fingerprint of the text
     and a timestamp. This is bookkeeping, not observation.
  2. The creator later opens their own post. The URL contains the activity URN,
     and the page contains the text. If the text matches an armed fingerprint,
     the URN belongs to that row.
  3. Engagers captured from that page carry the URN.

Link 2 is the only one that reads LinkedIn, and it reads a page the creator
opened themselves, from location.pathname rather than from markup. No request is
made, and nothing depends on a CSS class that LinkedIn can rename.

The fingerprint deliberately does not try to be exact. LinkedIn rewrites
whitespace, converts some characters and may append nothing at all, so a hash of
the raw text would never match. What survives is the sequence of word characters
in the opening of the post, which is enough to tell one of a creator's own
drafts from another.
"""

import hashlib
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# How much of the opening to fingerprint. Long enough that two drafts on the
# same topic do not collide, short enough to survive a truncated render.
FINGERPRINT_CHARS = 140

# A LinkedIn activity URN as it appears in a post permalink.
ACTIVITY_URN_PATTERN = re.compile(r"urn:li:(?:activity|share|ugcPost):\d+")

# What a post this studio published is keyed by until LinkedIn's own id for it
# is known. A post the creator published from the Composer is out, so it has a
# publication record, but only LinkedIn can say what its activity id is, and
# inventing one that looks like LinkedIn's would put a dead permalink on
# screen. This namespace is deliberately not urn:li:, so ACTIVITY_URN_PATTERN
# does not match it, no capture can be attributed to it, and
# linkedin_permalink() refuses to build a link for it. bind_activity_urn
# replaces it with the real URN the first time the post is seen on LinkedIn.
LOCAL_URN_PREFIX = "urn:inox:post:"

# The numeric id inside a URN of any of LinkedIn's three post namespaces. One
# post is named urn:li:activity:N on its permalink and urn:li:share:N or
# urn:li:ugcPost:N in the data archive, with the same N.
_URN_ID = re.compile(r"urn:li:(?:activity|share|ugcPost):(\d+)")

# A content fingerprint as content_fingerprint() formats it.
_FINGERPRINT = re.compile(r"\d+:[0-9a-f]{32}")

# A bare activity id, as a permalink's last path element sometimes gives it.
_BARE_ID = re.compile(r"^\d{10,25}$")

# Everything that is not a letter or a digit, in any script. This was
# [^0-9a-z], which reduced a post in Devanagari, Gujarati, Chinese, Arabic or
# Cyrillic to nothing, so none of those creators' posts could ever be bound.
# Combining marks (Devanagari vowel signs among them) fall outside \w and are
# dropped, which loses a little distinctiveness and survives LinkedIn
# composing or decomposing them differently.
_NON_WORD = re.compile(r"[\W_]+")


def normalize_for_fingerprint(text: str) -> str:
    """
    Reduce post text to what survives a round trip through LinkedIn.

    Case, punctuation, emoji, combining marks, the bold unicode letterforms
    this studio's formatter emits, and every kind of whitespace are all
    discarded. What is left is the case-folded spine of letters and digits, in
    whatever script the post is written. For plain English text that is exactly what
    the ASCII-only version produced, so fingerprints stored before still match.
    """
    if not text:
        return ""
    # Unbold BEFORE folding case. The mathematical alphanumeric block has no
    # case mapping, so casefold leaves it alone; mapping it back to ASCII
    # afterwards yields capitals, which the non-word filter would then strip.
    # This studio's own formatter emits those letterforms, so getting the order
    # wrong means a post injected from the studio never matches itself.
    plain = "".join(_unbold(ch) for ch in text)
    # NFKC so that a letter typed precomposed and one LinkedIn hands back
    # decomposed are the same letter, and full-width forms fold to their
    # ordinary ones.
    return _NON_WORD.sub("", unicodedata.normalize("NFKC", plain).casefold())


def _unbold(ch: str) -> str:
    """Map a mathematical alphanumeric codepoint back to its ASCII equivalent."""
    o = ord(ch)
    # Bold, italic, bold-italic, script, fraktur, sans and monospace letters.
    for start, base in (
        (0x1D400, "A"), (0x1D434, "A"), (0x1D468, "A"), (0x1D49C, "A"),
        (0x1D504, "A"), (0x1D5A0, "A"), (0x1D5D4, "A"), (0x1D608, "A"),
        (0x1D63C, "A"), (0x1D670, "A"),
    ):
        if start <= o < start + 26:
            return chr(ord(base) + o - start)
        if start + 26 <= o < start + 52:
            return chr(ord("a") + o - start - 26)
    if 0x1D7CE <= o <= 0x1D7FF:  # bold and sans digits
        return str((o - 0x1D7CE) % 10)
    return ch


def content_fingerprint(text: str) -> Optional[str]:
    """
    A stable short identifier for the opening of a piece of post text.

    Formatted "<length>:<hash>", because the length is needed to compare it
    against a candidate. A fingerprint that hashed the whole normalized text
    would not match once LinkedIn or the creator appended anything: a post whose
    spine is shorter than the window would have trailing hashtags fall inside
    the hashed region, and the same post would then fail to match itself.
    Carrying the length lets a comparison slice the candidate to exactly the
    span that was fingerprinted.

    Returns None when there is not enough text to identify anything. A
    fingerprint of two words would match half the creator's drafts, and a wrong
    binding is worse than no binding: it would attribute one post's engagers to
    another.
    """
    opening = normalize_for_fingerprint(text)[:FINGERPRINT_CHARS]
    if len(opening) < 24:
        return None
    digest = hashlib.sha256(opening.encode("utf-8")).hexdigest()[:32]
    return f"{len(opening)}:{digest}"


def fingerprint_matches(candidate_text: str, fingerprint: str) -> bool:
    """
    True when a page's post text opens with the fingerprinted span.

    A post rendered on its permalink carries what the creator wrote, plus
    whatever they or LinkedIn added after it. Comparing openings rather than
    whole texts is what makes the binding survive an edit that appends.
    """
    if not fingerprint or ":" not in fingerprint:
        return False
    length_part, _, digest = fingerprint.partition(":")
    try:
        length = int(length_part)
    except ValueError:
        return False

    candidate = normalize_for_fingerprint(candidate_text)
    if len(candidate) < length:
        return False
    opening = candidate[:length]
    return hashlib.sha256(opening.encode("utf-8")).hexdigest()[:32] == digest


def extract_activity_urn(url_or_path: str) -> Optional[str]:
    """
    Pull the activity URN out of a post permalink.

    LinkedIn writes these three ways:

        /feed/update/urn:li:activity:7390000000000000103/
        /feed/update/urn:li:share:7390000000000000103/
        /posts/someone_slug-activity-7390000000000000103-AbCd

    The first two carry the URN literally. The third carries the numeric id
    after "activity-", which is the same number.
    """
    if not url_or_path:
        return None

    found = ACTIVITY_URN_PATTERN.search(url_or_path)
    if found:
        return found.group(0)

    slug = re.search(r"-activity-(\d{6,})", url_or_path)
    if slug:
        return f"urn:li:activity:{slug.group(1)}"

    return None


# ---------------------------------------------------------------------------
# One identity for a post
# ---------------------------------------------------------------------------
#
# Four tables used to answer "what did the creator write": posts (the studio's
# own record), own_posts (the record of what LinkedIn published), drafts and
# queue_items. They disagreed, and 36% of captured engagement could not be
# reached from the post it belonged to.
#
# The shape now:
#
#   posts       is THE record. One row per thing the creator wrote, keyed by
#               the studio's own id, carrying the status it is at, the
#               fingerprint that recognises it on LinkedIn, and the activity
#               URN once LinkedIn's id for it is known.
#   own_posts   is the record of the publication: the figures and the
#               readings, keyed by the URN, with post_id naming the posts row
#               it belongs to. One publication per post, one post per
#               publication.
#   drafts      holds nothing posts does not: create_draft writes the posts
#               row beside it, and migration 26 brought the rest across.
#   queue_items is gone (migration 26). Nothing reachable wrote or read it.
#
# Everything that turns an identifier into a post comes through resolve(), and
# everything that learns a post's URN comes through bind_activity_urn().
# There is one of each.

# Statuses that mean the text has left the drafting stage, so a page showing
# that text may be this post even when nothing armed a fingerprint for it.
# routers/posts.py POSTED_STATUSES names the same idea for its own refusals.
POSTED_STATUSES = ("published", "scheduled", "queued", "due", "sent", "injected")

# How far a studio record's time may run past a post's publish time and still
# be its source: the machine's clock and LinkedIn's can disagree a little.
BIND_CLOCK_SKEW = timedelta(minutes=10)

# What resolve() reads off a posts row.
_POST_COLUMNS = "id, content, status, activity_urn, content_fingerprint, published_at, scheduled_for, created_at"


def local_urn(post_id: str) -> str:
    """The key a post this studio published is recorded under until LinkedIn's own id is known."""
    return f"{LOCAL_URN_PREFIX}{post_id}"


def is_local_urn(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(LOCAL_URN_PREFIX)


def activity_id(value: Any) -> str:
    """
    The numeric id inside a post URN, whichever of LinkedIn's three
    namespaces it is written in, or "". One post is urn:li:activity:N on its
    permalink and urn:li:share:N or urn:li:ugcPost:N in the data archive.
    """
    found = _URN_ID.search(value or "") if isinstance(value, str) else None
    return found.group(1) if found else ""


def linkedin_permalink(urn: Any) -> Optional[str]:
    """
    The LinkedIn address of a post, or None when there is not one to give.

    A post published from the studio is recorded under a local key until the
    creator opens it on LinkedIn, and a link built from that key would 404.
    Nothing invented on screen: a screen with no URL says so instead.
    """
    return f"https://www.linkedin.com/feed/update/{urn}/" if ACTIVITY_URN_PATTERN.fullmatch(urn or "") else None


def canonical_urn(value: Any) -> Optional[str]:
    """
    A post URN from whatever the product was handed: a URN, a permalink, a
    slug carrying the activity id, or the bare id. None when it holds none.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if _BARE_ID.fullmatch(text):
        return f"urn:li:activity:{text}"
    return extract_activity_urn(text)


def _query(conn, sql: str, params: Any = ()) -> List[Any]:
    """Rows addressable by column name, whatever the connection's row factory."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    return cursor.execute(sql, params).fetchall()


def _own_posts_has_post_id(conn) -> bool:
    """
    Whether own_posts carries the column migration 26 adds.

    Resolution runs on databases that have not been migrated yet (the CLI's
    doctor, a backup being inspected), and a missing column must answer
    "no publication row" rather than raise.
    """
    return any(r[1] == "post_id" for r in conn.execute("PRAGMA table_info(own_posts)"))


def _publication_of(conn, post_id: Optional[str], activity_urn: Optional[str]) -> Optional[Any]:
    """The own_posts row for a post: by its URN, else by the post it names."""
    if activity_urn:
        rows = _query(conn, "SELECT activity_urn, post_id, text, published_at FROM own_posts WHERE activity_urn = ?",
                      (activity_urn,))
        if rows:
            return rows[0]
    if post_id and _own_posts_has_post_id(conn):
        rows = _query(conn, "SELECT activity_urn, post_id, text, published_at FROM own_posts WHERE post_id = ?",
                      (post_id,))
        if rows:
            return rows[0]
    return None


def _ref(conn, post: Any, matched: str) -> Dict[str, Any]:
    """
    One post's identity, however it was asked for.

    engagement_urns is every key the post's captured engagement may be filed
    under: the URN the posts row carries and the one its publication record
    does, which differ for a post LinkedIn named one way on its permalink and
    another way in the creator's archive. A local key is left out, because no
    capture can be attributed to it.
    """
    publication = _publication_of(conn, post["id"], post["activity_urn"])
    publication_urn = post["activity_urn"] or (publication["activity_urn"] if publication else None)
    spellings = [u for u in (post["activity_urn"], publication_urn) if u and not is_local_urn(u)]
    return {
        "post_id": post["id"],
        "activity_urn": post["activity_urn"],
        "publication_urn": publication_urn,
        "engagement_urns": list(dict.fromkeys(spellings)),
        "status": post["status"],
        "text": post["content"],
        "content_fingerprint": post["content_fingerprint"],
        "published_at": post["published_at"] or (publication["published_at"] if publication else None),
        "matched": matched,
    }


def bound_post(conn, urn: str) -> Optional[Any]:
    """
    The posts row that carries this URN, in any of LinkedIn's three
    namespaces, and how it matched. None when no post is bound to it.

    One post is urn:li:activity:N on its permalink and urn:li:share:N in the
    creator's data archive, so comparing the strings alone found neither.
    """
    rows = _query(conn, f"SELECT {_POST_COLUMNS} FROM posts WHERE activity_urn = ?", (urn,))
    if rows:
        return rows[0], "activity_urn"
    wanted = activity_id(urn)
    if wanted:
        for row in _query(conn, f"SELECT {_POST_COLUMNS} FROM posts WHERE activity_urn IS NOT NULL"):
            if activity_id(row["activity_urn"]) == wanted:
                return row, "activity_id"
    return None


def resolve(conn, identifier: Any) -> Optional[Dict[str, Any]]:
    """
    The one post an identifier names, or None.

    Every identifier the product uses is accepted, because callers are handed
    all of them: the studio's own id from its own screens, an activity URN
    from the extension, a share or ugcPost URN from the creator's data
    archive, a permalink or a slug from a browser tab, a bare activity id, the
    local key a studio publication is recorded under, and a content
    fingerprint from the inject-then-bind chain.

    Two posts matching one fingerprint resolve to neither: a wrong answer
    credits one post's engagers to another and is very hard to notice.
    """
    if identifier is None:
        return None
    value = identifier.strip() if isinstance(identifier, str) else str(identifier).strip()
    if not value:
        return None

    if is_local_urn(value):
        if _own_posts_has_post_id(conn):
            rows = _query(conn, "SELECT post_id FROM own_posts WHERE activity_urn = ? AND post_id IS NOT NULL",
                          (value,))
            if rows:
                found = _query(conn, f"SELECT {_POST_COLUMNS} FROM posts WHERE id = ?", (rows[0]["post_id"],))
                if found:
                    return _ref(conn, found[0], "publication")
        return None

    # A URN is read as a URN first. A posts row may be named by one (a
    # database seeded before the studio had its own key for a post), so the
    # id is still tried below when no post carries the URN.
    urn = canonical_urn(value)
    if urn:
        bound = bound_post(conn, urn)
        if bound:
            return _ref(conn, bound[0], bound[1])
        # The publication record can know a post before the posts row does.
        if _own_posts_has_post_id(conn):
            wanted = activity_id(urn)
            for row in _query(conn, "SELECT activity_urn, post_id FROM own_posts WHERE post_id IS NOT NULL"):
                if activity_id(row["activity_urn"]) == wanted:
                    found = _query(conn, f"SELECT {_POST_COLUMNS} FROM posts WHERE id = ?", (row["post_id"],))
                    if found:
                        return _ref(conn, found[0], "publication")

    rows = _query(conn, f"SELECT {_POST_COLUMNS} FROM posts WHERE id = ?", (value,))
    if rows:
        return _ref(conn, rows[0], "studio_id")

    if _FINGERPRINT.fullmatch(value):
        rows = _query(conn, f"SELECT {_POST_COLUMNS} FROM posts WHERE content_fingerprint = ?", (value,))
        return _ref(conn, rows[0], "fingerprint") if len(rows) == 1 else None

    return None


# ---------------------------------------------------------------------------
# The one binder
# ---------------------------------------------------------------------------
#
# There were two, with different candidate sets and different tie breaks:
# POST /api/v1/posts/bind-urn, which runs when the creator opens a post's
# permalink, and onboarding._bind_to_studio, which ran when the extension
# imported the creator's own posts. A post could therefore bind one way and
# not the other. This is both of them.
#
# The rule, once:
#
#   1. A posts row already carrying this post's id, in any namespace, is the
#      answer: already bound.
#   2. Otherwise, among the posts rows that have no URN yet and whose opening
#      the page's text matches, exactly one binds. Two or more bind nothing: a
#      wrong binding credits one post's engagers to another.
#   3. A row that did not exist when the post went out cannot be where it came
#      from, so it is not a candidate, unless the creator marked it published
#      themselves, which they often do after posting.
#   4. Among several matches, the single one whose stored fingerprint matches
#      wins. That is the row the studio put into LinkedIn's composer.
#   5. With nothing in posts, a drafts row that matches gets a posts row made
#      for it. The legacy drafts store keeps no writing of its own now, so
#      this only ever fires on a database written before migration 26.
#
# Who may be matched depends on what is proven. An imported own post, or a
# permalink whose author is the confirmed creator, is proven to be theirs, so
# any text of theirs may be its source. A permalink whose author the bridge
# could not read is not, so only a post that already left the studio is
# considered: a plain draft can hold somebody else's words.


def _parse_moment(value: Any) -> Optional[datetime]:
    """A stored time, ISO or SQLite's "YYYY-MM-DD HH:MM:SS" (UTC), or None."""
    if not value or not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _matches(text: str, stored_fingerprint: Optional[str], content: Optional[str]) -> bool:
    """
    Whether a page's text opens the way a stored row does.

    Both the stored fingerprint and the one the row's text gives today are
    tried: a fingerprint stored before the normaliser kept every script's
    letters no longer matches text with accents, circled digits or non-Latin
    letters in it.
    """
    return any(
        fingerprint and fingerprint_matches(text, fingerprint)
        for fingerprint in (stored_fingerprint, content_fingerprint(content or ""))
    )


def _existed_by_then(row: Any, posted: Optional[datetime]) -> bool:
    """
    Whether a studio row was already written when the post went out.

    Without this, a new draft that reused an old hit's opening was taken over
    by a history import: marked published, with the old post's date and
    figures, and gone from the drafts. A row the creator marked published is
    exempt, because "Mark as published" stamps the click, which is often after
    the post. A scheduled row counts from the earlier of written and due.
    """
    if posted is None:
        return True
    keys = row.keys() if hasattr(row, "keys") else ()
    status = ((row["status"] or "").lower() if "status" in keys else "")
    if status == "published":
        return True
    times = [row["created_at"] if "created_at" in keys else None]
    if status == "scheduled" and "scheduled_for" in keys:
        times.append(row["scheduled_for"])
    moments = [m for m in (_parse_moment(t) for t in times) if m]
    return not moments or min(moments) <= posted + BIND_CLOCK_SKEW


def published_at_from_urn(activity_urn: Any) -> Optional[str]:
    """When a post was published, read from its activity id. onboarding owns the decoding."""
    try:
        from .onboarding import published_at_from_urn as decode
    except (ImportError, ValueError):
        from onboarding import published_at_from_urn as decode
    return decode(activity_urn)


def _is_the_creators(author_vanity: Any) -> bool:
    try:
        from . import onboarding
    except (ImportError, ValueError):
        import onboarding
    me = onboarding.confirmed_vanity()
    return bool(me) and onboarding.normalise_vanity(author_vanity) == me


def bind_activity_urn(
    conn,
    activity_urn: Any,
    text: Optional[str],
    published_at: Optional[str] = None,
    author_vanity: Optional[str] = None,
    from_history: bool = False,
    prefer_post_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Binds one LinkedIn post to the one studio record it came from.

    from_history says the URN arrived in an import of the creator's own posts
    rather than from a page they are standing on. That changes two things, and
    nothing else: the post is proven to be theirs by its actor, so any writing
    of theirs may be its source; and the import brings years of posts at once,
    so a row written after a post cannot be where it came from. On a permalink
    the creator opened, a row with no fingerprint and no posted status is not
    considered at all, because a draft can hold somebody else's words.

    Writes inside the caller's transaction, as post_summary.refresh does, so a
    capture that binds leaves nothing half written. Returns the answer both
    callers report: status, bound, post_id, activity_urn, and how many
    candidates were weighed.

    status is one of invalid_urn, not_yours, already_bound, bound, ambiguous,
    no_match, or too_short (the text cannot identify anything).
    """
    urn = canonical_urn(activity_urn)
    if not urn:
        return {"status": "invalid_urn", "bound": False, "activity_urn": activity_urn}

    # Whose post the page showed. A follower's plain repost of the creator's
    # post shows the creator's text under the repost's own activity id, so a
    # text match alone bound the repost and the real post never bound after it.
    proven_own = from_history
    if author_vanity:
        if not _is_the_creators(author_vanity):
            return {"status": "not_yours", "bound": False, "activity_urn": urn}
        proven_own = True

    already = bound_post(conn, urn)
    if already:
        return {"status": "already_bound", "bound": True, "post_id": already[0]["id"], "activity_urn": urn}

    body = text or ""
    if content_fingerprint(body) is None:
        return {"status": "too_short", "bound": False, "activity_urn": urn}

    posted = (_parse_moment(published_at) or _parse_moment(published_at_from_urn(urn))) if from_history else None
    eligible = (
        f"SELECT {_POST_COLUMNS} FROM posts WHERE activity_urn IS NULL AND COALESCE(content, '') != ''"
    )
    if not proven_own:
        eligible += (
            " AND (content_fingerprint IS NOT NULL OR status IN ("
            + ", ".join("'" + s + "'" for s in POSTED_STATUSES) + "))"
        )
    candidates = _query(conn, eligible + " ORDER BY COALESCE(published_at, scheduled_for, created_at) DESC")
    matched = [r for r in candidates
               if _matches(body, r["content_fingerprint"], r["content"]) and _existed_by_then(r, posted)]

    # The side panel names the post it filled LinkedIn's composer from, and
    # that beats a text match on any other row.
    if len(matched) > 1 and prefer_post_id:
        named = [r for r in matched if r["id"] == prefer_post_id]
        if len(named) == 1:
            matched = named
    # A database from before the insert route stopped copying posts holds a
    # queued post and a second, armed copy. Both match by text; the armed one
    # is the post the creator put into LinkedIn.
    if len(matched) > 1:
        armed = [r for r in matched if r["content_fingerprint"] and fingerprint_matches(body, r["content_fingerprint"])]
        if len(armed) == 1:
            matched = armed

    now_iso = datetime.now(timezone.utc).isoformat()
    if len(matched) == 1:
        row = matched[0]
        conn.execute(
            "UPDATE posts SET activity_urn = ?, status = 'published', "
            "content_fingerprint = COALESCE(content_fingerprint, ?), "
            "published_at = COALESCE(?, published_at, ?) WHERE id = ?",
            (urn, content_fingerprint(row["content"] or ""), published_at or published_at_from_urn(urn),
             now_iso, row["id"]),
        )
        _claim_publication(conn, row["id"], urn, body, published_at)
        return {"status": "bound", "bound": True, "post_id": row["id"], "activity_urn": urn,
                "candidates_considered": len(candidates), "how": "post"}

    if len(matched) > 1:
        return {"status": "ambiguous", "bound": False, "activity_urn": urn,
                "candidates_considered": len(candidates)}

    if proven_own:
        bound = _bind_legacy_draft(conn, urn, body, published_at, posted)
        if bound:
            return {**bound, "candidates_considered": len(candidates)}

    return {"status": "no_match", "bound": False, "activity_urn": urn,
            "candidates_considered": len(candidates)}


def _bind_legacy_draft(conn, urn: str, text: str, published_at: Optional[str],
                       posted: Optional[datetime]) -> Optional[Dict[str, Any]]:
    """
    A drafts row that matches, given the posts row it should have had.

    The legacy drafts store has held nothing posts does not since migration
    26, so this only fires on a database written before it, or on a row put
    into drafts by hand.
    """
    if not _has_table(conn, "drafts"):
        return None
    drafts = [r for r in _query(
        conn,
        "SELECT id, raw_content, status, created_at FROM drafts WHERE COALESCE(raw_content, '') != '' "
        "AND id NOT IN (SELECT draft_id FROM posts WHERE draft_id IS NOT NULL)")
        if _matches(text, None, r["raw_content"]) and _existed_by_then(r, posted)]
    if len(drafts) != 1:
        return None
    post_id = f"post-{hashlib.sha256(urn.encode()).hexdigest()[:12]}"
    conn.execute(
        "INSERT INTO posts (id, content, status, published_at, content_fingerprint, draft_id, activity_urn) "
        "VALUES (?, ?, 'published', ?, ?, ?, ?)",
        (post_id, text, published_at, content_fingerprint(text), drafts[0]["id"], urn),
    )
    _claim_publication(conn, post_id, urn, text, published_at)
    return {"status": "bound", "bound": True, "post_id": post_id, "activity_urn": urn, "how": "draft"}


def _has_table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


# ---------------------------------------------------------------------------
# The publication record
# ---------------------------------------------------------------------------


def _claim_publication(conn, post_id: str, urn: str, text: Optional[str], published_at: Optional[str]) -> None:
    """
    Points the publication record at the post that has just bound to it, and
    absorbs the local record a studio publication was kept under.

    A post published from the studio is recorded under its local key straight
    away, so the studio can see its own post. When LinkedIn's id for it
    arrives, that local record becomes this one: its text and date are kept
    where the import brought none, and the local key is retired. Without this
    the creator would have two publications for one post, which is the
    duplication this batch exists to remove.
    """
    if not _own_posts_has_post_id(conn):
        return
    local = local_urn(post_id)
    mine = _query(conn, "SELECT activity_urn, text, published_at FROM own_posts WHERE activity_urn = ?", (local,))
    real = _query(conn, "SELECT activity_urn FROM own_posts WHERE activity_urn = ?", (urn,))

    if mine and not real:
        conn.execute(
            "UPDATE own_posts SET activity_urn = ?, text = COALESCE(?, text), "
            "published_at = COALESCE(?, published_at), published_at_source = 'studio' WHERE activity_urn = ?",
            (urn, text or None, published_at, local),
        )
        conn.execute("DELETE FROM post_engagement WHERE post_urn = ?", (local,))
    elif mine and real:
        # The import wrote the real row first. Keep what it did not bring.
        conn.execute(
            "UPDATE own_posts SET text = COALESCE(text, ?), published_at = COALESCE(published_at, ?) "
            "WHERE activity_urn = ?",
            (mine[0]["text"], mine[0]["published_at"], urn),
        )
        conn.execute("DELETE FROM own_posts WHERE activity_urn = ?", (local,))
        conn.execute("DELETE FROM post_engagement WHERE post_urn = ?", (local,))

    if real or mine:
        conn.execute("UPDATE own_posts SET post_id = ? WHERE activity_urn = ?", (post_id, urn))


def record_publication(conn, post_id: str, published_at: Optional[str] = None) -> Dict[str, Any]:
    """
    Records that a post the creator wrote has gone out.

    This is what an imported own post does, done for a post the studio
    published: the fingerprint that will recognise it on LinkedIn is armed,
    the publication record is created so every surface that reads own_posts
    can see the post, and its engagement row is created so the Posts screen
    has somewhere to read. Publishing used to write two columns, and the
    studio could not see its own published post until the extension imported
    it back.

    The figures are left unset, not zero: nothing has read them yet.

    Writes inside the caller's transaction. Returns the publication key and
    the fingerprint, or {"status": "no_such_post"}.
    """
    try:
        from . import post_summary
    except (ImportError, ValueError):
        import post_summary

    rows = _query(conn, f"SELECT {_POST_COLUMNS} FROM posts WHERE id = ?", (post_id,))
    if not rows:
        return {"status": "no_such_post"}
    post = rows[0]
    now_iso = datetime.now(timezone.utc).isoformat()
    moment = published_at or post["published_at"] or now_iso

    fingerprint = post["content_fingerprint"] or content_fingerprint(post["content"] or "")
    if fingerprint and fingerprint != post["content_fingerprint"]:
        conn.execute("UPDATE posts SET content_fingerprint = ? WHERE id = ?", (fingerprint, post_id))

    urn = post["activity_urn"] or local_urn(post_id)
    has_post_id = _own_posts_has_post_id(conn)
    columns = "activity_urn, text, published_at, published_at_source, first_seen_at, last_seen_at"
    values = [urn, post["content"], moment, "studio", now_iso, now_iso]
    if has_post_id:
        columns += ", post_id"
        values.append(post_id)
    conn.execute(
        f"INSERT INTO own_posts ({columns}) VALUES ({', '.join('?' for _ in values)}) "
        "ON CONFLICT(activity_urn) DO UPDATE SET "
        "text = COALESCE(excluded.text, own_posts.text), "
        "published_at = COALESCE(own_posts.published_at, excluded.published_at), "
        "last_seen_at = excluded.last_seen_at"
        + (", post_id = COALESCE(own_posts.post_id, excluded.post_id)" if has_post_id else ""),
        values,
    )
    post_summary.ensure_row(conn, urn)
    return {"status": "recorded", "post_id": post_id, "publication_urn": urn,
            "content_fingerprint": fingerprint, "published_at": moment}
