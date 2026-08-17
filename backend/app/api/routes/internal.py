"""TEMPORARY: a one-shot migration-apply endpoint -- see the same pattern
used for migration 0013. This session's local machine still can't reach
the Supabase pooler directly, while the deployed service can. SQL is
passed in the request body (the Docker image only COPYs app/, not
migrations/). Gated by SECRET_KEY. Meant to be removed in the very next
commit after use."""

from fastapi import APIRouter, Body, HTTPException, Query
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/apply-sql")
def apply_sql(secret: str = Query(...), sql: str = Body(..., media_type="text/plain")):
    settings = get_settings()
    if not settings.secret_key or secret != settings.secret_key:
        raise HTTPException(status_code=403, detail="Forbidden")
    with engine.begin() as conn:
        conn.execute(text(sql))
    return {"applied": True}
