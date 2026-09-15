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
    cleaned = text.replace("—", ", ").replace("–", ", ")
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
            "hook_line": "",
            "mobile_safe": True,
            "desktop_safe": True,
            "recommendations": ["Write a strong first sentence to hook your reader."]
        }

    raw_lines = text.splitlines()
    non_empty_lines = [l.strip() for l in raw_lines if l.strip()]
    first_line = non_empty_lines[0] if non_empty_lines else ""
    words = re.findall(r'\b\w+\b', text)
    word_count = len(words)
    char_count = len(text)
    
    # Check mobile fold (typically 3 visual lines or ~210 characters)
    # If the first non-empty block is too long or there are >3 lines before 210 chars
    mobile_cutoff_chars = 210
    desktop_cutoff_chars = 320
    
    first_3_lines_text = "\n".join(raw_lines[:3]) if len(raw_lines) >= 3 else text
    mobile_safe = len(first_3_lines_text) <= mobile_cutoff_chars and len(first_line) <= 140
    desktop_safe = len("\n".join(raw_lines[:5])) <= desktop_cutoff_chars

    # Classify Hook Archetype
    fl_lower = first_line.lower()
    archetype = "Direct Statement"
    recommendations = []

    if any(q in fl_lower for q in ["?", "why", "how do you", "have you ever", "what if"]):
        archetype = "Question / Curiosity Gap"
    elif any(c in fl_lower for c in ["stop", "don't", "never", "nobody", "wrong", "myth", "instead of", "versus", "vs"]):
        archetype = "Contrarian / Pattern Interrupt"
    elif re.search(r'^\d+\s|^\b[1-9]\b|\b\d+%\b|\b\d+\s(ways|steps|rules|lessons|frameworks|secrets)', fl_lower):
        archetype = "Numbered Framework / Listicle"
    elif any(s in fl_lower for s in ["i spent", "after 3 years", "last week i", "when i was", "i failed", "stepping into", "during my time"]):
        archetype = "Personal Experience / Narrative"
    elif "how to" in fl_lower or "the blueprint" in fl_lower or "the architecture" in fl_lower:
        archetype = "Playbook / Tactical Guide"

    # Score calculation
    score = 70

    # Archetype bonus
    if archetype in ["Contrarian / Pattern Interrupt", "Numbered Framework / Listicle"]:
        score += 12
    elif archetype in ["Personal Experience / Narrative", "Question / Curiosity Gap"]:
        score += 8

    # Specificity & numbers
    has_number = bool(re.search(r'\d+', first_line))
    if has_number:
        score += 8

    # Cutoff compliance
    if mobile_safe:
        score += 10
    else:
        score -= 15
        recommendations.append("Your hook exceeds the mobile 3-line fold (~210 chars). Tighten line 1 so readers don't lose context before 'see more'.")

    # White space & line breaks
    blank_line_count = text.count("\n\n")
    if blank_line_count >= 2:
        score += 5
    elif len(raw_lines) <= 2 and char_count > 400:
        score -= 15
        recommendations.append("Avoid dense walls of text. Break long paragraphs into 1-2 sentence digestible chunks.")

    # Em-dash check
    if "—" in text or "–" in text:
        recommendations.append("Em-dashes detected. Use natural commas or periods for executive readability.")
        score -= 5

    # Hashtags check
    hashtags = re.findall(r'#\w+', text)
    if len(hashtags) > 5:
        recommendations.append(f"Found {len(hashtags)} hashtags. LinkedIn's 2026 algorithm penalizes hashtag stuffing; keep to 3-5 high-relevance tags.")
        score -= 5

    final_score = min(max(score, 25), 100)

    return {
        "char_count": char_count,
        "word_count": word_count,
        "line_count": len(raw_lines),
        "hook_line": first_line,
        "hook_length": len(first_line),
        "hook_archetype": archetype,
        "mobile_safe": mobile_safe,
        "desktop_safe": desktop_safe,
        "score": final_score,
        "blank_lines": blank_line_count,
        "hashtag_count": len(hashtags),
        "has_em_dashes": ("—" in text or "–" in text),
        "recommendations": recommendations if recommendations else ["Outstanding hook structure! Highly optimized for mobile scroll stoppage."]
    }
