import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.models import Notification
from app.db.session import get_db
from app.schemas.notifications import NotificationListResponse, NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Newest 30 for the dropdown, plus a true unread count (not capped by
    that limit) for the bell badge."""
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == current.id)
        .order_by(Notification.created_at.desc())
        .limit(30)
        .all()
    )
    unread_count = (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == current.id, Notification.read_at.is_(None))
        .scalar()
    )
    return NotificationListResponse(
        notifications=[
            NotificationOut(
                id=n.id, kind=n.kind, title=n.title, body=n.body, link=n.link, read_at=n.read_at, created_at=n.created_at
            )
            for n in rows
        ],
        unread_count=unread_count or 0,
    )


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = db.get(Notification, notification_id)
    if notification is None or str(notification.user_id) != str(current.id):
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
    return NotificationOut(
        id=notification.id,
        kind=notification.kind,
        title=notification.title,
        body=notification.body,
        link=notification.link,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


@router.post("/read-all")
def mark_all_read(
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(Notification).filter(Notification.user_id == current.id, Notification.read_at.is_(None)).update(
        {"read_at": datetime.now(timezone.utc)}, synchronize_session=False
    )
    db.commit()
    return {"status": "ok"}
