from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.supabase_admin import SupabaseAdminError, create_auth_user, delete_auth_user, update_auth_user_app_metadata
from app.db.models import Location, User
from app.db.session import get_db
from app.schemas.users import UserCreateRequest, UserResponse, UserUpdateRequest

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_response(user: User, locations_by_id: dict) -> UserResponse:
    location_name = None
    if user.location_scope:
        location_name = locations_by_id.get(user.location_scope[0])
    return UserResponse(id=user.id, email=user.email, roles=user.roles, location_name=location_name, status="Active")


def _locations_by_id(db: Session, tenant_id) -> dict:
    return {loc.id: loc.name for loc in db.query(Location).filter(Location.tenant_id == tenant_id).all()}


@router.get("/users", response_model=list[UserResponse])
def list_users(current: CurrentUser = Depends(require_roles("Admin")), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.tenant_id == current.tenant_id).order_by(User.email).all()
    return [_to_response(u, _locations_by_id(db, current.tenant_id)) for u in users]


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


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    current: CurrentUser = Depends(require_roles("Admin")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.tenant_id != current.tenant_id:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.location_id is not None:
        location = db.get(Location, payload.location_id)
        if location is None or location.tenant_id != current.tenant_id:
            raise HTTPException(status_code=404, detail="Location not found")
        user.location_scope = [payload.location_id]

    if payload.roles is not None:
        user.roles = payload.roles
        try:
            update_auth_user_app_metadata(str(user.id), {"roles": payload.roles, "tenant_id": str(current.tenant_id)})
        except SupabaseAdminError as exc:
            raise HTTPException(status_code=502, detail=f"Could not update auth user: {exc.detail}") from exc

    db.commit()
    db.refresh(user)
    return _to_response(user, _locations_by_id(db, current.tenant_id))


@router.delete("/users/{user_id}", status_code=204)
def remove_user(
    user_id: str,
    current: CurrentUser = Depends(require_roles("Admin")),
    db: Session = Depends(get_db),
):
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="You cannot remove your own account")

    user = db.get(User, user_id)
    if user is None or user.tenant_id != current.tenant_id:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        delete_auth_user(str(user.id))
    except SupabaseAdminError as exc:
        raise HTTPException(status_code=502, detail=f"Could not remove auth user: {exc.detail}") from exc

    db.delete(user)
    db.commit()
