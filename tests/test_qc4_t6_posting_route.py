"""
Decision D2's open question, answered from LinkedIn's documentation.
====================================================================

docs/OFFICIAL_POSTING_ROUTE.md answers whether LinkedIn's authorization
code flow can be completed by a public client with no secret, with the two
pages it read, their dates, and what the answer means for a desktop app
with no server. No OAuth code is written in this cycle, and this holds that
too.

Strict Invariants:
- Zero em-dashes.
"""

import io
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ANSWER = os.path.join(REPO_ROOT, "docs", "OFFICIAL_POSTING_ROUTE.md")


def _flat(path):
    with io.open(path, encoding="utf-8") as handle:
        return " ".join(handle.read().split())


def test_the_answer_cites_both_flows_with_their_dates():
    text = _flat(ANSWER)
    for source in ("https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow ",
                   "https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow-native",
                   "updated 2026-05-15", "updated 2023-04-03", "26 October 2026"):
        assert source in text, f"the answer does not cite {source!r}"


def test_the_answer_says_what_the_documentation_says():
    text = _flat(ANSWER)
    assert "Yes in LinkedIn's documentation, but not self-serve." in text
    assert "client_secret" in text and "code_verifier" in text and "native-pkce/authorization" in text
    assert "please reach out to your point of contact at LinkedIn, and we will enable PKCE OAuth 2 flow for your app" in text
    assert "no server of ours" in text
    assert "## Recommendation" in text


def test_no_oauth_code_is_written_this_cycle():
    backend = os.path.join(REPO_ROOT, "studio", "backend")
    hits = []
    for base, _dirs, files in os.walk(backend):
        for name in files:
            if name.endswith(".py"):
                with io.open(os.path.join(base, name), encoding="utf-8") as handle:
                    if re.search(r"oauth/v2|oauth/native-pkce|code_verifier|w_member_social", handle.read()):
                        hits.append(name)
    assert hits == [], f"OAuth code appeared before LinkedIn enabled the flow for the app: {hits}"


def test_each_page_is_quoted_in_its_own_words():
    """Review note N-19: the 3-legged page writes "60-day", and the refresh skips consent on two conditions."""
    text = _flat(ANSWER)
    assert 'Both pages: "Currently' not in text
    assert "60-day lifespan" in text and "60 day lifespan" in text
    assert "current access token has not expired" in text
