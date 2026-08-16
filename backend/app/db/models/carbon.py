import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmissionCalculation(Base):
    """One immutable row per (entry, factor-resolution attempt). Never
    updated in place -- a recalculation inserts a new row with
    supersedes_calculation_id pointing at the one it replaces, and marks
    the old row status='superseded'. This is what lets an old approved
    month stay reproducible with its original factor version even after
    the factor library changes."""

    __tablename__ = "emission_calculation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("location.id", ondelete="CASCADE"), nullable=False)
    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entry.id", ondelete="CASCADE"), nullable=False)
    data_point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_point.id", ondelete="CASCADE"), nullable=False)
    reporting_period: Mapped[date] = mapped_column(nullable=False)

    scope: Mapped[int] = mapped_column(nullable=False)
    calculation_method: Mapped[str | None] = mapped_column(String)  # location_based | market_based, Scope 2 only
    status: Mapped[str] = mapped_column(String, nullable=False)  # calculated | unresolved | superseded | void

    activity_value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    activity_unit: Mapped[str] = mapped_column(String, nullable=False)
    normalized_activity_value: Mapped[Decimal | None] = mapped_column(Numeric)
    normalized_activity_unit: Mapped[str | None] = mapped_column(String)

    factor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("emission_factor.id", ondelete="SET NULL"))
    ipcc_reference_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ipcc_reference.id", ondelete="SET NULL"))
    factor_version: Mapped[str | None] = mapped_column(String)
    factor_value: Mapped[Decimal | None] = mapped_column(Numeric)
    factor_unit: Mapped[str | None] = mapped_column(String)
    factor_source: Mapped[str | None] = mapped_column(String)
    factor_effective_year: Mapped[int | None] = mapped_column()

    emissions_kgco2e: Mapped[Decimal | None] = mapped_column(Numeric)
    formula: Mapped[str | None] = mapped_column(Text)
    resolution_reason: Mapped[str | None] = mapped_column(Text)

    calculated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    calculated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))

    supersedes_calculation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("emission_calculation.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class ProductionVolumeMapping(Base):
    """Which data point represents battery production for this tenant/
    location, and how to convert its native unit into the canonical MnAh
    the intensity KPI is defined in. Config, not a hard-coded category
    name -- see Prompt 4."""

    __tablename__ = "production_volume_mapping"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("location.id", ondelete="CASCADE"))
    data_point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_point.id", ondelete="CASCADE"), nullable=False)
    native_unit: Mapped[str] = mapped_column(String, nullable=False)
    canonical_unit: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'MnAh'"))
    conversion_multiplier: Mapped[Decimal] = mapped_column(Numeric, nullable=False, server_default=text("1"))
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
