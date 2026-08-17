"""Tenant-wide workflow settings, Admin-only. Currently just one switch:
auto-approve entries a Manager submits, instead of leaving them in the
Approver's queue."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import Tenant
from app.db.session import get_db

router = APIRouter(prefix="/admin/tenant-settings", tags=["admin"])


class TenantSettingsOut(BaseModel):
    auto_approve_entries: bool


class TenantSettingsUpdate(BaseModel):
    auto_approve_entries: bool


def _get_tenant(db: Session, current: CurrentUser) -> Tenant:
    tenant = db.get(Tenant, current.tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found for the current user")
    return tenant


@router.get("", response_model=TenantSettingsOut)
def get_tenant_settings(
    current: CurrentUser = Depends(require_roles("Admin")),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant(db, current)
    return TenantSettingsOut(auto_approve_entries=tenant.auto_approve_entries)


@router.patch("", response_model=TenantSettingsOut)
def update_tenant_settings(
    payload: TenantSettingsUpdate,
    current: CurrentUser = Depends(require_roles("Admin")),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant(db, current)
    tenant.auto_approve_entries = payload.auto_approve_entries
    db.commit()
    db.refresh(tenant)
    return TenantSettingsOut(auto_approve_entries=tenant.auto_approve_entries)
