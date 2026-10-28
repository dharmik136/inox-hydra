"""
Stage 2 of From your record: the creator's own model, checked before anything it wrote is shown.
================================================================================================

Cycle 4, track 7, batch 7 of the personalised daily ideas report, and
decisions 7, 8 and 9. The gateway sent a plain prompt to every provider; it
now asks for a JSON Schema each provider's own way. The section sends a
redacted set of the creator's own rows (an allowlist: own text, own ids,
topic labels, the studio's word for how a post did, the asks they kept,
their habits in words) and accepts only ids it sent, an angle from a fixed
list and short phrases. An idea is dropped, never repaired, when it cites a
row that was not sent or is gone, quotes words that are not in the post,
carries a number, names a person, or runs long. It runs once a day on the
creator's first open, under a daily ceiling, on the Creator tier.

The fake provider is an OpenAI-compatible endpoint on loopback, so the real
request builder, the egress category and the parser all run; it records
what arrived. Invented people and posts only.
"""

import io
import json
import os
import re
import sqlite3
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)

LEAD = "Morgan Quillfeather"
CONNECTION = "Tobias Inkwell"
AUTHOR = "Selene Marchbanks"
EMAIL = "someone@example.org"
PHONE = "+44 20 7946 0958"
SECRET_FIGURE = "777"


class Provider:
    """An OpenAI-compatible endpoint on loopback that answers what a test tells it to, and keeps what it was sent."""

    def __init__(self):
        self.requests = []
        self.answer = {"ideas": []}
        self.on_request = None
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                recorder.requests.append(body)
                if recorder.on_request:
                    recorder.on_request(body)
                content = json.dumps(recorder.answer)
                out = json.dumps({"choices": [{"message": {"content": content}}],
                                  "usage": {"prompt_tokens": 1234, "completion_tokens": 321}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    monkeypatch.delenv("INOX_NO_EGRESS", raising=False)
    for key in ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    import results
    from database import init_db

    results.forget_cache()
    init_db()
    return tmp_path


@pytest.fixture
def provider(home):
    from agno_agentos import model_gateway

    fake = Provider()
    model_gateway.save_ai_config(provider="custom_openai", api_key="sk-record-fake-000000", model="fake-model",
                                 base_url=f"http://127.0.0.1:{fake.port}/v1")
    yield fake
    model_gateway.save_ai_config(provider="local_deterministic")
    fake.close()


def db():
    import paths

    conn = sqlite3.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def urn(n):
    return f"urn:li:activity:74300000000000{n:05d}"


TEXTS = [
    f"Hiring without a recruiter taught me to write the job post first. Thanks {LEAD} for the push.",
    f"Pricing is a design decision. Email me at {EMAIL} or call {PHONE} if you disagree.",
    "We changed our hiring loop and the offers got better, not slower. https://example.com/loop",
    "Pricing pages lie less when the founder writes them herself.",
    "A short note on writing every morning before the inbox opens.",
]


def seed():
    conn = db()
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    for n, text in enumerate(TEXTS):
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
                     "first_seen_at, last_seen_at) VALUES (?, ?, ?, 'archive', ?, ?, ?)",
                     (urn(n), text, old, int(SECRET_FIGURE) if n == 0 else 10 + n, old, old))
        observed = datetime.now(timezone.utc) - timedelta(days=2)
        conn.execute("INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
                     "impressions, reactions, comments, reposts) VALUES (?, ?, ?, ?, 'post_analytics', ?, ?, 1, 0)",
                     (urn(n), observed.isoformat(), observed.strftime("%Y-%m-%dT%H"), 900.0, 5000,
                      int(SECRET_FIGURE) if n == 0 else 10 + n))
    conn.execute("INSERT INTO leads (id, name, full_name, headline) VALUES ('lead-x', ?, ?, 'Founder')", (LEAD, LEAD))
    conn.execute("INSERT INTO connections (profile_url, first_name, last_name, source, imported_at) "
                 "VALUES ('https://www.linkedin.com/in/tobias-x', 'Tobias', 'Inkwell', 'archive', ?)", (old,))
    conn.execute("INSERT INTO outbound_engagements (target_activity_urn, target_author, target_excerpt, kind, my_text, "
                 "my_text_key, first_seen_at, last_seen_at) VALUES ('urn:li:activity:7399', ?, 'their own words here', "
                 "'comment', 'my reply about hiring', 'k', ?, ?)", (AUTHOR, old, old))
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO asks (text, source, status, created_at, updated_at) VALUES "
                 "('hiring without a recruiter', 'ask_box', 'open', ?, ?)", (now, now))
    conn.commit()
    conn.close()
    import record_daily

    assert record_daily.run_today()["status"] == "built"


def good_idea(based_on=None, ask="ask-1", hook="Write the job post before you look for anyone",
              quote="write the job post first"):
    return {"based_on": based_on or [urn(0)], "ask": ask, "angle_kind": "story", "hook": hook,
            "angle": "How writing the post first changed who applied", "why": "Your hiring posts land above your usual",
            "quote": quote}


def today_cards():
    import record_daily

    return record_daily.read_today()["cards"]


def run_model():
    import record_model

    return record_model.run_on_open(wait=True)


def the_run():
    import record_daily

    conn = db()
    try:
        return dict(conn.execute("SELECT * FROM daily_run WHERE day = ?", (record_daily.local_today().isoformat(),)).fetchone())
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The gateway asks for a schema each provider's own way
# ---------------------------------------------------------------------------

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["a"],
          "properties": {"a": {"type": "string", "enum": ["x"]}}}


@pytest.mark.parametrize("provider_name", ["openai", "groq", "ollama", "custom_openai"])
def test_the_openai_family_gets_a_strict_json_schema(provider_name):
    from agno_agentos import model_gateway

    endpoint, payload, _headers = model_gateway._request_for(provider_name, "https://h/v1", "k", "m", "p", "s", 100, 0.2,
                                                             structured={"name": "n", "schema": SCHEMA})
    assert endpoint == "https://h/v1/chat/completions"
    assert payload["response_format"] == {"type": "json_schema", "json_schema": {"name": "n", "schema": SCHEMA, "strict": True}}


def test_anthropic_gets_output_config_format():
    from agno_agentos import model_gateway

    _endpoint, payload, _headers = model_gateway._request_for("anthropic", "https://h/v1", "k", "m", "p", "s", 100, 0.2,
                                                              structured={"name": "n", "schema": SCHEMA})
    assert payload["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}


def test_gemini_gets_a_json_mime_type_and_schema_without_what_it_does_not_document():
    from agno_agentos import model_gateway

    _endpoint, payload, _headers = model_gateway._request_for("gemini", "https://h", "k", "m", "p", "s", 100, 0.2,
                                                              structured={"name": "n", "schema": SCHEMA})
    generation = payload["generationConfig"]
    assert generation["responseMimeType"] == "application/json"
    assert generation["responseJsonSchema"] == {"type": "object", "required": ["a"],
                                                "properties": {"a": {"type": "string", "enum": ["x"]}}}


@pytest.mark.parametrize("provider_name", ["gemini", "openai", "groq", "ollama", "custom_openai", "anthropic"])
def test_an_unstructured_request_is_exactly_what_it_was(provider_name):
    """No schema, no new field: every existing caller sends what it always sent."""
    from agno_agentos import model_gateway

    _endpoint, payload, _headers = model_gateway._request_for(provider_name, "https://h/v1", "k", "m", "p", "s", 100, 0.2)
    text = json.dumps(payload)
    for added in ("response_format", "output_config", "responseMimeType", "responseJsonSchema"):
        assert added not in text, f"{provider_name}: an unstructured request now carries {added}"


@pytest.mark.parametrize("provider_name,data,usage", [
    ("openai", {"choices": [{"message": {"content": '{"a": "x"}'}}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
     {"input": 5, "output": 2}),
    ("anthropic", {"content": [{"type": "text", "text": '{"a": "x"}'}], "usage": {"input_tokens": 7, "output_tokens": 3}},
     {"input": 7, "output": 3}),
    ("gemini", {"candidates": [{"content": {"parts": [{"text": '{"a": "x"}'}]}}],
                "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 4}}, {"input": 9, "output": 4}),
])
def test_a_structured_answer_is_parsed_with_the_providers_own_counts(monkeypatch, provider_name, data, usage):
    from agno_agentos import model_gateway

    seen = {}

    def fake_post(endpoint, payload, headers, stop, who, model, budget):
        seen["payload"] = payload
        return data

    monkeypatch.setattr(model_gateway, "_post_json", fake_post)
    config = model_gateway.AIProviderConfig(provider=provider_name, api_key="sk-fake-key-123456", model="m")
    answer = model_gateway.execute_structured_completion(config, "p", "s", SCHEMA, "n")
    assert answer["data"] == {"a": "x"} and answer["usage"] == usage
    assert seen["payload"], "nothing was sent"


@pytest.mark.parametrize("data", [
    {"choices": [{"message": {"content": "not json at all"}}]},
    {"choices": [{"message": {"content": None, "refusal": "I will not"}}]},
])
def test_an_answer_that_is_not_the_json_asked_for_is_an_error_not_a_success(monkeypatch, data):
    from agno_agentos import model_gateway

    monkeypatch.setattr(model_gateway, "_post_json", lambda *args, **kwargs: data)
    config = model_gateway.AIProviderConfig(provider="openai", api_key="sk-fake-key-123456", model="m")
    with pytest.raises(model_gateway.ProviderError):
        model_gateway.execute_structured_completion(config, "p", "s", SCHEMA, "n")


# ---------------------------------------------------------------------------
# What is sent: an allowlist of the creator's own rows, redacted
# ---------------------------------------------------------------------------

def test_what_is_sent_is_the_creators_own_and_nobody_elses(provider):
    seed()
    provider.answer = {"ideas": [good_idea()]}
    run_model()
    assert len(provider.requests) == 1
    sent = json.dumps(provider.requests[0])
    for absent, what in ((LEAD, "a person who engaged"), (CONNECTION, "a connection"), (AUTHOR, "an author engaged with"),
                         ("their own words here", "another person's post"), (EMAIL, "an address"), (PHONE, "a phone"),
                         ("https://example.com/loop", "a link"), (SECRET_FIGURE, "a figure")):
        assert absent not in sent, f"{what} left the machine: {absent!r}"
    assert "[person]" in sent and "[email]" in sent and "[phone]" in sent and "[link]" in sent
    assert "Hiring without a recruiter taught me" in sent, "the creator's own words were not sent"
    assert "hiring without a recruiter" in sent and "above your usual" in sent
    schema = provider.requests[0]["response_format"]["json_schema"]["schema"]
    enum = schema["properties"]["ideas"]["items"]["properties"]["based_on"]["items"]["enum"]
    assert set(enum) == {urn(n) for n in range(len(TEXTS))}


def test_the_idea_is_shown_with_its_provenance_and_the_run_records_the_call(provider):
    seed()
    provider.answer = {"ideas": [good_idea()]}
    assert run_model()["status"] == "done"
    slot5 = [c for c in today_cards() if c["slot"] == 5 and c["status"] == "shown"]
    assert len(slot5) == 1 and slot5[0]["kind"] == "idea" and slot5[0]["label"] == "suggested"
    card = slot5[0]
    model = card["provenance"]["model"]
    assert model["provider"] == "custom_openai" and model["schema_version"] == 1 and model["call_id"] and model["prompt_hash"]
    assert card["provenance"]["verification"] == {"ids_exist": True, "excerpt_is_substring": True,
                                                  "digits_in_model_text": False, "dropped_reason": None}
    assert {"table": "own_posts", "id": urn(0)} in card["provenance"]["source_rows"]
    assert card["payload"]["because"].startswith("Because you asked for")
    run = the_run()
    assert run["model_status"] == "ran" and run["model_calls"] == 1
    assert run["model_tokens_in"] == 1234 and run["model_tokens_out"] == 321
    assert run["estimated_cost_usd"] == 0 and run["price_date"] == "2026-10-26"


# ---------------------------------------------------------------------------
# No number from a model reaches the screen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("planted", [
    "Post 3 times a week", "Your reach doubled by 40%", "Twice the replies, a times-two week",
    "Nine out of ten founders ٣ agree",  # an Arabic-Indic digit
    "Half the posts, ½ the effort",
])
def test_a_number_planted_in_the_models_answer_never_reaches_the_screen(provider, planted):
    seed()
    provider.answer = {"ideas": [good_idea(hook=planted), good_idea(hook="Write the job post before anyone applies")]}
    run_model()
    shown = [c for c in today_cards() if c["slot"] == 5 and c["status"] == "shown"]
    assert len(shown) == 1 and shown[0]["payload"]["excerpt"] == "Write the job post before anyone applies"
    screen = json.dumps(shown)
    assert planted not in screen
    run = the_run()
    assert run["dropped_cards"] == 1 and "carried a number" in run["model_note"]


def test_the_number_guard_is_what_stops_it(provider, monkeypatch):
    """Falsified: with the filter switched off, the planted digit is on the screen."""
    import record_model

    seed()
    monkeypatch.setattr(record_model, "has_number", lambda text: False)
    provider.answer = {"ideas": [good_idea(hook="Post 3 times a week")]}
    run_model()
    shown = [c for c in today_cards() if c["slot"] == 5 and c["status"] == "shown"]
    assert shown and shown[0]["payload"]["excerpt"] == "Post 3 times a week"


def test_the_number_filter_reads_digits_in_any_script_and_the_two_words():
    import record_model

    for text in ("3", "٣", "३", "40%", "½", "x²", "two times", "ten percent", "per cent"):
        assert record_model.has_number(text), text
    for text in ("Write the post first", "timeless advice", "a percentile is not here"):
        assert not record_model.has_number(text), text


# ---------------------------------------------------------------------------
# Every cited row exists, and nothing is repaired
# ---------------------------------------------------------------------------

def test_an_id_that_was_not_sent_is_dropped(provider):
    seed()
    provider.answer = {"ideas": [good_idea(based_on=["urn:li:activity:1111111111111111111"])]}
    run_model()
    assert not [c for c in today_cards() if c["kind"] == "idea" and c["status"] == "shown"]
    assert "cited a post that was not sent" in the_run()["model_note"]
    slot5 = [c for c in today_cards() if c["slot"] == 5 and c["status"] == "abstained"]
    assert slot5 and "none of its ideas could be checked" in slot5[0]["payload"]["sentence"]


def test_a_row_that_is_gone_by_the_time_the_answer_arrives_is_dropped(provider):
    seed()

    def delete_the_post(_body):
        conn = db()
        conn.execute("DELETE FROM own_posts WHERE activity_urn = ?", (urn(3),))
        conn.commit()
        conn.close()

    provider.on_request = delete_the_post
    provider.answer = {"ideas": [good_idea(based_on=[urn(3)], quote="")]}
    run_model()
    dropped = [c for c in today_cards() if c["kind"] == "idea"]
    assert not [c for c in dropped if c["status"] == "shown"]
    assert "a cited row was not found" in the_run()["model_note"]


@pytest.mark.parametrize("idea,reason", [
    (good_idea(quote="words the creator never wrote"), "quoted words that are not in your post"),
    (good_idea(hook=f"Ask {LEAD} how she hires"), "named a person"),
    (good_idea(hook="x" * 200), "a phrase longer than"),
    ({**good_idea(), "angle_kind": "viral"}, "an angle outside the list"),
    ({**good_idea(), "ask": "ask-999"}, "cited an ask that was not sent"),
    ({"hook": "only a hook"}, "not the shape asked for"),
])
def test_an_idea_that_fails_a_check_is_dropped_with_the_reason(provider, idea, reason):
    seed()
    provider.answer = {"ideas": [idea]}
    run_model()
    assert not [c for c in today_cards() if c["kind"] == "idea" and c["status"] == "shown"]
    assert reason in the_run()["model_note"]


# ---------------------------------------------------------------------------
# When it runs: on the first open, once, under the ceiling, on the tier
# ---------------------------------------------------------------------------

def test_reading_the_section_and_the_daily_job_never_call_the_model(provider):
    seed()
    from fastapi.testclient import TestClient

    import app as app_module
    import record_daily

    client = TestClient(app_module.app)
    assert client.get("/api/v1/record").json()["model"]["should_run"] is True
    record_daily.run_today()
    assert provider.requests == [], "a read or the daily job called the model"
    callers = []
    for root, _dirs, names in os.walk(BACKEND):
        for name in names:
            if name.endswith(".py") and "run_on_open(" in io.open(os.path.join(root, name), encoding="utf-8").read():
                callers.append(name)
    assert sorted(callers) == ["record.py", "record_model.py"], callers


def test_the_first_open_calls_once_and_the_second_does_not(provider):
    seed()
    from fastapi.testclient import TestClient

    import app as app_module

    provider.answer = {"ideas": [good_idea()]}
    client = TestClient(app_module.app)
    assert client.post("/api/v1/record/model").status_code == 200
    for _ in range(100):
        if the_run()["model_status"] != "running":
            break
        threading.Event().wait(0.05)
    assert the_run()["model_status"] == "ran"
    second = client.post("/api/v1/record/model").json()
    assert second["status"] == "not_run"
    assert len(provider.requests) == 1


def test_the_daily_ceiling_holds_the_call_back(home, monkeypatch):
    from agno_agentos import model_gateway

    seed()

    def refuse(*_args, **_kwargs):
        raise AssertionError("a call was made over the ceiling")

    monkeypatch.setattr(model_gateway, "_post_json", refuse)
    model_gateway.save_ai_config(provider="openai", api_key="sk-record-fake-000000", model="gpt-5")
    import record_store

    record_store.set_settings({"cost_ceiling_usd": 0.0})
    run_model()
    run = the_run()
    assert run["model_status"] == "capped" and "over what is left of your daily ceiling of $0.00" in run["model_note"]
    model_gateway.save_ai_config(provider="local_deterministic")


def test_a_provider_with_no_listed_price_is_not_called(home, monkeypatch):
    from agno_agentos import model_gateway

    seed()
    monkeypatch.setattr(model_gateway, "_post_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    model_gateway.save_ai_config(provider="groq", api_key="gsk-record-fake-000000", model="llama-3.3-70b-versatile")
    run_model()
    assert the_run()["model_status"] == "capped"
    assert "no price is listed for Groq" in the_run()["model_note"]
    model_gateway.save_ai_config(provider="local_deterministic")


def test_an_unlisted_model_is_estimated_at_its_providers_dearest_price():
    import record_model
    from agno_agentos import model_gateway

    config = model_gateway.AIProviderConfig(provider="openai", api_key="sk-record-fake-000000", model="gpt-4o")
    price, basis = record_model.price_of(config)
    assert price == (2.50, 15.00) and "dearest OpenAI price" in basis and "gpt-4o" in basis


@pytest.mark.parametrize("setup,reason", [
    ("off", "The model stage is off"),
    ("no_key", "No AI provider is connected"),
    ("tier", "part of the Creator licence"),
])
def test_off_no_key_and_the_tier_send_nothing(provider, monkeypatch, setup, reason):
    import licensing
    import record_model
    import record_store
    from agno_agentos import model_gateway

    seed()
    if setup == "off":
        record_store.set_settings({"model_stage": "off"})
    elif setup == "no_key":
        model_gateway.save_ai_config(provider="local_deterministic")
    else:
        monkeypatch.setattr(licensing, "BETA_OPEN", False)
        monkeypatch.setattr(licensing, "current", lambda today=None: {"tier": "free"})
    state = record_model.state()
    assert state["should_run"] is False and reason in state["reason"]
    assert run_model()["status"] == "not_run"
    assert provider.requests == []


def test_a_refused_category_fails_in_words_and_the_local_cards_stand(provider, monkeypatch):
    seed()
    before = [c["card_id"] for c in today_cards() if c["status"] == "shown"]
    monkeypatch.setenv("INOX_NO_EGRESS", "1")
    run_model()
    run = the_run()
    assert run["model_status"] == "failed: refused" and "INOX_NO_EGRESS" in run["model_note"]
    assert [c["card_id"] for c in today_cards() if c["status"] == "shown"] == before
    assert provider.requests == []


def test_the_call_is_counted_under_the_model_category(provider):
    import egress

    seed()
    provider.answer = {"ideas": [good_idea()]}
    egress.reset_for_tests()
    run_model()
    counted = {c["name"]: c["performed"] for c in egress.describe()["categories"]}
    assert counted["model"] == 1 and sum(counted.values()) == 1


def test_a_carried_forward_day_keeps_yesterdays_idea_and_asks_nothing(provider):
    import record_daily
    import record_model

    seed()
    provider.answer = {"ideas": [good_idea()]}
    run_model()
    tomorrow = record_daily.local_today() + timedelta(days=1)
    assert record_daily.run_today(tomorrow)["status"] == "carried"
    state = record_model.state(tomorrow)
    assert state["should_run"] is False and "yesterday's idea stands" in state["reason"]


# ---------------------------------------------------------------------------
# The policy and the help say it before it ships
# ---------------------------------------------------------------------------

def _system_sent(request):
    return next(m["content"] for m in request["messages"] if m["role"] == "system")


def test_a_fresh_profile_asks_for_three_ideas(provider):
    """Phase 3: how many ideas a call asks for is the creator's preference, three until they change it."""
    seed()
    provider.answer = {"ideas": [good_idea()]}
    run_model()
    assert "at most three ideas" in _system_sent(provider.requests[0])
    assert "up to three ideas" in json.dumps(provider.requests[0])


def test_how_many_ideas_is_the_creators_preference(provider):
    import writing

    writing.save({"ideas": 1})
    seed()
    provider.answer = {"ideas": [good_idea(), good_idea(hook="Write the job post before anyone applies")]}
    run_model()
    assert "at most one idea" in _system_sent(provider.requests[0])
    assert "up to one idea" in json.dumps(provider.requests[0])
    conn = db()
    try:
        kept = conn.execute("SELECT COUNT(*) FROM daily_view WHERE kind = 'idea' AND label = 'suggested'").fetchone()[0]
    finally:
        conn.close()
    assert kept == 1, "an idea past the number asked for was read"


def test_the_policy_and_the_help_name_the_model_stage():
    policy = io.open(os.path.join(REPO_ROOT, "docs", "PRIVACY_POLICY.md"), encoding="utf-8").read()
    assert "only at the moment you use the feature that needs it" in policy
    assert "From your\nrecord for the first time each day, never on a timer" in policy
    help_text = io.open(os.path.join(REPO_ROOT, "docs", "help", "what-leaves-this-machine.md"), encoding="utf-8").read()
    row = next(line for line in help_text.splitlines() if line.startswith("| `model` |"))
    assert "From your record" in row and "the first time you open that section each day" in row
    assert "never a figure" in row


def test_an_ask_from_an_archive_search_is_never_sent(provider):
    """A search is often a person's name: whatever the creator ticked, it does not leave."""
    seed()
    conn = db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO asks (text, source, origin_ref, status, created_at, updated_at) VALUES "
                 "('hiring like Wren Example does', 'archive_search', 'archive_record:9', 'open', ?, ?)", (now, now))
    conn.commit()
    conn.close()
    provider.answer = {"ideas": [good_idea()]}
    run_model()
    assert "Wren Example" not in json.dumps(provider.requests[0])
