"""
Clean formatting keeps what the text means
==========================================
Clean is offered to take dashes out of a post. It turned every en dash that
was not between two digits into a comma, so "Mon-Fri, 9am-5pm" written with
en dashes came back as "Mon, Fri, 9am, 5pm": two days and two times rather
than two ranges. It also flattened indentation and took the space out of
"Use .env files", gluing the file name to the word before it.

Spacing decides what an en dash is doing. Unspaced it joins a range or a pair
("Q1-Q4", "London-Paris"), and a hyphen keeps that. Spaced it is a pause, and
a comma is right. The em dash is always a pause, which is the anti-slop rule.
"""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from formatters import clean_text_formatting  # noqa: E402

EN_DASH = chr(0x2013)
EM_DASH = chr(0x2014)


def test_unspaced_en_dash_ranges_stay_ranges():
    assert clean_text_formatting(f"Office hours Mon{EN_DASH}Fri, 9am{EN_DASH}5pm.") == "Office hours Mon-Fri, 9am-5pm."
    assert clean_text_formatting(f"Targets for Q1{EN_DASH}Q4 are below.") == "Targets for Q1-Q4 are below."
    assert clean_text_formatting(f"London{EN_DASH}Paris in 2h.") == "London-Paris in 2h."


def test_a_spaced_en_dash_is_still_a_pause():
    assert clean_text_formatting(f"first principles {EN_DASH} always") == "first principles, always"


def test_numeric_ranges_and_the_em_dash_rule_are_unchanged():
    assert clean_text_formatting(f"pages 10 {EN_DASH} 20") == "pages 10-20"
    assert clean_text_formatting(f"Revenue grew 2021{EN_DASH}2024") == "Revenue grew 2021-2024"
    assert clean_text_formatting(f"A{EM_DASH}B") == "A, B"
    assert clean_text_formatting(f"Scaling {EM_DASH} zero downtime") == "Scaling, zero downtime"


def test_indentation_survives_and_inner_runs_of_spaces_collapse():
    cleaned = clean_text_formatting("Run   it   like   this:\n    npm run build\n\tthen ship")
    assert cleaned == "Run it like this:\n    npm run build\n\tthen ship", repr(cleaned)


def test_a_dot_that_starts_a_word_keeps_its_space():
    assert clean_text_formatting("Use .env files .") == "Use .env files."
    assert clean_text_formatting("Ship it , then measure .") == "Ship it, then measure."
    assert clean_text_formatting("Call it .NET or .gitignore") == "Call it .NET or .gitignore"
