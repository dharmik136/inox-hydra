"""
The archive age nudge: one sentence when the last archive is a month old.
=========================================================================

LinkedIn's data archive is the record baseline: posts, comments, reactions
and connections, complete, with no page reading, and it never carries a
figure. Importing it again adds nothing twice and merges with what the
bridge read since, so a monthly loop is cheap to keep. This is the one
sentence Setup and Today say when the last import is older than a month,
computed here so both screens say the same thing (capture report, item 25).

Strict Invariants:
- Zero em-dashes.
- Nothing invented: no import, no sentence. A date that cannot be read is no
  date.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

NUDGE_AFTER = timedelta(days=31)


def _moment(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        when = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def sentence(imported_at: Optional[str], now: Optional[datetime] = None) -> Optional[str]:
    """
    "Your last archive was imported N weeks ago. ..." when the last import is
    older than NUDGE_AFTER; None when it is younger, or when there is none.
    """
    when = _moment(imported_at)
    if when is None:
        return None
    age = (now or datetime.now(timezone.utc)) - when
    if age < NUDGE_AFTER:
        return None
    weeks = age.days // 7
    return (f"Your last archive was imported {weeks} weeks ago. Ask LinkedIn for a fresh one about once a "
            "month, so your record stays complete without the extension.")
