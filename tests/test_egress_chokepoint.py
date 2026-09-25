"""
Egress Chokepoint Guard
=======================
The product's first constraint is that your work stays on this machine. For a
long time that was enforced for one destination: `linkedin_client` routed its
three requests through a guard that refuses by default and returns a visible
refusal. Six other modules, fourteen calls between them, reached nine hosts
with no guard, no counter, and no way to say no.

`studio/backend/egress.py` is that guard generalised. The point of this file is
to prove the chokepoint is real rather than decorative, which means two things
that are easy to get wrong:

  1. every outbound call passes through it, including ones added later
  2. a refusal actually prevents the connection, rather than being recorded
     next to a request that goes out anyway

The second is why the socket layer is booby trapped below instead of the
policy being read back.

The wiring itself was got wrong once, in a way worth remembering. The first
pass inserted each guard by line number, having captured those numbers before
adding an import block, so thirteen of fourteen landed several lines below the
call they were meant to protect. Every one still parsed, imported and passed
the suite. Only checking that each call had a guard above it inside its own
function found it, which is what the first test here does.
"""

import io
import os
import re
import sys
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)

import egress  # noqa: E402

# Anything that opens a socket to another host.
CALL = re.compile(r"urllib\.request\.urlopen\(|requests\.(?:get|post|put|patch|delete)\(")

CATEGORIES = ("linkedin", "model", "image", "library", "updates", "ingress")


@pytest.fixture(autouse=True)
def clean_counters():
    egress.reset_for_tests()
    yield
    egress.reset_for_tests()


@pytest.fixture
def no_egress(monkeypatch):
    monkeypatch.setenv(egress.MASTER_OFF_FLAG, "1")
    yield


def _backend_sources():
    for base, _dirs, files in os.walk(BACKEND):
        if "__pycache__" in base:
            continue
        for name in sorted(files):
            if name.endswith(".py") and name != "egress.py":
                yield os.path.join(base, name)


def test_every_outbound_call_is_guarded():
    """
    The structural half, and the check that caught the misplaced wiring.

    Searches back to the top of the enclosing function rather than at the line
    immediately above. linkedin_client guards with an early return, which is
    the better shape of the two: it refuses once and leaves the request
    unreachable, rather than sitting adjacent to it.
    """
    problems = []
    for path in _backend_sources():
        lines = io.open(path, encoding="utf-8").read().split(chr(10))
        rel = os.path.relpath(path, REPO_ROOT)
        for index, line in enumerate(lines):
            if not CALL.search(line) or "_egress" in line:
                continue

            guarded = False
            for back in range(index - 1, -1, -1):
                candidate = lines[back]
                if "_egress.require(" in candidate or "egress_guard(" in candidate:
                    guarded = True
                    break
                if candidate.strip().startswith(("def ", "async def ")):
                    break
            if not guarded:
                problems.append(f"{rel}:{index + 1} unguarded: {line.strip()[:70]}")

    assert not problems, (
        "an outbound call is not behind the chokepoint:" + chr(10) + "  "
        + (chr(10) + "  ").join(problems)
    )


def test_linkedin_still_refuses_by_default():
    """The original contract, unchanged by generalising it."""
    refusal = egress.guard("voyager/api/me", category="linkedin")
    assert refusal is not None
    assert refusal["status"] == "egress_refused"
    assert refusal["checked"] is False
    # Not healthy and not unhealthy. A caller must be able to tell "we did not
    # look" from "we looked and it was fine".
    assert refusal["healthy"] is None
    assert egress.stats_for("linkedin")["refused"] == 1
    assert egress.stats_for("linkedin")["performed"] == 0


def test_an_action_you_asked_for_is_not_refused_by_default():
    """
    Pressing Generate is consent. Refusing it by default would only teach
    someone to set a flag and forget it, which enforces nothing and costs a
    working feature.
    """
    assert egress.guard("https://image.pollinations.ai/x", category="image") is None
    assert egress.stats_for("image")["performed"] == 1
    assert egress.stats_for("image")["last_destination"].endswith("/x")


def test_the_master_switch_refuses_every_category(no_egress):
    """
    One variable, and nothing in this process may open a connection. This is
    what makes the constraint enforceable rather than descriptive.
    """
    for category in CATEGORIES:
        refusal = egress.guard("https://example.invalid", category=category)
        assert refusal is not None, f"{category} was allowed with the master switch on"
        assert egress.MASTER_OFF_FLAG in refusal["message"]


def test_update_checks_are_off_before_the_guard_is_even_consulted():
    """
    Defence in depth, confirmed rather than assumed.

    updates.py asks before it ever checks, so on a default install the network
    path is unreachable for a reason that has nothing to do with egress policy.
    Worth pinning: it is the layer a user actually benefits from, and it would
    be easy to lose while refactoring the layer below it.
    """
    import updates

    result = updates.check_for_update(force=True)
    assert result["checked"] is False
    assert result["enabled"] is False
    assert "disabled" in result["reason"].lower()
    assert egress.stats_for("updates")["performed"] == 0


def test_a_refusal_prevents_the_connection_rather_than_recording_it(no_egress, monkeypatch):
    """
    The half that matters, exercised rather than read back.

    A counter that increments beside a request which goes out anyway is worse
    than no counter, so the socket layer itself is booby trapped: if anything
    on the refused path reaches the network this fails with that assertion
    rather than with a refusal.

    Update checks are turned on first, precisely so the outer preference stops
    shielding the inner guard. That leaves the egress policy as the only thing
    standing between this call and a socket, which is what is being tested.
    """
    import socket

    import updates

    def explode(*_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("a socket was opened despite the refusal")

    monkeypatch.setattr(socket, "socket", explode)
    monkeypatch.setattr(socket, "create_connection", explode)

    updates.set_enabled(True)
    try:
        result = updates.check_for_update(force=True)
    finally:
        updates.set_enabled(False)

    blob = str(result)
    assert egress.MASTER_OFF_FLAG in blob, (
        f"the refusal did not reach the caller, which got: {blob[:300]}"
    )
    assert egress.stats_for("updates")["refused"] >= 1
    assert egress.stats_for("updates")["performed"] == 0


def test_a_refused_category_reports_itself(no_egress):
    """
    describe() is what the Local security tab reads, so it has to reflect the
    live state rather than the defaults compiled in.
    """
    egress.guard("https://api.openai.com/v1/x", category="model")
    described = egress.describe()

    assert described["master_off"] is True
    assert described["total_refused"] == 1
    assert described["total_performed"] == 0

    model = next(c for c in described["categories"] if c["name"] == "model")
    assert model["allowed"] is False
    assert model["default_allowed"] is True, "the default should still be readable when overridden"
    assert model["last_refused_endpoint"].startswith("https://api.openai.com")


def test_every_category_is_described():
    """The tab renders this list, so a new category must not be invisible."""
    names = {c["name"] for c in egress.describe()["categories"]}
    assert names == set(CATEGORIES), f"described categories drifted: {sorted(names)}"


def test_an_unknown_category_is_a_mistake_not_a_silent_allow():
    """
    A typo in a category name must not open a hole. Failing loudly here is the
    difference between a chokepoint and a suggestion.
    """
    with pytest.raises(ValueError):
        egress.guard("https://example.invalid", category="lnkedin")


def test_the_linkedin_counters_are_the_same_object_the_client_exposes():
    """
    linkedin_client.egress_stats is written to directly by
    tests/test_passive_observer_boundary.py. Rebinding it to a fresh dict
    would detach the counters from the chokepoint without failing anything.
    """
    import linkedin_client

    assert linkedin_client.egress_stats is egress.stats_for("linkedin")


def test_refusing_egress_does_not_break_image_generation(no_egress):
    """
    The switch costs a provider, not the feature.

    image_studio tries three remote providers and then falls back to a
    typographic renderer that runs here. With egress refused, the remote
    attempts raise EgressRefused, each is caught by the handler already around
    them, and the local path produces a real file.

    This is the behaviour that makes the master switch usable rather than
    theoretical, and it was found by running it rather than by reading: a first
    probe sampled the counters too early, read zero refusals, and looked like
    the guard had been bypassed.

    What this asserts in process is that generation completes and nothing
    reached the network. It deliberately does not assert a refusal was counted,
    because image_studio skips the whole provider block when it detects a test
    run, so the remote path is never attempted here and there is nothing to
    refuse. The refusal itself was verified against a running server with
    INOX_NO_EGRESS=1 set: image performed=0, refused=1, and a real file at
    /assets/generated. Asserting it here would pass for the wrong reason.
    """
    import image_studio

    manager = image_studio.image_studio_manager
    task_id = manager.start_task({"concept": "a plain grey square", "aspect_ratio": "1:1"})

    for _ in range(60):
        progress = manager.get_progress(task_id)
        if progress.get("status") in ("completed", "failed"):
            break
        time.sleep(0.5)

    assert progress.get("status") == "completed", (
        f"generation did not finish under a refusal: {progress}"
    )
    assert progress.get("result_url"), "no image was produced"
    assert egress.stats_for("image")["performed"] == 0, "something reached the network"
