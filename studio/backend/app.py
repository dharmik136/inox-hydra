"""
Inox Hydra - Core API Gateway & Lifespan Controller
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
import logging
import csv
import json
import sqlite3
import uuid
import re
from typing import Optional, List, Dict, Any
from urllib.parse import unquote
from datetime import datetime, date, timedelta, timezone
from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, HTTPException, Response, UploadFile, File, Form, Request, Header, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
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
                            is_queue_paused, set_queue_paused, LINKEDIN_HOLDS_KEY)
    from .agno_agent import agno_orchestrator
    from .agno_agentos import orchestrator
    from .image_studio import image_studio_manager
    from .event_bus import event_bus
    from .ingress import IngressMessageParser, TelegramIngressDaemon, ingress_daemon
    from .crm import ICPScoringEngine, ReverseCRMManager, reverse_crm
    from .rate_limiter import rate_limiter, write_actor
    from .intelligence_sync import intelligence_sync_engine
    from . import universal_search
    from .gstack_governance import gstack_engine
    from .internal_sheet import internal_sheet_manager
    from . import onboarding
    from . import accounts
    from . import licensing
    from . import archive_import
    from . import today as today_module
    from . import insights
    from . import devtools
    from . import security
    from . import desktop as desktop_integration
    from .migrations import describe as describe_schema
    from . import support as support_tools
    from . import updates as update_checker
    from .paths import (get_assets_dir, get_uploads_dir, get_generated_dir, get_data_dir,
                        get_frontend_dir, get_docs_dir, get_modules_docs_dir, get_backups_dir,
                        describe as describe_paths)
    from . import paths as paths_module
    from .docs_engine import (search_docs_fts, init_docs_search_index,
                              document_library, document_slug,
                              help_sections, section_meta, section_kind)
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
                           is_queue_paused, set_queue_paused, LINKEDIN_HOLDS_KEY)
    from agno_agent import agno_orchestrator
    from agno_agentos import orchestrator
    from image_studio import image_studio_manager
    from event_bus import event_bus
    from ingress import IngressMessageParser, TelegramIngressDaemon, ingress_daemon
    from crm import ICPScoringEngine, ReverseCRMManager, reverse_crm
    from rate_limiter import rate_limiter, write_actor
    from intelligence_sync import intelligence_sync_engine
    import universal_search
    from gstack_governance import gstack_engine
    from internal_sheet import internal_sheet_manager
    import onboarding
    import accounts
    import licensing
    import archive_import
    import today as today_module
    import insights
    import devtools
    import security
    import desktop as desktop_integration
    from migrations import describe as describe_schema
    import support as support_tools
    import updates as update_checker
    from paths import (get_assets_dir, get_uploads_dir, get_generated_dir, get_data_dir,
                       get_frontend_dir, get_docs_dir, get_modules_docs_dir, get_backups_dir,
                        describe as describe_paths)
    import paths as paths_module
    from docs_engine import (search_docs_fts, init_docs_search_index,
                            document_library, document_slug,
                            help_sections, section_meta, section_kind)
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
    # Every other creator profile's database too, so switching to one, or the
    # scheduler visiting it, never meets a schema older than this build.
    for _profile in paths_module.profile_ids():
        if _profile == paths_module.get_active_profile_id():
            continue
        try:
            with paths_module.using_profile(_profile):
                init_db()
        except Exception:
            logging.getLogger("studio.profiles").warning(
                "Could not bring profile %s up to this build's schema.", _profile, exc_info=True)
    # An AI key saved before keys were sealed is still readable in the file
    # until something saves it again. Sealed here instead, once; a sealed
    # value is left alone, so this does nothing on every later start.
    try:
        from secret_settings import upgrade_plaintext as _upgrade_secrets
    except ImportError:
        from .secret_settings import upgrade_plaintext as _upgrade_secrets
    try:
        _conn = get_db()
        try:
            _upgrade_secrets(_conn)
        finally:
            _conn.close()
    except Exception:
        logging.getLogger("studio.vault").warning("Could not seal stored secrets at startup.", exc_info=True)
    # The offline documentation index, built here rather than on whichever
    # search happened to run first. It was imported into this module and never
    # called, so the index was a snapshot of the corpus as it stood the first
    # time anyone searched, for the life of the database. Cheap: 38 files.
    try:
        init_docs_search_index()
    except Exception:
        # A documentation index that cannot build is not a reason to refuse to
        # start. search_docs_fts retries, and the reader opens documents from
        # disk either way. Logged through the docs_engine logger, which already
        # records the specific failures; this module declares none of its own,
        # and reaching for an undefined one here would turn a warning into a
        # NameError inside the startup path.
        logging.getLogger("studio.docs").warning(
            "The documentation search index did not build at startup.", exc_info=True
        )
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
    title="Inox Hydra",
    description="A self-hosted, local-first LinkedIn creator studio on localhost. Nothing leaves this machine unless a feature you switch on needs to.",
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


# -------------------------------------------------------------
# One error boundary
#
# Without these, any error a route did not catch answered a bare
# "500 Internal Server Error" in plain text, which the interface showed as
# "The studio refused this request (500)". Worse, a request carrying half an
# emoji (a lone UTF-16 surrogate) or a NaN failed validation, and FastAPI's own
# 422 handler then crashed echoing that input back, so the extension's capture
# was answered 500 and resent for ever.
#
# Every answer below is JSON in the shape refusalFrom() in the interface
# reads: {"detail": {"code", "message"}} or, for validation, a list of
# {"loc", "msg", "type"}. None carries a traceback, the request's input, or a
# stored value. The traceback goes to the log only.
# -------------------------------------------------------------
_error_log = logging.getLogger("studio.errors")

# The access log keeps paths, never query strings, and only the requests that
# failed or changed something. See log_setup.py.
try:
    from . import log_setup
except ImportError:
    import log_setup
log_setup.install()

try:
    from fastapi.exceptions import RequestValidationError
    from pydantic import ValidationError as _PydanticValidationError
except ImportError:  # pragma: no cover
    RequestValidationError = _PydanticValidationError = None


def _printable(text: Any) -> str:
    """Text that can always be encoded as UTF-8: a lone surrogate becomes U+FFFD."""
    return str(text).encode("utf-8", "replace").decode("utf-8") if text is not None else ""


def _studio_error(status: int, code: str, message: str, headers: Optional[Dict[str, str]] = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": {"code": code, "message": message}}, headers=headers)


def _validation_answer(errors) -> JSONResponse:
    detail = []
    for error in errors or []:
        detail.append({
            "loc": [_printable(part) if not isinstance(part, int) else part for part in error.get("loc", ())],
            "msg": _printable(error.get("msg", "")),
            "type": _printable(error.get("type", "")),
        })
    return JSONResponse(status_code=422, content={"detail": detail})


def _database_trouble(error: BaseException) -> Optional[JSONResponse]:
    """The answer for a database or disk failure a person can act on, or None."""
    said = str(error).lower()
    full = (isinstance(error, OSError) and getattr(error, "errno", None) == 28) or "disk is full" in said \
        or "database or disk is full" in said
    if full:
        return _studio_error(
            503, "disk_full",
            "The drive that holds the studio's data is full, so this was not saved. "
            f"Free some space on it (the data folder is {paths_module.get_app_home()}) and try again.",
        )
    if isinstance(error, sqlite3.OperationalError) and ("locked" in said or "busy" in said):
        return _studio_error(
            503, "studio_busy",
            "The studio's database is busy with another task, such as an import, a backup or a second "
            "copy of the studio. Nothing was saved. Try again in a moment.",
            headers={"Retry-After": "5"},
        )
    if isinstance(error, sqlite3.DatabaseError) and ("malformed" in said or "not a database" in said):
        return _studio_error(
            503, "database_damaged",
            "The studio's database file is damaged, so this could not be read or saved. Restore your "
            "newest backup: run \"python -m studio.cli doctor\", which prints the exact restore command, "
            "then start the studio again.",
        )
    return None


_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
_SURROGATE_ESCAPE = re.compile(rb"\\u[dD][89a-fA-F][0-9a-fA-F]{2}")


def _without_lone_surrogates(value: Any) -> Any:
    if isinstance(value, str):
        return _LONE_SURROGATE.sub("", value)
    if isinstance(value, list):
        return [_without_lone_surrogates(item) for item in value]
    if isinstance(value, dict):
        return {_without_lone_surrogates(k): _without_lone_surrogates(v) for k, v in value.items()}
    return value


class DropLoneSurrogates:
    """
    Removes half-characters from a JSON body before any route reads it.

    JavaScript cuts strings in UTF-16 units, so a client that trims text to a
    length can cut an emoji in half, and JSON.stringify then sends the lone
    half as an escape such as \\ud83d. Python decodes it into a string nothing
    can store or encode: SQLite refused it, and the extension's lead was lost.
    A lone half shows as nothing on any screen, so it is dropped and the rest
    of the text is kept. A whole pair decodes to one character and is never
    touched. Only a body that contains such an escape is re-read.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        if b"json" not in headers.get(b"content-type", b""):
            return await self.app(scope, receive, send)

        chunks, more = [], True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                return await self.app(scope, _replay([message], receive), send)
            chunks.append(message.get("body", b""))
            more = message.get("more_body", False)
        body = b"".join(chunks)

        if _SURROGATE_ESCAPE.search(body):
            try:
                cleaned = _without_lone_surrogates(json.loads(body))
                body = json.dumps(cleaned, ensure_ascii=False).encode("utf-8")
                scope = dict(scope)
                scope["headers"] = [(k, v) for k, v in scope["headers"] if k != b"content-length"] + [
                    (b"content-length", str(len(body)).encode("ascii"))]
            except ValueError:
                pass  # Not JSON at all: the route's own validation answers it.
        return await self.app(scope, _replay([{"type": "http.request", "body": body, "more_body": False}], receive),
                              send)


def _replay(messages, then):
    """Hands back the messages already read, then whatever the client sends next."""
    pending = list(messages)

    async def receive():
        if pending:
            return pending.pop(0)
        return await then()

    return receive


app.add_middleware(DropLoneSurrogates)


@app.exception_handler(RequestValidationError)
async def _answer_invalid_request(request: Request, error):
    return _validation_answer(error.errors())


@app.exception_handler(_PydanticValidationError)
async def _answer_invalid_value(request: Request, error):
    # A model built inside a route from the request's values, such as an
    # agent's input contract, is the request's fault, not the studio's.
    return _validation_answer(error.errors(include_url=False, include_input=False, include_context=False))


@app.exception_handler(sqlite3.Error)
async def _answer_database_error(request: Request, error):
    answer = _database_trouble(error)
    if answer is not None:
        _error_log.warning("%s %s: %s", request.method, request.scope.get("path", ""), _printable(error))
        return answer
    return _answer_unexpected_error_now(request, error)


@app.exception_handler(OSError)
async def _answer_os_error(request: Request, error):
    answer = _database_trouble(error)
    if answer is not None:
        _error_log.warning("%s %s: %s", request.method, request.scope.get("path", ""), _printable(error))
        return answer
    return _answer_unexpected_error_now(request, error)


def _answer_unexpected_error_now(request: Request, error: BaseException, log: bool = True) -> JSONResponse:
    if log:
        _error_log.error("%s %s failed", request.method, request.scope.get("path", ""),
                         exc_info=(type(error), error, error.__traceback__))
    return _studio_error(
        500, "internal_error",
        "Something went wrong inside the studio and this did not finish. Nothing more is shown here; "
        "the details are in the studio's log (engine.log in the logs folder).",
    )


@app.exception_handler(Exception)
async def _answer_unexpected_error(request: Request, error):
    # Starlette raises the error again after this answer is sent, and the
    # server logs its traceback then, so it is not logged twice here.
    return _answer_unexpected_error_now(request, error, log=False)


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


# Which creator profile a window is showing. The interface sends it on every
# request, and every trusted answer carries the profile that served it.
PROFILE_HEADER = "X-Inox-Profile"


def _is_trusted_api_request(request: Request) -> bool:
    """
    The checks enforce_local_access makes, asked again here.

    pin_creator_profile is the outer middleware, so it runs before the
    security one. Without these it would tell an unauthenticated caller which
    profile is active, and refuse its writes with a different code than the
    401 it is owed.
    """
    path = request.scope.get("path", "")
    if not path.startswith("/api") or security.request_is_exempt(path):
        return False
    host = request.headers.get("host")
    if not security.is_loopback_host(host):
        return False
    if not security.is_allowed_origin(request.headers.get("origin"), security.extract_port(host)):
        return False
    supplied = request.headers.get(security.TOKEN_HEADER) or request.cookies.get(security.TOKEN_COOKIE)
    return security.constant_time_match(supplied, security.get_or_create_token())


def _profile_name(profile_id: str) -> str:
    try:
        account = accounts.get_account(profile_id)
    except Exception:
        account = None
    return (account or {}).get("name") or profile_id[:64]


@app.middleware("http")
async def pin_creator_profile(request: Request, call_next):
    """
    Resolves the active creator profile once, at the start of each request.

    Every connection the request opens then goes to the same profile's
    database, even if the creator switches profile while it is running. A
    switch takes effect from the next request.

    A write from a window that still shows another profile is refused. The
    active profile is one value for the whole studio, so a second window left
    on profile A went on saving into profile B after another window switched,
    while still showing A and reporting SAVED: one client's confidential draft
    landed in another client's profile. The interface names the profile it
    loaded with in X-Inox-Profile; a write naming one that is no longer active
    is a 409 the window shows, and changes nothing. Reads still answer, and
    each answer names the active profile, which is how the window notices.
    The profile routes themselves are exempt: switching from a stale window is
    the creator's explicit choice, and it reloads that window.
    """
    active = paths_module.get_active_profile_id()
    trusted = _is_trusted_api_request(request)
    shown = request.headers.get(PROFILE_HEADER)
    path = request.scope.get("path", "")
    if (
        trusted
        and shown
        and shown != active
        and request.method not in ("GET", "HEAD", "OPTIONS")
        and not path.startswith("/api/v1/accounts")
    ):
        response = JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "code": "profile_changed",
                    "message": (
                        f"This window still shows {_profile_name(shown)}, but the studio has "
                        f"switched to {_profile_name(active)} in another window. Nothing was "
                        "changed. Copy anything you have not saved, then reload this window."
                    ),
                }
            },
        )
    else:
        with paths_module.using_profile(active):
            response = await call_next(request)
    if trusted:
        response.headers[PROFILE_HEADER] = active
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
    # No default: an audience nobody gave is not told to the model (F2-N2).
    target_audience: Optional[str] = None
    post_format: Optional[str] = "framework_breakdown"
    attached_media_type: Optional[str] = None


class CarouselRequest(BaseModel):
    slides: List[Dict[str, str]]
    theme: Optional[str] = "dark_slate"
    author_name: Optional[str] = None
    author_title: Optional[str] = None


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
# (Modularized into studio/backend/routers/analytics.py)
# -------------------------------------------------------------
try:
    from .routers import analytics as analytics_router_module
except (ImportError, ValueError):
    from routers import analytics as analytics_router_module

app.include_router(analytics_router_module.router)

get_range_days = analytics_router_module.get_range_days
get_kpis = analytics_router_module.get_kpis
get_analytics_overview = analytics_router_module.get_analytics_overview
get_demographics = analytics_router_module.get_demographics
export_analytics = analytics_router_module.export_analytics
get_posts_leaderboard = analytics_router_module.get_posts_leaderboard
get_post_leads_attribution = analytics_router_module.get_post_leads_attribution


# -------------------------------------------------------------
# Module 2: Post Studio & Simulator Endpoints
# (Modularized into studio/backend/routers/posts.py)
# -------------------------------------------------------------
try:
    from .routers import posts as posts_router_module
except (ImportError, ValueError):
    from routers import posts as posts_router_module

app.include_router(posts_router_module.router)

list_posts = posts_router_module.list_posts
create_post = posts_router_module.create_post
update_post = posts_router_module.update_post
reschedule_post = posts_router_module.reschedule_post
delete_post = posts_router_module.delete_post


@app.post("/api/posts/{post_id}/publish-now", tags=["LinkedIn Native Scheduler"])
def publish_post_now(post_id: str):
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

        event_bus.publish_sync("post_published", {
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


# -------------------------------------------------------------
# Module 3: Media Studio & Unified Drag-and-Drop Dropzone
# -------------------------------------------------------------
# The largest file each kind of upload accepts. Documents and video match what
# LinkedIn itself takes (100 MB per document, 5 GB per video); images are
# capped well above what a post image needs. There was no limit at all, and
# the whole file was read into memory, so a large video could take the studio
# down mid-session.
MEDIA_UPLOAD_CAPS = {
    "image": 50 * 1024 * 1024,
    "carousel": 100 * 1024 * 1024,
    "video": 5 * 1024 * 1024 * 1024,
}
MEDIA_UPLOAD_CHUNK = 1024 * 1024


def _readable_size(size: int) -> str:
    for unit, step in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if size >= step:
            return f"{size / step:.0f} {unit}" if size % step == 0 else f"{size / step:.1f} {unit}"
    return f"{size} bytes"


@app.post("/api/media/upload", tags=["Media Studio & Dropzone"])
def upload_media_file(file: UploadFile = File(...)):
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

    cap = MEDIA_UPLOAD_CAPS[media_type]
    too_big = HTTPException(
        status_code=413,
        detail=f"That file is larger than the {_readable_size(cap)} the studio accepts for a {media_type}.",
    )
    declared = getattr(file, "size", None)
    if isinstance(declared, int) and declared > cap:
        raise too_big

    # The signature checks below need only the start of the file; the rest is
    # copied to disk in chunks, so memory stays bounded whatever the size.
    # A plain function, so this runs on the thread pool: the disk and database
    # work below no longer holds up every other request while it waits.
    content = file.file.read(64 * 1024)
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

    try:
        with open(file_path, "wb") as f:
            f.write(content)
            while True:
                chunk = file.file.read(MEDIA_UPLOAD_CHUNK)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > cap:
                    raise too_big
                f.write(chunk)
    except BaseException:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise
    if size_bytes > cap:
        os.remove(file_path)
        raise too_big

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
    # None means "the creator's own": see _creator_byline. This defaulted to one
    # particular author's title, which every new user then saw on their slides.
    author_title: Optional[str] = None

    @field_validator("slides")
    @classmethod
    def validate_slides_list(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not v or len(v) < 1:
            raise ValueError("Carousel requires at least 1 slide")
        if len(v) > 50:
            raise ValueError("Carousel cannot exceed 50 slides")
        return v


def _creator_byline() -> tuple:
    """
    The name and title a slide is signed with when the request names neither.

    Brand Studio's saved profile first, then the confirmed LinkedIn profile,
    then nothing. Nothing is a blank byline, which is honest; a stranger's
    title is not.
    """
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'creator_profile'").fetchone()
        saved = json.loads(row["value"]) if row and row["value"] else {}
        name, title = (saved.get("name") or "").strip(), (saved.get("headline") or "").strip()
        if not (name and title):
            try:
                me = conn.execute(
                    "SELECT display_name, headline FROM creator_identity WHERE id = 1 AND confirmed_at IS NOT NULL"
                ).fetchone()
            except sqlite3.OperationalError:
                me = None
            if me:
                name = name or (me["display_name"] or "")
                title = title or (me["headline"] or "")
        return name, title
    except (ValueError, TypeError):
        return "", ""
    finally:
        conn.close()


@app.post("/api/v1/carousel/deck/generate", tags=["Media Studio & Dropzone"])
def generate_vector_carousel_deck(req: CarouselDeckRequest):
    """
    Day 13: Compiles structured slide cards into 4:5 vertical (1080x1350)
    or 1:1 square vector SVG slides with Swiss typography.
    """
    own_name, own_title = _creator_byline()
    res = carousel_engine.compile_carousel_deck(
        slides=req.slides,
        theme=req.theme or "dark_obsidian",
        aspect_ratio=req.aspect_ratio or "4:5",
        author_name=req.author_name or own_name,
        author_title=req.author_title if req.author_title is not None else own_title,
    )
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to compile carousel deck"))
    return res


get_10x_hooks = posts_router_module.get_10x_hooks
audit_algorithm = posts_router_module.audit_algorithm
repurpose = posts_router_module.repurpose


# -------------------------------------------------------------
# Module 5: Agno AgentOS Content Copilot & Bring-Your-Own-AI
# -------------------------------------------------------------
try:
    from .routers import ai as ai_router_module
except ImportError:
    from routers import ai as ai_router_module

app.include_router(ai_router_module.router)
ai_status = ai_router_module.ai_status
get_ai_config_endpoint = ai_router_module.get_ai_config_endpoint
configure_ai_endpoint = ai_router_module.configure_ai_endpoint
save_ai_settings = ai_router_module.save_ai_settings
execute_ai_command = ai_router_module.execute_ai_command
copilot_optimize = ai_router_module.copilot_optimize
analyze_swipe_pattern = ai_router_module.analyze_swipe_pattern
stream_ai_completion = ai_router_module.stream_ai_completion


format_bold = posts_router_module.format_bold
format_italic = posts_router_module.format_italic
format_mono = posts_router_module.format_mono
format_strike = posts_router_module.format_strike
format_clean = posts_router_module.format_clean
format_analyze = posts_router_module.format_analyze
format_serif_bold = posts_router_module.format_serif_bold
format_serif_italic = posts_router_module.format_serif_italic
format_blackboard = posts_router_module.format_blackboard
format_underline = posts_router_module.format_underline
format_circled_numbers = posts_router_module.format_circled_numbers
format_dwell = posts_router_module.format_dwell


# -------------------------------------------------------------
# Taplio Pro ($199/mo) Feature 5: Lead Database & Relationship CRM
# (Modularized into studio/backend/routers/crm.py)
# -------------------------------------------------------------
try:
    from .routers import crm as crm_router_module
except (ImportError, ValueError):
    from routers import crm as crm_router_module

app.include_router(crm_router_module.router)

get_leads = crm_router_module.get_leads
export_leads_csv_route = crm_router_module.export_leads_csv_route
create_lead = crm_router_module.create_lead
create_leads_batch = crm_router_module.create_leads_batch
update_lead = crm_router_module.update_lead
remove_lead = crm_router_module.remove_lead
get_lead_dm = crm_router_module.get_lead_dm
enrich_lead_endpoint = crm_router_module.enrich_lead_endpoint
get_lead_enrichment_endpoint = crm_router_module.get_lead_enrichment_endpoint
_ENRICHMENT_RETIRED = crm_router_module._ENRICHMENT_RETIRED


# -------------------------------------------------------------
# Module: Onboarding, the creator's own identity and history
# -------------------------------------------------------------
# The extension reaches the POST routes through its service worker relay, and
# the onboarding screen reads the state. Every write goes through onboarding.py,
# which refuses anything that is not the confirmed creator's. A refusal is a 409
# with the reason, because the extension logs it and the screen may show it.

class BridgeHeartbeat(BaseModel):
    extension_version: Optional[str] = None
    page_kind: Optional[str] = None


class IdentityConfirm(BaseModel):
    vanity: str


class OwnPostsIngest(BaseModel):
    author: str
    posts: List[Dict[str, Any]]


class OutboundIngest(BaseModel):
    actor: str
    items: List[Dict[str, Any]]


class ImportRequest(BaseModel):
    kind: str


class ImportEvent(BaseModel):
    id: int
    event: str
    items_seen: Optional[int] = None
    outcome: Optional[str] = None


def _refusal(error: "onboarding.RefusedCapture"):
    raise HTTPException(status_code=409, detail=str(error))


try:
    from .routers import insights as insights_router_module
except (ImportError, ValueError):
    from routers import insights as insights_router_module

app.include_router(insights_router_module.router)

get_posts_insights = insights_router_module.get_posts_insights
get_patterns_insights = insights_router_module.get_patterns_insights
get_cadence_insights = insights_router_module.get_cadence_insights
get_outbound_insights = insights_router_module.get_outbound_insights
get_contrast_insights = insights_router_module.get_contrast_insights
get_attribution_insights = insights_router_module.get_attribution_insights
get_evidence_brief = insights_router_module.get_evidence_brief


@app.get("/api/v1/today", tags=["Onboarding"])
def get_today():
    """What to do in the next hour. See today.py."""
    return today_module.today_brief()


@app.post("/api/v1/today/demo-cleanup-notice/dismiss", tags=["Onboarding"])
def dismiss_demo_cleanup_notice():
    """Hides Today's note on removed demo content; the record of it is kept."""
    return today_module.dismiss_demo_cleanup()


@app.get("/api/v1/onboarding/state", tags=["Onboarding"])
def get_onboarding_state():
    return onboarding.onboarding_state()


@app.post("/api/v1/bridge/heartbeat", tags=["Onboarding"])
def post_bridge_heartbeat(payload: BridgeHeartbeat):
    return onboarding.record_heartbeat(payload.extension_version, payload.page_kind)


@app.post("/api/v1/bridge/capture", tags=["Onboarding"])
def post_bridge_capture(payload: Dict[str, Any]):
    """One extractor run, as the extension saw it. See onboarding.record_capture."""
    try:
        return onboarding.record_capture(payload)
    except onboarding.RefusedCapture as error:
        _refusal(error)


@app.post("/api/v1/bridge/voyager-ingest", tags=["Onboarding"])
def post_bridge_voyager_ingest(payload: Dict[str, Any]):
    """Ingests structured data captured via Voyager API network interception."""
    try:
        return onboarding.record_voyager_ingest(payload)
    except onboarding.RefusedCapture as error:
        _refusal(error)


@app.post("/api/v1/bridge/schema-drift", tags=["Onboarding"])
def post_bridge_schema_drift(payload: Dict[str, Any]):
    """Records Voyager API schema drift events when response shapes change."""
    try:
        return onboarding.record_schema_drift(payload)
    except onboarding.RefusedCapture as error:
        _refusal(error)


@app.get("/api/v1/extension/health", tags=["Onboarding"])
def get_extension_health():
    """Returns aggregated health status of the Chrome extension and Voyager interception."""
    return onboarding.extension_health()


@app.post("/api/v1/identity/observe", tags=["Onboarding"])
def post_identity_observe(payload: Dict[str, Any]):
    try:
        return onboarding.observe_profile(payload)
    except onboarding.RefusedCapture as error:
        _refusal(error)


@app.post("/api/v1/identity/me", tags=["Onboarding"])
def post_identity_me():
    """
    The confirmed vanity, or null. POST only so the extension's relay, which
    forwards a fixed allowlist of paths, can reach it without a query string.
    The extension uses it to recognise the creator's own pages, and to send a
    profile only when that profile could be the creator's.
    """
    return {"status": "success", "vanity": onboarding.confirmed_vanity() or None}


@app.post("/api/v1/identity/confirm", tags=["Onboarding"])
def post_identity_confirm(payload: IdentityConfirm):
    try:
        return onboarding.confirm_identity(payload.vanity)
    except onboarding.RefusedCapture as error:
        _refusal(error)


@app.post("/api/v1/identity/reject", tags=["Onboarding"])
def post_identity_reject():
    return onboarding.reject_candidate()


@app.delete("/api/v1/identity", tags=["Onboarding"])
def delete_identity():
    return onboarding.forget_identity()


@app.post("/api/v1/self/posts/ingest", tags=["Onboarding"])
def post_own_posts(payload: OwnPostsIngest):
    try:
        return onboarding.ingest_own_posts(payload.author, payload.posts)
    except onboarding.RefusedCapture as error:
        _refusal(error)


class PostAnalyticsIngest(BaseModel):
    author: str
    activity_urn: str
    metrics: Dict[str, Any]


@app.post("/api/v1/self/posts/analytics", tags=["Onboarding"])
def post_own_post_analytics(payload: PostAnalyticsIngest):
    try:
        return onboarding.ingest_post_analytics(payload.author, payload.activity_urn, payload.metrics)
    except onboarding.RefusedCapture as error:
        _refusal(error)


@app.post("/api/v1/self/outbound/ingest", tags=["Onboarding"])
def post_outbound(payload: OutboundIngest):
    try:
        return onboarding.ingest_outbound(payload.actor, payload.items)
    except onboarding.RefusedCapture as error:
        _refusal(error)


@app.post("/api/v1/self/imports", tags=["Onboarding"])
def post_import_request(payload: ImportRequest):
    try:
        return onboarding.request_import(payload.kind)
    except onboarding.RefusedCapture as error:
        _refusal(error)


@app.post("/api/v1/self/imports/pending", tags=["Onboarding"])
def get_pending_import(payload: ImportRequest):
    kind = payload.kind
    return {"status": "success", "request": onboarding.pending_import(kind),
            "vanity": onboarding.confirmed_vanity() or None}


@app.post("/api/v1/self/imports/event", tags=["Onboarding"])
def post_import_event(payload: ImportEvent):
    try:
        return onboarding.update_import(payload.id, payload.event, payload.items_seen, payload.outcome)
    except onboarding.RefusedCapture as error:
        _refusal(error)


# -------------------------------------------------------------
# Module: Browser Bridge & Extension Launcher
# (Modularized into studio/backend/routers/browser.py)
# -------------------------------------------------------------
try:
    from .routers import browser as browser_router_module
except (ImportError, ValueError):
    from routers import browser as browser_router_module

app.include_router(browser_router_module.router)

get_browser_status_endpoint = browser_router_module.get_browser_status_endpoint
create_browser_shortcuts_endpoint = browser_router_module.create_browser_shortcuts_endpoint
launch_browser_endpoint = browser_router_module.launch_browser_endpoint
copy_browser_path_endpoint = browser_router_module.copy_browser_path_endpoint
sync_all_activity = browser_router_module.sync_all_activity
get_activity_stream = browser_router_module.get_activity_stream



# -------------------------------------------------------------
# Module 3: Smart Queue & Slots
# -------------------------------------------------------------
try:
    from .routers import queue as queue_router_module
except ImportError:
    from routers import queue as queue_router_module

app.include_router(queue_router_module.router)
CadenceValidationPayload = queue_router_module.CadenceValidationPayload
QueuePausePayload = queue_router_module.QueuePausePayload
get_smart_slots = queue_router_module.get_smart_slots
get_next_smart_slot = queue_router_module.get_next_smart_slot
get_cadence_health = queue_router_module.get_cadence_health
validate_queue_cadence = queue_router_module.validate_queue_cadence
trigger_scheduler_dispatch = queue_router_module.trigger_scheduler_dispatch
get_queue_status = queue_router_module.get_queue_status
toggle_queue_pause = queue_router_module.toggle_queue_pause



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


@app.delete("/api/auth/cookies")
def delete_cookies():
    linkedin_client.clear_tokens()
    return {"status": "success", "message": "The stored LinkedIn session is deleted."}


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


ingest_live_analytics = analytics_router_module.ingest_live_analytics
get_telemetry_shard_status = analytics_router_module.get_telemetry_shard_status
flush_telemetry_shard = analytics_router_module.flush_telemetry_shard


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
# Enterprise Documentation Suite & Universal Search API
# (Modularized into studio/backend/routers/search.py)
# -------------------------------------------------------------
try:
    from .routers import search as search_router_module
except (ImportError, ValueError):
    from routers import search as search_router_module

app.include_router(search_router_module.router)

DOCS_DIR = search_router_module.DOCS_DIR
MODULES_DIR = search_router_module.MODULES_DIR
DOCS_MODULES = search_router_module.DOCS_MODULES
_docs_catalogue = search_router_module._docs_catalogue
list_docs_modules = search_router_module.list_docs_modules
search_documentation = search_router_module.search_documentation
search_everything = search_router_module.search_everything
get_doc_module = search_router_module.get_doc_module

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

def _active_provider():
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
        config = get_current_ai_config()
        return (
            getattr(config, "provider", "") or "",
            getattr(config, "base_url", "") or "",
        )
    except Exception:
        return "", ""


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
        "egress": mcp_client.egress_report(*_active_provider()),
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
    provider, base_url = _active_provider()
    gathered = mcp_client.gather(provider=provider, base_url=base_url)
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
    # from_telegram=False, because this request is not from Telegram. It came
    # through the local API, which already required a loopback Host, an allowed
    # Origin and the session cookie, so the caller is someone at this machine's
    # keyboard. The Telegram chat id whitelist answers a different question and
    # must not be the thing standing between the creator and their own tray.
    result = ingress_daemon.process_incoming_update(update_payload, from_telegram=False)
    if not result:
        return {"status": "skipped", "message": "Message was empty or carried no usable text."}
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


class StagePostRequest(BaseModel):
    scheduled_at: str
    confirm: bool = False
    # Sends again after an earlier send got no answer, once the creator has
    # checked LinkedIn and the post is not there.
    confirm_resend: bool = False


# A send LinkedIn never answered, per post: the time it went out.
UNANSWERED_SEND_KEY = "linkedin_send_unanswered:"


def _unanswered_send(post_id: str) -> Optional[str]:
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (UNANSWERED_SEND_KEY + post_id,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def _record_unanswered_send(post_id: str) -> None:
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
            (UNANSWERED_SEND_KEY + post_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _send_refusal_text(result: Dict[str, Any]) -> str:
    """Why a send to LinkedIn did not happen, in one sentence the creator can act on."""
    message = result.get("message")
    if isinstance(message, str) and message.strip():
        return message
    status = result.get("http_status")
    if status:
        # LinkedIn's own body is often a page of HTML, which is not a reason.
        return f"LinkedIn refused the post (HTTP {status}). Nothing was scheduled."
    error = str(result.get("error") or "").strip()
    if error:
        return f"The studio could not reach LinkedIn ({error[:200]}). Nothing was scheduled."
    return "LinkedIn did not accept the post. Nothing was scheduled."


@app.post("/api/v1/posts/{post_id}/stage-to-linkedin", tags=["LinkedIn Native Scheduler"])
def stage_post_to_linkedin(post_id: str, req: StagePostRequest):
    """
    Hands a stored post to LinkedIn's own scheduler, for real.

    This is the one route in this product that reaches LinkedIn on the
    creator's behalf, and everything about its shape follows from that.

    It schedules rather than posts. The Voyager payload carries
    lifecycleState SCHEDULED and a scheduledAt, so LinkedIn holds the post and
    publishes it at the given time. That is the point: it solves the sleeping
    laptop, which a local scheduler cannot.

    `confirm` must be true. A missing confirmation is a 400 rather than a
    default, because the request is not reversible from here: once LinkedIn has
    it, cancelling means going to LinkedIn. An interface that can fire this by
    accident is the wrong interface.

    The content is read from the record rather than accepted from the caller.
    The creator approved what is in the row; a body that carried its own text
    could post something they never saw.

    Three refusals are possible and all three are returned rather than
    swallowed. No saved session means nothing to authenticate with. The egress
    guard refuses the `linkedin` category by default, so this returns the
    refusal naming INOX_ALLOW_LINKEDIN_EGRESS unless the creator has opted in.
    And the circuit breaker refuses after repeated 401 or 403, which on this
    endpoint means LinkedIn has noticed.
    """
    if not req.confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                "This sends the post to LinkedIn and cannot be undone from here. "
                "Set confirm to true to proceed."
            ),
        )

    scheduled = normalize_datetime_to_utc_iso(req.scheduled_at)
    if not scheduled:
        raise HTTPException(status_code=400, detail="Invalid scheduled_at timestamp.")

    parsed = parse_datetime_flexible(scheduled)
    if parsed is None:
        raise HTTPException(status_code=400, detail="Invalid scheduled_at timestamp.")
    if parsed <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail="LinkedIn will not hold a post for a time that has passed.",
        )

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, content, status FROM posts WHERE id = ?", (post_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found")
        if row["status"] == "published":
            raise HTTPException(status_code=400, detail="Post is already published")
        content = row["content"] or ""
    finally:
        conn.close()

    if not content.strip():
        raise HTTPException(status_code=400, detail="This post has no content to send.")

    # An earlier send that LinkedIn never answered may have scheduled the post
    # already, so a second one waits until the creator has looked.
    unanswered = _unanswered_send(post_id)
    if unanswered and not req.confirm_resend:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "send_unconfirmed",
                "message": (
                    f"An earlier send of this post ({unanswered[:16].replace('T', ' ')} UTC) got no "
                    "answer from LinkedIn, so LinkedIn may already be holding it. Check your "
                    "scheduled posts on LinkedIn. Send again only if it is not there."
                ),
            },
        )

    result = linkedin_client.schedule_norm_share(
        content=content,
        scheduled_at_ms=int(parsed.timestamp() * 1000),
    )

    if result.get("status") == "unknown":
        _record_unanswered_send(post_id)
        raise HTTPException(
            status_code=504,
            detail={"code": "send_unknown", "message": _send_refusal_text(result)},
        )

    if result.get("status") != "success":
        # A 502 whose detail is a sentence. The refusal text names the flag or
        # the breaker, and rewording it here would lose the one thing the
        # creator needs in order to act, so it is passed through as written.
        # The detail used to be the whole result dict, which the interface
        # could not read, so the creator saw "502" and nothing else.
        raise HTTPException(status_code=502, detail=_send_refusal_text(result))

    # A mock result is not a send, and must never be reported as one.
    #
    # schedule_norm_share has a fast path that returns status "success" with
    # mode "mock" when there is no saved li_at, which is the default state of a
    # fresh install. The first version of this route checked only the status,
    # so a creator with no session was told "LinkedIn is holding this post" and
    # the row moved to scheduled while nothing left the machine. That is the
    # precise failure this product has spent its history removing, reintroduced
    # by the route added to fix a different one. Caught by its own test.
    #
    # The mock path is useful to the suite and to an air-gapped run. It is not
    # an acceptable answer to someone who pressed a button that says it sends.
    if result.get("mode") == "mock":
        raise HTTPException(
            status_code=409,
            detail=(
                "Nothing was sent. This studio has no saved LinkedIn session, so "
                "the scheduler ran in mock mode. Open the Studio Bridge extension "
                "in your LinkedIn browser, press Sync LinkedIn Session, then try "
                "again. The session is kept only for sending to LinkedIn, and "
                "Setup can delete it."
            ),
        )

    # Recorded only after LinkedIn accepted it. Writing the row first would
    # leave a post marked as handed over when it was not, which is the failure
    # this product keeps finding in its own history.
    conn = get_db()
    try:
        conn.execute(
            "UPDATE posts SET status = 'scheduled', scheduled_for = ? WHERE id = ?",
            (scheduled, post_id),
        )
        conn.execute("DELETE FROM settings WHERE key = ?", (UNANSWERED_SEND_KEY + post_id,))
        # LinkedIn holds it, so at its time the queue records it as published
        # rather than as due for the creator to post again.
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
            (LINKEDIN_HOLDS_KEY + post_id, result.get("scheduled_urn") or "held"),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "success",
        "mode": result.get("mode", "live"),
        "scheduled_urn": result.get("scheduled_urn", ""),
        "scheduled_for": scheduled,
        "message": (
            "LinkedIn is holding this post and will publish it at the scheduled time."
        ),
    }


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
# (Modularized into studio/backend/routers/crm.py)
# -------------------------------------------------------------
IngestInteractionRequest = crm_router_module.IngestInteractionRequest
ingest_crm_interaction = crm_router_module.ingest_crm_interaction
get_high_value_leads = crm_router_module.get_high_value_leads
get_crm_telemetry = crm_router_module.get_crm_telemetry
GenerateDMRequest = crm_router_module.GenerateDMRequest
generate_lead_dm = crm_router_module.generate_lead_dm
generate_anti_slop_dm_variants = crm_router_module.generate_anti_slop_dm_variants
ScorePreviewRequest = crm_router_module.ScorePreviewRequest
preview_icp_score = crm_router_module.preview_icp_score
purge_crm_lead = crm_router_module.purge_crm_lead
ArchiveInactiveRequest = crm_router_module.ArchiveInactiveRequest
archive_inactive_crm_leads = crm_router_module.archive_inactive_crm_leads
get_lead_interaction_timeline = crm_router_module.get_lead_interaction_timeline
LeadRemoval = crm_router_module.LeadRemoval
get_lead_review = crm_router_module.get_lead_review
post_lead_review_remove = crm_router_module.post_lead_review_remove


# -------------------------------------------------------------
# Post Identity: binding what the creator wrote to what LinkedIn published
# (Modularized into studio/backend/routers/posts.py)
# -------------------------------------------------------------
InjectedPostRequest = posts_router_module.InjectedPostRequest
record_injected_post = posts_router_module.record_injected_post
BindUrnRequest = posts_router_module.BindUrnRequest
bind_post_urn = posts_router_module.bind_post_urn
get_post_engagers = posts_router_module.get_post_engagers


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
    """
    The backups folder: full backups first, then pre-upgrade database copies,
    then anything else, each newest first.

    This was reverse file name order, so the automatic pre-upgrade copies
    always came first and the five the interface shows were rarely the newest,
    or ones the creator had made.
    """
    directory = get_backups_dir()
    entries = []
    for name in os.listdir(directory):
        full = os.path.join(directory, name)
        if not os.path.isfile(full):
            continue
        # One damaged file (a malformed manifest, a cut-short ZIP) must not
        # take the whole list down with it: it is listed as unreadable.
        try:
            info = support_tools.inspect_backup(full)
            kind = info.get("kind") if info.get("has_database") else "other"
        except Exception:
            kind = "unreadable"
        entries.append({"name": name, "bytes": os.path.getsize(full),
                        "modified": datetime.fromtimestamp(os.path.getmtime(full)).isoformat(),
                        "kind": kind, "restorable": kind in ("backup", "database"),
                        "_mtime": os.path.getmtime(full)})
    order = {"backup": 0, "database": 1}
    entries.sort(key=lambda entry: (order.get(entry["kind"], 2), -entry["_mtime"]))
    for entry in entries:
        del entry["_mtime"]
    return {"directory": directory, "count": len(entries), "backups": entries}


@app.post("/api/v1/support/export", tags=["Support & Maintenance"])
def export_user_data(payload: Optional[Dict[str, Any]] = None):
    fmt = (payload or {}).get("format", "json")
    if fmt not in support_tools.EXPORT_FORMATS:
        raise HTTPException(status_code=400, detail="format must be json, csv or obsidian")
    # No destination from the request: the folder is always under the app
    # home, so a request can never point the export at a vault of the user's.
    note = "Content only. Credentials are deliberately excluded."
    if fmt == "obsidian":
        # The profile's one vault, refreshed in place, so the vault the creator
        # opened in Obsidian sees fresh data. Every press used to write a new
        # timestamped folder, and the refresh existed only in the CLI.
        try:
            from .obsidian_export import export_obsidian_vault
        except ImportError:
            from obsidian_export import export_obsidian_vault
        try:
            vault = export_obsidian_vault()
        except ValueError as refused:
            raise HTTPException(status_code=409, detail=str(refused))
        said = [f"{vault['notes']} notes. Open it in Obsidian with \"Open folder as vault\"; "
                "export again to refresh this same vault."]
        if vault["kept_your_notes"]:
            said.append(f"Kept what you wrote in {vault['kept_your_notes']} of them.")
        if vault["kept_edited"]:
            said.append(f"Left {len(vault['kept_edited'])} you edited as they are, with fresh copies beside them.")
        moved = [m for m in vault["renamed"] if m["wanted"] not in vault["kept_edited"]]
        if moved:
            said.append(f"Wrote {len(moved)} under another name, because a note of yours has the name.")
        return {"status": "success", "path": vault["path"], "format": fmt, "note": " ".join(said + [note])}
    path = support_tools.export_data(fmt=fmt)
    return {"status": "success", "path": path, "format": fmt, "note": note}


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
# Module 17: Multi-Tenant Creator Accounts & Profile Switching
# -------------------------------------------------------------
class CreateAccountPayload(BaseModel):
    name: str = Field(..., max_length=120, description="Creator or company profile name")
    headline: Optional[str] = Field("", max_length=300, description="Professional headline or title")
    vanity: Optional[str] = Field("", max_length=100, description="LinkedIn vanity handle")
    id: Optional[str] = Field(None, max_length=40, description="Optional custom account slug")


class SwitchAccountPayload(BaseModel):
    account_id: str = Field(..., min_length=1, max_length=60, description="Target account identifier")


@app.get("/api/v1/accounts", tags=["Multi-Tenancy & Profiles"])
def get_accounts():
    """
    Returns all registered creator profile accounts, active account, and metrics.
    """
    return accounts.list_accounts()


@app.post("/api/v1/accounts", tags=["Multi-Tenancy & Profiles"])
def post_create_account(payload: CreateAccountPayload):
    """
    Registers a new creator profile account in the local studio.
    """
    res = accounts.create_account(payload.model_dump())
    if res.get("status") == "error":
        # 402 when the licence is what stands in the way, so the interface can
        # say so rather than show a generic failure.
        status = 402 if res.get("code") == "licence" else 400
        raise HTTPException(status_code=status, detail=res.get("message", "Could not create account"))
    return res


@app.post("/api/v1/accounts/switch", tags=["Multi-Tenancy & Profiles"])
def post_switch_account(payload: SwitchAccountPayload):
    """
    Switches the active studio creator profile to the target account.
    """
    res = accounts.switch_account(payload.account_id)
    if res.get("status") == "error":
        # 402 when the licence no longer covers the profile, 409 when a newer
        # build wrote its database, so the switcher can say why rather than
        # claim it does not exist or show a bare server error.
        status = {"licence": 402, "schema": 409}.get(res.get("code"), 404)
        raise HTTPException(status_code=status, detail=res.get("message", "Account not found"))
    return res


class DeleteAccountPayload(BaseModel):
    confirm: str = Field("", max_length=160, description="The profile's name or ID, repeated")


@app.delete("/api/v1/accounts/{account_id}", tags=["Multi-Tenancy & Profiles"])
def delete_creator_account(account_id: str, payload: Optional[DeleteAccountPayload] = None):
    """
    Deletes a secondary creator profile and every file it holds. The default
    profile cannot be deleted, and the caller must repeat the profile's name.
    """
    res = accounts.delete_account(account_id, confirm=payload.confirm if payload else "")
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Cannot delete account"))
    return res


class LicencePayload(BaseModel):
    key: str = Field(..., min_length=1, max_length=4000, description="The licence key, as issued")


class ArchiveSourcePayload(BaseModel):
    source: str = Field(..., min_length=1, max_length=2000, description="upload:<token> or downloads:<path>")


class ArchiveImportPayload(ArchiveSourcePayload):
    include: Optional[List[str]] = Field(None, description="Kinds to import; the defaults when omitted")
    confirm_owner: bool = Field(False, description="The creator says the archive is theirs, whoever it names")


def _archive_call(work):
    try:
        return work()
    except (archive_import.OwnerUnconfirmed, archive_import.ArchiveBusy) as error:
        raise HTTPException(status_code=409, detail=str(error))
    except archive_import.ArchiveError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.get("/api/v1/archive", tags=["Onboarding"])
def get_archive_state():
    """
    When the LinkedIn archive was asked for, what is waiting in Downloads, and
    the last import. Called by the Setup step while it is open; nothing else
    makes the studio look in Downloads.
    """
    return archive_import.archive_state(look=True)


@app.post("/api/v1/archive/requested", tags=["Onboarding"])
def post_archive_requested():
    """The creator says they asked LinkedIn for their archive, so Downloads may be looked in."""
    return archive_import.mark_requested()


@app.post("/api/v1/archive/no-posts", tags=["Onboarding"])
def post_archive_no_posts():
    """The creator says their LinkedIn account has no posts, so the archive step is done without any."""
    return archive_import.mark_no_posts()


@app.post("/api/v1/archive/upload", tags=["Onboarding"])
async def post_archive_upload(request: Request):
    """
    Keeps an archive the creator chose by hand, and previews it. Nothing is imported.

    The file is the raw request body, streamed to disk with the size cap
    checked as it arrives. A multipart form would be spooled to the system's
    temporary folder in full before any check could run.
    """
    declared = request.headers.get("content-length") or ""
    if declared.isdigit() and int(declared) > archive_import.MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than any LinkedIn archive the studio expects.")
    writer = archive_import.UploadWriter(unquote(request.headers.get("x-archive-name") or "archive.zip"))
    try:
        async for chunk in request.stream():
            await run_in_threadpool(writer.write, chunk)
    except archive_import.ArchiveError as error:
        raise HTTPException(status_code=413, detail=str(error))
    except BaseException:
        writer.abort()
        raise
    source = writer.finish()

    def work():
        try:
            return archive_import.preview(source)
        except BaseException:
            archive_import.discard(source)
            raise
    return await run_in_threadpool(_archive_call, work)


@app.post("/api/v1/archive/discard", tags=["Onboarding"])
def post_archive_discard(payload: ArchiveSourcePayload):
    """Deletes the copy of an archive the creator chose by hand and then set aside."""
    return archive_import.discard(payload.source)


@app.post("/api/v1/archive/preview", tags=["Onboarding"])
def post_archive_preview(payload: ArchiveSourcePayload):
    """What an archive holds and what would be imported from it. Writes nothing."""
    return _archive_call(lambda: archive_import.preview(payload.source))


@app.post("/api/v1/archive/undo", tags=["Onboarding"])
def post_archive_undo():
    """Removes what the last archive import added: its posts, activity, profile fields and connections."""
    return _archive_call(archive_import.remove_last_import)


@app.post("/api/v1/archive/import", tags=["Onboarding"])
def post_archive_import(payload: ArchiveImportPayload):
    """
    Imports what the creator kept ticked from their own LinkedIn archive.

    409 when the archive names someone other than the confirmed creator, or
    no creator is confirmed yet, and the creator has not said it is theirs.
    """
    if not licensing.allows("archive_import"):
        raise HTTPException(status_code=402, detail="Importing the LinkedIn archive is part of the Creator licence.")
    return _archive_call(lambda: archive_import.import_archive(payload.source, payload.include,
                                                               confirm_owner=payload.confirm_owner))


@app.get("/api/v1/licence", tags=["Multi-Tenancy & Profiles"])
def get_licence():
    """The licence in effect, checked on this machine against the vendor's public key."""
    return licensing.current()


@app.post("/api/v1/licence", tags=["Multi-Tenancy & Profiles"])
def post_licence(payload: LicencePayload):
    res = licensing.install(payload.key)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res["message"])
    return res


@app.delete("/api/v1/licence", tags=["Multi-Tenancy & Profiles"])
def delete_licence():
    return licensing.remove()


# -------------------------------------------------------------
# Static Dashboard UI & Master Asset Mount
# -------------------------------------------------------------
FRONTEND_DIR = get_frontend_dir()
class _ProfileAssets:
    """
    Serves /assets from the active creator profile's media folder.

    A StaticFiles mount fixes its directory when the app starts, so after a
    profile switch it kept serving the first profile's uploads and generated
    images. One StaticFiles per folder, chosen per request, keeps each
    profile's media its own.
    """

    def __init__(self) -> None:
        self._apps: Dict[str, StaticFiles] = {}

    async def __call__(self, scope, receive, send):
        directory = get_assets_dir()
        served = self._apps.get(directory)
        if served is None:
            served = self._apps[directory] = StaticFiles(directory=directory)
        await served(scope, receive, send)


app.mount("/assets", _ProfileAssets(), name="assets")

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
