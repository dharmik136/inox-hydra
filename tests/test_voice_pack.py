"""
The creator's own profile and posts reach the writing prompt.
=============================================================

The bridge reads a creator's headline, about, roles and skills, and every post
they publish, and until the voice pack nothing that writes read any of it. A
hook was written for a generic practitioner whoever asked.

These hold the pack to its rules: each part appears only when there is real
data for it, habits are measured rather than described, an unconfirmed profile
is not treated as the creator's, and the copilot carries the pack into its
brief and says so in its provenance.
"""

import os
import shutil
import sqlite3
import sys
import tempfile

import pytest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
sys.path.insert(0, BACKEND)

import paths  # noqa: E402
from agno_agentos.agents import content_copilot_agent as copilot_module  # noqa: E402
from agno_agentos.agents.content_copilot_agent import LinkedInContentCopilotAgent  # noqa: E402
from agno_agentos.model_gateway import AIProviderConfig  # noqa: E402
from voice_pack import get_voice_pack  # noqa: E402

NOW = "2026-10-01T10:00:00+00:00"


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_voice_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _db():
    return sqlite3.connect(paths.get_db_path())


def _confirm_creator(confirmed=True):
    conn = _db()
    conn.execute(
        "INSERT OR REPLACE INTO creator_identity (id, vanity, headline, about, confirmed_at) "
        "VALUES (1, 'ada', 'I build engines that think', 'Twenty years of turning maths into machinery.', ?)",
        (NOW if confirmed else None,),
    )
    conn.execute(
        "INSERT INTO creator_positions (ordinal, title, company, observed_at) VALUES (0, 'Analyst', 'Engines Ltd', ?)", (NOW,)
    )
    conn.execute(
        "INSERT INTO creator_positions (ordinal, title, company, observed_at) VALUES (1, 'Tutor', 'Private', ?)", (NOW,)
    )
    conn.execute("INSERT INTO creator_skills (skill, observed_at) VALUES ('Mathematics', ?)", (NOW,))
    conn.commit()
    conn.close()


def _post(n, text, reactions, published_at=NOW):
    """One of the creator's posts. Published at NOW it is settled: older than a week."""
    conn = _db()
    conn.execute(
        "INSERT INTO own_posts (activity_urn, text, reactions, published_at, first_seen_at, last_seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"urn:li:activity:73800000000000000{n:02d}", text, reactions, published_at, NOW, NOW),
    )
    conn.commit()
    conn.close()


def test_nothing_known_means_no_pack(home):
    assert get_voice_pack() == {"has_voice": False, "brief_section": None, "parts": []}


def test_an_unconfirmed_profile_is_not_the_creators(home):
    _confirm_creator(confirmed=False)
    assert "who" not in get_voice_pack()["parts"]


def test_who_they_are(home):
    _confirm_creator()
    pack = get_voice_pack()
    assert pack["parts"] == ["who"]
    text = pack["brief_section"]
    assert "Headline: I build engines that think" in text
    assert "Current role: Analyst, Engines Ltd" in text
    assert "Before that: Tutor, Private" in text
    assert "Mathematics" in text
    assert "maths into machinery" in text


def test_habits_are_measured_and_need_enough_posts(home):
    _post(1, "Why do engines fail?\n\nBecause nobody reads the logs.", 10)
    _post(2, "Three lessons from the mill.\n\nOne.\n\nTwo.", 30)
    assert "habits" not in get_voice_pack()["parts"], "two posts were treated as a habit"

    _post(3, "What would you automate first?\n\nTell me. #automation", 20)
    pack = get_voice_pack()
    assert "habits" in pack["parts"]
    text = pack["brief_section"]
    assert "Measured across 3 of their posts" in text
    assert "opens with a question in 2 of 3" in text
    assert "hashtags in 1 of 3" in text


def test_openers_are_their_best_first_lines(home):
    _post(1, "A quiet post.\n\nBody.", 2)
    _post(2, "The loud one.\n\nBody.", 90)
    _post(3, "The middle one.\n\nBody.", 40)
    text = get_voice_pack(max_openers=2)["brief_section"]
    openers = text.split("drew the most reactions:\n")[1].splitlines()
    assert openers == ['- "The loud one."', '- "The middle one."']


def test_openers_come_from_the_one_ranking_so_a_young_post_is_not_an_exemplar(home):
    """
    The openers ranked raw own_posts.reactions with no settled rule, so a post
    three hours old with a burst of reactions could be the creator's best
    opener while every other screen left it out of the ranking (cycle 4,
    track 3: results.ranking is the one ranking, over settled posts, against
    the creator's own median).
    """
    import datetime as dt
    from results import ranking
    from database import get_db
    _post(1, "A quiet post.\n\nBody.", 2)
    _post(2, "The loud one.\n\nBody.", 90)
    _post(3, "The middle one.\n\nBody.", 40)
    this_morning = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).isoformat()
    _post(4, "Too young to judge.\n\nBody.", 900, published_at=this_morning)
    text = get_voice_pack(max_openers=3)["brief_section"]
    openers = text.split("drew the most reactions:\n")[1].splitlines()
    assert openers == ['- "The loud one."', '- "The middle one."', '- "A quiet post."'], openers
    conn = get_db()
    try:
        order = ranking(conn)["order"]
    finally:
        conn.close()
    assert "urn:li:activity:7380000000000000004" not in order, "the engine ranks the young post too"


def test_the_copilot_carries_the_pack_and_says_so(home, monkeypatch):
    _confirm_creator()
    seen = {}

    def capture(config, user_prompt, system_prompt="", **kwargs):
        seen["user"] = user_prompt
        return "\n".join(f"{n}. Hook {n} about engines that read their own logs" for n in range(1, 7))

    monkeypatch.setattr(copilot_module, "execute_llm_completion", capture)
    agent = LinkedInContentCopilotAgent(ai_config=AIProviderConfig(
        provider="local_deterministic", api_key="notarealkey", model="test-model", status="connected",
    ))
    _hooks, record = agent._generate_llm_hooks(topic="engines", content="A draft about engines and logs.")

    assert "I build engines that think" in seen["user"], "the creator's profile never reached the prompt"
    assert record["voice_pack"] == ["who"], "the provenance does not say the voice pack was sent"
