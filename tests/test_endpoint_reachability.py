"""
How much of this backend the interface can actually reach, written down.
=======================================================================

A handoff reported "77 of 146 endpoints unreachable, down from 84". The real
figure was 79 of 145. Nobody had misled anyone: the number was counted by hand
once, quoted afterwards, and drifted because nothing measured it. A number that
appears in a handoff and in no test is a number that will be wrong by the time
somebody acts on it.

This is not a ratchet, and the distinction is the whole design.

A ratchet asserts a count does not grow, which is right for hex literals and
inline styles because those should only ever decrease. Reachability is
different: adding an endpoint before its surface exists is ordinary, correct
work, and a ceiling would fail the build for doing it. The existing ratchets in
this repository also sit at zero headroom, so adding another of that shape
would inherit a problem rather than solve one.

What this does instead is require the recorded numbers to match reality. Any
drift fails, in either direction, and the fix is to update the constants below
on purpose while saying what changed. Surfacing an endpoint is then a visible
improvement in a diff rather than an invisible one, and adding an unsurfaced
endpoint is a deliberate entry rather than a silent slide.

The counts are asserted exactly rather than as bounds, because "at most 79"
would quietly permit the one thing being guarded against: a route added,
unreached, and unremarked.

What is counted, and why it differs from the audit figure
--------------------------------------------------------
Distinct API paths, not route decorators. app.py has 146 decorators but fewer
paths: two handlers carry stacked aliases, and several paths serve more than
one method, so `GET /api/posts/{id}` and `DELETE /api/posts/{id}` are two
decorators on one path. An audit counting decorators reported 145 API routes
where this counts 137 paths, and neither is wrong.

Paths are the right unit here because reachability is a question about whether
the interface names an address at all. A path it never mentions is definitively
out of reach. Whether every method on a reachable path is exercised is a finer
question this does not attempt, and saying so is better than implying a
precision it does not have.
"""

import os
import re
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(REPO_ROOT, "studio", "backend", "app.py")
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")

# ---------------------------------------------------------------------------
# The recorded state. Update deliberately, with the reason in the commit.
#
# Measured 27 Sep 2026. The interface is the React source in studio/ui/src,
# which is the only interface now that the vanilla page is retired.
#
# Reached moved 62 -> 67 in one change, and only one of those five is new work.
# Surfacing /api/leads/*/dm-script accounts for one. The other four,
# /api/analytics/export, /api/analytics/kpis, /api/analytics/overview and
# /api/v1/intelligence/templates, were being called by the interface the whole
# time and counted as unreachable, because _normalise never stripped the query
# string those four calls carry. So this ledger was understating its own subject
# for as long as it has existed, in the direction that makes the product look
# worse than it is, which is the less dangerous direction but still wrong.
# ---------------------------------------------------------------------------
#
# Then 138 -> 150 paths, with onboarding. Twelve new paths: five the Setup
# screen calls, seven only the extension calls (heartbeat, identity/me,
# identity/observe, self/posts/ingest, self/outbound/ingest, the two import
# routes). Those seven are unreachable by this file's definition, which counts
# the interface, and that is the right answer rather than a gap: they are the
# extension's to call. In the same change the prefix rule was removed (see
# measured() below), which takes back one route it had been crediting falsely.
# ---------------------------------------------------------------------------
TOTAL_API_PATHS = 150
REACHED_BY_INTERFACE = 71
UNREACHABLE = 79

ROUTE_DECORATOR = re.compile(
    r"^\s*@app\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)[\"']", re.MULTILINE
)


def _normalise(path):
    """
    Reduces a path to something comparable across the two languages.

    FastAPI writes `/api/v1/mcp/servers/{name}/enabled`; the interface builds
    `/api/v1/mcp/servers/${encodeURIComponent(name)}/enabled`. Both become
    `/api/v1/mcp/servers/*/enabled`, so a parameterised route is not counted
    as unreachable merely because the two spell the hole differently.

    The query string goes too, and this was a real miss rather than a
    refinement. The containment check below was written on the assumption that a
    called path "may carry a query string", but nothing ever removed one, so
    `/api/leads/*/dm-script?*` failed all three comparisons against the route
    `/api/leads/*/dm-script`. A freshly surfaced endpoint therefore stayed in
    the unreachable column, which is the one outcome this file exists to
    prevent: a real improvement measured as no change at all.
    """
    path = path.split("?", 1)[0]
    path = re.sub(r"\$\{[^}]*\}", "*", path)
    path = re.sub(r"\{[^}]*\}", "*", path)
    return path.rstrip("/") or "/"


def _declared_routes():
    with open(APP, encoding="utf-8") as handle:
        source = handle.read()
    routes = set()
    for _method, path in ROUTE_DECORATOR.findall(source):
        if path.startswith("/api"):
            routes.add(_normalise(path))
    return routes


def _interface_paths():
    """Every /api path the interface names, from any file under studio/ui/src."""
    found = set()
    for dirpath, _dirnames, filenames in os.walk(UI_SRC):
        for name in filenames:
            if not name.endswith((".ts", ".tsx")):
                continue
            with open(os.path.join(dirpath, name), encoding="utf-8") as handle:
                text = handle.read()
            for hit in re.findall(r"[\"'`](/api/[^\"'`\s]*)[\"'`]", text):
                found.add(_normalise(hit))
    return found


@pytest.fixture(scope="module")
def measured():
    if not os.path.isdir(UI_SRC):
        pytest.skip("studio/ui/src is absent from this checkout")

    declared = _declared_routes()
    reached_paths = _interface_paths()

    reached = set()
    for route in declared:
        for called in reached_paths:
            # Exact, or the interface calls a longer path under this one.
            #
            # There was a third clause, route.startswith(called), meant for a
            # client that appends to a prefix. Normalisation already turns
            # every ${...} into *, so that case never needed it, and what it
            # actually did was credit a route whenever a SHORTER path was
            # called: DELETE /api/v1/identity counted /api/v1/identity/observe
            # as reached, and /api/v1/internal-sheet/issues/*/promote had been
            # counted for as long as this file existed although nothing in the
            # interface calls it.
            if route == called or called.startswith(route + "/"):
                reached.add(route)
                break

    return {
        "declared": declared,
        "reached": reached,
        "unreachable": declared - reached,
    }


def test_the_recorded_path_total_is_still_true(measured):
    actual = len(measured["declared"])
    assert actual == TOTAL_API_PATHS, (
        f"this backend declares {actual} distinct API paths, and this file records "
        f"{TOTAL_API_PATHS}. Update TOTAL_API_PATHS and say in the commit "
        f"what was added or removed."
    )


def test_the_recorded_reachable_count_is_still_true(measured):
    actual = len(measured["reached"])
    assert actual == REACHED_BY_INTERFACE, (
        f"the interface reaches {actual} routes, and this file records "
        f"{REACHED_BY_INTERFACE}. If you surfaced something, raise the number: "
        f"that is the improvement this test exists to make visible."
    )


def test_the_recorded_unreachable_count_is_still_true(measured):
    actual = len(measured["unreachable"])
    assert actual == UNREACHABLE, (
        f"{actual} routes have no caller in the interface, and this file "
        f"records {UNREACHABLE}.\n\n"
        f"If you added an endpoint without a surface, that is allowed, and "
        f"raising this number is how it stops being invisible. If you gave one "
        f"a surface, lower it.\n\n"
        f"Currently unreachable:\n  "
        + "\n  ".join(sorted(measured["unreachable"])[:20])
    )


def test_the_three_numbers_agree_with_each_other():
    """A transcription slip in the constants above should not need a diff to spot."""
    assert REACHED_BY_INTERFACE + UNREACHABLE == TOTAL_API_PATHS


def test_more_than_a_third_of_the_backend_is_reachable(measured):
    """
    A floor rather than a ceiling, and deliberately generous.

    This one does not need updating when a route is added. It exists so that a
    long run of unsurfaced endpoints cannot quietly become most of the product
    while each individual addition looks reasonable.
    """
    share = len(measured["reached"]) / max(1, len(measured["declared"]))
    assert share > 0.33, (
        f"only {share:.0%} of the backend is reachable from the interface"
    )
