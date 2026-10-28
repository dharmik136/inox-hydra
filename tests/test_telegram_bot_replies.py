"""
The bot answers: a short fixed sentence for every message.
==========================================================

The owner's first real test (2026-10-28) showed the path works and feels
dead: the bot never replied, so nothing said whether a message arrived. Now
every message gets one short fixed sentence back, carrying none of the
creator's data: saved as a draft; Today will ask you to open this post (or
this link); that is not one of your posts; paired; not paired yet, with how
to pair; and, from another chat once one is paired, that the bot takes
messages only from its owner's chat. On by default, since it sends only those
sentences to the Telegram service the bot already polls; one switch turns
the confirmations off.

Driven end to end against the fake Bot API (tests/telegram_fake.py).

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
from test_telegram_bot_e2e import OWNER, STRANGER, TOKEN, _drafts, _save, _until, bot  # noqa: E402,F401

SAID = telegram_bot.SENTENCES
ME = "replies-creator"


def _texts(bot, chat=OWNER):
    """What the bot sent a chat, after the Paired. that saving a chat id sends it."""
    return [m["text"] for m in bot["fake"].sent if m["chat_id"] == chat and m["text"] != SAID["paired"]]


def _saved(bot):
    """The bot saved with its chat, and the chat told it is paired, before anything else is planned."""
    _save(bot)
    assert _until(lambda: [m["text"] for m in bot["fake"].sent] == [SAID["paired"]]), bot["fake"].sent


def _own_post(bot, days=1, salt=1):
    """One of the creator's recorded posts, as the posts import would hold it."""
    client = bot["client"]
    client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                                  "display_name": "Replies Probe"})
    client.post("/api/v1/identity/confirm", json={"vanity": ME})
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    urn = "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": urn, "actor": ME, "text": "A post of mine"}]})
    return urn


def test_a_saved_draft_is_confirmed_without_its_text(bot):
    _saved(bot)
    bot["fake"].push(OWNER, "Idea: pricing for a two person studio")
    assert _until(lambda: _texts(bot) == [SAID["draft"]]), _texts(bot)
    assert "pricing" not in " ".join(m["text"] for m in bot["fake"].sent), "the creator's words went back out"


def test_a_post_link_a_strangers_post_and_a_short_link_each_get_their_sentence(bot):
    _saved(bot)
    mine = _own_post(bot)
    stranger_post = "urn:li:activity:7390000000000000777"
    bot["fake"].push(OWNER, f"https://www.linkedin.com/feed/update/{mine}/")
    bot["fake"].push(OWNER, f"https://www.linkedin.com/feed/update/{stranger_post}/")
    bot["fake"].push(OWNER, "https://lnkd.in/p/dXyZ4bQ7")
    assert _until(lambda: len(_texts(bot)) == 3), _texts(bot)
    assert _texts(bot) == [SAID["post"], SAID["not_yours"], SAID["short"]]


def test_text_with_a_post_link_says_both(bot):
    _saved(bot)
    mine = _own_post(bot)
    bot["fake"].push(OWNER, f"Draft: this did well https://www.linkedin.com/feed/update/{mine}/")
    assert _until(lambda: len(_texts(bot)) == 1)
    assert _texts(bot) == [f"{SAID['draft']} {SAID['post']}"]


def test_not_paired_yet_says_how_to_pair_and_paired_says_so(bot):
    res = bot["client"].post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": ""})
    assert res.status_code == 200 and bot["daemon"].is_running
    bot["fake"].push(OWNER, "hello")
    assert _until(lambda: len(_texts(bot)) == 1)
    assert _texts(bot) == [SAID["not_paired"].format(chat_id=OWNER)]
    assert "This is me" in _texts(bot)[0] and OWNER in _texts(bot)[0]
    # A second message soon after is refused as well, and not answered again.
    bot["fake"].push(OWNER, "hello again")
    assert _until(lambda: bot["fake"].waiting() == [])
    assert len(_texts(bot)) == 1, "the pairing sentence was sent for every refused message"
    # This is me: the chat is told it is paired.
    bot["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": OWNER})
    everything = lambda: [m["text"] for m in bot["fake"].sent if m["chat_id"] == OWNER]  # noqa: E731
    assert _until(lambda: len(everything()) == 2)
    assert everything()[1] == SAID["paired"]


def test_another_chat_is_told_the_bot_is_its_owners_once(bot):
    _saved(bot)
    bot["fake"].push(STRANGER, "let me in")
    bot["fake"].push(STRANGER, "please")
    assert _until(lambda: bot["fake"].waiting() == [])
    assert _until(lambda: len(_texts(bot, STRANGER)) == 1)
    assert _texts(bot, STRANGER) == [SAID["other_chat"]]
    assert _drafts() == []


def test_a_message_with_no_text_says_nothing_was_saved(bot):
    _saved(bot)
    bot["fake"].push(OWNER, None, photo=[{"file_id": "x"}])
    assert _until(lambda: _texts(bot) == [SAID["no_text"]]), _texts(bot)


def test_the_confirmations_can_be_turned_off_and_the_message_is_still_saved(bot):
    _saved(bot)
    res = bot["client"].post("/api/v1/ingress/options", json={"replies": False})
    assert res.status_code == 200 and res.json()["options"]["replies"] is False
    bot["fake"].push(OWNER, "Idea: quietly")
    assert _until(lambda: _drafts() == ["quietly"])
    assert _until(lambda: bot["fake"].waiting() == [])
    assert _texts(bot) == []


def test_the_confirmations_are_on_by_default(bot):
    _save(bot)
    assert bot["client"].get("/api/v1/ingress/settings").json()["options"]["replies"] is True


def test_every_sentence_is_fixed_and_short():
    for key, sentence in SAID.items():
        assert len(sentence) <= 200, key
        assert "{" not in sentence.replace("{chat_id}", ""), f"{key} carries a value other than the chat's own id"


def test_a_reply_telegram_rate_limits_is_sent_after_the_wait(bot):
    _saved(bot)
    bot["fake"].plan("sendMessage", ("429", 1))
    bot["fake"].push(OWNER, "Idea: patience")
    assert _until(lambda: len(_texts(bot)) == 1, timeout=8.0), "the reply was dropped after a 429"
    sends = bot["fake"].calls_of("sendMessage")[1:]
    assert sends[1]["at"] - sends[0]["at"] >= 0.9, "the reply was sent again before Telegram's retry_after"


def test_a_reply_lost_to_the_network_is_tried_again(bot):
    _saved(bot)
    bot["fake"].plan("sendMessage", ("drop",))
    bot["fake"].push(OWNER, "Idea: twice")
    assert _until(lambda: len(_texts(bot)) == 1, timeout=8.0), "the reply was dropped after a network fault"
    assert _drafts() == ["twice"], "the message was saved twice when its reply had to be sent again"


def test_a_chat_that_blocked_the_bot_is_said_in_plain_words(bot):
    _saved(bot)
    bot["fake"].blocked_chats.add(OWNER)
    bot["fake"].push(OWNER, "Idea: unheard")
    assert _until(lambda: _drafts() == ["unheard"])
    assert _until(lambda: bool(bot["client"].get("/api/v1/ingress/settings").json().get("last_send_error")))
    said = bot["client"].get("/api/v1/ingress/settings").json()["last_send_error"]
    assert "blocked" in said and TOKEN not in said
    assert len(bot["fake"].calls_of("sendMessage")) == 2, "a refusal that will not change was tried again"
