import uuid
from collections.abc import Awaitable, Callable
from time import perf_counter

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from app.core.observability import current_correlation_id, log_request
from app.db.engine import make_engine


class Health(BaseModel):
    status: str


def identity_ready() -> bool:
    """Probe the required identity boundary without sending session data."""
    try:
        with httpx.Client(timeout=2, trust_env=False) as client:
            response = client.get(
                f"{settings.identity_internal_url.rstrip('/')}/api/v1/health/ready"
            )
        return (
            response.status_code == 200
            and response.headers.get("X-ProcessMind-Service") == "identity"
            and response.json() == {"status": "ok"}
        )
    except (httpx.RequestError, ValueError):
        return False


def configure_http(app: FastAPI, service_name: str | None = None) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
    )
    app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unexpected_error_handler)

    @app.middleware("http")
    async def correlation_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.correlation_id = str(uuid.uuid4())
        context_token = current_correlation_id.set(request.state.correlation_id)
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Correlation-ID"] = request.state.correlation_id
            if request.url.path.startswith("/api/v1/"):
                response.headers["Cache-Control"] = "no-store"
            if service_name:
                response.headers["X-ProcessMind-Service"] = service_name
            return response
        finally:
            route = request.scope.get("route")
            try:
                log_request(
                    service_name or "business",
                    request.state.correlation_id,
                    request.method,
                    route.path if route is not None else "unmatched",
                    status_code,
                    (perf_counter() - started) * 1000,
                )
            finally:
                current_correlation_id.reset(context_token)

    @app.get("/api/v1/health/live", response_model=Health)
    def live() -> Health:
        return Health(status="ok")

    @app.get("/api/v1/health/ready", response_model=Health)
    def ready(response: Response) -> Health:
        try:
            with make_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            response.status_code = 503
            return Health(status="unavailable")
        if service_name != "identity" and settings.business_auth_mode == "identity":
            if not identity_ready():
                response.status_code = 503
                return Health(status="unavailable")
        return Health(status="ok")
