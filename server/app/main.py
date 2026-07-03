import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine
from app.db_migrations import run_migrations
from app.errors import http_exception_handler
from app.routers import admin, artifacts, health, job_sessions, legacy, profile
from app.routers import settings as settings_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    run_migrations(engine)
    yield


app = FastAPI(title="Resume Tailor API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^chrome-extension://[a-z]{32}$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.add_exception_handler(HTTPException, http_exception_handler)

for router_module in (
    health,
    settings_router,
    profile,
    job_sessions,
    artifacts,
    admin,
    legacy,
):
    app.include_router(router_module.router)
