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
from pydantic import BaseModel, Field

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
    )
    from ..linkedin_client import linkedin_client
    from ..event_bus import event_bus
    from .. import post_identity
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
    )
    from linkedin_client import linkedin_client
    from event_bus import event_bus
    import post_identity

router = APIRouter()


class PostCreate(BaseModel):
    content: str
    media_urls: Optional[List[str]] = []
    status: Optional[str] = "draft"
    scheduled_for: Optional[str] = None
    tags: Optional[List[str]] = []


class PostUpdate(BaseModel):
    content: Optional[str] = None
    media_urls: Optional[List[str]] = None
    status: Optional[str] = None
    scheduled_for: Optional[str] = None
    tags: Optional[List[str]] = None


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


class BindUrnRequest(BaseModel):
    activity_urn: str
    post_text: Optional[str] = ""


@router.get("/api/posts")
def list_posts(status: Optional[str] = None):
    conn = get_db()
    try:
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT * FROM posts WHERE status = ? ORDER BY COALESCE(scheduled_for, created_at) ASC", (status,))
        else:
            cursor.execute("SELECT * FROM posts ORDER BY created_at DESC")

        rows = []
        for r in cursor.fetchall():
            d = dict(r)
            d["media_urls"] = json.loads(d["media_urls"]) if d["media_urls"] else []
            d["tags"] = json.loads(d["tags"]) if d["tags"] else []
            rows.append(d)
        conn.close()
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




@router.delete("/api/posts/{post_id}")
def delete_post(post_id: str):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Post deleted"}
    finally:
        conn.close()




@router.post("/api/format/re-hook")
def get_10x_hooks(req: FormatRequest):
    return {"status": "success", "hooks": generate_10x_hooks(req.text)}


@router.post("/api/format/algorithm-audit")
def audit_algorithm(req: FormatRequest):
    return audit_linkedin_algorithm_safety(req.text)


@router.post("/api/format/repurpose")
def repurpose(req: FormatRequest):
    return {"status": "success", "frameworks": repurpose_content(req.text)}


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


@router.post("/api/format/analyze")
def format_analyze(req: FormatRequest):
    return analyze_hook(req.text)


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


@router.post("/api/format/dwell")
def format_dwell(req: FormatRequest):
    return calculate_dwell_metrics(req.text)


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

    conn = get_db()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM posts WHERE content_fingerprint = ? AND activity_urn IS NULL",
                (fingerprint,),
            )
            existing = cursor.fetchone()
            now = datetime.now(timezone.utc).isoformat()

            if existing:
                post_id = existing["id"]
                cursor.execute(
                    "UPDATE posts SET published_at = ?, status = 'published' WHERE id = ?",
                    (now, post_id),
                )
            else:
                post_id = f"post-{uuid.uuid4().hex[:12]}"
                cursor.execute(
                    """
                    INSERT INTO posts (id, content, status, published_at, content_fingerprint, draft_id)
                    VALUES (?, ?, 'published', ?, ?, ?)
                    """,
                    (post_id, req.content, now, fingerprint, req.draft_id),
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
    urn = post_identity.extract_activity_urn(req.activity_urn) or req.activity_urn
    if not post_identity.ACTIVITY_URN_PATTERN.fullmatch(urn or ""):
        return {"status": "invalid_urn", "bound": False, "activity_urn": urn}

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM posts WHERE activity_urn = ?", (urn,))
        already = cursor.fetchone()
        if already:
            return {"status": "already_bound", "bound": True, "post_id": already["id"], "activity_urn": urn}

        cursor.execute(
            """
            SELECT id, content_fingerprint FROM posts
            WHERE activity_urn IS NULL AND content_fingerprint IS NOT NULL
            ORDER BY published_at DESC
            LIMIT 50
            """
        )
        candidates = cursor.fetchall()

        for row in candidates:
            if post_identity.fingerprint_matches(req.post_text or "", row["content_fingerprint"]):
                with conn:
                    conn.execute(
                        "UPDATE posts SET activity_urn = ? WHERE id = ?", (urn, row["id"])
                    )
                return {
                    "status": "bound",
                    "bound": True,
                    "post_id": row["id"],
                    "activity_urn": urn,
                }

        return {
            "status": "no_match",
            "bound": False,
            "activity_urn": urn,
            "candidates_considered": len(candidates),
        }
    finally:
        conn.close()


@router.get("/api/v1/posts/{post_id}/engagers", tags=["Post Identity"])
def get_post_engagers(post_id: str):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, activity_urn, content FROM posts WHERE id = ?", (post_id,))
        post = cursor.fetchone()
        if not post:
            raise HTTPException(status_code=404, detail="No such post")

        if not post["activity_urn"]:
            return {
                "status": "unbound",
                "post_id": post_id,
                "engagers": [],
                "message": "This post has no LinkedIn URN yet. Open it on LinkedIn once to bind it.",
            }

        cursor.execute(
            """
            SELECT l.id, l.full_name, l.name, l.headline, l.company,
                   l.seniority_level, l.icp_score, l.profile_url,
                   i.interaction_type, i.comment_text, i.interacted_at
            FROM lead_interactions i
            JOIN leads l ON l.id = i.lead_id
            WHERE i.post_urn = ?
            ORDER BY l.icp_score DESC
            """,
            (post["activity_urn"],),
        )
        engagers = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    return {
        "status": "success",
        "post_id": post_id,
        "activity_urn": post["activity_urn"],
        "count": len(engagers),
        "engagers": engagers,
    }
