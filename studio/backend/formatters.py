import re
import unicodedata
import math
from typing import Any

MAX_FORMAT_TEXT_LENGTH = 50000


def _normalize_text(text: Any) -> str:
    """Safely normalizes input text to bounded string, guarding against nulls and non-string types."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return text[:MAX_FORMAT_TEXT_LENGTH]


def _measurable_text(text: Any) -> str:
    r"""
    The text as a reader perceives it, with decoration stripped.

    to_strikethrough and to_underline work by inserting a combining mark after
    every character. Those marks are separate code points that \w does not
    match, so re.findall(r"\b\w+\b", ...) counts each decorated letter as
    its own word and len() doubles.

    Measured: a 220 word post run through to_underline reported 880 words, and
    an 80 character hook run through to_strikethrough reported 160 pre-fold
    characters, which flipped mobile_safe from True to False. Both endpoints
    ship, so a creator who struck a line through then asked for an audit was
    told their fold-safe hook would truncate.

    Only the combining-mark formatters cause this. Mathematical bold maps each
    letter to a single code point, and measures correctly without help.
    """
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def to_sans_bold(text: Any) -> str:
    """Converts standard ASCII characters to Unicode Mathematical Sans-Serif Bold."""
    text = _normalize_text(text)
    if not text:
        return ""
    out = []
    for c in text:
        if 'A' <= c <= 'Z':
            out.append(chr(0x1D5D4 + ord(c) - ord('A')))
        elif 'a' <= c <= 'z':
            out.append(chr(0x1D5EE + ord(c) - ord('a')))
        elif '0' <= c <= '9':
            out.append(chr(0x1D7EC + ord(c) - ord('0')))
        else:
            out.append(c)
    return ''.join(out)


def to_sans_italic(text: Any) -> str:
    """Converts standard ASCII characters to Unicode Mathematical Sans-Serif Italic."""
    text = _normalize_text(text)
    if not text:
        return ""
    out = []
    for c in text:
        if 'A' <= c <= 'Z':
            out.append(chr(0x1D608 + ord(c) - ord('A')))
        elif 'a' <= c <= 'z':
            out.append(chr(0x1D622 + ord(c) - ord('a')))
        else:
            out.append(c)
    return ''.join(out)


def to_monospace(text: Any) -> str:
    """Converts ASCII characters to Unicode Mathematical Monospace."""
    text = _normalize_text(text)
    if not text:
        return ""
    out = []
    for c in text:
        if 'A' <= c <= 'Z':
            out.append(chr(0x1D670 + ord(c) - ord('A')))
        elif 'a' <= c <= 'z':
            out.append(chr(0x1D68A + ord(c) - ord('a')))
        elif '0' <= c <= '9':
            out.append(chr(0x1D7F6 + ord(c) - ord('0')))
        else:
            out.append(c)
    return ''.join(out)


def to_strikethrough(text: Any) -> str:
    """Adds combining long stroke overlay (strikethrough) to each character."""
    text = _normalize_text(text)
    if not text:
        return ""
    return ''.join(c + '\u0336' if c != '\n' else c for c in text)


def to_serif_bold(text: Any) -> str:
    """Converts standard ASCII characters to Unicode Mathematical Serif Bold."""
    text = _normalize_text(text)
    if not text:
        return ""
    out = []
    for c in text:
        if 'A' <= c <= 'Z':
            out.append(chr(0x1D400 + ord(c) - ord('A')))
        elif 'a' <= c <= 'z':
            out.append(chr(0x1D41A + ord(c) - ord('a')))
        elif '0' <= c <= '9':
            out.append(chr(0x1D7CE + ord(c) - ord('0')))
        else:
            out.append(c)
    return ''.join(out)


def to_serif_italic(text: Any) -> str:
    """Converts standard ASCII characters to Unicode Mathematical Serif Italic."""
    text = _normalize_text(text)
    if not text:
        return ""
    out = []
    for c in text:
        if 'A' <= c <= 'Z':
            out.append(chr(0x1D434 + ord(c) - ord('A')))
        elif c == 'h':
            # Unicode Planck constant symbol represents italic small h
            out.append('\u210E')
        elif 'a' <= c <= 'z':
            out.append(chr(0x1D44E + ord(c) - ord('a')))
        else:
            out.append(c)
    return ''.join(out)


def to_blackboard_bold(text: Any) -> str:
    """Converts standard ASCII characters to Unicode Mathematical Double-Struck (Blackboard)."""
    text = _normalize_text(text)
    if not text:
        return ""
    # Gaps in Unicode BMP for capital letters
    special_caps = {
        'C': '\u2102',
        'H': '\u210D',
        'N': '\u2115',
        'P': '\u2119',
        'Q': '\u211A',
        'R': '\u211D',
        'Z': '\u2124',
    }
    out = []
    for c in text:
        if c in special_caps:
            out.append(special_caps[c])
        elif 'A' <= c <= 'Z':
            out.append(chr(0x1D538 + ord(c) - ord('A')))
        elif 'a' <= c <= 'z':
            out.append(chr(0x1D552 + ord(c) - ord('a')))
        elif '0' <= c <= '9':
            out.append(chr(0x1D7D8 + ord(c) - ord('0')))
        else:
            out.append(c)
    return ''.join(out)


def to_underline(text: Any) -> str:
    """Adds combining low line overlay (underline) to each character."""
    text = _normalize_text(text)
    if not text:
        return ""
    return ''.join(c + '\u0332' if c != '\n' else c for c in text)


def to_circled_numbers(text: Any) -> str:
    """Converts ASCII numbers 0-9 into filled black circled numbers (❶, ❷, ...)."""
    text = _normalize_text(text)
    if not text:
        return ""
    circled_map = {
        '0': '\u24FF',  # Negative circled 0
        '1': '\u2776',  # Dingbat negative circled digit 1
        '2': '\u2777',
        '3': '\u2778',
        '4': '\u2779',
        '5': '\u277A',
        '6': '\u277B',
        '7': '\u277C',
        '8': '\u277D',
        '9': '\u277E',
    }
    return ''.join(circled_map.get(c, c) for c in text)


def calculate_dwell_metrics(text: Any) -> dict:
    """
    Calculates estimated reading velocity, dwell probability, and reading time:
    - 220 words per minute average reading velocity
    - 0.8s pause penalty per paragraph break

    Measured on the undecorated text: see _measurable_text.
    """
    text = _measurable_text(text)
    if not text.strip():
        return {
            "word_count": 0,
            "char_count": 0,
            "paragraph_count": 0,
            "estimated_reading_sec": 0.0,
            "dwell_status": "EMPTY",
            "dwell_badge": "0.0s",
            "description": "Empty canvas",
        }

    words = re.findall(r'\b\w+\b', text)
    word_count = len(words)
    char_count = len(text)
    paragraphs = [p for p in text.split('\n\n') if p.strip()]
    paragraph_count = max(1, len(paragraphs))
    paragraph_breaks = max(0, paragraph_count - 1)

    # 220 WPM = ~3.67 words per second
    reading_sec = round((word_count / 220.0) * 60.0 + (paragraph_breaks * 0.8), 1)

    if reading_sec < 8.0:
        dwell_status = "LOW_VELOCITY"
        desc = "Quick glance: high risk of rapid scroll-by"
    elif reading_sec <= 22.0:
        dwell_status = "OPTIMAL_HOOK"
        desc = "Ideal reading velocity: prompts 'see more' click"
    else:
        dwell_status = "DEEP_DWELL"
        desc = "In-depth authority: high dwell time distribution"

    return {
        "word_count": word_count,
        "char_count": char_count,
        "paragraph_count": paragraph_count,
        "estimated_reading_sec": reading_sec,
        "dwell_status": dwell_status,
        "dwell_badge": f"{reading_sec}s",
        "description": desc,
    }


def clean_text_formatting(text: Any) -> str:
    """
    Cleans em-dashes, en-dashes, irregular spaces, and restores clean natural punctuation.
    """
    text = _normalize_text(text)
    if not text:
        return ""

    em_dash = chr(0x2014)
    en_dash = chr(0x2013)
    # The em-dash always becomes a pause, which is the anti-slop rule.
    cleaned = text.replace(em_dash, ", ")

    # The en-dash depends on what it is joining, because it does two jobs.
    #
    # Between numbers it is a range, and a comma changes the meaning:
    # "Revenue grew 2021-2024" became "Revenue grew 2021, 2024" and
    # "pages 10-20" became "pages 10, 20", which say different things.
    #
    # Between words it is a pause, and a comma is right:
    # "first principles - always" reads better than a hyphen.
    #
    # Mapping every en-dash the same way is what got one of these wrong,
    # whichever way it was mapped.
    cleaned = re.sub(r"(?<=\d)\s*" + en_dash + r"\s*(?=\d)", "-", cleaned)
    cleaned = cleaned.replace(en_dash, ", ")
    # Fix double/triple hyphens used as dashes
    cleaned = re.sub(r'(?<=\w)--+(?=\w)', ', ', cleaned)
    # Clean redundant spaces
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    # Clean space before commas or periods
    cleaned = re.sub(r' +([,.:;?!])', r'\1', cleaned)
    # Clean double commas
    cleaned = re.sub(r',\s*,', ',', cleaned)
    return cleaned.strip()


def analyze_hook(text: Any) -> dict:
    """
    Deep-dive algorithmic analysis of LinkedIn post:
    - Hook strength and archetype classification
    - Truncation cutoff check for Mobile (3 lines / 210 chars) and Desktop (5 lines / 320 chars)
    - Pacing & whitespace density (penalizing walls of text)
    - Readability & punchiness score (0 - 100)

    Measured on the undecorated text: see _measurable_text.
    """
    text = _measurable_text(text)
    if not text.strip():
        return {
            "char_count": 0,
            "word_count": 0,
            "line_count": 0,
            "score": 0,
            "hook_archetype": "Empty",
            "archetype": "Empty",
            "hook_line": "",
            "mobile_safe": True,
            "is_pre_fold_safe": True,
            "has_air_gap": False,
            "pre_fold_chars": 0,
            "pre_fold_length": 0,
            "desktop_safe": True,
            "recommendations": ["Write a strong first sentence to hook your reader."]
        }

    raw_lines = text.splitlines()
    non_empty_lines = [l.strip() for l in raw_lines if l.strip()]
    first_line = non_empty_lines[0] if non_empty_lines else ""
    words = re.findall(r'\b\w+\b', text)
    word_count = len(words)
    char_count = len(text)
    
    # Check mobile fold physics (strictly 140 characters or 3 visual lines per Day 05 PRD)
    mobile_cutoff_chars = 140
    desktop_cutoff_chars = 320

    first_3_lines = raw_lines[:3] if len(raw_lines) >= 3 else raw_lines
    first_3_lines_text = "\n".join(first_3_lines)
    pre_fold_chars = len(first_3_lines_text)

    # Visual air gap: empty line directly following the first sentence
    has_air_gap = bool(len(raw_lines) >= 2 and raw_lines[1].strip() == "")

    mobile_safe = pre_fold_chars <= mobile_cutoff_chars and len(first_line) <= mobile_cutoff_chars
    desktop_safe = len("\n".join(raw_lines[:5])) <= desktop_cutoff_chars

    # Classify 5 High-Velocity Hook Archetypes (Project Prudent PRD-005)
    fl_lower = first_line.lower()
    archetype = "Direct Statement"
    recommendations = []

    if any(k in fl_lower for k in ["i spent", "i wasted", "before realizing", "biggest mistake", "hard truth", "stop doing"]):
        archetype = "The Contrarian Confession"
    elif any(k in fl_lower for k in ["90% of engineers", "how it actually works", "system design", "architecture", "under the hood", "monolith", "decoupling"]):
        archetype = "The Architectural Breakdown"
    elif any(k in fl_lower for k in ["we processed", "0 downtime", "reduced latency", "benchmarked", "10m records", "100k requests"]):
        archetype = "The Concrete Proof"
    elif any(k in fl_lower for k in ["how to build", "step-by-step", "blueprint", "teardown", "in 48 hours", "without paying"]):
        archetype = "The Step-by-Step Teardown"
    elif any(k in fl_lower for k in ["failed completely", "post-mortem", "i was wrong", "my confession", "what nobody tells you", "my biggest failure", "crashed", "outage", "broke"]):
        archetype = "The Direct Vulnerability"
    elif any(q in fl_lower for q in ["?", "why", "how do you", "have you ever", "what if"]):
        archetype = "Question / Curiosity Gap"
    elif any(c in fl_lower for c in ["stop", "don't", "never", "nobody", "wrong", "myth", "instead of", "versus", "vs"]):
        archetype = "Contrarian / Pattern Interrupt"
    elif re.search(r'^\d+\s|^\b[1-9]\b|\b\d+%\b|\b\d+\s(ways|steps|rules|lessons|frameworks|secrets)', fl_lower):
        archetype = "Numbered Framework / Listicle"

    # Score calculation
    score = 65

    # Archetype bonus
    if archetype in [
        "The Contrarian Confession", "The Architectural Breakdown", "The Concrete Proof",
        "The Step-by-Step Teardown", "The Direct Vulnerability", "Contrarian / Pattern Interrupt"
    ]:
        score += 15
    elif archetype in ["Numbered Framework / Listicle", "Question / Curiosity Gap"]:
        score += 10

    # Air gap bonus
    if has_air_gap:
        score += 10
    else:
        recommendations.append("Insert a visual air gap (blank line) immediately after line 1 to eliminate mobile reader fatigue.")
        score -= 10

    # Specificity & numbers
    has_number = bool(re.search(r'\d+', first_line))
    if has_number:
        score += 10

    # Cutoff compliance
    if mobile_safe:
        score += 15
    else:
        score -= 20
        recommendations.append(f"Your hook ({pre_fold_chars} chars) exceeds the 140-char mobile fold. Tighten line 1 so readers don't lose context before 'see more'.")

    # White space & line breaks
    blank_line_count = text.count("\n\n")
    if blank_line_count >= 2:
        score += 5
    elif len(raw_lines) <= 2 and char_count > 300:
        score -= 15
        recommendations.append("Avoid dense walls of text. Break long paragraphs into 1-2 sentence digestible chunks.")

    # Em-dash check
    em_dash = chr(0x2014)
    en_dash = chr(0x2013)
    has_dashes = (em_dash in text or en_dash in text)
    if has_dashes:
        recommendations.append("Em-dashes detected. Use natural commas or periods for executive readability.")
        score -= 10

    # Hashtags check
    hashtags = re.findall(r'#\w+', text)
    if len(hashtags) > 5:
        recommendations.append(f"Found {len(hashtags)} hashtags. LinkedIn's 2026 algorithm penalizes hashtag stuffing; keep to 3-5 high-relevance tags.")
        score -= 5

    final_score = min(max(score, 20), 100)

    return {
        "char_count": char_count,
        "word_count": word_count,
        "line_count": len(raw_lines),
        "hook_line": first_line,
        "hook_length": len(first_line),
        "hook_archetype": archetype,
        "archetype": archetype,
        "pre_fold_chars": pre_fold_chars,
        "pre_fold_length": pre_fold_chars,
        "mobile_safe": mobile_safe,
        "is_pre_fold_safe": mobile_safe,
        "has_air_gap": has_air_gap,
        "desktop_safe": desktop_safe,
        "score": final_score,
        "blank_lines": blank_line_count,
        "hashtag_count": len(hashtags),
        "has_em_dashes": has_dashes,
        "recommendations": recommendations if recommendations else ["Outstanding hook structure! Highly optimized for mobile scroll stoppage."]
    }
