import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MappingTemplate(Base):
    """Remembers a confirmed bulk-upload column mapping, keyed by a
    fingerprint of the uploaded file's header row, so the next upload of the
    same file format can skip straight past the mapping step."""

    __tablename__ = "mapping_template"
    __table_args__ = (UniqueConstraint("tenant_id", "category_id", "header_fingerprint"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"), nullable=False)
    header_fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    column_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
