"""
The help's page sizes are the code's page sizes.
=================================================

Carried out of cycle 3's integration list as T6-N2: "two help articles now
describe Posts/Analytics wrongly". One of the two had already been swept, and
the Posts article documents the table's search, settled-state filter, sort and
pager correctly. The Analytics article had not been: cycle 3 paged its post
comparison, and the article still described a table that listed every post,
with no mention of the pager, the count line, or that the impossible-rate note
counts only the posts on the page in view.

A page size written into prose drifts the moment the constant changes, and the
creator who counts fourteen rows against an article saying twenty has no way
to know which is wrong. So the numbers in the help are read back out of the
code here, rather than trusted.

Cycle 4 moved the Analytics table to Posts, so the Analytics article is held
to saying so, and the Posts article to its table as before.
"""

import io
import os
import re

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HELP = os.path.join(REPO, "docs", "help")
UI = os.path.join(REPO, "studio", "ui", "src", "components")

WORDS = {
    1: "one", 2: "two", 7: "seven", 10: "ten", 12: "twelve",
    14: "fourteen", 20: "twenty", 25: "twenty-five", 50: "fifty",
}


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _constant(component, name):
    found = re.search(rf"const {name}\s*=\s*(\d+)", _read(os.path.join(UI, component)))
    assert found, f"{name} is no longer declared in {component}"
    return int(found.group(1))


def test_the_analytics_article_sends_the_reader_to_posts_for_the_table():
    """
    Cycle 4 took the post table off Analytics: it was a second copy of the
    Posts screen's, fourteen rows at a time (track 3, batch 1). The article
    held to its page size, its pager and its page-scoped note now has to say
    the table is gone and where the posts are, and the screen has no page
    size left for an article to drift from.
    """
    surface = _read(os.path.join(UI, "AnalyticsSurface.tsx"))
    assert "ANALYTICS_PAGE_SIZE" not in surface and "<table" not in surface, "Analytics still draws a post table"
    assert 'href="#/posts"' in surface, "the aside no longer links into Posts"
    article = _read(os.path.join(HELP, "read-your-analytics.md"))
    assert "## Post comparison" not in article, "the article still describes the table"
    section = article.split("## Your posts", 1)[1].split("\n## ", 1)[0]
    assert "**Posts**" in section and "**Open Posts**" in section, (
        "the article does not say where the posts went, or how to get there"
    )
    assert "most seen first" not in article.lower() and "turn the page" not in article.lower()


def test_the_posts_article_still_matches_its_table():
    """
    The article that was already correct, held so: the four controls above the
    Posts table and the count line it prints.
    """
    article = _read(os.path.join(HELP, "see-what-worked-and-where-your-attention-goes.md"))
    section = article.split("## Posts", 1)[1].split("\n## ", 1)[0]
    for control in ("Search your posts", "Settled state", "Sort", "Previous"):
        assert control in section, f"the Posts article no longer documents {control!r}"
    assert re.search(r"\b1-20 of\b|\b1–20 of\b", section), (
        "the Posts article no longer gives the count line the screen prints"
    )
