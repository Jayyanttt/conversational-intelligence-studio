"""LLM client interface.

Batch 1: only the interface and a placeholder client exist. The placeholder never
fabricates an answer; it reports every provider as unavailable (-> HTTP 503).
Batch 2 replaces it with the LiteLLM key-pool client with failover.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


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
    def complete(self, messages: list[dict], simulate_failure: Optional[str] = None) -> LLMResult: ...


class UnconfiguredClient:
    def complete(self, messages: list[dict], simulate_failure: Optional[str] = None) -> LLMResult:
        raise AllProvidersUnavailable()
