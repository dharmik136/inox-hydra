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

import re
from typing import Dict, Any, List, Optional, Tuple

try:
    from .database import get_db
    from .contrast_engine import compute_all_contrasts
except ImportError:
    from database import get_db
    from contrast_engine import compute_all_contrasts


TOPIC_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("Product & Strategy", re.compile(r"\b(saas|pricing|revenue|growth|product|market|b2b|customer retention)\b", re.IGNORECASE)),
    ("Architecture & Systems", re.compile(r"\b(architecture|distributed|system|database|sqlite|postgres|wal|infrastructure|concurrency|backend)\b", re.IGNORECASE)),
    ("AI & Machine Learning", re.compile(r"\b(ai|llm|agent|model|inference|rag|prompt|gemini|openai|claude|ollama)\b", re.IGNORECASE)),
    ("Leadership & Hiring", re.compile(r"\b(hiring|engineer recruiting|management|culture|interview|career|compensation)\b", re.IGNORECASE)),
]


def classify_post_topic(text: Optional[str]) -> str:
    """Classifies a post text into a distinct topic based on domain regex."""
    if not text:
        return "General Practitioner"
    for topic_name, pattern in TOPIC_PATTERNS:
        if pattern.search(text):
            return topic_name
    return "Practitioner Insights"


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

    # Map post URN to qualified leads count
    leads_per_post: Dict[str, int] = {}
    for row in interactions:
        urn = row["post_urn"]
        icp = row["icp_score"] or 0
        lead_status = (row["lead_status"] or "").upper()
        status = (row["status"] or "").lower()
        is_qualified = (icp >= 60.0) or (lead_status in ("ENGAGED", "CONVERTED")) or ("connected" in status or "meeting" in status)
        if is_qualified:
            leads_per_post[urn] = leads_per_post.get(urn, 0) + 1

    # Aggregate by topic
    topic_aggregates: Dict[str, Dict[str, Any]] = {}
    for p in posts:
        urn = p.get("activity_urn") or ""
        topic = classify_post_topic(p.get("text"))
        q_leads = leads_per_post.get(urn, 0)
        rxn = p.get("reactions") or 0

        entry = topic_aggregates.setdefault(topic, {
            "topic": topic,
            "posts_count": 0,
            "post_count": 0,
            "total_reactions": 0,
            "qualified_leads": 0
        })
        entry["posts_count"] += 1
        entry["post_count"] += 1
        entry["total_reactions"] += rxn
        entry["qualified_leads"] += q_leads

    topic_list = sorted(
        topic_aggregates.values(),
        key=lambda t: (t["qualified_leads"], t["total_reactions"]),
        reverse=True
    )

    for t in topic_list:
        t["lead_conversion_rate"] = round(t["qualified_leads"] / max(1, t["posts_count"]), 4)
        t["summary"] = f"{t['qualified_leads']} qualified leads from {t['posts_count']} posts"

    if len(topic_list) >= 2:
        top = topic_list[0]
        bottom = topic_list[-1]
        summary_sentence = (
            f"Your {top['topic']} posts: {top['qualified_leads']} qualified leads from {top['posts_count']} posts. "
            f"{bottom['topic']}: {bottom['qualified_leads']} from {bottom['posts_count']}."
        )
    elif topic_list:
        top = topic_list[0]
        summary_sentence = f"Your {top['topic']} posts: {top['qualified_leads']} qualified leads from {top['posts_count']} posts."
    else:
        summary_sentence = "No topic attribution available yet."

    return {
        "status": "success",
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
        rows = conn.execute("""
            SELECT p.activity_urn, p.text, p.reactions, p.comments,
                   COUNT(CASE WHEN l.icp_score >= 60 THEN 1 END) AS qualified_leads
            FROM own_posts p
            LEFT JOIN lead_interactions i ON i.post_urn = p.activity_urn
            LEFT JOIN leads l ON l.id = i.lead_id
            WHERE p.text IS NOT NULL AND p.reactions IS NOT NULL
            GROUP BY p.activity_urn
            ORDER BY qualified_leads DESC, p.reactions DESC
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
        lines.append(f"- \"{excerpt}...\" ({rxn} reactions, {q_leads} qualified leads)")

    brief_section = "\n".join(lines)

    return {
        "has_evidence": True,
        "top_exemplars": top_posts,
        "bottom_exemplars": bottom_posts,
        "contrast_findings": conclusive_contrasts,
        "brief_section": brief_section
    }
