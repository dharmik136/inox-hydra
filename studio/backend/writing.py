"""
Writing for the creator: their preferences, one template, and the studio's guarantees.
=====================================================================================

Phase 3 of the Telegram bot (docs/quality/cycle4/collection-box.md), and the
owner's direction of 2026-10-29: "do not hardcode things as they will be
users preference in AI work". Every choice a writing request makes is one
of the creator's preferences, with a default they can see and change, kept
in one settings row (PREFS_KEY) and read through this module, the same way
in the studio and on the bot:

  length_words  how long a draft is                     Make a post, Combine, Write it up
  tone          how it sounds                           every writing request
  language      what language it is in                  every writing request
  opening       how its first line works                every writing request
  emojis, hashtags, line_breaks                         every writing request
  ending        how a post ends                         Make a post, Combine, Write it up, Command
  avoid         words and phrases never to write        every writing request
  angles        how many opening lines Angles offers    Angles, and the bot's button

The defaults keep what Command said until now (its tone, its paragraphs,
its first-line rule, its ending, its four phrases), so a fresh profile
writes as before; the creator changes them in Brand, under Writing.

The words a prompt carries for each preference are made here (words_for),
and the template each request is built from is here too, filled from them:
nothing a creator would want to change is fixed in a prompt. What is fixed
is the product's guarantee: use only what was sent; never invent a fact, a
person, a figure, a date or a quote; never an em dash. An answer that names
a figure, or a person known to the studio, that is not in what was sent is
refused and said, never repaired.

Every request goes to the creator's own provider through the model gateway,
counted under the "model" egress category.

Strict Invariants:
- Zero em-dashes.
- Nothing about another person is sent: only the creator's own items.
"""

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Set

try:
    from . import changes, collection, voice_pack
    from . import egress as _egress
    from .agno_agentos import model_gateway
    from .agno_agentos.model_gateway import ProviderError
    from .database import get_db
    from .formatters import clean_text_formatting
except ImportError:
    import changes
    import collection
    import egress as _egress
    import voice_pack
    from agno_agentos import model_gateway
    from agno_agentos.model_gateway import ProviderError
    from database import get_db
    from formatters import clean_text_formatting

PREFS_KEY = "writing_preferences"

# Re-Hook's forms, kept here so the opening preference and Re-Hook name the
# same ones.
HOOK_FORMS = ("Pattern Interrupt", "Concrete Metric", "Hard Lesson", "Counter-Intuitive", "Tactical Playbook",
              "Cost of Inaction", "Quiet Title", "Unpopular Truth", "Before vs After", "Razor of Leverage")

# Command's own phrases until now: the default words to avoid.
DEFAULT_AVOID = ("In today's fast-paced world", "game-changer", "delve", "testament")

LENGTHS = (60, 100, 150, 200, 300)
ANGLE_COUNTS = (2, 3, 4, 5)
EMOJIS = {"none": "no emojis", "few": "at most two emojis, only where one helps",
          "as_posts": "emojis as their own posts use them"}
HASHTAGS = {"from_note": "only the hashtags already in what they wrote", "none": "no hashtags",
            "up_to_three": "up to three hashtags that fit"}
LINE_BREAKS = {"short": "short paragraphs of one or two sentences, with generous spacing",
               "one_per_line": "one sentence per line, with space between",
               "as_posts": "paragraphs shaped as their own posts are"}
ENDINGS = {"question_or_takeaway": "an authentic, thoughtful question or takeaway",
           "question": "a question to the reader", "takeaway": "one clear takeaway",
           "none": "no set ending: stop when the point is made"}
TONE_MAX, LANGUAGE_MAX, AVOID_MAX, AVOID_PHRASE_MAX = 160, 40, 12, 60

DEFAULTS: Dict[str, Any] = {
    "length_words": 150,
    "tone": "punchy, high-signal, authentic and authoritative",
    "language": "",
    "opening": "",
    "emojis": "none",
    "hashtags": "from_note",
    "line_breaks": "short",
    "ending": "question_or_takeaway",
    "avoid": list(DEFAULT_AVOID),
    "angles": 3,
    # What ideas may draw on: the morning idea (its item from the collection,
    # its angle from the creator's posts) and the daily cards.
    "sources": ["collection", "posts", "asks"],
}
SOURCES = ("collection", "posts", "asks")
DEFAULT_LANGUAGE_WORDS = "the same language as what they wrote"
DEFAULT_OPENING_WORDS = "a first line that stops the scroll"

# The form a morning idea's angle names, as a request says it.
FORMS = {"question": "open with a question", "story": "open with something that happened to them",
         "short": "open with one short line", "statement": "open with a plain, bold statement"}

# Combine takes this many items at most, so one request stays small.
COMBINE_AT_MOST = 10
# An opening line Angles offers fits before LinkedIn's "see more".
ANGLE_CHARS = 200

NO_PROVIDER = ("No AI provider is set up, so nothing was written. Connect yours on the Composer's Prompt tab, or "
               "use the item as a draft as it is.")


class Refused(ValueError):
    """A request the writer will not make, with the sentence that says why."""


# ---------------------------------------------------------------------------
# The preferences
# ---------------------------------------------------------------------------

def _valid(field: str, value: Any) -> bool:
    if field == "length_words":
        return value in LENGTHS and not isinstance(value, bool)
    if field == "angles":
        return value in ANGLE_COUNTS and not isinstance(value, bool)
    if field == "tone":
        return isinstance(value, str) and 0 < len(value.strip()) <= TONE_MAX
    if field == "language":
        return isinstance(value, str) and len(value.strip()) <= LANGUAGE_MAX
    if field == "opening":
        return value == "" or value in HOOK_FORMS
    if field == "emojis":
        return value in EMOJIS
    if field == "hashtags":
        return value in HASHTAGS
    if field == "line_breaks":
        return value in LINE_BREAKS
    if field == "ending":
        return value in ENDINGS
    if field == "avoid":
        return (isinstance(value, list) and len(value) <= AVOID_MAX
                and all(isinstance(p, str) and 0 < len(p.strip()) <= AVOID_PHRASE_MAX for p in value))
    if field == "sources":
        return isinstance(value, list) and all(v in SOURCES for v in value) and len(set(value)) == len(value)
    return False


def preferences(conn=None) -> Dict[str, Any]:
    """The creator's writing preferences in the open profile, each its default until changed."""
    own = conn is None
    conn = conn or get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (PREFS_KEY,)).fetchone()
    finally:
        if own:
            conn.close()
    try:
        held = json.loads(row[0]) if row and row[0] else {}
    except (TypeError, ValueError):
        held = {}
    held = held if isinstance(held, dict) else {}
    return {field: held[field] if field in held and _valid(field, held[field]) else default
            for field, default in DEFAULTS.items()}


def save(changes_asked: Dict[str, Any]) -> Dict[str, Any]:
    """
    Saves the preferences sent; one not sent keeps its value. A value
    outside its choices refuses the whole change with a sentence, and
    nothing is saved.
    """
    asked = {k: v for k, v in (changes_asked or {}).items() if v is not None}
    for field, value in asked.items():
        if field not in DEFAULTS:
            raise Refused(f"There is no writing preference called {field}.")
        if isinstance(value, str):
            value = value.strip()
            asked[field] = value
        if field == "avoid" and isinstance(value, list):
            asked[field] = [p.strip() for p in value if isinstance(p, str) and p.strip()]
        if field == "sources" and isinstance(value, list):
            asked[field] = [s for s in SOURCES if s in value] if all(v in SOURCES for v in value) else value
        if not _valid(field, asked[field]):
            raise Refused(_REFUSALS.get(field, "That preference was not saved."))
    conn = get_db()
    try:
        merged = {**preferences(conn), **asked}
        with conn:
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                (PREFS_KEY, json.dumps(merged)))
    finally:
        conn.close()
    return described()


_REFUSALS = {
    "length_words": f"A draft is about {', '.join(str(n) for n in LENGTHS)} words long. Nothing was saved.",
    "angles": f"Angles offers {', '.join(str(n) for n in ANGLE_COUNTS)} opening lines. Nothing was saved.",
    "tone": f"Say the tone in a few words, at most {TONE_MAX} characters. Nothing was saved.",
    "language": f"Name the language in at most {LANGUAGE_MAX} characters, or leave it empty. Nothing was saved.",
    "opening": "The opening line is one of Re-Hook's forms, or left to the writer. Nothing was saved.",
    "emojis": "Emojis are none, a few, or as your posts use them. Nothing was saved.",
    "hashtags": "Hashtags are the ones in your note, none, or up to three. Nothing was saved.",
    "line_breaks": "Line breaks are short paragraphs, one sentence a line, or as your posts are. Nothing was saved.",
    "ending": "A post ends with a question or takeaway, a question, a takeaway, or nothing set. Nothing was saved.",
    "avoid": (f"Words to avoid are at most {AVOID_MAX} phrases of up to {AVOID_PHRASE_MAX} characters each. "
              "Nothing was saved."),
    "sources": "Ideas draw on your collection, your posts and your asks, or some of them. Nothing was saved.",
}


def words_for(prefs: Dict[str, Any]) -> Dict[str, str]:
    """The words a prompt carries for each preference: the one place they are made."""
    language = (prefs.get("language") or "").strip()
    opening = prefs.get("opening") or ""
    return {
        "length_words": f"About {prefs['length_words']} words",
        "tone": prefs["tone"],
        "language": f"Write in {language}" if language else f"Write in {DEFAULT_LANGUAGE_WORDS}",
        "opening": f"a {opening} opening line" if opening else DEFAULT_OPENING_WORDS,
        "emojis": EMOJIS[prefs["emojis"]],
        "hashtags": HASHTAGS[prefs["hashtags"]],
        "line_breaks": LINE_BREAKS[prefs["line_breaks"]],
        "ending": ENDINGS[prefs["ending"]],
        "avoid": ", ".join(f"'{phrase}'" for phrase in prefs["avoid"]) or "none",
        "angles": f"{prefs['angles']} different opening lines",
    }


def described() -> Dict[str, Any]:
    """What Brand's Writing view shows: each value, its default, its choices, and the provider every request uses."""
    config = model_gateway.get_current_ai_config()
    return {
        "status": "success",
        "values": preferences(),
        "defaults": DEFAULTS,
        "choices": {
            "length_words": list(LENGTHS), "angles": list(ANGLE_COUNTS), "opening": [""] + list(HOOK_FORMS),
            "emojis": EMOJIS, "hashtags": HASHTAGS, "line_breaks": LINE_BREAKS, "ending": ENDINGS,
            "sources": list(SOURCES),
        },
        # Each choice as the creator reads it, beside the feature it shapes.
        "labels": {
            "emojis": {"none": "No emojis", "few": "A few, only where one helps", "as_posts": "As your own posts use them"},
            "hashtags": {"from_note": "Only those already in what you wrote", "none": "None",
                         "up_to_three": "Up to three that fit"},
            "line_breaks": {"short": "Short paragraphs of one or two sentences", "one_per_line": "One sentence a line",
                            "as_posts": "As your own posts are shaped"},
            "ending": {"question_or_takeaway": "A thoughtful question or takeaway", "question": "A question to the reader",
                       "takeaway": "One clear takeaway", "none": "Nothing set: stop when the point is made"},
            "sources": {"collection": "Your collection", "posts": "Your posts", "asks": "Your asks"},
            "language": "The language of what you wrote",
            "opening": "A first line that stops the scroll",
        },
        "limits": {"tone": TONE_MAX, "language": LANGUAGE_MAX, "avoid": AVOID_MAX, "avoid_phrase": AVOID_PHRASE_MAX},
        "provider": {"configured": bool(config.is_configured),
                     "provider": config.provider if config.is_configured else None,
                     "model": config.model if config.is_configured else None},
    }


# ---------------------------------------------------------------------------
# The template, filled from the preferences
# ---------------------------------------------------------------------------

def command_system(prefs: Optional[Dict[str, Any]] = None) -> str:
    """Command's instruction to the model, from the creator's preferences (its own words until now by default)."""
    w = words_for(prefs or preferences())
    return (
        "You are a writing assistant for a practitioner who posts on LinkedIn.\n"
        f"Your writing style is {w['tone']}.\n"
        "CRITICAL FORMATTING RULES:\n"
        "1. NEVER use em-dashes (\u2014) or en-dashes (\u2013). Use commas, periods, or clean line breaks instead.\n"
        f"2. NO corporate clichés or generic buzzwords (avoid: {w['avoid']}).\n"
        f"3. Format for mobile dwell time: {w['line_breaks']}.\n"
        f"4. Hook rule: {w['opening']}.\n"
        f"5. Conclude with {w['ending']}.\n"
        f"6. {w['language']}. Use {w['emojis']}, and {w['hashtags']}."
    )


def hook_rules(prefs: Optional[Dict[str, Any]] = None) -> str:
    """What Re-Hook's request adds from the preferences: its forms are its catalogue, its words are the creator's."""
    w = words_for(prefs or preferences())
    return (f"- Tone: {w['tone']}.\n- {w['language']}.\n- Emojis: {w['emojis']}.\n"
            f"- Never write these words or phrases: {w['avoid']}.\n")


def _system(prefs: Dict[str, Any]) -> str:
    w = words_for(prefs)
    return "\n".join((
        "You write LinkedIn posts for one creator, in their own voice, from notes they sent themselves.",
        "Use only their notes below and what is said about them and how they write. Never invent a fact, a "
        "person, a company, a result, a figure, a date or a quote: a figure may appear only if their notes give it.",
        "Never use an em dash.",
        f"Tone: {w['tone']}.",
        f"{w['language']}.",
        f"Opening line: {w['opening']}.",
        f"Line breaks: {w['line_breaks']}.",
        f"Emojis: {w['emojis']}. Hashtags: {w['hashtags']}.",
        f"Never write these words or phrases: {w['avoid']}.",
        "Return only the JSON the schema describes.",
    ))


def _notes(items: List[Dict[str, Any]]) -> str:
    if len(items) == 1:
        return "THEIR NOTE:\n" + items[0]["text"].strip()
    return "THEIR NOTES:\n" + "\n".join(f"{n}. {item['text'].strip()}" for n, item in enumerate(items, 1))


def _context() -> str:
    """What is said about the creator beyond their notes: the voice pack, as Command sends it."""
    try:
        return voice_pack.prompt_block()
    except Exception:
        return ""


def _post_request(items: List[Dict[str, Any]], angle: Optional[str], prefs: Dict[str, Any],
                  form: Optional[str] = None) -> str:
    w = words_for(prefs)
    asked = "one post that brings these notes together" if len(items) > 1 else "one post from this note"
    lines = [_notes(items), "", f"WRITE: {asked}. {w['length_words']}. End with {w['ending']}."]
    if angle:
        lines.append(f"Open with this line, or close to it: {angle.strip()}")
    elif form in FORMS:
        lines.append(f"For this post, {FORMS[form]}, as the posts of theirs that did best did.")
    return "\n".join(lines) + _context()


def _angles_request(item: Dict[str, Any], prefs: Dict[str, Any]) -> str:
    w = words_for(prefs)
    return "\n".join((
        _notes([item]), "",
        f"WRITE: {w['angles']} for a post from this note, each a different angle on it, each one line of at most "
        f"{ANGLE_CHARS} characters.",
    )) + _context()


# ---------------------------------------------------------------------------
# What is kept: only what was sent
# ---------------------------------------------------------------------------

_FIGURE = re.compile(r"\d+(?:[.,]\d+)*")
_WORD = re.compile(r"[^\W\d_][\w'’-]*")


def _figures(text: str) -> Set[str]:
    return {re.sub(r"\D", "", found) for found in _FIGURE.findall(text or "")}


def _names_in(text: str, names: Set[str]) -> Set[str]:
    words = [w.casefold() for w in _WORD.findall(text or "")]
    found: Set[str] = set()
    for size in (4, 3, 2):
        for i in range(0, max(0, len(words) - size + 1)):
            joined = " ".join(words[i:i + size])
            if joined in names:
                found.add(joined)
    return found


def check(answer: str, sources: Iterable[str], conn) -> Optional[str]:
    """
    What a written answer carries that was not sent: "figure" (a number in
    no source) or "person's name" (someone the studio knows of, in no
    source), or None. The answer is then refused, never repaired.
    """
    sources = [s for s in sources if s]
    allowed: Set[str] = set()
    for source in sources:
        allowed |= _figures(source)
    if _figures(answer) - allowed:
        return "figure"
    try:
        from . import record_model
    except ImportError:
        import record_model
    names = record_model.known_names(conn)
    if names:
        sent: Set[str] = set()
        for source in sources:
            sent |= _names_in(source, names)
        if _names_in(answer, names) - sent:
            return "person's name"
    return None


def _refusal(what: str) -> str:
    return (f"Nothing was kept: what your provider wrote has a {what} that is not in what you sent. Try again, or "
            "use the item as a draft as it is.")


# ---------------------------------------------------------------------------
# Make a post, Combine, Angles
# ---------------------------------------------------------------------------

def _ask(config, prompt: str, system: str, schema: Dict[str, Any], name: str, max_tokens: int):
    try:
        return model_gateway.execute_structured_completion(config, prompt, system, schema, name,
                                                           max_tokens=max_tokens, temperature=0.6)
    except _egress.EgressRefused as refused:
        raise ProviderError(f"Model requests are off on this machine. {refused}", status_code=503) from None


def _materials(conn, item_ids: Iterable[Any]) -> List[Dict[str, Any]]:
    ids: List[int] = []
    for raw in item_ids:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise Refused("Name the items by their numbers.") from None
        if value not in ids:
            ids.append(value)
    if not ids:
        raise Refused("Choose an item to write from.")
    if len(ids) > COMBINE_AT_MOST:
        raise Refused(f"Combine takes ten items at most ({COMBINE_AT_MOST}), so one request stays small.")
    items = []
    for item_id in ids:
        item = collection.get(conn, item_id)
        if not item:
            raise LookupError("That item is no longer in your collection.")
        items.append(item)
    if not all((item.get("text") or "").strip() for item in items):
        raise Refused("An item with no words of yours has nothing to write from.")
    return items


def make_post(item_ids: Iterable[Any], angle: Optional[str] = None, form: Optional[str] = None) -> Dict[str, Any]:
    """
    Make a post (one item) or Combine (several): a draft written from the
    items' words, as the creator's preferences say, into the Composer. The
    items are used, and what they became is the draft. Returns
    {status: drafted | no_provider | refused, ...}; a provider that fails
    raises ProviderError, which says why in plain words.
    """
    conn = get_db()
    try:
        items = _materials(conn, item_ids)
        config = model_gateway.get_current_ai_config()
        if not config.is_configured:
            return {"status": "no_provider", "said": NO_PROVIDER}
        prefs = preferences(conn)
        schema = {"type": "object", "additionalProperties": False, "required": ["draft"],
                  "properties": {"draft": {"type": "string"}}}
        answer = _ask(config, _post_request(items, angle, prefs, form), _system(prefs), schema, "collection_post",
                      max_tokens=max(400, prefs["length_words"] * 3))
        if answer is None:
            return {"status": "no_provider", "said": NO_PROVIDER}
        data = answer.get("data") if isinstance(answer.get("data"), dict) else {}
        draft = clean_text_formatting(str(data.get("draft") or "")).strip()
        if not draft:
            raise ProviderError(f"{config.provider} ({config.model}) answered, but not with a draft the studio "
                                "could read. Nothing was changed.")
        problem = check(draft, [item["text"] for item in items] + [angle or ""], conn)
        if problem:
            return {"status": "refused", "said": _refusal(problem)}
        tags: List[str] = []
        for item in items:
            tags += [t for t in item.get("tags") or [] if t not in tags]
        with conn:
            post_id = collection.new_draft(conn, draft, tags)
            collection.mark_used(conn, [item["id"] for item in items], post_id)
    finally:
        conn.close()
    changes.publish("collection")
    return {"status": "drafted", "id": post_id, "content": draft, "items": [item["id"] for item in items],
            "provider": config.provider, "model": config.model}


def angles(item_id: Any) -> Dict[str, Any]:
    """
    The creator's number of opening lines for a post from one item, each
    checked as a draft is, kept on the item for the box and the bot. The
    item stays as it was: offering angles makes nothing from it.
    """
    conn = get_db()
    try:
        [item] = _materials(conn, [item_id])
        config = model_gateway.get_current_ai_config()
        if not config.is_configured:
            return {"status": "no_provider", "said": NO_PROVIDER}
        prefs = preferences(conn)
        schema = {"type": "object", "additionalProperties": False, "required": ["angles"],
                  "properties": {"angles": {"type": "array", "items": {"type": "string"}}}}
        answer = _ask(config, _angles_request(item, prefs), _system(prefs), schema, "collection_angles",
                      max_tokens=600)
        if answer is None:
            return {"status": "no_provider", "said": NO_PROVIDER}
        data = answer.get("data") if isinstance(answer.get("data"), dict) else {}
        offered = []
        for line in data.get("angles") or []:
            cleaned = " ".join(clean_text_formatting(str(line or "")).split())
            if cleaned and len(cleaned) <= ANGLE_CHARS and not check(cleaned, [item["text"]], conn):
                offered.append(cleaned)
            if len(offered) == prefs["angles"]:
                break
        if not offered:
            return {"status": "refused", "said": _refusal("figure or a person's name")}
        with conn:
            conn.execute("UPDATE collection_items SET angles = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(offered), collection._now(), item["id"]))
    finally:
        conn.close()
    changes.publish("collection")
    return {"status": "success", "angles": offered, "asked": prefs["angles"], "item": item["id"]}
