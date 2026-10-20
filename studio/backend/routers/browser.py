"""
Browser Bridge and Extension Launcher API Router
================================================
Detects installed browsers, launches bridge instance with unpackaged extension,
manages desktop shortcuts, clipboard paths, and autonomous history sync. Zero cloud egress.
"""

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from ..text_cut import clip
except ImportError:  # pragma: no cover - direct script use
    from text_cut import clip

try:
    from ..browser_launcher import (
        detect_installed_browsers,
        get_extension_dir,
        create_desktop_shortcuts,
        launch_browser_with_extension,
        copy_extension_path_to_clipboard,
    )
    from .. import onboarding
    from ..database import get_db
except (ImportError, ValueError):
    from browser_launcher import (
        detect_installed_browsers,
        get_extension_dir,
        create_desktop_shortcuts,
        launch_browser_with_extension,
        copy_extension_path_to_clipboard,
    )
    import onboarding
    from database import get_db

router = APIRouter()


class BrowserLaunchPayload(BaseModel):
    browser_id: Optional[str] = "auto"
    url: Optional[str] = "https://www.linkedin.com/feed/"


@router.get("/api/v1/browser/status", tags=["Browser Bridge"])
def get_browser_status_endpoint():
    browsers = detect_installed_browsers()
    return {
        "status": "success",
        "browsers": browsers,
        "extension_path": get_extension_dir(),
        "total_detected": len(browsers),
    }


@router.post("/api/v1/browser/create-shortcuts", tags=["Browser Bridge"])
def create_browser_shortcuts_endpoint():
    shortcuts = create_desktop_shortcuts()
    return {
        "status": "success",
        "shortcuts": shortcuts,
        "total_created": len([s for s in shortcuts if s.get("status") == "created"]),
    }


@router.post("/api/v1/browser/launch", tags=["Browser Bridge"])
def launch_browser_endpoint(payload: Optional[Dict[str, Any]] = None):
    browser_id = "auto"
    url = "https://www.linkedin.com/feed/"
    if payload and isinstance(payload, dict):
        browser_id = payload.get("browser_id", "auto")
        url = payload.get("url", "https://www.linkedin.com/feed/")
    return launch_browser_with_extension(browser_id=browser_id, target_url=url)


@router.post("/api/v1/browser/copy-path", tags=["Browser Bridge"])
def copy_browser_path_endpoint():
    return copy_extension_path_to_clipboard()


@router.post("/api/v1/self/sync-all", tags=["Onboarding"])
def sync_all_activity(payload: Optional[Dict[str, Any]] = None):
    """
    Unified backend orchestrator that triggers and tracks live history ingestion
    across all three activity streams (posts, outbound comments, and reactions).
    Pushes heavy-lifting to the backend so the user has a single-click action.
    """
    vanity = onboarding.confirmed_vanity()
    if not vanity:
        raise HTTPException(
            status_code=400,
            detail="Creator identity is not confirmed yet. Confirm your profile on Setup first.",
        )

    # Check current counts from local SQLite store
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM own_posts")
        posts_row = cursor.fetchone()
        posts_count = posts_row[0] if posts_row else 0

        cursor.execute(
            "SELECT kind, COUNT(*) FROM outbound_engagements GROUP BY kind"
        )
        outbound_rows = dict(cursor.fetchall())
        comments_count = outbound_rows.get("comment", 0)
        reactions_count = outbound_rows.get("reaction", 0)
    finally:
        conn.close()

    sequence = None
    if payload and isinstance(payload, dict) and "sequence" in payload:
        sequence = payload["sequence"]

    # Start the sequential ingestion chain on backend
    try:
        chain_res = onboarding.start_sync_chain(sequence=sequence)
    except onboarding.RefusedCapture as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    target_url = chain_res["open_url"]
    first_kind = chain_res["current_kind"]

    # Launch or switch the browser tab to the first activity page via CDP
    launch_res = launch_browser_with_extension("auto", target_url=target_url)

    # What actually happened. This said "Autonomous activity sync started"
    # whatever the launcher reported: with no browser installed, with only
    # Chrome (which cannot load the bridge), and with the bridge not running.
    connected = bool(onboarding.bridge_status().get("connected"))
    name = launch_res.get("browser") or "the browser"
    order = ", then ".join(chain_res["sequence"])
    if launch_res.get("status") != "success" or launch_res.get("carries_extension") is False:
        reason = launch_res.get("message") or "The browser could not be opened."
        if not connected:
            onboarding.cancel_sync_chain(withdraw=True)
            raise HTTPException(status_code=409, detail=f"{reason} Nothing was imported.")
        message = (
            f"{name} cannot load the bridge. " if launch_res.get("status") == "success"
            else "No browser could be opened from here. "
        ) + (
            f"The bridge is running in another browser: open your {first_kind} activity page there and "
            f"the import starts ({order})."
        )
    else:
        message = f"Opened your {first_kind} activity page in {name}. "
        if connected:
            message += f"The bridge imports your {order}, one after another; keep that tab in view."
        else:
            message += (f"The import starts when the bridge reports in, within a minute, and goes on to "
                        f"your {order} one after another; keep that tab in view.")
        if launch_res.get("carries_extension") is None:
            message += f" Whether {name} loads the bridge has not been checked on this computer; if nothing starts, use Edge or Brave."

    return {
        "status": "success",
        "current_kind": first_kind,
        "target_url": target_url,
        "sequence": chain_res["sequence"],
        "counts": {
            "posts": posts_count,
            "comments": comments_count,
            "reactions": reactions_count,
        },
        "browser": launch_res.get("browser", "Browser Bridge"),
        "carries_extension": launch_res.get("carries_extension"),
        "bridge_connected": connected,
        "message": message,
    }


@router.get("/api/v1/self/activity-stream", tags=["Browser Bridge"])
def get_activity_stream(limit: int = 25):
    """
    Returns real-time inspection data of all activity streams and live ingestion records
    for the product dashboard and CLI monitors. Zero cloud egress.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()

        # Aggregate counts
        cursor.execute("SELECT COUNT(*) FROM own_posts")
        posts_count = (cursor.fetchone() or [0])[0]

        cursor.execute("SELECT kind, COUNT(*) FROM outbound_engagements GROUP BY kind")
        outbound_counts = dict(cursor.fetchall())
        comments_count = outbound_counts.get("comment", 0)
        reactions_count = outbound_counts.get("reaction", 0)

        cursor.execute("SELECT COUNT(*) FROM leads")
        leads_count = (cursor.fetchone() or [0])[0]

        # Recent own posts
        cursor.execute(
            """
            SELECT activity_urn, text, published_at, reactions, comments, reposts, impressions, last_seen_at
            FROM own_posts
            ORDER BY COALESCE(published_at, last_seen_at) DESC
            LIMIT ?
            """,
            (limit,),
        )
        recent_posts = [
            {
                "activity_urn": r[0],
                "excerpt": clip(r[1] or "", 200),
                "published_at": r[2],
                "reactions": r[3],
                "comments": r[4],
                "reposts": r[5],
                "impressions": r[6],
                "last_seen_at": r[7],
            }
            for r in cursor.fetchall()
        ]

        # Recent outbound comments
        cursor.execute(
            """
            SELECT target_author, my_text, target_excerpt, target_activity_urn, last_seen_at
            FROM outbound_engagements
            WHERE kind = 'comment'
            ORDER BY last_seen_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
        recent_comments = [
            {
                "target_author": r[0] or "Unknown",
                "my_text": clip(r[1] or "", 240),
                "target_excerpt": clip(r[2] or "", 160),
                "target_activity_urn": r[3],
                "last_seen_at": r[4],
            }
            for r in cursor.fetchall()
        ]

        # Recent reactions
        cursor.execute(
            """
            SELECT target_author, reaction_kind, target_excerpt, target_activity_urn, last_seen_at
            FROM outbound_engagements
            WHERE kind = 'reaction'
            ORDER BY last_seen_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
        recent_reactions = [
            {
                "target_author": r[0] or "Unknown",
                "reaction_kind": r[1] or "like",
                "target_excerpt": clip(r[2] or "", 160),
                "target_activity_urn": r[3],
                "last_seen_at": r[4],
            }
            for r in cursor.fetchall()
        ]

        # Recent leads, by when the bridge last captured a new engagement from
        # them. This was ORDER BY id, and a captured lead's id is a hash, so
        # the list was in no order and the people just captured could be
        # missing from it. Re-reading a comment does not move anyone up.
        cursor.execute(
            """
            SELECT l.id, l.name, l.headline, l.company, l.engagement_type, l.icp_score, l.status, l.created_at
            FROM leads l
            ORDER BY COALESCE(
                (SELECT MAX(COALESCE(i.first_seen_at, i.interacted_at)) FROM lead_interactions i WHERE i.lead_id = l.id),
                l.created_at) DESC, l.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        recent_leads = [
            {
                "id": r[0],
                "name": r[1] or "Unknown",
                "headline": r[2] or "",
                "company": r[3] or "",
                # As stored; not read is not "Commented".
                "engagement_type": r[4],
                "icp_score": r[5] or 0.0,
                "status": r[6] or "NEW",
                "created_at": r[7],
            }
            for r in cursor.fetchall()
        ]

        # Recent import requests
        cursor.execute(
            """
            SELECT id, kind, requested_at, started_at, finished_at, items_seen, outcome
            FROM self_import_requests
            ORDER BY id DESC
            LIMIT 10
            """
        )
        recent_imports = [
            {
                "id": r[0],
                "kind": r[1],
                "requested_at": r[2],
                "started_at": r[3],
                "finished_at": r[4],
                "items_seen": r[5],
                "outcome": r[6] or "pending",
            }
            for r in cursor.fetchall()
        ]
    finally:
        conn.close()

    bridge = onboarding.bridge_status()
    sync_chain = onboarding.get_active_sync_chain()

    return {
        "status": "success",
        "creator": onboarding.confirmed_vanity(),
        "summary": {
            "posts_count": posts_count,
            "comments_count": comments_count,
            "reactions_count": reactions_count,
            "leads_count": leads_count,
            "bridge_connected": bridge.get("connected", False),
            "bridge_last_seen": bridge.get("last_seen_at"),
            "bridge_carrier": bridge.get("carrier"),
            "active_sync_chain": sync_chain,
        },
        "recent_posts": recent_posts,
        "recent_comments": recent_comments,
        "recent_reactions": recent_reactions,
        "recent_leads": recent_leads,
        "recent_imports": recent_imports,
    }
