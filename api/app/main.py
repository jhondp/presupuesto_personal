import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import ApiError, error_response
from app.routes import account, profile


def create_app() -> FastAPI:
    app = FastAPI(title="Personal Finance API", version="0.1.0")

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, error: ApiError) -> JSONResponse:
        # Error responses always carry a trace identifier; successful responses do not log request data.
        request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        return error_response(request, error)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, error: Exception) -> JSONResponse:
        # Safety net so every failure — not just ApiError — returns the stable
        # {code, message, field_errors, request_id} envelope. The raw exception
        # text is never leaked to the client; it is only available server-side
        # via the ASGI server's own logging.
        request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        return error_response(
            request,
            ApiError(500, "internal_error", "An unexpected error occurred"),
        )

    app.include_router(profile.router, prefix="/v1")
    app.include_router(account.router, prefix="/v1")
    return app


app = create_app()
