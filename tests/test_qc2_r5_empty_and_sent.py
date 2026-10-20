"""
Empty screens end in the button that fills them; a copied message offers its next step.
====================================================================================

Cycle 2, batch R5, D-22 and D-24. Posts, Patterns and Outbound said "Import
them in Setup" with no way there but the rail. On Leads, after COPY of a
drafted message nothing offered to record it as sent, so the person stayed on
Today until the stage was changed by hand, and the find box's placeholder was
cut off at "headlin".
"""

import pytest

from qc2_r5_live import confirm_identity, open_section, seed_creator, server, studio  # noqa: F401


@pytest.mark.parametrize("section", ["posts", "patterns", "outbound"])
def test_an_empty_screen_goes_to_setup(studio, section):
    confirm_identity(studio["client"])
    page = open_section(studio, section)
    page.get_by_role("button", name="Go to Setup").click()
    page.wait_for_selector("text=Teach the studio who you are")
    assert page.url.endswith("#/setup"), page.url


def test_a_copied_message_offers_to_record_it_as_sent(studio):
    seed_creator(studio["client"])
    studio["context"].grant_permissions(["clipboard-read", "clipboard-write"])
    page = open_section(studio, "leads")
    page.get_by_role("button", name="Anika Shah").first.click()
    page.get_by_role("button", name="Reply to their comment").click()
    page.get_by_role("button", name="COPY").click()
    page.get_by_role("button", name="Mark as Outreach Sent").click()
    page.wait_for_selector("button[aria-pressed='true']:has-text('Outreach Sent')")
    assert page.get_by_role("button", name="Mark as Outreach Sent").count() == 0
    assert not studio["errors"]


def test_the_find_box_placeholder_fits(studio):
    seed_creator(studio["client"])
    page = open_section(studio, "leads")
    box = page.get_by_label("Find a lead")
    fits = box.evaluate(
        """(input) => {
            const probe = document.createElement('span');
            const style = getComputedStyle(input);
            probe.style.font = style.font;
            probe.style.position = 'absolute';
            probe.style.visibility = 'hidden';
            probe.textContent = input.placeholder;
            document.body.appendChild(probe);
            const room = input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
            const needed = probe.getBoundingClientRect().width;
            probe.remove();
            return needed <= room;
        }"""
    )
    assert fits, box.get_attribute("placeholder")
