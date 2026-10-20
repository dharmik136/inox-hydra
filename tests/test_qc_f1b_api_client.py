"""
The interface's request core, executed in node against a fake fetch.
===================================================================

WRITE-24 / UX-07: a refusal whose detail was an object (a provider's own
message, LinkedIn's refusal) or a validation list showed as a bare "400" or
"502", because only a string detail was read.

UX-21: a request that could not reach the studio showed the browser's "Failed
to fetch", and nothing told the window the studio had gone.
"""

import json
import os
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
API_MODULE = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")
UI_DIR = os.path.join(REPO_ROOT, "studio", "ui")
NODE = shutil.which("node") or shutil.which("node.exe")


def _esbuild():
    for name in ("esbuild.cmd", "esbuild"):
        candidate = os.path.join(UI_DIR, "node_modules", ".bin", name)
        if os.path.exists(candidate):
            return candidate
    return None


ESBUILD = _esbuild()

# Each scenario is a list of fake answers, consumed in order. "throw" stands
# for a request that never reached the studio.
PROBE = r"""
import * as api from "./api.js";

const queue = [];
const seen = [];
globalThis.fetch = async (path, init) => {
  seen.push({ path, headers: Object.fromEntries(new Headers(init && init.headers).entries()) });
  const next = queue.shift();
  if (next === "throw") throw new TypeError("Failed to fetch");
  const headers = new Headers(next.headers || {});
  const text = typeof next.body === "string" ? next.body : JSON.stringify(next.body);
  return new Response(text, { status: next.status, statusText: next.statusText || "", headers });
};

async function attempt(answers, run) {
  queue.length = 0;
  queue.push(...answers);
  try {
    await run();
    return { ok: true, state: api.currentConnection ? api.currentConnection().state : "none" };
  } catch (error) {
    return {
      ok: false,
      message: error.message,
      status: error.status,
      code: error.code,
      state: api.currentConnection ? api.currentConnection().state : "none",
    };
  }
}

const out = {};
const changes = [];
if (api.onConnectionChange) api.onConnectionChange((next) => changes.push(next.state));

out.objectDetail = await attempt(
  [{ status: 400, body: { detail: { error: "AI Provider Verification Failed", message: "HTTP 401: Incorrect API key provided" } } }],
  () => api.fetchAccounts(),
);
out.codedDetail = await attempt(
  [{ status: 409, body: { detail: { code: "send_unconfirmed", message: "Check LinkedIn first." } } }],
  () => api.fetchAccounts(),
);
out.listDetail = await attempt(
  [{ status: 422, body: { detail: [{ loc: ["body", "content"], msg: "Field required" }] } }],
  () => api.fetchAccounts(),
);
out.htmlError = await attempt(
  [{ status: 500, statusText: "Internal Server Error", body: "<html>boom</html>" }],
  () => api.fetchAccounts(),
);
out.stringDetail = await attempt(
  [{ status: 400, body: { detail: "Post content exceeds maximum 5,000 character limit." } }],
  () => api.fetchAccounts(),
);
out.unreachable = await attempt(["throw"], () => api.fetchAccounts());
out.back = await attempt(
  [{ status: 200, body: { accounts: [], active_account_id: "default", profile_limit: 1 } }],
  () => api.fetchAccounts(),
);
out.changes = changes.slice();

// WRITE-01: the window learns its profile from the first answer that names
// one, names it on every request after, and notices when the studio answers
// for another.
const accounts = { status: 200, body: { accounts: [], active_account_id: "default", profile_limit: 1 } };
await attempt([{ ...accounts, headers: { "X-Inox-Profile": "default" } }], () => api.fetchAccounts());
await attempt([{ ...accounts, headers: { "X-Inox-Profile": "default" } }], () => api.fetchAccounts());
out.sentProfile = seen[seen.length - 1].headers["x-inox-profile"] || null;
out.switched = await attempt([{ ...accounts, headers: { "X-Inox-Profile": "client-b" } }], () => api.fetchAccounts());
out.shownAfterSwitch = api.shownProfileId ? api.shownProfileId() : null;
out.staleConnection = api.currentConnection ? api.currentConnection() : null;
// An answer that names no profile (a crash page, a 401) does not prove the
// window is back on its profile, so it stays stale.
await attempt([{ status: 500, body: "<html>crash</html>" }], () => api.fetchAccounts());
out.staleAfterCrash = api.currentConnection ? api.currentConnection().state : null;
await attempt([{ ...accounts, headers: { "X-Inox-Profile": "default" } }], () => api.fetchAccounts());
out.afterSwitchBack = api.currentConnection ? api.currentConnection().state : null;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def probe():
    if not NODE:
        pytest.skip("node is not installed")
    if not ESBUILD:
        pytest.skip("studio/ui dependencies are not installed")
    with tempfile.TemporaryDirectory() as work:
        compiled = os.path.join(work, "api.js")
        build = subprocess.run(
            [ESBUILD, API_MODULE, "--format=esm", f"--outfile={compiled}"],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert build.returncode == 0, build.stderr
        script = os.path.join(work, "probe.mjs")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(PROBE)
        run = subprocess.run([NODE, script], capture_output=True, text=True, encoding="utf-8", cwd=work, timeout=60)
        assert run.returncode == 0, run.stderr
        return json.loads(run.stdout)


def test_an_object_detail_shows_the_providers_own_words(probe):
    result = probe["objectDetail"]
    assert result["message"] == "AI Provider Verification Failed: HTTP 401: Incorrect API key provided"
    assert result["status"] == 400


def test_a_coded_refusal_keeps_its_code_for_the_caller(probe):
    assert probe["codedDetail"]["code"] == "send_unconfirmed"
    assert probe["codedDetail"]["message"] == "Check LinkedIn first."


def test_a_validation_failure_is_a_sentence(probe):
    assert "Field required" in probe["listDetail"]["message"]


def test_a_page_that_is_not_json_still_reads_as_a_sentence(probe):
    message = probe["htmlError"]["message"]
    assert message != "500"
    assert "500" in message and "refused" in message


def test_a_string_detail_is_unchanged(probe):
    assert probe["stringDetail"]["message"] == "Post content exceeds maximum 5,000 character limit."


def test_an_unreachable_studio_is_said_in_words_and_announced(probe):
    result = probe["unreachable"]
    assert "Failed to fetch" not in result["message"]
    assert "not answering" in result["message"]
    assert result["status"] == 0
    assert result["state"] == "offline"


def test_every_request_names_the_profile_the_window_loaded_with(probe):
    assert probe["sentProfile"] == "default"


def test_an_answer_for_another_profile_marks_the_window_stale(probe):
    assert probe["shownAfterSwitch"] == "default", "the window must keep the profile it loaded with"
    assert probe["staleConnection"] == {"state": "stale-profile", "shown": "default", "active": "client-b"}


def test_an_answer_naming_no_profile_does_not_clear_a_stale_window(probe):
    assert probe["staleAfterCrash"] == "stale-profile"
    assert probe["afterSwitchBack"] == "online"


def test_the_window_learns_the_studio_is_back(probe):
    assert probe["back"]["ok"] is True
    assert probe["back"]["state"] == "online"
    assert probe["changes"][-2:] == ["offline", "online"]
