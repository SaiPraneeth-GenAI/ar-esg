import uuid

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import get_settings

bearer_scheme = HTTPBearer(auto_error=True)

# Supabase signs tokens with a per-project asymmetric key (ES256/RS256), verified
# against its published JWKS -- not the legacy shared HS256 secret.
_jwks_cache: dict | None = None


def _fetch_jwks() -> dict:
    settings = get_settings()
    resp = httpx.get(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _find_signing_key(kid: str) -> dict | None:
    global _jwks_cache
    if _jwks_cache is None:
        _jwks_cache = _fetch_jwks()

    for key in _jwks_cache.get("keys", []):
        if key.get("kid") == kid:
            return key

    # key rotated since we cached -- refresh once and retry
    _jwks_cache = _fetch_jwks()
    for key in _jwks_cache.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


class CurrentUser:
    def __init__(self, id: str, email: str, roles: list[str], tenant_id: uuid.UUID | None):
        self.id = id
        self.email = email
        self.roles = roles
        self.tenant_id = tenant_id


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> CurrentUser:
    token = credentials.credentials
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = _find_signing_key(kid) if kid else None
        if key is None:
            raise JWTError("no matching signing key")

        payload = jwt.decode(
            token,
            key,
            algorithms=[key.get("alg", "ES256")],
            audience="authenticated",
        )
    except (JWTError, httpx.HTTPError) as exc:
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
