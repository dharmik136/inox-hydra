"""
Ubiquitous Telegram Ingress Daemon & Mobile Message Parser.
===========================================================
Handles outbound long-polling to api.telegram.org (zero inbound ports),
parses structured and unstructured creator thoughts, persists into SQLite WAL,
and broadcasts live events over the local EventBus.

Strict Invariants:
- Zero open inbound ports (pure outbound HTTP long-polling).
- Zero em-dashes in any generated or parsed text.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import logging
import os
import re
import requests
import threading
import time

try:
    from .database import get_db, create_draft, get_draft
    from .event_bus import event_bus
except ImportError:
    from database import get_db, create_draft, get_draft
    from event_bus import event_bus

MAX_UPDATE_ATTEMPTS = 3

logger = logging.getLogger("studio.ingress")

# Fold limits per Day 01 spec
MOBILE_FOLD_CHAR_LIMIT = 140
MOBILE_FOLD_LINE_LIMIT = 3
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
    def parse_message(cls, raw_text: Any) -> Dict[str, Any]:
        """Extracts intent, content, scheduling directives, and tags from incoming message."""
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
        if lower.startswith("draft:"):
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

        # Extract hashtags from text (capped to 30 unique tags, max 50 chars each)
        raw_hashtags = re.findall(r"#(\w+)", content)
        if raw_hashtags:
            tags.extend([h[:50] for h in raw_hashtags[:30]])

        # Generate title from the first non-empty line (truncated to 60 chars)
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        title = lines[0][:60] if lines else "Untitled Mobile Ingress"

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
        }


class TelegramIngressDaemon:
    """Outbound long-polling worker for Telegram Bot API with zero open ports."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        authorized_chat_id: Optional[str] = None,
    ):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "") or os.environ.get("PRUDENT_TELEGRAM_BOT_TOKEN", "")
        self.authorized_chat_id = authorized_chat_id or os.environ.get("TELEGRAM_CHAT_ID", "") or os.environ.get("PRUDENT_TELEGRAM_CHAT_ID", "")
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
        self.total_messages_processed = 0
        self.last_poll_at: Optional[str] = None
        self.last_error: Optional[str] = None

    def is_quiet_hours(self, current_time: Optional[datetime] = None) -> bool:
        """Determines if current time falls within low-power night window (23:00 to 06:00)."""
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

    def process_incoming_update(self, update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single Telegram update dictionary."""
        if not isinstance(update, dict):
            return None

        message = update.get("message", {})
        if not isinstance(message, dict):
            return None

        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "")

        # Security: Whitelist check (silently drop unauthorized chat IDs)
        if self.authorized_chat_id and chat_id != str(self.authorized_chat_id):
            logger.warning(f"Unauthorized ingress attempt from chat_id: {chat_id}")
            return None

        if not text:
            if "voice" in message:
                text = "[Voice Memo Received: Local transcription pending]"
            else:
                return None

        # Parse message
        parsed = IngressMessageParser.parse_message(text)

        # Store in local SQLite database (both drafts table and posts table for full sync)
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

        # Also store into posts table for seamless integration with legacy post studio
        conn = None
        try:
            conn = get_db()
            with conn:
                post_id = f"post-tg-{draft_id}"
                conn.execute("""
                INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
                VALUES (?, ?, 'draft', ?, CURRENT_TIMESTAMP)
                """, (post_id, parsed["raw_content"], json.dumps(parsed["tags"])))
        except Exception as e:
            logger.error(f"Error syncing post to posts table: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        # Broadcast live to UI via SSE bus
        event_payload = {
            "draft_id": draft_id,
            "title": record["title"],
            "raw_content": record["raw_content"],
            "archetype": record["archetype"],
            "tags": record["tags"],
            "is_pre_fold_safe": record["is_pre_fold_safe"],
            "created_at": record["created_at"],
        }
        event_bus.publish_sync(
            event_type="draft_ingested",
            data=event_payload,
        )

        return record

    def poll_once(self) -> List[Dict[str, Any]]:
        """Single polling request to Telegram getUpdates API."""
        if not self.bot_token:
            return []

        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {
            "offset": self.last_update_id + 1,
            "timeout": 30,
        }

        self.total_polls += 1
        self.last_poll_at = datetime.now(timezone.utc).isoformat()

        try:
            res = requests.get(url, params=params, timeout=35)
            if res.status_code == 200:
                data = res.json()
                if data.get("ok"):
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
                            logger.error(
                                "Could not process Telegram update %s (attempt %d of %d): %s",
                                update_id, attempts, MAX_UPDATE_ATTEMPTS, update_error,
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

                        if isinstance(update_id, int) and update_id > self.last_update_id:
                            self.last_update_id = update_id
                    self.total_messages_processed += len(processed)
                    self.last_error = None
                    return processed
                else:
                    self.last_error = f"Telegram API error: {data.get('description', 'Unknown')}"
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
                self.last_error = (
                    f"HTTP 429: Rate limited by Telegram API, "
                    f"backing off {self.current_delay:.1f}s"
                )
            else:
                self.last_error = f"HTTP {res.status_code}: {res.text[:100]}"
        except Exception as err:
            self.last_error = str(err)
            logger.error(f"Polling error: {err}")
            raise
        return []

    def start_worker(self):
        """Start background polling thread with adaptive pacing."""
        if self.is_running:
            return
        self.is_running = True
        self._stop_event.clear()

        def _loop():
            while self.is_running and not self._stop_event.is_set():
                if not self.bot_token:
                    if self._stop_event.wait(30.0):
                        break
                    continue

                has_err = False
                try:
                    self.poll_once()
                except Exception as e:
                    has_err = True
                    logger.error(f"Worker loop error: {e}")

                delay = self.calculate_next_poll_interval(has_error=has_err)
                if self._stop_event.wait(delay):
                    break

        self._thread = threading.Thread(target=_loop, daemon=True, name="TelegramIngressWorker")
        self._thread.start()

    def stop_worker(self):
        """Stop background worker gracefully."""
        self.is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)


# Global singleton daemon
ingress_daemon = TelegramIngressDaemon()
