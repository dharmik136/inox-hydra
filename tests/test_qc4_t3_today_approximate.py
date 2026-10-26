"""
A rounded figure is marked approximate on Today as it is on Analytics.
=====================================================================

LinkedIn writes some figures as 1.2K, which is anything from 1,150 to
1,249. The KPI route says which of its figures and changes were built from
one (`approximate`) and which changes it withheld as smaller than the
rounding (`within_rounding`). Analytics drew a ~ on those; Today's "Last 30
days" strip read the same route and drew the figures unmarked (cycle 4,
track 3, batch 0, from the sections report's defects table). The two fields
are now on the shared type, and Today draws the mark.
"""

import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
API = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")
TODAY = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "TodaySurface.tsx")
ANALYTICS = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "AnalyticsSurface.tsx")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_the_shared_type_carries_what_the_route_says_about_rounding():
    block = _read(API).split("export interface AnalyticsKpis {", 1)[1].split("\n}", 1)[0]
    assert "approximate?: string[]" in block and "within_rounding?: string[]" in block
    assert "approximate?: string[]" not in _read(ANALYTICS), "Analytics still declares the field privately"


def test_today_draws_the_mark_on_a_rounded_figure():
    source = _read(TODAY)
    strip = source[source.index("function ThirtyDays"):]
    strip = strip[:strip.index("\nfunction ", 10)]
    assert "kpis.approximate" in strip or "kpis?.approximate" in strip, "the strip never reads which figures are rounded"
    for key in ("impressions", "total_engagements", "total_followers"):
        assert re.search(rf'approx\.has\("{key}"\)', strip), f"the {key} figure is never marked"
    about = source[source.index("function About"):source.index("function Figure")]
    assert 'aria-hidden="true">~<' in about and 'className="sr-only">about <' in about, (
        "the mark is not drawn, or a screen reader is not told what it means"
    )
    figure = source[source.index("function Figure"):]
    assert figure.count("<About />") == 2, "the figure and its change are not both marked"
