import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    industry_vertical: Mapped[str | None] = mapped_column(String)
    branding_config: Mapped[dict | None] = mapped_column(JSONB)
    schema_mode: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    locations: Mapped[list["Location"]] = relationship(back_populates="tenant")
    users: Mapped[list["User"]] = relationship(back_populates="tenant")
    categories: Mapped[list["Category"]] = relationship(back_populates="tenant")


class Location(Base):
    __tablename__ = "location"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    plant_type: Mapped[str | None] = mapped_column(String)
    parent_location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("location.id", ondelete="SET NULL"))

    tenant: Mapped["Tenant"] = relationship(back_populates="locations")


class User(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    roles: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default=text("'{}'"))
    location_scope: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    auth_provider: Mapped[str | None] = mapped_column(String)

    tenant: Mapped["Tenant"] = relationship(back_populates="users")


class Category(Base):
    __tablename__ = "category"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    industry_pack: Mapped[str | None] = mapped_column(String)
    display_order: Mapped[int | None] = mapped_column()

    tenant: Mapped["Tenant"] = relationship(back_populates="categories")
    data_points: Mapped[list["DataPoint"]] = relationship(back_populates="category")


class DataPoint(Base):
    __tablename__ = "data_point"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    unit: Mapped[str | None] = mapped_column(String)
    input_type: Mapped[str | None] = mapped_column(String)
    validation_rules: Mapped[dict | None] = mapped_column(JSONB)
    conditional_on: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_point.id", ondelete="SET NULL"))
    framework_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String))

    category: Mapped["Category"] = relationship(back_populates="data_points")
