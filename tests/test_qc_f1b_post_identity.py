"""
Post identity for every script, and for every way a post leaves the studio.
==========================================================================

WRITE-10 / BRIDGE-07: the fingerprint kept only [0-9a-z], so a post written in
Devanagari, Gujarati, Chinese, Arabic or Cyrillic reduced to nothing and was
refused as "too short". Nothing such a creator wrote could ever be bound to its
LinkedIn post, and no engager was ever attributed to it.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import post_identity  # noqa: E402

SAMPLES = {
    "hindi": "मैंने पाँच साल में जो सीखा, वह आज आपके साथ साझा कर रहा हूँ। पहली बात: धैर्य रखिए।",
    "gujarati": "મેં પાંચ વર્ષમાં જે શીખ્યું તે આજે તમારી સાથે શેર કરું છું. પહેલી વાત: ધીરજ રાખો.",
    "chinese": "我在五年里学到的东西，今天和大家分享。第一点是耐心，第二点是坚持，第三点是复盘。",
    "arabic": "ما تعلمته في خمس سنوات أشاركه معكم اليوم. الدرس الأول: الصبر، والثاني: الاستمرار.",
    "russian": "За пять лет я научился одному: терпению. Сегодня делюсь этим уроком со всеми вами.",
    "french": "Ce que j'ai appris en cinq ans, je le partage aujourd'hui. Première leçon : la patience.",
}


@pytest.mark.parametrize("script", sorted(SAMPLES))
def test_a_post_in_any_script_has_a_fingerprint(script):
    assert post_identity.content_fingerprint(SAMPLES[script]) is not None


@pytest.mark.parametrize("script", sorted(SAMPLES))
def test_the_fingerprint_survives_linkedins_rewriting(script):
    text = SAMPLES[script]
    fingerprint = post_identity.content_fingerprint(text)
    # What the permalink shows: whitespace reflowed, a hashtag appended.
    rendered = "  " + text.replace(" ", "\n ", 3) + "\n\n#leadership"
    assert post_identity.fingerprint_matches(rendered, fingerprint)


def test_two_different_posts_in_one_script_do_not_match():
    first = post_identity.content_fingerprint(SAMPLES["hindi"])
    other = "आज मैं आपको बताना चाहता हूँ कि मैंने अपनी पहली नौकरी कैसे छोड़ी और क्या सीखा।"
    assert not post_identity.fingerprint_matches(other, first)


def test_the_studios_bold_letters_still_match_plain_text():
    bold = "".join(chr(0x1D5D4 + ord(c) - 65) if "A" <= c <= "Z" else c for c in "HIRING JUNIORS")
    text = bold + " is the best decision we made in five years, and here is why it worked."
    plain = "Hiring juniors is the best decision we made in five years, and here is why it worked."
    assert post_identity.fingerprint_matches(plain, post_identity.content_fingerprint(text))


def test_ascii_fingerprints_stored_before_this_change_still_match():
    """An English post fingerprinted by the old normaliser must still bind."""
    import hashlib
    import re

    text = "Hiring juniors is the best decision we made in five years, and here is why."
    old_spine = re.sub(r"[^0-9a-z]+", "", text.casefold())[:140]
    old = f"{len(old_spine)}:{hashlib.sha256(old_spine.encode()).hexdigest()[:32]}"
    assert post_identity.fingerprint_matches(text, old)


def test_a_short_post_is_still_refused():
    assert post_identity.content_fingerprint("धैर्य रखिए") is None


# ---------------------------------------------------------------------------
# The routes that depend on it
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
from database import get_db  # noqa: E402

client = TestClient(app_module.app)


def _delete_posts(text):
    conn = get_db()
    try:
        conn.execute("DELETE FROM posts WHERE content = ?", (text,))
        conn.commit()
    finally:
        conn.close()


@pytest.mark.parametrize("script", ["hindi", "chinese", "russian"])
def test_a_non_latin_insert_is_recorded_and_binds(script):
    text = SAMPLES[script] + " (" + script + " binding probe)"
    try:
        injected = client.post("/api/v1/posts/injected", json={"content": text}).json()
        assert injected["status"] == "recorded", injected
        urn = "urn:li:activity:73900000000" + str(10000 + len(script))
        bound = client.post("/api/v1/posts/bind-urn", json={"activity_urn": urn, "post_text": text}).json()
        assert bound["status"] == "bound", bound
        assert bound["post_id"] == injected["post_id"]
    finally:
        _delete_posts(text)
