"""
No status mark the studio has not measured
==========================================
The Composer's header read "POST / DRAFT 01" for every post, which looks like
a draft number. The Live Activity button carried a pulsing green dot on every
screen, even on Setup beside "Not seen yet", and the profile avatar a green
online dot that nothing set. Each read as live state and was decoration. The
pulsing dot was also the last raw palette colour (bg-emerald-400) in the
interface, so it did not follow the theme.

The browser half (the dot follows the bridge) is in
tests/test_qc_f1a_composer.py; this pins the source so none comes back.
"""

import glob
import io
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")

# Tailwind's own palette, as opposed to the studio's tokens (bg-signal-green,
# text-ink-muted and so on), which follow the theme.
PALETTE = re.compile(
    r"\b(?:bg|text|border|ring|fill|stroke|from|to|via|outline|decoration|shadow|accent|caret|divide|placeholder)-"
    r"(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|"
    r"violet|purple|fuchsia|pink|rose)-\d{2,3}\b|\b(?:bg|text|border)-(?:white|black)\b"
)


def _sources():
    for path in sorted(glob.glob(os.path.join(UI_SRC, "**", "*.ts*"), recursive=True)):
        yield os.path.relpath(path, REPO_ROOT), io.open(path, encoding="utf-8").read()


def test_no_component_uses_a_raw_palette_colour():
    found = [f"{path}: {hit.group(0)}" for path, source in _sources() for hit in PALETTE.finditer(source)]
    assert not found, "colours that ignore the theme tokens:\n" + "\n".join(found)


def test_the_palette_guard_is_not_vacuous():
    assert PALETTE.search('className="size-1.5 rounded-full bg-emerald-400 animate-pulse"')
    assert PALETTE.search('className="hover:text-red-500"')
    assert not PALETTE.search('className="bg-signal-green text-ink-muted border-edge-strong"')


def test_the_composer_header_carries_no_invented_draft_number():
    for path, source in _sources():
        assert "DRAFT 01" not in source, path


def test_the_profile_avatar_claims_no_online_state():
    source = io.open(os.path.join(UI_SRC, "components", "AccountSwitcher.tsx"), encoding="utf-8").read()
    assert "bg-signal-green ring-2" not in source, "the avatar still wears an online dot nothing measures"
