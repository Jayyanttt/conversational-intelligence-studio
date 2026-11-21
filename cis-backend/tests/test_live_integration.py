"""REAL-PROVIDER integration tests (not mocked, cost real quota).

Skipped unless RUN_LIVE_TESTS=1 and LLM_API_KEYS (>=2 real keys) are set:
    RUN_LIVE_TESTS=1 LLM_API_KEYS=k1,k2 pytest -m live
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.config import ApiKey, Settings, parse_api_keys
from app.main import create_app

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="set RUN_LIVE_TESTS=1 to run live tests"),
]


@pytest.fixture
def live_client(tmp_path):
    keys = parse_api_keys(os.getenv("LLM_API_KEYS"))
    assert len(keys) >= 2, "need at least two real keys"
    s = Settings(keys, str(tmp_path / "live.db"), ("http://localhost:3000",), True, True,
                 os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash"))
    with TestClient(create_app(s)) as c:
        yield c


def test_live_answer(live_client):
    r = live_client.post("/chat", json={"session_id": "live1", "message": "What is the capital of France? One word."})
    assert r.status_code == 200
    m = r.json()["metadata"]
    assert "paris" in r.json()["reply"].lower() and m["key_id"] == "key_1" and m["input_tokens"] > 0


def test_live_failover_returns_real_answer_from_key_2(live_client):
    r = live_client.post("/chat", json={"session_id": "live2", "message": "Say hello."},
                         headers={"X-Simulate-Failure": "key_1=429"})
    assert r.status_code == 200 and r.json()["metadata"]["key_id"] == "key_2"
