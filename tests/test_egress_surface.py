"""
Egress Surface Guard
====================
The product's first constraint is that your work stays on this machine, and
for a long time the interface stated something stronger and untrue: the Local
security tab ended with "NOTHING ELSE IN THE STUDIO LEAVES THIS MACHINE" and
the launcher banner read "Zero Cloud Egress".

Neither survives contact with the code. The backend reaches nine hosts across
six modules. egress_guard(), which is a real mechanism that returns a visible
refusal rather than failing silently, is wired into exactly one of them.

The claim and the code had no test holding either to the other, which is why
they drifted apart without anyone noticing, and why one grep across two files
was enough for me to conclude the opposite and write it into the publish
dialog.

So this file pins the surface. It does not decide policy: whether these calls
should be guarded is a product decision and is recorded as an open one. What it
does is make the set of destinations impossible to change silently. Adding a
host, or a module that reaches one, fails here with a message saying which
user-facing sentence now needs rewriting.
"""

import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")

# Every destination the backend is known to reach, and why. Reviewed as of the
# shipping audit. This is a record of what is true, not a list of what is
# allowed: changing it is the point, doing so without noticing is not.
KNOWN_HOSTS = {
    "www.linkedin.com": "session health, profile sync, native scheduling",
    "linkedin.com": "same, without the subdomain",
    "api.openai.com": "a provider key you configured",
    "api.anthropic.com": "a provider key you configured",
    "api.groq.com": "a provider key you configured",
    "generativelanguage.googleapis.com": "a provider key you configured",
    "image.pollinations.ai": "generating an image",
    "api.telegram.org": "the ingress bridge, off unless TELEGRAM_BOT_TOKEN is set",
    "raw.githubusercontent.com": "update checks and the template bundle",
    "github.com": "update checks",
    "ez4cast.s3.eu-west-1.amazonaws.com": "a seeded example asset URL, not fetched at runtime",
}

# Hosts that are not egress: documentation, XML namespaces, the machine itself.
IGNORED = re.compile(
    r"^(127\.0\.0\.1|localhost|0\.0\.0\.0|example\.com|www\.w3\.org|schema\.org"
    r"|nodejs\.org|json-schema\.org)$"
)

URL = re.compile(r"https?://([A-Za-z0-9.-]+)")


def _python_sources(root):
    for base, _dirs, files in os.walk(root):
        if "__pycache__" in base:
            continue
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(base, name)


def _found_hosts():
    hosts = {}
    for path in _python_sources(BACKEND):
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                for host in URL.findall(line):
                    if IGNORED.match(host):
                        continue
                    hosts.setdefault(host, []).append(
                        f"{os.path.relpath(path, REPO_ROOT)}:{number}"
                    )
    return hosts


def _rendered(path):
    """
    A component's source with every comment removed.

    Three guards in this repository have now been written that grep a component
    for a sentence, and then failed on the comment explaining why that sentence
    is forbidden. A comment is not what the reader sees, so it is not what a
    claim check should read.
    """
    if not os.path.exists(path):
        pytest.skip(f"{os.path.basename(path)} is not present in this checkout")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)   # JSX comments
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)         # block comments
    source = re.sub(r"^\s*//[^\n]*$", "", source, flags=re.MULTILINE)  # line comments
    return source


def test_no_destination_appears_without_being_recorded():
    """
    The guard itself. A new host means a new thing leaving the machine.

    If this fails, decide whether the call belongs behind egress_guard(), then
    add it to KNOWN_HOSTS with its reason and update the Local security tab,
    which enumerates these for the reader.
    """
    found = _found_hosts()
    unknown = {h: refs[:3] for h, refs in found.items() if h not in KNOWN_HOSTS}
    assert not unknown, (
        "the backend reaches a host this product has not written down:\n  "
        + "\n  ".join(f"{h} at {', '.join(refs)}" for h, refs in sorted(unknown.items()))
        + "\n\nIf this is intended, add it to KNOWN_HOSTS with its reason and "
        "update the egress list in BrandStudioSurface.tsx, which tells the "
        "reader what reaches out."
    )


def test_the_recorded_destinations_still_exist():
    """
    The other direction, so the list does not rot into fiction.

    A host that no longer appears is one the interface is still telling the
    reader about, which is the same defect pointed the other way.
    """
    found = _found_hosts()
    stale = sorted(set(KNOWN_HOSTS) - set(found))
    assert not stale, (
        "these destinations are recorded but no longer reached, so the claim "
        f"about them is now fiction: {stale}"
    )


def test_the_interface_does_not_claim_nothing_else_leaves():
    """
    The specific false sentence, kept out.

    It read "NOTHING ELSE IN THE STUDIO LEAVES THIS MACHINE" beneath a true
    sentence about provider keys, which is how a reasonable-looking paragraph
    ends up asserting something eleven hosts contradict.
    """
    rendered = _rendered(os.path.join(UI_SRC, "components", "BrandStudioSurface.tsx"))
    assert "NOTHING ELSE IN THE STUDIO LEAVES THIS MACHINE" not in rendered, (
        "the blanket claim is back. Four features reach out; say which."
    )
    assert "YOUR DRAFTS, LEADS AND LINKEDIN SESSION NEVER LEAVE THIS MACHINE" in rendered, (
        "the true and load bearing half of the claim was dropped along with the "
        "false half"
    )


def test_the_publish_dialog_claims_only_what_it_knows():
    """
    A line I wrote on a wrong reading, and the reason this file exists.

    Having grepped two files and found no outbound calls, I concluded the
    backend made none and put "THE STUDIO NEVER LEAVES THIS MACHINE" into the
    dialog. The dialog's real claim is about its own two buttons, which is
    both true and checkable.
    """
    rendered = _rendered(os.path.join(UI_SRC, "components", "PublishDialog.tsx"))

    assert "THE STUDIO NEVER LEAVES THIS MACHINE" not in rendered, (
        "the dialog asserts something about the whole product that is not true "
        "of the whole product"
    )

    # The dialog now has three controls, not two: one of them hands the post to
    # LinkedIn's scheduler and really does send. So the claim narrowed from
    # "neither sends anything" to "neither of those two", and the sentence has
    # to stay scoped to the controls it is true of. A blanket claim here would
    # be the same mistake as the line removed above, one control later.
    assert "NEITHER OF THOSE TWO SENDS ANYTHING" in rendered, (
        "the dialog no longer scopes its claim to the controls it is true of"
    )
    assert "THIS ONE REALLY SENDS" in rendered, (
        "the control that reaches LinkedIn does not say so, which is the same "
        "defect in the opposite direction"
    )


def test_the_guard_covers_what_it_claims_to_cover():
    """
    Records the actual state of egress_guard() rather than asserting a target.

    Whether the unguarded modules should be guarded is an open product
    decision. What must not happen is the guard quietly losing coverage of the
    one module it does protect.
    """
    client = os.path.join(BACKEND, "linkedin_client.py")
    with open(client, encoding="utf-8") as handle:
        source = handle.read()

    assert "def egress_guard" in source, "the egress guard was removed"
    # Every outbound call in this module sits behind a refusal check.
    calls = len(re.findall(r"\brequests\.(?:get|post)\b", source))
    guards = len(re.findall(r"egress_guard\(", source))
    assert guards >= calls, (
        f"linkedin_client makes {calls} outbound calls behind {guards} guard "
        "references, so at least one LinkedIn request can now happen without a "
        "refusal path"
    )
