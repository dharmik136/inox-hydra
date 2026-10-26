"""
One gap in days, printed one way.
=================================

The backend measures a creator's rhythm once, in `insights.cadence`:
`median_gap_days`, `days_since_last` and `longest_gap.days`, each rounded to
one decimal. Three screens printed those same numbers three ways:

    Today      `${v.toFixed(1)} DAYS`          0.9 DAYS
    Queue      `${v.toFixed(1)} days`          0.9 days
    Patterns   `${Math.round(v)} days`         1 days

So Today said the creator posts every 0.9 days and Patterns said every 1 days,
about the same posts, and neither said it had rounded. Patterns also printed
`Math.round(cadence.days_since_last ?? 0)`, which showed a rhythm that had
never been measured as "0 days": a figure the studio does not hold.

This is the same fault cycle 3 was about, one step smaller: one measurement,
several renderings, and the renderings disagree. `studio/ui/src/lib/cadence.ts`
is now the one place a gap in days is turned into words, and the three screens
call it. What this holds is that they keep calling it.

The three words for the absent case were "NOT MEASURED", "Not measured" and
"Unknown"; there is now one, which a screen may upper-case for its own
typography.
"""

import io
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")
COMPONENTS = os.path.join(UI_SRC, "components")
MODULE = os.path.join(UI_SRC, "lib", "cadence.ts")

# The measured fields a creator reads as a number of days.
FIELDS = ("median_gap_days", "days_since_last", "longest_gap.days")


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _surfaces():
    for name in sorted(os.listdir(COMPONENTS)):
        if name.endswith(".tsx"):
            yield name, _read(os.path.join(COMPONENTS, name))


def test_the_one_formatter_exists_and_keeps_one_decimal():
    source = _read(MODULE)
    assert "export function formatDays" in source
    assert "export const NOT_MEASURED" in source
    assert "toFixed(1)" in source, "the one formatter no longer fixes the precision"


def test_no_screen_formats_a_measured_gap_itself():
    """
    A screen may compose a sentence around the formatted value. It may not turn
    the number into text, because that is where the three answers came from.
    """
    offenders = []
    for name, source in _surfaces():
        for line_number, line in enumerate(source.splitlines(), start=1):
            if "cadence" not in line and "rhythm" not in line and "longest_gap" not in line:
                continue
            for field in FIELDS:
                if field not in line:
                    continue
                if re.search(r"toFixed\(|Math\.round\(", line):
                    offenders.append(f"{name}:{line_number}: {line.strip()[:72]}")
    assert not offenders, (
        "a screen is formatting a measured gap itself instead of calling "
        "formatDays from lib/cadence.ts: " + "; ".join(offenders)
    )


def test_no_screen_shows_an_unmeasured_gap_as_a_number():
    """
    `?? 0` on a measured field prints a figure the studio does not have. Today
    and the Queue both branch on the absent case; Patterns defaulted it to 0.
    """
    offenders = []
    for name, source in _surfaces():
        for line_number, line in enumerate(source.splitlines(), start=1):
            for field in FIELDS:
                if field in line and re.search(r"\?\?\s*0\b", line):
                    offenders.append(f"{name}:{line_number}: {line.strip()[:72]}")
    assert not offenders, (
        "an unmeasured gap would print as a number: " + "; ".join(offenders)
    )


def test_every_screen_that_prints_a_gap_calls_the_one_formatter():
    """
    Read from the tree rather than from a list: a list named Patterns after
    cycle 4 moved its rhythm to the Queue, and would not have named a fourth
    screen that started printing a gap.
    """
    printing = sorted(name for name, source in _surfaces()
                      if any(field.split(".")[0] in source for field in FIELDS))
    assert {"TodaySurface.tsx", "QueueSurface.tsx"} <= set(printing), printing
    for name in printing:
        source = _read(os.path.join(COMPONENTS, name))
        assert '@/lib/cadence"' in source, f"{name} prints a gap without the one formatter"
        assert "formatDays(" in source or "gapOrNotMeasured(" in source, name


def test_one_wording_for_a_gap_that_was_not_measured():
    """
    "Unknown" was Patterns' own word for it. A screen may upper-case the one
    wording for its typography, which is why the literal is allowed to appear
    only through the constant.
    """
    offenders = []
    for name, source in _surfaces():
        for line_number, line in enumerate(source.splitlines(), start=1):
            if not any(field in line for field in FIELDS):
                continue
            if '"Unknown"' in line or '"NOT MEASURED"' in line:
                offenders.append(f"{name}:{line_number}")
    assert not offenders, (
        "a screen has its own word for a gap that was not measured, instead of "
        "NOT_MEASURED from lib/cadence.ts: " + ", ".join(offenders)
    )

# A screen may give the measured field a local name, which is how
# `const usual = rhythm?.median_gap_days` then reached `usual.toFixed(1)` in
# four places on the Queue without naming the field on those lines. So the
# three screens are also read for the shape rather than the field name.
ALIASED = re.compile(r"\b(?:usual|gap|slotGap|rhythm)\w*\.toFixed\(|Math\.round\(\s*(?:usual|gap|slotGap)\w*\s*\)")


def test_no_screen_formats_a_gap_under_a_local_name_either():
    offenders = []
    for name, source in _surfaces():
        for line_number, line in enumerate(source.splitlines(), start=1):
            if ALIASED.search(line):
                offenders.append(f"{name}:{line_number}: {line.strip()[:72]}")
    assert not offenders, (
        "a gap is formatted through a local alias instead of formatDays: "
        + "; ".join(offenders)
    )
