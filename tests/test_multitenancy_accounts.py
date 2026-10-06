"""
Multi-Tenant Creator Profile Verification Suite.
================================================
Validates:
1. Migration 16: creator_accounts table schema, index, and default account seeding.
2. GET /api/v1/accounts: listing accounts, active_account_id, and aggregate metrics.
3. POST /api/v1/accounts: creating a new profile with initials generation.
4. POST /api/v1/accounts/switch: switching active creator profiles.
5. DELETE /api/v1/accounts/{id}: deletion constraints (protects default account).
6. Strict zero em-dash compliance across multi-tenant files.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import get_db, init_db
import accounts

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database schema and migrations are initialized."""
    init_db()


def test_creator_accounts_table_and_default_seeding():
    """Verify Migration 16 creates creator_accounts table and seeds the default profile."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(creator_accounts)")
    cols = {row["name"]: row for row in cursor.fetchall()}
    assert "id" in cols
    assert "name" in cols
    assert "vanity" in cols
    assert "headline" in cols
    assert "avatar_initials" in cols
    assert "is_default" in cols

    # Check default account exists
    cursor.execute("SELECT id, name, is_default, avatar_initials FROM creator_accounts WHERE id = 'default'")
    row = cursor.fetchone()
    assert row is not None
    assert row["id"] == "default"
    assert row["is_default"] == 1
    assert len(row["avatar_initials"]) >= 1
    conn.close()


def test_accounts_api_list_and_active_detection():
    """Verify GET /api/v1/accounts returns accounts array and active_account_id."""
    res = client.get("/api/v1/accounts")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "success"
    assert "accounts" in data
    assert "active_account_id" in data
    assert len(data["accounts"]) >= 1

    default_acc = next((a for a in data["accounts"] if a["id"] == "default"), None)
    assert default_acc is not None
    assert default_acc["is_default"] is True


def test_accounts_api_create_and_initials():
    """Verify POST /api/v1/accounts creates profile with initials and default values."""
    payload = {
        "name": "Aravind Subramanian",
        "headline": "VP of Engineering at CloudScale",
        "vanity": "aravind-sub",
        "id": "aravind-cloudscale",
    }
    res = client.post("/api/v1/accounts", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "success"
    acc = data["account"]
    assert acc["id"] == "aravind-cloudscale"
    assert acc["name"] == "Aravind Subramanian"
    assert acc["headline"] == "VP of Engineering at CloudScale"
    assert acc["vanity"] == "aravind-sub"
    assert acc["avatar_initials"] == "AS"
    assert acc["is_default"] is False


def test_accounts_api_switch_lifecycle():
    """Verify POST /api/v1/accounts/switch alters active account."""
    # 1. Create a second account
    create_res = client.post("/api/v1/accounts", json={
        "name": "Sarah Jenkins",
        "headline": "Director of Product Architecture",
        "vanity": "sarah-jenkins-lead",
        "id": "sarah-j",
    })
    assert create_res.status_code == 200

    # 2. Switch to this account
    switch_res = client.post("/api/v1/accounts/switch", json={"account_id": "sarah-j"})
    assert switch_res.status_code == 200
    switch_data = switch_res.json()
    assert switch_data["status"] == "success"
    assert switch_data["active_account_id"] == "sarah-j"

    # 3. Verify listing reports sarah-j as active
    list_res = client.get("/api/v1/accounts")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["active_account_id"] == "sarah-j"

    sarah = next((a for a in list_data["accounts"] if a["id"] == "sarah-j"), None)
    assert sarah is not None
    assert sarah["is_active"] is True

    # 4. Switch back to default
    switch_back = client.post("/api/v1/accounts/switch", json={"account_id": "default"})
    assert switch_back.status_code == 200
    assert switch_back.json()["active_account_id"] == "default"


def test_accounts_api_delete_safeguards():
    """Verify DELETE /api/v1/accounts/{id} protects default profile and removes custom profiles."""
    # Refuse deleting default
    res = client.delete("/api/v1/accounts/default")
    assert res.status_code == 400

    # Create disposable account
    create_res = client.post("/api/v1/accounts", json={
        "name": "Temporary Client Profile",
        "id": "temp-client",
    })
    assert create_res.status_code == 200

    # Delete disposable account
    del_res = client.delete("/api/v1/accounts/temp-client")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # Verify gone from listing
    list_res = client.get("/api/v1/accounts")
    acc_ids = [a["id"] for a in list_res.json()["accounts"]]
    assert "temp-client" not in acc_ids


def test_strict_zero_em_dashes_in_multitenancy():
    """Strict verification: Zero literal em-dashes in Multi-Tenant files."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    targets = [
        os.path.join(base_dir, "studio", "backend", "accounts.py"),
        os.path.join(base_dir, "studio", "ui", "src", "components", "AccountSwitcher.tsx"),
        os.path.join(base_dir, "tests", "test_multitenancy_accounts.py"),
    ]

    for fpath in targets:
        assert os.path.exists(fpath), f"File {fpath} not found"
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            assert "\u2014" not in content, f"Forbidden em-dash found in {fpath}"
