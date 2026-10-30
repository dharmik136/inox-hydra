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
    from . import changes, desk_requests, phone_media, post_identity
    from .database import get_db
except ImportError:
    import changes
    import desk_requests
    import phone_media
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
# A photo put in the media library, where the images for a post are kept.
MEDIA_SAID = "In your media library"
MEDIA_GONE_SAID = "Put in your media library, and since deleted there"


class Refused(ValueError):
    """A change the box will not make, with the sentence that says why."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _when(text: Any) -> Optional[datetime]:
    """A time as the collection keeps it, or None."""
    try:
        when = datetime.fromisoformat(str(text or "").strip())
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


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
    try:
        media = json.loads(item.get("media") or "null")
    except (TypeError, ValueError):
        media = None
    item["media"] = media if isinstance(media, dict) else None
    item["kind_said"] = KIND_SAID.get(item["kind"], item["kind"])
    item["became"] = became(conn, item)
    # Phase 4: how many of the creator's messages it is built from, and
    # whether one was edited on the phone (and after it was used).
    linked = _linked_mine(conn, item["id"])
    item["messages"] = len(linked)
    edited = [m["edited_at"] for m in linked if m["edited_at"]]
    item["edited_at"] = max(edited) if edited else None
    return item


def became(conn, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """What an item became: a draft (and where it is now), or the request on Today. None while it is material."""
    if item.get("post_id"):
        post = conn.execute("SELECT status FROM posts WHERE id = ?", (item["post_id"],)).fetchone()
        said = BECAME_SAID.get(post[0], BECAME_SAID["draft"]) if post else GONE_SAID
        return {"kind": "draft", "post_id": item["post_id"], "said": said}
    if item.get("media_asset_id"):
        held = conn.execute("SELECT 1 FROM media_assets WHERE id = ?", (item["media_asset_id"],)).fetchone()
        return {"kind": "media", "said": MEDIA_SAID if held else MEDIA_GONE_SAID}
    if item.get("desk_request_id"):
        request = conn.execute("SELECT id, activity_urn, state, link FROM desk_requests WHERE id = ?",
                               (item["desk_request_id"],)).fetchone()
        if not request:
            return {"kind": "request", "said": "A request on Today, since closed"}
        waiting = request["state"] == desk_requests.OPEN and desk_requests.waits_for_its_post(dict(request))
        said = desk_requests.SAID_SHORT if waiting else desk_requests.SAID.get(request["state"], "")
        return {"kind": "request", "said": said}
    return None


# ---------------------------------------------------------------------------
# Messages linked to items (phase 4): a reply adds to its item, an edit follows it
# ---------------------------------------------------------------------------

def _linked_mine(conn, item_id: int) -> List[Dict[str, Any]]:
    try:
        return [dict(r) for r in conn.execute(
            "SELECT id, chat_id, message_id, words, at, edited_at FROM collection_messages "
            "WHERE item_id = ? AND whose = 'yours' ORDER BY id", (int(item_id),))]
    except Exception:
        # A database from before the links were kept holds none.
        return []


def link_message(item_id: Any, chat_id: Any, message_id: Any, whose: str, words: Optional[str] = None,
                 conn=None) -> None:
    """
    One Telegram message linked to the item it is about: the creator's own
    (with the words it gave the item) or the bot's answer about it. A message
    linked once stays linked to its first item; a message id of 0 (an
    ephemeral message) is never linked.
    """
    if whose not in ("yours", "bot") or not isinstance(message_id, int) or message_id <= 0 or not str(chat_id or ""):
        return
    own = conn is None
    conn = conn or get_db()
    try:
        with conn:
            conn.execute("INSERT OR IGNORE INTO collection_messages (item_id, chat_id, message_id, whose, words, at) "
                         "VALUES (?, ?, ?, ?, ?, ?)", (int(item_id), str(chat_id), message_id, whose,
                                                       None if whose == "bot" else (words or ""), _now()))
    finally:
        if own:
            conn.close()


def item_for_message(chat_id: Any, message_id: Any) -> Optional[Dict[str, Any]]:
    """The item a message from this chat is linked to, the creator's or the bot's, while the item is kept."""
    if not isinstance(message_id, int) or message_id <= 0:
        return None
    conn = get_db()
    try:
        row = conn.execute("SELECT c.* FROM collection_messages m JOIN collection_items c ON c.id = m.item_id "
                           "WHERE m.chat_id = ? AND m.message_id = ?", (str(chat_id), message_id)).fetchone()
        return _row(conn, row) if row else None
    except Exception:
        return None
    finally:
        conn.close()


def _retag(old_text: str, new_text: str, tags: List[str]) -> List[str]:
    """The tags that came from the old words go, those of the new words come; any other tag stays."""
    gone = set(hashtags(old_text))
    kept = [t for t in tags if t not in gone]
    return (kept + [t for t in hashtags(new_text) if t not in kept])[:TAGS_KEPT]


def _rewords(conn, item: Dict[str, Any]) -> str:
    """
    An item's own words from the messages it is built from, their words
    joined by a blank line, written onto it with its tags and topic. An item
    with no message of the creator's linked keeps its words.
    """
    parts = [m["words"] for m in _linked_mine(conn, item["id"])]
    if not parts:
        return item["text"]
    text = "\n\n".join(p.strip() for p in parts if (p or "").strip())
    tags = _retag(item["text"], text, item["tags"])
    conn.execute("UPDATE collection_items SET text = ?, tags = ?, topic = ?, updated_at = ? WHERE id = ?",
                 (text, json.dumps(tags), topic_of(conn, text, tags), _now(), item["id"]))
    return text


def add_words(item_id: Any, chat_id: Any, message_id: Any, words: str) -> Optional[Dict[str, Any]]:
    """
    A reply from the phone: its words added to the item it replies to, as a
    part of its own after the others, whatever the item became. Handled
    again, nothing is added twice. Returns the item, or None when it is gone.
    """
    words = clean_links((words or "").strip())[:50000]
    conn = get_db()
    try:
        item = get(conn, int(item_id))
        if item is None or not words:
            return item
        with conn:
            if not _linked_mine(conn, item["id"]) and item["text"].strip():
                # Its own words first, from before its messages were linked.
                conn.execute("INSERT INTO collection_messages (item_id, chat_id, message_id, whose, words, at) "
                             "VALUES (?, '', NULL, 'yours', ?, ?)", (item["id"], item["text"], item["received_at"]))
            conn.execute("INSERT OR IGNORE INTO collection_messages (item_id, chat_id, message_id, whose, words, at) "
                         "VALUES (?, ?, ?, 'yours', ?, ?)", (item["id"], str(chat_id), message_id, words, _now()))
            _rewords(conn, item)
        item = get(conn, item["id"])
    finally:
        conn.close()
    changes.publish("collection")
    return item


def message_of(chat_id: Any, message_id: Any) -> Optional[Dict[str, Any]]:
    """
    The creator's message as the collection holds it, for an edit: its row,
    its item, and whether it is the first of the item's own messages (the
    one that made it), which an edit reads as that message was read.
    """
    if not isinstance(message_id, int) or message_id <= 0:
        return None
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM collection_messages WHERE chat_id = ? AND message_id = ? AND whose = 'yours'",
                           (str(chat_id), message_id)).fetchone()
        if row is None:
            return None
        item = get(conn, row["item_id"])
        if item is None:
            return None
        first = conn.execute("SELECT MIN(id) FROM collection_messages WHERE item_id = ? AND whose = 'yours' "
                             "AND message_id IS NOT NULL", (item["id"],)).fetchone()[0]
        return {"row": dict(row), "item": item, "first": first == row["id"]}
    except Exception:
        return None
    finally:
        conn.close()


def edit_words(row_id: int, words: str) -> Optional[Dict[str, Any]]:
    """
    An edit on the phone: the message's words replaced on its item, whatever
    the item became; what was made from it is not changed. Returns the item.
    """
    conn = get_db()
    try:
        row = conn.execute("SELECT item_id FROM collection_messages WHERE id = ?", (int(row_id),)).fetchone()
        item = get(conn, row["item_id"]) if row else None
        if item is None:
            return None
        with conn:
            conn.execute("UPDATE collection_messages SET words = ?, edited_at = ? WHERE id = ?",
                         (clean_links((words or "").strip())[:50000], _now(), int(row_id)))
            _rewords(conn, item)
        item = get(conn, item["id"])
    finally:
        conn.close()
    changes.publish("collection")
    return item


def take_words_back(item_id: Any, chat_id: Any, message_id: Any) -> str:
    """
    Undo under "Added to the item": the reply's words taken back off the
    item, while it has not been used since they were added. A key of
    telegram_bot.SENTENCES.
    """
    conn = get_db()
    try:
        item = get(conn, int(item_id)) if str(item_id or "").isdigit() else None
        if item is None:
            return "undo_item_gone"
        row = conn.execute("SELECT id, at FROM collection_messages WHERE item_id = ? AND chat_id = ? AND message_id = ? "
                           "AND whose = 'yours'", (item["id"], str(chat_id), message_id)).fetchone()
        if row is None:
            return "added_gone"
        used, added = _when(item.get("used_at")), _when(row["at"])
        if used is not None and added is not None and used > added:
            return "added_kept"
        with conn:
            conn.execute("DELETE FROM collection_messages WHERE id = ?", (row["id"],))
            _rewords(conn, item)
    finally:
        conn.close()
    changes.publish("collection")
    return "added_undone"


def _forget_links(conn, item_ids: Iterable[int]) -> None:
    for item_id in item_ids:
        try:
            conn.execute("DELETE FROM collection_messages WHERE item_id = ?", (int(item_id),))
        except Exception:
            return


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
        media: Optional[Dict[str, Any]] = None, conn=None) -> Dict[str, Any]:
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
                "topic, status, post_id, source, origin_ref, updated_at, used_at, media) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now, kind, words, link, activity_urn, desk_request_id, json.dumps(tags),
                 topic_of(conn, words, tags), status, post_id, source, origin_ref, now,
                 now if status == "used" else None, json.dumps(media) if media else None)).lastrowid
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
        held = get(conn, item_id)
        if not held:
            raise LookupError("That item is no longer in your collection.")
        with conn:
            conn.execute("UPDATE collection_items SET status = ?, updated_at = ? WHERE id = ?",
                         (status, _now(), int(item_id)))
            if held["status"] == "used" and status == "new" and held.get("post_id"):
                # The Composer's Undo after Add to the draft: the words came
                # back out of the draft, so the item became nothing.
                conn.execute("UPDATE collection_items SET post_id = NULL, used_at = NULL WHERE id = ?",
                             (int(item_id),))
        item = get(conn, item_id)
    finally:
        conn.close()
    changes.publish("collection")
    return item


def remove(item_id: int) -> bool:
    """
    Removes an item for good, with its photo or voice note. Says whether
    there was one. A draft made from it stays a draft, and a photo put in the
    media library stays there.
    """
    conn = get_db()
    try:
        row = conn.execute("SELECT media FROM collection_items WHERE id = ?", (int(item_id),)).fetchone()
        with conn:
            gone = conn.execute("DELETE FROM collection_items WHERE id = ?", (int(item_id),)).rowcount
            if gone:
                _forget_links(conn, [item_id])
    finally:
        conn.close()
    if gone:
        phone_media.discard(row["media"] if row else None)
        changes.publish("collection")
    return bool(gone)


def to_library(item_id: int) -> Dict[str, Any]:
    """
    Add to your media library: a copy of a photo where the images for a post
    are kept. The item is then used, and says so. Once is enough: asked
    again, it is where it was.
    """
    conn = get_db()
    try:
        item = get(conn, item_id)
        if not item:
            raise LookupError("That item is no longer in your collection.")
        if item["kind"] != "photo" or not item.get("media"):
            raise Refused("Only a photo goes into your media library; a voice note stays in your collection.")
        if item.get("became") and item["became"]["kind"] == "media" and item["became"]["said"] == MEDIA_SAID:
            return item
        now = _now()
        with conn:
            try:
                asset_id = phone_media.to_library(conn, item["media"])
            except FileNotFoundError:
                raise Refused("The photo is no longer on this computer, so it cannot go into your media library.")
            conn.execute("UPDATE collection_items SET media_asset_id = ?, status = 'used', used_at = ?, updated_at = ? "
                         "WHERE id = ?", (asset_id, now, now, int(item_id)))
        item = get(conn, item_id)
    finally:
        conn.close()
    changes.publish("collection")
    return item


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
        row = conn.execute("SELECT status, media FROM collection_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return "undo_item_gone"
        with conn:
            gone = conn.execute("DELETE FROM collection_items WHERE id = ? AND status = 'new' AND post_id IS NULL",
                                (item_id,)).rowcount
            if gone:
                _forget_links(conn, [item_id])
    finally:
        conn.close()
    if gone:
        phone_media.discard(row["media"])
        changes.publish("collection")
    return "undone_item" if gone else "undo_item_kept"


_STOPWORDS = frozenset((
    "about", "after", "again", "being", "could", "every", "first", "from", "have", "into", "just", "like", "more",
    "most", "much", "only", "other", "over", "should", "some", "than", "that", "their", "them", "then", "there",
    "these", "they", "this", "those", "very", "what", "when", "where", "which", "while", "will", "with", "would",
    "your", "yours", "were", "been", "also", "because", "does", "doing"))


def _keywords(text: str) -> set:
    """A text's words that carry meaning, read locally: four letters or more, not the common ones."""
    return {w for w in re.findall(r"[^\W\d_]{4,}", (text or "").lower()) if w not in _STOPWORDS}


def related(text: str, limit: int = 3) -> Dict[str, Any]:
    """
    The Composer's "From your collection": the new items whose words the
    draft shares, most shared first, then newest. Matched locally; nothing
    leaves the machine.
    """
    wanted = _keywords(text)
    if not wanted:
        return {"status": "success", "items": []}
    conn = get_db()
    try:
        marks = ", ".join("?" for _ in MATERIAL)
        scored = []
        for row in conn.execute(f"SELECT * FROM collection_items WHERE status = 'new' AND kind IN ({marks}) "
                                "AND TRIM(text) != ''", MATERIAL):
            shared = len(wanted & (_keywords(row["text"]) | set(json.loads(row["tags"] or "[]"))))
            if shared:
                scored.append((shared, row["received_at"], row))
        scored.sort(key=lambda found: (found[0], found[1]), reverse=True)
        return {"status": "success", "items": [_row(conn, row) for _shared, _at, row in scored[:max(1, int(limit))]]}
    finally:
        conn.close()


def used_in(item_id: int, post_id: str) -> Dict[str, Any]:
    """The Composer's Add to the draft: the item is used, and what it became is that draft."""
    if not post_id or len(str(post_id)) > 80:
        raise Refused("Name the draft it went into.")
    conn = get_db()
    try:
        if not get(conn, item_id):
            raise LookupError("That item is no longer in your collection.")
        with conn:
            mark_used(conn, [item_id], str(post_id))
        item = get(conn, item_id)
    finally:
        conn.close()
    changes.publish("collection")
    return item


def waiting(conn) -> int:
    """How many items with words are new: ideas not used yet."""
    marks = ", ".join("?" for _ in MATERIAL)
    return conn.execute(f"SELECT COUNT(*) FROM collection_items WHERE status = 'new' AND kind IN ({marks}) "
                        "AND TRIM(text) != ''", MATERIAL).fetchone()[0]


def matching(word: str) -> List[Dict[str, Any]]:
    """/recall: the items whose words hold a word, newest first."""
    words = re.findall(r"\w+", (word or "").lower())
    if not words:
        return []
    conn = get_db()
    try:
        found = []
        for row in conn.execute("SELECT * FROM collection_items WHERE TRIM(text) != '' ORDER BY received_at DESC, id DESC"):
            held = set(re.findall(r"\w+", row["text"].lower()))
            if all(w in held for w in words):
                found.append(_row(conn, row))
        return found
    finally:
        conn.close()


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
    """A draft taken back with the bot's Undo: the item that recorded it goes with it, and any file of its."""
    files = [row[0] for row in conn.execute("SELECT media FROM collection_items WHERE post_id = ? AND media IS NOT NULL",
                                            (post_id,))]
    _forget_links(conn, [row[0] for row in conn.execute("SELECT id FROM collection_items WHERE post_id = ?",
                                                        (post_id,))])
    conn.execute("DELETE FROM collection_items WHERE post_id = ?", (post_id,))
    for media in files:
        phone_media.discard(media)


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
    """Delete everything: every item the creator sent, the messages linked to them, and every file with them."""
    conn.execute("DELETE FROM collection_items")
    try:
        conn.execute("DELETE FROM collection_messages")
    except Exception:
        pass
    phone_media.forget()
