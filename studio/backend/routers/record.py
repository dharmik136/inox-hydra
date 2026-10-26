"""
From your record: the section's routes.
=======================================
What the section "From your record" reads and asks for. The day's batch is
read, never computed, by GET /api/v1/record: the daily job builds it the
first time the studio runs each day (record_daily.py). Every write here is
an act of the creator's: an ask typed or ticked, a mark, More of this,
Draft from this, a setting, a note.

Strict Invariants:
- Zero em-dashes in all code, comments, and strings.
- Nothing here calls a model or opens a connection on a GET.
"""

from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from .. import record_daily, record_evaluation, record_model, record_store
except (ImportError, ValueError):
    import record_daily
    import record_evaluation
    import record_model
    import record_store

router = APIRouter(tags=["From your record"])

_DAY = r"^\d{4}-\d{2}-\d{2}$"


class CardRef(BaseModel):
    day: str = Field(..., pattern=_DAY)
    card_id: str = Field(..., min_length=1, max_length=300)


class MarkRequest(CardRef):
    mark: str = Field(..., max_length=10)


class AskRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=record_store.MAX_ASK_CHARS)
    source: str = Field("ask_box", max_length=20)


class AskChange(BaseModel):
    text: Optional[str] = Field(None, max_length=record_store.MAX_ASK_CHARS)
    status: Optional[str] = Field(None, max_length=10)


class SetupField(BaseModel):
    text: str = Field("", max_length=record_store.MAX_ASK_CHARS)


class SettingsChange(BaseModel):
    changes: Dict[str, Any]


class NoteRequest(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    text: str = Field("", max_length=record_store.MAX_ASK_CHARS)


def _refused(call):
    try:
        return call()
    except record_store.Refused as refused:
        raise HTTPException(status_code=400, detail=str(refused))


@router.get("/api/v1/record")
def get_record():
    """
    Today's batch, or the newest before it with the sentence that says so,
    and what the model stage can do today. A read: nothing is computed and
    nothing is sent.
    """
    return {**record_daily.read_today(), "model": record_model.state()}


@router.post("/api/v1/record/model")
def post_record_model():
    """
    The creator opened the section: today's one call to their own model, if
    it has not run and may. Answers at once; the idea arrives into today's
    row when the model has answered.
    """
    return record_model.run_on_open()


@router.get("/api/v1/record/model/preview")
def get_record_model_preview():
    """Exactly what the next call would send, to read. Sends nothing."""
    return record_model.preview()


@router.get("/api/v1/record/days/{day}")
def get_record_day(day: str):
    """An earlier day's batch as it was shown, with the marks made on it."""
    try:
        wanted = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="A day is written as YYYY-MM-DD.")
    return record_daily.read_day(wanted)


@router.post("/api/v1/record/reroll")
def post_record_reroll():
    """Suggest new: today's batch drawn again, once a day."""
    answer = record_daily.run_today(reroll=True)
    if answer["status"] == "refused":
        raise HTTPException(status_code=409, detail=answer["message"])
    return answer


@router.post("/api/v1/record/marks")
def post_record_mark(payload: MarkRequest):
    return _refused(lambda: record_store.mark(payload.day, payload.card_id, payload.mark))


@router.post("/api/v1/record/marks/remove")
def post_record_unmark(payload: MarkRequest):
    return _refused(lambda: record_store.unmark(payload.day, payload.card_id, payload.mark))


@router.post("/api/v1/record/unhide-all")
def post_record_unhide_all():
    return record_store.unhide_all()


@router.post("/api/v1/record/more")
def post_record_more(payload: CardRef):
    """More of this: the card's topic becomes an ask."""
    return _refused(lambda: record_store.more_of_this(payload.day, payload.card_id))


@router.post("/api/v1/record/draft")
def post_record_draft(payload: CardRef):
    """Draft from this: a Composer draft that records the card it came from."""
    return _refused(lambda: record_store.draft_from(payload.day, payload.card_id))


@router.get("/api/v1/record/kept")
def get_record_kept():
    """The Kept level: every card the creator kept."""
    return {"kept": record_store.kept()}


@router.get("/api/v1/record/knows")
def get_record_knows():
    """What the studio knows: asks, Setup fields, marks, archive records, settings and the job's state."""
    return {**record_store.knows(), "job": record_daily.status(), "model": record_model.state()}


@router.post("/api/v1/record/asks")
def post_record_ask(payload: AskRequest):
    """An ask typed into the section's box, or an instruction the creator ticked "remember this" on."""
    if payload.source not in ("ask_box", "composer"):
        raise HTTPException(status_code=400, detail="An ask typed here comes from the ask box or the Composer.")
    return _refused(lambda: record_store.add_ask(payload.text, payload.source))


@router.put("/api/v1/record/asks/{ask_id}")
def put_record_ask(ask_id: int, payload: AskChange):
    return _refused(lambda: record_store.update_ask(ask_id, payload.text, payload.status))


@router.delete("/api/v1/record/asks/{ask_id}")
def delete_record_ask(ask_id: int):
    return _refused(lambda: record_store.remove_ask(ask_id))


@router.get("/api/v1/record/setup")
def get_record_setup():
    return {"fields": record_store.setup_fields()}


@router.put("/api/v1/record/setup/{field}")
def put_record_setup(field: str, payload: SetupField):
    return _refused(lambda: record_store.set_setup_field(field, payload.text))


@router.put("/api/v1/record/settings")
def put_record_settings(payload: SettingsChange):
    return _refused(lambda: record_store.set_settings(payload.changes))


@router.get("/api/v1/record/evaluation")
def get_record_evaluation():
    """Did these help? The marks as counts, the comparison at 48 hours, and a sentence a month, each able to abstain."""
    return record_evaluation.overview()


@router.post("/api/v1/record/notes")
def post_record_note(payload: NoteRequest):
    return _refused(lambda: record_store.save_note(payload.month, payload.text))
