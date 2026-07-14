from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

WEB_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = WEB_ROOT / "static"

router = APIRouter(include_in_schema=False)


@router.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/app", status_code=307)


@router.get("/app")
@router.get("/app/")
def application_shell() -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html", media_type="text/html")
