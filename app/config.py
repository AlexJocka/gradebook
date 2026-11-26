"""Настройки приложения. Все значения, зависящие от окружения, берутся из переменных окружения."""

import os
import secrets


class Settings:
    def __init__(self) -> None:
        # По умолчанию SQLite, чтобы прототип запускался без СУБД; в контейнерах задаётся PostgreSQL.
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./gradebook.db")
        # Ключ подписи сессий. Если не задан, генерируется при старте (сессии сбросятся после перезапуска).
        self.secret_key: str = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
        self.session_max_age: int = int(os.getenv("SESSION_MAX_AGE", "1800"))  # 30 минут (п. 4.1.8 ТЗ)
        self.max_login_attempts: int = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
        self.lockout_minutes: int = int(os.getenv("LOCKOUT_MINUTES", "15"))
        self.environment: str = os.getenv("APP_ENV", "dev")
        # Передавать cookie сессии только по HTTPS (включается, когда перед приложением есть TLS).
        self.cookie_secure: bool = os.getenv("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")


settings = Settings()
