from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.router import api_router
from .config import get_settings
from .dependencies import get_store
from .exceptions import APIError
from .schemas import ErrorEnvelope, ErrorInfo
from .utils import new_trace_id


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        get_store().close()


async def trace_id_middleware(request: Request, call_next):
    request.state.trace_id = request.headers.get("X-Trace-Id") or new_trace_id()
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    payload = ErrorEnvelope(
        trace_id=getattr(request.state, "trace_id", new_trace_id()),
        error=ErrorInfo(
            code=exc.code,
            message=exc.message,
            retryable=exc.retryable,
            details=[
                {"field": item.get("field"), "message": str(item.get("message"))}
                for item in exc.details
            ],
        ),
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    payload = ErrorEnvelope(
        trace_id=getattr(request.state, "trace_id", new_trace_id()),
        error=ErrorInfo(
            code="invalid_request",
            message="Request validation failed",
            retryable=False,
            details=[
                {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
                for item in exc.errors()
            ],
        ),
    )
    return JSONResponse(status_code=400, content=payload.model_dump())


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    payload = ErrorEnvelope(
        trace_id=getattr(request.state, "trace_id", new_trace_id()),
        error=ErrorInfo(code="internal_error", message=str(exc), retryable=False, details=[]),
    )
    return JSONResponse(status_code=500, content=payload.model_dump())


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
