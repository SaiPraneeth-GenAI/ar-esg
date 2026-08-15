import httpx

from app.core.config import get_settings


class SupabaseAdminError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _headers() -> dict:
    settings = get_settings()
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


def create_auth_user(email: str, password: str, app_metadata: dict) -> dict:
    """Creates a Supabase Auth user directly (no invite email) via the admin API.
    Only ever called from the backend with SUPABASE_SERVICE_ROLE_KEY.
    """
    settings = get_settings()
    resp = httpx.post(
        f"{settings.supabase_url}/auth/v1/admin/users",
        headers=_headers(),
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "app_metadata": app_metadata,
        },
        timeout=15,
    )
    if resp.status_code >= 400:
        raise SupabaseAdminError(resp.status_code, resp.text)
    return resp.json()


def get_auth_user_by_email(email: str) -> dict | None:
    settings = get_settings()
    resp = httpx.get(
        f"{settings.supabase_url}/auth/v1/admin/users",
        headers=_headers(),
        params={"email": email},
        timeout=15,
    )
    if resp.status_code >= 400:
        raise SupabaseAdminError(resp.status_code, resp.text)
    users = resp.json().get("users", [])
    return users[0] if users else None
