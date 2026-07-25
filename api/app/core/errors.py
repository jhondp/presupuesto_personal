from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, field_errors: dict[str, str] | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors or {}


def error_response(request: Request, error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "code": error.code,
            "message": error.message,
            "field_errors": error.field_errors,
            "request_id": request.state.request_id,
        },
    )
