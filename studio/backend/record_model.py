"""
From your record, stage 2: the creator's own model, once a day, when they open the section.
===========================================================================================
"Using the AI to find good posts" cannot mean browsing: the gateway is text
in, text out, with no tool use and no search. What it can honestly do is
find ideas inside the creator's own record. So once a day, the first time
the creator opens From your record (decision 7), and only with their own
key, the studio sends a redacted set of their own rows and asks for at most
three ideas, in a shape it can check:

  sent      the first 300 characters of up to ten of their own posts with
            each post's id, its topic label and the studio's own word for
            how it did (above, about or below their usual, or not
            measured); the asks they kept; who they write for and what to
            avoid, if they said; their habits said in words; who they are
            from the profile they confirmed. Nothing else: never a figure,
            another person's name or words, a connection, a score. Inside
            their own text an @mention, an address, a phone number, a link
            and the name of anybody the studio has a record of are replaced
            before it leaves. An allowlist, as support.py's bundle is: a
            field not named here is not sent.
  asked     a JSON Schema (model_gateway's structured outputs) allowing only
            ids from the set sent, an angle from a closed list and short
            phrases
  checked   every idea is dropped, not repaired, when it cites an id that
            was not sent or a row that is gone, quotes words that are not in
            the post it names, carries a digit or the words "times" or
            "percent" (no number from a model reaches the screen), names a
            person the studio has a record of, or runs past 160 characters;
            the count of what was dropped is on the day's row and the screen
  limits    one call a day (two if the first failed), 1,200 tokens out, and
            the creator's daily ceiling in US dollars (10 cents unless they
            change it), estimated before the call from the dated price table
            below; with no price for the provider the call is not made
  tier      the Creator tier once BETA_OPEN closes (licensing "ai")
  egress    the existing `model` category, at the moment the creator opens
            the section: the policy's "only at the moment you use the
            feature that needs it" stays true

Strict Invariants:
- Zero em-dashes.
- Never called by the daily job or a screen load: only run_on_open, which
  only POST /api/v1/record/model calls.
- Nothing invented: no figure from the model, and every cited row found.
"""

import hashlib
import json
import logging
import re
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit

try:
    from . import egress, evidence_briefing, licensing, record_cards, record_daily, record_store, results, voice_pack
    from .agno_agentos import model_gateway
    from .agno_agentos.scar_tissue import scrub_em_dashes
    from .database import get_db
except ImportError:  # top-level import mode
    import egress
    import evidence_briefing
    import licensing
    import record_cards
    import record_daily
    import record_store
    import results
    import voice_pack
    from agno_agentos import model_gateway
    from agno_agentos.scar_tissue import scrub_em_dashes
    from database import get_db

logger = logging.getLogger("studio.record")

SCHEMA_VERSION = 1
SCHEMA_NAME = "record_ideas"
MAX_CALLS_PER_DAY = 2
MAX_OUTPUT_TOKENS = 1200
MAX_IDEAS = 3
POSTS_SENT = 10
RANKED_SENT = 7
EXCERPT_CHARS = 300
PHRASE_CHARS = 160
ANGLE_KINDS = ("opener", "topic", "format", "length", "question", "story")
# An assumption, labelled wherever the estimate is shown: about four
# characters a token for English prose.
CHARS_PER_TOKEN = 4

# ---------------------------------------------------------------------------
# Prices, dated
# ---------------------------------------------------------------------------
#
# US dollars per million tokens, (input, output), as each provider's own
# pricing page listed them on PRICE_DATE (ideas report, Appendix A and the
# methods note). Prices change; the screen says which date they are from.
# A model of a listed provider that is not in its table is estimated at that
# provider's dearest listed price, and says so. A provider with no table is
# not called: the studio could not keep the call under the ceiling.
PRICE_DATE = "2026-10-26"
PRICES: Dict[str, Dict[str, Tuple[float, float]]] = {
    "anthropic": {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00),
                  "claude-opus-5-5": (4.00, 20.00)},
    "openai": {"gpt-5-nano": (0.05, 0.40), "gpt-5-mini": (0.25, 2.00), "gpt-4.1-mini": (0.40, 1.60),
               "gpt-5": (1.25, 10.00), "gpt-5.4": (2.50, 15.00), "gpt-5.4-mini": (0.75, 4.50),
               "gpt-5.4-nano": (0.20, 1.25)},
    "gemini": {"gemini-2.5-flash-lite": (0.10, 0.40), "gemini-2.5-flash": (0.30, 2.50),
               "gemini-3.1-flash-lite": (0.25, 1.50), "gemini-3-flash-preview": (0.50, 3.00)},
}
PROVIDER_WORDS = {"anthropic": "Anthropic", "openai": "OpenAI", "gemini": "Google", "groq": "Groq",
                  "ollama": "Ollama", "custom_openai": "your endpoint"}

# What each provider says it does with what it is sent, as read on PRICE_DATE.
# Said beside the switch, so the creator reads it before the first call.
STATEMENTS = {
    "openai": ("OpenAI says it does not use what is sent to its API to train its models unless you opt in, and keeps "
               "abuse-monitoring logs for up to 30 days (its own page, as read on 2026-10-26)."),
    "anthropic": ("Anthropic says it does not keep the content of a request by default, except for the models it lists "
                  "as covered, which it keeps for 30 days, and never trains on it without your permission (its own "
                  "page, as read on 2026-10-26)."),
    "gemini": ("Google says it does not use what is sent with a paid Gemini key to improve its products and stores it "
               "for 30 days, while the free tier's requests may be used (its own terms, as read on 2026-10-26)."),
    "groq": "Groq's own terms govern what it keeps. The studio has not read them.",
    "local": ("A model on this computer: nothing leaves it, though the request is still counted under model in the "
              "ledger."),
    "custom_openai": "Your endpoint's own terms govern what it keeps.",
}

_running = threading.Lock()
_DIGIT = re.compile(r"\d|[%¼-¾⅐-⅟²³¹⁰-⁹₀-₉]")
_NUMBER_WORDS = re.compile(r"\b(times|percent|per cent|percentage)\b", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def has_number(text: Any) -> bool:
    """A digit in any script, a percent sign, a fraction or a power, or the words "times" and "percent"."""
    value = str(text or "")
    return bool(_DIGIT.search(value) or _NUMBER_WORDS.search(value))


# ---------------------------------------------------------------------------
# What may leave: the allowlist and the redactor
# ---------------------------------------------------------------------------

_MENTION = re.compile(r"@[\w.'-]+(?:\s[A-Z][\w'-]+)?")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
_LINK = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_WORD = re.compile(r"[^\W\d_][\w'’-]*")


def known_names(conn) -> Set[str]:
    """
    The full names of everybody the studio has a record of: people who
    engaged, connections, and the authors of posts the creator engaged with.
    Two or three words each, lower case. Never sent; used to keep them out.
    """
    names: Set[str] = set()

    def add(value: Any) -> None:
        words = _WORD.findall(str(value or "").casefold())
        if 2 <= len(words) <= 4:
            names.add(" ".join(words))

    for sql in ("SELECT name, full_name FROM leads",
                "SELECT first_name || ' ' || last_name, NULL FROM connections",
                "SELECT DISTINCT target_author, NULL FROM outbound_engagements WHERE target_author IS NOT NULL"):
        try:
            for first, second in conn.execute(sql):
                add(first)
                add(second)
        except Exception:
            continue
    return names


def scrub(text: Any, names: Set[str]) -> str:
    """The creator's own text with every person, address, number to call and link replaced."""
    value = str(text or "")
    value = _EMAIL.sub("[email]", value)
    value = _LINK.sub("[link]", value)
    value = _MENTION.sub("@[person]", value)
    value = _PHONE.sub("[phone]", value)
    if names:
        spans = [(m.start(), m.end(), m.group(0).casefold()) for m in _WORD.finditer(value)]
        cut: List[Tuple[int, int]] = []
        i = 0
        while i < len(spans):
            hit = None
            for size in (4, 3, 2):
                window = spans[i:i + size]
                if len(window) == size and " ".join(w[2] for w in window) in names:
                    hit = (window[0][0], window[-1][1], size)
                    break
            if hit:
                cut.append(hit[:2])
                i += hit[2]
            else:
                i += 1
        for start, end in reversed(cut):
            value = value[:start] + "[person]" + value[end:]
    return value


def _names_in(text: str, names: Set[str]) -> bool:
    return scrub(text, names) != text and "[person]" in scrub(text, names)


def _bucket(ratio: Optional[float]) -> str:
    """How a post did, as a word: results' own notable band, never the figure."""
    if ratio is None:
        return "not measured"
    if ratio >= results.NOTABLE_HIGH:
        return "above your usual"
    if ratio <= results.NOTABLE_LOW:
        return "below your usual"
    return "about your usual"


def build_bundle(conn) -> Dict[str, Any]:
    """
    What would be sent, field by field from the allowlist, and the full text
    of each post sent (kept here, never sent) so a quote can be checked.
    """
    names = known_names(conn)
    posts = {r["activity_urn"]: dict(r) for r in conn.execute(
        "SELECT activity_urn, text, published_at FROM own_posts WHERE text IS NOT NULL AND TRIM(text) != ''")}
    ranking = results.ranking(conn)
    chosen: List[str] = [urn for urn in ranking["order"] if urn in posts][:RANKED_SENT]
    recent = sorted(posts.values(), key=lambda p: p.get("published_at") or "", reverse=True)
    for post in recent:
        if len(chosen) >= POSTS_SENT:
            break
        if post["activity_urn"] not in chosen:
            chosen.append(post["activity_urn"])
    vocabulary = evidence_briefing.derive_topic_vocabulary([p["text"] for p in posts.values()])
    figures = ranking["figures"]
    sent_posts = []
    for urn in chosen:
        text = posts[urn]["text"]
        ratio = results.against_usual(figures.get(urn), ranking["usual"]).get(results.RANKED_METRIC) \
            if urn in ranking["order"] else None
        sent_posts.append({
            "id": urn,
            "topic": evidence_briefing.classify_post_topic(text, vocabulary),
            "did": _bucket(ratio),
            "text": scrub(" ".join(text.split())[:EXCERPT_CHARS], names),
        })
    asks, audience, avoid = [], [], []
    for row in conn.execute("SELECT id, text, field FROM asks WHERE status != 'retired' AND hidden_at IS NULL "
                            "ORDER BY updated_at DESC LIMIT 12"):
        cleaned = scrub(row["text"], names)
        if row["field"] == "audience":
            audience.append(cleaned)
        elif row["field"] == "avoid":
            avoid.append(cleaned)
        else:
            asks.append({"id": f"ask-{row['id']}", "text": cleaned})
    texts = [p["text"] for p in posts.values()]
    return {
        "posts": sent_posts,
        "asks": asks,
        "audience": audience,
        "avoid": avoid,
        "habits": voice_pack.habits_in_words(texts),
        "who": [scrub(line, names) for line in voice_pack.who_lines()],
        "_full_text": {urn: posts[urn]["text"] for urn in chosen},
        "_names": names,
    }


SYSTEM_PROMPT = (
    "You suggest LinkedIn post ideas for one creator, built only from their own posts and the asks they made, "
    "which are listed below with ids.\n"
    "Rules you must follow on every response:\n"
    "- Cite only ids that appear below. Suggest at most three ideas.\n"
    "- Each hook, angle and why is one short phrase of at most 160 characters.\n"
    "- Never write a number, a percentage, a count or a statistic, in digits or in words.\n"
    "- Never name a person, a client or a company the posts do not name.\n"
    "- quote is a few words copied exactly from the post the idea builds on, or empty.\n"
    "- Never suggest anything listed under NEVER SUGGEST. Never use an em dash.\n"
    "Return only the JSON the schema describes."
)


def render_prompt(bundle: Dict[str, Any]) -> str:
    lines = ["THEIR POSTS (id | topic | how it did against their usual | the first words):"]
    for post in bundle["posts"]:
        lines.append(f"- {post['id']} | {post['topic']} | {post['did']} | {post['text']}")
    if bundle["asks"]:
        lines.append("")
        lines.append("WHAT THEY ASKED TO WRITE ABOUT (id | ask):")
        lines.extend(f"- {ask['id']} | {ask['text']}" for ask in bundle["asks"])
    if bundle["audience"]:
        lines.extend(["", "WHO THEY WRITE FOR: " + "; ".join(bundle["audience"])])
    if bundle["avoid"]:
        lines.extend(["", "NEVER SUGGEST: " + "; ".join(bundle["avoid"])])
    if bundle["habits"]:
        lines.extend(["", "HOW THEY WRITE: " + "; ".join(bundle["habits"])])
    if bundle["who"]:
        lines.extend(["", "WHO THEY ARE:"] + [f"- {line}" for line in bundle["who"]])
    lines.extend(["", "OUTPUT: up to three ideas, each built on one or more of their posts and, where it fits, one "
                      "of their asks; ask is \"none\" when no ask fits."])
    return scrub_em_dashes("\n".join(lines))


def schema_for(bundle: Dict[str, Any]) -> Dict[str, Any]:
    post_ids = [post["id"] for post in bundle["posts"]]
    ask_ids = ["none"] + [ask["id"] for ask in bundle["asks"]]
    phrase = {"type": "string"}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["ideas"],
        "properties": {
            "ideas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["based_on", "ask", "angle_kind", "hook", "angle", "why", "quote"],
                    "properties": {
                        "based_on": {"type": "array", "items": {"type": "string", "enum": post_ids}},
                        "ask": {"type": "string", "enum": ask_ids},
                        "angle_kind": {"type": "string", "enum": list(ANGLE_KINDS)},
                        "hook": phrase,
                        "angle": phrase,
                        "why": phrase,
                        "quote": phrase,
                    },
                },
            },
        },
    }


def preview() -> Dict[str, Any]:
    """Exactly what the next call would send, for the creator to read. Sends nothing."""
    conn = get_db()
    try:
        bundle = build_bundle(conn)
    finally:
        conn.close()
    config = model_gateway.get_current_ai_config()
    return {"provider": config.provider, "model": config.model, "system": SYSTEM_PROMPT, "prompt": render_prompt(bundle),
            "posts": len(bundle["posts"]), "asks": len(bundle["asks"])}


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

def _local(config) -> bool:
    return config.provider in ("ollama", "custom_openai") and egress.on_this_machine(config.base_url or "")


def price_of(config) -> Tuple[Optional[Tuple[float, float]], str]:
    """(input, output) dollars per million tokens and the sentence that says where it came from."""
    if _local(config):
        return (0.0, 0.0), "no cost: a model on this computer"
    table = PRICES.get(config.provider)
    if not table:
        return None, (f"no price is listed for {PROVIDER_WORDS.get(config.provider, config.provider)}, so the studio "
                      "cannot keep the call under your daily ceiling")
    if config.model in table:
        return table[config.model], f"estimated from {PROVIDER_WORDS[config.provider]} prices of {PRICE_DATE}"
    dearest = max(table.values(), key=lambda pair: pair[1])
    return dearest, (f"estimated at the dearest {PROVIDER_WORDS[config.provider]} price listed on {PRICE_DATE}, "
                     f"since {config.model} is not in the studio's price table")


def estimate(price: Tuple[float, float], tokens_in: int, tokens_out: int) -> float:
    return round(tokens_in * price[0] / 1e6 + tokens_out * price[1] / 1e6, 6)


# ---------------------------------------------------------------------------
# State, for the screen
# ---------------------------------------------------------------------------

def _statement(config) -> Optional[str]:
    if config.provider == "local_deterministic":
        return None
    if _local(config):
        return STATEMENTS["local"]
    return STATEMENTS.get(config.provider)


def state(day: Optional[date] = None) -> Dict[str, Any]:
    """What the model stage can do today, and the sentence that says why not when it cannot. A read."""
    day = day or record_daily.local_today()
    config = model_gateway.get_current_ai_config()
    settings = record_store.settings()
    conn = get_db()
    try:
        run = conn.execute("SELECT * FROM daily_run WHERE day = ?", (day.isoformat(),)).fetchone()
        run = dict(run) if run else None
        carried_idea = bool(conn.execute(
            "SELECT 1 FROM daily_view WHERE day = ? AND kind = 'idea' AND status = 'shown'", (day.isoformat(),)).fetchone())
    finally:
        conn.close()
    configured = config.is_configured
    allowed = licensing.allows("ai")
    status = (run or {}).get("model_status") or ("no_batch" if not run else "not_run")
    calls = (run or {}).get("model_calls") or 0
    reason = None
    if not configured:
        reason = "No AI provider is connected. Connect your own in the Composer's Prompt tab to add an idea a day."
    elif not allowed:
        reason = "Your own model's ideas are part of the Creator licence."
    elif settings["model_stage"] != "on":
        reason = "The model stage is off. Nothing is sent."
    elif not run or not run.get("local_ok"):
        reason = "Today's cards have not been built yet, so there is nothing to ask the model about."
    elif run.get("carried_from") and carried_idea and status == "not_run":
        reason = "Nothing new since yesterday, so yesterday's idea stands and the model is not asked again."
    should_run = (reason is None and (status == "not_run" or (status.startswith("failed") and calls < MAX_CALLS_PER_DAY)))
    if reason is None and not should_run:
        reason = {"running": "Your model is answering now.", "ran": "Your model answered today."}.get(
            status, (run or {}).get("model_note") or status)
    price, basis = price_of(config) if configured else (None, None)
    return {
        "configured": configured,
        "allowed": allowed,
        "stage": settings["model_stage"],
        "status": status,
        "should_run": should_run,
        "provider": config.provider if configured else None,
        "provider_label": PROVIDER_WORDS.get(config.provider) if configured else None,
        "model": config.model if configured else None,
        "statement": _statement(config),
        "ceiling_usd": settings["cost_ceiling_usd"],
        "spent_today_usd": (run or {}).get("estimated_cost_usd"),
        "price_date": PRICE_DATE,
        "price_basis": basis,
        "priced": price is not None,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# One run: on the creator's first open of the day
# ---------------------------------------------------------------------------

def run_on_open(day: Optional[date] = None, wait: bool = False) -> Dict[str, Any]:
    """
    Starts today's model call when the creator opens the section and it has
    not run yet, on its own thread, so the local cards are on screen at once
    and the model's idea arrives into today's row. Called by
    POST /api/v1/record/model and nothing else.
    """
    day = day or record_daily.local_today()
    current = state(day)
    if not current["should_run"]:
        return {"status": "not_run", "reason": current["reason"], "model": current}
    if not _running.acquire(blocking=False):
        return {"status": "running", "reason": "Your model is answering now."}
    try:
        conn = get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT model_status FROM daily_run WHERE day = ?", (day.isoformat(),)).fetchone()
            if not row or row[0] == "running" or row[0] == "ran":
                conn.execute("ROLLBACK")
                _running.release()
                return {"status": "not_run", "reason": "Your model has already been asked today."}
            conn.execute("UPDATE daily_run SET model_status = 'running', model_note = NULL WHERE day = ?",
                         (day.isoformat(),))
            conn.execute("COMMIT")
        finally:
            conn.close()
    except BaseException:
        _running.release()
        raise

    def work():
        try:
            _run(day)
        except Exception:
            logger.warning("From your record: the model stage failed.", exc_info=True)
            _finish(day, status="failed: the studio could not finish the call", note=None)
        finally:
            _running.release()

    if wait:
        work()
        return {"status": "done", "model": state(day)}
    try:
        threading.Thread(target=work, name="inox-record-model", daemon=True).start()
    except BaseException:
        _running.release()
        _finish(day, status="failed: the studio could not start the call", note=None)
        raise
    return {"status": "running", "reason": "Your model is answering now."}


def _finish(day: date, status: str, note: Optional[str], calls: int = 0, tokens_in: int = 0, tokens_out: int = 0,
            cost: float = 0.0, dropped: int = 0, cards: Optional[List[Dict[str, Any]]] = None) -> None:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE daily_run SET model_status = ?, model_note = ?, model_calls = model_calls + ?, "
                "model_tokens_in = model_tokens_in + ?, model_tokens_out = model_tokens_out + ?, "
                "estimated_cost_usd = COALESCE(estimated_cost_usd, 0) + ?, price_date = ?, "
                "dropped_cards = dropped_cards + ? WHERE day = ?",
                (status, note, calls, tokens_in, tokens_out, cost, PRICE_DATE, dropped, day.isoformat()))
            if cards is not None:
                shown = [c for c in cards if c["status"] == "shown"]
                if shown:
                    conn.execute("UPDATE daily_view SET status = 'replaced' WHERE day = ? AND slot = ? "
                                 "AND status IN ('shown', 'abstained')", (day.isoformat(), record_daily.OPEN_SLOT))
                elif any(c["status"] == "abstained" for c in cards):
                    conn.execute("UPDATE daily_view SET status = 'replaced' WHERE day = ? AND slot = ? "
                                 "AND status = 'abstained'", (day.isoformat(), record_daily.OPEN_SLOT))
                record_cards.store_batch(conn, day, {"cards": cards}, replace=False)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def _run(day: date) -> None:
    config = model_gateway.get_current_ai_config()
    settings = record_store.settings()
    conn = get_db()
    try:
        bundle = build_bundle(conn)
        run = dict(conn.execute("SELECT * FROM daily_run WHERE day = ?", (day.isoformat(),)).fetchone())
    finally:
        conn.close()
    if not bundle["posts"]:
        _finish(day, "off", "No posts of yours with text yet, so there is nothing to ask the model about.")
        return
    prompt = render_prompt(bundle)
    schema = schema_for(bundle)
    price, basis = price_of(config)
    if price is None:
        _finish(day, "capped", f"Not sent: {basis}.")
        return
    tokens_in_estimate = (len(SYSTEM_PROMPT) + len(prompt) + len(json.dumps(schema))) // CHARS_PER_TOKEN
    bound = estimate(price, tokens_in_estimate, MAX_OUTPUT_TOKENS)
    spent = run.get("estimated_cost_usd") or 0.0
    if spent + bound > settings["cost_ceiling_usd"]:
        _finish(day, "capped", f"Not sent: the call could cost up to ${bound:.4f} ({basis}), which is over what is left "
                               f"of your daily ceiling of ${settings['cost_ceiling_usd']:.2f}.")
        return
    call_id = uuid.uuid4().hex
    try:
        answer = model_gateway.execute_structured_completion(config, prompt, SYSTEM_PROMPT, schema, SCHEMA_NAME,
                                                             max_tokens=MAX_OUTPUT_TOKENS, temperature=0.4)
    except egress.EgressRefused as refused:
        _finish(day, "failed: refused", "Not sent: " + egress.redact(str(refused)))
        return
    except model_gateway.ProviderError as failure:
        _finish(day, "failed: provider", "The model did not answer today: " + egress.redact(failure.message), calls=1)
        return
    if answer is None:
        _finish(day, "no_key", "No AI provider is connected.")
        return
    usage = answer["usage"]
    tokens_in = usage.get("input") if usage.get("input") is not None else tokens_in_estimate
    tokens_out = usage.get("output") if usage.get("output") is not None else MAX_OUTPUT_TOKENS
    cost = estimate(price, tokens_in, tokens_out)
    meta = {"provider": config.provider, "model": config.model, "call_id": call_id,
            "prompt_hash": hashlib.sha256((SYSTEM_PROMPT + prompt).encode("utf-8")).hexdigest()[:32],
            "schema_version": SCHEMA_VERSION}
    conn = get_db()
    try:
        cards, dropped, reasons = verify_ideas(conn, answer["data"], bundle, meta, day)
    finally:
        conn.close()
    shown = [c for c in cards if c["status"] == "shown"]
    said = f"{len(cards)} idea{'s' if len(cards) != 1 else ''} returned"
    if dropped:
        said += f"; {dropped} dropped as unverifiable ({', '.join(sorted(set(reasons)))})"
    if not shown:
        cards.append(record_cards._abstained(
            record_daily.OPEN_SLOT, "model", "idea",
            f"Your model answered, but none of its ideas could be checked against your record: {said}. Nothing it "
            "wrote is shown.", "the model stage's checks"))
    _finish(day, "ran", said + ".", calls=1, tokens_in=tokens_in, tokens_out=tokens_out, cost=cost, dropped=dropped,
            cards=cards)


def _normalised(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


def verify_ideas(conn, data: Any, bundle: Dict[str, Any], meta: Dict[str, Any], day: date
                 ) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    """
    Every idea the model returned, as a card: the first that passes every
    check is shown in the open slot, the others kept as spares, and those
    that fail are kept dropped with the reason, never shown and never
    repaired. Returns (cards, how many were dropped, the reasons).
    """
    sent_posts = {post["id"]: post for post in bundle["posts"]}
    sent_asks = {ask["id"]: ask for ask in bundle["asks"]}
    names = bundle["_names"]
    ideas = data.get("ideas") if isinstance(data, dict) else None
    cards: List[Dict[str, Any]] = []
    dropped, reasons = 0, []
    if not isinstance(ideas, list):
        return cards, 0, []
    shown_one = False
    for index, idea in enumerate(ideas[:MAX_IDEAS]):
        reason = None
        fields = {}
        if not isinstance(idea, dict):
            reason = "not the shape asked for"
        else:
            for key in ("hook", "angle", "why", "quote", "ask", "angle_kind"):
                value = idea.get(key)
                fields[key] = value if isinstance(value, str) else None
            based_on = idea.get("based_on") if isinstance(idea.get("based_on"), list) else None
            if None in fields.values() or not based_on or not all(isinstance(b, str) for b in based_on):
                reason = "not the shape asked for"
            elif any(b not in sent_posts for b in based_on):
                reason = "cited a post that was not sent"
            elif fields["ask"] != "none" and fields["ask"] not in sent_asks:
                reason = "cited an ask that was not sent"
            elif fields["angle_kind"] not in ANGLE_KINDS:
                reason = "an angle outside the list"
            elif any(not fields[k].strip() for k in ("hook", "angle", "why")):
                reason = "an empty phrase"
            elif any(len(fields[k]) > PHRASE_CHARS for k in ("hook", "angle", "why", "quote")):
                reason = f"a phrase longer than {PHRASE_CHARS} characters"
            elif any(has_number(fields[k]) for k in ("hook", "angle", "why", "quote")):
                reason = "carried a number"
            elif any(_names_in(fields[k], names) for k in ("hook", "angle", "why", "quote")):
                reason = "named a person"
            elif fields["quote"].strip() and not any(
                    _normalised(fields["quote"]) in _normalised(bundle["_full_text"].get(b, "")) for b in based_on):
                reason = "quoted words that are not in your post"
            else:
                rows = [{"table": "own_posts", "id": b} for b in based_on]
                if fields["ask"] != "none":
                    rows.append({"table": "asks", "id": int(fields["ask"].split("-", 1)[1])})
                if record_cards.missing_rows(conn, rows):
                    reason = "a cited row was not found"
        card_id = f"idea:{day.isoformat()}:{meta['call_id'][:8]}:{index}"
        verification = {"ids_exist": reason not in ("cited a post that was not sent", "cited an ask that was not sent",
                                                    "a cited row was not found"),
                        "excerpt_is_substring": reason != "quoted words that are not in your post",
                        "digits_in_model_text": reason == "carried a number",
                        "dropped_reason": reason}
        if reason:
            dropped += 1
            reasons.append(reason)
            card = record_cards._card(card_id, record_daily.OPEN_SLOT, "model", "idea", "suggested",
                                      "suggested by your own model", {"title": "Idea", "block_label": "Suggested by your model"},
                                      [], status="dropped")
            card["provenance"]["model"] = meta
            card["provenance"]["verification"] = verification
            cards.append(card)
            continue
        based_on = idea["based_on"]
        first = sent_posts[based_on[0]]
        published = conn.execute("SELECT published_at FROM own_posts WHERE activity_urn = ?", (based_on[0],)).fetchone()
        ask = sent_asks.get(fields["ask"])
        ask_row = None
        if ask:
            ask_row = conn.execute("SELECT text, created_at FROM asks WHERE id = ?",
                                   (int(fields["ask"].split("-", 1)[1]),)).fetchone()
        provider_word = PROVIDER_WORDS.get(meta["provider"], meta["provider"])
        because = "Because "
        if ask_row:
            because += f"you asked for “{record_cards._excerpt(ask_row['text'], 80)}” on {record_cards._said_weekday(ask_row['created_at'])}, and "
        because += (f"your post of {record_cards._said_date(published[0] if published else None)} ({first['did']}, "
                    f"topic {first['topic']})")
        if len(based_on) > 1:
            because += f" and {len(based_on) - 1} more of yours"
        because += f" · rule: suggested by your own model from your own rows"
        payload = {
            "title": "Idea",
            "badge": f"suggested by your {provider_word} key",
            "excerpt": scrub_em_dashes(fields["hook"].strip()),
            "angle": scrub_em_dashes(fields["angle"].strip()),
            "model_why": scrub_em_dashes(fields["why"].strip()),
            "quote": fields["quote"].strip(),
            "angle_kind": fields["angle_kind"],
            "date": None,
            "url": None,
            "figures": [],
            "figure_sentence": "",
            "because": because,
            "source_sentence": (f"suggested by {provider_word} {meta['model']} on {record_cards._said_date(day.isoformat())}, "
                                f"from {len(bundle['posts'])} of your posts and {len(bundle['asks'])} of your asks; "
                                "nothing else was sent"),
            "method_sentence": ("asked in a schema that allows only the ids sent, an angle from a fixed list and short "
                                "phrases; every phrase checked for numbers and names, every quote found in your post, "
                                "every cited row found; the studio has not checked whether the idea is good"),
            "draft_text": f"{fields['hook'].strip()}\n\n{fields['angle'].strip()}",
            "provider": provider_word,
            "ask_id": int(fields["ask"].split("-", 1)[1]) if ask_row else None,
            "block_label": "Suggested by your model",
        }
        rows = [{"table": "own_posts", "id": b} for b in based_on]
        if ask_row:
            rows.append({"table": "asks", "id": payload["ask_id"]})
        card = record_cards._card(card_id, record_daily.OPEN_SLOT, "model", "idea", "suggested",
                                  "suggested by your own model", payload, rows,
                                  status="shown" if not shown_one else "spare")
        card["provenance"]["model"] = meta
        card["provenance"]["verification"] = verification
        shown_one = True
        cards.append(card)
    return cards, dropped, reasons
