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

Some messages carry buttons (phase 2): Undo under a saved draft, Remind me
in an hour and Done under a due post. A button's data is an opaque id and
one letter, never words from a post or a draft; what it does is kept here,
in the bot's profile (BUTTONS_KEY), and a press acts on the studio's own
records only, once, for the paired chat only. Nothing a button does
reaches LinkedIn.

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
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from datetime import time as day_time
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from . import changes
    from . import collection
    from . import egress as _egress
    from . import writing
    from .database import get_db
except ImportError:
    import changes
    import collection
    import egress as _egress
    import writing
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
BUTTONS_KEY = "telegram_buttons"         # what each message's buttons do, and whether they were used
BUTTONS_KEPT = 100                       # the newest messages' buttons; an older one is old
REMIND_KEY = "telegram_remind"           # due posts the creator asked to be reminded of, and when
REMIND_KEPT = 20
# Remind me in an hour.
REMIND_AFTER_SECONDS = 3600.0
# Quiet hours, the creator's: the notifications wait while they are on, and
# go when they end. Whole hours on the computer's own clock, {on, from, to};
# on by default from 23:00 to 07:00. Answers to the creator's own messages,
# commands and presses are never held. Not the poller's night pace
# (ingress.is_quiet_hours), which changes only how often Telegram is asked.
QUIET_KEY = "telegram_quiet"
QUIET_FROM, QUIET_TO = 23, 7
# The weekly summary, off by default: {on, day (0 is Monday), hour, since},
# on the computer's own clock, Monday 09:00 unless changed. The first comes
# at the first chosen moment after it was turned on or changed (since), and
# each week is told once (telegram_told, "week:<year>-W<week>").
WEEKLY_KEY = "telegram_weekly"
WEEKLY_DAY, WEEKLY_HOUR = 0, 9
# The posts of the week whose figures the summary lists, newest first.
WEEKLY_POSTS_SHOWN = 7

# The buttons, by the one letter a button's data ends with, and which a
# message of each kind carries. "a" says the creator's own number of angles
# (writing.py), and a digit writes up the angle it numbers.
BUTTON_LABELS = {"u": "Undo", "r": "Remind me in an hour", "d": "Done", "w": "Write it up", "a": "Angles",
                 "n": "Not today"}
BUTTON_ROWS = {"undo": (("u",),), "item": (("w", "a"), ("u",)), "item_bare": (("u",),),
               "due": (("r",), ("d",)), "morning": (("w", "n"),)}
# The bot may send what it writes from the collection (its words): off unless "on".
COLLECTION_WORDS_KEY = "telegram_collection_words"
# The morning idea, off by default: {on, days (0 is Monday), hour, since}.
MORNING_KEY = "telegram_morning"
MORNING_DAYS, MORNING_HOUR = (0, 1, 2, 3, 4), 8

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
    "test": "This is a test message from your Inox Hydra studio. If you can read it, the bot can reach you.",
    "due_one": "A post in your queue is due now. Open your studio to post it.",
    "due_many": "{count} posts in your queue are due now. Open your studio to post them.",
    "due_again_one": "Reminder: a post in your queue is still due. Open your studio to post it.",
    "due_again_many": "Reminder: {count} posts in your queue are still due. Open your studio to post them.",
    # What a press of a button did, as the phone's notice says it and as the
    # message then says it under its first words.
    "undone": "Undone: the draft is removed from your studio.",
    "undo_changed": "Not undone: the draft has changed in your studio since, so it was kept.",
    "undo_gone": "Nothing to undo: the draft is no longer in your studio.",
    "remind_set": "I will remind you in an hour if it is still due.",
    "done": "Reminder cleared. Nothing was marked as posted: it stays due in your studio until you post it.",
    "button_used": "That button was already used, so nothing more was done.",
    "button_old": "That button is old, so nothing was done.",
    "press_failed": "Your studio could not do that. Open the studio to see why.",
    "drafts": "Drafts made from what you sent, in the last seven days: {count}.",
    "drafts_none": "No draft was made from what you sent in the last seven days.",
    # Phase 3: everything sent lands in the collection.
    "collected": "Saved to your collection.",
    "bookmarked": "Saved to your collection as a bookmark. Your studio never opens other people's posts.",
    "undone_item": "Undone: it is removed from your collection.",
    "undo_item_kept": "Not undone: you have used it in your studio since, so it was kept.",
    "undo_item_gone": "Nothing to undo: it is no longer in your collection.",
    # Phase 3, item 2: something made from the collection.
    "writing": "Writing it up in your studio.",
    "finding_angles": "Finding angles in your studio.",
    "draft_ready": "Draft ready in your studio.",
    "draft_ready_words": "Draft ready in your studio. It begins:",
    "angles_ready": "{count} angles are ready in your studio, on the item in your collection.",
    "angles_here": "Angles from your collection. Press one to write it up:",
    "no_provider": ("No AI provider is set up in your studio, so nothing was written. Connect yours on the Composer's "
                    "Prompt tab, or use it as a draft in your collection."),
    "write_failed": "Your AI provider did not write it, so nothing changed. Open your studio to see why.",
    "write_refused": ("Nothing was kept: what your AI provider wrote had a figure or a name that is not in your "
                      "note."),
    "not_today": "Not today. It stays in your collection.",
    "morning": "An idea from your collection:",
    "angle_question": "Angle: open with a question, as the posts of yours that did best did.",
    "angle_story": "Angle: open with something that happened to you, as the posts of yours that did best did.",
    "angle_short": "Angle: open with one short line, as the posts of yours that did best did.",
    "angle_statement": "Angle: open with a plain, bold statement, as the posts of yours that did best did.",
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
    "I am your Inox Hydra bot. Everything you send me goes into the collection in your studio on your computer.",
    "",
    "Send me:",
    "- any text, or a message you forward: kept in your collection, to write from when you like",
    "- /idea and your idea: kept in your collection as an idea",
    "- a link to one of your LinkedIn posts: Today asks you to open its analytics",
    "- a link to someone else's post: kept as a bookmark, never opened",
    "- Draft: and your post: saved straight as a draft",
    "- /ask and what your studio should remember when it picks what to write about",
    "- /status: whether your studio and its bridge are running",
    "- /today: your latest post's figures, replies waiting and your next scheduled post, only if you allow "
    "figures in your studio",
    "- /drafts: how many drafts were made from what you sent in the last seven days",
    "",
    "Press Undo under my answer to take it back, while it is still new in your studio.",
    "",
    "To pair a chat: in your studio, open Settings, then Local security, and press This is me beside it.",
    "",
    "I never send your posts, your drafts, your words, or anything about other people.",
))

# Commands answered whatever the confirmations switch says: they are questions.
QUESTIONS = ("start", "help", "status", "today", "drafts")
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
        return f"Rate limited by Telegram, which asked the studio to slow down: it waits {wait} before asking again."
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


# Two refusals that say the work is already done, not that something went
# wrong: an edit to what the message already says, and the answer to a press
# Telegram stopped waiting for (the edit after it says what became of it).
_ALREADY = (("edit", "message is not modified"), ("answerCallbackQuery", "query is too old"))


def call(token: str, method: str, params: Dict[str, Any], timeout: float = SEND_TIMEOUT) -> Dict[str, Any]:
    """
    One Bot API request: sendMessage, answerCallbackQuery or an edit. Returns
    {ok, kind, said, retry_after}: kind is sent, already (nothing left to
    do), rate_limited, network (worth trying again), refused (not worth it)
    or refused_here (this computer's egress switch).
    """
    url = method_url(token, method)
    try:
        _egress.require(ledger_url(method), "ingress")
    except _egress.EgressRefused:
        return {"ok": False, "kind": "refused_here", "said": EGRESS_OFF, "retry_after": None}
    try:
        res = requests.post(url, json=params, timeout=timeout)
    except Exception as error:
        logger.warning("A request to Telegram (%s) did not go: %s", method, type(error).__name__)
        return {"ok": False, "kind": "network", "said": UNREACHABLE, "retry_after": None}
    try:
        body = res.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}
    if res.status_code == 200 and body.get("ok"):
        return {"ok": True, "kind": "sent", "said": None, "retry_after": None}
    description = str(body.get("description") or "")
    if res.status_code == 400 and any(method.startswith(m) and w in description.lower() for m, w in _ALREADY):
        return {"ok": True, "kind": "already", "said": None, "retry_after": None}
    if res.status_code == 429:
        try:
            retry = float((body.get("parameters") or {}).get("retry_after"))
        except (TypeError, ValueError):
            retry = None
        retry = retry if retry and retry > 0 else 5.0
        return {"ok": False, "kind": "rate_limited", "said": plain_words(429, retry_after=retry), "retry_after": retry}
    kind = "network" if res.status_code >= 500 else "refused"
    logger.warning("Telegram refused a request (%s): status %s", method, res.status_code)
    return {"ok": False, "kind": kind, "said": plain_words(res.status_code, description), "retry_after": None}


def send_message(token: str, chat_id: Any, text: str, timeout: float = SEND_TIMEOUT,
                 keyboard: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One message to one chat, with its buttons when it has any. Returns what call() returns."""
    return call(token, "sendMessage", message_params(chat_id, text, keyboard), timeout=timeout)


def message_params(chat_id: Any, text: str, keyboard: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"chat_id": str(chat_id), "text": text, "disable_web_page_preview": True}
    if keyboard:
        params["reply_markup"] = keyboard
    return params


class Outbox:
    """
    The bot's requests waiting to go, oldest first, in memory only: its
    messages, and the answer and the edit a button press is given. One
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

    def put(self, chat_id: Any, text: str, keyboard: Optional[Dict[str, Any]] = None) -> None:
        """A message to a chat, with its buttons when it has any."""
        self.put_call("sendMessage", message_params(chat_id, text, keyboard))

    def put_call(self, method: str, params: Dict[str, Any]) -> None:
        """Any Bot API request: the answer to a press, an edit."""
        with self._lock:
            self._items.append({"method": method, "params": dict(params), "attempts": 0, "not_before": 0.0})
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
                result = call(token, item["method"], item["params"])
                with self._lock:
                    if result["ok"]:
                        self._items.pop(0)
                        self.sent += 1 if result["kind"] == "sent" else 0
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
            head = f"Your latest post, published {ago(_instant(row['published_at']))}"
            words = figure_words(figure)
            said.append(f"{head}: {words}." if words else f"{head}, has no figures read yet.")
        said.append(f"Replies waiting: {replies.waiting_count(conn)}.")
        said.append(next_scheduled(conn))
        return " ".join(said)
    finally:
        conn.close()


def figure_words(figure: Dict[str, Any]) -> Optional[str]:
    """
    One post's figures as the bot says them, each with where and how long
    ago it was read ("1,234 impressions, 56 reactions, read on its analytics
    page 3 hours ago"), or None when nobody read one. A figure nobody read
    is left out, never said as 0.
    """
    by_figure = figure.get("by_figure") or {}
    read = [(field, words) for field, words in FIGURE_WORDS if figure.get(field) is not None]
    if not read:
        return None
    places = {(by_figure.get(f) or {}).get("source") or figure.get("source"): None for f, _w in read}
    times = {(by_figure.get(f) or {}).get("read_at") or figure.get("read_at") for f, _w in read}
    if len(places) == 1 and len(times) == 1:
        first = by_figure.get(read[0][0]) or figure
        return ", ".join(f"{figure[f]:,} {w}" for f, w in read) + f", {_where(first)}"
    return ", ".join(f"{figure[f]:,} {w} ({_where(by_figure.get(f) or figure)})" for f, w in read)


def next_scheduled(conn) -> str:
    """When the next post is scheduled, on the computer's own clock, or that none is."""
    upcoming = conn.execute("SELECT scheduled_for FROM posts WHERE status = 'scheduled' "
                            "AND scheduled_for IS NOT NULL ORDER BY scheduled_for LIMIT 1").fetchone()
    when = _instant(upcoming[0]) if upcoming else None
    if when is None:
        return SENTENCES["nothing_scheduled"]
    return f"Next scheduled post: {when.astimezone().strftime('%a %d %b, %H:%M')} (your computer's time)."


def drafts_answer() -> str:
    """/drafts: how many drafts were made from what was sent in the last seven days. A count, never words."""
    now = datetime.now(timezone.utc)
    conn = get_db()
    try:
        count = collection.drafts_made(conn, now - timedelta(days=7), now + timedelta(minutes=1))
    finally:
        conn.close()
    return SENTENCES["drafts"].format(count=count) if count else SENTENCES["drafts_none"]


def weekly_summary(conn, moment: datetime) -> str:
    """
    The weekly summary for the seven days to `moment`: the posts the studio
    recorded as published, the drafts saved from the phone, the replies
    waiting and the next scheduled post, as counts and a time; and, only if
    the bot may answer with the creator's figures, each of the week's posts'
    figures with where and when they were read. Never a name, never a
    comment, never a post's or a draft's words: a post is named by its day.
    """
    try:
        from . import replies, results
    except ImportError:
        import replies
        import results
    start = moment - timedelta(days=7)
    first_day = (start - timedelta(days=1)).date().isoformat()
    published = []
    for row in conn.execute("SELECT activity_urn, published_at FROM own_posts WHERE published_at IS NOT NULL "
                            "AND substr(published_at, 1, 10) >= ?", (first_day,)):
        when = _instant(row["published_at"])
        if when is not None and start <= when < moment:
            published.append((when, row["activity_urn"]))
    published.sort(reverse=True)
    drafts = collection.drafts_made(conn, start, moment)
    lines = [f"Your week, the seven days to {moment.strftime('%a %d %b, %H:%M')} on your computer's clock:",
             f"Posts published, as your studio recorded them: {len(published)}",
             f"Drafts made from what you sent: {drafts}",
             f"Replies waiting: {replies.waiting_count(conn)}",
             next_scheduled(conn)]
    if published and figures_on():
        figures = results.figures(conn, [urn for _when, urn in published])
        lines += ["", "Your figures, each as last read:"]
        for when, urn in published[:WEEKLY_POSTS_SHOWN]:
            words = figure_words(figures.get(urn) or {}) or "no figures read yet"
            lines.append(f"- Published {when.astimezone().strftime('%a %d %b')}: {words}")
        if len(published) > WEEKLY_POSTS_SHOWN:
            lines.append(f"- and {len(published) - WEEKLY_POSTS_SHOWN} more, in your studio")
    return "\n".join(lines)


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


def local_now() -> datetime:
    """The computer's own clock, with its time zone: what quiet hours and the weekly summary are read against."""
    return datetime.now().astimezone()


def _hour(value: Any, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 23 else default


def quiet_hours() -> Dict[str, Any]:
    """Quiet hours in the open profile: {on, from, to}, whole hours. On from 23:00 to 07:00 unless changed."""
    try:
        held = json.loads(_setting(QUIET_KEY) or "{}")
    except (TypeError, ValueError):
        held = {}
    held = held if isinstance(held, dict) else {}
    start, end = _hour(held.get("from"), QUIET_FROM), _hour(held.get("to"), QUIET_TO)
    if start == end:
        start, end = QUIET_FROM, QUIET_TO
    return {"on": held.get("on") is not False, "from": start, "to": end}


def in_quiet_hours(now: Optional[datetime] = None) -> bool:
    """Whether the notifications wait now: quiet hours are on and the hour is inside them, across midnight too."""
    quiet = quiet_hours()
    if not quiet["on"]:
        return False
    hour = (now or local_now()).hour
    start, end = quiet["from"], quiet["to"]
    return start <= hour < end if start < end else (hour >= start or hour < end)


def weekly() -> Dict[str, Any]:
    """The weekly summary's setting in the open profile: {on, day, hour, since}. Off, Monday 09:00, by default."""
    try:
        held = json.loads(_setting(WEEKLY_KEY) or "{}")
    except (TypeError, ValueError):
        held = {}
    held = held if isinstance(held, dict) else {}
    day = held.get("day")
    day = day if isinstance(day, int) and not isinstance(day, bool) and 0 <= day <= 6 else WEEKLY_DAY
    return {"on": held.get("on") is True, "day": day, "hour": _hour(held.get("hour"), WEEKLY_HOUR),
            "since": held.get("since") if isinstance(held.get("since"), str) else None}


def _weekly_moment(now: datetime, setting: Dict[str, Any]) -> datetime:
    """The chosen day and hour in the week of `now` (weeks start on Monday), on the computer's clock."""
    monday = now.date() - timedelta(days=now.weekday())
    return datetime.combine(monday + timedelta(days=setting["day"]), day_time(hour=setting["hour"])).astimezone()


def _week_key(moment: datetime) -> str:
    year, week, _day = moment.isocalendar()
    return f"week:{year}-W{week:02d}"


def _weekly_due(told: List[str]) -> Optional[datetime]:
    """This week's moment, when the summary is due: on, the moment passed, after it was turned on, not yet told."""
    setting = weekly()
    if not setting["on"]:
        return None
    now = local_now()
    moment = _weekly_moment(now, setting)
    since = _instant(setting["since"])
    if moment > now or (since is not None and since >= moment) or _week_key(moment) in told:
        return None
    return moment


def weekly_next() -> Optional[str]:
    """When the next weekly summary goes, as the panel says it, or None while it is off."""
    setting = weekly()
    if not setting["on"]:
        return None
    conn = get_db()
    try:
        told = _told(conn)
    finally:
        conn.close()
    due = _weekly_due(told)
    if due is None:
        due = _weekly_moment(local_now(), setting)
        if due <= local_now() or _week_key(due) in told:
            due = _weekly_moment(local_now() + timedelta(days=7), setting)
    return due.strftime("%a %d %b, %H:%M")


def collection_words_on() -> bool:
    """Whether the bot may send what it writes from the collection, in the open profile. Off unless turned on."""
    return (_setting(COLLECTION_WORDS_KEY) or "off") == "on"


def morning() -> Dict[str, Any]:
    """The morning idea's setting in the open profile: {on, days, hour, since}. Off, Monday to Friday, 08:00."""
    try:
        held = json.loads(_setting(MORNING_KEY) or "{}")
    except (TypeError, ValueError):
        held = {}
    held = held if isinstance(held, dict) else {}
    days = held.get("days")
    if not (isinstance(days, list) and days and all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6
                                                    for d in days)):
        days = list(MORNING_DAYS)
    return {"on": held.get("on") is True, "days": sorted(set(days)), "hour": _hour(held.get("hour"), MORNING_HOUR),
            "since": held.get("since") if isinstance(held.get("since"), str) else None}


def options() -> Dict[str, Any]:
    """The bot's switches, as the panel shows them."""
    quiet, week, early = quiet_hours(), weekly(), morning()
    return {"replies": replies_on(), "figures": figures_on(), "notify_due": notify_due_on(),
            "notify_24h": notify_24h_on(), "quiet_hours": quiet["on"], "quiet_from": quiet["from"],
            "quiet_to": quiet["to"], "weekly": week["on"], "weekly_day": week["day"], "weekly_hour": week["hour"],
            "collection_words": collection_words_on(), "morning": early["on"], "morning_days": early["days"],
            "morning_hour": early["hour"],
            # Shown beside the bot's button, set in Brand under Writing.
            "angles": writing.preferences()["angles"]}


def save_options(replies: Optional[bool] = None, figures: Optional[bool] = None,
                 notify_due: Optional[bool] = None, notify_24h: Optional[bool] = None,
                 quiet: Optional[bool] = None, quiet_from: Optional[int] = None,
                 quiet_to: Optional[int] = None, weekly_on: Optional[bool] = None,
                 weekly_day: Optional[int] = None, weekly_hour: Optional[int] = None,
                 collection_words: Optional[bool] = None, morning_on: Optional[bool] = None,
                 morning_days: Optional[List[int]] = None, morning_hour: Optional[int] = None) -> Dict[str, Any]:
    """
    Saves the switches the panel sent; a switch not sent is left as it is.
    Quiet hours run from one whole hour to another that differs from it;
    the weekly summary goes on a day (0 is Monday) at a whole hour, and the
    first comes at the first such moment after it is turned on or changed.
    Anything else raises ValueError with the sentence the panel shows, and
    nothing is saved.
    """
    changes = {}
    for key, value in ((REPLIES_KEY, replies), (FIGURES_KEY, figures), (NOTIFY_DUE_KEY, notify_due),
                       (NOTIFY_24H_KEY, notify_24h)):
        if value is not None:
            changes[key] = "on" if value else "off"
    if quiet is not None or quiet_from is not None or quiet_to is not None:
        held = quiet_hours()
        start = held["from"] if quiet_from is None else quiet_from
        end = held["to"] if quiet_to is None else quiet_to
        if _hour(start, -1) < 0 or _hour(end, -1) < 0:
            raise ValueError("Quiet hours run from one whole hour to another, 00:00 to 23:00. Nothing was saved.")
        if start == end:
            raise ValueError("Quiet hours need a start and an end that differ. To have none, untick Hold "
                             "notifications during quiet hours. Nothing was saved.")
        changes[QUIET_KEY] = json.dumps({"on": held["on"] if quiet is None else bool(quiet), "from": start,
                                         "to": end})
    if weekly_on is not None or weekly_day is not None or weekly_hour is not None:
        held = weekly()
        day = held["day"] if weekly_day is None else weekly_day
        hour = held["hour"] if weekly_hour is None else weekly_hour
        if not (isinstance(day, int) and 0 <= day <= 6) or _hour(hour, -1) < 0:
            raise ValueError("The weekly summary goes on a day of the week at a whole hour, 00:00 to 23:00. "
                             "Nothing was saved.")
        changes[WEEKLY_KEY] = json.dumps({"on": held["on"] if weekly_on is None else bool(weekly_on), "day": day,
                                          "hour": hour, "since": local_now().astimezone(timezone.utc).isoformat()})
    if collection_words is not None:
        changes[COLLECTION_WORDS_KEY] = "on" if collection_words else "off"
    if morning_on is not None or morning_days is not None or morning_hour is not None:
        held = morning()
        days = held["days"] if morning_days is None else morning_days
        hour = held["hour"] if morning_hour is None else morning_hour
        if (not isinstance(days, list) or not days
                or not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in days)
                or _hour(hour, -1) < 0):
            raise ValueError("The morning idea comes on one or more days of the week at a whole hour, 00:00 to "
                             "23:00. Nothing was saved.")
        changes[MORNING_KEY] = json.dumps({"on": held["on"] if morning_on is None else bool(morning_on),
                                           "days": sorted(set(days)), "hour": hour,
                                           "since": local_now().astimezone(timezone.utc).isoformat()})
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


def draft_of(record: Optional[Dict[str, Any]]) -> Optional[int]:
    """The id of the draft a message was saved as, which its answer's Undo removes; None for anything else."""
    if not record or record.get("kind") or "raw_content" not in record:
        return None
    try:
        return int(record["id"])
    except (KeyError, TypeError, ValueError):
        return None


def _item(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The collection item a message made, whether it was words (collected) or a link alone (desk_request)."""
    if not record:
        return {}
    if record.get("kind") == "collected":
        return record.get("item") or {}
    if record.get("kind") == "desk_request":
        return record.get("collection_item") or {}
    return {}


def item_of(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    The item a message was collected as, while it is new material: its
    answer carries Undo, and Write it up and the angles when it has words.
    """
    item = _item(record)
    if item.get("kind") not in collection.MATERIAL or item.get("status") != "new":
        return None
    return item


def answer_for(record: Optional[Dict[str, Any]]) -> Optional[str]:
    """The sentence that confirms what became of an accepted message, from what was stored."""
    if not record:
        return None
    if _item(record):
        kind = _item(record).get("kind")
        if kind == "bookmark":
            return SENTENCES["bookmarked"]
        extra = {"post": SENTENCES["post"], "link": SENTENCES["short"]}.get(kind)
        return f"{SENTENCES['collected']} {extra}" if extra else SENTENCES["collected"]
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


def notifications() -> List[Dict[str, Any]]:
    """
    What there is to tell the paired chat, in the open profile, each thing
    once: a queued post that is due, as a count; the latest post's reading
    at about 24 hours, with that reading's own figures; a due post the
    creator asked to be reminded of (Remind me in an hour), again, while it
    is still due; and the weekly summary, once a week. Marks what it
    returns as told. Counts and the creator's own figures only. Each is
    {text, due}: due names the due posts a message's Remind me in an hour
    and Done are about, or is None.
    """
    due_on, day_on, week_on, early_on = notify_due_on(), notify_24h_on(), weekly()["on"], morning()["on"]
    conn = get_db()
    try:
        if not due_on:
            # Unticked, no reminder comes either.
            conn.execute("DELETE FROM settings WHERE key = ?", (REMIND_KEY,))
            conn.commit()
        if not (due_on or day_on or week_on or early_on):
            return []
        try:
            from . import post_identity
        except ImportError:
            import post_identity
        told = _told(conn)
        said: List[Dict[str, Any]] = []
        newly: List[str] = []
        if due_on:
            due_now = [f"due:{r['id']}:{r['scheduled_for']}" for r in conn.execute(
                "SELECT id, scheduled_for FROM posts WHERE status = 'due' ORDER BY scheduled_for")]
            fresh = [key for key in due_now if key not in told]
            if fresh:
                said.append({"text": SENTENCES["due_one"] if len(fresh) == 1
                             else SENTENCES["due_many"].format(count=len(fresh)), "due": fresh})
                newly += fresh
            said += _reminders_due(conn, set(due_now))
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
                    said.append({"text": f"Your latest post at about 24 hours: {', '.join(counts)}, read {where}.",
                                 "due": None})
                    newly.append(key)
        week = _weekly_due(told) if week_on else None
        if week is not None:
            said.append({"text": weekly_summary(conn, week), "due": None})
            newly.append(_week_key(week))
        idea = _morning_idea(conn, told) if early_on else None
        if idea is not None:
            key, offered = idea
            newly.append(key)
            if offered:
                said.append(offered)
        if newly:
            _mark_told(conn, told + newly)
        return said
    finally:
        conn.close()


def _morning_due(told: List[str]) -> Optional[str]:
    """Today's key when the morning idea is due: on, a chosen day, its hour passed, after it was set, not told today."""
    setting = morning()
    if not setting["on"]:
        return None
    now = local_now()
    if now.weekday() not in setting["days"]:
        return None
    moment = datetime.combine(now.date(), day_time(hour=setting["hour"])).astimezone()
    since = _instant(setting["since"])
    key = f"morning:{now.date().isoformat()}"
    if now < moment or (since is not None and since >= moment) or key in told:
        return None
    return key


def opening_form(conn) -> Optional[str]:
    """
    The form of the opening line of the creator's post that did best
    against their usual (the voice pack's first opener), read locally:
    question, story, short or statement. None when the studio cannot say.
    """
    try:
        try:
            from . import voice_pack
        except ImportError:
            import voice_pack
        openers = voice_pack._openers(conn, 1)
    except Exception:
        return None
    line = (openers[0] if openers else "").strip()
    if not line:
        return None
    words = line.split()
    if line.endswith("?"):
        return "question"
    if words[0].lower().strip(",.") in ("i", "i'm", "i've", "my", "we", "our", "last", "yesterday", "when"):
        return "story"
    if len(words) <= 6:
        return "short"
    return "statement"


def _morning_idea(conn, told: List[str]) -> Optional[Tuple[str, Optional[Dict[str, Any]]]]:
    """
    The morning idea, when it is due: one unused item from the collection,
    the one offered least recently, with an angle from what worked in the
    creator's own posts, both as their sources allow. It carries the
    creator's words, so it goes only with the switch that lets the bot send
    them. Returns (today's key, the message or None): a day with nothing to
    offer is marked told all the same, so nothing comes later that day.
    """
    key = _morning_due(told)
    if key is None or not collection_words_on():
        return None
    sources = writing.preferences(conn)["sources"]
    item = collection.least_offered(conn) if "collection" in sources else None
    if item is None:
        return key, None
    form = opening_form(conn) if "posts" in sources else None
    text = SENTENCES["morning"] + "\n\n" + _first_line(item["text"])
    if form:
        text += "\n\n" + SENTENCES[f"angle_{form}"]
    collection.offered(conn, item["id"])
    return key, {"text": text, "due": None, "morning": {"item": item["id"], "form": form}}


def _reminders_due(conn, due_now) -> List[Dict[str, Any]]:
    """
    The reminders asked for with Remind me in an hour whose hour is up: each
    told again for the posts in it that are still due, and forgotten either
    way. A post posted, moved or deleted in the meantime is not told again.
    """
    reminders = _read_json(conn, REMIND_KEY, [])
    now = datetime.now(timezone.utc)
    waiting, said = [], []
    for reminder in reminders:
        if not isinstance(reminder, dict):
            continue
        at = _instant(reminder.get("at"))
        if at is not None and at > now:
            waiting.append(reminder)
            continue
        still = [key for key in (reminder.get("due") or []) if key in due_now]
        if still:
            said.append({"text": SENTENCES["due_again_one"] if len(still) == 1
                         else SENTENCES["due_again_many"].format(count=len(still)), "due": still})
    if len(waiting) != len(reminders):
        _write_json(conn, REMIND_KEY, waiting)
    return said


# ---------------------------------------------------------------------------
# Buttons: Undo under a saved draft, Remind me in an hour and Done under a
# due post. Each acts on the studio's own records, once, for the paired chat
# ---------------------------------------------------------------------------

_BUTTONS_LOCK = threading.Lock()


def _read_json(conn, key: str, default: Any) -> Any:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    try:
        value = json.loads(row["value"]) if row and row["value"] else default
    except (TypeError, ValueError):
        value = default
    return value if isinstance(value, type(default)) else default


def _write_json(conn, key: str, value: Any) -> None:
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
            (key, json.dumps(value)))


def _label(letter: str) -> str:
    if letter == "a":
        return f"{writing.preferences()['angles']} angles"
    if letter.isdigit():
        return f"Write up {letter}"
    return BUTTON_LABELS[letter]


def issue_buttons(chat_id: Any, kind: str, said: str, rows: Optional[List[List[str]]] = None,
                  **target: Any) -> Dict[str, Any]:
    """
    Keeps what the buttons on one message do, in the open profile, and
    returns the message's inline keyboard. kind is "undo" (target: draft, a
    draft id), "item" or "item_bare" (target: item, a collection item),
    "due" (target: due, the due posts' keys), "angles" (target: item and the
    angles offered) or "morning" (target: item and the angle's form). Each
    button's data is the message's opaque id and the button's letter, and
    nothing else.
    """
    rows = [list(row) for row in (rows or BUTTON_ROWS[kind])]
    token = secrets.token_urlsafe(9)
    record = {"id": token, "kind": kind, "chat": str(chat_id), "at": _now(), "said": said, "used": None,
              "letters": [letter for row in rows for letter in row]}
    record.update(target)
    with _BUTTONS_LOCK:
        conn = get_db()
        try:
            records = [r for r in _read_json(conn, BUTTONS_KEY, []) if isinstance(r, dict)]
            records.append(record)
            _write_json(conn, BUTTONS_KEY, records[-max(1, int(BUTTONS_KEPT)):])
        finally:
            conn.close()
    return {"inline_keyboard": [[{"text": _label(letter), "callback_data": f"{token}.{letter}"}
                                 for letter in row] for row in rows]}


def press(data: Any, chat_id: Any) -> Dict[str, Any]:
    """
    A press of one of the bot's buttons, from the paired chat, in the open
    profile. Returns {key, answer, edit, job}: the notice the phone shows,
    the message's text to put in its place, its buttons gone, or None to
    take only the buttons away (an old button, one already used), and what
    is to be written beside the bot's loop, if anything (run_job). Acts once.
    """
    token, _dot, letter = str(data or "").partition(".")
    with _BUTTONS_LOCK:
        conn = get_db()
        try:
            records = [r for r in _read_json(conn, BUTTONS_KEY, []) if isinstance(r, dict)]
            record = next((r for r in records if token and r.get("id") == token), None)
            letters = record.get("letters") if record else None
            if letters is None and record:
                # Kept before buttons named their own letters (2.11.0).
                letters = [x for row in BUTTON_ROWS.get(record.get("kind"), ()) for x in row]
            if record is None or record.get("chat") != str(chat_id) or letter not in (letters or ()):
                return {"key": "button_old", "answer": SENTENCES["button_old"], "edit": None}
            if record.get("used"):
                return {"key": "button_used", "answer": SENTENCES["button_used"], "edit": None}
            job = None
            if letter in ("w", "a") or letter.isdigit():
                # Something to write: never in the bot's loop, and only with a provider.
                if not writing.model_gateway.get_current_ai_config().is_configured:
                    key = "no_provider"
                elif letter == "a":
                    key, job = "finding_angles", {"kind": "angles", "item": record.get("item")}
                else:
                    angles = record.get("angles") or []
                    angle = angles[int(letter) - 1] if letter.isdigit() and int(letter) <= len(angles) else None
                    key, job = "writing", {"kind": "write", "item": record.get("item"), "angle": angle,
                                           "form": record.get("form")}
            elif letter == "n":
                key = "not_today"
            elif letter == "u" and record.get("kind") in ("item", "item_bare"):
                key = collection.undo(record.get("item"))
            elif letter == "u":
                key = _undo(conn, record.get("draft"))
            elif letter == "r":
                key = _remind(conn, record.get("due") or [])
            else:
                # Done: the reminder is cleared, and that is all. The post
                # stays due; nothing is marked as posted, and nothing is
                # asked of LinkedIn.
                key = "done"
            record["used"] = _now()
            _write_json(conn, BUTTONS_KEY, records)
        finally:
            conn.close()
    said = str(record.get("said") or "")
    edit = f"{said}\n\n{SENTENCES[key]}" if said else SENTENCES[key]
    return {"key": key, "answer": SENTENCES[key], "edit": edit, "job": job}


def _first_line(text: str) -> str:
    return next((line.strip() for line in (text or "").splitlines() if line.strip()), "")[:300]


def run_job(job: Dict[str, Any], chat_id: Any) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    What a press asked to be written, in the open profile, beside the bot's
    loop: Write it up (a draft, from an angle or a morning idea's form when
    it has one) or the angles. Returns the bot's next message and its
    buttons. The written words go only with the switch "The bot may send me
    what it writes from my collection"; otherwise it says only that it is done.
    """
    try:
        if job.get("kind") == "angles":
            result = writing.angles(job.get("item"))
        else:
            result = writing.make_post([job.get("item")], angle=job.get("angle"), form=job.get("form"))
    except (writing.Refused, LookupError):
        return SENTENCES["write_failed"], None
    except writing.ProviderError:
        return SENTENCES["write_failed"], None
    status = result.get("status")
    if status == "no_provider":
        return SENTENCES["no_provider"], None
    if status == "refused":
        return SENTENCES["write_refused"], None
    words = collection_words_on()
    if job.get("kind") == "angles":
        offered = result.get("angles") or []
        if not words:
            return SENTENCES["angles_ready"].format(count=len(offered)), None
        text = SENTENCES["angles_here"] + "\n\n" + "\n".join(f"{n}. {line}" for n, line in enumerate(offered, 1))
        rows = [[str(n)] for n in range(1, len(offered) + 1)]
        return text, issue_buttons(chat_id, "angles", text, rows=rows, item=job.get("item"), angles=offered)
    if not words:
        return SENTENCES["draft_ready"], None
    return SENTENCES["draft_ready_words"] + "\n\n" + _first_line(result.get("content") or ""), None


def _undo(conn, draft_id: Any) -> str:
    """
    Removes a draft the phone saved, only while it is untouched in the
    studio: still a draft, its text, tags and media as the bot saved them,
    never queued, published or bound to a post on LinkedIn. One conditional
    delete, so an edit made a moment earlier keeps the draft.
    """
    try:
        draft_id = int(draft_id)
    except (TypeError, ValueError):
        return "undo_gone"
    post_id = f"post-draft-{draft_id}"
    draft = conn.execute("SELECT raw_content, tags, status FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    held = conn.execute("SELECT 1 FROM posts WHERE id = ? AND draft_id = ?", (post_id, draft_id)).fetchone()
    if draft is None or held is None:
        return "undo_gone"
    if draft["status"] != "DRAFT":
        return "undo_changed"
    with conn:
        removed = conn.execute(
            "DELETE FROM posts WHERE id = ? AND draft_id = ? AND status = 'draft' AND content = ? "
            "AND scheduled_for IS NULL AND published_at IS NULL AND activity_urn IS NULL "
            "AND COALESCE(media_urls, '') IN ('', '[]') AND COALESCE(tags, '') = ?",
            (post_id, draft_id, draft["raw_content"], draft["tags"] or "")).rowcount
        if removed:
            conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
            # The collection recorded the draft; taken back, it goes too.
            collection.forget_draft(conn, post_id)
    if removed:
        changes.publish("collection")
    return "undone" if removed else "undo_changed"


def _remind(conn, due: List[str]) -> str:
    """Remind me in an hour: the due posts are told again then, if they are still due."""
    reminders = [r for r in _read_json(conn, REMIND_KEY, []) if isinstance(r, dict)]
    at = datetime.now(timezone.utc) + timedelta(seconds=float(REMIND_AFTER_SECONDS))
    reminders.append({"due": [str(key) for key in due], "at": at.isoformat()})
    _write_json(conn, REMIND_KEY, reminders[-REMIND_KEPT:])
    return "remind_set"
