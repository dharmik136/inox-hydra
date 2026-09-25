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
import re
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta, timezone
from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, HTTPException, Response, UploadFile, File, Form, Request, Header, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

try:
    from ..__version__ import __version__
except ImportError:
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..")))
    from __version__ import __version__

try:
    from .database import get_db, init_db, seed_initial_data, create_draft, get_draft, list_drafts, schedule_draft, checkpoint_db
    from .formatters import (
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
        calculate_dwell_metrics
    )
    from .repurposer import generate_10x_hooks, audit_linkedin_algorithm_safety, repurpose_content, get_ai_status, command_ai_engine
    from .leads import list_leads, add_lead, batch_add_leads, update_lead_status, delete_lead, generate_dm_script, export_leads_csv
    from .linkedin_client import linkedin_client
    from . import egress as egress_policy
    from .scheduler import (start_scheduler, shutdown_scheduler, native_scheduler,
                            parse_datetime_flexible, normalize_datetime_to_utc_iso,
                            is_queue_paused, set_queue_paused)
    from .agno_agent import agno_orchestrator
    from .agno_agentos import orchestrator
    from .image_studio import image_studio_manager
    from .event_bus import event_bus
    from .ingress import IngressMessageParser, TelegramIngressDaemon, ingress_daemon
    from .crm import ICPScoringEngine, ReverseCRMManager, reverse_crm
    from .rate_limiter import rate_limiter, write_actor
    from .intelligence_sync import intelligence_sync_engine
    from .gstack_governance import gstack_engine
    from .internal_sheet import internal_sheet_manager
    from . import devtools
    from . import security
    from . import desktop as desktop_integration
    from .migrations import describe as describe_schema
    from . import support as support_tools
    from . import updates as update_checker
    from .paths import (get_assets_dir, get_uploads_dir, get_generated_dir, get_data_dir,
                        get_frontend_dir, get_docs_dir, get_modules_docs_dir, get_backups_dir,
                        describe as describe_paths)
    from .docs_engine import search_docs_fts, init_docs_search_index
    from .carousel_engine import carousel_engine
    from . import post_identity
    from . import mcp_client
    from .browser_launcher import (
        detect_installed_browsers,
        create_desktop_shortcuts,
        launch_browser_with_extension,
        copy_extension_path_to_clipboard,
        get_extension_dir
    )
    try:
        from studio.core.telemetry_shard import telemetry_engine, telemetry_buffer
    except ImportError:
        try:
            from core.telemetry_shard import telemetry_engine, telemetry_buffer
        except ImportError:
            telemetry_engine = None
            telemetry_buffer = None
except ImportError:
    from database import get_db, init_db, seed_initial_data, create_draft, get_draft, list_drafts, schedule_draft, checkpoint_db
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
        calculate_dwell_metrics
    )
    from repurposer import generate_10x_hooks, audit_linkedin_algorithm_safety, repurpose_content, get_ai_status, command_ai_engine
    from leads import list_leads, add_lead, batch_add_leads, update_lead_status, delete_lead, generate_dm_script, export_leads_csv
    from linkedin_client import linkedin_client
    import egress as egress_policy
    from scheduler import (start_scheduler, shutdown_scheduler, native_scheduler,
                           parse_datetime_flexible, normalize_datetime_to_utc_iso,
                           is_queue_paused, set_queue_paused)
    from agno_agent import agno_orchestrator
    from agno_agentos import orchestrator
    from image_studio import image_studio_manager
    from event_bus import event_bus
    from ingress import IngressMessageParser, TelegramIngressDaemon, ingress_daemon
    from crm import ICPScoringEngine, ReverseCRMManager, reverse_crm
    from rate_limiter import rate_limiter, write_actor
    from intelligence_sync import intelligence_sync_engine
    from gstack_governance import gstack_engine
    from internal_sheet import internal_sheet_manager
    import devtools
    import security
    import desktop as desktop_integration
    from migrations import describe as describe_schema
    import support as support_tools
    import updates as update_checker
    from paths import (get_assets_dir, get_uploads_dir, get_generated_dir, get_data_dir,
                       get_frontend_dir, get_docs_dir, get_modules_docs_dir, get_backups_dir,
                        describe as describe_paths)
    from docs_engine import search_docs_fts, init_docs_search_index
    from carousel_engine import carousel_engine
    import post_identity
    import mcp_client
    from browser_launcher import (
        detect_installed_browsers,
        create_desktop_shortcuts,
        launch_browser_with_extension,
        copy_extension_path_to_clipboard,
        get_extension_dir
    )
    try:
        from studio.core.telemetry_shard import telemetry_engine, telemetry_buffer
    except ImportError:
        try:
            from core.telemetry_shard import telemetry_engine, telemetry_buffer
        except ImportError:
            telemetry_engine = None
            telemetry_buffer = None

OPENAPI_TAGS = [
    {"name": "Analytics", "description": "Creator metrics, impressions, period deltas, demographics, and CSV exports."},
    {"name": "Post Studio", "description": "Draft authoring, scheduling, real-time simulator validation, and post lifecycle."},
    {"name": "Media Studio & Dropzone", "description": "Drag-and-drop file uploads for Images, PDF Carousels, and MP4/WebM Videos."},
    {"name": "AI Image Studio", "description": "Multi-stage AI image generation with Agno prompt synthesis and 1%..100% progress tracking."},
    {"name": "AI Content Copilot", "description": "Agno AgentOS post drafting, hook generation, and dwell optimization."},
    {"name": "AI Command Engine", "description": "Dual-mode AI: Gemini 2.5 Flash cloud API & Antigravity local deterministic engine."},
    {"name": "Formatting & Audit", "description": "Unicode mathematical formatting, em-dash scrubber, and 2026 algorithm safety scoring."},
    {"name": "Leads & CRM", "description": "Prospect engagement pipeline, status transitions, and personalized DM scripts."},
    {"name": "Smart Queue", "description": "Cadence management and peak engagement time slots."},
    {"name": "LinkedIn Bridge", "description": "Passive session token synchronization and live analytics ingestion."},
    {"name": "Settings & Creator Profile", "description": "Creator branding, personal watermark configuration, and session bridge."},
    {"name": "Documentation", "description": "Interactive enterprise documentation suite and in-app playbook viewer."},
    {"name": "Real-Time Event Stream", "description": "Server-Sent Events (SSE) bus for under 5ms instant live inbox updates."},
    {"name": "Ubiquitous Ingress", "description": "Outbound long-polling Telegram ingress, directive parser, and mobile fold analyzer."},
    {"name": "LinkedIn Native Scheduler", "description": "Voyager cloud pre-staging and self-healing morning grace window recovery."},
    {"name": "Enterprise Reverse CRM", "description": "Deterministic ICP scoring engine and anti-slop 1-to-1 contextual DM generation."},
    {"name": "Anti-Bot & Rate Limiting", "description": "Gaussian jitter request governor, human pacing, and single-writer WAL actor."},
    {"name": "Intelligence Sync & Radar", "description": "Asymmetric GitHub CDN intelligence sync, ETag caching, and viral hook templates."},
    {"name": "G-Stack Multi-Agent Governance", "description": "Garry Tan 6-role virtual team governance, role backlogs, and multi-gate anti-slop audits."},
    {"name": "Internal Sheet & Concept Identifier", "description": "Visual screen element inspection, bug annotations, and zero-egress internal sheet tracking."},
    {"name": "Developer Tools", "description": "Maintainer only. Screen registry, state and migration inspectors, and annotation portability. Absent unless INOX_DEV_MODE is set."}
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_initial_data()
    start_scheduler()
    if os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("PRUDENT_TELEGRAM_BOT_TOKEN"):
        ingress_daemon.start_worker()
    yield
    shutdown_scheduler()
    ingress_daemon.stop_worker()


# The interactive documentation is a maintainer tool, so it follows the same
# gate everything else maintainer facing does.
#
# It was not gated, and none of /openapi.json, /docs or /redoc begins with
# "/api", so the auth middleware never saw them either. A consumer build
# published a complete, unauthenticated map of its own API, including every
# devtools route it otherwise answers 404 for. That directly contradicted the
# invariant those 404s exist to maintain. Swagger UI also pulls its bundle
# from a CDN, which a product claiming zero egress should not do by default.
#
# Read from the environment rather than devtools.is_dev_mode(), because this
# runs before the database exists.
_DEV_DOCS = devtools.env_allows_dev_mode()

app = FastAPI(
    title="LinkedIn Studio Enterprise",
    description="A 100% self-hosted, air-gapped, privacy-first alternative to $199/month SaaS creator tools running on localhost.",
    version=__version__,
    openapi_url="/openapi.json" if _DEV_DOCS else None,
    docs_url="/docs" if _DEV_DOCS else None,
    redoc_url="/redoc" if _DEV_DOCS else None,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan
)

# CORS for the studio interface and the extension, and nothing else.
#
# This used to be allow_origins=["*"] with credentials enabled, which meant any
# page the creator had open in another tab could call this server and read the
# response. Binding to 127.0.0.1 never prevented that: the browser is already
# on this machine. See studio/backend/security.py for the full reasoning,
# including why LinkedIn itself is not on this list.
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(security.allowed_origins()),
    allow_origin_regex=r"^chrome-extension://[a-z]{32}$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", security.TOKEN_HEADER],
)


@app.middleware("http")
async def enforce_local_access(request: Request, call_next):
    """
    Host, origin and token, checked before anything reaches a route.

    Applied as middleware rather than as a dependency on each route so that a
    new endpoint is protected the moment it is written. A route that has to be
    remembered about is a route that will eventually be forgotten about.
    """
    # scope["path"], not request.url.path.
    #
    # Starlette reconstructs request.url from the path PLUS the raw Host header
    # as the netloc, then re-splits it. A Host of "127.0.0.1:8000/x" therefore
    # yields request.url.path == "/x/api/v1/..." while the router still matches
    # scope["path"] == "/api/v1/...". Gating on the reconstructed value let a
    # caller move their own request out from behind this check while still
    # reaching the endpoint. Reading the same value the router reads closes
    # that by construction rather than by relying on Starlette's Host parsing.
    path = request.scope.get("path", "")
    host_header = request.headers.get("host")
    port = security.extract_port(host_header)

    # The Host check applies to everything, not only /api.
    #
    # It used to guard the API alone, which left the SPA and the /assets mount
    # answering a rebound origin. That is enough for an attacker who points
    # their domain at 127.0.0.1 to read the creator's uploaded and generated
    # media from a page they control, and to fingerprint the install.
    if not security.is_loopback_host(host_header):
        return JSONResponse(
            status_code=403,
            content={"detail": "This server answers on loopback only."},
        )

    if path.startswith("/api") and not security.request_is_exempt(path):
        # Preflight carries no credentials by design. CORSMiddleware has
        # already decided whether the origin may ask.
        if request.method != "OPTIONS":
            if not security.is_allowed_origin(request.headers.get("origin"), port):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "This origin is not permitted to use the local studio."},
                )

            supplied = (
                request.headers.get(security.TOKEN_HEADER)
                or request.cookies.get(security.TOKEN_COOKIE)
            )
            if not security.constant_time_match(supplied, security.get_or_create_token()):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing or invalid studio token."},
                )

    response = await call_next(request)

    # Hand the interface its token as it loads. SameSite=Strict is the part
    # that matters: a browser will not attach this cookie to a request started
    # by any other site, so a hostile page cannot borrow the creator's session
    # even from the same machine.
    if not path.startswith("/api") and security.is_loopback_host(host_header):
        response.set_cookie(
            key=security.TOKEN_COOKIE,
            value=security.get_or_create_token(),
            # HttpOnly, so no script on this origin can read the token.
            #
            # This was briefly false, on the assumption that the extension
            # needed script access. It does not: chrome.cookies.get is a
            # privileged extension API that reads HttpOnly cookies given host
            # permission, which the extension holds for 127.0.0.1:8000. The
            # only thing the false setting bought was letting any script on
            # this origin exfiltrate the token, which turns an XSS here into
            # full API access.
            httponly=True,
            samesite="strict",
            path="/",
            max_age=60 * 60 * 24 * 365,
        )

    return response


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
    text: str = Field(..., max_length=20000)


class ImageGenerateRequest(BaseModel):
    concept: str = Field(..., max_length=2000)
    aspect_ratio: Optional[str] = "1:1"
    visual_style: Optional[str] = "photorealistic"
    color_palette: Optional[str] = "navy_cyan"
    lighting: Optional[str] = "studio"
    render_quote_overlay: Optional[bool] = True
    custom_quote_text: Optional[str] = None
    custom_quote_author: Optional[str] = None
    eliminate_provider_watermark: Optional[bool] = True
    apply_personal_watermark: Optional[bool] = False
    personal_watermark_text: Optional[str] = None
    personal_watermark_position: Optional[str] = "bottom_right"
    personal_watermark_style: Optional[str] = "glass_pill"

    @field_validator("concept")
    @classmethod
    def validate_concept_non_empty(cls, v: str) -> str:
        s = v.strip() if isinstance(v, str) else ""
        if not s:
            raise ValueError("concept cannot be empty or only whitespace")
        return s[:2000]


class CreatorProfilePayload(BaseModel):
    name: Optional[str] = ""
    headline: Optional[str] = ""
    company: Optional[str] = ""
    brand_watermark_text: Optional[str] = ""
    brand_watermark_position: Optional[str] = "bottom_right"
    brand_watermark_style: Optional[str] = "glass_pill"
    brand_watermark_enabled: Optional[bool] = True
    eliminate_provider_watermark_default: Optional[bool] = True
    default_aspect_ratio: Optional[str] = "1:1"
    default_visual_style: Optional[str] = "photorealistic"


class CopilotRequest(BaseModel):
    raw_content: str
    target_audience: Optional[str] = "Engineering & Product Leaders"
    post_format: Optional[str] = "framework_breakdown"
    attached_media_type: Optional[str] = None


class CarouselRequest(BaseModel):
    slides: List[Dict[str, str]]
    theme: Optional[str] = "dark_slate"
    author_name: Optional[str] = None
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


class AIConfigureRequest(BaseModel):
    provider: str
    api_key: Optional[str] = ""
    model: Optional[str] = None
    base_url: Optional[str] = None


class AICommandPayload(BaseModel):
    command: str
    context: Optional[str] = None
    draft_context: Optional[str] = None

    def resolved_context(self) -> Optional[str]:
        return self.context if self.context is not None else self.draft_context


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
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT MAX(date) FROM analytics_daily")
        max_d_row = cursor.fetchone()
        if not max_d_row or not max_d_row[0]:
            # Nothing captured yet. Return the full shape with nulls rather than an
            # empty object: callers should render "not known yet", and an empty dict
            # made every consumer reach for a fallback constant instead.
            cursor.execute("SELECT COUNT(*) FROM posts WHERE status = 'scheduled'")
            scheduled_when_empty = cursor.fetchone()[0]
            conn.close()
            return {
                "range": f"{days}d",
                "impressions": None,
                "impressions_delta_pct": None,
                "total_engagements": None,
                "engagements_delta_pct": None,
                "avg_engagement_rate": None,
                "engagement_rate_delta": None,
                "total_followers": None,
                "follower_growth": None,
                "profile_views": None,
                "profile_views_delta_pct": None,
                # Counted, not assumed. An empty analytics table says nothing about
                # the queue, and the queue screen was showing posts this reported as
                # zero.
                "scheduled_posts_count": scheduled_when_empty,
            }

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
        # An unknown metric is null. It used to fall back to 2412 followers and 104
        # profile views, which meant a creator who had captured nothing, or who
        # genuinely had zero profile views, was shown a number that looked measured.
        # Null travels to the interface and renders as a dash.
        cur_followers = latest_stat["followers"] if (latest_stat and latest_stat["followers"] is not None) else None
        cur_pviews = latest_stat["profile_views"] if (latest_stat and latest_stat["profile_views"] is not None) else None

        cursor.execute("SELECT followers, profile_views FROM analytics_daily WHERE date = ?", (start_cur.strftime("%Y-%m-%d"),))
        start_stat = cursor.fetchone()
        start_followers = start_stat["followers"] if (start_stat and start_stat["followers"] is not None) else cur_followers
        start_pviews = start_stat["profile_views"] if (start_stat and start_stat["profile_views"] is not None) else cur_pviews

        # A delta between two points needs both points. One missing means no answer,
        # not a zero and not a hundred percent.
        follower_growth = (cur_followers - start_followers) if (cur_followers is not None and start_followers is not None) else None
        pviews_delta = calc_delta(cur_pviews, start_pviews) if (cur_pviews is not None and start_pviews is not None) else None

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
    finally:
        conn.close()


@app.get("/api/analytics/overview")
def get_analytics_overview(range: str = "30d"):
    days = get_range_days(range)
    conn = get_db()
    try:
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
    finally:
        conn.close()


@app.get("/api/analytics/demographics")
def get_demographics(dimension: Optional[str] = None):
    conn = get_db()
    try:
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
    finally:
        conn.close()


@app.get("/api/analytics/export")
def export_analytics(format: str = "csv"):
    conn = get_db()
    try:
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
    finally:
        conn.close()


@app.get("/api/analytics/posts")
def get_posts_leaderboard():
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, content, media_urls, status, published_at, impressions, reactions, comments, shares, tags,
               activity_urn,
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

            # Attribution correlation summary for post leaderboard.
            #
            # Matched on the activity URN, which is what an engagement is actually
            # recorded under. This used to compare posts.id against li.post_urn,
            # two different namespaces, so the badge read zero on every post no
            # matter how many commenters had been captured. li.post_id is an
            # INTEGER key into drafts(id) and could not match a posts.id string
            # either, so all three disjuncts were dead.
            post_id_str = str(d["id"])
            post_urn = d.get("activity_urn") or ""
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT l.id) as total_leads,
                    COUNT(DISTINCT CASE WHEN l.icp_score >= 75.0 THEN l.id END) as vip_leads,
                    ROUND(AVG(l.icp_score), 1) as avg_icp
                FROM leads l
                LEFT JOIN lead_interactions li ON l.id = li.lead_id
                WHERE (li.post_urn != '' AND li.post_urn IN (?, ?)) OR l.post_id = ?
            """, (post_id_str, post_urn, post_id_str))
            attr_row = cursor.fetchone()
            d["attribution"] = {
                "total_leads": int(attr_row["total_leads"] or 0) if attr_row else 0,
                "vip_leads": int(attr_row["vip_leads"] or 0) if attr_row else 0,
                "avg_icp": float(attr_row["avg_icp"] or 0.0) if attr_row and attr_row["avg_icp"] else 0.0,
            }
            rows.append(d)
        conn.close()
        return {"status": "success", "posts": rows}
    finally:
        conn.close()


@app.get("/api/v1/analytics/posts/{post_id}/leads", tags=["Enterprise Reverse CRM", "Analytics"])
def get_post_leads_attribution(post_id: str, account_id: str = "default"):
    """
    Returns full post-to-lead attribution analytics and detailed engager dossier list.
    Supports post ID or LinkedIn activity URN.
    """
    return reverse_crm.get_post_attribution(post_id, account_id=account_id)


# -------------------------------------------------------------
# Module 2: Post Studio & Simulator Endpoints
# -------------------------------------------------------------
@app.get("/api/posts")
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


@app.post("/api/posts")
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


@app.put("/api/posts/{post_id}")
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


@app.post("/api/posts/{post_id}/reschedule")
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


@app.post("/api/posts/{post_id}/publish-now", tags=["LinkedIn Native Scheduler"])
async def publish_post_now(post_id: str):
    """
    Immediately dispatches a scheduled post or draft as published.
    Normalizes status to published, records UTC published_at,
    and broadcasts the post_published event across the real-time event bus.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        existing = cursor.fetchone()
        if not existing:
            conn.close()
            raise HTTPException(status_code=404, detail="Post not found")

        if existing["status"] == "published":
            conn.close()
            raise HTTPException(status_code=400, detail="Post is already published")

        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
        UPDATE posts
        SET status = 'published', published_at = ?
        WHERE id = ?
        """, (now_iso, post_id))
        conn.commit()
        conn.close()

        await event_bus.publish("post_published", {
            "post_id": post_id,
            "content": existing["content"][:80],
            "action": "published_now",
            "published_at": now_iso
        })

        return {
            "status": "success",
            "message": "Post published immediately.",
            "post_id": post_id,
            "published_at": now_iso
        }
    finally:
        conn.close()


@app.delete("/api/posts/{post_id}")
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


# -------------------------------------------------------------
# Module 3: Media Studio & Unified Drag-and-Drop Dropzone
# -------------------------------------------------------------
@app.post("/api/media/upload", tags=["Media Studio & Dropzone"])
async def upload_media_file(file: UploadFile = File(...)):
    """
    Unified drag-and-drop media upload handler supporting:
    - Single & Multi-Images (.png, .jpg, .jpeg, .webp)
    - Multi-Slide Document Carousels (.pdf)
    - High-Definition Video (.mp4, .webm)
    """
    filename = file.filename or "uploaded_media"
    ext = os.path.splitext(filename)[1].lower()

    ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
    ALLOWED_DOC_EXTS = {".pdf"}
    ALLOWED_VIDEO_EXTS = {".mp4", ".webm"}

    if ext in ALLOWED_IMAGE_EXTS:
        media_type = "image"
    elif ext in ALLOWED_DOC_EXTS:
        media_type = "carousel"
    elif ext in ALLOWED_VIDEO_EXTS:
        media_type = "video"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: Images (.png, .jpg, .webp), Carousels (.pdf), Videos (.mp4, .webm)"
        )

    uploads_dir = get_uploads_dir()

    clean_name = re.sub(r'[^a-zA-Z0-9_\.-]', '_', filename)
    safe_name = f"{uuid.uuid4().hex[:8]}_{clean_name}"
    file_path = os.path.join(uploads_dir, safe_name)

    content = await file.read()
    size_bytes = len(content)

    if size_bytes == 0:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty (0 bytes). Please upload a valid media file."
        )

    # Validate file signatures against declared extension
    if ext == ".pdf":
        if b"%PDF-" not in content[:1024]:
            raise HTTPException(
                status_code=400,
                detail="Invalid PDF format. The file content does not match the .pdf extension."
            )
    elif ext == ".png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(
                status_code=400,
                detail="Invalid PNG format. The file content does not match the .png extension."
            )
    elif ext in {".jpg", ".jpeg"}:
        if not content.startswith(b"\xff\xd8"):
            raise HTTPException(
                status_code=400,
                detail="Invalid JPEG format. The file content does not match the image extension."
            )
    elif ext == ".webp":
        if not (content.startswith(b"RIFF") and b"WEBP" in content[:16]):
            raise HTTPException(
                status_code=400,
                detail="Invalid WEBP format. The file content does not match the .webp extension."
            )
    elif ext == ".mp4":
        if b"ftyp" not in content[:64] and not content.startswith(b"\x00\x00\x00"):
            raise HTTPException(
                status_code=400,
                detail="Invalid MP4 format. The file content does not match the .mp4 extension."
            )

    with open(file_path, "wb") as f:
        f.write(content)

    relative_url = f"/assets/uploads/{safe_name}"
    page_count = None
    dimensions = None

    if media_type == "carousel":
        try:
            import fitz
            doc = fitz.open(file_path)
            page_count = len(doc)
            doc.close()
        except Exception:
            page_count = 1
    elif media_type == "image":
        try:
            from PIL import Image
            with Image.open(file_path) as im:
                dimensions = {"width": im.width, "height": im.height}
        except Exception:
            pass

    asset_id = f"asset_{uuid.uuid4().hex[:10]}"
    conn = get_db()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO media_assets 
            (id, filename, storage_path, media_type, mime_type, size_bytes, dimensions, page_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                asset_id,
                filename,
                relative_url,
                media_type,
                file.content_type or f"application/{ext.lstrip('.')}",
                size_bytes,
                json.dumps(dimensions) if dimensions else None,
                page_count
            ))
    finally:
        conn.close()

    return {
        "status": "success",
        "asset_id": asset_id,
        "media_type": media_type,
        "url": relative_url,
        "filename": filename,
        "size_bytes": size_bytes,
        "page_count": page_count,
        "dimensions": dimensions
    }


@app.get("/api/media", tags=["Media Studio & Dropzone"])
def list_media_assets():
    """Lists all uploaded and AI-generated media assets in the local library."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM media_assets ORDER BY created_at DESC")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return {"status": "success", "count": len(rows), "assets": rows}
    finally:
        conn.close()


@app.delete("/api/media/{asset_id}", tags=["Media Studio & Dropzone"])
def delete_media_asset(asset_id: str):
    """Deletes an uploaded media asset and cleans up local storage."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT storage_path FROM media_assets WHERE id = ?", (asset_id,))
        row = cursor.fetchone()
        if row:
            rel_path = row["storage_path"]
            if rel_path.startswith("/assets/"):
                sub_path = rel_path.replace("/assets/", "")
                full_path = os.path.join(get_assets_dir(), sub_path)
                if os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                    except Exception:
                        pass
            cursor.execute("DELETE FROM media_assets WHERE id = ?", (asset_id,))
            conn.commit()
        conn.close()
        return {"status": "success", "message": f"Asset {asset_id} deleted"}
    finally:
        conn.close()


# -------------------------------------------------------------
# Module 4: Structured AI Image Generation Studio
# -------------------------------------------------------------
@app.post("/api/image/generate", tags=["AI Image Studio"])
def generate_ai_image(req: ImageGenerateRequest):
    """
    Launches asynchronous AI image generation task with live 1%..100% progress tracking.
    Poll /api/image/progress/{task_id} for live progress updates.
    """
    task_id = image_studio_manager.start_task(req.model_dump())
    return {
        "status": "started",
        "task_id": task_id,
        "message": "AI image generation launched. Poll /api/image/progress/{task_id} for progress percentage."
    }


@app.get("/api/image/progress/{task_id}", tags=["AI Image Studio"])
def get_image_progress(task_id: str):
    """Returns live percentage (1%..100%), stage message, and result URL."""
    return image_studio_manager.get_progress(task_id)


@app.post("/api/image/synthesize-prompt", tags=["AI Image Studio"])
def synthesize_image_prompt(req: ImageGenerateRequest):
    """Agno prompt engineering preview before rendering."""
    result = orchestrator.synthesize_image_prompt(req.model_dump())
    dump = result.model_dump()
    return {"status": "success", "synthesized": dump, **dump}


# -------------------------------------------------------------
# Module 5: Agno AgentOS Content Copilot & Pattern Harvester
# -------------------------------------------------------------
@app.post("/api/copilot/optimize", tags=["AI Content Copilot"])
def copilot_optimize(req: CopilotRequest):
    """Agno Content Copilot post drafting, line formatting, and viral hook formulation."""
    result = orchestrator.optimize_content(req.model_dump())
    return {"status": "success", "copilot": result.model_dump()}


@app.post("/api/swipe/analyze", tags=["AI Content Copilot"])
def analyze_swipe_pattern(payload: Dict[str, Any]):
    """Reverse-engineers viral posts into reusable formulas and blueprints."""
    result = orchestrator.analyze_swipe(payload)
    return {"status": "success", "pattern": result.model_dump()}


# Backwards compatibility stub for legacy carousel call
@app.post("/api/carousel/generate", tags=["Media Studio & Dropzone"])
def legacy_carousel_stub(req: CarouselRequest):
    """Legacy endpoint notice: Synthetic Pillow carousels deprecated in favor of native PDF dropzone."""
    padding = b" " * 10500
    content = b"%PDF-1.4\n% Decommissioned: Use native PDF drag-and-drop in Media Dropzone.\n" + padding + b"\n%%EOF"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=use_media_dropzone.pdf"}
    )


class CarouselDeckRequest(BaseModel):
    slides: List[Dict[str, Any]] = Field(..., min_length=1, max_length=50)
    theme: Optional[str] = "dark_obsidian"
    aspect_ratio: Optional[str] = "4:5"
    author_name: Optional[str] = None
    author_title: Optional[str] = "Enterprise Systems Practitioner"

    @field_validator("slides")
    @classmethod
    def validate_slides_list(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not v or len(v) < 1:
            raise ValueError("Carousel requires at least 1 slide")
        if len(v) > 50:
            raise ValueError("Carousel cannot exceed 50 slides")
        return v


@app.post("/api/v1/carousel/deck/generate", tags=["Media Studio & Dropzone"])
def generate_vector_carousel_deck(req: CarouselDeckRequest):
    """
    Day 13: Compiles structured slide cards into 4:5 vertical (1080x1350)
    or 1:1 square vector SVG slides with Swiss typography.
    """
    res = carousel_engine.compile_carousel_deck(
        slides=req.slides,
        theme=req.theme or "dark_obsidian",
        aspect_ratio=req.aspect_ratio or "4:5",
        author_name=req.author_name or "",
        author_title=req.author_title or "Enterprise Systems Practitioner"
    )
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to compile carousel deck"))
    return res


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
# Bring-Your-Own-AI (BYO-AI) & Antigravity Intelligence Bridge
# -------------------------------------------------------------
@app.get("/api/ai/status", tags=["AI Command Engine"])
def ai_status():
    return get_ai_status()


@app.get("/api/ai/config", tags=["AI Command Engine"])
def get_ai_config_endpoint():
    """Returns active Bring-Your-Own-AI provider, verified model, and available providers."""
    try:
        from .agno_agentos.model_gateway import get_current_ai_config, SUPPORTED_PROVIDERS
    except ImportError:
        from agno_agentos.model_gateway import get_current_ai_config, SUPPORTED_PROVIDERS
    cfg = get_current_ai_config()
    return {
        "status": "success",
        "config": cfg.to_dict(),
        "supported_providers": SUPPORTED_PROVIDERS
    }


@app.post("/api/ai/configure", tags=["AI Command Engine"])
def configure_ai_endpoint(req: AIConfigureRequest):
    """
    Validates connection to the selected AI provider (Gemini, OpenAI, Claude, Groq, Ollama)
    via live ping. If verified, updates local SQLite configuration.
    If invalid, rejects configuration with 400 Bad Request and preserves existing settings.
    """
    try:
        from .agno_agentos.model_gateway import verify_ai_connection, save_ai_config
    except ImportError:
        from agno_agentos.model_gateway import verify_ai_connection, save_ai_config

    success, message, latency_ms = verify_ai_connection(
        provider=req.provider,
        api_key=req.api_key or "",
        model=req.model,
        base_url=req.base_url
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "AI Provider Verification Failed",
                "message": message,
                "latency_ms": latency_ms
            }
        )

    saved_cfg = save_ai_config(
        provider=req.provider,
        api_key=req.api_key or "",
        model=req.model,
        base_url=req.base_url
    )

    return {
        "status": "success",
        "message": message,
        "latency_ms": latency_ms,
        "config": saved_cfg.to_dict()
    }


@app.post("/api/ai/settings", tags=["AI Command Engine"])
def save_ai_settings(payload: AISettingsPayload):
    try:
        from .agno_agentos.model_gateway import save_ai_config
    except ImportError:
        from agno_agentos.model_gateway import save_ai_config
    
    save_ai_config(provider="gemini", api_key=payload.gemini_api_key.strip(), model="gemini-2.5-flash")

    return {
        "status": "success",
        "message": "Gemini API key saved to local SQLite settings",
        "ai_status": get_ai_status()
    }


@app.post("/api/ai/command", tags=["AI Command Engine"])
@app.post("/api/repurposer/command", tags=["AI Command Engine"])
def execute_ai_command(payload: AICommandPayload):
    return command_ai_engine(payload.command, payload.resolved_context())


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


@app.post("/api/format/serif-bold")
def format_serif_bold(req: FormatRequest):
    return {"formatted": to_serif_bold(req.text)}


@app.post("/api/format/serif-italic")
def format_serif_italic(req: FormatRequest):
    return {"formatted": to_serif_italic(req.text)}


@app.post("/api/format/blackboard")
def format_blackboard(req: FormatRequest):
    return {"formatted": to_blackboard_bold(req.text)}


@app.post("/api/format/underline")
def format_underline(req: FormatRequest):
    return {"formatted": to_underline(req.text)}


@app.post("/api/format/circled-numbers")
def format_circled_numbers(req: FormatRequest):
    return {"formatted": to_circled_numbers(req.text)}


@app.post("/api/format/dwell")
def format_dwell(req: FormatRequest):
    return calculate_dwell_metrics(req.text)


# -------------------------------------------------------------
# Taplio Pro ($199/mo) Feature 5: Lead Database & Relationship CRM
# -------------------------------------------------------------
@app.get("/api/leads")
def get_leads(status: Optional[str] = None, search: Optional[str] = None):
    return {"status": "success", "leads": list_leads(status, search)}


@app.get("/api/v1/crm/leads/export-csv", tags=["Enterprise Reverse CRM"])
@app.get("/api/leads/export/csv", tags=["Inbound CRM"])
def export_leads_csv_route(status: Optional[str] = None, search: Optional[str] = None):
    csv_data = export_leads_csv(status, search)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=linkedin_studio_crm_leads.csv"}
    )


@app.post("/api/leads")
def create_lead(lead: LeadCreate):
    data = lead.model_dump() if hasattr(lead, "model_dump") else lead.dict()
    return add_lead(data)


@app.post("/api/leads/batch")
def create_leads_batch(payload: Dict[str, Any]):
    leads_list = payload.get("leads", [])
    result = batch_add_leads(leads_list)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.put("/api/leads/{lead_id}/status")
def update_lead(lead_id: str, payload: LeadStatusUpdate):
    result = update_lead_status(lead_id, payload.status, payload.notes)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.delete("/api/leads/{lead_id}")
def remove_lead(lead_id: str):
    result = delete_lead(lead_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")
    return result


@app.get("/api/leads/{lead_id}/dm-script")
def get_lead_dm(lead_id: str, style: Optional[str] = "value_add", topic: Optional[str] = None):
    return generate_dm_script(lead_id, style=style, post_topic=topic)


@app.post("/api/leads/{lead_id}/enrich", tags=["Leads & CRM"])
def enrich_lead_endpoint(lead_id: str):
    try:
        return agno_orchestrator.enrich_lead(lead_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agno enrichment failed: {str(e)}")


@app.get("/api/leads/{lead_id}/enrichment", tags=["Leads & CRM"])
def get_lead_enrichment_endpoint(lead_id: str):
    enrichment = agno_orchestrator.get_enrichment(lead_id)
    if not enrichment:
        raise HTTPException(status_code=404, detail=f"No enrichment dossier found for lead '{lead_id}'. Run POST /api/leads/{lead_id}/enrich first.")
    return {
        "status": "success",
        "enrichment": enrichment
    }


# -------------------------------------------------------------
# Module: Browser Bridge & Extension Launcher
# -------------------------------------------------------------
@app.get("/api/v1/browser/status", tags=["Browser Bridge"])
def get_browser_status_endpoint():
    browsers = detect_installed_browsers()
    return {
        "status": "success",
        "browsers": browsers,
        "extension_path": get_extension_dir(),
        "total_detected": len(browsers)
    }


@app.post("/api/v1/browser/create-shortcuts", tags=["Browser Bridge"])
def create_browser_shortcuts_endpoint():
    shortcuts = create_desktop_shortcuts()
    return {
        "status": "success",
        "shortcuts": shortcuts,
        "total_created": len([s for s in shortcuts if s.get("status") == "created"])
    }


@app.post("/api/v1/browser/launch", tags=["Browser Bridge"])
def launch_browser_endpoint(payload: Optional[Dict[str, Any]] = None):
    browser_id = "auto"
    url = "https://www.linkedin.com/feed/"
    if payload and isinstance(payload, dict):
        browser_id = payload.get("browser_id", "auto")
        url = payload.get("url", "https://www.linkedin.com/feed/")
    return launch_browser_with_extension(browser_id=browser_id, target_url=url)


@app.post("/api/v1/browser/copy-path", tags=["Browser Bridge"])
def copy_browser_path_endpoint():
    return copy_extension_path_to_clipboard()



# -------------------------------------------------------------
# Module 3: Smart Queue & Slots
# -------------------------------------------------------------
@app.get("/api/queue/smart-slots")
def get_smart_slots():
    conn = get_db()
    try:
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
    finally:
        conn.close()


class CadenceValidationPayload(BaseModel):
    scheduled_for: str
    post_id: Optional[str] = None


@app.get("/api/queue/next-slot", tags=["Smart Queue"])
def get_next_smart_slot(from_time: Optional[str] = None):
    """Calculates the chronologically next optimal smart slot with 12h cooldown clearance."""
    cursor_dt = parse_datetime_flexible(from_time) if from_time else None
    slot = native_scheduler.calculate_next_smart_slot(from_time=cursor_dt)
    return {"status": "success", "slot": slot}


@app.get("/api/queue/cadence-health", tags=["Smart Queue"])
def get_cadence_health():
    """Returns global cadence health score (0-100%) and queue collision analysis."""
    overview = native_scheduler.get_cadence_overview()
    return overview


@app.post("/api/queue/validate-cadence", tags=["Smart Queue"])
def validate_queue_cadence(payload: CadenceValidationPayload):
    """Validates proposed scheduling timestamp against the 12-hour cooldown rule."""
    result = native_scheduler.validate_schedule_cadence(payload.scheduled_for, post_id=payload.post_id)
    return {"status": "success", "validation": result}


@app.post("/api/v1/scheduler/dispatch/now", tags=["LinkedIn Native Scheduler"])
def trigger_scheduler_dispatch():
    """Forces an immediate on-demand evaluation of the scheduled queue and grace window recovery."""
    actions = native_scheduler.check_scheduled_queue()
    return {"status": "success", "actions": actions, "executed_at": datetime.now(timezone.utc).isoformat()}


@app.get("/api/queue/status", tags=["Smart Queue"])
def get_queue_status():
    """Returns whether the automated publishing queue is active or paused."""
    return {
        "status": "success",
        "queue_paused": native_scheduler.is_queue_paused()
    }


class QueuePausePayload(BaseModel):
    paused: Optional[bool] = None


@app.post("/api/queue/toggle-pause", tags=["Smart Queue"])
async def toggle_queue_pause(payload: Optional[QueuePausePayload] = None):
    """Toggles or sets the automated publishing queue pause state."""
    current = native_scheduler.is_queue_paused()
    new_state = payload.paused if (payload and payload.paused is not None) else not current

    # The write is checked, and the state is read back.
    #
    # This discarded the result, published queue_status_changed and returned
    # success regardless. A failed write therefore told the creator their
    # queue was paused while the dispatcher went on publishing, which is the
    # one outcome this control exists to prevent.
    wrote = native_scheduler.set_queue_paused(new_state)
    actual_state = native_scheduler.is_queue_paused()

    if not wrote or actual_state != new_state:
        return {
            "status": "error",
            "queue_paused": actual_state,
            "message": (
                "Could not change the queue state. It is still "
                + ("paused" if actual_state else "running")
                + ". Check studio/logs for the database error."
            ),
        }

    await event_bus.publish("queue_status_changed", {"queue_paused": actual_state})
    msg = "Publishing queue paused." if actual_state else "Publishing queue resumed."
    return {
        "status": "success",
        "queue_paused": actual_state,
        "message": msg
    }



# -------------------------------------------------------------
# Viral Inspirations Hub (356 Vaulted High-Performing Blueprints)
# -------------------------------------------------------------
@app.get("/api/inspirations")
def search_inspirations(query: Optional[str] = None, topic: Optional[str] = None, limit: Optional[int] = 100):
    conn = get_db()
    try:
        cursor = conn.cursor()

        # Whether the retired table has rows, not whether it exists.
        #
        # This used to switch on table existence alone, which made the swipe file
        # work once and then go empty forever. init_db runs before ensure_schema on
        # every boot and recreates `inspirations` through CREATE TABLE IF NOT
        # EXISTS, but the ledger only runs migration 2 once, so nothing dropped it
        # again. From the second launch onward an empty legacy table was present,
        # this switch took the legacy path, and the creator saw nothing.
        #
        # Emptiness is the honest test: migration 2 moved every row into
        # viral_templates, so a table with no rows has nothing left to serve
        # whether or not some later boot recreated its shell.
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inspirations'")
        has_inspirations = cursor.fetchone() is not None
        if has_inspirations:
            cursor.execute("SELECT COUNT(*) FROM inspirations")
            has_inspirations = cursor.fetchone()[0] > 0

        if not has_inspirations:
            conn.close()
            templates = intelligence_sync_engine.get_templates(archetype=topic, query=query, limit=limit or 100)
            total_vaulted = intelligence_sync_engine.get_total_count()
            adapted_rows = [
                {
                    "id": f"tpl-{t.get('id', idx)}",
                    "author_name": "Blueprint",
                    "author_headline": t.get("archetype", "Engineering"),
                    "topic": t.get("archetype", "Engineering"),
                    "content": (t.get("hook_text") or "") + "\n\n" + (t.get("pacing_style") or ""),
                    # No reactions, no comments.
                    #
                    # These used to be int(velocity_score * 1000) and a literal
                    # 50, so every card on the swipe wall showed "9,800
                    # REACTIONS . 50 COMMENTS" for a template nobody had ever
                    # posted. Neither number is stored anywhere. Both were
                    # manufactured here at render time and then displayed as
                    # though they had been measured.
                    #
                    # velocity_score survives because it is a real stored
                    # field: a rating of how strongly the form performs, which
                    # is the whole point of a template library. A reaction
                    # count is a claim about an event, and there was no event.
                    "likes_count": None,
                    "comments_count": None,
                    # Passed through, never defaulted. viral_templates has
                    # three insert paths (the offline seeder, the bundle feed,
                    # and a local import), so filling a NULL in with 'shipped'
                    # would assert where a row came from on no evidence. Rows
                    # written before migration 9 stay unknown, which is what
                    # migration 4 does for the same reason.
                    "origin": t.get("origin"),
                    "key_hook": t.get("hook_text", ""),
                    "archetype": t.get("archetype", "Engineering"),
                    "velocity_score": t.get("velocity_score", 8.0),
                    "engagement_multiplier": t.get("engagement_multiplier", "2.0x"),
                    "pacing_style": t.get("pacing_style", "")
                }
                for idx, t in enumerate(templates)
            ]
            return {
                "status": "success",
                "total_vaulted": total_vaulted,
                "count": len(adapted_rows),
                "inspirations": adapted_rows
            }

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
    finally:
        conn.close()



# -------------------------------------------------------------
# Module 4: Extension Ingestion & Session Bridge
# -------------------------------------------------------------
@app.post("/api/auth/cookies")
def receive_cookies(payload: CookiePayload):
    # Saving a token is local bookkeeping. It used to also trigger an
    # authenticated GET to LinkedIn, which meant every creator-analytics page
    # load and every 15 minute alarm produced a request the creator never made.
    # The sync is still available on its own endpoint for anyone who opts into
    # egress deliberately.
    linkedin_client.save_tokens(payload.li_at, payload.JSESSIONID)
    return {
        "status": "success",
        "message": "LinkedIn session tokens saved to local studio",
        "sync": {"status": "skipped", "message": "Token save does not contact LinkedIn"}
    }


@app.get("/api/auth/status")
def get_auth_status():
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'session_status'")
        row = cursor.fetchone()
        status = row["value"] if row else "disconnected"
        conn.close()
        # is_connected requires both halves, not just the stored string.
        #
        # It used to read the settings row alone, so a fresh install with no
        # credentials at all answered {"is_connected": true,
        # "client_session": false}: the endpoint certifying a session in the
        # same breath as reporting that none is held. The interface already
        # worked around it by reading client_session and ignoring this field,
        # which is the shape of a bug that survives because everyone routes
        # around it.
        #
        # Both are still reported separately, because they mean different
        # things and a caller may need to tell "the app believes it connected
        # once" apart from "usable tokens are on disk right now".
        held = linkedin_client.is_authenticated()
        return {
            "status": status,
            "is_connected": status in ["connected", "ready"] and held,
            "client_session": held
        }
    finally:
        conn.close()


@app.post("/api/analytics/ingest", tags=["Analytics"])
def ingest_live_analytics(payload: dict):
    # Asynchronously record in telemetry shard ring buffer without blocking
    if telemetry_buffer:
        try:
            event_type = payload.get("event_type") or ("feed_updates" if "posts" in payload or "feed_updates" in payload else "analytics_ingest")
            source = payload.get("source", "extension")
            telemetry_buffer.ingest(event_type=event_type, payload=payload, source=source)
        except Exception:
            pass

    result = linkedin_client.ingest_analytics_payload(payload)
    return result


@app.get("/api/v1/telemetry/status", tags=["Analytics"])
def get_telemetry_shard_status():
    """Returns telemetry shard diagnostics, event counts, and WAL metrics."""
    if not telemetry_engine:
        return {"status": "unavailable", "message": "Telemetry shard not initialized"}
    status = telemetry_engine.get_status()
    if telemetry_buffer:
        status["pending_in_buffer"] = telemetry_buffer.pending_count()
    return status


@app.post("/api/v1/telemetry/flush", tags=["Analytics"])
def flush_telemetry_shard():
    """Flushes in-memory staged telemetry events to SQLite."""
    if not telemetry_buffer:
        return {"flushed_events": 0, "flushed_dwells": 0}
    return telemetry_buffer.flush()


# -------------------------------------------------------------
# Module 5: Personal Settings & Creator Onboarding Profile
# -------------------------------------------------------------
@app.get("/api/settings/profile", tags=["Settings & Creator Profile"])
def get_creator_profile():
    """
    Returns the creator's saved profile, personal watermark preferences,
    studio defaults, and passive LinkedIn session telemetry.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'creator_profile'")
        row = cursor.fetchone()

        defaults = {
            # Empty, not absent: the shape stays stable for the form that binds to
            # it. `is_set` in the response is how a caller tells "not configured"
            # apart from "configured to an empty string".
            "name": "",
            "headline": "",
            "company": "",
            "brand_watermark_text": "",
            "brand_watermark_position": "bottom_right",
            "brand_watermark_style": "glass_pill",
            "brand_watermark_enabled": True,
            "eliminate_provider_watermark_default": True,
            "default_aspect_ratio": "1:1",
            "default_visual_style": "photorealistic"
        }

        profile = json.loads(row["value"]) if row and row["value"] else defaults
        for k, v in defaults.items():
            if k not in profile:
                profile[k] = v

        cursor.execute("SELECT value FROM settings WHERE key = 'session_status'")
        s_row = cursor.fetchone()
        cursor.execute("SELECT value FROM settings WHERE key = 'last_token_update'")
        t_row = cursor.fetchone()
        cursor.execute("SELECT value FROM settings WHERE key = 'li_at'")
        li_row = cursor.fetchone()
        conn.close()

        # Whether this install knows who its creator is. Callers need to tell
        # "never configured" apart from "configured to an empty string", and the
        # first is the state every fresh install starts in. Anything that renders a
        # name (watermarks, carousel footers, the feed simulator) should ask before
        # rendering rather than falling back to a value it invented.
        identity_is_set = bool((profile.get("name") or "").strip())

        return {
            "status": "success",
            "profile": profile,
            "is_set": identity_is_set,
            "linkedin_connected": linkedin_client.is_authenticated(),
            "session_status": s_row["value"] if s_row else "ready",
            "last_token_update": t_row["value"] if t_row else None,
            "has_li_cookie": bool(li_row and li_row["value"])
        }
    finally:
        conn.close()


@app.post("/api/settings/profile", tags=["Settings & Creator Profile"])
def update_creator_profile(payload: CreatorProfilePayload):
    """
    Persists creator onboarding profile, personal watermark styling,
    and studio defaults into local SQLite vault.
    """
    conn = get_db()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('creator_profile', ?)", (
                json.dumps(payload.model_dump()),
            ))
    finally:
        conn.close()

    return {
        "status": "success",
        "message": "Creator profile and watermark settings saved successfully",
        "profile": payload.model_dump()
    }


# -------------------------------------------------------------
# Enterprise Documentation Suite API
# -------------------------------------------------------------
DOCS_DIR = get_docs_dir()
MODULES_DIR = get_modules_docs_dir()

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


@app.get("/api/docs/search", tags=["Documentation"])
def search_documentation(q: str, limit: int = 10):
    """
    Sub-millisecond full-text search across all offline Markdown playbooks using SQLite FTS5 (Day 09).
    """
    safe_q = str(q or "")[:300].strip()
    try:
        safe_limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        safe_limit = 10
    results = search_docs_fts(safe_q, limit=safe_limit)
    return {
        "status": "success",
        "query": safe_q,
        "count": len(results),
        "results": results
    }


@app.get("/api/docs/{module_id}", tags=["Documentation"])
def get_doc_module(module_id: str):
    """
    Retrieves the full markdown content of a documentation module by ID or number.
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(module_id or ""))[:60]
    if not safe_id:
        raise HTTPException(status_code=400, detail="Invalid documentation module ID.")

    target = None
    for m in DOCS_MODULES:
        if m["id"].lower() == safe_id.lower() or m["number"] == safe_id:
            target = m
            break

    if not target:
        raise HTTPException(status_code=404, detail=f"Documentation module '{safe_id}' not found.")

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
# Grounding: the creator's own material, through MCP
#
# These routes are the surface for a feature that already worked and that
# nobody could switch on. The client was built and wired into hook generation
# and there was no way to add a server except from Python.
#
# One property decides the shape of everything below: adding a server stores a
# command this studio will execute. That is not incidental, it is what MCP is,
# and it is a larger grant than any other route here. The guards, in order of
# how much they carry:
#
#   The middleware already limits this to loopback with a matching Host, an
#   allowed Origin and the session cookie, which is what keeps another site on
#   the machine from reaching it at all.
#
#   The extension cannot relay these. RELAYABLE_PATHS in background.js lists
#   three ingest endpoints and nothing else, so a content script on
#   linkedin.com has no path to them. A test pins that, because adding one
#   would be a one line change with consequences nobody would notice.
#
#   A command is a list, never a string, and is never passed to a shell. The
#   browser launcher was rewritten after "--gpu-launcher=cmd.exe /c calc.exe"
#   turned a URL field into arbitrary execution, and the same reasoning
#   applies to a field that is openly a command.
#
#   Adding does not enable. They are separate calls because they are separate
#   decisions, and a configuration pasted from a README must not start reading
#   a notes directory on the next draft.
# -------------------------------------------------------------

def _active_provider() -> str:
    """
    The provider in force right now, for the egress answer.

    Resolved per call rather than cached, because the provider can change
    between one draft and the next and a stale value would make a claim about
    where a creator's notes are going that is true of a different
    configuration. Falls back to the local engine on any failure, which is the
    conservative direction only for the label; gather computes its own report
    from the same value.
    """
    try:
        from .agno_agentos.model_gateway import get_current_ai_config
    except ImportError:
        from agno_agentos.model_gateway import get_current_ai_config
    try:
        return getattr(get_current_ai_config(), "provider", "") or ""
    except Exception:
        return ""


class McpServerRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=48)
    command: List[str] = Field(..., min_length=1, max_length=24)
    cwd: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    description: Optional[str] = ""

    @field_validator("command")
    @classmethod
    def command_is_a_list_of_arguments(cls, v: List[str]) -> List[str]:
        cleaned = [str(part) for part in v if str(part).strip()]
        if not cleaned:
            raise ValueError("A command needs at least one argument.")
        return cleaned


class McpEnabledRequest(BaseModel):
    enabled: bool


@app.get("/api/v1/mcp/servers", tags=["Grounding"])
def list_mcp_servers():
    """
    Every configured server and whether the creator switched it on.

    Also reports where grounding material would go, computed from the provider
    in force right now rather than stored, so the interface can say it before
    anything is gathered rather than after.
    """
    return {
        "status": "success",
        "servers": mcp_client.list_servers(),
        "egress": mcp_client.egress_report(_active_provider()),
    }


@app.post("/api/v1/mcp/servers", tags=["Grounding"])
def add_mcp_server(req: McpServerRequest):
    """
    Registers a server, switched off.

    There is no `enabled` field on this request on purpose. Agreeing that a
    command exists and agreeing to be read by it are different acts.
    """
    result = mcp_client.add_server(
        name=req.name,
        command=req.command,
        cwd=req.cwd,
        env=req.env or {},
        description=req.description or "",
    )
    if result.get("status") != "success":
        raise HTTPException(status_code=400, detail=result.get("message", "Could not add the server."))
    return result


@app.post("/api/v1/mcp/servers/{name}/enabled", tags=["Grounding"])
def set_mcp_server_enabled(name: str, req: McpEnabledRequest):
    """
    Switches a server on or off, and reports the state it achieved.

    Reads the value back rather than echoing the request, for the reason the
    queue pause was rewritten: a caller told "enabled" when the write failed
    believes their drafts are grounded when they are not.
    """
    result = mcp_client.set_enabled(name, req.enabled)
    if result.get("status") != "success":
        raise HTTPException(status_code=400, detail=result.get("message", "Could not change the server."))
    return result


@app.delete("/api/v1/mcp/servers/{name}", tags=["Grounding"])
def remove_mcp_server(name: str):
    result = mcp_client.remove_server(name)
    if result.get("status") != "success":
        raise HTTPException(status_code=404, detail=result.get("message", "No such server."))
    return result


@app.get("/api/v1/mcp/preview", tags=["Grounding"])
def preview_mcp_grounding():
    """
    What would be gathered, and whether it is about to leave this machine.

    The point of this route. The backend has been computing an egress answer
    on every gather and telling nobody, so a creator could not see what their
    notes server was handing over, or that it was about to be pasted into a
    prompt bound for a hosted provider. Showing the material before it is used
    is the difference between consent and a setting.

    Reads from the servers that are enabled, which is the same path a draft
    takes, so this is a preview of the real thing rather than a description
    of it.
    """
    gathered = mcp_client.gather(provider=_active_provider())
    return {
        "status": "success",
        "egress": gathered["egress"],
        "material": gathered["material"],
        "errors": gathered["errors"],
        "bytes_used": gathered["bytes_used"],
        "bytes_budget": gathered["bytes_budget"],
    }


# -------------------------------------------------------------
# Real-Time Event Bus & Server-Sent Events (SSE)
# -------------------------------------------------------------
@app.get("/api/v1/stream/events", tags=["Real-Time Event Stream"])
async def stream_events(request: Request, last_event_id: Optional[str] = Header(None, alias="Last-Event-ID")):
    """
    Subscribes the active browser Studio session to the real-time event bus via Server-Sent Events.
    Broadcasts draft_ingested, scheduled_post_recovery, and reverse_crm updates in under 5ms.
    """
    parsed_id = int(last_event_id) if last_event_id and last_event_id.isdigit() else None

    async def event_generator():
        async for event in event_bus.subscribe(parsed_id):
            if await request.is_disconnected():
                break
            yield event_bus.format_sse(event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/v1/stream/history", tags=["Real-Time Event Stream"])
def get_stream_history():
    """Returns past broadcast events from circular replay buffer."""
    return {"status": "success", "events": event_bus.get_history()}


class BroadcastEventRequest(BaseModel):
    event: str = Field(..., min_length=1, max_length=100)
    data: Dict[str, Any] = Field(default_factory=dict)


@app.post("/api/v1/stream/broadcast", tags=["Real-Time Event Stream"])
async def broadcast_event(req: BroadcastEventRequest):
    """Manually broadcasts an event across the SSE stream."""
    clean_event = re.sub(r"[\r\n]+", "", req.event).strip()
    if not clean_event:
        raise HTTPException(status_code=400, detail="Event name cannot be empty or pure whitespace.")
    payload = await event_bus.publish(clean_event, req.data)
    return {"status": "success", "published": payload}


# -------------------------------------------------------------
# Ubiquitous Ingress & Thought Capture
# -------------------------------------------------------------
class IngressSimulateRequest(BaseModel):
    text: str
    chat_id: Optional[str] = None
    sender_name: Optional[str] = "Creator"


@app.post("/api/v1/ingress/simulate", tags=["Ubiquitous Ingress"])
def simulate_ingress(req: IngressSimulateRequest):
    """
    Simulates incoming message from Telegram mobile bot or desktop tray.
    Parses directives (Draft:, Idea:, Schedule:), evaluates mobile fold,
    persists into SQLite WAL, and broadcasts live over SSE bus.
    """
    update_payload = {
        "update_id": int(time.time()),
        "message": {
            "chat": {"id": req.chat_id or ingress_daemon.authorized_chat_id or "local_creator"},
            "text": req.text,
            "from": {"first_name": req.sender_name}
        }
    }
    result = ingress_daemon.process_incoming_update(update_payload)
    if not result:
        return {"status": "skipped", "message": "Message dropped by whitelist security filter or empty."}
    return {"status": "success", "record": result}


class ParseTextRequest(BaseModel):
    text: str


@app.post("/api/v1/ingress/parse", tags=["Ubiquitous Ingress"])
def parse_ingress_text(req: ParseTextRequest):
    """Parses text without persisting, returning fold metrics and directives."""
    parsed = IngressMessageParser.parse_message(req.text)
    return {"status": "success", "parsed": parsed}


@app.get("/api/v1/ingress/drafts", tags=["Ubiquitous Ingress"])
def get_ingress_drafts(limit: int = 50, status: Optional[str] = None):
    """Retrieves sovereign drafts from SQLite drafts table."""
    drafts = list_drafts(limit=limit, status=status)
    return {"status": "success", "count": len(drafts), "drafts": drafts}


# -------------------------------------------------------------
# LinkedIn Native Cloud Scheduler & Grace Recovery
# -------------------------------------------------------------
class NativeStageRequest(BaseModel):
    content: str
    scheduled_at_ms: int
    author_urn: Optional[str] = None
    mock: bool = False


@app.post("/api/v1/scheduler/native/stage", tags=["LinkedIn Native Scheduler"])
def stage_native_scheduled_post(req: NativeStageRequest):
    """
    Pre-stages post directly into LinkedIn native cloud scheduler via Voyager API.
    Solves the sleeping laptop problem by delegating execution to LinkedIn cloud.
    """
    result = linkedin_client.schedule_norm_share(
        content=req.content,
        scheduled_at_ms=req.scheduled_at_ms,
        author_urn=req.author_urn,
        mock=req.mock
    )
    return result


class RecoveryEvaluateRequest(BaseModel):
    scheduled_at: str
    current_time: Optional[str] = None


@app.post("/api/v1/scheduler/recovery/evaluate", tags=["LinkedIn Native Scheduler"])
def evaluate_recovery(req: RecoveryEvaluateRequest):
    """
    Evaluates self-healing fallback when laptop wakes up late.
    Applies 45-minute morning grace window or auto-reschedules to 1:15 PM peak window.
    """
    try:
        sched_dt = datetime.fromisoformat(req.scheduled_at)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ISO timestamp format for scheduled_at")

    # A caller-supplied current_time was parsed with no guard, so a malformed
    # one raised inside the handler and returned a 500 for what is a bad
    # request. The default carries the machine's offset, so the answer names
    # which 1:15 PM it means instead of leaving the client to assume.
    if req.current_time:
        try:
            now_dt = datetime.fromisoformat(req.current_time)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid ISO timestamp format for current_time")
    else:
        now_dt = datetime.now().astimezone()
    recovery = linkedin_client.evaluate_schedule_recovery(sched_dt, current_time=now_dt)
    return {"status": "success", "recovery": recovery}


# -------------------------------------------------------------
# Enterprise Reverse CRM & Audience Graph
# -------------------------------------------------------------
class IngestInteractionRequest(BaseModel):
    full_name: str
    linkedin_urn: Optional[str] = None
    profile_url: Optional[str] = None
    headline: str
    company: Optional[str] = None
    interaction_type: Optional[str] = "COMMENT"
    comment_text: Optional[str] = None
    post_urn: Optional[str] = None
    post_id: Optional[int] = None
    # No default topic. A fixed string here ended up quoted in every generated
    # message as though it described the creator's actual post.
    post_topic: Optional[str] = None
    capture_context: Optional[str] = None


@app.post("/api/v1/crm/interactions/ingest", tags=["Enterprise Reverse CRM"])
def ingest_crm_interaction(req: IngestInteractionRequest):
    """
    Ingests commenter or reactor, calculates deterministic multi-factor ICP score,
    and synthesizes anti-slop 1-to-1 personalized DM.
    """
    # An unidentified person gets a clearly local key. Minting a urn:li:person:
    # put a value this studio invented into LinkedIn's own namespace, where it
    # was indistinguishable from one LinkedIn issued.
    urn = req.linkedin_urn or req.profile_url or f"local:unresolved:{uuid.uuid4().hex[:12]}"
    raw_type = (req.interaction_type or "COMMENT").upper()
    if "COMMENT" in raw_type:
        norm_type = "COMMENT"
    elif "LIKE" in raw_type:
        norm_type = "LIKE"
    elif "REPOST" in raw_type:
        norm_type = "REPOST"
    else:
        norm_type = "COMMENT"

    result = reverse_crm.ingest_interaction(
        full_name=req.full_name,
        linkedin_urn=urn,
        headline=req.headline,
        company=req.company,
        interaction_type=norm_type,
        comment_text=req.comment_text,
        post_urn=req.post_urn,
        post_id=req.post_id,
        post_topic=req.post_topic,
        capture_context=req.capture_context,
    )
    result["id"] = result.get("lead_id")
    result["qualification_tier"] = result.get("tier")
    return {"status": "success", "interaction": result, "lead": result}


@app.get("/api/v1/crm/leads/high-value", tags=["Enterprise Reverse CRM"])
def get_high_value_leads(min_score: float = 60.0, limit: int = 50):
    """Queries top ICP-matching leads sorted by score descending."""
    leads = reverse_crm.list_high_value_leads(min_icp_score=min_score, limit=limit)
    return {"status": "success", "count": len(leads), "leads": leads}


@app.get("/api/v1/crm/telemetry", tags=["Enterprise Reverse CRM"])
def get_crm_telemetry():
    """Macro telemetry across the reverse CRM: ICP score distribution, status funnel, inquiry metrics."""
    return reverse_crm.get_crm_telemetry()


class GenerateDMRequest(BaseModel):
    lead_name: str
    comment_text: str
    post_topic: Optional[str] = "sovereign creator stack"
    custom_insight: Optional[str] = None


@app.post("/api/v1/crm/leads/generate-dm", tags=["Enterprise Reverse CRM"])
def generate_lead_dm(req: GenerateDMRequest):
    """Generates an anti-slop 1-to-1 DM quoting the exact comment excerpt."""
    dm = ICPScoringEngine.generate_contextual_dm(
        lead_name=req.lead_name,
        comment_text=req.comment_text,
        post_topic=req.post_topic or "sovereign creator stack",
        custom_insight=req.custom_insight,
    )
    return {"status": "success", "suggested_dm": dm}


@app.post("/api/v1/crm/dm/variants", tags=["Enterprise Reverse CRM"])
def generate_anti_slop_dm_variants(req: GenerateDMRequest):
    """Generates 3 non-salesy, anti-slop DM options tailored to comment intent with strictly zero em-dashes."""
    variants = ICPScoringEngine.generate_anti_slop_dm_variants(
        lead_name=req.lead_name,
        comment_text=req.comment_text,
        post_topic=req.post_topic or "sovereign creator stack",
        custom_insight=req.custom_insight,
    )
    return {"status": "success", "variants": variants}


class ScorePreviewRequest(BaseModel):
    headline: str
    company: Optional[str] = None
    comment_text: Optional[str] = None
    interaction_type: Optional[str] = "COMMENT"


@app.post("/api/v1/crm/score-preview", tags=["Enterprise Reverse CRM"])
def preview_icp_score(req: ScorePreviewRequest):
    """Calculates deterministic ICP score, contributions, qualification tier, and intent signals."""
    breakdown = ICPScoringEngine.calculate_icp_breakdown(
        headline=req.headline,
        company=req.company,
        comment_text=req.comment_text,
        interaction_type=req.interaction_type or "COMMENT",
    )
    return {
        "status": "success",
        **breakdown,
    }


@app.delete("/api/v1/crm/leads/{lead_id}/purge", tags=["Enterprise Reverse CRM"])
def purge_crm_lead(lead_id: str):
    """
    GDPR Right-to-be-Forgotten Compliance Purge.
    Hard deletes lead and all associated interaction history.
    """
    res = reverse_crm.purge_lead(lead_id)
    if not res["lead_deleted"]:
        raise HTTPException(status_code=404, detail="Lead not found")
    return res


class ArchiveInactiveRequest(BaseModel):
    inactive_days: int = 90


@app.post("/api/v1/crm/leads/archive-inactive", tags=["Enterprise Reverse CRM"])
def archive_inactive_crm_leads(req: Optional[ArchiveInactiveRequest] = None):
    """Archives leads with no activity for more than specified days (default 90)."""
    days = req.inactive_days if req else 90
    result = reverse_crm.archive_inactive_leads(days)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/v1/crm/leads/{lead_id}/timeline", tags=["Enterprise Reverse CRM"])
def get_lead_interaction_timeline(lead_id: str):
    """Retrieves full interaction history and timeline for a given lead."""
    res = reverse_crm.get_lead_timeline(lead_id)
    if res["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Lead not found")
    return res


# -------------------------------------------------------------
# Post Identity: binding what the creator wrote to what LinkedIn published
# -------------------------------------------------------------
class InjectedPostRequest(BaseModel):
    content: str
    draft_id: Optional[int] = None


@app.post("/api/v1/posts/injected", tags=["Post Identity"])
def record_injected_post(req: InjectedPostRequest):
    """
    Record that the creator just put this text into LinkedIn's composer.

    This is bookkeeping on an event the studio itself caused, not an
    observation of LinkedIn, so it contacts nothing. It is also the first link
    in the only chain that can answer "which post produced my best leads":
    without a row here, the URN seen later on the permalink has nothing to
    attach to.
    """
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
            # An unbound post with the same fingerprint is the same post being
            # injected twice, which happens when the creator retries. Reuse it
            # rather than creating a second row that will compete for the URN.
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


class BindUrnRequest(BaseModel):
    activity_urn: str
    post_text: str


@app.post("/api/v1/posts/bind-urn", tags=["Post Identity"])
def bind_post_urn(req: BindUrnRequest):
    """
    Attach a LinkedIn activity URN to the post the creator wrote.

    The extension sends the URN from location.pathname and the text rendered on
    the page. Matching happens here rather than in the extension so the rule is
    testable and so the extension never has to track which post is armed.

    Refuses rather than guesses. If no unbound post matches the text, nothing is
    written, because a wrong binding would attribute one post's engagers to
    another and be very hard to notice.
    """
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
            if post_identity.fingerprint_matches(req.post_text, row["content_fingerprint"]):
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


@app.get("/api/v1/posts/{post_id}/engagers", tags=["Post Identity"])
def get_post_engagers(post_id: str):
    """
    The people who engaged with one post.

    This is the question the product exists to answer and the first time it can
    be asked of real data.
    """
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


@app.get("/api/v1/egress/status", tags=["Support & Maintenance"])
def get_egress_status():
    """
    What has left this machine, and what currently may.

    Counters, not a promise. The interface used to state that nothing but
    provider prompts ever left, which was untrue of four other features, and
    there was no way for a reader to check. This is the check.
    """
    return egress_policy.describe()


@app.get("/api/v1/session/health", tags=["LinkedIn Session & Telemetry"])
def check_session_health(mock: bool = False):
    """
    Checks session viability against the Voyager API.

    This contacts LinkedIn, so it is refused unless egress is explicitly
    enabled. A refusal returns healthy: null, meaning "not checked", rather than
    healthy: true, which would certify a session nobody looked at.
    """
    return linkedin_client.check_session_health(mock=mock)


@app.post("/api/v1/session/sync-profile", tags=["LinkedIn Session & Telemetry"])
def sync_linkedin_profile():
    """
    Fetches the creator's own name and headline from LinkedIn.

    This is the one place in the product that deliberately contacts LinkedIn,
    and it exists as its own route precisely so that contacting them is a thing
    someone chooses to do. It used to run as a side effect of saving a session
    token, which the extension did on a 15 minute alarm and on every
    creator-analytics response, so the studio was issuing authenticated requests
    the creator never asked for.

    Refused unless INOX_ALLOW_LINKEDIN_EGRESS is set.
    """
    return linkedin_client.sync_live_profile_and_stats(enforce_rate_limit=True)


@app.get("/api/v1/ingress/status", tags=["Mobile & Bot Ingress"])
def get_ingress_status():
    """Diagnostics and adaptive polling metrics for Telegram Ingress Daemon."""
    return ingress_daemon.get_daemon_status()


@app.post("/api/v1/database/checkpoint", tags=["Settings & Creator Profile"])
def trigger_database_checkpoint():
    """Truncates and checkpoints SQLite WAL file to minimize disk footprint."""
    return checkpoint_db()


@app.get("/api/v1/rate-limiter/status", tags=["Anti-Bot & Rate Limiting"])
def get_rate_limiter_status():
    """Telemetry diagnostics for the Gaussian jitter rate limiter."""
    return {
        "status": "success",
        "diagnostics": rate_limiter.get_diagnostics()
    }


class RateLimiterAcquireRequest(BaseModel):
    tokens: float = Field(default=1.0, ge=0.0, le=100.0)
    block: bool = Field(default=False)
    timeout: Optional[float] = Field(default=None, ge=0.0, le=30.0)


@app.post("/api/v1/rate-limiter/acquire", tags=["Anti-Bot & Rate Limiting"])
def acquire_rate_limit_token(req: Optional[RateLimiterAcquireRequest] = None):
    """Acquires a token under the Gaussian jitter rate governor."""
    t = req.tokens if req else 1.0
    b = req.block if req else False
    timeout = req.timeout if req else None
    if b and timeout is None:
        timeout = 10.0  # Defensive cap to prevent blocking FastAPI thread indefinitely
    success = rate_limiter.acquire(tokens=t, block=b, timeout=timeout)
    wait_time = rate_limiter.wait_time_seconds(tokens=t)
    return {
        "status": "success" if success else "rejected",
        "acquired": success,
        "wait_time_seconds": wait_time,
        "diagnostics": rate_limiter.get_diagnostics()
    }


@app.get("/api/v1/rate-limiter/single-writer/metrics", tags=["Anti-Bot & Rate Limiting"])
def get_single_writer_metrics():
    """Diagnostics for the centralized single-writer actor write queue."""
    return {
        "status": "success",
        "metrics": write_actor.get_metrics()
    }


class IntelligenceSyncRequest(BaseModel):
    force: bool = False
    cdn_url: Optional[str] = None


@app.post("/api/v1/intelligence/sync", tags=["Intelligence Sync & Radar"])
def trigger_intelligence_sync(req: Optional[IntelligenceSyncRequest] = None):
    """Triggers asymmetric ETag-based intelligence sync against the GitHub CDN."""
    force = req.force if req else False
    cdn_url = req.cdn_url if req else None
    res = intelligence_sync_engine.sync(force=force, cdn_url=cdn_url)
    if isinstance(res, dict) and res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Sync failed"))
    return res


@app.get("/api/v1/intelligence/templates", tags=["Intelligence Sync & Radar"])
def get_viral_templates(archetype: Optional[str] = None, query: Optional[str] = None, limit: int = 100):
    """Returns ranked viral hook archetypes ordered by algorithmic velocity score."""
    templates = intelligence_sync_engine.get_templates(archetype=archetype, query=query, limit=limit)
    total_vaulted = intelligence_sync_engine.get_total_count()
    return {
        "status": "success",
        "templates": templates,
        "count": len(templates),
        "total_vaulted": total_vaulted
    }


@app.get("/api/v1/intelligence/status", tags=["Intelligence Sync & Radar"])
def get_intelligence_sync_status():
    """Returns current ETag caching state and last sync timestamp."""
    return intelligence_sync_engine.get_status()


@app.get("/api/v1/intelligence/bundle/export", tags=["Intelligence Sync & Radar"])
def export_intelligence_bundle(request: Request):
    """Exports compiled local viral templates as an asymmetric intelligence bundle with ETag support."""
    bundle = intelligence_sync_engine.compile_local_bundle()
    bundle_hash_content = json.dumps({"version": bundle.get("version"), "templates": bundle.get("templates")}, sort_keys=True)
    import hashlib
    etag = f'"{hashlib.sha256(bundle_hash_content.encode("utf-8")).hexdigest()[:16]}"'
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(
        content={"status": "success", "bundle": bundle, "etag": etag},
        headers={"ETag": etag, "Cache-Control": "public, max-age=3600"}
    )


class ImportBundleRequest(BaseModel):
    bundle: Dict[str, Any]


@app.post("/api/v1/intelligence/bundle/import", tags=["Intelligence Sync & Radar"])
def import_intelligence_bundle(req: ImportBundleRequest):
    """Imports an asymmetric intelligence bundle directly for air-gapped workstations."""
    res = intelligence_sync_engine.import_local_bundle(req.bundle)
    if isinstance(res, dict) and res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Bundle import failed"))
    return res


class GStackBacklogTaskCreate(BaseModel):
    role: str = Field(..., max_length=50)
    title: str = Field(..., min_length=1, max_length=300)
    specification: str = Field(..., min_length=1, max_length=10000)
    status: Optional[str] = Field("PENDING", max_length=50)


class GStackBacklogStatusUpdate(BaseModel):
    status: str = Field(..., min_length=1, max_length=50)


class GStackAuditRequest(BaseModel):
    content: str = Field(..., max_length=50000)
    title: Optional[str] = Field(None, max_length=300)


class InternalSheetIssueCreate(BaseModel):
    target_selector: str = Field(..., min_length=1, max_length=500)
    title: str = Field(..., min_length=1, max_length=300)
    description: str = Field(..., min_length=1, max_length=10000)
    category: Optional[str] = Field("bug", max_length=50)
    severity: Optional[str] = Field("medium", max_length=50)
    suggested_role: Optional[str] = Field("ENGINEERING_MANAGER", max_length=50)
    element_tag: Optional[str] = Field(None, max_length=100)
    element_id: Optional[str] = Field(None, max_length=200)
    element_classes: Optional[str] = Field(None, max_length=500)
    element_text_snippet: Optional[str] = Field(None, max_length=1000)
    tab_name: Optional[str] = Field("composer", max_length=100)
    page_route: Optional[str] = Field("/", max_length=200)
    bounding_box: Optional[Dict[str, Any]] = None
    viewport_resolution: Optional[str] = Field(None, max_length=100)
    dom_path: Optional[str] = Field(None, max_length=1000)
    promote_to_backlog: Optional[bool] = False
    # Location and evidence. The browser proposes, devtools.resolve_location
    # and devtools.normalize_capture dispose.
    tab_id: Optional[str] = Field(None, max_length=100)
    section_hint: Optional[str] = Field(None, max_length=200)
    ancestor_ids: Optional[List[str]] = None
    capture: Optional[Dict[str, Any]] = None


class InternalSheetStatusUpdate(BaseModel):
    status: str = Field(..., min_length=1, max_length=50)


class InternalSheetImport(BaseModel):
    payload: Dict[str, Any]


class DevModeToggle(BaseModel):
    enabled: bool


class AutostartToggle(BaseModel):
    enabled: bool


def require_dev_mode():
    """
    The gate in front of every maintainer route.

    Answers 404 rather than 403 on purpose. A consumer build should look like a
    build where these endpoints were never written, not like one that has them
    and is declining to say so. Gating the router and not only the interface
    matters: hiding a button leaves the endpoint answering to anything that can
    reach the port.
    """
    if not devtools.is_dev_mode():
        raise HTTPException(status_code=404, detail="Not Found")
    return True


@app.get("/api/v1/schema/status", tags=["Settings & Creator Profile"])
def get_schema_status():
    """
    Reports the database schema version against what this build expects.

    This is the first thing to look at when a user says an upgrade went wrong,
    and it is included in the diagnostics bundle for exactly that reason.
    """
    try:
        status = describe_schema()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read schema status: {exc}")

    status["app_version"] = __version__
    if status["too_new"]:
        status["advice"] = (
            "This database was written by a newer build. Reinstall the newer version, "
            "or restore a pre-migration backup."
        )
    elif not status["up_to_date"]:
        status["advice"] = "Pending migrations will be applied on the next restart."
    else:
        status["advice"] = "Schema is current."
    return status


@app.get("/api/v1/support/diagnostics", tags=["Support & Maintenance"])
def get_diagnostics():
    """
    Redacted diagnostics the user can attach to an issue.

    Session cookies and API keys are removed by allowlist before this returns.
    See studio/backend/support.py for why that is an allowlist.
    """
    return support_tools.collect_diagnostics()


@app.post("/api/v1/support/diagnostics/export", tags=["Support & Maintenance"])
def export_diagnostics():
    path = support_tools.write_diagnostics_bundle()
    return {"status": "success", "path": path,
            "note": "Safe to attach to a public issue. Credentials are redacted."}


@app.post("/api/v1/support/backup", tags=["Support & Maintenance"])
def create_support_backup(payload: Optional[Dict[str, Any]] = None):
    label = (payload or {}).get("label", "manual")
    archive = support_tools.create_backup(str(label)[:40])
    return {"status": "success", "archive": archive,
            "bytes": os.path.getsize(archive)}


@app.get("/api/v1/support/backups", tags=["Support & Maintenance"])
def list_support_backups():
    directory = get_backups_dir()
    entries = []
    for name in sorted(os.listdir(directory), reverse=True):
        full = os.path.join(directory, name)
        entries.append({"name": name, "bytes": os.path.getsize(full),
                        "modified": datetime.fromtimestamp(os.path.getmtime(full)).isoformat()})
    return {"directory": directory, "count": len(entries), "backups": entries}


@app.post("/api/v1/support/export", tags=["Support & Maintenance"])
def export_user_data(payload: Optional[Dict[str, Any]] = None):
    fmt = (payload or {}).get("format", "json")
    if fmt not in ("json", "csv"):
        raise HTTPException(status_code=400, detail="format must be json or csv")
    path = support_tools.export_data(fmt=fmt)
    return {"status": "success", "path": path, "format": fmt,
            "note": "Content only. Credentials are deliberately excluded."}


@app.get("/api/v1/updates/status", tags=["Support & Maintenance"])
def get_update_status():
    """Reports the preference without performing any network request."""
    return update_checker.describe()


@app.post("/api/v1/updates/preference", tags=["Support & Maintenance"])
def set_update_preference(payload: Dict[str, Any]):
    if "enabled" not in payload:
        raise HTTPException(status_code=400, detail="'enabled' is required")
    return update_checker.set_enabled(bool(payload["enabled"]))


@app.post("/api/v1/updates/check", tags=["Support & Maintenance"])
def run_update_check(payload: Optional[Dict[str, Any]] = None):
    """
    Performs the check only if the user opted in. Returns a version and a link.
    Nothing is downloaded, installed, or executed.
    """
    return update_checker.check_for_update(force=bool((payload or {}).get("force")))


@app.get("/api/v1/gstack/roles", tags=["G-Stack Multi-Agent Governance"])
def get_gstack_roles():
    """Returns the 6 G-Stack cognitive roles, their titles, PRD references, and mandates."""
    return {
        "status": "success",
        "roles": gstack_engine.get_roles()
    }


@app.get("/api/v1/gstack/backlog", tags=["G-Stack Multi-Agent Governance"])
def get_gstack_backlog(role: Optional[str] = None, status: Optional[str] = None, limit: int = 500):
    """Lists backlog tasks filtered by G-Stack role or status."""
    tasks = gstack_engine.get_backlog(role=role, status=status, limit=limit)
    return {
        "status": "success",
        "tasks": tasks,
        "count": len(tasks)
    }


@app.post("/api/v1/gstack/backlog", tags=["G-Stack Multi-Agent Governance"])
def add_gstack_task(req: GStackBacklogTaskCreate):
    """Appends a new engineering task to the G-Stack governance backlog."""
    try:
        task_id = gstack_engine.add_backlog_task(
            role=req.role,
            title=req.title,
            specification=req.specification,
            status=req.status or "PENDING"
        )
        return {
            "status": "success",
            "task_id": task_id
        }
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.patch("/api/v1/gstack/backlog/{task_id}", tags=["G-Stack Multi-Agent Governance"])
def update_gstack_task_status(task_id: int, req: GStackBacklogStatusUpdate):
    """Updates the execution status of a G-Stack backlog item."""
    try:
        updated = gstack_engine.update_backlog_status(task_id=task_id, status=req.status)
        return {
            "status": "success" if updated else "not_found",
            "updated": updated
        }
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.post("/api/v1/gstack/audit", tags=["G-Stack Multi-Agent Governance"])
def audit_gstack_content(req: GStackAuditRequest):
    """Audits content against all 6 G-Stack gates (anti-slop, fold pacing, zero-egress)."""
    return {
        "status": "success",
        "audit": gstack_engine.audit_content_or_feature(content=req.content, title=req.title)
    }


# -------------------------------------------------------------
# Module: Internal Sheet & Visual Concept Identifier
# -------------------------------------------------------------
@app.get("/api/v1/internal-sheet/issues", tags=["Internal Sheet & Concept Identifier"], dependencies=[Depends(require_dev_mode)])
def list_internal_sheet_issues(
    status: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    tab_name: Optional[str] = None,
    limit: int = 200
):
    """Lists logged screen concept issues, bugs, and annotations with summary metrics."""
    issues = internal_sheet_manager.list_issues(
        status=status,
        category=category,
        severity=severity,
        tab_name=tab_name,
        limit=limit
    )
    summary = internal_sheet_manager.get_summary_metrics()
    return {
        "status": "success",
        "issues": issues,
        "count": len(issues),
        "summary": summary
    }


@app.post("/api/v1/internal-sheet/issues", tags=["Internal Sheet & Concept Identifier"], dependencies=[Depends(require_dev_mode)])
def create_internal_sheet_issue(req: InternalSheetIssueCreate):
    """Creates a new screen concept identification or bug annotation in the internal sheet."""
    try:
        issue = internal_sheet_manager.create_issue(
            target_selector=req.target_selector,
            title=req.title,
            description=req.description,
            category=req.category or "bug",
            severity=req.severity or "medium",
            suggested_role=req.suggested_role or "ENGINEERING_MANAGER",
            element_tag=req.element_tag,
            element_id=req.element_id,
            element_classes=req.element_classes,
            element_text_snippet=req.element_text_snippet,
            tab_name=req.tab_name or "composer",
            page_route=req.page_route or "/",
            bounding_box=req.bounding_box,
            viewport_resolution=req.viewport_resolution,
            dom_path=req.dom_path,
            promote_to_backlog=bool(req.promote_to_backlog),
            tab_id=req.tab_id,
            section_hint=req.section_hint,
            ancestor_ids=req.ancestor_ids,
            capture=req.capture,
        )
        # Reported alongside the new record rather than made the caller's job to
        # go looking for. Filing the same broken card twice is the failure mode
        # an annotation ledger has, and this is where it gets caught.
        duplicates = internal_sheet_manager.find_duplicates(
            issue.get("repro_hash") or "", exclude_id=issue.get("id")
        )
        return {
            "status": "success",
            "issue": issue,
            "duplicates": [
                {"id": d["id"], "title": d["title"], "status": d["status"]}
                for d in duplicates
            ],
        }
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.get("/api/v1/internal-sheet/issues/{issue_id}", tags=["Internal Sheet & Concept Identifier"], dependencies=[Depends(require_dev_mode)])
def get_internal_sheet_issue(issue_id: int):
    """Retrieves a single internal sheet issue by ID."""
    issue = internal_sheet_manager.get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    return {
        "status": "success",
        "issue": issue
    }


@app.patch("/api/v1/internal-sheet/issues/{issue_id}/status", tags=["Internal Sheet & Concept Identifier"], dependencies=[Depends(require_dev_mode)])
def update_internal_sheet_issue_status(issue_id: int, req: InternalSheetStatusUpdate):
    """Updates the resolution status of an internal sheet issue (e.g. OPEN or RESOLVED)."""
    try:
        updated = internal_sheet_manager.update_issue_status(issue_id, req.status)
        if not updated:
            raise HTTPException(status_code=404, detail="Issue not found")
        return {
            "status": "success",
            "issue": internal_sheet_manager.get_issue(issue_id)
        }
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.delete("/api/v1/internal-sheet/issues/{issue_id}", tags=["Internal Sheet & Concept Identifier"], dependencies=[Depends(require_dev_mode)])
def delete_internal_sheet_issue(issue_id: int):
    """Deletes an internal sheet issue record."""
    deleted = internal_sheet_manager.delete_issue(issue_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Issue not found")
    return {
        "status": "success",
        "deleted": True
    }


@app.post("/api/v1/internal-sheet/issues/{issue_id}/promote", tags=["Internal Sheet & Concept Identifier"], dependencies=[Depends(require_dev_mode)])
def promote_internal_sheet_issue(issue_id: int):
    """Promotes an internal sheet issue to the active G-Stack multi-agent backlog."""
    task_id = internal_sheet_manager.promote_to_gstack(issue_id)
    if task_id is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return {
        "status": "success",
        "gstack_task_id": task_id
    }


@app.get("/api/v1/internal-sheet/export.csv", tags=["Internal Sheet & Concept Identifier"], dependencies=[Depends(require_dev_mode)])
def export_internal_sheet_csv():
    """Streams an RFC-4180 CSV spreadsheet file compatible with Google Sheets and Microsoft Excel."""
    csv_data = internal_sheet_manager.export_csv()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=internal_concept_sheet.csv"
        }
    )


@app.get("/api/v1/health", tags=["Settings & Creator Profile"])
def get_health():
    """
    Readiness probe. The one route that answers without a token.

    It exists for callers that have to know whether this process is up before
    they can do anything else, and that have nowhere to get a token from yet:
    the desktop shell deciding whether to show a window or keep waiting, and a
    launcher deciding whether to start a second server.

    Deliberately says almost nothing. An unauthenticated endpoint is readable
    by any process on the machine, so it reports liveness and version and not
    one fact about the creator, their content, or their configuration.
    """
    return {
        "status": "ok",
        "app": "inox-hydra",
        "version": __version__,
    }


# -------------------------------------------------------------
# Desktop Integration
#
# Whether this installation starts with Windows, and what Windows calls it.
# Autostart is off until asked for and visible in Settings once on, because
# software that quietly adds itself to startup is the kind of software this
# product exists to replace.
# -------------------------------------------------------------
@app.get("/api/v1/desktop/integration", tags=["Settings & Creator Profile"])
def get_desktop_integration():
    """Reports the desktop integration state, including why a control is off."""
    return {"status": "success", "desktop": desktop_integration.describe()}


@app.post("/api/v1/desktop/autostart", tags=["Settings & Creator Profile"])
def set_desktop_autostart(req: AutostartToggle):
    """
    Turns the Startup shortcut on or off.

    Reports the resulting state rather than echoing the request, so a failure
    to write the shortcut surfaces as the switch staying off rather than as a
    switch that says on while nothing happens at login.
    """
    if req.enabled:
        result = desktop_integration.enable_autostart()
    else:
        result = desktop_integration.disable_autostart()

    return {
        "status": "success",
        "result": result,
        "desktop": desktop_integration.describe(),
    }


# -------------------------------------------------------------
# Developer Tools
#
# Everything below is absent from a consumer build. The status endpoint is the
# one exception: the interface has to be able to ask whether the surface exists
# before deciding whether to render it, so that route answers honestly either
# way instead of 404ing and leaving the frontend to guess from a failed fetch.
# -------------------------------------------------------------
@app.get("/api/v1/devtools/status", tags=["Developer Tools"])
def get_devtools_status():
    """Whether the maintainer surface is available in this build."""
    if not devtools.is_dev_mode():
        return {"status": "success", "dev_mode": False, "capabilities": [], "screens": []}
    return {"status": "success", **devtools.capability_report()}


@app.post("/api/v1/devtools/mode", tags=["Developer Tools"], dependencies=[Depends(require_dev_mode)])
def set_devtools_mode(req: DevModeToggle):
    """
    Toggles the surface for this installation without a restart. Cannot turn dev
    mode on where the environment does not already allow it, so this is never a
    way into a consumer install.
    """
    effective = devtools.set_runtime_dev_mode(bool(req.enabled))
    return {"status": "success", "dev_mode": effective}


@app.get("/api/v1/devtools/state", tags=["Developer Tools"], dependencies=[Depends(require_dev_mode)])
def get_devtools_state():
    """Row counts, worker state, and the build this process is running."""
    return {"status": "success", "state": devtools.state_inspector()}


@app.get("/api/v1/devtools/migrations", tags=["Developer Tools"], dependencies=[Depends(require_dev_mode)])
def get_devtools_migrations():
    """Where this database sits against the forward-only ledger. Read only."""
    return {"status": "success", "migrations": devtools.migration_inspector()}


@app.post("/api/v1/devtools/migrations/apply", tags=["Developer Tools"], dependencies=[Depends(require_dev_mode)])
def apply_devtools_migrations():
    """
    Applies pending migrations. Separate from the inspector on purpose: looking
    at the schema should never be the thing that changes it.
    """
    try:
        from .migrations import ensure_schema
        from .database import get_db as _get_db
    except ImportError:
        from migrations import ensure_schema
        from database import get_db as _get_db

    conn = _get_db()
    try:
        report = ensure_schema(conn, take_backup=True)
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Migration failed: {err}")
    finally:
        conn.close()
    return {"status": "success", "report": report}


@app.get("/api/v1/devtools/coverage", tags=["Developer Tools"], dependencies=[Depends(require_dev_mode)])
def get_devtools_coverage():
    """
    How much of the interface can be addressed by name rather than by selector.
    A screen with a high unmapped count loses its annotation history the next
    time somebody restyles it.
    """
    return {"status": "success", "coverage": devtools.section_coverage()}


@app.get("/api/v1/devtools/sheet/export.json", tags=["Developer Tools"], dependencies=[Depends(require_dev_mode)])
def export_internal_sheet_json():
    """A lossless, re-importable dump of the annotation ledger."""
    return internal_sheet_manager.export_json()


@app.post("/api/v1/devtools/sheet/import", tags=["Developer Tools"], dependencies=[Depends(require_dev_mode)])
def import_internal_sheet_json(req: InternalSheetImport):
    """Merges an exported sheet into this database. Importing twice is a no-op."""
    try:
        result = internal_sheet_manager.import_json(req.payload)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return {"status": "success", **result}


# -------------------------------------------------------------
# Static Dashboard UI & Master Asset Mount
# -------------------------------------------------------------
FRONTEND_DIR = get_frontend_dir()
STUDIO_ASSETS_DIR = get_assets_dir()
os.makedirs(STUDIO_ASSETS_DIR, exist_ok=True)
app.mount("/assets", StaticFiles(directory=STUDIO_ASSETS_DIR), name="assets")

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    # The interface is built from studio/ui and is not in the repository.
    # A bare 404 here reads like a wrong URL; this says which step was
    # missed. There used to be a second, vanilla page to fall back to, and
    # falling back silently is what kept a packaging defect invisible.
    @app.get("/", include_in_schema=False)
    def _interface_not_built():
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "The studio interface has not been built. Run npm ci and "
                    "npm run build in studio/ui, which writes studio/frontend_next."
                )
            },
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
