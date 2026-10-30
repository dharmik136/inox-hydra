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
    for key in ("paired", "collected", "draft", "short"):
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


def test_the_buttons_it_promises_are_the_ones_the_bot_shows():
    """Phase 2: Undo in step 3, and the due post's two buttons in the later, optional check."""
    article = _article()
    for label in telegram_bot.BUTTON_LABELS.values():
        assert f"**{label}**" in article, label
    for key in ("undone_item", "due_one", "remind_set", "due_again_one", "done"):
        assert telegram_bot.SENTENCES[key] in article, key


def test_the_quiet_hours_it_names_are_the_panels():
    """Phase 2: the optional check of quiet hours names the panel's own words."""
    panel = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "TelegramIngressPanel.tsx"),
                 encoding="utf-8").read()
    for words in ("Hold notifications during quiet hours", "QUIET NOW"):
        assert words in _article() and words in panel, words


def test_the_weekly_summary_it_names_is_the_panels_and_the_bots():
    """Phase 2: the optional check of the weekly summary quotes the panel and the bot."""
    panel = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "TelegramIngressPanel.tsx"),
                 encoding="utf-8").read()
    for words in ("Send me a weekly summary", "NEXT SUMMARY:"):
        assert words in _article() and words in panel, words
    bot = open(os.path.join(REPO_ROOT, "studio", "backend", "telegram_bot.py"), encoding="utf-8").read()
    assert "Your week, the seven days to" in _article() and "Your week, the seven days to" in bot


def test_the_drafts_answer_it_quotes_is_the_bots():
    """Phase 2: /drafts, in the later, optional check."""
    assert telegram_bot.SENTENCES["drafts"].format(count=2) in _article()


def test_the_memory_steps_quote_the_bot_and_the_studio():
    """Phase 3, item 3: /remember, /forget and /recall, and the words of Brand's list and the Composer."""
    article = _article()
    assert telegram_bot.SENTENCES["remembered"].split(" Your studio")[0] in article
    assert telegram_bot.SENTENCES["forgot"] in article
    ui = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")
    remember = open(os.path.join(ui, "ThingsToRemember.tsx"), encoding="utf-8").read()
    composer = open(os.path.join(ui, "ComposerCollection.tsx"), encoding="utf-8").read()
    assert "Things to remember" in article and "Things to remember" in remember
    for words in ("What this draft was written from", "From your collection", "Add to the draft"):
        assert words in article and words in composer, words


def _panel():
    return open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "TelegramIngressPanel.tsx"),
                encoding="utf-8").read()


def test_phase_4_seen_working_and_a_day_not_checked_quote_the_bot_and_the_panel():
    """Phase 4, items 1 and 2: the orange sentence, the last check, the notice of a day not checked."""
    import ingress
    article = _article()
    assert ingress.NOT_YET_TESTED.split(":")[0] in article
    assert telegram_bot.GAP_NOTICE.split(" from {start}")[0] in article
    for words in ("Last checked Telegram", "A DAY THE STUDIO DID NOT CHECK TELEGRAM", "Got it"):
        assert words in article and words in _panel(), words


def test_phase_4_the_menu_step_names_the_panels_row():
    """Phase 4, item 3: the / menu, and the panel's row that says Telegram took it."""
    article = _article()
    assert "The / menu in your chat" in article and "The / menu in your chat" in _panel()


def test_phase_4_the_whole_post_and_the_rewrite_quote_the_bot_and_the_studio():
    """Phase 4, items 4 and 5: the whole post's answer, a rewrite's answers, and the Composer's Put it back."""
    article = _article()
    for key in ("whole_sent", "rewriting"):
        assert telegram_bot.SENTENCES[key] in article, key
    assert telegram_bot.REWRITTEN_WORDS.format(label="Shorter") in article
    composer = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "ComposerCollection.tsx"),
                    encoding="utf-8").read()
    for words in ("Rewritten from your phone", "Put it back in the editor"):
        assert words in article and words in composer, words
    writing_view = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "WritingPreferences.tsx"),
                        encoding="utf-8").read()
    assert "Rewrite buttons on your bot" in article and "Rewrite buttons on your bot" in writing_view


def test_phase_4_building_an_idea_up_quotes_the_bot_and_the_panel():
    """Phase 4, item 6: a reply's answer, the box's line, and the panel's switch."""
    article = _article()
    assert telegram_bot.SENTENCES["added"] in article
    assert "A reply adds to what it replies to" in article and "A reply adds to what it replies to" in _panel()
    box = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "CollectionPanel.tsx"),
               encoding="utf-8").read()
    assert "of your messages" in article and "of your messages" in box


def test_phase_4_edits_quote_the_bot_and_the_box():
    """Phase 4, item 7: an edit's answers, and the box's mark."""
    article = _article()
    for key in ("edited", "edited_draft"):
        assert telegram_bot.SENTENCES[key] in article, key
    box = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "CollectionPanel.tsx"),
               encoding="utf-8").read()
    assert "edited on your phone" in article and "edited on your phone" in box


def test_phase_4_write_quotes_the_bot_and_the_writing_view():
    """Phase 4, item 9: /write's answer, and the preference it reads."""
    article = _article()
    assert telegram_bot.SENTENCES["write_from"].format(count=2) in article
    writing_view = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "WritingPreferences.tsx"),
                        encoding="utf-8").read()
    assert "Most items in one draft" in article and "Most items in one draft" in writing_view
