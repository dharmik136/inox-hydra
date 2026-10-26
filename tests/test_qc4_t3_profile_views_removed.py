"""
Profile views are not offered until a reader exists.
====================================================

Analytics offered profile views as a measure and a figure, and Today's
thirty-day strip offered the figure too, while no reader on a real install
writes one: the only writer is linkedin_client.py's ingest, which nothing
calls on a real install. The figure was a permanent "not measured", which is
a figure the screen cannot ever answer. Decision 8 of cycle 4's PRD removes
it until a reader exists; the route still carries the column, so nothing
stored is lost and a reader can bring it back.
"""

import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COMPONENTS = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")
HELP = os.path.join(REPO_ROOT, "docs", "help")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as handle:
        return handle.read()


def test_analytics_offers_no_figure_no_reader_fills():
    source = _read(COMPONENTS, "AnalyticsSurface.tsx")
    assert "profile_views" not in source and "Profile views" not in source


def test_todays_thirty_days_offers_no_figure_no_reader_fills():
    source = _read(COMPONENTS, "TodaySurface.tsx")
    assert "profile_views" not in source and "Profile views" not in source


def test_the_help_no_longer_lists_the_measure():
    article = _read(HELP, "read-your-analytics.md")
    measures = next(line for line in article.splitlines() if line.startswith("- **Measure**"))
    assert "Profile views" not in measures, "the help still offers Profile views as a measure"
    assert "| Profile views |" not in article
    empty = _read(HELP, "why-is-my-analytics-chart-empty.md")
    assert "**Profile views** or **Comments**" not in empty
