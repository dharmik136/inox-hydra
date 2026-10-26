"""
The coverage meter keeps an address only as the words of LinkedIn's API.
========================================================================

Review finding S1 of cycle 4, track 1. The meter blanked a path segment only
when it looked like an identifier or followed one of 24 listed collections,
compared with case, so a member's plain-word vanity after any other collection
(/identity/miniProfiles/johndoe), or after a case variant (/identity/Profiles/
JohnDoe), was kept by the page, accepted by the studio, stored for seven days
and listed in the side panel. The query-name slot was not checked at all.

It now fails closed on both sides: a segment is kept only if it is a word from
a fixed list of LinkedIn's API path words, compared without regard to case
and written as listed; everything else becomes "_id_", and so does the
segment after a collection that takes an identifier. The query-name slot holds
a GraphQL query name of LinkedIn's one shape or "other". The page's list and
the studio's are held equal here.

Every name here is invented or a public example the review used.

Strict Invariants:
- Zero em-dashes.
"""

import os
import re
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT = os.path.join(REPO_ROOT, "studio", "extension")
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

BASE = "https://www.linkedin.com/voyager/api"
# The review's probe addresses (scratchpad/t1review/probe_page_keys.js) and the coordinator's shapes.
PAGE_KEYS = [
    (BASE + "/identity/profiles/johndoe/profileView", "/voyager/api/identity/profiles/_id_/profileView"),
    (BASE + "/identity/profiles/john.doe/profileView", "/voyager/api/identity/profiles/_id_/profileView"),
    (BASE + "/identity/profiles/jos%C3%A9-x/profileView", "/voyager/api/identity/profiles/_id_/profileView"),
    (BASE + "/identity/profiles/%E0%A4%85%E0%A4%AE%E0%A4%BF%E0%A4%A4/", "/voyager/api/identity/profiles/_id_"),
    (BASE + "/identity/Profiles/JohnDoe/profileView", "/voyager/api/identity/profiles/_id_/profileView"),
    (BASE + "/identity/miniProfiles/johndoe", "/voyager/api/identity/miniProfiles/_id_"),
    (BASE + "/identity/publicContactInfo/satyanadella", "/voyager/api/identity/publicContactInfo/_id_"),
    (BASE + "/feed/followerInfo/jdoe123", "/voyager/api/feed/followerInfo/_id_"),
    (BASE + "/identity/dash/memberBadges/ACoAABcdEfGhIjKlMnOpQ", "/voyager/api/identity/dash/memberBadges/_id_"),
    (BASE + "/feed/updates/urn:li:activity:7123456789012345678", "/voyager/api/feed/updates/_id_"),
    (BASE + "/feed/updatesV2/urn%3Ali%3Aactivity%3A7123456789012345678", "/voyager/api/feed/updatesV2/_id_"),
    (BASE + "/graphql?variables=(vanityName:john-doe)&queryId=voyagerIdentityDashProfiles.b5c27c04968c409f",
     "/voyager/api/graphql voyagerIdentityDashProfiles"),
    (BASE + "/graphql?queryId=john-doe-12345.abc&variables=(x:1)", "/voyager/api/graphql other"),
    (BASE + "/graphql?queryId=urn:li:fsd_profile:ACoAAB.abc", "/voyager/api/graphql other"),
    (BASE + "/graphql?queryId=urn%3Ali%3Afsd_profile%3AACoAAB", "/voyager/api/graphql other"),
    (BASE + "/graphql?queryId=urnlifsd_profileACoAAB.abc", "/voyager/api/graphql other"),
    (BASE + "/identity/dash/profiles?q=memberIdentity&memberIdentity=johndoe", "/voyager/api/identity/dash/profiles"),
    (BASE + "/messaging/conversations/2-ZmFhNTM2/events", "/voyager/api/messaging/conversations/_id_/events"),
    (BASE + "/entities/companies/microsoft", "/voyager/api/entities/companies/_id_"),
    (BASE + "/voyagerIdentityDashProfiles/johndoe", "/voyager/api/voyagerIdentityDashProfiles/_id_"),
    (BASE + "/feed/hashtags/johndoe", "/voyager/api/feed/hashtags/_id_"),
    (BASE + "/identity/profiles/comments/profileView", "/voyager/api/identity/profiles/_id_/profileView"),
]

# Keys an extension that did not clean, or cleaned by the old denylist, could send.
REFUSED_KEYS = [
    "/voyager/api/identity/miniProfiles/johndoe",
    "/voyager/api/identity/publicContactInfo/satyanadella",
    "/voyager/api/feed/followerInfo/jdoe123",
    "/voyager/api/identity/Profiles/JohnDoe/profileView",
    "/voyager/api/identity/profiles/_id_/JohnDoe",
    "/voyager/api/identity/dash/memberBadges/ACoAABcdEfGhIjKlMnOpQ",
    "/voyager/api/graphql urnlifsd_profileACoAAB",
    "/voyager/api/graphql john-doe-12345",
    "/voyager/api/graphql voyagerIdentityDashProfiles.b5c27c04",
    "/voyager/api/identity/profiles/comments/profileView",
    "/voyager/api/feed/updates?count=10",
    "/not/voyager/at/all",
]
ACCEPTED_KEYS = [key for _, key in PAGE_KEYS]


@pytest.fixture(scope="module")
def pages():
    pytest.importorskip("playwright.sync_api")
    from qc_f3_pages import Pages
    p = Pages()
    yield p
    p.close()


def test_the_page_keeps_an_address_only_as_the_words_of_linkedins_api(pages):
    from qc_f3_pages import page_html
    page = pages.open("/feed/", page_html("<main></main>"))
    for url, expected in PAGE_KEYS:
        assert page.evaluate("(u) => voyagerCallKey(u).key", url) == expected, url


def test_the_studio_keeps_only_a_key_in_that_shape():
    import onboarding
    kept = onboarding._clean_voyager_calls({key: 1 for key in REFUSED_KEYS + ACCEPTED_KEYS})
    assert sorted(kept) == sorted(set(ACCEPTED_KEYS)), sorted(set(kept) - set(ACCEPTED_KEYS))


def _js_list(source, name):
    found = re.search(name + r" = \[([^\]]*)\]", source)
    assert found, f"content.js no longer declares {name}"
    return re.findall(r'"([^"]+)"', found.group(1))


def test_the_page_and_the_studio_hold_one_list():
    """Two copies, one in each language, held equal so they cannot drift apart."""
    import onboarding
    with open(os.path.join(EXT, "content.js"), encoding="utf-8") as handle:
        content = handle.read()
    assert _js_list(content, "const VOYAGER_PATH_WORDS") == list(onboarding.VOYAGER_PATH_WORDS)
    assert _js_list(content, "const VOYAGER_ID_AFTER") == list(onboarding.VOYAGER_ID_AFTER)
    query = re.search(r"const VOYAGER_QUERY_NAME = /(.+)/;", content)
    assert query and query.group(1) == onboarding.VOYAGER_QUERY_NAME.pattern
