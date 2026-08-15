import uuid
from datetime import date, datetime

from sqlalchemy import ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Rollup(Base):
    __tablename__ = "rollup"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("location.id", ondelete="CASCADE"), nullable=False)
    period: Mapped[date] = mapped_column(nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    aggregated_value: Mapped[float | None] = mapped_column(Numeric)
    target_value: Mapped[float | None] = mapped_column(Numeric)
    benchmark_value: Mapped[float | None] = mapped_column(Numeric)


class ComplianceReport(Base):
    __tablename__ = "compliance_report"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    framework: Mapped[str] = mapped_column(String, nullable=False)
    period: Mapped[date] = mapped_column(nullable=False)
    generated_file_url: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class ReportRequest(Base):
    __tablename__ = "report_request"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    report_type: Mapped[str] = mapped_column(String, nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    parameters: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String, nullable=False, default="Pending")
    generated_file_url: Mapped[str | None] = mapped_column(Text)
    source_rollup_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column()


class MailingList(Base):
    __tablename__ = "mailing_list"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    recipients: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    schedule: Mapped[str | None] = mapped_column(String)


class EmailLog(Base):
    __tablename__ = "email_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    recipient: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    related_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String, nullable=False)
