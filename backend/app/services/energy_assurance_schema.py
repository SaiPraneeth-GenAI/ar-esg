import logging
from pathlib import Path

from app.db.session import engine

logger = logging.getLogger(__name__)
MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "0021_energy_assurance.sql"


def ensure_energy_assurance_schema() -> None:
    """Apply only the isolated showcase schema, idempotently, at startup.

    This project has no migration runner in its deployment image. The
    advisory transaction lock prevents two rollout replicas from racing.
    Existing ESG tables are neither altered nor written by this migration.
    """
    if engine is None:
        logger.info("DATABASE_URL is not configured; skipping Energy Assurance schema check")
        return
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    with engine.begin() as connection:
        connection.exec_driver_sql("select pg_advisory_xact_lock(2026082101)")
        connection.exec_driver_sql(sql)
    logger.info("Energy Assurance schema is ready")
