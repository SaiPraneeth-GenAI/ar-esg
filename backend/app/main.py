from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin_locations, admin_users, dashboard, health
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
app.include_router(dashboard.router)
