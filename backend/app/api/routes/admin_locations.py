from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import Location, User
from app.db.session import get_db
from app.schemas.users import LocationCreateRequest, LocationResponse, LocationUpdateRequest

router = APIRouter(prefix="/admin/locations", tags=["admin"])


@router.get("", response_model=list[LocationResponse])
def list_locations(
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    locations = db.query(Location).filter(Location.tenant_id == current.tenant_id).order_by(Location.name).all()
    return [LocationResponse(id=loc.id, name=loc.name) for loc in locations]


@router.post("", response_model=LocationResponse, status_code=201)
def create_location(
    payload: LocationCreateRequest,
    current: CurrentUser = Depends(require_roles("Admin")),
    db: Session = Depends(get_db),
):
    if (
        db.query(Location)
        .filter(Location.tenant_id == current.tenant_id, Location.name == payload.name)
        .first()
        is not None
    ):
        raise HTTPException(status_code=409, detail="A plant with this name already exists")

    location = Location(
        tenant_id=current.tenant_id,
        name=payload.name,
        address=payload.address,
        plant_type=payload.plant_type,
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return LocationResponse(id=location.id, name=location.name)


@router.patch("/{location_id}", response_model=LocationResponse)
def update_location(
    location_id: str,
    payload: LocationUpdateRequest,
    current: CurrentUser = Depends(require_roles("Admin")),
    db: Session = Depends(get_db),
):
    location = db.get(Location, location_id)
    if location is None or location.tenant_id != current.tenant_id:
        raise HTTPException(status_code=404, detail="Plant not found")

    location.name = payload.name
    db.commit()
    db.refresh(location)
    return LocationResponse(id=location.id, name=location.name)


@router.delete("/{location_id}", status_code=204)
def delete_location(
    location_id: str,
    current: CurrentUser = Depends(require_roles("Admin")),
    db: Session = Depends(get_db),
):
    location = db.get(Location, location_id)
    if location is None or location.tenant_id != current.tenant_id:
        raise HTTPException(status_code=404, detail="Plant not found")

    in_use = (
        db.query(User)
        .filter(User.tenant_id == current.tenant_id, User.location_scope.any(location.id))
        .first()
        is not None
    )
    if in_use:
        raise HTTPException(status_code=409, detail="This plant is still assigned to one or more users")

    db.delete(location)
    db.commit()
