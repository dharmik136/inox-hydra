"""
Publishing Claim Guard
======================
The studio offered to "Send this now", called the control "Publish now", and
answered the click with a green check reading PUBLISHED. Nothing reached
LinkedIn.

The endpoint behind that button, /api/posts/{post_id}/publish-now, sets a row's
status to published and stamps published_at. It opens no connection. So the
composer reported a delivery on the strength of a local write.

What makes this a defect rather than a limitation is that the product does have
a real path. linkedin_client.schedule_norm_share posts to Voyager's
contentcreation/normShares with the saved li_at and JSESSIONID, behind an
egress guard and a circuit breaker, and it is exposed at
/api/v1/scheduler/native/stage. The interface does not call it. The endpoint
parity diff that cleared the vanilla page missed it, which is worth recording:
a family can be absent from the interface and from the list of things known to
be absent.

So the interface is wired to the honest endpoint and now uses honest words for
it. Wiring the composer to the staging path is a product decision, not a bug
fix, because it posts to a real account.

The two halves asserted here:

  1. the endpoint the control calls cannot publish, measured at the handler
  2. the interface does not say that it did

If the control is ever pointed at the staging endpoint, half one fails first
and names the copy that should change with it.
"""

import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")

APP = os.path.join(BACKEND, "app.py")
PUBLISH_DIALOG = os.path.join(UI_SRC, "components", "PublishDialog.tsx")
CONTEXT_BAR = os.path.join(UI_SRC, "components", "ContextBar.tsx")
API_CLIENT = os.path.join(UI_SRC, "lib", "api.ts")

# Anything that would open a socket to another host.
OUTBOUND = re.compile(
    r"\brequests\.(get|post|put|patch|delete)\b"
    r"|\bhttpx\.(get|post|put|patch|delete|Client|AsyncClient)\b"
    r"|\baiohttp\."
    r"|\burlopen\("
)


def _read(path):
    if not os.path.exists(path):
        pytest.skip(f"{os.path.basename(path)} is not present in this checkout")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _handler(source, route):
    """The body of one route, up to the next decorated handler."""
    found = re.search(
        r'@app\.(?:post|get|put|patch|delete)\("' + re.escape(route) + r'".*?(?=\n@app\.)',
        source,
        re.DOTALL,
    )
    assert found, f"the handler for {route} has moved or been renamed"
    return found.group(0)


def test_the_endpoint_behind_the_button_only_writes_a_local_row():
    """
    Half one, measured at the handler rather than assumed from the product's
    architecture. The architecture allows publishing; this endpoint does not do
    it.
    """
    body = _handler(_read(APP), "/api/posts/{post_id}/publish-now")

    assert "UPDATE posts" in body, "publish-now no longer writes the post's status"
    assert not OUTBOUND.search(body), (
        "publish-now now makes an outbound request. If the control can report a "
        "real delivery, revisit the copy in PublishDialog.tsx rather than "
        "deleting this test"
    )


def test_the_interface_is_not_wired_to_the_staging_path():
    """
    Establishes why the copy has to be cautious, and fails loudly if that
    changes.

    /api/v1/scheduler/native/stage does reach LinkedIn. The day the composer
    calls it, "mark as published" becomes the wrong words in the other
    direction, and this test is where that is noticed.
    """
    # Comments are stripped first. api.ts documents the gap by naming the
    # endpoint, and a check against the raw file fails on its own explanation.
    client = re.sub(r"/\*.*?\*/", "", _read(API_CLIENT), flags=re.DOTALL)
    client = re.sub(r"//[^\n]*", "", client)

    assert "/api/v1/scheduler/native/stage" not in client, (
        "the interface now calls the native staging endpoint, which really does "
        "post to LinkedIn. The publish copy should be revisited: it currently "
        "tells the author that nothing is sent"
    )


def test_the_real_staging_path_still_exists():
    """
    Guards the premise of the test above.

    If the staging endpoint were deleted, the interface would be correct by
    accident rather than on purpose, and the note explaining the gap would be
    describing something that is no longer there.
    """
    app = _read(APP)
    assert "/api/v1/scheduler/native/stage" in app, (
        "the native staging endpoint is gone, so the gap this file documents no "
        "longer exists and the notes referring to it are stale"
    )


def test_the_dialog_does_not_offer_to_send_anything():
    """
    Half two. The control names the action it performs.

    "Send" and "Publish now" both describe transmission. What happens is a
    status write, so the verb is "mark".
    """
    source = _read(PUBLISH_DIALOG)

    # Scoped to what a reader sees. The module docstring explains the history
    # and necessarily contains the words it is explaining.
    rendered = source[source.index("return ("):]

    assert "Mark as published" in rendered, "the control no longer names what it does"
    assert "Publish now" not in rendered, (
        "the control claims to publish, which this endpoint does not do"
    )
    assert "Send this now" not in rendered, (
        "the dialog offers to send the post, and nothing is sent"
    )


def test_the_dialog_says_where_the_post_still_has_to_go():
    """
    Telling an author the truth is not enough if it leaves them stuck.

    Without this line the corrected copy reads as a feature that does less, and
    the author is not told that the posting is theirs to do.
    """
    rendered = _read(PUBLISH_DIALOG)
    rendered = rendered[rendered.index("return ("):]
    assert "LINKEDIN" in rendered.upper(), (
        "the dialog no longer explains that the post itself is still to be made"
    )


def test_the_composer_badge_does_not_claim_a_delivery():
    """
    The green check was the loudest part of the claim, and it is the part an
    author sees after the dialog closes.
    """
    source = _read(CONTEXT_BAR)

    published_branch = re.search(
        r'saveState === "published" &&(.{0,600}?)\)\}', source, re.DOTALL
    )
    assert published_branch, "the published branch of the context bar has moved"
    branch = published_branch.group(1)

    assert "MARKED AS PUBLISHED" in branch, (
        "the fallback badge reads as a delivery report rather than a record state"
    )
    assert not re.search(r'"PUBLISHED"', branch), (
        "the badge asserts the post was published, which the studio cannot know"
    )
