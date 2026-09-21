"""
No Fabricated Metrics
=====================
The studio used to generate 90 days of analytics and 18 demographic rows by
modulo arithmetic at every boot, with nothing marking them as synthetic. On the
live install this was measurable: the stored follower count was exactly
2330 + 90/3 = 2360, the stored profile views exactly 70 + 90/5 = 88, and the
newest date exactly the generator's hardcoded base_date. Three values, three
exact matches. Every chart, KPI, range pill and CSV export drew from it, and it
rendered identically to real capture.

Worse, the seeder deleted real rows: `if count < 60: DELETE FROM analytics_daily`
ran at startup, so a creator who had genuinely captured twenty days lost them.

These tests pin the repair:

1. Fabricated observations are opt-in, off by default.
2. Real captured rows are never deleted by the seeder.
3. An uncaptured metric is null, never a plausible-looking constant.
4. Rows carry provenance, so a seeded row can never again be mistaken for one
   that was measured.

Queue slots are deliberately exempt. They are default posting times, not claims
about anything that happened, so seeding them asserts nothing.
"""

import importlib
import os
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# The literals that used to be displayed as though they had been measured.
BANNED_DISPLAY_CONSTANTS = [
    ("studio/backend/app.py", "2412"),
    ("studio/backend/app.py", "104)"),
    ("studio/frontend/app.js", "2412"),
    ("studio/frontend/app.js", "96% Safe"),
    ("studio/frontend/app.js", '"18.4"'),
    ("studio/frontend/index.html", "2,412"),
    ("studio/frontend/index.html", "94% Safe"),
    ("studio/frontend/index.html", "98% Safe"),
]


def _run_in_clean_home(code, demo_flag):
    """
    Boot the app's data layer in a throwaway home directory, in a subprocess.

    A subprocess is required rather than an import: database.py reads
    INOX_DEMO_DATA at call time but the seeding decision is made once per
    process, and this suite's conftest sets the flag for every in-process test.
    """
    home = tempfile.mkdtemp(prefix="inox_nofab_")
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
    assert result.returncode == 0, (
        f"subprocess failed (demo flag {demo_flag!r}):\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    return result.stdout.strip().splitlines()[-1]


BOOT_AND_COUNT = """
import sys
sys.path.insert(0, ".")
from studio.backend.database import init_db, seed_initial_data, get_db
init_db()
seed_initial_data()
conn = get_db()
a = conn.execute("SELECT COUNT(*) FROM analytics_daily").fetchone()[0]
d = conn.execute("SELECT COUNT(*) FROM audience_demographics").fetchone()[0]
q = conn.execute("SELECT COUNT(*) FROM queue_slots").fetchone()[0]
conn.close()
print("RESULT", a, d, q)
"""


def test_a_fresh_install_fabricates_nothing():
    """The default install captures its own data or shows nothing. It invents neither."""
    out = _run_in_clean_home(BOOT_AND_COUNT, demo_flag=None)
    _, analytics, demographics, slots = out.split()
    assert analytics == "0", (
        f"A fresh install generated {analytics} analytics rows. Every one of them "
        f"would render as measured data the creator never produced."
    )
    assert demographics == "0", (
        f"A fresh install generated {demographics} demographic rows describing an "
        f"audience it has never observed."
    )
    assert int(slots) >= 8, (
        "Queue slots are default posting times, not measurements, and should "
        "still seed so the scheduler has somewhere to put a post."
    )


def test_the_demo_flag_still_produces_a_full_fixture():
    """Turning the flag on must restore the old behaviour exactly, for demos and tests."""
    out = _run_in_clean_home(BOOT_AND_COUNT, demo_flag="1")
    _, analytics, demographics, _ = out.split()
    assert int(analytics) >= 60, f"INOX_DEMO_DATA=1 produced only {analytics} analytics rows"
    assert int(demographics) >= 14, f"INOX_DEMO_DATA=1 produced only {demographics} demographic rows"


SEED_THEN_REBOOT = """
import sys
sys.path.insert(0, ".")
from studio.backend.database import init_db, seed_initial_data, get_db
init_db()
seed_initial_data()

# A creator captures twenty real days, well under the old threshold of sixty.
conn = get_db()
for i in range(20):
    conn.execute(
        "INSERT OR REPLACE INTO analytics_daily (date, followers, impressions, source) "
        "VALUES (?, ?, ?, 'observed')",
        (f"2026-01-{i + 1:02d}", 900 + i, 100 + i),
    )
conn.commit()
conn.close()

# The studio restarts.
seed_initial_data()

conn = get_db()
survived = conn.execute(
    "SELECT COUNT(*) FROM analytics_daily WHERE source = 'observed'"
).fetchone()[0]
conn.close()
print("RESULT", survived)
"""


def test_a_restart_never_destroys_captured_rows():
    """
    The regression that made this test necessary: seed_initial_data ran
    `DELETE FROM analytics_daily` whenever the table held fewer than sixty rows,
    which is exactly the situation of every creator in their first two months.
    """
    out = _run_in_clean_home(SEED_THEN_REBOOT, demo_flag=None)
    survived = int(out.split()[1])
    assert survived == 20, (
        f"Only {survived} of 20 captured days survived a restart. Real observations "
        f"must never be deleted to make room for fabricated ones."
    )


def test_observations_carry_provenance():
    """A row must say where it came from, or seeded and measured stay indistinguishable."""
    code = """
import sys
sys.path.insert(0, ".")
from studio.backend.database import init_db, seed_initial_data, get_db
init_db()
seed_initial_data()
conn = get_db()
cols = {r[1] for r in conn.execute("PRAGMA table_info(analytics_daily)")}
dcols = {r[1] for r in conn.execute("PRAGMA table_info(audience_demographics)")}
seeded = conn.execute("SELECT COUNT(*) FROM analytics_daily WHERE source = 'seed'").fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM analytics_daily").fetchone()[0]
conn.close()
print("RESULT", int("source" in cols), int("source" in dcols), seeded, total)
"""
    out = _run_in_clean_home(code, demo_flag="1")
    _, has_source, has_dsource, seeded, total = out.split()
    assert has_source == "1", "analytics_daily has no provenance column"
    assert has_dsource == "1", "audience_demographics has no provenance column"
    assert seeded == total and int(seeded) > 0, (
        f"Only {seeded} of {total} seeded rows are marked 'seed'. An unmarked "
        f"fabricated row is the whole problem."
    )


def test_an_uncaptured_metric_is_null_not_a_constant():
    """
    get_kpis used to fall back to 2412 followers and 104 profile views. Because
    the fallback used `or` rather than an explicit None check, a creator with a
    truthful zero was shown the constant too.
    """
    code = """
import sys
sys.path.insert(0, ".")
from studio.backend.database import init_db, seed_initial_data, get_db
init_db()
seed_initial_data()
from fastapi.testclient import TestClient
from studio.backend.app import app
client = TestClient(app, raise_server_exceptions=False)
r = client.get("/api/analytics/kpis?range=30d")
d = r.json()
print("RESULT", r.status_code, repr(d.get("total_followers")), repr(d.get("profile_views")), repr(d.get("range")))
"""
    out = _run_in_clean_home(code, demo_flag=None)
    parts = out.split(None, 1)[1]
    status, rest = parts.split(None, 1)
    assert status == "200", f"An empty analytics table must still answer, got {status}"
    assert "None" in rest, (
        f"Expected null metrics on an install that has captured nothing, got: {rest}"
    )
    assert "2412" not in rest and "104" not in rest, (
        f"A fabricated constant reached the API response: {rest}"
    )
    assert "'30d'" in rest, "The response shape must survive an empty table"


@pytest.mark.parametrize("relative_path,literal", BANNED_DISPLAY_CONSTANTS)
def test_fabricated_display_constants_are_gone(relative_path, literal):
    """
    Each of these was rendered to the creator as though it had been measured.
    They are checked as literals because that is how they came back last time:
    one at a time, each looking harmless on its own.
    """
    path = os.path.join(REPO_ROOT, relative_path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Comments may name a constant while explaining why it was removed.
    lines = [
        line for line in content.splitlines()
        if literal in line
        and not line.lstrip().startswith(("#", "//", "*", "/*"))
    ]
    assert not lines, (
        f"{relative_path} still ships the literal {literal!r}:\n  "
        + "\n  ".join(line.strip()[:120] for line in lines[:4])
    )
