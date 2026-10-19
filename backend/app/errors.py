"""One error format for every API response that fails:

    {"error": {"code": "recipe_not_found", "message": "...", "details": null}}

`code` is stable and meant for the frontend to branch on; `message` is for
people; `details` carries extra data, such as which fields were invalid.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    """The documented shape of every error response (shown at /docs)."""

    error: ErrorBody


# For routers: responses={**ERROR_RESPONSES}, so /docs shows the real error shape.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not found"},
    422: {"model": ErrorResponse, "description": "Invalid request"},
}


class ApiError(Exception):
    """Raise from an endpoint to return a specific error, e.g. ApiError(404, "recipe_not_found", "...")."""

    def __init__(self, status_code: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(
    status_code: int, code: str, message: str, details: Any = None, headers: dict[str, str] | None = None
) -> JSONResponse:
    content = {"error": {"code": code, "message": message, "details": jsonable_encoder(details)}}
    return JSONResponse(status_code=status_code, content=content, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    """Make FastAPI's own errors use the same format as ours."""

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # For example /api/recipes/abc, where the id must be a number. `details` lists each problem.
        return error_response(422, "invalid_request", "The request is not valid.", exc.errors())

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # FastAPI's built-in errors, such as an unknown path (404) or a wrong method (405).
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail), headers=exc.headers)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # A bug, not a bad request. The server log already shows the full traceback
        # (uvicorn prints it), so the browser only gets a generic message.
        return error_response(500, "internal_error", "Something went wrong on the server.")
