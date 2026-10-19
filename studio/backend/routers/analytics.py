"""
Analytics API Router
====================
Creator metrics, impressions, period deltas, demographics, CSV export,
post leaderboard with lead attribution, and telemetry shard diagnostics.
Zero cloud egress.
"""

import csv
import io
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Response

try:
    from ..database import get_db
    from ..crm import reverse_crm
    from ..linkedin_client import linkedin_client
except (ImportError, ValueError):
    from database import get_db
    from crm import reverse_crm
    from linkedin_client import linkedin_client

try:
    from studio.core.telemetry_shard import telemetry_engine, telemetry_buffer
except ImportError:
    try:
        from core.telemetry_shard import telemetry_engine, telemetry_buffer
    except ImportError:
        telemetry_engine = None
        telemetry_buffer = None

router = APIRouter()


def get_range_days(range_str: str) -> int:
    mapping = {"7d": 7, "14d": 14, "30d": 30, "90d": 90, "365d": 365, "all": 3650}
    return mapping.get(range_str.lower(), 30)


@router.get("/api/analytics/kpis")
def get_kpis(range: str = "30d"):
    days = get_range_days(range)
    conn = get_db()
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT MAX(date) FROM analytics_daily")
        max_d_row = cursor.fetchone()
        if not max_d_row or not max_d_row[0]:
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
                "scheduled_posts_count": scheduled_when_empty,
            }

        end_date = datetime.strptime(max_d_row[0], "%Y-%m-%d").date()
        start_cur = end_date - timedelta(days=days - 1)
        start_prev = start_cur - timedelta(days=days)
        end_prev = start_cur - timedelta(days=1)

        daily_only = "(period_label IN ('1d', 'day', 'daily') OR (period_label IS NULL AND source = 'seed'))"

        def window_totals(start, end):
            cursor.execute(f"""
            SELECT COUNT(*), SUM(impressions), SUM(reactions), SUM(comments), SUM(shares)
            FROM analytics_daily
            WHERE date >= ? AND date <= ? AND {daily_only}
            """, (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
            return cursor.fetchone()

        cur_days, cur_imp, cur_rxn, cur_comm, cur_shr = window_totals(start_cur, end_date)
        cur_imp = cur_imp or 0
        cur_eng = (cur_rxn or 0) + (cur_comm or 0) + (cur_shr or 0)
        cur_eng_rate = round((cur_eng / cur_imp * 100), 2) if cur_imp > 0 else None

        cursor.execute(f"""
        SELECT COUNT(*) FROM analytics_daily
        WHERE date >= ? AND date <= ? AND NOT {daily_only}
        """, (start_cur.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
        excluded_days = cursor.fetchone()[0]

        prev_days, prev_imp, prev_rxn, prev_comm, prev_shr = window_totals(start_prev, end_prev)
        prev_imp = prev_imp or 0
        prev_eng = (prev_rxn or 0) + (prev_comm or 0) + (prev_shr or 0)
        prev_eng_rate = round((prev_eng / prev_imp * 100), 2) if prev_imp > 0 else None

        def calc_delta(cur, prev):
            if not prev_days or prev == 0:
                return None
            return round(((cur - prev) / prev) * 100.0, 1)

        imp_delta = calc_delta(cur_imp, prev_imp)
        eng_delta = calc_delta(cur_eng, prev_eng)
        eng_rate_delta = (round(cur_eng_rate - prev_eng_rate, 2)
                          if cur_eng_rate is not None and prev_eng_rate is not None else None)

        cursor.execute("SELECT followers, profile_views FROM analytics_daily WHERE date = ?", (end_date.strftime("%Y-%m-%d"),))
        latest_stat = cursor.fetchone()
        cur_followers = latest_stat["followers"] if (latest_stat and latest_stat["followers"] is not None) else None
        cur_pviews = latest_stat["profile_views"] if (latest_stat and latest_stat["profile_views"] is not None) else None

        cursor.execute("SELECT followers, profile_views FROM analytics_daily WHERE date = ?", (start_cur.strftime("%Y-%m-%d"),))
        start_stat = cursor.fetchone()
        start_followers = start_stat["followers"] if (start_stat and start_stat["followers"] is not None) else None
        start_pviews = start_stat["profile_views"] if (start_stat and start_stat["profile_views"] is not None) else None

        follower_growth = (cur_followers - start_followers) if (cur_followers is not None and start_followers is not None) else None
        pviews_delta = (round(((cur_pviews - start_pviews) / start_pviews) * 100.0, 1)
                        if (cur_pviews is not None and start_pviews) else None)

        cursor.execute("SELECT COUNT(*) FROM posts WHERE status = 'scheduled'")
        scheduled_count = cursor.fetchone()[0]

        conn.close()

        if not cur_days:
            cur_imp = cur_eng = None

        return {
            "range": f"{days}d",
            "days_counted": cur_days,
            "days_excluded_unknown_window": excluded_days,
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


@router.get("/api/analytics/overview")
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


@router.get("/api/analytics/demographics")
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


@router.get("/api/analytics/export")
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


@router.get("/api/analytics/posts")
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


@router.get("/api/v1/analytics/posts/{post_id}/leads", tags=["Enterprise Reverse CRM", "Analytics"])
def get_post_leads_attribution(post_id: str, account_id: str = "default"):
    return reverse_crm.get_post_attribution(post_id, account_id=account_id)


@router.post("/api/analytics/ingest", tags=["Analytics"])
def ingest_live_analytics(payload: dict):
    # Analytics belong to one LinkedIn account. A reading was filed under
    # whichever creator profile was open, whoever was signed in to LinkedIn,
    # so an agency user's own figures landed in a client's profile as measured
    # fact. The bridge now names the signed-in account as `author`, and a
    # reading that names another account, or none, or reaches a profile that
    # has not confirmed who it is, is refused, as own posts already are.
    if payload.get("series") or (payload.get("data") or {}).get("series") or payload.get("profile_views") is not None:
        try:
            from .. import onboarding
        except (ImportError, ValueError):
            import onboarding
        me = onboarding.confirmed_vanity()
        author = onboarding.normalise_vanity(payload.get("author"))
        if not me:
            raise HTTPException(status_code=409, detail=(
                "confirm your profile in Setup first, so the studio knows whose analytics these are"))
        if not author:
            raise HTTPException(status_code=409, detail=(
                "the bridge could not tell which LinkedIn account is signed in. Open your own LinkedIn "
                "profile once in this browser, then reload the analytics page"))
        if author != me:
            raise HTTPException(status_code=409, detail=(
                f"these analytics are from linkedin.com/in/{author}, not from linkedin.com/in/{me}, "
                "the profile open in the studio"))
    if telemetry_buffer:
        try:
            event_type = payload.get("event_type") or ("feed_updates" if "posts" in payload or "feed_updates" in payload else "analytics_ingest")
            source = payload.get("source", "extension")
            telemetry_buffer.ingest(event_type=event_type, payload=payload, source=source)
        except Exception:
            pass

    result = linkedin_client.ingest_analytics_payload(payload)
    return result


@router.get("/api/v1/telemetry/status", tags=["Analytics"])
def get_telemetry_shard_status():
    if not telemetry_engine:
        return {"status": "unavailable", "message": "Telemetry shard not initialized"}
    status = telemetry_engine.get_status()
    if telemetry_buffer:
        status["pending_in_buffer"] = telemetry_buffer.pending_count()
    return status


@router.post("/api/v1/telemetry/flush", tags=["Analytics"])
def flush_telemetry_shard():
    if not telemetry_buffer:
        return {"flushed_events": 0, "flushed_dwells": 0}
    return telemetry_buffer.flush()
