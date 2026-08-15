import uuid

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def write_audit(
    db: Session,
    entry_id: uuid.UUID,
    actor: str,
    action: str,
    old_value: str | None,
    new_value: str | None,
) -> None:
    db.add(AuditLog(entry_id=entry_id, actor=actor, action=action, old_value=old_value, new_value=new_value))
    db.commit()
