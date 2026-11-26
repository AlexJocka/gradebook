"""Пользовательские исключительные ситуации (п. 4.2.6 ТЗ, таблица 5)."""


class GradebookError(Exception):
    """Базовая пользовательская исключительная ситуация."""

    code = "GB-000"
    status_code = 400

    def __init__(self, message: str, **details) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class DisciplineNotInPlan(GradebookError):
    code = "GB-001"
    status_code = 422


class InvalidResult(GradebookError):
    code = "GB-002"
    status_code = 422


class DuplicateRecord(GradebookError):
    code = "GB-003"
    status_code = 409


class StudentExpelled(GradebookError):
    code = "GB-004"
    status_code = 409


class ControlFormLocked(GradebookError):
    code = "GB-005"
    status_code = 409


class AccessDenied(GradebookError):
    code = "GB-006"
    status_code = 403


class TooManyAttempts(GradebookError):
    code = "GB-007"
    status_code = 429


class NotFound(GradebookError):
    code = "GB-008"
    status_code = 404


class NotAuthenticated(GradebookError):
    """Пользователь не вошёл в систему (не входит в таблицу 5, служебная ситуация)."""

    code = "GB-401"
    status_code = 401
