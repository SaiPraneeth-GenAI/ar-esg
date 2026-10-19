from datetime import date

from mangum import Mangum

from app.main import app


# API Gateway HTTP API payload v2 adapter. Lifespan is disabled because the
# application has no startup/shutdown hooks and this reduces cold-start work.
_http_handler = Mangum(app, lifespan="off")


def _run_ops_task(event: dict) -> dict:
    """Operator tasks, reachable only by invoking this function directly
    with IAM (lambda:InvokeFunction) -- an API Gateway event is always an
    HTTP payload and never carries a top-level "oceans_task" key."""
    from app.db.session import SessionLocal
    from app.services import live_demo_seed

    task = event["oceans_task"]
    admin_email = event.get("admin_email", "saipraneeth836@gmail.com")
    db = SessionLocal()
    try:
        if task == "inspect":
            return live_demo_seed.inspect(db, admin_email)
        if task == "seed_live_demo":
            live_months = [date.fromisoformat(m) for m in event.get("live_months", ["2026-09-01", "2026-10-01"])]
            scope3_start = date.fromisoformat(event.get("scope3_start", "2024-08-01"))
            return live_demo_seed.seed(db, admin_email, live_months, scope3_start, int(event.get("max_rows", 900)))
        return {"error": f"unknown task {task!r}"}
    finally:
        db.close()


def handler(event, context):
    if isinstance(event, dict) and "oceans_task" in event:
        return _run_ops_task(event)
    return _http_handler(event, context)
