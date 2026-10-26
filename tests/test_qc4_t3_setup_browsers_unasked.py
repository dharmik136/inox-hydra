"""
Setup tells "could not ask" apart from "none found".
====================================================

Setup's load-by-hand box printed "No Chromium browser was found on this
computer" when /api/v1/browser/status had failed, because the failure was
swallowed into an empty list of browsers (cycle 4, track 3, batch 0, from the
sections report's defects table). A studio that could not be asked is not a
computer with no browser, and the sentence sent a creator to install Edge
over an outage.

The failed read now marks the answer as unreachable, and the box says the
studio could not be asked.
"""

import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SURFACE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "OnboardingSurface.tsx")
API = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_a_failed_read_is_not_an_empty_list():
    source = _read(SURFACE)
    catch = re.search(r"fetchBrowserBridge\(\)\s*\.then\(setBridge\)\s*\.catch\(\(\) => setBridge\((\{[^}]*\})\)\)", source)
    assert catch, "the browser read's failure is no longer recorded on the bridge state"
    assert "unreachable: true" in catch.group(1), "a failed read still reads as a computer with no browser"
    assert "unreachable?: boolean" in _read(API).split("export interface BrowserBridge {", 1)[1].split("\n}", 1)[0]


def test_the_box_says_the_studio_could_not_be_asked():
    source = _read(SURFACE)
    box = source[source.index("function LoadByHand"):]
    assert "bridge.unreachable" in box
    assert "could not be asked" in box, "the box does not tell a creator the studio could not be asked"
    assert "No Chromium browser was found" in box, "the honest sentence for a computer with no browser is gone"
