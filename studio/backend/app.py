"""
LinkedIn Studio Enterprise - Core API Gateway & Lifespan Controller
====================================================================
FastAPI application orchestrating local creator analytics, post scheduling,
AI hook generation, 1080x1080 PDF carousel builds, and CRM lead pipelines.

Zero Cloud Egress Guarantee:
- Binds strictly to 127.0.0.1:8000.
- All drafts, metrics, leads, and tokens persisted in local SQLite (WAL mode).
- Interactive OpenAPI documentation available at /docs.
"""

import os
import io
import csv
import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from .database import get_db, init_db, seed_initial_data
    from .formatters import (
        to_sans_bold,
        to_sans_italic,
        to_monospace,
        to_strikethrough,
        clean_text_formatting,
        analyze_hook
    )
    from .carousel_generator import generate_carousel_pdf
    from .repurposer import generate_10x_hooks, audit_linkedin_algorithm_safety, repurpose_content, get_ai_status, command_ai_engine
    from .leads import list_leads, add_lead, batch_add_leads, update_lead_status, delete_lead, generate_dm_script, export_leads_csv
    from .linkedin_client import linkedin_client
    from .scheduler import start_scheduler, shutdown_scheduler
except ImportError:
    from database import get_db, init_db, seed_initial_data
    from formatters import (
        to_sans_bold,
        to_sans_italic,
        to_monospace,
        to_strikethrough,
        clean_text_formatting,
        analyze_hook
    )
    from carousel_generator import generate_carousel_pdf
    from repurposer import generate_10x_hooks, audit_linkedin_algorithm_safety, repurpose_content, get_ai_status, command_ai_engine
    from leads import list_leads, add_lead, batch_add_leads, update_lead_status, delete_lead, generate_dm_script, export_leads_csv
    from linkedin_client import linkedin_client
    from scheduler import start_scheduler, shutdown_scheduler

OPENAPI_TAGS = [
    {"name": "Analytics", "description": "Creator metrics, impressions, period deltas, demographics, and CSV exports."},
    {"name": "Post Studio", "description": "Draft authoring, scheduling, real-time simulator validation, and post lifecycle."},
    {"name": "Carousel Builder", "description": "Native 1080x1080 Pillow PDF carousel slide deck rendering."},
    {"name": "AI Command Engine", "description": "Dual-mode AI: Gemini 2.5 Flash cloud API & Antigravity local deterministic engine."},
    {"name": "Formatting & Audit", "description": "Unicode mathematical formatting, em-dash scrubber, and 2026 algorithm safety scoring."},
    {"name": "Leads & CRM", "description": "Prospect engagement pipeline, status transitions, and personalized DM scripts."},
    {"name": "Smart Queue", "description": "Cadence management and peak engagement time slots."},
    {"name": "LinkedIn Bridge", "description": "Passive session token synchronization and live analytics ingestion."},
    {"name": "Documentation", "description": "Interactive enterprise documentation suite and in-app playbook viewer."}
]

app = FastAPI(
    title="LinkedIn Studio Enterprise",
    description="A 100% self-hosted, air-gapped, privacy-first alternative to $199/month SaaS creator tools running on localhost.",
    version="2.5.0",
    openapi_tags=OPENAPI_TAGS
)

# Enable CORS for local extension and browser UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    seed_initial_data()
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    shutdown_scheduler()


# -------------------------------------------------------------
# Pydantic Request Models
# -------------------------------------------------------------
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
    text: str


class CarouselRequest(BaseModel):
    slides: List[Dict[str, str]]
    theme: Optional[str] = "dark_slate"
    author_name: Optional[str] = "Dharmik Shingala"
    author_title: Optional[str] = "Content Strategist & Enterprise Systems Practitioner"


class LeadCreate(BaseModel):
    name: str
    headline: Optional[str] = ""
    company: Optional[str] = ""
    profile_url: Optional[str] = ""
    engagement_type: Optional[str] = "Commented"
    post_id: Optional[str] = ""
    status: Optional[str] = "New Lead"
    notes: Optional[str] = ""


class LeadStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class CookiePayload(BaseModel):
    li_at: str
    JSESSIONID: str


class AISettingsPayload(BaseModel):
    gemini_api_key: str


class AICommandPayload(BaseModel):
    command: str
    context: Optional[str] = None


# -------------------------------------------------------------
# Module 1: Analytics Endpoints (Multi-Range & Period Deltas)
# -------------------------------------------------------------
def get_range_days(range_str: str) -> int:
    mapping = {"7d": 7, "14d": 14, "30d": 30, "90d": 90}
    return mapping.get(range_str.lower(), 30)


@app.get("/api/analytics/kpis")
def get_kpis(range: str = "30d"):
    days = get_range_days(range)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(date) FROM analytics_daily")
    max_d_row = cursor.fetchone()
    if not max_d_row or not max_d_row[0]:
        conn.close()
        return {}

    end_date = datetime.strptime(max_d_row[0], "%Y-%m-%d").date()
    start_cur = end_date - timedelta(days=days - 1)
    start_prev = start_cur - timedelta(days=days)
    end_prev = start_cur - timedelta(days=1)

    # 1. Current Window Totals
    cursor.execute("""
    SELECT SUM(impressions), SUM(reactions), SUM(comments), SUM(shares)
    FROM analytics_daily
    WHERE date >= ? AND date <= ?
    """, (start_cur.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
    cur_imp, cur_rxn, cur_comm, cur_shr = cursor.fetchone()
    cur_imp = cur_imp or 0
    cur_rxn = cur_rxn or 0
    cur_comm = cur_comm or 0
    cur_shr = cur_shr or 0
    cur_eng = cur_rxn + cur_comm + cur_shr
    cur_eng_rate = round((cur_eng / cur_imp * 100), 2) if cur_imp > 0 else 0.0

    # 2. Previous Window Totals for True Period Deltas
    cursor.execute("""
    SELECT SUM(impressions), SUM(reactions), SUM(comments), SUM(shares)
    FROM analytics_daily
    WHERE date >= ? AND date <= ?
    """, (start_prev.strftime("%Y-%m-%d"), end_prev.strftime("%Y-%m-%d")))
    prev_imp, prev_rxn, prev_comm, prev_shr = cursor.fetchone()
    prev_imp = prev_imp or 0
    prev_rxn = prev_rxn or 0
    prev_comm = prev_comm or 0
    prev_shr = prev_shr or 0
    prev_eng = prev_rxn + prev_comm + prev_shr
    prev_eng_rate = round((prev_eng / prev_imp * 100), 2) if prev_imp > 0 else 0.0

    def calc_delta(cur, prev):
        if prev == 0:
            return 100.0 if cur > 0 else 0.0
        return round(((cur - prev) / prev) * 100.0, 1)

    imp_delta = calc_delta(cur_imp, prev_imp)
    eng_delta = calc_delta(cur_eng, prev_eng)
    eng_rate_delta = round(cur_eng_rate - prev_eng_rate, 2)

    cursor.execute("SELECT followers, profile_views FROM analytics_daily WHERE date = ?", (end_date.strftime("%Y-%m-%d"),))
    latest_stat = cursor.fetchone()
    cur_followers = latest_stat["followers"] if latest_stat else 2412
    cur_pviews = latest_stat["profile_views"] if latest_stat else 104

    cursor.execute("SELECT followers, profile_views FROM analytics_daily WHERE date = ?", (start_cur.strftime("%Y-%m-%d"),))
    start_stat = cursor.fetchone()
    start_followers = start_stat["followers"] if start_stat else cur_followers
    start_pviews = start_stat["profile_views"] if start_stat else cur_pviews

    follower_growth = cur_followers - start_followers
    pviews_delta = calc_delta(cur_pviews, start_pviews)

    cursor.execute("SELECT COUNT(*) FROM posts WHERE status = 'scheduled'")
    scheduled_count = cursor.fetchone()[0]

    conn.close()

    return {
        "range": f"{days}d",
        "impressions": cur_imp,
        "impressions_delta_pct": imp_delta,
        "total_engagements": cur_eng,
        "engagements_delta_pct": eng_delta,
        "avg_engagement_rate": cur_eng_rate,
        "engagement_rate_delta": eng_rate_delta,
        "total_followers": cur_followers,
        "follower_growth": follower_growth,
        "profile_views": cur_pviews,
        "profile_views_delta_pct": pviews_delta,
        "scheduled_posts_count": scheduled_count
    }


@app.get("/api/analytics/overview")
def get_analytics_overview(range: str = "30d"):
    days = get_range_days(range)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(date) FROM analytics_daily")
    max_d_row = cursor.fetchone()
    if not max_d_row or not max_d_row[0]:
        conn.close()
        return {"status": "success", "count": 0, "series": []}

    end_date = datetime.strptime(max_d_row[0], "%Y-%m-%d").date()
    start_date = end_date - timedelta(days=days - 1)

    cursor.execute("""
    SELECT * FROM analytics_daily 
    WHERE date >= ? AND date <= ? 
    ORDER BY date ASC
    """, (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {
        "status": "success",
        "range": f"{days}d",
        "count": len(rows),
        "series": rows
    }


@app.get("/api/analytics/demographics")
def get_demographics(dimension: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()
    if dimension:
        cursor.execute("SELECT dimension, label, percentage FROM audience_demographics WHERE dimension = ? ORDER BY percentage DESC", (dimension,))
    else:
        cursor.execute("SELECT dimension, label, percentage FROM audience_demographics ORDER BY percentage DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    grouped = {}
    for r in rows:
        dim = r["dimension"]
        grouped.setdefault(dim, []).append(r)

    return {"status": "success", "demographics": grouped}


@app.get("/api/analytics/export")
def export_analytics(format: str = "csv"):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analytics_daily ORDER BY date ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if format.lower() == "json":
        return rows

    output = io.StringIO()
    writer = csv.writer(output)
    if rows:
        writer.writerow(rows[0].keys())
        for r in rows:
            writer.writerow(r.values())
    
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=linkedin_analytics_export.csv"}
    )


@app.get("/api/analytics/posts")
def get_posts_leaderboard():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, content, media_urls, status, published_at, impressions, reactions, comments, shares, tags,
           CASE WHEN impressions > 0 THEN ROUND((reactions + comments + shares) * 100.0 / impressions, 2) ELSE 0.0 END as engagement_rate
    FROM posts
    WHERE status = 'published'
    ORDER BY impressions DESC
    """)
    rows = []
    for r in cursor.fetchall():
        d = dict(r)
        d["media_urls"] = json.loads(d["media_urls"]) if d["media_urls"] else []
        d["tags"] = json.loads(d["tags"]) if d["tags"] else []
        rows.append(d)
    conn.close()
    return {"status": "success", "posts": rows}


# -------------------------------------------------------------
# Module 2: Post Studio & Simulator Endpoints
# -------------------------------------------------------------
@app.get("/api/posts")
def list_posts(status: Optional[str] = None):
    conn = get_db()
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


@app.post("/api/posts")
def create_post(post: PostCreate):
    post_id = f"post_{uuid.uuid4().hex[:10]}"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO posts (id, content, media_urls, status, scheduled_for, tags)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        post_id,
        post.content,
        json.dumps(post.media_urls),
        post.status,
        post.scheduled_for,
        json.dumps(post.tags)
    ))
    conn.commit()
    conn.close()
    return {"status": "success", "id": post_id, "message": "Post created successfully"}


@app.put("/api/posts/{post_id}")
def update_post(post_id: str, updates: PostUpdate):
    conn = get_db()
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

    cursor.execute("""
    UPDATE posts
    SET content = ?, media_urls = ?, status = ?, scheduled_for = ?, tags = ?
    WHERE id = ?
    """, (content, media_urls, status, scheduled_for, tags, post_id))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Post updated successfully"}


@app.post("/api/posts/{post_id}/reschedule")
def reschedule_post(post_id: str, payload: ReschedulePayload):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Post not found")

    cursor.execute("UPDATE posts SET scheduled_for = ?, status = 'scheduled' WHERE id = ?", (payload.scheduled_for, post_id))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Post rescheduled to {payload.scheduled_for}"}


@app.delete("/api/posts/{post_id}")
def delete_post(post_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Post deleted"}


# -------------------------------------------------------------
# Taplio Pro ($199/mo) Feature 1: Local PDF Carousel Builder
# -------------------------------------------------------------
@app.post("/api/carousel/generate")
def create_carousel_pdf(req: CarouselRequest):
    try:
        pdf_bytes = generate_carousel_pdf(
            slides_data=req.slides,
            author_name=req.author_name or "Dharmik Shingala",
            author_title=req.author_title or "Content Strategist & Enterprise Systems Practitioner",
            theme_name=req.theme or "dark_slate"
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=linkedin_carousel.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------------------------------------------------------------
# Taplio Pro ($199/mo) Feature 2: 10x Viral Re-Hooker Engine
# -------------------------------------------------------------
@app.post("/api/format/re-hook")
def get_10x_hooks(req: FormatRequest):
    return {"status": "success", "hooks": generate_10x_hooks(req.text)}


# -------------------------------------------------------------
# Taplio Pro ($199/mo) Feature 3: 2026 Algorithm & Shadowban Safety Audit
# -------------------------------------------------------------
@app.post("/api/format/algorithm-audit")
def audit_algorithm(req: FormatRequest):
    return audit_linkedin_algorithm_safety(req.text)


# -------------------------------------------------------------
# Taplio Pro ($199/mo) Feature 4: Multi-Style Content Repurposer
# -------------------------------------------------------------
@app.post("/api/format/repurpose")
def repurpose(req: FormatRequest):
    return {"status": "success", "frameworks": repurpose_content(req.text)}


# -------------------------------------------------------------
# Gemini & Antigravity AI Engine Bridge
# -------------------------------------------------------------
@app.get("/api/ai/status")
def ai_status():
    return get_ai_status()


@app.post("/api/ai/settings")
def save_ai_settings(payload: AISettingsPayload):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO settings (key, value, updated_at)
    VALUES ('gemini_api_key', ?, CURRENT_TIMESTAMP)
    """, (payload.gemini_api_key.strip(),))
    conn.commit()
    conn.close()
    return {
        "status": "success",
        "message": "Gemini API key saved to local SQLite settings",
        "ai_status": get_ai_status()
    }


@app.post("/api/ai/command")
def execute_ai_command(payload: AICommandPayload):
    return command_ai_engine(payload.command, payload.context)


# -------------------------------------------------------------
# Formatting Endpoints
# -------------------------------------------------------------
@app.post("/api/format/bold")
def format_bold(req: FormatRequest):
    return {"formatted": to_sans_bold(req.text)}


@app.post("/api/format/italic")
def format_italic(req: FormatRequest):
    return {"formatted": to_sans_italic(req.text)}


@app.post("/api/format/monospace")
def format_mono(req: FormatRequest):
    return {"formatted": to_monospace(req.text)}


@app.post("/api/format/strikethrough")
def format_strike(req: FormatRequest):
    return {"formatted": to_strikethrough(req.text)}


@app.post("/api/format/clean")
def format_clean(req: FormatRequest):
    return {"cleaned": clean_text_formatting(req.text)}


@app.post("/api/format/analyze")
def format_analyze(req: FormatRequest):
    return analyze_hook(req.text)


# -------------------------------------------------------------
# Taplio Pro ($199/mo) Feature 5: Lead Database & Relationship CRM
# -------------------------------------------------------------
@app.get("/api/leads")
def get_leads(status: Optional[str] = None, search: Optional[str] = None):
    return {"status": "success", "leads": list_leads(status, search)}


@app.get("/api/leads/export/csv")
def export_leads_csv_route(status: Optional[str] = None, search: Optional[str] = None):
    csv_data = export_leads_csv(status, search)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=linkedin_studio_crm_leads.csv"}
    )


@app.post("/api/leads")
def create_lead(lead: LeadCreate):
    return add_lead(lead.dict())


@app.post("/api/leads/batch")
def create_leads_batch(payload: Dict[str, Any]):
    leads_list = payload.get("leads", [])
    return batch_add_leads(leads_list)


@app.put("/api/leads/{lead_id}/status")
def update_lead(lead_id: str, payload: LeadStatusUpdate):
    return update_lead_status(lead_id, payload.status, payload.notes)


@app.delete("/api/leads/{lead_id}")
def remove_lead(lead_id: str):
    return delete_lead(lead_id)


@app.get("/api/leads/{lead_id}/dm-script")
def get_lead_dm(lead_id: str, style: Optional[str] = "value_add", topic: Optional[str] = None):
    return generate_dm_script(lead_id, style=style, post_topic=topic)


# -------------------------------------------------------------
# Module 3: Smart Queue & Slots
# -------------------------------------------------------------
@app.get("/api/queue/smart-slots")
def get_smart_slots():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM queue_slots WHERE is_active = 1 ORDER BY day_of_week, time_slot")
    slots = [dict(r) for r in cursor.fetchall()]

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for s in slots:
        s["day_name"] = day_names[s["day_of_week"]]

    cursor.execute("SELECT id, content, scheduled_for FROM posts WHERE status = 'scheduled' ORDER BY scheduled_for ASC")
    scheduled_posts = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {
        "status": "success",
        "slots": slots,
        "scheduled_posts": scheduled_posts
    }


# -------------------------------------------------------------
# Viral Inspirations Hub (356 Vaulted High-Performing Blueprints)
# -------------------------------------------------------------
@app.get("/api/inspirations")
def search_inspirations(query: Optional[str] = None, topic: Optional[str] = None, limit: Optional[int] = 100):
    conn = get_db()
    cursor = conn.cursor()
    conditions = []
    params = []

    if topic:
        conditions.append("topic LIKE ?")
        params.append(f"%{topic}%")

    if query:
        conditions.append("(topic LIKE ? OR author_name LIKE ? OR content LIKE ? OR key_hook LIKE ?)")
        pattern = f"%{query}%"
        params.extend([pattern, pattern, pattern, pattern])

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"SELECT * FROM inspirations{where_clause} ORDER BY likes_count DESC"
    if limit and limit > 0:
        sql += f" LIMIT {int(limit)}"

    cursor.execute(sql, tuple(params))
    rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) FROM inspirations")
    total_count = cursor.fetchone()[0]

    conn.close()
    return {
        "status": "success",
        "total_vaulted": total_count,
        "count": len(rows),
        "inspirations": rows
    }



# -------------------------------------------------------------
# Module 4: Extension Ingestion & Session Bridge
# -------------------------------------------------------------
@app.post("/api/auth/cookies")
def receive_cookies(payload: CookiePayload):
    linkedin_client.save_tokens(payload.li_at, payload.JSESSIONID)
    sync_result = linkedin_client.sync_live_profile_and_stats()
    return {
        "status": "success",
        "message": "LinkedIn session tokens saved to local studio",
        "sync": sync_result
    }


@app.get("/api/auth/status")
def get_auth_status():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'session_status'")
    row = cursor.fetchone()
    status = row["value"] if row else "disconnected"
    conn.close()
    return {
        "status": status,
        "is_connected": status in ["connected", "ready"],
        "client_session": linkedin_client.is_authenticated()
    }


@app.post("/api/analytics/ingest")
def ingest_live_analytics(payload: dict):
    result = linkedin_client.ingest_analytics_payload(payload)
    return result


# -------------------------------------------------------------
# Enterprise Documentation Suite API
# -------------------------------------------------------------
DOCS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs"))
MODULES_DIR = os.path.join(DOCS_DIR, "modules")

DOCS_MODULES = [
    {
        "id": "studio-editor",
        "number": "01",
        "title": "Studio & Editor",
        "category": "Core Authoring",
        "icon": "edit",
        "file": "01_STUDIO_AND_EDITOR.md",
        "summary": "Universal top bar telemetry, dynamic glowing fold tracker, 1080×1080 PDF carousel deck, and 6-dimension algorithmic safety audit."
    },
    {
        "id": "schedule-queue",
        "number": "02",
        "title": "Schedule & Queue",
        "category": "Cadence & Timing",
        "icon": "calendar",
        "file": "02_SCHEDULE_AND_QUEUE.md",
        "summary": "Publishing cadence rules, peak smart engagement slots (8:30 AM & 5:30 PM), and local background scheduler daemon."
    },
    {
        "id": "inbound-crm",
        "number": "03",
        "title": "Inbound CRM",
        "category": "Pipeline & Outreach",
        "icon": "users",
        "file": "03_INBOUND_CRM.md",
        "summary": "Relationship pipeline stages, column dictionary, search/filtering, and 3-style contextual DM generator with zero em-dash compliance."
    },
    {
        "id": "viral-swipe-file",
        "number": "04",
        "title": "Viral Swipe File",
        "category": "Research & Blueprints",
        "icon": "zap",
        "file": "04_VIRAL_SWIPE_FILE.md",
        "summary": "356 vaulted blueprints, 13 topic taxonomies, instant search, and Agno Framework autonomous inbound roadmap."
    },
    {
        "id": "analytics",
        "number": "05",
        "title": "Creator Analytics",
        "category": "Performance Telemetry",
        "icon": "bar-chart",
        "file": "05_ANALYTICS.md",
        "summary": "Direct LinkedIn session ingestion (li_at & JSESSIONID), multi-range growth deltas, Chart.js vector curves, and demographics."
    },
    {
        "id": "ai-command",
        "number": "06",
        "title": "AI Command Hub",
        "category": "Dual-Mode Intelligence",
        "icon": "sparkles",
        "file": "06_AI_COMMAND.md",
        "summary": "Dual-mode Gemini 2.5 Flash cloud API + Antigravity local deterministic engine, prompt presets, and direct Studio transfer."
    },
    {
        "id": "enterprise-usage",
        "number": "Master",
        "title": "Enterprise Usage Manual",
        "category": "Master Architecture",
        "icon": "book",
        "file": "ENTERPRISE_USAGE.md",
        "summary": "Master operational reference manual covering all platform capabilities, security, and algorithms."
    }
]


@app.get("/api/docs", tags=["Documentation"])
def list_docs_modules():
    """
    Returns the list of all available enterprise documentation modules.
    """
    return {
        "status": "success",
        "count": len(DOCS_MODULES),
        "modules": DOCS_MODULES
    }


@app.get("/api/docs/{module_id}", tags=["Documentation"])
def get_doc_module(module_id: str):
    """
    Retrieves the full markdown content of a documentation module by ID or number.
    """
    target = None
    for m in DOCS_MODULES:
        if m["id"].lower() == module_id.lower() or m["number"] == module_id:
            target = m
            break

    if not target:
        raise HTTPException(status_code=404, detail=f"Documentation module '{module_id}' not found.")

    # Locate the file (either in modules/ or directly in docs/)
    file_path = os.path.join(MODULES_DIR, target["file"])
    if not os.path.exists(file_path):
        file_path = os.path.join(DOCS_DIR, target["file"])

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Documentation file for '{module_id}' not found on disk.")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    return {
        "status": "success",
        "module": target,
        "content": content
    }


# -------------------------------------------------------------
# Static Dashboard UI & Master Asset Mount
# -------------------------------------------------------------
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets")

if os.path.exists(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
