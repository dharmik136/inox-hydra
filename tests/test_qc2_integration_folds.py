"""
Integration of batches R3 and R4: the per-post leads drawer after a fold.

A post's leads drawer counts the folded reactors with no names, so its count
can be larger than its list of names. The drawer says how many are counts
only, and a post whose every lead was folded is not shown as having none.
"""

import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI = os.path.join(REPO_ROOT, "studio", "ui", "src")


def _read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as handle:
        return handle.read()


def test_the_drawer_says_how_many_leads_are_kept_only_as_counts():
    """
    The drawer lived under Analytics' post table, which cycle 4 moved to Posts
    (track 3, batch 1). The property moved with it, to the detail the Posts
    table opens into: the engagers route carries the post's folded people,
    the detail says how many are counts only, and a post whose every engager
    was folded is not shown as having nobody.
    """
    api = _read("lib", "api.ts")
    assert "folded_people: data.folded?.people ?? 0" in api
    detail = _read("components", "PostDetail.tsx")
    assert "foldedPeople > 0" in detail
    assert "KEPT AS A COUNT" in detail
    # Every lead folded is still a lead: the empty line needs no count at all.
    assert "engagers.length === 0 && foldedPeople === 0" in detail


def test_the_fold_confirmation_says_a_list_of_names_can_be_shorter_than_the_count():
    panel = _read("components", "StoragePrivacyWorkspace.tsx")
    assert "list of names can be shorter than its" in panel
