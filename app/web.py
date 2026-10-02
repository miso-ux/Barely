"""Template rendering helpers shared by routers."""

from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.i18n import t

BASE_DIR = Path(__file__).parent
_FLASH_KEY = "_flash"
_LOCAL_TZ = ZoneInfo(get_settings().timezone)

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["t"] = t


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(_LOCAL_TZ).strftime("%d.%m.%Y %H:%M")


def format_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


templates.env.filters["dt"] = format_datetime
templates.env.filters["d"] = format_date


def flash(request: Request, message: str, category: str = "info") -> None:
    """Queue a message for the next rendered page. `message` is already translated.

    Assign a new list instead of appending: Starlette only persists the session cookie when
    it sees a top-level assignment, nested mutations are invisible to it.
    """
    queued = list(request.session.get(_FLASH_KEY, []))
    queued.append({"text": message, "category": category})
    request.session[_FLASH_KEY] = queued


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    ctx = {
        "current_user": getattr(request.state, "user", None),
        "unread_notifications": getattr(request.state, "unread_notifications", 0),
        "flashes": request.session.pop(_FLASH_KEY, []),
        **(context or {}),
    }
    return templates.TemplateResponse(request, template, ctx, status_code=status_code)
