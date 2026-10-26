"""
Backtest From your record on your own history, offline.
=======================================================
Before any creator sees the section, the strongest check is to ask, of a
history that already happened: month by month, using only what the studio
held at the start of that month, what would the section have called "what
worked", and were those still the right posts when the readings came in?

Run it on your own database, or a copy of it. It opens the file read-only,
copies what it needs into memory, sends nothing anywhere, and writes a
report that holds no post text, no post id and no name: counts and shares
only, so it can be shared.

    python tools/backtest_record.py --db ~/InoxHydra/data/linkedin_studio.db
    python tools/backtest_record.py --db copy.db --out report.json --top 5 --tune 2024

For each month m (from the fourth month with posts, to the last whole month):

  snapshot      own_posts published before m, with the "last seen" figures
                blanked, and post_metric_observations observed before m;
                "now" is m, so a post is settled only if it was old enough
                at m. results.ranking on the snapshot is what the section
                would have ranked
  picks         the top N of that ranking (N is --top, 5 by default)
  stability     the share of the picks that are in the top quarter of the
                final ranking (every reading the database holds today)
  foresight     the share of the next month's posts that reached the final
                top quarter whose topic (the creator's own vocabulary as it
                stood at m) is a topic of the picks
  resurfacing   the share of the opener pool at m (the top quarter of the
                ranking at m when 8 or more posts are ranked, else every post
                with an opener of six words or more) whose post ends above the
                creator's final median
  model         for a month the section actually ran in: how many of the
                model's ideas were shown and dropped, by reason; a shown idea
                with a missing row or a number would be a defect

Output (--out, JSON; the same as a table on stdout):

  {"tool": "backtest_record", "format": 1, "database": "<file name only>",
   "generated_at": "<UTC ISO>", "top": N,
   "months": [{"month": "YYYY-MM", "posts_before": int, "ranked_before": int,
               "picks": int, "stability": float|null, "foresight": float|null,
               "next_month_top": int, "resurfacing": float|null,
               "opener_pool": int, "model": {...}|null}],
   "years": {"YYYY": {"months": int, "stability": float|null,
                      "foresight": float|null, "resurfacing": float|null}},
   "split": {"tune": ["YYYY", ...], "test": ["YYYY", ...]},
   "model_rerank": "<sentence>"}

A share is null when there is nothing to share out of (no picks, no next
month top posts, no pool). Tune on the --tune years and read the others as
the test, so the same history is not used twice. If a model re-rank is ever
built, it is kept only if it beats the rule order here.

Strict Invariants:
- Zero em-dashes.
- Zero egress, and the database is never written.
- The report carries no text, id or name.
"""

import argparse
import contextlib
import json
import os
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

REPO = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
sys.path.insert(0, os.path.join(REPO, "studio", "backend"))

import evidence_briefing  # noqa: E402
import results  # noqa: E402

FORMAT = 1
WARM_UP_MONTHS = 3
QUARTER = 0.25
POOL_FROM_RANKING_AT = 8
MIN_OPENER_WORDS = 6

# The columns the snapshot always has. Every other column the source holds is
# copied too, so the engine reads the snapshot exactly as it reads the studio:
# a fixed list here left out `precision` when migration 28 added it, the
# engine's newest-reading query failed on the snapshot, and every month ranked
# nothing. A column an older database lacks is NULL in the snapshot, which is
# how the engine reads a reading that does not say how it was read.
POST_COLUMNS = ("activity_urn", "text", "published_at", "published_at_source", "reactions", "comments", "reposts",
                "impressions", "first_seen_at", "last_seen_at")
READING_COLUMNS = ("activity_urn", "observed_at", "observed_hour", "age_hours", "source", "impressions",
                   "members_reached", "reactions", "comments", "reposts", "saves", "sends", "precision")


@contextlib.contextmanager
def now_is(moment: datetime) -> Iterator[None]:
    """results.py asks datetime.now() how old a post is; for a month of the past, the answer is that month."""
    real = results.datetime

    class Then(real):  # type: ignore[misc, valid-type]
        @classmethod
        def now(cls, tz=None):
            return moment if tz is None else moment.astimezone(tz)

    results.datetime = Then
    try:
        yield
    finally:
        results.datetime = real


def open_read_only(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{os.path.abspath(path)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def snapshot(source: sqlite3.Connection, before: Optional[str]) -> sqlite3.Connection:
    """
    An in-memory database holding what the studio held before `before` (or
    everything, for None): posts published before it, their "last seen"
    figures blanked so only readings can rank them, and readings observed
    before it.
    """
    memory = sqlite3.connect(":memory:")
    memory.row_factory = sqlite3.Row
    posts = _columns(source, "own_posts", POST_COLUMNS)
    readings = _columns(source, "post_metric_observations", READING_COLUMNS)
    memory.execute(f"CREATE TABLE own_posts ({', '.join(posts['all'])}, PRIMARY KEY (activity_urn))")
    memory.execute(f"CREATE TABLE post_metric_observations ({', '.join(readings['all'])})")
    where_posts = "WHERE published_at IS NOT NULL" + (" AND published_at < ?" if before else "")
    where_readings = "WHERE observed_at < ?" if before else ""
    params = (before,) if before else ()
    for row in (source.execute(f"SELECT {', '.join(posts['held'])} FROM own_posts {where_posts}", params)
                if posts["held"] else ()):
        values = dict(row)
        if before:
            for column in ("reactions", "comments", "reposts", "impressions"):
                values[column] = None
        memory.execute(f"INSERT INTO own_posts ({', '.join(posts['held'])}) VALUES "
                       f"({', '.join('?' for _ in posts['held'])})", tuple(values[c] for c in posts['held']))
    for row in (source.execute(f"SELECT {', '.join(readings['held'])} FROM post_metric_observations "
                               f"{where_readings}", params) if readings["held"] else ()):
        memory.execute(f"INSERT INTO post_metric_observations ({', '.join(readings['held'])}) VALUES "
                       f"({', '.join('?' for _ in readings['held'])})", tuple(row))
    return memory


def _columns(source: sqlite3.Connection, table: str, always: Tuple[str, ...]) -> Dict[str, List[str]]:
    """
    The columns a snapshot table has ("all": the ones it always has, then
    every other column the source's table holds) and the ones copied from the
    source ("held": those the source has), so a column the engine reads is
    never missing from the snapshot and a column the source lacks is NULL.
    """
    held = [row[1] for row in source.execute(f"PRAGMA table_info({table})")]
    return {"all": list(always) + [c for c in held if c not in always], "held": held}


def _ranking(conn: sqlite3.Connection, moment: Optional[datetime]) -> Dict[str, Any]:
    results.forget_cache()
    if moment is None:
        return results.ranking(conn)
    with now_is(moment):
        return results.ranking(conn)


def _month_start(month: str) -> datetime:
    year, number = (int(part) for part in month.split("-"))
    return datetime(year, number, 1, tzinfo=timezone.utc)


def _next(month: str) -> str:
    year, number = (int(part) for part in month.split("-"))
    return f"{year + (number == 12):04d}-{number % 12 + 1:02d}"


def _share(part: int, whole: int) -> Optional[float]:
    return round(part / whole, 3) if whole else None


def _model_month(source: sqlite3.Connection, month: str) -> Optional[Dict[str, Any]]:
    try:
        rows = source.execute("SELECT status, provenance_json FROM daily_view WHERE kind = 'idea' AND day LIKE ?",
                              (month + "-%",)).fetchall()
    except sqlite3.OperationalError:
        return None
    if not rows:
        return None
    shown = [r for r in rows if r["status"] in ("shown", "spare")]
    dropped: Dict[str, int] = {}
    defects = 0
    for row in rows:
        verification = (json.loads(row["provenance_json"] or "{}").get("verification") or {})
        if row["status"] == "dropped":
            reason = verification.get("dropped_reason") or "unknown"
            dropped[reason] = dropped.get(reason, 0) + 1
        elif not verification.get("ids_exist", True) or verification.get("digits_in_model_text"):
            defects += 1
    return {"ideas": len(rows), "shown": len(shown), "dropped": dropped, "shown_with_a_defect": defects}


def backtest(path: str, top: int = 5, tune: Optional[List[str]] = None) -> Dict[str, Any]:
    source = open_read_only(path)
    try:
        months = sorted({r[0][:7] for r in source.execute(
            "SELECT published_at FROM own_posts WHERE published_at IS NOT NULL")})
        full = snapshot(source, None)
        final = _ranking(full, None)
        final_order = final["order"]
        final_top = set(final_order[: max(1, int(len(final_order) * QUARTER))]) if final_order else set()
        final_usual = final["usual"][results.RANKED_METRIC]["median"]
        final_ratio = {urn: results.against_usual(final["figures"].get(urn), final["usual"]).get(results.RANKED_METRIC)
                       for urn in final_order}
        texts = {r["activity_urn"]: r["text"] for r in full.execute("SELECT activity_urn, text FROM own_posts")}
        published = {r["activity_urn"]: r["published_at"] for r in full.execute("SELECT activity_urn, published_at FROM own_posts")}
        last_whole = datetime.now(timezone.utc).strftime("%Y-%m")
        report_months = []
        for month in months[WARM_UP_MONTHS:]:
            if month >= last_whole:
                break
            moment = _month_start(month)
            at_m = snapshot(source, moment.isoformat())
            ranking = _ranking(at_m, moment)
            picks = ranking["order"][:top]
            vocabulary = evidence_briefing.derive_topic_vocabulary(
                [texts.get(u) for u in texts if (published.get(u) or "") < moment.isoformat()])
            pick_topics = {evidence_briefing.classify_post_topic(texts.get(u), vocabulary) for u in picks}
            nxt = _next(month)
            next_top = [u for u in final_top if (published.get(u) or "")[:7] == nxt]
            hits = sum(1 for u in next_top if evidence_briefing.classify_post_topic(texts.get(u), vocabulary) in pick_topics)
            if len(ranking["order"]) >= POOL_FROM_RANKING_AT:
                pool = ranking["order"][: max(1, int(len(ranking["order"]) * QUARTER))]
            else:
                pool = [u for u in texts if (published.get(u) or "") < moment.isoformat()
                        and len(((texts.get(u) or "").strip().splitlines() or [""])[0].split()) >= MIN_OPENER_WORDS]
            judged = [u for u in pool if final_ratio.get(u) is not None]
            above = sum(1 for u in judged if final_ratio[u] >= 1.0)
            report_months.append({
                "month": month,
                "posts_before": ranking["posts"],
                "ranked_before": ranking["ranked_posts"],
                "picks": len(picks),
                "stability": _share(sum(1 for u in picks if u in final_top), len(picks)),
                "foresight": _share(hits, len(next_top)),
                "next_month_top": len(next_top),
                "resurfacing": _share(above, len(judged)),
                "opener_pool": len(pool),
                "model": _model_month(source, month),
            })
            at_m.close()
        full.close()
    finally:
        source.close()
        results.forget_cache()

    years: Dict[str, Dict[str, Any]] = {}
    for item in report_months:
        bucket = years.setdefault(item["month"][:4], {"months": 0, "stability": [], "foresight": [], "resurfacing": []})
        bucket["months"] += 1
        for key in ("stability", "foresight", "resurfacing"):
            if item[key] is not None:
                bucket[key].append(item[key])
    for bucket in years.values():
        for key in ("stability", "foresight", "resurfacing"):
            bucket[key] = round(statistics.mean(bucket[key]), 3) if bucket[key] else None
    tune_years = sorted(set(tune or [])) or (sorted(years)[:1] if years else [])
    return {
        "tool": "backtest_record",
        "format": FORMAT,
        "database": os.path.basename(path),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "top": top,
        "final_median_reactions": final_usual,
        "months": report_months,
        "years": years,
        "split": {"tune": tune_years, "test": [y for y in sorted(years) if y not in tune_years]},
        "model_rerank": ("not built: the section has no model re-rank. Rules stay unless one is built and beats the "
                         "rule order on this backtest."),
    }


def table(report: Dict[str, Any]) -> str:
    lines = [f"backtest of {report['database']}: top {report['top']} picks a month, final median "
             f"{report['final_median_reactions']} reactions", "",
             "| Month | Posts before | Ranked | Stability | Foresight | Resurfacing |", "|---|---|---|---|---|---|"]
    for m in report["months"]:
        def said(value):
            return "n/a" if value is None else f"{value:.2f}"
        lines.append(f"| {m['month']} | {m['posts_before']} | {m['ranked_before']} | {said(m['stability'])} | "
                     f"{said(m['foresight'])} | {said(m['resurfacing'])} |")
    lines.append("")
    for year, bucket in sorted(report["years"].items()):
        role = "tune" if year in report["split"]["tune"] else "test"
        lines.append(f"{year} ({role}): {bucket['months']} months, stability {bucket['stability']}, "
                     f"foresight {bucket['foresight']}, resurfacing {bucket['resurfacing']}")
    lines.append(report["model_rerank"])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", required=True, help="your studio database, or a copy of it; opened read-only")
    parser.add_argument("--out", help="write the JSON report here")
    parser.add_argument("--top", type=int, default=5, help="how many picks a month (default 5)")
    parser.add_argument("--tune", nargs="*", default=None, help="the years to tune on (default: the first year)")
    args = parser.parse_args(argv)
    if not os.path.isfile(args.db):
        print(f"There is no database at {args.db}.", file=sys.stderr)
        return 2
    report = backtest(args.db, top=max(1, args.top), tune=args.tune)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
    print(table(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
