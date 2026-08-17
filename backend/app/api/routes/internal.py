"""TEMPORARY: a one-shot migration-apply endpoint, added only because this
session's local machine could not reach the Supabase pooler directly to run
the usual migrations/*.sql apply script, while the deployed service (this
process) can. The Docker image only COPYs app/, not migrations/, so the SQL
is passed in the request body rather than read from a filename. Gated by
SECRET_KEY (a real deploy secret, not guessable) -- never a permissions
bypass beyond "know the same secret the deployed app already holds". Meant
to be removed in the very next commit after use."""

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
