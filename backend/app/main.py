from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
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
    internal,
    peers,
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
app.include_router(internal.router)
