"""
Prototype Sweep Guards
======================
Four findings from the shipping audit, fixed and held.

1. The swipe wall showed 9,800 REACTIONS on templates nobody had ever posted.
   The numbers were not even stored: the endpoint built likes_count from
   velocity_score * 1000 and hard-coded comments_count to 50, at render time,
   and the surface drew them as measurements. Analytics had already learned
   this lesson at migration 4; the swipe file had not, so one product held two
   surfaces to different standards.

2. /api/auth/status answered {"is_connected": true, "client_session": false} on
   an install holding no credentials, certifying a session in the same breath
   as reporting that none existed. The interface had already worked around it
   by reading the other field, which is the shape of a bug that survives
   because every caller routes around it.

3. The carousel renderer still imported three faces from Google after the
   interface stopped doing so, which fails the product's first constraint and,
   on an air-gapped machine, silently falls back mid-render.

4. A fresh clone could not start. frontend_next is gitignored, the fallback
   page is gone, and the build step appeared in no user-facing document and no
   launcher, so the studio answered 503 to everything.
"""

import os
import re

import pytest
from fastapi.testclient import TestClient

from app import app
from database import init_db

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")
SWIPE_SURFACE = os.path.join(UI_SRC, "components", "SwipeSurface.tsx")
CAROUSEL = os.path.join(REPO_ROOT, "studio", "backend", "carousel_engine.py")
README = os.path.join(REPO_ROOT, "README.md")
LAUNCHER = os.path.join(REPO_ROOT, "launch_studio.bat")

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def ensure_db():
    init_db()


def _read(path):
    if not os.path.exists(path):
        pytest.skip(f"{os.path.basename(path)} is not present in this checkout")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


# ---------------------------------------------------------------------------
# 1. The swipe file reports no engagement it did not observe
# ---------------------------------------------------------------------------


def test_shipped_specimens_carry_no_engagement_counts():
    """
    The defect measured at the endpoint, which is where the numbers were made.

    A shipped template was never posted, so it has no reactions and no
    comments. Null is the only honest answer; a number here is manufactured.
    """
    response = client.get("/api/inspirations")
    assert response.status_code == 200, response.text
    rows = response.json().get("inspirations", [])
    if not rows:
        pytest.skip("no specimens in this database")

    shipped = [r for r in rows if r.get("origin") == "shipped"]
    assert shipped, "no specimen reports its origin, so the column is not reaching the surface"

    for row in shipped:
        assert row.get("likes_count") is None, (
            f"{row.get('id')} reports {row.get('likes_count')} reactions on a post that "
            "was never made"
        )
        assert row.get("comments_count") is None, (
            f"{row.get('id')} reports {row.get('comments_count')} comments on a post that "
            "was never made"
        )


def test_velocity_survives_because_it_is_real():
    """
    The correction has to stop at the invented fields.

    velocity_score is a stored rating of how strongly a form performs, which is
    the entire point of a template library. Stripping it along with the
    fabricated counts would fix the honesty problem by removing the feature.
    """
    rows = client.get("/api/inspirations").json().get("inspirations", [])
    if not rows:
        pytest.skip("no specimens in this database")
    assert any(
        isinstance(r.get("velocity_score"), (int, float)) and r["velocity_score"] > 0
        for r in rows
    ), "every specimen lost its velocity score, so the library no longer ranks anything"


def test_the_origin_column_exists_to_be_read():
    """Guards the schema half: migration 9 has to have run."""
    from database import get_db

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(viral_templates)")
        columns = {row[1] for row in cursor.fetchall()}
    finally:
        conn.close()
    assert "origin" in columns, (
        "viral_templates has no origin column, so nothing can distinguish a "
        "shipped illustration from a captured post"
    )


def test_the_wall_states_what_it_is_showing():
    """
    The surface half, in the same terms Analytics already uses above its chart.
    """
    source = _read(SWIPE_SURFACE)
    assert "shipped" in source, "the surface never checks a specimen's origin"
    assert "never posted" in source.lower(), (
        "the specimen wall does not tell the reader that its contents were "
        "never posted, which is the statement the banner exists to make"
    )


# ---------------------------------------------------------------------------
# 2. The session flag reflects a session
# ---------------------------------------------------------------------------


def test_auth_status_does_not_certify_a_session_it_does_not_hold():
    """
    is_connected must require held credentials, not only a stored string.

    Asserted against the live response rather than the source, because the
    defect was a disagreement between two fields of one payload.
    """
    response = client.get("/api/auth/status")
    assert response.status_code == 200, response.text
    body = response.json()

    assert "is_connected" in body and "client_session" in body
    if not body["client_session"]:
        assert body["is_connected"] is False, (
            "the studio reports a LinkedIn connection while holding no usable "
            f"session: {body}"
        )


# ---------------------------------------------------------------------------
# 3. Nothing the backend renders fetches type from Google
# ---------------------------------------------------------------------------


def test_generated_decks_do_not_fetch_fonts():
    """
    Constraint 1, applied to the renderer that was still breaking it.

    A deck is produced on this machine and may be opened on one with no
    network, so a remote face is both an egress violation and a silent
    downgrade of the typography it was chosen for.
    """
    source = _read(CAROUSEL)
    assert "fonts.googleapis.com" not in source, (
        "the carousel renderer imports type from Google, so every generated "
        "deck reaches out"
    )
    assert "fonts.gstatic.com" not in source


def test_the_backend_renders_no_remote_resources_at_all():
    """
    The wider sweep, so the next renderer does not reintroduce it elsewhere.

    Scoped to font and stylesheet fetches inside generated markup. The backend
    legitimately calls provider APIs, and that is a separate question from
    whether a document it produces phones home when opened.
    """
    backend = os.path.join(REPO_ROOT, "studio", "backend")
    offenders = []
    for root, _dirs, files in os.walk(backend):
        if "__pycache__" in root:
            continue
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as handle:
                for number, line in enumerate(handle, start=1):
                    if re.search(r"@import\s+url\(\s*['\"]?https?://", line) or re.search(
                        r"<link[^>]+href=['\"]https?://", line
                    ):
                        offenders.append(
                            f"{os.path.relpath(path, REPO_ROOT)}:{number}: {line.strip()[:90]}"
                        )
    assert not offenders, "generated markup fetches a remote resource:\n  " + "\n  ".join(offenders)


# ---------------------------------------------------------------------------
# 4. A fresh clone can start
# ---------------------------------------------------------------------------


def test_the_readme_documents_the_build_step():
    """
    Removing the vanilla fallback was right; leaving the docs behind was not.

    Without this the sequence is: clone, pip install, run, 503, with nothing in
    the README to explain it.
    """
    readme = _read(README)
    source_section = readme[readme.index("Run from source"):] if "Run from source" in readme else readme

    assert "npm" in source_section, (
        "the run-from-source instructions never mention the interface build, so "
        "following them exactly produces a studio that serves 503"
    )
    assert "run build" in source_section, "the README stops short of the build command"


def test_the_launcher_builds_the_interface_when_it_is_absent():
    """
    The double-click path, which is the one that cannot read a 503 body.
    """
    launcher = _read(LAUNCHER)
    assert "frontend_next" in launcher, (
        "the launcher does not check whether the interface exists before starting "
        "a server that can only answer 503"
    )
    assert "run build" in launcher, "the launcher detects the missing build but cannot fix it"
    assert "nodejs.org" in launcher, (
        "the launcher needs npm and does not say where to get it when it is absent"
    )


# ---------------------------------------------------------------------------
# 5. Your own work is reachable without the CLI
# ---------------------------------------------------------------------------


def test_backup_is_reachable_from_the_interface():
    """
    Everything the studio holds is one file, and taking a copy used to require
    knowing the CLI existed. The endpoints were written and tested long before
    this interface, and no surface ever called them.
    """
    client_source = _read(os.path.join(UI_SRC, "lib", "api.ts"))
    for route in ("/api/v1/support/backup", "/api/v1/support/backups", "/api/v1/support/export"):
        assert route in client_source, f"{route} is still unreachable from the interface"


def test_the_backup_control_exists_on_a_surface():
    """A wrapper nothing renders is the same gap one level further in."""
    surface = _read(os.path.join(UI_SRC, "components", "BrandStudioSurface.tsx"))
    assert "createBackup" in surface, "nothing on any surface takes a backup"
    assert "fetchBackups" in surface, "the surface never shows what backups exist"


def test_taking_a_backup_actually_writes_one():
    """
    The behaviour, not the wiring.

    A control that reports success without producing a file is worse than no
    control, because it replaces a known gap with a false assurance.
    """
    before = client.get("/api/v1/support/backups")
    assert before.status_code == 200, before.text
    count_before = before.json().get("count", 0)

    made = client.post("/api/v1/support/backup", json={"label": "guard"})
    assert made.status_code == 200, made.text
    body = made.json()
    assert body.get("bytes", 0) > 0, "the backup reported success and wrote no bytes"
    assert os.path.exists(body["archive"]), f"the named archive does not exist: {body['archive']}"

    after = client.get("/api/v1/support/backups").json()
    assert after.get("count", 0) > count_before, "the new archive did not appear in the listing"
