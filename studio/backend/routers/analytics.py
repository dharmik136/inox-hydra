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
from fastapi import APIRouter, HTTPException, Response, Path, Query

try:
    from ..database import get_db
    from .. import insights
    from .. import post_summary
    from .. import results
    from ..crm import reverse_crm, VIP_THRESHOLD
    from ..linkedin_client import linkedin_client
except (ImportError, ValueError):
    from database import get_db
    import insights
    import post_summary
    import results
    from crm import reverse_crm, VIP_THRESHOLD
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
# impressions a day was reported as +650%. The share lives in results.py with
# the rest of the rules, so a new screen cannot pick its own.
MIN_CAPTURED_SHARE_TO_COMPARE = results.MIN_CAPTURED_SHARE_TO_COMPARE


def rounding_half_width(value, precision) -> float:
    """
    How far a stored figure can be from the true one, given how LinkedIn wrote it.

    A row marked 'rounded' holds at least one figure LinkedIn abbreviated,
    such as 1.2K stored as 1200, without saying which. LinkedIn writes compact
    numbers the way the browser's compact number format does: one decimal
    below 10K (1.2K, and 2K for 2.0K), whole thousands up to 999K (12K), one
    decimal below 10M (1.2M), whole millions above. So the step a figure was
    rounded to follows from its size: 100 below 10,000, 1,000 below a
    million, 100,000 below 10 million, 1,000,000 above, and the figure is
    half a step either way. A value that is not a multiple of its step
    cannot be one LinkedIn abbreviated, so it was written out in full and is
    exact. (This replaced reading the last non-zero digit, which gave a bare
    20K a margin of 5,000.)
    """
    if precision != "rounded" or value is None or value < 1000:
        return 0.0
    step = 100 if value < 10_000 else 1_000 if value < 1_000_000 else 100_000 if value < 10_000_000 else 1_000_000
    return step / 2.0 if value % step == 0 else 0.0


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
            """
            Per metric: the days it was read on, its sum over those days, and
            how far rounding can move that sum.

            Counted per metric, not per row. A day whose impressions were read
            and whose engagements were not is a captured impressions day and
            an uncaptured engagements day: counted per row it was a captured
            day of 0 engagements, and a month read that way was a -100% fall.
            The rate uses only days on which both were read.
            """
            cursor.execute(f"""
            SELECT impressions, reactions, comments, shares, precision
            FROM analytics_daily
            WHERE date >= ? AND date <= ? AND {daily_only}
            """, (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
            rows = cursor.fetchall()
            parts = ("reactions", "comments", "shares")

            def imp_read(r):
                return r["impressions"] is not None

            def eng_read(r):
                return any(r[k] is not None for k in parts)

            def eng(r):
                return sum(r[k] or 0 for k in parts)

            def imp_slack(r):
                return rounding_half_width(r["impressions"], r["precision"])

            def eng_slack(r):
                return sum(rounding_half_width(r[k], r["precision"]) for k in parts)

            imp_rows = [r for r in rows if imp_read(r)]
            eng_rows = [r for r in rows if eng_read(r)]
            both = [r for r in imp_rows if eng_read(r)]
            return {
                "rows": len(rows),
                "impressions": (len(imp_rows), sum(r["impressions"] for r in imp_rows),
                                sum(imp_slack(r) for r in imp_rows)),
                "engagements": (len(eng_rows), sum(eng(r) for r in eng_rows), sum(eng_slack(r) for r in eng_rows)),
                "rate": (len(both), sum(r["impressions"] for r in both), sum(eng(r) for r in both),
                         sum(imp_slack(r) for r in both), sum(eng_slack(r) for r in both)),
            }

        cur, prev = window_totals(start_cur, end_date), window_totals(start_prev, end_prev)
        cur_days, prev_days = cur["rows"], prev["rows"]
        cur_imp_days, cur_imp, cur_imp_slack = cur["impressions"]
        cur_eng_days, cur_eng, cur_eng_slack = cur["engagements"]

        def rate_of(window):
            n, imp, eng, _is, _es = window["rate"]
            return round(eng / imp * 100, 2) if n and imp > 0 else None

        cur_eng_rate, prev_eng_rate = rate_of(cur), rate_of(prev)

        cursor.execute(f"""
        SELECT COUNT(*) FROM analytics_daily
        WHERE date >= ? AND date <= ? AND NOT {daily_only}
        """, (start_cur.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
        excluded_days = cursor.fetchone()[0]

        days_needed = math.ceil(days * MIN_CAPTURED_SHARE_TO_COMPARE)

        def comparable(metric):
            """Each metric's change stands or falls on that metric's own coverage."""
            return (results.window_complete(cur[metric][0], days_needed)
                    and results.window_complete(prev[metric][0], days_needed))

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

        def calc_delta(key, metric):
            (cur_n, cur_sum, cur_slack), (prev_n, prev_sum, prev_slack) = cur[metric], prev[metric]
            if not comparable(metric) or prev_sum == 0:
                return None
            cur_level, prev_level = cur_sum / cur_n, prev_sum / prev_n
            pct = round(((cur_level - prev_level) / prev_level) * 100.0, 1)
            return judged(key, pct, cur_slack / cur_n + prev_slack / prev_n, cur_level - prev_level)

        imp_delta = calc_delta("impressions_delta_pct", "impressions")
        eng_delta = calc_delta("engagements_delta_pct", "engagements")

        def rate_bounds(window):
            _n, imp, eng, imp_slack, eng_slack = window["rate"]
            return ((eng - eng_slack) / (imp + imp_slack) * 100,
                    (eng + eng_slack) / max(imp - imp_slack, 1) * 100)

        eng_rate_delta = None
        if comparable("rate") and cur_eng_rate is not None and prev_eng_rate is not None:
            eng_rate_delta = round(cur_eng_rate - prev_eng_rate, 2)
            if any(cur["rate"][3:]) or any(prev["rate"][3:]):
                cur_lo, cur_hi = rate_bounds(cur)
                prev_lo, prev_hi = rate_bounds(prev)
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
        if cur_eng_rate is not None and any(cur["rate"][3:]):
            approximate.append("avg_engagement_rate")
        if cur_followers is not None and slack_of(latest_stat, "followers"):
            approximate.append("total_followers")
        if cur_pviews is not None and slack_of(latest_stat, "profile_views"):
            approximate.append("profile_views")

        cursor.execute("SELECT COUNT(*) FROM posts WHERE status = 'scheduled'")
        scheduled_count = cursor.fetchone()[0]

        conn.close()

        # A metric read on no day of the range is not measured, not 0.
        if not cur_imp_days:
            cur_imp = None
        if not cur_eng_days:
            cur_eng = None

        return {
            "range": f"{days}d",
            "days_counted": cur_days,
            "previous_days_counted": prev_days,
            "days_needed_to_compare": days_needed,
            # Days each figure was read on, this period and the one before.
            "coverage": {metric: {"current": cur[metric][0], "previous": prev[metric][0]}
                         for metric in ("impressions", "engagements", "rate")},
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
    """
    (reactions + comments + shares) / impressions as a percentage, and the
    reason there is none when there is none.

    results.engagement_rate owns the rule. This had no clamp and no check that
    engagements cannot exceed impressions, so one post of 1,417 printed
    "116.25% engagement" as a measured fact, and the aside beside the table
    promoted exactly that post.
    """
    return results.engagement_rate({"impressions": impressions, "reactions": reactions,
                                    "comments": comments, "reposts": shares})


@router.get("/api/analytics/posts")
def get_posts_leaderboard(limit: Optional[int] = Query(None, ge=1), offset: int = Query(0, ge=0)):
    """
    The creator's posts, each with its figures and the leads it brought.

    One page of posts, most seen first, insights.POSTS_PAGE of them by
    default. This used to answer with every post, 2,432 KB on three years of
    one creator, and a `limit` in the URL was accepted and ignored: limit=50
    and limit=2000 returned the same 1,418 posts. The order is the order it
    always was, so the rows of a page are the rows that page always held.

    The comparison is the creator's LinkedIn posts, imported from their
    activity pages or their archive: that is what they published. It read
    only the studio's own posts table, so a creator with years of history
    imported saw "NO PUBLISHED POSTS TO COMPARE". A studio post marked
    published that no LinkedIn post has been matched to is listed as well.

    Nothing reads a studio post's figures. The table writes every one at its
    column default of 0, so a studio post whose figures are all 0 or empty
    was never measured, and says so (None) rather than showing a 0% rate.

    Every figure, the rate and "which post worked best" come from results.py,
    so this screen and the Posts screen answer alike. `best` is read from the
    whole history, never from the page.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        # One reading per post, from the one engine, so this table and the
        # Posts screen cannot show one post two sets of figures.
        read = results.figures(conn)
        listed = []
        for r in cursor.execute("""
            SELECT o.activity_urn, o.text, o.published_at,
                   p.id AS post_id, p.media_urls, p.tags
            FROM own_posts o LEFT JOIN posts p ON p.activity_urn = o.activity_urn
        """).fetchall():
            figure = read.get(r["activity_urn"]) or {}
            listed.append({
                "id": r["activity_urn"], "content": r["text"] or "", "media_urls": r["media_urls"],
                "status": "published", "published_at": r["published_at"],
                "impressions": figure.get("impressions"), "reactions": figure.get("reactions"),
                "comments": figure.get("comments"), "shares": figure.get("reposts"), "tags": r["tags"],
                "figures_source": figure.get("source"), "figures_read_at": figure.get("read_at"),
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
            d.setdefault("figures_source", None)
            d.setdefault("figures_read_at", None)
            listed.append(d)

        listed.sort(key=lambda d: (d["impressions"] is None, -(d["impressions"] or 0),
                                   d["reactions"] is None, -(d["reactions"] or 0)))
        # The page, cut after the sort, so a page holds the posts that page
        # has always held. Everything below runs for the page's posts only:
        # the lead attribution of 1,418 posts was computed and sent on every
        # Analytics load for a table nobody scrolled to the end of.
        size, start = insights.page_bounds(limit, offset)
        total = len(listed)
        listed = listed[start:start + size]
        # Who each post brought, from the per-post summary: its people, how
        # many are VIP, and their scores' sum. Reading every interaction to
        # build each post's set took 1 s at 500,000. A lead tied to a post by
        # leads.post_id, or a post reached under two keys, is counted from the
        # sets themselves, so nobody is counted twice.
        summary = post_summary.current(conn)
        folds = post_summary.folded(conn)
        scores: Dict[str, Any] = {}
        by_post_id: Dict[str, set] = {}
        for r in cursor.execute(
                "SELECT post_id, id, icp_score FROM leads WHERE post_id IS NOT NULL AND post_id != ''").fetchall():
            scores[r["id"]] = r["icp_score"]
            by_post_id.setdefault(r["post_id"], set()).add(r["id"])

        def attribution(post_id_str: str, post_urn: str) -> Dict[str, Any]:
            keys = [k for k in dict.fromkeys((post_id_str, post_urn)) if k]
            rows_for = [summary[k] for k in keys if k in summary and summary[k]["people"]]
            tied = [by_post_id[k] for k in keys if k in by_post_id]
            # A summary row's counts include the reactors the retention job
            # folded (batch R4) who did nothing else on the post, with their
            # tiers as they were then; one who also commented is counted once.
            if len(rows_for) == 1 and not tied:
                row = rows_for[0]
                return {"total_leads": row["people"], "vip_leads": row["vip"],
                        "avg_icp": round(row["icp_sum"] / row["icp_known"], 1) if row["icp_known"] else 0.0}
            # Named people are counted from the sets; the fold keeps no names,
            # so its people and tiers are added to theirs.
            fold = {column: 0 for column in post_summary.FOLDED_TIERS}
            for entry in (folds[k] for k in keys if k in folds):
                for column in fold:
                    fold[column] += entry.get(column) or 0
            brought = set().union(*tied, *(post_summary.lead_ids_of(row) for row in rows_for))
            missing = [lead for lead in brought if lead not in scores]
            if missing:
                for r in cursor.execute("SELECT id, icp_score FROM leads WHERE id IN (SELECT value FROM json_each(?))",
                                        (json.dumps(missing),)).fetchall():
                    scores[r["id"]] = r["icp_score"]
            known = [scores[lead] for lead in brought if scores.get(lead) is not None]
            known_count = len(known) + fold["icp_known"]
            return {
                "total_leads": len(brought) + fold["people"],
                "vip_leads": sum(1 for score in known if score >= VIP_THRESHOLD) + fold["vip"],
                "avg_icp": round(round(sum(known) + fold["icp_sum"], 6) / known_count, 1) if known_count else 0.0,
            }

        rows = []
        for d in listed:
            rate, reason = _rate(d["impressions"], d["reactions"], d["comments"], d["shares"])
            d["engagement_rate"] = rate
            # Why there is no rate, so the screen says it rather than leaving
            # a blank or printing an impossible number.
            d["engagement_rate_unmeasured"] = reason
            d["engagement_rate_note"] = results.rate_reason_sentence(reason)
            d["media_urls"] = json.loads(d["media_urls"]) if d["media_urls"] else []
            d["tags"] = json.loads(d["tags"]) if d["tags"] else []

            post_id_str = str(d.pop("studio_post_id") or d["id"])
            post_urn = d.get("activity_urn") or ""
            d["attribution"] = attribution(post_id_str, post_urn)
            rows.append(d)
        # Which posts worked, from the whole history and the one engine. The
        # aside beside this table used to take the highest engagement rate out
        # of the rows the page had fetched, so after paging it named the best
        # post on page one, and the post it named shared no ground with the
        # two the Posts screen named.
        worked = results.best(conn, limit=2, read=read)
        conn.close()
        return {"status": "success", "posts": rows, "best": worked,
                **insights.paging(total, size, start, len(rows))}
    finally:
        conn.close()


@router.get("/api/analytics/best")
def get_best_posts():
    """
    The posts that did best and worst against the creator's own median, from
    the whole history (results.best), with each named post's figures.

    What the Analytics aside reads. It came with a fourteen-row post table
    that the Posts screen holds in full, sortable and searchable, so the
    table moved to Posts (cycle 4, track 3, batch 1) and the aside reads the
    engine's answer without a page of rows it would not draw.
    """
    conn = get_db()
    try:
        return {"status": "success", "best": results.best(conn, limit=2)}
    finally:
        conn.close()


@router.get("/api/v1/analytics/posts/{post_id}/leads", tags=["Enterprise Reverse CRM", "Analytics"])
def get_post_leads_attribution(post_id: str = Path(..., max_length=200),
                               account_id: str = Query("default", max_length=100)):
    # A numeric id is also looked up as an integer, and one SQLite cannot hold
    # raised OverflowError, a 500, rather than finding nothing.
    digits = post_id.strip().lstrip("-")
    if digits.isdigit() and int(digits) > 2 ** 63 - 1:
        raise HTTPException(status_code=422, detail="That post id is out of range.")
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
                "the bridge could not tell which LinkedIn account is signed in. Open your own profile at "
                "https://www.linkedin.com/in/me/"
                " once in this browser, then reload the analytics page"))
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

