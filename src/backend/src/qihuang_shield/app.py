from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.router import api_router
from .config import get_settings
from .dependencies import get_exception_mapper, get_store, get_trace_service
from .exceptions import APIError
from .utils import new_trace_id


settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        get_store().close()


async def trace_id_middleware(request: Request, call_next):
    trace_service = get_trace_service()
    request.state.trace_id = request.headers.get("X-Trace-Id") or new_trace_id()
    trace_token = trace_service.bind_trace_id(request.state.trace_id)
    try:
        response = await call_next(request)
    finally:
        trace_service.reset_trace_id(trace_token)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", new_trace_id())
    status_code, payload = get_exception_mapper().to_error_envelope(exc, trace_id=trace_id)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", new_trace_id())
    status_code, payload = get_exception_mapper().to_error_envelope(exc, trace_id=trace_id)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error", exc_info=exc)
    trace_id = getattr(request.state, "trace_id", new_trace_id())
    status_code, payload = get_exception_mapper().to_error_envelope(exc, trace_id=trace_id)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def create_app() -> FastAPI:
    app = FastAPI(
        title="QiHuang Shield API",
        version="0.1.0",
        summary="QiHuang Shield MVP API skeleton",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Trace-Id"],
    )
    app.middleware("http")(trace_id_middleware)
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router)
    return app


app = create_app()
