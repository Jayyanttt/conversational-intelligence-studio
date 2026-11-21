"""Batch 2: key pool, failover and X-Simulate-Failure.

MOCKED tests: no network. They run the real LiteLLMClient and the real LiteLLM
`completion()` code path, with `mock_response` supplying the "provider" output, or
with an injected completion function that raises genuine LiteLLM exceptions.
"""
import logging
from dataclasses import replace

import litellm
import pytest
from fastapi.testclient import TestClient

from app.llm import AllProvidersUnavailable, LiteLLMClient
from app.main import create_app
from app.simulation import InvalidSimulationHeader, build_exception, parse_simulate_header, status_for

META_FIELDS = {"resolution_source", "model", "latency_ms", "input_tokens", "output_tokens", "key_id", "fallback_attempts"}
REPLY = "The capital of France is Paris."


class Recorder:
    """completion_fn that runs real litellm.completion with a mocked provider reply."""

    def __init__(self, behaviour=None):
        self.calls = []
        self.behaviour = behaviour  # optional fn(kwargs) -> raises / returns response

    def __call__(self, **kw):
        self.calls.append(kw)
        if self.behaviour:
            out = self.behaviour(kw)
            if out is not None:
                return out
        return litellm.completion(**{"mock_response": REPLY, **kw})


MODEL = "gemini/gemini-2.0-flash"  # real LiteLLM model name so the real completion() path runs


def make_client(settings, rec):
    settings = replace(settings, model=MODEL)
    app = create_app(settings, LiteLLMClient(settings, completion_fn=rec))
    return TestClient(app, raise_server_exceptions=False)


def chat(c, sid="s1", msg="What is the capital of France?", **headers):
    return c.post("/chat", json={"session_id": sid, "message": msg}, headers=headers)


# ---- header parsing -----------------------------------------------------------

def test_parse_header_variants():
    assert parse_simulate_header(None) is None
    assert parse_simulate_header("  ") is None
    assert parse_simulate_header("key_1=429") == {"key_1": 429}
    assert parse_simulate_header("key_1=429, key_2=500") == {"key_1": 429, "key_2": 500}
    assert parse_simulate_header("*=503") == {"*": 503}


@pytest.mark.parametrize("bad", ["key_1", "key_1=", "=429", "key_1=418", "key_1=abc", "key_1=429;key_2=500"])
def test_parse_header_rejects_malformed(bad):
    with pytest.raises(InvalidSimulationHeader):
        parse_simulate_header(bad)


def test_explicit_key_beats_wildcard():
    sim = {"*": 429, "key_2": 500}
    assert status_for("key_1", sim) == 429 and status_for("key_2", sim) == 500
    assert status_for("key_1", None) is None


@pytest.mark.parametrize("status,exc", [
    (429, litellm.RateLimitError), (500, litellm.InternalServerError),
    (502, litellm.BadGatewayError), (503, litellm.ServiceUnavailableError)])
def test_build_exception_is_real_litellm_error(status, exc):
    e = build_exception(status, "gemini/gemini-2.0-flash")
    assert isinstance(e, exc) and e.status_code == status


# ---- normal path ----------------------------------------------------------------

def test_success_uses_key_1_with_full_metadata(settings):
    rec = Recorder()
    with make_client(settings, rec) as c:
        r = chat(c)
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == REPLY
    m = body["metadata"]
    assert set(m) == META_FIELDS
    assert m["resolution_source"] == "LIVE_INFERENCE" and m["key_id"] == "key_1"
    assert m["fallback_attempts"] == 0 and m["model"] == MODEL
    assert isinstance(m["latency_ms"], int) and m["latency_ms"] >= 0
    assert m["input_tokens"] > 0 and m["output_tokens"] > 0
    assert len(rec.calls) == 1 and rec.calls[0]["api_key"] == "x1"
    assert rec.calls[0]["num_retries"] == 0


def test_tokens_come_from_provider_usage_per_request(settings):
    class U: prompt_tokens, completion_tokens = 42, 9
    class Msg: content = "ok"
    class Ch: message = Msg()
    class Resp: choices = [Ch()]; usage = U()
    rec = Recorder(lambda kw: Resp())
    with make_client(settings, rec) as c:
        m1 = chat(c, "a").json()["metadata"]
        m2 = chat(c, "a", "second").json()["metadata"]
    assert (m1["input_tokens"], m1["output_tokens"]) == (42, 9)
    assert (m2["input_tokens"], m2["output_tokens"]) == (42, 9)  # not accumulated


# ---- simulated failover -----------------------------------------------------------

@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_key1_fails_key2_answers(settings, status):
    rec = Recorder()
    with make_client(settings, rec) as c:
        r = chat(c, **{"X-Simulate-Failure": f"key_1={status}"})
        assert r.status_code == 200
        m = r.json()["metadata"]
        assert m["key_id"] == "key_2" and m["fallback_attempts"] == 1
        assert m["resolution_source"] == "LIVE_INFERENCE"
        assert r.json()["reply"] == REPLY  # produced by the (mocked) provider, not hardcoded
        assert len(c.get("/sessions/s1/messages").json()["messages"]) == 2
    # key_1 call carried a real LiteLLM exception; key_2 call carried none
    assert isinstance(rec.calls[0]["mock_response"], Exception)
    assert rec.calls[0]["api_key"] == "x1" and rec.calls[1]["api_key"] == "x2"
    assert "mock_response" not in rec.calls[1]


def test_all_keys_failing_specific_pairs_503_and_not_persisted(settings):
    with make_client(settings, Recorder()) as c:
        r = chat(c, **{"X-Simulate-Failure": "key_1=429,key_2=500"})
        assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
        assert c.get("/sessions/s1/messages").status_code == 404


def test_wildcard_429_503_and_not_persisted(settings):
    with make_client(settings, Recorder()) as c:
        r = chat(c, **{"X-Simulate-Failure": "*=429"})
        assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
        assert c.get("/sessions/s1/messages").status_code == 404


def test_failed_request_does_not_pollute_existing_history(settings):
    with make_client(settings, Recorder()) as c:
        chat(c, msg="one")
        assert chat(c, msg="two", **{"X-Simulate-Failure": "*=500"}).status_code == 503
        msgs = c.get("/sessions/s1/messages").json()["messages"]
        assert [m["content"] for m in msgs] == ["one", REPLY]


def test_simulation_is_per_request_only(settings):
    with make_client(settings, Recorder()) as c:
        assert chat(c, "a", **{"X-Simulate-Failure": "key_1=429"}).json()["metadata"]["key_id"] == "key_2"
        assert chat(c, "b").json()["metadata"]["key_id"] == "key_1"


def test_wildcard_with_explicit_override_only_hits_listed(settings):
    # *=429 fails every key, so even an explicit different status still fails both
    with make_client(settings, Recorder()) as c:
        assert chat(c, **{"X-Simulate-Failure": "*=429,key_2=503"}).status_code == 503


def test_header_ignored_when_simulation_disabled(settings):
    rec = Recorder()
    with make_client(replace(settings, enable_failure_simulation=False), rec) as c:
        r = chat(c, **{"X-Simulate-Failure": "*=429"})
    assert r.status_code == 200 and r.json()["metadata"]["key_id"] == "key_1"
    assert all("mock_response" not in call for call in rec.calls)


def test_malformed_header_is_422_and_not_persisted(settings):
    with make_client(settings, Recorder()) as c:
        r = chat(c, **{"X-Simulate-Failure": "key_1=teapot"})
        assert r.status_code == 422 and isinstance(r.json()["detail"], str)
        assert c.get("/sessions/s1/messages").status_code == 404


def test_three_keys_fallback_attempts_counts_failures(settings):
    from app.config import ApiKey
    s3 = replace(settings, api_keys=(ApiKey("key_1", "x1"), ApiKey("key_2", "x2"), ApiKey("key_3", "x3")))
    with make_client(s3, Recorder()) as c:
        m = chat(c, **{"X-Simulate-Failure": "key_1=429,key_2=503"}).json()["metadata"]
    assert m["key_id"] == "key_3" and m["fallback_attempts"] == 2


# ---- genuine (non-simulated) provider failures --------------------------------------

def test_real_style_provider_errors_trigger_failover(settings):
    def behaviour(kw):
        if kw["api_key"] == "x1":
            raise litellm.RateLimitError(message="quota exceeded", llm_provider="gemini", model="m")
    with make_client(settings, Recorder(behaviour)) as c:
        m = chat(c).json()["metadata"]
    assert m["key_id"] == "key_2" and m["fallback_attempts"] == 1


@pytest.mark.parametrize("exc", [
    litellm.Timeout(message="t", model="m", llm_provider="gemini"),
    litellm.APIConnectionError(message="down", llm_provider="gemini", model="m"),
    litellm.AuthenticationError(message="bad key", llm_provider="gemini", model="m"),
    RuntimeError("boom"),
])
def test_other_provider_failures_also_fail_over(settings, exc):
    def behaviour(kw):
        if kw["api_key"] == "x1":
            raise exc
    with make_client(settings, Recorder(behaviour)) as c:
        r = chat(c)
    assert r.status_code == 200 and r.json()["metadata"]["key_id"] == "key_2"


def test_empty_completion_fails_over(settings):
    class Msg: content = "  "
    class Ch: message = Msg()
    class U: prompt_tokens, completion_tokens = 1, 0
    class Empty: choices = [Ch()]; usage = U()
    def behaviour(kw):
        if kw["api_key"] == "x1":
            return Empty()
    with make_client(settings, Recorder(behaviour)) as c:
        r = chat(c)
    assert r.json()["metadata"]["key_id"] == "key_2" and r.json()["reply"] == REPLY


def test_all_real_failures_503(settings):
    def behaviour(kw):
        raise litellm.InternalServerError(message="x", llm_provider="gemini", model="m")
    with make_client(settings, Recorder(behaviour)) as c:
        r = chat(c)
        assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
        assert c.get("/sessions/s1/messages").status_code == 404


def test_client_raises_when_pool_empty(settings):
    with pytest.raises(AllProvidersUnavailable):
        LiteLLMClient(replace(settings, api_keys=()), completion_fn=Recorder()).complete([{"role": "user", "content": "x"}])


# ---- secrets ---------------------------------------------------------------------

def test_secrets_never_in_responses_or_logs(settings, caplog):
    caplog.set_level(logging.DEBUG)
    def behaviour(kw):
        if kw["api_key"] == "x1":
            raise litellm.RateLimitError(message="bad key x1 / x2", llm_provider="gemini", model="m")
    with make_client(settings, Recorder(behaviour)) as c:
        r = chat(c)
        h = c.get("/sessions/s1/messages")
        hl = c.get("/health")
    for text in (r.text, h.text, hl.text):
        assert "x1" not in text.replace("key_1", "") and "x2" not in text.replace("key_2", "")
    assert "bad key" not in caplog.text  # provider error text is not logged
    assert "key_1 failed" in caplog.text
