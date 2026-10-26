"""
From your record: what the creator asked, and the marks they put on the cards.
==============================================================================
Nothing the creator asked of the studio used to survive the answer: the
instruction box, Re-Hook, search and the palette persisted nothing, and the
access log drops query strings because it once held every typed word. So
the asks store is written only by explicit acts (decision 5):

  setup         the optional topics, audience and things-to-avoid fields
  ask_box       the box on the section itself
  composer      an instruction, only when the creator ticked "remember this"
  telegram      an "Idea:" sent from the phone (record_daily.sync_telegram_ideas)
  more_of_this  "More of this" on a card, which writes the card's topic
  archive_search  never written here: the archive's search queries are
                archive_records, imported only behind their own tick

Every ask is listed on the section's "What the studio knows" page, editable,
retirable and removable. Nothing typed anywhere else is kept.

The marks are the writer the deferred Library lacked (decision 3):

  keep    pins the card to Kept, the section's second level, and doubles its
          chance of coming back
  skip    not today: held back two weeks, and half as likely after
  hide    never shown again until "Unhide all"
  used    the studio's: "Draft from this" opened the Composer with the card
  posted  the studio's: a draft that came from a card went out (a trigger,
          migration 28, writes it whichever path took the post out)

Every mark changes selection only, never a figure, and takes effect on the
next day's batch.

Strict Invariants:
- Zero em-dashes.
- Zero egress.
- Nothing silent: no function here is called by anything the creator did not do.
"""

import json
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from . import evidence_briefing, record_cards, record_daily
    from .database import get_db
except ImportError:  # top-level import mode
    import evidence_briefing
    import record_cards
    import record_daily
    from database import get_db

MAX_ASK_CHARS = 2000
CREATOR_SOURCES = ("setup", "ask_box", "composer", "more_of_this")
SETUP_FIELDS = ("topics", "audience", "avoid")
CREATOR_MARKS = ("keep", "skip", "hide")
STATUSES = ("open", "kept", "retired")

MODEL_STAGE_KEY = "record_model_stage"
COST_CEILING_KEY = "record_cost_ceiling_usd"
COST_CEILING_DEFAULT = 0.10
COST_CEILING_MAX = 5.00

TOMORROW = "It takes effect on tomorrow's cards."


class Refused(ValueError):
    """A request the store will not carry out, with the reason to show."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: Any) -> str:
    cleaned = " ".join(str(text or "").split())
    # The studio's own writing rule, applied to what it stores as well.
    cleaned = cleaned.replace(chr(0x2014), ", ").replace(chr(0x2013), "-")
    return cleaned[:MAX_ASK_CHARS]


# ---------------------------------------------------------------------------
# Asks
# ---------------------------------------------------------------------------

def add_ask(text: Any, source: str, field: Optional[str] = None, origin_ref: Optional[str] = None) -> Dict[str, Any]:
    """Records an ask the creator made. Refused for an empty text or a source no creator act is."""
    if source not in CREATOR_SOURCES:
        raise Refused("An ask comes from Setup, the ask box, a ticked Composer instruction or More of this.")
    if field is not None and field not in SETUP_FIELDS:
        raise Refused(f"A Setup field is one of {', '.join(SETUP_FIELDS)}.")
    cleaned = _clean(text)
    if not cleaned:
        raise Refused("There is nothing to remember: the ask is empty.")
    now = _now()
    conn = get_db()
    try:
        with conn:
            same = conn.execute("SELECT id FROM asks WHERE text = ? AND status != 'retired' AND hidden_at IS NULL",
                                (cleaned,)).fetchone()
            if same:
                conn.execute("UPDATE asks SET updated_at = ? WHERE id = ?", (now, same[0]))
                ask_id = same[0]
            else:
                ask_id = conn.execute(
                    "INSERT INTO asks (text, source, field, origin_ref, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 'open', ?, ?)", (cleaned, source, field, origin_ref, now, now)).lastrowid
        return {"status": "remembered", "id": ask_id, "text": cleaned, "message": TOMORROW}
    finally:
        conn.close()


def set_setup_field(field: str, text: Any) -> Dict[str, Any]:
    """The Setup step's field: one current value each, and an empty one retires it."""
    if field not in SETUP_FIELDS:
        raise Refused(f"A Setup field is one of {', '.join(SETUP_FIELDS)}.")
    cleaned = _clean(text)
    now = _now()
    conn = get_db()
    try:
        with conn:
            current = conn.execute("SELECT id FROM asks WHERE source = 'setup' AND field = ? AND status != 'retired'",
                                   (field,)).fetchone()
            if not cleaned:
                if current:
                    conn.execute("UPDATE asks SET status = 'retired', updated_at = ? WHERE id = ?", (now, current[0]))
                return {"status": "cleared", "field": field}
            if current:
                conn.execute("UPDATE asks SET text = ?, updated_at = ? WHERE id = ?", (cleaned, now, current[0]))
                ask_id = current[0]
            else:
                ask_id = conn.execute(
                    "INSERT INTO asks (text, source, field, status, created_at, updated_at) "
                    "VALUES (?, 'setup', ?, 'open', ?, ?)", (cleaned, field, now, now)).lastrowid
        return {"status": "remembered", "id": ask_id, "field": field, "text": cleaned, "message": TOMORROW}
    finally:
        conn.close()


def setup_fields() -> Dict[str, Optional[str]]:
    conn = get_db()
    try:
        rows = conn.execute("SELECT field, text FROM asks WHERE source = 'setup' AND status != 'retired' "
                            "ORDER BY updated_at").fetchall()
    finally:
        conn.close()
    out: Dict[str, Optional[str]] = {field: None for field in SETUP_FIELDS}
    for row in rows:
        out[row["field"]] = row["text"]
    return out


def list_asks() -> List[Dict[str, Any]]:
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT id, text, source, field, status, created_at, updated_at, last_used_at FROM asks "
            "WHERE hidden_at IS NULL ORDER BY CASE status WHEN 'retired' THEN 1 ELSE 0 END, updated_at DESC")]
    finally:
        conn.close()


def update_ask(ask_id: int, text: Any = None, status: Optional[str] = None) -> Dict[str, Any]:
    if status is not None and status not in STATUSES:
        raise Refused(f"An ask is {', '.join(STATUSES)}.")
    conn = get_db()
    try:
        row = conn.execute("SELECT id FROM asks WHERE id = ?", (ask_id,)).fetchone()
        if not row:
            raise Refused("There is no such ask.")
        with conn:
            if text is not None:
                cleaned = _clean(text)
                if not cleaned:
                    raise Refused("An ask cannot be empty. Retire it instead.")
                conn.execute("UPDATE asks SET text = ?, updated_at = ? WHERE id = ?", (cleaned, _now(), ask_id))
            if status is not None:
                conn.execute("UPDATE asks SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), ask_id))
        return {"status": "updated", "id": ask_id, "message": TOMORROW}
    finally:
        conn.close()


def remove_ask(ask_id: int) -> Dict[str, Any]:
    """The creator's own words, so they can remove them for good."""
    conn = get_db()
    try:
        with conn:
            gone = conn.execute("DELETE FROM asks WHERE id = ?", (ask_id,)).rowcount
        if not gone:
            raise Refused("There is no such ask.")
        return {"status": "removed", "id": ask_id}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------

def _card(conn, day: str, card_id: str) -> Dict[str, Any]:
    row = conn.execute("SELECT * FROM daily_view WHERE day = ? AND card_id = ?", (day, card_id)).fetchone()
    if not row:
        raise Refused("There is no such card on that day.")
    card = dict(row)
    card["payload"] = json.loads(card.pop("payload_json") or "{}")
    card["provenance"] = json.loads(card.pop("provenance_json") or "{}")
    return card


def _valid_day(day: Any) -> str:
    try:
        return date.fromisoformat(str(day)).isoformat()
    except ValueError:
        raise Refused("A day is written as YYYY-MM-DD.") from None


def mark(day: Any, card_id: str, which: str) -> Dict[str, Any]:
    """The creator's keep, skip or hide on a card. Used and posted are the studio's to write."""
    if which not in CREATOR_MARKS:
        raise Refused("A card can be kept, skipped or hidden; used and posted are written by the studio.")
    day = _valid_day(day)
    conn = get_db()
    try:
        card = _card(conn, day, card_id)
        if card["status"] != "shown" and which != "hide":
            raise Refused("Only a card that is shown can be kept or skipped.")
        with conn:
            conn.execute("INSERT OR IGNORE INTO card_marks (day, card_id, mark, at) VALUES (?, ?, ?, ?)",
                         (day, card_id, which, _now()))
            if which == "keep":
                # Keeping and skipping the same card in one day is not two opinions.
                conn.execute("DELETE FROM card_marks WHERE day = ? AND card_id = ? AND mark = 'skip'", (day, card_id))
            elif which == "skip":
                conn.execute("DELETE FROM card_marks WHERE day = ? AND card_id = ? AND mark = 'keep'", (day, card_id))
        return {"status": "marked", "mark": which, "message": f"{mark_said(which, card['kind'])} {TOMORROW}"}
    finally:
        conn.close()


def mark_said(which: str, kind: str) -> str:
    """
    What a mark does to this kind of card, and nothing it does not: keep and
    skip move a drawn card's chance, only set aside a card the record
    chooses, and change nothing about a card that is never shown twice.
    """
    if kind in record_cards.DRAWN_KINDS:
        return {"keep": "Kept. It is on the Kept list now, and it comes back more often.",
                "skip": f"Skipped. It stays away for {record_cards.SKIP_HOLD_DAYS} days, and comes back less often after.",
                "hide": "Hidden. It is not shown again until you choose Unhide all on What the studio knows."}[which]
    if kind in record_cards.CHOSEN_KINDS:
        return {"keep": "Kept. It is on the Kept list now. Your record, not your marks, decides when it comes back.",
                "skip": f"Skipped. It stays away for {record_cards.SKIP_HOLD_DAYS} days, and the next one in line takes "
                        "its place.",
                "hide": "Hidden. The next one in line takes its place until you choose Unhide all on What the studio "
                        "knows."}[which]
    return {"keep": "Kept. It is on the Kept list now.",
            "skip": "Skipped. A card like this is never shown twice in any case.",
            "hide": "Hidden, and left out of Kept. A card like this is never shown twice in any case."}[which]


def unmark(day: Any, card_id: str, which: str) -> Dict[str, Any]:
    if which not in CREATOR_MARKS:
        raise Refused("Only keep, skip and hide can be taken back.")
    day = _valid_day(day)
    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM card_marks WHERE day = ? AND card_id = ? AND mark = ?", (day, card_id, which))
        return {"status": "unmarked", "mark": which, "message": TOMORROW}
    finally:
        conn.close()


def unhide_all() -> Dict[str, Any]:
    conn = get_db()
    try:
        with conn:
            gone = conn.execute("DELETE FROM card_marks WHERE mark = 'hide'").rowcount
        return {"status": "unhidden", "cards": gone, "message": TOMORROW}
    finally:
        conn.close()


def more_of_this(day: Any, card_id: str) -> Dict[str, Any]:
    """
    "More of this" writes the card's topic as an ask: the creator's own
    recurring word the card's text goes under, or, when it goes under none,
    the card's own excerpt. Never the other person's words.
    """
    day = _valid_day(day)
    conn = get_db()
    try:
        card = _card(conn, day, card_id)
        texts = [r[0] for r in conn.execute("SELECT text FROM own_posts WHERE text IS NOT NULL")]
    finally:
        conn.close()
    payload = card["payload"]
    topic = payload.get("topic")
    if not topic:
        vocabulary = evidence_briefing.derive_topic_vocabulary(texts)
        topic = evidence_briefing.classify_post_topic(payload.get("draft_text") or payload.get("excerpt"), vocabulary)
    text = topic if topic and topic != evidence_briefing.OTHER_TOPIC else (payload.get("excerpt") or "")
    if not text:
        raise Refused("This card carries nothing to ask for more of.")
    return add_ask(text, "more_of_this", origin_ref=f"{day}:{card_id}")


def draft_from(day: Any, card_id: str) -> Dict[str, Any]:
    """
    Opens a draft from a card: a Composer draft (a posts row) carrying the
    card's text and which card it came from, and the studio's "used" mark.
    """
    day = _valid_day(day)
    conn = get_db()
    try:
        card = _card(conn, day, card_id)
        if card["status"] != "shown":
            raise Refused("Only a card that is shown can be drafted from.")
        content = (card["payload"].get("draft_text") or card["payload"].get("excerpt") or "").strip()[:5000]
        post_id = f"post_{uuid.uuid4().hex[:10]}"
        with conn:
            conn.execute(
                "INSERT INTO posts (id, content, media_urls, status, tags, origin_card_id, origin_day) "
                "VALUES (?, ?, '[]', 'draft', '[]', ?, ?)", (post_id, content, card_id, day))
            conn.execute("INSERT OR IGNORE INTO card_marks (day, card_id, mark, at, post_id) VALUES (?, ?, 'used', ?, ?)",
                         (day, card_id, _now(), post_id))
            ask_id = card["payload"].get("ask_id")
            if ask_id:
                conn.execute("UPDATE asks SET last_used_at = ? WHERE id = ?", (_now(), ask_id))
        return {"status": "drafted", "id": post_id, "content": content}
    finally:
        conn.close()


def kept() -> List[Dict[str, Any]]:
    """
    The Kept level, which is the Library the earlier report deferred for want
    of a writer: every card the creator kept, newest keep first, read from
    the keep marks. A batch a mark refers to is never pruned, so a kept card
    stays readable.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT m.day AS kept_day, m.at AS kept_at, v.* FROM card_marks m "
            "JOIN daily_view v ON v.day = m.day AND v.card_id = m.card_id "
            "WHERE m.mark = 'keep' ORDER BY m.at DESC").fetchall()
        hidden = {r[0] for r in conn.execute("SELECT card_id FROM card_marks WHERE mark = 'hide'")}
    finally:
        conn.close()
    out, seen = [], set()
    for row in rows:
        item = dict(row)
        if item["card_id"] in seen or item["card_id"] in hidden:
            continue
        seen.add(item["card_id"])
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        item["provenance"] = json.loads(item.pop("provenance_json") or "{}")
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Settings the section's page holds
# ---------------------------------------------------------------------------

def _get_setting(conn, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def settings() -> Dict[str, Any]:
    conn = get_db()
    try:
        keep_days = _get_setting(conn, record_daily.KEEP_DAYS_KEY) or record_daily.KEEP_DAYS_DEFAULT
        model_stage = _get_setting(conn, MODEL_STAGE_KEY) or "on"
        ceiling = _get_setting(conn, COST_CEILING_KEY)
    finally:
        conn.close()
    try:
        ceiling_usd = float(ceiling) if ceiling is not None else COST_CEILING_DEFAULT
    except ValueError:
        ceiling_usd = COST_CEILING_DEFAULT
    return {
        "keep_days": keep_days if keep_days in record_daily.KEEP_DAYS_OPTIONS else record_daily.KEEP_DAYS_DEFAULT,
        "keep_days_options": list(record_daily.KEEP_DAYS_OPTIONS),
        "model_stage": model_stage if model_stage in ("on", "off") else "on",
        "cost_ceiling_usd": ceiling_usd,
        "cost_ceiling_default_usd": COST_CEILING_DEFAULT,
    }


def set_settings(changes: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(changes, dict) or not changes:
        raise Refused("Name a setting to change.")
    writes = []
    for name, value in changes.items():
        if name == "keep_days":
            if str(value) not in record_daily.KEEP_DAYS_OPTIONS:
                raise Refused(f"Batches are kept {', '.join(record_daily.KEEP_DAYS_OPTIONS)} days.")
            writes.append((record_daily.KEEP_DAYS_KEY, str(value)))
        elif name == "model_stage":
            if value not in ("on", "off"):
                raise Refused("The model stage is on or off.")
            writes.append((MODEL_STAGE_KEY, value))
        elif name == "cost_ceiling_usd":
            try:
                ceiling = round(float(value), 2)
            except (TypeError, ValueError):
                raise Refused("The daily ceiling is an amount in US dollars, such as 0.10.") from None
            if not 0 <= ceiling <= COST_CEILING_MAX:
                raise Refused(f"The daily ceiling is between 0 and {COST_CEILING_MAX:.2f} US dollars.")
            writes.append((COST_CEILING_KEY, f"{ceiling:.2f}"))
        else:
            raise Refused(f"There is no setting called {name!r}.")
    conn = get_db()
    try:
        with conn:
            for key, value in writes:
                conn.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                             "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                             (key, value))
    finally:
        conn.close()
    return settings()


# ---------------------------------------------------------------------------
# What the studio knows
# ---------------------------------------------------------------------------

def knows() -> Dict[str, Any]:
    """
    Everything the section has been told and has kept, on one page: the
    asks, the Setup fields, the marks, what the archive brought, and the
    settings. Intelligible and reversible, which is the control readers of
    personalised feeds value most.
    """
    conn = get_db()
    try:
        marks = {r[0]: r[1] for r in conn.execute("SELECT mark, COUNT(*) FROM card_marks GROUP BY mark")}
        hidden = [dict(r) for r in conn.execute(
            "SELECT m.day, m.card_id, m.at, v.kind, v.payload_json FROM card_marks m "
            "LEFT JOIN daily_view v ON v.day = m.day AND v.card_id = m.card_id WHERE m.mark = 'hide' "
            "ORDER BY m.at DESC LIMIT 50")]
        archive = {r[0]: r[1] for r in conn.execute("SELECT kind, COUNT(*) FROM archive_records GROUP BY kind")}
        days = conn.execute("SELECT COUNT(*), MIN(day), MAX(day) FROM daily_run WHERE local_ok = 1").fetchone()
        notes = [dict(r) for r in conn.execute("SELECT month, text, at FROM record_notes ORDER BY month DESC LIMIT 12")]
    finally:
        conn.close()
    for item in hidden:
        payload = json.loads(item.pop("payload_json") or "{}")
        item["title"] = payload.get("title")
        item["excerpt"] = payload.get("excerpt")
    return {
        "asks": list_asks(),
        "setup": setup_fields(),
        "marks": {mark_name: marks.get(mark_name, 0) for mark_name in ("keep", "skip", "hide", "used", "posted")},
        "hidden": hidden,
        "archive": archive,
        "batches": {"days": days[0], "first": days[1], "last": days[2]},
        "prune": record_daily.preview_prune(),
        "notes": notes,
        "settings": settings(),
    }


# ---------------------------------------------------------------------------
# The monthly note
# ---------------------------------------------------------------------------

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def save_note(month: str, text: Any) -> Dict[str, Any]:
    """A note in the creator's own words on whether the cards helped. Kept here, sent nowhere."""
    if not _MONTH.match(str(month or "")):
        raise Refused("A month is written as YYYY-MM.")
    cleaned = " ".join(str(text or "").split())[:MAX_ASK_CHARS]
    conn = get_db()
    try:
        with conn:
            if cleaned:
                conn.execute("INSERT INTO record_notes (month, text, at) VALUES (?, ?, ?) "
                             "ON CONFLICT(month) DO UPDATE SET text = excluded.text, at = excluded.at",
                             (month, cleaned, _now()))
            else:
                conn.execute("DELETE FROM record_notes WHERE month = ?", (month,))
        return {"status": "saved" if cleaned else "removed", "month": month}
    finally:
        conn.close()
