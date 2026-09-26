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


def test_a_live_send_exists_and_is_guarded():
    """
    This replaces a tripwire, and the reason is worth recording.

    The previous version asserted that api.ts did not contain the string
    "/api/v1/scheduler/native/stage", to catch the day the composer gained a
    real send. That day came, the send was wired through a different route,
    /api/v1/posts/{id}/stage-to-linkedin, and the test stayed green while its
    own premise went false. It guarded a spelling rather than a property.

    So this asserts the property: if the interface can reach LinkedIn, the
    guards that make that defensible have to be present. Matched by shape
    rather than by exact path, so renaming the route does not silently reopen
    the gap a second time.
    """
    client = re.sub(r"/\*.*?\*/", "", _read(API_CLIENT), flags=re.DOTALL)
    client = re.sub(r"//[^\n]*", "", client)

    sends = re.findall(r"/api/[^\s\"'`]*stage[^\s\"'`]*", client)
    if not sends:
        pytest.skip("the interface has no live send, which is also a valid state")

    app = _read(APP)
    assert "confirm" in app, "the live send has no confirmation requirement"
    assert 'result.get("mode") == "mock"' in app, (
        "a mock run could be reported to the author as a real send, which is "
        "the defect this route introduced once already"
    )


def test_the_live_send_asks_a_second_time():
    """
    The action cannot be undone from this side, so one press is the wrong
    interface for it. Asserted on the component's state rather than on the
    copy, because copy gets reworded and a state machine does not vanish by
    accident.
    """
    source = _read(PUBLISH_DIALOG)
    if "stageToLinkedIn" not in source:
        pytest.skip("the dialog has no live send")

    assert "confirmingSend" in source, "the live send fires on one press"
    assert "cannot be undone" in source, (
        "nothing tells the author that this one is irreversible"
    )


def test_the_local_actions_still_say_they_are_local():
    """
    Adding a real send must not blur the two that are not. The earlier copy
    said "neither sends anything", which was true of two controls and is the
    wrong sentence for three.
    """
    rendered = _read(PUBLISH_DIALOG)
    rendered = rendered[rendered.index("return ("):]

    assert "NEITHER OF THOSE TWO SENDS ANYTHING" in rendered, (
        "the local actions no longer distinguish themselves from the live one"
    )
    assert "Mark as published" in rendered, (
        "the honest control for a post the author published themselves is gone"
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
