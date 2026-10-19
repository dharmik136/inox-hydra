"""
What the Publish dialog says leaves the machine.
================================================

UX-15 (the Publish dialog's part): the studio said elsewhere that drafts and
the LinkedIn session never leave the machine, while Send to LinkedIn sends the
post's text to LinkedIn, signed in with the stored session. The dialog said
only that the control "really sends", so a creator could not tell that the
text and the session were what left.
"""

import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIALOG = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "PublishDialog.tsx")


def _rendered():
    with open(DIALOG, encoding="utf-8") as handle:
        source = handle.read()
    source = source[source.index("return ("):]
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)
    return " ".join(source.replace("&apos;", "'").split())


def test_the_send_says_the_text_and_the_session_leave_the_machine():
    text = _rendered()
    assert "THE POST'S TEXT LEAVES THIS MACHINE FOR LINKEDIN, SIGNED IN WITH YOUR SAVED LINKEDIN SESSION" in text
    assert "This sends the post's text to LinkedIn, signed in with your saved LinkedIn session" in text


def test_the_dialog_promises_nothing_never_leaves():
    text = _rendered().lower()
    assert "never leave" not in text
    assert "never leaves" not in text
