"""
How much of this backend the interface can actually reach, written down.
=======================================================================

A handoff reported "77 of 146 endpoints unreachable, down from 84". The real
figure was 79 of 145. Nobody had misled anyone: the number was counted by hand
once, quoted afterwards, and drifted because nothing measured it. A number that
appears in a handoff and in no test is a number that will be wrong by the time
somebody acts on it.

This is not a ratchet, and the distinction is the whole design.

A ratchet asserts a count does not grow, which is right for hex literals and
inline styles because those should only ever decrease. Reachability is
different: adding an endpoint before its surface exists is ordinary, correct
work, and a ceiling would fail the build for doing it. The existing ratchets in
this repository also sit at zero headroom, so adding another of that shape
would inherit a problem rather than solve one.

What this does instead is require the recorded numbers to match reality. Any
drift fails, in either direction, and the fix is to update the constants below
on purpose while saying what changed. Surfacing an endpoint is then a visible
improvement in a diff rather than an invisible one, and adding an unsurfaced
endpoint is a deliberate entry rather than a silent slide.

The counts are asserted exactly rather than as bounds, because "at most 79"
would quietly permit the one thing being guarded against: a route added,
unreached, and unremarked.

What is counted, and why it differs from the audit figure
--------------------------------------------------------
Distinct API paths, not route decorators. app.py has 146 decorators but fewer
paths: two handlers carry stacked aliases, and several paths serve more than
one method, so `GET /api/posts/{id}` and `DELETE /api/posts/{id}` are two
decorators on one path. An audit counting decorators reported 145 API routes
where this counts 137 paths, and neither is wrong.

Paths are the right unit here because reachability is a question about whether
the interface names an address at all. A path it never mentions is definitively
out of reach. Whether every method on a reachable path is exercised is a finer
question this does not attempt, and saying so is better than implying a
precision it does not have.
"""

import os
import re
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(REPO_ROOT, "studio", "backend", "app.py")
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")

# ---------------------------------------------------------------------------
# The recorded state. Update deliberately, with the reason in the commit.
#
# Measured 27 Sep 2026. The interface is the React source in studio/ui/src,
# which is the only interface now that the vanilla page is retired.
#
# Reached moved 62 -> 67 in one change, and only one of those five is new work.
# Surfacing /api/leads/*/dm-script accounts for one. The other four,
# /api/analytics/export, /api/analytics/kpis, /api/analytics/overview and
# /api/v1/intelligence/templates, were being called by the interface the whole
# time and counted as unreachable, because _normalise never stripped the query
# string those four calls carry. So this ledger was understating its own subject
# for as long as it has existed, in the direction that makes the product look
# worse than it is, which is the less dangerous direction but still wrong.
# ---------------------------------------------------------------------------
#
# Then 138 -> 150 paths, with onboarding. Twelve new paths: five the Setup
# screen calls, seven only the extension calls (heartbeat, identity/me,
# identity/observe, self/posts/ingest, self/outbound/ingest, the two import
# routes). Those seven are unreachable by this file's definition, which counts
# the interface, and that is the right answer rather than a gap: they are the
# extension's to call. In the same change the prefix rule was removed (see
# measured() below), which takes back one route it had been crediting falsely.
# ---------------------------------------------------------------------------
#
# Then 150 -> 151, with universal search. One new path, /api/v1/search, and
# the palette calls it, so reached moves with the total and the unreachable
# count stays where it was.
#
# Then 151 -> 153, with the lead review. /api/v1/leads/review and its /remove,
# both called by the Leads stream's review panel, so again reached moves with
# the total.
#
# Then 153 -> 154, with capture health. /api/v1/bridge/capture is written by
# the extension only (the Setup screen reads the result through the onboarding
# state), so it joins the unreachable column by design, like the other
# extension routes.
#
# Then 154 -> 156, with Today and per-post readings. /api/v1/today is the
# Today screen's, so it is reached; /api/v1/self/posts/analytics is written by
# the extension from a post's analytics page, so it is unreachable by design.
#
# Then 156 -> 158, with Posts and Outbound: /api/v1/insights/posts and
# /api/v1/insights/outbound, each called by its own screen.
#
# Then 158 -> 160, with Patterns: /api/v1/insights/patterns and
# /api/v1/insights/cadence, both called by the Patterns screen.
#
# Then 160 -> 163, with Voyager self-healing and extension health:
# /api/v1/bridge/voyager-ingest and /api/v1/bridge/schema-drift are written by
# the extension only; /api/v1/extension/health is read by the extension sidepanel,
# so all three join the unreachable column by design.
#
# Then 163 -> 166, with Multi-Tenant Creator Profiles:
# /api/v1/accounts, /api/v1/accounts/switch, and /api/v1/accounts/*, all three
# Then 163 -> 166, with Multi-Tenant Creator Profiles:
# /api/v1/accounts, /api/v1/accounts/switch, and /api/v1/accounts/*, all three
# called by the AccountSwitcher in StudioRail and NavigationTray, so reached
# moves with the total and unreachable count stays at 84.
# ---------------------------------------------------------------------------
# Then 166 -> 167, with CP1 Contrast Engine:
# /api/v1/insights/contrasts, computing binary feature contrasts with n>=8 per arm.
#
# Then 167 -> 168, with CP4 Topic-to-Lead Attribution and CP1 Contrast Surfacing:
# /api/v1/insights/attribution added (+1 declared path).
# Both /api/v1/insights/contrasts and /api/v1/insights/attribution are now surfaced
# in PatternsSurface and api.ts (+2 reached, -1 unreachable).
# Reached moves 82 -> 84, unreachable drops 85 -> 84, total moves 167 -> 168.
# ---------------------------------------------------------------------------
# Then 168 -> 169, with CP2 Evidence-Backed Composer Panel and CP3 Retrieval:
# /api/v1/insights/evidence added (+1 declared path, surfaced in EvidencePanel and api.ts).
# Reached moves 84 -> 85, unreachable stays at 84, total moves 168 -> 169.
# ---------------------------------------------------------------------------
# Then 169 -> 170, with Autonomous History Sync Orchestrator:
# /api/v1/self/sync-all added (+1 declared path, surfaced in OnboardingSurface,
# TodaySurface, and api.ts).
# Reached moves 85 -> 86, unreachable stays at 84, total moves 169 -> 170.
# ---------------------------------------------------------------------------
# Then 170 -> 171, with Real-Time Activity Stream and Ingestion Dashboard:
# /api/v1/self/activity-stream added (+1 declared path, surfaced in
# ActivitySurface and api.ts).
# Reached moves 86 -> 87, unreachable stays at 84, total moves 170 -> 171.
# ---------------------------------------------------------------------------
# Then 171 -> 172, with AI Async Streaming Completion:
# /api/ai/stream added (+1 declared path, surfaced in api.ts streamAiCompletion).
# Reached moves 87 -> 88, unreachable stays at 84, total moves 171 -> 172.
# ---------------------------------------------------------------------------
# Then 172 -> 173, with the offline licence: /api/v1/licence added (GET, POST
# and DELETE on one declared path, surfaced in LicenceWorkspace and api.ts).
# Reached moves 88 -> 89, unreachable stays at 84, total moves 172 -> 173.
# ---------------------------------------------------------------------------
# Then 173 -> 178, with the LinkedIn archive import: /api/v1/archive,
# /api/v1/archive/requested, /api/v1/archive/upload, /api/v1/archive/preview
# and /api/v1/archive/import added, surfaced in ArchiveImport and api.ts.
# Reached moves 89 -> 94, unreachable stays at 84, total moves 173 -> 178.
# ---------------------------------------------------------------------------
# Then 178 -> 179: /api/v1/archive/discard, so "Not now" deletes an uploaded
# archive at once (surfaced in ArchiveImport and api.ts).
# Reached moves 94 -> 95, unreachable stays at 84, total moves 178 -> 179.
# ---------------------------------------------------------------------------
# Then /api/queue/status gains a caller: the interface asks it, as the
# cheapest answer the studio gives, to learn the studio is back after losing
# it (pingStudio in api.ts). No route added.
# Reached moves 95 -> 96, unreachable drops 84 -> 83, total stays at 179.
# ---------------------------------------------------------------------------
# Then /api/v1/today/demo-cleanup-notice/dismiss (batch F8), Today's Dismiss
# on the note that says what the demo cleanup removed (TodaySurface, api.ts).
# Reached moves 98 -> 99, unreachable stays at 83, total moves 181 -> 182.
# ---------------------------------------------------------------------------
# Then 182 -> 152 (cycle 2, batch R2, owner decision D1): thirty paths no
# interface, extension, CLI or desktop shell calls were removed because they
# bypassed a guard the interface enforces, were broken, or duplicated another
# route. /api/ai/stream was one, and was counted reached only because an
# unused helper in api.ts named it; the client's strings now count only when a
# component imports the function that carries them [BE-22]. Telegram ingress
# and the G-Stack backlog stay declared but answer 404 outside dev mode.
# Reached moves 99 -> 98, unreachable 83 -> 54, total 182 -> 152.
# ---------------------------------------------------------------------------
# And (batch R4), the Storage and privacy panel in Brand Studio:
# /api/v1/storage, /api/v1/storage/rules, /api/v1/storage/preview/*,
# /api/v1/storage/run/*, /api/v1/storage/review, /api/v1/storage/review/forget,
# /api/v1/storage/review/keep, /api/v1/storage/backups/scrub and
# /api/v1/storage/compact, all surfaced in StoragePrivacyWorkspace and api.ts.
# Reached moves 99 -> 108, unreachable stays at 83, total moves 182 -> 191.
# ---------------------------------------------------------------------------
# Then /api/v1/support/restore (batch R5, D-6), Brand Studio's Restore on
# each listed backup (BrandStudioSurface, api.ts restoreBackup).
# Reached moves 99 -> 100, unreachable stays at 83, total moves 182 -> 183.
# ---------------------------------------------------------------------------
# Then batch R6 (cycle 2), each called by the interface:
#   POST /api/posts/{id}/move-to-next-slot (Today, a missed post), BE-02;
#   POST /api/queue/slots and PUT/DELETE /api/queue/slots/{id} (the Queue's
#   Change slots), D-4; POST /api/v1/intelligence/packs/engineering (the
#   Swipe File), D-8; GET /api/v1/posts/{id}/linkedin-send (Publish), BE-09.
# Removed: POST /api/v1/scheduler/native/stage, the unguarded duplicate
# send, which nothing called (BE-08).
# Reached moves 99 -> 104, unreachable drops 83 -> 82, total moves 182 -> 186.
# ---------------------------------------------------------------------------
# Then /api/image/provider (batch R7, GET and POST on one path): the image
# provider setting in the Prompt tab (ImageProviderSettings, api.ts).
# Reached moves 99 -> 100, unreachable stays at 83, total moves 182 -> 183.
# ---------------------------------------------------------------------------
# Reconciled at integration (cycle 2), each batch from the 182 / 99 / 83 base,
# to 167 paths, 114 reached and 53 unreachable:
#   R2: 30 paths removed (reached -1, unreachable -29).
#   R4: 9 Storage and privacy paths added, all reached (+9).
#   R5: /api/v1/support/restore added, reached (+1).
#   R6: 5 paths added and reached, native/stage removed (unreachable -1).
#   R7: /api/image/provider added, reached (+1).
# ---------------------------------------------------------------------------
# Cycle 3, batch T3 (one path in): /api/v1/extension/captures/waiting added.
# It answers how many captures the extension is holding for a studio that was
# busy, which nothing in the product could say. It is read by the extension's
# side panel, not by the studio interface, so it joins the unreachable column
# by design, beside /api/v1/extension/health. Total 167 -> 168, reached stays
# at 114, unreachable 53 -> 54. The Today screen reads it in a later batch.
# ---------------------------------------------------------------------------
# Cycle 3, batch T8 (docs honesty): /api/v1/linkedin/risk-ack added. It records
# a studio installation's one-time acknowledgement of the Send to LinkedIn
# account risk, and the Publish dialog calls it, so it is reached. Total
# 168 -> 169, reached 114 -> 115, unreachable stays at 54.
# ---------------------------------------------------------------------------
# Cycle 3, batch T5 (Today, Queue, Composer feeding): two paths added, both
# reached. /api/queue/due is the one due list with the scheduler's missed
# note, which the Queue reads instead of the generic posts endpoint.
# /api/v1/storage/backups answers the backup schedule alone, which Today
# reads to say when it has gone stale: the whole storage overview costs
# 578 ms on a three year install against 1.7 ms for this.
# T3's /api/v1/extension/captures/waiting is now read by Today, which is the
# batch T3 said would read it, so it leaves the unreachable column.
# Total 168 -> 170, reached 114 -> 117, unreachable 54 -> 53.
# ---------------------------------------------------------------------------
# Cycle 3, batch T6 (sections B): /api/v1/insights/posts/{activity_urn} added,
# one post's whole text and figures, which the Posts table opens into rather
# than rendering every post's text inline. Read by PostDetail.tsx, so it is
# reached. Total 168 -> 169, reached 114 -> 115, unreachable stays at 54.
# ---------------------------------------------------------------------------
# Cycle 3, batch T7 (sections C): the Swipe File is gone. It drew the same
# viral_templates rows as the Composer’s hook rail through a second endpoint,
# and nothing could put a specimen in or take one out, so its two client
# functions went with it: GET /api/inspirations and POST
# /api/v1/intelligence/packs/engineering now have no caller in the interface.
# Neither route was removed. The first still serves Ctrl+K’s hook form search
# through /api/v1/search, and the second is how the opt-in pack is added, which
# is a control the hook rail should carry (MAKING.md D3) and does not yet, so
# it sits in the unreachable column until it does, where it is visible.
# Total stays at 168, reached 114 -> 112, unreachable 54 -> 56.
# ---------------------------------------------------------------------------
# All of cycle 3 applied. The counts below are what the running application
# declares and what the interface reaches, measured, not added up by hand.
# The engineering pack route is reached again: T7 removed the Swipe File and
# its client function with it, and the hook rail is that function's caller
# now, so the merge restored it. The pack has a way out and no way in until
# its 36 first-person claims are rewritten, which is a decision, not a gap.
# ---------------------------------------------------------------------------
# Then 172 -> 174 and 118 -> 125, with Health (cycle 4, track 4). Two new
# paths, both called by the Health screen: /api/v1/bridge/readers, each
# reader's runs this week as counts, which capture_health read with LIMIT 1
# and dropped, and /api/v1/bridge/readers/{extractor}, one reader's runs and
# day rows one level down. Five existing paths gained their first caller in
# the interface: /api/v1/extension/health (whose drift events only the
# extension's side panel had shown), /api/v1/schema/status,
# /api/v1/updates/status, /api/v1/updates/preference and /api/v1/updates/check.
# The new paths are not under /api/v1/health on purpose: the containment rule
# below would have credited the liveness route /api/v1/health, which nothing
# in the interface calls.
# ---------------------------------------------------------------------------
# Then 174 -> 177 and 125 -> 128, with Replies (cycle 4, track 4). Three new
# paths, all called by the Replies screen: /api/v1/replies, the comments on
# your posts waiting on a reply, and /api/v1/replies/mark and
# /api/v1/replies/unmark, the creator's own Answered mark.
# ---------------------------------------------------------------------------
# Then 177 -> 181 and 128 -> 132, with Audience (cycle 4, track 4). Four new
# paths, all called by the interface: /api/v1/audience, the first view;
# /api/v1/audience/connections, the searchable list; /api/v1/audience/counts,
# the funnel and company counts one level down; and
# /api/v1/audience/people/{lead_id}, the facts the Leads dossier draws.
# ---------------------------------------------------------------------------
# Cycle 4, track 5: 172 -> 173 paths, unreachable 54 -> 55. The one new path is
# GET /api/analytics/post-field-sightings: how long each figure the post
# analytics reader added this cycle has gone unread, which is where such a
# label shows now that an absent one is not drift (the owner, 2026-10-26).
# Track 4's Health section is its caller once that section is built; until
# then it sits in the unreachable column, where it is visible.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Cycle 4, track 7, batch 0 (honesty prerequisites): GET /api/inspirations is
# retired. It served viral_templates under the retired Swipe File's name with
# counts set to None at render time, nothing in the interface called it, and
# it was the one way a library of other people's posts could have come back
# (ideas report, "Other people's posts stay out of the database"). It sat in
# the unreachable column. Total 172 -> 171, reached stays 118, unreachable
# 54 -> 53.
# ---------------------------------------------------------------------------
# Cycle 4, track 7, batches 4 and 6 (the section and its asks): sixteen paths
# under /api/v1/record, the day's batch and earlier days, Suggest new, the
# marks and Unhide all, More of this, Draft from this, Kept, What the studio
# knows, the asks, the Setup fields, the settings and the monthly note. Every
# one is called by the section's screen except the monthly note, which the
# evaluation batch's "Did these help" calls. Total 171 -> 187, reached
# 118 -> 133, unreachable 53 -> 54.
# ---------------------------------------------------------------------------
# Cycle 4, track 7, batch 7 (the model stage): POST /api/v1/record/model,
# today's one call to the creator's own model on their first open of the
# section, and GET /api/v1/record/model/preview, exactly what it would send.
# Both reached by the section. Total 187 -> 189, reached 133 -> 135.
# ---------------------------------------------------------------------------
# Cycle 4, track 7, batch 8 (the evaluation): GET /api/v1/record/evaluation,
# "Did these help?", added and reached; the monthly note, recorded above as
# unreachable until this batch, is now saved from that screen. Total
# 189 -> 190, reached 135 -> 137, unreachable 54 -> 53.
# ---------------------------------------------------------------------------
# Cycle 4, track 7, batch 9 (the signed library): the unsigned sync's three
# routes are gone with intelligence_sync.py (/api/v1/intelligence/status,
# /bundle/export and /bundle/import, none reached by the interface), and the
# library's two are added and reached from What the studio knows
# (/api/v1/record/library/fetch and /import). Total 190 -> 189, reached
# 137 -> 139, unreachable 53 -> 50.
# ---------------------------------------------------------------------------
# Integration (t5 then t7): 172 + 1 + 17 = 190 paths, reached 118 + 21 = 139,
# unreachable 54 + 1 - 4 = 51.
# ---------------------------------------------------------------------------
# Cycle 4, track 3, batch 1: decision 7 retired the "Topic to Qualified Lead
# Attribution" table on Patterns, and with it the interface's only caller of
# /api/v1/insights/attribution. The route stays for the API, where AUDIENCE-12
# still holds its people counts; topics are compared as forms under
# /api/v1/insights/contrasts now. Total stays at 172, reached 118 -> 117,
# unreachable 54 -> 55.
# ---------------------------------------------------------------------------
# The same batch took the post table off Analytics (a second copy of the Posts
# screen's). GET /api/analytics/best is added for the aside, which reads the
# engine's best and weakest without a page of rows (+1 declared, reached).
# The table's per-row attribution, /api/v1/analytics/posts/*/leads, has no
# caller in the interface now; it stays for the API and its index tests.
# /api/analytics/posts was already counted unreached: its client wrote the
# path in a template literal this file's pattern does not read.
# Total 172 -> 173, reached stays 117, unreachable 55 -> 56.
# ---------------------------------------------------------------------------
# Review round 2 of track 3 (B2 b): GET /api/v1/posts/published-not-seen is
# added, and Posts reads it, for the posts marked published in the studio that
# no list held once Analytics' table moved. Total 173 -> 174, reached 117 ->
# 118, unreachable stays 56.
# ---------------------------------------------------------------------------
# Integration of tracks 5, 7 and 3, measured on the merged tree: 192 paths,
# 139 reached by the interface, 53 unreachable.
# ---------------------------------------------------------------------------
# Cycle 4, track 6: seven paths added, every one with its surface. The phone's
# Telegram bot under Local security (/api/v1/ingress/settings), and LinkedIn's
# analytics export in Setup (/api/v1/analytics-export and its requested,
# upload, preview, import and discard). Total 172 -> 179, reached 118 -> 125,
# unreachable unchanged at 54. Then, in its review round, Today's Not now for
# a post the phone asked for (/api/v1/desk-requests/{id}/dismiss): total 180,
# reached 126, unreachable still 54; and the Local security panel's
# Understood for a session removed from a profile beyond the first
# (/api/auth/session-removed/dismiss): total 181, reached 127.
# ---------------------------------------------------------------------------
# Integration of tracks 5, 7, 3 and 6, measured on the merged tree: 201
# paths, 148 reached by the interface, 53 unreachable.
# ---------------------------------------------------------------------------
# Track 4 merged with the integration of tracks 5, 7, 3 and 6, measured on the
# merged tree: 210 paths, 162 reached, 48 unreachable (track 4's nine paths and
# five newly reached on top of integration's 201, 148 and 53). Then Health
# draws track 5's /api/analytics/post-field-sightings: reached 163, 47
# unreachable.
# ---------------------------------------------------------------------------
TOTAL_API_PATHS = 210
REACHED_BY_INTERFACE = 163
UNREACHABLE = 47

ROUTER_DIR = os.path.join(REPO_ROOT, "studio", "backend", "routers")

ROUTE_DECORATOR = re.compile(
    r"^\s*@(?:app|router)\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)[\"']", re.MULTILINE
)


def _normalise(path):
    """
    Reduces a path to something comparable across the two languages.

    FastAPI writes `/api/v1/mcp/servers/{name}/enabled`; the interface builds
    `/api/v1/mcp/servers/${encodeURIComponent(name)}/enabled`. Both become
    `/api/v1/mcp/servers/*/enabled`, so a parameterised route is not counted
    as unreachable merely because the two spell the hole differently.

    The query string goes too, and this was a real miss rather than a
    refinement. The containment check below was written on the assumption that a
    called path "may carry a query string", but nothing ever removed one, so
    `/api/leads/*/dm-script?*` failed all three comparisons against the route
    `/api/leads/*/dm-script`. A freshly surfaced endpoint therefore stayed in
    the unreachable column, which is the one outcome this file exists to
    prevent: a real improvement measured as no change at all.
    """
    path = path.split("?", 1)[0]
    path = re.sub(r"\$\{[^}]*\}", "*", path)
    path = re.sub(r"\{[^}]*\}", "*", path)
    return path.rstrip("/") or "/"


def _declared_routes():
    files_to_scan = [APP]
    if os.path.isdir(ROUTER_DIR):
        for name in os.listdir(ROUTER_DIR):
            if name.endswith(".py"):
                files_to_scan.append(os.path.join(ROUTER_DIR, name))

    routes = set()
    for target in files_to_scan:
        with open(target, encoding="utf-8") as handle:
            source = handle.read()
        for _method, path in ROUTE_DECORATOR.findall(source):
            if path.startswith("/api"):
                routes.add(_normalise(path))
    return routes


API_CLIENT = os.path.join("lib", "api.ts")
_PATH_LITERAL = re.compile(r"[\"'`](/api/[^\"'`\s]*)[\"'`]")
_TOP_LEVEL = re.compile(r"^(?:export\s+)?(?:async\s+)?(?:function|const|let|class|interface|type)\s+(\w+)", re.MULTILINE)


def _client_chunks(text):
    """(name, exported, body) for each top-level declaration in the API client."""
    starts = list(_TOP_LEVEL.finditer(text))
    chunks = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        chunks.append((match.group(1), match.group(0).startswith("export"), text[match.start():end]))
    return chunks


def _interface_paths(ui_src=UI_SRC):
    """
    Every /api path the interface names, from any file under studio/ui/src.

    Except that a path written in the API client counts only when the exported
    function that carries it is imported by something else in the interface.
    Crediting any string in api.ts counted /api/ai/stream as reached for as long
    as its helper existed, although no component ever called it [BE-22].
    A helper api.ts keeps to itself is counted, since its callers are there.
    """
    sources = {}
    for dirpath, _dirnames, filenames in os.walk(ui_src):
        for name in filenames:
            if name.endswith((".ts", ".tsx")):
                full = os.path.join(dirpath, name)
                with open(full, encoding="utf-8") as handle:
                    sources[os.path.relpath(full, ui_src)] = handle.read()

    found = set()
    for relpath, text in sources.items():
        if relpath == API_CLIENT:
            continue
        found.update(_normalise(hit) for hit in _PATH_LITERAL.findall(text))

    client = sources.get(API_CLIENT)
    if client is not None:
        elsewhere = "\n".join(text for relpath, text in sources.items() if relpath != API_CLIENT)
        for name, exported, body in _client_chunks(client):
            if exported and not re.search(rf"\b{re.escape(name)}\b", elsewhere):
                continue
            found.update(_normalise(hit) for hit in _PATH_LITERAL.findall(body))
    return found


def test_an_exported_but_unused_client_function_is_not_counted(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "api.ts").write_text(
        'async function call(path) { return fetch(path); }\n'
        'export async function used() { return call("/api/used"); }\n'
        'export async function unused() { return call("/api/unused"); }\n',
        encoding="utf-8",
    )
    (tmp_path / "Screen.tsx").write_text('import { used } from "./lib/api";\nused();\n', encoding="utf-8")
    assert _interface_paths(str(tmp_path)) == {"/api/used"}


@pytest.fixture(scope="module")
def measured():
    if not os.path.isdir(UI_SRC):
        pytest.skip("studio/ui/src is absent from this checkout")

    declared = _declared_routes()
    reached_paths = _interface_paths()

    reached = set()
    for route in declared:
        for called in reached_paths:
            # Exact, or the interface calls a longer path under this one.
            #
            # There was a third clause, route.startswith(called), meant for a
            # client that appends to a prefix. Normalisation already turns
            # every ${...} into *, so that case never needed it, and what it
            # actually did was credit a route whenever a SHORTER path was
            # called: DELETE /api/v1/identity counted /api/v1/identity/observe
            # as reached, and /api/v1/internal-sheet/issues/*/promote had been
            # counted for as long as this file existed although nothing in the
            # interface calls it.
            if route == called or called.startswith(route + "/"):
                reached.add(route)
                break

    return {
        "declared": declared,
        "reached": reached,
        "unreachable": declared - reached,
    }


def test_the_recorded_path_total_is_still_true(measured):
    actual = len(measured["declared"])
    assert actual == TOTAL_API_PATHS, (
        f"this backend declares {actual} distinct API paths, and this file records "
        f"{TOTAL_API_PATHS}. Update TOTAL_API_PATHS and say in the commit "
        f"what was added or removed."
    )


def test_the_recorded_reachable_count_is_still_true(measured):
    actual = len(measured["reached"])
    assert actual == REACHED_BY_INTERFACE, (
        f"the interface reaches {actual} routes, and this file records "
        f"{REACHED_BY_INTERFACE}. If you surfaced something, raise the number: "
        f"that is the improvement this test exists to make visible."
    )


def test_the_recorded_unreachable_count_is_still_true(measured):
    actual = len(measured["unreachable"])
    assert actual == UNREACHABLE, (
        f"{actual} routes have no caller in the interface, and this file "
        f"records {UNREACHABLE}.\n\n"
        f"If you added an endpoint without a surface, that is allowed, and "
        f"raising this number is how it stops being invisible. If you gave one "
        f"a surface, lower it.\n\n"
        f"Currently unreachable:\n  "
        + "\n  ".join(sorted(measured["unreachable"])[:20])
    )


def test_the_three_numbers_agree_with_each_other():
    """A transcription slip in the constants above should not need a diff to spot."""
    assert REACHED_BY_INTERFACE + UNREACHABLE == TOTAL_API_PATHS


def test_more_than_a_third_of_the_backend_is_reachable(measured):
    """
    A floor rather than a ceiling, and deliberately generous.

    This one does not need updating when a route is added. It exists so that a
    long run of unsurfaced endpoints cannot quietly become most of the product
    while each individual addition looks reasonable.
    """
    share = len(measured["reached"]) / max(1, len(measured["declared"]))
    assert share > 0.33, (
        f"only {share:.0%} of the backend is reachable from the interface"
    )
