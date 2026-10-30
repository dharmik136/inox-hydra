"""
Your phone, through Telegram: the settings behind the Local security panel.
===========================================================================
Decision D6 of the capture report: the Telegram ingress leaves dev mode
behind a Settings surface, with the bot token sealed like the AI key. These
two routes are what that panel reads and saves. The token is never answered
back; the panel is told only that one is set.

Strict Invariants:
- Zero em-dashes in all code, comments, and strings.
- Zero egress of its own: saving contacts nobody. The worker ingress.py runs
  afterwards is the one outbound path, already under the ingress category.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from .. import desk_requests, ingress, telegram_bot
    from ..database import get_db
except (ImportError, ValueError):
    import desk_requests
    import ingress
    import telegram_bot
    from database import get_db

router = APIRouter()


class DeskLandingPayload(BaseModel):
    request_id: int = Field(..., ge=1, description="The request named by the #inox-desk-<id> fragment the page kept")
    activity_urn: str = Field(..., min_length=1, max_length=80, description="The post the page names")


class IngressOptionsPayload(BaseModel):
    replies: Optional[bool] = Field(None, description="The bot confirms each message with a short fixed sentence")
    figures: Optional[bool] = Field(None, description="The bot may answer /today with your own figures")
    notify_due: Optional[bool] = Field(None, description="Tell the paired chat when a queued post is due")
    notify_24h: Optional[bool] = Field(None, description="Send the latest post's figures at about 24 hours")
    quiet_hours: Optional[bool] = Field(None, description="Hold notifications during quiet hours")
    quiet_from: Optional[int] = Field(None, ge=0, le=23, description="Quiet hours start, a whole hour")
    quiet_to: Optional[int] = Field(None, ge=0, le=23, description="Quiet hours end, a whole hour")
    weekly: Optional[bool] = Field(None, description="Send me a weekly summary")
    collection_words: Optional[bool] = Field(None, description="The bot may send me what it writes from my collection")
    morning: Optional[bool] = Field(None, description="Send me an idea from my collection each morning")
    morning_days: Optional[List[int]] = Field(None, description="The morning idea's days, 0 is Monday")
    morning_hour: Optional[int] = Field(None, ge=0, le=23, description="The morning idea's hour, a whole hour")
    weekly_day: Optional[int] = Field(None, ge=0, le=6, description="The weekly summary's day, 0 is Monday")
    weekly_hour: Optional[int] = Field(None, ge=0, le=23, description="The weekly summary's hour, a whole hour")
    replies_add: Optional[bool] = Field(None, description="A reply adds to the item it replies to")


class IngressSettingsPayload(BaseModel):
    bot_token: Optional[str] = Field(None, max_length=200, description="The bot token Telegram's BotFather gave you; empty removes it")
    chat_id: Optional[str] = Field(None, max_length=40, description="Your own numeric chat id; empty removes it")


@router.get("/api/v1/ingress/settings", tags=["Phone"])
def get_ingress_settings():
    """Whether a bot is set up in this profile, whether the studio is asking Telegram, and what has arrived."""
    return ingress.describe_settings()


@router.post("/api/v1/ingress/settings", tags=["Phone"])
def post_ingress_settings(payload: IngressSettingsPayload):
    """
    Keeps the bot token (sealed) and the chat id in this profile's settings
    and starts asking Telegram for messages; both empty stops it and removes
    them. A value of the wrong shape is refused with a sentence, and nothing
    is stored.
    """
    result = ingress.save_settings(payload.bot_token or "", payload.chat_id or "")
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/api/v1/ingress/test-message", tags=["Phone"])
def post_ingress_test_message():
    """Send a test message: one fixed sentence to the paired chat, and whether Telegram took it."""
    return ingress.send_test_message()


@router.post("/api/v1/ingress/gap/seen", tags=["Phone"])
def post_ingress_gap_seen():
    """
    Got it, under the notice that the studio did not check Telegram for more
    than a day: the panel stops showing it. The bot's own message about it
    is sent once either way.
    """
    return ingress.gap_seen()


@router.post("/api/v1/ingress/options", tags=["Phone"])
def post_ingress_options(payload: IngressOptionsPayload):
    """
    The bot's switches for this profile. A switch not sent is left as it is.
    Quiet hours whose start and end are the same hour are refused with a
    sentence, and nothing is saved.
    """
    try:
        telegram_bot.save_options(replies=payload.replies, figures=payload.figures, notify_due=payload.notify_due,
                                  notify_24h=payload.notify_24h, quiet=payload.quiet_hours,
                                  quiet_from=payload.quiet_from, quiet_to=payload.quiet_to,
                                  weekly_on=payload.weekly, weekly_day=payload.weekly_day,
                                  weekly_hour=payload.weekly_hour, collection_words=payload.collection_words,
                                  morning_on=payload.morning, morning_days=payload.morning_days,
                                  morning_hour=payload.morning_hour, replies_add=payload.replies_add)
    except ValueError as refused:
        raise HTTPException(status_code=400, detail=str(refused))
    return ingress.describe_settings()


@router.post("/api/v1/desk-requests/{request_id}/dismiss", tags=["Phone"])
def dismiss_desk_request(request_id: int):
    """Today's Not now: closes an open request from the phone. Says whether there was one to close."""
    conn = get_db()
    try:
        return {"status": "success", "dismissed": desk_requests.dismiss(conn, request_id)}
    finally:
        conn.close()


@router.post("/api/v1/desk-requests/{request_id}/done", tags=["Phone"])
def done_desk_request(request_id: int):
    """
    Today's Done, for a short link from the phone whose post the browser
    never reported: the creator says they have seen it. Says whether one was
    closed; a request that names its post is done when that post is read.
    """
    conn = get_db()
    try:
        return {"status": "success", "done": desk_requests.done(conn, request_id)}
    finally:
        conn.close()


@router.post("/api/v1/desk-requests/landed", tags=["Phone"])
def desk_request_landed(payload: DeskLandingPayload):
    """
    From the extension, through its worker: a post page that kept a short
    link's #inox-desk-<id> fragment, and the post it names. One of the
    creator's posts is attached to that request; anyone else's refuses it.
    The studio never follows the short link itself.
    """
    conn = get_db()
    try:
        return {"status": "success", **desk_requests.landed(conn, payload.request_id, payload.activity_urn)}
    finally:
        conn.close()
