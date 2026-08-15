import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import Category, MappingTemplate
from app.db.session import get_db
from app.schemas.mapping import MappingTemplateOut

router = APIRouter(prefix="/admin/mapping-templates", tags=["admin"])


@router.get("", response_model=list[MappingTemplateOut])
def list_templates(current: CurrentUser = Depends(require_roles("Admin", "Approver")), db: Session = Depends(get_db)):
    rows = (
        db.query(MappingTemplate, Category.name)
        .join(Category, Category.id == MappingTemplate.category_id)
        .filter(MappingTemplate.tenant_id == current.tenant_id)
        .order_by(Category.name)
        .all()
    )
    return [
        MappingTemplateOut(
            id=t.id,
            category_id=t.category_id,
            category_name=cname,
            header_fingerprint=t.header_fingerprint,
            column_mapping=t.column_mapping,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t, cname in rows
    ]


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    template = db.get(MappingTemplate, template_id)
    if template is None or template.tenant_id != current.tenant_id:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(template)
    db.commit()
