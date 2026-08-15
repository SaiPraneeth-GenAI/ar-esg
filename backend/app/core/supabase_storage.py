import httpx

from app.core.config import get_settings

BUCKET = "attachments"

_bucket_ready = False


def _headers() -> dict:
    settings = get_settings()
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }


def _ensure_bucket() -> None:
    global _bucket_ready
    if _bucket_ready:
        return
    settings = get_settings()
    httpx.post(
        f"{settings.supabase_url}/storage/v1/bucket",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"id": BUCKET, "name": BUCKET, "public": True},
        timeout=15,
    )
    # Ignore the response: 200 means created, 400/409 means it already exists -- either way it's usable now.
    _bucket_ready = True


def upload_file(path: str, content: bytes, content_type: str) -> str:
    _ensure_bucket()
    settings = get_settings()
    resp = httpx.post(
        f"{settings.supabase_url}/storage/v1/object/{BUCKET}/{path}",
        headers={**_headers(), "Content-Type": content_type or "application/octet-stream"},
        content=content,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"upload failed: {resp.status_code} {resp.text}")
    return f"{settings.supabase_url}/storage/v1/object/public/{BUCKET}/{path}"
