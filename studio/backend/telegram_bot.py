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

import logging
import re
import threading
import time
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
}

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
    "",
    "To pair a chat: in your studio, open Settings, then Local security, and press This is me beside it.",
    "",
    "I never send your posts, your drafts, your words, or anything about other people.",
))

# Commands answered whatever the confirmations switch says: they are questions.
QUESTIONS = ("start", "help", "status")
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
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


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


def options() -> Dict[str, Any]:
    """The bot's switches, as the panel shows them."""
    return {"replies": replies_on()}


def save_options(replies: Optional[bool] = None) -> Dict[str, Any]:
    """Saves the switches the panel sent; a switch not sent is left as it is."""
    changes = {}
    if replies is not None:
        changes[REPLIES_KEY] = "on" if replies else "off"
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
