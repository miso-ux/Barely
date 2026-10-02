"""Template rendering helpers shared by routers."""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth.permissions import Perm
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


@dataclass(frozen=True)
class NavItem:
    label: str  # i18n key
    href: str
    permissions: tuple[str, ...]  # any of these; empty = every signed-in user

    def is_active(self, path: str) -> bool:
        return path == self.href if self.href == "/" else path.startswith(self.href)


# Main navigation. Items appear only when the user holds one of the listed permissions.
NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("nav.dashboard", "/", ()),
    NavItem("nav.orders", "/orders", (Perm.ORDERS_READ_OWN, Perm.ORDERS_READ_ALL)),
    NavItem(
        "nav.exceptions",
        "/exceptions",
        (Perm.EXCEPTIONS_CREATE, Perm.EXCEPTIONS_DECIDE, Perm.ORDERS_READ_ALL),
    ),
    NavItem("nav.warehouse", "/warehouse", (Perm.BARRELS_READ,)),
    NavItem("nav.barrels", "/barrels", (Perm.BARRELS_READ,)),
    NavItem("nav.pumps", "/pumps", (Perm.PUMPS_READ,)),
    NavItem(
        "nav.penalties",
        "/penalties",
        (Perm.ORDERS_READ_OWN, Perm.PENALTIES_MANAGE, Perm.DEBTORS_READ, Perm.ORDERS_READ_ALL),
    ),
    NavItem("nav.invoices", "/invoices", (Perm.INVOICES_READ, Perm.INVOICES_DRAFT)),
    NavItem(
        "nav.reports",
        "/reports",
        (
            Perm.REPORTS_READ_ALL,
            Perm.REPORTS_READ_OPERATIONS,
            Perm.REPORTS_READ_INVOICING,
            Perm.DEBTORS_READ,
        ),
    ),
    NavItem("nav.users", "/users", (Perm.USERS_READ,)),
    NavItem("nav.settings", "/admin/settings", (Perm.SETTINGS_READ,)),
    NavItem(
        "nav.audit",
        "/admin/audit",
        (
            Perm.AUDIT_READ_ALL,
            Perm.AUDIT_READ_USERS,
            Perm.AUDIT_READ_OPERATIONS,
            Perm.AUDIT_READ_INVOICING,
        ),
    ),
)


def nav_for(user: Any) -> list[NavItem]:
    if user is None:
        return []
    return [
        item
        for item in NAV_ITEMS
        if not item.permissions or user.has_any_permission(*item.permissions)
    ]


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
    user = getattr(request.state, "user", None)
    ctx = {
        "current_user": user,
        "unread_notifications": getattr(request.state, "unread_notifications", 0),
        "flashes": request.session.pop(_FLASH_KEY, []),
        "nav_items": nav_for(user),
        "current_path": request.url.path,
        **(context or {}),
    }
    return templates.TemplateResponse(request, template, ctx, status_code=status_code)
