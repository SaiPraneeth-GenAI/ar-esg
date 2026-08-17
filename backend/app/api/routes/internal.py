"""TEMPORARY: a one-shot migration-apply endpoint, added only because this
session's local machine could not reach the Supabase pooler directly to run
the usual migrations/*.sql apply script, while the deployed service (this
process) can. Gated by SECRET_KEY (a real deploy secret, not guessable) --
never a permissions bypass beyond "know the same secret the deployed app
already holds". Meant to be removed in the very next commit after use."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter(prefix="/internal", tags=["internal"])

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


@router.post("/apply-migration/{filename}")
def apply_migration(filename: str, secret: str = Query(...)):
    settings = get_settings()
    if not settings.secret_key or secret != settings.secret_key:
        raise HTTPException(status_code=403, detail="Forbidden")
    if "/" in filename or "\\" in filename or not filename.endswith(".sql"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = MIGRATIONS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Migration file not found")
    sql = path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))
    return {"applied": filename}
