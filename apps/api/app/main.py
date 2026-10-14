import uuid
from collections.abc import Awaitable, Callable

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
from app.db.engine import make_engine
from app.features.ai.routes import router as ai_router
from app.features.audit.routes import router as audit_router
from app.features.identity.routes import auth_router, organizations_router
from app.features.ingestion.routes import router as ingestion_router

app = FastAPI(title="ProcessMind AI API", version="0.1.0")
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
app.include_router(auth_router)
app.include_router(organizations_router)
app.include_router(ingestion_router)
app.include_router(audit_router)
app.include_router(ai_router)


@app.middleware("http")
async def correlation_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request.state.correlation_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = request.state.correlation_id
    if request.url.path.startswith("/api/v1/auth/"):
        response.headers["Cache-Control"] = "no-store"
    return response


class Health(BaseModel):
    status: str


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
    return Health(status="ok")
