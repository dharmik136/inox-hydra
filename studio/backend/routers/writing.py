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
    from .. import remembered, writing
except (ImportError, ValueError):
    import remembered
    import writing

router = APIRouter()


class ReshapeButton(BaseModel):
    # The limits a button is held to are writing.py's, refused with its sentence; these only bound the request.
    label: str = Field(..., max_length=200, description="The button's label, as the phone shows it")
    asks: str = Field(..., max_length=1000, description="What the rewrite asks the writer for, in your words")


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
    memory: Optional[str] = Field(None, max_length=10, description="Things to remember: all, chosen or off")
    ideas: Optional[int] = Field(None, description="How many ideas the daily model stage asks for, 1 to 5")
    combine_at_most: Optional[int] = Field(None, description="The most items one draft is written from, 2 to 20")
    reshapes: Optional[List[ReshapeButton]] = Field(None, max_length=50,
                                                    description="The rewrite buttons under a draft the bot wrote")


@router.get("/api/v1/writing/preferences", tags=["Writing"])
def get_writing_preferences():
    """Each writing preference with its value, its default and its choices, and the provider every request uses."""
    return writing.described()


class FactPayload(BaseModel):
    text: str = Field(..., max_length=remembered.TEXT_MAX + 50, description="The thing to remember, in a sentence")
    about: str = Field("you", max_length=20, description="you, audience, offer or date")


class FactChange(BaseModel):
    text: Optional[str] = Field(None, max_length=remembered.TEXT_MAX + 50)
    about: Optional[str] = Field(None, max_length=20)
    in_use: Optional[bool] = Field(None, description="Used in writing while only the ticked ones go")


def _fact(work):
    try:
        return work()
    except remembered.Refused as refused:
        raise HTTPException(status_code=400, detail=str(refused))
    except LookupError as gone:
        raise HTTPException(status_code=404, detail=str(gone))


@router.get("/api/v1/remembered", tags=["Writing"])
def get_remembered():
    """Things to remember: every fact, what each is about, whether it is ticked, and which go with writing."""
    return {"status": "success", "facts": remembered.listing(), "mode": writing.preferences()["memory"],
            "about": remembered.ABOUT}


@router.post("/api/v1/remembered", tags=["Writing"])
def post_remembered(payload: FactPayload):
    """Keeps a thing to remember; the same words again are kept once."""
    return _fact(lambda: {"status": "success", "fact": remembered.add(payload.text, payload.about, "studio")})


@router.put("/api/v1/remembered/{fact_id}", tags=["Writing"])
def put_remembered(fact_id: int, payload: FactChange):
    """Changes a fact's words, what it is about, or whether it is ticked."""
    return _fact(lambda: {"status": "success",
                          "fact": remembered.update(fact_id, payload.text, payload.about, payload.in_use)})


@router.delete("/api/v1/remembered/{fact_id}", tags=["Writing"])
def delete_remembered(fact_id: int):
    """Removes a thing to remember for good."""
    if not remembered.remove(fact_id):
        raise HTTPException(status_code=404, detail="That thing to remember is no longer kept.")
    return {"status": "success", "removed": True}


@router.put("/api/v1/writing/preferences", tags=["Writing"])
def put_writing_preferences(payload: PreferencesPayload):
    """Saves the preferences sent; one not sent keeps its value. Outside its choices, nothing is saved."""
    try:
        return writing.save(payload.model_dump(exclude_none=True))
    except writing.Refused as refused:
        raise HTTPException(status_code=400, detail=str(refused))
