"""
Batch R5, D-15. The article on writing and saving still said the Composer
keeps working on the same post after Publish, and told the reader to reload
before starting the next one. That stopped being true when the editor began
to clear after Publish (WRITE-02), and the sibling article says so.
"""

import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_the_save_article_says_the_composer_clears_after_publish():
    with open(os.path.join(REPO_ROOT, "docs", "help", "write-format-and-save-a-post.md"), encoding="utf-8") as handle:
        text = handle.read()
    assert "keeps working on that same post" not in text
    assert "reload the page first" not in text
    assert re.search(r"editor clears", text), "the article does not say the editor clears after Publish"
