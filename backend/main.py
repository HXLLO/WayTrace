from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from loguru import logger

from config import settings
from routers import health, scan
from store import store


def _configure_logging() -> None:
    logger.remove()
    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    logger.add(sys.stderr, format=fmt, level=settings.log_level)


_configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("WayTrace starting up")
    health.set_start_time()
    await store.start_cleanup_loop()
    yield
    logger.info("WayTrace shutting down")
    await store.stop_cleanup_loop()


app = FastAPI(
    title="WayTrace",
    description="OSINT tool using the Wayback Machine to reconstruct domain history",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
)

app.include_router(scan.router)
app.include_router(health.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
async def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")
