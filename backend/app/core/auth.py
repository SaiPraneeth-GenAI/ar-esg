import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import get_settings

bearer_scheme = HTTPBearer(auto_error=True)


class CurrentUser:
    def __init__(self, id: str, email: str, roles: list[str], tenant_id: uuid.UUID | None):
        self.id = id
        self.email = email
        self.roles = roles
        self.tenant_id = tenant_id


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> CurrentUser:
    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc

    app_metadata = payload.get("app_metadata") or {}
    tenant_id_raw = app_metadata.get("tenant_id")

    return CurrentUser(
        id=payload["sub"],
        email=payload.get("email", ""),
        roles=app_metadata.get("roles", []),
        tenant_id=uuid.UUID(tenant_id_raw) if tenant_id_raw else None,
    )


def require_roles(*allowed_roles: str):
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not any(role in user.roles for role in allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return dependency
