import uuid
from datetime import date

from sqlalchemy import ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmissionFactor(Base):
    __tablename__ = "emission_factor"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source: Mapped[str] = mapped_column(String, nullable=False)
    gas_type: Mapped[str] = mapped_column(String, nullable=False)
    factor_value: Mapped[float] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False)
    effective_date: Mapped[date] = mapped_column(nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)


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
