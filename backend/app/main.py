import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# No handler was configured anywhere, so custom loggers (e.g.
# app/services/peer_extraction.py's token/cost telemetry) were silently
# dropped instead of reaching Render's log stream -- this gives every
# logger a stdout handler at INFO level.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

from app.api.routes import (
    admin_demo,
    admin_emission_factors,
    admin_locations,
    admin_mapping_templates,
    admin_tenant_settings,
    admin_users,
    carbon,
    charts,
    dashboard,
    entries,
    health,
    intensity,
    notifications,
    peers,
    reports,
    safety,
    targets,
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="Envigo API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(admin_users.router)
app.include_router(admin_locations.router)
app.include_router(admin_tenant_settings.router)
app.include_router(dashboard.router)
app.include_router(entries.router)
app.include_router(admin_mapping_templates.router)
app.include_router(admin_emission_factors.router)
app.include_router(carbon.router)
app.include_router(targets.router)
app.include_router(intensity.router)
app.include_router(safety.router)
app.include_router(charts.router)
app.include_router(peers.router)
app.include_router(reports.router)
app.include_router(admin_demo.router)
app.include_router(notifications.router)
