"""
The owner's five-minute check of the bot, on the real service.
==============================================================

docs/help/test-your-telegram-bot.md is the checklist the owner runs on their
real bot and phone. Every sentence it says the bot or the panel will show is
quoted from the code that says it, so the checklist cannot drift from the
bot: this test reads each one from telegram_bot.py and the panel and finds it
in the article.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import telegram_bot  # noqa: E402

ARTICLE = os.path.join(REPO_ROOT, "docs", "help", "test-your-telegram-bot.md")


def _article():
    return " ".join(open(ARTICLE, encoding="utf-8").read().split())


def test_the_checklist_is_filed_with_the_telegram_help():
    import docs_engine
    paths = [p for section in docs_engine.SECTIONS for p in section["paths"]] if hasattr(docs_engine, "SECTIONS") \
        else open(os.path.join(REPO_ROOT, "studio", "backend", "docs_engine.py"), encoding="utf-8").read()
    assert "help/test-your-telegram-bot.md" in paths
    guide = open(os.path.join(REPO_ROOT, "docs", "help", "send-a-post-idea-from-telegram.md"), encoding="utf-8").read()
    assert "(test-your-telegram-bot.md)" in guide


def test_every_sentence_it_promises_is_the_one_the_bot_says():
    article = _article()
    for key in ("paired", "draft", "short"):
        assert telegram_bot.SENTENCES[key] in article, key
    assert telegram_bot.SENTENCES["not_paired"].split(" beside chat")[0] in article
    assert telegram_bot.SENTENCES["test"].split(" If you can")[0] in article
    assert "Your studio is running." in article and telegram_bot.status_sentence().startswith("Your studio is running.")


def test_every_panel_word_it_names_is_on_the_panel():
    panel = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "TelegramIngressPanel.tsx"),
                 encoding="utf-8").read()
    for words in ("Save and start", "This is me", "Send a test message", "The bot may answer with your figures",
                  "CHATS THE BOT REFUSED", "NOT SET YET, PAIR BELOW", "Last message the bot could not send",
                  "Last problem reaching Telegram", "Sent: Telegram took it for your chat. Check your phone."):
        assert words in _article(), words
        assert words in panel or words in open(os.path.join(REPO_ROOT, "studio", "backend", "ingress.py"),
                                               encoding="utf-8").read(), words


def test_it_takes_about_five_minutes():
    """Five numbered steps, whose stated times add up to five minutes."""
    import re
    steps = [line for line in open(ARTICLE, encoding="utf-8") if re.match(r"^## \d\. ", line)]
    assert len(steps) == 5
    worth = {"one minute": 1.0, "two minutes": 2.0, "thirty seconds": 0.5}
    total = sum(next(v for k, v in worth.items() if k in step) for step in steps)
    assert total == 5.0, total
