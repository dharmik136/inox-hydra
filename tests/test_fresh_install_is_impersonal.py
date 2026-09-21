"""
A Fresh Install Belongs To Nobody
=================================
G-Stack #246 and #247. Two things a second user must not inherit: content about
people who did not consent to it, and the author's identity as their default.

What shipped before this:

- Sixteen launch drafts in the author's first person, about a campaign the new
  user is not running, seeded from two separate call sites.
- Four invented personas with pipeline states, one at "Meeting Booked", which
  registers as a real conversion now that the funnel works. Also from two call
  sites.
- Five posts attributed to Dan Koe, Sahil Bloom, Garry Tan, Shreyas Doshi and
  Alex Hormozi, with invented engagement counts of 4,200 to 15,300.
- The author's name, headline, company and handle as the default in roughly
  twenty places, including a carousel footer drawn from a literal, so fixing the
  settings API alone still exported somebody else's name into a PNG.

The split matters. The drafts and the personas are gated behind INOX_DEMO_DATA,
because they are the author's own writing and obviously fictional people.
The third-party attributions were deleted outright, because no flag makes it
acceptable to put words in an identifiable person's mouth and attach metrics to
a post they never wrote.
"""

import os
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

REAL_PEOPLE = ("Dan Koe", "Sahil Bloom", "Garry Tan", "Shreyas Doshi", "Alex Hormozi")
AUTHOR_MARKERS = ("Dharmik", "dharmik136", "Enterprise Labs")


def _boot(demo_flag):
    """Boot the data layer in a throwaway home and report what it seeded."""
    code = """
import sys
sys.path.insert(0, ".")
from studio.backend.database import init_db, seed_initial_data, get_db
init_db(); seed_initial_data()
c = get_db()
out = []
for t in ("drafts", "posts", "leads", "lead_enrichments", "queue_slots"):
    out.append(str(c.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]))
c.close()
print("RESULT " + " ".join(out))
"""
    env = dict(os.environ)
    env["INOX_HYDRA_HOME"] = tempfile.mkdtemp(prefix="inox_impersonal_")
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
    counts = result.stdout.strip().splitlines()[-1].split()[1:]
    return dict(zip(("drafts", "posts", "leads", "enrichments", "slots"), map(int, counts)))


def test_a_fresh_install_contains_no_content_about_anybody():
    """
    The whole point. A new user opens a product that knows nothing, which is the
    truth, rather than one pre-loaded with somebody else's campaign.
    """
    counts = _boot(demo_flag=None)

    assert counts["drafts"] == 0, (
        f"{counts['drafts']} drafts seeded. These are the author's own posts in "
        f"their first person."
    )
    assert counts["leads"] == 0, (
        f"{counts['leads']} leads seeded. Invented people, one of them recorded "
        f"as a booked meeting."
    )
    assert counts["posts"] == 0
    assert counts["enrichments"] == 0

    # Default posting times assert nothing about anyone and stay.
    assert counts["slots"] >= 8, "the scheduler needs somewhere to put a post"


def test_the_demo_flag_restores_all_of_it():
    """
    If the flag changed nothing, the test above would be proving the wrong
    thing: that the seeds were deleted rather than gated.
    """
    counts = _boot(demo_flag="1")
    assert counts["drafts"] >= 16
    assert counts["leads"] == 4
    assert counts["posts"] > 0


def test_both_seed_call_sites_are_gated():
    """
    The drafts and the leads each seeded from two places. Gating one leaves the
    behaviour reachable through the other, which is exactly what happened on the
    first attempt: leads still appeared with the flag off.
    """
    path = os.path.join(REPO_ROOT, "studio", "backend", "database.py")
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()

    # Every seed_dayNN_draft call must sit inside a guard, which shows as an
    # indent deeper than the function body.
    ungated = [
        line for line in source.splitlines()
        if line.strip().startswith("seed_day")
        and line.strip().endswith("_draft(conn)")
        and not line.startswith("        ")
    ]
    assert not ungated, (
        "These draft seed calls are not inside the demo guard:\n  "
        + "\n  ".join(line.strip() for line in ungated)
    )

    # Both sample_leads blocks must sit behind the flag. Checked by counting
    # rather than by indent, because each is guarded through a local boolean
    # rather than by being nested directly under the call.
    lead_blocks = source.count("sample_leads = [")
    guarded = source.count("if demo_data_enabled():")
    assert lead_blocks == 2, f"expected 2 sample_leads blocks, found {lead_blocks}"
    assert guarded >= 4, (
        f"only {guarded} demo_data_enabled guards found. Both leads blocks, the "
        f"enrichment and the drafts each need one."
    )


@pytest.mark.parametrize("person", REAL_PEOPLE)
def test_no_post_is_attributed_to_a_real_person(person):
    """
    Deleted rather than gated. Fabricating the user's own numbers is one thing;
    attaching invented engagement to a named person's imaginary post is another,
    and a demo flag does not make it acceptable to display.
    """
    path = os.path.join(REPO_ROOT, "studio", "backend", "database.py")
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    # A comment may name them while explaining the removal. Quoted string
    # literals are the seed data itself.
    offenders = [
        line.strip()[:110] for line in lines
        if f'"{person}"' in line and not line.lstrip().startswith("#")
    ]
    assert not offenders, (
        f"{person} still appears as seed data:\n  " + "\n  ".join(offenders)
    )


def test_the_studio_ships_no_creator_identity():
    """
    The API fix alone was not enough: static value= attributes render before any
    fetch resolves, and the carousel footer was drawn from a literal.
    """
    offenders = []
    for root, dirs, files in os.walk(os.path.join(REPO_ROOT, "studio")):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules")]
        for name in files:
            if not name.endswith((".py", ".js", ".html", ".css", ".json")):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, REPO_ROOT).replace("\\", "/")
            with open(full, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    # The repository URL is a location, not an identity.
                    if "github" in line.lower():
                        continue
                    if line.lstrip().startswith(("#", "//", "*")):
                        continue
                    for marker in AUTHOR_MARKERS:
                        if marker in line:
                            offenders.append(f"{rel}:{i}  {line.strip()[:90]}")

    assert not offenders, (
        "The shipped app still carries the author's identity:\n  "
        + "\n  ".join(offenders[:12])
    )


def test_an_unset_name_renders_nothing_rather_than_somebody_else():
    """
    carousel_generator drew 'Dharmik Shingala - Personal LinkedIn Studio' into
    every exported slide from a string literal, so a correct settings form still
    produced a wrong file.
    """
    from studio.backend import carousel_generator as cg

    path = os.path.join(REPO_ROOT, "studio", "backend", "carousel_generator.py")
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()

    assert "Personal LinkedIn Studio" in source, "the footer was removed entirely rather than parameterised"
    footer_lines = [
        l for l in source.splitlines()
        if "Personal LinkedIn Studio" in l and not l.lstrip().startswith("#")
    ]
    assert footer_lines, "no footer draw call found"
    for line in footer_lines:
        assert "safe_author" in line or "author" in line, (
            f"the footer still draws from a literal: {line.strip()[:100]}"
        )


def test_the_profile_endpoint_admits_when_it_does_not_know():
    """
    It used to synthesise a person, so every consumer downstream believed a name
    had been set. is_set is how a caller tells 'never configured' apart from
    'configured to an empty string'.
    """
    from fastapi.testclient import TestClient
    import studio.backend.app as app_module
    from studio.backend.database import get_db

    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = 'creator_profile'").fetchone()
    saved = row["value"] if row else None
    conn.execute("DELETE FROM settings WHERE key = 'creator_profile'")
    conn.commit()
    conn.close()

    try:
        client = TestClient(app_module.app, raise_server_exceptions=False)
        body = client.get("/api/settings/profile").json()

        assert body["is_set"] is False, "an install with no name must say so"
        profile = body["profile"]
        for field in ("name", "headline", "company", "brand_watermark_text"):
            assert profile[field] == "", (
                f"{field} defaulted to {profile[field]!r} instead of being empty"
            )
    finally:
        if saved is not None:
            conn = get_db()
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('creator_profile', ?)",
                (saved,),
            )
            conn.commit()
            conn.close()
