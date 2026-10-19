"""Typed errors mapped to problem responses with stable codes (docs/07-api-spec.md)."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    code = "error"
    status = 500
    title = "Something went wrong"

    def __init__(self, detail: str = "", *, code: str | None = None, status: int | None = None) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        if code:
            self.code = code
        if status:
            self.status = status


class NotFound(AppError):
    code, status, title = "not_found", 404, "Not found"


class InvalidWorkspace(AppError):
    code, status, title = "invalid_workspace", 401, "Missing or invalid workspace token"


class RateLimited(AppError):
    code, status, title = "rate_limited", 429, "Too many requests, try again later"


class ValidationFailed(AppError):
    code, status, title = "validation_error", 422, "Invalid input"


class Conflict(AppError):
    code, status, title = "conflict", 409, "Conflict"


# Qloo (fatal to the scout phase)
class QlooError(AppError):
    code, status, title = "qloo_unavailable", 502, "Qloo is unavailable"


class QlooUnconfigured(QlooError):
    code, status, title = "qloo_unconfigured", 503, "Qloo API key is not configured. TasteRoute cannot rank venues without Qloo."


class QlooAuthError(QlooError):
    code, status, title = "qloo_auth", 502, "Qloo rejected the API key. TasteRoute cannot rank venues without Qloo."


class QlooRateLimited(QlooError):
    code, status, title = "qloo_rate_limited", 503, "Qloo rate limit reached"


class QlooBadRequest(QlooError):
    code, status, title = "qloo_bad_request", 502, "Qloo rejected the request"


class QlooBudgetExceeded(QlooError):
    code, status, title = "qloo_budget_exceeded", 429, "Qloo call budget reached"


class QlooContractViolation(QlooError):
    code, status, title = "qloo_contract_violation", 502, "Qloo returned data that does not match the request"


class LLMUnavailable(AppError):
    code, status, title = "llm_unavailable", 503, "The language model is unavailable"


class LLMBadResponse(AppError):
    code, status, title = "llm_bad_response", 502, "The language model returned invalid output"


def problem(status: int, code: str, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        {"type": f"https://tasteroute.app/errors/{code}", "title": title, "status": status, "detail": detail, "code": code},
        status_code=status,
        media_type="application/problem+json",
    )


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return problem(exc.status, exc.code, exc.title, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        return problem(422, "validation_error", "Invalid input", detail)
