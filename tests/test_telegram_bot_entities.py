"""
Text kept whole: links behind words, and tags (phase 4, item 11).
=================================================================

What collection.py already derived before this item: a message's hashtags
as its tags (lower case, each once, up to 30), a topic, and every LinkedIn
post link rebuilt from its id. What was lost: a link hidden behind words (a
text_link entity, its offsets in UTF-16 code units), which Telegram sends
beside the text, never in it. It is now written into the item's words right
after the words it hides behind, so it is kept, shown, found and written
from, and a LinkedIn post link behind words is treated as a visible one. A
caption's entities likewise. /recall #tag matches the item's tags. A link's
#fragment is not a hashtag.

docs/quality/cycle4/bot-phase4.md, item 11. Against the fake Bot API.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_collection_box import _items, _send  # noqa: E402
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _own_post, _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES


def _units(text):
    return len(text.encode("utf-16-le")) // 2


def _link(text, words, url):
    """A text_link entity over `words` in `text`, with offsets in UTF-16 code units as Telegram sends them."""
    start = text.index(words)
    return {"type": "text_link", "offset": _units(text[:start]), "length": _units(words), "url": url}


def test_a_link_behind_words_is_kept_after_them(bot):
    _saved(bot)
    text = "Read this before the call on pricing"
    _send(bot, text, entities=[_link(text, "this", "https://example.com/pricing-notes")])
    [item] = _items()
    assert item["text"] == "Read this https://example.com/pricing-notes before the call on pricing"


def test_offsets_are_read_in_utf16_as_telegram_counts_them(bot):
    _saved(bot)
    text = "\U0001F680 launch notes: see the draft here"
    _send(bot, text, entities=[_link(text, "the draft", "https://example.com/d")])
    [item] = _items()
    assert item["text"] == "\U0001F680 launch notes: see the draft https://example.com/d here"


def test_someone_elses_post_behind_words_is_a_bookmark_without_its_slug(bot):
    _saved(bot)
    url = "https://www.linkedin.com/posts/jane-doe-pricing-secrets-activity-7390000000000000777-AbCd?utm_source=x"
    text = "Worth reading for the pricing angle"
    assert _send(bot, text, entities=[_link(text, "Worth reading", url)]) == SAID["bookmarked"]
    [item] = _items()
    assert item["kind"] == "bookmark"
    assert item["link"] == "https://www.linkedin.com/feed/update/urn:li:activity:7390000000000000777/"
    assert "jane-doe" not in json.dumps(item), "the slug that names the author was kept"


def test_one_of_your_posts_behind_words_is_a_request_on_today(bot):
    _saved(bot)
    urn = _own_post(bot)
    text = "check how my post did"
    answer = _send(bot, text, entities=[_link(text, "my post", f"https://www.linkedin.com/feed/update/{urn}/")])
    assert answer == f"{SAID['collected']} {SAID['post']}", answer
    conn = get_db()
    requests = conn.execute("SELECT activity_urn FROM desk_requests").fetchall()
    conn.close()
    assert [r[0] for r in requests] == [urn]


def test_a_captions_link_behind_words_is_kept(bot):
    _saved(bot)
    jpeg = b"\xff\xd8\xff\xe0" + b"photo" * 20
    bot["fake"].add_file("ph-1", jpeg, "photos/ph1.jpg")
    caption = "the whiteboard from the workshop"
    _send(bot, None, photo=[{"file_id": "ph-1", "file_unique_id": "p1", "width": 9, "height": 9,
                             "file_size": len(jpeg)}], caption=caption,
          caption_entities=[_link(caption, "the workshop", "https://example.com/workshop")])
    [item] = _items()
    assert item["text"] == "the whiteboard from the workshop https://example.com/workshop"


def test_only_web_addresses_are_written_in(bot):
    _saved(bot)
    text = "ask Sam about it"
    _send(bot, text, entities=[_link(text, "Sam", "tg://user?id=123456")])
    assert _items()[0]["text"] == "ask Sam about it"


def test_hashtags_were_already_tags_and_a_links_fragment_is_not_one(bot):
    _saved(bot)
    _send(bot, "a note on #Pricing and #hiring, see https://example.com/page#section")
    [item] = _items()
    assert item["tags"] == ["pricing", "hiring"], item["tags"]


def test_recall_a_tag_matches_the_items_tags(bot):
    import collection
    _saved(bot)
    collection.add("note", "an old draft idea from the archive", tags=["pricing"])
    collection.add("note", "nothing to do with it", tags=["hiring"])
    bot["fake"].push(OWNER, "/recall #pricing")
    assert _until(lambda: _texts(bot)[-1:] == [SAID["recall_one"]]), _texts(bot)


def test_an_edit_keeps_a_link_behind_words(bot):
    _saved(bot)
    update_id = bot["fake"].push(OWNER, "see the notes")
    assert _until(lambda: len(_items()) == 1)
    message_id = bot["fake"].message_ids[update_id]
    text = "see the new notes"
    bot["fake"].edit(OWNER, message_id, text, entities=[_link(text, "new notes", "https://example.com/n2")])
    assert _until(lambda: _items()[0]["text"] == "see the new notes https://example.com/n2"), _items()
