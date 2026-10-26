"""
Quality cycle 2026-10, batch F4b: who the creator is.
=====================================================

SETUP-02. A LinkedIn address may carry any letter: e-acute, u-umlaut, Chinese,
Cyrillic, Arabic, Devanagari. LinkedIn percent-encodes those in the URL and
the extension decodes them, and the studio's pattern accepted only a-z, 0-9,
'-', '_' and '%', so every profile capture for such a creator was refused and
Setup waited forever on step 2.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module
import onboarding
from database import get_db

client = TestClient(app_module.app)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OWN_PAGES = os.path.join(REPO_ROOT, "studio", "extension", "own_pages.js")

TABLES = ("creator_identity", "creator_positions", "creator_education", "creator_skills",
          "own_posts", "outbound_engagements", "self_import_requests")


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        conn = get_db()
        try:
            with conn:
                for table in TABLES:
                    conn.execute(f"DELETE FROM {table}")
                conn.execute("DELETE FROM settings WHERE key IN ('creator_profile', 'identity_filled_profile')")
        finally:
            conn.close()
    wipe()
    yield
    wipe()


def _observe(vanity, **extra):
    body = {"vanity": vanity, "display_name": "Sample Person", "self_evidence": ["owner_edit_controls"]}
    body.update(extra)
    return client.post("/api/v1/identity/observe", json=body)


# Each written as the extension reads it (decoded) and as the URL carries it.
UNICODE_VANITIES = [
    ("josé-sample-1a2b3c", "jos%C3%A9-sample-1a2b3c"),
    ("müller-sample", "m%C3%BCller-sample"),
    ("王伟-sample", "%E7%8E%8B%E4%BC%9F-sample"),
    ("иван-sample", "%D0%B8%D0%B2%D0%B0%D0%BD-sample"),
    ("محمد-sample", "%D9%85%D8%AD%D9%85%D8%AF-sample"),
    ("राहुल-sample", "%E0%A4%B0%E0%A4%BE%E0%A4%B9%E0%A5%81%E0%A4%B2-sample"),
]


@pytest.mark.parametrize("decoded,encoded", UNICODE_VANITIES)
def test_a_vanity_with_any_letter_is_one_identity_in_either_spelling(decoded, encoded):
    assert onboarding.normalise_vanity(decoded) == decoded
    assert onboarding.normalise_vanity(encoded) == decoded
    assert onboarding.normalise_vanity(encoded.lower()) == decoded
    assert onboarding.normalise_vanity(f"https://www.linkedin.com/in/{encoded}/?miniProfileUrn=x") == decoded


@pytest.mark.parametrize("decoded,encoded", UNICODE_VANITIES)
def test_a_creator_with_a_non_latin_address_can_finish_setup(decoded, encoded):
    result = _observe(decoded)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "candidate"

    assert client.post("/api/v1/identity/confirm", json={"vanity": encoded}).status_code == 200
    assert onboarding.confirmed_vanity() == decoded

    # The same person read again, from the profile URL, is still them.
    again = client.post("/api/v1/identity/observe", json={
        "profile_url": f"https://www.linkedin.com/in/{encoded}/", "headline": "Still me"}).json()
    assert again["status"] == "updated"

    # Their posts are accepted whichever spelling names them.
    urn = "urn:li:activity:7300000000000002002"
    for author in (decoded, encoded):
        posted = client.post("/api/v1/self/posts/ingest", json={
            "author": author, "posts": [{"activity_urn": urn, "actor": author}]})
        assert posted.status_code == 200, posted.text
        assert posted.json()["written"] == 1

    # And the history import opens a URL a browser can be handed.
    opened = client.post("/api/v1/self/imports", json={"kind": "posts"}).json()["open_url"]
    assert opened.isascii() and onboarding.normalise_vanity(opened) == decoded


def test_composed_and_decomposed_accents_are_the_same_person():
    composed, decomposed = "josé-sample", "josé-sample"
    assert onboarding.normalise_vanity(decomposed) == composed


@pytest.mark.parametrize("bad", ["", "-leading-dash", "a", "has space", "semi;colon", "slash/inside", "%ZZbroken"])
def test_what_is_not_a_vanity_is_still_refused(bad):
    assert onboarding.normalise_vanity(bad) == ""


def _vanity_of(href):
    """Runs the extension's vanityOf under node."""
    with open(OWN_PAGES, encoding="utf-8") as handle:
        source = handle.read()
    start = source.index("function vanityOf(")
    depth, i = 0, source.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        if depth == 0:
            break
        i += 1
    script = source[start:i + 1] + "\nprocess.stdout.write(JSON.stringify(vanityOf(" + json.dumps(href) + ")));"
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required to execute the extension logic")
@pytest.mark.parametrize("decoded,encoded", UNICODE_VANITIES)
def test_the_extension_reads_the_same_spelling_the_studio_keeps(decoded, encoded):
    href = f"https://www.linkedin.com/in/{encoded}/recent-activity/all/"
    assert _vanity_of(href) == onboarding.normalise_vanity(href) == decoded
    # A decomposed accent in the address is read as the studio spells it too.
    assert _vanity_of("https://www.linkedin.com/in/jose%CC%81-sample/") == "josé-sample"


# ---------------------------------------------------------------------------
# SETUP-08. Confirming fills Brand Studio's name, headline and company where
# they are empty. Forgetting left them, and confirming the right account then
# filled only blanks, so bylines and the watermark kept signing as the wrong
# person after Setup said everything was deleted.
# ---------------------------------------------------------------------------

def _brand():
    return client.get("/api/settings/profile").json()["profile"]


def _confirm_as(vanity, name, headline, company):
    observed = _observe(vanity, display_name=name, headline=headline, current_company=company).json()
    assert observed["status"] == "candidate"
    assert client.post("/api/v1/identity/confirm", json={"vanity": vanity}).status_code == 200


def test_forgetting_the_wrong_account_takes_back_what_it_filled_in():
    _confirm_as("sample-bob", "Sample Bob", "Bob's synthetic headline", "Bob Co")
    assert _brand()["name"] == "Sample Bob"

    assert client.delete("/api/v1/identity").status_code == 200
    brand = _brand()
    assert (brand["name"], brand["headline"], brand["company"]) == ("", "", "")

    _confirm_as("sample-carol", "Sample Carol", "Carol's headline", "Carol Co")
    brand = _brand()
    assert (brand["name"], brand["headline"], brand["company"]) == ("Sample Carol", "Carol's headline", "Carol Co")


def test_what_you_typed_in_brand_studio_survives_forgetting():
    profile = _brand()
    profile.update({"name": "", "headline": "The headline I wrote", "company": ""})
    assert client.post("/api/settings/profile", json=profile).status_code == 200

    _confirm_as("sample-bob", "Sample Bob", "Bob's synthetic headline", "Bob Co")
    # Saved again in Brand Studio, with one filled field edited by hand.
    profile = _brand()
    profile["company"] = "My own company"
    assert client.post("/api/settings/profile", json=profile).status_code == 200

    client.delete("/api/v1/identity")
    brand = _brand()
    assert brand["headline"] == "The headline I wrote"
    assert brand["company"] == "My own company"
    assert brand["name"] == "", "the name came from the forgotten account and was not changed since"


# ---------------------------------------------------------------------------
# SETUP-17. Capture health listed two "Voyager ... interception" rows that stay
# NOT SEEN YET for everyone, because network reading is off unless switched on
# in the extension, while the help said seven parts and to open the page.
# ---------------------------------------------------------------------------

HELP = os.path.join(REPO_ROOT, "docs", "help", "set-up-the-studio-from-your-linkedin.md")

# Capture health moved from Setup to its own section, Health, in cycle 4
# (track 4), and its description moved with it. The rule is unchanged: the
# screen that lists the readers lists exactly the parts its help describes.
HEALTH_HELP = os.path.join(REPO_ROOT, "docs", "help", "check-the-bridge-is-reading.md")


def _health_labels():
    return [entry["label"] for entry in client.get("/api/v1/bridge/readers").json()["readers"]]


def _help_parts():
    with open(HEALTH_HELP, encoding="utf-8") as handle:
        section = handle.read().split("## Which readers there are")[1].split("\n## ")[0]
    rows = [line for line in section.splitlines()
            if line.startswith("| ") and not line.startswith(("| Part", "| ---"))]
    return [row.split("|")[1].strip() for row in rows]


def test_capture_health_shows_what_the_help_describes():
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM captures")
    conn.close()
    labels = _health_labels()
    assert not any("voyager" in label.lower() for label in labels)
    assert labels == _help_parts()


def test_a_network_reading_part_appears_once_it_has_run():
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM captures")
    conn.close()
    client.post("/api/v1/bridge/voyager-ingest", json={"schema_name": "feed_updates", "data": []})
    try:
        labels = _health_labels()
        added = [label for label in labels if label not in _help_parts()]
        assert len(added) == 1 and "network reading" in added[0].lower()
        assert "voyager" not in added[0].lower()
        with open(HEALTH_HELP, encoding="utf-8") as handle:
            assert added[0] in handle.read(), "the help does not name the part the screen shows"
    finally:
        conn = get_db()
        with conn:
            conn.execute("DELETE FROM captures")
        conn.close()


# ---------------------------------------------------------------------------
# SETUP-18. The help never mentioned Sync All, and the panel's jargon
# ("Automates sequential ingestion") hid that it moves the bridge from one
# activity page to the next by itself, which the help's note said happens
# only after you click Import.
# ---------------------------------------------------------------------------

SETUP_SCREEN = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "OnboardingSurface.tsx")


def test_the_import_all_button_is_described_in_the_help():
    with open(SETUP_SCREEN, encoding="utf-8") as handle:
        screen = handle.read()
    with open(HELP, encoding="utf-8") as handle:
        help_text = handle.read()
    assert "Automates sequential ingestion" not in screen
    assert "Import your history" in screen
    step_five = help_text.split("## 5. Your history")[1].split("\n## ")[0]
    assert "**Import your history**" in step_five
    assert "one after another" in step_five and "by itself" in step_five
    assert "only after you click **Import**." not in step_five, "the note leaves out Import your history"


# ---------------------------------------------------------------------------
# SETUP-09 [BRIDGE-08]. The profile page shows the first few roles and two or
# three skills, with "Show all". Reading it replaced the full lists the
# details pages or the archive had brought, so 40 skills became 2 every time
# the creator opened their own profile.
# ---------------------------------------------------------------------------

SKILLS = [f"Sample Skill {i:02d}" for i in range(40)]
ROLES = [{"title": f"Role {i}", "company": f"Company {i}", "date_range": f"{2010 + i} - {2011 + i}"} for i in range(6)]


def _profile_page(**extra):
    """What captureProfile sends from /in/<you>/: the top card, and the sections it could see."""
    body = {"vanity": "sample-dana", "self_evidence": [], "display_name": "Sample Dana", "headline": "Builder",
            "location": None, "follower_count": None, "connection_count": None, "about": None}
    body.update(extra)
    return client.post("/api/v1/identity/observe", json=body)


def _lists():
    identity = client.get("/api/v1/onboarding/state").json()["identity"]
    return identity["skills"], [(p["title"], p["company"]) for p in identity["positions"]]


def _known_dana():
    assert _observe("sample-dana", display_name="Sample Dana").json()["status"] == "candidate"
    assert client.post("/api/v1/identity/confirm", json={"vanity": "sample-dana"}).status_code == 200
    # The details pages: whole lists.
    assert client.post("/api/v1/identity/observe", json={"vanity": "sample-dana", "skills": SKILLS}).status_code == 200
    assert client.post("/api/v1/identity/observe", json={"vanity": "sample-dana", "positions": ROLES}).status_code == 200


def test_opening_your_profile_keeps_the_full_lists():
    _known_dana()
    result = _profile_page(skills=["Sample Skill 00", "A Brand New Skill"],
                           positions=[{"title": "Role 5", "company": "Company 5", "date_range": "2015 - Present"},
                                      {"title": "New Role", "company": "New Company", "date_range": "2026 - Present"}])
    assert result.json()["status"] == "updated"
    skills, roles = _lists()
    assert len(skills) == 41 and "A Brand New Skill" in skills
    assert len(roles) == 7 and roles[0] == ("New Role", "New Company"), "a new role from the profile goes first"
    assert ("Role 0", "Company 0") in roles


def test_a_details_page_still_replaces_its_list():
    _known_dana()
    client.post("/api/v1/identity/observe", json={"vanity": "sample-dana", "skills": SKILLS[:35]})
    skills, _ = _lists()
    assert len(skills) == 35


def test_the_profile_read_before_you_confirm_does_not_shrink_the_archive_lists():
    conn = get_db()
    with conn:
        conn.executemany("INSERT INTO creator_skills (skill, observed_at) VALUES (?, '2026-10-01')",
                         [(s,) for s in SKILLS])
    conn.close()
    assert _profile_page(self_evidence=["owner_edit_controls"], skills=["Sample Skill 01"]).json()["status"] == "candidate"
    assert client.post("/api/v1/identity/confirm", json={"vanity": "sample-dana"}).status_code == 200
    skills, _ = _lists()
    assert len(skills) == 40
