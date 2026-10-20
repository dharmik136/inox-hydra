"""
Text is cut on whole characters, in the extension and in the studio. [BE-01]

The extension cut comments to 140 and excerpts to 300 with String.slice, which
counts UTF-16 units, so an emoji across the cut left half a surrogate pair:
the studio could not store it, the commenter never became a lead, and the
extension resent every 30 s. The studio's own cuts count code points, which
never splits a pair but can still split what a reader sees as one character:
a flag, a skin-toned or joined emoji, a Devanagari letter and its vowel sign.
"""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
EXTENSION = os.path.join(REPO_ROOT, "studio", "extension")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from text_cut import clip  # noqa: E402

ROCKET = "\U0001F680"
INDIA = "\U0001F1EE\U0001F1F3"
THUMBS_MEDIUM = "\U0001F44D\U0001F3FD"
FAMILY = "\U0001F468‍\U0001F469‍\U0001F467"
HINDI_KI = "कि"  # ka + vowel sign i
CONJUNCT = "क्ष"  # ka + virama + ssa


# The four cuts, as they stand in the extension.
CUT_LINES = [
    ("content.js", "Array.from(bodyEl.innerText.trim()).slice(0, 140).join(\"\")"),
    ("content.js", "Array.from(c.commentText).slice(0, 140).join(\"\")"),
    ("own_pages.js", "Array.from(cardText(card) || \"\").slice(0, 300).join(\"\")"),
]


@pytest.mark.parametrize("name, expression", CUT_LINES)
def test_the_extension_cuts_by_code_point(name, expression):
    with open(os.path.join(EXTENSION, name), encoding="utf-8") as handle:
        source = handle.read()
    assert expression in source


def test_no_extension_cut_counts_utf16_units():
    for name in ("content.js", "own_pages.js"):
        with open(os.path.join(EXTENSION, name), encoding="utf-8") as handle:
            source = handle.read()
        by_code_point = re.sub(r"Array\.from\([^;]*?\)\.slice\(0, (140|300)\)", "", source)
        assert not re.search(r"\.slice\(0, (140|300)\)", by_code_point), name


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_a_code_point_cut_never_leaves_half_an_emoji():
    """The same expression, run by node on a comment with an emoji across the cut."""
    script = r"""
      const text = "x".repeat(139) + "\u{1F680} and more";
      const old = text.slice(0, 140);
      const now = Array.from(text).slice(0, 140).join("");
      process.stdout.write(JSON.stringify({old: JSON.stringify(old), now: JSON.stringify(now)}));
    """
    # encoding: node writes UTF-8, and text=True alone decodes it with the
    # console code page. On Windows that is cp1252, which turned the rocket
    # into the four letters of its UTF-8 bytes and failed the last assertion.
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True,
                                    encoding="utf-8", check=True).stdout)
    assert "\\ud83d" in out["old"]  # the defect, as it was
    assert "\\ud83d" not in out["now"]
    assert json.loads(out["now"]).endswith("\U0001F680")


@pytest.mark.parametrize("whole", [ROCKET, INDIA, THUMBS_MEDIUM, FAMILY, HINDI_KI, CONJUNCT, "é"])
def test_clip_never_splits_a_character(whole):
    text = "abc " + whole + " tail"
    for limit in range(1, len(text) + 1):
        cut = clip(text, limit)
        assert len(cut) <= limit
        assert text.startswith(cut)
        start = text.index(whole)
        # Either the whole character is in the cut or none of it is.
        inside = cut[start:start + len(whole)]
        assert inside in ("", whole), (limit, cut)


def test_clip_keeps_short_text_and_handles_none():
    assert clip("short", 140) == "short"
    assert clip(None, 10) is None
    assert clip("abc", 0) == ""
    assert clip("abcdef", 3) == "abc"


def test_two_flags_are_cut_between_them():
    text = INDIA + INDIA
    assert clip(text, 3) == INDIA


def test_a_stored_comment_ends_on_a_whole_character(confirmed_creator):
    """The studio's own cut of a long comment, with a flag across it."""
    from crm import MAX_CRM_COMMENT_LENGTH
    from fastapi.testclient import TestClient
    from app import app

    comment = "y" * (MAX_CRM_COMMENT_LENGTH - 1) + INDIA + " the rest"
    res = TestClient(app).post("/api/v1/crm/interactions/ingest", json={
        "full_name": "Priya Shah",
        "linkedin_urn": "https://www.linkedin.com/in/priya-shah-qc2-cut",
        "headline": "Founder",
        "interaction_type": "COMMENTED",
        "comment_text": comment,
        "post_urn": "urn:li:activity:7300000000000000002",
        "post_author": confirmed_creator,
    })
    assert res.status_code == 200, res.text

    from database import get_db

    conn = get_db()
    try:
        stored = conn.execute(
            "SELECT comment_text FROM lead_interactions WHERE comment_text LIKE 'yyyy%' ORDER BY rowid DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        conn.close()
    assert stored == "y" * (MAX_CRM_COMMENT_LENGTH - 1)
