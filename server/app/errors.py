"""Consistent error responses shared across routers.

`fail()` builds an ``HTTPException`` whose ``detail`` already carries the
``{"error": {...}}`` envelope; ``http_exception_handler`` renders that envelope
verbatim (and wraps plain-string details in the same shape).
"""

from typing import cast

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


def fail(status_code: int, code: str, message: str, **details: object) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message, "details": details}},
    )


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(HTTPException, exc)
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "REQUEST_FAILED", "message": str(exc.detail), "details": {}}},
    )
