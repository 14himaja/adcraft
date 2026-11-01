from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    status: int = 500
    code: str = "INTERNAL"

    def __init__(self, message: str = "", details: dict | None = None):
        super().__init__(message)
        self.message = message or self.code
        self.details = details or {}


class NotFound(AppError):
    status, code = 404, "NOT_FOUND"


class Unauthenticated(AppError):
    status, code = 401, "UNAUTHENTICATED"


class EmailTaken(AppError):
    status, code = 409, "EMAIL_TAKEN"


class RateLimited(AppError):
    status, code = 429, "RATE_LIMITED"


def _envelope(code: str, message: str, details: dict, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": details}}, status_code=status)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return _envelope(exc.code, exc.message, exc.details, exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _envelope("VALIDATION_FAILED", "Request validation failed", {"errors": errors}, 422)
