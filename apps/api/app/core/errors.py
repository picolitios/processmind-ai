import logging
import uuid

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "correlation_id": correlation_id},
    )


def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(request, exc.status_code, exc.code, exc.message)


def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return error_response(request, exc.status_code, "http_error", str(exc.detail))


def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(request, 422, "validation_error", "Dados inválidos")


def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled API error: %s (correlation_id=%s)",
        type(exc).__name__,
        getattr(request.state, "correlation_id", "unknown"),
    )
    return error_response(request, 500, "internal_error", "Erro interno")
