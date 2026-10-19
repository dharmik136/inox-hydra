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
import math
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

# A period is compared with the one before it only when each has at least this
# share of its days captured, and then by the level per captured day, not by
# the sum. The sums were compared whatever was captured: two weeks after
# install the previous 30 days held 4 captured days, and a flat 1,000
# impressions a day was reported as +650%.
MIN_CAPTURED_SHARE_TO_COMPARE = 0.8


def rounding_half_width(value, precision) -> float:
    """
    How far a stored figure can be from the true one, given how LinkedIn wrote it.

    A row marked 'rounded' holds at least one figure LinkedIn abbreviated,
    such as 1.2K stored as 1200, without saying which. An abbreviation only
    ever produces a multiple of 100 from 1,000 up, so any other value in that
    row was written out in full and is exact. For the rest, the last non-zero
    digit is the one LinkedIn rounded to: 1.2K is 1,150 to 1,249, 50 either
    way, and a bare 2K is taken as 500 either way, the wider of what it can
    mean.
    """
    if precision != "rounded" or value is None or value < 1000 or value % 100:
        return 0.0
    step = 100
    while value % (step * 10) == 0 and step * 10 <= value:
        step *= 10
    return step / 2.0


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
            """Days counted, impressions and engagements summed, and how far rounding can move each sum."""
            cursor.execute(f"""
            SELECT impressions, reactions, comments, shares, precision
            FROM analytics_daily
            WHERE date >= ? AND date <= ? AND {daily_only}
            """, (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
            rows = cursor.fetchall()
            imp = sum(r["impressions"] or 0 for r in rows)
            eng = sum((r["reactions"] or 0) + (r["comments"] or 0) + (r["shares"] or 0) for r in rows)
            imp_slack = sum(rounding_half_width(r["impressions"], r["precision"]) for r in rows)
            eng_slack = sum(rounding_half_width(r[k], r["precision"]) for r in rows
                            for k in ("reactions", "comments", "shares"))
            return len(rows), imp, eng, imp_slack, eng_slack

        cur_days, cur_imp, cur_eng, cur_imp_slack, cur_eng_slack = window_totals(start_cur, end_date)
        cur_eng_rate = round((cur_eng / cur_imp * 100), 2) if cur_imp > 0 else None

        cursor.execute(f"""
        SELECT COUNT(*) FROM analytics_daily
        WHERE date >= ? AND date <= ? AND NOT {daily_only}
        """, (start_cur.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
        excluded_days = cursor.fetchone()[0]

        prev_days, prev_imp, prev_eng, prev_imp_slack, prev_eng_slack = window_totals(start_prev, end_prev)
        prev_eng_rate = round((prev_eng / prev_imp * 100), 2) if prev_imp > 0 else None

        days_needed = math.ceil(days * MIN_CAPTURED_SHARE_TO_COMPARE)
        comparable = (cur_days or 0) >= days_needed and (prev_days or 0) >= days_needed

        # Every figure built from one LinkedIn rounded is named in
        # "approximate", and a change smaller than the rounding could hide is
        # not reported at all: it is named in "within_rounding" instead. The
        # rounded column was stored and read by nothing, so a 2.4K reading
        # became "Followers +396" against an exact 2,004.
        approximate: List[str] = []
        within_rounding: List[str] = []

        def judged(key, value, slack, change):
            """value when the change clears the rounding, else None; records which."""
            if value is None or not slack:
                return value
            if abs(change) <= slack:
                within_rounding.append(key)
                return None
            approximate.append(key)
            return value

        def calc_delta(key, cur, cur_slack, prev, prev_slack):
            if not comparable or prev == 0:
                return None
            cur_level, prev_level = cur / cur_days, prev / prev_days
            pct = round(((cur_level - prev_level) / prev_level) * 100.0, 1)
            return judged(key, pct, cur_slack / cur_days + prev_slack / prev_days, cur_level - prev_level)

        imp_delta = calc_delta("impressions_delta_pct", cur_imp, cur_imp_slack, prev_imp, prev_imp_slack)
        eng_delta = calc_delta("engagements_delta_pct", cur_eng, cur_eng_slack, prev_eng, prev_eng_slack)

        def rate_bounds(eng, eng_slack, imp, imp_slack):
            return ((eng - eng_slack) / (imp + imp_slack) * 100,
                    (eng + eng_slack) / max(imp - imp_slack, 1) * 100)

        eng_rate_delta = None
        if comparable and cur_eng_rate is not None and prev_eng_rate is not None:
            eng_rate_delta = round(cur_eng_rate - prev_eng_rate, 2)
            if cur_imp_slack or cur_eng_slack or prev_imp_slack or prev_eng_slack:
                cur_lo, cur_hi = rate_bounds(cur_eng, cur_eng_slack, cur_imp, cur_imp_slack)
                prev_lo, prev_hi = rate_bounds(prev_eng, prev_eng_slack, prev_imp, prev_imp_slack)
                overlap = cur_lo <= prev_hi and prev_lo <= cur_hi
                (within_rounding if overlap else approximate).append("engagement_rate_delta")
                if overlap:
                    eng_rate_delta = None

        cursor.execute("SELECT followers, profile_views, precision FROM analytics_daily WHERE date = ?", (end_date.strftime("%Y-%m-%d"),))
        latest_stat = cursor.fetchone()
        cur_followers = latest_stat["followers"] if (latest_stat and latest_stat["followers"] is not None) else None
        cur_pviews = latest_stat["profile_views"] if (latest_stat and latest_stat["profile_views"] is not None) else None

        cursor.execute("SELECT followers, profile_views, precision FROM analytics_daily WHERE date = ?", (start_cur.strftime("%Y-%m-%d"),))
        start_stat = cursor.fetchone()
        start_followers = start_stat["followers"] if (start_stat and start_stat["followers"] is not None) else None
        start_pviews = start_stat["profile_views"] if (start_stat and start_stat["profile_views"] is not None) else None

        def slack_of(row, key):
            return rounding_half_width(row[key], row["precision"]) if row else 0.0

        follower_growth = (cur_followers - start_followers) if (cur_followers is not None and start_followers is not None) else None
        follower_growth = judged("follower_growth", follower_growth,
                                 slack_of(latest_stat, "followers") + slack_of(start_stat, "followers"),
                                 follower_growth or 0)
        pviews_delta = (round(((cur_pviews - start_pviews) / start_pviews) * 100.0, 1)
                        if (cur_pviews is not None and start_pviews) else None)
        pviews_delta = judged("profile_views_delta_pct", pviews_delta,
                              slack_of(latest_stat, "profile_views") + slack_of(start_stat, "profile_views"),
                              (cur_pviews or 0) - (start_pviews or 0))

        if cur_imp_slack:
            approximate.append("impressions")
        if cur_eng_slack:
            approximate.append("total_engagements")
        if cur_eng_rate is not None and (cur_imp_slack or cur_eng_slack):
            approximate.append("avg_engagement_rate")
        if cur_followers is not None and slack_of(latest_stat, "followers"):
            approximate.append("total_followers")
        if cur_pviews is not None and slack_of(latest_stat, "profile_views"):
            approximate.append("profile_views")

        cursor.execute("SELECT COUNT(*) FROM posts WHERE status = 'scheduled'")
        scheduled_count = cursor.fetchone()[0]

        conn.close()

        if not cur_days:
            cur_imp = cur_eng = None

        return {
            "range": f"{days}d",
            "days_counted": cur_days,
            "previous_days_counted": prev_days,
            "days_needed_to_compare": days_needed,
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
            "approximate": approximate,
            "within_rounding": within_rounding,
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


def _rate(impressions, reactions, comments, shares):
    """(reactions + comments + shares) / impressions, as a percentage, or None without both read."""
    if not impressions or reactions is None:
        return None
    return round((reactions + (comments or 0) + (shares or 0)) * 100.0 / impressions, 2)


@router.get("/api/analytics/posts")
def get_posts_leaderboard():
    """
    The creator's posts, each with its figures and the leads it brought.

    The comparison is the creator's LinkedIn posts, imported from their
    activity pages or their archive: that is what they published. It read
    only the studio's own posts table, so a creator with years of history
    imported saw "NO PUBLISHED POSTS TO COMPARE". A studio post marked
    published that no LinkedIn post has been matched to is listed as well.

    Nothing reads a studio post's figures. The table writes every one at its
    column default of 0, so a studio post whose figures are all 0 or empty
    was never measured, and says so (None) rather than showing a 0% rate.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        listed = []
        for r in cursor.execute("""
            SELECT o.activity_urn, o.text, o.published_at, o.impressions, o.reactions, o.comments, o.reposts,
                   p.id AS post_id, p.media_urls, p.tags
            FROM own_posts o LEFT JOIN posts p ON p.activity_urn = o.activity_urn
        """).fetchall():
            listed.append({
                "id": r["activity_urn"], "content": r["text"] or "", "media_urls": r["media_urls"],
                "status": "published", "published_at": r["published_at"], "impressions": r["impressions"],
                "reactions": r["reactions"], "comments": r["comments"], "shares": r["reposts"], "tags": r["tags"],
                "activity_urn": r["activity_urn"], "studio_post_id": r["post_id"],
            })
        for r in cursor.execute("""
            SELECT id, content, media_urls, status, published_at, impressions, reactions, comments, shares, tags,
                   activity_urn
            FROM posts
            WHERE status = 'published'
              AND (activity_urn IS NULL OR activity_urn NOT IN (SELECT activity_urn FROM own_posts WHERE activity_urn IS NOT NULL))
              AND id NOT IN (SELECT activity_urn FROM own_posts WHERE activity_urn IS NOT NULL)
        """).fetchall():
            d = dict(r)
            if all(not d[k] for k in ("impressions", "reactions", "comments", "shares")):
                d.update(impressions=None, reactions=None, comments=None, shares=None)
            d["studio_post_id"] = d["id"]
            listed.append(d)

        listed.sort(key=lambda d: (d["impressions"] is None, -(d["impressions"] or 0),
                                   d["reactions"] is None, -(d["reactions"] or 0)))
        rows = []
        for d in listed:
            d["engagement_rate"] = _rate(d["impressions"], d["reactions"], d["comments"], d["shares"])
            d["media_urls"] = json.loads(d["media_urls"]) if d["media_urls"] else []
            d["tags"] = json.loads(d["tags"]) if d["tags"] else []

            post_id_str = str(d.pop("studio_post_id") or d["id"])
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
