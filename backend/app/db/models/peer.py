import uuid
from datetime import date, datetime

from sqlalchemy import ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PeerCompany(Base):
    """A benchmark company the tenant tracks for comparison -- Exide,
    Tata Chemicals, an industry average, whatever they want to compare
    themselves against. Tenant-scoped: one tenant's peer list never
    leaks into another's."""

    __tablename__ = "peer_company"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    industry: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class PeerData(Base):
    """One peer company's figures for one period, keyed by the same
    metric keys the Chart Builder's CHARTABLE_METRICS registry uses --
    manually entered (BRSR disclosures, annual reports, etc.), never
    computed. Only Amara Raja's own numbers ever come from approved
    entries; peer numbers are always someone's manual, sourced entry,
    tracked via data_source/source_link/data_confidence."""

    __tablename__ = "peer_data"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    peer_company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("peer_company.id", ondelete="CASCADE"), nullable=False)
    period: Mapped[date] = mapped_column(nullable=False)

    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    data_source: Mapped[str | None] = mapped_column(Text)
    source_link: Mapped[str | None] = mapped_column(Text)
    data_confidence: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
