import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ColumnMappingMemory(Base):
    """Remembers what ONE column header means, independent of the rest of
    the file's headers -- unlike MappingTemplate (keyed by a hash of the
    WHOLE header set, so a single renamed/added column is a total cache
    miss), this is consulted per-header, so a customer's confirmed mapping
    for "Grid Power" -> Grid Electricity Consumed keeps working even if
    they add or reorder other columns. Populated automatically whenever a
    mapping is confirmed (see save_mapping_template / AI-mapping confirm),
    never written directly by a customer."""

    __tablename__ = "column_mapping_memory"
    __table_args__ = (UniqueConstraint("tenant_id", "category_id", "source_header"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"), nullable=False)
    source_header: Mapped[str] = mapped_column(String, nullable=False)  # normalized (see services/mapping.normalize)
    target_type: Mapped[str] = mapped_column(String, nullable=False)  # "metadata" | "data_point"
    target: Mapped[str] = mapped_column(String, nullable=False)  # "period" | "note" | data_point id (as text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # "manual_confirm" | "ai_confirm"
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
