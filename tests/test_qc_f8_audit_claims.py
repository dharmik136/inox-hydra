"""
Quality cycle 2026-10, batch F8 [F2-N3]: the Distribution audit states no reach
effect the studio never measured.

Any draft with a link was told "-40% algorithmic reach penalty" (while the
score took off 35), heavy tagging that it "demotes post reach", and a 45 to 90
second read that it had "High algorithmic retention potential". LinkedIn has
published none of these figures and the studio has measured none of them. The
audit says what it found in the text, and advice as advice.
"""

import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from repurposer import audit_linkedin_algorithm_safety  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# A draft that trips every rule, and one that lands in the 45 to 90 second window.
EVERYTHING = (
    "Read the write-up at https://example.com/post — it matters.\n"
    "line two\nline three\nline four\nline five\n\n"
    "@ana @ben @cleo @dev thoughts?\n\n"
    "#a #b #c #d #e #f #g"
)
WINDOW = "\n\n".join(["We rebuilt the oven schedule this winter and the queue at seven vanished."] * 14)

INVENTED = re.compile(
    r"\d+\s*%|reach penalty|demotes?|suppress|algorithmic|retention|spam (filter|categori)|maximum optimal",
    re.IGNORECASE,
)


def _messages(text):
    audit = audit_linkedin_algorithm_safety(text)
    return audit["penalties"] + audit["recommendations"]


def test_no_audit_message_carries_an_unmeasured_figure_or_reach_claim():
    for text in (EVERYTHING, WINDOW):
        for message in _messages(text):
            assert not INVENTED.search(message), f"the audit states an unmeasured effect: {message!r}"


def test_the_audit_still_reports_what_it_found():
    audit = audit_linkedin_algorithm_safety(EVERYTHING)
    joined = " ".join(audit["penalties"]).lower()
    for found in ("link", "hashtag", "paragraph", "dash", "mention"):
        assert found in joined, f"the audit no longer reports the {found}"
    assert audit["has_outbound_links"] and audit["hashtag_count"] == 7 and audit["mention_count"] == 4


def test_the_help_article_no_longer_quotes_the_figure():
    with open(os.path.join(REPO_ROOT, "docs", "help", "check-a-draft-before-you-post.md"), encoding="utf-8") as handle:
        article = handle.read()
    assert "-40%" not in article
