"""LLM client: LiteLLM calls over a pool of API keys with sequential failover.

Each request tries key_1, key_2, ... in order. Any provider failure on a key
(429 / quota, 5xx, connection errors, timeouts, auth errors, empty replies) moves on to
the next key. The first success returns its key_id and how many keys failed before it.
If every key fails, AllProvidersUnavailable is raised and the API answers HTTP 503.
Provider error text is never logged or returned, because it can echo key fragments.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

import litellm
from litellm.caching.caching import Cache, CacheMode

from .config import Settings
from .simulation import build_exception, status_for

litellm.suppress_debug_info = True
log = logging.getLogger("cis.llm")


# ---- process-wide LiteLLM cache ------------------------------------------------------
#
# LiteLLM's cache is a module-global (`litellm.cache`). It is therefore initialised once
# per process, under a lock, and is never replaced or disabled by constructing another
# LiteLLMClient. The cache runs in "default_off" mode: a call only touches it when that
# call explicitly opts in (cache={"use-cache": True}), so a client with caching disabled,
# or a simulated-failure request, can never read from or write to it.

_cache_lock = threading.Lock()
_PROBE_MODEL = "nvidia_nim/nvidia/nemotron-3.5-bolt-e4b"


def _new_cache() -> Cache:
    return Cache(type="local", mode=CacheMode.default_off)


def _verify_cache_roundtrip() -> bool:
    """Run one miss + one hit through the real LiteLLM cache path using mock_response.

    This pays LiteLLM's lazy imports up front (so the first real cache hit is fast) and
    proves cache hits actually work in this environment, instead of failing request-by-request.
    """
    probe = [{"role": "user", "content": "__cis_cache_probe__"}]
    hit = None
    for _ in range(2):
        resp = litellm.completion(
            model=_PROBE_MODEL, messages=probe, api_key="probe", mock_response="probe",
            num_retries=0, cache={"use-cache": True},
        )
        hit = (getattr(resp, "_hidden_params", None) or {}).get("cache_hit")
    return bool(hit)


def init_cache() -> bool:
    """Enable LiteLLM's in-memory cache once for this process. Idempotent: an existing
    cache (and its entries) is never reset. Returns True when a working cache is active."""
    with _cache_lock:
        if isinstance(litellm.cache, Cache):
            return True
        try:
            litellm.cache = _new_cache()  # throwaway: holds only the probe entry
            ok = _verify_cache_roundtrip()
        except Exception as exc:  # noqa: BLE001
            ok = False
            log.error("cache self-test failed (%s)", type(exc).__name__)
        if not ok:
            litellm.cache = None
            log.error("LiteLLM cache hits are not working here; running without cache")
            return False
        litellm.cache = _new_cache()  # fresh and empty: the probe entry is never served
        return True


def reset_cache() -> None:
    """Drop the process-wide cache (tests / explicit operator reset only)."""
    with _cache_lock:
        litellm.cache = None


def cache_active() -> bool:
    return isinstance(litellm.cache, Cache)


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
        # Never touches an already-running cache; see init_cache().
        self._cache_enabled = bool(settings.cache_enabled) and init_cache()

    @property
    def cache_enabled(self) -> bool:
        """True only while this client uses a working LiteLLM cache (reported by /health)."""
        return self._cache_enabled and cache_active()

    def complete(
        self, messages: list[dict], simulate_failure: Optional[dict[str, int]] = None
    ) -> LLMResult:
        started = time.perf_counter()
        failures = 0
        # While failure simulation is active the cache is bypassed (no read, no write), so a
        # cached answer can never hide the requested provider failures, and a simulated
        # request leaves no cache entry behind.
        use_cache = self.cache_enabled and not simulate_failure
        for key in self._keys:
            kwargs: dict = {
                "model": self._model,
                "messages": messages,
                "api_key": key.secret,
                "timeout": self._timeout,
                "num_retries": 0,  # failover across keys replaces same-key retries
            }
            if use_cache:
                kwargs["cache"] = {"use-cache": True}  # opt in (cache is default_off)
            else:
                # Cache disabled or simulated failure: no read and no write. Explicit even
                # though the cache is opt-in, so it holds if the cache mode ever changes.
                kwargs["cache"] = {"no-cache": True, "no-store": True}
            status = status_for(key.key_id, simulate_failure)
            if status is not None:
                # The failure is raised by LiteLLM itself, so the real fallback path runs.
                kwargs["mock_response"] = build_exception(status, self._model)
            try:
                response = self._completion(**kwargs)
                reply = (response.choices[0].message.content or "").strip()
                if not reply:
                    raise ValueError("empty completion")
                usage = response.usage  # on a cache hit: the usage stored with the cached response
                cache_hit = bool(use_cache and (getattr(response, "_hidden_params", None) or {}).get("cache_hit"))
                return LLMResult(
                    reply=reply,
                    resolution_source="LLM_CACHE" if cache_hit else "LIVE_INFERENCE",
                    model=self._model,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    input_tokens=int(usage.prompt_tokens),
                    output_tokens=int(usage.completion_tokens),
                    key_id=None if cache_hit else key.key_id,
                    fallback_attempts=0 if cache_hit else failures,
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
