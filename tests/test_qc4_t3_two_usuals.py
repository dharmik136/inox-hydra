"""
Each screen names which "usual" it compares against.
====================================================

Today compares the latest post, at about two days old, with the median of
the creator's earlier posts read at the same age. Posts compares each
settled post with the median of the posts older than the settle age. Both
are "your usual", both come from results.py's primitives, and the two
medians answer differently by construction; no screen said so (cycle 4,
track 3, batch 0, from the sections report's defects table). Each screen now
says which usual it means, and Today says that Posts' is a different figure.
"""

import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COMPONENTS = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")


def _read(name):
    with open(os.path.join(COMPONENTS, name), encoding="utf-8") as handle:
        return handle.read()


def test_today_names_its_usual_and_says_posts_differs():
    source = _read("TodaySurface.tsx")
    assert "AGAINST YOUR USUAL" in source
    assert "READ AT THE SAME AGE" in source, "Today does not say its usual is the median at the same age"
    assert "POSTS COMPARES SETTLED POSTS" in source, "Today does not say that Posts' usual is a different figure"


def test_posts_names_its_usual():
    source = _read("PostsSurface.tsx")
    assert "Your usual, the median of your posts older than" in source
