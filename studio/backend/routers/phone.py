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

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from .. import ingress
except (ImportError, ValueError):
    import ingress

router = APIRouter()


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
