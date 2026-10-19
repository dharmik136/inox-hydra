"""
Insert into LinkedIn Composer types into the post composer, and nowhere else.
============================================================================

BRIDGE-06  The editor was the first matching box in document order, and
           LinkedIn's comment boxes and message boxes are the same kind of
           editor as the composer, which renders last, in a modal. The draft
           landed in a comment box behind the composer, or in an open message
           to a contact, and the page said it had been placed in the composer.

These run the shipped content.js in headless Chromium (see qc_f3_pages.py)
and send it the message the side panel sends.
"""

import pytest

from qc_f3_pages import Pages, page_html, toast_text

DRAFT = "Three things I learned shipping a local-first app this year."

COMMENT_BOX_AND_COMPOSER = page_html("""
<main>
 <div class="share-box-feed-entry"><button class="share-box-feed-entry__trigger">Start a post</button></div>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7385000000000000077">
   <div class="update-components-text">Somebody else's post.</div>
   <div class="comments-comment-box"><div class="ql-editor" contenteditable="true" id="comment-box" data-placeholder="Add a comment..."><p><br></p></div></div>
 </div>
</main>
<div id="artdeco-modal-outlet">
 <div class="artdeco-modal share-creation-state" role="dialog">
   <h2>Create a post</h2>
   <div class="share-creation-state__text-editor"><div class="ql-editor" contenteditable="true" id="post-composer" data-placeholder="What do you want to talk about?"><p><br></p></div></div>
 </div>
</div>
""")

MESSAGE_OPEN_COMPOSER_CLOSED = page_html("""
<main>
 <div class="share-box-feed-entry"><button class="share-box-feed-entry__trigger" onclick="document.getElementById('outlet').innerHTML='<div role=dialog><div class=ql-editor contenteditable=true id=post-composer></div></div>'">Start a post</button></div>
</main>
<aside class="msg-overlay-list-bubble">
  <div class="msg-form__contenteditable" contenteditable="true" role="textbox" id="dm-box" aria-label="Write a message..."><p><br></p></div>
</aside>
<div id="outlet"></div>
""")

POST_PAGE_NO_COMPOSER = page_html("""
<main>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7385000000000000077">
   <div class="update-components-text">Somebody else's post.</div>
   <div class="comments-comment-box"><div class="ql-editor" contenteditable="true" id="comment-box" data-placeholder="Add a comment..."><p><br></p></div></div>
 </div>
</main>
<div role="dialog" aria-label="Messaging"><div contenteditable="true" role="textbox" id="dm-dialog" aria-label="Write a message..."></div></div>
""")

INSERT = """(draft) => new Promise((resolve) => {
  for (const fn of window.__messageListeners) fn({ action: 'INJECT_POST', content: draft }, {}, resolve);
})"""
BOXES = "() => Object.fromEntries(Array.from(document.querySelectorAll('[contenteditable=true]')).map(e => [e.id, e.innerText.trim()]))"


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _insert(page):
    promise = page.evaluate_handle(INSERT, DRAFT)
    page.clock.run_for(2000)
    return promise.json_value()


def test_an_open_comment_box_does_not_take_the_draft(pages):
    page = pages.open("/feed/", COMMENT_BOX_AND_COMPOSER)
    answer = _insert(page)
    boxes = page.evaluate(BOXES)
    assert boxes["comment-box"] == ""
    assert boxes["post-composer"] == DRAFT
    assert answer == {"status": "success"}


def test_an_open_message_does_not_take_the_draft(pages):
    page = pages.open("/feed/", MESSAGE_OPEN_COMPOSER_CLOSED)
    answer = _insert(page)
    boxes = page.evaluate(BOXES)
    assert boxes["dm-box"] == ""
    assert boxes["post-composer"] == DRAFT
    assert answer == {"status": "success"}


def test_with_no_composer_to_open_nothing_is_typed_anywhere(pages):
    page = pages.open("/feed/update/urn:li:activity:7385000000000000077/", POST_PAGE_NO_COMPOSER)
    answer = _insert(page)
    boxes = page.evaluate(BOXES)
    assert boxes == {"comment-box": "", "dm-dialog": ""}
    assert answer == {"status": "failed"}
    assert "injected" not in (toast_text(page) or "")
