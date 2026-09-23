"""
The application can replace itself, and only with something its author signed.
==============================================================================

Auto update was wired off because `tauri-plugin-updater` needs a signing
keypair, and enabling it without one produces an application that fails at
runtime. That is now handled the same way code signing is: the updater block
is written at build time, so a checkout with no keys builds exactly the
application it built before, and the tray says updates are not configured
rather than pretending.

Two keys are involved and confusing them is the usual mistake:

  code signing     proves to Windows who published the installer
  updater signing  proves to the application that an update came from the
                   same author as the build it replaces

Only the second one is what makes an update endpoint safe. Without it, a URL
in a config file is a way to install arbitrary software on the user's machine,
which is why the plugin refuses to run without a public key.

The security boundary these tests defend hardest is a different one. The
studio is a remote origin served over loopback, and capabilities/default.json
deliberately grants that origin nothing. The updater is driven from Rust,
through the tray, so no page in the webview can ask the shell to install
software. Granting `updater:default` to that window would undo it.
"""

import json
import os
import re
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TAURI = os.path.join(REPO_ROOT, "desktop", "src-tauri")
WORKFLOW = os.path.join(REPO_ROOT, ".github", "workflows", "desktop.yml")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def lib_rs():
    return _read(TAURI, "src", "lib.rs")


@pytest.fixture(scope="module")
def cargo():
    return _read(TAURI, "Cargo.toml")


@pytest.fixture(scope="module")
def workflow():
    return _read(WORKFLOW)


@pytest.fixture(scope="module")
def capabilities():
    return json.loads(_read(TAURI, "capabilities", "default.json"))


# ---------------------------------------------------------------------------
# The boundary. These are the ones worth breaking a build over.
# ---------------------------------------------------------------------------

def test_the_webview_origin_cannot_reach_the_updater(capabilities):
    """
    The window navigates to a loopback origin the shell does not author. If
    that origin held an updater permission, any page the webview ever loads
    could ask the shell to download and install software. The check is driven
    from Rust precisely so this list does not have to grow.
    """
    granted = " ".join(capabilities["permissions"])
    assert "updater" not in granted, (
        f"the updater is exposed to the webview origin through {granted}, so a "
        f"page rather than the user can trigger an install"
    )


def test_rust_side_invocation_needs_no_capability(lib_rs):
    """
    The corollary worth stating: the check runs through UpdaterExt on the app
    handle, not through an invoke from JavaScript. That is what allows the
    permission list above to stay empty.
    """
    assert "UpdaterExt" in lib_rs
    assert "app.updater()" in lib_rs


def test_the_update_endpoint_is_https(workflow):
    """
    The plugin refuses plain http with InsecureTransportProtocol, but the
    failure would arrive at the user as a broken update rather than as a
    configuration mistake, so it is caught here.
    """
    endpoints = re.findall(r'endpoints\s*=\s*@\("([^"]+)"\)', workflow)
    assert endpoints, "no update endpoint is configured at all"
    for url in endpoints:
        assert url.startswith("https://"), f"update endpoint is not https: {url}"


def test_a_public_key_alone_does_not_enable_updates(workflow):
    """
    A build with a public key and no private key produces an application that
    checks for updates it can never verify, against a manifest nothing signed.
    Both halves, or neither.
    """
    assert "TAURI_UPDATER_PUBKEY -and [bool]$env:TAURI_SIGNING_PRIVATE_KEY" in workflow, (
        "the updater is enabled on one key rather than both"
    )


def test_an_unsigned_artifact_is_never_published_as_an_update(workflow):
    """
    Tauri writes the .sig only when it actually signed something. Publishing a
    manifest without it means every client downloads an update it then
    refuses, which breaks updating for people who already installed.
    """
    assert "Refusing to publish an update the application cannot verify" in workflow
    assert "Test-Path $sigPath" in workflow


# ---------------------------------------------------------------------------
# A build with no keys is still a working build
# ---------------------------------------------------------------------------

def test_the_base_config_names_no_public_key():
    """
    tauri.conf.json is what a local build and a fork use. A pubkey committed
    there would either be a placeholder that fails at runtime, which is the
    reason this feature was off, or someone's real key in a public repo.
    """
    config = json.loads(_read(TAURI, "tauri.conf.json"))
    assert "updater" not in json.dumps(config.get("plugins", {})), (
        "the committed config configures an updater, so a checkout without "
        "keys builds an application that fails at runtime"
    )


def test_registration_failure_does_not_stop_the_application(lib_rs):
    """
    Without plugins.updater the plugin cannot register. That must cost the
    update feature and nothing else.
    """
    assert "if let Err(error) = handle.plugin(tauri_plugin_updater" in lib_rs, (
        "the plugin is registered with ? or unwrap, so a build without keys "
        "fails to start instead of starting without updates"
    )


def test_an_unconfigured_build_says_so(lib_rs):
    """
    Silence would read as "no update available", which is a different claim
    and one this build cannot make.
    """
    assert '"Updates are not configured"' in lib_rs


# ---------------------------------------------------------------------------
# The manifest the client actually reads
# ---------------------------------------------------------------------------

def test_the_platform_key_is_the_one_the_client_looks_up(workflow):
    """
    A wrong key produces TargetNotFound on every machine, which the user reads
    as "there is no update" rather than as a broken manifest. Nothing else
    fails, which is what makes it worth a test.
    """
    assert '"windows-x86_64"' in workflow, (
        "the manifest does not carry the platform key a Windows x64 client "
        "looks itself up by"
    )


def test_the_manifest_carries_a_signature_and_a_url(workflow):
    section = workflow[workflow.index("Build The Update Manifest"):]
    section = section[:section.index("Upload The Installer")]
    for field in ("version", "pub_date", "platforms", "signature", "url"):
        assert field in section, f"the update manifest has no {field}"


def test_the_two_manifests_do_not_collide():
    """
    studio/backend/updates.py already reads release/latest.json for its opt-in
    check, with a different schema entirely. The Tauri manifest is a release
    asset under another name, and the two must not be mistaken for each other
    by anyone maintaining this.
    """
    workflow = _read(WORKFLOW)
    assert "latest-desktop.json" in workflow

    backend_manifest = json.loads(_read(REPO_ROOT, "release", "latest.json"))
    assert "platforms" not in backend_manifest, (
        "release/latest.json has grown a Tauri updater shape; the backend "
        "check and the desktop updater are separate things"
    )


def test_the_version_comes_from_the_single_source(workflow):
    """
    A manifest announcing a version the artifact was not signed for is
    rejected by the client as SignedVersionMismatch, so it has to come from
    the same place the build does.
    """
    assert "studio/__version__.py" in workflow, (
        "the manifest version is written by hand rather than read from the "
        "one file that declares it"
    )


# ---------------------------------------------------------------------------
# The user, and consent
# ---------------------------------------------------------------------------

def test_the_check_is_something_the_user_asks_for(lib_rs):
    """
    This studio runs a scheduler and holds someone's professional
    correspondence. updates.py is opt-in for the same reason. An update that
    installed itself unannounced would be the one moment the product took an
    action on its own.
    """
    assert '"update"' in lib_rs and "Check for Updates" in lib_rs, (
        "there is no way for the user to ask for an update check"
    )


def test_the_application_does_not_restart_itself(lib_rs):
    """
    Restarting is the install. Doing it on its own would take the window away
    mid sentence, from someone who may be mid draft.
    """
    assert "app.restart()" not in lib_rs, (
        "the shell restarts itself after installing, which can discard what "
        "the user was in the middle of writing"
    )
    assert "Restart to use it" in lib_rs


def test_every_outcome_is_reported(lib_rs):
    """
    Four things can happen and the user is told which. A check that silently
    does nothing is worse than no check, because it looks the same as being up
    to date.
    """
    for outcome in (
        "You are on the latest version",
        "Update installed. Restart to use it",
        "Could not reach the update server",
        "Updates are not configured",
    ):
        assert outcome in lib_rs, f"nothing reports: {outcome}"


def test_the_updater_dependency_is_declared(cargo):
    assert "tauri-plugin-updater" in cargo
