"""Журнал событий (Ф7)."""

from sqlalchemy.orm import Session

from app.models import AppUser, AuditLog


def write(
    db: Session,
    user: AppUser | None,
    action: str,
    entity: str | None = None,
    entity_id: int | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details,
        )
    )
