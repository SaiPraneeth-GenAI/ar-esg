import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RevenueMapping(Base):
    """Which data point represents revenue for this tenant/location, and how
    to convert its native unit into the canonical INR Cr the revenue-
    intensity KPIs are defined in. Config, not a hard-coded category name --
    same shape and reasoning as ProductionVolumeMapping (carbon.py)."""

    __tablename__ = "revenue_mapping"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("location.id", ondelete="CASCADE"))
    data_point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_point.id", ondelete="CASCADE"), nullable=False)
    native_unit: Mapped[str] = mapped_column(String, nullable=False)
    canonical_unit: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'INR Cr'"))
    conversion_multiplier: Mapped[Decimal] = mapped_column(Numeric, nullable=False, server_default=text("1"))
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
