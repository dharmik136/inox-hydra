"""
The API serves what the studio uses, and no more. [D1, BE-17, BE-21, BE-22]

About thirty routes no screen, extension, CLI or desktop shell calls were
removed because they bypassed a guard the interface enforces, were broken, or
duplicated another route. Among them: POST /api/leads and /api/leads/batch
wiped a lead's notes and skipped the engagement gate; POST /api/ai/settings
made Gemini the active provider with an unverified key (one real request
reached Google that way during the research); archive-inactive wrote one of
two status columns; /api/ai/stream turned a refused provider into an empty
success; the rate limiter's acquire took the only token the profile sync
needs; stream/broadcast accepted a forged post_published. Telegram ingress
and the internal G-Stack backlog stay, for maintainers only: 404 outside dev
mode.

The LinkedIn send and schedule routes are batch R6's, the image routes R7's,
and DELETE /api/v1/crm/leads/{id}/purge is left for R4's forgetting work.
"""

import os
import re
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

REMOVED = [
    ("POST", "/api/leads"),
    ("POST", "/api/leads/batch"),
    ("POST", "/api/ai/settings"),
    ("POST", "/api/ai/stream"),
    ("POST", "/api/repurposer/command"),
    ("POST", "/api/swipe/analyze"),
    ("POST", "/api/carousel/generate"),
    ("POST", "/api/format/repurpose"),
    ("POST", "/api/format/analyze"),
    ("POST", "/api/format/dwell"),
    ("GET", "/api/analytics/demographics"),
    ("GET", "/api/v1/telemetry/status"),
    ("POST", "/api/v1/telemetry/flush"),
    ("GET", "/api/v1/crm/leads/export-csv"),
    ("GET", "/api/v1/crm/leads/high-value"),
    ("GET", "/api/v1/crm/telemetry"),
    ("POST", "/api/v1/crm/score-preview"),
    ("POST", "/api/v1/crm/dm/variants"),
    ("POST", "/api/v1/crm/leads/archive-inactive"),
    ("GET", "/api/v1/stream/events"),
    ("GET", "/api/v1/stream/history"),
    ("POST", "/api/v1/stream/broadcast"),
    ("GET", "/api/v1/session/health"),
    ("POST", "/api/v1/session/sync-profile"),
    ("POST", "/api/v1/database/checkpoint"),
    ("GET", "/api/v1/rate-limiter/status"),
    ("POST", "/api/v1/rate-limiter/acquire"),
    ("GET", "/api/v1/rate-limiter/single-writer/metrics"),
    ("POST", "/api/v1/intelligence/sync"),
    ("GET", "/api/v1/support/diagnostics"),
    ("POST", "/api/v1/support/diagnostics/export"),
]

MAINTAINER_ONLY = [
    ("POST", "/api/v1/ingress/simulate", {"text": "Idea: a post about pricing"}),
    ("POST", "/api/v1/ingress/parse", {"text": "Idea: a post about pricing"}),
    ("GET", "/api/v1/ingress/drafts", None),
    ("GET", "/api/v1/ingress/status", None),
    ("GET", "/api/v1/gstack/roles", None),
    ("GET", "/api/v1/gstack/backlog", None),
    ("POST", "/api/v1/gstack/backlog", {"role": "CEO", "title": "x", "description": "y"}),
    ("PATCH", "/api/v1/gstack/backlog/1", {"status": "done"}),
]


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("method, path", REMOVED)
def test_a_removed_route_is_gone(client, method, path):
    res = client.request(method, path, json={})
    assert res.status_code in (404, 405), (method, path, res.status_code)


@pytest.mark.parametrize("method, path, body", MAINTAINER_ONLY)
def test_maintainer_routes_are_404_for_a_creator(client, monkeypatch, method, path, body):
    monkeypatch.delenv("INOX_DEV_MODE", raising=False)
    res = client.request(method, path, json=body)
    assert res.status_code == 404, (method, path, res.status_code, res.text[:200])


@pytest.mark.parametrize("path", ["/api/v1/ingress/status", "/api/v1/gstack/roles", "/api/v1/ingress/drafts"])
def test_maintainer_routes_answer_in_dev_mode(client, monkeypatch, path):
    monkeypatch.setenv("INOX_DEV_MODE", "1")
    res = client.get(path)
    assert res.status_code == 200, res.text[:200]


def test_the_telegram_worker_needs_dev_mode(monkeypatch):
    import ingress

    started = []
    monkeypatch.setattr(ingress.ingress_daemon, "start_worker", lambda: started.append(True))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:not-a-real-token")
    monkeypatch.delenv("INOX_DEV_MODE", raising=False)
    import app as app_module

    monkeypatch.setattr(app_module, "ingress_daemon", ingress.ingress_daemon)
    with TestClient(app_module.app):
        pass
    assert started == [], "a bot token alone started the Telegram worker in a creator's install"


def _declared():
    declared = set()
    pattern = re.compile(r"@(?:app|router)\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)[\"']")
    sources = [os.path.join(BACKEND, "app.py")] + [
        os.path.join(BACKEND, "routers", name) for name in os.listdir(os.path.join(BACKEND, "routers"))
        if name.endswith(".py")]
    for source in sources:
        with open(source, encoding="utf-8") as handle:
            for method, path in pattern.findall(handle.read()):
                declared.add((method.upper(), re.sub(r"\{[^}]*\}", "*", path)))
    return declared


def test_every_route_the_extension_calls_still_exists():
    declared_paths = {path for _method, path in _declared()}
    extension = os.path.join(REPO_ROOT, "studio", "extension")
    called = set()
    for name in os.listdir(extension):
        if name.endswith(".js"):
            with open(os.path.join(extension, name), encoding="utf-8") as handle:
                for hit in re.findall(r"[\"'`](/api/[^\"'`\s]*)[\"'`]", handle.read()):
                    called.add(re.sub(r"\$\{[^}]*\}", "*", hit.split("?", 1)[0]).rstrip("/"))
    missing = sorted(path for path in called if path not in declared_paths)
    assert not missing, f"the extension calls routes that no longer exist: {missing}"


def test_the_cli_and_desktop_shell_routes_still_exist():
    declared = _declared()
    for method, path in [("GET", "/api/v1/health"), ("GET", "/api/v1/schema/status")]:
        assert (method, path) in declared, path
