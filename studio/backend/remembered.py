"""
Things to remember: what the creator tells the studio about themselves.
=======================================================================

Phase 3 of the Telegram bot (docs/quality/cycle4/collection-box.md, item 3).
Facts about the creator, their audience, their offers and dates, typed in
Brand (Writing) or sent from the phone with /remember. They go with every
writing request as the creator chose (writing.py's "memory" preference:
all of them, only the ones ticked, or none), never with an image prompt,
and a draft the studio writes names which went with it.

A change is published on the "collection" kind, so Brand's list and the
collection box show a /remember from the phone without a reload.

Strict Invariants:
- Zero em-dashes.
- Nothing here leaves the machine; writing.py sends what the creator allows.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from . import changes
    from .database import get_db
except ImportError:
    import changes
    from database import get_db

ABOUT = {"you": "About you", "audience": "Your audience", "offer": "An offer", "date": "A date"}
# How a request names each, beside the fact.
ABOUT_IN_A_REQUEST = {"you": "about them", "audience": "their audience", "offer": "an offer of theirs",
                      "date": "a date"}
# What may start a /remember to say what the fact is about.
PREFIXES = {"me": "you", "you": "you", "about me": "you", "audience": "audience", "offer": "offer", "date": "date"}
TEXT_MAX = 300


class Refused(ValueError):
    """A fact the list will not keep, with the sentence that says why."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def _row(row) -> Dict[str, Any]:
    fact = dict(row)
    fact["in_use"] = bool(fact.get("in_use"))
    fact["about_said"] = ABOUT.get(fact.get("about"), fact.get("about"))
    return fact


def parse_phone(argument: str) -> Tuple[str, str]:
    """A /remember from the phone: (what it is about, the fact). "offer: ..." says what it is about."""
    found = re.match(r"^\s*(about me|me|you|audience|offer|date)\s*:\s*(.*)$", argument or "", re.IGNORECASE | re.DOTALL)
    if found:
        return PREFIXES[found.group(1).lower()], found.group(2)
    return "you", argument or ""


def add(text: Any, about: str = "you", source: str = "studio", origin_ref: Optional[str] = None) -> Dict[str, Any]:
    """Keeps one fact; the same words again are kept once. An empty, too long or unknown kind is refused."""
    cleaned = _clean(text)
    if not cleaned:
        raise Refused("Say what to remember, in a sentence.")
    if len(cleaned) > TEXT_MAX:
        raise Refused(f"A thing to remember is at most {TEXT_MAX} characters. Say it shorter, or as two.")
    if about not in ABOUT:
        raise Refused("A thing to remember is about you, your audience, an offer or a date.")
    if source not in ("studio", "telegram"):
        raise Refused("A thing to remember comes from the studio or your bot.")
    conn = get_db()
    try:
        held = conn.execute("SELECT * FROM remembered WHERE text = ? OR (origin_ref IS NOT NULL AND origin_ref = ?)",
                            (cleaned, origin_ref)).fetchone()
        if held:
            return _row(held)
        now = _now()
        with conn:
            fact_id = conn.execute(
                "INSERT INTO remembered (text, about, in_use, source, origin_ref, created_at, updated_at) "
                "VALUES (?, ?, 1, ?, ?, ?, ?)", (cleaned, about, source, origin_ref, now, now)).lastrowid
        fact = _row(conn.execute("SELECT * FROM remembered WHERE id = ?", (fact_id,)).fetchone())
    finally:
        conn.close()
    changes.publish("collection")
    return fact


def listing() -> List[Dict[str, Any]]:
    conn = get_db()
    try:
        return [_row(r) for r in conn.execute("SELECT * FROM remembered ORDER BY id")]
    finally:
        conn.close()


def update(fact_id: int, text: Any = None, about: Optional[str] = None, in_use: Optional[bool] = None) -> Dict[str, Any]:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM remembered WHERE id = ?", (int(fact_id),)).fetchone()
        if not row:
            raise LookupError("That thing to remember is no longer kept.")
        fact = dict(row)
        if text is not None:
            cleaned = _clean(text)
            if not cleaned or len(cleaned) > TEXT_MAX:
                raise Refused(f"A thing to remember is a sentence of at most {TEXT_MAX} characters.")
            fact["text"] = cleaned
        if about is not None:
            if about not in ABOUT:
                raise Refused("A thing to remember is about you, your audience, an offer or a date.")
            fact["about"] = about
        if in_use is not None:
            fact["in_use"] = 1 if in_use else 0
        with conn:
            conn.execute("UPDATE remembered SET text = ?, about = ?, in_use = ?, updated_at = ? WHERE id = ?",
                         (fact["text"], fact["about"], fact["in_use"], _now(), int(fact_id)))
        changed = _row(conn.execute("SELECT * FROM remembered WHERE id = ?", (int(fact_id),)).fetchone())
    finally:
        conn.close()
    changes.publish("collection")
    return changed


def remove(fact_id: Any) -> bool:
    try:
        fact_id = int(fact_id)
    except (TypeError, ValueError):
        return False
    conn = get_db()
    try:
        with conn:
            gone = bool(conn.execute("DELETE FROM remembered WHERE id = ?", (fact_id,)).rowcount)
    finally:
        conn.close()
    if gone:
        changes.publish("collection")
    return gone


def for_writing(conn, mode: str) -> List[Dict[str, Any]]:
    """The facts a writing request carries: all of them, only those ticked (chosen), or none (off)."""
    if mode == "off":
        return []
    where = " WHERE in_use = 1" if mode == "chosen" else ""
    return [_row(r) for r in conn.execute(f"SELECT * FROM remembered{where} ORDER BY id")]


def block(facts: Iterable[Dict[str, Any]]) -> str:
    """The facts as a request carries them, or "" when none go."""
    lines = [f"- {ABOUT_IN_A_REQUEST.get(f['about'], 'about them')}: {f['text']}" for f in facts]
    if not lines:
        return ""
    return ("\n\nTHINGS THEY ASKED YOU TO REMEMBER (use one only where it fits; never contradict one):\n"
            + "\n".join(lines))


def mark_used(conn, fact_ids: Iterable[int]) -> None:
    """These facts went with a writing request now."""
    now = _now()
    for fact_id in fact_ids:
        conn.execute("UPDATE remembered SET used_count = used_count + 1, last_used_at = ? WHERE id = ?",
                     (now, int(fact_id)))


def forget_matching(words: str) -> Tuple[str, int]:
    """
    /forget from the phone: removes the one fact whose words hold all of
    these, and never guesses. Returns ("forgot", 1), ("forget_many", n) or
    ("forget_none", 0), keys of telegram_bot.SENTENCES.
    """
    asked = [w for w in re.findall(r"\w+", (words or "").lower()) if w]
    conn = get_db()
    try:
        found = [r for r in conn.execute("SELECT id, text FROM remembered")
                 if asked and all(w in set(re.findall(r"\w+", r["text"].lower())) for w in asked)]
        if len(found) == 1:
            with conn:
                conn.execute("DELETE FROM remembered WHERE id = ?", (found[0]["id"],))
    finally:
        conn.close()
    if len(found) == 1:
        changes.publish("collection")
        return "forgot", 1
    return ("forget_many", len(found)) if found else ("forget_none", 0)


def forget(conn) -> None:
    """Delete everything: every thing to remember."""
    conn.execute("DELETE FROM remembered")
