"""
The creator's own surfaces nothing read before (cycle 4, track 5, phase 2).
==========================================================================

The creator opens these pages and the studio walked past them (the capture
report's coverage table): profile views and search appearances, the new
followers graph, "Who viewed your profile", the search appearances page, an
article's and a newsletter's own analytics pages, and on their Activity tab
their own reposts and the "edited" mark on their posts. The extension's
readers live in studio/extension/own_insights.js; this module keeps what
they send, and says how long each figure has gone unread.

The rules:

- Counts and windows only. A viewer's or a searcher's name, headline or
  company is another member's, and no column here can hold one.
- A windowed count is kept only with the window the page named; an account
  figure with no window it can name is not kept at all.
- Absent is not read: a figure the page did not show is NULL, never 0, and
  never drift (the owner's decision of 2026-10-26). How long each has gone
  unread is page_sightings, beside the post analytics page's sightings.
- A repost keeps that it is one, its date and its own figures. The original's
  author, words and figures are never kept, whatever the reader sent.

Strict Invariants:
- Zero em-dashes.
- This module imports onboarding only inside its functions: onboarding
  imports this one.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import results
    from .database import get_db
except ImportError:
    import results
    from database import get_db


# The pages, what each keeps, and the words a sentence uses for them.
PAGES: Dict[str, Dict[str, Any]] = {
    "account_analytics": {
        "words": ("analytics page", "analytics pages"), "content": False,
        "fields": (("profile_views", "profile views"), ("search_appearances", "search appearances")),
        "points": (("new_followers", "new followers by day"),),
    },
    "profile_views": {
        "words": ("profile views page", "profile views pages"), "content": False,
        "fields": (("profile_views", "profile views"),), "points": (),
    },
    "search_appearances": {
        "words": ("search appearances page", "search appearances pages"), "content": False,
        "fields": (("search_appearances", "search appearances"),), "points": (),
    },
    "article_analytics": {
        "words": ("article analytics page", "article analytics pages"), "content": True, "kind": "article",
        "fields": (("views", "article views"), ("impressions", "impressions"), ("members_reached", "members reached"),
                   ("reactions", "reactions"), ("comments", "comments"), ("reposts", "reposts")),
        "points": (),
    },
    "newsletter_analytics": {
        "words": ("newsletter analytics page", "newsletter analytics pages"), "content": True, "kind": "newsletter",
        "fields": (("subscribers", "subscribers"), ("views", "article views"), ("impressions", "impressions"),
                   ("email_sends", "email sends"), ("email_open_rate_pct", "email open rate")),
        "points": (),
    },
}
READING_COLUMNS = ("profile_views", "search_appearances", "views", "impressions", "members_reached", "reactions",
                   "comments", "reposts", "subscribers", "email_sends", "email_open_rate_pct")
SHARE_COLUMNS = ("email_open_rate_pct",)
REPOST_FIGURES = ("reactions", "comments", "reposts", "impressions")
# The Activity tab's facts, for the sightings: when each was last seen.
ACTIVITY_FIELDS = (("own_reposts", "your own reposts"), ("edited", "a post marked edited"))
ACTIVITY_WORDS = ("Activity tab read", "Activity tab reads")

_WINDOW = re.compile(r"^\d{1,3}d$")
_CONTENT_URN = re.compile(r"^urn:li:[A-Za-z_]+:[A-Za-z0-9_-]{3,80}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Refused(ValueError):
    """What the studio says when it will not keep a reading."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_creator(author: Any) -> None:
    """The figures are the confirmed creator's own, as every analytics reading must be."""
    try:
        from . import onboarding
    except ImportError:
        import onboarding
    me = onboarding.confirmed_vanity()
    named = onboarding.normalise_vanity(author)
    if not me:
        raise Refused("confirm your profile in Setup first, so the studio knows whose figures these are")
    if not named:
        # The address ends its own literal, as the analytics router's does, so
        # the distribution check sees LinkedIn's /in/me/ alias and nothing else.
        raise Refused("the bridge could not tell which LinkedIn account is signed in. Open your own profile at "
                      "https://www.linkedin.com/in/me/"
                      " once in this browser, then reload the page")
    if named != me:
        raise Refused(f"these figures are from linkedin.com/in/{named}, not from linkedin.com/in/{me}, "
                      "the profile open in the studio")


def _count(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _share(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 2) if 0.0 <= number <= 100.0 else None


def _precision(value: Any) -> Optional[str]:
    return value if value in ("exact", "rounded") else None


def ingest_page(author: Any, page: Any, content_urn: Any, readings: Any, points: Any) -> Dict[str, Any]:
    """
    One read of one of the pages in PAGES: its readings (each a window, a
    precision and the figures shown under it) and, for the account page, the
    per day points of its new followers graph.
    """
    _require_creator(author)
    spec = PAGES.get(page if isinstance(page, str) else "")
    if spec is None:
        raise Refused("not a page the studio reads")
    urn = content_urn if isinstance(content_urn, str) else ""
    if spec["content"] and not _CONTENT_URN.match(urn):
        raise Refused("an own content page must name its content")
    if not spec["content"]:
        urn = ""
    fields = {name for name, _label in spec["fields"]}
    figures_for: List[Tuple[str, Optional[str], Dict[str, Any]]] = []
    for reading in (readings if isinstance(readings, list) else [])[:20]:
        if not isinstance(reading, dict):
            continue
        window = reading.get("period_label") if isinstance(reading.get("period_label"), str) else ""
        # A count over a window is kept only with the window the page named.
        if window and not _WINDOW.match(window):
            continue
        if not window and not spec["content"]:
            continue
        shown = reading.get("figures") if isinstance(reading.get("figures"), dict) else {}
        kept = {}
        for name in fields:
            value = (_share if name in SHARE_COLUMNS else _count)(shown.get(name))
            if value is not None:
                kept[name] = value
        if kept:
            figures_for.append((window, _precision(reading.get("precision")), kept))
    point_rows = []
    allowed_points = {name for name, _label in spec["points"]}
    for point in (points if isinstance(points, list) else [])[:400]:
        if not isinstance(point, dict) or point.get("figure") not in allowed_points:
            continue
        day, value = point.get("date"), _count(point.get("value"))
        if not isinstance(day, str) or not _DAY.match(day) or value is None:
            continue
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            continue
        point_rows.append((day, point["figure"], value, _precision(point.get("precision"))))
    if not figures_for and not point_rows:
        return {"status": "success", "readings_recorded": 0, "points_recorded": 0}

    now = _now()
    conn = get_db()
    try:
        with conn:
            # A read that kept only graph points still counts as a read of the
            # page, so the sightings can say how many reads went without a card.
            for window, precision, kept in figures_for or [("", None, {})]:
                columns = list(kept)
                conn.execute(
                    f"""
                    INSERT INTO insight_readings (page, content_urn, observed_at, observed_hour, period_label,
                                                  precision{"".join(", " + c for c in columns)})
                    VALUES (?, ?, ?, ?, ?, ?{", ?" * len(columns)})
                    ON CONFLICT(page, content_urn, period_label, observed_hour) DO UPDATE SET
                        observed_at = excluded.observed_at,
                        precision = CASE
                            WHEN excluded.precision = 'rounded' OR insight_readings.precision = 'rounded'
                            THEN 'rounded' ELSE COALESCE(excluded.precision, insight_readings.precision) END
                        {"".join(f", {c} = COALESCE(excluded.{c}, insight_readings.{c})" for c in columns)}
                    """,
                    (page, urn, now.isoformat(), now.strftime("%Y-%m-%dT%H"), window, precision,
                     *[kept[c] for c in columns]))
            for day, figure, value, precision in point_rows:
                conn.execute(
                    "INSERT INTO insight_daily_points (date, figure, value, precision, source, observed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(date, figure, source) DO UPDATE SET "
                    "value = excluded.value, precision = excluded.precision, observed_at = excluded.observed_at",
                    (day, figure, value, precision, page, now.isoformat()))
    finally:
        conn.close()
    return {"status": "success", "readings_recorded": len(figures_for), "points_recorded": len(point_rows)}


# ---------------------------------------------------------------------------
# The Activity tab: the creator's own reposts and the edited flag
# ---------------------------------------------------------------------------

def record_own_repost(conn, activity_urn: str, item: Dict[str, Any]) -> int:
    """
    That the creator reposted, when, and the repost's own figures where the
    reader could tell them apart from the original's (own_figures). Nothing
    else in the item is read: its actor, text and counts may be the
    original's. 1 when kept.
    """
    try:
        from . import onboarding
    except ImportError:
        import onboarding
    own = item.get("own_figures") if isinstance(item.get("own_figures"), dict) else {}
    figures = {name: _count(own.get(name)) for name in REPOST_FIGURES}
    now = _now().isoformat()
    conn.execute(
        f"""
        INSERT INTO own_reposts (activity_urn, reposted_at, {", ".join(REPOST_FIGURES)}, first_seen_at, last_seen_at)
        VALUES (?, ?, {", ".join("?" for _ in REPOST_FIGURES)}, ?, ?)
        ON CONFLICT(activity_urn) DO UPDATE SET
            last_seen_at = excluded.last_seen_at,
            {", ".join(f"{n} = COALESCE(excluded.{n}, own_reposts.{n})" for n in REPOST_FIGURES)}
        """,
        (activity_urn, onboarding.published_at_from_urn(activity_urn), *[figures[n] for n in REPOST_FIGURES],
         now, now))
    return 1


def record_edited(conn, activity_urn: str, item: Dict[str, Any]) -> None:
    """When one of the creator's posts was first seen marked edited; kept once, never cleared."""
    if item.get("edited") is True:
        conn.execute("UPDATE own_posts SET edited_first_seen_at = COALESCE(edited_first_seen_at, ?) "
                     "WHERE activity_urn = ?", (_now().isoformat(), activity_urn))


# ---------------------------------------------------------------------------
# Reading them back
# ---------------------------------------------------------------------------

def account_figures(days: int) -> Dict[str, Any]:
    """
    Profile views and search appearances as the pages read them, each with
    its window and precision, and new followers by day, over the days
    counted back from the latest one read.
    """
    conn = get_db()
    try:
        latest = conn.execute(
            "SELECT MAX(day) FROM (SELECT MAX(substr(observed_at, 1, 10)) AS day FROM insight_readings "
            "WHERE content_urn = '' UNION ALL SELECT MAX(date) FROM insight_daily_points)").fetchone()[0]
        out: Dict[str, Any] = {"status": "success", "range_days": days, "profile_views": [],
                               "search_appearances": [], "new_followers": []}
        if not latest:
            return out
        start = (datetime.strptime(latest, "%Y-%m-%d").toordinal() - days + 1)
        start_day = datetime.fromordinal(start).strftime("%Y-%m-%d")
        for figure in ("profile_views", "search_appearances"):
            out[figure] = [
                {"date": r["observed_at"][:10], "value": r[figure], "period_label": r["period_label"],
                 "precision": r["precision"], "source": r["page"], "read_at": r["observed_at"]}
                for r in conn.execute(
                    f"SELECT page, observed_at, period_label, precision, {figure} FROM insight_readings "
                    f"WHERE content_urn = '' AND {figure} IS NOT NULL AND substr(observed_at, 1, 10) BETWEEN ? AND ? "
                    "ORDER BY observed_at", (start_day, latest))]
        out["new_followers"] = [
            {"date": r["date"], "value": r["value"], "precision": r["precision"], "source": r["source"]}
            for r in conn.execute("SELECT date, value, precision, source FROM insight_daily_points "
                                  "WHERE figure = 'new_followers' AND date BETWEEN ? AND ? ORDER BY date",
                                  (start_day, latest))]
        out["from"], out["to"] = start_day, latest
        return out
    finally:
        conn.close()


def content_figures() -> Dict[str, Any]:
    """
    Each article or newsletter whose analytics page was read: every reading,
    oldest first, and each figure's latest value, the newest reading that
    has it (review S2), with its window and precision.
    """
    kinds = {page: spec["kind"] for page, spec in PAGES.items() if spec["content"]}
    conn = get_db()
    try:
        rows = [dict(r) for r in conn.execute(
            f"SELECT page, content_urn, observed_at, period_label, precision, {', '.join(READING_COLUMNS)} "
            f"FROM insight_readings WHERE content_urn != '' ORDER BY content_urn, observed_at")]
    finally:
        conn.close()
    content: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row["page"] not in kinds:
            continue
        entry = content.setdefault(row["content_urn"], {"content_urn": row["content_urn"], "kind": kinds[row["page"]],
                                                        "readings": [], "latest": {}})
        fields = [name for name, _label in PAGES[row["page"]]["fields"]]
        entry["readings"].append({key: row[key] for key in ("observed_at", "period_label", "precision", *fields)})
        for name in fields:
            if row[name] is not None:
                entry["latest"][name] = {"value": row[name], "read_at": row["observed_at"],
                                         "period_label": row["period_label"], "precision": row["precision"]}
    return {"status": "success", "content": list(content.values())}


def own_reposts() -> List[Dict[str, Any]]:
    """The creator's own reposts, newest first: when, and their own figures where read."""
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(
            f"SELECT activity_urn, reposted_at, {', '.join(REPOST_FIGURES)}, first_seen_at, last_seen_at "
            "FROM own_reposts ORDER BY COALESCE(reposted_at, first_seen_at) DESC")]
    finally:
        conn.close()


def page_sightings() -> List[Dict[str, Any]]:
    """
    Per page this module reads, and for the Activity tab's two facts: each
    figure's last read and how many reads of its page have gone without it
    since, in results.sighting's one sentence.
    """
    out = []
    conn = get_db()
    try:
        for page, spec in PAGES.items():
            total = conn.execute("SELECT COUNT(*) FROM insight_readings WHERE page = ?", (page,)).fetchone()[0]
            fields = []
            for field, label in spec["fields"]:
                last = conn.execute(f"SELECT MAX(observed_at) FROM insight_readings WHERE page = ? "
                                    f"AND {field} IS NOT NULL", (page,)).fetchone()[0]
                fields.append(_sighting(conn, "SELECT COUNT(*) FROM insight_readings WHERE page = ? AND observed_at > ?",
                                        (page,), field, label, total, last, spec["words"]))
            for field, label in spec["points"]:
                last = conn.execute("SELECT MAX(observed_at) FROM insight_daily_points WHERE figure = ? AND source = ?",
                                    (field, page)).fetchone()[0]
                fields.append(_sighting(conn, "SELECT COUNT(*) FROM insight_readings WHERE page = ? AND observed_at > ?",
                                        (page,), field, label, total, last, spec["words"]))
            out.append({"page": page, "readings": total, "fields": fields})
        # The Activity tab: its reads are the hours its readings were taken in.
        reads = ("SELECT COUNT(DISTINCT observed_hour) FROM post_metric_observations "
                 "WHERE source = 'activity_page'")
        total = conn.execute(reads).fetchone()[0]
        lasts = {"own_reposts": conn.execute("SELECT MAX(last_seen_at) FROM own_reposts").fetchone()[0],
                 "edited": conn.execute("SELECT MAX(edited_first_seen_at) FROM own_posts").fetchone()[0]}
        out.append({"page": "activity", "readings": total, "fields": [
            _sighting(conn, reads + " AND observed_at > ?", (), field, label, total, lasts[field], ACTIVITY_WORDS)
            for field, label in ACTIVITY_FIELDS]})
    finally:
        conn.close()
    return out


def _sighting(conn, since_sql: str, params: tuple, field: str, label: str, total: int, last: Optional[str],
              words: Tuple[str, str]) -> Dict[str, Any]:
    since = total if last is None else conn.execute(since_sql, (*params, last)).fetchone()[0]
    return {"field": field, "label": label, **results.sighting(label, total, last, since, words)}
