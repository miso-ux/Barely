import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import quote
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.auth.deps import NotAuthenticated, PasswordChangeRequired
from app.config import get_settings
from app.db import get_db
from app.i18n import t
from app.jobs import daily
from app.routers import (
    audit,
    auth,
    barrels,
    dashboard,
    exceptions,
    notifications,
    orders,
    penalties,
    settings,
    users,
)
from app.web import BASE_DIR, flash, render

# Uvicorn configures this logger, so startup messages show up next to its own.
log = logging.getLogger("uvicorn.error")
app_settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start the daily job scheduler with the app (NFR-06). One process, one scheduler."""
    scheduler: BackgroundScheduler | None = None
    if app_settings.scheduler_enabled:
        scheduler = BackgroundScheduler(timezone=ZoneInfo(app_settings.timezone))
        scheduler.add_job(
            daily.run,
            CronTrigger(hour=app_settings.daily_job_hour, minute=0),
            id="daily",
            misfire_grace_time=6 * 3600,
            coalesce=True,
        )
        scheduler.start()
        log.info(
            "daily job scheduled at %02d:00 %s", app_settings.daily_job_hour, app_settings.timezone
        )
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


app = FastAPI(title="Barely", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=app_settings.secret_key,
    https_only=app_settings.secure_cookies or app_settings.app_env == "production",
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(dashboard.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(settings.router)
app.include_router(audit.router)
app.include_router(barrels.router)
app.include_router(orders.router)
app.include_router(exceptions.router)
app.include_router(notifications.router)
app.include_router(penalties.router)


@app.exception_handler(NotAuthenticated)
def _not_authenticated(request: Request, exc: NotAuthenticated):
    return RedirectResponse(f"/login?next={quote(request.url.path)}", status.HTTP_303_SEE_OTHER)


@app.exception_handler(PasswordChangeRequired)
def _password_change_required(request: Request, exc: PasswordChangeRequired):
    flash(request, t("auth.password_change_required"), "warning")
    return RedirectResponse("/password", status.HTTP_303_SEE_OTHER)


@app.exception_handler(StarletteHTTPException)
def _http_error(request: Request, exc: StarletteHTTPException):
    message_key = {
        status.HTTP_403_FORBIDDEN: "error.forbidden",
        status.HTTP_404_NOT_FOUND: "error.not_found",
    }.get(exc.status_code, "error.generic")
    return render(
        request,
        "errors/error.html",
        {"status": exc.status_code, "message": t(message_key)},
        status_code=exc.status_code,
    )


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except SQLAlchemyError:
        return {"status": "degraded"}
