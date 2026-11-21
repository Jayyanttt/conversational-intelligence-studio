"""X-Simulate-Failure header parsing and LiteLLM exception construction."""
from __future__ import annotations

import litellm

ALLOWED_STATUSES = {429, 500, 502, 503}

_EXC_BY_STATUS = {
    429: litellm.RateLimitError,
    500: litellm.InternalServerError,
    502: litellm.BadGatewayError,
    503: litellm.ServiceUnavailableError,
}


class InvalidSimulationHeader(ValueError):
    pass


def parse_simulate_header(raw: str | None) -> dict[str, int] | None:
    """'key_1=429,key_2=500' / '*=429' -> {'key_1': 429, ...}. None when absent/blank."""
    if raw is None or not raw.strip():
        return None
    out: dict[str, int] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        key, sep, status = part.partition("=")
        key, status = key.strip(), status.strip()
        if not sep or not key or not status.isdigit() or int(status) not in ALLOWED_STATUSES:
            raise InvalidSimulationHeader(
                "X-Simulate-Failure must be comma-separated <key_id>=<status> pairs "
                "(status one of 429, 500, 502, 503; '*' matches every key)"
            )
        out[key] = int(status)
    return out or None


def status_for(key_id: str, simulate: dict[str, int] | None) -> int | None:
    """Explicit key entry wins over the '*' wildcard."""
    if not simulate:
        return None
    return simulate.get(key_id, simulate.get("*"))


def build_exception(status: int, model: str) -> Exception:
    """A genuine LiteLLM exception, raised from inside litellm.completion via mock_response."""
    provider = model.split("/", 1)[0] if "/" in model else "unknown"
    return _EXC_BY_STATUS[status](
        message=f"simulated provider failure (HTTP {status})", llm_provider=provider, model=model
    )
