"""Механизм обработчиков (хуков) пользовательских исключительных ситуаций.

Обработчик регистрируется на код ситуации (например, "GB-002") или на "*" (все ситуации):

    @hooks.on("GB-007")
    def notify_admin(error, context): ...

Обработчики вызываются после отката транзакции и записи события в журнал.
Ошибка внутри обработчика не влияет на ответ пользователю.
"""

import logging
from collections import defaultdict
from collections.abc import Callable

from app.errors import GradebookError

log = logging.getLogger("gradebook.hooks")

Hook = Callable[[GradebookError, dict], None]
_registry: dict[str, list[Hook]] = defaultdict(list)


def on(code: str = "*") -> Callable[[Hook], Hook]:
    def decorator(func: Hook) -> Hook:
        _registry[code].append(func)
        return func

    return decorator


def fire(error: GradebookError, context: dict) -> None:
    for hook in [*_registry.get(error.code, []), *_registry.get("*", [])]:
        try:
            hook(error, context)
        except Exception:  # noqa: BLE001 - сбой хука не должен ломать обработку
            log.exception("hook %s failed for %s", getattr(hook, "__name__", hook), error.code)


def clear() -> None:
    _registry.clear()


@on("*")
def log_error(error: GradebookError, context: dict) -> None:
    log.warning("%s %s user=%s path=%s", error.code, error.message, context.get("user"), context.get("path"))


@on("GB-007")
def warn_lockout(error: GradebookError, context: dict) -> None:
    # Место для уведомления администратора (почта, мессенджер) о блокировке учётной записи.
    log.error("account locked: %s", error.details.get("login"))
