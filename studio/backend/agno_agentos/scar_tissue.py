"""
Agno AgentOS Scar Tissue Engine (P6 Anti-Pattern Memory)
========================================================
Encodes lessons from past system failures, algorithmic flags, and content drift.
Strict negative constraints checked before any text is returned or persisted.
"""

import re
from typing import Tuple, List, Any

# Banned tropes that trigger LinkedIn algorithmic downranking or scream generic AI
BANNED_TROPES = [
    "game-changing",
    "revolutionary",
    "seamlessly",
    "delve",
    "testament to",
    "in today's fast-paced world",
    "bustling",
    "tapestry",
    "beacon",
    "furthermore",
    "moreover",
    "supercharge",
    "unlocking the potential",
    "at the end of the day",
]


def scrub_em_dashes(text: Any) -> str:
    """
    Enforces strict zero em-dash compliance across all generated text.
    Replaces em-dashes, en-dashes, and double dashes with natural punctuation.
    """
    if not text:
        return ""
    text_str = str(text)
    em_dash = chr(0x2014)
    en_dash = chr(0x2013)
    # Replace em-dash and en-dash
    cleaned = text_str.replace(em_dash, ", ").replace(en_dash, ", ")
    # Replace ASCII double/triple dash
    cleaned = re.sub(r'\s*--+\s*', ', ', cleaned)
    # Clean up double punctuation resulting from substitution
    cleaned = re.sub(r',\s*,', ',', cleaned)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    return cleaned.strip()


def validate_banned_vocabulary(text: str) -> Tuple[bool, List[str]]:
    """
    Checks if text contains banned AI buzzwords or low-signal tropes.
    Returns (is_clean, list_of_violations).
    """
    if not text:
        return True, []
    text_lower = text.lower()
    violations = [trope for trope in BANNED_TROPES if trope in text_lower]
    return len(violations) == 0, violations


def clean_banned_vocabulary(text: str) -> str:
    """Removes or replaces banned tropes with direct enterprise equivalents."""
    if not text:
        return ""
    cleaned = text
    replacements = {
        "game-changing": "high-impact",
        "revolutionary": "modern",
        "seamlessly": "directly",
        "supercharge": "accelerate",
        "unlocking the potential": "scaling",
        "in today's fast-paced world": "in modern engineering",
        "delve": "examine",
    }
    for bad, good in replacements.items():
        pattern = re.compile(re.escape(bad), re.IGNORECASE)
        cleaned = pattern.sub(good, cleaned)
    return cleaned


def validate_pre_fold_hook(first_lines: str, max_chars: int = 180) -> Tuple[bool, int]:
    """
    Validates that the post opening hook falls within the mobile '...see more' fold limit.
    Returns (is_safe, character_count).
    """
    if not first_lines:
        return True, 0
    # Measure first paragraph before double newline or first 2 lines
    paragraphs = first_lines.strip().split("\n\n")
    hook_text = paragraphs[0] if paragraphs else first_lines
    char_count = len(hook_text)
    return char_count <= max_chars, char_count
