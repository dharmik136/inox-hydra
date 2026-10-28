"""
Health names each browser the bridge runs in, and what each is holding.
======================================================================

Cycle 4, track 1, phase 2. With one bridge per browser, Health lists each
browser by name with the LinkedIn account it is signed in to, whether it was
heard from and how many LinkedIn pages it has open, and says when one holds
captures for an account no creator profile here holds. A tab the update
could not give the new readers is named; a reload is never asked of an
extension that reloads itself.

Every name here is invented.

Strict Invariants:
- Zero em-dashes.
"""

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from qc2_r5_live import confirm_identity, open_section, server, studio  # noqa: F401,E402


def _beat(client, instance, browser, vanity, **extra):
    body = {"extension_version": "2.10.0", "page_kind": "service_worker", "contract_version": 1,
            "browser_instance_id": instance, "browser": browser, "signed_in_vanity": vanity,
            "self_reload": True, "files_version": "2.10.0"}
    body.update(extra)
    assert client.post("/api/v1/bridge/heartbeat", json=body).status_code == 200


def test_health_lists_each_browser_and_what_it_holds(studio):
    client = studio["client"]
    confirm_identity(client)
    _beat(client, "b1a2c3d4-0000-4000-8000-000000000001", "Brave", "priya-raman-r5", open_pages={"feed": 2})
    _beat(client, "e5f6a7b8-0000-4000-8000-000000000002", "Microsoft Edge", "client-two-example",
          open_pages={}, held={"client-two-example": 3}, tabs_needing_reload=1)
    page = open_section(studio, "health")
    browsers = page.get_by_role("list", name="Browsers the bridge runs in")
    expect(browsers).to_contain_text("Brave, signed in as priya-raman-r5: connected, 2 LinkedIn pages open.", timeout=10000)
    expect(browsers).to_contain_text("Microsoft Edge, signed in as client-two-example: connected, no LinkedIn page open.")
    expect(browsers).to_contain_text("3 captures held: no creator profile here holds linkedin.com/in/client-two-example.")
    header = page.locator("main header")
    expect(header).to_contain_text("1 LinkedIn tab still carries an older copy of the bridge's readers")
    expect(header).not_to_contain_text("press Reload")
