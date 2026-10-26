"""
Today's side panels are read again, as their failure sentence says.
===================================================================

When a panel's read did not come back, Today printed "The studio did not
answer. It is read again when this window comes back." That was true of
/api/v1/today, which useRefresh re-reads, and false of the six side panels
(evidence, cadence, the thirty days, the slots, the two held signals), which
were read once per mount and never again (cycle 4, track 3, batch 0, from
the sections report's defects table). A panel that failed stayed failed
until the creator left the screen.

Each panel's read is now under useRefresh with no interval: read again when
the studio answers after an outage and when the window comes back after
being away. Track 2 adds the event stream on top of the same hook.
"""

import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SURFACE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "TodaySurface.tsx")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _function(source, name):
    start = source.index(f"function {name}")
    depth, i = 0, source.index("{", start)
    for j in range(i, len(source)):
        if source[j] == "{":
            depth += 1
        elif source[j] == "}":
            depth -= 1
            if depth == 0:
                return source[start:j + 1]
    raise AssertionError(f"{name} does not close")


def test_every_side_panel_read_is_under_refresh():
    source = _read(SURFACE)
    hook = _function(source, "useRead")
    # With no interval; track 2 passes the panel's stream rule as the third
    # argument (useRefresh(again, undefined, listen)).
    assert re.search(r"useRefresh\(again(?:, undefined(?:, \w+)?)?\)", hook), \
        "useRead does not put its read under useRefresh, with no interval"
    # The six panels all read through useRead, so one wiring covers them.
    for endpoint in ("fetchEvidenceBrief", "fetchCadenceInsights", "fetchAnalyticsKpis", "fetchSmartSlots",
                     "fetchWaitingCaptures", "fetchBackupSchedule"):
        assert re.search(rf"useRead\(useCallback\(\(\) => {endpoint}\(", source), f"{endpoint} is not read through useRead"


def test_the_failure_sentence_still_promises_only_what_happens():
    source = _read(SURFACE)
    assert "It is read again when this window comes back" in source
