"""
The diagnostics bundle carries no typed words and nobody's identity. [BE-03]

The bundle tails logs/engine.log, where every launcher sends uvicorn's console.
uvicorn's access log wrote each request with its query string, so the bundle
the creator is told to attach to a public issue held every Ctrl+K search
("Asha Mehta"), every first-message topic ("layoffs at Acme") and every help
search. Now the access log never writes a query string and skips successful
reads, and the bundle reduces every log line it includes to its shape.
"""

import json
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
BACKEND = os.path.join(os.path.dirname(__file__), "..", "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, os.path.abspath(BACKEND))

from studio.backend import database, paths, support  # noqa: E402

NAMES = ("Asha", "Mehta", "Durand", "layoffs", "Acme", "asha-mehta-42", "priya@example.com",
         "ACoAAB12345", "Pune meetup", "before the Acme pitch")

PLANTED = [
    '--- engine launch at unix time 1792000000 ---',
    'INFO:     127.0.0.1:53122 - "GET /api/v1/search?q=Asha%20Mehta&limit=8 HTTP/1.1" 200 OK',
    'INFO:     127.0.0.1:53122 - "GET /api/v1/search?q=%C3%89mile%20Durand%20Acme%20layoffs&limit=8 HTTP/1.1" 200 OK',
    'INFO:     127.0.0.1:53122 - "GET /api/leads/lead_3f2a/dm-script?style=value_add&topic=your+post+about+the+layoffs+at+Acme HTTP/1.1" 200 OK',
    'Traceback (most recent call last):',
    '  File "/opt/inox/studio/backend/crm.py", line 412, in ingest',
    '    raise ValueError(f"no lead named {name!r}")',
    "ValueError: no lead named 'Asha Mehta' from https://www.linkedin.com/in/asha-mehta-42/ (priya@example.com)",
    'WARNING:studio.leads: could not file urn:li:fsd_profile:ACoAAB12345 "Met at the Pune meetup"',
]


@pytest.fixture
def home_with_log(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio-home"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    with open(os.path.join(paths.get_logs_dir(), "engine.log"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(PLANTED) + "\n")
    return tmp_path


def test_the_bundle_carries_no_query_string_name_or_typed_text(home_with_log):
    text = json.dumps(support.collect_diagnostics())
    for needle in NAMES:
        assert needle not in text, f"the bundle carries {needle!r}"


def test_the_bundle_still_shows_what_a_maintainer_needs(home_with_log):
    lines = support.collect_diagnostics()["logs"][0]["last_lines"]
    joined = "\n".join(lines)
    assert '"GET /api/v1/search?<redacted> HTTP/1.1" 200' in joined
    assert '"GET /api/leads/lead_3f2a/dm-script?<redacted> HTTP/1.1" 200' in joined
    assert 'File "/opt/inox/studio/backend/crm.py", line 412, in ingest' in joined
    assert "ValueError: no lead named" in joined
    assert "linkedin.com/in/<redacted>" in joined


def test_a_backup_label_the_creator_typed_is_not_in_the_bundle(home_with_log):
    backups = paths.get_backups_dir()
    for name in ("inox_backup_before the Acme pitch_20261020_101010.zip",
                 "inox_backup_manual_20261020_101011.zip"):
        with open(os.path.join(backups, name), "wb") as handle:
            handle.write(b"x")
    report = support.collect_diagnostics()
    names = [b["name"] for b in report["backups"]]
    assert "inox_backup_manual_20261020_101011.zip" in names
    assert "inox_backup_<redacted>_20261020_101010.zip" in names
    assert "Acme" not in json.dumps(report)


def _access_record(method, target, status):
    return logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                             ("127.0.0.1:53122", method, target, "1.1", status), None)


def test_the_access_log_drops_query_strings_and_successful_reads():
    import log_setup

    log_setup.install()
    logger = logging.getLogger("uvicorn.access")
    assert sum(isinstance(f, log_setup.PrivateAccessLog) for f in logger.filters) == 1

    read = _access_record("GET", "/api/v1/search?q=Asha%20Mehta", 200)
    assert not logger.filter(read), "a successful read is still written"

    failed = _access_record("GET", "/api/v1/search?q=Asha%20Mehta", 500)
    assert logger.filter(failed)
    assert failed.getMessage() == '127.0.0.1:53122 - "GET /api/v1/search HTTP/1.1" 500'

    write = _access_record("POST", "/api/posts?topic=layoffs", 200)
    assert logger.filter(write)
    assert "layoffs" not in write.getMessage()


def test_the_app_installs_the_access_filter():
    import app  # noqa: F401
    import log_setup

    assert any(isinstance(f, log_setup.PrivateAccessLog) for f in logging.getLogger("uvicorn.access").filters)


def test_the_cli_no_longer_calls_the_bundle_safe_to_publish_unread():
    with open(os.path.join(os.path.dirname(__file__), "..", "studio", "cli.py"), encoding="utf-8") as handle:
        source = handle.read()
    assert "This file is safe to attach to a public issue" not in source
