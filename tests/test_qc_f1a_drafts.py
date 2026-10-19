"""
A save over a draft that changed since the editor loaded it is refused
======================================================================
The same draft open in two windows: whichever saved last silently replaced
the other's text, and the window that saved first still said SAVED, so the
creator believed both were kept.

The Composer now sends the text it last loaded or saved as base_content. When
the stored draft no longer matches it, the save is a 409 with a reason the
author can read, and nothing is written. A caller that sends no base_content
(the queue, the publish flow) is unchanged. The browser half, including
"Keep this version", is in tests/test_qc_f1a_composer.py.
"""

import os
import re

import pytest
from fastapi.testclient import TestClient

from app import app
from database import get_db

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
API_TS = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")

client = TestClient(app)


def _create(content):
    response = client.post("/api/posts", json={"content": content, "status": "draft"})
    assert response.status_code == 200
    return response.json()["id"]


def _stored(post_id):
    return next(row for row in client.get("/api/posts").json()["posts"] if row["id"] == post_id)["content"]


def test_the_later_of_two_saves_from_the_same_version_is_refused():
    post_id = _create("Shared opening.\n\nShared body.")

    first = client.put(f"/api/posts/{post_id}", json={
        "content": "Shared opening.\n\nShared body.\n\nWindow A's closing.",
        "base_content": "Shared opening.\n\nShared body.",
    })
    assert first.status_code == 200

    second = client.put(f"/api/posts/{post_id}", json={
        "content": "Window B fixed a typo.\n\nShared body.",
        "base_content": "Shared opening.\n\nShared body.",
    })
    assert second.status_code == 409, second.text
    assert "changed in another window" in second.json()["detail"]
    assert _stored(post_id) == "Shared opening.\n\nShared body.\n\nWindow A's closing.", "the stale save was written"


def test_a_save_from_the_current_version_goes_through():
    post_id = _create("v1")
    assert client.put(f"/api/posts/{post_id}", json={"content": "v2", "base_content": "v1"}).status_code == 200
    assert client.put(f"/api/posts/{post_id}", json={"content": "v3", "base_content": "v2"}).status_code == 200
    assert _stored(post_id) == "v3"


def test_a_caller_that_sends_no_base_is_unchanged():
    post_id = _create("v1")
    assert client.put(f"/api/posts/{post_id}", json={"content": "v2"}).status_code == 200
    assert client.put(f"/api/posts/{post_id}", json={"status": "draft"}).status_code == 200
    assert _stored(post_id) == "v2"


def test_the_interface_recognises_the_refusal_the_server_sends():
    """The client tells a conflict from any other failure by the server's own words."""
    detail = client.put(f"/api/posts/{_create('v1')}", json={"content": "x", "base_content": "v0"}).json()["detail"]
    source = open(API_TS, encoding="utf-8").read()
    marker = re.search(r'DRAFT_CHANGED_ELSEWHERE = "([^"]+)"', source)
    assert marker, "api.ts no longer names the phrase it recognises a conflict by"
    assert detail.startswith(marker.group(1)), (detail, marker.group(1))


# F1b-N1: the Composer clears after Publish, but any other client (a second
# tab, an old build) could still PUT new text over a post that is published,
# queued, due or sent. Such a post's text now changes only when the request
# says it means to.

LOCKED = ["published", "scheduled", "queued", "due", "sent"]


def _with_status(status):
    post_id = _create(f"The {status} text.")
    conn = get_db()
    try:
        conn.execute("UPDATE posts SET status = ? WHERE id = ?", (status, post_id))
        conn.commit()
    finally:
        conn.close()
    return post_id


@pytest.mark.parametrize("status", LOCKED)
def test_new_text_over_a_published_or_queued_post_is_refused(status):
    post_id = _with_status(status)
    refused = client.put(f"/api/posts/{post_id}", json={"content": "Next post, typed in a stale tab."})
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    # A code the interface acts on, distinct from the stale-draft refusal, and
    # words that name the two actions the Composer offers for it.
    assert detail["code"] == "posted_text_locked", detail
    assert detail["status"] == status
    assert "Correct the" in detail["message"] and "Save as a new draft" in detail["message"], detail
    assert "changed in another window" not in detail["message"]
    assert _stored(post_id) == f"The {status} text."


@pytest.mark.parametrize("status", LOCKED)
def test_editing_that_text_on_purpose_still_works(status):
    post_id = _with_status(status)
    meant = client.put(f"/api/posts/{post_id}", json={"content": "A typo fixed on purpose.", "edit_posted_text": True})
    assert meant.status_code == 200, meant.text
    assert _stored(post_id) == "A typo fixed on purpose."


def test_changes_that_leave_the_text_alone_are_not_refused():
    post_id = _with_status("scheduled")
    assert client.put(f"/api/posts/{post_id}", json={"content": "The scheduled text."}).status_code == 200
    assert client.put(f"/api/posts/{post_id}", json={"tags": ["x"]}).status_code == 200
    draft_id = _create("A draft")
    assert client.put(f"/api/posts/{draft_id}", json={"content": "Still a draft"}).status_code == 200


def _run_api_probe(probe_source):
    """Compiles studio/ui/src/lib/api.ts and runs a probe against it in node."""
    import json
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node") or shutil.which("node.exe")
    ui_dir = os.path.join(REPO_ROOT, "studio", "ui")
    esbuild = next((os.path.join(ui_dir, "node_modules", ".bin", n) for n in ("esbuild.cmd", "esbuild")
                    if os.path.exists(os.path.join(ui_dir, "node_modules", ".bin", n))), None)
    if not node or not esbuild:
        pytest.skip("node or the UI's esbuild is not installed")
    with tempfile.TemporaryDirectory() as work:
        build = subprocess.run([esbuild, API_TS, "--format=esm", f"--outfile={os.path.join(work, 'api.js')}"],
                               capture_output=True, text=True)
        assert build.returncode == 0, build.stderr
        with open(os.path.join(work, "probe.mjs"), "w", encoding="utf-8") as handle:
            handle.write(probe_source)
        run = subprocess.run([node, "probe.mjs"], capture_output=True, text=True, cwd=work)
        assert run.returncode == 0, run.stderr
        return json.loads(run.stdout)


def test_only_the_stale_draft_refusal_counts_as_changed_elsewhere():
    """
    Other refusals answer 409 too: new text over a queued post, and a write
    from a window showing another profile. Counting every 409 offered Keep
    this version for refusals it could never get past.
    """
    out = _run_api_probe("""
import { isDraftChangedElsewhere, isPostedTextLocked } from "./api.js";
const refusal = (message, status, code = null) => Object.assign(new Error(message), { status, code });
const stale = refusal("This draft was changed in another window after this one opened it, so saving would replace that version.", 409);
const locked = refusal("This post is already queued, so its text was not changed.", 409, "posted_text_locked");
const profile = refusal("This window shows another creator profile.", 409, "profile_mismatch");
console.log(JSON.stringify({
  changed: [stale, locked, profile].map(isDraftChangedElsewhere),
  locked: [stale, locked, profile].map(isPostedTextLocked),
}));
""")
    assert out == {"changed": [True, False, False], "locked": [False, True, False]}
