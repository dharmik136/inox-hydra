"""
Voice Pack: Who the Creator Is, and How They Write, for Every Writing Prompt.
=============================================================================
The bridge reads the creator's headline, about, roles and skills, and every
post they have published. Until this module, no prompt read any of it, so a
hook was written for a generic "practitioner" no matter whose studio asked.

The pack has three parts, each only when there is something real to put in it:

  who         headline, current role and the two before it, top skills, the
              first lines of the about section; only once the creator has
              confirmed which profile is theirs
  habits      measured from their own posts: typical length, how many
              paragraphs, how often they open with a question, emoji and
              hashtag use; only with at least MIN_POSTS_FOR_HABITS posts
  openers     the first lines of their posts that drew the most reactions,
              as examples of their voice rather than templates to copy

It is the creator's own public profile and their own published posts. It goes
to a hosted model only when one is configured, on the same path and under the
same provenance as the rest of the brief.

Strict Invariants:
- Zero em-dashes in any code, docstring or comment.
- Pure local processing: reads the database, calls nothing.
- Nothing invented: a part with no data is omitted, never filled.
"""

import json
import re
import statistics
from typing import Any, Dict, List

try:
    from . import results
    from .database import get_db
except ImportError:
    import results
    from database import get_db

MIN_POSTS_FOR_HABITS = 3
ABOUT_CHARS = 400
OPENER_CHARS = 140

# Pictographs and the common symbol blocks. A rough reading is enough here: it
# only decides whether "uses emoji" is worth telling the model.
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
_HASHTAG = re.compile(r"(?:^|\s)#\w+")


def _first_line(text: str) -> str:
    return next((line.strip() for line in (text or "").splitlines() if line.strip()), "")


def _paragraphs(text: str) -> int:
    return len([block for block in re.split(r"\n\s*\n", text or "") if block.strip()])


def _share(count: int, total: int) -> str:
    return f"{count} of {total}"


def _who(conn) -> List[str]:
    row = conn.execute(
        "SELECT headline, about, current_company FROM creator_identity WHERE id = 1 AND confirmed_at IS NOT NULL"
    ).fetchone()
    if not row:
        return []
    lines: List[str] = []
    if row["headline"]:
        lines.append(f"Headline: {row['headline']}")
    roles = conn.execute(
        "SELECT title, company FROM creator_positions ORDER BY ordinal LIMIT 3"
    ).fetchall()
    described = [", ".join(p for p in (r["title"], r["company"]) if p) for r in roles]
    described = [d for d in described if d]
    if described:
        lines.append("Current role: " + described[0])
        if len(described) > 1:
            lines.append("Before that: " + "; ".join(described[1:]))
    elif row["current_company"]:
        lines.append(f"Works at: {row['current_company']}")
    skills = [r["skill"] for r in conn.execute("SELECT skill FROM creator_skills ORDER BY skill LIMIT 8")]
    if skills:
        lines.append("Skills they list: " + ", ".join(skills))
    about = (row["about"] or "").strip()
    if about:
        if len(about) > ABOUT_CHARS:
            about = about[:ABOUT_CHARS].rsplit(" ", 1)[0] + "..."
        lines.append("In their own words: " + " ".join(about.split()))
    return lines


def _habits(texts: List[str]) -> List[str]:
    if len(texts) < MIN_POSTS_FOR_HABITS:
        return []
    total = len(texts)
    lengths = [len(t) for t in texts]
    paragraphs = [_paragraphs(t) for t in texts]
    questions = sum(1 for t in texts if _first_line(t).endswith("?"))
    emoji = sum(1 for t in texts if _EMOJI.search(t))
    hashtags = sum(1 for t in texts if _HASHTAG.search(t))
    return [
        f"Measured across {total} of their posts:",
        f"- typical length about {int(statistics.median(lengths))} characters, "
        f"in about {int(statistics.median(paragraphs))} short paragraphs",
        f"- opens with a question in {_share(questions, total)}",
        f"- uses emoji in {_share(emoji, total)}, hashtags in {_share(hashtags, total)}",
    ]


def _openers(conn, limit: int) -> List[str]:
    """
    The first lines of the posts that did best, by the one ranking.

    This ordered raw own_posts.reactions with no settled rule, so a post
    three hours old with a burst of reactions could be the creator's best
    opener while every screen left it out of the ranking. results.ranking is
    the ranking every screen reads: settled posts only, against the creator's
    own median, from one reading of each post's figures.
    """
    ranked = results.ranking(conn)["order"]
    if not ranked:
        return []
    texts = {row["activity_urn"]: row["text"] for row in conn.execute(
        "SELECT activity_urn, text FROM own_posts WHERE activity_urn IN (SELECT value FROM json_each(?)) "
        "AND text IS NOT NULL AND TRIM(text) != ''", (json.dumps(ranked[:limit * 4]),))}
    openers = []
    for urn in ranked:
        if len(openers) >= limit:
            break
        text = texts.get(urn)
        if text is None:
            continue
        line = _first_line(text)
        if len(line) > OPENER_CHARS:
            line = line[:OPENER_CHARS].rsplit(" ", 1)[0] + "..."
        if line:
            openers.append(f'- "{line}"')
    return openers


def prompt_block() -> str:
    """
    The pack as a paragraph to append to a plain prompt, or "" when there is none.

    For the generators that build a prompt string rather than a Brief. The
    instruction travels with the material, so a model is told what it is for.
    """
    pack = get_voice_pack()
    if not pack["has_voice"]:
        return ""
    return (
        "\n\nAbout the author, measured from their own profile and posts. Match their length, "
        "rhythm and the way they open a post. Do not copy their openers, and do not mention "
        "their title or employer unless the text does.\n" + pack["brief_section"]
    )


def _read(max_openers: int):
    """(who, habits, openers, post count), each empty when there is no data."""
    conn = get_db()
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"creator_identity", "own_posts"} <= tables:
            return [], [], [], 0
        who = _who(conn)
        texts = [r["text"] for r in conn.execute(
            "SELECT text FROM own_posts WHERE text IS NOT NULL AND TRIM(text) != ''"
        )]
        return who, _habits(texts), _openers(conn, max_openers), len(texts)
    finally:
        conn.close()


# Each line _who can write, and what it is called where the creator reads it.
_WHO_SAID = (
    ("Headline: ", "your headline"),
    ("Current role: ", "your current role"),
    ("Before that: ", "your earlier roles"),
    ("Works at: ", "your employer"),
    ("Skills they list: ", "the skills on your profile"),
    ("In their own words: ", f"the first {ABOUT_CHARS} characters of your About section"),
)


def disclosure(max_openers: int = 3) -> List[str]:
    """
    What prompt_block() adds to a prompt, in the creator's own terms.

    Read by the Prompt tab and returned with each Command answer. The pack
    went with every Re-Hook and Command request while the screen said only
    "prompt text" left the machine and the help said the instruction alone
    did, so a creator deciding what to share was told less than was sent.
    Derived from the same reads as the pack, so the two cannot drift. Empty
    when nothing would be added.
    """
    who, habits, openers, post_count = _read(max_openers)
    said = [label for line in who for prefix, label in _WHO_SAID if line.startswith(prefix)]
    if habits:
        said.append(
            f"how your posts are usually shaped, measured from {post_count} of them: "
            "length, paragraphs, opening questions, emoji and hashtags"
        )
    if openers:
        said.append(f"the opening lines of your {len(openers)} most-reacted posts")
    return said


# How the openers are chosen, in the creator's terms (results.ranking).
OPENERS_RULE = ("the opening lines of your posts that did best against your own usual, among posts old enough "
                "for their figures to have settled, by the one ranking every screen reads")


def told(max_openers: int = 3) -> Dict[str, Any]:
    """
    The pack as the Composer's "What the model is told" shows it: the lines
    prompt_block() appends, part by part, from the same reads, so the panel
    shows exactly what a Re-Hook or Command request carries.
    """
    who, habits, openers, post_count = _read(max_openers)
    return {
        "sent": bool(who or habits or openers),
        "who": who,
        "habits": habits,
        "posts_measured": post_count,
        "habits_need": MIN_POSTS_FOR_HABITS,
        "openers": openers,
        "openers_rule": OPENERS_RULE,
        "sent_with": ["Re-Hook", "Command"],
    }


def get_voice_pack(max_openers: int = 3) -> Dict[str, Any]:
    """
    The voice pack as a brief section, and what went into it.

    Returns {"has_voice": bool, "brief_section": str | None, "parts": [...]},
    where parts names which of who, habits and openers had data.
    """
    who, habits, openers, _count = _read(max_openers)

    sections: List[str] = []
    parts: List[str] = []
    if who:
        sections.append("\n".join(who))
        parts.append("who")
    if habits:
        sections.append("\n".join(habits))
        parts.append("habits")
    if openers:
        sections.append("Openers of theirs that drew the most reactions:\n" + "\n".join(openers))
        parts.append("openers")

    if not sections:
        return {"has_voice": False, "brief_section": None, "parts": []}
    return {"has_voice": True, "brief_section": "\n\n".join(sections), "parts": parts}

