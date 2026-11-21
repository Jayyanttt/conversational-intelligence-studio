"""LLM client: LiteLLM calls over a pool of API keys with sequential failover.

Each request tries key_1, key_2, ... in order. Any provider failure on a key
(429 / quota, 5xx, connection errors, timeouts, auth errors, empty replies) moves on to
the next key. The first success returns its key_id and how many keys failed before it.
If every key fails, AllProvidersUnavailable is raised and the API answers HTTP 503.
Provider error text is never logged or returned, because it can echo key fragments.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

import litellm

from .config import Settings
from .simulation import build_exception, status_for

litellm.suppress_debug_info = True
log = logging.getLogger("cis.llm")


class AllProvidersUnavailable(Exception):
    """Every configured key failed (or none are usable)."""


@dataclass
class LLMResult:
    reply: str
    resolution_source: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: Optional[str]
    fallback_attempts: int

    def metadata(self) -> dict:
        return {
            "resolution_source": self.resolution_source,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "key_id": self.key_id,
            "fallback_attempts": self.fallback_attempts,
        }


class LLMClient(Protocol):
    def complete(
        self, messages: list[dict], simulate_failure: Optional[dict[str, int]] = None
    ) -> LLMResult: ...


class LiteLLMClient:
    def __init__(
        self,
        settings: Settings,
        completion_fn: Optional[Callable[..., object]] = None,
        timeout: float = 30.0,
    ):
        self._keys = settings.api_keys
        self._model = settings.model
        self._timeout = timeout
        self._completion = completion_fn or litellm.completion  # injectable for tests

    def complete(
        self, messages: list[dict], simulate_failure: Optional[dict[str, int]] = None
    ) -> LLMResult:
        started = time.perf_counter()
        failures = 0
        for key in self._keys:
            kwargs: dict = {
                "model": self._model,
                "messages": messages,
                "api_key": key.secret,
                "timeout": self._timeout,
                "num_retries": 0,  # failover across keys replaces same-key retries
            }
            status = status_for(key.key_id, simulate_failure)
            if status is not None:
                # The failure is raised by LiteLLM itself, so the real fallback path runs.
                kwargs["mock_response"] = build_exception(status, self._model)
            try:
                response = self._completion(**kwargs)
                reply = (response.choices[0].message.content or "").strip()
                if not reply:
                    raise ValueError("empty completion")
                usage = response.usage
                return LLMResult(
                    reply=reply,
                    resolution_source="LIVE_INFERENCE",
                    model=self._model,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    input_tokens=int(usage.prompt_tokens),
                    output_tokens=int(usage.completion_tokens),
                    key_id=key.key_id,
                    fallback_attempts=failures,
                )
            except Exception as exc:  # noqa: BLE001 - any provider failure triggers failover
                failures += 1
                log.warning(
                    "%s failed (%s, status=%s); %s",
                    key.key_id,
                    type(exc).__name__,
                    getattr(exc, "status_code", None),
                    "trying next key" if failures < len(self._keys) else "no keys left",
                )
        raise AllProvidersUnavailable()
