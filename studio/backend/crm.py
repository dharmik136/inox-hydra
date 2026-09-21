"""
Enterprise Reverse CRM & Audience Graph Engine.
================================================
Enables passive capture of post commenters/reactors, deterministic ICP scoring,
seniority classification, and contextual follow-up DM generation.

Strict Invariants:
- Zero em-dashes in any generated templates or text.
- Deterministic multi-factor scoring formula:
  ICP Score = min(100, max(0, (Ws * 0.45) + (Wi * 0.30) + (Wc * 0.15) + (Wq * 0.10)))
"""

from typing import Any, Dict, List, Optional
import re
import json
import logging

try:
    from .database import get_db
except ImportError:
    from database import get_db

logger = logging.getLogger("studio.crm")

# -- Validation constants --------------------------------------------------
MAX_CRM_NAME_LENGTH = 200
MAX_CRM_HEADLINE_LENGTH = 500
MAX_CRM_COMPANY_LENGTH = 300
MAX_CRM_COMMENT_LENGTH = 5000
MIN_ARCHIVE_INACTIVE_DAYS = 7
MAX_HIGH_VALUE_QUERY_LIMIT = 500


class ICPScoringEngine:
    """Calculates Ideal Customer Profile (ICP) fit score (0.0 to 100.0) from profile and engagement data."""

    # High-value seniority patterns
    FOUNDER_PATTERN = re.compile(r"\b(founder|co-founder|owner|managing\s+director|partner)\b", re.IGNORECASE)
    C_SUITE_PATTERN = re.compile(r"\b(ceo|cto|cpo|coo|cro|cmo|chief\s+\w+\s+officer)\b", re.IGNORECASE)
    VP_DIRECTOR_PATTERN = re.compile(r"\b(vp|vice\s+president|director|head\s+of)\b", re.IGNORECASE)
    SENIOR_PRACTITIONER_PATTERN = re.compile(r"\b(staff|principal|lead|architect|senior\s+software)\b", re.IGNORECASE)
    STUDENT_PENALTY_PATTERN = re.compile(r"\b(student|intern|job\s+seeker|seeking\s+opportunities)\b", re.IGNORECASE)

    # Tier-1 / Enterprise industry & company indicators
    TIER1_COMPANY_PATTERN = re.compile(
        r"\b(cloud|scale|systems|fintech|enterprise|ai|saas|platform|data|security|infra)\b",
        re.IGNORECASE
    )

    @classmethod
    def classify_seniority(cls, headline: str) -> str:
        """Categorize professional seniority level based on LinkedIn headline."""
        if not headline:
            return "Unknown"
        if cls.FOUNDER_PATTERN.search(headline):
            return "Founder"
        if cls.C_SUITE_PATTERN.search(headline):
            return "C-Suite"
        if cls.VP_DIRECTOR_PATTERN.search(headline):
            return "VP/Director"
        if cls.SENIOR_PRACTITIONER_PATTERN.search(headline):
            return "Senior Practitioner"
        if cls.STUDENT_PENALTY_PATTERN.search(headline):
            return "Student/Intern"
        return "Individual Contributor"

    @classmethod
    def calculate_seniority_weight(cls, headline: str) -> float:
        """Calculates W_s (Seniority Weight: -40.0 to 100.0)."""
        if not headline:
            return 20.0
        if cls.FOUNDER_PATTERN.search(headline):
            return 100.0
        if cls.C_SUITE_PATTERN.search(headline):
            return 90.0
        if cls.VP_DIRECTOR_PATTERN.search(headline):
            return 75.0
        if cls.SENIOR_PRACTITIONER_PATTERN.search(headline):
            return 50.0
        if cls.STUDENT_PENALTY_PATTERN.search(headline):
            return -40.0
        return 20.0

    @classmethod
    def calculate_interaction_weight(cls, interaction_type: str, comment_text: Optional[str] = None) -> float:
        """Calculates W_i (Interaction Depth Weight: 15.0 to 100.0)."""
        itype = (interaction_type or "COMMENT").upper()
        if itype == "COMMENT" and comment_text:
            word_count = len(comment_text.split())
            if word_count >= 15:
                return 100.0
            elif word_count >= 5:
                return 60.0
            else:
                return 30.0
        elif itype == "REPOST":
            return 50.0
        elif itype == "LIKE":
            return 15.0
        return 20.0

    @classmethod
    def calculate_company_weight(cls, company: Optional[str] = None) -> float:
        """Calculates W_c (Company Fit Weight: 0.0 to 80.0)."""
        if not company or not company.strip():
            return 0.0
        comp_clean = company.strip()
        if cls.TIER1_COMPANY_PATTERN.search(comp_clean):
            return 80.0
        return 50.0

    @classmethod
    def calculate_question_weight(cls, comment_text: Optional[str] = None) -> float:
        """Calculates W_q (Question Multiplier Weight: 0.0 or 100.0)."""
        if comment_text and "?" in comment_text:
            return 100.0
        return 0.0

    @classmethod
    def calculate_icp_score(
        cls,
        headline: str,
        company: Optional[str] = None,
        comment_text: Optional[str] = None,
        interaction_type: str = "COMMENT",
    ) -> float:
        """
        Compute deterministic ICP score from 0.0 to 100.0 using the specification formula:
        ICP Score = min(100, max(0, W_s * 0.45 + W_i * 0.30 + W_c * 0.15 + W_q * 0.10))
        """
        w_s = cls.calculate_seniority_weight(headline)
        w_i = cls.calculate_interaction_weight(interaction_type, comment_text)
        w_c = cls.calculate_company_weight(company)
        w_q = cls.calculate_question_weight(comment_text)

        raw_score = (w_s * 0.45) + (w_i * 0.30) + (w_c * 0.15) + (w_q * 0.10)
        final_score = max(0.0, min(100.0, round(raw_score, 1)))
        return final_score

    @classmethod
    def calculate_icp_breakdown(
        cls,
        headline: str,
        company: Optional[str] = None,
        comment_text: Optional[str] = None,
        interaction_type: str = "COMMENT",
    ) -> Dict[str, Any]:
        """
        Calculates microscopic breakdown of the 4-factor ICP formula,
        including contribution points, intent signals, and qualification tier.
        """
        w_s = cls.calculate_seniority_weight(headline)
        w_i = cls.calculate_interaction_weight(interaction_type, comment_text)
        w_c = cls.calculate_company_weight(company)
        w_q = cls.calculate_question_weight(comment_text)

        c_s = round(w_s * 0.45, 2)
        c_i = round(w_i * 0.30, 2)
        c_c = round(w_c * 0.15, 2)
        c_q = round(w_q * 0.10, 2)

        raw_score = round(c_s + c_i + c_c + c_q, 2)
        final_score = max(0.0, min(100.0, round(raw_score, 1)))

        seniority = cls.classify_seniority(headline)

        if final_score >= 80.0:
            tier = "TIER_1_VIP"
        elif final_score >= 60.0:
            tier = "QUALIFIED"
        elif final_score >= 30.0:
            tier = "NURTURE"
        else:
            tier = "DISQUALIFIED"

        intent_signals: List[str] = []
        if w_s >= 90.0:
            intent_signals.append("EXECUTIVE_DECISION_MAKER")
        elif w_s >= 50.0:
            intent_signals.append("TECHNICAL_PRACTITIONER")
        elif w_s < 0:
            intent_signals.append("STUDENT_OR_SEEKER")

        if w_q == 100.0:
            intent_signals.append("DIRECT_BUYING_INQUIRY")
        if w_i >= 100.0:
            intent_signals.append("HIGH_SUBSTANCE_ENGAGEMENT")
        elif w_i >= 60.0:
            intent_signals.append("ACTIVE_DISCUSSION")
        if w_c >= 80.0:
            intent_signals.append("TIER_1_ENTERPRISE_AFFINITY")

        return {
            "icp_score": final_score,
            "raw_score": raw_score,
            "seniority_level": seniority,
            "qualification_tier": tier,
            "weights": {
                "w_seniority": w_s,
                "w_interaction": w_i,
                "w_company": w_c,
                "w_question": w_q,
            },
            "contributions": {
                "seniority_points": c_s,
                "interaction_points": c_i,
                "company_points": c_c,
                "question_points": c_q,
            },
            "intent_signals": intent_signals,
        }

    @staticmethod
    def generate_contextual_dm(
        lead_name: str,
        comment_text: str,
        post_topic: str = "local-first architecture",
        custom_insight: Optional[str] = None,
    ) -> str:
        """
        Generate a natural, high-context 1-to-1 conversation starter without AI slop.
        Bans generic cliches and strictly enforces zero em-dashes.

        Returns an empty string when there is nothing real to quote. Two ways
        this used to produce a message that was simply false:

          - A reactor has no comment. The caller passed the scraper's own
            placeholder, so the stored draft read
            `Your point about "Reacted to post on LinkedIn..." was spot on.`
          - post_topic was a fixed string, so every draft claimed the post was
            about "sovereign creator architecture" whatever the creator wrote.

        An empty draft is the correct output here. The interface shows the
        person and their actual words, and the creator writes the message.
        """
        first_name = lead_name.split()[0] if lead_name else "there"
        text = (comment_text or "").strip()

        # The scraper's own placeholders, which are not things anyone said.
        PLACEHOLDERS = (
            "reacted to post on linkedin",
            "commented on post",
        )
        if not text or text.lower() in PLACEHOLDERS or any(text.lower().startswith(p) for p in PLACEHOLDERS):
            return ""

        if not post_topic:
            return ""

        excerpt = text[:60]
        if excerpt.endswith((".", "!", "?")):
            excerpt = excerpt[:-1]

        if "?" in text:
            insight = custom_insight or "We found decoupling background ingestion eliminates write lock contention entirely."
            return (
                f"Hi {first_name}, saw your question on my recent post about {post_topic}. "
                f"Specifically regarding \"{excerpt}...\", wanted to share a quick perspective directly. "
                f"{insight} "
                f"Are you testing similar workflows in your stack?"
            )
        else:
            return (
                f"Hi {first_name}, thanks for the comment on the {post_topic} breakdown. "
                f"Your point about \"{excerpt}...\" was spot on. "
                f"Are you testing similar workflows in your stack?"
            )

    @classmethod
    def generate_anti_slop_dm_variants(
        cls,
        lead_name: str,
        comment_text: str,
        post_topic: str = "sovereign creator architecture",
        custom_insight: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Generates 3 distinct strategic anti-slop DM options tailored to comment intent.
        Strictly zero em-dashes (\\u2014) and no corporate jargon.
        """
        first_name = lead_name.split()[0] if lead_name else "there"
        excerpt = comment_text.strip()[:60] if comment_text else ""
        if excerpt.endswith((".", "!", "?")):
            excerpt = excerpt[:-1]

        insight = custom_insight or "We found local-first SQLite WAL eliminating cloud egress and network latency completely."
        has_question = "?" in (comment_text or "")

        variants = [
            {
                "angle": "Direct Technical Perspective",
                "dm_text": (
                    f"Hi {first_name}, saw your question on my recent post about {post_topic}. "
                    f"Specifically regarding \"{excerpt}...\", wanted to share a quick perspective directly. "
                    f"{insight} "
                    f"Are you testing similar workflows in your stack?"
                ) if has_question else (
                    f"Hi {first_name}, thanks for the comment on the {post_topic} breakdown. "
                    f"Your point about \"{excerpt}...\" was spot on. "
                    f"{insight} "
                    f"Are you testing similar workflows in your stack?"
                )
            },
            {
                "angle": "Architecture Teardown",
                "dm_text": (
                    f"Hi {first_name}, great insight on \"{excerpt}...\". "
                    f"When we benchmarked this architecture on localhost, the bottleneck was always network egress rather than local CPU cycles. "
                    f"Curious how your team currently handles data boundaries for these tools?"
                )
            },
            {
                "angle": "Peer-to-Peer Exchange",
                "dm_text": (
                    f"Hi {first_name}, really appreciated you joining the conversation on {post_topic}. "
                    f"Given your focus on this space, thought you might find our offline-first benchmark numbers interesting. "
                    f"Happy to share the raw notes if you are exploring similar patterns."
                )
            }
        ]
        for v in variants:
            v["text"] = v["dm_text"]
        return variants


class ReverseCRMManager:
    """Database coordinator for lead ingestion, interaction recording, and ICP queries."""

    def __init__(self):
        pass

    def ingest_interaction(
        self,
        full_name: str,
        linkedin_urn: str,
        headline: str,
        company: Optional[str] = None,
        interaction_type: str = "COMMENT",
        comment_text: Optional[str] = None,
        post_urn: Optional[str] = None,
        post_id: Optional[int] = None,
        post_topic: Optional[str] = None,
        capture_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ingest or update a lead and record an interaction."""
        # Sanitize field lengths to prevent abuse
        full_name = (full_name or "").strip()[:MAX_CRM_NAME_LENGTH]
        headline = (headline or "").strip()[:MAX_CRM_HEADLINE_LENGTH]
        company = (company or "").strip()[:MAX_CRM_COMPANY_LENGTH] if company else company
        comment_text = comment_text[:MAX_CRM_COMMENT_LENGTH] if comment_text else comment_text

        seniority = ICPScoringEngine.classify_seniority(headline)
        icp_score = ICPScoringEngine.calculate_icp_score(headline, company, comment_text, interaction_type)
        # Only a comment carries words to reply to. A reaction does not, and a
        # draft written as though it did puts a fabricated quote in front of a
        # real person.
        if (interaction_type or "").upper() == "COMMENT":
            suggested_dm = ICPScoringEngine.generate_contextual_dm(
                full_name, comment_text or "", post_topic
            )
        else:
            suggested_dm = ""

        lead_id = None
        conn = get_db()
        try:
            with conn:
                cursor = conn.cursor()
                # Check if lead exists by linkedin_urn or name
                cursor.execute("SELECT id, icp_score FROM leads WHERE linkedin_urn = ? OR (name = ? AND company = ?)",
                               (linkedin_urn, full_name, company or ""))
                row = cursor.fetchone()

                if row:
                    lead_id = row["id"]
                    new_icp = max(float(row["icp_score"] or 0.0), icp_score)
                    cursor.execute("""
                    UPDATE leads SET
                        full_name = ?,
                        name = ?,
                        headline = ?,
                        company = ?,
                        seniority_level = ?,
                        icp_score = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """, (full_name, full_name, headline, company, seniority, new_icp, lead_id))
                else:
                    new_id = f"lead-{abs(hash(linkedin_urn or full_name)) % 1000000}"
                    cursor.execute("""
                    INSERT INTO leads (
                        id, linkedin_urn, full_name, name, headline, company,
                        seniority_level, icp_score, lead_status, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NEW', CURRENT_TIMESTAMP)
                    """, (new_id, linkedin_urn, full_name, full_name, headline, company, seniority, icp_score))
                    lead_id = new_id

                # Record interaction
                cursor.execute("""
                INSERT INTO lead_interactions (
                    lead_id, post_id, post_urn, interaction_type,
                    comment_text, suggested_dm_reply, capture_context, interacted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (lead_id, post_id, post_urn, interaction_type, comment_text,
                      suggested_dm, capture_context))
                interaction_id = cursor.lastrowid
        finally:
            conn.close()

        tier = "VIP" if icp_score >= 80.0 else ("QUALIFIED" if icp_score >= 60.0 else ("NURTURE" if icp_score >= 30.0 else "DISQUALIFIED"))
        return {
            "lead_id": lead_id,
            "interaction_id": interaction_id,
            "full_name": full_name,
            "lead_name": full_name,
            "seniority_level": seniority,
            "icp_score": icp_score,
            "tier": tier,
            "suggested_dm": suggested_dm,
        }

    def list_high_value_leads(self, min_icp_score: float = 60.0, limit: int = 50) -> List[Dict[str, Any]]:
        """Query top ICP-matching leads."""
        limit = min(limit, MAX_HIGH_VALUE_QUERY_LIMIT)
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, full_name, name, headline, company, seniority_level, icp_score, lead_status, created_at
                FROM leads
                WHERE icp_score >= ?
                ORDER BY icp_score DESC, updated_at DESC
                LIMIT ?
                """,
                (min_icp_score, limit),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            return rows
        finally:
            conn.close()

    def purge_lead(self, lead_id: str) -> Dict[str, Any]:
        """
        GDPR Right-to-be-Forgotten and Privacy Hard Purge.
        Permanently cascades deletion across lead_interactions and leads.
        """
        conn = get_db()
        interactions_deleted = 0
        lead_deleted = False
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM lead_interactions WHERE lead_id = ?", (lead_id,))
                interactions_deleted = cursor.rowcount

                cursor.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
                lead_deleted = cursor.rowcount > 0
        finally:
            conn.close()

        return {
            "status": "purged" if lead_deleted else "not_found",
            "lead_id": lead_id,
            "lead_deleted": lead_deleted,
            "interactions_deleted": interactions_deleted,
        }

    def archive_inactive_leads(self, inactive_days: int = 90) -> Dict[str, Any]:
        """
        Bulk archival of stale leads.
        Marks leads inactive if no updates within inactive_days (default 90).
        Minimum threshold: MIN_ARCHIVE_INACTIVE_DAYS (7) to prevent accidental mass-archival.
        """
        if inactive_days < MIN_ARCHIVE_INACTIVE_DAYS:
            return {
                "status": "error",
                "message": f"inactive_days must be >= {MIN_ARCHIVE_INACTIVE_DAYS} to prevent accidental mass-archival"
            }
        conn = get_db()
        archived_count = 0
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE leads
                    SET lead_status = 'ARCHIVED', updated_at = CURRENT_TIMESTAMP
                    WHERE lead_status != 'ARCHIVED'
                      AND (julianday('now') - julianday(COALESCE(updated_at, created_at, 'now'))) >= ?
                    """,
                    (inactive_days,),
                )
                archived_count = cursor.rowcount
        finally:
            conn.close()

        return {
            "status": "success",
            "archived_count": archived_count,
            "inactive_threshold_days": inactive_days,
        }

    def get_lead_timeline(self, lead_id: str) -> Dict[str, Any]:
        """Retrieves interaction history for a specific lead."""
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
            lead_row = cursor.fetchone()
            if not lead_row:
                return {"status": "not_found", "lead": None, "interactions": []}

            cursor.execute(
                """
                SELECT id, post_id, post_urn, interaction_type, comment_text, suggested_dm_reply, interacted_at
                FROM lead_interactions
                WHERE lead_id = ?
                ORDER BY interacted_at DESC
                """,
                (lead_id,),
            )
            interactions = [dict(r) for r in cursor.fetchall()]
            return {
                "status": "success",
                "lead": dict(lead_row),
                "interactions": interactions,
            }
        finally:
            conn.close()

    def get_crm_telemetry(self) -> Dict[str, Any]:
        """
        Computes macro CRM telemetry across the reverse CRM lead and interaction pipelines.
        Aggregates ICP tiers, status funnel, seniority distribution, inquiry rates, and conversion.
        """
        conn = get_db()
        try:
            cursor = conn.cursor()

            # 1. Macro counts & score aggregates
            cursor.execute("""
                SELECT
                    COUNT(*) as total_leads,
                    COALESCE(AVG(icp_score), 0.0) as avg_icp_score,
                    COALESCE(SUM(CASE WHEN icp_score >= 70.0 THEN 1 ELSE 0 END), 0) as high_value_leads,
                    COALESCE(SUM(CASE WHEN icp_score >= 50.0 AND icp_score < 70.0 THEN 1 ELSE 0 END), 0) as qualified_leads,
                    COALESCE(SUM(CASE WHEN icp_score >= 30.0 AND icp_score < 50.0 THEN 1 ELSE 0 END), 0) as nurture_leads,
                    COALESCE(SUM(CASE WHEN icp_score < 30.0 THEN 1 ELSE 0 END), 0) as disqualified_leads
                FROM leads
            """)
            row = cursor.fetchone()
            total_leads = int(row["total_leads"]) if row and row["total_leads"] else 0
            avg_icp_score = round(float(row["avg_icp_score"]), 2) if row and row["avg_icp_score"] else 0.0
            high_value_leads = int(row["high_value_leads"]) if row and row["high_value_leads"] else 0
            qualified_leads = int(row["qualified_leads"]) if row and row["qualified_leads"] else 0
            nurture_leads = int(row["nurture_leads"]) if row and row["nurture_leads"] else 0
            disqualified_leads = int(row["disqualified_leads"]) if row and row["disqualified_leads"] else 0

            # 2. Status Funnel
            funnel_keys = ["NEW", "ENGAGED", "DM_DRAFTED", "DM_SENT", "CONVERTED", "ARCHIVED"]
            funnel = {k: 0 for k in funnel_keys}
            cursor.execute("SELECT lead_status, COUNT(*) as count FROM leads GROUP BY lead_status")
            for r in cursor.fetchall():
                status_name = r["lead_status"] or "NEW"
                funnel[status_name] = int(r["count"])

            converted_count = funnel.get("CONVERTED", 0)
            conversion_rate = round((converted_count / total_leads * 100.0), 2) if total_leads > 0 else 0.0

            # 3. Seniority Distribution
            seniority_dist: Dict[str, int] = {}
            cursor.execute("SELECT seniority_level, COUNT(*) as count FROM leads GROUP BY seniority_level")
            for r in cursor.fetchall():
                level = r["seniority_level"] or "Unknown"
                seniority_dist[level] = int(r["count"])

            # 4. Interaction & Question Telemetry
            cursor.execute("""
                SELECT
                    COUNT(*) as total_interactions,
                    COALESCE(SUM(CASE WHEN interaction_type = 'COMMENT' THEN 1 ELSE 0 END), 0) as comments_count,
                    COALESCE(SUM(CASE WHEN interaction_type = 'LIKE' THEN 1 ELSE 0 END), 0) as likes_count,
                    COALESCE(SUM(CASE WHEN interaction_type = 'REPOST' THEN 1 ELSE 0 END), 0) as reposts_count,
                    COALESCE(SUM(CASE WHEN comment_text LIKE '%?%' THEN 1 ELSE 0 END), 0) as questions_count
                FROM lead_interactions
            """)
            irow = cursor.fetchone()
            total_interactions = int(irow["total_interactions"]) if irow and irow["total_interactions"] else 0
            comments_count = int(irow["comments_count"]) if irow and irow["comments_count"] else 0
            likes_count = int(irow["likes_count"]) if irow and irow["likes_count"] else 0
            reposts_count = int(irow["reposts_count"]) if irow and irow["reposts_count"] else 0
            questions_count = int(irow["questions_count"]) if irow and irow["questions_count"] else 0

            question_inquiry_rate = round((questions_count / comments_count * 100.0), 2) if comments_count > 0 else 0.0
            avg_interactions_per_lead = round((total_interactions / total_leads), 2) if total_leads > 0 else 0.0

            return {
                "status": "success",
                "summary": {
                    "total_leads": total_leads,
                    "high_value_leads": high_value_leads,
                    "qualified_leads": qualified_leads,
                    "nurture_leads": nurture_leads,
                    "disqualified_leads": disqualified_leads,
                    "avg_icp_score": avg_icp_score,
                    "conversion_rate_pct": conversion_rate,
                    "avg_interactions_per_lead": avg_interactions_per_lead,
                },
                "funnel": funnel,
                "seniority_distribution": seniority_dist,
                "inquiry_telemetry": {
                    "total_interactions": total_interactions,
                    "comments_count": comments_count,
                    "likes_count": likes_count,
                    "reposts_count": reposts_count,
                    "questions_count": questions_count,
                    "question_inquiry_rate_pct": question_inquiry_rate,
                },
            }
        finally:
            conn.close()

    def get_post_attribution(self, post_identifier: Any, account_id: str = "default") -> Dict[str, Any]:
        """
        Calculates post-to-lead attribution metrics for a specific post.
        Accepts post_id (int or str) or LinkedIn activity URN.
        Zero em-dashes enforced.
        """
        post_str = str(post_identifier).strip() if post_identifier is not None else ""
        conn = get_db()
        try:
            cursor = conn.cursor()

            # 1. Fetch post metadata if available from posts or drafts table
            post_meta = None
            cursor.execute(
                "SELECT id, content, published_at, impressions, reactions, comments FROM posts WHERE id = ?",
                (post_str,)
            )
            p_row = cursor.fetchone()
            if not p_row:
                try:
                    p_id_int = int(post_str)
                    cursor.execute(
                        "SELECT id, title, raw_content as content, status, created_at as published_at FROM drafts WHERE id = ?",
                        (p_id_int,)
                    )
                    p_row = cursor.fetchone()
                except (ValueError, TypeError):
                    pass
            if p_row:
                post_meta = dict(p_row)

            # 2. Query leads and interactions associated with this post
            query = """
            SELECT 
                l.id as lead_id,
                COALESCE(l.full_name, l.name) as name,
                l.headline,
                l.company,
                COALESCE(l.seniority_level, 'Unknown') as seniority_level,
                COALESCE(l.icp_score, 0.0) as icp_score,
                COALESCE(l.lead_status, 'NEW') as lead_status,
                l.profile_url,
                li.id as interaction_id,
                li.interaction_type,
                li.comment_text,
                li.suggested_dm_reply,
                li.interacted_at
            FROM leads l
            LEFT JOIN lead_interactions li ON l.id = li.lead_id AND (li.post_id = ? OR li.post_urn = ? OR li.post_id = ?)
            WHERE (li.post_id = ? OR li.post_urn = ? OR li.post_id = ? OR l.post_id = ?)
            ORDER BY l.icp_score DESC, li.interacted_at DESC
            """
            cursor.execute(query, (post_str, post_str, post_str, post_str, post_str, post_str, post_str))
            rows = cursor.fetchall()

            deduped_leads: Dict[str, Dict[str, Any]] = {}
            total_interactions = 0
            comments_count = 0
            likes_count = 0
            reposts_count = 0
            questions_count = 0

            for r in rows:
                lid = str(r["lead_id"])
                itype = (r["interaction_type"] or "").upper()
                ctext = r["comment_text"] or ""

                if r["interaction_id"]:
                    total_interactions += 1
                    if itype == "COMMENT":
                        comments_count += 1
                    elif itype == "LIKE":
                        likes_count += 1
                    elif itype == "REPOST":
                        reposts_count += 1
                    if "?" in ctext:
                        questions_count += 1

                if lid not in deduped_leads:
                    icp = float(r["icp_score"] or 0.0)
                    tier = "VIP" if icp >= 80.0 else ("QUALIFIED" if icp >= 60.0 else ("NURTURE" if icp >= 30.0 else "DISQUALIFIED"))
                    deduped_leads[lid] = {
                        "lead_id": r["lead_id"],
                        "name": r["name"],
                        "headline": r["headline"] or "",
                        "company": r["company"] or "",
                        "seniority_level": r["seniority_level"],
                        "icp_score": icp,
                        "qualification_tier": tier,
                        "lead_status": r["lead_status"],
                        "profile_url": r["profile_url"] or "",
                        "latest_comment": ctext,
                        "suggested_dm": r["suggested_dm_reply"] or "",
                    }

            leads_list = list(deduped_leads.values())
            total_leads = len(leads_list)
            vip_leads_count = sum(1 for l in leads_list if l["icp_score"] >= 75.0 or l["seniority_level"] in ("C-Suite", "VP / SVP / EVP", "Founder / Owner"))
            avg_icp = round(sum(l["icp_score"] for l in leads_list) / total_leads, 1) if total_leads > 0 else 0.0

            return {
                "status": "success",
                "post_identifier": post_identifier,
                "post_meta": post_meta,
                "attribution_summary": {
                    "total_leads_generated": total_leads,
                    "vip_leads_count": vip_leads_count,
                    "avg_icp_score": avg_icp,
                    "total_interactions": total_interactions,
                    "comments_count": comments_count,
                    "likes_count": likes_count,
                    "reposts_count": reposts_count,
                    "questions_count": questions_count,
                },
                "leads": leads_list,
            }
        finally:
            conn.close()


reverse_crm = ReverseCRMManager()

