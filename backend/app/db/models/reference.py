import uuid
from datetime import date

from sqlalchemy import ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmissionFactor(Base):
    __tablename__ = "emission_factor"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    scope: Mapped[int] = mapped_column(nullable=False)  # 1, 2, or 3
    source: Mapped[str | None] = mapped_column(String)
    # Substance/fuel name (Scope 1) or a free display label -- not meaningful
    # for Scope 2 (which uses `method`) or Scope 3 (which uses
    # `scope3_category` + `description`).
    gas_type: Mapped[str | None] = mapped_column(String)
    method: Mapped[str | None] = mapped_column(String)  # Scope 2 only: location-based / market-based
    scope3_category: Mapped[str | None] = mapped_column(String)  # Scope 3 only -- GHG Protocol category
    description: Mapped[str | None] = mapped_column(String)
    factor_value: Mapped[float] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False)
    effective_date: Mapped[date] = mapped_column(nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    # Citation/traceability for this number -- required before a factor can
    # be saved, since it ends up in a regulatory report.
    source_reference: Mapped[str | None] = mapped_column(String)
    # Which seeded ipcc_reference row this was derived from via the
    # IPCC-assisted panel. Null for manual entry or bulk upload.
    ipcc_reference_key: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ipcc_reference.id", ondelete="SET NULL"))
    # Soft delete -- a factor already used in a historical calculation is
    # never hard-deleted, just deactivated so it drops out of new entries.
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))


class IpccReference(Base):
    """Read-only, seeded-at-migration-time published emission factors (IPCC
    Vol 2 fuel defaults, IPCC AR4/AR5/AR6 refrigerant GWPs, CEA grid
    electricity, DEFRA Scope 3 proxies). Never user-editable -- powers the
    Add Factor panel's autocomplete/version history/calculation breakdown
    and the bulk-upload IPCC cross-reference. Not itself a tenant's factor
    library; that's EmissionFactor."""

    __tablename__ = "ipcc_reference"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    substance_name: Mapped[str] = mapped_column(String, nullable=False)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    scope: Mapped[int] = mapped_column(nullable=False)
    factor_type: Mapped[str] = mapped_column(String, nullable=False)  # fuel | gwp | odp | grid_electricity | spend_based
    scope3_category: Mapped[str | None] = mapped_column(String)
    publication: Mapped[str] = mapped_column(String, nullable=False)
    effective_year: Mapped[int] = mapped_column(nullable=False)
    ncv_mj_per_unit: Mapped[float | None] = mapped_column(Numeric)
    density_kg_per_unit: Mapped[float | None] = mapped_column(Numeric)
    co2_ef_per_tj: Mapped[float | None] = mapped_column(Numeric)
    oxidation_factor: Mapped[float | None] = mapped_column(Numeric)
    derived_factor_value: Mapped[float] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False)
    source_reference: Mapped[str] = mapped_column(String, nullable=False)


class ComplianceFramework(Base):
    __tablename__ = "compliance_framework"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    field_mapping: Mapped[dict | None] = mapped_column(JSONB)


class Threshold(Base):
    __tablename__ = "threshold"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    data_point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_point.id", ondelete="CASCADE"), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String)
    min_value: Mapped[float | None] = mapped_column(Numeric)
    max_value: Mapped[float | None] = mapped_column(Numeric)
    target_value: Mapped[float | None] = mapped_column(Numeric)
