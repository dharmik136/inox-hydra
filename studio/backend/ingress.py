"""
Ubiquitous Telegram Ingress Daemon & Mobile Message Parser.
===========================================================
Handles outbound long-polling to api.telegram.org (zero inbound ports),
parses structured and unstructured creator thoughts, and persists into
SQLite WAL.

What the phone can send (cycle 4, programme item 24): text, which becomes a
draft as it always did, and a LinkedIn post link, which becomes a desk
request (desk_requests.py) that Today surfaces as the page to open at this
computer. The phone sends a link, never a figure: nothing it says is written
as a reading, and the extension reads the real page at the desk.

A short link, which the LinkedIn app's Copy link gives (lnkd.in/p/<code>),
names no post, and the studio never fetches it. It is a post sent from the
phone all the same: a desk request holding the short link, never a draft,
which Today opens in the creator's own browser (2.10.1).

Strict Invariants:
- Zero open inbound ports (pure outbound HTTP long-polling).
- Zero em-dashes in any generated or parsed text.
- Nothing from the phone is a figure.
"""

from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import logging
import os
import re
import requests
from urllib.parse import unquote

try:  # the shared egress chokepoint
    from . import egress as _egress
except ImportError:
    import egress as _egress
import threading
import time

try:
    from .database import get_db, create_draft, get_draft
    from . import (collection, desk_requests, paths, phone_media, post_identity, remembered, secret_settings,
                   telegram_bot)
except ImportError:
    from database import get_db, create_draft, get_draft
    import collection
    import desk_requests
    import paths
    import phone_media
    import remembered
    import post_identity
    import secret_settings
    import telegram_bot

# The bot, set up per profile in Brand Studio's Local security tab (cycle 4,
# decision D6). The token is a secret setting, sealed at rest like the AI key
# and never answered back; the chat id is the creator's own and is not.
SETTINGS_TOKEN_KEY = "telegram_bot_token"
SETTINGS_CHAT_KEY = "telegram_chat_id"
# A bot token as BotFather issues one: the bot's number, a colon, a secret.
TOKEN_SHAPE = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{20,}$")
# Your own chat with the bot: a positive integer. A group's id is negative,
# and any member of the group could then file drafts, so it is refused.
CHAT_ID_SHAPE = re.compile(r"^\d{1,20}$")
# When a message from the chat saved in a profile was first saved there, so
# the panel can stop saying it has not been seen working. Removed whenever
# the chat id changes: a message from one chat says nothing about another.
SETTINGS_HEARD_KEY = "telegram_chat_heard_at"
# When the chat saved in a profile was paired there (phase 4): what was saved
# from Telegram before it came from another chat, so it does not count as
# seen working for this one. A chat paired before this was kept has none, and
# then anything saved from Telegram counts, since only the paired chat's
# messages are ever saved. Removed with the bot.
SETTINGS_PAIRED_KEY = "telegram_chat_paired_at"
# The ingress met the real Telegram service on the owner's install on
# 2026-10-28: polling worked, a chat that was not the one saved was refused,
# and once the right chat was paired its message was saved. On another
# computer the panel says this until a message from its own chat is saved.
NOT_YET_TESTED = ("Not yet seen working on this computer: no message from your own chat has been saved here. "
                  "Send your bot a message to check.")

# Telegram never shows a creator their chat id, so the bot can be saved with
# its token alone, and the chats it refused say who wrote: the last few, in
# memory only and never stored (the log keeps a refused chat's id, never its
# text), each with how many messages, when, and the first characters of the
# first one, for the panel to ask "Is that you?". Pairing is the creator's
# press; nothing here pairs a chat by itself.
REFUSED_CHATS_KEPT = 5
REFUSED_START_CHARS = 60

# A LinkedIn address in a message. The app's share menu writes
# /posts/<slug>-activity-<id>-<suffix> with tracking parameters; the feed
# writes /feed/update/urn:li:activity:<id>/. post_identity.extract_activity_urn
# reads both.
LINKEDIN_URL = re.compile(r"https?://(?:[a-z]{1,3}\.)?linkedin\.com/[^\s<>\"']+", re.IGNORECASE)
# The app's Copy link: an lnkd.in short link, whose code names nothing the
# studio can resolve without fetching it, which it never does. Kept as its
# address alone: the host lower-cased, the code exactly as written (its case
# is part of it), with no query, fragment or punctuation after it.
SHORT_LINK = re.compile(r"\bhttps?://lnkd\.in(/[A-Za-z0-9_\-/]{1,80})", re.IGNORECASE)
SHORT_LINK_HOST = "lnkd.in"

MAX_UPDATE_ATTEMPTS = 3

# What says a message was forwarded. The text of a forward is kept as the
# creator's note (phase 3); who or what it came from (a person, an account,
# a channel, a signature) is never read past this check, and never kept.
FORWARD_FIELDS = ("forward_origin", "forward_from", "forward_from_chat", "forward_sender_name", "forward_date",
                  "forward_signature", "is_automatic_forward")

# What the studio asks Telegram for: the messages sent to the bot, and the
# presses of its buttons. Telegram keeps the kinds a bot last asked for, so
# a bot another program once set to messages alone would never hear a press
# unless the poll names both; and nothing else (an edited message, a channel
# post) is delivered to be confirmed unread.
ALLOWED_UPDATES = ("message", "callback_query")

logger = logging.getLogger("studio.ingress")

# Fold limits per Day 01 spec
try:
    from .fold import MOBILE_FOLD_CHARS, MOBILE_FOLD_LINES
except ImportError:
    from fold import MOBILE_FOLD_CHARS, MOBILE_FOLD_LINES

MOBILE_FOLD_CHAR_LIMIT = MOBILE_FOLD_CHARS
MOBILE_FOLD_LINE_LIMIT = MOBILE_FOLD_LINES
BLANK_LINE_EQUIVALENT_CHARS = 45


class IngressMessageParser:
    """Parses raw text and structured creator instructions from mobile messaging."""

    @staticmethod
    def calculate_fold_metrics(text: Any) -> Dict[str, Any]:
        """Calculates deterministic mobile fold lines (3 lines or 140 characters).
        
        Blank lines count as 45 characters.
        """
        if text is None:
            safe_text = ""
        elif not isinstance(text, str):
            safe_text = str(text)
        else:
            safe_text = text

        safe_text = safe_text[:50000]
        lines = safe_text.splitlines()
        char_count = 0
        fold_line_index = -1
        fold_char_index = -1

        for i, line in enumerate(lines):
            effective_len = BLANK_LINE_EQUIVALENT_CHARS if line.strip() == "" else len(line)
            char_count += effective_len

            if i >= MOBILE_FOLD_LINE_LIMIT or char_count >= MOBILE_FOLD_CHAR_LIMIT:
                fold_line_index = i
                fold_char_index = char_count
                break

        return {
            "total_chars": len(safe_text),
            "lines_count": len(lines),
            "is_pre_fold_safe": fold_line_index == -1 and char_count <= MOBILE_FOLD_CHAR_LIMIT,
            "pre_fold_chars": char_count if fold_char_index == -1 else fold_char_index,
            "lines_above_fold": len(lines) if fold_line_index == -1 else fold_line_index,
        }

    @classmethod
    def parse_message(cls, raw_text: Any, links: bool = True) -> Dict[str, Any]:
        """
        Extracts intent, content, scheduling directives, and tags from incoming message.
        With links=False (/idea) a link is part of the text, never a request.
        """
        if raw_text is None:
            text = ""
        elif not isinstance(raw_text, str):
            text = str(raw_text)
        else:
            text = raw_text

        # Sanitize em-dash characters dynamically to preserve the zero em-dash rule
        em_dash = chr(0x2014)
        en_dash = chr(0x2013)
        sanitized_text = text.replace(em_dash, " -- ").replace(en_dash, "-")

        cleaned = sanitized_text.strip()[:50000]
        archetype = "Direct"
        tags = ["mobile-ingress"]
        schedule_target: Optional[str] = None
        content = cleaned

        # Check for command prefixes
        lower = cleaned.lower()
        if lower.startswith("read:"):
            # "read: <post link>": the desk is asked to read that post's
            # analytics. Any text beside the link is kept as a draft.
            archetype = "Draft"
            tags.append("read")
            content = cleaned[5:].strip()
        elif lower.startswith("draft:"):
            archetype = "Draft"
            content = cleaned[6:].strip()
        elif lower.startswith("idea:"):
            archetype = "Raw Idea"
            tags.append("idea")
            content = cleaned[5:].strip()
        elif lower.startswith("schedule"):
            match = re.match(r"^schedule\s+([\w\s:\-]+)[:|]\s*(.*)$", cleaned, re.IGNORECASE)
            if match:
                schedule_target = match.group(1).strip()[:100]
                content = match.group(2).strip()
                archetype = "Scheduled Post"
                tags.append("scheduled")

        # A LinkedIn post link becomes a desk request; the first one that
        # names a post is the request, and it leaves the text. A link that
        # names no post (a short link, a profile) stays in the text, so the
        # message is kept whole as a draft rather than lost.
        read_request: Optional[Dict[str, Any]] = None
        for url in (LINKEDIN_URL.findall(content) if links else ()):
            # A link copied with its colons encoded (urn%3Ali%3Aactivity) names the same post.
            urn = post_identity.extract_activity_urn(unquote(url))
            if urn:
                read_request = {"url": url, "activity_urn": urn}
                content = re.sub(r"[ \t]{2,}", " ", content.replace(url, " ")).strip()
                break
        # A short link is a post sent from the phone, alone or with text
        # around it: the request, and never a draft. The text around it is
        # the share sheet's or a note on the post, not a post idea.
        if read_request is None and links:
            short = SHORT_LINK.search(content)
            if short:
                link = "https://" + SHORT_LINK_HOST + short.group(1).rstrip("/")
                read_request = {"url": link, "activity_urn": None, "short_link": link}
                content = ""

        # Extract hashtags from text (capped to 30 unique tags, max 50 chars each)
        raw_hashtags = re.findall(r"#(\w+)", content)
        if raw_hashtags:
            tags.extend([h[:50] for h in raw_hashtags[:30]])

        # Generate title from the first non-empty line (truncated to 60 chars)
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        title = lines[0][:60] if lines else "Untitled Mobile Ingress"
        if read_request and not lines:
            title = "A post sent from the phone" if read_request.get("short_link") else "Read request from the phone"

        metrics = cls.calculate_fold_metrics(content)

        return {
            "title": title,
            "raw_content": content,
            "formatted_content": content,
            "archetype": archetype,
            "tags": sorted(list(set(tags))),
            "schedule_target": schedule_target,
            "char_count": metrics["total_chars"],
            "lines_above_fold": metrics["lines_above_fold"],
            "pre_fold_chars": metrics["pre_fold_chars"],
            "is_pre_fold_safe": metrics["is_pre_fold_safe"],
            # {"url", "activity_urn"} when the message carried a post link.
            "read_request": read_request,
        }


class TelegramIngressDaemon:
    """Outbound long-polling worker for Telegram Bot API with zero open ports."""

    # How long stop_worker waits for the loop to finish. A poll can be waiting
    # on Telegram for up to 30 seconds, so the loop is told to stop rather
    # than waited for, and a loop that outlives this wait stops after its poll.
    STOP_JOIN_SECONDS = 3.0

    def __init__(
        self,
        bot_token: Optional[str] = None,
        authorized_chat_id: Optional[str] = None,
    ):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "") or os.environ.get("PRUDENT_TELEGRAM_BOT_TOKEN", "")
        self.authorized_chat_id = authorized_chat_id or os.environ.get("TELEGRAM_CHAT_ID", "") or os.environ.get("PRUDENT_TELEGRAM_CHAT_ID", "")
        # Where the token came from: "environment" (a maintainer, dev mode),
        # "settings" (the Local security tab), or None. apply_settings only
        # ever stops a worker it started itself.
        self.configured_from: Optional[str] = "environment" if self.bot_token else None
        # The creator profile a bot from the settings belongs to. Its messages
        # are saved there whichever profile is open, so one creator's phone
        # never files a draft in another creator's studio. None for a
        # maintainer's bot from the environment, which saves to the open one.
        self.profile_id: Optional[str] = None
        self.is_running = False
        self._stop_event = threading.Event()
        self.last_update_id = 0
        self._thread: Optional[threading.Thread] = None
        self.base_delay = 2.0
        self.max_delay = 60.0
        self.quiet_delay = 120.0
        self.quiet_hours_start = 23  # 11:00 PM
        self.quiet_hours_end = 6     # 6:00 AM
        self.current_delay = 2.0
        self.consecutive_errors = 0

        # A deadline, on the monotonic clock, before which Telegram has asked
        # us not to poll. Held separately from consecutive_errors because a 429
        # is not a failure to reach the server, it is the server answering with
        # an instruction. Treating it as an error would double the delay on a
        # ladder Telegram never asked for; treating it as a success, which is
        # what used to happen, threw the instruction away entirely.
        self.rate_limited_until = 0.0

        # update_id -> how many times processing it has failed. Bounded so a
        # message that can never be handled does not block the ones behind it.
        self._failed_updates = {}
        self.total_polls = 0
        # The last poll was answered with an error (not a 429, which has its
        # own deadline): the loop backs off as from a network fault.
        self.poll_failed = False
        self.total_messages_processed = 0
        self.last_poll_at: Optional[str] = None
        self.last_error: Optional[str] = None
        # chat id -> {chat_id, count, first_at, last_at, first}: the chats
        # refused since this bot was set, newest last, in memory only.
        self.refused_chats: Dict[str, Dict[str, Any]] = {}
        # What the bot says back (telegram_bot.py): waiting replies, and when
        # each refused chat was last answered.
        self.outbox = telegram_bot.Outbox()
        self._answered_refusals: Dict[str, float] = {}
        self._last_notify_check = 0.0
        # Phase 4, item 2: the last successful check (a getUpdates Telegram
        # answered), on the wall clock, which goes on while a computer sleeps;
        # the one before the batch being handled, for /status; and when the
        # last check was last written to the bot's profile.
        self.last_ok_at: Optional[datetime] = None
        self.previous_ok_at: Optional[datetime] = None
        self._checked_written_at: Optional[datetime] = None

    def configure(self, bot_token: str, authorized_chat_id: str, origin: Optional[str],
                  profile_id: Optional[str] = None) -> None:
        """
        Points the worker at a bot, and at the profile its messages belong
        to. The loop reads these on every poll, so a running worker follows a
        change without a restart; the error ladder starts again, because the
        old errors were the old bot's.
        """
        token = bot_token or ""
        if token != self.bot_token:
            # Update ids are each bot's own, and Telegram treats every update
            # below the offset as confirmed. Carried from one bot to another,
            # the old offset confirmed the new bot's waiting messages unread.
            self.last_update_id = 0
            self._failed_updates = {}
            # Who wrote to the old bot says nothing about who writes to this one,
            # and its replies are not this bot's to send.
            self.refused_chats = {}
            self.outbox.clear()
            self._answered_refusals = {}
            # Another bot's last check says nothing about this one's messages.
            self.last_ok_at = None
            self.previous_ok_at = None
            self._checked_written_at = None
        self.bot_token = token
        self.authorized_chat_id = authorized_chat_id or ""
        # A chat now saved is no longer asked about.
        self.refused_chats.pop(str(self.authorized_chat_id), None)
        self.configured_from = origin if self.bot_token else None
        self.profile_id = profile_id if self.bot_token else None
        self.consecutive_errors = 0
        self.rate_limited_until = 0.0
        self.last_error = None
        if self.last_ok_at is None and self.configured_from == "settings" and self.profile_id:
            # A restart: the last check this bot's profile kept, so a day the
            # studio was off is noticed at its first check.
            try:
                with self._bots_profile():
                    self.last_ok_at = telegram_bot.last_checked()
            except Exception:
                self.last_ok_at = None

    def _note_check(self, now: datetime) -> None:
        """
        A successful check: kept in memory at once, and in the bot's profile
        at most once a minute, or at once when it comes more than a day after
        the one before, which is then kept as the gap's notice (phase 4).
        Never raises: the check itself went well.
        """
        before = self.last_ok_at
        self.previous_ok_at = before
        self.last_ok_at = now
        if not (self.configured_from == "settings" and self.profile_id):
            return
        gap = before is not None and (now - before).total_seconds() > telegram_bot.TELEGRAM_KEEPS_HOURS * 3600
        written = self._checked_written_at
        if not gap and written is not None and (now - written).total_seconds() < telegram_bot.CHECKED_WRITTEN_EVERY_SECONDS:
            return
        try:
            with self._bots_profile():
                telegram_bot.note_checked(now, before if gap else None)
            self._checked_written_at = now
        except Exception as error:
            logger.warning("The time of the last check could not be kept: %s", type(error).__name__)

    def _keep_last_check(self) -> None:
        """When the worker stops: the last check as it was, so a restart measures from it."""
        if self.last_ok_at is None or not (self.configured_from == "settings" and self.profile_id):
            return
        if self._checked_written_at is not None and self._checked_written_at >= self.last_ok_at:
            return
        try:
            with self._bots_profile():
                telegram_bot.note_checked(self.last_ok_at)
            self._checked_written_at = self.last_ok_at
        except Exception as error:
            logger.warning("The time of the last check could not be kept: %s", type(error).__name__)

    def is_quiet_hours(self, current_time: Optional[datetime] = None) -> bool:
        """
        The poller's night pace: whether the time falls in the low-power night
        window (23:00 to 06:00), when the studio asks Telegram less often.
        Not the bot's quiet hours (telegram_bot.in_quiet_hours), the creator's
        setting, which hold only notifications and never change this pace.
        """
        now = current_time or datetime.now()
        hour = now.hour
        if self.quiet_hours_start > self.quiet_hours_end:
            return hour >= self.quiet_hours_start or hour < self.quiet_hours_end
        return self.quiet_hours_start <= hour < self.quiet_hours_end

    def calculate_next_poll_interval(self, current_time: Optional[datetime] = None, has_error: bool = False) -> float:
        """
        Calculates adaptive polling delay.
        - Quiet hours: 120.0s sleep to conserve battery/CPU when creator is asleep.
        - Network errors: Exponential backoff doubling delay up to max_delay (60.0s).
        - Normal daytime operation: 2.0s responsive polling.
        """
        # An outstanding rate limit outranks everything below, including the
        # quiet hours branch. Checked first because the whole point is that
        # nothing else is allowed to shorten it.
        remaining = self.rate_limited_until - time.monotonic()
        if remaining > 0:
            self.current_delay = remaining
            return remaining

        if has_error:
            self.consecutive_errors += 1
            delay = min(self.max_delay, self.base_delay * (2 ** min(self.consecutive_errors, 6)))
            self.current_delay = delay
            return delay

        self.consecutive_errors = 0
        if self.is_quiet_hours(current_time):
            self.current_delay = self.quiet_delay
            return self.quiet_delay

        self.current_delay = self.base_delay
        return self.base_delay

    def _remember_refusal(self, chat_id: str, message: Dict[str, Any]) -> None:
        """One more message refused from this chat, kept in memory for the panel's "Is that you?"."""
        if not chat_id:
            return
        now = datetime.now(timezone.utc).isoformat()
        held = self.refused_chats.pop(chat_id, None)
        if held is None:
            text = message.get("text")
            if isinstance(text, str) and text.strip():
                first = " ".join(text.split())[:REFUSED_START_CHARS]
            elif message.get("callback_query"):
                first = "a button press"
            else:
                first = "a voice note" if "voice" in message else "a message with no text"
            held = {"chat_id": chat_id, "count": 0, "first_at": now, "first": first}
        held["count"] += 1
        held["last_at"] = now
        # Newest last; the oldest goes when there are more than a few.
        self.refused_chats[chat_id] = held
        while len(self.refused_chats) > REFUSED_CHATS_KEPT:
            self.refused_chats.pop(next(iter(self.refused_chats)))

    def _bots_profile(self):
        """The bot's own profile to read its switches in, or the open one for a maintainer's bot."""
        if self.profile_id and self.profile_id in paths.profile_ids():
            return paths.using_profile(self.profile_id)
        return nullcontext()

    def _reply(self, chat_id: str, text: Optional[str], always: bool = False,
               draft_id: Optional[int] = None, item: Optional[Dict[str, Any]] = None,
               fact_id: Optional[int] = None) -> None:
        """
        Queues one of the bot's fixed sentences for a chat: a confirmation when
        the bot confirms messages, and an answer to a question (always) in any
        case. A confirmation of a saved draft, or of an item kept in the
        collection, carries Undo, which takes it back.
        """
        if not text or not chat_id or not self.bot_token:
            return
        if not always:
            try:
                with self._bots_profile():
                    if not telegram_bot.replies_on():
                        return
            except Exception:
                return
        if draft_id is not None:
            keyboard = self._buttons(chat_id, text, "undo", draft=draft_id)
        elif fact_id is not None:
            keyboard = self._buttons(chat_id, text, "fact", fact=fact_id)
        elif item is not None:
            # Something to write from: Write it up and the angles; a link alone: Undo only.
            kind = "item" if (item.get("text") or "").strip() else "item_bare"
            keyboard = self._buttons(chat_id, text, kind, item=item["id"])
        else:
            keyboard = None
        self.outbox.put(chat_id, text, keyboard)

    def _start_job(self, job: Dict[str, Any], chat_id: str) -> None:
        """
        What a press asked to be written (telegram_bot.run_job), on a thread of
        its own in the bot's profile, never in the polling loop: a provider
        can take its time, and the bot answers everything else meanwhile.
        When it is done the bot sends a new message, which the phone notifies.
        """
        profile = self.profile_id

        def run() -> None:
            try:
                pinned = profile if profile and profile in paths.profile_ids() else None
                with (paths.using_profile(pinned) if pinned else nullcontext()):
                    text, keyboard = telegram_bot.run_job(job, chat_id)
            except Exception as error:
                logger.warning("Writing from the collection failed: %s", type(error).__name__)
                text, keyboard = telegram_bot.SENTENCES["write_failed"], None
            self.outbox.put(chat_id, text, keyboard)
            self.flush_replies()

        threading.Thread(target=run, daemon=True, name="TelegramCollectionWriting").start()

    def _buttons(self, chat_id: str, text: str, kind: str, **target: Any) -> Optional[Dict[str, Any]]:
        """A message's buttons, kept in the bot's profile; None if they cannot be kept (the message goes anyway)."""
        try:
            with self._bots_profile():
                return telegram_bot.issue_buttons(chat_id, kind, text, **target)
        except Exception as error:
            logger.warning("A message goes without its buttons: %s", type(error).__name__)
            return None

    def _answer_refusal(self, chat_id: str, key: str, callback_id: Optional[str] = None) -> None:
        """
        A refused chat is told why, at most once in a while, so a stranger
        cannot make the bot talk on: in a message, or for a button press in
        the notice the phone shows, never a message of its own.
        """
        now = time.monotonic()
        last = self._answered_refusals.get(chat_id)
        if last is not None and now - last < telegram_bot.REFUSAL_REPLY_EVERY_SECONDS:
            return
        self._answered_refusals[chat_id] = now
        # Bounded like the refused chats themselves.
        while len(self._answered_refusals) > 4 * REFUSED_CHATS_KEPT:
            self._answered_refusals.pop(next(iter(self._answered_refusals)))
        said = telegram_bot.SENTENCES[key].format(chat_id=chat_id)
        if not callback_id:
            self._reply(chat_id, said)
            return
        try:
            with self._bots_profile():
                if not telegram_bot.replies_on():
                    return
        except Exception:
            return
        self.outbox.put_call("answerCallbackQuery", {"callback_query_id": callback_id, "text": said})

    def check_notifications(self) -> None:
        """
        Between polls: what the creator asked to be told (telegram_bot's
        notifications, each opt-in), to the paired chat of a bot set up in a
        profile, except during the creator's quiet hours, when they wait.
        Never raises: a notification is never worth a lost poll.
        """
        if not (self.bot_token and self.authorized_chat_id and self.configured_from == "settings"):
            return
        if time.monotonic() - self._last_notify_check < telegram_bot.NOTIFY_EVERY_SECONDS:
            return
        self._last_notify_check = time.monotonic()
        chat = self.authorized_chat_id
        try:
            with self._bots_profile():
                # Quiet hours: nothing is looked at, so nothing is marked as
                # told, and everything waiting goes at the first check after.
                if telegram_bot.in_quiet_hours():
                    return
                # A day not checked (phase 4): told once, whatever the
                # notification switches say, and before anything else.
                gap = telegram_bot.gap_to_tell()
                said = ([{"text": gap, "due": None}] if gap else []) + telegram_bot.notifications()
        except Exception as error:
            logger.warning("The bot's notifications could not be read: %s", type(error).__name__)
            return
        for item in said:
            # A due post's message carries Remind me in an hour and Done; the
            # morning idea, Write it up and Not today.
            if item.get("due"):
                keyboard = self._buttons(chat, item["text"], "due", due=item["due"])
            elif item.get("morning"):
                keyboard = self._buttons(chat, item["text"], "morning", **item["morning"])
            else:
                keyboard = None
            self.outbox.put(chat, item["text"], keyboard)
        if said:
            self.flush_replies()

    def flush_replies(self) -> None:
        """Sends the bot's waiting replies. Never raises: a reply is never worth a lost poll."""
        try:
            self.outbox.flush(self.bot_token)
        except Exception as error:
            logger.warning("The bot's replies could not be sent: %s", type(error).__name__)

    def refused(self) -> List[Dict[str, Any]]:
        """The chats refused since this bot was set, newest first, each saying whether it can be paired."""
        return [{**chat, "own_chat": bool(CHAT_ID_SHAPE.match(chat["chat_id"]))}
                for chat in reversed(list(self.refused_chats.values()))]

    def get_daemon_status(self) -> Dict[str, Any]:
        """Telemetry diagnostics for the ingress daemon."""
        return {
            "is_running": self.is_running,
            "current_delay_seconds": self.current_delay,
            "consecutive_errors": self.consecutive_errors,
            "is_quiet_hours": self.is_quiet_hours(),
            "total_polls": self.total_polls,
            "total_messages_processed": self.total_messages_processed,
            "last_poll_at": self.last_poll_at,
            "last_error": self.last_error,
            "has_token": bool(self.bot_token),
            "has_authorized_chat_id": bool(self.authorized_chat_id),
        }

    def process_incoming_update(
        self,
        update: Dict[str, Any],
        from_telegram: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Process a single Telegram update dictionary."""
        if not isinstance(update, dict):
            return None

        # A press of one of the bot's buttons (phase 2).
        if from_telegram and isinstance(update.get("callback_query"), dict):
            self._press(update["callback_query"])
            return None

        message = update.get("message", {})
        if not isinstance(message, dict):
            return None

        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "")

        # The whitelist is not optional.
        #
        # This read `if self.authorized_chat_id and chat_id != ...`, so the
        # check applied only when a chat id had been configured, and
        # authorized_chat_id defaults to empty. The documented way to start the
        # daemon is the bot token alone, which means the shipped configuration
        # was: anyone who learns the bot's username can send it a message and
        # have the text land in the creator's drafts and their posts table, on
        # a product whose next step is publishing to LinkedIn.
        #
        # A bot username is not a secret. Telegram lists bots in search.
        #
        # So an unconfigured whitelist now accepts nothing rather than
        # everything. That is the same direction every other default in this
        # product takes: autostart off until asked for, the queue pause failing
        # closed, an MCP server added switched off. Absence of a preference is
        # not permission.
        # The whitelist governs Telegram, and only Telegram.
        #
        # /api/v1/ingress/simulate reaches this method too, and its
        # authorization is a different one that has already happened: the
        # access middleware required a loopback Host, an allowed Origin and
        # the session cookie before the request arrived. Someone at the
        # keyboard of this machine is the creator.
        #
        # The two used to share this check, and the simulate route passed a
        # made up chat id of "local_creator" that the open whitelist happened
        # to accept. That is how the hole stayed invisible: the local path
        # appeared to be authorized, when in truth nothing was.
        #
        # Separating them is what lets the Telegram side fail closed without
        # taking the local one with it.
        if from_telegram:
            if not self.authorized_chat_id:
                self._remember_refusal(chat_id, message)
                self._answer_refusal(chat_id, "not_paired")
                self.last_error = (
                    "TELEGRAM_CHAT_ID is not set, so every incoming message is "
                    "refused. Set it to your own numeric chat id to accept drafts "
                    "from yourself."
                )
                # The chat id goes in the log, never the message: it is what
                # the creator needs, and the panel offers it (This is me).
                logger.warning(
                    "Refused an ingress message from chat_id: %s. No chat id is saved, so this bot has no way to "
                    "tell you from anybody else; if it is yours, press This is me under Local security.", chat_id
                )
                return None

            if chat_id != str(self.authorized_chat_id):
                self._remember_refusal(chat_id, message)
                self._answer_refusal(chat_id, "other_chat")
                logger.warning(f"Unauthorized ingress attempt from chat_id: {chat_id}")
                return None

        # A photo or a voice note is kept as it is (phase 3, item 4), never
        # read. Only from Telegram: the local route has no file to fetch.
        media = phone_media.wanted(message) if from_telegram else None
        if not text and not media:
            # A sticker, a document, a video: nothing of it is kept, and the
            # chat is told. (A voice note once left a placeholder draft
            # promising a transcription that never came.)
            if from_telegram:
                self._reply(chat_id, telegram_bot.SENTENCES["no_text"])
            return None
        forwarded = any(field in message for field in FORWARD_FIELDS)

        # A message from Telegram is saved in the profile its bot was set up
        # in. A message through the local simulate route is the open
        # profile's, because that is where the person at the keyboard is.
        pinned = self.profile_id if from_telegram else None
        if pinned and pinned not in paths.profile_ids():
            self.last_error = ("The profile this bot was set up in is closed or gone, so its messages are not "
                               "saved. Set the bot up again in the profile you use.")
            return None
        with (paths.using_profile(pinned) if pinned else nullcontext()):
            # A forwarded "/help" is someone else's words, not the creator's command.
            command = None if forwarded or media else telegram_bot.parse_command(text)
            if media:
                stored = self._store_media(media, message.get("caption"), _origin(update, from_telegram))
                question, answer = False, telegram_bot.answer_for(stored)
            elif command:
                stored, answer, question = self._command(command, update, from_telegram)
            else:
                stored = self._store(text, origin=_origin(update, from_telegram), from_telegram=from_telegram,
                                     forwarded=forwarded)
                question, answer = False, telegram_bot.answer_for(stored)
            if from_telegram and stored is not None and stored.get("kind") not in ("too_big", "media_failed"):
                _note_heard()
        if from_telegram:
            self._reply(chat_id, answer, always=question, draft_id=telegram_bot.draft_of(stored),
                        item=telegram_bot.item_of(stored),
                        fact_id=stored.get("id") if isinstance(stored, dict) and stored.get("kind") == "fact" else None)
        return stored

    def _press(self, callback: Dict[str, Any]) -> None:
        """
        A press of one of the bot's buttons. Refused like a stranger's message
        unless it comes from the paired chat, by its own person; otherwise
        telegram_bot.press does what the button says, on the studio's own
        records and only once, and the press is answered (the notice the
        phone shows) and its message edited to say so, its buttons gone. A
        press is answered whatever the confirmations switch says: it is the
        creator's own act. Logged by its chat, never its data.
        """
        query_id = str(callback.get("id") or "")
        held = callback.get("message") if isinstance(callback.get("message"), dict) else {}
        chat_id = str((held.get("chat") or {}).get("id", ""))
        who = str((callback.get("from") or {}).get("id", "") or chat_id)
        paired = str(self.authorized_chat_id or "")
        if not paired or chat_id != paired or who != paired:
            # The person who pressed, or the chat it came from when that is not the paired one.
            stranger = who if who != paired else chat_id
            self._remember_refusal(stranger, {"callback_query": True})
            self._answer_refusal(stranger, "other_chat" if paired else "not_paired", callback_id=query_id)
            logger.warning("Refused a button press from chat_id: %s", stranger)
            return
        if self.profile_id and self.profile_id not in paths.profile_ids():
            return
        with self._bots_profile():
            done = telegram_bot.press(callback.get("data"), chat_id)
        if query_id:
            self.outbox.put_call("answerCallbackQuery", {"callback_query_id": query_id, "text": done["answer"]})
        message_id = held.get("message_id")
        if isinstance(message_id, int):
            if done["edit"]:
                # No reply_markup: the edit takes the message's buttons away.
                self.outbox.put_call("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                                         "text": done["edit"]})
            else:
                self.outbox.put_call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id})
        if done.get("job"):
            self._start_job(done["job"], chat_id)

    def _command(self, command, update: Dict[str, Any], from_telegram: bool = True):
        """One of the bot's commands: (what was stored or done, the answer, whether it was a question)."""
        name, argument = command
        done = {"kind": "command", "command": name}
        if name in ("start", "help"):
            return done, telegram_bot.HELP, True
        if name == "status":
            return done, telegram_bot.status_sentence(self.previous_ok_at if from_telegram else self.last_ok_at), True
        if name == "drafts":
            # A count of the creator's own drafts, never their words.
            return done, telegram_bot.drafts_answer(), True
        if name == "today":
            # The creator's own figures leave only when they turned that on.
            if not telegram_bot.figures_on():
                return done, telegram_bot.SENTENCES["figures_off"], True
            return done, telegram_bot.today_answer(), True
        if name == "idea":
            if not argument:
                return done, telegram_bot.SENTENCES["empty_idea"], False
            stored = self._store("Idea: " + argument, links=False, origin=_origin(update, from_telegram),
                                 from_telegram=from_telegram)
            return stored, telegram_bot.answer_for(stored), False
        if name == "remember":
            # A thing to remember (phase 3): the creator's own fact, kept
            # for every writing request as they allow, with Undo.
            about, fact = remembered.parse_phone(argument)
            if not fact.strip():
                return done, telegram_bot.SENTENCES["empty_remember"], False
            try:
                kept = remembered.add(fact, about, "telegram", origin_ref=_origin(update, from_telegram))
            except remembered.Refused:
                too_long = len(" ".join(fact.split())) > remembered.TEXT_MAX
                return done, telegram_bot.SENTENCES["remember_long" if too_long else "empty_remember"], False
            return {"kind": "fact", "id": kept["id"]}, telegram_bot.SENTENCES["remembered"], False
        if name == "forget":
            if not argument.strip():
                return done, telegram_bot.SENTENCES["empty_forget"], True
            key, count = remembered.forget_matching(argument)
            return done, telegram_bot.SENTENCES[key].format(count=count), True
        if name == "recall":
            if not argument.strip():
                return done, telegram_bot.SENTENCES["empty_recall"], True
            return done, telegram_bot.recall_answer(argument), True
        if name == "ask":
            # An explicit act of the creator's, so it goes through the asks
            # store's own rule (record_store.py), from the paired chat only.
            try:
                from . import record_store
            except ImportError:
                import record_store
            try:
                kept = record_store.add_ask(argument, "telegram", origin_ref=f"telegram:{update.get('update_id')}")
            except record_store.Refused:
                return done, telegram_bot.SENTENCES["empty_ask"], False
            return {"kind": "ask", "id": kept.get("id")}, telegram_bot.SENTENCES["ask"], False
        return done, telegram_bot.SENTENCES["unknown_command"], False

    def _store_media(self, media: Dict[str, Any], caption: Any, origin: Optional[str]) -> Dict[str, Any]:
        """
        A photo or a voice note, kept as it is (phase 3, item 4): fetched from
        Telegram through the egress check, into the profile's assets folder,
        and listed in the collection with its caption as the creator's words.
        Never read. Handled again, it is not fetched twice. A file too big,
        or one Telegram will not hand over, is said and nothing is kept; a
        network fault raises, so the update is tried again.
        """
        held = collection.by_origin(origin) if origin else None
        if held:
            return {"kind": "collected", "archetype": held["kind"], "item": held, "desk_request": None}
        try:
            kept = phone_media.fetch(self.bot_token, media)
        except phone_media.TooBig:
            return {"kind": "too_big"}
        except phone_media.Unfetched as failure:
            if not failure.lasting:
                raise
            # Why, in Telegram's words of status only: never the token, never the file.
            logger.warning("Telegram did not hand over a file the paired chat sent: %s", failure)
            return {"kind": "media_failed"}
        words = str(caption or "").replace(chr(0x2014), " -- ").replace(chr(0x2013), "-")
        try:
            item = collection.add(media["kind"], words, media=kept, origin_ref=origin, source="telegram")
        except BaseException:
            phone_media.discard(kept)
            raise
        return {"kind": "collected", "archetype": media["kind"], "item": item, "desk_request": None}

    def _store(self, text: str, links: bool = True, origin: Optional[str] = None, from_telegram: bool = True,
               forwarded: bool = False) -> Optional[Dict[str, Any]]:
        """
        Saves one accepted message in the collection (phase 3): a note, an
        idea, a forwarded message, a bookmark (a link to someone else's post),
        or a link that is also a request on Today. Nothing is written from it
        until the creator asks. "Draft:" and "Schedule <when>:" still go
        straight to a draft, as they always did, recorded in the collection
        as used. A forward's links are part of its text, never a request.
        """
        parsed = IngressMessageParser.parse_message(text, links=links and not forwarded)
        source = "telegram" if from_telegram else "studio"
        # Handled again: what it made the first time, and nothing written twice.
        held = collection.by_origin(origin) if origin else None
        if held:
            return {"kind": "collected", "archetype": parsed["archetype"], "item": held, "desk_request": None}

        # A post link is a request to read that post at the desk, recorded
        # first: one of the creator's posts is open on Today, anyone else's
        # is refused there and kept here as a bookmark.
        request = None
        asked = parsed.get("read_request")
        if asked and asked.get("short_link"):
            request = self._record_short_link(asked["short_link"])
        elif asked:
            request = self._record_desk_request(asked["activity_urn"])
        words = parsed["raw_content"].strip()

        straight = not forwarded and (parsed["archetype"] == "Scheduled Post"
                                      or (parsed["archetype"] == "Draft" and "read" not in parsed["tags"]))
        if straight and words:
            # One record of what the creator wrote: create_draft writes the
            # posts row with the draft.
            draft_id = create_draft(
                title=parsed["title"],
                raw_content=parsed["raw_content"],
                formatted_content=parsed["formatted_content"],
                char_count=parsed["char_count"],
                lines_above_fold=parsed["lines_above_fold"],
                pre_fold_chars=parsed["pre_fold_chars"],
                is_pre_fold_safe=parsed["is_pre_fold_safe"],
                archetype=parsed["archetype"],
                tags=parsed["tags"],
            )
            record = get_draft(draft_id)
            if not record:
                return None
            if request:
                record["desk_request"] = request
            record["collection_item"] = collection.add(
                "note", words, status="used", post_id=f"post-draft-{draft_id}",
                desk_request_id=request["id"] if request else None, source=source, origin_ref=origin)
            return record

        if not words and not request:
            return None
        link = urn = None
        if request is None:
            kind = "forward" if forwarded else ("idea" if parsed["archetype"] == "Raw Idea" else "note")
        elif request.get("link") and not request.get("activity_urn"):
            kind, link = "link", request["link"]
        else:
            urn = request["activity_urn"]
            kind = "bookmark" if request.get("state") == desk_requests.REFUSED else "post"
            link = collection.canonical_post_link(urn)
        # A request with no words of the creator's has become what it is for;
        # anything with words is material until something is made from it.
        status = "new" if words or kind == "bookmark" else "used"
        item = collection.add(kind, words, link=link, activity_urn=urn,
                              desk_request_id=request["id"] if request else None, status=status, source=source,
                              origin_ref=origin)
        if request and not words:
            # A link alone: what it made is the request, as it always was, and the item that lists it.
            return {"kind": "desk_request", **request, "collection_item": item, "archetype": parsed["archetype"]}
        return {"kind": "collected", "archetype": parsed["archetype"], "item": item, "desk_request": request}

    @staticmethod
    def _record_desk_request(activity_urn: str) -> Dict[str, Any]:
        """
        Writes the link: open for one of the creator's own posts, refused,
        with its reason, for anything else, so a link to someone else's post
        never reaches Today. The phone's link names the post and nothing
        else: no figure is written from it.
        """
        conn = get_db()
        try:
            return desk_requests.record(conn, activity_urn, source=desk_requests.SOURCE_TELEGRAM)
        finally:
            conn.close()

    @staticmethod
    def _record_short_link(link: str) -> Dict[str, Any]:
        """
        Writes a short link as a request that waits for its post. Nothing
        follows the link here: which post it is becomes known only in the
        creator's own browser, when they open it from Today.
        """
        conn = get_db()
        try:
            return desk_requests.record_short(conn, link, source=desk_requests.SOURCE_TELEGRAM)
        finally:
            conn.close()

    def _redact(self, text: str) -> str:
        """
        Removes the bot token from anything about to be stored or logged.

        The token is a path segment of the getUpdates URL, and requests puts
        the URL in its exception message, so `str(err)` on a connection failure
        reads:

            HTTPSConnectionPool(host='api.telegram.org', port=443): Max
            retries exceeded with url: /bot<THE WHOLE TOKEN>/getUpdates

        That string was assigned to last_error, which GET /api/v1/ingress/status
        returns verbatim, and logged to stderr, which under the desktop shell
        is redirected into the engine log, which support.py tails into a
        diagnostics bundle whose docstring offers it for a public issue. A
        misconfigured bot on a machine with no network was one support request
        away from publishing a credential that can read and send the creator's
        messages.

        Both spellings are removed: the raw token, and `bot<token>` as it
        appears in the path, so a partial match cannot leave the secret half
        behind.
        """
        cleaned = str(text or "")
        token = str(self.bot_token or "")
        if token:
            cleaned = cleaned.replace(f"bot{token}", "bot<redacted>")
            cleaned = cleaned.replace(token, "<redacted>")
        return cleaned

    def poll_once(self) -> List[Dict[str, Any]]:
        """Single polling request to Telegram getUpdates API."""
        if not self.bot_token:
            return []
        if self.configured_from == "settings" and self.profile_id and self.profile_id not in paths.profile_ids():
            # The profile this bot was set up in was deleted, or closed with
            # its licence. Asking on would confirm each of its messages to
            # Telegram and then drop it, so the worker stops asking.
            self.configure("", "", origin=None)
            self.last_error = ("The profile this bot was set up in is closed or gone, so the studio stopped asking "
                               "Telegram for its messages. Set the bot up again in the profile you use.")
            return []

        # Replies that had to wait (a 429, a network fault) get their turn
        # before the next question to Telegram.
        self.flush_replies()

        token = self.bot_token
        url = telegram_bot.method_url(token, "getUpdates")
        params = {
            "offset": self.last_update_id + 1,
            "timeout": 30,
            "allowed_updates": json.dumps(list(ALLOWED_UPDATES)),
        }

        self.total_polls += 1
        self.last_poll_at = datetime.now(timezone.utc).isoformat()

        try:
            # Refuses rather than connecting when this category is off. See
            # egress.py. Counted under an address without the token, which
            # the ledger would otherwise show on Local security.
            _egress.require(telegram_bot.ledger_url("getUpdates"), "ingress")
            res = requests.get(url, params=params, timeout=35)
            if token != self.bot_token:
                # The bot changed while this request waited on Telegram. The
                # answer is the old bot's: nothing in it is handled under the
                # new bot's settings, and nothing is confirmed, so the old
                # bot's messages wait with Telegram for its next poll.
                return []
            if res.status_code == 200:
                data = res.json()
                if data.get("ok"):
                    # Telegram answered: a successful check, kept before the
                    # batch is handled, so /status in it says the one before.
                    self._note_check(datetime.now(timezone.utc))
                    results = data.get("result", [])
                    processed = []
                    for update in results:
                        if not isinstance(update, dict):
                            continue
                        update_id = update.get("update_id", 0)

                        # Process first, then acknowledge.
                        #
                        # last_update_id becomes the offset on the next poll,
                        # so advancing it before handling the message told
                        # Telegram we had it while we had not. A draft that
                        # failed to store was gone, because Telegram never
                        # sends an acknowledged update again.
                        #
                        # Simply moving the advance below the call is not
                        # enough on its own: a message that can never be
                        # processed would then be retried forever and block
                        # every message behind it. So a failure is retried a
                        # bounded number of times and then stepped over, with
                        # the reason logged, which is the only outcome that
                        # loses neither the queue nor the evidence.
                        try:
                            p = self.process_incoming_update(update)
                            if p:
                                processed.append(p)
                            self._failed_updates.pop(update_id, None)
                        except Exception as update_error:
                            attempts = self._failed_updates.get(update_id, 0) + 1
                            self._failed_updates[update_id] = attempts
                            # The kind of failure only: an exception's text can
                            # quote the message, and no message reaches a log.
                            logger.error(
                                "Could not process Telegram update %s (attempt %d of %d): %s",
                                update_id, attempts, MAX_UPDATE_ATTEMPTS, type(update_error).__name__,
                            )
                            if attempts < MAX_UPDATE_ATTEMPTS:
                                # Leave the offset where it is so Telegram
                                # sends it again.
                                break
                            logger.error(
                                "Giving up on Telegram update %s after %d attempts. "
                                "The message is being skipped so the queue can drain.",
                                update_id, attempts,
                            )
                            self._failed_updates.pop(update_id, None)
                            # Said to the chat it came from, if it is the paired one.
                            sender = str(((update.get("message") or {}).get("chat") or {}).get("id", ""))
                            if sender and sender == str(self.authorized_chat_id):
                                self._reply(sender, telegram_bot.SENTENCES["not_saved"])
                            # A press from the paired chat is answered, so its button stops spinning.
                            pressed = update.get("callback_query")
                            if (isinstance(pressed, dict) and pressed.get("id") and self.authorized_chat_id
                                    and str((pressed.get("from") or {}).get("id", "")) == str(self.authorized_chat_id)):
                                self.outbox.put_call("answerCallbackQuery", {
                                    "callback_query_id": str(pressed["id"]),
                                    "text": telegram_bot.SENTENCES["press_failed"]})

                        if isinstance(update_id, int) and update_id > self.last_update_id:
                            self.last_update_id = update_id
                    self.total_messages_processed += len(processed)
                    self.last_error = None
                    self.poll_failed = False
                    self.flush_replies()
                    return processed
                else:
                    self.poll_failed = True
                    self.last_error = self._redact(telegram_bot.plain_words(
                        int(data.get("error_code") or 400), str(data.get("description") or "")))
            elif res.status_code == 429:
                # Telegram says wait. Record it as a deadline, not as a delay.
                #
                # This used to set current_delay and return normally. The loop
                # read no exception, so calculate_next_poll_interval took the
                # success path, reset consecutive_errors and overwrote
                # current_delay with base_delay. The daemon then re-polled two
                # seconds later while reporting "backing off 25.0s", which
                # escalates the rate limit it is supposed to be respecting.
                retry_after = None
                try:
                    raw_retry = res.json().get("parameters", {}).get("retry_after")
                    if raw_retry is not None:
                        retry_after = float(raw_retry)
                except Exception:
                    retry_after = None

                if retry_after and retry_after > 0:
                    # The server named a figure, so use it rather than guessing.
                    self.current_delay = max(retry_after, self.base_delay)
                else:
                    # A 429 with no retry_after is the one case where the
                    # exponential ladder is the right answer, because nothing
                    # told us how long to wait.
                    self.consecutive_errors += 1
                    self.current_delay = min(
                        self.max_delay,
                        self.base_delay * (2 ** min(self.consecutive_errors, 6)),
                    )

                self.rate_limited_until = time.monotonic() + self.current_delay
                self.last_error = telegram_bot.plain_words(429, retry_after=self.current_delay)
            else:
                # Any other answer is a failure the loop backs off from, said
                # in plain words: a token Telegram does not know, a second
                # program asking for the same bot, Telegram's own trouble.
                self.poll_failed = True
                try:
                    description = str((res.json() or {}).get("description") or "")
                except Exception:
                    description = ""
                self.last_error = self._redact(telegram_bot.plain_words(res.status_code, description))
        except Exception as err:
            # Plain words for the panel; the detail, redacted because the
            # token is in the URL and the URL is in the exception, for the log.
            self.last_error = (telegram_bot.EGRESS_OFF if isinstance(err, _egress.EgressRefused)
                               else telegram_bot.UNREACHABLE)
            logger.error("Polling error: %s", self._redact(str(err)))
            raise
        return []

    def start_worker(self):
        """Start background polling thread with adaptive pacing."""
        if self.is_running:
            return
        self.is_running = True
        # Each loop has its own stop flag. A loop still waiting on Telegram
        # when it was stopped used to find the shared flag cleared by the
        # next start, and polled on beside the new loop.
        stop = threading.Event()
        self._stop_event = stop

        def _loop():
            while not stop.is_set():
                if not self.bot_token:
                    if stop.wait(30.0):
                        break
                    continue

                has_err = False
                self.poll_failed = False
                try:
                    self.poll_once()
                except Exception as e:
                    has_err = True
                    logger.error("Worker loop error: %s", self._redact(str(e)))
                has_err = has_err or self.poll_failed
                self.check_notifications()

                delay = self.calculate_next_poll_interval(has_error=has_err)
                if stop.wait(delay):
                    break

        self._thread = threading.Thread(target=_loop, daemon=True, name="TelegramIngressWorker")
        self._thread.start()

    def stop_worker(self):
        """Stop background worker gracefully, keeping the time of its last check."""
        self.is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.STOP_JOIN_SECONDS)
        self._keep_last_check()


# Global singleton daemon
ingress_daemon = TelegramIngressDaemon()


# ---------------------------------------------------------------------------
# The settings behind the Local security panel (cycle 4, decision D6)
# ---------------------------------------------------------------------------

def _origin(update: Dict[str, Any], from_telegram: bool) -> Optional[str]:
    """
    What keys a Telegram message so it is kept once, even if its update is
    handled again (a failure after it was kept, or a restart before Telegram
    was told). Update ids are each bot's own and a new bot's may meet an old
    one's, so the message's own date goes with it.
    """
    if not from_telegram or not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
        return None
    message = update.get("message") if isinstance(update.get("message"), dict) else {}
    return f"telegram:{update['update_id']}:{message.get('date')}"


def _note_heard() -> None:
    """A message from the saved chat was saved: the first time, the open profile records when."""
    conn = get_db()
    try:
        with conn:
            conn.execute("INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                         (SETTINGS_HEARD_KEY, datetime.now(timezone.utc).isoformat()))
    finally:
        conn.close()


def _when(text: Any) -> Optional[datetime]:
    """A time as the settings and the collection keep it, or None."""
    try:
        when = datetime.fromisoformat(str(text or "").strip().replace(" ", "T", 1))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


# What a message from the paired chat leaves in a profile, by when it was saved.
_SAVED_FROM_TELEGRAM = (("collection_items", "received_at"), ("remembered", "created_at"), ("asks", "created_at"))


def _seen_working(conn) -> Optional[str]:
    """
    Whether a message from the chat saved here has been saved here, and since
    when: the marker, or else the first thing this profile holds from
    Telegram since that chat was paired (an item in the collection, a thing
    to remember, an ask). Only the paired chat's messages are ever saved, so
    each came from it. Found once, the marker is set to that thing's time, so
    the answer stays when the thing is removed (phase 4, item 1).
    """
    heard = conn.execute("SELECT value FROM settings WHERE key = ?", (SETTINGS_HEARD_KEY,)).fetchone()
    if heard:
        return heard["value"]
    paired = conn.execute("SELECT value FROM settings WHERE key = ?", (SETTINGS_PAIRED_KEY,)).fetchone()
    since = _when(paired["value"]) if paired else None
    earliest: Optional[tuple] = None
    for table, column in _SAVED_FROM_TELEGRAM:
        try:
            if since is None:
                rows = conn.execute(f"SELECT {column} FROM {table} WHERE source = 'telegram'")
            else:
                # The date part reads alike in every form a time is kept in.
                rows = conn.execute(f"SELECT {column} FROM {table} WHERE source = 'telegram' "
                                    f"AND substr({column}, 1, 10) >= ?", (since.date().isoformat(),))
            for (kept,) in rows:
                when = _when(kept)
                if when is not None and (since is None or when >= since) and (earliest is None or when < earliest[0]):
                    earliest = (when, str(kept))
        except Exception:
            # A profile from before one of these tables keeps nothing in it.
            continue
    if earliest is None:
        return None
    with conn:
        conn.execute("INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                     (SETTINGS_HEARD_KEY, earliest[1]))
    # A derived fact, kept so it is not worked out again: no window need read again for it.
    try:
        from . import changes
    except ImportError:
        import changes
    changes.derived_written()
    return earliest[1]


def read_settings(profile_id: Optional[str] = None) -> Dict[str, str]:
    """The bot token (unsealed, for the worker) and chat id held in a profile, the open one by default."""
    with (paths.using_profile(profile_id) if profile_id else nullcontext()):
        conn = get_db()
        try:
            held = {r["key"]: r["value"] for r in conn.execute(
                "SELECT key, value FROM settings WHERE key IN (?, ?)", (SETTINGS_TOKEN_KEY, SETTINGS_CHAT_KEY))}
        finally:
            conn.close()
    return {
        "token": secret_settings.unseal(SETTINGS_TOKEN_KEY, held.get(SETTINGS_TOKEN_KEY)),
        "chat_id": str(held.get(SETTINGS_CHAT_KEY) or "").strip(),
    }


def apply_settings(at_startup: bool = False) -> bool:
    """
    Points the worker at a bot set up in the settings and starts it. Returns
    whether one is running for a profile's settings.

    One worker runs per studio, so one bot is asked at a time. On a save it
    is the open profile's; at startup, the first profile the licence opens
    that has one. When the open profile's bot is removed, a worker serving
    that profile stops. A worker a maintainer started from the environment
    is left alone.
    """
    active = paths.get_active_profile_id()
    candidates = paths.profile_ids() if at_startup else [active]
    for profile_id in candidates:
        try:
            held = read_settings(profile_id)
        except Exception:
            # A profile whose database cannot be read keeps no bot that can run.
            continue
        # A token alone runs too: every message is refused until the creator
        # says which refused chat is theirs (This is me).
        if held["token"]:
            ingress_daemon.configure(held["token"], held["chat_id"], origin="settings", profile_id=profile_id)
            ingress_daemon.start_worker()
            return True
    if not at_startup and ingress_daemon.configured_from == "settings" and ingress_daemon.profile_id == active:
        ingress_daemon.stop_worker()
        ingress_daemon.configure("", "", origin=None)
    return False


def save_settings(bot_token: str, chat_id: str) -> Dict[str, Any]:
    """
    Keeps the token (sealed) and the chat id, then applies them. Both empty
    removes them and stops the worker. An empty field keeps what is held:
    a token alone starts the bot with no chat saved, every message refused
    and its chat remembered for the panel, and a chat id alone (This is me)
    pairs that chat with the token held. A value of the wrong shape is
    refused with a sentence and nothing is written.
    """
    token = (bot_token or "").strip()
    chat = (chat_id or "").strip()
    if not token and not chat:
        conn = get_db()
        try:
            with conn:
                conn.execute("DELETE FROM settings WHERE key IN (?, ?, ?, ?)",
                             (SETTINGS_TOKEN_KEY, SETTINGS_CHAT_KEY, SETTINGS_HEARD_KEY, SETTINGS_PAIRED_KEY))
                telegram_bot.forget_checks(conn)
        finally:
            conn.close()
        if ingress_daemon.configured_from == "settings" and ingress_daemon.profile_id == paths.get_active_profile_id():
            # Removed: the worker stopping now keeps no last check for a bot that is gone.
            ingress_daemon.last_ok_at = None
        apply_settings()
        return describe_settings()
    held = read_settings()
    if not token:
        if not held["token"]:
            return {"status": "error", "message": (
                "Paste your bot token first: the chat id says which chat with that bot is yours. "
                "Nothing was stored.")}
        token = held["token"]
    if not TOKEN_SHAPE.match(token):
        return {"status": "error", "message": (
            "That is not the shape of a Telegram bot token: BotFather issues a number, a colon and a secret, "
            "for example 123456789:AAF... Paste it exactly as given. Nothing was stored.")}
    if chat.startswith("-"):
        return {"status": "error", "message": (
            "That is a group's chat id: any member of the group could then file drafts in your studio. Use your "
            "own chat id with the bot, a number with no minus sign. Nothing was stored.")}
    if chat and not CHAT_ID_SHAPE.match(chat):
        return {"status": "error", "message": (
            "Your chat id is a number, digits only. Or leave it empty: save the token, message the bot once, "
            "then press This is me. Nothing was stored.")}
    chat = chat or held["chat_id"]
    conn = get_db()
    try:
        with conn:
            if token != held["token"]:
                conn.execute(
                    "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                    (SETTINGS_TOKEN_KEY, secret_settings.seal(SETTINGS_TOKEN_KEY, token)))
                telegram_bot.forget_checks(conn)
            if chat:
                conn.execute(
                    "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                    (SETTINGS_CHAT_KEY, chat))
            if chat != held["chat_id"]:
                conn.execute("DELETE FROM settings WHERE key = ?", (SETTINGS_HEARD_KEY,))
                if chat:
                    conn.execute(
                        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                        (SETTINGS_PAIRED_KEY, datetime.now(timezone.utc).isoformat()))
    finally:
        conn.close()
    apply_settings()
    if chat and chat != held["chat_id"] and _asking_for_this_profile():
        # The chat is told at once that it is paired (This is me, or a chat id typed in).
        ingress_daemon._reply(chat, telegram_bot.SENTENCES["paired"])
        ingress_daemon.flush_replies()
    return describe_settings()


def send_test_message() -> Dict[str, Any]:
    """
    The panel's Send a test message: one fixed sentence to the paired chat,
    now, and whether Telegram took it. Telegram's answer says the chat
    received it; whether the phone showed it, only the phone can say.
    """
    held = read_settings()
    if not held["token"] or not held["chat_id"]:
        return {"status": "success", "sent": False,
                "said": "Pair a chat first: message the bot from your phone, then press This is me."}
    result = telegram_bot.send_message(held["token"], held["chat_id"], telegram_bot.SENTENCES["test"])
    if result["ok"]:
        return {"status": "success", "sent": True, "said": "Sent: Telegram took it for your chat. Check your phone."}
    return {"status": "success", "sent": False, "said": result["said"]}


def _asking_for_this_profile() -> bool:
    """Whether the worker is asking Telegram for the open profile's own bot."""
    return (bool(ingress_daemon.is_running) and ingress_daemon.configured_from == "settings"
            and ingress_daemon.profile_id == paths.get_active_profile_id())


def describe_settings() -> Dict[str, Any]:
    """What the Local security panel shows. Never the token."""
    held = read_settings()
    status = ingress_daemon.get_daemon_status()
    conn = get_db()
    try:
        # Settled first, so a request read at the desk is not counted as waiting.
        desk_requests.settle(conn)
        waiting = desk_requests.open_count(conn)
        links = desk_requests.recent(conn)
        heard = _seen_working(conn) if held["chat_id"] else None
    finally:
        conn.close()
    active = paths.get_active_profile_id()
    from_settings = ingress_daemon.configured_from == "settings"
    # Asking Telegram for this profile: its own bot, or a maintainer's bot
    # from the environment, which saves to whichever profile is open.
    running_here = bool(status["is_running"]) and (
        (from_settings and ingress_daemon.profile_id == active) or ingress_daemon.configured_from == "environment")
    return {
        "status": "success",
        "profile": active,
        "configured": bool(held["token"] and held["chat_id"]),
        # A token and no chat yet: every message is refused, and the chats
        # that wrote are listed for the creator to say which is theirs.
        "pairing": bool(held["token"] and not held["chat_id"]),
        "has_token": bool(held["token"]),
        "chat_id": held["chat_id"],
        "running": running_here,
        "running_for_another_profile": bool(status["is_running"]) and from_settings
                                       and ingress_daemon.profile_id != active,
        "configured_from": ingress_daemon.configured_from,
        "last_poll_at": status["last_poll_at"],
        "last_error": status["last_error"],
        "total_messages_processed": status["total_messages_processed"],
        "open_requests": waiting,
        # The newest links from the phone, each with what became of it; a
        # refused one says why: not one of your posts.
        "recent_links": links,
        # The chats this profile's bot refused, newest first: in memory only.
        "refused_chats": ingress_daemon.refused() if running_here or (
            from_settings and ingress_daemon.profile_id == active) else [],
        # A message from the chat saved here has been saved here.
        "tested_against_real_service": bool(heard),
        "not_yet_tested": None if heard else NOT_YET_TESTED,
        # The bot's switches, and why its last message to Telegram did not
        # go, in plain words (telegram_bot.py).
        "options": telegram_bot.options(),
        # The bot's notifications are waiting for quiet hours to end.
        "quiet_now": telegram_bot.in_quiet_hours(),
        # When the next weekly summary goes, on this computer's clock; None while it is off.
        "weekly_next": telegram_bot.weekly_next(),
        "last_send_error": ingress_daemon.outbox.last_error if running_here else None,
        "replies_waiting": ingress_daemon.outbox.waiting() if running_here else 0,
        # Phase 4, item 2: the last successful check of Telegram, and a day
        # not checked, said until Got it.
        "last_check_at": _last_check(running_here),
        "gap": telegram_bot.gap_shown(),
    }


def _last_check(running_here: bool) -> Optional[str]:
    """The last successful check for this profile's bot: the worker's own while it asks for it, else the one kept."""
    if running_here and ingress_daemon.last_ok_at is not None:
        return ingress_daemon.last_ok_at.isoformat()
    kept = telegram_bot.last_checked()
    return kept.isoformat() if kept else None


def gap_seen() -> Dict[str, Any]:
    """The panel's Got it: the notice of a day not checked is not shown again."""
    telegram_bot.gap_seen()
    return describe_settings()
