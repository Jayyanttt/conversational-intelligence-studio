"""Request/response models. Field names follow the assignment contract exactly."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

AnalystType = Literal["customer", "workplace", "patterns"]
ResolutionSource = Literal["LIVE_INFERENCE", "LLM_CACHE"]


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., max_length=4000 * 4)  # real limit enforced after trim below
    system_prompt: Optional[str] = None
    analyst_type: Optional[AnalystType] = None

    @field_validator("session_id")
    @classmethod
    def _session_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("session_id must not be blank")
        return v

    @field_validator("message")
    @classmethod
    def _message_trimmed(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 4000):
            raise ValueError("message must be 1-4000 characters after trimming")
        return v

    @field_validator("system_prompt")
    @classmethod
    def _blank_prompt_is_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        return v.strip()


class Metadata(BaseModel):
    resolution_source: ResolutionSource
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: Optional[str]
    fallback_attempts: int


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: Metadata


class StoredMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    metadata: Optional[Metadata] = None


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[StoredMessage]
