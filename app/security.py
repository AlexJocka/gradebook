"""Аутентификация, хранение паролей и проверка ролей (Ф5, п. 4.1.8 ТЗ)."""

import base64
import binascii
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.errors import AccessDenied, NotAuthenticated, TooManyAttempts
from app.models import AppUser


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def authenticate(db: Session, login: str, password: str) -> AppUser:
    """Проверяет логин и пароль, ведёт счётчик неудачных попыток (GB-007)."""
    from app import audit

    user = db.scalar(select(AppUser).where(AppUser.login == login))
    if user is None:
        audit.write(db, None, "login_failed", details={"login": login})
        db.commit()
        raise NotAuthenticated("Неверный логин или пароль")

    locked_until = _aware(user.locked_until)
    if locked_until and locked_until > _now():
        raise TooManyAttempts(
            "Учётная запись временно заблокирована после нескольких неудачных попыток входа",
            login=login,
            locked_until=locked_until.isoformat(),
        )
    if user.is_blocked:
        raise AccessDenied("Учётная запись заблокирована администратором")

    if not verify_password(password, user.password_hash):
        user.failed_attempts += 1
        audit.write(db, user, "login_failed", "app_user", user.id)
        if user.failed_attempts >= settings.max_login_attempts:
            user.failed_attempts = 0
            user.locked_until = _now() + timedelta(minutes=settings.lockout_minutes)
            db.commit()
            raise TooManyAttempts(
                f"Превышено число попыток входа, учётная запись заблокирована на {settings.lockout_minutes} мин.",
                login=login,
            )
        db.commit()
        raise NotAuthenticated("Неверный логин или пароль")

    user.failed_attempts = 0
    user.locked_until = None
    audit.write(db, user, "login", "app_user", user.id)
    db.commit()
    return user


def _basic_credentials(request: Request) -> tuple[str, str] | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return None
    try:
        login, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError):
        return None
    return login, password


def current_user(request: Request, db: Session = Depends(get_db)) -> AppUser:
    """Пользователь из сессии (веб-интерфейс) или из заголовка Basic (REST API)."""
    user_id = request.session.get("user_id") if "session" in request.scope else None
    if user_id:
        user = db.get(AppUser, user_id)
        if user and not user.is_blocked:
            return user
        request.session.clear()
    creds = _basic_credentials(request)
    if creds:
        return authenticate(db, *creds)
    raise NotAuthenticated("Требуется вход в систему")


def require(*roles: str):
    """Зависимость FastAPI: пропускает только пользователей с указанными ролями."""

    def checker(request: Request, user: AppUser = Depends(current_user)) -> AppUser:
        request.state.user = user
        if roles and user.role not in roles:
            raise AccessDenied("Недостаточно прав для выполнения операции", role=user.role)
        return user

    return checker
