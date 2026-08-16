"""Oahu Trip — family vacation planner. FastAPI app.

API routes first, then the static frontend mount (order matters: the mount
must never shadow /api). Access control is a single shared-link token checked
by middleware; identity is a credential-less name picker.
"""
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import bootstrap, days, ideas, members
from app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(title=settings.APP_NAME)


# Registered on the Starlette base class so routing 404s and StaticFiles
# errors also come back in the {"error": {code, message}} shape (Caltrain
# precedent).
@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    detail = (
        exc.detail
        if isinstance(exc.detail, dict)
        else {"code": "error", "message": str(exc.detail)}
    )
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "invalid_request", "message": str(exc.errors()[:3])}},
    )


@app.middleware("http")
async def _trip_token_guard(request: Request, call_next):
    """The shared link's ?k= token, sent back as X-Trip-Token, is the only
    access control. Health stays open for Railway checks; static assets are
    public but contain no data."""
    path = request.url.path
    if (
        settings.LINK_TOKEN
        and path.startswith("/api")
        and path != "/api/health"
        and not secrets.compare_digest(
            request.headers.get("X-Trip-Token", ""), settings.LINK_TOKEN
        )
    ):
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "bad_token",
                    "message": "Missing or invalid trip link token.",
                }
            },
        )
    return await call_next(request)


app.include_router(bootstrap.router)
app.include_router(members.router)
app.include_router(ideas.router)
app.include_router(days.router)

# Static frontend — registered last so it never shadows /api routes.
app.mount(
    "/", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="frontend"
)
