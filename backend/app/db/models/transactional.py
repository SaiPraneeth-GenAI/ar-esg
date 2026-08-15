import uuid
from datetime import date, datetime

from sqlalchemy import ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Entry(Base):
    __tablename__ = "entry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    data_point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_point.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("location.id", ondelete="CASCADE"), nullable=False)
    period: Mapped[date] = mapped_column(nullable=False)
    value: Mapped[float | None] = mapped_column(Numeric)
    method_of_entry: Mapped[str] = mapped_column(String, nullable=False, default="Manual")
    status: Mapped[str] = mapped_column(String, nullable=False, default="Draft")
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)
    meter_id: Mapped[str | None] = mapped_column(String)
    severity: Mapped[str | None] = mapped_column(String)

    approvals: Mapped[list["Approval"]] = relationship(back_populates="entry")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="entry")


class Approval(Base):
    __tablename__ = "approval"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entry.id", ondelete="CASCADE"), nullable=False)
    approver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String, nullable=False)
    reject_note: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(server_default=text("now()"))

    entry: Mapped["Entry"] = relationship(back_populates="approvals")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entry.id", ondelete="CASCADE"), nullable=False)
    actor: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Attachment(Base):
    __tablename__ = "attachment"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entry.id", ondelete="CASCADE"), nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str | None] = mapped_column(String)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    entry: Mapped["Entry"] = relationship(back_populates="attachments")


class DBConnection(Base):
    __tablename__ = "db_connection"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    db_type: Mapped[str] = mapped_column(String, nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    schema_mapping: Mapped[dict | None] = mapped_column(JSONB)
    sync_schedule: Mapped[str | None] = mapped_column(String)
    last_synced_at: Mapped[datetime | None] = mapped_column()
