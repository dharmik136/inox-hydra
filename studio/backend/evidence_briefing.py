"""
Evidence Briefing & Topic Attribution Service (CP3 & CP4).
===========================================================
Extracts evidence-backed retrieval briefs for AI generation (CP3) and
computes the Topic-to-Qualified-Lead attribution map (CP4) from real SQLite history.

Strict Invariants:
- Zero em-dashes in any comments or strings.
- Pure zero-cloud-egress local processing.
- Clean connection closure in finally blocks.
"""

import time
import unicodedata
from collections import Counter
from typing import Dict, Any, List, Optional, Tuple

try:
    from .database import get_db, get_db_path
    from .contrast_engine import compute_all_contrasts
except ImportError:
    from database import get_db, get_db_path
    from contrast_engine import compute_all_contrasts


# ---------------------------------------------------------------------------
# Topics, from the creator's own posts
# ---------------------------------------------------------------------------
#
# Topics were four fixed buckets in the original author's own vocabulary
# (sqlite, postgres, wal, backend, llm, saas), with everything else filed as
# "Practitioner Insights". A bakery's history put 10 of 12 posts in that one
# bucket, and "pricing your croissants" became Product & Strategy.
#
# So the topics are now the words and hashtags that recur across the
# creator's own posts. A post goes under the first chosen topic it mentions,
# and a post that shares none goes under "Other posts". It is a keyword
# grouping, not a reading of what a post means, and the screen says so.

TOPIC_GROUPING = "keywords and hashtags that recur across your own posts"
OTHER_TOPIC = "Other posts"
MAX_TOPICS = 6
MIN_POSTS_PER_TOPIC = 2
# A word on more than this share of the posts separates nothing.
MAX_TOPIC_SHARE = 0.5
# Only the most widespread words can win a round, so only they are weighed.
TOPIC_CANDIDATES = 300

_STOPWORDS = frozenset("""
a about above after again against all almost also always am among an and another any anyone anything are
around as ask asked at away back be became because become been before being below best better between big
both but by came can cannot come could day days did do does doing done down during each else enough even
ever every everyone everything few find first for found from full get gets getting give go goes going gone
good got great had has have having he hello her here hers him his how however i if in into is isn it its
just keep kind know last least less let lets like little long look lot lots made make makes making many may
me might more most much must my need needs never new next no nobody none nor not nothing now of off often
on once one only or other others our ours out over own part people per post posts put quite rather read
real really right said same say says see seen she should show since so some someone something sometimes
start still such sure take than thank thanks that the their them then there these they thing things think
this those though thought three through time times to today together too took toward try two under until
up upon us use used using very want wants was way ways we week weeks well went were what when where whether
which while who whom whose why will with within without work would yes yet you your yours year years
""".split())


def _words(text: str) -> List[Tuple[str, str, bool]]:
    """(key, as written, was a hashtag) for each word of the text, in any alphabet."""
    out, word, tagged = [], [], False

    def flush():
        written = "".join(word)
        key = written.casefold()
        if len(key) >= 3 and key not in _STOPWORDS and not key.isdigit():
            # A plural and its singular are one topic: croissants, croissant.
            if len(key) > 4 and key.endswith("s") and not key.endswith("ss"):
                key = key[:-1]
            out.append((key, written, tagged))

    for ch in str(text or "") + " ":
        if ch.isalnum() or (word and unicodedata.category(ch).startswith("M")):
            word.append(ch)
            continue
        if word:
            flush()
        word, tagged = [], ch == "#"
    return out


def derive_topic_vocabulary(texts: List[Optional[str]]) -> List[Tuple[str, str]]:
    """
    The creator's topics, as (key, label) in the order a post is tested against them.

    Chosen greedily: each round takes the word or hashtag that covers the
    most posts not yet covered, preferring one the creator used as a
    hashtag, then the longer, more specific word, and stops at MAX_TOPICS
    or when nothing covers two more posts.
    """
    posts_with: Dict[str, set] = {}
    written: Dict[str, Counter] = {}
    hashtags = set()
    count = 0
    for text in texts:
        if not text:
            continue
        for key, form, tagged in _words(text):
            posts_with.setdefault(key, set()).add(count)
            written.setdefault(key, Counter())[form.casefold()] += 1
            if tagged:
                hashtags.add(key)
        count += 1
    ceiling = max(MIN_POSTS_PER_TOPIC, int(count * MAX_TOPIC_SHARE))
    candidates = sorted((k for k, ids in posts_with.items() if MIN_POSTS_PER_TOPIC <= len(ids) <= ceiling),
                        key=lambda k: -len(posts_with[k]))[:TOPIC_CANDIDATES]

    chosen: List[Tuple[str, str]] = []
    uncovered = set(range(count))
    while len(chosen) < MAX_TOPICS and candidates:
        gain = {k: len(posts_with[k] & uncovered) for k in candidates}
        best = max(candidates, key=lambda k: (gain[k], k in hashtags, len(k), [-ord(c) for c in k]))
        if gain[best] < MIN_POSTS_PER_TOPIC:
            break
        form = sorted(written[best].items(), key=lambda item: (-item[1], len(item[0]), item[0]))[0][0]
        chosen.append((best, form[:1].upper() + form[1:]))
        uncovered -= posts_with[best]
        candidates.remove(best)
    return chosen


# The Obsidian export classifies one post at a time, 2,000 calls for 2,000
# posts, so the active creator's vocabulary is kept, and whether their posts
# have changed is asked at most once every few seconds.
_VOCABULARY_RECHECK_SECONDS = 2.0
_vocabulary_cache: Dict[str, Dict[str, Any]] = {}


def _creator_vocabulary() -> List[Tuple[str, str]]:
    """The vocabulary of the active creator's posts, rebuilt only when their posts change."""
    path = get_db_path()
    cached = _vocabulary_cache.get(path)
    now = time.monotonic()
    if cached and now - cached["checked"] < _VOCABULARY_RECHECK_SECONDS:
        return cached["vocabulary"]
    conn = get_db()
    try:
        signature = tuple(conn.execute(
            "SELECT COUNT(*), MAX(last_seen_at), TOTAL(LENGTH(text)) FROM own_posts WHERE text IS NOT NULL"
        ).fetchone())
        if not cached or cached["signature"] != signature:
            texts = [r[0] for r in conn.execute("SELECT text FROM own_posts WHERE text IS NOT NULL")]
            cached = {"signature": signature, "vocabulary": derive_topic_vocabulary(texts)}
        cached["checked"] = now
        _vocabulary_cache.clear()
        _vocabulary_cache[path] = cached
        return cached["vocabulary"]
    finally:
        conn.close()


def classify_post_topic(text: Optional[str], vocabulary: Optional[List[Tuple[str, str]]] = None) -> str:
    """
    The topic a post goes under: the first of the creator's topics it mentions.

    Without a vocabulary, the active creator's own is used, so the Obsidian
    export groups posts exactly as Patterns does.
    """
    if vocabulary is None:
        vocabulary = _creator_vocabulary()
    keys = {key for key, _w, _t in _words(text or "")}
    for key, label in vocabulary:
        if key in keys:
            return label
    return OTHER_TOPIC


def _people(n: int) -> str:
    return f"{n} {'person' if n == 1 else 'people'}"


def _posts(n: int) -> str:
    return f"{n} {'post' if n == 1 else 'posts'}"


def _topic_posts(topic: str) -> str:
    """A topic's posts, named once: "Croissant posts", but "Other posts", not "Other posts posts"."""
    return topic if topic == OTHER_TOPIC else f"{topic} posts"


def get_topic_attribution_map() -> Dict[str, Any]:
    """
    Computes CP4 Topic to Qualified-Lead Attribution Map.
    Maps creator's posts to topics and counts qualified leads generated.
    """
    conn = get_db()
    try:
        # Fetch posts
        post_rows = conn.execute(
            "SELECT activity_urn, text, reactions, comments FROM own_posts WHERE text IS NOT NULL"
        ).fetchall()
        posts = [dict(r) for r in post_rows]

        # Fetch lead interactions linked to post URNs with qualified status
        interactions = conn.execute("""
            SELECT i.post_urn, l.id, l.icp_score, l.lead_status, l.status
            FROM lead_interactions i
            JOIN leads l ON l.id = i.lead_id
            WHERE i.post_urn IS NOT NULL
        """).fetchall()
    finally:
        conn.close()

    if not posts:
        return {
            "status": "cold_start",
            "message": "No posts recorded yet. Publish or ingest posts to view topic attribution.",
            "topics": [],
            "summary_sentence": "Cold start: no post topics recorded yet."
        }

    # People per post, not interactions. Adding one per interaction row made
    # a founder who commented and reacted two qualified leads, three people
    # "6 qualified leads", and leads divided by posts a 600% "conversion".
    people_per_post: Dict[str, set] = {}
    qualified_people: set = set()
    for row in interactions:
        urn = row["post_urn"]
        icp = row["icp_score"] or 0
        lead_status = (row["lead_status"] or "").upper()
        status = (row["status"] or "").lower()
        is_qualified = (icp >= 60.0) or (lead_status in ("ENGAGED", "CONVERTED")) or ("connected" in status or "meeting" in status)
        people_per_post.setdefault(urn, set()).add(row["id"])
        if is_qualified:
            qualified_people.add(row["id"])

    # Aggregate by topic
    vocabulary = derive_topic_vocabulary([p.get("text") for p in posts])
    topic_aggregates: Dict[str, Dict[str, Any]] = {}
    for p in posts:
        urn = p.get("activity_urn") or ""
        topic = classify_post_topic(p.get("text"), vocabulary)
        rxn = p.get("reactions") or 0

        entry = topic_aggregates.setdefault(topic, {
            "topic": topic,
            "posts_count": 0,
            "post_count": 0,
            "total_reactions": 0,
            "people": set(),
        })
        entry["posts_count"] += 1
        entry["post_count"] += 1
        entry["total_reactions"] += rxn
        # A person who engaged with two posts of a topic is one person for it.
        entry["people"] |= people_per_post.get(urn, set())

    for entry in topic_aggregates.values():
        people = entry.pop("people")
        entry["people_engaged"] = len(people)
        entry["qualified_leads"] = len(people & qualified_people)

    topic_list = sorted(
        topic_aggregates.values(),
        key=lambda t: (t["qualified_leads"], t["total_reactions"]),
        reverse=True
    )

    for t in topic_list:
        # The share of the people captured on the topic's posts who are
        # qualified: a rate that cannot pass 100%, and none without people.
        t["lead_conversion_rate"] = (round(t["qualified_leads"] / t["people_engaged"], 4)
                                     if t["people_engaged"] else None)
        t["summary"] = f"{_people(t['qualified_leads'])} qualified from {_posts(t['posts_count'])}"

    if len(topic_list) >= 2:
        top = topic_list[0]
        bottom = topic_list[-1]
        summary_sentence = (
            f"Your {_topic_posts(top['topic'])}: {_people(top['qualified_leads'])} qualified "
            f"from {_posts(top['posts_count'])}. Your {_topic_posts(bottom['topic'])}: "
            f"{_people(bottom['qualified_leads'])} qualified from {_posts(bottom['posts_count'])}."
        )
    elif topic_list:
        top = topic_list[0]
        summary_sentence = (f"Your {_topic_posts(top['topic'])}: {_people(top['qualified_leads'])} qualified "
                            f"from {_posts(top['posts_count'])}.")
    else:
        summary_sentence = "No topic attribution available yet."

    return {
        "status": "success",
        "grouping": TOPIC_GROUPING,
        "topics": topic_list,
        "summary_sentence": summary_sentence
    }


def get_retrieval_evidence_brief(limit_top: int = 3, limit_bottom: int = 2) -> Dict[str, Any]:
    """
    CP3 Grounded Retrieval Brief for BYO-AI Copilot.
    Extracts top and bottom performing historical post exemplars and conclusive contrasts.
    """
    conn = get_db()
    try:
        # Ranked by reactions, the measure "top performing" names, with the
        # people each post brought counted once each and shown beside it. It
        # was ranked by a count of interactions, which put a 50 reaction post
        # with three chatty commenters above posts with 300.
        #
        # The interactions are joined to leads from the leads side, inside
        # the subquery. Joined the other way, lead_interactions.lead_id
        # (INTEGER affinity) against leads.id (TEXT) can use no index, and
        # every post scanned every lead: 1.8 s at 2,000 posts, 19 ms now.
        rows = conn.execute("""
            SELECT p.activity_urn, p.text, p.reactions, p.comments,
                   COUNT(DISTINCT CASE WHEN q.icp_score >= 60 THEN q.lead_id END) AS qualified_leads
            FROM own_posts p
            LEFT JOIN (
                SELECT li.post_urn, l.id AS lead_id, l.icp_score
                FROM leads l CROSS JOIN lead_interactions li ON li.lead_id = l.id
            ) q ON q.post_urn = p.activity_urn
            WHERE p.text IS NOT NULL AND p.reactions IS NOT NULL
            GROUP BY p.activity_urn
            ORDER BY p.reactions DESC
        """).fetchall()
        posts = [dict(r) for r in rows]
    finally:
        conn.close()

    if len(posts) < 3:
        return {
            "has_evidence": False,
            "message": "Cold start: fewer than 3 settled posts found.",
            "top_exemplars": [],
            "bottom_exemplars": [],
            "contrast_findings": [],
            "brief_section": ""
        }

    top_posts = posts[:limit_top]
    bottom_posts = posts[-limit_bottom:] if len(posts) > limit_top else []

    # Get contrasts
    contrast_res = compute_all_contrasts()
    conclusive_contrasts = [
        c for c in contrast_res.get("contrasts", [])
        if c.get("status") == "conclusive" and c.get("planted_or_significant")
    ]

    contrast_lines = []
    for c in conclusive_contrasts:
        ratio = c.get("ratio", 1.0)
        label = c.get("label", "")
        if ratio > 1.15:
            contrast_lines.append(f"- Posts with {label} went with {ratio}x higher engagement.")
        elif ratio < 0.85:
            contrast_lines.append(f"- Posts with {label} went with lower engagement ({ratio}x).")

    lines = [
        "AUDIENCE PERFORMANCE EVIDENCE (From creator's actual local post history):",
    ]
    if contrast_lines:
        lines.extend(contrast_lines)

    lines.append("TOP PERFORMING EXAMPLES:")
    for p in top_posts:
        excerpt = " ".join((p.get("text") or "").split())[:90]
        q_leads = p.get("qualified_leads", 0)
        rxn = p.get("reactions", 0)
        lines.append(f"- \"{excerpt}...\" ({rxn} reactions, {_people(q_leads)} qualified)")

    brief_section = "\n".join(lines)

    return {
        "has_evidence": True,
        "top_exemplars": top_posts,
        "bottom_exemplars": bottom_posts,
        "contrast_findings": conclusive_contrasts,
        "brief_section": brief_section
    }
