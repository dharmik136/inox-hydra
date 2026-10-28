"""
The collection box: everything sent to the bot, in one place.
=============================================================

Phase 3 of the Telegram bot (docs/quality/cycle4/collection-box.md). One
person, one bot, and that bot is the single collection box for everything
they send: a note, an idea, a forwarded message, a link. Each lands here as
an item, with when it arrived, its kind, its words, its tags and a topic
read locally, a status (new, used, not now) and what it became. Nothing is
written from an item until the creator asks.

What is kept, and what never is:

- A link to one of the creator's posts, and a short link, are requests on
  Today, as they were (desk_requests.py); the item points at the request.
- A link to anyone else's post is a bookmark: the address rebuilt from the
  post's activity id, and the creator's own words with it. The address the
  phone sent carries the author's name and the post's words in its slug,
  and tracking parameters; none of that is kept. Every LinkedIn post link in
  any item's words is rebuilt the same way.
- A forwarded message keeps its text as the creator's note. Who or what it
  was forwarded from is never kept (ingress.py never hands it here).

Each write is published on the change stream (kind "collection"), so the
studio shows an item the moment the phone sends it.

Strict Invariants:
- Zero em-dashes.
- Nothing here reaches the network, and nothing is fetched or read from a link.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import unquote

try:
    from . import changes, desk_requests, post_identity
    from .database import get_db
except ImportError:
    import changes
    import desk_requests
    import post_identity
    from database import get_db

KINDS = ("note", "idea", "forward", "post", "link", "bookmark", "photo", "voice")
KIND_SAID = {
    "note": "Note",
    "idea": "Idea",
    "forward": "Forwarded",
    "post": "Your post",
    "link": "Link",
    "bookmark": "Bookmark",
    "photo": "Photo",
    "voice": "Voice note",
}
STATUSES = ("new", "used", "not_now")
# The creator sets these; "used" is set by making something from an item.
SET_BY_CREATOR = ("new", "not_now")
# Kinds whose words are material to write from (a request on Today is not).
MATERIAL = ("note", "idea", "forward", "bookmark", "photo", "voice")

POST_LINK = re.compile(r"https?://(?:[a-z]{1,3}\.)?linkedin\.com/[^\s<>\"']+", re.IGNORECASE)
HASHTAG = re.compile(r"#(\w{1,50})")
TAGS_KEPT = 30
PAGE = 50

# What a draft an item became is now, in the box's words.
BECAME_SAID = {
    "draft": "A draft in the Composer",
    "scheduled": "Queued in the Composer",
    "due": "Queued, and due now",
    "published": "Published",
    "sent": "Published",
}
GONE_SAID = "A draft since deleted in the studio"


class Refused(ValueError):
    """A change the box will not make, with the sentence that says why."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_post_link(activity_urn: str) -> str:
    """A post's address from its id alone: names no one, carries no words."""
    return f"https://www.linkedin.com/feed/update/{activity_urn}/"


def clean_links(text: str) -> str:
    """Every LinkedIn post link in the words rebuilt from its activity id: no slug, no tracking."""
    def rebuilt(found):
        urn = post_identity.extract_activity_urn(unquote(found.group(0)))
        return canonical_post_link(urn) if urn else found.group(0)
    return POST_LINK.sub(rebuilt, text or "")


def hashtags(text: str) -> List[str]:
    """The words' hashtags, lower case, each once, in the order written."""
    seen: List[str] = []
    for tag in HASHTAG.findall(text or ""):
        tag = tag.lower()
        if tag not in seen:
            seen.append(tag)
    return seen[:TAGS_KEPT]


def _creator_topics(conn) -> List[str]:
    """The topics the creator gave in Setup ("What you write about"), each as written."""
    row = conn.execute("SELECT text FROM asks WHERE source = 'setup' AND field = 'topics' AND status != 'retired' "
                       "ORDER BY updated_at DESC LIMIT 1").fetchone()
    if not row or not row[0]:
        return []
    return [part.strip() for part in re.split(r"[,;\n]", row[0]) if part.strip()]


def topic_of(conn, text: str, tags: Iterable[str]) -> Optional[str]:
    """
    A topic, read locally: the first of the creator's own topics whose words
    the item's words name, else its first hashtag, else none. No model.
    """
    words = set(re.findall(r"\w+", (text or "").lower()))
    for topic in _creator_topics(conn):
        topic_words = re.findall(r"\w+", topic.lower())
        if topic_words and all(word in words for word in topic_words):
            return topic
    tags = list(tags)
    return tags[0] if tags else None


def _row(conn, row) -> Dict[str, Any]:
    item = dict(row)
    try:
        item["tags"] = json.loads(item.get("tags") or "[]")
    except (TypeError, ValueError):
        item["tags"] = []
    try:
        item["angles"] = json.loads(item.get("angles") or "[]")
    except (TypeError, ValueError):
        item["angles"] = []
    item["kind_said"] = KIND_SAID.get(item["kind"], item["kind"])
    item["became"] = became(conn, item)
    return item


def became(conn, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """What an item became: a draft (and where it is now), or the request on Today. None while it is material."""
    if item.get("post_id"):
        post = conn.execute("SELECT status FROM posts WHERE id = ?", (item["post_id"],)).fetchone()
        said = BECAME_SAID.get(post[0], BECAME_SAID["draft"]) if post else GONE_SAID
        return {"kind": "draft", "post_id": item["post_id"], "said": said}
    if item.get("desk_request_id"):
        request = conn.execute("SELECT id, activity_urn, state, link FROM desk_requests WHERE id = ?",
                               (item["desk_request_id"],)).fetchone()
        if not request:
            return {"kind": "request", "said": "A request on Today, since closed"}
        waiting = request["state"] == desk_requests.OPEN and desk_requests.waits_for_its_post(dict(request))
        said = desk_requests.SAID_SHORT if waiting else desk_requests.SAID.get(request["state"], "")
        return {"kind": "request", "said": said}
    return None


def by_origin(origin_ref: str) -> Optional[Dict[str, Any]]:
    """The item a message already made, if it was handled before."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM collection_items WHERE origin_ref = ?", (origin_ref,)).fetchone()
        return _row(conn, row) if row else None
    finally:
        conn.close()


def get(conn, item_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM collection_items WHERE id = ?", (int(item_id),)).fetchone()
    return _row(conn, row) if row else None


def add(kind: str, text: str = "", *, link: Optional[str] = None, activity_urn: Optional[str] = None,
        desk_request_id: Optional[int] = None, status: str = "new", post_id: Optional[str] = None,
        source: str = "telegram", origin_ref: Optional[str] = None, tags: Optional[List[str]] = None,
        conn=None) -> Dict[str, Any]:
    """
    One item in the collection, and its publication on the change stream.
    A message already recorded (the same origin_ref) is not written twice:
    the item it made is returned.
    """
    if kind not in KINDS:
        raise Refused(f"An item is one of {', '.join(KINDS)}.")
    if status not in STATUSES:
        raise Refused(f"An item's status is one of {', '.join(STATUSES)}.")
    words = clean_links((text or "").strip())[:50000]
    own = conn is None
    conn = conn or get_db()
    try:
        if origin_ref:
            held = conn.execute("SELECT * FROM collection_items WHERE origin_ref = ?", (origin_ref,)).fetchone()
            if held:
                return _row(conn, held)
        tags = list(tags) if tags is not None else hashtags(words)
        now = _now()
        with conn:
            item_id = conn.execute(
                "INSERT INTO collection_items (received_at, kind, text, link, activity_urn, desk_request_id, tags, "
                "topic, status, post_id, source, origin_ref, updated_at, used_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now, kind, words, link, activity_urn, desk_request_id, json.dumps(tags),
                 topic_of(conn, words, tags), status, post_id, source, origin_ref, now,
                 now if status == "used" else None)).lastrowid
        item = get(conn, item_id)
    finally:
        if own:
            conn.close()
    changes.publish("collection")
    return item


def listing(status: str = "new", kind: Optional[str] = None, q: Optional[str] = None,
            limit: int = PAGE, offset: int = 0) -> Dict[str, Any]:
    """
    The box: items newest first, of one status (new by default) or all, of
    one kind or every kind, holding a word or not; and how many there are of
    each status.
    """
    if status not in STATUSES + ("all",):
        raise Refused("Show new, not now, used or all.")
    if kind and kind not in KINDS:
        raise Refused(f"A kind is one of {', '.join(KINDS)}.")
    where, params = [], []
    if status != "all":
        where.append("status = ?")
        params.append(status)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    for word in re.findall(r"\S+", (q or "").strip())[:8]:
        where.append("(text LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\' OR COALESCE(topic, '') LIKE ? ESCAPE '\\')")
        like = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        params += [like, like, like]
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    conn = get_db()
    try:
        rows = conn.execute(f"SELECT * FROM collection_items{clause} ORDER BY received_at DESC, id DESC "
                            "LIMIT ? OFFSET ?", params + [max(1, min(int(limit), 200)), max(0, int(offset))]).fetchall()
        counts = {s: 0 for s in STATUSES}
        for found_status, count in conn.execute("SELECT status, COUNT(*) FROM collection_items GROUP BY status"):
            counts[found_status] = count
        counts["all"] = sum(counts[s] for s in STATUSES)
        return {"status": "success", "items": [_row(conn, r) for r in rows], "counts": counts}
    finally:
        conn.close()


def set_status(item_id: int, status: str) -> Dict[str, Any]:
    """New or not now, as the creator says. Used is what making something from an item sets."""
    if status not in SET_BY_CREATOR:
        raise Refused("An item is set aside (not now) or brought back (new); it is used when something is made "
                      "from it.")
    conn = get_db()
    try:
        if not get(conn, item_id):
            raise LookupError("That item is no longer in your collection.")
        with conn:
            conn.execute("UPDATE collection_items SET status = ?, updated_at = ? WHERE id = ?",
                         (status, _now(), int(item_id)))
        item = get(conn, item_id)
    finally:
        conn.close()
    changes.publish("collection")
    return item


def remove(item_id: int) -> bool:
    """Removes an item for good. Says whether there was one. A draft made from it stays a draft."""
    conn = get_db()
    try:
        with conn:
            gone = conn.execute("DELETE FROM collection_items WHERE id = ?", (int(item_id),)).rowcount
    finally:
        conn.close()
    if gone:
        changes.publish("collection")
    return bool(gone)


def mark_used(conn, item_ids: Iterable[int], post_id: str) -> None:
    """The items a draft was made from: used, and what they became."""
    now = _now()
    for item_id in item_ids:
        conn.execute("UPDATE collection_items SET status = 'used', post_id = ?, used_at = ?, updated_at = ? "
                     "WHERE id = ?", (post_id, now, now, int(item_id)))


def new_draft(conn, content: str, tags: Optional[List[str]] = None) -> str:
    """A Composer draft (a posts row), as a card's Draft from this makes one. Returns its id."""
    post_id = f"post_{uuid.uuid4().hex[:10]}"
    conn.execute("INSERT INTO posts (id, content, media_urls, status, tags) VALUES (?, ?, '[]', 'draft', ?)",
                 (post_id, content[:5000], json.dumps(["collection"] + list(tags or []))))
    return post_id


def use_as_draft(item_id: int) -> Dict[str, Any]:
    """Use as a draft: the item's words, as they are, as a Composer draft; the item is used."""
    conn = get_db()
    try:
        item = get(conn, item_id)
        if not item:
            raise LookupError("That item is no longer in your collection.")
        content = (item["text"] or "").strip()
        if not content:
            raise Refused("This item has no words of yours to make a draft from.")
        with conn:
            post_id = new_draft(conn, content, item["tags"])
            mark_used(conn, [item["id"]], post_id)
    finally:
        conn.close()
    changes.publish("collection")
    return {"status": "drafted", "id": post_id, "content": content}


def undo(item_id: Any) -> str:
    """
    The bot's Undo under "Saved to your collection.": removes the item while
    it is still new, and says so. A key of telegram_bot.SENTENCES.
    """
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return "undo_item_gone"
    conn = get_db()
    try:
        row = conn.execute("SELECT status FROM collection_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return "undo_item_gone"
        with conn:
            gone = conn.execute("DELETE FROM collection_items WHERE id = ? AND status = 'new' AND post_id IS NULL",
                                (item_id,)).rowcount
    finally:
        conn.close()
    if gone:
        changes.publish("collection")
    return "undone_item" if gone else "undo_item_kept"


def least_offered(conn) -> Optional[Dict[str, Any]]:
    """The morning idea's pick: a new item with words, never offered first, then the one offered longest ago."""
    marks = ", ".join("?" for _ in MATERIAL)
    row = conn.execute(
        f"SELECT * FROM collection_items WHERE status = 'new' AND kind IN ({marks}) AND TRIM(text) != '' "
        "ORDER BY offered_at IS NOT NULL, offered_at, received_at, id LIMIT 1", MATERIAL).fetchone()
    return _row(conn, row) if row else None


def offered(conn, item_id: int) -> None:
    """The morning idea offered this item now."""
    with conn:
        conn.execute("UPDATE collection_items SET offered_at = ? WHERE id = ?", (_now(), int(item_id)))


def forget_draft(conn, post_id: str) -> None:
    """A draft taken back with the bot's Undo: the item that recorded it goes with it."""
    conn.execute("DELETE FROM collection_items WHERE post_id = ?", (post_id,))


def drafts_made(conn, start: datetime, end: datetime) -> int:
    """How many drafts were made from what was sent, from `start` up to `end`."""
    count = 0
    for (used_at,) in conn.execute("SELECT MAX(used_at) FROM collection_items WHERE post_id IS NOT NULL "
                                   "GROUP BY post_id"):
        try:
            when = datetime.fromisoformat(str(used_at))
        except (TypeError, ValueError):
            continue
        when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
        count += 1 if start <= when < end else 0
    return count


def forget(conn) -> None:
    """Delete everything: every item the creator sent."""
    conn.execute("DELETE FROM collection_items")
