"""
Capture Honesty
===============
Four defects in the capture path, each of which produced a row that looked
exactly like a real observation:

W3  parseInt("1.2K") returned 1. Only creators under a thousand impressions were
    ever recorded correctly, and the engagement rate then divided by that 1.
M3  The figure on a creator analytics card covers whatever window the range
    selector is set to. It was written into a row keyed by today's date, so a
    28 day total became today's impressions and the dashboard summed overlapping
    windows.
W2  The reactor scraper matched a bare `li` inside any `.artdeco-modal` or
    `div[role="dialog"]` on any LinkedIn page. Messaging overlays, notification
    panels and search dropdowns all qualified, so strangers were stored as
    having reacted to a post.
W6  Every generated message said "thanks for the comment on the sovereign
    creator architecture breakdown". For reactors, who have no comment, the
    scraper's own placeholder was quoted back:
    `Your point about "Reacted to post on LinkedIn..." was spot on.`

The JavaScript is checked by running it under Node where possible and by reading
the source where not, because there is no DOM here.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONTENT_JS = os.path.join(REPO_ROOT, "studio", "extension", "content.js")

NODE = shutil.which("node")
requires_node = pytest.mark.skipif(NODE is None, reason="node is not on PATH")


def _content_source():
    with open(CONTENT_JS, "r", encoding="utf-8") as f:
        return f.read()


@requires_node
def test_the_shipped_metric_parser_handles_abbreviated_numbers():
    """
    Runs the real parseMetricValue out of the shipped file. LinkedIn writes
    "1.2K" and "1.5M"; the old code turned both into 1.
    """
    source = _content_source()
    match = re.search(r"function parseMetricValue\b[\s\S]*?\n}", source)
    assert match, "parseMetricValue is missing from content.js"

    cases = {
        "1,234": 1234,
        "892": 892,
        "1.2K": 1200,
        "13K": 13000,
        "1.5M": 1500000,
        "3.4K": 3400,
        "1K": 1000,
        "2.1B": 2100000000,
    }
    script = (
        match.group(0)
        + "\nconst out = {};"
        + f"\nfor (const k of {json.dumps(list(cases))}) {{"
        + "\n  const r = parseMetricValue(k); out[k] = r ? r.value : null; }"
        + "\nconsole.log(JSON.stringify(out));"
    )
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    got = json.loads(result.stdout.strip())

    wrong = {k: (got[k], v) for k, v in cases.items() if got[k] != v}
    assert not wrong, f"parser is wrong for (got, expected): {wrong}"


@requires_node
def test_the_parser_refuses_text_that_is_not_a_number():
    """Coercing unparseable text to 0 would store a measurement nobody made."""
    source = _content_source()
    match = re.search(r"function parseMetricValue\b[\s\S]*?\n}", source)
    script = (
        match.group(0)
        + "\nconst out = {};"
        + '\nfor (const k of ["--", "N/A", "", "abc", "1.2.3", "12 followers"]) {'
        + "\n  out[k] = parseMetricValue(k); }"
        + "\nconsole.log(JSON.stringify(out));"
    )
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    got = json.loads(result.stdout.strip())
    coerced = {k: v for k, v in got.items() if v is not None}
    assert not coerced, f"these should have been refused, not coerced: {coerced}"


@requires_node
def test_an_abbreviated_reading_is_marked_as_rounded():
    """1.2K means somewhere in [1150, 1250). Recording it as exactly 1200 and
    later presenting it as measured would be a quieter second fabrication."""
    source = _content_source()
    match = re.search(r"function parseMetricValue\b[\s\S]*?\n}", source)
    script = (
        match.group(0)
        + '\nconsole.log(JSON.stringify({'
        + ' exact: parseMetricValue("1,234").precision,'
        + ' rounded: parseMetricValue("1.2K").precision }));'
    )
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    got = json.loads(result.stdout.strip())
    assert got["exact"] == "exact"
    assert got["rounded"] == "rounded"


def test_a_multi_day_aggregate_is_refused_rather_than_stored_as_daily():
    """
    The defect no later fix could repair: the period was never recorded, so a
    28 day total stored as today's impressions was indistinguishable from a real
    daily figure once written.
    """
    import studio.backend.linkedin_client as lc

    result = lc.linkedin_client.ingest_analytics_payload({
        "period_label": "28d",
        "precision": "rounded",
        "series": [{"date": "2026-09-20", "impressions": 41000, "reactions": 900}],
    })

    assert result.get("status") == "window_mismatch", result
    assert result.get("saved") == 0


def test_a_daily_figure_is_accepted_and_keeps_its_window():
    """The refusal must be specific to the mis-windowed case, not blanket."""
    import studio.backend.linkedin_client as lc
    from studio.backend.database import get_db

    # This row is removed again below. Left behind it would advance
    # MAX(date) in analytics_daily, which is what every range window in
    # get_kpis and get_analytics_overview is anchored to, and other tests in
    # this session assert on those window sizes.
    probe_date = "2026-09-19"
    try:
        result = lc.linkedin_client.ingest_analytics_payload({
            "period_label": "1d",
            "precision": "exact",
            "series": [{"date": probe_date, "impressions": 412, "reactions": 17}],
        })
        assert result.get("status") != "window_mismatch", result

        conn = get_db()
        row = conn.execute(
            "SELECT impressions, period_label, precision, source FROM analytics_daily WHERE date = ?",
            (probe_date,),
        ).fetchone()
        conn.close()

        assert row is not None, "a daily figure should have been stored"
        assert row["impressions"] == 412
        assert row["period_label"] == "1d"
        assert row["precision"] == "exact"
        assert row["source"] == "observed"
    finally:
        conn = get_db()
        conn.execute("DELETE FROM analytics_daily WHERE date = ?", (probe_date,))
        conn.commit()
        conn.close()


def test_the_reactor_scraper_is_scoped_to_a_post():
    """
    The bare `li` fallback is what turned every dialog on linkedin.com into a
    source of leads. Its absence is the fix, so its absence is the assertion.
    """
    source = _content_source()

    reactor_block = source[source.index("const reactorModals"):source.index("// Only POST if we have valid leads")]
    assert re.search(r"querySelectorAll\(\s*$", reactor_block, re.M) or "reactorItems" in reactor_block

    selector_lists = re.findall(r"querySelectorAll\(\s*\n?\s*['\"]([^'\"]+)['\"]", reactor_block)
    assert selector_lists, "could not read the reactor selectors"
    for selectors in selector_lists:
        parts = [s.strip() for s in selectors.split(",")]
        assert "li" not in parts, (
            f"a bare 'li' selector is still present: {selectors!r}. It matches a "
            f"list item in any dialog, including messaging and notifications."
        )

    assert "isPostEngagementSurface" in source, (
        "engager capture is not gated on being on a post page"
    )


def test_no_linkedin_urn_is_minted_from_a_name_hash():
    """A forged key in LinkedIn's namespace collides and cannot be resolved."""
    source = _content_source()
    # Comments explain why the forging was removed and must not read as the code.
    code_lines = [
        line for line in source.splitlines()
        if not line.lstrip().startswith(("//", "*", "/*"))
    ]
    offenders = [line.strip()[:110] for line in code_lines if "urn:li:person:" in line]
    assert not offenders, (
        "content.js still mints a urn:li:person: value. Only LinkedIn issues "
        f"those:\n  " + "\n  ".join(offenders)
    )

    app_py = os.path.join(REPO_ROOT, "studio", "backend", "app.py")
    with open(app_py, "r", encoding="utf-8") as f:
        backend = f.read()
    minting = [
        line for line in backend.splitlines()
        if 'f"urn:li:person:' in line and not line.lstrip().startswith("#")
    ]
    assert not minting, f"the backend still mints a LinkedIn URN: {minting}"


def test_a_reaction_produces_no_suggested_message():
    """
    A reactor said nothing. The stored draft used to quote the scraper's own
    placeholder back at them as though it were their words.
    """
    from studio.backend.crm import reverse_crm

    result = reverse_crm.ingest_interaction(
        full_name="Reaction Only Person",
        linkedin_urn="https://www.linkedin.com/in/reaction-only-person",
        headline="VP of Engineering at Acme",
        company="Acme",
        interaction_type="LIKE",
        comment_text="Reacted to post on LinkedIn",
    )

    dm = (result.get("suggested_dm") or result.get("suggested_dm_reply") or "")
    assert "Reacted to post on LinkedIn" not in dm, (
        f"the scraper's placeholder was quoted back as a human sentence: {dm!r}"
    )
    assert dm == "", f"a reaction carries no words to reply to, got {dm!r}"


def test_no_stored_message_claims_a_topic_the_creator_did_not_write():
    """post_topic was a fixed string, so every draft described the same post."""
    from studio.backend.crm import ICPScoringEngine

    dm = ICPScoringEngine.generate_contextual_dm(
        "Priya Raman",
        "How did you handle the migration without downtime?",
        post_topic=None,
    )
    assert dm == "", "with no known topic the honest output is no draft at all"

    grounded = ICPScoringEngine.generate_contextual_dm(
        "Priya Raman",
        "How did you handle the migration without downtime?",
        post_topic="the zero downtime migration",
    )
    assert "the zero downtime migration" in grounded
    assert "sovereign creator" not in grounded.lower()


def test_the_hardcoded_topic_is_gone_from_the_capture_path():
    source = _content_source()
    live = [
        line for line in source.splitlines()
        if "sovereign creator architecture" in line and not line.lstrip().startswith("//")
    ]
    assert not live, f"content.js still ships a fixed post topic: {live}"
