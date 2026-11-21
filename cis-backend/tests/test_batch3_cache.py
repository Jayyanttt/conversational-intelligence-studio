"""Batch 3: LiteLLM response cache through the full API.

MOCKED provider (no network) but the REAL LiteLLM cache and completion() code path.
Every live call returns a different reply ("live reply #N"), so a repeated reply can
only have been served from the cache. Live calls are slowed with mock_delay so a hit
is measurably faster.
"""
from dataclasses import replace

import litellm
import pytest
from fastapi.testclient import TestClient

from app.llm import LiteLLMClient
from app.main import create_app

MODEL = "gemini/gemini-2.0-flash"
DELAY = 0.15
META_FIELDS = {"resolution_source", "model", "latency_ms", "input_tokens", "output_tokens", "key_id", "fallback_attempts"}


class Provider:
    def __init__(self, fail_keys=()):
        self.n = 0
        self.calls = []
        self.fail_keys = set(fail_keys)

    def __call__(self, **kw):
        self.calls.append(kw)
        self.n += 1
        if kw.get("api_key") in self.fail_keys:
            raise litellm.RateLimitError(message="quota", llm_provider="gemini", model=MODEL)
        kw.setdefault("mock_response", f"live reply #{self.n}")
        kw.setdefault("mock_delay", DELAY)
        return litellm.completion(**kw)


def make(settings, provider=None, **overrides):
    s = replace(settings, model=MODEL, **overrides)
    provider = provider or Provider()
    return TestClient(create_app(s, LiteLLMClient(s, completion_fn=provider)), raise_server_exceptions=False), provider


def chat(c, sid, msg="What is the capital of France?", **extra):
    headers = extra.pop("headers", None)
    return c.post("/chat", json={"session_id": sid, "message": msg, **extra}, headers=headers)


def meta(r):
    assert r.status_code == 200, r.text
    return r.json()["metadata"]


# ---- core contract ---------------------------------------------------------------------

def test_same_first_message_in_new_session_is_cache_hit(settings):
    c, _ = make(settings)
    with c:
        r1, r2 = chat(c, "s1"), chat(c, "s2")
        m1, m2 = meta(r1), meta(r2)
    assert m1["resolution_source"] == "LIVE_INFERENCE" and m1["key_id"] == "key_1"
    assert m2["resolution_source"] == "LLM_CACHE"
    assert m2["key_id"] is None and m2["fallback_attempts"] == 0
    assert r2.json()["reply"] == r1.json()["reply"] == "live reply #1"  # identical text
    assert (m2["input_tokens"], m2["output_tokens"]) == (m1["input_tokens"], m1["output_tokens"])
    assert set(m2) == META_FIELDS and m2["model"] == MODEL
    assert isinstance(m2["latency_ms"], int)


def test_cache_hit_is_faster_than_live(settings):
    c, _ = make(settings)
    with c:
        live, hit = meta(chat(c, "s1")), meta(chat(c, "s2"))
    assert live["latency_ms"] >= DELAY * 1000 * 0.9
    assert hit["latency_ms"] < live["latency_ms"] / 2


def test_different_message_is_never_served_from_cache(settings):
    c, _ = make(settings)
    with c:
        chat(c, "s1", "What is the capital of France?")
        r = chat(c, "s2", "What is the capital of Spain?")
    assert meta(r)["resolution_source"] == "LIVE_INFERENCE"
    assert r.json()["reply"] == "live reply #2"


def test_different_system_prompt_is_a_miss_same_prompt_is_a_hit(settings):
    c, _ = make(settings)
    with c:
        chat(c, "a", system_prompt="PROMPT A")
        assert meta(chat(c, "b", system_prompt="PROMPT B"))["resolution_source"] == "LIVE_INFERENCE"
        assert meta(chat(c, "c", system_prompt="PROMPT A"))["resolution_source"] == "LLM_CACHE"


def test_analyst_preset_is_part_of_cache_key(settings):
    c, _ = make(settings)
    with c:
        chat(c, "a", analyst_type="customer")
        assert meta(chat(c, "b", analyst_type="workplace"))["resolution_source"] == "LIVE_INFERENCE"
        assert meta(chat(c, "c", analyst_type="customer"))["resolution_source"] == "LLM_CACHE"


def test_conversation_history_is_part_of_cache_key(settings):
    c, _ = make(settings)
    with c:
        chat(c, "a", "first x"); chat(c, "a", "same question")
        chat(c, "b", "first y")                       # different history ...
        assert meta(chat(c, "b", "same question"))["resolution_source"] == "LIVE_INFERENCE"
        chat(c, "d", "first x")                       # same history as session a ...
        assert meta(chat(c, "d", "same question"))["resolution_source"] == "LLM_CACHE"


# ---- persistence & sessions ---------------------------------------------------------------

def test_cache_hit_metadata_is_persisted_and_sessions_stay_separate(settings):
    c, _ = make(settings)
    with c:
        chat(c, "s1"); chat(c, "s2")
        h1 = c.get("/sessions/s1/messages").json()["messages"]
        h2 = c.get("/sessions/s2/messages").json()["messages"]
    assert [m["role"] for m in h2] == ["user", "assistant"] and len(h1) == 2
    assert h1[1]["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    m = h2[1]["metadata"]
    assert set(m) == META_FIELDS and m["resolution_source"] == "LLM_CACHE" and m["key_id"] is None
    assert h2[1]["content"] == h1[1]["content"]


def test_cache_hit_survives_restart_of_history_but_cache_is_in_memory(settings):
    c, _ = make(settings)
    with c:
        chat(c, "s1"); chat(c, "s2")
    from app.llm import reset_cache
    reset_cache()           # a real restart: the in-memory cache is gone ...
    c2, _ = make(settings)  # ... but history in SQLite persists
    with c2:
        assert c2.get("/sessions/s2/messages").json()["messages"][1]["metadata"]["resolution_source"] == "LLM_CACHE"
        assert meta(chat(c2, "s3"))["resolution_source"] == "LIVE_INFERENCE"


# ---- cache + failover ------------------------------------------------------------------------

def test_failover_answer_is_cached_for_everyone(settings):
    c, p = make(settings, Provider(fail_keys={"x1"}))
    with c:
        m1 = meta(chat(c, "a"))
        m2 = meta(chat(c, "b"))
    assert m1["key_id"] == "key_2" and m1["fallback_attempts"] == 1
    assert m2["resolution_source"] == "LLM_CACHE" and m2["key_id"] is None and m2["fallback_attempts"] == 0


def test_simulated_failure_bypasses_cache_hit(settings):
    c, _ = make(settings)
    with c:
        chat(c, "seed")  # message is now cached
        r = chat(c, "s", headers={"X-Simulate-Failure": "key_1=429"})
        m = meta(r)
        assert m["resolution_source"] == "LIVE_INFERENCE"   # NOT served from cache
        assert m["key_id"] == "key_2" and m["fallback_attempts"] == 1
        r = chat(c, "t", headers={"X-Simulate-Failure": "*=429"})
        assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
        assert c.get("/sessions/t/messages").status_code == 404


def test_simulated_request_does_not_write_to_cache(settings):
    c, _ = make(settings)
    with c:
        assert meta(chat(c, "a", "fresh question", headers={"X-Simulate-Failure": "key_1=500"}))["key_id"] == "key_2"
        assert meta(chat(c, "b", "fresh question"))["resolution_source"] == "LIVE_INFERENCE"
        assert meta(chat(c, "c", "fresh question"))["resolution_source"] == "LLM_CACHE"


def test_simulation_header_ignored_when_disabled_so_cache_still_hits(settings):
    c, _ = make(settings, enable_failure_simulation=False)
    with c:
        chat(c, "a")
        assert meta(chat(c, "b", headers={"X-Simulate-Failure": "*=429"}))["resolution_source"] == "LLM_CACHE"


# ---- switch / health -------------------------------------------------------------------------------

def test_cache_disabled_never_hits_and_health_says_so(settings):
    c, _ = make(settings, cache_enabled=False)
    with c:
        assert meta(chat(c, "a"))["resolution_source"] == "LIVE_INFERENCE"
        assert meta(chat(c, "b"))["resolution_source"] == "LIVE_INFERENCE"
        assert c.get("/health").json() == {"status": "ok", "keys_configured": 2, "cache_enabled": False}


def test_health_reports_cache_enabled(settings):
    c, _ = make(settings)
    with c:
        assert c.get("/health").json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_warmup_entry_never_served_to_users(settings):
    c, _ = make(settings)
    with c:
        r = chat(c, "a", "__cis_cache_warmup__")
    assert meta(r)["resolution_source"] == "LIVE_INFERENCE" and r.json()["reply"] != "warmup"


# ---- global cache lifecycle (LiteLLM's cache is process-wide) ------------------------------------

def test_second_client_does_not_reset_running_cache(settings):
    c1, _ = make(settings)
    with c1:
        chat(c1, "a")                                   # cached by the running app
        make(settings)                                  # another client is created meanwhile
        make(settings, cache_enabled=False)             # ... even one with caching disabled
        assert meta(chat(c1, "b"))["resolution_source"] == "LLM_CACHE"
        assert c1.get("/health").json()["cache_enabled"] is True


def test_cache_disabled_client_never_reads_or_writes_shared_cache(settings):
    on, _ = make(settings)
    off, _ = make(settings, cache_enabled=False)
    with on, off:
        chat(on, "a", "shared question")                # enabled app caches it
        assert meta(chat(off, "b", "shared question"))["resolution_source"] == "LIVE_INFERENCE"
        chat(off, "c", "only the disabled app saw this")
        assert meta(chat(on, "d", "only the disabled app saw this"))["resolution_source"] == "LIVE_INFERENCE"


def test_init_cache_is_idempotent():
    import litellm
    from app.llm import init_cache

    assert init_cache() is True
    first = litellm.cache
    assert init_cache() is True
    assert litellm.cache is first                       # same object: never replaced


def test_health_reports_actual_cache_state(settings):
    import litellm
    c, _ = make(settings)
    with c:
        assert c.get("/health").json()["cache_enabled"] is True
        litellm.cache = None                            # cache lost at runtime
        assert c.get("/health").json()["cache_enabled"] is False


def test_broken_cache_degrades_to_live_inference_not_503(settings, monkeypatch):
    import app.llm as llm

    def boom():
        raise ModuleNotFoundError("simulated missing cache dependency")

    monkeypatch.setattr(llm, "_verify_cache_roundtrip", boom)
    c, _ = make(settings)
    with c:
        assert c.get("/health").json()["cache_enabled"] is False
        assert meta(chat(c, "a"))["resolution_source"] == "LIVE_INFERENCE"
        assert meta(chat(c, "b"))["resolution_source"] == "LIVE_INFERENCE"


# ---- SQLite persistence across restarts -------------------------------------------------------------

def test_history_survives_restart_and_session_continues(settings):
    c1, _ = make(settings)
    with c1:
        chat(c1, "keep", "first question")
        chat(c1, "keep", "second question")
    c2, p2 = make(settings)                             # same DB file, fresh app + cache
    with c2:
        msgs = c2.get("/sessions/keep/messages").json()["messages"]
        assert [m["content"] for m in msgs if m["role"] == "user"] == ["first question", "second question"]
        assert all(m["metadata"]["resolution_source"] == "LIVE_INFERENCE" for m in msgs if m["role"] == "assistant")
        chat(c2, "keep", "third question")
        sent = p2.calls[-1]["messages"]                 # history was reloaded into the LLM call
        assert [m["content"] for m in sent if m["role"] == "user"] == ["first question", "second question", "third question"]
