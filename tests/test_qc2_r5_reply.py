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


def test_a_comment_on_a_post_the_studio_lacks_never_borrows_another_post(studio):
    """
    Review send-back: the person reacted to a post the studio holds, then
    commented on one it does not. The reply named the post they only liked.
    """
    from qc2_r5_live import ME, urn_days_ago

    client = studio["client"]
    urns = seed_creator(client, commenter=None)
    person = {"full_name": "Meera Iyer", "profile_url": "https://www.linkedin.com/in/meera-iyer-x",
              "headline": "CTO at Trackwise", "company": "Trackwise"}
    liked = client.post("/api/v1/crm/interactions/ingest", json={
        **person, "interaction_type": "LIKE", "post_urn": urns[1], "post_author": ME})
    assert liked.status_code == 200, liked.text
    commented = client.post("/api/v1/crm/interactions/ingest", json={
        **person, "interaction_type": "COMMENT", "comment_text": "Great breakdown of the hiring freeze.",
        "post_urn": urn_days_ago(1, 99), "post_author": ME})
    assert commented.status_code == 200, commented.text

    page = _open_person(studio, "Meera Iyer")
    assert "Great breakdown of the hiring freeze." in page.inner_text("main")
    sent = []
    page.on("request", lambda request: "generate-dm" in request.url and sent.append(request.post_data_json))
    page.get_by_role("button", name="Reply to their comment").click()
    page.wait_for_selector("text=Say which post they commented on")
    assert sent and not sent[0].get("post_topic"), sent
    # No draft at all, rather than one about the post they only liked.
    assert page.locator("p.whitespace-pre-wrap").count() == 0
    placeholder = page.get_by_label("The post they engaged with").get_attribute("placeholder") or ""
    assert "does not hold the post they commented on" in placeholder, placeholder


def test_the_field_names_the_post_it_will_use(studio):
    """The creator sees which post the draft will name before pressing anything."""
    seed_creator(studio["client"])
    page = _open_person(studio, "Anika Shah")
    placeholder = page.get_by_label("The post they engaged with").get_attribute("placeholder") or ""
    assert "Your on-call rota is a culture document" in placeholder, placeholder
