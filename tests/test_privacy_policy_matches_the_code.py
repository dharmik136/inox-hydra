"""
The privacy policy says what the code does.
============================================

The policy used to live only in `~/.cache/inox-qc2/store/`, outside the
repository, which is why it went a cycle without noticing that the code had
moved under it. It is now `docs/PRIVACY_POLICY.md`, and the figures and
behaviours it asserts are read back out of the code here.

This matters more than an ordinary document test. A privacy policy is a
statement to a creator and to two store reviewers about where other people's
names, headlines and comments are held. Cycle 2 already had to correct this
document once, when it claimed nothing was ever held in the browser while the
extension's own retry queue held up to 200 captures. What was corrected at
2.7.0, each verified against the code before publishing:

  version          2.6.1, now 2.7.0
  held captures    "only while Inox Hydra is not answering". A capture is
                   also held when the database is busy (503) and when the
                   studio refuses an unpaired browser (401/403).
  the database     "a single SQLite database file". One per creator profile.
  Send to LinkedIn acknowledged once "on this installation". Once per
                   creator profile, because the setting lives in that
                   profile's own database.
  waiting count    first written as "the popup and Today both show" it. The
                   popup shows nothing of the kind; only Today does.
"""

import io
import os
import re

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
POLICY = os.path.join(REPO, "docs", "PRIVACY_POLICY.md")
BACKGROUND = os.path.join(REPO, "studio", "extension", "background.js")
POPUP = os.path.join(REPO, "studio", "extension", "popup.js")
TODAY = os.path.join(REPO, "studio", "ui", "src", "components", "TodaySurface.tsx")


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def test_the_policy_is_in_the_repository():
    assert os.path.exists(POLICY), (
        "the policy lives outside the repository again, where no test can read it"
    )


def test_it_names_the_version_the_studio_is():
    version = {}
    exec(_read(os.path.join(REPO, "studio", "__version__.py")), version)
    declared = version.get("__version__") or version.get("VERSION")
    assert declared, "the studio no longer declares a version"
    assert f"version {declared}" in _read(POLICY), (
        f"the studio is {declared} and the policy names a different version"
    )


def test_the_number_of_held_captures_is_the_number_the_extension_holds():
    found = re.search(r"const KEPT_CAPTURES_LIMIT\s*=\s*(\d+)", _read(BACKGROUND))
    assert found, "the extension no longer caps what it holds"
    cap = found.group(1)
    assert f"at most {cap} are" in _read(POLICY), (
        f"the extension holds at most {cap} captures and the policy says otherwise"
    )


def test_it_does_not_claim_captures_are_held_only_when_the_studio_is_down():
    """
    `later` in background.js is the condition: unreachable (0), refused
    (401/403) or a server error (5xx). Saying only "not answering" hides that
    an unpaired browser holds other people's names and comments.
    """
    source = _read(BACKGROUND)
    assert "401" in source and "403" in source, "the keep conditions changed"
    policy = _read(POLICY)
    assert "only while\nInox Hydra is not answering" not in policy
    for condition in ("not running", "busy", "paired"):
        assert condition in policy, (
            f"the policy does not say a capture is held when the studio is {condition!r}"
        )


def test_it_does_not_promise_one_database_when_a_profile_gets_its_own():
    paths = _read(os.path.join(REPO, "studio", "backend", "paths.py"))
    assert "PROFILES_DIRNAME" in paths, "creator profiles are gone; revisit this"
    policy = _read(POLICY)
    assert "a single SQLite database file" not in policy
    assert "each profile is a separate folder" in policy, (
        "the policy does not say that each creator profile has its own database"
    )


def test_the_send_to_linkedin_acknowledgement_is_described_per_profile():
    """
    It is a row in the `settings` table, and `settings` is in the profile's own
    database, so one profile's acknowledgement is not another's.
    """
    app = _read(os.path.join(REPO, "studio", "backend", "app.py"))
    assert 'LINKEDIN_RISK_ACK_KEY = "linkedin_send_risk_ack"' in app
    assert "FROM settings WHERE key = ?" in app, "the acknowledgement is no longer a setting"
    policy = _read(POLICY)
    assert "on this installation" not in policy
    assert "for a given creator profile" in policy


def test_it_does_not_credit_the_popup_with_a_count_it_does_not_show():
    popup = _read(POPUP)
    assert not re.search(r"waiting|keptCaptures", popup, re.I), (
        "the popup now does show what is waiting; the policy may say so again"
    )
    # The count itself is a template expression, so the literal in the source
    # is the tail of the sentence rather than the whole of it.
    assert "WAITING FOR THE STUDIO" in _read(TODAY), (
        "Today no longer shows the waiting count, so the policy must stop saying it does"
    )
    assert "extension's popup and Inox Hydra's Today screen both show" not in _read(POLICY)


def test_no_em_dashes():
    """The repository rule, and the policy is published text."""
    assert "—" not in _read(POLICY)


def test_the_published_page_is_not_carrying_the_owner_instructions():
    """
    The store folder's copy ends with hosting instructions addressed to the
    owner. Those are not part of a policy a creator reads.
    """
    policy = _read(POLICY)
    assert "For the owner" not in policy
    assert "GitHub Pages" not in policy
    assert policy.rstrip().endswith("-->") or "## Contact" in policy

def test_it_carries_exactly_one_last_updated_line():
    """
    The published page went out with two, 2.7.0's and 2.6.1's, one under the
    other: the 2.7.0 header was prepended while the old one was still there.
    Every other test passed, because each looked for a string that was
    present. A policy that states two different dates and two different
    versions in its first two lines is worse than one that is out of date.
    """
    policy = _read(POLICY)
    headers = re.findall(r"^\*\*Last updated:.*$", policy, re.M)
    assert len(headers) == 1, f"the policy has {len(headers)} 'Last updated' lines: {headers}"
    versions = set(re.findall(r"version (\d+\.\d+\.\d+)", policy))
    assert len(versions) == 1, f"the policy names more than one version of itself: {sorted(versions)}"
