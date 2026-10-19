import json
import uuid

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import get_settings

bearer_scheme = HTTPBearer(auto_error=True)

# Both Supabase and Cognito use asymmetric signing keys. API Gateway validates
# Cognito JWTs before invoking Lambda; direct/local requests still verify JWKS.
_jwks_cache: dict[str, dict] = {}


def _issuer_and_audience() -> tuple[str, str]:
    settings = get_settings()
    if settings.auth_provider == "cognito":
        issuer = f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}"
        return issuer, settings.cognito_app_client_id
    return f"{settings.supabase_url}/auth/v1", "authenticated"


def _fetch_jwks(issuer: str) -> dict:
    resp = httpx.get(f"{issuer}/.well-known/jwks.json", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _find_signing_key(issuer: str, kid: str) -> dict | None:
    keys = _jwks_cache.get(issuer)
    if keys is None:
        keys = _fetch_jwks(issuer)
        _jwks_cache[issuer] = keys

    for key in keys.get("keys", []):
        if key.get("kid") == kid:
            return key

    # key rotated since we cached -- refresh once and retry
    keys = _fetch_jwks(issuer)
    _jwks_cache[issuer] = keys
    for key in keys.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


class CurrentUser:
    def __init__(self, id: str, email: str, roles: list[str], tenant_id: uuid.UUID | None):
        self.id = id
        self.email = email
        self.roles = roles
        self.tenant_id = tenant_id


def _roles_from_claims(claims: dict) -> list[str]:
    app_metadata = claims.get("app_metadata") or {}
    raw_roles = claims.get("custom:roles") or claims.get("cognito:groups") or app_metadata.get("roles") or []
    if isinstance(raw_roles, list):
        return [str(role) for role in raw_roles]
    if isinstance(raw_roles, str):
        try:
            parsed = json.loads(raw_roles)
            if isinstance(parsed, list):
                return [str(role) for role in parsed]
        except json.JSONDecodeError:
            pass
        return [role.strip() for role in raw_roles.split(",") if role.strip()]
    return []


def _current_user_from_claims(claims: dict) -> CurrentUser:
    app_metadata = claims.get("app_metadata") or {}
    tenant_id_raw = claims.get("custom:tenant_id") or app_metadata.get("tenant_id")
    # custom:user_id preserves the existing app_user UUID and every historical
    # foreign key while Cognito keeps its own immutable subject separately.
    user_id = claims.get("custom:user_id") or claims.get("sub")
    return CurrentUser(
        id=user_id,
        email=claims.get("email", ""),
        roles=_roles_from_claims(claims),
        tenant_id=uuid.UUID(tenant_id_raw) if tenant_id_raw else None,
    )


def _api_gateway_claims(request: Request) -> dict | None:
    event = request.scope.get("aws.event") or {}
    return (((event.get("requestContext") or {}).get("authorizer") or {}).get("jwt") or {}).get("claims")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    gateway_claims = _api_gateway_claims(request)
    if gateway_claims:
        return _current_user_from_claims(gateway_claims)

    token = credentials.credentials
    try:
        issuer, audience = _issuer_and_audience()
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = _find_signing_key(issuer, kid) if kid else None
        if key is None:
            raise JWTError("no matching signing key")

        payload = jwt.decode(
            token,
            key,
            algorithms=[key.get("alg", "RS256")],
            audience=audience,
            issuer=issuer,
        )
    except (JWTError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc

    return _current_user_from_claims(payload)


def require_roles(*allowed_roles: str):
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not any(role in user.roles for role in allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return dependency
