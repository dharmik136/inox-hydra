"""
How the studio writes for the creator: their writing preferences.
================================================================
Phase 3 of the Telegram bot, and the owner's direction of 2026-10-29: every
choice a writing request makes is the creator's preference, read through
studio/backend/writing.py. Brand's Writing view reads and saves them here;
each feature that uses one shows its value beside it.

Strict Invariants:
- Zero em-dashes in all code, comments, and strings.
- Zero egress: saving a preference contacts nobody.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from .. import writing
except (ImportError, ValueError):
    import writing

router = APIRouter()


class PreferencesPayload(BaseModel):
    length_words: Optional[int] = Field(None, description="About how many words a draft is")
    tone: Optional[str] = Field(None, max_length=writing.TONE_MAX, description="How it sounds, in a few words")
    language: Optional[str] = Field(None, max_length=writing.LANGUAGE_MAX,
                                    description="The language to write in; empty for the language of the note")
    opening: Optional[str] = Field(None, max_length=40, description="One of Re-Hook's forms, or empty")
    emojis: Optional[str] = Field(None, max_length=20)
    hashtags: Optional[str] = Field(None, max_length=20)
    line_breaks: Optional[str] = Field(None, max_length=20)
    ending: Optional[str] = Field(None, max_length=30)
    avoid: Optional[List[str]] = Field(None, description="Words and phrases never to write")
    angles: Optional[int] = Field(None, description="How many opening lines Angles offers")
    sources: Optional[List[str]] = Field(None, description="What ideas may draw on: collection, posts, asks")


@router.get("/api/v1/writing/preferences", tags=["Writing"])
def get_writing_preferences():
    """Each writing preference with its value, its default and its choices, and the provider every request uses."""
    return writing.described()


@router.put("/api/v1/writing/preferences", tags=["Writing"])
def put_writing_preferences(payload: PreferencesPayload):
    """Saves the preferences sent; one not sent keeps its value. Outside its choices, nothing is saved."""
    try:
        return writing.save(payload.model_dump(exclude_none=True))
    except writing.Refused as refused:
        raise HTTPException(status_code=400, detail=str(refused))
