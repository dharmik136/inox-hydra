"""
Regressions Found Reviewing the Honesty Fixes
=============================================
The F1 to F8 changes were adversarially reviewed and 27 findings survived
refutation. These tests pin the repairs. Each one exists because the first
attempt at fixing a fabrication introduced a new one.

The worst of them is worth stating plainly. F6 removed the "High Reach" verdict
and replaced it with `Math.round((100 - score) / 10)`, labelled "N to fix". The
six checks deduct 40/20/25/15/15/15, so that expression is the penalty total
divided by ten, not a count of anything. One failing URL check rendered
"4 to fix". All six failing clamped to 20 and rendered "8 to fix", more unmet
checks than checks that exist. An invented number was replaced by a differently
invented number.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS = os.path.join(REPO_ROOT, "studio", "frontend", "app.js")
CONTENT_JS = os.path.join(REPO_ROOT, "studio", "extension", "content.js")
NODE = shutil.which("node")
requires_node = pytest.mark.skipif(NODE is None, reason="node is not on PATH")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _code_lines(source):
    return [
        line for line in source.splitlines()
        if not line.lstrip().startswith(("//", "*", "/*", "#"))
    ]


# --------------------------------------------------------------------------
# The verdict
# --------------------------------------------------------------------------

def test_the_verdict_counts_failures_rather_than_deriving_them_from_the_score():
    """
    The deductions are not uniform, so no arithmetic on the score can recover
    the count. It has to be counted where the failures happen.
    """
    source = _read(APP_JS)
    audit = source[source.index("function runAlgorithmicAudit"):]
    audit = audit[:audit.index("\n}")]

    deductions = re.findall(r"score -= (\d+);", audit)
    increments = re.findall(r"failedChecks \+= 1;", audit)
    assert len(deductions) >= 6, "the audit no longer has its checks"
    assert len(increments) == len(deductions), (
        f"{len(deductions)} checks deduct from the score but only {len(increments)} "
        f"increment the counter, so the reported count is wrong for some inputs."
    )

    verdict = source[source.index("const verdictDisplay"):]
    verdict = verdict[:verdict.index("\n}")]
    assert "(100 - score)" not in verdict, (
        "The verdict still derives a count from the weighted score. The "
        "deductions are 40/20/25/15/15/15, so this is the penalty total over "
        "ten and never equals the number of failing checks."
    )


def test_the_deductions_are_genuinely_non_uniform():
    """
    Guards the reasoning above. If someone makes every deduction equal, the
    derived form becomes valid and this test should be revisited rather than
    silently continuing to assert a rule whose premise has changed.
    """
    source = _read(APP_JS)
    audit = source[source.index("function runAlgorithmicAudit"):]
    audit = audit[:audit.index("\n}")]
    deductions = {int(d) for d in re.findall(r"score -= (\d+);", audit)}
    assert len(deductions) > 1, (
        f"All deductions are now equal ({deductions}), which changes the premise "
        f"of test_the_verdict_counts_failures_rather_than_deriving_them_from_the_score."
    )


def test_no_reach_claim_survives_anywhere_including_static_markup():
    """
    The string was removed from app.js but left in index.html, where it was what
    the creator saw until their first keystroke, which is the exact scenario the
    fix was written for.
    """
    for rel in ("studio/frontend/app.js", "studio/frontend/index.html"):
        source = _read(os.path.join(REPO_ROOT, rel))
        offenders = [
            line.strip()[:110] for line in _code_lines(source)
            if "High Reach" in line or "Suppressed" in line
        ]
        assert not offenders, f"{rel} still asserts a reach outcome:\n  " + "\n  ".join(offenders)


# --------------------------------------------------------------------------
# Seeded posts
# --------------------------------------------------------------------------

def _boot_clean(code, demo_flag):
    home = tempfile.mkdtemp(prefix="inox_rev_")
    env = dict(os.environ)
    env["INOX_HYDRA_HOME"] = home
    env["PYTHONIOENCODING"] = "utf-8"
    if demo_flag is None:
        env.pop("INOX_DEMO_DATA", None)
    else:
        env["INOX_DEMO_DATA"] = demo_flag
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    return result.stdout.strip().splitlines()[-1]


def test_a_fresh_install_seeds_no_post_with_invented_engagement():
    """
    The F1 gate covered analytics_daily and audience_demographics but missed
    posts_data, so the KPI strip honestly showed a dash while the table directly
    beneath it reported 1,450 impressions on a post nobody wrote.
    """
    code = """
import sys
sys.path.insert(0, ".")
from studio.backend.database import init_db, seed_initial_data, get_db
init_db(); seed_initial_data()
conn = get_db()
n = conn.execute("SELECT COUNT(*) FROM posts WHERE impressions > 0 OR reactions > 0").fetchone()[0]
conn.close()
print("RESULT", n)
"""
    assert _boot_clean(code, demo_flag=None).split()[1] == "0", (
        "A fresh install still seeds posts carrying fabricated engagement counts."
    )


def test_the_demo_flag_still_restores_those_posts():
    code = """
import sys
sys.path.insert(0, ".")
from studio.backend.database import init_db, seed_initial_data, get_db
init_db(); seed_initial_data()
conn = get_db()
n = conn.execute("SELECT COUNT(*) FROM posts WHERE impressions > 0").fetchone()[0]
conn.close()
print("RESULT", n)
"""
    assert int(_boot_clean(code, demo_flag="1").split()[1]) > 0


# --------------------------------------------------------------------------
# The egress refusal
# --------------------------------------------------------------------------

def test_a_refused_health_check_does_not_certify_the_session():
    """
    check_session_health returns the refusal dict straight out of its route, so
    hardcoding healthy: True meant a default install reported an expired li_at
    as healthy without ever looking at it.
    """
    import importlib
    import studio.backend.linkedin_client as lc
    importlib.reload(lc)

    os.environ.pop("INOX_ALLOW_LINKEDIN_EGRESS", None)
    refusal = lc.egress_guard("voyager/api/me")

    assert refusal is not None
    assert refusal["healthy"] is None, (
        f"healthy is {refusal['healthy']!r}. A session nobody checked is not "
        f"healthy; it is unknown."
    )
    assert refusal.get("checked") is False
    assert "circuit_breaker" in refusal, (
        "Every other branch of check_session_health returns circuit_breaker. "
        "Dropping it makes callers that read circuit_breaker.state raise KeyError."
    )


# --------------------------------------------------------------------------
# The observation window
# --------------------------------------------------------------------------

def test_a_multi_day_window_declared_per_bucket_is_also_refused():
    """The guard read only the top-level label, so a per-bucket one slipped past."""
    import studio.backend.linkedin_client as lc

    result = lc.linkedin_client.ingest_analytics_payload({
        "series": [{"date": "2026-09-22", "period_label": "28d", "impressions": 41000}],
    })
    assert result.get("status") == "window_mismatch", (
        f"A 28 day aggregate declared inside the bucket was accepted: {result}"
    )


def test_a_metric_that_was_not_read_does_not_overwrite_one_that_was():
    """
    The guard lets a payload through when followers parsed but impressions did
    not. `or 0` then stamped a fabricated zero over the real figure captured
    earlier the same day, marked source='observed'.
    """
    import studio.backend.linkedin_client as lc
    from studio.backend.database import get_db

    day = "2026-09-23"
    try:
        lc.linkedin_client.ingest_analytics_payload({
            "period_label": "1d",
            "series": [{"date": day, "impressions": 1200, "reactions": 34}],
        })
        lc.linkedin_client.ingest_analytics_payload({
            "period_label": "1d",
            "series": [{"date": day, "followers": 2401}],
        })

        conn = get_db()
        row = conn.execute(
            "SELECT impressions, reactions, followers FROM analytics_daily WHERE date = ?",
            (day,),
        ).fetchone()
        conn.close()

        assert row["impressions"] == 1200, (
            f"impressions became {row['impressions']}. A payload that did not "
            f"read impressions must not overwrite the figure that did."
        )
        assert row["reactions"] == 34
        assert row["followers"] == 2401
    finally:
        conn = get_db()
        conn.execute("DELETE FROM analytics_daily WHERE date = ?", (day,))
        conn.commit()
        conn.close()


# --------------------------------------------------------------------------
# The funnel
# --------------------------------------------------------------------------

def test_creating_a_lead_sets_both_status_columns():
    """
    The dual write covered update_lead_status only, so a lead created with a
    status appeared converted in the CRM list and NEW in the funnel from the
    moment it existed.
    """
    from studio.backend.database import get_db
    from studio.backend.leads import add_lead

    created = add_lead({
        "name": "Insert Path Probe",
        "headline": "CTO at Probe Industries",
        "company": "Probe Industries",
        "profile_url": "https://www.linkedin.com/in/insert-path-probe",
        "status": "Meeting Booked",
    })
    lead_id = created["id"]
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT status, lead_status FROM leads WHERE id = ?", (lead_id,)
        ).fetchone()
        conn.close()
        assert row["status"] == "Meeting Booked"
        assert row["lead_status"] == "CONVERTED", (
            f"lead_status is {row['lead_status']!r} on a lead created as "
            f"Meeting Booked, so the funnel disagrees with the list."
        )
    finally:
        conn = get_db()
        conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.commit()
        conn.close()


# --------------------------------------------------------------------------
# The extension
# --------------------------------------------------------------------------

@requires_node
def test_the_parser_refuses_a_decimal_comma_rather_than_multiplying_by_ten():
    """"1,2K" is 1.2K in de-DE. Stripping the comma made it 12000."""
    source = _read(CONTENT_JS)
    fn = re.search(r"function parseMetricValue\b[\s\S]*?\n}", source).group(0)
    script = fn + '\nconsole.log(JSON.stringify(["1,2K","12,5K","1,23"].map(parseMetricValue)));'
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[null,null,null]", (
        f"locale-ambiguous figures were parsed rather than refused: {result.stdout.strip()}"
    )


def test_commenter_capture_still_works_on_the_feed():
    """
    Over-restricting is its own failure. Gating capture on a post permalink
    removed the feed, which is where most comment reading happens and which the
    commenter block's own comment names as a supported surface.
    """
    source = _read(CONTENT_JS)
    gate = source[source.index("function isPostEngagementSurface"):]
    gate = gate[:gate.index("\n}")]
    assert "/feed/" in gate, (
        "isPostEngagementSurface excludes the feed, so commenter capture that "
        "previously worked there is now dead."
    )


def test_spa_navigation_is_actually_observed():
    """
    popstate fires for back and forward only. LinkedIn navigates with pushState,
    which emits nothing, so the previous fix did not cover the navigation its
    own comment described.
    """
    source = _read(CONTENT_JS)
    assert "pushState" in source, (
        "Nothing observes pushState, so the analytics extractor never runs for a "
        "creator who reaches the page by clicking through the app."
    )


def test_the_capture_toast_waits_for_the_writes_it_reports_on():
    """It fired synchronously, so with the studio down it still claimed success."""
    source = _read(CONTENT_JS)
    assert "Promise.allSettled" in source, (
        "The capture toast does not wait for its requests, so it reports a "
        "capture that may have been entirely refused."
    )


def test_unidentified_people_are_excluded_from_both_writes():
    """
    Filtering only the CRM call left them in the leads table via the batch
    endpoint, so the toast said "skipped" about rows that had just been stored.
    """
    source = _read(CONTENT_JS)
    assert "JSON.stringify({ leads: identified })" in source, (
        "The batch lead POST still sends the unfiltered array, so people the "
        "toast reports as skipped are written to the leads table anyway."
    )
