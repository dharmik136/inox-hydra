"""
The Funnel, the Verdict, and the Inverted Flag
==============================================
Three defects that each made the interface say something the code did not know.

F5  `leads` carried two status columns for one entity. The CRM screen wrote
    `status`; the funnel and conversion_rate_pct read `lead_status`, which only
    ever received the literal 'NEW' at insert or 'ARCHIVED' at delete. Marking
    someone "Meeting Booked" therefore moved nothing, and the conversion rate
    was pinned at 0.00% by construction rather than by fact.

F6  The composer displayed "High Reach" or "Suppressed", a claim about how
    LinkedIn will distribute a post. The score behind it came from six
    formatting regexes running in the browser and was never once compared
    against the impression counts already in the database. An empty composer
    scored 100 and read "High Reach" before a character was typed.

F8  The hook generator's one measured signal was surfaced inverted. The backend
    emits `mobile_safe`; the frontend read `is_mobile_fold_safe`, which is
    undefined and therefore falsy, so every hook was labelled "Truncated".
"""

import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")


def _app_js():
    """
    The interface source, concatenated.

    This read one app.js. The interface is many components now, so the same
    question is asked of all of them: naming one file would let the stale
    read move into another and stop being seen.
    """
    import glob

    paths = glob.glob(os.path.join(UI_SRC, "**", "*.ts"), recursive=True)
    paths += glob.glob(os.path.join(UI_SRC, "**", "*.tsx"), recursive=True)
    assert paths, "no interface source was found to check"
    return "\n".join(open(path, encoding="utf-8").read() for path in sorted(paths))


def _code_lines(source):
    """Source with comment-only lines dropped, so prose is not mistaken for code."""
    return [
        line for line in source.splitlines()
        if not line.lstrip().startswith(("//", "*", "/*"))
    ]


def test_marking_a_lead_converted_moves_the_funnel():
    """
    The end to end assertion, because each half worked in isolation: the write
    succeeded and the read succeeded, and they simply addressed different
    columns.
    """
    from studio.backend.crm import reverse_crm
    from studio.backend.database import get_db
    from studio.backend.leads import update_lead_status

    ingested = reverse_crm.ingest_interaction(
        full_name="Funnel Probe Person",
        linkedin_urn="https://www.linkedin.com/in/funnel-probe-person",
        headline="VP of Platform Engineering at Northwind",
        company="Northwind",
        interaction_type="COMMENT",
        comment_text="How did you size the connection pool for this?",
    )
    lead_id = ingested["lead_id"]

    try:
        result = update_lead_status(lead_id, "Meeting Booked")
        assert result["status"] == "success", result

        conn = get_db()
        row = conn.execute(
            "SELECT status, lead_status FROM leads WHERE id = ?", (lead_id,)
        ).fetchone()
        conn.close()

        assert row["status"] == "Meeting Booked", "the human facing column did not move"
        assert row["lead_status"] == "CONVERTED", (
            f"lead_status is {row['lead_status']!r}. Every analytic reads this "
            f"column, so a funnel driven by it could never move."
        )
    finally:
        conn = get_db()
        conn.execute("DELETE FROM lead_interactions WHERE lead_id = ?", (lead_id,))
        conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.commit()
        conn.close()


@pytest.mark.parametrize("human,pipeline", [
    ("New Lead", "NEW"),
    ("Outreach Sent", "DM_SENT"),
    ("Connected", "ENGAGED"),
    ("Meeting Booked", "CONVERTED"),
])
def test_every_human_status_maps_to_a_pipeline_status(human, pipeline):
    """A gap here silently sends a lead back to NEW."""
    from studio.backend.leads import LEAD_STATUS_TO_PIPELINE, VALID_LEAD_STATUSES

    assert human in VALID_LEAD_STATUSES
    assert LEAD_STATUS_TO_PIPELINE[human] == pipeline


def test_the_mapping_covers_the_whole_vocabulary():
    from studio.backend.leads import LEAD_STATUS_TO_PIPELINE, VALID_LEAD_STATUSES

    missing = VALID_LEAD_STATUSES - set(LEAD_STATUS_TO_PIPELINE)
    assert not missing, (
        f"These statuses have no pipeline equivalent and would fall back to NEW: {missing}"
    )


def test_the_composer_makes_no_claim_about_reach():
    """
    Nothing in this product measures distribution. A formatting checklist may
    report on formatting; it may not report on reach.
    """
    source = _app_js()
    lines = _code_lines(source)

    forbidden = ["High Reach", "Suppressed"]
    offenders = []
    for line in lines:
        for phrase in forbidden:
            if phrase in line:
                offenders.append(line.strip()[:110])

    assert not offenders, (
        "The composer still asserts a reach outcome it cannot know:\n  "
        + "\n  ".join(offenders)
    )


def test_an_empty_composer_asserts_nothing():
    """
    The tell that the verdict was unbacked: with no text at all the score was
    100 and the label read "High Reach".
    """
    # This used to grep app.js for the guard inside const verdictDisplay.
    # The interface renders whatever the audit returns rather than deciding a
    # label itself, so the guarantee moved to the audit and is asserted on
    # behaviour. That is stronger: the old check passed as long as the guard
    # existed, whatever it did.
    from studio.backend.repurposer import audit_linkedin_algorithm_safety

    for empty in ("", "   "):
        result = audit_linkedin_algorithm_safety(empty)
        assert result["status_label"] == "Empty Draft", (
            "an empty composer is labelled as though something had been assessed"
        )
        assert not result["penalties"], "an empty draft was given penalties"


def test_the_fold_safe_flag_reads_the_field_the_backend_sends():
    """
    Caught by name mismatch rather than by behaviour: undefined is falsy, so
    the panel rendered confidently and wrongly rather than erroring.
    """
    source = _app_js()
    lines = _code_lines(source)

    stale = [line.strip()[:110] for line in lines if "is_mobile_fold_safe" in line]
    assert not stale, (
        "the interface still reads is_mobile_fold_safe, which the backend never sends:\n  "
        + "\n  ".join(stale)
    )

    # The field is named on a typed interface now rather than read off a
    # local, so the access is not written "h.mobile_safe".
    assert any("mobile_safe" in line for line in lines), (
        "the interface no longer reads the fold-safe flag at all"
    )


def test_the_backend_still_emits_that_field():
    """Guards the other half of the rename, so the pair cannot drift apart again."""
    path = os.path.join(REPO_ROOT, "studio", "backend", "repurposer.py")
    with open(path, "r", encoding="utf-8") as f:
        backend = f.read()
    assert '"mobile_safe"' in backend, (
        "repurposer.py no longer emits mobile_safe, so the frontend read is stale again"
    )
