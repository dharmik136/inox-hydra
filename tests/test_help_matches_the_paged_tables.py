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


def test_the_analytics_article_gives_the_page_size_the_screen_uses():
    size = _constant("AnalyticsSurface.tsx", "ANALYTICS_PAGE_SIZE")
    article = _read(os.path.join(HELP, "read-your-analytics.md"))
    word = WORDS.get(size)
    assert word, f"no word for a page of {size}; add it to WORDS"
    assert re.search(rf"\b{word}\b", article, re.I) or f"{size} posts" in article, (
        f"the Analytics screen shows {size} posts a page and the article does not say so"
    )


def test_the_analytics_article_says_the_comparison_can_be_paged():
    article = _read(os.path.join(HELP, "read-your-analytics.md"))
    section = article.split("## Post comparison", 1)[1].split("\n## ", 1)[0]
    # Not the bare word "page": it already appeared in this section as "a
    # post's own analytics page", so the first version of this assertion
    # passed on an article that said nothing about paging at all.
    assert "turn the page" in section.lower() or "at a time" in section.lower(), (
        "the Post comparison section does not say the table is shown a page "
        "at a time, or how to turn it"
    )
    assert "most seen first" in section, (
        "the article does not give the order the table is actually in "
        "(the screen prints 'most seen first')"
    )


def test_the_analytics_article_scopes_the_impossible_rate_note_to_the_page():
    """
    The screen's note reads "N POSTS ON THIS PAGE HAVE MORE ENGAGEMENTS
    RECORDED THAN IMPRESSIONS". A creator who read it as a count of all their
    posts would draw the wrong conclusion from a page turn.
    """
    surface = _read(os.path.join(UI, "AnalyticsSurface.tsx"))
    assert "ON THIS PAGE" in surface, "the screen no longer scopes that note to the page"
    article = _read(os.path.join(HELP, "read-your-analytics.md"))
    assert "on the page you are looking at" in article, (
        "the article does not say the impossible-rate note counts only the page in view"
    )


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
