"""Точка входа приложения GradeBook."""

import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app import __version__, audit, hooks, web
from app.api import router as api_router
from app.config import settings
from app.db import SessionLocal, engine
from app.errors import GradebookError
from app.models import Base

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger("gradebook")


def _setup_file_logging() -> None:
    """Дублирует журнал приложения и uvicorn в файл LOG_DIR/gradebook.log (том контейнера)."""
    if not settings.log_dir:
        return
    path = Path(settings.log_dir)
    try:
        path.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path / "gradebook.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    except OSError as exc:
        log.warning("file logging disabled: %s", exc)
        return
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    for name in ("", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).addHandler(handler)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _setup_file_logging()
    # До внедрения миграций (ЛР8) схема создаётся при старте.
    Base.metadata.create_all(engine)
    log.info("GradeBook %s started, env=%s", __version__, settings.environment)
    yield


app = FastAPI(
    title="GradeBook",
    description="АИС учёта успеваемости студентов",
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.cookie_secure,
)
app.include_router(api_router)
app.include_router(web.router)


@app.get("/health", tags=["service"], summary="Проверка работоспособности")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_state = "ok"
    except Exception as exc:  # noqa: BLE001
        log.error("health: database unavailable: %s", exc)
        return JSONResponse({"status": "fail", "db": "unavailable", "version": __version__}, status_code=503)
    return {"status": "ok", "db": db_state, "version": __version__}


def _user_of(request: Request):
    user = getattr(request.state, "user", None)
    if user is None and "session" in request.scope:
        return request.session.get("user_id")
    return user.id if user else None


@app.exception_handler(GradebookError)
async def gradebook_error_handler(request: Request, error: GradebookError):
    """Ф6: операция уже откачена (сессия БД закрыта без commit); пишем журнал, вызываем хуки, отвечаем."""
    user_id = _user_of(request)
    if error.status_code != 401:
        with SessionLocal() as db:
            db.add(
                audit.AuditLog(
                    user_id=user_id,
                    action="error",
                    entity=error.code,
                    details={"message": error.message, "path": request.url.path, **error.details},
                )
            )
            db.commit()
    hooks.fire(error, {"user": user_id, "path": request.url.path, "method": request.method})
    if web.is_web_request(request):
        return web.web_error_response(request, error.message, error)
    return JSONResponse(error.to_dict(), status_code=error.status_code)


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, error: ValidationError):
    """Ошибки проверки полей веб-форм (в API их обрабатывает сам FastAPI)."""
    fields = ", ".join(str(e["loc"][-1]) for e in error.errors() if e.get("loc"))
    message = f"Проверьте поля: {fields}" if fields else "Проверьте введённые данные"
    if web.is_web_request(request):
        return web.web_error_response(request, message, error)
    details = error.errors(include_url=False, include_context=False)
    return JSONResponse({"code": "GB-422", "message": message, "details": details}, status_code=422)
