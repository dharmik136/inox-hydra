"""
The interface's type for a person on Today is what Today sends.
==============================================================

today._reply_to sends each person's engaged_at, when the studio first saw
their latest comment, and the Reply to rows print it. The shared TodayPerson
type in api.ts left it out, so TodaySurface.tsx patched a second type
beside it (cycle 4, track 3, batch 0, from the sections report's defects
table). A field a screen reads that its type does not declare is a field
the next screen will not know exists.

The keys Today actually answers with are read here from a live brief and
compared with the fields the interface declares.
"""

import os
import re
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

API = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")
SURFACE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "TodaySurface.tsx")
URN = "urn:li:activity:7380000000000000201"


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t3_person_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    import datetime as dt
    today = dt.datetime.now(dt.timezone.utc).isoformat()
    conn = get_db()
    with conn:
        # Today lists people to reply to only once the creator has confirmed
        # who they are, as Setup's first steps do.
        conn.execute("INSERT OR REPLACE INTO creator_identity (id, vanity, display_name, confirmed_at) "
                     "VALUES (1, 'priya-raman', 'Priya Raman', ?)", (today,))
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, reactions, first_seen_at, last_seen_at) "
                     "VALUES (?, 'A post.', ?, 3, ?, ?)", (URN, today, today, today))
        conn.execute("INSERT INTO leads (id, name, full_name, headline) VALUES ('lead-asha', 'Asha Rao', 'Asha Rao', 'Baker')")
        conn.execute("INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at) "
                     "VALUES ('lead-asha', ?, 'COMMENT', 'Lovely crumb.', ?)", (URN, today))
    conn.close()
    import app as app_module
    from fastapi.testclient import TestClient
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def _declared_fields():
    with open(API, encoding="utf-8") as handle:
        block = handle.read().split("export interface TodayPerson {", 1)[1].split("\n}", 1)[0]
    return set(re.findall(r"^\s*([a-z_]+)\??:", block, re.M))


def test_the_type_declares_every_field_today_sends(studio):
    answer = studio.get("/api/v1/today")
    assert answer.status_code == 200, answer.text
    people = answer.json()["reply_to"]
    assert people and people[0]["name"] == "Asha Rao", people
    sent = set(people[0])
    assert "engaged_at" in sent
    declared = _declared_fields()
    assert sent == declared, f"Today sends {sorted(sent)}; the interface declares {sorted(declared)}"


def test_the_screen_patches_no_second_type_beside_it():
    with open(SURFACE, encoding="utf-8") as handle:
        source = handle.read()
    assert not re.search(r"=\s*TodayPerson\s*&", source), "TodaySurface.tsx still patches TodayPerson with a local type"
