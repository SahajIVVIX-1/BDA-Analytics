"""FastAPI application entry point.

Run (from backend/):  uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from app import __version__
from app.api import analytics, ingestion, performance, posts
from app.api.json import MongoJSONResponse
from app.config import get_settings
from app.database import mongo
from app.schemas.models import Health

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    mongo.close_client()


app = FastAPI(
    title="Social Media Big Data Analytics API",
    version=__version__,
    description="Sentiment, topic, trend, engagement and anomaly analytics over social-media posts stored in MongoDB.",
    default_response_class=MongoJSONResponse,
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["GET", "POST"],
                   allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.exception_handler(ServerSelectionTimeoutError)
async def mongo_down(_: Request, exc: ServerSelectionTimeoutError):
    log.error("MongoDB unavailable: %s", exc)
    return JSONResponse(status_code=503, content={"detail": "database unavailable"})


@app.exception_handler(PyMongoError)
async def mongo_error(_: Request, exc: PyMongoError):
    log.exception("MongoDB error")
    return JSONResponse(status_code=500, content={"detail": "database error"})


@app.get("/api/health", response_model=Health, tags=["health"])
def health():
    settings = get_settings()
    ok = mongo.ping()
    out = {"status": "ok" if ok else "degraded", "mongodb": ok, "database": settings.mongo_db, "version": __version__}
    if ok:
        db = mongo.get_db()
        out["posts"] = db[mongo.POSTS].estimated_document_count()
        out["processed_posts"] = db[mongo.POSTS].count_documents({"processed": True}) if out["posts"] < 50_000 else \
            out["posts"] - db[mongo.POSTS].count_documents({"processed": False}, hint="unprocessed_partial")
        out["server_version"] = mongo.get_client().server_info().get("version")
    return out


app.include_router(analytics.router)
app.include_router(posts.router)
app.include_router(ingestion.router)
app.include_router(performance.router)
