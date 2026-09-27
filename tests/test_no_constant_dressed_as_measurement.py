"""
Numbers the studio shows must be measured, or labelled as what they are.
========================================================================

Audit W15 to W17.

W15. Generated hooks carried predicted_score: 92 if the hook fit the fold, 80
if not. The composer showed it as "SCORE 92", a forecast nobody made.

W16. Swipe templates carry velocity_score and engagement_multiplier values that
were typed in by the template's author. The interface called the first
"VELOCITY", which reads as a rate someone observed. It is an editorial rating,
and is now labelled as one.

W17. The fold limit was 140 in the formatter and 180 in the copilot, so one
draft could be fold-safe on one screen and truncated on another.
"""

import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI = os.path.join(REPO_ROOT, "studio", "ui", "src")


def _ui(path):
    with open(os.path.join(UI, path), encoding="utf-8") as handle:
        source = handle.read()
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//[^\n]*$", "", source)


def test_generated_hooks_carry_no_invented_score():
    import repurposer

    for hook in repurposer.generate_10x_hooks("Most migrations fail because nobody owns the rollback."):
        assert "predicted_score" not in hook, "a hook is given a score that predicts nothing"
    assert "predicted_score" not in _ui("components/HookFilmstrip.tsx")
    assert "predicted_score" not in _ui("lib/api.ts")


def test_a_typed_rating_is_not_called_velocity():
    for path in ("components/HookFilmstrip.tsx", "components/SwipeSurface.tsx"):
        source = _ui(path)
        assert not re.search(r'"VELOCITY"|>\s*VELOCITY\b|\bVELOCITY \{', source), (
            f"{path} labels an author's typed rating as a measured velocity"
        )


def test_every_fold_check_uses_one_limit():
    import fold
    from agno_agentos.scar_tissue import validate_pre_fold_hook
    from agno_agentos.agents import content_copilot_agent
    import ingress

    assert validate_pre_fold_hook("x" * (fold.MOBILE_FOLD_CHARS + 1))[0] is False
    assert validate_pre_fold_hook("x" * fold.MOBILE_FOLD_CHARS)[0] is True
    assert content_copilot_agent.HOOK_FOLD_LIMIT == fold.MOBILE_FOLD_CHARS
    assert ingress.MOBILE_FOLD_CHAR_LIMIT == fold.MOBILE_FOLD_CHARS

    for base, _dirs, files in os.walk(os.path.join(REPO_ROOT, "studio", "backend")):
        for name in files:
            if not name.endswith(".py"):
                continue
            with open(os.path.join(base, name), encoding="utf-8") as handle:
                text = handle.read()
            assert "max_chars=180" not in text and "180-char fold" not in text, (
                f"{name} carries its own fold limit again"
            )


# ---------------------------------------------------------------------------
# W13, W14, W18
# ---------------------------------------------------------------------------

def test_a_product_owner_is_not_a_founder():
    from crm import ICPScoringEngine

    for title in ("Product Owner", "Process Owner", "HR Business Partner", "Channel Partner Manager"):
        assert ICPScoringEngine.calculate_seniority_weight(title) < 100.0, f"{title} scored as a founder"
    for title in ("Co-Founder & CEO", "Managing Partner", "Owner at Loomwork", "Business Owner"):
        assert ICPScoringEngine.calculate_seniority_weight(title) == 100.0, f"{title} is no longer recognised"


def test_a_question_is_not_called_a_buying_inquiry():
    from crm import ICPScoringEngine

    breakdown = ICPScoringEngine.calculate_icp_breakdown(
        headline="Engineer", company=None, comment_text="Who else agrees?", interaction_type="COMMENT")
    assert "DIRECT_BUYING_INQUIRY" not in breakdown["intent_signals"]
    assert "ASKED_A_QUESTION" in breakdown["intent_signals"]


def test_one_tier_definition_everywhere():
    import crm
    import leads

    assert crm.qualification_tier(79.9) == "QUALIFIED" and crm.qualification_tier(80) == "TIER_1_VIP"
    for module in (crm, leads):
        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        assert not re.search(r'"VIP" if', source), f"{module.__name__} cuts its own tiers again"
        assert ">= 70.0" not in source, f"{module.__name__} counts high value from a different threshold"


def test_the_score_follows_the_headline_down():
    """It was max(old, new), so a lead could only ever rise."""
    from crm import reverse_crm
    from database import get_db

    profile = "https://www.linkedin.com/in/ratchet-probe-lead"
    try:
        high = reverse_crm.ingest_interaction("Ratchet Probe", profile, "Chief Technology Officer", "Loomwork",
                                              "COMMENT", "Short note.")
        low = reverse_crm.ingest_interaction("Ratchet Probe", profile, "Student", "Loomwork",
                                             "COMMENT", "Short note.")
        assert low["lead_id"] == high["lead_id"]
        conn = get_db()
        stored = conn.execute("SELECT icp_score FROM leads WHERE id = ?", (low["lead_id"],)).fetchone()[0]
        conn.close()
        assert stored < high["icp_score"], "the score kept a title the person no longer has"
    finally:
        conn = get_db()
        with conn:
            conn.execute("DELETE FROM lead_interactions WHERE lead_id IN (SELECT id FROM leads WHERE name = 'Ratchet Probe')")
            conn.execute("DELETE FROM leads WHERE name = 'Ratchet Probe'")
        conn.close()


def test_an_unread_post_count_does_not_overwrite_a_real_one():
    from database import get_db
    from linkedin_client import linkedin_client

    try:
        linkedin_client.ingest_analytics_payload({"posts": [{"id": "w18-probe", "impressions": 900, "reactions": 40}]})
        linkedin_client.ingest_analytics_payload({"posts": [{"id": "w18-probe", "comments": 5}]})
        conn = get_db()
        row = conn.execute("SELECT impressions, reactions, comments, published_at FROM posts WHERE id = 'w18-probe'").fetchone()
        conn.close()
        assert (row["impressions"], row["reactions"], row["comments"]) == (900, 40, 5)
        assert row["published_at"] is None, "the moment of ingest was recorded as the publish time"
    finally:
        conn = get_db()
        with conn:
            conn.execute("DELETE FROM posts WHERE id = 'w18-probe'")
        conn.close()
