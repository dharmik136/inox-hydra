"""
Posts, Formatting, and Post Identity API Router
===============================================
Draft composer, native scheduling dispatch, feed simulator, typography formatters,
algorithmic audit, and post identity binding. Zero cloud egress.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

try:
    from ..database import get_db
    from ..formatters import (
        to_sans_bold,
        to_sans_italic,
        to_serif_bold,
        to_serif_italic,
        to_blackboard_bold,
        to_underline,
        to_circled_numbers,
        to_monospace,
        to_strikethrough,
        clean_text_formatting,
        analyze_hook,
        calculate_dwell_metrics,
    )
    from ..repurposer import (
        generate_10x_hooks,
        audit_linkedin_algorithm_safety,
        repurpose_content,
    )
    from ..scheduler import (
        native_scheduler,
        parse_datetime_flexible,
        normalize_datetime_to_utc_iso,
        LINKEDIN_HOLDS_KEY,
        MISSED_POST_KEY,
    )
    from ..linkedin_client import linkedin_client
    from .. import post_identity
    from .. import post_summary
except (ImportError, ValueError):
    from database import get_db
    from formatters import (
        to_sans_bold,
        to_sans_italic,
        to_serif_bold,
        to_serif_italic,
        to_blackboard_bold,
        to_underline,
        to_circled_numbers,
        to_monospace,
        to_strikethrough,
        clean_text_formatting,
        analyze_hook,
        calculate_dwell_metrics,
    )
    from repurposer import (
        generate_10x_hooks,
        audit_linkedin_algorithm_safety,
        repurpose_content,
    )
    from scheduler import (
        native_scheduler,
        parse_datetime_flexible,
        normalize_datetime_to_utc_iso,
        LINKEDIN_HOLDS_KEY,
        MISSED_POST_KEY,
    )
    from linkedin_client import linkedin_client
    import post_identity
    import post_summary

router = APIRouter()


# Every status a post can be stored with. Any other string was stored as given
# ("banana", or a megabyte of text), and the post then appeared on no screen.
POST_STATUSES = frozenset({"draft", "scheduled", "queued", "due", "published", "sent", "failed"})


def _known_status(value: Optional[str]) -> Optional[str]:
    if value is not None and value not in POST_STATUSES:
        raise ValueError("status must be one of " + ", ".join(sorted(POST_STATUSES)))
    return value


class PostCreate(BaseModel):
    content: str
    media_urls: Optional[List[str]] = []
    status: Optional[str] = "draft"
    scheduled_for: Optional[str] = None
    tags: Optional[List[str]] = []

    @field_validator("status")
    @classmethod
    def _status_is_known(cls, value: Optional[str]) -> Optional[str]:
        return _known_status(value)


class PostUpdate(BaseModel):
    content: Optional[str] = None
    media_urls: Optional[List[str]] = None
    status: Optional[str] = None
    scheduled_for: Optional[str] = None
    tags: Optional[List[str]] = None

    @field_validator("status")
    @classmethod
    def _status_is_known(cls, value: Optional[str]) -> Optional[str]:
        return _known_status(value)
    # The text the editor last loaded or saved. When it is sent and the stored
    # post no longer matches it, someone else saved in between and the update
    # is refused rather than written over theirs. Callers that send none, such
    # as the queue, are unchanged.
    base_content: Optional[str] = None
    # True only from a caller that means to change the text of a post that is
    # already published, queued, due or sent. Without it such a change is
    # refused, because the likeliest sender is a stale editor still attached
    # to that post, writing the next post over it.
    edit_posted_text: bool = False


# Statuses whose text has left the drafting stage. "due" is a queued post
# whose time has come; "scheduled" is how a queued post is stored.
POSTED_STATUSES = {"published", "scheduled", "queued", "due", "sent"}

# The refusal's code, which the Composer acts on, and the words for each
# status. The words name the post the way the Composer's buttons do
# ("Correct the queued post"), so the message points at a control that exists.
POSTED_TEXT_LOCKED = "posted_text_locked"
POSTED_WORDS = {"published": "published", "scheduled": "queued", "queued": "queued", "due": "queued", "sent": "sent"}


# Starts the refusal. studio/ui/src/lib/api.ts recognises a conflict by it.
DRAFT_CHANGED_ELSEWHERE = "This draft was changed in another window"


class ReschedulePayload(BaseModel):
    scheduled_for: str


class FormatRequest(BaseModel):
    text: str = Field(..., max_length=20000)


class StagePostRequest(BaseModel):
    scheduled_at: str
    confirm: bool = False


class InjectedPostRequest(BaseModel):
    content: str
    draft_id: Optional[int] = None
    # The studio post the side panel was filled from, when it was one.
    post_id: Optional[str] = None


class BindUrnRequest(BaseModel):
    activity_urn: str
    post_text: Optional[str] = ""
    # The vanity of the post's author, as the page showed it.
    post_author: Optional[str] = None


@router.get("/api/posts")
def list_posts(status: Optional[str] = None, limit: Optional[int] = None):
    """
    Posts, filtered by status. Without a limit this answers with every one of
    them, as it always has.

    `limit` answers the newest that many instead, in the same order as the
    full list, so a caller that wants only the most recent draft no longer
    pays for all of them: on a three year install
    /api/posts?status=draft was 259 KB for 1,044 drafts, read on every load
    of the interface to reopen one of them.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        capped = max(1, int(limit)) if limit is not None else None
        if status:
            if capped is None:
                cursor.execute(
                    "SELECT * FROM posts WHERE status = ? ORDER BY COALESCE(scheduled_for, created_at) ASC",
                    (status,))
            else:
                # Taken newest first so the limit keeps the newest rows, then
                # put back into ascending order below, which is the order
                # every existing caller reads.
                cursor.execute(
                    "SELECT * FROM posts WHERE status = ? ORDER BY COALESCE(scheduled_for, created_at) DESC LIMIT ?",
                    (status, capped))
        elif capped is None:
            cursor.execute("SELECT * FROM posts ORDER BY created_at DESC")
        else:
            cursor.execute("SELECT * FROM posts ORDER BY created_at DESC LIMIT ?", (capped,))

        rows = []
        for r in cursor.fetchall():
            d = dict(r)
            d["media_urls"] = json.loads(d["media_urls"]) if d["media_urls"] else []
            d["tags"] = json.loads(d["tags"]) if d["tags"] else []
            rows.append(d)
        if status and capped is not None:
            rows.reverse()
        return {"status": "success", "posts": rows}
    finally:
        conn.close()


@router.post("/api/posts")
def create_post(post: PostCreate):
    if len(post.content) > 5000:
        raise HTTPException(status_code=400, detail="Post content exceeds maximum 5,000 character limit.")

    cadence_info = None
    sched_for = post.scheduled_for
    if post.status == "scheduled" and sched_for:
        val = native_scheduler.validate_schedule_cadence(sched_for)
        if not val["valid"]:
            raise HTTPException(status_code=400, detail=val["error"])
        cadence_info = {
            "has_collision": val.get("has_collision", False),
            "warning": val.get("warning"),
            "cadence_health_score": val.get("cadence_health_score", 100)
        }
        sched_for = normalize_datetime_to_utc_iso(sched_for) or sched_for

    post_id = f"post_{uuid.uuid4().hex[:10]}"
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO posts (id, content, media_urls, status, scheduled_for, tags)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            post_id,
            post.content,
            json.dumps(post.media_urls),
            post.status,
            sched_for,
            json.dumps(post.tags)
        ))
        conn.commit()
        conn.close()
        resp = {"status": "success", "id": post_id, "message": "Post created successfully"}
        if cadence_info:
            resp["cadence"] = cadence_info
        return resp
    finally:
        conn.close()


@router.put("/api/posts/{post_id}")
def update_post(post_id: str, updates: PostUpdate):
    if updates.content is not None and len(updates.content) > 5000:
        raise HTTPException(status_code=400, detail="Post content exceeds maximum 5,000 character limit.")

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        existing = cursor.fetchone()
        if not existing:
            conn.close()
            raise HTTPException(status_code=404, detail="Post not found")

        # Two windows on one draft: the later save used to replace the earlier
        # one without a word, while the earlier window still said SAVED.
        if updates.base_content is not None and existing["content"] != updates.base_content:
            conn.close()
            raise HTTPException(status_code=409, detail=(
                f"{DRAFT_CHANGED_ELSEWHERE} after this one opened it, so saving would replace that "
                "version. Keep this version to save over it, or copy your text and reload to see the other one."
            ))

        # A published or queued post keeps its text unless the caller says it
        # is editing that text on purpose. The Composer clears after Publish,
        # but a second tab or an older build still attached to the post would
        # otherwise save the next post over it.
        if (
            updates.content is not None
            and updates.content != existing["content"]
            and existing["status"] in POSTED_STATUSES
            and not updates.edit_posted_text
        ):
            conn.close()
            word = POSTED_WORDS.get(existing["status"], existing["status"])
            raise HTTPException(status_code=409, detail={
                "code": POSTED_TEXT_LOCKED,
                "status": existing["status"],
                "message": (
                    f"This post is already {word}, so its text was not changed. Choose Correct the "
                    f"{word} post to change its text on purpose, or Save as a new draft to keep this "
                    "text as a separate post."
                ),
            })

        content = updates.content if updates.content is not None else existing["content"]
        media_urls = json.dumps(updates.media_urls) if updates.media_urls is not None else existing["media_urls"]
        status = updates.status if updates.status is not None else existing["status"]
        scheduled_for = updates.scheduled_for if updates.scheduled_for is not None else existing["scheduled_for"]
        tags = json.dumps(updates.tags) if updates.tags is not None else existing["tags"]

        cadence_info = None
        if status == "scheduled" and scheduled_for:
            val = native_scheduler.validate_schedule_cadence(scheduled_for, post_id=post_id)
            if not val["valid"]:
                conn.close()
                raise HTTPException(status_code=400, detail=val["error"])
            cadence_info = {
                "has_collision": val.get("has_collision", False),
                "warning": val.get("warning"),
                "cadence_health_score": val.get("cadence_health_score", 100)
            }
            scheduled_for = normalize_datetime_to_utc_iso(scheduled_for) or scheduled_for

        cursor.execute("""
        UPDATE posts
        SET content = ?, media_urls = ?, status = ?, scheduled_for = ?, tags = ?
        WHERE id = ?
        """, (content, media_urls, status, scheduled_for, tags, post_id))
        conn.commit()
        conn.close()
        resp = {"status": "success", "message": "Post updated successfully"}
        if cadence_info:
            resp["cadence"] = cadence_info
        return resp
    finally:
        conn.close()


@router.post("/api/posts/{post_id}/reschedule")
def reschedule_post(post_id: str, payload: ReschedulePayload):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Post not found")

        cadence_val = native_scheduler.validate_schedule_cadence(payload.scheduled_for, post_id=post_id)
        if not cadence_val["valid"]:
            raise HTTPException(status_code=400, detail=cadence_val["error"])

        normalized_sched = normalize_datetime_to_utc_iso(payload.scheduled_for) or payload.scheduled_for
        cursor.execute("UPDATE posts SET scheduled_for = ?, status = 'scheduled' WHERE id = ?", (normalized_sched, post_id))
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "success",
        "message": f"Post rescheduled to {payload.scheduled_for}",
        "cadence_warning": cadence_val.get("warning"),
        "has_collision": cadence_val.get("has_collision", False),
        "cadence_health_score": cadence_val.get("cadence_health_score", 100)
    }




@router.post("/api/posts/{post_id}/move-to-next-slot")
def move_post_to_next_slot(post_id: str):
    """
    A due post, usually one missed while the machine slept, queued again at
    the next free slot. Only on the creator's word: the scheduler never moves
    a post by itself.
    """
    try:
        slot = native_scheduler.move_to_next_slot(post_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Post not found")
    except ValueError:
        raise HTTPException(
            status_code=409,
            detail="This post is not due any more, so it was not moved. Reload to see where it is now.",
        )
    return {
        "status": "success",
        "scheduled_for": slot["slot_datetime"],
        "slot": slot,
        "message": f"Moved to {slot['day_name']} {slot['time_slot']}.",
    }


@router.delete("/api/posts/{post_id}")
def delete_post(post_id: str):
    """
    Deletes a post that has not gone out: a draft, which the Composer's
    drafts list deletes, or a queued one.

    A published or sent post is part of the creator's record, and one handed
    to LinkedIn's scheduler is held there whatever this database says, so
    those are kept. This used to delete any of them without a check, and
    answered "Post deleted" for an id that did not exist (BE-18).
    """
    conn = get_db()
    try:
        row = conn.execute("SELECT status FROM posts WHERE id = ?", (post_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="There is no such post. It may have been deleted already.")
        held = conn.execute(
            "SELECT 1 FROM settings WHERE key = ?", (LINKEDIN_HOLDS_KEY + post_id,)
        ).fetchone()
        if row["status"] in ("published", "sent") or held:
            word = "held by LinkedIn's scheduler" if held else POSTED_WORDS.get(row["status"], row["status"])
            raise HTTPException(
                status_code=409,
                detail=f"This post is {word}, not a draft, so it was kept.",
            )
        with conn:
            conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            conn.execute("DELETE FROM settings WHERE key = ?", (MISSED_POST_KEY + post_id,))
        return {"status": "success", "message": "Deleted"}
    finally:
        conn.close()




@router.post("/api/format/re-hook")
def get_10x_hooks(req: FormatRequest):
    return {"status": "success", "hooks": generate_10x_hooks(req.text)}


@router.post("/api/format/algorithm-audit")
def audit_algorithm(req: FormatRequest):
    return audit_linkedin_algorithm_safety(req.text)


@router.post("/api/format/bold")
def format_bold(req: FormatRequest):
    return {"formatted": to_sans_bold(req.text)}


@router.post("/api/format/italic")
def format_italic(req: FormatRequest):
    return {"formatted": to_sans_italic(req.text)}


@router.post("/api/format/monospace")
def format_mono(req: FormatRequest):
    return {"formatted": to_monospace(req.text)}


@router.post("/api/format/strikethrough")
def format_strike(req: FormatRequest):
    return {"formatted": to_strikethrough(req.text)}


@router.post("/api/format/clean")
def format_clean(req: FormatRequest):
    return {"cleaned": clean_text_formatting(req.text)}


@router.post("/api/format/serif-bold")
def format_serif_bold(req: FormatRequest):
    return {"formatted": to_serif_bold(req.text)}


@router.post("/api/format/serif-italic")
def format_serif_italic(req: FormatRequest):
    return {"formatted": to_serif_italic(req.text)}


@router.post("/api/format/blackboard")
def format_blackboard(req: FormatRequest):
    return {"formatted": to_blackboard_bold(req.text)}


@router.post("/api/format/underline")
def format_underline(req: FormatRequest):
    return {"formatted": to_underline(req.text)}


@router.post("/api/format/circled-numbers")
def format_circled_numbers(req: FormatRequest):
    return {"formatted": to_circled_numbers(req.text)}


@router.post("/api/v1/posts/injected", tags=["Post Identity"])
def record_injected_post(req: InjectedPostRequest):
    fingerprint = post_identity.content_fingerprint(req.content)
    if fingerprint is None:
        return {
            "status": "too_short",
            "message": (
                "This text is too short to identify the post again later. "
                "It was injected, but engagement cannot be attributed to it."
            ),
        }

    # Inserting is not publishing. The creator may close LinkedIn's composer,
    # edit, or post next week, so the row is armed (it carries the
    # fingerprint) and keeps its status. It becomes published when the creator
    # opens the post on LinkedIn and bind-urn sees it, or when they mark it.
    # This used to write status 'published' stamped with the moment of
    # insertion, so a post nobody posted showed in Analytics and the cadence,
    # and an insert of a queued post made a second row that left the queued
    # one to come due again.
    conn = get_db()
    try:
        with conn:
            cursor = conn.cursor()
            existing = None
            if req.post_id:
                # The side panel names the queued post it was filled from. It
                # is that post only while its opening is still what is being
                # inserted; an edited text is a different post.
                row = cursor.execute(
                    "SELECT id, content FROM posts WHERE id = ? AND activity_urn IS NULL",
                    (req.post_id,),
                ).fetchone()
                if row and post_identity.fingerprint_matches(row["content"] or "", fingerprint):
                    existing = row
            if existing is None:
                # The Composer's own draft or queued post of the same text, so
                # the post does not exist twice.
                rows = cursor.execute(
                    "SELECT id, content, content_fingerprint FROM posts WHERE activity_urn IS NULL"
                ).fetchall()
                found = [
                    r for r in rows
                    if r["content_fingerprint"] == fingerprint
                    or post_identity.content_fingerprint(r["content"] or "") == fingerprint
                ]
                existing = found[0] if len(found) == 1 else None
                if len(found) > 1:
                    # More than one post opens this way. Arming one at random
                    # would bind the wrong one; recording another would make
                    # the binding ambiguous anyway.
                    return {
                        "status": "ambiguous",
                        "message": (
                            "More than one post in the studio opens with this text, so the "
                            "studio cannot tell which one this is. Mark it as published in "
                            "the Composer once it is posted."
                        ),
                    }

            if existing:
                post_id = existing["id"]
                cursor.execute(
                    "UPDATE posts SET content_fingerprint = ? WHERE id = ?",
                    (fingerprint, post_id),
                )
            else:
                post_id = f"post-{uuid.uuid4().hex[:12]}"
                cursor.execute(
                    """
                    INSERT INTO posts (id, content, status, content_fingerprint, draft_id)
                    VALUES (?, ?, 'injected', ?, ?)
                    """,
                    (post_id, req.content, fingerprint, req.draft_id),
                )
    finally:
        conn.close()

    return {
        "status": "recorded",
        "post_id": post_id,
        "content_fingerprint": fingerprint,
        "message": "Open this post on LinkedIn once and the studio will bind its URN.",
    }


@router.post("/api/v1/posts/bind-urn", tags=["Post Identity"])
def bind_post_urn(req: BindUrnRequest):
    """
    Binds the post on the permalink the creator just opened to the studio
    record it came from.

    The rule lives in post_identity.bind_activity_urn, which is also what the
    history import binds with. There used to be two binders with different
    candidate sets and different tie breaks, so a post could bind one way and
    not the other.
    """
    conn = get_db()
    try:
        with conn:
            result = post_identity.bind_activity_urn(
                conn,
                req.activity_urn,
                req.post_text or "",
                author_vanity=req.post_author,
            )
        # The permalink route runs on every post the creator opens, so text
        # too short to identify anything is simply no match, as it was before.
        if result["status"] == "too_short":
            return {"status": "no_match", "bound": False, "activity_urn": result["activity_urn"],
                    "candidates_considered": 0}
        return result
    finally:
        conn.close()


@router.get("/api/v1/posts/{post_id}/engagers", tags=["Post Identity"])
def get_post_engagers(post_id: str):
    """
    Who engaged with a post, for any identifier the product uses: the studio's
    own id, an activity, share or ugcPost URN, a permalink, or a fingerprint.

    It used to take a studio id only, so the 523 posts the extension had
    imported but the studio had no row for answered 404, and the busiest post
    in a three year install could not be asked about at all. The join is the
    one post_summary documents: lead_interactions.lead_id is declared INTEGER
    and leads.id is TEXT, so a join written l.id = i.lead_id applies numeric
    affinity and scans every lead.
    """
    conn = get_db()
    try:
        ref = post_identity.resolve(conn, post_id)
        if not ref:
            raise HTTPException(status_code=404, detail="No such post")

        if not ref["engagement_urns"]:
            return {
                "status": "unbound",
                "post_id": ref["post_id"],
                "engagers": [],
                "message": "This post has no LinkedIn URN yet. Open it on LinkedIn once to bind it.",
            }

        cursor = conn.cursor()
        # post_summary.LEAD_JOIN, the one join in the codebase that can read
        # this table by index: lead_interactions.lead_id is declared INTEGER
        # and leads.id is TEXT, so a join written l.id = i.lead_id applies
        # numeric affinity and the leads primary key cannot serve it. Written
        # that way this read scanned all 49,142 leads (7.66 ms for one post of
        # three years); by the index it is 0.12 ms, for the same rows in the
        # same order. The last two sort keys are the order the old scan met
        # rows in.
        cursor.execute(
            f"""
            SELECT l.id, l.full_name, l.name, l.headline, l.company,
                   l.seniority_level, l.icp_score, l.profile_url,
                   i.interaction_type, i.comment_text, i.interacted_at
            FROM lead_interactions i {post_summary.LEAD_JOIN}
            WHERE i.post_urn IN ({', '.join('?' for _ in ref['engagement_urns'])})
            ORDER BY l.icp_score DESC, l.rowid, i.id
            """,
            ref["engagement_urns"],
        )
        engagers = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    return {
        "status": "success",
        "post_id": ref["post_id"],
        "activity_urn": ref["publication_urn"],
        "count": len(engagers),
        "engagers": engagers,
    }
