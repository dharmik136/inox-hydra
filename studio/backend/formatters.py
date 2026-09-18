import re
import math

def to_sans_bold(text: str) -> str:
    """Converts standard ASCII characters to Unicode Mathematical Sans-Serif Bold."""
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


def to_sans_italic(text: str) -> str:
    """Converts standard ASCII characters to Unicode Mathematical Sans-Serif Italic."""
    out = []
    for c in text:
        if 'A' <= c <= 'Z':
            out.append(chr(0x1D608 + ord(c) - ord('A')))
        elif 'a' <= c <= 'z':
            out.append(chr(0x1D622 + ord(c) - ord('a')))
        else:
            out.append(c)
    return ''.join(out)


def to_monospace(text: str) -> str:
    """Converts ASCII characters to Unicode Mathematical Monospace."""
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


def to_strikethrough(text: str) -> str:
    """Adds combining long stroke overlay (strikethrough) to each character."""
    return ''.join(c + '\u0336' if c != '\n' else c for c in text)


def clean_text_formatting(text: str) -> str:
    """
    Cleans em-dashes, en-dashes, irregular spaces, and restores clean natural punctuation.
    """
    # Replace em-dashes and en-dashes with natural comma/pause
    cleaned = text.replace("\u2014", ", ").replace("–", ", ")
    # Fix double/triple hyphens used as dashes
    cleaned = re.sub(r'(?<=\w)--+(?=\w)', ', ', cleaned)
    # Clean redundant spaces
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    # Clean space before commas or periods
    cleaned = re.sub(r' +([,.:;?!])', r'\1', cleaned)
    # Clean double commas
    cleaned = re.sub(r',\s*,', ',', cleaned)
    return cleaned.strip()


def analyze_hook(text: str) -> dict:
    """
    Deep-dive algorithmic analysis of LinkedIn post:
    - Hook strength and archetype classification
    - Truncation cutoff check for Mobile (3 lines / 210 chars) and Desktop (5 lines / 320 chars)
    - Pacing & whitespace density (penalizing walls of text)
    - Readability & punchiness score (0 - 100)
    """
    if not text or not text.strip():
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
    if "\u2014" in text or "–" in text:
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
        "has_em_dashes": ("\u2014" in text or "–" in text),
        "recommendations": recommendations if recommendations else ["Outstanding hook structure! Highly optimized for mobile scroll stoppage."]
    }
