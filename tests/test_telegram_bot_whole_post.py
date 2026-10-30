"""
Post from the phone: the whole post, to copy and paste (phase 4, item 4).
=========================================================================

While "The bot may send me what it writes from my collection" is on, "Draft
ready in your studio. It begins:" carries Send me the whole post, and so does
"A post in your queue is due now." (Send me the posts when several are due).
A press sends the post's text as the studio holds it now, as a message of its
own with nothing around it, for long-press, Copy and paste into the LinkedIn
app. Longer than Telegram takes in one message (4096 characters, counted in
UTF-16 code units as Telegram counts them), it is split on paragraph
boundaries, each part beginning "Part 1 of 2". The press keeps the message's
other buttons. With the switch off the button is not offered, and a press on
an older message says why. Nothing is posted and nothing reaches LinkedIn.

docs/quality/cycle4/bot-phase4.md, item 4. Against the fake Bot API, which
refuses a message over 4096 characters as Telegram does, and the fake
provider.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_collection_bot_writing import DRAFT, _collect, _labels, _newest, _words_on, provider  # noqa: E402,F401
from test_telegram_bot_buttons import _linkedin_counts  # noqa: E402
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_notifications import _due, _settle, notifying  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
WHOLE = "Send me the whole post"


def _units(text):
    return len(text.encode("utf-16-le")) // 2


def _content(post_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT content FROM posts WHERE id = ?", (post_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _drafted(bot):
    """Write it up with the words switch on; returns the 'Draft ready' message and the draft's id."""
    _saved(bot)
    _words_on(bot)
    _collect(bot)
    bot["fake"].press_button("Write it up", OWNER)
    assert _until(lambda: _texts(bot)[-1].startswith(SAID["draft_ready_words"])), _texts(bot)
    conn = get_db()
    post_id = conn.execute("SELECT post_id FROM collection_items WHERE post_id IS NOT NULL").fetchone()[0]
    conn.close()
    return _newest(bot), post_id


def test_draft_ready_carries_send_me_the_whole_post_and_a_press_sends_exactly_the_post(bot, provider):
    message, post_id = _drafted(bot)
    assert WHOLE in _labels(bot, message)
    before = _linkedin_counts()
    bot["fake"].press_button(WHOLE, OWNER)
    assert _until(lambda: _texts(bot)[-1] == DRAFT), _texts(bot)
    assert _content(post_id) == DRAFT
    answered = [a["text"] for a in bot["fake"].answered]
    assert answered[-1] == SAID["whole_sent"]
    assert WHOLE not in _labels(bot, message), "the button stayed after it was used"
    assert _linkedin_counts() == before, "the whole post reached for LinkedIn"


def test_the_post_sent_is_the_one_in_the_studio_now(bot, provider):
    message, post_id = _drafted(bot)
    conn = get_db()
    with conn:
        conn.execute("UPDATE posts SET content = ? WHERE id = ?", ("Edited at the desk.\n\nThen kept.", post_id))
    conn.close()
    bot["fake"].press_button(WHOLE, OWNER)
    assert _until(lambda: _texts(bot)[-1] == "Edited at the desk.\n\nThen kept."), _texts(bot)


def test_with_the_switch_off_no_button_is_offered(bot, provider):
    _saved(bot)
    _collect(bot)
    bot["fake"].press_button("Write it up", OWNER)
    assert _until(lambda: _texts(bot)[-1] == SAID["draft_ready"])
    assert WHOLE not in _labels(bot)


def test_a_press_on_an_older_message_after_the_switch_went_off_says_why(bot, provider):
    message, _post_id = _drafted(bot)
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": False})
    sent_before = len(bot["fake"].sent)
    bot["fake"].press_button(WHOLE, OWNER)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered][-1:] == [SAID["whole_off"]])
    _settle(bot)
    assert len(bot["fake"].sent) == sent_before, "the post went with the switch off"


def test_a_due_post_carries_it_and_keeps_remind_and_done(notifying):
    bot = notifying
    _saved(bot)
    _words_on(bot)
    _due("due-1")
    bot["client"].post("/api/v1/ingress/options", json={"notify_due": True})
    assert _until(lambda: SAID["due_one"] in _texts(bot)), _texts(bot)
    message = [m for m in bot["fake"].sent if m["text"] == SAID["due_one"]][-1]
    assert _labels(bot, message) == [WHOLE, "Remind me in an hour", "Done"]
    bot["fake"].press_button(WHOLE, OWNER)
    assert _until(lambda: _texts(bot)[-1] == "My queued words"), _texts(bot)
    assert _labels(bot, message) == ["Remind me in an hour", "Done"], "the other buttons went with it"
    bot["fake"].press_button("Done", OWNER)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered][-1] == SAID["done"])


def test_several_due_posts_are_each_sent(notifying):
    bot = notifying
    _saved(bot)
    _words_on(bot)
    _due("due-1")
    _due("due-2", minutes_ago=3)
    conn = get_db()
    with conn:
        conn.execute("UPDATE posts SET content = 'The second queued post' WHERE id = 'due-2'")
    conn.close()
    bot["client"].post("/api/v1/ingress/options", json={"notify_due": True})
    many = SAID["due_many"].format(count=2)
    assert _until(lambda: many in _texts(bot)), _texts(bot)
    assert "Send me the posts" in _labels(bot, [m for m in bot["fake"].sent if m["text"] == many][-1])
    bot["fake"].press_button("Send me the posts", OWNER)
    assert _until(lambda: _texts(bot)[-2:] == ["My queued words", "The second queued post"]), _texts(bot)


def test_with_the_switch_off_a_due_post_has_only_remind_and_done(notifying):
    bot = notifying
    _saved(bot)
    _due("due-1")
    bot["client"].post("/api/v1/ingress/options", json={"notify_due": True})
    assert _until(lambda: SAID["due_one"] in _texts(bot))
    message = [m for m in bot["fake"].sent if m["text"] == SAID["due_one"]][-1]
    assert _labels(bot, message) == ["Remind me in an hour", "Done"]


def test_a_post_longer_than_one_message_comes_in_parts_split_on_paragraphs():
    paragraph = "A line about pricing that a reader might keep. " * 20
    post = "\n\n".join(f"{n}. {paragraph.strip()}" for n in range(1, 9))
    assert _units(post) > 4096
    parts = telegram_bot.whole_post_messages(post)
    assert len(parts) >= 2
    for index, part in enumerate(parts, 1):
        assert part.startswith(f"Part {index} of {len(parts)}\n\n"), part[:30]
        assert _units(part) <= 4096
    bodies = [part.split("\n\n", 1)[1] for part in parts]
    assert "\n\n".join(bodies) == post, "the parts do not add up to the post"
    for body in bodies:
        assert body.split("\n\n")[0][:2] in {f"{n}." for n in range(1, 9)}, "a part began inside a paragraph"


def test_it_counts_as_telegram_counts_an_emoji_as_two():
    post = ("\U0001F600" * 2000) + "\n\n" + ("\U0001F680" * 100)
    assert len(post) < 4096 < _units(post)
    parts = telegram_bot.whole_post_messages(post)
    assert len(parts) == 2 and all(_units(part) <= 4096 for part in parts)


def test_a_post_that_fits_is_sent_alone_and_unlabelled():
    assert telegram_bot.whole_post_messages(DRAFT) == [DRAFT]


def test_one_paragraph_longer_than_a_message_is_split_on_lines_then_words():
    post = " ".join(["word"] * 3000)
    parts = telegram_bot.whole_post_messages(post)
    assert len(parts) >= 2 and all(_units(p) <= 4096 for p in parts)
    assert " ".join(p.split("\n\n", 1)[1] for p in parts) == post
