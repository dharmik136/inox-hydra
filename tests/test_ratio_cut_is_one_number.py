"""
The Ratio Cut Is One Number
===========================
results.difference calls a ratio "more" at 1.25 and above and "fewer" at 0.8
and below (NOTABLE_HIGH, NOTABLE_LOW); between them it answers "none", a
difference the creator's own posts cannot separate. Four screens coloured a
ratio green from 1.2, so a 1.22x line read as a gain beside an engine that
had just said it was nothing (cycle 4, track 3, batch 0, from the sections
report's defects table).

The precedent is the fold and the gap in days: the number lives in one
TypeScript module, studio/ui/src/lib/results.ts, this reads both files
because nothing else joins them, and no surface may carry a cut of its own.
Falsified by planting `ratio >= 1.2` back into one surface.
"""

import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import results  # noqa: E402

UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")
MODULE = os.path.join(UI_SRC, "lib", "results.ts")
COMPONENTS = os.path.join(UI_SRC, "components")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _interface_cut(name):
    found = re.findall(rf"export const {name}\s*=\s*([0-9.]+)\s*;", _read(MODULE))
    assert len(found) == 1, f"expected one {name} declaration in lib/results.ts, found {found}"
    return float(found[0])


def test_the_interface_colours_at_the_engines_cut():
    assert _interface_cut("NOTABLE_HIGH") == results.NOTABLE_HIGH
    assert _interface_cut("NOTABLE_LOW") == results.NOTABLE_LOW


def _own_cuts(source):
    """Lines that compare a ratio with a literal cut, outside comments."""
    found = []
    for number, line in enumerate(source.splitlines(), 1):
        code = line.split("//")[0]
        if code.strip().startswith("*"):
            continue
        if re.search(r"ratio\s*(>=|<=|>|<)\s*[01]\.\d+\b", code):
            found.append((number, line.strip()))
    return found


def test_no_surface_carries_a_cut_of_its_own():
    offenders = []
    for name in sorted(os.listdir(COMPONENTS)):
        if not name.endswith(".tsx"):
            continue
        for number, line in _own_cuts(_read(os.path.join(COMPONENTS, name))):
            offenders.append(f"{name}:{number}: {line}")
    assert not offenders, "a surface colours a ratio at a cut of its own:\n" + "\n".join(offenders)


def test_the_guard_catches_the_cut_that_shipped():
    """A guard that cannot fail protects nothing: the exact line the four surfaces carried."""
    shipped = 'ratio >= 1.2 ? "text-signal-green-text" : ratio <= 0.8 ? "text-signal-orange-text" : "text-ink-muted",'
    assert _own_cuts(shipped), "the shipped cut is not caught"
    assert not _own_cuts("ratioTone(ratio)"), "a surface reading the one cut is flagged"


def test_every_surface_that_colours_a_ratio_reads_the_one_module():
    colouring = []
    for name in sorted(os.listdir(COMPONENTS)):
        if not name.endswith(".tsx"):
            continue
        source = _read(os.path.join(COMPONENTS, name))
        if "ratioTone(" in source and '"@/lib/results"' not in source:
            colouring.append(name)
    assert not colouring, f"these surfaces call ratioTone without importing it from lib/results: {colouring}"
