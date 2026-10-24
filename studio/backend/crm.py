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
import sqlite3

try:
    from . import post_summary, results
    from .database import get_db, write_with_retry
    from .migrations import INTERACTION_PLACEHOLDERS, interaction_comment_key
except ImportError:
    import post_summary
    import results
    from database import get_db, write_with_retry
    from migrations import INTERACTION_PLACEHOLDERS, interaction_comment_key

try:
    from .text_cut import clip
except ImportError:
    from text_cut import clip

logger = logging.getLogger("studio.crm")


def _find_lead(cursor, linkedin_urn: Optional[str]):
    """
    The existing lead for this person, found by their profile and nothing else.

    This used to match `linkedin_urn = ? OR (name = ? AND company = ?)`. The
    capture rarely knows a company, so the second half became "same display
    name", and two different people called Rahul Sharma were one lead: the
    creator could then open the dossier of one and quote the other's comment
    to him. Across writers the profile was also spelled differently (with and
    without a trailing slash or query string, http or https), so one person
    could just as easily become two.

    Now only the profile decides, compared by its /in/ identifier. Someone
    without a profile link is never merged into anyone; a duplicate costs far
    less than a wrong merge.
    """
    if not linkedin_urn:
        return None
    match = re.search(r"linkedin\.com/in/([^/?#]+)", linkedin_urn, re.IGNORECASE)
    if not match:
        cursor.execute("SELECT id, icp_score FROM leads WHERE linkedin_urn = ?", (linkedin_urn,))
        return cursor.fetchone()
    # LIKE treats _ and % as wildcards, and both are legal in a vanity, so
    # they are escaped: "asha_k" must not find "ashaxk".
    vanity = match.group(1).lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
    for column in ("linkedin_urn", "profile_url"):
        cursor.execute(
            f"SELECT id, icp_score FROM leads WHERE lower({column}) LIKE ? ESCAPE '!' "
            f"OR lower({column}) LIKE ? ESCAPE '!' OR lower({column}) LIKE ? ESCAPE '!' "
            f"ORDER BY created_at LIMIT 1",
            (f"%linkedin.com/in/{vanity}", f"%linkedin.com/in/{vanity}/%", f"%linkedin.com/in/{vanity}?%"),
        )
        row = cursor.fetchone()
        if row:
            return row
    return None

# How a lead engaged, as the leads table and the first-message drafts word it,
# strongest first. A lead keeps the strongest interaction on record: someone
# who commented and later reacted still commented.
ENGAGEMENT_LABELS = {"COMMENT": "Commented", "REPOST": "Reposted", "LIKE": "Liked"}
_ENGAGEMENT_RANK = {"Commented": 3, "Reposted": 2, "Liked": 1}


def strongest_engagement(current: Optional[str], interaction_type: Optional[str]) -> str:
    """The label to keep after this interaction, given the one already stored."""
    new = ENGAGEMENT_LABELS.get((interaction_type or "").upper(), "Liked")
    if _ENGAGEMENT_RANK.get(current or "", 0) >= _ENGAGEMENT_RANK[new]:
        return current
    return new


# -- Validation constants --------------------------------------------------
MAX_CRM_NAME_LENGTH = 200
MAX_CRM_HEADLINE_LENGTH = 500
MAX_CRM_COMPANY_LENGTH = 300
MAX_CRM_COMMENT_LENGTH = 5000
MIN_ARCHIVE_INACTIVE_DAYS = 7
MAX_HIGH_VALUE_QUERY_LIMIT = 500

# -- Qualification tiers ---------------------------------------------------
# One definition, in results.py, which every screen reads. The same lead used
# to be VIP on one screen and not another: tiers were cut at 80/60/30 in four
# places, the CRM summary counted "high value" from 70 and "qualified" from
# 50, and the top tier was called VIP in two places and TIER_1_VIP in two
# others. These names are kept because the whole backend reads them.
VIP_THRESHOLD = results.VIP_SCORE
QUALIFIED_THRESHOLD = results.QUALIFIED_SCORE
NURTURE_THRESHOLD = results.NURTURE_SCORE
qualification_tier = results.tier


def stable_lead_key(identity: str) -> str:
    """
    A deterministic id for a person, derived from how they are identified.

    This was abs(hash(identity)) % 1000000. Python randomises hash() per
    process unless PYTHONHASHSEED is fixed, so the same profile produced a
    different id on every restart: measured at 32333, 827572 and 711202 across
    three runs of the same input. Re-capturing someone therefore created a new
    lead rather than matching the existing one.

    A million buckets is also too few. At a thousand leads the birthday bound
    puts a collision near 39 percent, and a collision here is an IntegrityError
    on the primary key in the middle of a capture.

    sha256 is deterministic across processes and machines, and twelve hex
    characters give 48 bits, which is ample for a personal CRM.
    """
    import hashlib

    return hashlib.sha256((identity or "").encode("utf-8")).hexdigest()[:12]


class ICPScoringEngine:
    """Calculates Ideal Customer Profile (ICP) fit score (0.0 to 100.0) from profile and engagement data."""

    # High-value seniority patterns
    # Bare "owner" and "partner" matched Product Owner, Process Owner, HR
    # Business Partner and Channel Partner, all scored as founders at 100.
    # Only the forms that mean owning or running the firm count.
    FOUNDER_PATTERN = re.compile(
        r"\b(founder|co-founder|managing\s+director|managing\s+partner|founding\s+partner"
        r"|general\s+partner|business\s+owner|owner\s+(?:at|of)|partner\s+at)\b",
        re.IGNORECASE,
    )
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
    def blend(cls, w_s: float, w_i: float, w_c: float, w_q: float) -> float:
        """
        The formula, written once: every caller blends the four weights here.

        Kept separate from calculate_icp_score because who a person is (their
        seniority and company weights) is read from their row once, while the
        engagement weights are read per engagement: recomputing 49,142 people
        from 500,000 engagements classifies the headline once each instead of
        half a million times (548 ms against ten seconds).
        """
        raw_score = (w_s * 0.45) + (w_i * 0.30) + (w_c * 0.15) + (w_q * 0.10)
        return max(0.0, min(100.0, round(raw_score, 1)))

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
        return cls.blend(cls.calculate_seniority_weight(headline),
                         cls.calculate_interaction_weight(interaction_type, comment_text),
                         cls.calculate_company_weight(company),
                         cls.calculate_question_weight(comment_text))

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
        # The score itself from the one formula, so a breakdown cannot add up
        # to a different number than the score beside it.
        final_score = cls.blend(w_s, w_i, w_c, w_q)

        seniority = cls.classify_seniority(headline)

        tier = qualification_tier(final_score)

        intent_signals: List[str] = []
        if w_s >= 90.0:
            intent_signals.append("EXECUTIVE_DECISION_MAKER")
        elif w_s >= 50.0:
            intent_signals.append("TECHNICAL_PRACTITIONER")
        elif w_s < 0:
            intent_signals.append("STUDENT_OR_SEEKER")

        # Named for what it detects. It was DIRECT_BUYING_INQUIRY, raised by any
        # "?" at all, so "Who else agrees?" was flagged as a buying signal.
        if w_q == 100.0:
            intent_signals.append("ASKED_A_QUESTION")
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
        post_topic: Optional[str] = None,
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

        excerpt = clip(text, 60)
        if excerpt.endswith((".", "!", "?")):
            excerpt = excerpt[:-1]

        # The creator's own words, only when they supplied some. This used to
        # fall back to a canned sentence, "We found decoupling background
        # ingestion eliminates write lock contention entirely.", sent under
        # the creator's name as a finding they never made. The closing
        # question, "Are you testing similar workflows in your stack?", and
        # "the ... breakdown" were the original author's world as well, and a
        # question reply promised "a quick perspective" it never gave.
        insight = f"{custom_insight.strip()} " if custom_insight and custom_insight.strip() else ""
        if "?" in text:
            return (
                f"Hi {first_name}, saw your question on my recent post about {post_topic}: "
                f"\"{excerpt}...\" "
                f"{insight}"
                f"Happy to go into it here if that would help."
            )
        else:
            return (
                f"Hi {first_name}, thanks for the comment on my post about {post_topic}. "
                f"Your point about \"{excerpt}...\" was spot on. "
                f"{insight}"
                f"Would you be open to connecting here?"
            )

    @classmethod
    def generate_anti_slop_dm_variants(
        cls,
        lead_name: str,
        comment_text: str,
        post_topic: Optional[str] = None,
        custom_insight: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Generates 3 distinct strategic anti-slop DM options tailored to comment intent.
        Strictly zero em-dashes (\\u2014) and no corporate jargon.
        """
        first_name = lead_name.split()[0] if lead_name else "there"
        excerpt = clip(comment_text.strip(), 60) if comment_text else ""
        if excerpt.endswith((".", "!", "?")):
            excerpt = excerpt[:-1]

        # Nothing below is a claim the creator did not make. These used to carry
        # a default topic ("sovereign creator architecture"), a canned finding
        # presented as the creator's, and two invented results: "When we
        # benchmarked this architecture on localhost..." and "our offline-first
        # benchmark numbers". A prospect reads any of those as something the
        # creator did. The topic and the insight now appear only when supplied,
        # and the other two angles ask rather than assert.
        insight = f"{custom_insight.strip()} " if custom_insight and custom_insight.strip() else ""
        topic = (post_topic or "").strip()
        about = f" about {topic}" if topic else ""
        on = f" on {topic}" if topic else ""
        has_question = "?" in (comment_text or "")

        variants = [
            {
                "angle": "Direct Technical Perspective",
                "dm_text": (
                    f"Hi {first_name}, saw your question on my recent post{about}: "
                    f"\"{excerpt}...\" "
                    f"{insight}"
                    f"Happy to go into it here if that would help."
                ) if has_question else (
                    f"Hi {first_name}, thanks for the comment on my recent post{about}. "
                    f"Your point about \"{excerpt}...\" was spot on. "
                    f"{insight}"
                    f"Would you be open to connecting here?"
                )
            },
            {
                "angle": "Architecture Teardown",
                "dm_text": (
                    f"Hi {first_name}, your point about \"{excerpt}...\" stayed with me. "
                    f"What led you to it? I would like to understand how it plays out on your side."
                )
            },
            {
                "angle": "Peer-to-Peer Exchange",
                "dm_text": (
                    f"Hi {first_name}, really appreciated you joining the conversation{on}. "
                    f"Would you be open to comparing notes on what you are working on?"
                )
            }
        ]
        for v in variants:
            v["text"] = v["dm_text"]
        return variants


# ---------------------------------------------------------------------------
# Scores that are current
# ---------------------------------------------------------------------------
#
# icp_score was written once, at capture, and never recomputed. Measured on
# one creator's three years: the stored scores said 0 of 49,142 people
# qualified, while this engine on the same headlines and the same comments
# qualified 11,767 of them. Every screen read the stored number, which is why
# Patterns told a creator with 49,142 captured people that none qualified.
#
# So the score is a derived value with a stale mark, exactly as the per-post
# summary is (post_summary.py): migration 27's triggers mark a lead whenever
# anything the score is computed from changes (their headline, their company,
# an interaction added, changed or removed), and the readers below bring the
# marked ones current before anything counts them.
#
# The other option was to recompute on every read. Measured on the same data:
# 548 ms to walk 500,000 interactions and score 49,142 leads, on every screen
# that counts qualified people, against a 100 ms budget for a whole endpoint.
# One lead's recompute is a single indexed read, so marking is the cheap way
# round.

# Leads recomputed per transaction, so a capture waiting for the write lock
# waits for one batch at most.
SCORE_BATCH = 500
_SCORE_WAIT_MS = 250


def score_of(headline: Optional[str], company: Optional[str],
             interactions: List[Any]) -> Optional[float]:
    """
    A lead's score: the best of their recorded engagements, judged against who
    they are now, and None for a person with no engagement recorded.

    The same walk a re-capture does (ingest_interaction), in one place, so a
    backfilled score and a captured score cannot differ. Half the score is the
    engagement, so a person nobody has seen engage has no score rather than a
    low one, and the dossier says "not scored" instead of inventing a tier.
    """
    scores = [ICPScoringEngine.calculate_icp_score(headline, company, row["comment_text"],
                                                   row["interaction_type"])
              for row in interactions]
    return max(scores) if scores else None


def _scores_by_seek(cursor, rows) -> Dict[str, Optional[float]]:
    """
    Each lead's score, reading their own engagements by the index that starts
    with lead_id. For a handful of leads, which is what a capture marks.
    """
    return {row["id"]: score_of(row["headline"], row["company"], cursor.execute(
        "SELECT interaction_type, comment_text FROM lead_interactions WHERE lead_id = ?",
        (row["id"],)).fetchall()) for row in rows}


def _scores_in_one_pass(cursor, rows) -> Dict[str, Optional[float]]:
    """
    Every named lead's score in one pass over the engagements, for a backfill.

    lead_interactions.lead_id is declared INTEGER while leads.id is TEXT, so a
    filter on a list of ids can use no index from the interaction side (the
    phase 3 rebuild fixes the column). Reading every engagement once is 433 ms
    at 500,000; filtering 98 batches of 500 against them was 9.8 s.

    Who a person is is weighed once each here, and only their engagements are
    weighed per row, which is what makes one pass affordable. The formula is
    still ICPScoringEngine.blend.
    """
    engine = ICPScoringEngine
    profile = {row["id"]: (engine.calculate_seniority_weight(row["headline"]),
                           engine.calculate_company_weight(row["company"])) for row in rows}
    best: Dict[str, Optional[float]] = {lead: None for lead in profile}
    for lead_id, interaction_type, comment_text in cursor.execute(
            "SELECT CAST(lead_id AS TEXT), interaction_type, comment_text FROM lead_interactions"):
        weights = profile.get(lead_id)
        if weights is None:
            continue
        score = engine.blend(weights[0], engine.calculate_interaction_weight(interaction_type, comment_text),
                             weights[1], engine.calculate_question_weight(comment_text))
        if best[lead_id] is None or score > best[lead_id]:
            best[lead_id] = score
    return best


# Above this many marked leads, their engagements are read in one pass rather
# than sought one lead at a time.
SCORE_BULK_FROM = 200


def recompute_scores(conn, lead_ids: List[str]) -> int:
    """
    Writes the current score and seniority of the leads named, inside the
    caller's transaction, and clears their marks. Returns how many moved.
    """
    if not lead_ids:
        return 0
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT id, headline, company, icp_score FROM leads WHERE id IN (SELECT value FROM json_each(?))",
        (json.dumps(lead_ids),)).fetchall()
    scored = (_scores_in_one_pass(cursor, rows) if len(rows) > SCORE_BULK_FROM
              else _scores_by_seek(cursor, rows))
    moved = 0
    for row in rows:
        score = scored.get(row["id"])
        if (row["icp_score"] is None) != (score is None) or (
                score is not None and row["icp_score"] is not None
                and abs(float(row["icp_score"]) - score) > 1e-9):
            moved += 1
        # Written even when it has not moved, because the mark has to clear
        # and the trigger only fires on a real change.
        cursor.execute(
            "UPDATE leads SET icp_score = ?, seniority_level = ?, icp_stale = 0 WHERE id = ?",
            (score, ICPScoringEngine.classify_seniority(row["headline"]), row["id"]))
    # Marks on leads that no longer exist would otherwise be looked at for ever.
    cursor.execute("UPDATE leads SET icp_stale = 0 WHERE id IN (SELECT value FROM json_each(?))",
                   (json.dumps(lead_ids),))
    return moved


def _marked_leads(conn, batch: Optional[int] = None) -> List[str]:
    limit = "" if batch is None else f" LIMIT {int(batch):d}"
    return [row[0] for row in conn.execute(f"SELECT id FROM leads WHERE icp_stale != 0{limit}")]


def catch_up_scores(conn, batch: int = SCORE_BATCH) -> int:
    """
    Brings every marked lead's score current, a batch to a transaction, so a
    capture waiting for the lock waits for one batch at most. Stops early and
    leaves the rest marked when another writer keeps the lock, as the per-post
    summary's catch-up does. Returns how many scores moved.
    """
    try:
        if not conn.execute("SELECT 1 FROM leads WHERE icp_stale != 0 LIMIT 1").fetchone():
            return 0
    except sqlite3.OperationalError:
        # Before migration 27 there is no mark, and the stored score is all
        # there is. A reader must not fail over that.
        return 0
    if conn.in_transaction:
        return recompute_scores(conn, _marked_leads(conn))
    # A backfill (migration 27 marks every lead) is one pass over the
    # engagements and one transaction, the way the per-post summary's own
    # rebuild is: measured on three years, 1.5 s for 49,142 leads against
    # 9.8 s for ninety-eight batches that each read the engagements again.
    # Everything smaller than that is a capture's handful of leads.
    marked = conn.execute("SELECT COUNT(*) FROM leads WHERE icp_stale != 0").fetchone()[0]
    if marked > SCORE_BULK_FROM:
        batch = marked
    moved = 0
    previous = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    conn.execute(f"PRAGMA busy_timeout = {_SCORE_WAIT_MS:d}")
    try:
        while True:
            if not conn.execute("SELECT 1 FROM leads WHERE icp_stale != 0 LIMIT 1").fetchone():
                break
            conn.execute("BEGIN IMMEDIATE")
            marked = _marked_leads(conn, batch)
            if marked:
                moved += recompute_scores(conn, marked)
            conn.commit()
            if len(marked) < batch:
                break
    except sqlite3.OperationalError:
        if conn.in_transaction:
            conn.rollback()
    finally:
        conn.execute(f"PRAGMA busy_timeout = {int(previous)}")
    return moved


def scores_current(conn) -> int:
    """
    What a reader calls before counting qualified people: the scores of leads
    whose inputs have changed are recomputed first, so a stale one cannot
    survive a single screen load.
    """
    return catch_up_scores(conn)


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
        full_name = clip((full_name or "").strip(), MAX_CRM_NAME_LENGTH)
        headline = clip((headline or "").strip(), MAX_CRM_HEADLINE_LENGTH)
        company = clip((company or "").strip(), MAX_CRM_COMPANY_LENGTH) if company else company
        comment_text = clip(comment_text, MAX_CRM_COMMENT_LENGTH) if comment_text else comment_text
        # The capture's own placeholders are not words anybody wrote. Stored as
        # comment text, "Reacted to post on LinkedIn" was shown in the dossier
        # as the person's comment, beside a Reply button that could only fail.
        if comment_text and comment_text.strip().lower() in INTERACTION_PLACEHOLDERS:
            comment_text = None

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

        # A capture that found the write lock held was refused outright, and
        # the person the extension had just captured was lost with it. The
        # whole write, its connection and its transaction, is made again
        # while SQLite says the database is locked: nothing of a refused
        # attempt is left behind, so a second one is the same as the
        # extension having sent this capture a moment later.
        def write():
            lead_id = None
            interaction_id = None
            icp = icp_score
            conn = get_db()
            try:
                with conn:
                    cursor = conn.cursor()
                    row = _find_lead(cursor, linkedin_urn)
                    # The capture sends the profile URL as linkedin_urn. The rest
                    # of the studio reads profile_url, which stayed empty.
                    profile_url = linkedin_urn if (linkedin_urn or "").lower().startswith("http") else None

                    if row:
                        lead_id = row["id"]
                        stored = cursor.execute(
                            "SELECT engagement_type FROM leads WHERE id = ?", (lead_id,)
                        ).fetchone()["engagement_type"]
                        cursor.execute(
                            "UPDATE leads SET engagement_type = ?, "
                            "profile_url = COALESCE(NULLIF(profile_url, ''), ?) WHERE id = ?",
                            (strongest_engagement(stored, interaction_type), profile_url, lead_id),
                        )
                        # The score reflects the person as they are now and the
                        # best engagement on record. It was max(old, new), which
                        # only ever rose: after a headline change from CTO to
                        # intern the seniority updated and the score stayed at 95.
                        # Every recorded interaction is scored against the current
                        # headline, with this one, and the result written once. A
                        # provisional score written first and corrected after
                        # marked every post the person had engaged with in the
                        # per-post summary on every capture. score_of is the one
                        # walk, which the catch-up for a lead whose headline
                        # changed outside a capture uses as well.
                        recorded = score_of(headline, company, cursor.execute(
                            "SELECT interaction_type, comment_text FROM lead_interactions WHERE lead_id = ?",
                            (lead_id,)).fetchall())
                        new_icp = icp = icp if recorded is None else max(icp, recorded)
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
                        new_id = f"lead-{stable_lead_key(linkedin_urn or full_name)}"
                        cursor.execute("""
                        INSERT INTO leads (
                            id, linkedin_urn, profile_url, full_name, name, headline, company,
                            seniority_level, icp_score, engagement_type, lead_status, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW', CURRENT_TIMESTAMP)
                        """, (new_id, linkedin_urn, profile_url, full_name, full_name, headline, company,
                              seniority, icp, strongest_engagement(None, interaction_type)))
                        lead_id = new_id

                    # One row per interaction. Reading the same comment again, which
                    # happens every time the post is reopened, updates when it was
                    # last seen instead of counting as a second engagement.
                    cursor.execute("""
                    INSERT INTO lead_interactions (
                        lead_id, post_id, post_urn, interaction_type,
                        comment_text, suggested_dm_reply, capture_context, interacted_at,
                        comment_key, first_seen_at, last_seen_at, seen_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                    ON CONFLICT(lead_id, COALESCE(post_urn, ''), interaction_type, comment_key) DO UPDATE SET
                        last_seen_at = CURRENT_TIMESTAMP,
                        seen_count = lead_interactions.seen_count + 1,
                        post_id = COALESCE(lead_interactions.post_id, excluded.post_id)
                    """, (lead_id, post_id, post_urn, interaction_type, comment_text,
                          suggested_dm, capture_context, interaction_comment_key(comment_text)))
                    interaction_id = cursor.execute(
                        "SELECT id FROM lead_interactions WHERE lead_id = ? AND COALESCE(post_urn, '') = ? "
                        "AND interaction_type = ? AND comment_key = ?",
                        (lead_id, post_urn or "", interaction_type, interaction_comment_key(comment_text)),
                    ).fetchone()[0]

                    # The captured post's summary row is brought current here,
                    # so a capture leaves its post right. A name or score that
                    # moved also marked the person's other posts: those are
                    # caught up after this transaction, in the background and by
                    # the next reader, in small batches, never inside the
                    # capture's hold on the write lock.
                    if post_urn:
                        post_summary.refresh(conn, [post_urn])
            finally:
                conn.close()
            return lead_id, interaction_id, icp

        lead_id, interaction_id, icp_score = write_with_retry("Capturing an engagement", write)
        post_summary.catch_up_later()

        tier = qualification_tier(icp_score)
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

        Every row about the person, in one transaction: their engagements,
        their stage history, any enrichment, and the lead itself. The stage
        history used to be left behind, and since a lead's id is a hash of
        their profile it reattached to them if they engaged again. Every
        removal path calls this; the trigger from migration 19 covers any that
        deletes from leads directly.
        """
        conn = get_db()
        deleted = {"lead_interactions": 0, "lead_stage_events": 0, "lead_enrichments": 0}
        lead_deleted = False
        try:
            with conn:
                cursor = conn.cursor()
                for table in deleted:
                    cursor.execute(f"DELETE FROM {table} WHERE lead_id = ?", (lead_id,))
                    deleted[table] = cursor.rowcount

                cursor.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
                lead_deleted = cursor.rowcount > 0
                # The per-post summary lists people by name; the deletes
                # marked their posts, so recompute them now, or the name
                # stays in the file until a screen next reads those posts.
                post_summary.refresh(conn)
        finally:
            conn.close()

        return {
            "status": "purged" if lead_deleted else "not_found",
            "lead_id": lead_id,
            "lead_deleted": lead_deleted,
            "interactions_deleted": deleted["lead_interactions"],
            "stage_events_deleted": deleted["lead_stage_events"],
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
        finally:
            conn.close()

        # Whether each interaction was on one of your own posts, and that
        # post's opening line: the dossier's one window onto a person's
        # actual engagement with your writing, rather than a lead naming a
        # post the creator has to remember themselves. Unreliable before one
        # post identity existed (it read the post id a capture happened to
        # record, not the one id a post is known by), so it was never wired
        # here.
        try:
            from . import onboarding
        except ImportError:
            import onboarding
        interactions = onboarding.annotate_interactions(interactions)

        return {
            "status": "success",
            "lead": dict(lead_row),
            "interactions": interactions,
        }

    def get_crm_telemetry(self) -> Dict[str, Any]:
        """
        Computes macro CRM telemetry across the reverse CRM lead and interaction pipelines.
        Aggregates ICP tiers, status funnel, seniority distribution, inquiry rates, and conversion.
        """
        conn = get_db()
        try:
            cursor = conn.cursor()

            # 1. Macro counts & score aggregates
            # The same cut points as qualification_tier, so the summary and the
            # lead list count the same people in each tier.
            cursor.execute("""
                SELECT
                    COUNT(*) as total_leads,
                    COALESCE(AVG(icp_score), 0.0) as avg_icp_score,
                    COALESCE(SUM(CASE WHEN icp_score >= :vip THEN 1 ELSE 0 END), 0) as high_value_leads,
                    COALESCE(SUM(CASE WHEN icp_score >= :qual AND icp_score < :vip THEN 1 ELSE 0 END), 0) as qualified_leads,
                    COALESCE(SUM(CASE WHEN icp_score >= :nurt AND icp_score < :qual THEN 1 ELSE 0 END), 0) as nurture_leads,
                    COALESCE(SUM(CASE WHEN icp_score < :nurt THEN 1 ELSE 0 END), 0) as disqualified_leads
                FROM leads
            """, {"vip": VIP_THRESHOLD, "qual": QUALIFIED_THRESHOLD, "nurt": NURTURE_THRESHOLD})
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
                # Accumulate, never assign.
                #
                # GROUP BY returns NULL and '' as two separate groups, and both
                # fold to NEW on the line below, so the second one overwrote
                # the first. Measured: 30 leads with a NULL status and 12 with
                # an empty one gave a funnel reading 12, and 30 leads simply
                # stopped existing as far as every chart was concerned.
                status_name = r["lead_status"] or "NEW"
                # A status outside the known set used to silently add a bucket,
                # so the funnel could grow a category nobody designed. Unknown
                # values are counted where they belong instead.
                if status_name not in funnel:
                    status_name = "NEW"
                funnel[status_name] = funnel.get(status_name, 0) + int(r["count"])

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
                    -- Questions among COMMENTS, because that is what the rate
                    -- is divided by. Counting a question mark on a LIKE or a
                    -- REPOST row put it in the numerator and not the
                    -- denominator, so question_inquiry_rate_pct could exceed
                    -- 100 percent and be presented as a percentage anyway.
                    COALESCE(SUM(CASE WHEN interaction_type = 'COMMENT'
                                       AND comment_text LIKE '%?%'
                                      THEN 1 ELSE 0 END), 0) as questions_count
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

            # The identifiers an interaction could have been recorded under.
            #
            # The caller passes posts.id, which is this application's own key.
            # lead_interactions.post_urn holds what LinkedIn calls the post,
            # and those are different namespaces, so matching one against the
            # other could never succeed. Migration 7 added posts.activity_urn
            # precisely to bridge them; this resolves through it.
            #
            # li.post_id is worse than useless here: it is an INTEGER foreign
            # key into drafts(id), so comparing it to a posts.id string can
            # never match either.
            match_keys = {post_str}
            cursor.execute("SELECT activity_urn FROM posts WHERE id = ?", (post_str,))
            urn_row = cursor.fetchone()
            if urn_row and urn_row["activity_urn"]:
                match_keys.add(urn_row["activity_urn"])

            # The reverse direction, for a caller who already holds the URN.
            cursor.execute("SELECT id FROM posts WHERE activity_urn = ?", (post_str,))
            id_row = cursor.fetchone()
            if id_row and id_row["id"]:
                match_keys.add(str(id_row["id"]))
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
            #
            # Each interaction on the post, by idx_interactions_post, then each
            # lead tied to the post only by leads.post_id. Written as one LEFT
            # JOIN with an OR across the two tables, no index could serve it
            # and every lead was scanned: 386 ms for one post at 49,142 leads.
            # CAST(... AS TEXT) lets the leads key serve the join despite the
            # INTEGER affinity of lead_interactions.lead_id (fixed by the
            # phase 3 rebuild). The last two sort keys are the order the old
            # scan met rows in, so ties come out as they always did.
            columns = """
                l.id as lead_id,
                COALESCE(l.full_name, l.name) as name,
                l.headline,
                l.company,
                COALESCE(l.seniority_level, 'Unknown') as seniority_level,
                COALESCE(l.icp_score, 0.0) as icp_score,
                COALESCE(l.lead_status, 'NEW') as lead_status,
                l.profile_url,
                l.icp_score as sort_score,
                l.rowid as lead_row,
            """
            query = f"""
            SELECT {columns}
                li.id as interaction_id,
                li.interaction_type,
                li.comment_text,
                li.suggested_dm_reply,
                li.interacted_at
            FROM lead_interactions li JOIN leads l ON l.id = CAST(li.lead_id AS TEXT)
            WHERE li.post_urn IN ({{placeholders}})
            UNION ALL
            SELECT {columns}
                NULL, NULL, NULL, NULL, NULL
            FROM leads l
            WHERE l.post_id IN ({{placeholders}})
              AND NOT EXISTS (SELECT 1 FROM lead_interactions li
                              WHERE li.lead_id = l.id AND li.post_urn IN ({{placeholders}}))
            ORDER BY sort_score DESC, interacted_at DESC, lead_row, interaction_id
            """
            keys = sorted(match_keys)
            placeholders = ", ".join("?" for _ in keys)
            query = query.format(placeholders=placeholders)
            cursor.execute(query, tuple(keys) * 3)
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
                    tier = qualification_tier(icp)
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
            # Reactions older than 24 months that the retention job folded
            # (retention.folded_counts): each was a like on this post, and the
            # folded reactors who did nothing else on it are still among its
            # leads, with their tiers as they were. They have no names here.
            fold = {"reactions": 0, "people": 0, "vip": 0, "icp_sum": 0.0}
            for entry in post_summary.folded(conn, keys).values():
                for column in fold:
                    fold[column] += entry.get(column) or 0
            total_interactions += fold["reactions"]
            likes_count += fold["reactions"]
            total_leads = len(leads_list) + fold["people"]
            # The one tier rule, as in the CRM and the CSV. This counted from 75,
            # and from seniority labels classify_seniority never produces.
            vip_leads_count = sum(1 for l in leads_list if l["qualification_tier"] == "TIER_1_VIP") + fold["vip"]
            # A lead with no score counts as 0 here, as it always has; the
            # fold sums only known scores, which is the same total.
            score_sum = round(sum(l["icp_score"] for l in leads_list) + fold["icp_sum"], 6)
            avg_icp = round(score_sum / total_leads, 1) if total_leads > 0 else 0.0

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
                    # Of the likes and leads above, how many are kept only as
                    # counts, so the list below names fewer people.
                    "folded_reactions": fold["reactions"],
                    "folded_leads": fold["people"],
                },
                "leads": leads_list,
            }
        finally:
            conn.close()


reverse_crm = ReverseCRMManager()

