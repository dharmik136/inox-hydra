"""
The help says where the bridge captures leads, and nowhere else.
================================================================

BRIDGE-13  The capture table in "Install the browser extension" said
           commenters are captured on "Feed, post pages and activity pages",
           but the engager reader deliberately skips every /in/ page, which is
           where activity pages live. Creators looked at their posts' comments
           on their activity page, saw nothing captured and no notice, and
           concluded capture was broken.
"""

import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ARTICLE = os.path.join(REPO_ROOT, "docs", "help", "install-the-browser-extension.md")
CONTENT_JS = os.path.join(REPO_ROOT, "studio", "extension", "content.js")


def _lead_rows():
    with open(ARTICLE, encoding="utf-8") as handle:
        rows = [line for line in handle if line.startswith("|") and "**Leads**" in line]
    assert rows, "the capture table no longer names where leads come from"
    return rows


def test_the_capture_table_names_only_pages_the_engager_reader_reads():
    with open(CONTENT_JS, encoding="utf-8") as handle:
        source = handle.read()
    gate = source[source.index("function isPostEngagementSurface"):]
    gate = re.sub(r"//[^\n]*", "", gate[:gate.index("\n}")])
    assert '"/in/"' not in gate and "startsWith(\"/in/\")" not in gate
    for row in _lead_rows():
        where = row.split("|")[1].lower()
        assert "activity page" not in where, row


def test_the_article_does_not_undercount_what_the_page_scripts_can_reach():
    # F3-N1: it said "just three studio functions" while the worker relayed
    # fifteen, including the heartbeat, the own-profile and history routes and
    # the two network reading routes (retired in 2.10.2).
    background = os.path.join(REPO_ROOT, "studio", "extension", "background.js")
    with open(background, encoding="utf-8") as handle:
        relayed = re.findall(r'"(/api/[^"]+)"', handle.read().split("RELAYABLE_PATHS = new Set([")[1].split("]);")[0])
    assert len(relayed) > 3
    with open(ARTICLE, encoding="utf-8") as handle:
        text = handle.read()
    assert "just three studio functions" not in text
    paragraph = next(p for p in text.split("\n\n") if "runs inside LinkedIn pages" in p)
    for words in ("heartbeat", "your own profile", "history imports"):
        assert words in paragraph, words
    # The two network reading routes left the list in 2.10.2, when network
    # reading was retired, and the article no longer offers them.
    assert "network reading" not in paragraph, "the article still lists network reading's routes"


def test_the_article_says_activity_pages_are_not_read_for_leads():
    with open(ARTICLE, encoding="utf-8") as handle:
        text = handle.read()
    assert re.search(r"activity pages?\b.{0,80}?\bnot read for leads", text, re.IGNORECASE)
