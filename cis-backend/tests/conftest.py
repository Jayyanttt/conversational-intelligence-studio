import pytest
from fastapi.testclient import TestClient

from app.config import ApiKey, Settings
from app.llm import AllProvidersUnavailable, LLMResult
from app.main import create_app


class FakeLLM:
    """Test double standing in for the LiteLLM client (mocked, no network)."""

    def __init__(self):
        self.calls = []
        self.fail = False

    def complete(self, messages, simulate_failure=None):
        self.calls.append({"messages": messages, "simulate_failure": simulate_failure})
        if self.fail:
            raise AllProvidersUnavailable()
        return LLMResult(
            reply=f"echo:{messages[-1]['content']}",
            resolution_source="LIVE_INFERENCE",
            model="fake/model",
            latency_ms=5,
            input_tokens=len(messages) * 10,
            output_tokens=3,
            key_id="key_1",
            fallback_attempts=0,
        )


@pytest.fixture
def settings(tmp_path):
    return Settings(
        api_keys=(ApiKey("key_1", "x1"), ApiKey("key_2", "x2")),
        database_path=str(tmp_path / "app.db"),
        allowed_origins=("http://localhost:3000",),
        enable_failure_simulation=True,
        cache_enabled=True,
        model="fake/model",
    )


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def client(settings, fake_llm):
    with TestClient(create_app(settings, fake_llm), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def _fresh_litellm_cache():
    """LiteLLM's cache is process-global; every test starts and ends without one."""
    from app.llm import reset_cache

    reset_cache()
    yield
    reset_cache()
