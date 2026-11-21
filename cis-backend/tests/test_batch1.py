"""Batch 1 tests. The LLM is mocked (FakeLLM); no real provider is called."""
from fastapi.testclient import TestClient

from app.config import parse_api_keys, parse_database_path
from app.main import create_app

META_FIELDS = {"resolution_source", "model", "latency_ms", "input_tokens", "output_tokens", "key_id", "fallback_attempts"}


def chat(client, sid="s1", msg="hello", **extra):
    return client.post("/chat", json={"session_id": sid, "message": msg, **extra})


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_health_503_without_keys(settings, fake_llm):
    from dataclasses import replace
    with TestClient(create_app(replace(settings, api_keys=()), fake_llm)) as c:
        assert c.get("/health").status_code == 503


def test_key_parsing_ids_in_order_and_hidden_in_repr():
    keys = parse_api_keys(" a , b,,c ")
    assert [k.key_id for k in keys] == ["key_1", "key_2", "key_3"]
    assert "a" not in repr(keys[0]).replace("key_1", "")


def test_database_url_parsing():
    assert parse_database_path("sqlite:////data/app.db") == "/data/app.db"
    assert parse_database_path("sqlite:///./x.db") == "./x.db"


def test_chat_success_returns_contract(client):
    r = chat(client)
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s1" and body["reply"] == "echo:hello"
    assert set(body["metadata"]) == META_FIELDS


def test_empty_and_whitespace_message_422(client):
    assert chat(client, msg="").status_code == 422
    assert chat(client, msg="   \n ").status_code == 422


def test_overlong_message_422_but_4000_ok(client):
    assert chat(client, msg="a" * 4001).status_code == 422
    assert chat(client, msg=" " + "a" * 4000 + " ").status_code == 200


def test_bad_session_ids_422(client):
    assert chat(client, sid="").status_code == 422
    assert chat(client, sid="   ").status_code == 422
    assert chat(client, sid="s" * 129).status_code == 422
    assert chat(client, sid="s" * 128).status_code == 200


def test_malformed_json_and_unknown_analyst_422(client):
    r = client.post("/chat", content="{bad", headers={"content-type": "application/json"})
    assert r.status_code == 422 and "detail" in r.json()
    assert chat(client, analyst_type="nope").status_code == 422


def test_multi_turn_history_sent_to_llm_and_session_separation(client, fake_llm):
    chat(client, "a", "one")
    chat(client, "a", "two")
    chat(client, "b", "other")
    second = fake_llm.calls[1]["messages"]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "user"]
    assert second[1]["content"] == "one" and second[-1]["content"] == "two"
    assert [m["role"] for m in fake_llm.calls[2]["messages"]] == ["system", "user"]


def test_history_endpoint_order_metadata_and_no_system_prompt(client):
    chat(client, "a", "one", system_prompt="SECRET PROMPT")
    chat(client, "a", "two")
    r = client.get("/sessions/a/messages")
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert [m["content"] for m in msgs] == ["one", "echo:one", "two", "echo:two"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert "metadata" not in msgs[0]
    assert set(msgs[1]["metadata"]) == META_FIELDS
    assert "SECRET PROMPT" not in r.text


def test_unknown_session_404(client):
    r = client.get("/sessions/nope/messages")
    assert r.status_code == 404 and r.json() == {"detail": "session not found"}


def test_persistence_survives_app_restart(settings, fake_llm):
    with TestClient(create_app(settings, fake_llm)) as c1:
        chat(c1, "p", "remember me")
    with TestClient(create_app(settings, fake_llm)) as c2:
        msgs = c2.get("/sessions/p/messages").json()["messages"]
        assert msgs[0]["content"] == "remember me"
        assert msgs[1]["metadata"]["key_id"] == "key_1"


def test_failed_request_not_persisted_and_returns_503(client, fake_llm):
    fake_llm.fail = True
    r = chat(client, "f", "x")
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
    assert client.get("/sessions/f/messages").status_code == 404
    fake_llm.fail = False
    chat(client, "f", "ok")
    fake_llm.fail = True
    chat(client, "f", "bad")
    assert len(client.get("/sessions/f/messages").json()["messages"]) == 2


def test_default_client_with_no_keys_gives_503_not_fake_answer(settings):
    from dataclasses import replace
    with TestClient(create_app(replace(settings, api_keys=()))) as c:
        r = chat(c)
        assert r.status_code == 503 and r.json()["detail"] == "all providers unavailable"


def test_unhandled_error_is_json_without_trace(settings):
    class Boom:
        def complete(self, *a, **k):
            raise RuntimeError("secret internal detail")
    with TestClient(create_app(settings, Boom()), raise_server_exceptions=False) as c:
        r = chat(c)
        assert r.status_code == 500 and r.json() == {"detail": "internal server error"}


def test_simulate_header_only_forwarded_when_enabled(settings, fake_llm):
    from dataclasses import replace
    with TestClient(create_app(settings, fake_llm)) as c:
        c.post("/chat", json={"session_id": "s", "message": "m"}, headers={"X-Simulate-Failure": "key_1=429"})
    assert fake_llm.calls[-1]["simulate_failure"] == {"key_1": 429}
    with TestClient(create_app(replace(settings, enable_failure_simulation=False), fake_llm)) as c:
        c.post("/chat", json={"session_id": "s2", "message": "m"}, headers={"X-Simulate-Failure": "key_1=429"})
    assert fake_llm.calls[-1]["simulate_failure"] is None


def test_prompt_precedence_and_persistence_across_turns(client, fake_llm):
    chat(client, "x", "q1", analyst_type="workplace")
    assert "Workplace Intelligence Analyst" in fake_llm.calls[-1]["messages"][0]["content"]
    chat(client, "x", "q2")  # no prompt supplied -> stored prompt continues
    assert "Workplace Intelligence Analyst" in fake_llm.calls[-1]["messages"][0]["content"]
    chat(client, "x", "q3", system_prompt="CUSTOM", analyst_type="workplace")  # new prompt wins
    assert fake_llm.calls[-1]["messages"][0]["content"] == "CUSTOM"
    chat(client, "x", "q4")
    assert fake_llm.calls[-1]["messages"][0]["content"] == "CUSTOM"
    assert len(fake_llm.calls[-1]["messages"]) == 1 + 6 + 1  # history preserved
    chat(client, "y", "q")
    assert "careful conversation analyst" in fake_llm.calls[-1]["messages"][0]["content"]


def test_cors_allows_configured_origin(client):
    r = client.options("/chat", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-simulate-failure,content-type",
    })
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
