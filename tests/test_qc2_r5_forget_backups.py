"""
Deleting a person says where they still are.
===========================================

Cycle 2, R4-N3 (found by batch R4, fixed in R5's Leads screen). Batch R4
added secure delete and removal from backups. Leads' Forget this person, and
its delete of leads that engaged only with other people's posts, said nothing
of backups: the person stays in older backups until rotation removes them,
and Settings, Storage and privacy is where to remove them from backups
too.
"""

import os

from qc2_r5_live import open_section, seed_creator, server, studio  # noqa: F401

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SENTENCE = "Older backups still hold them until rotation removes those backups"


def test_forget_this_person_says_backups_keep_them(studio):
    seed_creator(studio["client"])
    page = open_section(studio, "leads")
    page.get_by_role("button", name="Anika Shah").first.click()
    page.get_by_role("button", name="Forget this person").click()
    text = page.locator("section", has_text="Forgetting removes this person").inner_text()
    assert SENTENCE in text, text
    # Settings since Brand Studio split in two (cycle 4, track 4, phase b).
    assert "Settings, Storage and privacy" in text, text


def test_the_bulk_delete_confirmation_and_the_help_say_so_too():
    with open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "LeadsSurface.tsx"), encoding="utf-8") as h:
        code = h.read()
    assert code.count("{BACKUPS_KEEP_THEM}") == 2, "both delete paths name what backups keep"
    with open(os.path.join(REPO_ROOT, "docs", "help", "review-leads-and-draft-a-message.md"), encoding="utf-8") as h:
        assert "**Settings**, **Storage and privacy**" in h.read()
