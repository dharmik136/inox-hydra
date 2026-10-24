"""
Posts and Outbound: what your own history says.
===============================================

Two questions a creator can act on, answered only from what the studio
observed on their own account:

  Posts     Which of my posts worked, and whom did each one bring?
  Outbound  Whose content do I spend my attention on, and does it come back?

Neither screen predicts anything. A post is compared with your own median, not
with a benchmark, and "worked" is said only of posts old enough for their
numbers to have settled. Reciprocity is matched by name, because a reaction
records the author's display name and not their profile, and the screen says
so rather than presenting a name match as an identity.

Strict Invariants:
- Zero em-dashes.
- Every comparison carries the number of posts it rests on.
- A count never read is shown as unknown, not as zero.
"""

import json
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from .text_cut import clip
except ImportError:
    from text_cut import clip

try:
    from . import onboarding, post_identity, post_summary, results
    from .database import get_db
except ImportError:
    import onboarding
    import post_identity
    import post_summary
    import results
    from database import get_db

# What worked, how old a post must be before it is judged, and the creator's
# own median are results.py's to define, so that the Posts screen, the
# Evidence panel and Analytics cannot answer differently. This module reads
# them and adds the people each post brought.
MIN_FOR_MEDIAN = results.MIN_FOR_MEDIAN

# ---------------------------------------------------------------------------
# One page of posts
# ---------------------------------------------------------------------------
#
# Posts and Analytics each answered with every post the creator has ever
# written, each carrying the people who engaged with it: measured on three
# years, 2,201 KB from /api/v1/insights/posts and 2,432 KB from
# /api/analytics/posts, on every load of either screen, and the second
# accepted a `limit` in the URL and ignored it. One page of 50 is 78 KB and
# 83 KB. Both endpoints page through here, so the contract is written once:
# the rows of one page, and what a caller needs to ask for the next.
#
# Only the list of posts is a page. Every figure beside it (the creator's
# usual, which posts are worth repurposing, how many settled posts carry no
# figures) is still computed from the whole history, because a median of the
# first fifty posts is a different number, not the same number read faster.

POSTS_PAGE = 50
POSTS_PAGE_MAX = 200


def page_bounds(limit: Optional[int], offset: Optional[int]) -> tuple:
    """The page a caller asked for, as (size, start), clamped to what one answer carries."""
    size = POSTS_PAGE if limit is None else max(1, min(int(limit), POSTS_PAGE_MAX))
    return size, max(0, int(offset or 0))


def paging(total: int, size: int, start: int, returned: int) -> Dict[str, Any]:
    """What a caller needs to know to ask for the rest, as every paged answer says it."""
    return {"total": total, "limit": size, "offset": start, "returned": returned,
            "has_more": start + returned < total}


def _excerpt(text: Optional[str], limit: int = 140) -> Optional[str]:
    return clip(" ".join((text or "").split()), limit) or None


# What the Posts screen's table can sort and filter by. Every option still
# pages through page_bounds/paging above: sorting and filtering choose which
# posts make the ordered list that is then cut into a page, so sorting by
# reactions surfaces the creator's true top post on page one rather than the
# top of whichever fifty rows a fixed published_at order happened to put
# there first.
POSTS_SORTS = ("newest", "oldest", "reactions", "impressions", "comments")
POSTS_SETTLED_STATES = ("settled", "growing")


def _for_like(term: str) -> str:
    """
    A search term as LIKE should read it: the creator's own characters.

    LIKE takes % and _ as wildcards, so a search for "50%" matched every post
    and a search for "a_b" matched "axb".
    """
    for character in ("\\", "%", "_"):
        term = term.replace(character, "\\" + character)
    return term


def posts_overview(limit: Optional[int] = None, offset: Optional[int] = None, sort: str = "newest",
                    settled_state: Optional[str] = None, q: Optional[str] = None) -> Dict[str, Any]:
    size, start = page_bounds(limit, offset)
    sort = sort if sort in POSTS_SORTS else "newest"
    settled_state = settled_state if settled_state in POSTS_SETTLED_STATES else None
    search = (q or "").strip() or None
    conn = get_db()
    try:
        # What worked, over the whole history: the creator's own median, the
        # best and worst posts, and the settle rule, all from the one engine,
        # so the Posts screen cannot name a post Analytics does not. Never
        # narrowed by a sort, a filter or a search: a median of the posts a
        # search happened to match is a different number, not the same
        # number read faster.
        settle = results.settled_after_hours(conn)
        read_all = results.figures(conn)
        worked = results.best(conn, limit=2, settled_after=settle["hours"], read=read_all)
        # Every post's figures, which the usual, the best two and the counts
        # below are all read from, and which carry no text: the text of 1,417
        # posts was most of the 2,201 KB this answer used to be.
        posts = [dict(r) for r in conn.execute(
            "SELECT activity_urn, published_at, published_at_source FROM own_posts ORDER BY published_at DESC")]

        # The ordered, filtered list a page is cut from. A search reads text
        # at the database, which SQLite scans in under a millisecond at 1,417
        # rows; the settled state and the metric sorts are read from read_all,
        # which this call already holds for the whole history.
        candidates = list(posts) if search is None else [dict(r) for r in conn.execute(
            "SELECT activity_urn, published_at, published_at_source FROM own_posts "
            "WHERE text LIKE ? ESCAPE '\\' ORDER BY published_at DESC", (f"%{_for_like(search)}%",))]
        if settled_state == "settled":
            candidates = [p for p in candidates if results.is_settled(p["published_at"], settle["hours"])]
        elif settled_state == "growing":
            candidates = [p for p in candidates if not results.is_settled(p["published_at"], settle["hours"])]

        def _metric_key(urn: str, metric: str):
            value = (read_all.get(urn) or {}).get(metric)
            # None sorts last whichever direction the metric is read in: a
            # post never read is not worse than zero, it is unmeasured.
            return (value is None, -(value or 0))

        if sort == "oldest":
            candidates.sort(key=lambda p: (p["published_at"] is None, p["published_at"] or ""))
        elif sort in ("reactions", "impressions", "comments"):
            candidates.sort(key=lambda p: _metric_key(p["activity_urn"], sort))
        # "newest" needs no re-sort: every query above already read that order.

        total = len(candidates)
        sliced = candidates[start:start + size]
        urns_on_page = [p["activity_urn"] for p in sliced]
        # The text for the page's rows only, read by the ids the sort and the
        # filter settled on, never for the whole history.
        marks = ", ".join("?" for _ in urns_on_page)
        texts = ({r["activity_urn"]: r["text"] for r in conn.execute(
            f"SELECT activity_urn, text FROM own_posts WHERE activity_urn IN ({marks})", urns_on_page)}
                 if urns_on_page else {})
        page = [{**p, "text": texts.get(p["activity_urn"])} for p in sliced]
        # One reading per post, with the page it was read from named, and
        # where the post sits among the creator's own posts at the same age.
        pairs = results.pair(conn, urns_on_page, read=read_all)

        # Who engaged with each post on the page, from the per-post summary.
        # Every interaction used to be read into Python on every load: 1.9 s
        # at 500,000. A post whose engagement was recorded under two spellings
        # of its URN is counted from the raw rows, each person once.
        summary = post_summary.current(conn)
        wanted = {onboarding._activity_id(p["activity_urn"]) for p in page}
        spellings: Dict[str, List[str]] = {}
        for urn, row in summary.items():
            key = onboarding._activity_id(urn)
            if key in wanted and (row["people"] or row["folded_reactions"]):
                spellings.setdefault(key, []).append(urn)
        engagers: Dict[str, Dict[str, Any]] = {
            key: (summary[urns[0]] if len(urns) == 1 else post_summary.combined(conn, urns))
            for key, urns in spellings.items()}
    finally:
        conn.close()

    settled = [p for p in posts if results.is_settled(p["published_at"], settle["hours"])]
    usual = worked["usual"]

    # Settled posts no figure was ever read for, usually from LinkedIn's
    # archive, which carries none. Counted so the screen can say why there is
    # no usual, rather than blaming the age of posts that are years old.
    unmeasured = [p for p in settled
                  if all((read_all.get(p["activity_urn"]) or {}).get(m) is None
                         for m in results.COMPARED_METRICS)]

    out = []
    for post in page:
        urn = post["activity_urn"]
        age = results.age_hours(post["published_at"])
        engaged = engagers.get(onboarding._activity_id(urn))
        figure = read_all.get(urn) or {}
        settled_now = results.is_settled(post["published_at"], settle["hours"])
        ratios = results.against_usual(figure, usual) if settled_now else {}

        out.append({
            "activity_urn": urn,
            "excerpt": _excerpt(post["text"]),
            "published_at": post["published_at"],
            "age_days": round(age / 24, 1) if age is not None else None,
            "settled": settled_now,
            "reactions": figure.get("reactions"),
            "comments": figure.get("comments"),
            "reposts": figure.get("reposts"),
            "impressions": figure.get("impressions"),
            # Which page these figures were read from, and when. Posts and
            # Analytics showed the stored snapshot while Today showed a
            # reading, so one post read 19,943 impressions on one screen and
            # 50,118 on the other in the same minute.
            "figures_source": figure.get("source"),
            "figures_read_at": figure.get("read_at"),
            "against_usual": ratios or None,
            # Reach and response together: a post of this creator's sat at p5
            # for impressions and p86 for reactions at the same moment, and
            # either number alone reads as the opposite of the truth. None
            # when the studio has no reading at a comparable age.
            "reach_and_response": pairs.get(urn),
            # Commenters first, then by name, at most post_summary.TOP_PEOPLE.
            "people": post_summary.people_of(engaged),
            # Reactions older than 24 months are kept as counts once the
            # retention job folds them (retention.py). The summary's people
            # include the folded reactors who did nothing else on this post;
            # one who also commented is counted once, from the comment.
            # folded_reactions is how many reactions were folded.
            "people_count": engaged["people"] if engaged else 0,
            "folded_reactions": engaged["folded_reactions"] if engaged else 0,
            # People from this post the creator went on to talk to: Connected
            # or Meeting Booked. The question the Posts screen exists for.
            "conversations": engaged["conversations"] if engaged else 0,
            # None for a post published from the studio and not yet seen on
            # LinkedIn: it is recorded under a local key, and a link built
            # from that key would 404.
            "url": post_identity.linkedin_permalink(post["activity_urn"]),
        })

    return {
        "status": "success",
        "posts": out,
        **paging(total, size, start, len(out)),
        # The table's own state, echoed back, so the screen can keep its
        # controls in step with the page it is showing rather than track them
        # twice.
        "sort": sort,
        "settled_state": settled_state,
        "q": search,
        "usual": usual,
        # The settled posts that did best and worst against your own median
        # reactions, which is what "repurpose the top two" means: forms that
        # already worked. Read from the whole history, not from the page, so
        # the same posts are named whichever page the screen is showing, and
        # from the one engine, so Analytics names them too.
        "best": worked["best"],
        "worst": worked["worst"],
        "metric": worked["metric"],
        "ranked_posts": worked["ranked_posts"],
        # How old a post of this creator's has to be before its figures are
        # judged: measured from their own readings where they can say
        # (settled.measured), and the week the studio used to assume where
        # they cannot.
        "settled_after": settle,
        "settled_after_days": round(settle["hours"] / 24, 1),
        "settled_without_figures": len(unmeasured),
        "settled_without_figures_from_archive": sum(1 for p in unmeasured if p["published_at_source"] == "archive"),
    }


def post_detail(activity_urn: str) -> Optional[Dict[str, Any]]:
    """
    One post, in full, for the detail view the Posts table opens into.

    The table's own page carries a 140 character excerpt, because the full
    text of every post on it was most of what made that answer 2,201 KB. A
    creator who opens one post gets its whole text here, read once, with the
    same figures, the same settle rule and the same comparison against their
    own median that the table's row already carried, so the two screens
    cannot disagree about the one post either of them is showing.

    None when the studio holds no such post.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT activity_urn, text, published_at, published_at_source FROM own_posts WHERE activity_urn = ?",
            (activity_urn,)).fetchone()
        if not row:
            return None
        row = dict(row)
        settle = results.settled_after_hours(conn)
        read_all = results.figures(conn)
        figure = read_all.get(activity_urn) or {}
        settled_now = results.is_settled(row["published_at"], settle["hours"])
        settled_posts = [p for p in conn.execute(
            "SELECT activity_urn, published_at FROM own_posts WHERE published_at IS NOT NULL")
            if results.is_settled(p["published_at"], settle["hours"])]
        usual = results.usual_of(read_all.get(p["activity_urn"]) or {} for p in settled_posts)
        ratios = results.against_usual(figure, usual) if settled_now else None
        pair = results.pair(conn, [activity_urn], read=read_all).get(activity_urn)
        rate, reason = results.engagement_rate(figure)
        age = results.age_hours(row["published_at"])
    finally:
        conn.close()

    return {
        "status": "success",
        "activity_urn": row["activity_urn"],
        "text": row["text"] or "",
        "published_at": row["published_at"],
        "published_at_source": row["published_at_source"],
        "age_days": round(age / 24, 1) if age is not None else None,
        "settled": settled_now,
        "settled_after": settle,
        "settled_after_days": round(settle["hours"] / 24, 1),
        "reactions": figure.get("reactions"),
        "comments": figure.get("comments"),
        "reposts": figure.get("reposts"),
        "impressions": figure.get("impressions"),
        "figures_source": figure.get("source"),
        "figures_read_at": figure.get("read_at"),
        "engagement_rate": rate,
        "engagement_rate_unmeasured": reason,
        "engagement_rate_note": results.rate_reason_sentence(reason),
        "against_usual": ratios,
        "usual": usual,
        # Where this post sits among the creator's own posts at the same age,
        # for reach and for response, together: the pair results.py exists
        # for, read from the whole history, not from the table's page.
        "reach_and_response": pair,
        # None for a post published from the studio and not yet seen on
        # LinkedIn: it is recorded under a local key, and a link built from
        # that key would 404.
        "url": post_identity.linkedin_permalink(row["activity_urn"]),
    }


def _name_key(name: Optional[str]) -> str:
    return " ".join((name or "").lower().split())


def outbound_overview() -> Dict[str, Any]:
    conn = get_db()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT target_author, kind, reaction_kind, my_text, last_seen_at FROM outbound_engagements")]
        own_ids = onboarding._own_activity_ids(conn)
        # People who engaged with your posts, by display name, and on how
        # many of them: a comment and a like on one post is one post, not two.
        #
        # Only the names of accounts you engaged with can be matched, so only
        # leads with one of those names are looked up, and their interactions
        # read by lead. Reading every interaction to build every name's set
        # took 1.1 s at 500,000.
        wanted = {_name_key(r["target_author"]) for r in rows if r["target_author"]}
        named: Dict[str, str] = {}
        if wanted:
            for lead in conn.execute("SELECT id, COALESCE(full_name, name) AS name FROM leads"):
                key = _name_key(lead["name"])
                if key in wanted:
                    named[lead["id"]] = key
        engaged_back: Dict[str, set] = {}
        if named:
            for row in conn.execute(
                "SELECT CAST(lead_id AS TEXT) AS lead_id, post_urn FROM lead_interactions "
                "WHERE lead_id IN (SELECT value FROM json_each(?)) AND post_urn IS NOT NULL",
                (json.dumps(list(named)),)):
                post = onboarding._activity_id(row["post_urn"])
                if post in own_ids and row["lead_id"] in named:
                    engaged_back.setdefault(named[row["lead_id"]], set()).add(post)
        # Which of your posts the studio has read engagers on, for coverage.
        read_posts = {onboarding._activity_id(urn) for urn, row in post_summary.current(conn).items()
                      if row["people"] or row["folded_reactions"]}
    finally:
        conn.close()

    authors: Dict[str, Dict[str, Any]] = {}
    unknown = 0
    for row in rows:
        if not row["target_author"]:
            unknown += 1
            continue
        key = _name_key(row["target_author"])
        entry = authors.setdefault(key, {"name": row["target_author"], "reactions": 0, "comments": 0,
                                         "last_at": None})
        entry["reactions" if row["kind"] == "reaction" else "comments"] += 1
        if (row["last_seen_at"] or "") > (entry["last_at"] or ""):
            entry["last_at"] = row["last_seen_at"]

    for key, entry in authors.items():
        entry["total"] = entry["reactions"] + entry["comments"]
        entry["engaged_back"] = len(engaged_back.get(key, ()))

    ranked = sorted(authors.values(), key=lambda a: (a["total"], a["comments"]), reverse=True)

    # "Never engaged back" is only a finding once the studio has read who
    # engaged with most of your posts. Engagers are captured as you open your
    # posts, so on a new install nobody has, and every account would be listed
    # as one-way on the strength of the studio not having looked. Measured on
    # the first live install: 1 engager captured, and 6 of 6 top accounts
    # would have been called one-way.
    conn = get_db()
    try:
        engaged_posts = [r["activity_urn"] for r in conn.execute(
            "SELECT activity_urn FROM own_posts WHERE COALESCE(reactions, 0) + COALESCE(comments, 0) > 0")]
    finally:
        conn.close()
    covered = sum(1 for urn in engaged_posts if onboarding._activity_id(urn) in read_posts)
    coverage = round(covered / len(engaged_posts), 2) if engaged_posts else 0.0
    judged = coverage >= 0.5

    return {
        "coverage": {"posts_read": covered, "posts_with_engagement": len(engaged_posts), "share": coverage,
                     "one_way_judged": judged},
        "status": "success",
        "totals": {"reactions": sum(1 for r in rows if r["kind"] == "reaction"),
                   "comments": sum(1 for r in rows if r["kind"] == "comment"),
                   "authors": len(authors), "without_author": unknown},
        "authors": ranked[:40],
        # Accounts you engaged with at least three times that have never
        # engaged with a post of yours: where your attention goes one way.
        "one_way": ([a["name"] for a in ranked if a["total"] >= 3 and not a["engaged_back"]][:12]
                    if judged else []),
        "reciprocal": [a["name"] for a in ranked if a["engaged_back"]][:12],
        "matched_by": "display name",
    }


# ---------------------------------------------------------------------------
# Patterns: which forms have gone with more engagement, for you
# ---------------------------------------------------------------------------
#
# Each pattern splits your settled posts in two (has it, does not) and compares
# the median reactions of each side. The features, the minimum per side and
# what counts as a difference are results.py's, so that this screen cannot
# publish a line the Evidence panel suppresses on the same posts: it asked for
# 3 posts a side where the panel asked for 8. Every line carries both counts
# and a verdict, which may be "none": on a few dozen posts a difference is a
# lead to try, not a finding. The wording is "went with", never "causes": this
# compares posts, it runs no experiment.

PATTERNS = results.BINARY_FEATURES
MIN_PER_SIDE = results.MIN_PER_SIDE
opening_line = results.opening_line


def patterns_overview() -> Dict[str, Any]:
    conn = get_db()
    try:
        settle = results.settled_after_hours(conn)
        read = results.figures(conn)
        posts = [dict(r) for r in conn.execute(
            "SELECT activity_urn, text, published_at FROM own_posts WHERE text IS NOT NULL")]
        # Left out because no reactions were ever read for them, as for every
        # post imported from LinkedIn's archive. Not because of their age.
        unread = [dict(r) for r in conn.execute(
            "SELECT activity_urn, published_at, published_at_source FROM own_posts")]
    finally:
        conn.close()

    def reactions_of(post):
        return (read.get(post["activity_urn"]) or {}).get("reactions")

    settled = [p for p in posts if results.is_settled(p["published_at"], settle["hours"])
               and reactions_of(p) is not None]
    unread = [p for p in unread if results.is_settled(p["published_at"], settle["hours"])
              and reactions_of(p) is None]

    found, too_few = [], []
    for key, label, test in results.BINARY_FEATURES:
        with_it, without, with_dates, without_dates = [], [], [], []
        for post in settled:
            has = test(post["text"], results.opening_line(post["text"]))
            (with_it if has else without).append(reactions_of(post))
            (with_dates if has else without_dates).append(results.timestamp(post["published_at"]))
        entry = {"key": key, "label": label, "with_posts": len(with_it), "without_posts": len(without)}
        if len(with_it) < results.MIN_PER_SIDE or len(without) < results.MIN_PER_SIDE:
            entry["difference"] = results.difference(None, len(with_it), len(without))
            too_few.append(entry)
            continue
        a, b = statistics.median(with_it), statistics.median(without)
        ratio = round(a / b, 2) if b else None
        entry.update({"with_median": a, "without_median": b, "ratio": ratio})
        # What this line is allowed to say, including "none": the same cut as
        # the Evidence panel's, so one screen cannot call a split notable
        # while the other calls it nothing.
        entry["difference"] = results.difference(ratio, len(with_it), len(without))
        # When the two sides come from different periods, the difference may
        # be about when rather than how. Measured on the first live install:
        # hashtags went with 2.7x the reactions, and the hashtag posts were
        # mostly from two years earlier, when the account and its audience
        # were different. Flagged rather than hidden.
        entry.update(results.different_periods([d for d in with_dates if d],
                                               [d for d in without_dates if d]))
        found.append(entry)

    found.sort(key=lambda e: abs((e["ratio"] or 1) - 1), reverse=True)
    return {
        "status": "success",
        "posts_compared": len(settled),
        "settled_without_reactions": len(unread),
        "settled_without_reactions_from_archive": sum(1 for p in unread if p["published_at_source"] == "archive"),
        "metric": results.RANKED_METRIC,
        "patterns": found,
        "not_enough_posts": too_few,
        "min_per_side": results.MIN_PER_SIDE,
        "settled_after": settle,
        # Nothing here is a finding unless its own verdict says so.
        "no_difference": results.NO_DIFFERENCE,
    }


# ---------------------------------------------------------------------------
# Cadence: how steadily you post
# ---------------------------------------------------------------------------
#
# Counts, gaps and the queue. It deliberately does not name a best day or
# time: the studio does not choose when your posts go out, so the days you
# posted on are the days you chose, and a few posts per weekday cannot separate
# the day from everything else about those posts.

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def cadence_overview() -> Dict[str, Any]:
    conn = get_db()
    try:
        dates = [datetime.fromisoformat(r["published_at"]).astimezone()
                 for r in conn.execute("SELECT published_at FROM own_posts WHERE published_at IS NOT NULL "
                                       "ORDER BY published_at")]
        now = datetime.now(timezone.utc)
        horizon = (now + timedelta(days=14)).isoformat()
        scheduled = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE status = 'scheduled' AND scheduled_for IS NOT NULL "
            "AND scheduled_for >= ? AND scheduled_for <= ?", (now.isoformat(), horizon)).fetchone()[0]
        slots = conn.execute("SELECT COUNT(*) FROM queue_slots WHERE is_active = 1").fetchone()[0]
    finally:
        conn.close()

    if not dates:
        return {"status": "success", "posts": 0}

    gaps = [(b - a).total_seconds() / 86400.0 for a, b in zip(dates, dates[1:])]
    months: Dict[str, int] = {}
    cursor = dates[0].replace(day=1)
    end = datetime.now().astimezone()
    while (cursor.year, cursor.month) <= (end.year, end.month):
        months[f"{cursor.year:04d}-{cursor.month:02d}"] = 0
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    for d in dates:
        months[f"{d.year:04d}-{d.month:02d}"] = months.get(f"{d.year:04d}-{d.month:02d}", 0) + 1

    longest = max(range(len(gaps)), key=lambda i: gaps[i]) if gaps else None
    return {
        "status": "success",
        "posts": len(dates),
        "first_post": dates[0].date().isoformat(),
        "last_post": dates[-1].date().isoformat(),
        "days_since_last": round((datetime.now().astimezone() - dates[-1]).total_seconds() / 86400.0, 1),
        "median_gap_days": round(statistics.median(gaps), 1) if gaps else None,
        "longest_gap": ({"days": round(gaps[longest], 1), "from": dates[longest].date().isoformat(),
                         "to": dates[longest + 1].date().isoformat()} if longest is not None else None),
        "by_month": [{"month": m, "posts": n} for m, n in months.items()],
        "by_weekday": [{"day": WEEKDAYS[i], "posts": sum(1 for d in dates if d.weekday() == i)} for i in range(7)],
        "queue": {"scheduled_next_14_days": scheduled, "weekly_slots": slots},
    }
