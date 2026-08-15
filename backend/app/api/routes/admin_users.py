from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.supabase_admin import SupabaseAdminError, create_auth_user
from app.db.models import Location, User
from app.db.session import get_db
from app.schemas.users import LocationResponse, UserCreateRequest, UserResponse

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_response(user: User, locations_by_id: dict) -> UserResponse:
    location_name = None
    if user.location_scope:
        location_name = locations_by_id.get(user.location_scope[0])
    return UserResponse(id=user.id, email=user.email, roles=user.roles, location_name=location_name, status="Active")


@router.get("/users", response_model=list[UserResponse])
def list_users(current: CurrentUser = Depends(require_roles("Admin")), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.tenant_id == current.tenant_id).order_by(User.email).all()
    locations_by_id = {loc.id: loc.name for loc in db.query(Location).filter(Location.tenant_id == current.tenant_id).all()}
    return [_to_response(u, locations_by_id) for u in users]


@router.get("/locations", response_model=list[LocationResponse])
def list_locations(
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    locations = db.query(Location).filter(Location.tenant_id == current.tenant_id).order_by(Location.name).all()
    return [LocationResponse(id=loc.id, name=loc.name) for loc in locations]


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(
    payload: UserCreateRequest,
    current: CurrentUser = Depends(require_roles("Admin")),
    db: Session = Depends(get_db),
):
    location = db.get(Location, payload.location_id)
    if location is None or location.tenant_id != current.tenant_id:
        raise HTTPException(status_code=404, detail="Location not found")

    if db.query(User).filter(User.email == payload.email).first() is not None:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    try:
        auth_user = create_auth_user(
            email=payload.email,
            password=payload.password,
            app_metadata={"roles": payload.roles, "tenant_id": str(current.tenant_id)},
        )
    except SupabaseAdminError as exc:
        raise HTTPException(status_code=502, detail=f"Could not create auth user: {exc.detail}") from exc

    user = User(
        id=auth_user["id"],
        tenant_id=current.tenant_id,
        email=payload.email,
        roles=payload.roles,
        location_scope=[payload.location_id],
        auth_provider="email",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _to_response(user, {location.id: location.name})
