"""
Reply to a commenter from the person page, with what the page already shows.
==========================================================================

Cycle 2, batch R5, D-3. The person page lists the comment and the post it was
on ("ON YOUR POST: ..."), and Reply to their comment still answered "Say which
post they commented on, above". The reply now uses the post the comment was
on when the creator has not typed one, so the flow Today starts ends in a
draft.
"""

from qc2_r5_live import open_section, seed_creator, server, studio  # noqa: F401


def _open_person(studio, name):
    page = open_section(studio, "leads")
    page.get_by_role("button", name=name).first.click()
    page.wait_for_selector("text=Recent interactions")
    return page


def test_reply_to_their_comment_drafts_from_the_post_the_page_shows(studio):
    seed_creator(studio["client"])
    page = _open_person(studio, "Anika Shah")
    assert "ON YOUR POST: Your on-call rota is a culture document." in page.inner_text("main")

    page.get_by_role("button", name="Reply to their comment").click()
    page.wait_for_selector("text=This matches what we saw last year", state="attached")
    body = page.inner_text("main")
    assert "Say which post they commented on" not in body, body
    draft = page.locator("p.whitespace-pre-wrap").first.inner_text()
    assert "Anika" in draft and "This matches what we saw last year" in draft, draft
    assert "Your on-call rota is a culture document" in draft, draft
    assert not studio["errors"]


def test_a_post_typed_by_the_creator_still_wins(studio):
    seed_creator(studio["client"])
    page = _open_person(studio, "Anika Shah")
    page.get_by_label("The post they engaged with").fill("on-call rotas")
    page.get_by_role("button", name="Reply to their comment").click()
    page.wait_for_selector("text=Reply to their comment >> xpath=..", state="attached")
    page.wait_for_function("() => document.body.innerText.includes('about on-call rotas')")
    draft = page.locator("p.whitespace-pre-wrap").first.inner_text()
    assert "about on-call rotas" in draft, draft


def test_the_field_names_the_post_it_will_use(studio):
    """The creator sees which post the draft will name before pressing anything."""
    seed_creator(studio["client"])
    page = _open_person(studio, "Anika Shah")
    placeholder = page.get_by_label("The post they engaged with").get_attribute("placeholder") or ""
    assert "Your on-call rota is a culture document" in placeholder, placeholder
