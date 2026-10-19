"""
The Diagnostics Bundle Is Safe to Post in Public.
=================================================

Creators are told to attach the bundle to a public GitHub issue. On most
machines every path in it starts with the OS account folder, which is often the
person's real name, and each bundle used to carry the previous one inside it.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.backend import database, support  # noqa: E402


@pytest.fixture
def named_home(tmp_path, monkeypatch):
    """A studio whose data lives under an account folder carrying a real name."""
    account = tmp_path / "Jane Doe"
    monkeypatch.setenv("HOME", str(account))
    monkeypatch.setenv("USERPROFILE", str(account))
    monkeypatch.setenv("LOCALAPPDATA", str(account / "AppData" / "Local"))
    monkeypatch.setenv("INOX_HYDRA_HOME", str(account / ".local" / "share" / "inox-hydra"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    return account


def test_the_bundle_does_not_carry_the_account_folder(named_home):
    report = support.collect_diagnostics()
    serialized = json.dumps(report, default=str)
    assert "Jane Doe" not in serialized, "the bundle carries the OS account folder"
    assert report["paths"]["app_home"].startswith("~")


def test_a_bundle_does_not_carry_the_previous_one(named_home):
    first = support.write_diagnostics_bundle()
    second = support.write_diagnostics_bundle()
    assert first != second, "two bundles in the same second overwrote each other"
    with open(second, encoding="utf-8") as handle:
        report = json.load(handle)
    assert not [entry["name"] for entry in report["logs"] if entry["name"].startswith("inox_diagnostics_")]
    with open(second, encoding="utf-8") as handle:
        assert "Jane Doe" not in handle.read()
