"""FastAPI application: /health, POST /chat, GET /sessions/{id}/messages."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings, load_settings
from .db import Database
from .llm import AllProvidersUnavailable, LLMClient, UnconfiguredClient
from .prompts import resolve_system_prompt
from .schemas import ChatRequest, ChatResponse, HistoryResponse

log = logging.getLogger("cis")


def create_app(settings: Optional[Settings] = None, llm_client: Optional[LLMClient] = None) -> FastAPI:
    settings = settings or load_settings()
    db = Database(settings.database_path)
    client: LLMClient = llm_client or UnconfiguredClient()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init_schema()
        log.info("CIS backend started: %d key(s) configured", len(settings.api_keys))
        yield

    app = FastAPI(title="Conversational Intelligence Studio API", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["*"],
        allow_headers=["*"],  # includes X-Simulate-Failure
    )

    # ---- error shapes: always JSON with `detail` ------------------------------

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(_: Request, exc: StarletteHTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(_: Request, exc: RequestValidationError):
        detail = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        return JSONResponse({"detail": detail}, status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")  # logs trace server-side only
        return JSONResponse({"detail": "internal server error"}, status_code=500)

    # ---- routes ---------------------------------------------------------------

    @app.get("/health")
    def health():
        db_ok = db.ping()
        keys = len(settings.api_keys)
        if not db_ok or keys < 1:
            return JSONResponse(
                {
                    "status": "error",
                    "detail": "database unreachable" if not db_ok else "no api keys configured",
                    "keys_configured": keys,
                    "cache_enabled": settings.cache_enabled,
                },
                status_code=503,
            )
        return {"status": "ok", "keys_configured": keys, "cache_enabled": settings.cache_enabled}

    @app.post("/chat", response_model=ChatResponse)
    def chat(
        body: ChatRequest,
        x_simulate_failure: Optional[str] = Header(default=None),
    ):
        session = db.get_session(body.session_id)
        stored_prompt = session["system_prompt"] if session else None
        effective_prompt = resolve_system_prompt(body.system_prompt, body.analyst_type, stored_prompt)

        history = [{"role": m["role"], "content": m["content"]} for m in db.get_history(body.session_id)]
        messages = (
            [{"role": "system", "content": effective_prompt}]
            + history
            + [{"role": "user", "content": body.message}]
        )

        simulate = x_simulate_failure if settings.enable_failure_simulation else None
        try:
            result = client.complete(messages, simulate_failure=simulate)
        except AllProvidersUnavailable:
            # Nothing is persisted for failed requests.
            return JSONResponse({"detail": "all providers unavailable"}, status_code=503)

        metadata = result.metadata()
        db.save_turn(
            session_id=body.session_id,
            user_message=body.message,
            assistant_reply=result.reply,
            metadata=metadata,
            analyst_type=body.analyst_type,
            system_prompt=effective_prompt,
        )
        return {"session_id": body.session_id, "reply": result.reply, "metadata": metadata}

    @app.get("/sessions/{session_id}/messages", response_model=HistoryResponse, response_model_exclude_unset=True)
    def session_messages(session_id: str):
        if db.get_session(session_id) is None:
            return JSONResponse({"detail": "session not found"}, status_code=404)
        return {"session_id": session_id, "messages": db.get_history(session_id)}

    return app
