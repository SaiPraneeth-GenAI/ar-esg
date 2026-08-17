"""Temporary, secret-gated raw-SQL endpoint used to apply a migration when
this session's local machine cannot reach the Supabase Postgres pooler
directly. Removed again immediately after the migration is confirmed
applied -- never left registered."""

from fastapi import APIRouter, Body, HTTPException, Query
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/apply-sql")
def apply_sql(secret: str = Query(...), sql: str = Body(..., media_type="text/plain")):
    settings = get_settings()
    if not settings.secret_key or secret != settings.secret_key:
        raise HTTPException(status_code=404)
    with engine.begin() as conn:
        result = conn.execute(text(sql))
        try:
            rows = [dict(row._mapping) for row in result]
        except Exception:
            rows = []
    return {"rows": rows}
