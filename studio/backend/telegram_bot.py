"""
The Telegram bot: what it says back, and how it reaches Telegram.
=================================================================

ingress.py asks Telegram for the messages the creator sends their own bot
and saves them. This module is the bot's side of the conversation (2.11.0):
the short fixed sentences it answers with, and the one way a message goes
out.

What the bot sends is fixed: each answer is one of SENTENCES, and none
carries the creator's data. The one value any of them holds is the
recipient's own chat id, in the sentence that tells a chat how to pair.

Every request goes to the Bot API at API_BASE, through egress.py under the
category the ingress already uses, so the Local security tab counts it and
INOX_NO_EGRESS refuses it. The suite points API_BASE at a fake Bot API on
loopback (tests/telegram_fake.py); nothing in the suite reaches Telegram.

A reply waits in an outbox, in memory only: it is tried again after a
network fault (three times, the wait doubling) and after the time Telegram
asked for with a 429, and given up when Telegram refuses it outright, with
the reason in plain words for the Local security panel. The message it
answers was saved before the reply was sent, so a reply that never arrives
never costs the message, and a reply sent again never saves it twice.

Strict Invariants:
- Zero em-dashes.
- Nothing about another member is ever sent: no name, no comment text.
- No message text in a log line: the logs say what kind of thing happened.
"""

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from . import egress as _egress
    from .database import get_db
except ImportError:
    import egress as _egress
    from database import get_db

logger = logging.getLogger("studio.telegram")

# The Bot API. One base for every method, so the suite can stand in for it.
API_BASE = "https://api.telegram.org"

# Settings, each in the profile the bot belongs to.
REPLIES_KEY = "telegram_replies"   # the bot confirms each message: on unless "off"
FIGURES_KEY = "telegram_figures"   # the bot may answer with your figures: off unless "on"
NOTIFY_DUE_KEY = "telegram_notify_due"   # tell me when a queued post is due: off unless "on"
NOTIFY_24H_KEY = "telegram_notify_24h"   # my latest post's figures at about 24 hours: off unless "on"
TOLD_KEY = "telegram_told"               # what the notifications have told, so nothing is told twice
TOLD_KEPT = 200

# The worker looks for something to tell between polls, at most this often.
NOTIFY_EVERY_SECONDS = 60.0
# A reading this old counts as "about 24 hours", and is told only while the
# post is still under two days old.
DAY_READING_HOURS = (20.0, 30.0)
DAY_READING_TOLD_UNTIL_HOURS = 48.0

# Every sentence the bot answers a message with. Fixed: none carries the
# creator's data. {chat_id} is the recipient's own chat id.
SENTENCES = {
    "draft": "Saved as a draft in your studio.",
    "post": "Today will ask you to open this post's analytics at your computer.",
    "short": "Today will ask you to open this link at your computer.",
    "not_yours": "That is not one of your posts, so your studio will not read it.",
    "paired": "Paired. Messages from this chat now arrive in your studio. Send /help to see what I do.",
    "not_paired": ("Not paired yet. In your studio, open Settings, then Local security, and press This is me "
                   "beside chat {chat_id}."),
    "other_chat": "This bot takes messages only from the chat its owner paired.",
    "no_text": "That message had no text, so nothing was saved.",
    "not_saved": "Your studio could not save that message. Open the studio to see why.",
    "ask": "Remembered. Your studio uses it when it picks what to write about, from tomorrow's cards.",
    "empty_idea": "Send /idea with your idea after it, for example /idea pricing for a small studio.",
    "empty_ask": "Send /ask with what your studio should remember, for example /ask more on hiring.",
    "unknown_command": "I do not know that command. Send /help to see what I do.",
    "bridge_connected": "The bridge in your browser is connected.",
    "bridge_quiet": ("The bridge in your browser has not been heard from in the last few minutes: open LinkedIn "
                     "in the bridge browser."),
    "bridge_never": "The bridge has not been heard from yet: install it, then open LinkedIn in the bridge browser.",
    "figures_off": ("Your figures stay in your studio. To have me answer with them, turn on The bot may answer "
                    "with your figures under Local security."),
    "no_post": "No post of yours is in your studio yet.",
    "nothing_scheduled": "No post is scheduled.",
    "due_one": "A post in your queue is due now. Open your studio to post it.",
    "due_many": "{count} posts in your queue are due now. Open your studio to post them.",
}

# Where a figure was read, as /today says it.
SOURCE_WORDS = {
    "post_analytics": "on its analytics page",
    "activity_page": "on your Activity tab",
    "linkedin_export": "from LinkedIn's analytics export",
    "voyager_network": "by network reading",
    "snapshot": "as your feed last showed it",
}
FIGURE_WORDS = (("impressions", "impressions"), ("reactions", "reactions"), ("comments", "comments"),
                ("reposts", "reposts"))

# What /start and /help answer: what the bot does, how to pair, and what it
# never sends. Fixed, like every sentence above.
HELP = "\n".join((
    "I am your Inox Hydra bot. I pass what you send me to your studio on your computer.",
    "",
    "Send me:",
    "- any text: saved as a draft",
    "- a link to one of your LinkedIn posts: Today asks you to open its analytics",
    "- /idea and your idea: saved as a draft, tagged as an idea",
    "- /ask and what your studio should remember when it picks what to write about",
    "- /status: whether your studio and its bridge are running",
    "- /today: your latest post's figures, replies waiting and your next scheduled post, only if you allow "
    "figures in your studio",
    "",
    "To pair a chat: in your studio, open Settings, then Local security, and press This is me beside it.",
    "",
    "I never send your posts, your drafts, your words, or anything about other people.",
))

# Commands answered whatever the confirmations switch says: they are questions.
QUESTIONS = ("start", "help", "status", "today")
_COMMAND = re.compile(r"^/([A-Za-z][A-Za-z0-9_]{0,31})(?:@[A-Za-z0-9_]{1,64})?(?:\s+(.*))?$", re.DOTALL)


def parse_command(text: str) -> Optional[Tuple[str, str]]:
    """(name, what follows it) for a command such as /idea or /idea@YourBot, or None for any other text."""
    found = _COMMAND.match((text or "").strip())
    if not found:
        return None
    return found.group(1).lower(), (found.group(2) or "").strip()


def status_sentence() -> str:
    """/status: whether the studio and its bridge are running. No figure, no time, no count."""
    try:
        from . import onboarding
    except ImportError:
        import onboarding
    try:
        bridge = onboarding.bridge_status()
    except Exception:
        bridge = {"connected": False, "last_seen_at": None}
    if bridge.get("connected"):
        said = SENTENCES["bridge_connected"]
    elif bridge.get("last_seen_at"):
        said = SENTENCES["bridge_quiet"]
    else:
        said = SENTENCES["bridge_never"]
    return f"Your studio is running. {said}"

# A chat the bot refused is answered at most this often, so a stranger who
# writes twenty times is answered once, and the owner who writes twice before
# pairing is not answered twice.
REFUSAL_REPLY_EVERY_SECONDS = 600.0

OUTBOX_KEPT = 30
SEND_ATTEMPTS = 3
SEND_TIMEOUT = 10.0

# Why Telegram did not take a request, in the words the panel shows.
UNREACHABLE = ("The studio could not reach Telegram. Check this computer's internet connection; the studio "
               "tries again by itself.")
EGRESS_OFF = ("Requests to Telegram are turned off on this computer (INOX_ALLOW_INGRESS_EGRESS or "
              "INOX_NO_EGRESS), so the studio cannot reach your bot.")


def method_url(token: str, method: str) -> str:
    """The address of one Bot API method for this bot. It carries the token: never logged or shown."""
    return f"{API_BASE}/bot{token}/{method}"


def ledger_url(method: str) -> str:
    """
    The same address as the egress ledger records it, without the token.
    The ledger shows each category's last destination on Local security,
    and the Bot API carries a bot's token in the path, which the ledger's
    own clean-up (scheme, host and path) keeps.
    """
    return f"{API_BASE}/bot<token>/{method}"


def plain_words(status: int, description: str = "", retry_after: Optional[float] = None) -> str:
    """Telegram's answer to a request, as the panel says it. Never the token, never the message."""
    text = (description or "").lower()
    if status == 429:
        wait = f"{float(retry_after):.1f}s" if retry_after else "a while"
        return f"Telegram asked the studio to slow down, so it waits {wait} before asking again."
    if status in (401, 404):
        return "Telegram does not recognise this bot's token. Paste the token BotFather gave you again."
    if status == 403:
        return ("Telegram would not deliver the bot's message: the bot may be blocked in your chat. Unblock it "
                "in Telegram, then send it a message.")
    if status == 400 and "chat not found" in text:
        return "Telegram does not know the paired chat. Pair your phone again: message the bot, then press This is me."
    if status == 409:
        return ("Another program is asking Telegram for this bot's messages, such as a second studio or a "
                "webhook. Only one can at a time.")
    if status >= 500:
        return "Telegram's service answered with an error. The studio tries again by itself."
    return f"Telegram refused the request (status {status})."


def send_message(token: str, chat_id: Any, text: str, timeout: float = SEND_TIMEOUT) -> Dict[str, Any]:
    """
    One message to one chat. Returns {ok, kind, said, retry_after}: kind is
    sent, rate_limited, network (worth trying again), refused (not worth it)
    or refused_here (this computer's egress switch).
    """
    url = method_url(token, "sendMessage")
    try:
        _egress.require(ledger_url("sendMessage"), "ingress")
    except _egress.EgressRefused:
        return {"ok": False, "kind": "refused_here", "said": EGRESS_OFF, "retry_after": None}
    try:
        res = requests.post(url, json={"chat_id": str(chat_id), "text": text, "disable_web_page_preview": True},
                            timeout=timeout)
    except Exception as error:
        logger.warning("A message to Telegram did not go: %s", type(error).__name__)
        return {"ok": False, "kind": "network", "said": UNREACHABLE, "retry_after": None}
    try:
        body = res.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}
    if res.status_code == 200 and body.get("ok"):
        return {"ok": True, "kind": "sent", "said": None, "retry_after": None}
    if res.status_code == 429:
        try:
            retry = float((body.get("parameters") or {}).get("retry_after"))
        except (TypeError, ValueError):
            retry = None
        retry = retry if retry and retry > 0 else 5.0
        return {"ok": False, "kind": "rate_limited", "said": plain_words(429, retry_after=retry), "retry_after": retry}
    kind = "network" if res.status_code >= 500 else "refused"
    logger.warning("Telegram refused a message: status %s", res.status_code)
    return {"ok": False, "kind": kind, "said": plain_words(res.status_code, str(body.get("description") or "")),
            "retry_after": None}


class Outbox:
    """
    The bot's messages waiting to go, oldest first, in memory only. One
    flush at a time: the worker flushes after each poll, and a press in the
    panel (This is me) may flush at once.
    """

    def __init__(self) -> None:
        self._items: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._flushing = threading.Lock()
        self.not_before = 0.0
        self.last_error: Optional[str] = None
        self.last_error_at: Optional[str] = None
        self.sent = 0

    def put(self, chat_id: Any, text: str) -> None:
        with self._lock:
            self._items.append({"chat_id": str(chat_id), "text": text, "attempts": 0, "not_before": 0.0})
            # A bot that cannot reach Telegram for a day keeps the newest few.
            del self._items[:-OUTBOX_KEPT]

    def clear(self) -> None:
        with self._lock:
            self._items = []
            self.not_before = 0.0

    def waiting(self) -> int:
        with self._lock:
            return len(self._items)

    def flush(self, token: str) -> None:
        """Sends what is due, in order. Stops at the first item that must wait, so the order holds."""
        if not token:
            return
        with self._flushing:
            while True:
                now = time.monotonic()
                with self._lock:
                    if not self._items or now < self.not_before:
                        return
                    item = self._items[0]
                    if item["not_before"] > now:
                        return
                result = send_message(token, item["chat_id"], item["text"])
                with self._lock:
                    if result["ok"]:
                        self._items.pop(0)
                        self.sent += 1
                        self.last_error = None
                        continue
                    self.last_error = result["said"]
                    self.last_error_at = _now()
                    if result["kind"] == "rate_limited":
                        self.not_before = time.monotonic() + float(result["retry_after"] or 5.0)
                        return
                    if result["kind"] == "network":
                        item["attempts"] += 1
                        if item["attempts"] >= SEND_ATTEMPTS:
                            self._items.pop(0)
                            continue
                        item["not_before"] = time.monotonic() + 0.5 * (2 ** item["attempts"])
                        return
                    # Refused outright (blocked, unknown chat, bad token) or
                    # refused here: sending it again would be refused again.
                    self._items.pop(0)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _instant(text: Any) -> Optional[datetime]:
    if not text:
        return None
    try:
        when = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def ago(when: Optional[datetime]) -> str:
    """How long ago, in words: minutes under an hour, hours under two days, then days."""
    if when is None:
        return "at a time not recorded"
    hours = max(0.0, (datetime.now(timezone.utc) - when).total_seconds() / 3600.0)
    if hours < 1:
        minutes = max(1, int(round(hours * 60)))
        return f"{minutes} minute ago" if minutes == 1 else f"{minutes} minutes ago"
    if hours < 48:
        whole = int(hours)
        return f"{whole} hour ago" if whole == 1 else f"{whole} hours ago"
    days = int(hours // 24)
    return f"{days} days ago"


def _where(entry: Dict[str, Any]) -> str:
    source = entry.get("source") or ""
    words = SOURCE_WORDS.get(source) or "by your studio"
    return f"read {words} {ago(_instant(entry.get('read_at')))}"


def today_answer() -> str:
    """
    /today, with figures allowed: the latest post's figures, each with where
    and how long ago it was read; how many replies are waiting; when the next
    post is scheduled. Counts and the creator's own figures only: no one's
    name, no comment, not even the creator's own words.
    """
    try:
        from . import post_identity, replies, results
    except ImportError:
        import post_identity
        import replies
        import results
    conn = get_db()
    try:
        said = []
        row = conn.execute(
            "SELECT activity_urn, published_at FROM own_posts WHERE published_at IS NOT NULL "
            "AND activity_urn NOT LIKE ? ORDER BY published_at DESC LIMIT 1",
            (post_identity.LOCAL_URN_PREFIX + "%",)).fetchone()
        if not row:
            said.append(SENTENCES["no_post"])
        else:
            figure = results.figures(conn, [row["activity_urn"]]).get(row["activity_urn"]) or {}
            by_figure = figure.get("by_figure") or {}
            read = [(field, words) for field, words in FIGURE_WORDS if figure.get(field) is not None]
            head = f"Your latest post, published {ago(_instant(row['published_at']))}"
            if not read:
                said.append(f"{head}, has no figures read yet.")
            else:
                places = {(by_figure.get(f) or {}).get("source") or figure.get("source"): None for f, _w in read}
                times = {(by_figure.get(f) or {}).get("read_at") or figure.get("read_at") for f, _w in read}
                if len(places) == 1 and len(times) == 1:
                    first = by_figure.get(read[0][0]) or figure
                    counts = ", ".join(f"{figure[f]:,} {w}" for f, w in read)
                    said.append(f"{head}: {counts}, {_where(first)}.")
                else:
                    counts = ", ".join(f"{figure[f]:,} {w} ({_where(by_figure.get(f) or figure)})" for f, w in read)
                    said.append(f"{head}: {counts}.")
        said.append(f"Replies waiting: {replies.waiting_count(conn)}.")
        upcoming = conn.execute("SELECT scheduled_for FROM posts WHERE status = 'scheduled' "
                                "AND scheduled_for IS NOT NULL ORDER BY scheduled_for LIMIT 1").fetchone()
        when = _instant(upcoming[0]) if upcoming else None
        if when is not None:
            local = when.astimezone()
            said.append(f"Next scheduled post: {local.strftime('%a %d %b, %H:%M')} (your computer's time).")
        else:
            said.append(SENTENCES["nothing_scheduled"])
        return " ".join(said)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The settings
# ---------------------------------------------------------------------------

def _setting(key: str) -> Optional[str]:
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return row["value"] if row else None


def replies_on() -> bool:
    """Whether the bot confirms each message, in the open profile. On unless turned off."""
    return (_setting(REPLIES_KEY) or "on") != "off"


def figures_on() -> bool:
    """Whether the bot may answer with the creator's figures, in the open profile. Off unless turned on."""
    return (_setting(FIGURES_KEY) or "off") == "on"


def notify_due_on() -> bool:
    return (_setting(NOTIFY_DUE_KEY) or "off") == "on"


def notify_24h_on() -> bool:
    return (_setting(NOTIFY_24H_KEY) or "off") == "on"


def options() -> Dict[str, Any]:
    """The bot's switches, as the panel shows them."""
    return {"replies": replies_on(), "figures": figures_on(), "notify_due": notify_due_on(),
            "notify_24h": notify_24h_on()}


def save_options(replies: Optional[bool] = None, figures: Optional[bool] = None,
                 notify_due: Optional[bool] = None, notify_24h: Optional[bool] = None) -> Dict[str, Any]:
    """Saves the switches the panel sent; a switch not sent is left as it is."""
    changes = {}
    for key, value in ((REPLIES_KEY, replies), (FIGURES_KEY, figures), (NOTIFY_DUE_KEY, notify_due),
                       (NOTIFY_24H_KEY, notify_24h)):
        if value is not None:
            changes[key] = "on" if value else "off"
    if changes:
        conn = get_db()
        try:
            with conn:
                for key, value in changes.items():
                    conn.execute(
                        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                        (key, value))
        finally:
            conn.close()
    return options()


def answer_for(record: Optional[Dict[str, Any]]) -> Optional[str]:
    """The sentence that confirms what became of an accepted message, from what was stored."""
    if not record:
        return None
    request = record.get("desk_request") if record.get("kind") != "desk_request" else record
    said = []
    if record.get("kind") != "desk_request":
        said.append(SENTENCES["draft"])
    if request:
        if request.get("state") == "refused":
            said.append(SENTENCES["not_yours"])
        elif request.get("link") and not request.get("activity_urn"):
            said.append(SENTENCES["short"])
        else:
            said.append(SENTENCES["post"])
    return " ".join(said) or None


# ---------------------------------------------------------------------------
# Notifications: each opt-in on its own, none by default
# ---------------------------------------------------------------------------

def _told(conn) -> List[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (TOLD_KEY,)).fetchone()
    try:
        told = json.loads(row["value"]) if row and row["value"] else []
    except (TypeError, ValueError):
        told = []
    return [str(item) for item in told if isinstance(item, str)]


def _mark_told(conn, told: List[str]) -> None:
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
            (TOLD_KEY, json.dumps(told[-TOLD_KEPT:])))


def notifications() -> List[str]:
    """
    What there is to tell the paired chat, in the open profile, each thing
    once: a queued post that is due, as a count; the latest post's reading
    at about 24 hours, with that reading's own figures. Marks what it
    returns as told. Counts and the creator's own figures only.
    """
    due_on, day_on = notify_due_on(), notify_24h_on()
    if not (due_on or day_on):
        return []
    try:
        from . import post_identity
    except ImportError:
        import post_identity
    conn = get_db()
    try:
        told = _told(conn)
        said: List[str] = []
        newly: List[str] = []
        if due_on:
            fresh = [f"due:{r['id']}:{r['scheduled_for']}" for r in conn.execute(
                "SELECT id, scheduled_for FROM posts WHERE status = 'due' ORDER BY scheduled_for")]
            fresh = [key for key in fresh if key not in told]
            if fresh:
                said.append(SENTENCES["due_one"] if len(fresh) == 1
                            else SENTENCES["due_many"].format(count=len(fresh)))
                newly += fresh
        if day_on:
            latest = conn.execute(
                "SELECT activity_urn, published_at FROM own_posts WHERE published_at IS NOT NULL "
                "AND activity_urn NOT LIKE ? ORDER BY published_at DESC LIMIT 1",
                (post_identity.LOCAL_URN_PREFIX + "%",)).fetchone()
            published = _instant(latest["published_at"]) if latest else None
            young = published is not None and (
                datetime.now(timezone.utc) - published).total_seconds() / 3600.0 <= DAY_READING_TOLD_UNTIL_HOURS
            key = f"24h:{latest['activity_urn']}" if latest else None
            if young and key not in told:
                reading = conn.execute(
                    "SELECT source, impressions, reactions, comments, reposts FROM post_metric_observations "
                    "WHERE activity_urn = ? AND age_hours BETWEEN ? AND ? "
                    "ORDER BY ABS(age_hours - 24.0), observed_at DESC LIMIT 1",
                    (latest["activity_urn"], DAY_READING_HOURS[0], DAY_READING_HOURS[1])).fetchone()
                counts = [f"{reading[f]:,} {w}" for f, w in FIGURE_WORDS if reading and reading[f] is not None]
                if counts:
                    where = SOURCE_WORDS.get(reading["source"] or "") or "by your studio"
                    said.append(f"Your latest post at about 24 hours: {', '.join(counts)}, read {where}.")
                    newly.append(key)
        if newly:
            _mark_told(conn, told + newly)
        return said
    finally:
        conn.close()
