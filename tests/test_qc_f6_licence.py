"""
The Licence, After It Ends.
===========================

An offline licence cannot be airtight, but it must not be undone by the
computer's clock, and an ended Agency licence must not keep every extra
creator profile working. Nothing is deleted or hidden when a licence ends:
a profile beyond what the licence covers can still be backed up, exported and
deleted, only not opened for work. The default profile always works.

Every key here is signed with a throwaway key made for the test, whose public
half is patched into PUBLIC_KEYS. The vendor key is never involved.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import base64
import os
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ed25519  # noqa: E402
import licensing  # noqa: E402
import paths  # noqa: E402

THROWAWAY_SECRET = os.urandom(32)


def _signed(**fields):
    payload = {"v": 1, "email": "buyer@example.com", "tier": "agency", "kind": "annual", "profiles": 5,
               "issued_at": "2026-10-19", "expires_at": "2099-01-01", "updates_until": "2099-01-01"}
    payload.update(fields)
    return licensing.encode(payload, lambda message: ed25519.sign(THROWAWAY_SECRET, message))


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", [base64.b64encode(ed25519.public_key(THROWAWAY_SECRET)).decode()])
    return tmp_path


# ---------------------------------------------------------------------------
# PLATFORM-23: an earlier clock does not revive an ended licence
# ---------------------------------------------------------------------------

def test_setting_the_clock_back_does_not_revive_an_ended_licence(vault):
    key = _signed(kind="monthly", issued_at="2026-10-19", expires_at="2026-11-19", updates_until="2026-11-19")
    assert licensing.install(key, today=date(2026, 10, 19))["status"] == "success"
    assert licensing.current(today=date(2026, 11, 1))["status"] == "active"

    ended = licensing.current(today=date(2026, 11, 25))
    assert ended["status"] == "expired" and ended["profile_limit"] == 1

    back = licensing.current(today=date(2026, 11, 1))
    assert back["status"] == "expired", "setting the clock back revived the licence"
    assert back["profile_limit"] == 1 and back["tier"] == "free"
    assert back["clock_behind"] is True and "2026-11-25" in back["reason"]


def test_a_renewal_still_works_while_the_clock_is_behind(vault):
    licensing.install(_signed(expires_at="2026-11-19"), today=date(2026, 10, 19))
    licensing.current(today=date(2026, 11, 25))
    renewed = licensing.install(_signed(expires_at="2026-12-31"), today=date(2026, 11, 1))
    assert renewed["status"] == "success"
    assert licensing.current(today=date(2026, 11, 1))["status"] == "active"


def test_an_ended_key_cannot_be_installed_by_setting_the_clock_back(vault):
    licensing.current(today=date(2026, 11, 25))
    result = licensing.install(_signed(expires_at="2026-11-19"), today=date(2026, 11, 1))
    assert result["status"] == "error" and "2026-11-19" in result["message"]
