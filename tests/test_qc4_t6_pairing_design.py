"""
Item 27: the phone pairing design is written against the checks it changes.
==========================================================================

docs/PHONE_PAIRING_DESIGN.md cites every check as `path:line` followed by
the name it points at. Each citation is held to its file: the file exists,
the line exists, and the name is in the file. Line numbers are allowed to
move, because security.py and app.py belong to other tracks and will move
at integration; a check that is renamed or removed fails here, because the
design would then describe code that is not there.

Strict Invariants:
- Zero em-dashes.
"""

import io
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DESIGN = os.path.join(REPO_ROOT, "docs", "PHONE_PAIRING_DESIGN.md")
CITATION = re.compile(r"`(studio/[^`:]+\.py):(\d+)(?:-(\d+))?` \(`([^`]+)`\)")


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _citations(text):
    return CITATION.findall(text)


def _broken(text, root=REPO_ROOT):
    broken = []
    for path, start, end, name in _citations(text):
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            broken.append(f"{path} does not exist")
            continue
        lines = _read(full).split("\n")
        if int(end or start) > len(lines):
            broken.append(f"{path}:{start} is past the end of the file")
        elif name not in "\n".join(lines):
            broken.append(f"{path} no longer has {name!r}")
    return broken


def test_every_citation_points_at_code_that_is_there():
    text = _read(DESIGN)
    assert len(_citations(text)) >= 20, "the design no longer cites the checks it changes"
    assert _broken(text) == []


def test_the_citation_guard_can_fail():
    """Falsified: a citation of a name the file does not hold is caught, and so is a missing file."""
    planted = ("`studio/backend/security.py:80` (`PAIRED_HOSTS_THAT_DO_NOT_EXIST`) and "
               "`studio/backend/nowhere.py:1` (`x`) and `studio/backend/security.py:99999` (`LOOPBACK_HOSTS`)")
    assert len(_broken(planted)) == 3


def test_the_design_keeps_the_decisions_it_was_asked_for():
    text = " ".join(_read(DESIGN).split())
    for decision in ("PAIRED_HOSTS", "never merged into `LOOPBACK_HOSTS`", "two minutes", "POST /api/v1/pair",
                     "inox_phone_token", "The studio cookie is never set on a paired host",
                     "`allowed_origins()`", "Refused: any Host-rewriting relay", "only with the code"):
        assert decision in text, f"the design lost {decision!r}"
    assert text.index("Tailscale Serve, first") < text.index("WireGuard, the option with no third party")
    assert "design document only" in text.lower() or "A design document only" in text


def test_nothing_in_the_code_pairs_a_phone_yet():
    """Item 27 is a design; item 38 builds it. No paired path may slip in unreviewed."""
    security = _read(os.path.join(REPO_ROOT, "studio", "backend", "security.py"))
    app = _read(os.path.join(REPO_ROOT, "studio", "backend", "app.py"))
    assert "PAIRED_HOSTS" not in security and "/api/v1/pair" not in app
