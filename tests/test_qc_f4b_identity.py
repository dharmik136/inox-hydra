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
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required to execute the extension logic")
@pytest.mark.parametrize("decoded,encoded", UNICODE_VANITIES)
def test_the_extension_reads_the_same_spelling_the_studio_keeps(decoded, encoded):
    href = f"https://www.linkedin.com/in/{encoded}/recent-activity/all/"
    assert _vanity_of(href) == onboarding.normalise_vanity(href) == decoded
    # A decomposed accent in the address is read as the studio spells it too.
    assert _vanity_of("https://www.linkedin.com/in/jose%CC%81-sample/") == "josé-sample"
