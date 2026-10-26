"""
A reader that last ran a month ago is not a reader that never ran.
=================================================================

Found after v2.7.0, on the live install, while confirming an extension
reload. The health screen read:

    Your profile        NOT SEEN YET

about a reader whose capture was recorded on 18 October. Seven days and
thirteen hours later the engagers reader posted a capture of its own, and the
prune inside record_capture, which deletes every row older than the window
without regard to which extractor it belongs to, took the profile reader's
only row with it. The live captures table held 26 engagers rows and none for
the profile.

That inverted the screen. A reader that runs constantly looked healthy; a
reader that runs once at setup, or weekly, was reported as never having run,
which is the one thing a creator reads that screen to find out. It is also
not a claim the product may make: the studio knew perfectly well when that
reader last worked, and said otherwise.

The two rows the screen reads are now kept whatever their age. Everything
else still ages out, so the log does not grow without bound.

Strict Invariants:
- Zero em-dashes.
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))


@pytest.fixture
def studio(monkeypatch):
    """A throwaway install, so the session's own captures cannot stand in."""
    home = tempfile.mkdtemp(prefix="inox_capture_health_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    from database import init_db
    init_db()
    yield
    shutil.rmtree(home, ignore_errors=True)


def _age(extractor, days, **fields):
    """One capture, recorded as though it happened `days` ago."""
    from database import get_db
    when = datetime.now(timezone.utc) - timedelta(days=days)
    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO captures (observed_at, extractor, page_kind, items_seen, items_kept, drift) "
                "VALUES (?,?,?,?,?,?)",
                (when.isoformat(), extractor, "own_profile",
                 fields.get("items_seen", 1), fields.get("items_kept", 1), fields.get("drift")),
            )
    finally:
        conn.close()
    return when


def _health(extractor):
    import onboarding
    return {entry["extractor"]: entry for entry in onboarding.capture_health()}[extractor]


def _capture(extractor, **fields):
    import onboarding
    payload = {"extractor": extractor, "items_seen": 1, "items_kept": 1}
    payload.update(fields)
    return onboarding.record_capture(payload)


def test_a_busy_reader_does_not_erase_a_quiet_one(studio):
    """The live defect: engagers ran, and the profile reader became NOT SEEN YET."""
    read_on = _age("profile", days=8)
    _capture("engagers")

    entry = _health("profile")
    assert entry["state"] == "working", (
        "a reader that read the creator's profile eight days ago is reported as never run")
    assert entry["last_run_at"] == read_on.isoformat()


def test_when_it_last_worked_survives_too(studio):
    """
    The LAST WORKED date beside a drifting reader is the whole of what tells
    the creator how long it has been broken, so it outlives the window as well.
    """
    worked_on = _age("activity_posts", days=20, items_seen=4, items_kept=4)
    _age("activity_posts", days=9, items_seen=4, items_kept=0, drift='["post_text"]')
    _capture("engagers")

    entry = _health("activity_posts")
    assert entry["state"] == "drifting"
    assert entry["last_good_at"] == worked_on.isoformat(), (
        "the date the reader last worked was pruned, so the screen cannot say "
        "how long it has been broken")


def test_the_log_still_ages_out(studio):
    """
    Keeping what the screen reads is not keeping everything: a reader that has
    run for months holds its latest run, its latest good run, and the window.
    """
    from database import get_db
    for day in range(40, 8, -1):
        _age("engagers", days=day, items_seen=3, items_kept=3)
    _capture("engagers")

    conn = get_db()
    try:
        rows = conn.execute("SELECT COUNT(*) FROM captures WHERE extractor = 'engagers'").fetchone()[0]
    finally:
        conn.close()
    assert rows <= 3, f"{rows} rows kept for one extractor; the log is not ageing out"
    assert _health("engagers")["state"] == "working"


def test_a_reader_that_has_truly_never_run_still_says_so(studio):
    """The fix must not invent a run for a reader the bridge has never used."""
    _capture("engagers")
    assert _health("profile")["state"] == "never_run"
    assert _health("profile")["last_run_at"] is None


def test_the_prune_keeps_what_capture_health_reads(studio):
    """
    One rule, asked the same way in both places. The prune keeps the latest
    run and the latest good run of each extractor because those are the two
    rows capture_health selects; if that query changes and this one does not,
    the screen starts reading a row the prune is free to delete.
    """
    import onboarding
    import inspect

    reads = inspect.getsource(onboarding.capture_health)
    keeps = onboarding.PRUNE_CAPTURES
    for clause in ("drift IS NULL", "refused IS NULL", "COALESCE(items_seen, 0) > 0", "COALESCE(items_kept, 0) > 0"):
        assert clause in onboarding.GOOD_RUN, f"a good run no longer asks {clause!r}"
    assert "GOOD_RUN" in reads, "capture_health decides the last good run by a rule of its own"
    assert keeps.count(onboarding.GOOD_RUN) == 2, (
        "capture_health decides the last good run with GOOD_RUN and the prune "
        "does not, so the row the screen shows can be deleted")
