"""
Profile views are offered only from a reader that fills them.
=============================================================

Analytics offered profile views as a measure and a figure, and Today's
thirty-day strip offered the figure too, while no reader on a real install
writes one: the only writer is linkedin_client.py's ingest, which nothing
calls on a real install. The figure was a permanent "not measured", which is
a figure the screen cannot ever answer. Decision 8 of cycle 4's PRD removed
it until a reader exists; the route still carries the column, so nothing
stored is lost and a reader can bring it back.

Track 5's own_insights.js is that reader: it reads profile views and search
appearances from the creator's own pages, each as a count over the window its
page names. So Analytics draws them again, from the account-figures route that
reader fills, and only from it. The daily column is still written by nothing,
so the chart still offers no profile-views measure, the KPI route's figure is
drawn nowhere, and Today's strip still offers none.
"""

import json
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COMPONENTS = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")
HELP = os.path.join(REPO_ROOT, "docs", "help")
EXTENSION = os.path.join(REPO_ROOT, "studio", "extension")

# The only places Analytics may name profile views: the account-figures
# reading, the page that reading came from, and the panel that draws it.
READING = "account.profile_views"
READ_FROM = 'profile_views: "Who viewed your profile"'
PANEL_LINE = 'line("Profile views", account.profile_views)'
PANEL_HEADING = "Profile views and search appearances"


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as handle:
        return handle.read()


def _code(source):
    """The source without its comments, which are allowed to say why the figure is gone."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(line.split("//")[0] for line in without_blocks.splitlines())


def test_analytics_offers_no_figure_no_reader_fills():
    source = _code(_read(COMPONENTS, "AnalyticsSurface.tsx"))
    measures = re.search(r"const METRICS = \[(.*?)\] as const", source, re.S)
    assert measures, "the chart's measures were not found"
    assert "profile_views" not in measures.group(1) and "Profile views" not in measures.group(1), (
        "the chart offers profile views as a daily measure, which no reader writes")
    # Every other profile_views is the account-figures reading or the page it
    # came from; the KPI route's column (kpis.profile_views and its delta),
    # which nothing fills, is read nowhere.
    assert source.count("profile_views") == source.count(READING) + source.count(READ_FROM), (
        "Analytics reads a profile_views other than the account-figures reading")
    assert source.count("Profile views") == source.count(PANEL_LINE) + source.count(PANEL_HEADING), (
        "Analytics draws Profile views somewhere other than the account-figures panel")


def test_the_profile_views_analytics_draws_come_from_a_reader_on_a_real_install():
    source = _code(_read(COMPONENTS, "AnalyticsSurface.tsx"))
    assert PANEL_LINE in source and "fetchAccountFigures(range)" in source
    api = _read(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")
    assert "/api/analytics/account-figures" in api
    route = _read(REPO_ROOT, "studio", "backend", "routers", "analytics.py")
    assert "own_insights.account_figures(" in route
    manifest = json.loads(_read(EXTENSION, "manifest.json"))
    scripts = [script for entry in manifest["content_scripts"] for script in entry["js"]]
    assert "own_insights.js" in scripts, "no reader on a real install reads profile views"
    assert '"profile_views"' in _read(EXTENSION, "own_insights.js")


def test_todays_thirty_days_offers_no_figure_no_reader_fills():
    source = _code(_read(COMPONENTS, "TodaySurface.tsx"))
    assert "profile_views" not in source and "Profile views" not in source


def test_the_help_no_longer_lists_the_measure():
    article = _read(HELP, "read-your-analytics.md")
    measures = next(line for line in article.splitlines() if line.startswith("- **Measure**"))
    assert "Profile views" not in measures, "the help still offers Profile views as a measure"
    assert "| Profile views |" not in article
    empty = _read(HELP, "why-is-my-analytics-chart-empty.md")
    assert "**Profile views** or **Comments**" not in empty
